import pytest
from pydantic import ValidationError

from feedstudio.rules.engine import CompiledRule, RuleEngine
from feedstudio.rules.schema import RuleDefinition
from feedstudio.rules.templates import TemplateSyntaxError, parse_template, render
from feedstudio.rules.text import parse_number, parse_price


def product(**fields):
    return {k: [v] if isinstance(v, str) else v for k, v in fields.items()}


def rule(rid=1, stage=0, **definition):
    definition.setdefault("name", f"rule-{rid}")
    return CompiledRule(id=rid, name=definition["name"], definition=RuleDefinition.model_validate(definition), stage=stage)


SHOE = product(id="SKU-1001", title="Zapatillas Runner", brand="Velox", color="Negro", size="42", product_type="Calzado")


# --- templates -----------------------------------------------------------------


def test_template_renders_spec_example():
    tpl = parse_template("{brand} {title} - {color} - Talla {size}")
    assert render(tpl, SHOE) == "Velox Zapatillas Runner - Negro - Talla 42"


def test_template_optional_section_dropped_when_variable_missing():
    tpl = parse_template("Descubre {title}[ de {brand}].[ Disponible en color {color}.]")
    assert render(tpl, product(title="Mesa")) == "Descubre Mesa."
    assert render(tpl, product(title="Mesa", brand="Solano", color="Gris")) == (
        "Descubre Mesa de Solano. Disponible en color Gris."
    )


def test_template_empty_policy_cleans_dangling_separators():
    tpl = parse_template("{brand} {title} - {color} - Talla {size}")
    assert render(tpl, product(title="Sofá", size="2"), policy="empty") == "Sofá - Talla 2"


def test_template_syntax_errors():
    for bad in ["{brand", "brand}", "[a [b]]", "{bad name}", "[x"]:
        with pytest.raises(TemplateSyntaxError):
            parse_template(bad)


def test_template_escapes():
    assert render(parse_template(r"\{literal\} \[x\]"), {}) == "{literal} [x]"


# --- spec scenarios ----------------------------------------------------------------

BRAND_PREFIX = dict(
    name="Añadir marca al título",
    target="title",
    condition={
        "operator": "and",
        "conditions": [
            {"field": "brand", "operator": "not_empty"},
            {"field": "title", "operator": "not_contains", "value_field": "brand"},
        ],
    },
    actions=[{"type": "prepend", "template": "{brand} "}],
)


def test_prepend_brand_only_when_absent():
    engine = RuleEngine([rule(**BRAND_PREFIX)])
    assert engine.apply(SHOE).data["title"] == ["Velox Zapatillas Runner"]
    already = product(title="velox zapatillas", brand="Velox")
    result = engine.apply(already)
    assert result.data["title"] == ["velox zapatillas"]
    assert result.changes == []


def test_prepend_skipped_when_brand_missing():
    engine = RuleEngine([rule(**BRAND_PREFIX)])
    result = engine.apply(product(title="Mesa"))
    assert result.data["title"] == ["Mesa"]


def test_chained_rules_receive_previous_output_and_record_changes():
    engine = RuleEngine(
        [
            rule(1, priority=10, **BRAND_PREFIX),
            rule(2, priority=20, name="color y talla", target="title",
                 actions=[{"type": "append", "template": "[ - {color}][ - Talla {size}]"}]),
        ]
    )
    result = engine.apply(SHOE)
    assert result.data["title"] == ["Velox Zapatillas Runner - Negro - Talla 42"]
    assert [c.rule_id for c in result.changes] == [1, 2]
    assert result.changes[0].before == "Zapatillas Runner"
    assert result.changes[1].before == "Velox Zapatillas Runner"
    # The original attributes are never mutated.
    assert SHOE["title"] == ["Zapatillas Runner"]


def test_append_with_missing_variables_produces_no_dangling_text():
    engine = RuleEngine([rule(target="title", actions=[{"type": "append", "template": "[ - {color}][ - Talla {size}]"}])])
    assert engine.apply(product(title="Mesa", size="2 Cuerpos")).data["title"] == ["Mesa - Talla 2 Cuerpos"]
    assert engine.apply(product(title="Mesa")).data["title"] == ["Mesa"]


def test_category_exclusion_condition():
    engine = RuleEngine([
        rule(target="title",
             condition={"operator": "and", "conditions": [{"field": "product_type", "operator": "not_contains", "value": "calzado"}]},
             actions=[{"type": "append", "template": " - {color}"}])
    ])
    assert engine.apply(SHOE).data["title"] == ["Zapatillas Runner"]
    assert engine.apply(product(title="Sofá", color="Gris", product_type="Muebles")).data["title"] == ["Sofá - Gris"]


def test_description_fallback_when_empty_without_inventing_data():
    engine = RuleEngine([
        rule(target="description",
             actions=[{"type": "set_if_empty", "template": "Descubre {title}[ de {brand}].[ Disponible en color {color}.]"}])
    ])
    assert engine.apply(product(title="Mesa", description="")).data["description"] == ["Descubre Mesa."]
    assert engine.apply(product(title="Mesa", description="Original")).data["description"] == ["Original"]


def test_contradictory_rules_resolve_deterministically_by_priority_then_id():
    a = rule(1, priority=50, target="custom_label_0", actions=[{"type": "set_value", "template": "A"}])
    b = rule(2, priority=50, target="custom_label_0", actions=[{"type": "set_value", "template": "B"}])
    for order in ([a, b], [b, a]):
        assert RuleEngine(order).apply(SHOE).data["custom_label_0"] == ["B"]


def test_global_rules_run_before_channel_rules():
    channel = rule(1, stage=1, priority=0, target="title", actions=[{"type": "uppercase"}])
    global_ = rule(2, stage=0, priority=999, target="title", actions=[{"type": "append", "template": " x"}])
    assert RuleEngine([channel, global_]).apply(SHOE).data["title"] == ["ZAPATILLAS RUNNER X"]


def test_evaluate_on_original_vs_current():
    first = rule(1, priority=1, target="title", actions=[{"type": "set_value", "template": "Cambiado"}])
    cond = {"operator": "and", "conditions": [{"field": "title", "operator": "equals", "value": "Zapatillas Runner"}]}
    on_current = rule(2, priority=2, target="custom_label_1", condition=cond, actions=[{"type": "set_value", "template": "hit"}])
    on_original = rule(3, priority=3, target="custom_label_2", condition=cond, evaluate_on="original",
                       actions=[{"type": "set_value", "template": "hit"}])
    data = RuleEngine([first, on_current, on_original]).apply(SHOE).data
    assert "custom_label_1" not in data
    assert data["custom_label_2"] == ["hit"]


def test_nested_and_or_groups():
    cond = {
        "operator": "or",
        "conditions": [
            {"operator": "and", "conditions": [
                {"field": "brand", "operator": "equals", "value": "velox"},
                {"field": "size", "operator": "in_list", "values": ["41", "42"]},
            ]},
            {"field": "color", "operator": "equals", "value": "Rojo"},
        ],
    }
    engine = RuleEngine([rule(target="custom_label_3", condition=cond, actions=[{"type": "set_value", "template": "ok"}])])
    assert engine.apply(SHOE).data["custom_label_3"] == ["ok"]
    assert "custom_label_3" not in engine.apply(product(brand="Velox", size="44", color="Negro")).data
    assert engine.apply(product(brand="Otra", color="rojo")).data["custom_label_3"] == ["ok"]


def test_numeric_condition_with_localized_price_and_custom_labels():
    engine = RuleEngine([
        rule(1, target="custom_label_0",
             condition={"conditions": [{"field": "price", "operator": "greater_than", "value": "100000"}]},
             actions=[{"type": "set_value", "template": "ticket_alto"}]),
        rule(2, target="custom_label_1",
             condition={"conditions": [{"field": "price", "operator": "between", "value": "10000", "value_to": "50000"}]},
             actions=[{"type": "set_value", "template": "medio"}]),
    ])
    high = engine.apply(product(price="949.990,00 CLP")).data
    assert high["custom_label_0"] == ["ticket_alto"] and "custom_label_1" not in high
    mid = engine.apply(product(price="29.990,00 CLP")).data
    assert mid["custom_label_1"] == ["medio"] and "custom_label_0" not in mid
    assert "custom_label_0" not in engine.apply(product(price="consultar")).data


def test_invalid_regex_rejected_at_definition_time():
    with pytest.raises(ValidationError):
        RuleDefinition.model_validate({"name": "x", "target": "title", "actions": [{"type": "replace", "find": "(", "use_regex": True}]})
    with pytest.raises(ValidationError):
        RuleDefinition.model_validate({"name": "x", "target": "t", "actions": [{"type": "uppercase"}],
                                       "condition": {"conditions": [{"field": "t", "operator": "matches_regex", "value": "[a-"}]}})


def test_value_actions_require_target_and_internal_fields_protected():
    with pytest.raises(ValidationError):
        RuleDefinition.model_validate({"name": "x", "actions": [{"type": "uppercase"}]})
    with pytest.raises(ValidationError):
        RuleDefinition.model_validate({"name": "x", "target": "_segments", "actions": [{"type": "uppercase"}]})
    RuleDefinition.model_validate({"name": "x", "actions": [{"type": "exclude"}]})


def test_exclusion_and_segments():
    engine = RuleEngine([
        rule(1, condition={"conditions": [{"field": "availability", "operator": "equals", "value": "out_of_stock"}]},
             actions=[{"type": "exclude"}]),
        rule(2, actions=[{"type": "add_to_segment", "segment": "verano"}]),
    ])
    out = engine.apply(product(availability="out_of_stock"))
    assert out.excluded and out.excluded_by == [1]
    assert out.data["_segments"] == ["verano"]
    assert not engine.apply(product(availability="in_stock")).excluded


def test_text_actions():
    def run(actions, value, **kw):
        return RuleEngine([rule(target="f", actions=actions, **kw)]).apply({"f": [value]}).data.get("f")

    assert run([{"type": "replace", "find": "TELA", "replace_with": "Tela"}], "Sofá tela gris") == ["Sofá Tela gris"]
    assert run([{"type": "replace", "find": r"(\d+) cm", "replace_with": r"\1cm", "use_regex": True}], "188 cm") == ["188cm"]
    assert run([{"type": "replace", "find": "a", "replace_with": r"\1"}], "a") == [r"\1"]
    assert run([{"type": "remove_text", "find": "¡Oferta!"}], "Sofá ¡oferta! gris") == ["Sofá gris"]
    assert run([{"type": "strip_html"}], "<p>Hola&nbsp;<b>mundo</b></p>") == ["Hola mundo"]
    assert run([{"type": "collapse_whitespace"}], "  a   b  ") == ["a b"]
    assert run([{"type": "capitalize", "mode": "words"}], "sofá GRIS perla") == ["Sofá Gris Perla"]
    assert run([{"type": "truncate", "max_length": 12}], "Sofá Nordlicht Tela") == ["Sofá"]
    assert run([{"type": "truncate", "max_length": 14}], "Sofá Nordlicht Tela") == ["Sofá Nordlicht"]
    assert run([{"type": "regex_extract", "pattern": r"(\d+) cm", "group": 1}], "Ancho 188 cm") == ["188"]
    assert run([{"type": "normalize_price"}], "949.990,00 CLP") == ["949990.00 CLP"]
    assert run([{"type": "map_values", "mappings": [{"from": "black", "to": "Negro"}, {"from": "navy", "to": "Azul marino"}]}],
               "BLACK") == ["Negro"]
    assert run([{"type": "set_value", "template": ""}], "x") is None


def test_text_actions_apply_to_every_repeated_value():
    engine = RuleEngine([rule(target="additional_image_link",
                              actions=[{"type": "replace", "find": "http://", "replace_with": "https://"}])])
    out = engine.apply({"additional_image_link": ["http://a/1.jpg", "http://a/2.jpg"]})
    assert out.data["additional_image_link"] == ["https://a/1.jpg", "https://a/2.jpg"]


def test_copy_from_preserves_nested_values():
    engine = RuleEngine([rule(target="shipping_copy", actions=[{"type": "copy_from", "field": "tax"}])])
    tax = {"country": ["CL"], "rate": ["0"]}
    out = engine.apply({"tax": [tax]})
    assert out.data["shipping_copy"] == [tax]
    out.data["shipping_copy"][0]["country"][0] = "AR"
    assert tax["country"] == ["CL"]


def test_missing_variable_error_policy_reports_issue():
    engine = RuleEngine([rule(target="title", on_missing_variable="error",
                              actions=[{"type": "set_value", "template": "{brand} {title}"}])])
    out = engine.apply(product(title="Mesa"))
    assert out.data["title"] == ["Mesa"]
    assert len(out.issues) == 1 and "brand" in out.issues[0].message


def test_disabled_rules_are_ignored():
    engine = RuleEngine([rule(target="title", enabled=False, actions=[{"type": "uppercase"}])])
    assert engine.apply(SHOE).data["title"] == ["Zapatillas Runner"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [("949.990,00 CLP", "949990.00"), ("1,299.50 USD", "1299.50"), ("59.90 EUR", "59.90"),
     ("1.190", "1190"), ("12,5", "12.5"), ("abc", None), ("1.2.3,4", "123.4")],
)
def test_parse_number(text, expected):
    value = parse_number(text)
    assert (str(value) if value is not None else None) == expected


def test_parse_price_currency():
    assert parse_price("569.990,00 CLP").currency == "CLP"
    assert parse_price("10").currency is None
