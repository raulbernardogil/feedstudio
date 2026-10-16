# Feed Studio

Web platform to import e-commerce XML product feeds, transform them with visual
IF/THEN rules, validate them against channel requirements and publish optimized
feeds at stable URLs. Functionally inspired by DataFeedWatch (no code, assets or
texts reused). UI language: Spanish (i18n-ready).

**Status: Phase 1 (MVP) complete and tested end to end** with the real feed
`client_feed.xml` (12.5 MB, 4,159 products). See
[docs/pending.md](docs/pending.md) for what is not done or not verified.

## What it does

1. Import XML from an upload or an HTTPS URL (RSS 2.0 + Google namespace, Atom 1.0,
   custom XML with auto-detected or configured product node; GZIP supported).
2. Keep every original file as an immutable snapshot; detect all attributes
   (scalar, repeated, nested) with coverage, types and samples.
3. Browse products in a server-paginated table (10/25/50/100), search by SKU or
   text, filter by any attribute, sort, choose/reorder columns, export CSV.
4. Build rules visually: nested AND/OR conditions (16 operators), 18 action types
   (prefix, suffix, replace, templates with `{brand} {title}[ - {color}]`,
   dictionaries, price normalization, truncation, regex extraction, exclusion,
   custom labels…), global or per-channel scope, deterministic order, versioning.
5. Preview any rule before saving on the real catalog with the backend engine:
   affected products, before/after diff, new validation issues, conflicts.
6. Generate a channel version: rules → Google validation (errors, warnings,
   recommendations) → materialized before/after view → Google RSS 2.0 XML + CSV.
7. Publish atomically at `/f/{secret-token}/google.xml`, roll back, revoke URLs;
   publication is blocked if a version suddenly loses most products.

## Quick start (local development, no Docker)

Requirements: Python ≥ 3.12, Node.js ≥ 20.

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS: .venv/bin/pip
.venv/Scripts/python run_dev.py                        # migrates SQLite, serves http://localhost:8000
```

```bash
cd frontend
npm install
npm run dev                                            # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173, go to **Fuentes XML → Añadir fuente** and upload
`client_feed.xml` (or `backend/samples/sample_feed.xml`).
API docs: http://localhost:8000/docs.

## Docker Compose (PostgreSQL + Redis + RQ worker + nginx)

```bash
cp .env.example .env        # set POSTGRES_PASSWORD, optionally FEEDSTUDIO_API_TOKEN
docker compose up --build   # UI: http://localhost:8080  API: http://localhost:8000
```

Verified with Docker Desktop (WSL 2): the real feed runs end to end through
nginx, the API, PostgreSQL 16 and the RQ worker. On Windows, if `docker info`
returns HTTP 500 with `no route to host` in the Docker Desktop logs, quit Docker
Desktop, run `wsl --shutdown` and start it again.

## Typical flow

1. **Fuentes XML**: add the feed; review detected attributes.
2. **Canales de exportación**: create a Google Merchant Center channel.
3. **Validación y diagnóstico**: review original-data issues; “Crear regla”
   pre-fills a fix (e.g. normalize `949.990,00 CLP` → `949990.00 CLP`).
4. **Editor de reglas**: build/preview rules (global or per channel).
5. **Canales → Generar y validar**: build a candidate version.
6. **Vista previa**: compare original vs transformed, filter by rule/errors.
7. **Publicar** (or download XML/CSV). Give the public URL to Merchant Center.

Findings on the real feed (before rules): 5 products with blocking errors
(4 empty descriptions, 1 missing main image). Every product has warnings for
undocumented but readable formats: locale-formatted `price`/`sale_price`
(`949.990,00 CLP`), `availability = "In Stock"` (documented `in_stock`) and
`identifier_exists = FALSE` (documented `yes`/`no`). 554 products have
`sale_price ≥ price`; 2,383 look like variants without `item_group_id`.
With 8 rules only 1 blocking error is left (the missing image).

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest          # 86 tests: engine, parser, security, validation, export, API e2e
cd frontend && npx vitest run && npx tsc -b           # 6 tests + type check
```

Covered scenarios include: 10 and 10,000-product feeds, empty feed, unknown,
repeated, nested and namespaced tags, special characters/CDATA, malformed XML
(with line), XXE / billion laughs / external DTD, GZIP bomb, depth limit,
duplicate ids, legitimate variants vs duplicates, chained/contradictory rules,
nested AND/OR, invalid regex, title length limits, export → reimport without
attribute loss, failed sync keeping the previous catalog, rollback, concurrent
imports (409), SSRF (private IPs, metadata IP, redirects, DNS rebinding cases),
pagination and filters. API tests can target PostgreSQL with
`FEEDSTUDIO_TEST_DATABASE_URL`.

Performance numbers (measured, not estimated): [docs/performance.md](docs/performance.md).

## Project structure

```
backend/
  feedstudio/
    catalog/      attribute value model
    ingestion/    secure streaming parser, schema inventory, SSRF-safe fetcher
    rules/        rule schema, conditions, templates, engine
    validation/   Google Merchant Center profile, GTIN
    export/       incremental Google XML writer, CSV
    services/     import, generate/publish, preview use cases
    api/          FastAPI routers
    models.py db.py jobs.py storage.py config.py main.py
  migrations/     Alembic
  tests/          pytest suite
  scripts/        benchmark
  samples/        sample feed
frontend/src/
  features/       dashboard, sources, catalog, rules, preview, validation, channels, jobs, settings
  components/     UI primitives (Radix-based), layout
  lib/            API client, types, workspace context, diff
  i18n/           Spanish messages
docs/             architecture, rules engine, requirements matrix, API, performance, pending
```

## Documentation

- [Architecture and decisions](docs/architecture.md)
- [Rules engine specification](docs/rules-engine.md)
- [Requirements matrix (sources, dates, status)](docs/requirements-matrix.md)
- [API](docs/api.md)
- [Performance](docs/performance.md)
- [Pending work](docs/pending.md)

## Security notes

DTDs are rejected and libxml2 runs without entity resolution or network access;
sizes, depth and item counts are bounded; URL sources are HTTPS-only by default
and every redirect hop and the connected peer are checked against private and
reserved ranges; regexes have timeouts; CSV cells are protected against formula
injection; public feed URLs use 192-bit random tokens and can be revoked. Set
`FEEDSTUDIO_API_TOKEN` before exposing the API: multi-user authentication is
Phase 4. Local validation does not guarantee approval by Google.
