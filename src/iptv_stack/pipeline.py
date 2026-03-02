from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple
import json
from urllib.parse import urlparse

from .check import health_check_entries
from .classify import classify_entries
from .fetch import fetch_sources
from .m3u import render_m3u
from .models import Source, StreamEntry, normalize_text


def load_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def score_entry(entry: StreamEntry, prefer_https: bool = True) -> float:
    score = float(entry.source_weight)
    scheme = urlparse(entry.url).scheme.lower()
    if prefer_https and scheme == "https":
        score += 10.0
    if entry.alive is True:
        score += 30.0
    if entry.alive is False:
        score -= 25.0
    if entry.status_code and entry.status_code >= 400:
        score -= 5.0
    score += max(0.0, 20.0 - float(entry.latency_ms or 20_000) / 1000.0)
    return round(score, 2)


def dedupe_entries(entries: List[StreamEntry], keep_per_channel: int) -> List[StreamEntry]:
    unique_by_url: Dict[str, StreamEntry] = {}
    for entry in entries:
        previous = unique_by_url.get(entry.url)
        if previous is None or entry.score > previous.score:
            unique_by_url[entry.url] = entry

    grouped: Dict[str, List[StreamEntry]] = defaultdict(list)
    for entry in unique_by_url.values():
        key = entry.normalized_name() or normalize_text(entry.extinf_attrs.get("tvg-name", ""))
        if not key:
            key = normalize_text(entry.url)
        grouped[key].append(entry)

    selected: List[StreamEntry] = []
    for key_entries in grouped.values():
        key_entries.sort(key=lambda item: (-item.score, item.url))
        selected.extend(key_entries[: max(1, keep_per_channel)])
    selected.sort(key=lambda item: (item.country, item.name.lower(), item.url))
    return selected


def assign_group_title(entries: List[StreamEntry], country_titles: Dict[str, str], category_titles: Dict[str, str]) -> None:
    for entry in entries:
        country_label = country_titles.get(entry.country, "Other")
        if entry.categories:
            category_label = category_titles.get(entry.categories[0], entry.categories[0].title())
        else:
            category_label = "General"
        entry.group_title = f"{country_label} | {category_label}"


def write_outputs(
    entries: List[StreamEntry],
    output_dir: Path,
    country_titles: Dict[str, str],
    category_titles: Dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_country_dir = output_dir / "by-country"
    by_category_dir = output_dir / "by-category"
    by_country_dir.mkdir(parents=True, exist_ok=True)
    by_category_dir.mkdir(parents=True, exist_ok=True)

    all_playlist = render_m3u(entries, title="Custom Auto IPTV")
    (output_dir / "all.m3u").write_text(all_playlist, encoding="utf-8")

    country_map: Dict[str, List[StreamEntry]] = defaultdict(list)
    category_map: Dict[str, List[StreamEntry]] = defaultdict(list)
    for entry in entries:
        country_map[entry.country].append(entry)
        for category in entry.categories or ["general"]:
            category_map[category].append(entry)

    for country, country_entries in country_map.items():
        title = country_titles.get(country, country.title())
        body = render_m3u(country_entries, title=f"Custom IPTV - {title}")
        (by_country_dir / f"{country}.m3u").write_text(body, encoding="utf-8")

    for category, category_entries in category_map.items():
        title = category_titles.get(category, category.title())
        body = render_m3u(category_entries, title=f"Custom IPTV - {title}")
        (by_category_dir / f"{category}.m3u").write_text(body, encoding="utf-8")

    rows = [entry.to_dict() for entry in entries]
    (output_dir / "channels.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_dataset(
    sources_path: Path,
    profile_path: Path,
    overrides_path: Path,
    output_dir: Path,
) -> Dict[str, object]:
    sources_data = load_json(sources_path)
    profile_data = load_json(profile_path)
    overrides_data = load_json(overrides_path) if overrides_path.exists() else {}

    fetch_conf = profile_data.get("fetch", {})
    check_conf = profile_data.get("healthcheck", {})
    channel_conf = profile_data.get("channel_selection", {})
    groups_conf = profile_data.get("groups", {})

    countries = groups_conf.get("countries", [])
    categories = groups_conf.get("categories", [])

    source_models = [
        Source(
            name=str(item.get("name")),
            url=str(item.get("url")),
            enabled=bool(item.get("enabled", True)),
            weight=int(item.get("weight", 50)),
            tags=[str(tag) for tag in item.get("tags", [])],
        )
        for item in sources_data.get("sources", [])
        if item.get("name") and item.get("url")
    ]

    entries, source_report = fetch_sources(
        sources=source_models,
        timeout=int(fetch_conf.get("timeout_seconds", 20)),
        workers=int(fetch_conf.get("workers", 8)),
    )

    classify_entries(
        entries=entries,
        countries=countries,
        categories=categories,
        overrides=overrides_data,
    )

    if bool(check_conf.get("enabled", True)):
        require_checked = bool(check_conf.get("require_checked", True))
        check_report = health_check_entries(
            entries=entries,
            timeout=int(check_conf.get("timeout_seconds", 8)),
            workers=int(check_conf.get("workers", 30)),
            max_urls=int(check_conf.get("max_urls", 1200)),
            strict_m3u8=bool(check_conf.get("strict_m3u8", False)),
            verify_segment=bool(check_conf.get("verify_segment", False)),
        )
        for entry in entries:
            url_report = check_report.get(entry.url)
            if not url_report:
                if require_checked:
                    entry.alive = False
                    entry.check_error = "not_checked"
                continue
            entry.alive = bool(url_report["alive"])
            entry.status_code = url_report["status_code"]
            entry.latency_ms = url_report["latency_ms"]
            entry.check_error = str(url_report["error"])
    else:
        for entry in entries:
            entry.alive = None

    drop_dead = bool(channel_conf.get("drop_dead_streams", True))
    if drop_dead:
        entries = [entry for entry in entries if entry.alive is not False]

    prefer_https = bool(channel_conf.get("prefer_https", True))
    for entry in entries:
        entry.score = score_entry(entry, prefer_https=prefer_https)

    selected = dedupe_entries(
        entries=entries,
        keep_per_channel=int(channel_conf.get("keep_per_channel", 2)),
    )

    country_titles = {str(item.get("id")): str(item.get("title")) for item in countries}
    category_titles = {str(item.get("id")): str(item.get("title")) for item in categories}
    assign_group_title(selected, country_titles=country_titles, category_titles=category_titles)
    write_outputs(selected, output_dir=output_dir, country_titles=country_titles, category_titles=category_titles)

    stats = {
        "sources_total": len(source_models),
        "sources_ok": len([row for row in source_report if row["ok"]]),
        "sources_failed": len([row for row in source_report if not row["ok"]]),
        "entries_fetched": len(entries),
        "entries_selected": len(selected),
    }
    summary = {"stats": stats, "source_report": source_report}
    (output_dir / "build-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
