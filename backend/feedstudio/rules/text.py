"""Text helpers shared by conditions, actions and validators.

Design notes:
- Case-insensitive comparisons use NFC normalization + ``str.casefold`` so
  that "Ñ"/"ñ" and composed/decomposed accents compare equal.
- Regular expressions use the third-party ``regex`` engine, which supports a
  per-call timeout. Patterns are also length-limited. This bounds the cost of
  catastrophic backtracking from user-supplied patterns.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache

import regex

MAX_PATTERN_LENGTH = 300
REGEX_TIMEOUT_SECONDS = 0.05


class RegexError(ValueError):
    pass


class RegexTimeout(RuntimeError):
    pass


def normalize(text: str, case_sensitive: bool) -> str:
    text = unicodedata.normalize("NFC", text)
    return text if case_sensitive else text.casefold()


@lru_cache(maxsize=512)
def compile_pattern(pattern: str, case_sensitive: bool = True) -> regex.Pattern:
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexError(f"La expresión regular supera {MAX_PATTERN_LENGTH} caracteres")
    flags = regex.V0
    if not case_sensitive:
        flags |= regex.IGNORECASE
    try:
        return regex.compile(pattern, flags)
    except regex.error as exc:  # pragma: no branch - message passthrough
        raise RegexError(f"Expresión regular inválida: {exc}") from exc


def regex_search(pattern: regex.Pattern, text: str) -> regex.Match | None:
    try:
        return pattern.search(text, timeout=REGEX_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise RegexTimeout("La expresión regular excedió el tiempo permitido") from exc


def regex_sub(pattern: regex.Pattern, repl: str, text: str, literal: bool = False) -> str:
    """Substitute matches. With ``literal`` the replacement is inserted as-is;
    otherwise only ``\\1``-style group references are expanded."""
    fn = (lambda _m: repl) if literal else _literal_repl(repl)
    try:
        return pattern.sub(fn, text, timeout=REGEX_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise RegexTimeout("La expresión regular excedió el tiempo permitido") from exc


def _literal_repl(repl: str):
    group_ref = re.compile(r"\\(\d)")

    def _fn(match: regex.Match) -> str:
        return group_ref.sub(lambda m: match.group(int(m.group(1))) or "", repl)

    return _fn


_TAG_RE = re.compile(r"<[^>]{0,2000}>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """Remove tags and decode entities. Block-level tags become spaces."""
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h\d)\s*/?\s*>", " ", text)
    text = _TAG_RE.sub("", text)
    return html.unescape(text)


def collapse_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def contains_html(text: str) -> bool:
    return bool(re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", text))


def capitalize_sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:].lower() if text else text


def capitalize_words(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in text.split(" "))


def truncate(text: str, max_length: int, strategy: str = "word", ellipsis: str = "") -> str:
    if len(text) <= max_length:
        return text
    budget = max(0, max_length - len(ellipsis))
    cut = text[:budget]
    if strategy == "word" and " " in cut:
        # Only back off to a word boundary if we are cutting inside a word.
        if budget < len(text) and text[budget] != " ":
            cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" -,;:/|") + ellipsis


# --- Numbers & prices -------------------------------------------------------

_NUMBER_RE = re.compile(r"[-+]?\d[\d.,\s\u00a0']*")
_CURRENCY_RE = re.compile(r"\b([A-Z]{3})\b")


def parse_number(text: str | None) -> Decimal | None:
    """Parse a localized number such as "949.990,00", "1,299.50", "59.90".

    Heuristics (documented in docs/rules-engine.md):
    - When both "." and "," appear, the right-most one is the decimal separator.
    - A single separator followed by exactly 3 digits, repeated in groups
      (e.g. "1.190" or "1,234,567"), is treated as a thousands separator.
    - Otherwise a single separator is the decimal separator.
    Returns None when no number can be parsed.
    """
    if text is None:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    raw = re.sub(r"[\s\u00a0']", "", match.group(0)).rstrip(".,")
    if not raw:
        return None
    has_dot, has_comma = "." in raw, "," in raw
    if has_dot and has_comma:
        decimal_sep = "." if raw.rfind(".") > raw.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        raw = raw.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        if re.fullmatch(rf"[-+]?\d{{1,3}}(\{sep}\d{{3}})+", raw):
            raw = raw.replace(sep, "")
        elif raw.count(sep) == 1:
            raw = raw.replace(sep, ".")
        else:
            return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class ParsedPrice:
    amount: Decimal | None
    currency: str | None


def parse_price(text: str | None) -> ParsedPrice:
    if text is None:
        return ParsedPrice(None, None)
    currency_match = _CURRENCY_RE.search(text)
    return ParsedPrice(parse_number(text), currency_match.group(1) if currency_match else None)


def format_price(amount: Decimal, currency: str | None, decimals: int = 2) -> str:
    quantized = amount.quantize(Decimal(1).scaleb(-decimals)) if decimals > 0 else amount.quantize(Decimal(1))
    text = f"{quantized:f}"
    return f"{text} {currency}" if currency else text
