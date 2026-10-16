"""Feed generation, publication and rollback."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Iterator

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from feedstudio.db import session_scope
from feedstudio.export.csv_export import write_csv
from feedstudio.export.google_xml import exportable, write_google_feed
from feedstudio.jobs import JobFailed, handler, report
from feedstudio.models import (
    Channel,
    FeedItem,
    FeedPublication,
    FeedVersion,
    ProcessingJob,
    Product,
    Rule,
    Source,
    SourceSchemaField,
    ValidationIssue,
    utcnow,
)
from feedstudio.rules.engine import CompiledRule, RuleEngine
from feedstudio.rules.schema import RuleDefinition
from feedstudio.storage import get_storage
from feedstudio.validation.google import CatalogValidator, validate_product
from feedstudio.validation.issues import worst

BATCH = 500


class PublishBlocked(Exception):
    def __init__(self, message: str, detail: dict):
        super().__init__(message)
        self.message = message
        self.detail = detail


def load_rules(s: Session, source_id: int, channel_id: int | None) -> list[CompiledRule]:
    """Global rules (channel_id NULL) run in stage 0, channel rules in stage 1."""
    query = select(Rule).where(Rule.source_id == source_id)
    rows = s.execute(query).scalars().all()
    out = []
    for r in rows:
        if r.channel_id is not None and r.channel_id != channel_id:
            continue
        out.append(CompiledRule(r.id, r.name, RuleDefinition.model_validate(r.definition), stage=0 if r.channel_id is None else 1))
    return out


def iter_products(s: Session, snapshot_id: int, batch: int = BATCH) -> Iterator[Product]:
    """Keyset pagination over products: constant memory per batch."""
    last = 0
    while True:
        rows = s.execute(
            select(Product).where(Product.snapshot_id == snapshot_id, Product.position > last)
            .order_by(Product.position).limit(batch)
        ).scalars().all()
        if not rows:
            return
        yield from rows
        last = rows[-1].position
        s.expunge_all()


@handler("generate")
def run_generate(job_id: int) -> dict:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        version = s.get(FeedVersion, job.params["version_id"])
        channel = s.get(Channel, version.channel_id)
        source = s.get(Source, channel.source_id)
        version_id, channel_id, snapshot_id = version.id, channel.id, version.snapshot_id
        settings = dict(channel.settings or {})
        source_name = source.name
        rules = load_rules(s, source.id, channel.id)
        version.rules_snapshot = [
            {"id": r.id, "name": r.name, "stage": r.stage, "definition": r.definition.model_dump(mode="json")} for r in rules
        ]
        total = s.scalar(select(func.count()).select_from(Product).where(Product.snapshot_id == snapshot_id)) or 0
    try:
        return _generate(job_id, version_id, channel_id, snapshot_id, rules, settings, source_name, total)
    except Exception as exc:
        with session_scope() as s:
            s.execute(delete(ValidationIssue).where(ValidationIssue.version_id == version_id))
            s.execute(delete(FeedItem).where(FeedItem.version_id == version_id))
            v = s.get(FeedVersion, version_id)
            v.status = "failed"
            v.error = {"message": getattr(exc, "message", str(exc))[:500]}
        if isinstance(exc, JobFailed):
            raise
        raise JobFailed(f"Error al generar el feed: {exc}", code="generate_failed") from exc


def _generate(job_id, version_id, channel_id, snapshot_id, rules, settings, source_name, total) -> dict:
    engine = RuleEngine(rules)
    catalog_validator = CatalogValidator()
    counts = Counter()
    issue_counter: Counter[tuple[str, str]] = Counter()
    rule_hits: Counter[int] = Counter()
    report(job_id, 0.02, f"Aplicando {len(engine.rules)} reglas a {total} productos")

    with session_scope() as s:
        items: list[dict] = []
        issues_rows: list[dict] = []
        processed = 0
        for product in iter_products(s, snapshot_id):
            processed += 1
            result = engine.apply(product.data)
            for rid in result.matched_rules:
                rule_hits[rid] += 1
            issues = [] if result.excluded else validate_product(result.data) + catalog_validator.add(product.position, result.data)
            level = "excluded" if result.excluded else worst(issues)
            counts[level] += 1
            counts["changed"] += bool(result.changes)
            touched = sorted({c.rule_id for c in result.changes} | set(result.excluded_by))
            items.append({
                "version_id": version_id, "product_id": product.id, "position": product.position,
                "external_id": product.external_id, "data": result.data, "excluded": result.excluded,
                "changed": bool(result.changes), "changes": [c.as_dict() for c in result.changes],
                "rule_ids": "," + ",".join(map(str, touched)) + "," if touched else "",
                "issue_level": level, "rule_issues": [i.as_dict() for i in result.issues],
            })
            for issue in issues:
                issue_counter[(issue.code, issue.severity.value)] += 1
                issues_rows.append({"version_id": version_id, "product_id": product.id, "external_id": product.external_id,
                                    "code": issue.code, "severity": issue.severity.value, "attribute": issue.attribute,
                                    "message": issue.message})
            if len(items) >= BATCH:
                _flush(s, items, issues_rows)
                report(job_id, 0.05 + 0.75 * processed / max(1, total), f"{processed}/{total} productos transformados")
        _flush(s, items, issues_rows)

        extra = catalog_validator.finalize()
        if extra:
            by_position = {}
            positions = list(extra)
            for i in range(0, len(positions), 900):
                chunk = positions[i : i + 900]
                for fi in s.execute(select(FeedItem).where(FeedItem.version_id == version_id, FeedItem.position.in_(chunk))).scalars():
                    by_position[fi.position] = fi
            from feedstudio.services.importing import merge_level

            for position, issues in extra.items():
                fi = by_position[position]
                counts[fi.issue_level] -= 1
                fi.issue_level = merge_level(fi.issue_level, issues)
                counts[fi.issue_level] += 1
                for issue in issues:
                    issue_counter[(issue.code, issue.severity.value)] += 1
                    s.add(ValidationIssue(version_id=version_id, product_id=fi.product_id, external_id=fi.external_id,
                                          code=issue.code, severity=issue.severity.value, attribute=issue.attribute,
                                          message=issue.message))

    report(job_id, 0.85, "Escribiendo XML")
    storage = get_storage()
    xml_key = f"feeds/{channel_id}/v{version_id}.xml"
    csv_key = f"feeds/{channel_id}/v{version_id}.csv"
    tmp_xml, tmp_csv = storage.temp_path(".xml"), storage.temp_path(".csv")
    with session_scope() as s:
        written = write_google_feed(
            tmp_xml,
            _included(s, version_id),
            settings.get("title") or source_name,
            settings.get("link") or "https://example.invalid",
            settings.get("description") or f"Feed generado por Feed Studio para {source_name}",
        )
        columns = _columns(s, snapshot_id, version_id)
        write_csv(tmp_csv, columns, _included(s, version_id))
    digest = hashlib.sha256(tmp_xml.read_bytes()).hexdigest()
    size = tmp_xml.stat().st_size
    storage.put_file(xml_key, tmp_xml)
    storage.put_file(csv_key, tmp_csv)

    with session_scope() as s:
        v = s.get(FeedVersion, version_id)
        v.status = "ready"
        v.storage_key, v.csv_storage_key, v.sha256, v.size_bytes = xml_key, csv_key, digest, size
        v.total_count = total
        v.item_count = written
        v.excluded_count = counts["excluded"]
        v.changed_count = counts["changed"]
        v.error_count = counts["error"]
        v.warning_count = counts["warning"]
        v.valid_count = counts["valid"] + counts["recommendation"]
        v.stats = {
            "issues": [{"code": c, "severity": sev, "count": n} for (c, sev), n in issue_counter.most_common()],
            "levels": {k: counts[k] for k in ("valid", "recommendation", "warning", "error", "excluded")},
            "rule_hits": {str(k): v_ for k, v_ in rule_hits.items()},
        }
    return {"version_id": version_id, "items": written, "excluded": counts["excluded"], "errors": counts["error"]}


def _flush(s: Session, items: list[dict], issues_rows: list[dict]) -> None:
    if items:
        s.execute(insert(FeedItem), items)
    if issues_rows:
        s.execute(insert(ValidationIssue), issues_rows)
    items.clear()
    issues_rows.clear()
    # Short transactions per batch (see importing.py); failed versions are cleaned up.
    s.commit()


def _included(s: Session, version_id: int) -> Iterator[dict]:
    last = 0
    while True:
        rows = s.execute(
            select(FeedItem.position, FeedItem.data).where(
                FeedItem.version_id == version_id, FeedItem.excluded.is_(False), FeedItem.position > last
            ).order_by(FeedItem.position).limit(BATCH)
        ).all()
        if not rows:
            return
        for _, data in rows:
            yield data
        last = rows[-1][0]


def _columns(s: Session, snapshot_id: int, version_id: int) -> list[str]:
    keys = list(s.execute(select(SourceSchemaField.key).where(SourceSchemaField.snapshot_id == snapshot_id)
                          .order_by(SourceSchemaField.position)).scalars())
    seen = set(keys)
    # Attributes created by rules (e.g. custom labels) are appended.
    for data in _included(s, version_id):
        for k in data:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return [k for k in keys if exportable(k)]


def publish(s: Session, channel: Channel, version: FeedVersion, actor: str, force: bool = False, action: str = "publish") -> FeedPublication:
    if version.channel_id != channel.id:
        raise ValueError("La versión no pertenece a este canal")
    if version.status != "ready":
        raise PublishBlocked("Solo se pueden publicar versiones generadas correctamente", {"status": version.status})
    current = s.get(FeedVersion, channel.published_version_id) if channel.published_version_id else None
    if current and not force and action == "publish":
        from feedstudio.config import get_settings

        threshold = get_settings().publish_drop_threshold
        if current.item_count and version.item_count < current.item_count * (1 - threshold):
            raise PublishBlocked(
                "La nueva versión reduce drásticamente el número de productos; confirma la publicación forzada",
                {"current_items": current.item_count, "new_items": version.item_count, "threshold": threshold},
            )
    channel.published_version_id = version.id  # single-row update: atomic switch
    pub = FeedPublication(channel_id=channel.id, version_id=version.id, published_by=actor, action=action, published_at=utcnow())
    s.add(pub)
    return pub
