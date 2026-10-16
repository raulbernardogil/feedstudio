"""Secure streaming XML feed parser.

Security measures:
- Any DOCTYPE / DTD is rejected (product feeds do not need them). This blocks
  XXE and entity-expansion ("billion laughs") attacks.
- lxml is configured with ``resolve_entities=False``, ``no_network=True``,
  ``load_dtd=False`` and ``huge_tree=False`` as defence in depth.
- Element depth, decompressed size and item count are bounded.
- GZIP input is decompressed incrementally with a hard size cap.

Memory: ``lxml.etree.iterparse`` is used and every processed item is cleared
and detached from the tree, so memory is proportional to one item, not to the
whole document.
"""

from __future__ import annotations

import gzip
import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator

from lxml import etree

from feedstudio.catalog.attributes import Attributes, Value

GOOGLE_NS = "http://base.google.com/ns/1.0"
GOOGLE_CUSTOM_NS = "http://base.google.com/cns/1.0"
ATOM_NS = "http://www.w3.org/2005/Atom"
GZIP_MAGIC = b"\x1f\x8b"


class FeedParseError(Exception):
    """Raised when a feed cannot be parsed. ``line`` is 1-based when known."""

    def __init__(self, message: str, line: int | None = None, code: str = "xml_invalid"):
        super().__init__(message)
        self.message = message
        self.line = line
        self.code = code


@dataclass(frozen=True)
class ParserLimits:
    max_bytes: int = 200 * 1024 * 1024
    max_depth: int = 32
    max_items: int = 1_000_000
    max_text_length: int = 1_000_000


@dataclass
class FeedStructure:
    format: str  # "rss" | "atom" | "custom"
    root_tag: str
    item_tag: str  # Clark notation, e.g. "item" or "{ns}product"
    namespaces: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedItem:
    position: int
    attributes: Attributes
    qnames: dict[str, str]  # field key -> original Clark name
    line: int | None


class _LimitedReader(io.RawIOBase):
    """Read-through wrapper that raises once ``limit`` bytes are exceeded."""

    def __init__(self, raw: BinaryIO, limit: int):
        self._raw = raw
        self._limit = limit
        self.read_bytes = 0

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        if not self.closed:
            self._raw.close()
        super().close()

    def readinto(self, buffer) -> int:  # type: ignore[override]
        data = self._raw.read(len(buffer))
        if not data:
            return 0
        self.read_bytes += len(data)
        if self.read_bytes > self._limit:
            raise FeedParseError(
                f"El XML (descomprimido) supera el límite de {self._limit // (1024 * 1024)} MB",
                code="size_limit",
            )
        buffer[: len(data)] = data
        return len(data)


def open_feed(path: Path, limits: ParserLimits) -> BinaryIO:
    """Open a stored feed, transparently decompressing GZIP with a size cap."""
    fh = open(path, "rb")
    head = fh.read(2)
    fh.seek(0)
    raw: BinaryIO = gzip.GzipFile(fileobj=fh, mode="rb") if head == GZIP_MAGIC else fh  # type: ignore[assignment]
    return io.BufferedReader(_LimitedReader(raw, limits.max_bytes), buffer_size=64 * 1024)  # type: ignore[arg-type]


def _iterparse(source: BinaryIO, events: tuple[str, ...]):
    return etree.iterparse(
        source,
        events=events,
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
        recover=False,
    )


def _check_no_dtd(element: etree._Element) -> None:
    docinfo = element.getroottree().docinfo
    if docinfo.doctype or docinfo.internalDTD is not None or docinfo.externalDTD is not None:
        raise FeedParseError("El XML contiene una declaración DOCTYPE/DTD, que no está permitida", code="xml_dtd_forbidden")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def _ns(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _syntax_error(exc: etree.XMLSyntaxError) -> FeedParseError:
    line = exc.position[0] if getattr(exc, "position", None) else exc.lineno
    return FeedParseError(f"XML mal formado: {exc.msg}", line=line, code="xml_malformed")


def detect_structure(path: Path, limits: ParserLimits, item_tag: str | None = None) -> FeedStructure:
    """Inspect the beginning of the document to determine where products live."""
    with open_feed(path, limits) as fh:
        _sniff_xml(fh)
        root: etree._Element | None = None
        depth = 0
        child_counts: Counter[tuple[int, str]] = Counter()
        namespaces: dict[str, str] = {}
        try:
            for event, el in _iterparse(fh, ("start-ns", "start", "end")):
                if event == "start-ns":
                    prefix, uri = el
                    namespaces.setdefault(prefix or "", uri)
                    continue
                if event == "start":
                    depth += 1
                    if root is None:
                        root = el
                        _check_no_dtd(el)
                        fmt = _known_format(el.tag)
                        if fmt and not item_tag:
                            return FeedStructure(fmt[0], el.tag, fmt[1], namespaces)
                    if depth > limits.max_depth:
                        raise FeedParseError("El XML supera la profundidad máxima permitida", code="depth_limit")
                    if depth in (2, 3):
                        child_counts[(depth, el.tag)] += 1
                    if sum(child_counts.values()) > 2000:
                        break
                else:
                    depth -= 1
                    if depth >= 2:
                        el.clear()
        except etree.XMLSyntaxError as exc:
            raise _syntax_error(exc) from exc

    if root is None:
        raise FeedParseError("El documento está vacío", code="xml_empty")
    if item_tag:
        resolved = _resolve_item_tag(item_tag, namespaces)
        return FeedStructure("custom" if not _known_format(root.tag) else _known_format(root.tag)[0], root.tag, resolved, namespaces)
    if not child_counts:
        raise FeedParseError("No se encontraron nodos repetidos de producto", code="no_items")
    (depth_, tag), _ = max(child_counts.items(), key=lambda kv: (kv[1], -kv[0][0]))
    return FeedStructure("custom", root.tag, tag, namespaces)


def _resolve_item_tag(item_tag: str, namespaces: dict[str, str]) -> str:
    if item_tag.startswith("{") or ":" not in item_tag:
        return item_tag
    prefix, local = item_tag.split(":", 1)
    uri = namespaces.get(prefix)
    if uri is None:
        raise FeedParseError(f"Prefijo de namespace desconocido: '{prefix}'", code="item_tag_invalid")
    return f"{{{uri}}}{local}"


def _known_format(root_tag: str) -> tuple[str, str] | None:
    if root_tag == "rss":
        return ("rss", "item")
    if root_tag == f"{{{ATOM_NS}}}feed":
        return ("atom", f"{{{ATOM_NS}}}entry")
    return None


def _sniff_xml(fh: BinaryIO) -> None:
    """Reject content that is clearly not XML before handing it to lxml."""
    head = fh.peek(512)[:512] if hasattr(fh, "peek") else b""
    text = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if text[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return  # UTF-16 BOM: let lxml decide
    if not text.startswith(b"<"):
        raise FeedParseError("El contenido no es XML", code="not_xml")


def iter_items(path: Path, structure: FeedStructure, limits: ParserLimits) -> Iterator[ParsedItem]:
    """Yield products one by one. Memory use is bounded by a single item."""
    position = 0
    depth = 0
    item_depth: int | None = None
    with open_feed(path, limits) as fh:
        _sniff_xml(fh)
        context = _iterparse(fh, ("start", "end"))
        try:
            for event, el in context:
                if event == "start":
                    depth += 1
                    if depth == 1:
                        _check_no_dtd(el)
                    if depth > limits.max_depth:
                        raise FeedParseError("El XML supera la profundidad máxima permitida", line=el.sourceline, code="depth_limit")
                    if item_depth is None and el.tag == structure.item_tag:
                        item_depth = depth
                    continue
                # end event
                if el.tag == structure.item_tag and depth == item_depth:
                    position += 1
                    if position > limits.max_items:
                        raise FeedParseError(f"El feed supera el máximo de {limits.max_items} productos", code="item_limit")
                    attrs, qnames = element_to_attributes(el, structure, limits)
                    yield ParsedItem(position, attrs, qnames, el.sourceline)
                    el.clear(keep_tail=False)
                    parent = el.getparent()
                    if parent is not None:
                        while el.getprevious() is not None:
                            del parent[0]
                depth -= 1
        except etree.XMLSyntaxError as exc:
            raise _syntax_error(exc) from exc


def _prefix_for(ns: str | None, nsmap: dict) -> str:
    if ns is None:
        return "rss"
    if ns == ATOM_NS:
        return "atom"
    for prefix, uri in nsmap.items():
        if uri == ns and prefix:
            return prefix
    return "ns"


_BARE_NAMESPACES = {GOOGLE_NS, None, ATOM_NS}


def element_to_attributes(item: etree._Element, structure: FeedStructure, limits: ParserLimits) -> tuple[Attributes, dict[str, str]]:
    """Convert an item element into the internal attribute model.

    Naming: Google-namespace, un-namespaced and Atom elements use their local
    name as key ("g:title" -> "title"). If an item contains the same local name
    from the Google namespace and another namespace, the Google one keeps the
    bare name and the other is prefixed ("rss:title") so values are never
    merged. Other namespaces always keep a prefix ("custom:foo").
    """
    children = [c for c in item if isinstance(c.tag, str)]
    google_locals = {_local(c.tag) for c in children if _ns(c.tag) in (GOOGLE_NS, GOOGLE_CUSTOM_NS)}
    attrs: Attributes = {}
    qnames: dict[str, str] = {}
    for child in children:
        ns, local = _ns(child.tag), _local(child.tag)
        if ns in (GOOGLE_NS, GOOGLE_CUSTOM_NS):
            key = local
        elif ns in _BARE_NAMESPACES and local not in google_locals:
            key = local
        else:
            key = f"{_prefix_for(ns, child.nsmap)}:{local}"
        value = _element_value(child, structure, limits, 1)
        if value is None:
            continue
        attrs.setdefault(key, []).append(value)
        qnames.setdefault(key, child.tag)
    return attrs, qnames


def _element_value(el: etree._Element, structure: FeedStructure, limits: ParserLimits, depth: int) -> Value | None:
    children = [c for c in el if isinstance(c.tag, str)]
    xml_attrs = {k: v for k, v in el.attrib.items()}
    text = el.text or ""
    if len(text) > limits.max_text_length:
        raise FeedParseError("Un valor de texto supera la longitud máxima", line=el.sourceline, code="text_limit")

    # Atom <link href="..."/> is the canonical product link.
    if structure.format == "atom" and _local(el.tag) == "link" and not children and "href" in xml_attrs:
        return xml_attrs["href"]

    if not children and not xml_attrs:
        return text
    if depth > 4:
        return text.strip()
    nested: dict[str, list[Value]] = {}
    for name, val in xml_attrs.items():
        nested.setdefault(f"@{_local(name)}", []).append(val)
    for child in children:
        value = _element_value(child, structure, limits, depth + 1)
        if value is not None:
            nested.setdefault(_local(child.tag), []).append(value)
    if text.strip():
        nested["#text"] = [text]
    return nested
