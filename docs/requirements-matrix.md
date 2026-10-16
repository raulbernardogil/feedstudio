# Requirements matrix

Research performed on **2026-10-16**. Every constraint implemented in code
references this file. Status legend:

- **Confirmed**: read in official documentation on the date above.
- **Inferred**: deduced from documentation or observed behavior; not stated verbatim.
- **Pending**: could not be verified from an official source. Not implemented as a rule.
- **Original**: Feed Studio design decision, not taken from any reference.

## 1. Google Merchant Center

Sources:
- Product data specification: https://support.google.com/merchants/answer/7052112
- RSS 2.0 XML specification: https://support.google.com/merchants/answer/14987622
- Attribute rules: https://support.google.com/merchants/answer/14994083

| Requirement | Value implemented | Status | Code |
|---|---|---|---|
| `id` max length | 50 | Confirmed | `validation/google.py` `MAX_LENGTHS` |
| `title` max length | 150 | Confirmed | `title_too_long` |
| `description` max length | 5000 | Confirmed | `too_long` |
| `brand`, `mpn` max length | 70 | Confirmed | `too_long` |
| `item_group_id` max length | 50 | Confirmed | `too_long` |
| `color` max length | 100 (40 per color not checked) | Confirmed / partial | `too_long` |
| `size` max length | 100 | Confirmed | `too_long` |
| `product_type` max length | 750 | Confirmed | `too_long` |
| `custom_label_0..4` max length | 100 | Confirmed | `too_long` |
| `custom_label` 1,000 unique values per label | not checked | Confirmed, not implemented | — |
| `additional_image_link` | max 10 values, 2000 chars each | Confirmed | `too_many_additional_images` |
| `availability` values | `in_stock`, `out_of_stock`, `preorder`, `backorder` | Confirmed (https://support.google.com/merchants/answer/6324448) | `invalid_availability` (error) for unknown values |
| `availability` written as `In Stock` / `in stock` | warning, normalization suggested | Inferred: the spec does not say other spellings are rejected; Google's UI labels the value "In stock" | `noncanonical_availability` |
| `condition`/`gender`/`age_group` differing only in case/spaces (`New`) | warning | Inferred (same reasoning) | `noncanonical_value` |
| `availability_date` required with `preorder` | warning | Confirmed | `preorder_without_date` |
| `condition` values | `new`, `refurbished`, `used` | Confirmed | `invalid_condition` |
| `identifier_exists` values | `yes`, `no` | Confirmed | `invalid_identifier_exists` (warning: older feeds use TRUE/FALSE; Google's acceptance of those is **not** confirmed) |
| `gender` values | `male`, `female`, `unisex` | Confirmed | `invalid_gender` |
| `age_group` values | `newborn`, `infant`, `toddler`, `kids`, `adult` | Confirmed | `invalid_age_group` |
| `gtin` lengths | 8, 12, 13, 14 digits | Confirmed | `invalid_gtin` |
| GTIN check digit | GS1 mod-10 | Inferred (GS1 standard) | `validation/gtin.py` |
| `price` format | number + ISO 4217 code, max 2 decimals | Confirmed (https://support.google.com/merchants/answer/6324371) | `invalid_price` (error) when no amount can be read |
| Thousands separators / comma decimal in price (`949.990,00 CLP`) | **warning**, normalization suggested | Inferred. The price page only shows period examples (`15.00 USD`) and does **not** say other separators are rejected. A "decimal point must be a period" sentence exists only for shipping/minimum-order amounts. Community reports show misparsing of `1.190`. Corrected on 2026-10-16: it was previously classified as a blocking error. | `price_locale_format` |
| Output price `949990.00 CLP` (2 decimals for CLP) | 2 decimals by default, configurable | Inferred (CLP has 0 minor units in ISO 4217; Google examples use 2 decimals) | `normalize_price` |
| `sale_price` same format, lower than `price` | error / warning | Confirmed / Inferred | `invalid_sale_price`, `sale_price_not_lower` |
| Image min 500×500 px enforced from 2027-01-31 | not checked (no remote image fetching yet) | Confirmed, not implemented | — |
| `link` must start with http/https | error | Confirmed | `invalid_link` |
| Root `<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">` | exported | Confirmed | `export/google_xml.py` |
| `title`/`link`/`description` as `g:` elements | exported with `g:` prefix (as in Google's example) | Confirmed (example) | `export/google_xml.py` |
| Remove attributes with no value | empty values are omitted | Confirmed | `export/google_xml.py` |
| Elements outside RSS/Google namespaces are ignored | foreign-namespace fields not exported | Confirmed | `exportable()` |
| Nested sub-attributes (`shipping`, `tax`) | nested `g:` elements | Confirmed (shipping example) | `_write_value` |
| Rules are cascading and order matters | deterministic order by stage/priority/id | Confirmed | `rules/engine.py` |
| Conditions may read raw or processed values | `evaluate_on: original | current` | Confirmed | `RuleDefinition.evaluate_on` |
| Plain-text title/description | HTML flagged as warning | Inferred | `html_in_text` |
| Promotional text in titles | recommendation (term list is Feed Studio's) | Inferred / Original | `promotional_title` |
| Passing local checks ≠ approval | stated in UI | Original | `ValidationPage` |

## 2. Pinterest Catalogs

Source: https://help.pinterest.com/en/business/article/before-you-get-started-with-catalogs

| Requirement | Value | Status | Implemented |
|---|---|---|---|
| Formats | TSV, CSV, XML (RSS 2.0, Atom 1.0), Google Sheets; .zip/.gz/.bz2 | Confirmed | Phase 3 adapter (pending) |
| Encoding | UTF-8 | Confirmed | XML exporter writes UTF-8 |
| Required fields | id, title, description, link, image_link, price, availability (+ item_group_id for variants) | Confirmed | Phase 3 |
| `id` max | 127 | Confirmed | Phase 3 |
| `title` max | 500 | Confirmed | Phase 3 |
| `description` max | 10,000 | Confirmed | Phase 3 |
| `link` max | 511 | Confirmed | Phase 3 |
| `availability` values | "in stock", "out of stock", "preorder" | Confirmed (note: differs from Google) | Phase 3 |
| Main image min | 1000×1500 px | Confirmed | Phase 3 |
| Hosted URL fetched daily, ports 80/443 only | — | Confirmed | Public URLs comply |

## 3. Meta (Commerce Manager)

The official page "Especificaciones de datos de productos para catálogos en el
administrador de ventas" (https://www.facebook.com/business/help/120325381656392)
renders client-side and its content could not be read. Only third-party guides
were available.

| Requirement | Value reported by third parties | Status |
|---|---|---|
| Required fields | id, title, description, availability, condition, price, link, image_link, brand | **Pending** |
| `id` max length | 100 | **Pending** |

No Meta rule is implemented until the official specification is verified.

## 4. DataFeedWatch (functional reference only)

Source: https://www.datafeedwatch.com/ (home page, 2026-10-16). No code, assets,
texts or designs were reused.

| Capability | Status on the reference site | Feed Studio |
|---|---|---|
| Automatic mapping to channel formats | Stated | Google profile (Phase 1), more channels Phase 3 |
| Conditional automation (pause out-of-stock, etc.) | Stated | IF/THEN rules + `exclude` action |
| Product grouping by price/season/margin | Stated | `custom_label_*` rules, `add_to_segment` |
| Feed review: missing GTIN, color, size, description | Stated | Diagnostics module |
| Copy setups between channels/markets | Stated | Pending (Phase 4) |
| Integrations with e-commerce platforms | Stated | Not planned; XML/URL sources instead |
| Visual IF/THEN editor, preview, scheduling details | Not stated on the page consulted | Original designs in Feed Studio |
