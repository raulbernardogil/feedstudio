from lxml import etree

from feedstudio.export.csv_export import write_csv
from feedstudio.export.google_xml import write_google_feed
from feedstudio.ingestion.parser import GOOGLE_NS, ParserLimits, detect_structure, iter_items
from feedstudio.validation.google import CatalogValidator, validate_product
from feedstudio.validation.gtin import is_valid_gtin


def codes(attrs):
    return {i.code for i in validate_product(attrs)}


VALID = {
    "id": ["SKU-1"], "title": ["Zapatillas Runner Negro 42"], "description": ["Zapatillas de running con suela de goma y malla transpirable."],
    "link": ["https://t.example/p/1"], "image_link": ["https://t.example/i/1.jpg"], "price": ["59.90 EUR"],
    "availability": ["in_stock"], "condition": ["new"], "brand": ["MarcaX"], "gtin": ["4006381333931"],
    "google_product_category": ["187"],
}


def test_valid_product_has_no_issues():
    assert codes(VALID) == set()


def test_real_feed_patterns_are_flagged():
    attrs = {**VALID, "price": ["949.990,00 CLP"], "sale_price": ["569.990,00 CLP"], "availability": ["In Stock"],
             "identifier_exists": ["FALSE"], "link": ["http://www.tienda-demo.example/x.html"]}
    found = codes(attrs)
    assert {"price_locale_format", "sale_price_locale_format", "noncanonical_availability", "invalid_identifier_exists", "insecure_url"} <= found


def test_required_fields_and_formats():
    found = codes({"title": [""], "price": ["gratis"], "gtin": ["1234567890123"], "condition": ["nuevo"]})
    assert {"missing_id", "missing_title", "missing_description", "missing_link", "missing_image_link",
            "invalid_price", "invalid_gtin", "invalid_condition", "missing_availability"} <= found


def test_title_length_limit_150():
    assert "title_too_long" in codes({**VALID, "title": ["a" * 151]})
    assert "title_too_long" not in codes({**VALID, "title": ["a" * 150]})


def test_sale_price_checks():
    assert "sale_price_not_lower" in codes({**VALID, "sale_price": ["70.00 EUR"]})
    assert "currency_mismatch" in codes({**VALID, "sale_price": ["10.00 USD"]})


def test_gtin_check_digit():
    assert is_valid_gtin("4006381333931")
    assert is_valid_gtin("036000291452")
    assert not is_valid_gtin("4006381333932")
    assert not is_valid_gtin("12345")


def test_duplicates_and_legitimate_variants():
    v = CatalogValidator()
    a = v.add(1, {"id": ["1"], "title": ["Sofá"], "item_group_id": ["G"], "color": ["Gris"], "size": ["2"]})
    b = v.add(2, {"id": ["2"], "title": ["Sofá"], "item_group_id": ["G"], "color": ["Gris"], "size": ["3"]})
    c = v.add(3, {"id": ["1"], "title": ["Mesa"]})
    d = v.add(4, {"id": ["4"], "title": ["Sofá"], "item_group_id": ["G"], "color": ["gris"], "size": ["3"]})
    assert a == [] and b == []  # legitimate variants: same title, different size
    assert [i.code for i in c] == ["duplicate_id"]
    assert [i.code for i in d] == ["duplicate_variant"]
    extra = v.finalize()
    assert 1 not in extra and 2 not in extra


def test_same_title_without_group_detected_as_missing_group():
    v = CatalogValidator()
    v.add(1, {"id": ["1"], "title": ["Polera"], "color": ["Rojo"]})
    v.add(2, {"id": ["2"], "title": ["Polera"], "color": ["Azul"]})
    v.add(3, {"id": ["3"], "title": ["Taza"]})
    v.add(4, {"id": ["4"], "title": ["Taza"]})
    extra = v.finalize()
    assert [i.code for i in extra[1]] == ["variant_missing_group"]
    assert [i.code for i in extra[4]] == ["duplicate_title"]
    assert 3 not in extra


def test_export_is_valid_xml_and_roundtrips_unmodified_attributes(tmp_path):
    items = [
        {**VALID, "additional_image_link": ["https://t.example/a.jpg", "https://t.example/b.jpg"],
         "tax": [{"country": ["CL"], "rate": ["0"], "tax_ship": ["y"]}], "product_width": ["188 cm"],
         "description": ["Sofá «Ñandú» & <cojines>\x0b"], "empty": [""], "_segments": ["x"], "c:extra": ["no"]},
    ]
    out = tmp_path / "google.xml"
    assert write_google_feed(out, items, "Tienda", "https://t.example", "Feed") == 1

    root = etree.parse(str(out)).getroot()
    assert root.tag == "rss" and root.nsmap["g"] == GOOGLE_NS
    item = root.find("channel/item")
    assert item.find(f"{{{GOOGLE_NS}}}empty") is None
    assert item.find(f"{{{GOOGLE_NS}}}_segments") is None

    limits = ParserLimits()
    structure = detect_structure(out, limits)
    [reimported] = list(iter_items(out, structure, limits))
    attrs = reimported.attributes
    for key in ("id", "title", "price", "gtin", "additional_image_link", "tax", "product_width"):
        assert attrs[key] == items[0][key], key
    assert attrs["description"] == ["Sofá «Ñandú» & <cojines>"]  # invalid control char removed
    assert "c:extra" not in attrs and "empty" not in attrs


def test_csv_export_escapes_formulas(tmp_path):
    out = tmp_path / "f.csv"
    write_csv(out, ["id", "title", "tax"], [{"id": ["1"], "title": ["=HYPERLINK(1)"], "tax": [{"country": ["CL"]}]}])
    content = out.read_text(encoding="utf-8-sig").splitlines()
    assert content[0] == "id,title,tax"
    assert content[1] == "1,'=HYPERLINK(1),country=CL"


def by_code(attrs):
    return {i.code: i for i in validate_product(attrs)}


def test_readable_but_undocumented_formats_are_warnings_not_errors():
    issues = by_code({**VALID, "price": ["949.990,00 CLP"], "sale_price": ["569.990,00 CLP"],
                      "availability": ["In Stock"], "condition": ["New"]})
    for code in ("price_locale_format", "sale_price_locale_format", "noncanonical_availability", "noncanonical_value"):
        assert issues[code].severity.value == "warning", code
    assert not any(i.severity.value == "error" for i in issues.values())


def test_unreadable_values_remain_errors():
    issues = by_code({**VALID, "price": ["consultar"], "availability": ["disponible"], "condition": ["nuevo"]})
    assert issues["invalid_price"].severity.value == "error"
    assert issues["invalid_availability"].severity.value == "error"
    assert issues["invalid_condition"].severity.value == "error"


def test_messages_explain_the_problem_and_value():
    issues = by_code({**VALID, "price": ["949.990,00 CLP"], "availability": ["In Stock"]})
    assert issues["price_locale_format"].message == (
        "Precio con formato no documentado (separadores locales): «949.990,00 CLP» se interpreta como 949990.00 CLP")
    assert issues["noncanonical_availability"].message == "Disponibilidad con formato no documentado: «In Stock» → in_stock"
