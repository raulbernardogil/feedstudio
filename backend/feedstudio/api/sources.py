from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, audit, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.serializers import job_out, snapshot_out, source_out
from feedstudio.config import get_settings
from feedstudio.ingestion.fetcher import FetchError, validate_url
from feedstudio.jobs import get_runner
from feedstudio.models import ProcessingJob, Source, SourceSchemaField, SourceSnapshot
from feedstudio.services.importing import fetch_policy, snapshot_key
from feedstudio.storage import StorageError, get_storage

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=2048)
    item_tag: str | None = Field(default=None, max_length=200, description="Product node for custom XML (auto-detected if empty)")
    schedule: Literal["manual"] = "manual"


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    item_tag: str | None = Field(default=None, max_length=200)


def _ensure_not_running(s: Session, source_id: int) -> None:
    running = s.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.source_id == source_id, ProcessingJob.kind == "import",
            ProcessingJob.status.in_(("queued", "running")),
        )
    )
    if running:
        raise ApiError(409, "import_in_progress", "Ya hay una importación en curso para esta fuente", {"job_id": running})


def _start_import(s: Session, p: Principal, source: Source, snapshot: SourceSnapshot) -> ProcessingJob:
    job = ProcessingJob(organization_id=p.organization_id, kind="import", source_id=source.id,
                        params={"snapshot_id": snapshot.id}, events=[])
    s.add(job)
    s.commit()
    get_runner().enqueue(job.id)
    s.refresh(job)
    return job


def _check_url(url: str) -> None:
    try:
        validate_url(url, fetch_policy())
    except FetchError as exc:
        raise ApiError(422, exc.code, exc.message) from exc


@router.get("")
def list_sources(s: Session = SessionDep, p: Principal = PrincipalDep):
    rows = s.execute(select(Source).where(Source.organization_id == p.organization_id).order_by(Source.id)).scalars().all()
    return {"items": [source_out(src, s.get(SourceSnapshot, src.active_snapshot_id) if src.active_snapshot_id else None) for src in rows]}


@router.post("", status_code=202)
def create_url_source(body: SourceCreate, s: Session = SessionDep, p: Principal = PrincipalDep):
    _check_url(body.url)
    source = Source(organization_id=p.organization_id, name=body.name, kind="url", url=body.url, item_tag=body.item_tag or None)
    s.add(source)
    s.flush()
    snapshot = SourceSnapshot(source_id=source.id, status="pending")
    s.add(snapshot)
    s.flush()
    audit(s, p, "source.create", "source", source.id, {"kind": "url"})
    job = _start_import(s, p, source, snapshot)
    return {"source": source_out(source), "job": job_out(job)}


@router.post("/upload", status_code=202)
def create_upload_source(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=200),
    item_tag: str | None = Form(default=None, max_length=200),
    source_id: int | None = Form(default=None, description="Upload a new snapshot for an existing source"),
    s: Session = SessionDep,
    p: Principal = PrincipalDep,
):
    if source_id:
        source = owned(s, Source, source_id, p, "Fuente")
        _ensure_not_running(s, source.id)
    else:
        source = Source(organization_id=p.organization_id, name=name, kind="upload", item_tag=item_tag or None)
        s.add(source)
        s.flush()
    snapshot = SourceSnapshot(source_id=source.id, status="pending", original_filename=(file.filename or "feed.xml")[:300])
    s.add(snapshot)
    s.flush()
    key = snapshot_key(source.id, snapshot.id)
    try:
        size, sha = get_storage().put_stream(key, file.file, get_settings().max_upload_mb * 1024 * 1024)
    except StorageError as exc:
        s.rollback()
        raise ApiError(413, "file_too_large", str(exc)) from exc
    if size == 0:
        s.rollback()
        raise ApiError(422, "empty_file", "El archivo está vacío")
    snapshot.storage_key, snapshot.size_bytes, snapshot.sha256 = key, size, sha
    audit(s, p, "source.upload", "source", source.id, {"snapshot_id": snapshot.id, "bytes": size})
    job = _start_import(s, p, source, snapshot)
    return {"source": source_out(source), "job": job_out(job)}


@router.get("/{source_id}")
def get_source(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    source = owned(s, Source, source_id, p, "Fuente")
    active = s.get(SourceSnapshot, source.active_snapshot_id) if source.active_snapshot_id else None
    return source_out(source, active)


@router.patch("/{source_id}")
def update_source(source_id: int, body: SourceUpdate, s: Session = SessionDep, p: Principal = PrincipalDep):
    source = owned(s, Source, source_id, p, "Fuente")
    if body.url is not None:
        if source.kind != "url":
            raise ApiError(422, "not_url_source", "Solo las fuentes por URL tienen URL")
        _check_url(body.url)
        source.url = body.url
    if body.name is not None:
        source.name = body.name
    if "item_tag" in body.model_fields_set:
        source.item_tag = body.item_tag or None
    audit(s, p, "source.update", "source", source.id, body.model_dump(exclude_none=True))
    s.commit()
    return source_out(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    source = owned(s, Source, source_id, p, "Fuente")
    _ensure_not_running(s, source.id)
    source.active_snapshot_id = None
    s.flush()
    audit(s, p, "source.delete", "source", source.id, {"name": source.name})
    s.delete(source)
    s.commit()


@router.post("/{source_id}/refresh", status_code=202)
def refresh_source(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    source = owned(s, Source, source_id, p, "Fuente")
    if source.kind != "url":
        raise ApiError(422, "not_url_source", "Las fuentes subidas se actualizan subiendo un archivo nuevo")
    s.execute(select(Source).where(Source.id == source.id).with_for_update())  # serialize concurrent refreshes (PostgreSQL)
    _ensure_not_running(s, source.id)
    _check_url(source.url or "")
    snapshot = SourceSnapshot(source_id=source.id, status="pending")
    s.add(snapshot)
    s.flush()
    audit(s, p, "source.refresh", "source", source.id)
    job = _start_import(s, p, source, snapshot)
    return {"job": job_out(job)}


@router.get("/{source_id}/snapshots")
def list_snapshots(source_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Source, source_id, p, "Fuente")
    rows = s.execute(select(SourceSnapshot).where(SourceSnapshot.source_id == source_id).order_by(SourceSnapshot.id.desc())).scalars()
    return {"items": [snapshot_out(r) for r in rows]}


@router.get("/{source_id}/schema")
def get_schema(source_id: int, snapshot_id: int | None = None, s: Session = SessionDep, p: Principal = PrincipalDep):
    source = owned(s, Source, source_id, p, "Fuente")
    sid = snapshot_id or source.active_snapshot_id
    if sid is None:
        return {"snapshot_id": None, "fields": []}
    snap = s.get(SourceSnapshot, sid)
    if snap is None or snap.source_id != source.id:
        raise ApiError(404, "not_found", "Snapshot no encontrado")
    fields = s.execute(select(SourceSchemaField).where(SourceSchemaField.snapshot_id == sid).order_by(SourceSchemaField.position)).scalars()
    return {
        "snapshot_id": sid,
        "product_count": snap.product_count,
        "fields": [
            {"key": f.key, "qname": f.qname, "kind": f.kind, "inferred_type": f.inferred_type, "present_count": f.present_count,
             "empty_count": f.empty_count, "max_repeat": f.max_repeat, "coverage": f.coverage, "samples": f.samples}
            for f in fields
        ],
    }
