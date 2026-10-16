"""Helpers to build test feeds."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape


def rss_item(i: int, **overrides: str | list[str] | None) -> str:
    fields: dict[str, str | list[str] | None] = {
        "g:id": f"SKU-{i:05d}",
        "title": f"Producto {i}",
        "description": f"Descripción del producto {i}",
        "link": f"https://tienda.example/p/{i}",
        "g:image_link": f"https://tienda.example/img/{i}.jpg",
        "g:price": "59.90 EUR",
        "g:availability": "in_stock",
        "g:condition": "new",
        "g:brand": "MarcaX",
        "g:color": "Negro",
        "g:size": "42",
    }
    fields.update(overrides)
    parts = []
    for tag, value in fields.items():
        if value is None:
            continue
        for v in value if isinstance(value, list) else [value]:
            parts.append(f"<{tag}>{escape(v)}</{tag}>")
    return "<item>" + "".join(parts) + "</item>"


def rss_feed(items: list[str], extra_ns: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"{extra_ns}><channel>'
        "<title>Tienda</title><link>https://tienda.example</link><description>Test</description>"
        + "".join(items)
        + "</channel></rss>"
    )


def write(tmp_path: Path, content: str | bytes, name: str = "feed.xml") -> Path:
    path = tmp_path / name
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def write_large_feed(path: Path, count: int) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel><title>T</title>')
        for i in range(count):
            fh.write(rss_item(i, **{"g:item_group_id": f"G-{i // 4}", "g:additional_image_link": [f"https://x.example/{i}-a.jpg", f"https://x.example/{i}-b.jpg"]}))
            fh.write("\n")
        fh.write("</channel></rss>")
    return path
