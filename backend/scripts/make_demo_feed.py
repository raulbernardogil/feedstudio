"""Generate the fictional demo feed (50 products) used for demos.

    python -m scripts.make_demo_feed ../demo/demo_feed.xml

Everything is invented: brands, products, SKUs, prices, GTINs and URLs (on the
reserved ``.example`` domain). The structure mirrors a typical e-commerce platform
Google feed (unprefixed title/link/description, CDATA, nested ``g:tax``,
locale-formatted CLP prices, ``In Stock``, ``identifier_exists`` FALSE) and a
few deliberate data problems are included so the diagnostics have something to
show. The output is deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path

SITE = "https://www.tienda-demo.example"

# (sku, title, brand, product_type, google_category, color, size, price, sale_price, extra)
FURNITURE = "Mobiliario"
CLOTHES = "Ropa y accesorios > Ropa"
SHOES = "Ropa y accesorios > Calzado"
CLEANING = "Casa y jardín > Suministros de limpieza"
BEDDING = "Casa y jardín > Ropa de cama"


def clp(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + ",00 CLP"


def gtin13(body12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def cdata(text: str) -> str:
    return f"<![CDATA[{text}]]>"


def describe(title: str, brand: str, material: str, use: str) -> str:
    return (f"    {title} de {brand}. Fabricado en {material}, pensado para {use}. "
            f"Diseño sencillo que combina con distintos estilos y es fácil de mantener.   ")


PRODUCTS: list[dict] = []


def add(sku, title, brand, ptype, gcat, color, size, price, sale=None, *, material, use,
        description=None, image=True, availability="In Stock", group=None, gtin=None,
        extra_images=3, label="Tienda Demo", dims=None):
    PRODUCTS.append(dict(
        sku=sku, title=title, brand=brand, ptype=ptype, gcat=gcat, color=color, size=size,
        price=price, sale=sale, material=material,
        description=describe(title, brand, material, use) if description is None else description,
        image=image, availability=availability, group=group, gtin=gtin, extra_images=extra_images,
        label=label, dims=dims or {},
    ))


# --- Sofás y muebles (14) ---------------------------------------------------------------
add("DM-10001", "Sofá Nordlicht Tela", "Nordlicht", "Muebles/Living/Sofás", f"{FURNITURE} > Sofás",
    "Gris Piedra", "3 Cuerpos", 899990, 649990, material="tela de lino y estructura de pino", use="el living",
    dims={"product_width": "210 cm", "product_height": "85 cm"})
add("DM-10002", "Sofá Nordlicht Tela", "Nordlicht", "Muebles/Living/Sofás", f"{FURNITURE} > Sofás",
    "Gris Piedra", "2 Cuerpos", 699990, 499990, material="tela de lino y estructura de pino", use="el living",
    dims={"product_width": "160 cm", "product_height": "85 cm"})
add("DM-10003", "Sofá Cama Brisa", "Brisa", "Muebles/Living/Sofás", f"{FURNITURE} > Sofás cama",
    "Azul Petróleo", "3 Cuerpos", 549990, 459990, material="microfibra y espuma de alta densidad", use="espacios pequeños")
add("DM-10004", "Sillón Reclinable Solano", "Solano", "Muebles/Living/Sillones", f"{FURNITURE} > Sillones",
    "Café", "1 Cuerpo", 389990, 389990, material="cuero sintético", use="descansar frente a la TV")  # sale == price
add("DM-10005", "Mesa de Centro Roble Natural", "Solano", "Muebles/Living/Mesas", f"{FURNITURE} > Mesas > Mesas de centro",
    "Roble", "100 x 60 cm", 189990, 149990, material="madera de roble macizo", use="el living",
    dims={"product_width": "100 cm", "product_length": "60 cm"})
add("DM-10006", "MESA DE COMEDOR EXTENSIBLE ¡OFERTA! ENVÍO GRATIS", "Kumo", "Muebles/Comedor/Mesas", f"{FURNITURE} > Mesas",
    "Blanco", "6 Personas", 459990, 359990, material="MDF lacado", use="comidas familiares")
add("DM-10007", "Silla de Comedor Kumo", "Kumo", "Muebles/Comedor/Sillas", f"{FURNITURE} > Sillas",
    "Negro", "Única", 69990, 54990, material="polipropileno y patas de haya", use="el comedor")
add("DM-10008", "Silla de Comedor Kumo", "Kumo", "Muebles/Comedor/Sillas", f"{FURNITURE} > Sillas",
    "Blanco", "Única", 69990, 54990, material="polipropileno y patas de haya", use="el comedor")
add("DM-10009", "Rack TV Industrial", "Ferro", "Muebles/Living/Racks", f"{FURNITURE} > Muebles para TV",
    "Negro / Madera", "180 cm", 219990, 179990, material="acero y madera reciclada", use="televisores de hasta 75 pulgadas")
add("DM-10010", "Estante Librero 5 Repisas", "Ferro", "Muebles/Oficina/Estantes", f"{FURNITURE} > Estanterías",
    "Nogal", "180 x 80 cm", 129990, 99990, material="melamina de 18 mm", use="libros y decoración")
add("DM-10011", "Escritorio Home Office Compacto", "Ferro", "Muebles/Oficina/Escritorios", f"{FURNITURE} > Escritorios",
    "Blanco", "120 x 60 cm", 149990, 119990, material="melamina y acero", use="teletrabajo",
    description="")  # empty description
add("DM-10012", "Cama Box Spring Descanso Plus 2 Plazas", "Brisa", "Muebles/Dormitorio/Camas", f"{FURNITURE} > Camas",
    "Beige", "2 Plazas 150x200", 799990, 599990, material="resortes ensacados y espuma viscoelástica", use="un descanso profundo",
    dims={"product_width": "150 cm", "product_length": "200 cm"})
add("DM-10013", "Velador 2 Cajones Nórdico", "Nordlicht", "Muebles/Dormitorio/Veladores", f"{FURNITURE} > Mesitas de noche",
    "Natural", "45 x 40 cm", 79990, 64990, material="madera de pino", use="el dormitorio", image=False)  # missing image
add("DM-10014", "Cómoda 6 Cajones Nórdica con Patas de Madera Torneada, Tiradores Metálicos Dorados y Acabado "
    "Mate Antihuellas Ideal para Dormitorios Juveniles y Matrimoniales Modernos", "Nordlicht",
    "Muebles/Dormitorio/Cómodas", f"{FURNITURE} > Cómodas", "Blanco", "120 x 45 cm", 249990, 199990,
    material="MDF y madera", use="guardar ropa")  # title > 150 chars

# --- Ropa (14): variants without item_group_id (same title, different color) -----------
for i, color in enumerate(["Blanco", "Negro", "Azul Marino"]):
    add(f"DM-20{i + 1:03d}", "Polera Básica Algodón Orgánico", "Kumo", "Ropa/Hombre/Poleras", f"{CLOTHES} > Camisetas",
        color, "M", 12990, 9990, material="algodón orgánico 100%", use="el uso diario", label="Tienda Demo")
for i, size in enumerate(["S", "M", "L"]):
    add(f"DM-20{i + 4:03d}", "Polerón Canguro Felpa", "Kumo", "Ropa/Mujer/Polerones", f"{CLOTHES} > Sudaderas",
        "Gris Melange", size, 29990, 24990, material="algodón y poliéster", use="días frescos", group="POLERON-FELPA")
add("DM-20007", "Chaqueta Impermeable Trekking", "Andes Pro", "Ropa/Hombre/Chaquetas", f"{CLOTHES} > Abrigos y chaquetas",
    "Verde Oliva", "L", 89990, 69990, material="poliéster con membrana impermeable", use="actividades al aire libre")
add("DM-20008", "Jeans Slim Fit Elasticado", "Denim Sur", "Ropa/Mujer/Jeans", f"{CLOTHES} > Pantalones",
    "Azul Claro", "38", 34990, 27990, material="denim con elastano", use="el día a día")
add("DM-20009", "Vestido Lino Verano", "Brisa", "Ropa/Mujer/Vestidos", f"{CLOTHES} > Vestidos",
    "Terracota", "M", 39990, 44990, material="lino", use="días de calor")  # sale > price
add("DM-20010", "Camisa Oxford Manga Larga", "Denim Sur", "Ropa/Hombre/Camisas", f"{CLOTHES} > Camisas",
    "Celeste", "L", 27990, 22990, material="algodón oxford", use="la oficina",
    description="<p>Camisa <b>Oxford</b> de algodón.</p><ul><li>Cuello abotonado</li><li>Corte regular</li></ul>")  # HTML
add("DM-20011", "Pijama Polar Infantil", "Demo Kids", "Ropa/Niños/Pijamas", f"{CLOTHES} > Ropa de dormir",
    "Rosado", "8 años", 19990, 15990, material="polar antipilling", use="noches de invierno", label="Demo Kids")
add("DM-20012", "Calcetines Deportivos Pack 3", "Andes Pro", "Ropa/Unisex/Calcetines", f"{CLOTHES} > Calcetines",
    "Surtido", "39-42", 7990, 5990, material="algodón y poliamida", use="hacer deporte", availability="Out of Stock")
add("DM-20013", "Gorro Lana Merino", "Andes Pro", "Ropa/Unisex/Accesorios", f"{CLOTHES} > Gorros",
    "Mostaza", "Única", 14990, 11990, material="lana merino", use="el invierno")
add("DM-20014", "Bufanda Tejida Trenzas", "Brisa", "Ropa/Unisex/Accesorios", f"{CLOTHES} > Bufandas",
    "Burdeo", "Única", 16990, 12990, material="acrílico suave", use="el invierno", description="")  # empty description

# --- Zapatos (9): legitimate variants with item_group_id ----------------------------------
for i, size in enumerate(["40", "41", "42", "43"]):
    add(f"DM-30{i + 1:03d}", "Zapatilla Urbana Runner", "Pisada", "Calzado/Hombre/Zapatillas", f"{SHOES} > Zapatillas",
        "Negro", size, 59990, 47990, material="malla transpirable y suela de goma", use="caminar por la ciudad",
        group="RUNNER-NEGRO", gtin=gtin13(f"780000003{i + 1:03d}"))
add("DM-30005", "Botín Cuero Chelsea", "Pisada", "Calzado/Mujer/Botines", f"{SHOES} > Botas",
    "Café", "38", 79990, 63990, material="cuero natural", use="el otoño", gtin="7800000030059")  # invalid check digit
add("DM-30006", "Sandalia Plataforma Corcho", "Brisa", "Calzado/Mujer/Sandalias", f"{SHOES} > Sandalias",
    "Beige", "37", 32990, 26990, material="corcho y cuero sintético", use="el verano")
add("DM-30007", "Zapato Formal Derby", "Pisada", "Calzado/Hombre/Formales", f"{SHOES} > Zapatos",
    "Negro", "42", 69990, 59990, material="cuero liso", use="ocasiones formales", availability="Out of Stock")
add("DM-30008", "Pantufla Memory Foam", "Kumo", "Calzado/Unisex/Pantuflas", f"{SHOES} > Pantuflas",
    "Gris", "39-40", 17990, 13990, material="felpa y espuma con memoria", use="estar en casa")
add("DM-30009", "Bota de Lluvia Infantil", "Demo Kids", "Calzado/Niños/Botas", f"{SHOES} > Botas",
    "Amarillo", "30", 19990, 16990, material="caucho natural", use="días de lluvia", label="Demo Kids")

# --- Limpieza (8) ----------------------------------------------------------------------------
add("DM-40001", "Detergente Líquido Concentrado 3 L", "Pulcro", "Hogar/Limpieza/Lavandería", f"{CLEANING} > Detergentes",
    "Sin color", "3 L", 12990, 9990, material="fórmula biodegradable", use="lavar 60 cargas", gtin=gtin13("780000004001"))
add("DM-40002", "Limpiador Multiuso Cítrico 1 L", "Pulcro", "Hogar/Limpieza/Superficies", f"{CLEANING} > Limpiadores multiuso",
    "Sin color", "1 L", 3990, 3290, material="extracto de cítricos", use="cocina y baño", gtin=gtin13("780000004002"))
add("DM-40003", "Paños de Microfibra Pack 6", "Pulcro", "Hogar/Limpieza/Accesorios", f"{CLEANING} > Paños",
    "Multicolor", "30 x 30 cm", 6990, 5490, material="microfibra", use="limpiar sin rayar")
add("DM-40004", "Mopa Giratoria con Balde", "Pulcro", "Hogar/Limpieza/Pisos", f"{CLEANING} > Mopas",
    "Azul", "Única", 24990, 19990, material="plástico reforzado y microfibra", use="todo tipo de pisos")
add("DM-40005", "Escoba Cerdas Suaves Interior", "Pulcro", "Hogar/Limpieza/Pisos", f"{CLEANING} > Escobas",
    "Verde", "Única", 5990, 4990, material="cerdas sintéticas y mango de aluminio", use="interiores")
add("DM-40006", "Desengrasante Cocina Spray 750 ml", "Pulcro", "Hogar/Limpieza/Cocina", f"{CLEANING} > Desengrasantes",
    "Sin color", "750 ml", 4590, 3990, material="fórmula sin fosfatos", use="campanas y hornos")
add("DM-40008", "Bolsas de Basura Biodegradables x30", "Pulcro", "Hogar/Limpieza/Basura", f"{CLEANING} > Bolsas de basura",
    "Negro", "80 x 110 cm", 3990, 3490, material="plástico biodegradable", use="residuos domésticos")

# --- Ropa de cama (5) -------------------------------------------------------------------------
add("DM-50001", "Plumón Microfibra 2 Plazas", "Brisa", "Hogar/Ropa de Cama/Plumones", f"{BEDDING} > Edredones",
    "Blanco", "2 Plazas", 49990, 39990, material="microfibra hipoalergénica", use="noches frías")
add("DM-50002", "Juego de Sábanas 300 Hilos", "Brisa", "Hogar/Ropa de Cama/Sábanas", f"{BEDDING} > Sábanas",
    "Gris Piedra", "King", 39990, 31990, material="algodón percal", use="un descanso fresco")
add("DM-50003", "Almohada Viscoelástica Cervical", "Brisa", "Hogar/Ropa de Cama/Almohadas", f"{BEDDING} > Almohadas",
    "Blanco", "50 x 70 cm", 24990, 19990, material="espuma viscoelástica", use="cuidar la postura")
add("DM-50004", "Manta Polar Jacquard", "Kumo", "Hogar/Ropa de Cama/Mantas", f"{BEDDING} > Mantas",
    "Azul Marino", "2 Plazas", 21990, 17990, material="polar jacquard", use="el invierno")
add("DM-50005", "Cubrecolchón Impermeable", "Brisa", "Hogar/Ropa de Cama/Protectores", f"{BEDDING} > Protectores de colchón",
    "Blanco", "1,5 Plazas", 17990, 14990, material="tela de rizo con membrana", use="proteger el colchón")

# Duplicate id on purpose (same SKU as the first sofa, different product).
add("DM-10001", "Puff Redondo Tejido", "Nordlicht", "Muebles/Living/Puffs", f"{FURNITURE} > Pufs",
    "Mostaza", "45 cm", 39990, 32990, material="tejido de algodón", use="el living")


def item_xml(p: dict) -> str:
    slug = p["sku"].lower()
    lines = [
        "<item>",
        f"<g:id>{cdata(p['sku'])}</g:id>",
        f"<title>{cdata(p['title'])}</title>",
        f"<description>{cdata(p['description'])}</description>",
        f"<link>{SITE}/{slug}.html</link>",
    ]
    if p["image"]:
        lines.append(f"<g:image_link>{SITE}/media/catalog/product/{slug}-1.jpg</g:image_link>")
    lines += [
        "<g:condition>new</g:condition>",
        f"<g:price>{clp(p['price'])}</g:price>",
        "<g:tax>\n    <g:country>CL</g:country>\n    <g:rate>0</g:rate>\n    <g:tax_ship>y</g:tax_ship>\n</g:tax>",
        f"<g:availability>{cdata(p['availability'])}</g:availability>",
        f"<g:google_product_category>{p['gcat']}</g:google_product_category>",
        f"<g:identifier_exists>{'TRUE' if p['gtin'] else 'FALSE'}</g:identifier_exists>",
        f"<g:product_type>{cdata(p['ptype'])}</g:product_type>",
    ]
    if p["sale"] is not None:
        lines.append(f"<g:sale_price>{clp(p['sale'])}</g:sale_price>")
    lines += [
        f"<g:brand>{cdata(p['brand'])}</g:brand>",
        f"<g:color>{cdata(p['color'])}</g:color>",
        f"<g:size>{cdata(p['size'])}</g:size>",
        f"<g:material>{cdata(p['material'])}</g:material>",
    ]
    if p["gtin"]:
        lines.append(f"<g:gtin>{p['gtin']}</g:gtin>")
    if p["group"]:
        lines.append(f"<g:item_group_id>{p['group']}</g:item_group_id>")
    for key, value in p["dims"].items():
        lines.append(f"<g:{key}>{cdata(value)}</g:{key}>")
    for n in range(2, 2 + p["extra_images"]):
        lines.append(f"<g:additional_image_link>{cdata(f'{SITE}/media/catalog/product/{slug}-{n}.jpg')}</g:additional_image_link>")
    lines.append(f"<g:custom_label_0>{p['label']}</g:custom_label_0>")
    lines.append("</item>")
    return "\n".join(lines)


def build() -> str:
    assert len(PRODUCTS) == 50, len(PRODUCTS)
    body = "\n\n".join(item_xml(p) for p in PRODUCTS)
    return f'<?xml version="1.0"?> <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>\n\n{body}\n\n</channel></rss>\n'


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "../demo/demo_feed.xml")
    out.write_text(build(), encoding="utf-8")
    print(f"{out}: {len(PRODUCTS)} products")
