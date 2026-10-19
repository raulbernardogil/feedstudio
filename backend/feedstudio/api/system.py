"""Jobs, dashboard, settings, audit log and the public feed endpoint."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from feedstudio import __version__
from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.serializers import dt, job_out
from feedstudio.config import get_settings
from feedstudio.db import session_scope
from feedstudio.models import AuditLog, Channel, FeedVersion, ProcessingJob, Rule, Source, SourceSnapshot
from feedstudio.storage import get_storage

router = APIRouter(tags=["system"])


@router.get("/api/jobs")
def list_jobs(source_id: int | None = None, channel_id: int | None = None, kind: str | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
              s: Session = SessionDep, p: Principal = PrincipalDep):
    stmt = select(ProcessingJob).where(ProcessingJob.organization_id == p.organization_id)
    if source_id:
        stmt = stmt.where(ProcessingJob.source_id == source_id)
    if channel_id:
        stmt = stmt.where(ProcessingJob.channel_id == channel_id)
    if kind:
        stmt = stmt.where(ProcessingJob.kind == kind)
    total = s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = s.execute(stmt.order_by(ProcessingJob.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"items": [job_out(j) for j in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    return job_out(owned(s, ProcessingJob, job_id, p, "Trabajo"), with_events=True)


@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: int, request: Request, p: Principal = PrincipalDep):
    """Server-Sent Events stream with job progress until it finishes."""
    with session_scope() as s:
        owned(s, ProcessingJob, job_id, p, "Trabajo")

    async def stream():
        last = None
        while True:
            if await request.is_disconnected():
                return
            with session_scope() as s:
                job = s.get(ProcessingJob, job_id)
                payload = job_out(job)
            data = json.dumps(payload, ensure_ascii=False)
            if data != last:
                yield f"event: job\ndata: {data}\n\n"
                last = data
            if payload["status"] in ("succeeded", "failed"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/api/dashboard")
def dashboard(s: Session = SessionDep, p: Principal = PrincipalDep):
    org = p.organization_id
    sources = s.execute(select(Source).where(Source.organization_id == org)).scalars().all()
    active_ids = [src.active_snapshot_id for src in sources if src.active_snapshot_id]
    snaps = s.execute(select(SourceSnapshot).where(SourceSnapshot.id.in_(active_ids))).scalars().all() if active_ids else []
    levels: dict[str, int] = {}
    for snap in snaps:
        for k, v in ((snap.stats or {}).get("issue_levels") or {}).items():
            levels[k] = levels.get(k, 0) + v
    channels = s.execute(select(Channel).where(Channel.organization_id == org)).scalars().all()
    channel_rows = []
    for c in channels:
        pub = s.get(FeedVersion, c.published_version_id) if c.published_version_id else None
        latest = s.scalar(select(FeedVersion).where(FeedVersion.channel_id == c.id).order_by(FeedVersion.id.desc()).limit(1))
        channel_rows.append({
            "id": c.id, "name": c.name, "kind": c.kind, "source_id": c.source_id,
            "published_version": {"id": pub.id, "number": pub.number, "items": pub.item_count, "created_at": dt(pub.created_at)} if pub else None,
            "latest_version": {"id": latest.id, "number": latest.number, "status": latest.status, "errors": latest.error_count,
                               "warnings": latest.warning_count, "items": latest.item_count} if latest else None,
        })
    last_refresh = max((src.last_refresh_at for src in sources if src.last_refresh_at), default=None)
    rules = s.scalar(select(func.count()).select_from(Rule).where(Rule.organization_id == org, Rule.enabled.is_(True)))
    recent_jobs = s.execute(select(ProcessingJob).where(ProcessingJob.organization_id == org)
                            .order_by(ProcessingJob.id.desc()).limit(5)).scalars()
    return {
        "sources": len(sources),
        "products": sum(snap.product_count for snap in snaps),
        "valid": levels.get("valid", 0) + levels.get("recommendation", 0),
        "warnings": levels.get("warning", 0),
        "errors": levels.get("error", 0),
        "active_rules": rules,
        "last_sync": dt(last_refresh),
        "next_sync": dt(min((src.next_run_at for src in sources if src.next_run_at), default=None)),
        "channels": channel_rows,
        "recent_jobs": [job_out(j) for j in recent_jobs],
    }


@router.get("/api/settings")
def app_settings(p: Principal = PrincipalDep):
    st = get_settings()
    return {
        "version": __version__, "environment": st.environment, "job_backend": st.job_backend,
        "database": st.database_url.split(":", 1)[0], "public_base_url": st.public_base_url,
        "max_feed_mb": st.max_feed_mb, "max_upload_mb": st.max_upload_mb, "allow_http_sources": st.allow_http_sources,
        "snapshot_retention": st.snapshot_retention, "publish_drop_threshold": st.publish_drop_threshold,
        "auth_enabled": bool(st.api_token),
    }


@router.get("/api/audit-logs")
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), s: Session = SessionDep, p: Principal = PrincipalDep):
    stmt = select(AuditLog).where(AuditLog.organization_id == p.organization_id)
    rows = s.execute(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars()
    return {"items": [{"id": a.id, "actor": a.actor, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
                       "detail": a.detail, "created_at": dt(a.created_at)} for a in rows]}


@router.get("/health", tags=["health"])
def health(s: Session = SessionDep):
    try:
        s.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "error"
    storage = "ok" if get_storage().base.exists() else "error"
    status = 200 if db == "ok" and storage == "ok" else 503
    return Response(json.dumps({"status": "ok" if status == 200 else "degraded", "database": db, "storage": storage}),
                    status_code=status, media_type="application/json")


@router.api_route("/f/{token}/{filename}", methods=["GET", "HEAD"], tags=["public feeds"], include_in_schema=True)
def public_feed(token: str, filename: str, request: Request, s: Session = SessionDep):
    """Stable public URL polled by ad platforms. Serves the published version."""
    if len(token) > 64:
        raise ApiError(404, "not_found", "Feed no encontrado")
    channel = s.scalar(select(Channel).where(Channel.public_token == token))
    if channel is None or channel.published_version_id is None:
        raise ApiError(404, "not_found", "Feed no encontrado o sin publicar")
    version = s.get(FeedVersion, channel.published_version_id)
    want_csv = filename == f"{channel.kind}.csv"
    if not (filename == f"{channel.kind}.xml" or want_csv):
        raise ApiError(404, "not_found", "Feed no encontrado")
    key = version.csv_storage_key if want_csv else version.storage_key
    etag = f'"{version.sha256}{"-csv" if want_csv else ""}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300",
        "X-Feed-Version": str(version.number),
        "X-Feed-Generated-At": dt(version.created_at) or "",
        "X-Content-Type-Options": "nosniff",
    }
    media = "text/csv; charset=utf-8" if want_csv else "application/xml; charset=utf-8"
    return FileResponse(get_storage().path(key), media_type=media, headers=headers)
