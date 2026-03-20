from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import re
import unicodedata


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.casefold().strip()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Source:
    name: str
    url: str
    enabled: bool = True
    weight: int = 50
    tags: List[str] = field(default_factory=list)


@dataclass
class StreamEntry:
    name: str
    url: str
    source_name: str
    source_weight: int
    source_tags: List[str] = field(default_factory=list)
    group_title: str = ""
    extinf_attrs: Dict[str, str] = field(default_factory=dict)
    country: str = "other"
    categories: List[str] = field(default_factory=list)
    alive: Optional[bool] = None
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    check_error: str = ""
    check_level: int = 0
    score: float = 0.0
    fallback_urls: List[str] = field(default_factory=list)

    def normalized_name(self) -> str:
        return normalize_text(self.name)

    def normalized_group(self) -> str:
        return normalize_text(self.group_title)

    def dedup_key(self) -> str:
        return f"{self.country}::{self.normalized_name()}"

    def stable_key(self) -> str:
        return f"{self.normalized_name()}::{self.url.strip()}"

    def tier(self) -> str:
        if self.check_level >= 2:
            return "strict"
        if self.check_level >= 1:
            return "relaxed"
        return "dead"

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "url": self.url,
            "source_name": self.source_name,
            "source_weight": self.source_weight,
            "source_tags": self.source_tags,
            "group_title": self.group_title,
            "country": self.country,
            "categories": self.categories,
            "alive": self.alive,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "check_error": self.check_error,
            "check_level": self.check_level,
            "tier": self.tier(),
            "score": self.score,
            "tvg_id": self.extinf_attrs.get("tvg-id", ""),
            "tvg_name": self.extinf_attrs.get("tvg-name", ""),
            "tvg_logo": self.extinf_attrs.get("tvg-logo", ""),
        }
