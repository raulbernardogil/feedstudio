"""Google OAuth 2.0 (web server flow) and Google Drive uploads.

References (consulted 2026-10-19):
- OAuth web server flow: https://developers.google.com/identity/protocols/oauth2/web-server
- Drive uploads: https://developers.google.com/workspace/drive/api/guides/manage-uploads
- files.update: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update

Scope ``drive.file`` (non-sensitive): the app can only see and modify files it
created, never the rest of the user's Drive. Uploads always use the resumable
protocol (recommended above 5 MB, valid for any size). Updating an existing
file keeps its id, so the Drive link stays stable across publications.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SCOPES = ("openid", "email", "https://www.googleapis.com/auth/drive.file")
TIMEOUT = httpx.Timeout(60.0, connect=15.0)

_transport: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Test hook: route every Google request through a mock transport."""
    global _transport
    _transport = transport


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, transport=_transport, trust_env=False)


class GoogleError(Exception):
    def __init__(self, message: str, code: str = "google_error", reconnect: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.reconnect = reconnect


def _error(response: httpx.Response, action: str) -> GoogleError:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    error = data.get("error")
    # OAuth errors: {"error": "invalid_grant", "error_description": "..."}
    # API errors:   {"error": {"code": 403, "message": "..."}}
    detail = error.get("message") if isinstance(error, dict) else (data.get("error_description") or error)
    if response.status_code in (400, 401) and error == "invalid_grant":
        return GoogleError("Google ha revocado o caducado el acceso; vuelve a conectar la cuenta", "invalid_grant", reconnect=True)
    if response.status_code == 401:
        return GoogleError("Credenciales de Google no válidas; vuelve a conectar la cuenta", "unauthorized", reconnect=True)
    if response.status_code == 403:
        return GoogleError(f"Google denegó el acceso al {action}: {detail or 'permiso insuficiente'}", "forbidden")
    if response.status_code == 404:
        return GoogleError(f"No se encontró el recurso de Google al {action}", "not_found")
    return GoogleError(f"Error de Google al {action} (HTTP {response.status_code}): {detail or ''}".strip(), "google_error")


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    scope: str


def authorization_url(cfg: OAuthConfig, state: str) -> str:
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # required to receive a refresh token
        "prompt": "consent",  # guarantees a refresh token on reconnection
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(cfg: OAuthConfig, code: str) -> Tokens:
    with _client() as client:
        res = client.post(TOKEN_URL, data={
            "client_id": cfg.client_id, "client_secret": cfg.client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": cfg.redirect_uri,
        })
    if res.status_code != 200:
        raise _error(res, "autorizar la cuenta")
    data = res.json()
    return Tokens(data["access_token"], data.get("refresh_token"), data.get("scope", ""))


def refresh_access_token(cfg: OAuthConfig, refresh_token: str) -> str:
    with _client() as client:
        res = client.post(TOKEN_URL, data={
            "client_id": cfg.client_id, "client_secret": cfg.client_secret,
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        })
    if res.status_code != 200:
        raise _error(res, "renovar el acceso")
    return res.json()["access_token"]


def fetch_email(access_token: str) -> str | None:
    with _client() as client:
        res = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    return res.json().get("email") if res.status_code == 200 else None


def revoke(token: str) -> None:
    with _client() as client:
        client.post(REVOKE_URL, data={"token": token})


@dataclass
class DriveFile:
    id: str
    web_view_link: str | None


def upload_file(access_token: str, path: Path, name: str, mime_type: str,
                folder_id: str | None = None, file_id: str | None = None) -> DriveFile:
    """Create a Drive file, or replace the content of ``file_id`` (keeping its id).

    If ``file_id`` no longer exists (deleted by the user), a new file is created.
    """
    if file_id:
        try:
            return _resumable(access_token, "PATCH", f"{UPLOAD_URL}/{file_id}", {"name": name}, path, mime_type)
        except GoogleError as exc:
            if exc.code != "not_found":
                raise
    metadata: dict = {"name": name, "mimeType": mime_type}
    if folder_id:
        metadata["parents"] = [folder_id]
    return _resumable(access_token, "POST", UPLOAD_URL, metadata, path, mime_type)


def _resumable(access_token: str, method: str, url: str, metadata: dict, path: Path, mime_type: str) -> DriveFile:
    size = path.stat().st_size
    auth = {"Authorization": f"Bearer {access_token}"}
    with _client() as client:
        init = client.request(
            method, url,
            params={"uploadType": "resumable", "fields": "id,webViewLink"},
            headers={**auth, "X-Upload-Content-Type": mime_type, "X-Upload-Content-Length": str(size)},
            json=metadata,
        )
        if init.status_code != 200 or "location" not in init.headers:
            raise _error(init, "iniciar la subida")
        res = client.put(init.headers["location"], content=_chunks(path),
                         headers={**auth, "Content-Type": mime_type, "Content-Length": str(size)})
    if res.status_code not in (200, 201):
        raise _error(res, "subir el archivo")
    data = res.json()
    return DriveFile(data["id"], data.get("webViewLink"))


def _chunks(path: Path, size: int = 1024 * 1024):
    """Stream the file body instead of loading it in memory."""
    with open(path, "rb") as fh:
        while chunk := fh.read(size):
            yield chunk
