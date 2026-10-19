# Feed Studio — frontend

React + TypeScript single-page app for Feed Studio. It only controls operations:
every transformation, preview and validation runs in the backend, so the UI can
never show results different from the generated feed. See the
[root README](../README.md) for the full project.

## Stack

Vite · React 19 · TypeScript · Tailwind CSS 4 · Radix UI · TanStack Query ·
TanStack Table 8 · React Hook Form + Zod · i18next (Spanish UI) · Vitest.

## Development

Requires Node.js ≥ 20 and the backend running on `http://localhost:8000`
(`backend/run_dev.py`).

```bash
npm install
npm run dev
```

The app is served at http://localhost:5173. Vite proxies `/api`, `/f/` and
`/health` to the backend; set `VITE_BACKEND_URL` to point elsewhere.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npx tsc -b` | Type check |
| `npx vitest run` | Unit and component tests |
| `npm run lint` | Lint with oxlint |
| `npm run build` | Production build into `dist/` |

## Structure

```
src/
  features/     one folder per screen: dashboard, sources, catalog, rules,
                preview, validation, channels, jobs, settings
  components/   UI primitives (Radix-based), layout, diff and job status
  lib/          API client and types, workspace context, job polling, diff
  i18n/         Spanish messages (add locales in i18n/index.ts)
  test/         Vitest setup and tests
```

Screens follow a container/presentational split: containers fetch data with
TanStack Query; presentational components receive props only.

## Production

`Dockerfile` builds the app and serves it with nginx (`nginx.conf`), which
proxies the API and the public feed URLs. It is started by the root
`docker-compose.yml` on http://localhost:8080.
