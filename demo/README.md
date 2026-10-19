# Demo

Everything in this folder is fictional: brands, products, SKUs, prices, GTINs
and URLs (on the reserved `.example` domain, all over HTTPS).

| File | Purpose |
|---|---|
| `demo_feed.xml` | 50-product catalog (furniture, sofas, clothing, shoes, cleaning, bedding) in Google RSS 2.0 format. Regenerate with `cd backend && python -m scripts.make_demo_feed`. |
| `seed_demo.py` | Loads the demo into a running Feed Studio using only the Python standard library. |

## Load the demo

```bash
docker compose up -d --build
```

```bash
python demo/seed_demo.py
```

The script creates the source **Tienda demo**, reading
`https://raw.githubusercontent.com/raulbernardogil/feedstudio/main/demo/demo_feed.xml`
and refreshing it **every 2 hours**; the channel **Google Merchant Center** with
automatic publication; two rules; and runs the first full update. Open
http://localhost:8080.

Without internet access, or before the file is on GitHub, use
`python demo/seed_demo.py --upload` (the scheduled refresh needs a URL source,
so it is skipped in that mode).

## Rules included

| Rule | Condition | Action |
|---|---|---|
| Añadir descripcion vacia (priority 80) | `description` is empty | Set a fallback description |
| Añadir premium (priority 100) | `brand` contains "ferro" | Prepend `PREMIUM ` to `title` |

## Deliberate data problems

The feed contains them on purpose so diagnostics have something to show:
duplicate id (`DM-10001`), invalid GTIN (`DM-30005`), empty descriptions
(`DM-10011`, `DM-20014`), missing image (`DM-10013`), title over 150 characters
(`DM-10014`), HTML in a description (`DM-20010`), promotional all-caps title
(`DM-10006`), `sale_price ≥ price` (`DM-10004`, `DM-20009`), variants without
`item_group_id`, out-of-stock items and locale-formatted CLP prices.

## Google Drive

Connecting Google Drive needs your own OAuth client: see
[docs/google-drive.md](../docs/google-drive.md).
