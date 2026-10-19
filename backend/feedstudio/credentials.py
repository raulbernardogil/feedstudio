"""Encryption of stored credentials (Fernet, from the ``cryptography`` package).

Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
and set it as FEEDSTUDIO_SECRET_KEY. Losing the key makes stored tokens
unreadable: accounts must then be reconnected.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as _secrets
import time

from cryptography.fernet import Fernet, InvalidToken

from feedstudio.config import get_settings


class CredentialError(Exception):
    pass


def _key() -> bytes:
    key = get_settings().secret_key
    if not key:
        raise CredentialError("FEEDSTUDIO_SECRET_KEY no está configurada")
    return key.encode()


def encrypt(value: str) -> str:
    try:
        return Fernet(_key()).encrypt(value.encode()).decode()
    except ValueError as exc:
        raise CredentialError("FEEDSTUDIO_SECRET_KEY no es una clave Fernet válida") from exc


def decrypt(token: str) -> str:
    try:
        return Fernet(_key()).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise CredentialError("No se pudo descifrar la credencial (¿cambió FEEDSTUDIO_SECRET_KEY?)") from exc


def sign_state(payload: str, max_age_seconds: int = 900) -> str:
    """Opaque, signed and expiring OAuth ``state`` value (CSRF protection)."""
    expires = int(time.time()) + max_age_seconds
    nonce = _secrets.token_urlsafe(12)
    body = f"{payload}|{expires}|{nonce}"
    mac = hmac.new(_key(), body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body.encode()).decode().rstrip("=") + "." + base64.urlsafe_b64encode(mac).decode().rstrip("=")


def verify_state(state: str) -> str:
    try:
        body_b64, mac_b64 = state.split(".", 1)
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4)).decode()
        mac = base64.urlsafe_b64decode(mac_b64 + "=" * (-len(mac_b64) % 4))
    except (ValueError, UnicodeDecodeError) as exc:
        raise CredentialError("Parámetro state inválido") from exc
    expected = hmac.new(_key(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise CredentialError("Parámetro state inválido")
    payload, expires, _nonce = body.rsplit("|", 2)
    if int(expires) < time.time():
        raise CredentialError("La autorización ha caducado; vuelve a intentarlo")
    return payload
