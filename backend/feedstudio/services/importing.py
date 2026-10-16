"""Feed import pipeline: fetch/receive -> store original -> parse -> persist."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from feedstudio.catalog.attributes import get_text
from feedstudio.config import get_settings
from feedstudio.db import session_scope
from feedstudio.ingestion.fetcher import FetchError, FetchPolicy, fetch_to_file
from feedstudio.ingestion.parser import FeedParseError, ParserLimits, detect_structure, iter_items
from feedstudio.ingestion.schema import SchemaCollector
from feedstudio.jobs import JobFailed, handler, report
from feedstudio.models import (
    FeedVersion,
    ProcessingJob,
    Product,
    Source,
    SourceSchemaField,
    SourceSnapshot,
    ValidationIssue,
    utcnow,
)
from feedstudio.rules.text import parse_price
from feedstudio.storage import get_storage
from feedstudio.validation.google import CatalogValidator, validate_product
from feedstudio.validation.issues import SEVERITY_ORDER, Severity, worst

BATCH = 500


def parser_limits() -> ParserLimits:
    s = get_settings()
    return ParserLimits(max_bytes=s.max_feed_mb * 1024 * 1024, max_items=s.max_items)


def fetch_policy() -> FetchPolicy:
    s = get_settings()
    return FetchPolicy(
        allow_http=s.allow_http_sources,
        max_bytes=s.max_feed_mb * 1024 * 1024,
        timeout_seconds=s.fetch_timeout_seconds,
        allow_private_networks=s.allow_private_networks,
    )


def snapshot_key(source_id: int, snapshot_id: int) -> str:
    return f"sources/{source_id}/snapshots/{snapshot_id}.xml"


def denormalize(data: dict) -> dict:
    title = get_text(data, "title")
    brand = get_text(data, "brand")
    ext = get_text(data, "id") or get_text(data, "sku")
    price = parse_price(get_text(data, "price"))
    search = " ".join(filter(None, [ext, title, brand, get_text(data, "mpn"), get_text(data, "gtin")])).casefold()
    return {
        "external_id": ext.strip()[:200] if ext else None,
        "title": title.strip()[:500] if title else None,
        "brand": brand.strip()[:200] if brand else None,
        "product_type": (get_text(data, "product_type") or "").strip()[:750] or None,
        "availability": (get_text(data, "availability") or "").strip()[:50] or None,
        "price_amount": price.amount if price.amount is not None and abs(price.amount) < 10**14 else None,
        "search_text": search[:4000],
    }


@handler("import")
def run_import(job_id: int) -> dict:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        snapshot = s.get(SourceSnapshot, job.params["snapshot_id"])
        source = s.get(Source, snapshot.source_id)
        snapshot.status = "processing"
        snapshot_id, source_id = snapshot.id, source.id
        url, item_tag, storage_key = source.url, source.item_tag, snapshot.storage_key
        previous_id = source.active_snapshot_id

    storage = get_storage()
    try:
        if storage_key is None:
            report(job_id, 0.02, "Descargando feed")
            key = snapshot_key(source_id, snapshot_id)
            try:
                result = fetch_to_file(url, storage.path(key), fetch_policy())
            except FetchError as exc:
                raise JobFailed(exc.message, code=exc.code) from exc
            with session_scope() as s:
                snap = s.get(SourceSnapshot, snapshot_id)
                snap.storage_key, snap.size_bytes, snap.sha256 = key, result.size_bytes, result.sha256
            storage_key = key
        return _parse_and_persist(job_id, source_id, snapshot_id, storage.path(storage_key), item_tag, previous_id)
    except JobFailed as exc:
        _fail_snapshot(snapshot_id, exc.code, exc.message, exc.detail.get("line"))
        raise
    except FeedParseError as exc:
        _fail_snapshot(snapshot_id, exc.code, exc.message, exc.line)
        raise JobFailed(exc.message, code=exc.code, detail={"line": exc.line}) from exc
    except Exception as exc:
        _fail_snapshot(snapshot_id, "internal_error", str(exc)[:500], None)
        raise


def _fail_snapshot(snapshot_id: int, code: str, message: str, line: int | None) -> None:
    with session_scope() as s:
        s.execute(delete(ValidationIssue).where(ValidationIssue.snapshot_id == snapshot_id))
        s.execute(delete(Product).where(Product.snapshot_id == snapshot_id))
        snap = s.get(SourceSnapshot, snapshot_id)
        snap.status = "failed"
        snap.error = {"code": code, "message": message, "line": line}
        snap.product_count = 0


def _parse_and_persist(job_id: int, source_id: int, snapshot_id: int, path: Path, item_tag: str | None, previous_id: int | None) -> dict:
    limits = parser_limits()
    started = time.perf_counter()
    report(job_id, 0.05, "Analizando estructura XML")
    structure = detect_structure(path, limits, item_tag)
    with session_scope() as s:
        previous = s.get(SourceSnapshot, previous_id) if previous_id else None
        estimate = previous.product_count if previous else 0
    collector = SchemaCollector()
    catalog_validator = CatalogValidator()
    product_rows: list[dict] = []
    issue_rows: list[tuple[int, list]] = []
    count = 0
    level_counts = {"valid": 0, "error": 0, "warning": 0, "recommendation": 0}

    def flush(session: Session) -> None:
        if not product_rows:
            return
        session.execute(insert(Product), product_rows)
        positions = [r["position"] for r in product_rows]
        ids = dict(session.execute(
            select(Product.position, Product.id).where(Product.snapshot_id == snapshot_id, Product.position.in_(positions))
        ).all())
        external = {r["position"]: r["external_id"] for r in product_rows}
        rows = [
            {"snapshot_id": snapshot_id, "product_id": ids[position], "external_id": external[position],
             "code": issue.code, "severity": issue.severity.value, "attribute": issue.attribute, "message": issue.message}
            for position, issues in issue_rows
            for issue in issues
        ]
        if rows:
            session.execute(insert(ValidationIssue), rows)
        product_rows.clear()
        issue_rows.clear()

    with session_scope() as s:
        for item in iter_items(path, structure, limits):
            count += 1
            collector.add(item.attributes, item.qnames)
            issues = validate_product(item.attributes) + catalog_validator.add(item.position, item.attributes)
            level = worst(issues)
            level_counts[level] += 1
            product_rows.append({"snapshot_id": snapshot_id, "position": item.position, "data": item.attributes,
                                 "issue_level": level, "issue_count": len(issues), **denormalize(item.attributes)})
            issue_rows.append((item.position, issues))
            if len(product_rows) >= BATCH:
                flush(s)
                # Commit per batch: keeps transactions short (SQLite allows a single
                # writer, and progress reports use their own transaction). The
                # snapshot only becomes active at the end; on failure its partial
                # rows are deleted by _fail_snapshot.
                s.commit()
                if count % (BATCH * 4) == 0:
                    # Progress is only an estimate when a previous import gives the expected size.
                    progress = 0.1 + 0.8 * min(1.0, count / estimate) if estimate else None
                    report(job_id, progress, f"{count} productos procesados")
        flush(s)
        _apply_catalog_issues(s, snapshot_id, catalog_validator.finalize())

    report(job_id, 0.93, "Guardando inventario de atributos")
    elapsed = time.perf_counter() - started
    with session_scope() as s:
        snap = s.get(SourceSnapshot, snapshot_id)
        for position, row in enumerate(collector.as_rows()):
            s.add(SourceSchemaField(snapshot_id=snapshot_id, position=position, **row))
        diff = _diff_with_previous(s, previous_id, snapshot_id)
        levels = dict(s.execute(
            select(Product.issue_level, func.count()).where(Product.snapshot_id == snapshot_id).group_by(Product.issue_level)
        ).all())
        snap.status = "ready"
        snap.format = structure.format
        snap.item_tag = structure.item_tag
        snap.namespaces = structure.namespaces
        snap.product_count = count
        snap.stats = {
            "fields": len(collector.fields),
            "parse_seconds": round(elapsed, 3),
            "issue_levels": levels,
            **diff,
        }
        snap.error = None
        source = s.get(Source, source_id)
        source.active_snapshot_id = snapshot_id
        source.last_refresh_at = utcnow()
        _apply_retention(s, source_id, snapshot_id)
    return {"snapshot_id": snapshot_id, "product_count": count, "fields": len(collector.fields), "seconds": round(elapsed, 3)}


def _apply_catalog_issues(s: Session, snapshot_id: int, extra: dict[int, list]) -> None:
    if not extra:
        return
    positions = list(extra)
    for i in range(0, len(positions), 900):
        chunk = positions[i : i + 900]
        products = s.execute(select(Product).where(Product.snapshot_id == snapshot_id, Product.position.in_(chunk))).scalars()
        for product in products:
            issues = extra[product.position]
            for issue in issues:
                s.add(ValidationIssue(snapshot_id=snapshot_id, product_id=product.id, external_id=product.external_id,
                                      code=issue.code, severity=issue.severity.value, attribute=issue.attribute, message=issue.message))
            product.issue_level = merge_level(product.issue_level, issues)
            product.issue_count += len(issues)


def merge_level(current: str, issues: list) -> str:
    levels = ([] if current == "valid" else [Severity(current)]) + [i.severity for i in issues]
    return min(levels, key=lambda lv: SEVERITY_ORDER[lv]).value if levels else "valid"


def _diff_with_previous(s: Session, previous_id: int | None, snapshot_id: int) -> dict:
    if previous_id is None:
        return {"previous_snapshot_id": None}
    prev = set(s.execute(select(Product.external_id).where(Product.snapshot_id == previous_id)).scalars())
    cur = set(s.execute(select(Product.external_id).where(Product.snapshot_id == snapshot_id)).scalars())
    return {"previous_snapshot_id": previous_id, "added": len(cur - prev), "removed": len(prev - cur), "kept": len(cur & prev)}


def _apply_retention(s: Session, source_id: int, active_id: int) -> None:
    """Drop parsed products of old snapshots that no feed version references.

    The original XML files are always kept: they are the immutable record.
    """
    keep = get_settings().snapshot_retention
    snapshots = s.execute(
        select(SourceSnapshot.id).where(SourceSnapshot.source_id == source_id, SourceSnapshot.status == "ready")
        .order_by(SourceSnapshot.id.desc())
    ).scalars().all()
    referenced = set(s.execute(select(FeedVersion.snapshot_id).distinct()).scalars())
    for old_id in snapshots[keep:]:
        if old_id != active_id and old_id not in referenced:
            s.execute(delete(ValidationIssue).where(ValidationIssue.snapshot_id == old_id))
            s.execute(delete(Product).where(Product.snapshot_id == old_id))
            snap = s.get(SourceSnapshot, old_id)
            snap.status = "archived"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
