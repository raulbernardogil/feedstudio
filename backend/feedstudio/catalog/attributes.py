"""Internal product attribute model.

A product is a mapping ``field_key -> list[Value]`` where ``Value`` is either a
string (scalar) or a nested mapping with the same shape (for structured
attributes such as ``shipping`` or ``tax``). Every field is a list so repeated
XML elements (``additional_image_link``) are preserved without special cases.

The model is plain JSON so it can be persisted as-is.
"""

from __future__ import annotations

from typing import Any, Union

Value = Union[str, dict[str, list["Value"]]]
Attributes = dict[str, list[Value]]

# Internal, non-exported fields are prefixed with an underscore.
INTERNAL_PREFIX = "_"
SEGMENTS_FIELD = "_segments"


def get_values(attrs: Attributes, key: str) -> list[Value]:
    return attrs.get(key) or []


def get_text(attrs: Attributes, key: str) -> str | None:
    """Return the first scalar value of a field, or None when absent.

    Nested values are not considered text. An empty string is returned as-is
    so callers can distinguish "present but empty" from "absent".
    """
    for value in attrs.get(key) or []:
        if isinstance(value, str):
            return value
    return None


def is_present(attrs: Attributes, key: str) -> bool:
    return key in attrs and len(attrs[key]) > 0


def is_blank(attrs: Attributes, key: str) -> bool:
    """True when the field is absent or all scalar values are whitespace."""
    values = attrs.get(key) or []
    if not values:
        return True
    return all(isinstance(v, str) and not v.strip() for v in values)


def set_text(attrs: Attributes, key: str, value: str | None) -> None:
    """Replace a field with a single scalar value; None or "" removes it."""
    if value is None or value == "":
        attrs.pop(key, None)
    else:
        attrs[key] = [value]


def copy_attributes(attrs: Attributes) -> Attributes:
    """Deep copy restricted to the JSON shapes used by the model."""

    def _copy(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: [_copy(v) for v in vs] for k, vs in value.items()}
        return value

    return {k: [_copy(v) for v in vs] for k, vs in attrs.items()}


def display_value(values: list[Value]) -> str:
    """Human-readable single-line representation (used by CSV and the UI)."""
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        else:
            inner = ";".join(f"{k}={display_value(v)}" for k, v in value.items())
            parts.append(inner)
    return ", ".join(parts)


def exportable_keys(attrs: Attributes) -> list[str]:
    return [k for k in attrs if not k.startswith(INTERNAL_PREFIX)]
