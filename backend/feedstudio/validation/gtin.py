"""GTIN (EAN/UPC/ITF-14) format and GS1 check-digit validation."""

from __future__ import annotations

import re

VALID_LENGTHS = (8, 12, 13, 14)


def clean_gtin(value: str) -> str:
    return re.sub(r"[\s-]", "", value)


def is_valid_gtin(value: str) -> bool:
    digits = clean_gtin(value)
    if not digits.isdigit() or len(digits) not in VALID_LENGTHS:
        return False
    body, check = digits[:-1], int(digits[-1])
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return (10 - total % 10) % 10 == check
