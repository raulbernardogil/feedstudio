"""Automated runs: refresh → generate → publish → deliver.

``pipeline`` job (params: source_id, trigger):
1. URL sources are downloaded again (a new snapshot). If the download or the
   parse fails, the run stops and the previous catalog stays active.
   Uploaded sources skip this step and reuse their active snapshot.
2. Every channel of the source gets a new candidate version (rules + validation).
3. Channels with ``auto_publish`` publish it. The drop-threshold protection
   still applies: a version that loses too many products is NOT published.
4. Each publication is delivered to the channel's enabled destinations.

Each step is a regular job run inline, so it appears in the run history.

``deliver`` job (params: destination_id, version_id): uploads the published XML
to Google Drive, updating the same Drive file every time.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from feedstudio.config import get_settings
from feedstudio.credentials import CredentialError, decrypt
from feedstudio.db import session_scope
from feedstudio.integrations import google
from feedstudio.jobs import JobFailed, get_runner, handler, report, run_job
from feedstudio.models import (
    Channel,
    ChannelDestination,
    FeedVersion,
    GoogleAccount,
    ProcessingJob,
    Source,
    SourceSnapshot,
    utcnow,
)
from feedstudio.services.feeds import PublishBlocked, create_generation, publish
from feedstudio.storage import get_storage

ACTOR = "automatización"


def _new_job(s: Session, org_id: int, kind: str, params: dict, source_id: int | None = None,
             channel_id: int | None = None) -> ProcessingJob:
    job = ProcessingJob(organization_id=org_id, kind=kind, params=params, source_id=source_id,
                        channel_id=channel_id, events=[])
    s.add(job)
    s.flush()
    return job


def _status(job_id: int) -> ProcessingJob:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        s.expunge(job)
        return job


def start_pipeline(s: Session, source: Source, trigger: str) -> ProcessingJob:
    """Create a queued pipeline job. Caller commits and enqueues."""
    return _new_job(s, source.organization_id, "pipeline", {"source_id": source.id, "trigger": trigger}, source_id=source.id)


def queue_deliveries(s: Session, channel: Channel, version_id: int) -> list[int]:
    """Enqueue one delivery per enabled destination of a channel (after publication)."""
    destinations = s.execute(select(ChannelDestination).where(
        ChannelDestination.channel_id == channel.id, ChannelDestination.enabled.is_(True))).scalars().all()
    ids = [_new_job(s, channel.organization_id, "deliver", {"destination_id": d.id, "version_id": version_id},
                    source_id=channel.source_id, channel_id=channel.id).id for d in destinations]
    s.commit()
    for job_id in ids:
        get_runner().enqueue(job_id)
    return ids


@handler("pipeline")
def run_pipeline(job_id: int) -> dict:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        source = s.get(Source, job.params["source_id"])
        if source is None:
            raise JobFailed("La fuente ya no existe", code="not_found")
        org_id, source_id, is_url = source.organization_id, source.id, source.kind == "url"
        source_name = source.name
    summary: dict = {"source_id": source_id, "trigger": job.params.get("trigger"), "channels": []}

    # 1. Refresh the catalog
    if is_url:
        report(job_id, 0.05, f"Descargando el feed de «{source_name}»")
        with session_scope() as s:
            snapshot = SourceSnapshot(source_id=source_id, status="pending")
            s.add(snapshot)
            s.flush()
            import_id = _new_job(s, org_id, "import", {"snapshot_id": snapshot.id}, source_id=source_id).id
        run_job(import_id)
        imported = _status(import_id)
        summary["import_job_id"] = import_id
        if imported.status != "succeeded":
            message = (imported.error or {}).get("message", "error desconocido")
            raise JobFailed(f"La actualización del feed falló: {message}. Se mantiene el catálogo anterior.",
                            code="refresh_failed", detail={"import_job_id": import_id})
    else:
        report(job_id, 0.05, "Fuente subida manualmente: se reutiliza el último catálogo importado")

    with session_scope() as s:
        source = s.get(Source, source_id)
        snapshot_id = source.active_snapshot_id
        channel_ids = list(s.execute(select(Channel.id).where(Channel.source_id == source_id).order_by(Channel.id)).scalars())
    if snapshot_id is None:
        raise JobFailed("La fuente no tiene ningún catálogo importado", code="no_catalog")

    # 2-4. Generate, publish and deliver per channel
    for n, channel_id in enumerate(channel_ids, start=1):
        report(job_id, 0.3 + 0.6 * (n - 1) / max(1, len(channel_ids)), f"Generando canal {n}/{len(channel_ids)}")
        entry = _run_channel(channel_id, snapshot_id)
        summary["channels"].append(entry)
    with session_scope() as s:
        s.get(Source, source_id).last_refresh_at = utcnow()
    return summary


def _run_channel(channel_id: int, snapshot_id: int) -> dict:
    with session_scope() as s:
        channel = s.get(Channel, channel_id)
        version, gen_job = create_generation(s, channel, snapshot_id)
        version_id, gen_id, auto, name = version.id, gen_job.id, channel.auto_publish, channel.name
    run_job(gen_id)
    entry: dict = {"channel_id": channel_id, "channel": name, "version_id": version_id, "generate_job_id": gen_id}
    if _status(gen_id).status != "succeeded":
        entry["result"] = "generation_failed"
        return entry
    if not auto:
        entry["result"] = "candidate"  # generated and validated, publication left to the user
        return entry
    with session_scope() as s:
        channel = s.get(Channel, channel_id)
        version = s.get(FeedVersion, version_id)
        try:
            publish(s, channel, version, ACTOR)
        except PublishBlocked as exc:
            entry.update(result="publish_blocked", detail=exc.detail)
            return entry
        destinations = list(s.execute(select(ChannelDestination.id).where(
            ChannelDestination.channel_id == channel_id, ChannelDestination.enabled.is_(True))).scalars())
        deliver_ids = [_new_job(s, channel.organization_id, "deliver", {"destination_id": d, "version_id": version_id},
                                source_id=channel.source_id, channel_id=channel_id).id for d in destinations]
    entry.update(result="published", deliveries=[])
    for deliver_id in deliver_ids:
        run_job(deliver_id)
        entry["deliveries"].append({"job_id": deliver_id, "status": _status(deliver_id).status})
    return entry


def oauth_config() -> google.OAuthConfig:
    settings = get_settings()
    if not settings.google_configured:
        raise JobFailed("Google Drive no está configurado en el servidor (FEEDSTUDIO_GOOGLE_CLIENT_ID, "
                        "FEEDSTUDIO_GOOGLE_CLIENT_SECRET y FEEDSTUDIO_SECRET_KEY)", code="google_not_configured")
    return google.OAuthConfig(settings.google_client_id, settings.google_client_secret, settings.google_callback_url)


@handler("deliver")
def run_deliver(job_id: int) -> dict:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        dest = s.get(ChannelDestination, job.params["destination_id"])
        if dest is None:
            raise JobFailed("El destino ya no existe", code="not_found")
        version = s.get(FeedVersion, job.params["version_id"])
        account = s.get(GoogleAccount, dest.google_account_id) if dest.google_account_id else None
        if version is None or version.status != "ready" or not version.storage_key:
            raise JobFailed("La versión a entregar no está disponible", code="version_unavailable")
        if account is None or account.status != "active":
            _mark(dest.id, "failed", "La cuenta de Google no está conectada")
            raise JobFailed("La cuenta de Google del destino no está conectada; vuelve a conectarla", code="google_disconnected")
        dest_id, account_id, version_id = dest.id, account.id, version.id
        file_name, folder_id, remote_id = dest.file_name, dest.folder_id, dest.remote_file_id
        storage_key, encrypted = version.storage_key, account.encrypted_refresh_token

    report(job_id, 0.2, f"Subiendo «{file_name}» a Google Drive")
    try:
        cfg = oauth_config()
        access = google.refresh_access_token(cfg, decrypt(encrypted))
        result = google.upload_file(access, get_storage().path(storage_key), file_name, "application/xml",
                                    folder_id=folder_id, file_id=remote_id)
    except google.GoogleError as exc:
        _mark(dest_id, "failed", exc.message)
        if exc.reconnect:
            with session_scope() as s:
                s.get(GoogleAccount, account_id).status = "invalid"
        raise JobFailed(exc.message, code=exc.code) from exc
    except CredentialError as exc:
        _mark(dest_id, "failed", str(exc))
        raise JobFailed(str(exc), code="credential_error") from exc

    with session_scope() as s:
        dest = s.get(ChannelDestination, dest_id)
        dest.remote_file_id = result.id
        dest.remote_url = result.web_view_link or dest.remote_url
        dest.last_status, dest.last_error = "succeeded", None
        dest.last_delivered_at = utcnow()
        dest.last_version_id = version_id
    return {"destination_id": dest_id, "file_id": result.id, "url": result.web_view_link, "version_id": version_id}


def _mark(dest_id: int, status: str, error: str | None) -> None:
    with session_scope() as s:
        dest = s.get(ChannelDestination, dest_id)
        if dest is not None:
            dest.last_status, dest.last_error = status, error
