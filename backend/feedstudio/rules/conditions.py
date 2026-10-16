"""Condition evaluation.

Semantics (formalized in docs/rules-engine.md):
- A field may hold several values. *Positive* operators (contains, equals,
  starts_with, ends_with, matches_regex, in_list, greater_than, less_than,
  between) are true when ANY scalar value satisfies them.
- *Negative* operators (not_contains, not_equals, not_in_list) are the exact
  complement of their positive counterpart: true when NO value satisfies it.
  Therefore an absent field "does not contain" anything.
- When ``value_field`` is used and that field is absent or blank, the
  comparison is undefined and the condition is FALSE for both positive and
  negative operators.
- Text comparisons strip surrounding whitespace, apply NFC normalization and,
  unless ``case_sensitive``, Unicode casefolding.
- Numeric operators parse localized numbers; values that cannot be parsed
  never satisfy the condition.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Union

from feedstudio.catalog.attributes import Attributes, get_text, is_blank
from feedstudio.rules.schema import Condition, ConditionGroup, ConditionOperator as Op
from feedstudio.rules.text import compile_pattern, normalize, parse_number, regex_search

_NEGATIONS = {
    Op.not_contains: Op.contains,
    Op.not_equals: Op.equals,
    Op.not_in_list: Op.in_list,
}


def evaluate(node: Union[ConditionGroup, Condition, None], attrs: Attributes) -> bool:
    if node is None:
        return True
    if isinstance(node, ConditionGroup):
        if node.operator == "and":
            return all(evaluate(c, attrs) for c in node.conditions)
        return any(evaluate(c, attrs) for c in node.conditions)
    return _evaluate_condition(node, attrs)


def _scalar_values(attrs: Attributes, field: str) -> list[str]:
    return [v for v in attrs.get(field) or [] if isinstance(v, str)]


def _evaluate_condition(cond: Condition, attrs: Attributes) -> bool:
    op = cond.operator
    if op == Op.exists:
        return cond.field in attrs
    if op == Op.not_exists:
        return cond.field not in attrs
    if op == Op.is_empty:
        return is_blank(attrs, cond.field)
    if op == Op.not_empty:
        return not is_blank(attrs, cond.field)

    operand = cond.value
    if cond.value_field is not None:
        operand = get_text(attrs, cond.value_field)
        if operand is None or not operand.strip():
            return False

    positive = _NEGATIONS.get(op)
    if positive is not None:
        return not _any_value(cond, positive, operand, attrs)
    return _any_value(cond, op, operand, attrs)


def _any_value(cond: Condition, op: Op, operand: str | None, attrs: Attributes) -> bool:
    values = _scalar_values(attrs, cond.field)
    if not values:
        return False

    if op in (Op.greater_than, Op.less_than, Op.between):
        low = parse_number(operand)
        high = parse_number(cond.value_to) if op == Op.between else None
        if low is None or (op == Op.between and high is None):
            return False
        return any(_numeric(op, parse_number(v), low, high) for v in values)

    if op == Op.matches_regex:
        pattern = compile_pattern(operand or "", cond.case_sensitive)
        return any(regex_search(pattern, v) is not None for v in values)

    cs = cond.case_sensitive
    if op == Op.in_list:
        options = {normalize(o.strip(), cs) for o in cond.values or []}
        return any(normalize(v.strip(), cs) in options for v in values)

    needle = normalize((operand or "").strip(), cs)
    for raw in values:
        hay = normalize(raw.strip(), cs)
        if op == Op.contains and needle in hay:
            return True
        if op == Op.equals and hay == needle:
            return True
        if op == Op.starts_with and hay.startswith(needle):
            return True
        if op == Op.ends_with and hay.endswith(needle):
            return True
    return False


def _numeric(op: Op, value: Decimal | None, low: Decimal, high: Decimal | None) -> bool:
    if value is None:
        return False
    if op == Op.greater_than:
        return value > low
    if op == Op.less_than:
        return value < low
    assert high is not None
    lo, hi = (low, high) if low <= high else (high, low)
    return lo <= value <= hi


def referenced_fields(node: Union[ConditionGroup, Condition, None]) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, Condition):
        return {node.field} | ({node.value_field} if node.value_field else set())
    out: set[str] = set()
    for child in node.conditions:
        out |= referenced_fields(child)
    return out
