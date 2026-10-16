"""Attribute inventory built incrementally while parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from feedstudio.catalog.attributes import Attributes
from feedstudio.rules.text import parse_number

MAX_SAMPLES = 8

_URL_RE = re.compile(r"^https?://", re.I)
_PRICE_RE = re.compile(r"^\s*[-+]?\d[\d.,\s]*\s+[A-Z]{3}\s*$")
_BOOL = {"true", "false", "yes", "no", "y", "n", "0", "1"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class FieldStats:
    key: str
    qname: str
    present_count: int = 0
    empty_count: int = 0
    max_repeat: int = 0
    nested: bool = False
    samples: list[str] = field(default_factory=list)
    type_votes: dict[str, int] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        if self.nested:
            return "nested"
        return "list" if self.max_repeat > 1 else "scalar"

    @property
    def inferred_type(self) -> str:
        if self.nested:
            return "object"
        if not self.type_votes:
            return "text"
        best, votes = max(self.type_votes.items(), key=lambda kv: kv[1])
        non_empty = self.present_count - self.empty_count
        return best if non_empty and votes / max(1, sum(self.type_votes.values())) >= 0.9 else "text"


def infer_type(value: str) -> str:
    v = value.strip()
    if _URL_RE.match(v):
        return "url"
    if _PRICE_RE.match(v):
        return "price"
    if v.lower() in _BOOL:
        return "boolean"
    if _DATE_RE.match(v):
        return "date"
    if parse_number(v) is not None and re.fullmatch(r"[-+]?[\d.,]+", v):
        return "number"
    return "text"


class SchemaCollector:
    def __init__(self) -> None:
        self.fields: dict[str, FieldStats] = {}
        self.product_count = 0

    def add(self, attrs: Attributes, qnames: dict[str, str]) -> None:
        self.product_count += 1
        for key, values in attrs.items():
            stats = self.fields.get(key)
            if stats is None:
                stats = self.fields[key] = FieldStats(key=key, qname=qnames.get(key, key))
            stats.present_count += 1
            stats.max_repeat = max(stats.max_repeat, len(values))
            texts = [v for v in values if isinstance(v, str)]
            if len(texts) != len(values):
                stats.nested = True
            if all(not t.strip() for t in texts) and len(texts) == len(values):
                stats.empty_count += 1
            for text in texts[:1]:
                if not text.strip():
                    continue
                kind = infer_type(text)
                stats.type_votes[kind] = stats.type_votes.get(kind, 0) + 1
                sample = text.strip()[:120]
                if len(stats.samples) < MAX_SAMPLES and sample not in stats.samples:
                    stats.samples.append(sample)

    def as_rows(self) -> list[dict]:
        return [
            {
                "key": s.key,
                "qname": s.qname,
                "present_count": s.present_count,
                "empty_count": s.empty_count,
                "max_repeat": s.max_repeat,
                "kind": s.kind,
                "inferred_type": s.inferred_type,
                "samples": s.samples,
                "coverage": round(s.present_count / self.product_count, 4) if self.product_count else 0,
            }
            for s in sorted(self.fields.values(), key=lambda s: (-s.present_count, s.key))
        ]
