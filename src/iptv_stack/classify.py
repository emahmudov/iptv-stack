from __future__ import annotations

from typing import Dict, List
from urllib.parse import urlparse

from .models import StreamEntry, normalize_text


def _find_country(entry: StreamEntry, countries: List[Dict[str, object]]) -> str:
    host = (urlparse(entry.url).hostname or "").lower()
    tvg_id = normalize_text(entry.extinf_attrs.get("tvg-id", ""))
    joined = " ".join(
        [
            normalize_text(entry.name),
            normalize_text(entry.group_title),
            normalize_text(entry.extinf_attrs.get("tvg-name", "")),
            tvg_id,
            normalize_text(host),
        ]
    )
    tag_set = {normalize_text(tag) for tag in entry.source_tags}

    # Collect ALL known tvg-id suffixes across all countries
    all_suffixes: Dict[str, str] = {}
    for item in countries:
        cid = str(item.get("id", "other"))
        for suffix in item.get("tvg_id_suffixes", []):
            if suffix:
                all_suffixes[normalize_text(suffix)] = cid

    # Pass 1: tvg-id suffix match (highest priority, definitive)
    if tvg_id:
        for suffix, cid in all_suffixes.items():
            if tvg_id.endswith(suffix):
                return cid

    # Determine if tvg-id belongs to a known non-matching country
    # If so, skip keyword matching to prevent false positives
    tvg_id_locked = False
    if tvg_id:
        # Check common country TLD patterns in tvg-id (e.g. ".us@", ".ca@", ".ru@")
        raw_tvg = (entry.extinf_attrs.get("tvg-id", "") or "").lower()
        for item in countries:
            cid = str(item.get("id", "other"))
            for suffix in item.get("tvg_id_suffixes", []):
                if suffix and suffix.lower() in raw_tvg:
                    tvg_id_locked = True

    # Pass 2: keyword match (skip if tvg-id already locked to another country)
    if not tvg_id_locked:
        for item in countries:
            country_id = str(item.get("id", "other"))
            keywords = [normalize_text(x) for x in item.get("keywords", []) if x]
            if any(kw and kw in joined for kw in keywords):
                return country_id

    # Pass 3: TLD match
    for item in countries:
        country_id = str(item.get("id", "other"))
        tlds = [normalize_text(x) for x in item.get("tlds", []) if x]
        if any(tld and host.endswith(tld) for tld in tlds):
            return country_id

    # Pass 4: source tag fallback
    for item in countries:
        country_id = str(item.get("id", "other"))
        source_tags = [normalize_text(x) for x in item.get("source_tags", [])]
        if any(tag in tag_set for tag in source_tags):
            return country_id
    return "other"


def _find_categories(entry: StreamEntry, categories: List[Dict[str, object]]) -> List[str]:
    joined = " ".join(
        [
            normalize_text(entry.name),
            normalize_text(entry.group_title),
            normalize_text(entry.extinf_attrs.get("tvg-name", "")),
        ]
    )
    found: List[str] = []
    for item in categories:
        cat_id = str(item.get("id", "general"))
        source_tags = [normalize_text(x) for x in item.get("source_tags", []) if x]
        if source_tags and any(tag in source_tags for tag in [normalize_text(t) for t in entry.source_tags]):
            found.append(cat_id)
            continue
        keywords = [normalize_text(x) for x in item.get("keywords", []) if x]
        if any(kw and kw in joined for kw in keywords):
            found.append(cat_id)
    if not found:
        found.append("general")
    return sorted(set(found))


def apply_overrides(entry: StreamEntry, overrides: Dict[str, object]) -> None:
    by_name = overrides.get("by_name", {}) if isinstance(overrides, dict) else {}
    by_url = overrides.get("by_url", {}) if isinstance(overrides, dict) else {}

    normalized_name = normalize_text(entry.name)
    for key, meta in by_name.items():
        if normalize_text(str(key)) != normalized_name:
            continue
        if isinstance(meta, dict):
            if meta.get("country"):
                entry.country = str(meta["country"])
            if meta.get("categories"):
                entry.categories = [str(cat) for cat in meta["categories"]]
            if meta.get("name"):
                entry.name = str(meta["name"])
        return

    meta = by_url.get(entry.url)
    if isinstance(meta, dict):
        if meta.get("country"):
            entry.country = str(meta["country"])
        if meta.get("categories"):
            entry.categories = [str(cat) for cat in meta["categories"]]
        if meta.get("name"):
            entry.name = str(meta["name"])


def classify_entries(
    entries: List[StreamEntry],
    countries: List[Dict[str, object]],
    categories: List[Dict[str, object]],
    overrides: Dict[str, object],
) -> None:
    for entry in entries:
        entry.country = _find_country(entry, countries)
        entry.categories = _find_categories(entry, categories)
        apply_overrides(entry, overrides)
