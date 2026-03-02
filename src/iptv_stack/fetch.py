from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import ssl
import time

from .m3u import parse_m3u
from .models import Source, StreamEntry


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Codex IPTV Builder)",
    "Accept": "*/*",
}


@dataclass
class SourceFetchResult:
    source: Source
    ok: bool
    entries: List[StreamEntry]
    error: str = ""
    elapsed_ms: int = 0


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_text(url: str, timeout: int = 20, max_bytes: int = 12_000_000) -> str:
    req = Request(url=url, headers=DEFAULT_HEADERS, method="GET")
    with urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        body = resp.read(max_bytes)
    return body.decode("utf-8", errors="replace")


def fetch_source(source: Source, timeout: int = 20) -> SourceFetchResult:
    started = time.perf_counter()
    try:
        text = fetch_text(source.url, timeout=timeout)
        entries = parse_m3u(
            text=text,
            source_name=source.name,
            source_weight=source.weight,
            source_tags=source.tags,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SourceFetchResult(source=source, ok=True, entries=entries, elapsed_ms=elapsed_ms)
    except (HTTPError, URLError, TimeoutError, ValueError, ssl.SSLError) as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SourceFetchResult(
            source=source,
            ok=False,
            entries=[],
            error=str(exc),
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SourceFetchResult(
            source=source,
            ok=False,
            entries=[],
            error=str(exc),
            elapsed_ms=elapsed_ms,
        )


def fetch_sources(sources: List[Source], timeout: int, workers: int) -> Tuple[List[StreamEntry], List[Dict[str, object]]]:
    entries: List[StreamEntry] = []
    report: List[Dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {executor.submit(fetch_source, source, timeout): source for source in sources if source.enabled}
        for future in as_completed(future_map):
            result = future.result()
            entries.extend(result.entries)
            report.append(
                {
                    "source": result.source.name,
                    "url": result.source.url,
                    "ok": result.ok,
                    "count": len(result.entries),
                    "elapsed_ms": result.elapsed_ms,
                    "error": result.error,
                }
            )
    report.sort(key=lambda item: item["source"])
    return entries, report
