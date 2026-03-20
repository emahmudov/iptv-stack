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


def _looks_like_denied_payload(content_type: str, body: bytes) -> bool:
    ctype = (content_type or "").lower()
    text_head = body[:2048].decode("utf-8", errors="ignore").lower()
    deny_markers = [
        "forbidden",
        "access denied",
        "permission",
        "not authorized",
        "unauthorized",
        "geo",
        "geo-block",
        "blocked",
        "token expired",
        "invalid token",
    ]
    if "text/html" in ctype and any(marker in text_head for marker in deny_markers):
        return True
    if "<html" in text_head and any(marker in text_head for marker in deny_markers):
        return True
    return False


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
        if exc.code == 416 and use_range:
            return _fetch_sample(url=url, timeout=timeout, max_bytes=max_bytes, use_range=False)
        body = b""
        try:
            body = exc.read(max_bytes)
        except Exception:
            pass
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        return False, exc.code, content_type, body, str(exc)
    except (URLError, TimeoutError, ssl.SSLError, ValueError) as exc:
        return False, None, "", b"", str(exc)
    except Exception as exc:
        return False, None, "", b"", str(exc)


def _is_playlist_response(content_type: str, body: bytes) -> bool:
    lowered_type = (content_type or "").lower()
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


def _probe_url_tiered(url: str, timeout: int) -> Tuple[int, int | None, int | None, str]:
    """Probe a URL and return the highest check level achieved.

    Levels:
        0 = dead (connection failed, 4xx/5xx, denied payload)
        1 = connects (HTTP 2xx/3xx, not denied) -> qualifies for "relaxed"
        2 = playlist valid (child URI also returns 2xx) -> qualifies for "strict"
        3 = segment verified (media segment reachable) -> extra confidence
    """
    started = time.perf_counter()
    if not _is_http_url(url):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, None, elapsed_ms, "unsupported_scheme"

    ok, status, content_type, body, error = _fetch_sample(url=url, timeout=timeout)
    if not ok or status is None or status >= 400:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, status, elapsed_ms, f"entry:{error or status}"
    if _looks_like_denied_payload(content_type, body):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, status, elapsed_ms, "entry:denied_payload"

    # Level 1 achieved: URL connects successfully
    if not _is_playlist_response(content_type, body):
        # Direct stream (not a playlist) — level 1 is the max we can verify
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 1, status, elapsed_ms, ""

    # It's a playlist — try to validate child URI for level 2
    first_uri = _first_media_uri(body.decode("utf-8", errors="ignore"))
    if not first_uri:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 1, status, elapsed_ms, "empty_playlist_but_connects"

    child_url = urljoin(url, first_uri)
    if not _is_http_url(child_url):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 1, status, elapsed_ms, "child_unsupported_scheme"

    ok2, status2, content_type2, body2, error2 = _fetch_sample(url=child_url, timeout=timeout)
    if not ok2 or status2 is None or status2 >= 400:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 1, status, elapsed_ms, f"child:{error2 or status2}"
    if _looks_like_denied_payload(content_type2, body2):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 1, status, elapsed_ms, "child:denied_payload"

    # Level 2 achieved: child URI is valid
    if not _is_playlist_response(content_type2, body2):
        # Child is a media segment directly — level 2 + segment = level 3
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 3, status2 or status, elapsed_ms, ""

    # Child is also a playlist — try segment for level 3
    segment_uri = _first_media_uri(body2.decode("utf-8", errors="ignore"))
    if not segment_uri:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 2, status2 or status, elapsed_ms, ""

    segment_url = urljoin(child_url, segment_uri)
    if not _is_http_url(segment_url):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 2, status2 or status, elapsed_ms, "segment_unsupported_scheme"

    ok3, status3, _, body3, error3 = _fetch_sample(url=segment_url, timeout=timeout, max_bytes=2048)
    if not ok3 or status3 is None or status3 >= 400:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 2, status2 or status, elapsed_ms, f"segment:{error3 or status3}"
    if _looks_like_denied_payload("", body3):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 2, status2 or status, elapsed_ms, "segment:denied_payload"

    # Level 3 achieved: segment is reachable
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return 3, status3 or status, elapsed_ms, ""


def _probe_with_retries(
    url: str,
    timeout: int,
    retries: int,
    retry_sleep_seconds: float,
) -> Tuple[int, int | None, int | None, str]:
    best_result: Tuple[int, int | None, int | None, str] = (0, None, None, "unknown")
    for idx in range(max(1, retries)):
        result = _probe_url_tiered(url=url, timeout=timeout)
        if result[0] > best_result[0]:
            best_result = result
        if best_result[0] >= 2:
            return best_result
        if idx < retries - 1 and retry_sleep_seconds > 0:
            time.sleep(retry_sleep_seconds)
    return best_result


def health_check_entries(
    entries: List[StreamEntry],
    timeout: int = 12,
    workers: int = 50,
    retries: int = 2,
    retry_sleep_seconds: float = 0.5,
) -> Dict[str, Dict[str, object]]:
    """Check unique URLs from entries and return a report keyed by URL."""
    unique_urls: List[str] = []
    seen: set[str] = set()
    for entry in entries:
        if entry.url in seen:
            continue
        seen.add(entry.url)
        unique_urls.append(entry.url)

    report: Dict[str, Dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(
                _probe_with_retries, url, timeout, retries, retry_sleep_seconds,
            ): url
            for url in unique_urls
        }
        for future in as_completed(future_map):
            url = future_map[future]
            level, status_code, elapsed_ms, error = future.result()
            report[url] = {
                "check_level": level,
                "alive": level >= 1,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
                "error": error,
            }
    return report


def health_check_with_fallback(
    entries: List[StreamEntry],
    timeout: int = 12,
    workers: int = 50,
    retries: int = 2,
    retry_sleep_seconds: float = 0.5,
    max_fallbacks: int = 3,
) -> Dict[str, Dict[str, object]]:
    """Check primary URLs, then try fallbacks for failed entries."""
    # Step 1: Check all primary URLs
    report = health_check_entries(
        entries=entries,
        timeout=timeout,
        workers=workers,
        retries=retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )

    # Step 2: Collect fallback URLs for failed entries
    fallback_urls_to_check: List[str] = []
    seen_urls: set[str] = {entry.url for entry in entries}
    for entry in entries:
        url_report = report.get(entry.url)
        if url_report and url_report["check_level"] >= 1:
            continue
        for fb_url in entry.fallback_urls[:max_fallbacks]:
            if fb_url not in seen_urls and fb_url not in report:
                fallback_urls_to_check.append(fb_url)
                seen_urls.add(fb_url)

    if not fallback_urls_to_check:
        return report

    # Step 3: Check fallback URLs
    fb_report: Dict[str, Dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(
                _probe_with_retries, url, timeout, retries, retry_sleep_seconds,
            ): url
            for url in fallback_urls_to_check
        }
        for future in as_completed(future_map):
            url = future_map[future]
            level, status_code, elapsed_ms, error = future.result()
            fb_report[url] = {
                "check_level": level,
                "alive": level >= 1,
                "status_code": status_code,
                "latency_ms": elapsed_ms,
                "error": error,
            }
    report.update(fb_report)

    # Step 4: Swap URLs for entries where fallback is better
    for entry in entries:
        primary = report.get(entry.url)
        primary_level = primary["check_level"] if primary else 0
        if primary_level >= 1:
            continue
        for fb_url in entry.fallback_urls[:max_fallbacks]:
            fb = report.get(fb_url)
            if fb and fb["check_level"] > primary_level:
                entry.url = fb_url
                break

    return report
