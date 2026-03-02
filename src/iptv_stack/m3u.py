from __future__ import annotations

from typing import Dict, Iterable, List
import re

from .models import StreamEntry


EXTINF_RE = re.compile(r"^#EXTINF:(-?\d+)\s*(.*?),(.*)$")
ATTR_RE = re.compile(r'([A-Za-z0-9\-_]+)="([^"]*)"')


def parse_extinf(line: str) -> Dict[str, str]:
    match = EXTINF_RE.match(line.strip())
    if not match:
        return {}
    _duration, attrs_blob, name = match.groups()
    attrs: Dict[str, str] = {}
    for key, value in ATTR_RE.findall(attrs_blob):
        attrs[key.strip()] = value.strip()
    attrs["__name__"] = name.strip()
    return attrs


def parse_m3u(text: str, source_name: str, source_weight: int, source_tags: List[str]) -> List[StreamEntry]:
    entries: List[StreamEntry] = []
    pending_attrs: Dict[str, str] = {}
    pending_group = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            pending_attrs = parse_extinf(line)
            continue
        if line.startswith("#EXTGRP:"):
            pending_group = line.replace("#EXTGRP:", "", 1).strip()
            continue
        if line.startswith("#"):
            continue
        if not pending_attrs:
            continue

        group_title = pending_attrs.get("group-title", pending_group)
        name = pending_attrs.get("__name__", "Unknown")
        attrs = {k: v for k, v in pending_attrs.items() if k != "__name__"}
        entries.append(
            StreamEntry(
                name=name,
                url=line,
                source_name=source_name,
                source_weight=source_weight,
                source_tags=source_tags,
                group_title=group_title,
                extinf_attrs=attrs,
            )
        )
        pending_attrs = {}
        pending_group = ""

    return entries


def render_m3u(entries: Iterable[StreamEntry], title: str = "My IPTV List") -> str:
    lines = [f'#EXTM3U x-tvg-url="" x-playlist-name="{title}"']
    for entry in entries:
        attrs = dict(entry.extinf_attrs)
        if entry.group_title:
            attrs["group-title"] = entry.group_title
        if entry.extinf_attrs.get("tvg-name", "").strip() == "":
            attrs["tvg-name"] = entry.name

        attr_blob = " ".join(f'{k}="{v}"' for k, v in sorted(attrs.items()) if v is not None)
        lines.append(f"#EXTINF:-1 {attr_blob},{entry.name}")
        lines.append(entry.url)
    return "\n".join(lines) + "\n"
