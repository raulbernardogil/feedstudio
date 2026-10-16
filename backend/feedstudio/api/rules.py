from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from feedstudio.api.catalogs import resolve_snapshot
from feedstudio.api.deps import Principal, PrincipalDep, SessionDep, audit, owned
from feedstudio.api.errors import ApiError
from feedstudio.api.serializers import dt, rule_out
from feedstudio.models import Channel, Product, Rule, RuleVersion, Source, SourceSnapshot
from feedstudio.rules.schema import RuleDefinition
from feedstudio.services.preview import preview_rule, test_rule_on_product

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCreate(BaseModel):
    source_id: int
    channel_id: int | None = Field(default=None, description="NULL = global rule applied to every channel")
    definition: RuleDefinition


class RuleUpdate(BaseModel):
    channel_id: int | None = None
    definition: RuleDefinition


class RulePreview(BaseModel):
    source_id: int
    channel_id: int | None = None
    rule_id: int | None = Field(default=None, description="When editing an existing rule, it is replaced by the draft")
    definition: RuleDefinition
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class RuleTest(BaseModel):
    source_id: int
    channel_id: int | None = None
    rule_id: int | None = None
    definition: RuleDefinition
    product_id: int | None = None
    external_id: str | None = None


def _check_scope(s: Session, p: Principal, source_id: int, channel_id: int | None) -> Source:
    source = owned(s, Source, source_id, p, "Fuente")
    if channel_id is not None:
        channel = owned(s, Channel, channel_id, p, "Canal")
        if channel.source_id != source.id:
            raise ApiError(422, "channel_mismatch", "El canal no pertenece a esta fuente")
    return source


@router.get("")
def list_rules(source_id: int, channel_id: int | None = Query(None), include_global: bool = True,
               s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Source, source_id, p, "Fuente")
    rows = s.execute(select(Rule).where(Rule.source_id == source_id)).scalars().all()
    selected = [
        r for r in rows
        if (r.channel_id is None and (include_global or channel_id is None)) or (channel_id is not None and r.channel_id == channel_id)
    ]
    selected.sort(key=lambda r: (0 if r.channel_id is None else 1, r.priority, r.id))
    return {"items": [rule_out(r) for r in selected]}


@router.post("", status_code=201)
def create_rule(body: RuleCreate, s: Session = SessionDep, p: Principal = PrincipalDep):
    _check_scope(s, p, body.source_id, body.channel_id)
    d = body.definition
    definition = d.model_dump(mode="json", by_alias=True)
    rule = Rule(organization_id=p.organization_id, source_id=body.source_id, channel_id=body.channel_id, name=d.name,
                enabled=d.enabled, priority=d.priority, definition=definition, version=1, updated_by=p.actor)
    s.add(rule)
    s.flush()
    s.add(RuleVersion(rule_id=rule.id, version=1, definition=definition, created_by=p.actor))
    audit(s, p, "rule.create", "rule", rule.id, {"name": d.name})
    s.commit()
    return rule_out(rule)


@router.get("/{rule_id}")
def get_rule(rule_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    return rule_out(owned(s, Rule, rule_id, p, "Regla"))


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, s: Session = SessionDep, p: Principal = PrincipalDep):
    rule = owned(s, Rule, rule_id, p, "Regla")
    _check_scope(s, p, rule.source_id, body.channel_id)
    d = body.definition
    definition = d.model_dump(mode="json", by_alias=True)
    rule.channel_id = body.channel_id
    rule.name, rule.enabled, rule.priority, rule.definition = d.name, d.enabled, d.priority, definition
    rule.version += 1
    rule.updated_by = p.actor
    s.add(RuleVersion(rule_id=rule.id, version=rule.version, definition=definition, created_by=p.actor))
    audit(s, p, "rule.update", "rule", rule.id, {"version": rule.version})
    s.commit()
    return rule_out(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    rule = owned(s, Rule, rule_id, p, "Regla")
    audit(s, p, "rule.delete", "rule", rule.id, {"name": rule.name, "definition": rule.definition})
    s.delete(rule)
    s.commit()


@router.get("/{rule_id}/versions")
def rule_versions(rule_id: int, s: Session = SessionDep, p: Principal = PrincipalDep):
    owned(s, Rule, rule_id, p, "Regla")
    rows = s.execute(select(RuleVersion).where(RuleVersion.rule_id == rule_id).order_by(RuleVersion.version.desc())).scalars()
    return {"items": [{"version": v.version, "definition": v.definition, "created_at": dt(v.created_at), "created_by": v.created_by} for v in rows]}


@router.post("/preview")
def preview(body: RulePreview, s: Session = SessionDep, p: Principal = PrincipalDep):
    _check_scope(s, p, body.source_id, body.channel_id)
    snap = resolve_snapshot(s, p, body.source_id)
    if body.rule_id:
        owned(s, Rule, body.rule_id, p, "Regla")
    return preview_rule(s, body.source_id, snap.id, body.channel_id, body.definition, body.rule_id, body.page, body.page_size)


@router.post("/test")
def test(body: RuleTest, s: Session = SessionDep, p: Principal = PrincipalDep):
    _check_scope(s, p, body.source_id, body.channel_id)
    snap = resolve_snapshot(s, p, body.source_id)
    product = None
    if body.product_id:
        product = s.get(Product, body.product_id)
        if product and product.snapshot_id != snap.id:
            product = None
    elif body.external_id:
        product = s.scalar(select(Product).where(Product.snapshot_id == snap.id, Product.external_id == body.external_id))
    if product is None:
        raise ApiError(404, "not_found", "Producto no encontrado en el catálogo activo")
    return test_rule_on_product(s, body.source_id, body.channel_id, body.definition, body.rule_id, product)


_ = SourceSnapshot  # re-exported for typing tools
