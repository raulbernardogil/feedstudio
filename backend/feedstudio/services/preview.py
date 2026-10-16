"""Rule preview: runs the SAME engine used by feed generation on live data.

A draft rule is inserted into the channel's real pipeline (at its priority)
and compared with the pipeline without it. Nothing is persisted.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from feedstudio.config import get_settings
from feedstudio.models import Product
from feedstudio.rules.engine import CompiledRule, RuleEngine
from feedstudio.rules.schema import PRODUCT_LEVEL_ACTIONS, RuleDefinition
from feedstudio.services.feeds import iter_products, load_rules
from feedstudio.validation.google import validate_product

DRAFT_ID = 0  # draft rules get id 0 (persisted rules are >= 1)


def _pipelines(s: Session, source_id: int, channel_id: int | None, draft: RuleDefinition, rule_id: int | None):
    existing = [r for r in load_rules(s, source_id, channel_id) if r.id != rule_id]
    stage = 1 if channel_id else 0
    draft_rule = CompiledRule(rule_id or DRAFT_ID, draft.name, draft.model_copy(update={"enabled": True}), stage=stage)
    without = RuleEngine(existing)
    with_draft = RuleEngine([*existing, draft_rule])
    conflicts = [
        {"rule_id": r.id, "name": r.name, "priority": r.definition.priority}
        for r in with_draft.rules
        if r.id != draft_rule.id and r.definition.target and r.definition.target == draft.target
        and r.sort_key > draft_rule.sort_key
        and not all(a.type in PRODUCT_LEVEL_ACTIONS for a in r.definition.actions)
    ]
    return without, with_draft, draft_rule, conflicts


def preview_rule(
    s: Session,
    source_id: int,
    snapshot_id: int,
    channel_id: int | None,
    draft: RuleDefinition,
    rule_id: int | None,
    page: int,
    page_size: int,
) -> dict:
    without, with_draft, draft_rule, conflicts = _pipelines(s, source_id, channel_id, draft, rule_id)
    max_scan = get_settings().preview_max_scan
    scanned = matched = affected = excluded = 0
    new_issue_counts: dict[str, int] = {}
    rows: list[dict] = []
    start = (page - 1) * page_size
    truncated = False
    for product in iter_products(s, snapshot_id):
        if scanned >= max_scan:
            truncated = True
            break
        scanned += 1
        after = with_draft.apply(product.data)
        if draft_rule.id not in after.matched_rules:
            continue
        matched += 1
        own = [c for c in after.changes if c.rule_id == draft_rule.id]
        is_excluded = draft_rule.id in after.excluded_by
        if not own and not is_excluded:
            continue
        affected += 1
        excluded += is_excluded
        before = without.apply(product.data)
        before_codes = {i.code for i in validate_product(before.data)}
        new_issues = [i.as_dict() for i in validate_product(after.data) if i.code not in before_codes]
        for issue in new_issues:
            new_issue_counts[issue["code"]] = new_issue_counts.get(issue["code"], 0) + 1
        if start <= affected - 1 < start + page_size:
            target = draft.target
            rows.append({
                "product_id": product.id,
                "external_id": product.external_id,
                "attribute": target,
                "original": _text(product.data, target),
                "before": own[0].before if own else _text(before.data, target),
                "after": own[-1].after if own else _text(after.data, target),
                "final": _text(after.data, target),
                "excluded": is_excluded,
                "new_issues": new_issues,
                "rule_issues": [i.as_dict() for i in after.issues if i.rule_id == draft_rule.id],
            })
    return {
        "scanned": scanned,
        "truncated": truncated,
        "matched": matched,
        "affected": affected,
        "excluded": excluded,
        "conflicts": conflicts,
        "new_issue_counts": new_issue_counts,
        "page": page,
        "page_size": page_size,
        "items": rows,
    }


def test_rule_on_product(s: Session, source_id: int, channel_id: int | None, draft: RuleDefinition,
                         rule_id: int | None, product: Product) -> dict:
    without, with_draft, draft_rule, conflicts = _pipelines(s, source_id, channel_id, draft, rule_id)
    after = with_draft.apply(product.data)
    before = without.apply(product.data)
    return {
        "product_id": product.id,
        "external_id": product.external_id,
        "matched": draft_rule.id in after.matched_rules,
        "excluded": after.excluded,
        "original": product.data,
        "before": before.data,
        "after": after.data,
        "changes": [c.as_dict() for c in after.changes],
        "rule_issues": [i.as_dict() for i in after.issues],
        "issues_before": [i.as_dict() for i in validate_product(before.data)],
        "issues_after": [i.as_dict() for i in validate_product(after.data)],
        "conflicts": conflicts,
    }


def _text(data: dict, key: str | None) -> str | None:
    if not key or key not in data:
        return None
    from feedstudio.catalog.attributes import display_value

    return display_value(data[key])
