"""Versioned JSON schema for rules (validated with Pydantic).

See docs/rules-engine.md for the formal semantics. ``RULE_SCHEMA_VERSION`` is
stored with every rule so definitions can be migrated in the future.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from feedstudio.rules.templates import TemplateSyntaxError, parse_template
from feedstudio.rules.text import RegexError, compile_pattern

RULE_SCHEMA_VERSION = 1
MAX_CONDITION_DEPTH = 5
MAX_CONDITIONS = 50

FieldName = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_:.\-]*$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionOperator(str, Enum):
    contains = "contains"
    not_contains = "not_contains"
    equals = "equals"
    not_equals = "not_equals"
    starts_with = "starts_with"
    ends_with = "ends_with"
    is_empty = "is_empty"
    not_empty = "not_empty"
    exists = "exists"
    not_exists = "not_exists"
    greater_than = "greater_than"
    less_than = "less_than"
    between = "between"
    matches_regex = "matches_regex"
    in_list = "in_list"
    not_in_list = "not_in_list"


UNARY_OPERATORS = {
    ConditionOperator.is_empty,
    ConditionOperator.not_empty,
    ConditionOperator.exists,
    ConditionOperator.not_exists,
}
NUMERIC_OPERATORS = {ConditionOperator.greater_than, ConditionOperator.less_than, ConditionOperator.between}
LIST_OPERATORS = {ConditionOperator.in_list, ConditionOperator.not_in_list}


class Condition(_Strict):
    field: FieldName
    operator: ConditionOperator
    value: str | None = Field(default=None, max_length=1000)
    value_to: str | None = Field(default=None, max_length=100, description="Upper bound for 'between'")
    values: list[Annotated[str, Field(max_length=500)]] | None = Field(default=None, max_length=1000)
    value_field: FieldName | None = Field(default=None, description="Compare against another attribute")
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check_operands(self) -> "Condition":
        op = self.operator
        if op in UNARY_OPERATORS:
            return self
        if op in LIST_OPERATORS:
            if not self.values:
                raise ValueError("Los operadores de lista requieren 'values'")
            return self
        if op == ConditionOperator.between:
            if self.value is None or self.value_to is None:
                raise ValueError("'between' requiere 'value' y 'value_to'")
            return self
        if self.value is None and self.value_field is None:
            raise ValueError(f"El operador '{op.value}' requiere 'value' o 'value_field'")
        if op == ConditionOperator.matches_regex:
            if self.value is None:
                raise ValueError("'matches_regex' requiere un patrón en 'value'")
            try:
                compile_pattern(self.value, self.case_sensitive)
            except RegexError as exc:
                raise ValueError(str(exc)) from exc
        return self


class ConditionGroup(_Strict):
    operator: Literal["and", "or"] = "and"
    conditions: list[Union["ConditionGroup", Condition]] = Field(min_length=1, max_length=MAX_CONDITIONS)

    @model_validator(mode="after")
    def _check_depth(self) -> "ConditionGroup":
        if _depth(self) > MAX_CONDITION_DEPTH:
            raise ValueError(f"Las condiciones no pueden anidarse más de {MAX_CONDITION_DEPTH} niveles")
        return self


def _depth(node: Union[ConditionGroup, Condition]) -> int:
    if isinstance(node, Condition):
        return 0
    return 1 + max((_depth(c) for c in node.conditions), default=0)


# --- Actions -----------------------------------------------------------------


class _TemplateAction(_Strict):
    template: str = Field(max_length=5000)

    @field_validator("template")
    @classmethod
    def _valid_template(cls, v: str) -> str:
        try:
            parse_template(v)
        except TemplateSyntaxError as exc:
            raise ValueError(str(exc)) from exc
        return v


class SetValue(_TemplateAction):
    """Replace the value (fixed text or template). Empty result removes the field."""

    type: Literal["set_value"]


class SetIfEmpty(_TemplateAction):
    type: Literal["set_if_empty"]


class Prepend(_TemplateAction):
    type: Literal["prepend"]


class Append(_TemplateAction):
    type: Literal["append"]


class Replace(_Strict):
    type: Literal["replace"]
    find: str = Field(min_length=1, max_length=1000)
    replace_with: str = Field(default="", max_length=1000)
    use_regex: bool = False
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check_regex(self) -> "Replace":
        if self.use_regex:
            try:
                compile_pattern(self.find, self.case_sensitive)
            except RegexError as exc:
                raise ValueError(str(exc)) from exc
        return self


class RemoveText(_Strict):
    type: Literal["remove_text"]
    find: str = Field(min_length=1, max_length=1000)
    use_regex: bool = False
    case_sensitive: bool = False

    @model_validator(mode="after")
    def _check_regex(self) -> "RemoveText":
        if self.use_regex:
            try:
                compile_pattern(self.find, self.case_sensitive)
            except RegexError as exc:
                raise ValueError(str(exc)) from exc
        return self


class Uppercase(_Strict):
    type: Literal["uppercase"]


class Lowercase(_Strict):
    type: Literal["lowercase"]


class Capitalize(_Strict):
    type: Literal["capitalize"]
    mode: Literal["sentence", "words"] = "sentence"


class CollapseWhitespace(_Strict):
    type: Literal["collapse_whitespace"]


class StripHtml(_Strict):
    type: Literal["strip_html"]


class Truncate(_Strict):
    type: Literal["truncate"]
    max_length: int = Field(ge=1, le=10000)
    strategy: Literal["word", "char"] = "word"
    ellipsis: str = Field(default="", max_length=5)


class CopyFrom(_Strict):
    type: Literal["copy_from"]
    field: FieldName


class ValueMapping(_Strict):
    source: str = Field(max_length=500, alias="from")
    target: str = Field(max_length=500, alias="to")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MapValues(_Strict):
    """Dictionary normalization (e.g. colors: "black" -> "Negro")."""

    type: Literal["map_values"]
    mappings: list[ValueMapping] = Field(min_length=1, max_length=5000)
    case_sensitive: bool = False


class NormalizePrice(_Strict):
    """Convert localized prices ("949.990,00 CLP") to "949990.00 CLP"."""

    type: Literal["normalize_price"]
    decimals: int = Field(default=2, ge=0, le=4)
    default_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class RegexExtract(_Strict):
    type: Literal["regex_extract"]
    pattern: str = Field(min_length=1, max_length=300)
    group: int = Field(default=0, ge=0, le=20)
    case_sensitive: bool = False
    keep_if_no_match: bool = True

    @model_validator(mode="after")
    def _check_regex(self) -> "RegexExtract":
        try:
            compiled = compile_pattern(self.pattern, self.case_sensitive)
        except RegexError as exc:
            raise ValueError(str(exc)) from exc
        if self.group > compiled.groups:
            raise ValueError("El grupo indicado no existe en la expresión regular")
        return self


class Exclude(_Strict):
    """Exclude the product from the output (channel or global by rule scope)."""

    type: Literal["exclude"]


class AddToSegment(_Strict):
    type: Literal["add_to_segment"]
    segment: str = Field(min_length=1, max_length=100)


Action = Annotated[
    Union[
        SetValue,
        SetIfEmpty,
        Prepend,
        Append,
        Replace,
        RemoveText,
        Uppercase,
        Lowercase,
        Capitalize,
        CollapseWhitespace,
        StripHtml,
        Truncate,
        CopyFrom,
        MapValues,
        NormalizePrice,
        RegexExtract,
        Exclude,
        AddToSegment,
    ],
    Field(discriminator="type"),
]

PRODUCT_LEVEL_ACTIONS = {"exclude", "add_to_segment"}


class RuleDefinition(_Strict):
    schema_version: int = RULE_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=100000)
    target: FieldName | None = None
    condition: ConditionGroup | None = None
    actions: list[Action] = Field(min_length=1, max_length=30)
    evaluate_on: Literal["current", "original"] = Field(
        default="current",
        description="'current': conditions read values transformed by previous rules; "
        "'original': conditions read the imported value.",
    )
    on_missing_variable: Literal["empty", "fallback", "skip_rule", "error"] = "skip_rule"
    fallback_value: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _check_target(self) -> "RuleDefinition":
        needs_target = any(a.type not in PRODUCT_LEVEL_ACTIONS for a in self.actions)
        if needs_target and not self.target:
            raise ValueError("Las acciones de valor requieren un atributo destino ('target')")
        if self.target and self.target.startswith("_"):
            raise ValueError("Los atributos internos no se pueden modificar")
        return self


ConditionGroup.model_rebuild()
