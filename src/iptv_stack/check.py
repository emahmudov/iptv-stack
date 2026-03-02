from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import ssl
import time

from .models import StreamEntry


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _is_http_url(url: str) -> bool:
    scheme = (urlparse(url).scheme or "").lower()
    return scheme in {"http", "https"}


def _fetch_sample(
    url: str,
    timeout: int,
    max_bytes: int = 8192,
    use_range: bool = True,
) -> Tuple[bool, int | None, str, bytes, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Codex IPTV Checker)",
        "Accept": "*/*",
    }
    if use_range:
        headers["Range"] = f"bytes=0-{max(1, max_bytes - 1)}"

    req = Request(url=url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            body = resp.read(max_bytes)
            status = resp.getcode()
            content_type = resp.headers.get("Content-Type", "")
            return status < 400, status, content_type, body, ""
    except HTTPError as exc:
        body = b""
        try:
            body = exc.read(max_bytes)
        except Exception:  # noqa: BLE001
            pass
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return False, exc.code, content_type, body, str(exc)
    except (URLError, TimeoutError, ssl.SSLError, ValueError) as exc:
        return False, None, "", b"", str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, None, "", b"", str(exc)


def _is_playlist_response(url: str, content_type: str, body: bytes) -> bool:
    lowered_url = url.lower()
    lowered_type = (content_type or "").lower()
    if ".m3u8" in lowered_url or lowered_url.endswith(".m3u"):
        return True
    if "mpegurl" in lowered_type:
        return True
    text_head = body[:512].decode("utf-8", errors="ignore")
    return "#EXTM3U" in text_head


def _first_media_uri(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return ""


def _probe_url(
    url: str,
    timeout: int,
    strict_m3u8: bool,
    verify_segment: bool,
) -> Tuple[bool, int | None, int | None, str]:
    started = time.perf_counter()
    if not _is_http_url(url):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, None, elapsed_ms, "unsupported_scheme"

    ok, status, content_type, body, error = _fetch_sample(url=url, timeout=timeout, max_bytes=8192, use_range=True)
    if not ok or status is None or status >= 400:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, status, elapsed_ms, f"entry:{error or status}"

    final_status = status
    if strict_m3u8 and _is_playlist_response(url, content_type, body):
        first_uri = _first_media_uri(body.decode("utf-8", errors="ignore"))
        if not first_uri:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return False, final_status, elapsed_ms, "entry:empty_playlist"

        child_url = urljoin(url, first_uri)
        if not _is_http_url(child_url):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return False, final_status, elapsed_ms, "entry:child_unsupported_scheme"

        ok2, status2, content_type2, body2, error2 = _fetch_sample(
            url=child_url,
            timeout=timeout,
            max_bytes=8192,
            use_range=True,
        )
        final_status = status2 or final_status
        if not ok2 or status2 is None or status2 >= 400:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return False, final_status, elapsed_ms, f"child:{error2 or status2}"

        if verify_segment and _is_playlist_response(child_url, content_type2, body2):
            segment_uri = _first_media_uri(body2.decode("utf-8", errors="ignore"))
            if not segment_uri:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return False, final_status, elapsed_ms, "child:empty_playlist"

            segment_url = urljoin(child_url, segment_uri)
            if not _is_http_url(segment_url):
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return False, final_status, elapsed_ms, "child:segment_unsupported_scheme"

            ok3, status3, _content_type3, _body3, error3 = _fetch_sample(
                url=segment_url,
                timeout=timeout,
                max_bytes=2048,
                use_range=True,
            )
            final_status = status3 or final_status
            if not ok3 or status3 is None or status3 >= 400:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return False, final_status, elapsed_ms, f"segment:{error3 or status3}"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return True, final_status, elapsed_ms, ""


def health_check_entries(
    entries: List[StreamEntry],
    timeout: int,
    workers: int,
    max_urls: int,
    strict_m3u8: bool = False,
    verify_segment: bool = False,
) -> Dict[str, Dict[str, object]]:
    unique_urls: List[str] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.url in seen:
            continue
        seen.add(entry.url)
        unique_urls.append(entry.url)
    if max_urls > 0:
        unique_urls = unique_urls[:max_urls]

    report: Dict[str, Dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(_probe_url, url, timeout, strict_m3u8, verify_segment): url
            for url in unique_urls
        }
        for future in as_completed(future_map):
            url = future_map[future]
            ok, status_code, elapsed_ms, error = future.result()
            report[url] = {
                "alive": ok,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
                "error": error,
            }
    return report
