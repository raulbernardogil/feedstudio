# API

The interactive OpenAPI documentation is served by the backend at
`http://localhost:8000/docs` (schema: `/openapi.json`).

Conventions:
- JSON bodies; errors are `{"error": {"code", "message", "details"}}` with the
  proper HTTP status (404, 409 conflict, 413 too large, 422 validation, 401).
- Long operations return **202** with a `job`; follow it with
  `GET /api/jobs/{id}` or the SSE stream `GET /api/jobs/{id}/events`.
- Pagination: `page`, `page_size` ∈ {10, 25, 50, 100}; responses include `total`.
- If `FEEDSTUDIO_API_TOKEN` is set: `Authorization: Bearer <token>` on `/api/*`.

## Sources
| Method | Path | Description |
|---|---|---|
| GET | `/api/sources` | List sources with the active snapshot |
| POST | `/api/sources` | Create a URL source (HTTPS, SSRF-checked) and start the import |
| POST | `/api/sources/upload` | Multipart upload (`file`, `name`, optional `item_tag`, `source_id` for a new snapshot) |
| GET / PATCH / DELETE | `/api/sources/{id}` | Read / update / delete |
| POST | `/api/sources/{id}/refresh` | Re-download a URL source (409 if one is running) |
| GET | `/api/sources/{id}/snapshots` | Import history |
| GET | `/api/sources/{id}/schema` | Detected attributes (kind, type, coverage, samples) |

| PUT | `/api/sources/{id}/schedule` | `{mode: manual|interval|daily, every_hours, times: ["08:00"], timezone}`; URL sources only |
| POST | `/api/sources/{id}/run` | Run the full pipeline now (refresh → generate → auto-publish → deliver) |

## Google Drive
| Method | Path | Description |
|---|---|---|
| GET | `/api/integrations/google` | Whether the server is configured, redirect URI and connected accounts |
| POST | `/api/integrations/google/authorize` | Consent URL (scope `drive.file`) |
| GET | `/api/integrations/google/callback` | OAuth redirect target (signed, expiring `state`) |
| DELETE | `/api/integrations/google/{id}` | Revoke and remove an account |
| GET / POST | `/api/channels/{id}/destinations` | Drive destinations: `{google_account_id, file_name, folder}` (folder URL or id) |
| PATCH / DELETE | `/api/destinations/{id}` | Rename, change folder, pause, remove |
| POST | `/api/destinations/{id}/deliver` | Upload the published version now |

## Catalogs (catalog id = source id)
| Method | Path | Description |
|---|---|---|
| GET | `/api/catalogs/{id}/products` | `q`, `filters` (JSON list of `{field, op, value}`), `issue_level`, `issue_code`, `sort`, `order` |
| GET | `/api/catalogs/{id}/products/export` | CSV of the filtered products |
| GET | `/api/catalogs/{id}/products/{product_id}` | Product + original diagnostics |
| GET | `/api/catalogs/{id}/stats` | Levels, top brands/types, availability |
| GET | `/api/catalogs/{id}/issues` | Diagnostics summary of the original data |
| GET | `/api/catalogs/{id}/original` | Download the original XML |

## Rules
| Method | Path | Description |
|---|---|---|
| GET | `/api/rules?source_id=&channel_id=` | Global + channel rules in execution order |
| POST | `/api/rules` | `{source_id, channel_id|null, definition}` |
| GET / PUT / DELETE | `/api/rules/{id}` | Every PUT creates a new version |
| GET | `/api/rules/{id}/versions` | Version history |
| POST | `/api/rules/preview` | Draft preview over the active catalog (see rules-engine.md) |
| POST | `/api/rules/test` | Full trace for one product (`product_id` or `external_id`) |

## Channels, feeds and validation
| Method | Path | Description |
|---|---|---|
| GET / POST | `/api/channels` | List / create (`kind: "google"`) |
| GET / PATCH / DELETE | `/api/channels/{id}` | |
| POST | `/api/channels/{id}/rotate-token` | Revoke the public URL and issue a new one |
| GET | `/api/channels/{id}/versions` | Generated versions |
| GET | `/api/channels/{id}/publications` | Publish/rollback history |
| POST | `/api/feeds/generate` | `{channel_id}` → candidate version + job |
| POST | `/api/validations/run` | Alias of generate: the candidate version is the validation report |
| GET | `/api/feed-versions/{id}` | Version detail (incl. rules snapshot) |
| POST | `/api/feed-versions/{id}/publish` | `{force}`; older version = rollback; 409 `publish_blocked` on large drops |
| GET | `/api/feed-versions/{id}/download?format=xml|csv` | Download |
| GET | `/api/feed-versions/{id}/issues` | Diagnostics + comparison with the previous version |
| GET | `/api/feed-versions/{id}/items` | Before/after rows: `only_changed`, `only_errors`, `excluded`, `rule_id`, `issue_code`, `issue_level`, `q`, `filters` |

## System
| Method | Path | Description |
|---|---|---|
| GET | `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/events` | Job history, detail, SSE |
| GET | `/api/dashboard` | Dashboard indicators |
| GET | `/api/settings` | Non-secret configuration |
| GET | `/api/audit-logs` | Audit trail |
| GET | `/health` | DB + storage health (503 if degraded) |
| GET/HEAD | `/f/{token}/google.xml` (`.csv`) | Public published feed; `ETag`, `X-Feed-Version`, 304 support |
