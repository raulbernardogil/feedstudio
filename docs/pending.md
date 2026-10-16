# Pending work

Explicit list of what is NOT implemented. Nothing here is simulated in the UI:
features that do not exist have no buttons.

## Verified on 2026-10-16
- API test suite against PostgreSQL 16 (`FEEDSTUDIO_TEST_DATABASE_URL`): 8/8 pass.
- `docker compose up --build`: db, redis, api (healthy), RQ worker and nginx web.
  The real feed was imported, transformed, generated and published through
  `http://localhost:8080` with jobs executed by the RQ worker.

## Not verified
- Browser file upload through the dialog (the automated browser could not attach
  local files; the same endpoint was exercised with curl and in API tests).
- Production hardening of the compose stack (TLS termination, backups,
  resource limits, secrets management).

## Phase 2 — advanced engine (partially done)
Done already: nested conditions, all 20 actions, custom labels via rules,
exclusions, rule versioning, run history.
- Dedicated title optimizer screen (per-category templates, duplicate-word
  removal, promotional-term removal list). Today: generic rules + diagnostics.
- Built-in color/size dictionaries per market (today: user-defined `map_values`).
- Size-system conversion (intentionally not done without verified tables).
- Structured duplicate detection beyond id/title/variant keys.
- External URL/image checks (HTTP status, image size ≥ 500 px from 2027-01-31).
- Unique-value limit per custom label (1,000).
- Rule templates library; copy rules between channels.

## Phase 3 — automation & channels
- Scheduled refresh (6/12/24 h, custom) with a scheduler process
  (`rq-scheduler` or APScheduler), auto-publish with anomaly threshold.
- Meta and Pinterest adapters (Pinterest requirements gathered; Meta pending
  verification of the official spec).
- Google Drive (OAuth with minimal scopes), SFTP and S3 sources; S3 storage adapter.
- Error notifications (email/webhook).
- Multiple catalogs per source / merging sources.

## Phase 4 — professional
- Users, organizations, roles and permissions (schema has `organizations`,
  `users`, `organization_id` everywhere; auth is a single optional API token).
- Optional AI assistance (title/description proposals with human approval,
  cost limits, AI-generated content disclosure per channel).
- Advanced calculated attributes (arithmetic).
- Performance metrics dashboards; backups automation.

## Known limitations
- Progress percentage during the first import of a source is indeterminate
  (no previous product count to estimate from).
- Preview scans up to `FEEDSTUDIO_PREVIEW_MAX_SCAN` products (200,000) and says
  when it is partial.
- `x-feed-generated-at` has no timezone with SQLite (stored naive).
- Frontend lint warnings (oxlint): 2× setState-in-effect (page reset) and
  1× fast-refresh export; no errors.
- Single JS bundle of ~670 KB (no code splitting yet).
