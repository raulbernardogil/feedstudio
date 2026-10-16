from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from feedstudio.api.catalogs import issue_summary, resolve_snapshot
from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, audit, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.querying import filter_clause, issue_code_clause, parse_filters, sort_column
from feedstudio.api.serializers import channel_out, dt, job_out, version_out
from feedstudio.jobs import get_runner
from feedstudio.models import Channel, FeedItem, FeedPublication, FeedVersion, ProcessingJob, Product, Source, ValidationIssue
from feedstudio.services.feeds import PublishBlocked, publish
from feedstudio.storage import get_storage

router = APIRouter(prefix="/api", tags=["channels & feeds"])


class ChannelSettings(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    link: str | None = Field(default=None, max_length=500, pattern=r"^https?://")
    description: str | None = Field(default=None, max_length=1000)


class ChannelCreate(BaseModel):
    source_id: int
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["google"] = "google"
    settings: ChannelSettings = ChannelSettings()


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: ChannelSettings | None = None


class GenerateRequest(BaseModel):
    channel_id: int


class PublishRequest(BaseModel):
    force: bool = False


def _channel(s: Session, p: Principal, channel_id: int) -> Channel:
    return owned(s, Channel, channel_id, p, "Canal")


def _version(s: Session, p: Principal, version_id: int) -> tuple[FeedVersion, Channel]:
    v = s.get(FeedVersion, version_id)
    if v is None:
        raise ApiError(404, "not_found", "Versión no encontrada")
    return v, _channel(s, p, v.channel_id)


@router.get("/channels")
def list_channels(source_id: int | None = None, s: Session = SessionDep, p: Principal = PrincipalDep):
    stmt = select(Channel).where(Channel.organization_id == p.organization_id)
    if source_id:
        stmt = stmt.where(Channel.source_id == source_id)
    rows = s.execute(stmt.order_by(Channel.id)).scalars().all()
    return {"items": [channel_out(c, s.get(FeedVersion, c.published_version_id) if c.published_version_id else None) for c in rows]}


@router.post("/channels", status_code=201)
def create_channel(body: ChannelCreate, s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Source, body.source_id, p, "Fuente")
    channel = Channel(organization_id=p.organization_id, source_id=body.source_id, name=body.name, kind=body.kind,
                      public_token=secrets.token_urlsafe(24), settings=body.settings.model_dump(exclude_none=True))
    s.add(channel)
    s.flush()
    audit(s, p, "channel.create", "channel", channel.id, {"kind": body.kind})
    s.commit()
    return channel_out(channel)


@router.get("/channels/{channel_id}")
def get_channel(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    c = _channel(s, p, channel_id)
    return channel_out(c, s.get(FeedVersion, c.published_version_id) if c.published_version_id else None)


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, body: ChannelUpdate, s: Session = SessionDep, p: Principal = PrincipalDep):
    c = _channel(s, p, channel_id)
    if body.name:
        c.name = body.name
    if body.settings is not None:
        c.settings = body.settings.model_dump(exclude_none=True)
    audit(s, p, "channel.update", "channel", c.id)
    s.commit()
    return channel_out(c)


@router.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    c = _channel(s, p, channel_id)
    c.published_version_id = None
    s.flush()
    audit(s, p, "channel.delete", "channel", c.id, {"name": c.name})
    s.delete(c)
    s.commit()


@router.post("/channels/{channel_id}/rotate-token")
def rotate_token(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    """Revoke the current public URL and issue a new one."""
    c = _channel(s, p, channel_id)
    c.public_token = secrets.token_urlsafe(24)
    audit(s, p, "channel.rotate_token", "channel", c.id)
    s.commit()
    return channel_out(c)


@router.get("/channels/{channel_id}/versions")
def list_versions(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    c = _channel(s, p, channel_id)
    rows = s.execute(select(FeedVersion).where(FeedVersion.channel_id == c.id).order_by(FeedVersion.id.desc()).limit(100)).scalars()
    return {"items": [{**version_out(v), "published": v.id == c.published_version_id} for v in rows]}


@router.get("/channels/{channel_id}/publications")
def list_publications(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    c = _channel(s, p, channel_id)
    rows = s.execute(select(FeedPublication).where(FeedPublication.channel_id == c.id).order_by(FeedPublication.id.desc()).limit(100)).scalars()
    return {"items": [{"id": r.id, "version_id": r.version_id, "action": r.action, "published_at": dt(r.published_at),
                       "published_by": r.published_by} for r in rows]}


@router.post("/feeds/generate", status_code=202)
def generate(body: GenerateRequest, s: Session = SessionDep, p: Principal = PrincipalDep):
    """Apply rules + validate + build a candidate version (not published)."""
    c = _channel(s, p, body.channel_id)
    snap = resolve_snapshot(s, p, c.source_id)
    running = s.scalar(select(ProcessingJob.id).where(ProcessingJob.channel_id == c.id, ProcessingJob.kind == "generate",
                                                      ProcessingJob.status.in_(("queued", "running"))))
    if running:
        raise ApiError(409, "generate_in_progress", "Ya se está generando una versión de este canal", {"job_id": running})
    number = (s.scalar(select(func.max(FeedVersion.number)).where(FeedVersion.channel_id == c.id)) or 0) + 1
    version = FeedVersion(channel_id=c.id, snapshot_id=snap.id, number=number, status="building")
    s.add(version)
    s.flush()
    job = ProcessingJob(organization_id=p.organization_id, kind="generate", source_id=c.source_id, channel_id=c.id,
                        params={"version_id": version.id}, events=[])
    s.add(job)
    s.flush()
    version.job_id = job.id
    s.commit()
    get_runner().enqueue(job.id)
    s.refresh(job)
    return {"version": version_out(version), "job": job_out(job)}


# Validation runs as part of generation: a candidate version is the validation report.
router.add_api_route("/validations/run", generate, methods=["POST"], status_code=202, tags=["validations"],
                     summary="Run validation (generates a candidate version)")


@router.get("/feed-versions/{version_id}")
def get_version(version_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    v, c = _version(s, p, version_id)
    return {**version_out(v), "published": v.id == c.published_version_id, "rules": v.rules_snapshot}


@router.post("/feed-versions/{version_id}/publish")
def publish_version(version_id: int, body: PublishRequest | None = None, s: Session = SessionDep, p: Principal = PrincipalDep):
    v, c = _version(s, p, version_id)
    current = c.published_version_id
    action = "rollback" if current and v.id < current else "publish"
    try:
        publish(s, c, v, p.actor, force=bool(body and body.force), action=action)
    except PublishBlocked as exc:
        raise ApiError(409, "publish_blocked", exc.message, exc.detail) from exc
    audit(s, p, f"feed.{action}", "feed_version", v.id, {"channel_id": c.id, "previous": current})
    s.commit()
    return channel_out(c, v)


@router.get("/feed-versions/{version_id}/download")
def download_version(version_id: int, format: Literal["xml", "csv"] = "xml", s: Session = SessionDep, p: Principal = PrincipalDep):
    v, c = _version(s, p, version_id)
    key = v.storage_key if format == "xml" else v.csv_storage_key
    if v.status != "ready" or not key:
        raise ApiError(409, "not_ready", "La versión aún no está disponible")
    media = "application/xml" if format == "xml" else "text/csv; charset=utf-8"
    return FileResponse(get_storage().path(key), media_type=media, filename=f"{c.kind}-v{v.number}.{format}")


@router.get("/feed-versions/{version_id}/issues")
def version_issues(version_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    v, _ = _version(s, p, version_id)
    rows = s.execute(
        select(ValidationIssue.code, ValidationIssue.severity, func.count(func.distinct(ValidationIssue.product_id)))
        .where(ValidationIssue.version_id == v.id).group_by(ValidationIssue.code, ValidationIssue.severity)
    ).all()
    previous = s.scalar(select(FeedVersion).where(FeedVersion.channel_id == v.channel_id, FeedVersion.id < v.id,
                                                  FeedVersion.status == "ready").order_by(FeedVersion.id.desc()).limit(1))
    prev_counts = {}
    if previous:
        prev_counts = {(c, sev): n for c, sev, n in s.execute(
            select(ValidationIssue.code, ValidationIssue.severity, func.count(func.distinct(ValidationIssue.product_id)))
            .where(ValidationIssue.version_id == previous.id).group_by(ValidationIssue.code, ValidationIssue.severity)).all()}
    summary = issue_summary(rows)
    for row in summary:
        row["previous_count"] = prev_counts.get((row["code"], row["severity"])) if previous else None
    return {"version_id": v.id, "previous_version_id": previous.id if previous else None, "analyzed": v.total_count - v.excluded_count,
            "valid": v.valid_count, "errors": v.error_count, "warnings": v.warning_count, "excluded": v.excluded_count,
            "previous": version_out(previous) if previous else None, "issues": summary}


@router.get("/feed-versions/{version_id}/items")
def version_items(
    version_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10),
    q: str | None = Query(None, max_length=200),
    only_changed: bool = False,
    only_errors: bool = False,
    excluded: bool | None = None,
    rule_id: int | None = None,
    issue_code: str | None = Query(None, max_length=60),
    issue_level: Literal["valid", "recommendation", "warning", "error", "excluded"] | None = None,
    filters: str | None = None,
    sort: str | None = Query(None, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_:.\-]*$"),
    order: Literal["asc", "desc"] = "asc",
    s: Session = SessionDep,
    p: Principal = PrincipalDep,
):
    """Before/after comparison: transformed item + original product + changes."""
    if page_size not in (10, 25, 50, 100):
        raise ApiError(422, "invalid_page_size", "page_size debe ser 10, 25, 50 o 100")
    v, _ = _version(s, p, version_id)
    stmt = select(FeedItem, Product).join(Product, Product.id == FeedItem.product_id).where(FeedItem.version_id == v.id)
    if q:
        from feedstudio.api.querying import search_clause

        stmt = stmt.where(search_clause(q))
    if only_changed:
        stmt = stmt.where(FeedItem.changed.is_(True))
    if only_errors:
        stmt = stmt.where(FeedItem.issue_level == "error")
    if excluded is not None:
        stmt = stmt.where(FeedItem.excluded.is_(excluded))
    if rule_id:
        stmt = stmt.where(FeedItem.rule_ids.like(f"%,{rule_id},%"))
    if issue_level:
        stmt = stmt.where(FeedItem.issue_level == issue_level)
    if issue_code:
        stmt = stmt.where(issue_code_clause(FeedItem, issue_code, v.id, None))
    for f in parse_filters(filters):
        stmt = stmt.where(filter_clause(FeedItem, f))
    total = s.scalar(select(func.count()).select_from(stmt.with_only_columns(FeedItem.id).subquery()))
    col = sort_column(FeedItem, sort)
    rows = s.execute(stmt.order_by(col.desc() if order == "desc" else col.asc(), FeedItem.position)
                     .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [fi.product_id for fi, _ in rows]
    issues: dict[int, list] = {}
    if ids:
        for i in s.execute(select(ValidationIssue).where(ValidationIssue.version_id == v.id, ValidationIssue.product_id.in_(ids))).scalars():
            issues.setdefault(i.product_id, []).append({"code": i.code, "severity": i.severity, "attribute": i.attribute, "message": i.message})
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "id": fi.id, "product_id": fi.product_id, "external_id": fi.external_id, "position": fi.position,
            "excluded": fi.excluded, "changed": fi.changed, "issue_level": fi.issue_level,
            "original": prod.data, "transformed": fi.data, "changes": fi.changes, "rule_issues": fi.rule_issues,
            "issues": issues.get(fi.product_id, []),
        } for fi, prod in rows],
    }
