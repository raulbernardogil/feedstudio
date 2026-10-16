"""Attribute templates such as ``{brand} {title} - {color}[ - Talla {size}]``.

Syntax:
- ``{field}`` inserts the first scalar value of ``field``.
- ``[ ... ]`` is an optional section: it is dropped entirely when any
  variable inside it is missing or blank. Sections cannot be nested.
- ``\\{``, ``\\}``, ``\\[``, ``\\]`` and ``\\\\`` insert literal characters.

Variables outside optional sections follow the rule's missing-variable policy:
- ``empty``: replace with an empty string.
- ``fallback``: replace with the configured fallback value.
- ``skip_rule``: abort the rule for this product (no change is applied).
- ``error``: abort the rule and report an issue for this product.

After rendering, whitespace is collapsed and dangling separators left by empty
variables (" - ", ", ") are cleaned so no incomplete phrases are produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Union

from feedstudio.catalog.attributes import Attributes, get_text

MissingPolicy = Literal["empty", "fallback", "skip_rule", "error"]

_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:.\-]{0,99}$")


class TemplateSyntaxError(ValueError):
    pass


class MissingVariable(Exception):
    def __init__(self, field_name: str, report: bool):
        super().__init__(field_name)
        self.field_name = field_name
        self.report = report


@dataclass(frozen=True)
class Literal_:
    text: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Optional_:
    parts: tuple[Union[Literal_, Var], ...]


Part = Union[Literal_, Var, Optional_]


@dataclass(frozen=True)
class Template:
    source: str
    parts: tuple[Part, ...] = field(default_factory=tuple)

    @property
    def variables(self) -> list[str]:
        names: list[str] = []
        for part in self.parts:
            inner = part.parts if isinstance(part, Optional_) else (part,)
            names.extend(p.name for p in inner if isinstance(p, Var))
        return names


def parse_template(source: str) -> Template:
    parts: list[Part] = []
    stack: list[Union[Literal_, Var]] | None = None  # current optional section
    buffer: list[str] = []
    i = 0

    def flush(target: list) -> None:
        if buffer:
            target.append(Literal_("".join(buffer)))
            buffer.clear()

    while i < len(source):
        ch = source[i]
        target = stack if stack is not None else parts
        if ch == "\\" and i + 1 < len(source) and source[i + 1] in "{}[]\\":
            buffer.append(source[i + 1])
            i += 2
            continue
        if ch == "{":
            end = source.find("}", i)
            if end == -1:
                raise TemplateSyntaxError("Falta '}' de cierre en la plantilla")
            name = source[i + 1 : end].strip()
            if not _FIELD_NAME_RE.match(name):
                raise TemplateSyntaxError(f"Nombre de variable inválido: '{name}'")
            flush(target)
            target.append(Var(name))
            i = end + 1
            continue
        if ch == "}":
            raise TemplateSyntaxError("'}' sin '{' de apertura")
        if ch == "[":
            if stack is not None:
                raise TemplateSyntaxError("Las secciones opcionales no se pueden anidar")
            flush(parts)
            stack = []
            i += 1
            continue
        if ch == "]":
            if stack is None:
                raise TemplateSyntaxError("']' sin '[' de apertura")
            flush(stack)
            parts.append(Optional_(tuple(stack)))
            stack = None
            i += 1
            continue
        buffer.append(ch)
        i += 1

    if stack is not None:
        raise TemplateSyntaxError("Falta ']' de cierre en la plantilla")
    flush(parts)
    return Template(source, tuple(parts))


def _value(attrs: Attributes, name: str) -> str | None:
    value = get_text(attrs, name)
    if value is None or not value.strip():
        return None
    return value.strip()


_DANGLING = [
    (re.compile(r"\s*([-|/,;:·])\s*(?:[-|/,;:·]\s*)+"), r" \1 "),  # "a - - b" -> "a - b"
    (re.compile(r"^\s*[-|/,;:·]\s*"), ""),  # leading separator
    (re.compile(r"\s*[-|/,;:·]\s*$"), ""),  # trailing separator
    (re.compile(r"\s+([,.;:])"), r"\1"),  # "word ," -> "word,"
]


def _cleanup(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, repl in _DANGLING:
        text = pattern.sub(repl, text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" , ", ", ")
    return text


SELF = "__self__"
_SENTINEL = ""


def render(
    template: Template,
    attrs: Attributes,
    policy: MissingPolicy = "empty",
    fallback: str = "",
    cleanup: bool = True,
    self_value: str | None = None,
) -> str:
    """Render a template against a product.

    ``self_value`` is the current value of the rule target; it is substituted
    for ``{__self__}`` *after* cleanup so the existing value is never altered
    by separator/whitespace cleanup (used by prepend/append).
    """
    out: list[str] = []
    for part in template.parts:
        if isinstance(part, Literal_):
            out.append(part.text)
        elif isinstance(part, Var) and part.name == SELF:
            out.append(_SENTINEL)
        elif isinstance(part, Var):
            value = _value(attrs, part.name)
            if value is None:
                if policy == "skip_rule":
                    raise MissingVariable(part.name, report=False)
                if policy == "error":
                    raise MissingVariable(part.name, report=True)
                value = fallback if policy == "fallback" else ""
            out.append(value)
        else:
            rendered: list[str] = []
            for inner in part.parts:
                if isinstance(inner, Literal_):
                    rendered.append(inner.text)
                else:
                    value = _value(attrs, inner.name)
                    if value is None:
                        rendered = []
                        break
                    rendered.append(value)
            out.extend(rendered)
    text = "".join(out)
    if cleanup:
        text = _cleanup(text)
    if _SENTINEL in text:
        current = self_value or ""
        text = text.replace(_SENTINEL, current)
        if not current:
            text = _cleanup(text) if cleanup else text.strip()
    return text
