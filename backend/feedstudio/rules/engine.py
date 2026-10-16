"""Deterministic rule engine.

Pipeline per product (documented in docs/rules-engine.md):

1. Start from a deep copy of the original (imported) attributes.
2. Run rules ordered by (stage, priority, id): stage 0 = global rules,
   stage 1 = channel rules. Lower priority numbers run first.
3. For each enabled rule, evaluate its condition against the *current* state
   (default, cascading) or the *original* state (``evaluate_on="original"``).
4. If the condition holds, run its actions in order on the target attribute.
   Each action receives the output of the previous one.
5. Every effective change is recorded as a ``Change`` for traceability.

The same engine is used by previews, tests and feed generation, so the UI can
never show a result different from the published feed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Callable, Iterable, Sequence

from feedstudio.catalog.attributes import (
    SEGMENTS_FIELD,
    Attributes,
    copy_attributes,
    get_text,
    is_blank,
    set_text,
)
from feedstudio.rules import schema as s
from feedstudio.rules.conditions import evaluate
from feedstudio.rules.templates import SELF, MissingVariable, Template, Var, parse_template, render
from feedstudio.rules.text import (
    RegexTimeout,
    capitalize_sentence,
    capitalize_words,
    collapse_whitespace,
    compile_pattern,
    format_price,
    normalize,
    parse_price,
    regex_search,
    regex_sub,
    strip_html,
    truncate,
)


@dataclass(frozen=True)
class CompiledRule:
    id: int
    name: str
    definition: s.RuleDefinition
    stage: int = 0  # 0 = global, 1 = channel

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return (self.stage, self.definition.priority, self.id)


@dataclass
class Change:
    rule_id: int
    rule_name: str
    field: str
    before: str | None
    after: str | None

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "field": self.field,
            "before": self.before,
            "after": self.after,
        }


@dataclass
class RuleIssue:
    rule_id: int
    rule_name: str
    message: str

    def as_dict(self) -> dict:
        return {"rule_id": self.rule_id, "rule_name": self.rule_name, "message": self.message}


@dataclass
class TransformResult:
    data: Attributes
    excluded: bool = False
    excluded_by: list[int] = field(default_factory=list)
    matched_rules: list[int] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    issues: list[RuleIssue] = field(default_factory=list)

    @property
    def changed_fields(self) -> set[str]:
        return {c.field for c in self.changes}


class _AbortRule(Exception):
    pass


@lru_cache(maxsize=1024)
def _template(source: str) -> Template:
    return parse_template(source)


class RuleEngine:
    def __init__(self, rules: Iterable[CompiledRule]):
        self.rules: list[CompiledRule] = sorted(
            (r for r in rules if r.definition.enabled), key=lambda r: r.sort_key
        )

    def apply(self, original: Attributes) -> TransformResult:
        current = copy_attributes(original)
        result = TransformResult(data=current)
        for rule in self.rules:
            self._apply_rule(rule, original, result)
        return result

    # -- internals -------------------------------------------------------------

    def _apply_rule(self, rule: CompiledRule, original: Attributes, result: TransformResult) -> None:
        d = rule.definition
        current = result.data
        context = original if d.evaluate_on == "original" else current
        try:
            if not evaluate(d.condition, context):
                return
        except RegexTimeout as exc:
            result.issues.append(RuleIssue(rule.id, rule.name, str(exc)))
            return

        result.matched_rules.append(rule.id)
        target = d.target
        before = _snapshot(current, target) if target else None
        working = list(current.get(target, [])) if target else []
        try:
            for action in d.actions:
                if action.type == "exclude":
                    result.excluded = True
                    result.excluded_by.append(rule.id)
                    continue
                if action.type == "add_to_segment":
                    segments = current.setdefault(SEGMENTS_FIELD, [])
                    if action.segment not in segments:
                        segments.append(action.segment)
                    continue
                working = self._apply_action(action, working, current, d)
        except MissingVariable as exc:
            if exc.report:
                result.issues.append(
                    RuleIssue(rule.id, rule.name, f"Variable '{exc.field_name}' ausente: regla no aplicada")
                )
            return
        except (RegexTimeout, _AbortRule) as exc:
            result.issues.append(RuleIssue(rule.id, rule.name, str(exc)))
            return

        if target is None:
            return
        cleaned = [v for v in working if not (isinstance(v, str) and v == "")]
        if cleaned:
            current[target] = cleaned
        else:
            current.pop(target, None)
        after = _snapshot(current, target)
        if after != before:
            result.changes.append(Change(rule.id, rule.name, target, before, after))

    def _apply_action(self, action, values: list, attrs: Attributes, d: s.RuleDefinition) -> list:
        t = action.type
        first = next((v for v in values if isinstance(v, str)), None)

        def render_tpl(tpl: Template, self_value: str | None = None) -> str:
            # Templates read the working state; the target reflects prior actions.
            view = attrs if d.target is None else {**attrs, d.target: values}
            return render(tpl, view, d.on_missing_variable, d.fallback_value, self_value=self_value)

        if t == "set_value":
            return [render_tpl(_template(action.template))]
        if t == "set_if_empty":
            if first is not None and first.strip():
                return values
            return [render_tpl(_template(action.template))]
        if t in ("prepend", "append"):
            base = _template(action.template)
            parts = (*base.parts, Var(SELF)) if t == "prepend" else (Var(SELF), *base.parts)
            tpl = Template(action.template, parts)
            if not values:
                return [render_tpl(tpl, "")]
            return [render_tpl(tpl, v) if isinstance(v, str) else v for v in values]
        if t == "copy_from":
            source = attrs.get(action.field)
            return [_deep(v) for v in source] if source else []
        if t == "normalize_price":
            return [_normalize_price(v, action) if isinstance(v, str) else v for v in values]
        if t == "regex_extract":
            pattern = compile_pattern(action.pattern, action.case_sensitive)

            def extract(v: str) -> str:
                match = regex_search(pattern, v)
                if match is None:
                    return v if action.keep_if_no_match else ""
                return match.group(action.group) or ""

            return _map_text(values, extract)
        if t == "map_values":
            table = {normalize(m.source.strip(), action.case_sensitive): m.target for m in action.mappings}
            return _map_text(values, lambda v: table.get(normalize(v.strip(), action.case_sensitive), v))
        return _map_text(values, _TEXT_ACTIONS[t](action))


def _replace(action: s.Replace) -> Callable[[str], str]:
    if action.use_regex:
        pattern = compile_pattern(action.find, action.case_sensitive)
        return lambda v: regex_sub(pattern, action.replace_with, v)
    pattern = compile_pattern(_escape(action.find), action.case_sensitive)
    return lambda v: regex_sub(pattern, action.replace_with, v, literal=True)


def _remove(action: s.RemoveText) -> Callable[[str], str]:
    source = action.find if action.use_regex else _escape(action.find)
    pattern = compile_pattern(source, action.case_sensitive)
    return lambda v: collapse_whitespace(regex_sub(pattern, "", v))


def _escape(text: str) -> str:
    import regex as _re

    return _re.escape(text)


_TEXT_ACTIONS: dict[str, Callable[[object], Callable[[str], str]]] = {
    "replace": _replace,
    "remove_text": _remove,
    "uppercase": lambda a: str.upper,
    "lowercase": lambda a: str.lower,
    "capitalize": lambda a: capitalize_sentence if a.mode == "sentence" else capitalize_words,
    "collapse_whitespace": lambda a: collapse_whitespace,
    "strip_html": lambda a: lambda v: collapse_whitespace(strip_html(v)),
    "truncate": lambda a: lambda v: truncate(v, a.max_length, a.strategy, a.ellipsis),
}


def _map_text(values: list, fn: Callable[[str], str]) -> list:
    return [fn(v) if isinstance(v, str) else v for v in values]


def _normalize_price(value: str, action: s.NormalizePrice) -> str:
    parsed = parse_price(value)
    if parsed.amount is None:
        return value
    currency = parsed.currency or action.default_currency
    return format_price(Decimal(parsed.amount), currency, action.decimals)


def _deep(value):
    if isinstance(value, dict):
        return {k: [_deep(x) for x in vs] for k, vs in value.items()}
    return value


def _snapshot(attrs: Attributes, key: str | None) -> str | None:
    if key is None or key not in attrs:
        return None
    values = attrs[key]
    texts = [v for v in values if isinstance(v, str)]
    if len(values) == 1 and texts:
        return texts[0]
    from feedstudio.catalog.attributes import display_value

    return display_value(values)


def compile_rules(rows: Sequence[tuple[int, str, dict, int]]) -> list[CompiledRule]:
    """Build engine rules from (id, name, definition_json, stage) tuples."""
    return [
        CompiledRule(id=rid, name=name, definition=s.RuleDefinition.model_validate(defn), stage=stage)
        for rid, name, defn, stage in rows
    ]


__all__ = [
    "Change",
    "CompiledRule",
    "RuleEngine",
    "RuleIssue",
    "TransformResult",
    "compile_rules",
    "get_text",
    "is_blank",
    "set_text",
]
