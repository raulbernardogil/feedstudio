from __future__ import annotations

from feedstudio.config import get_settings
from feedstudio.models import Channel, FeedVersion, ProcessingJob, Rule, Source, SourceSnapshot


def dt(value):
    return value.isoformat() if value else None


def snapshot_out(snap: SourceSnapshot | None) -> dict | None:
    if snap is None:
        return None
    return {
        "id": snap.id, "source_id": snap.source_id, "status": snap.status, "format": snap.format,
        "item_tag": snap.item_tag, "namespaces": snap.namespaces, "product_count": snap.product_count,
        "size_bytes": snap.size_bytes, "sha256": snap.sha256, "original_filename": snap.original_filename,
        "stats": snap.stats, "error": snap.error, "created_at": dt(snap.created_at),
    }


def source_out(src: Source, active: SourceSnapshot | None = None) -> dict:
    return {
        "id": src.id, "name": src.name, "kind": src.kind, "url": src.url, "item_tag": src.item_tag,
        "schedule": src.schedule, "active_snapshot_id": src.active_snapshot_id,
        "active_snapshot": snapshot_out(active), "last_refresh_at": dt(src.last_refresh_at),
        "created_at": dt(src.created_at),
    }


def job_out(job: ProcessingJob, with_events: bool = False) -> dict:
    out = {
        "id": job.id, "kind": job.kind, "status": job.status, "source_id": job.source_id,
        "channel_id": job.channel_id, "progress": job.progress, "message": job.message,
        "params": job.params, "result": job.result, "error": _public_error(job.error),
        "created_at": dt(job.created_at), "started_at": dt(job.started_at), "finished_at": dt(job.finished_at),
    }
    if with_events:
        out["events"] = job.events or []
    return out


def _public_error(error: dict | None) -> dict | None:
    if not error:
        return None
    return {k: v for k, v in error.items() if k != "trace"}


def rule_out(rule: Rule) -> dict:
    return {
        "id": rule.id, "source_id": rule.source_id, "channel_id": rule.channel_id, "name": rule.name,
        "enabled": rule.enabled, "priority": rule.priority, "version": rule.version,
        "definition": rule.definition, "updated_by": rule.updated_by,
        "created_at": dt(rule.created_at), "updated_at": dt(rule.updated_at),
    }


def public_url(channel: Channel) -> str:
    base = get_settings().public_base_url.rstrip("/")
    ext = "csv" if channel.kind == "csv" else "xml"
    return f"{base}/f/{channel.public_token}/{channel.kind}.{ext}"


def channel_out(channel: Channel, published: FeedVersion | None = None) -> dict:
    return {
        "id": channel.id, "source_id": channel.source_id, "name": channel.name, "kind": channel.kind,
        "settings": channel.settings, "published_version_id": channel.published_version_id,
        "published_version": version_out(published) if published else None,
        "public_url": public_url(channel), "created_at": dt(channel.created_at),
    }


def version_out(v: FeedVersion) -> dict:
    return {
        "id": v.id, "channel_id": v.channel_id, "snapshot_id": v.snapshot_id, "job_id": v.job_id,
        "number": v.number, "status": v.status, "size_bytes": v.size_bytes, "sha256": v.sha256,
        "total_count": v.total_count, "item_count": v.item_count, "excluded_count": v.excluded_count,
        "changed_count": v.changed_count, "error_count": v.error_count, "warning_count": v.warning_count,
        "valid_count": v.valid_count, "stats": v.stats, "error": v.error, "created_at": dt(v.created_at),
        "rules_count": len(v.rules_snapshot or []),
    }
