"""Google Merchant Center validation profile.

Every limit is parameterized and linked to its source in
docs/requirements-matrix.md (consulted 2026-10-16). Passing these local checks
does NOT guarantee approval by Google; Merchant Center applies additional
policy and data-quality reviews.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from feedstudio.catalog.attributes import Attributes, get_text, get_values, is_blank
from feedstudio.rules.text import contains_html, format_price, parse_price
from feedstudio.validation.gtin import clean_gtin, is_valid_gtin
from feedstudio.validation.issues import Issue, IssueDefinition, Severity

SPEC_URL = "https://support.google.com/merchants/answer/7052112"
PRICE_URL = "https://support.google.com/merchants/answer/6324371"
AVAILABILITY_URL = "https://support.google.com/merchants/answer/6324448"
SPEC_CONSULTED = "2026-10-16"

MAX_LENGTHS: dict[str, int] = {
    "id": 50,
    "title": 150,
    "description": 5000,
    "brand": 70,
    "mpn": 70,
    "item_group_id": 50,
    "color": 100,
    "size": 100,
    "product_type": 750,
    **{f"custom_label_{i}": 100 for i in range(5)},
}
MAX_ADDITIONAL_IMAGES = 10
MAX_ADDITIONAL_IMAGE_URL = 2000
AVAILABILITY_VALUES = {"in_stock", "out_of_stock", "preorder", "backorder"}
CONDITION_VALUES = {"new", "refurbished", "used"}
IDENTIFIER_EXISTS_VALUES = {"yes", "no"}
GENDER_VALUES = {"male", "female", "unisex"}
AGE_GROUP_VALUES = {"newborn", "infant", "toddler", "kids", "adult"}
# ISO 4217 active codes subset is not hard-coded: format is checked (3 letters).
PROMOTIONAL_TERMS = ("gratis", "envío gratis", "envio gratis", "free shipping", "oferta", "descuento", "rebaja", "% off", "liquidación", "black friday")
INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
# Thousands separators or a comma decimal separator ("949.990,00", "12,5", "1,299.50").
_LOCALE_PRICE = re.compile(r"\d,\d{1,2}(\s|$)|\d\.\d{3}(\.\d{3})*,|\d\.\d{3}(\s|$)|\d,\d{3}")

E, W, R = Severity.error, Severity.warning, Severity.recommendation


def _rule(name: str, target: str, actions: list[dict], condition: dict | None = None) -> dict:
    out = {"name": name, "target": target, "actions": actions}
    if condition:
        out["condition"] = condition
    return out


DEFINITIONS: dict[str, IssueDefinition] = {
    d.code: d
    for d in [
        IssueDefinition("missing_id", E, "Producto sin identificador", "Asigna un id único (máx. 50 caracteres).", SPEC_URL),
        IssueDefinition("duplicate_id", E, "ID duplicado", "Cada producto debe tener un id único dentro del feed.", SPEC_URL),
        IssueDefinition("missing_title", E, "Título ausente", "Crea el título con una plantilla a partir de otros atributos.", SPEC_URL,
                        _rule("Título de respaldo", "title", [{"type": "set_if_empty", "template": "{brand} {product_type}"}])),
        IssueDefinition("missing_description", E, "Descripción ausente", "Añade una descripción de respaldo basada solo en datos existentes.", SPEC_URL,
                        _rule("Descripción de respaldo", "description",
                              [{"type": "set_if_empty", "template": "{title}[ de {brand}].[ Color: {color}.][ Medida: {size}.]"}])),
        IssueDefinition("missing_link", E, "URL de producto ausente", "Mapea el atributo link con la URL de la ficha.", SPEC_URL),
        IssueDefinition("invalid_link", E, "URL de producto inválida", "La URL debe empezar por http o https y ser absoluta.", SPEC_URL),
        IssueDefinition("missing_image_link", E, "Imagen principal ausente", "Mapea image_link con la URL de la imagen principal.", SPEC_URL),
        IssueDefinition("invalid_image_link", E, "URL de imagen inválida", "La URL de imagen debe ser absoluta (http/https).", SPEC_URL),
        IssueDefinition("missing_price", E, "Precio ausente", "Todos los productos requieren price.", SPEC_URL),
        IssueDefinition("invalid_price", E, "Precio inválido", "Formato esperado: importe y moneda ISO 4217, p. ej. 15.00 USD.", SPEC_URL),
        # Google's price page only shows the "15.00 USD" format; it does not state that
        # other separators are rejected, so this is a warning, not a blocking error.
        IssueDefinition("price_locale_format", W, "Precio con formato no documentado (separadores locales)",
                        "El precio se puede leer, pero usa separador de miles y coma decimal. La especificación solo documenta "
                        "el formato «15.00 USD»; normalizarlo evita interpretaciones erróneas (949.990,00 CLP → 949990.00 CLP).",
                        PRICE_URL, _rule("Normalizar precio", "price", [{"type": "normalize_price", "decimals": 2}])),
        IssueDefinition("sale_price_locale_format", W, "Precio de oferta con formato no documentado (separadores locales)",
                        "Igual que en price: el valor se puede leer, pero conviene normalizarlo al formato «15.00 USD».",
                        PRICE_URL, _rule("Normalizar precio de oferta", "sale_price", [{"type": "normalize_price", "decimals": 2}])),
        IssueDefinition("missing_currency", E, "Moneda ausente o inválida", "Añade el código ISO 4217 tras el importe.", SPEC_URL),
        IssueDefinition("invalid_sale_price", E, "Precio de oferta inválido", "sale_price debe tener importe y moneda ISO 4217.", SPEC_URL),
        IssueDefinition("sale_price_not_lower", W, "Precio de oferta no inferior al precio", "Revisa sale_price: debería ser menor que price.", SPEC_URL),
        IssueDefinition("currency_mismatch", W, "Monedas distintas en price y sale_price", "Usa la misma moneda en ambos precios.", SPEC_URL),
        IssueDefinition("missing_availability", E, "Disponibilidad ausente", "Indica in_stock, out_of_stock, preorder o backorder.", SPEC_URL),
        IssueDefinition("invalid_availability", E, "Valor de disponibilidad desconocido",
                        "El valor no corresponde a ninguno de los documentados: in_stock, out_of_stock, preorder, backorder.",
                        AVAILABILITY_URL),
        IssueDefinition("noncanonical_availability", W, "Disponibilidad con formato no documentado",
                        "El valor equivale a uno documentado (p. ej. «In Stock» = in_stock), pero la especificación usa "
                        "minúsculas con guion bajo. Normalizarlo evita depender de la tolerancia de Google.", AVAILABILITY_URL,
                        _rule("Normalizar disponibilidad", "availability", [{"type": "map_values", "mappings": [
                            {"from": "In Stock", "to": "in_stock"}, {"from": "in stock", "to": "in_stock"},
                            {"from": "Out of Stock", "to": "out_of_stock"}, {"from": "out of stock", "to": "out_of_stock"},
                            {"from": "preorder", "to": "preorder"}, {"from": "backorder", "to": "backorder"}]}])),
        IssueDefinition("preorder_without_date", W, "Preventa sin availability_date", "availability_date es obligatorio con preorder.", SPEC_URL),
        IssueDefinition("noncanonical_value", W, "Valor con formato no documentado",
                        "El valor equivale a uno documentado salvo mayúsculas/espacios; normalízalo con un diccionario de valores.",
                        SPEC_URL),
        IssueDefinition("invalid_condition", E, "Valor de condition no admitido", "Valores admitidos: new, refurbished, used.", SPEC_URL),
        IssueDefinition("invalid_identifier_exists", W, "identifier_exists con valor no documentado",
                        "Valores documentados: yes, no.", SPEC_URL,
                        _rule("Normalizar identifier_exists", "identifier_exists", [{"type": "map_values", "mappings": [
                            {"from": "FALSE", "to": "no"}, {"from": "TRUE", "to": "yes"}]}])),
        IssueDefinition("invalid_gtin", E, "GTIN inválido", "Debe tener 8, 12, 13 o 14 dígitos y dígito de control válido.", SPEC_URL),
        IssueDefinition("missing_brand", W, "Marca ausente", "Brand es obligatorio para la mayoría de productos nuevos.", SPEC_URL),
        IssueDefinition("missing_identifiers", W, "Sin GTIN/MPN y sin identifier_exists=no",
                        "Indica gtin, o brand+mpn, o identifier_exists=no si el producto no tiene identificadores.", SPEC_URL),
        IssueDefinition("too_long", E, "Valor supera la longitud máxima", "Recorta o reescribe el valor para cumplir el límite.", SPEC_URL),
        IssueDefinition("title_too_long", E, "Título supera 150 caracteres",
                        "Recorta el título conservando la información de variante.", SPEC_URL,
                        _rule("Recortar título", "title", [{"type": "truncate", "max_length": 150, "strategy": "word"}])),
        IssueDefinition("too_many_additional_images", W, "Más de 10 imágenes adicionales", "Google usa como máximo 10 additional_image_link.", SPEC_URL),
        IssueDefinition("invalid_additional_image", W, "Imagen adicional inválida", "Cada URL debe ser absoluta y de máx. 2000 caracteres.", SPEC_URL),
        IssueDefinition("invalid_gender", E, "Valor de gender no admitido", "Valores admitidos: male, female, unisex.", SPEC_URL),
        IssueDefinition("invalid_age_group", E, "Valor de age_group no admitido", "Valores: newborn, infant, toddler, kids, adult.", SPEC_URL),
        IssueDefinition("invalid_xml_chars", E, "Caracteres no válidos en XML", "Elimina caracteres de control del valor.", None),
        IssueDefinition("html_in_text", W, "HTML en texto plano", "Title y description deben ser texto plano.", SPEC_URL,
                        _rule("Eliminar HTML de la descripción", "description", [{"type": "strip_html"}])),
        IssueDefinition("whitespace_padding", R, "Espacios sobrantes", "Limpia espacios duplicados o al inicio/final.", None,
                        _rule("Limpiar espacios de la descripción", "description", [{"type": "collapse_whitespace"}])),
        IssueDefinition("promotional_title", R, "Texto promocional en el título",
                        "Evita términos promocionales en el título (políticas editoriales de Google).", SPEC_URL),
        IssueDefinition("title_all_caps", R, "Título en mayúsculas", "Usa capitalización normal.", None),
        IssueDefinition("short_description", R, "Descripción muy corta", "Amplía la descripción con atributos reales del producto.", None),
        IssueDefinition("missing_google_product_category", R, "Sin google_product_category", "Asigna una categoría de la taxonomía de Google.", SPEC_URL),
        IssueDefinition("insecure_url", R, "URL sin HTTPS", "Usa https si el sitio lo admite (verifícalo antes de aplicar la regla).", None),
        IssueDefinition("variant_missing_group", W, "Posible variante sin item_group_id",
                        "Productos con el mismo título y distinto color/talla deberían compartir item_group_id.", SPEC_URL),
        IssueDefinition("duplicate_variant", W, "Variante repetida", "Dos productos del mismo grupo tienen idéntico color y talla.", SPEC_URL),
        IssueDefinition("duplicate_title", R, "Título duplicado", "Diferencia títulos idénticos de productos distintos.", None),
    ]
}


def _issue(code: str, attribute: str | None, detail: str | None = None) -> Issue:
    """The message always states the problem; ``detail`` adds the offending value."""
    d = DEFINITIONS[code]
    return Issue(code, d.severity, attribute, f"{d.title}: {detail}" if detail else d.title)


def _canonical(value: str) -> str:
    return "_".join(value.strip().casefold().split())


def _valid_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc) and " " not in value.strip()


def validate_product(attrs: Attributes) -> list[Issue]:
    issues: list[Issue] = []
    add = issues.append
    text = lambda k: (get_text(attrs, k) or "")  # noqa: E731

    if is_blank(attrs, "id"):
        add(_issue("missing_id", "id"))
    if is_blank(attrs, "title"):
        add(_issue("missing_title", "title"))
    if is_blank(attrs, "description"):
        add(_issue("missing_description", "description"))

    for key, limit in MAX_LENGTHS.items():
        value = get_text(attrs, key)
        if value and len(value.strip()) > limit:
            code = "title_too_long" if key == "title" else "too_long"
            add(_issue(code, key, f"{key}: {len(value.strip())} caracteres (máx. {limit})"))

    # Links
    for key, missing, invalid in (("link", "missing_link", "invalid_link"), ("image_link", "missing_image_link", "invalid_image_link")):
        value = get_text(attrs, key)
        if value is None or not value.strip():
            add(_issue(missing, key))
        elif not _valid_url(value):
            add(_issue(invalid, key))
        elif value.strip().lower().startswith("http://"):
            add(_issue("insecure_url", key))
    extra_images = [v for v in get_values(attrs, "additional_image_link") if isinstance(v, str) and v.strip()]
    if len(extra_images) > MAX_ADDITIONAL_IMAGES:
        add(_issue("too_many_additional_images", "additional_image_link", f"{len(extra_images)} imágenes adicionales (máx. {MAX_ADDITIONAL_IMAGES})"))
    if any(not _valid_url(v) or len(v) > MAX_ADDITIONAL_IMAGE_URL for v in extra_images):
        add(_issue("invalid_additional_image", "additional_image_link"))

    # Prices
    price_text = get_text(attrs, "price")
    price = None
    if price_text is None or not price_text.strip():
        add(_issue("missing_price", "price"))
    else:
        price = _check_price(price_text, "price", "price_locale_format", "invalid_price", issues)
    sale_text = get_text(attrs, "sale_price")
    if sale_text and sale_text.strip():
        sale = _check_price(sale_text, "sale_price", "sale_price_locale_format", "invalid_sale_price", issues)
        if price and sale:
            if price.currency and sale.currency and price.currency != sale.currency:
                add(_issue("currency_mismatch", "sale_price"))
            elif price.amount is not None and sale.amount is not None and sale.amount >= price.amount:
                add(_issue("sale_price_not_lower", "sale_price"))

    # Enumerations
    availability = text("availability").strip()
    if not availability:
        add(_issue("missing_availability", "availability"))
    elif availability not in AVAILABILITY_VALUES:
        if _canonical(availability) in AVAILABILITY_VALUES:
            add(_issue("noncanonical_availability", "availability", f"«{availability}» → {_canonical(availability)}"))
        else:
            add(_issue("invalid_availability", "availability", f"«{availability}»"))
    elif availability == "preorder" and is_blank(attrs, "availability_date"):
        add(_issue("preorder_without_date", "availability_date"))
    _enum(attrs, "condition", CONDITION_VALUES, "invalid_condition", issues)
    _enum(attrs, "identifier_exists", IDENTIFIER_EXISTS_VALUES, "invalid_identifier_exists", issues)
    _enum(attrs, "gender", GENDER_VALUES, "invalid_gender", issues)
    _enum(attrs, "age_group", AGE_GROUP_VALUES, "invalid_age_group", issues)

    # Identifiers
    gtins = [v for v in get_values(attrs, "gtin") if isinstance(v, str) and v.strip()]
    for value in gtins:
        for part in value.split(","):
            if part.strip() and not is_valid_gtin(part):
                add(_issue("invalid_gtin", "gtin", f"«{clean_gtin(part)}»"))
    if is_blank(attrs, "brand"):
        add(_issue("missing_brand", "brand"))
    identifier_exists = text("identifier_exists").strip().lower()
    if not gtins and is_blank(attrs, "mpn") and identifier_exists not in ("no", "false"):
        add(_issue("missing_identifiers", "gtin"))

    # Text quality
    for key in ("title", "description"):
        value = get_text(attrs, key)
        if not value:
            continue
        if INVALID_XML_CHARS.search(value):
            add(_issue("invalid_xml_chars", key))
        if contains_html(value):
            add(_issue("html_in_text", key))
        if value != value.strip() or "  " in value:
            add(_issue("whitespace_padding", key))
    title = text("title").strip()
    if title:
        lowered = title.casefold()
        if any(term in lowered for term in PROMOTIONAL_TERMS):
            add(_issue("promotional_title", "title"))
        letters = [c for c in title if c.isalpha()]
        if len(letters) >= 8 and all(c.isupper() for c in letters):
            add(_issue("title_all_caps", "title"))
    description = text("description").strip()
    if description and len(description) < 50:
        add(_issue("short_description", "description"))
    if is_blank(attrs, "google_product_category"):
        add(_issue("missing_google_product_category", "google_product_category"))
    return issues


def _check_price(value: str, key: str, locale_code: str, invalid_code: str, issues: list[Issue]):
    parsed = parse_price(value)
    if parsed.amount is None:
        issues.append(_issue(invalid_code, key, f"«{value.strip()}» no contiene un importe legible"))
        return None
    if not parsed.currency:
        issues.append(_issue("missing_currency", key, f"«{value.strip()}»"))
    if _LOCALE_PRICE.search(value):
        normalized = format_price(parsed.amount, parsed.currency)
        issues.append(_issue(locale_code, key, f"«{value.strip()}» se interpreta como {normalized}"))
    return parsed


def _enum(attrs: Attributes, key: str, allowed: set[str], code: str, issues: list[Issue]) -> None:
    value = (get_text(attrs, key) or "").strip()
    if not value or value in allowed:
        return
    if key != "identifier_exists" and _canonical(value) in allowed:
        issues.append(_issue("noncanonical_value", key, f"{key} «{value}» → {_canonical(value)}"))
    else:
        issues.append(_issue(code, key, f"«{value}»"))


@dataclass
class CatalogValidator:
    """Cross-product checks (duplicates, variants).

    Memory: keeps one entry per product id/title/variant key, i.e. O(n) in the
    number of products, not in the size of the XML. This is required to
    detect duplicates and cannot be done in constant memory.
    """

    _ids: dict[str, int] = field(default_factory=dict)
    _variants: dict[tuple[str, str, str], int] = field(default_factory=dict)
    _titles: dict[str, list[tuple[int, str | None, str, str]]] = field(default_factory=lambda: defaultdict(list))
    extra: dict[int, list[Issue]] = field(default_factory=lambda: defaultdict(list))

    def add(self, ref: int, attrs: Attributes) -> list[Issue]:
        issues: list[Issue] = []
        pid = (get_text(attrs, "id") or "").strip()
        if pid:
            if pid in self._ids:
                issues.append(_issue("duplicate_id", "id", f"«{pid}» ya aparece en otro producto"))
            else:
                self._ids[pid] = ref
        group = (get_text(attrs, "item_group_id") or "").strip() or None
        color = (get_text(attrs, "color") or "").strip().casefold()
        size = (get_text(attrs, "size") or "").strip().casefold()
        if group:
            key = (group, color, size)
            if (color or size) and key in self._variants:
                issues.append(_issue("duplicate_variant", "item_group_id",
                                     f"Grupo '{group}' repite color/talla"))
            else:
                self._variants.setdefault(key, ref)
        title = (get_text(attrs, "title") or "").strip().casefold()
        if title:
            self._titles[title].append((ref, group, color, size))
        return issues

    def finalize(self) -> dict[int, list[Issue]]:
        """Return issues that can only be known once every product was seen."""
        for _title, entries in self._titles.items():
            if len(entries) < 2:
                continue
            variants = {(c, s) for _, _, c, s in entries}
            ungrouped = [e for e in entries if e[1] is None]
            if len(variants) > 1 and ungrouped:
                # Same title, different color/size and no item_group_id: likely variants.
                for ref, _, _, _ in ungrouped:
                    self.extra[ref].append(_issue("variant_missing_group", "item_group_id"))
            elif len(variants) == 1:
                for ref, _, _, _ in entries[1:]:
                    self.extra[ref].append(_issue("duplicate_title", "title"))
        return self.extra
