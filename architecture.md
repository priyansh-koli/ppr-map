# Architecture at a glance

The project structure, tech stack and integrations on one page. For the full system diagram, the step-by-step data flow and the reasoning behind each choice, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/data-model.md](docs/data-model.md), [docs/api.md](docs/api.md) and [docs/DECISIONS.md](docs/DECISIONS.md).

## How it fits together

```
                       ┌──────────── Browser ────────────┐
                       │  Next.js pages + MapLibre map   │
                       └───────────────┬─────────────────┘
                                       │  one origin: http://localhost:8080 (Caddy)
          ┌──────────────────┬─────────┴──────────┬────────────────────┐
     /api/v1/tiles/*      /api/*            /basemap/*            everything else
          │                  │                    │                    │
       Martin             FastAPI          PMTiles files          Next.js server
     (tile server)      (/api/v1)        (basemap, terrain)      (frontend:3000)
          │                  │
          └────────┬─────────┘
                   ▼
        PostgreSQL 16 + PostGIS ◄──── pipeline (`ppr` CLI) ◄──── PPR, OSM, GTFS, Tailte,
                   ▲                  run by RQ workers           Pobal, CSO, DHLGH (batch)
                 Redis                       │
     (cache, RQ queues, rate limits)   Nominatim (batch geocoding only)
```

- **Read-heavy, monthly data.** Everything that is expensive is precomputed by the pipeline:
  - `property_summary` (hover cards);
  - `area_stats`;
  - `price_hex`;
  - `property_enrichment`.
- **One matching function.** `tile_matching_sales(env, params)` in SQL defines what a filter matches. The map tiles, the synced list, `/search`, saved searches and alerts all call it, so they cannot disagree (D-047). Migrations 0004, 0008 and 0012 define it.
- **No third party at view time.** Basemap, terrain, fonts, geocoding and enrichment are all self-hosted or precomputed.

## Repository structure

```
ppr-map/
├── CLAUDE.md, CONVENTIONS.md     working rules (read first)
├── goal.md, requirements.md, architecture.md, design.md, progress.md, task.md
├── Makefile                      every command: `make help`
├── .env.example                  every env var, documented, no values (`make env` creates .env)
├── backend/                      FastAPI app (Python 3.12)
│   ├── app/api/v1/               routes: properties, search, areas, stats, auth, me,
│   │                             saved_searches, reports, admin, tools, sources, health
│   ├── app/services/             SQL and logic: search, properties, areas, estimate, rppi,
│   │                             alerts, accounts, audit, email, rates, housekeeping
│   ├── app/models/               SQLAlchemy 2 typed ORM (data.py, users.py, enums.py)
│   ├── app/schemas/              Pydantic v2 API shapes (camelCase on the wire)
│   ├── app/auth/                 sessions, passwords (argon2id), CSRF, rate limits, permissions
│   ├── app/cli.py                admin CLI: grant-role, send-alerts, purge-deleted, openapi
│   ├── alembic/versions/         migrations 0001–0013 (tile functions live here as SQL)
│   └── tests/                    pytest; `db`-marked tests need PostGIS
├── pipeline/                     the `ppr` CLI (Typer); imports the backend's models
│   └── src/ppr_pipeline/
│       ├── ppr/                  download, cp1252 parse, load, bulk-sale flags
│       ├── address.py            normalisation and dedupe keys
│       ├── boundaries.py         Tailte Éireann counties, EDs, Small Areas, townlands, towns
│       ├── geocode/              Nominatim cascade (rules, runner), local gazetteer
│       ├── enrich/               stops, POIs, schools, Pobal deprivation, vicinity
│       ├── benchmarks.py         CSO RPPI and the estimate's calibration
│       └── aggregate.py          area_stats, price_hex, property_summary (one transaction)
├── frontend/                     Next.js App Router, TypeScript strict, Tailwind v4
│   ├── src/app/                  one folder per route (list in src/lib/routes.ts)
│   ├── src/components/           map, search, property, area, account, admin, home, tools, ui
│   ├── src/lib/                  api client + generated OpenAPI types, filters, formats
│   └── e2e/                      Playwright smoke tests over every route
├── infra/                        docker-compose.yml, caddy/Caddyfile, martin/martin.yaml
├── config/                       sources.yaml (every dataset, licence, allow/deny), rates.yaml
├── data/                         downloads, basemap, extracts (not committed)
└── docs/                         decisions, architecture, data model, API, permissions, research
```

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript strict, Tailwind CSS v4, MapLibre GL JS 6, PMTiles; fonts self-hosted with next/font |
| API | FastAPI, Python 3.12, SQLAlchemy 2 (async, psycopg), Pydantic v2, RFC 9457 problem+json errors |
| Database | PostgreSQL 16, PostGIS 3, `pg_trgm`, `citext`; H3 cells computed in Python, stored as `bigint` |
| Tiles | Martin, serving the PostGIS functions `sales_tiles` and `price_hex_tiles` |
| Jobs | RQ workers, plus one scheduler process that only queues jobs (D-051) |
| Geocoding | Self-hosted Nominatim (Ireland extract) and a local street gazetteer (D-046) |
| Cache | Redis: hover cards, rate limits, sessions cache, RQ queues |
| Auth | Opaque server-side sessions, argon2id, CSRF tokens |
| Basemap | Protomaps PMTiles for Ireland, plus Mapterhorn terrain, both self-hosted |
| Local dev | Docker Compose: db, redis, api, worker, scheduler, martin, frontend, caddy, mailpit, nominatim (opt-in profile) |
| Quality | ruff, mypy strict, pytest; eslint, prettier, tsc, Vitest, Playwright; GitHub Actions CI |
| Preview hosting | Vercel, a static export of the frontend only (D-056) |

## Integrations

**Data sources** (batch only; full list with licences in [docs/external-services.md](docs/external-services.md) and [config/sources.yaml](config/sources.yaml)):

| In use | Planned (verified, not loaded) | Blocked or rejected |
|---|---|---|
| PSRA PPR (core sales) | National Planning Applications (D-017) | OPW flood (NC-ND licence) |
| OSM Geofabrik extract (Nominatim, amenities, schools, gazetteer) | GZT zoning, EPA radon, EPA noise (D-018) | Daft, landdirect, propertymap (terms) |
| NTA GTFS (stops) | CSO crime CJA07, RTB rents RIQ02 | Google geocoding (terms) |
| Tailte Éireann boundaries | Dept of Education school lists (gov.ie blocks automated download) | SEAI BER at Eircode level (restricted) |
| Pobal deprivation (ED level) | | |
| DHLGH housing surveys (estates) | | |
| CSO RPPI HPM09 (estimate) | | |

**Runtime services:** Mailpit in development. Email, object storage, error tracking and the production host are all undecided (Q-04), and anything paid needs the owner's approval.

## Caching and versions

- **`dataVersion`:** for example `2026-09-18.r1.a27` (latest sale, PPR ingest run, aggregate run). It changes with every aggregate run and keys the hover-card cache (`summary:{id}:{dataVersion}`).
- **`tilesVersion`:** `dataVersion` plus the time of the latest admin hide or move. The map adds it to tile URLs as `v`, because Martin caches tiles by URL (D-057).
- **`/meta`:** cached in each API process for 60 s.

## Commands

| Task | Command |
|---|---|
| Start the stack | `make up`, then `make migrate`; open http://localhost:8080 (Mailpit at :8025) |
| Pipeline | `make pipeline` (monthly: ingest, gazetteer, geocode, enrich, benchmarks, aggregate); single steps: `make geocode`, `make aggregate`, … |
| Quality gates | `make lint`, `make typecheck`, `make test`, `make test-db` (needs the stack running), `make e2e` |
| After an API change | `make api-types` (regenerates `frontend/openapi.json` and the TypeScript types) |
| New migration | `cd backend && ../.venv/bin/alembic revision --autogenerate -m "..."`, then review the file |

Note: the `frontend` container runs a production build, so it must be rebuilt after frontend changes: `docker compose --env-file .env -f infra/docker-compose.yml up -d --build frontend`. The API reloads by itself.
