"""Catalog = the active (or a selected) snapshot of a source."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.querying import issue_code_clause, parse_filters, search_clause, sort_column, filter_clause
from feedstudio.export.csv_export import write_csv
from feedstudio.models import Product, Source, SourceSchemaField, SourceSnapshot, ValidationIssue
from feedstudio.storage import get_storage
from feedstudio.validation.google import DEFINITIONS

router = APIRouter(prefix="/api/catalogs", tags=["catalogs"])

PAGE_SIZES = (10, 25, 50, 100)
EXPORT_LIMIT = 100_000


def resolve_snapshot(s: Session, p: Principal, source_id: int, snapshot_id: int | None = None) -> SourceSnapshot:
    source = owned(s, Source, source_id, p, "Catálogo")
    sid = snapshot_id or source.active_snapshot_id
    snap = s.get(SourceSnapshot, sid) if sid else None
    if snap is None or snap.source_id != source.id:
        raise ApiError(404, "no_catalog", "La fuente aún no tiene un catálogo importado")
    return snap


def _query(snap: SourceSnapshot, q, filters, issue_level, issue_code):
    stmt = select(Product).where(Product.snapshot_id == snap.id)
    if q:
        stmt = stmt.where(search_clause(q))
    for f in parse_filters(filters):
        stmt = stmt.where(filter_clause(Product, f))
    if issue_level:
        stmt = stmt.where(Product.issue_level == issue_level)
    if issue_code:
        stmt = stmt.where(issue_code_clause(Product, issue_code, None, snap.id))
    return stmt


def product_summary(p: Product) -> dict:
    return {"id": p.id, "position": p.position, "external_id": p.external_id, "data": p.data,
            "issue_level": p.issue_level, "issue_count": p.issue_count}


@router.get("/{source_id}/products")
def list_products(
    source_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    q: str | None = Query(None, max_length=200),
    filters: str | None = Query(None, description='JSON: [{"field":"brand","op":"equals","value":"X"}]'),
    issue_level: Literal["valid", "recommendation", "warning", "error"] | None = None,
    issue_code: str | None = Query(None, max_length=60),
    sort: str | None = Query(None, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_:.\-]*$"),
    order: Literal["asc", "desc"] = "asc",
    snapshot_id: int | None = None,
    s: Session = SessionDep,
    p: Principal = PrincipalDep,
):
    if page_size not in PAGE_SIZES:
        raise ApiError(422, "invalid_page_size", f"page_size debe ser uno de {PAGE_SIZES}")
    snap = resolve_snapshot(s, p, source_id, snapshot_id)
    stmt = _query(snap, q, filters, issue_level, issue_code)
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    col = sort_column(Product, sort)
    ordering = [col.desc() if order == "desc" else col.asc(), Product.position.asc()]
    rows = s.execute(stmt.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {"items": [product_summary(r) for r in rows], "total": total, "page": page, "page_size": page_size,
            "snapshot_id": snap.id}


@router.get("/{source_id}/products/export")
def export_products(
    source_id: int,
    q: str | None = Query(None, max_length=200),
    filters: str | None = None,
    issue_level: Literal["valid", "recommendation", "warning", "error"] | None = None,
    issue_code: str | None = Query(None, max_length=60),
    s: Session = SessionDep,
    p: Principal = PrincipalDep,
):
    """CSV export of the filtered products (original values)."""
    snap = resolve_snapshot(s, p, source_id)
    stmt = _query(snap, q, filters, issue_level, issue_code).order_by(Product.position).limit(EXPORT_LIMIT)
    columns = list(s.execute(select(SourceSchemaField.key).where(SourceSchemaField.snapshot_id == snap.id)
                             .order_by(SourceSchemaField.position)).scalars())
    tmp = get_storage().temp_path(".csv")
    rows = (r.data for r in s.execute(stmt).scalars())
    write_csv(tmp, columns, rows)
    return FileResponse(tmp, media_type="text/csv; charset=utf-8", filename=f"catalogo-{source_id}.csv",
                        background=BackgroundTask(tmp.unlink, missing_ok=True))


@router.get("/{source_id}/products/{product_id}")
def get_product(source_id: int, product_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Source, source_id, p, "Catálogo")
    product = s.get(Product, product_id)
    snap = s.get(SourceSnapshot, product.snapshot_id) if product else None
    if product is None or snap is None or snap.source_id != source_id:
        raise ApiError(404, "not_found", "Producto no encontrado")
    issues = s.execute(select(ValidationIssue).where(ValidationIssue.product_id == product.id,
                                                     ValidationIssue.snapshot_id == snap.id)).scalars()
    return {**product_summary(product),
            "issues": [{"code": i.code, "severity": i.severity, "attribute": i.attribute, "message": i.message} for i in issues]}


@router.get("/{source_id}/stats")
def catalog_stats(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    snap = resolve_snapshot(s, p, source_id)
    levels = dict(s.execute(select(Product.issue_level, func.count()).where(Product.snapshot_id == snap.id)
                            .group_by(Product.issue_level)).all())
    brands = s.execute(select(Product.brand, func.count()).where(Product.snapshot_id == snap.id)
                       .group_by(Product.brand).order_by(func.count().desc()).limit(10)).all()
    types = s.execute(select(Product.product_type, func.count()).where(Product.snapshot_id == snap.id)
                      .group_by(Product.product_type).order_by(func.count().desc()).limit(10)).all()
    availability = s.execute(select(Product.availability, func.count()).where(Product.snapshot_id == snap.id)
                             .group_by(Product.availability)).all()
    return {
        "snapshot_id": snap.id, "product_count": snap.product_count, "levels": levels,
        "top_brands": [{"value": b, "count": c} for b, c in brands],
        "top_product_types": [{"value": t, "count": c} for t, c in types],
        "availability": [{"value": a, "count": c} for a, c in availability],
        "stats": snap.stats,
    }


@router.get("/{source_id}/issues")
def catalog_issues(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    """Diagnostics of the ORIGINAL catalog (before rules), Google profile."""
    snap = resolve_snapshot(s, p, source_id)
    rows = s.execute(
        select(ValidationIssue.code, ValidationIssue.severity, func.count(func.distinct(ValidationIssue.product_id)))
        .where(ValidationIssue.snapshot_id == snap.id).group_by(ValidationIssue.code, ValidationIssue.severity)
    ).all()
    return {"snapshot_id": snap.id, "product_count": snap.product_count, "issues": issue_summary(rows)}


def issue_summary(rows) -> list[dict]:
    out = []
    for code, severity, count in rows:
        d = DEFINITIONS.get(code)
        out.append({
            "code": code, "severity": severity, "count": count,
            "title": d.title if d else code, "recommendation": d.recommendation if d else None,
            "source": d.source if d else None, "suggested_rule": d.suggested_rule if d else None,
        })
    order = {"error": 0, "warning": 1, "recommendation": 2}
    return sorted(out, key=lambda r: (order.get(r["severity"], 3), -r["count"]))


@router.get("/{source_id}/original")
def download_original(source_id: int, snapshot_id: int | None = None, s: Session = SessionDep, p: Principal = PrincipalDep):
    snap = resolve_snapshot(s, p, source_id, snapshot_id)
    if not snap.storage_key:
        raise ApiError(404, "not_found", "Archivo original no disponible")
    return FileResponse(get_storage().path(snap.storage_key), media_type="application/xml",
                        filename=snap.original_filename or f"original-{snap.id}.xml")
