import gzip

import pytest

from feedstudio.ingestion.parser import FeedParseError, ParserLimits, detect_structure, iter_items
from feedstudio.ingestion.schema import SchemaCollector
from tests.factories import rss_feed, rss_item, write, write_large_feed

LIMITS = ParserLimits()


def parse(path, item_tag=None, limits=LIMITS):
    structure = detect_structure(path, limits, item_tag)
    return structure, list(iter_items(path, structure, limits))


def test_rss_with_google_namespace_ten_products(tmp_path):
    path = write(tmp_path, rss_feed([rss_item(i) for i in range(10)]))
    structure, items = parse(path)
    assert structure.format == "rss"
    assert len(items) == 10
    first = items[0].attributes
    assert first["id"] == ["SKU-00000"]
    assert first["title"] == ["Producto 0"]
    assert items[0].qnames["id"] == "{http://base.google.com/ns/1.0}id"
    assert items[0].qnames["title"] == "title"


def test_empty_feed_has_no_products(tmp_path):
    path = write(tmp_path, rss_feed([]))
    _, items = parse(path)
    assert items == []


def test_unknown_and_repeated_tags_are_preserved(tmp_path):
    item = rss_item(1, **{"g:additional_image_link": ["https://a/1.jpg", "https://a/2.jpg"], "g:mi_campo": "x", "c:extra": "y"})
    path = write(tmp_path, rss_feed([item], extra_ns=' xmlns:c="urn:custom"'))
    _, items = parse(path)
    attrs = items[0].attributes
    assert attrs["additional_image_link"] == ["https://a/1.jpg", "https://a/2.jpg"]
    assert attrs["mi_campo"] == ["x"]
    assert attrs["c:extra"] == ["y"]


def test_google_and_plain_title_are_not_merged(tmp_path):
    item = "<item><g:id>1</g:id><title>RSS</title><g:title>Google</g:title></item>"
    path = write(tmp_path, rss_feed([item]))
    _, items = parse(path)
    attrs = items[0].attributes
    assert attrs["title"] == ["Google"]
    assert attrs["rss:title"] == ["RSS"]


def test_nested_sub_attributes_and_xml_attributes(tmp_path):
    item = ("<item><g:id>1</g:id><g:tax><g:country>CL</g:country><g:rate>0</g:rate></g:tax>"
            '<g:shipping><g:country>CL</g:country><g:price currency="CLP">0</g:price></g:shipping></item>')
    path = write(tmp_path, rss_feed([item]))
    _, items = parse(path)
    attrs = items[0].attributes
    assert attrs["tax"] == [{"country": ["CL"], "rate": ["0"]}]
    assert attrs["shipping"][0]["price"] == [{"@currency": ["CLP"], "#text": ["0"]}]


def test_special_characters_and_cdata(tmp_path):
    item = "<item><g:id>1</g:id><title><![CDATA[Sofá «Ñandú» & Co <3]]></title><description>a &amp; b &lt;c&gt; 😀</description></item>"
    path = write(tmp_path, rss_feed([item]))
    _, items = parse(path)
    assert items[0].attributes["title"] == ["Sofá «Ñandú» & Co <3"]
    assert items[0].attributes["description"] == ["a & b <c> 😀"]


def test_malformed_xml_reports_line(tmp_path):
    path = write(tmp_path, '<?xml version="1.0"?>\n<rss version="2.0"><channel>\n<item><title>x</item></channel></rss>')
    with pytest.raises(FeedParseError) as exc:
        parse(path)
    assert exc.value.code == "xml_malformed"
    assert exc.value.line == 3


def test_not_xml_is_rejected(tmp_path):
    path = write(tmp_path, "id,title\n1,foo\n")
    with pytest.raises(FeedParseError) as exc:
        parse(path)
    assert exc.value.code == "not_xml"


@pytest.mark.parametrize(
    "payload",
    [
        # XXE: external entity reading a local file
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&x;</title></item></channel></rss>',
        # Billion laughs
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        '<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]><rss><channel><item><title>&c;</title></item></channel></rss>',
        # External DTD
        '<?xml version="1.0"?><!DOCTYPE rss SYSTEM "http://169.254.169.254/latest/meta-data"><rss><channel/></rss>',
    ],
)
def test_malicious_xml_is_rejected(tmp_path, payload):
    path = write(tmp_path, payload)
    with pytest.raises(FeedParseError) as exc:
        parse(path)
    assert exc.value.code in ("xml_dtd_forbidden", "xml_malformed")


def test_depth_limit(tmp_path):
    deep = "<a>" * 50 + "</a>" * 50
    path = write(tmp_path, f"<root><item>{deep}</item></root>")
    with pytest.raises(FeedParseError) as exc:
        parse(path, item_tag="item")
    assert exc.value.code == "depth_limit"


def test_gzip_input_and_decompression_bomb_limit(tmp_path):
    content = rss_feed([rss_item(i) for i in range(5)]).encode()
    path = write(tmp_path, gzip.compress(content), "feed.xml.gz")
    _, items = parse(path)
    assert len(items) == 5

    bomb = write(tmp_path, gzip.compress(b"<rss><channel>" + b" " * (5 * 1024 * 1024) + b"</channel></rss>"), "bomb.gz")
    with pytest.raises(FeedParseError) as exc:
        parse(bomb, limits=ParserLimits(max_bytes=1024 * 1024))
    assert exc.value.code == "size_limit"


def test_atom_feed(tmp_path):
    atom = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:g="http://base.google.com/ns/1.0">'
            '<title>T</title><entry><g:id>A1</g:id><title>Mesa</title><link href="https://t.example/a1"/>'
            "<g:price>10.00 EUR</g:price></entry></feed>")
    structure, items = parse(write(tmp_path, atom))
    assert structure.format == "atom"
    assert items[0].attributes["link"] == ["https://t.example/a1"]
    assert items[0].attributes["title"] == ["Mesa"]


def test_custom_xml_autodetects_repeated_product_nodes(tmp_path):
    custom = ("<catalogo><meta><v>1</v></meta><productos>"
              + "".join(f"<producto><sku>{i}</sku><nombre>P{i}</nombre></producto>" for i in range(6))
              + "</productos></catalogo>")
    structure, items = parse(write(tmp_path, custom))
    assert structure.item_tag == "producto"
    assert [i.attributes["sku"] for i in items][:2] == [["0"], ["1"]]


def test_custom_xml_with_explicit_item_tag(tmp_path):
    custom = "<root><x><p><id>1</id></p><p><id>2</id></p></x></root>"
    _, items = parse(write(tmp_path, custom), item_tag="p")
    assert len(items) == 2


def test_ten_thousand_products_stream_and_schema(tmp_path):
    path = write_large_feed(tmp_path / "big.xml", 10_000)
    structure = detect_structure(path, LIMITS)
    collector = SchemaCollector()
    count = 0
    for item in iter_items(path, structure, LIMITS):
        collector.add(item.attributes, item.qnames)
        count += 1
    assert count == 10_000
    rows = {r["key"]: r for r in collector.as_rows()}
    assert rows["additional_image_link"]["kind"] == "list"
    assert rows["price"]["inferred_type"] == "price"
    assert rows["link"]["inferred_type"] == "url"
    assert rows["id"]["coverage"] == 1.0
