"""Auxiliary CSV export (one column per attribute).

Repeated values are joined with ", ", nested values are rendered as
"sub=value;sub=value". CSV is an auxiliary format: it is NOT a guaranteed
channel-ready format for nested attributes.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from feedstudio.catalog.attributes import Attributes, display_value

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(text: str) -> str:
    # Prevent CSV/formula injection when opened in spreadsheet software.
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def write_csv(path: Path, columns: list[str], items: Iterable[Attributes], delimiter: str = ",") -> int:
    count = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(columns)
        for attrs in items:
            writer.writerow([_safe_cell(display_value(attrs.get(c) or [])) for c in columns])
            count += 1
    return count
