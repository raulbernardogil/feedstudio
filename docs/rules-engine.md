# Rules engine

Implementation: `backend/feedstudio/rules/`. The same engine runs in the rule
preview (`POST /api/rules/preview`), the single-product test
(`POST /api/rules/test`) and feed generation, so previews cannot diverge from
the published feed. The browser never transforms data.

## Data model

A product is `dict[str, list[Value]]`, where `Value` is a string or a nested
mapping of the same shape. Every field is a list, so repeated XML elements
(`additional_image_link`) and structured attributes (`tax`, `shipping`) are
preserved. XML attributes become `@name` keys and mixed text becomes `#text`.

Field naming: Google-namespace, unprefixed and Atom elements use their local
name (`g:brand` → `brand`). If an item has the same local name in the Google
namespace and another one, the Google element keeps the bare key and the other
is prefixed (`rss:title`), so values are never merged. Other namespaces keep a
prefix (`c:extra`).

## Rule document (schema version 1)

```json
{
  "schema_version": 1,
  "name": "Añadir marca al título",
  "enabled": true,
  "priority": 10,
  "target": "title",
  "evaluate_on": "current",
  "on_missing_variable": "skip_rule",
  "fallback_value": "",
  "condition": {
    "operator": "and",
    "conditions": [
      {"field": "brand", "operator": "not_empty"},
      {"field": "title", "operator": "not_contains", "value_field": "brand", "case_sensitive": false},
      {"operator": "or", "conditions": [
        {"field": "product_type", "operator": "contains", "value": "Calzado"},
        {"field": "price", "operator": "greater_than", "value": "100"}
      ]}
    ]
  },
  "actions": [{"type": "prepend", "template": "{brand} "}]
}
```

Validated by `RuleDefinition` (Pydantic, `extra="forbid"`). Invalid regular
expressions, templates or operands are rejected with HTTP 422 when saving.
The scope is stored on the rule row: `channel_id = NULL` is a global rule.

## Execution order

1. Copy the original attributes (the original is never mutated).
2. Sort enabled rules by `(stage, priority, id)`: stage 0 = global rules,
   stage 1 = channel rules; lower priority numbers run first; ties break by id.
   The order is deterministic: two contradictory rules always resolve the same
   way (the later one wins).
3. For each rule, evaluate its condition against:
   - `current` (default): the value after all previous rules (cascading), or
   - `original`: the imported value, ignoring earlier transformations.
4. If the condition holds (or there is none), run the actions in order on the
   target. Each action receives the previous action's output.
5. Record a `Change {rule_id, rule_name, field, before, after}` when the
   target value changed. Product-level actions (`exclude`, `add_to_segment`)
   do not need a target.

## Conditions

Groups: `{"operator": "and"|"or", "conditions": [...]}`, nested up to 5 levels,
at most 50 children per group.

| Operator | Semantics |
|---|---|
| `contains`, `equals`, `starts_with`, `ends_with`, `matches_regex`, `in_list`, `greater_than`, `less_than`, `between` | **Positive**: true when ANY scalar value of the field satisfies it. Absent field → false. |
| `not_contains`, `not_equals`, `not_in_list` | **Negative**: exact complement of the positive counterpart (true when NO value satisfies it). Absent field → true. |
| `is_empty` / `not_empty` | Absent, or every value is whitespace / the opposite. |
| `exists` / `not_exists` | The key is present (even if empty) / absent. |

- `value_field`: compare with another attribute's first value. If that
  attribute is absent or blank, the comparison is undefined and the condition
  is **false** for positive and negative operators alike.
- Text comparison strips surrounding whitespace, applies Unicode NFC and, unless
  `case_sensitive`, `str.casefold()` (so `Ñ`/`ñ`, `ß`/`ss` compare equal).
- Numbers are parsed from localized text (`949.990,00 CLP` → 949990.00,
  `1,299.50` → 1299.50, `12,5` → 12.5). When both separators appear, the
  right-most one is decimal; a single separator followed by groups of exactly 3
  digits is a thousands separator (`1.190` → 1190). Unparseable values never
  satisfy numeric conditions.
- Regular expressions use the `regex` engine with a 50 ms timeout per
  evaluation and a 300-character pattern limit. A timeout aborts that rule for
  that product and is reported as a rule issue.

## Actions

| Type | Effect |
|---|---|
| `set_value` | Replace with a fixed text or template. Empty result removes the field. |
| `set_if_empty` | Like `set_value` only if the target is absent or blank. |
| `prepend` / `append` | Add a template before/after the current value. |
| `replace` | Find & replace (literal or regex with `\1` group references). |
| `remove_text` | Remove a fragment and collapse the resulting whitespace. |
| `uppercase`, `lowercase`, `capitalize` (`sentence`/`words`) | Case changes. |
| `collapse_whitespace`, `strip_html` | Cleanup. |
| `truncate` | Max length; `word` strategy cuts on a word boundary, optional suffix. |
| `copy_from` | Copy all values (including nested) from another attribute. |
| `map_values` | Dictionary normalization (`black => Negro`); unknown values kept. |
| `normalize_price` | `949.990,00 CLP` → `949990.00 CLP`; optional default currency. |
| `regex_extract` | Keep a regex group; optionally keep the value when there is no match. |
| `exclude` | Exclude the product from the channel (global rule: from every channel). It stays in the internal catalog. |
| `add_to_segment` | Append to the internal `_segments` field (not exported). |

Text actions are applied to **every** scalar value of a repeated field.

## Templates

- `{field}` inserts the first value of `field` (trimmed).
- `[ ... ]` is an optional section: dropped entirely if any variable inside is
  missing or blank. Use it to avoid incomplete phrases:
  `Descubre {title}[ de {brand}].[ Disponible en color {color}.]`
- `\{ \} \[ \] \\` are literal characters.
- Missing variables outside optional sections follow `on_missing_variable`:
  `empty` (empty string), `fallback` (`fallback_value`), `skip_rule` (rule not
  applied to that product, default) or `error` (not applied + rule issue).
- After rendering, whitespace is collapsed and dangling separators
  (` - `, `, `) left by empty variables are removed. For `prepend`/`append`
  the existing value is protected from that cleanup.

Templates never invent data: a variable without a value produces no text.

## Preview & conflicts

`POST /api/rules/preview` inserts the draft (or the edited version of an
existing rule) into the real pipeline of the channel and compares the pipeline
with and without it over the active catalog:

- `matched`: products whose condition held; `affected`: products changed or
  excluded by the draft.
- Per row: original value, value before the draft, value after the draft and
  final value after all later rules.
- `new_issues`: validation issues that appear only with the draft.
- `conflicts`: later rules writing the same target (they may overwrite it).
