"""Incremental Google Merchant Center RSS 2.0 writer.

Format (https://support.google.com/merchants/answer/14987622, consulted
2026-10-16): ``<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">``
with one ``<item>`` per product. Attributes are written in the ``g:``
namespace, matching Google's example. Empty attributes are omitted, as the
specification asks. Nested attributes (shipping, tax) are written as nested
``g:`` elements. Repeated attributes are written as repeated elements.

Fields from foreign namespaces (keys with a "prefix:" such as "c:extra") and
internal fields ("_segments") are not exported: Google ignores elements
outside the RSS and Google namespaces.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from lxml import etree

from feedstudio.catalog.attributes import Attributes, Value
from feedstudio.ingestion.parser import GOOGLE_NS

_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
G = f"{{{GOOGLE_NS}}}"


def clean_text(value: str) -> str:
    return _INVALID_XML.sub("", value)


def exportable(key: str) -> bool:
    return not key.startswith("_") and ":" not in key and bool(_VALID_NAME.match(key))


def _has_content(value: Value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return any(_has_content(v) for vs in value.values() for v in vs)


def _write_value(xf, name: str, value: Value) -> None:
    if isinstance(value, str):
        with xf.element(G + name):
            xf.write(clean_text(value))
        return
    attrib = {k[1:]: clean_text(v[0]) for k, v in value.items() if k.startswith("@") and v and isinstance(v[0], str)}
    with xf.element(G + name, attrib):
        for sub, sub_values in value.items():
            if sub.startswith("@"):
                continue
            if sub == "#text":
                xf.write(clean_text("".join(v for v in sub_values if isinstance(v, str))))
                continue
            if not _VALID_NAME.match(sub):
                continue
            for sv in sub_values:
                if _has_content(sv):
                    _write_value(xf, sub, sv)


def write_google_feed(path: Path, items: Iterable[Attributes], channel_title: str, channel_link: str, channel_description: str) -> int:
    """Stream items to ``path``. Returns the number of items written."""
    count = 0
    with etree.xmlfile(str(path), encoding="utf-8") as xf:
        xf.write_declaration()
        with xf.element("rss", {"version": "2.0"}, nsmap={"g": GOOGLE_NS}):
            with xf.element("channel"):
                for tag, text in (("title", channel_title), ("link", channel_link), ("description", channel_description)):
                    with xf.element(tag):
                        xf.write(clean_text(text))
                for attrs in items:
                    with xf.element("item"):
                        for key, values in attrs.items():
                            if not exportable(key):
                                continue
                            for value in values:
                                if _has_content(value):
                                    _write_value(xf, key, value)
                    xf.flush()
                    count += 1
    return count
