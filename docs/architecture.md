# Architecture and decisions

## Overview

```
Browser (React SPA) ──HTTP/JSON──► FastAPI ──► PostgreSQL / SQLite
                                     │
                                     ├─► Job runner (thread pool | RQ + Redis workers)
                                     │      import:   fetch → store original → stream-parse → persist products + issues
                                     │      generate: rules → validation → materialized items → XML/CSV
                                     └─► Object storage (local FS; S3 adapter pending)
Ad platforms ──GET /f/{token}/google.xml──► FastAPI (published version file)
```

Pipeline for one channel:

`Original snapshot (immutable XML) → normalized products → global rules → channel rules → Google validation → feed items (materialized) → XML/CSV file → publication pointer`

## Backend layout (feature-oriented)

| Package | Responsibility | Depends on |
|---|---|---|
| `catalog/attributes.py` | Internal product value model | nothing |
| `rules/` | Schema, conditions, templates, actions, engine | `catalog` |
| `ingestion/` | Secure streaming parser, schema inventory, SSRF-safe fetcher | `catalog`, `rules.text` |
| `validation/` | Google profile, GTIN, issue catalog | `catalog`, `rules.text` |
| `export/` | Incremental Google XML writer, CSV | `catalog` |
| `services/` | Use cases: import, generate/publish, preview | all of the above + `models` |
| `api/` | HTTP adapters (routers, serialization, errors, auth) | `services`, `models` |
| `models.py`, `db.py`, `storage.py`, `jobs.py` | Persistence, storage and job adapters | SQLAlchemy, Redis |

The domain packages (`catalog`, `rules`, `ingestion`, `validation`, `export`)
have no FastAPI or SQLAlchemy dependency and are unit-tested in isolation.

## Key decisions

1. **Python + FastAPI + lxml.** `lxml.iterparse` gives streaming parsing with
   libxml2 security switches; Python is the preferred stack in the brief.
2. **Rules as versioned JSON documents** instead of `rule_conditions` /
   `rule_actions` tables. Nested condition trees are always loaded whole,
   validated by one Pydantic schema (`schema_version` for migrations), and every
   save writes a `rule_versions` row. Querying rules by condition is not a
   requirement.
3. **Products stored as JSON + denormalized columns.** Arbitrary attributes
   (any namespace, repeated, nested) fit a JSON column; id/title/brand/price/
   availability/product_type/search text are columns with indexes for search and
   sort. Arbitrary attribute filters use JSON path expressions (JSONB in
   PostgreSQL). `product_attributes` (EAV) was rejected: it multiplies rows by
   ~20 and complicates nested values.
4. **Catalog = active snapshot of a source** (1:1 in this phase). Each import is
   a new snapshot; the source points to the last successful one, so a failed sync
   keeps the previous catalog. Original XML files are kept immutable; parsed rows
   of old snapshots are pruned (configurable retention) when no feed version
   references them.
5. **Materialized feed items per version.** Generation writes each transformed
   product, its changes, the rules involved and its validation issues. The
   before/after view, diagnostics and the XML all read the same rows, so they are
   consistent and paginated server-side. Cost: storage proportional to catalog
   size per version.
6. **Atomic publication.** Version files are immutable; publishing is a
   single-row update of `channels.published_version_id` plus a
   `feed_publications` history row. Rollback = publishing an older version.
   A safety threshold blocks publishing a version that loses more than 50 % of
   the items (configurable) unless forced.
7. **Jobs behind a port.** `ThreadJobRunner` (any OS, development) and
   `RqJobRunner` (Redis workers, Docker/Linux). RQ was chosen over Celery for its
   smaller surface. Job state is in the database so the UI only polls/streams
   (`/api/jobs/{id}/events` is SSE).
8. **Short transactions per batch (500 rows).** SQLite allows a single writer;
   long transactions blocked progress updates during the first real-feed test
   (a real bug found and fixed). Partial rows of a failed import/generation are
   deleted; nothing is activated until the end.
9. **SQLite for local development, PostgreSQL in Docker.** Same migrations
   (Alembic) for both; circular foreign keys are created after both tables in
   PostgreSQL.
10. **Security first in ingestion.** DTD/DOCTYPE rejected, entity resolution and
    network access disabled in libxml2, depth/size/item limits, GZIP bomb cap,
    SSRF guard with DNS validation of every redirect hop and post-connect peer
    check, regex timeouts, CSV formula escaping, React escaping by default (no
    `dangerouslySetInnerHTML`).
11. **Tenancy-ready.** Every top-level entity has `organization_id` and every
    API query filters by the caller's organization. Phase 1 has a single default
    organization and an optional shared API token; users/roles are Phase 4.

## Memory model

- Parsing: one `<item>` in memory at a time (elements are cleared and
  detached). Measured RSS stays ~40 MB for a 112 MB file (docs/performance.md).
- Duplicate/variant detection needs global indexes: memory is O(products) for
  ids/titles/variant keys, not O(XML size). This cannot be constant.
- Generation streams products from the database with keyset pagination and
  writes XML incrementally with `lxml.etree.xmlfile`.
