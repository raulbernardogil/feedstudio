"""End-to-end acceptance scenario through the HTTP API (section 24)."""

import json
from pathlib import Path

from lxml import etree

from feedstudio.ingestion.parser import GOOGLE_NS, ParserLimits, detect_structure, iter_items
from tests.factories import rss_feed, rss_item

G = f"{{{GOOGLE_NS}}}"


def make_catalog() -> str:
    items = []
    for i in range(30):
        overrides = {
            "g:price": f"{(i + 1) * 10}.990,00 CLP",
            "g:availability": "In Stock",
            "g:product_type": "Muebles/Sofás" if i % 3 else "Muebles/Outlet",
            "g:brand": "Solano" if i % 2 else "Nordlicht",
            "g:color": None if i == 5 else "Gris",
            "g:size": "2 Cuerpos",
            "description": "" if i % 5 == 0 else f"Descripción larga del producto número {i} con detalles de materiales.",
            "g:item_group_id": f"G{i // 2}",
            "g:tax": None,
        }
        if i == 7:
            overrides["title"] = "Nordlicht Sofá"  # already contains the brand
            overrides["g:brand"] = "Nordlicht"
        items.append(rss_item(i, **overrides).replace("</item>", "<g:tax><g:country>CL</g:country><g:rate>0</g:rate></g:tax></item>"))
    return rss_feed(items)


def upload(client, content: str, name="Tienda Demo", source_id=None):
    data = {"name": name}
    if source_id:
        data["source_id"] = str(source_id)
    res = client.post("/api/sources/upload", data=data, files={"file": ("feed.xml", content.encode(), "application/xml")})
    assert res.status_code == 202, res.text
    return res.json()


def job(client, job_id):
    return client.get(f"/api/jobs/{job_id}").json()


def test_full_acceptance_flow(app_client, tmp_path: Path):
    c = app_client
    up = upload(c, make_catalog())
    source_id = up["source"]["id"]
    assert job(c, up["job"]["id"])["status"] == "succeeded"

    # 3. products & attributes identified
    schema = c.get(f"/api/sources/{source_id}/schema").json()
    keys = {f["key"] for f in schema["fields"]}
    assert {"id", "title", "price", "brand", "tax", "item_group_id"} <= keys
    assert next(f for f in schema["fields"] if f["key"] == "tax")["kind"] == "nested"

    # 4/5. paginated table + SKU search
    page = c.get(f"/api/catalogs/{source_id}/products", params={"page_size": 10}).json()
    assert page["total"] == 30 and len(page["items"]) == 10
    page3 = c.get(f"/api/catalogs/{source_id}/products", params={"page_size": 10, "page": 3}).json()
    assert page3["items"][0]["external_id"] == "SKU-00020"
    found = c.get(f"/api/catalogs/{source_id}/products", params={"q": "SKU-00007"}).json()
    assert [p["external_id"] for p in found["items"]] == ["SKU-00007"]
    filt = c.get(f"/api/catalogs/{source_id}/products",
                 params={"filters": json.dumps([{"field": "brand", "op": "equals", "value": "solano"}])}).json()
    assert filt["total"] == 14  # odd SKUs, except SKU-7 forced to Nordlicht
    sorted_desc = c.get(f"/api/catalogs/{source_id}/products", params={"sort": "price", "order": "desc"}).json()
    assert sorted_desc["items"][0]["external_id"] == "SKU-00029"

    # Original diagnostics show real-feed problems.
    issues = {i["code"] for i in c.get(f"/api/catalogs/{source_id}/issues").json()["issues"]}
    assert {"price_locale_format", "noncanonical_availability", "missing_description"} <= issues

    channel = c.post("/api/channels", json={"source_id": source_id, "name": "Google Chile", "kind": "google",
                                            "settings": {"title": "Solano", "link": "https://www.tienda-demo.example"}}).json()
    cid = channel["id"]

    def rule(definition, channel_id=None):
        res = c.post("/api/rules", json={"source_id": source_id, "channel_id": channel_id, "definition": definition})
        assert res.status_code == 201, res.text
        return res.json()

    outlet_guard = {"field": "product_type", "operator": "not_contains", "value": "Outlet"}
    # 6. prepend brand if absent
    r_brand = rule({"name": "Marca delante", "priority": 10, "target": "title",
                    "condition": {"operator": "and", "conditions": [
                        {"field": "brand", "operator": "not_empty"},
                        {"field": "title", "operator": "not_contains", "value_field": "brand"}, outlet_guard]},
                    "actions": [{"type": "prepend", "template": "{brand} "}]}, cid)
    # 7 + 8. color and size, not for Outlet category
    rule({"name": "Color y talla", "priority": 20, "target": "title",
          "condition": {"operator": "and", "conditions": [outlet_guard]},
          "actions": [{"type": "append", "template": "[ - {color}][ - {size}]"}]}, cid)
    # 9. generic description when empty
    rule({"name": "Descripción de respaldo", "priority": 30, "target": "description",
          "actions": [{"type": "set_if_empty", "template": "{title}[ de {brand}].[ Color {color}.]"}]})
    # Normalizations suggested by diagnostics
    rule({"name": "Precio", "priority": 1, "target": "price", "actions": [{"type": "normalize_price"}]})
    rule({"name": "Disponibilidad", "priority": 2, "target": "availability",
          "actions": [{"type": "map_values", "mappings": [{"from": "In Stock", "to": "in_stock"}]}]})

    # 10. preview ten products before/after with the same engine
    preview = c.post("/api/rules/preview", json={"source_id": source_id, "channel_id": cid, "rule_id": r_brand["id"],
                                                 "definition": r_brand["definition"], "page_size": 10}).json()
    assert preview["affected"] == 30 - 10 - 1  # 10 outlet products, SKU-7 already has brand
    assert len(preview["items"]) == 10
    assert preview["items"][0]["after"].startswith("Nordlicht Producto 1") or preview["items"][0]["after"].startswith("Solano ")
    test = c.post("/api/rules/test", json={"source_id": source_id, "channel_id": cid, "external_id": "SKU-00001",
                                           "definition": r_brand["definition"], "rule_id": r_brand["id"]}).json()
    assert test["after"]["title"] == ["Solano Producto 1 - Gris - 2 Cuerpos"]

    # 11/12. generate & diagnostics
    gen = c.post("/api/feeds/generate", json={"channel_id": cid}).json()
    assert job(c, gen["job"]["id"])["status"] == "succeeded", job(c, gen["job"]["id"])
    vid = gen["version"]["id"]
    version = c.get(f"/api/feed-versions/{vid}").json()
    assert version["status"] == "ready" and version["item_count"] == 30
    report = c.get(f"/api/feed-versions/{vid}/issues").json()
    codes = {i["code"] for i in report["issues"]}
    assert "price_locale_format" not in codes and "noncanonical_availability" not in codes and "missing_description" not in codes

    items = c.get(f"/api/feed-versions/{vid}/items", params={"only_changed": True, "page_size": 10}).json()
    assert items["total"] == 30
    by_rule = c.get(f"/api/feed-versions/{vid}/items", params={"rule_id": r_brand["id"], "page_size": 100}).json()
    assert by_rule["total"] == 19

    # 13. download XML, valid for Google namespace
    res = c.get(f"/api/feed-versions/{vid}/download")
    assert res.status_code == 200
    out = tmp_path / "out.xml"
    out.write_bytes(res.content)
    root = etree.parse(str(out)).getroot()
    xml_items = root.findall("channel/item")
    assert len(xml_items) == 30
    by_id = {it.findtext(G + "id"): it for it in xml_items}
    assert by_id["SKU-00001"].findtext(G + "title") == "Solano Producto 1 - Gris - 2 Cuerpos"
    assert by_id["SKU-00001"].findtext(G + "price") == "20990.00 CLP"
    assert by_id["SKU-00005"].findtext(G + "title") == "Solano Producto 5 - 2 Cuerpos"  # no color: no dangling separator
    assert by_id["SKU-00000"].findtext(G + "description") == "Producto 0 de Nordlicht. Color Gris."
    # 14. unaffected values preserved (outlet product title untouched)
    assert by_id["SKU-00003"].findtext(G + "title") == "Producto 3"
    assert by_id["SKU-00007"].findtext(G + "title") == "Nordlicht Sofá - Gris - 2 Cuerpos"
    assert by_id["SKU-00003"].find(G + "tax").findtext(G + "country") == "CL"

    # 15. reimport the output: no relevant attributes lost
    limits = ParserLimits()
    reparsed = {i.attributes["id"][0]: i.attributes for i in iter_items(out, detect_structure(out, limits), limits)}
    original = {p["external_id"]: p["data"] for p in c.get(f"/api/catalogs/{source_id}/products", params={"page_size": 100}).json()["items"]}
    for sku, attrs in original.items():
        lost = {k for k, v in attrs.items() if any(isinstance(x, dict) or x.strip() for x in v)} - set(reparsed[sku])
        assert not lost, (sku, lost)

    # Publish + stable public URL
    pub = c.post(f"/api/feed-versions/{vid}/publish").json()
    public = c.get(pub["public_url"].replace("http://testserver", ""))
    assert public.status_code == 200
    assert public.headers["content-type"].startswith("application/xml")
    assert public.headers["x-feed-version"] == "1"
    assert c.get(pub["public_url"].replace("http://testserver", ""), headers={"If-None-Match": public.headers["etag"]}).status_code == 304
    assert c.get(f"/f/{channel['public_url'].split('/f/')[1].split('/')[0]}/meta.xml").status_code == 404


def test_publish_safety_threshold_and_rollback(app_client):
    c = app_client
    up = upload(c, rss_feed([rss_item(i) for i in range(20)]))
    sid = up["source"]["id"]
    cid = c.post("/api/channels", json={"source_id": sid, "name": "G"}).json()["id"]
    v1 = c.post("/api/feeds/generate", json={"channel_id": cid}).json()["version"]["id"]
    c.post(f"/api/feed-versions/{v1}/publish")

    exclude = c.post("/api/rules", json={"source_id": sid, "channel_id": cid, "definition": {
        "name": "Excluir casi todo", "condition": {"conditions": [{"field": "id", "operator": "not_equals", "value": "SKU-00000"}]},
        "actions": [{"type": "exclude"}]}}).json()
    v2 = c.post("/api/feeds/generate", json={"channel_id": cid}).json()["version"]["id"]
    assert c.get(f"/api/feed-versions/{v2}").json()["item_count"] == 1
    blocked = c.post(f"/api/feed-versions/{v2}/publish")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "publish_blocked"
    # excluded products remain in the internal catalog
    assert c.get(f"/api/feed-versions/{v2}/items", params={"excluded": True}).json()["total"] == 19
    forced = c.post(f"/api/feed-versions/{v2}/publish", json={"force": True}).json()
    assert forced["published_version_id"] == v2
    rollback = c.post(f"/api/feed-versions/{v1}/publish").json()
    assert rollback["published_version_id"] == v1
    actions = [p["action"] for p in c.get(f"/api/channels/{cid}/publications").json()["items"]]
    assert actions == ["rollback", "publish", "publish"]
    c.delete(f"/api/rules/{exclude['id']}")


def test_failed_sync_keeps_previous_catalog(app_client):
    c = app_client
    up = upload(c, rss_feed([rss_item(i) for i in range(5)]))
    sid = up["source"]["id"]
    bad = upload(c, "<rss><channel><item><title>x</channel></rss>", source_id=sid)
    failed = job(c, bad["job"]["id"])
    assert failed["status"] == "failed" and failed["error"]["code"] == "xml_malformed"
    source = c.get(f"/api/sources/{sid}").json()
    assert source["active_snapshot"]["product_count"] == 5
    snaps = c.get(f"/api/sources/{sid}/snapshots").json()["items"]
    assert snaps[0]["status"] == "failed" and snaps[0]["error"]["line"] == 1


def test_concurrent_imports_are_rejected(app_client):
    from feedstudio.db import session_scope
    from feedstudio.models import ProcessingJob

    c = app_client
    sid = upload(c, rss_feed([rss_item(1)]))["source"]["id"]
    with session_scope() as s:
        s.add(ProcessingJob(organization_id=1, kind="import", status="running", source_id=sid, params={}, events=[]))
    res = c.post("/api/sources/upload", data={"name": "x", "source_id": str(sid)},
                 files={"file": ("f.xml", rss_feed([rss_item(1)]).encode(), "application/xml")})
    assert res.status_code == 409 and res.json()["error"]["code"] == "import_in_progress"


def test_url_sources_reject_private_and_plain_http(app_client):
    c = app_client
    for url in ("https://127.0.0.1/feed.xml", "https://169.254.169.254/latest", "http://example.com/feed.xml",
                "file:///etc/passwd", "https://user:pw@example.com/f.xml", "https://localhost:8080/x.xml"):
        res = c.post("/api/sources", json={"name": "x", "url": url})
        assert res.status_code == 422, url


def test_invalid_rules_rejected_with_structured_errors(app_client):
    c = app_client
    sid = upload(c, rss_feed([rss_item(1)]))["source"]["id"]
    res = c.post("/api/rules", json={"source_id": sid, "definition": {
        "name": "bad", "target": "title", "actions": [{"type": "replace", "find": "([", "use_regex": True}]}})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
    res = c.post("/api/rules", json={"source_id": sid, "definition": {"name": "bad", "target": "title",
                                                                      "actions": [{"type": "set_value", "template": "{brand"}]}})
    assert res.status_code == 422


def test_rule_versioning_and_audit(app_client):
    c = app_client
    sid = upload(c, rss_feed([rss_item(1)]))["source"]["id"]
    r = c.post("/api/rules", json={"source_id": sid, "definition": {"name": "a", "target": "title", "actions": [{"type": "uppercase"}]}}).json()
    c.put(f"/api/rules/{r['id']}", json={"definition": {"name": "b", "target": "title", "actions": [{"type": "lowercase"}]}})
    versions = c.get(f"/api/rules/{r['id']}/versions").json()["items"]
    assert [v["version"] for v in versions] == [2, 1]
    actions = {a["action"] for a in c.get("/api/audit-logs").json()["items"]}
    assert {"rule.create", "rule.update", "source.upload"} <= actions


def test_pagination_validation_and_dashboard(app_client):
    c = app_client
    sid = upload(c, rss_feed([rss_item(i) for i in range(12)]))["source"]["id"]
    assert c.get(f"/api/catalogs/{sid}/products", params={"page_size": 7}).status_code == 422
    assert c.get(f"/api/catalogs/{sid}/products", params={"filters": "not json"}).status_code == 422
    last = c.get(f"/api/catalogs/{sid}/products", params={"page_size": 10, "page": 2}).json()
    assert len(last["items"]) == 2
    dash = c.get("/api/dashboard").json()
    assert dash["sources"] == 1 and dash["products"] == 12
    assert c.get("/health").json()["status"] == "ok"
    assert c.get(f"/api/catalogs/{sid}/products/export").status_code == 200
