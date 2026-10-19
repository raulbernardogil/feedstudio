"""Google account connection (OAuth) and per-channel delivery destinations."""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, audit, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.serializers import destination_out, dt, job_out
from feedstudio.config import get_settings
from feedstudio.credentials import CredentialError, decrypt, encrypt, sign_state, verify_state
from feedstudio.integrations import google
from feedstudio.jobs import get_runner
from feedstudio.models import Channel, ChannelDestination, GoogleAccount, ProcessingJob
from feedstudio.services.automation import oauth_config

router = APIRouter(prefix="/api", tags=["integrations"])

_FOLDER_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
_FOLDER_URL_RE = re.compile(r"/folders/([A-Za-z0-9_-]{10,200})")


def _account_out(a: GoogleAccount) -> dict:
    return {"id": a.id, "email": a.email, "status": a.status, "scopes": a.scopes.split(), "created_at": dt(a.created_at)}


def _cfg() -> google.OAuthConfig:
    if not get_settings().google_configured:
        raise ApiError(409, "google_not_configured",
                       "Google Drive no está configurado en el servidor. Define FEEDSTUDIO_GOOGLE_CLIENT_ID, "
                       "FEEDSTUDIO_GOOGLE_CLIENT_SECRET y FEEDSTUDIO_SECRET_KEY (ver docs/google-drive.md).")
    return oauth_config()


@router.get("/integrations/google")
def google_status(s: Session = SessionDep, p: Principal = PrincipalDep):
    settings = get_settings()
    accounts = s.execute(select(GoogleAccount).where(GoogleAccount.organization_id == p.organization_id)
                         .order_by(GoogleAccount.id)).scalars()
    return {"configured": settings.google_configured, "redirect_uri": settings.google_callback_url,
            "accounts": [_account_out(a) for a in accounts]}


@router.post("/integrations/google/authorize")
def google_authorize(p: Principal = PrincipalDep):
    """Returns the Google consent URL; the browser navigates to it."""
    cfg = _cfg()
    return {"url": google.authorization_url(cfg, sign_state(str(p.organization_id)))}


@router.get("/integrations/google/callback", include_in_schema=False)
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                    s: Session = SessionDep):
    """OAuth redirect target. Authenticated by the signed, expiring ``state``."""
    app = get_settings().app_base_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{app}/channels?google=denied", status_code=303)
    try:
        org_id = int(verify_state(state))
        tokens = google.exchange_code(_cfg(), code)
    except (CredentialError, google.GoogleError, ValueError):
        return RedirectResponse(f"{app}/channels?google=error", status_code=303)
    if not tokens.refresh_token:
        return RedirectResponse(f"{app}/channels?google=no_refresh_token", status_code=303)
    email = google.fetch_email(tokens.access_token)
    account = s.scalar(select(GoogleAccount).where(GoogleAccount.organization_id == org_id, GoogleAccount.email == email)) if email else None
    if account is None:
        account = GoogleAccount(organization_id=org_id, email=email, scopes=tokens.scope, encrypted_refresh_token="")
        s.add(account)
    account.encrypted_refresh_token = encrypt(tokens.refresh_token)
    account.scopes = tokens.scope or account.scopes
    account.status = "active"
    s.flush()
    from feedstudio.models import AuditLog

    s.add(AuditLog(organization_id=org_id, actor="admin", action="google.connect", entity="google_account",
                   entity_id=account.id, detail={"email": email}))
    s.commit()
    return RedirectResponse(f"{app}/channels?google=connected", status_code=303)


@router.delete("/integrations/google/{account_id}", status_code=204)
def google_disconnect(account_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    account = owned(s, GoogleAccount, account_id, p, "Cuenta de Google")
    try:
        google.revoke(decrypt(account.encrypted_refresh_token))
    except Exception:  # noqa: BLE001 - revocation is best effort; the account is removed anyway
        pass
    audit(s, p, "google.disconnect", "google_account", account.id, {"email": account.email})
    s.delete(account)
    s.commit()


class DestinationIn(BaseModel):
    google_account_id: int
    file_name: str = Field(min_length=1, max_length=200, pattern=r"^[^/\\]+$")
    folder: str | None = Field(default=None, max_length=500, description="Drive folder id or folder URL (optional)")
    enabled: bool = True


class DestinationUpdate(BaseModel):
    file_name: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^[^/\\]+$")
    folder: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


def _folder_id(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    match = _FOLDER_URL_RE.search(value)
    folder = match.group(1) if match else value
    if not _FOLDER_RE.match(folder):
        raise ApiError(422, "invalid_folder", "Indica el ID de la carpeta de Drive o su URL (…/folders/ID)")
    return folder


def _destination(s: Session, p: Principal, destination_id: int) -> tuple[ChannelDestination, Channel]:
    d = s.get(ChannelDestination, destination_id)
    if d is None:
        raise ApiError(404, "not_found", "Destino no encontrado")
    return d, owned(s, Channel, d.channel_id, p, "Canal")


@router.get("/channels/{channel_id}/destinations")
def list_destinations(channel_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Channel, channel_id, p, "Canal")
    rows = s.execute(select(ChannelDestination).where(ChannelDestination.channel_id == channel_id)
                     .order_by(ChannelDestination.id)).scalars()
    return {"items": [destination_out(d) for d in rows]}


@router.post("/channels/{channel_id}/destinations", status_code=201)
def create_destination(channel_id: int, body: DestinationIn, s: Session = SessionDep, p: Principal = PrincipalDep):
    channel = owned(s, Channel, channel_id, p, "Canal")
    owned(s, GoogleAccount, body.google_account_id, p, "Cuenta de Google")
    d = ChannelDestination(channel_id=channel.id, kind="gdrive", google_account_id=body.google_account_id,
                           file_name=body.file_name, folder_id=_folder_id(body.folder), enabled=body.enabled)
    s.add(d)
    s.flush()
    audit(s, p, "destination.create", "destination", d.id, {"channel_id": channel.id})
    s.commit()
    return destination_out(d)


@router.patch("/destinations/{destination_id}")
def update_destination(destination_id: int, body: DestinationUpdate, s: Session = SessionDep, p: Principal = PrincipalDep):
    d, _ = _destination(s, p, destination_id)
    if body.file_name is not None:
        d.file_name = body.file_name
    if "folder" in body.model_fields_set:
        new_folder = _folder_id(body.folder)
        if new_folder != d.folder_id:
            d.folder_id, d.remote_file_id, d.remote_url = new_folder, None, None  # next upload creates a new file
    if body.enabled is not None:
        d.enabled = body.enabled
    audit(s, p, "destination.update", "destination", d.id)
    s.commit()
    return destination_out(d)


@router.delete("/destinations/{destination_id}", status_code=204)
def delete_destination(destination_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    d, _ = _destination(s, p, destination_id)
    audit(s, p, "destination.delete", "destination", d.id)
    s.delete(d)
    s.commit()


@router.post("/destinations/{destination_id}/deliver", status_code=202)
def deliver_now(destination_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    """Upload the currently published version now."""
    d, channel = _destination(s, p, destination_id)
    if channel.published_version_id is None:
        raise ApiError(409, "not_published", "El canal no tiene ninguna versión publicada")
    job = ProcessingJob(organization_id=p.organization_id, kind="deliver", source_id=channel.source_id,
                        channel_id=channel.id, params={"destination_id": d.id, "version_id": channel.published_version_id},
                        events=[])
    s.add(job)
    s.commit()
    get_runner().enqueue(job.id)
    s.refresh(job)
    return {"job": job_out(job)}

