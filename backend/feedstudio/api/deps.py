from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from feedstudio.api.errors import ApiError
from feedstudio.config import get_settings
from feedstudio.db import get_session
from feedstudio.models import AuditLog

DEFAULT_ORG_ID = 1


@dataclass(frozen=True)
class Principal:
    """Authenticated caller. Multi-user auth is Phase 4; today every caller
    authenticated by the shared API token belongs to the default organization.
    All data access is nevertheless filtered by ``organization_id``."""

    organization_id: int
    actor: str


def get_principal(authorization: str | None = Header(default=None)) -> Principal:
    token = get_settings().api_token
    if token:
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, token):
            raise ApiError(401, "unauthorized", "Token de API inválido o ausente")
    return Principal(DEFAULT_ORG_ID, "admin")


SessionDep = Depends(get_session)
PrincipalDep = Depends(get_principal)


def audit(s: Session, p: Principal, action: str, entity: str, entity_id: int | None, detail: dict | None = None) -> None:
    s.add(AuditLog(organization_id=p.organization_id, actor=p.actor, action=action, entity=entity, entity_id=entity_id, detail=detail))


def owned(s: Session, model, obj_id: int, p: Principal, label: str):
    obj = s.get(model, obj_id)
    if obj is None or getattr(obj, "organization_id", p.organization_id) != p.organization_id:
        raise ApiError(404, "not_found", f"{label} no encontrado")
    return obj
