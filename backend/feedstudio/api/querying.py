"""Server-side filtering, sorting and pagination over JSON attribute data."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.sql import ColumnElement

from feedstudio.api.errors import ApiError
from feedstudio.models import FeedItem, Product, ValidationIssue

FilterOp = Literal["equals", "not_equals", "contains", "not_contains", "starts_with", "is_empty", "not_empty", "gt", "lt"]


class AttributeFilter(BaseModel):
    field: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_:.\-]*$")
    op: FilterOp
    value: str | None = Field(default=None, max_length=500)


_filters_adapter = TypeAdapter(list[AttributeFilter])

DENORMALIZED = {"id": "external_id", "title": "title", "brand": "brand", "product_type": "product_type", "availability": "availability"}


def parse_filters(raw: str | None) -> list[AttributeFilter]:
    if not raw:
        return []
    try:
        filters = _filters_adapter.validate_python(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ApiError(422, "invalid_filters", "Parámetro 'filters' inválido") from exc
    if len(filters) > 20:
        raise ApiError(422, "invalid_filters", "Máximo 20 filtros")
    return filters


def json_text(model, field: str) -> ColumnElement:
    return model.data[(field, 0)].as_string()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filter_clause(model, f: AttributeFilter) -> ColumnElement:
    col = json_text(model, f.field)
    value = (f.value or "").strip()
    lowered = func.lower(col)
    like = f"%{_escape_like(value.lower())}%"
    match f.op:
        case "equals":
            return lowered == value.lower()
        case "not_equals":
            return or_(col.is_(None), lowered != value.lower())
        case "contains":
            return lowered.like(like, escape="\\")
        case "not_contains":
            return or_(col.is_(None), ~lowered.like(like, escape="\\"))
        case "starts_with":
            return lowered.like(f"{_escape_like(value.lower())}%", escape="\\")
        case "is_empty":
            return or_(col.is_(None), func.trim(col) == "")
        case "not_empty":
            return and_(col.is_not(None), func.trim(col) != "")
        case "gt" | "lt":
            # Numeric comparison over the denormalized price or a plain number.
            try:
                number = float(value.replace(",", "."))
            except ValueError as exc:
                raise ApiError(422, "invalid_filters", f"'{value}' no es un número") from exc
            if f.field == "price" and model is Product:
                target = Product.price_amount
            else:
                target = func.cast(col, _float())
            return target > number if f.op == "gt" else target < number
    raise ApiError(422, "invalid_filters", "Operador desconocido")


def _float():
    from sqlalchemy import Float

    return Float


def search_clause(q: str) -> ColumnElement:
    q = q.strip()
    return or_(Product.external_id == q, Product.search_text.like(f"%{_escape_like(q.casefold())}%", escape="\\"))


def issue_code_clause(model, code: str, version_id: int | None, snapshot_id: int | None) -> ColumnElement:
    product_col = Product.id if model is Product else FeedItem.product_id
    cond = [ValidationIssue.product_id == product_col, ValidationIssue.code == code]
    cond.append(ValidationIssue.version_id == version_id if version_id else ValidationIssue.snapshot_id == snapshot_id)
    return exists(select(ValidationIssue.id).where(*cond))


def sort_column(model, field: str | None):
    if not field or field == "position":
        return model.position
    if model is Product:
        if field in DENORMALIZED:
            return getattr(Product, DENORMALIZED[field])
        if field == "price":
            return Product.price_amount
        if field == "issue_level":
            return Product.issue_level
    return json_text(model, field)
