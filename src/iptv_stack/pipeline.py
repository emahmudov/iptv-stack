from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse
import json

from .check import health_check_with_fallback
from .classify import classify_entries
from .fetch import fetch_sources
from .m3u import render_m3u, render_m3u_country_grouped
from .models import Source, StreamEntry, normalize_text


def load_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Step 3: Pre-score (before health-check, drives dedup selection)
# ---------------------------------------------------------------------------

def pre_score_entry(entry: StreamEntry, prefer_https: bool = True) -> float:
    score = float(entry.source_weight)
    scheme = urlparse(entry.url).scheme.lower()
    if prefer_https and scheme == "https":
        score += 10.0
    # Bonus for rich metadata
    if entry.extinf_attrs.get("tvg-id"):
        score += 5.0
    if entry.extinf_attrs.get("tvg-logo"):
        score += 3.0
    if entry.extinf_attrs.get("tvg-name"):
        score += 2.0
    return round(score, 2)


# ---------------------------------------------------------------------------
# Step 4: Smart dedup with fallback URLs
# ---------------------------------------------------------------------------

def dedupe_with_fallbacks(
    entries: List[StreamEntry],
    keep_per_channel: int = 1,
    max_fallback_urls: int = 4,
) -> List[StreamEntry]:
    # Remove exact URL duplicates (keep highest scored)
    unique_by_url: Dict[str, StreamEntry] = {}
    for entry in entries:
        previous = unique_by_url.get(entry.url)
        if previous is None or entry.score > previous.score:
            unique_by_url[entry.url] = entry

    # Group by normalized name (country-agnostic to catch cross-source duplicates)
    grouped: Dict[str, List[StreamEntry]] = defaultdict(list)
    for entry in unique_by_url.values():
        key = entry.normalized_name()
        if not key:
            key = normalize_text(entry.extinf_attrs.get("tvg-name", ""))
        if not key:
            key = normalize_text(entry.url)
        grouped[key].append(entry)

    selected: List[StreamEntry] = []
    for key_entries in grouped.values():
        key_entries.sort(key=lambda item: (-item.score, item.url))
        winners = key_entries[: max(1, keep_per_channel)]
        alternates = key_entries[max(1, keep_per_channel):]

        # Attach fallback URLs from alternates to winners
        fallback_pool = [alt.url for alt in alternates]
        for winner in winners:
            winner.fallback_urls = fallback_pool[:max_fallback_urls]
            selected.append(winner)

    selected.sort(key=lambda item: (item.country, item.name.lower(), item.url))
    return selected


# ---------------------------------------------------------------------------
# Step 6: Post-score (after health-check, incorporates health data)
# ---------------------------------------------------------------------------

def post_score_entry(entry: StreamEntry, prefer_https: bool = True) -> float:
    score = float(entry.source_weight)
    scheme = urlparse(entry.url).scheme.lower()
    if prefer_https and scheme == "https":
        score += 10.0
    # Health bonuses
    if entry.alive is True:
        score += 30.0
    if entry.alive is False:
        score -= 25.0
    # Latency bonus (max 20 points for very fast, 0 for 20s+)
    latency = float(entry.latency_ms or 20_000)
    score += max(0.0, 20.0 - latency / 1000.0)
    # Check level bonus
    score += entry.check_level * 5.0
    # Metadata bonuses
    if entry.extinf_attrs.get("tvg-id"):
        score += 5.0
    if entry.extinf_attrs.get("tvg-logo"):
        score += 3.0
    return round(score, 2)


# ---------------------------------------------------------------------------
# Apply health results to entries
# ---------------------------------------------------------------------------

def _apply_health_results(
    entries: List[StreamEntry],
    report: Dict[str, Dict[str, object]],
) -> None:
    for entry in entries:
        url_report = report.get(entry.url)
        if not url_report:
            entry.alive = False
            entry.check_level = 0
            entry.check_error = "not_checked"
            continue
        entry.alive = bool(url_report["alive"])
        entry.status_code = url_report.get("status_code")
        entry.latency_ms = url_report.get("latency_ms")
        entry.check_error = str(url_report.get("error", ""))
        entry.check_level = int(url_report.get("check_level", 0))


# ---------------------------------------------------------------------------
# Group title assignment
# ---------------------------------------------------------------------------

def assign_group_title(
    entries: List[StreamEntry],
    country_titles: Dict[str, str],
    category_titles: Dict[str, str],
) -> None:
    for entry in entries:
        country_label = country_titles.get(entry.country, "Other")
        if entry.categories:
            category_label = category_titles.get(entry.categories[0], entry.categories[0].title())
        else:
            category_label = "General"
        entry.group_title = f"{country_label} | {category_label}"


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_outputs(
    entries: List[StreamEntry],
    output_dir: Path,
    country_titles: Dict[str, str],
    category_titles: Dict[str, str],
    playlist_title: str = "Custom Auto IPTV",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    by_country_dir = output_dir / "by-country"
    by_category_dir = output_dir / "by-category"
    by_country_dir.mkdir(parents=True, exist_ok=True)
    by_category_dir.mkdir(parents=True, exist_ok=True)

    all_playlist = render_m3u(entries, title=playlist_title)
    (output_dir / "all.m3u").write_text(all_playlist, encoding="utf-8")
    (by_category_dir / "all.m3u").write_text(all_playlist, encoding="utf-8")

    country_map: Dict[str, List[StreamEntry]] = defaultdict(list)
    category_map: Dict[str, List[StreamEntry]] = defaultdict(list)
    for entry in entries:
        country_map[entry.country].append(entry)
        for category in entry.categories or ["general"]:
            category_map[category].append(entry)

    # Per-country files: group-title = just country name (e.g. "Azerbaijan")
    for country, country_entries in country_map.items():
        title = country_titles.get(country, country.title())
        body = render_m3u(country_entries, title=f"{playlist_title} - {title}", group_override=title)
        (by_country_dir / f"{country}.m3u").write_text(body, encoding="utf-8")

    # by-country/all.m3u: all channels grouped by country name only
    country_grouped_lines: List[StreamEntry] = []
    for country in sorted(country_map.keys()):
        country_grouped_lines.extend(country_map[country])
    by_country_all = render_m3u_country_grouped(
        country_grouped_lines, country_titles=country_titles, title=f"{playlist_title} - All Countries",
    )
    (by_country_dir / "all.m3u").write_text(by_country_all, encoding="utf-8")

    for category, category_entries in category_map.items():
        title = category_titles.get(category, category.title())
        body = render_m3u(category_entries, title=f"{playlist_title} - {title}", group_override=title)
        (by_category_dir / f"{category}.m3u").write_text(body, encoding="utf-8")

    rows = [entry.to_dict() for entry in entries]
    (output_dir / "channels.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _write_reports(
    output_dir: Path,
    all_checked: List[StreamEntry],
    strict: List[StreamEntry],
    relaxed: List[StreamEntry],
    dead: List[StreamEntry],
) -> None:
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    reason_counter = Counter(
        entry.check_error for entry in dead if entry.check_error
    )
    verification_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_checked": len(all_checked),
        "strict_total": len(strict),
        "relaxed_total": len(relaxed),
        "dead_total": len(dead),
        "failed_reason_counts": dict(reason_counter.most_common()),
    }
    (reports_dir / "verification-report.json").write_text(
        json.dumps(verification_report, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    failed_rows = [entry.to_dict() for entry in dead]
    (reports_dir / "failed-channels.json").write_text(
        json.dumps(failed_rows, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    # Group audit for relaxed tier (main output)
    country_counts = Counter(entry.country for entry in relaxed)
    category_counts = Counter(
        cat for entry in relaxed for cat in (entry.categories or ["general"])
    )
    az_channels = [entry.to_dict() for entry in relaxed if entry.country == "az"]
    other_country = [entry.to_dict() for entry in relaxed if entry.country == "other"]

    audit_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "relaxed_total": len(relaxed),
        "strict_total": len(strict),
        "country_counts": dict(country_counts),
        "category_counts": dict(category_counts),
        "az_channels_total": len(az_channels),
        "other_country_total": len(other_country),
        "az_channels": az_channels,
        "other_country_examples": other_country[:120],
    }
    (reports_dir / "group-audit.json").write_text(
        json.dumps(audit_report, ensure_ascii=False, indent=2), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

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
    tiers_conf = profile_data.get("tiers", {})
    channel_conf = profile_data.get("channel_selection", {})
    groups_conf = profile_data.get("groups", {})

    countries = groups_conf.get("countries", [])
    categories = groups_conf.get("categories", [])
    prefer_https = bool(channel_conf.get("prefer_https", True))
    strict_min_level = int(tiers_conf.get("strict_min_level", 2))
    relaxed_min_level = int(tiers_conf.get("relaxed_min_level", 1))

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

    # Step 1: Fetch
    raw_entries, source_report = fetch_sources(
        sources=source_models,
        timeout=int(fetch_conf.get("timeout_seconds", 25)),
        workers=int(fetch_conf.get("workers", 8)),
    )
    print(f"[1/7] Fetched {len(raw_entries)} entries from {len(source_models)} sources")

    # Step 2: Classify
    classify_entries(
        entries=raw_entries,
        countries=countries,
        categories=categories,
        overrides=overrides_data,
    )
    print(f"[2/7] Classified {len(raw_entries)} entries")

    # Step 3: Pre-score
    for entry in raw_entries:
        entry.score = pre_score_entry(entry, prefer_https=prefer_https)
    print(f"[3/7] Pre-scored {len(raw_entries)} entries")

    # Step 4: Smart dedup with fallbacks
    selected = dedupe_with_fallbacks(
        entries=raw_entries,
        keep_per_channel=int(channel_conf.get("keep_per_channel", 1)),
        max_fallback_urls=int(channel_conf.get("max_fallback_urls", 4)),
    )
    total_fallbacks = sum(len(e.fallback_urls) for e in selected)
    print(f"[4/7] Deduped to {len(selected)} channels ({total_fallbacks} fallback URLs)")

    # Step 5: Health-check with fallback
    if bool(check_conf.get("enabled", True)):
        report = health_check_with_fallback(
            entries=selected,
            timeout=int(check_conf.get("timeout_seconds", 12)),
            workers=int(check_conf.get("workers", 50)),
            retries=int(check_conf.get("retries", 2)),
            retry_sleep_seconds=float(check_conf.get("retry_sleep_seconds", 0.5)),
            max_fallbacks=int(check_conf.get("max_fallbacks", 3)),
        )
        _apply_health_results(selected, report)
    else:
        for entry in selected:
            entry.alive = None
            entry.check_level = 1  # assume alive if not checked

    # Step 6: Post-score
    for entry in selected:
        entry.score = post_score_entry(entry, prefer_https=prefer_https)

    # Categorize by tier
    strict = [e for e in selected if e.check_level >= strict_min_level]
    relaxed = [e for e in selected if e.check_level >= relaxed_min_level]
    dead = [e for e in selected if e.check_level < relaxed_min_level]

    strict.sort(key=lambda e: (-e.score, e.country, e.name.lower()))
    relaxed.sort(key=lambda e: (-e.score, e.country, e.name.lower()))

    print(f"[5/7] Health-checked: {len(strict)} strict, {len(relaxed)} relaxed, {len(dead)} dead")

    # Step 7: Generate outputs
    country_titles = {str(item.get("id")): str(item.get("title")) for item in countries}
    category_titles = {str(item.get("id")): str(item.get("title")) for item in categories}

    # Relaxed tier -> dist/ (main, backward compatible)
    assign_group_title(relaxed, country_titles=country_titles, category_titles=category_titles)
    write_outputs(
        relaxed, output_dir=output_dir,
        country_titles=country_titles, category_titles=category_titles,
        playlist_title="Custom Auto IPTV",
    )

    # Strict tier -> dist/strict/
    strict_dir = output_dir / "strict"
    assign_group_title(strict, country_titles=country_titles, category_titles=category_titles)
    write_outputs(
        strict, output_dir=strict_dir,
        country_titles=country_titles, category_titles=category_titles,
        playlist_title="Custom Auto IPTV (Strict)",
    )

    print(f"[6/7] Wrote outputs: {len(relaxed)} relaxed, {len(strict)} strict")

    # Reports
    _write_reports(
        output_dir=output_dir,
        all_checked=selected,
        strict=strict,
        relaxed=relaxed,
        dead=dead,
    )
    print(f"[7/7] Reports generated")

    # Build summary
    stats = {
        "sources_total": len(source_models),
        "sources_ok": len([row for row in source_report if row["ok"]]),
        "sources_failed": len([row for row in source_report if not row["ok"]]),
        "entries_fetched_raw": len(raw_entries),
        "entries_after_dedupe": len(selected),
        "entries_strict": len(strict),
        "entries_relaxed": len(relaxed),
        "entries_dead": len(dead),
        "total_fallback_urls": total_fallbacks,
    }
    summary = {
        "stats": stats,
        "source_report": source_report,
    }
    (output_dir / "build-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary
