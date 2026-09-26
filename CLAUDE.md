# CLAUDE.md: project conventions

This app makes Ireland's Property Price Register (PPR) explorable on a map. Read `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` before changing structure.

## Working rules (from the project owner)

- Work in phases and **stop at each STOP checkpoint** for review. Current phase: **1 (scaffold)**. Phase 0 was reviewed on 2026-09-26: Q-09 = no licensed listing data, Q-10 = yes to the index-based estimate. Other open questions use their documented defaults.
- **Ask before adding any paid service or signing up for any API.** Also ask before contacting any third party on the project's behalf.
- Secrets live only in `.env`. Commit `.env.example` with every variable, documented, and no values.
- Write tests with each feature, not afterwards.
- Log every non-trivial decision in `docs/DECISIONS.md` (context, options, choice, why, status).
- **Never fake data.** Never invent bedrooms, floor area, photos or coordinates. If a requirement conflicts with what the data allows, say so and propose an alternative.

## Data rules

- PPR CSV is **cp1252**, not UTF-8. Keep the raw field values next to the parsed ones.
- Every coordinate carries a `geocode_confidence` (`exact | street | locality | routing_key | county | unmatched`) and a method. The UI shows it.
- Every enriched value is exposed as `Sourced<T>` (`value, source, asOf`).
- Default market filters exclude `not_full_market_price` and `bulk_group` sales. Always let users toggle them.
- New-build prices are VAT-exclusive as filed. Any VAT-inclusive figure is labelled as an estimate.
- The latest two months of PPR data are **provisional** in stats.
- Never join any dataset that could identify owners or occupants.
- Aggregates with n < 5 are suppressed.
- The hover-card path must never call a third party. Precompute.

## Repo layout (from Phase 1)

```
frontend/   Next.js App Router, TypeScript, Tailwind, MapLibre
backend/    FastAPI app (app/api, app/models, app/schemas, app/auth, app/services, app/cli.py), Alembic
pipeline/   Python package: ingest, normalise, dedupe, geocode, enrich, aggregate (CLI via Typer)
infra/      docker-compose.yml, Martin config, Nominatim setup, reverse proxy
docs/       architecture, decisions, data model, API, permissions, services, research
config/     sources.yaml (every dataset, licence, allow/deny) and rates.yaml (empty until verified in Phase 5)
```

## Code conventions

- **Python 3.12:** ruff (lint + format), mypy strict on `backend/` and `pipeline/`, SQLAlchemy 2 typed ORM (`Mapped[...]`), Pydantic v2, async DB sessions in the API and sync ones in the pipeline. Money is `Decimal`, never float.
- **TypeScript:** strict mode, eslint + prettier. Server components by default. Shared API types are generated from OpenAPI (`openapi-typescript`), never hand-written.
- **API:** `/api/v1`, camelCase JSON via Pydantic aliases, RFC 9457 problem+json errors, pagination with `page` and `pageSize`.
- **DB:** every schema change goes through an Alembic migration. Every geometry column gets a GIST index. Migrations must be reversible.
- **Tests:** pytest (backend and pipeline, with a Postgres+PostGIS test container), Vitest (frontend units), Playwright (key flows). Fixture CSVs are small cp1252 samples taken from the real PPR, including the tricky cases (Irish descriptions, mojibake, duplicate rows, bulk groups).
- **Accessibility:** WCAG 2.1 AA. The map always has a synced list view, the price scale is colour-blind-safe, and every hover interaction has a tap and a keyboard equivalent.
- **Geolocation** is requested only after an explicit button click.

## Commands

Run `make help` for the full list.

| Command | What it does |
|---|---|
| `make env` | create `.env` with random local secrets (never overwrites) |
| `make install` | Python venv (backend + pipeline, editable), npm packages, Playwright Chromium |
| `make up` / `make down` | local stack on http://localhost:8080 (Mailpit on :8025) |
| `make migrate` | `alembic upgrade head` + `sync-permissions` inside the api container |
| `make lint`, `make typecheck`, `make test` | what CI runs (no database needed) |
| `make test-db` | backend tests including live PostGIS checks (`alembic check`, audit trigger) |
| `make e2e` | Playwright smoke test over every route |
| `.venv/bin/ppr sources --all` | list data sources, licences and blocked sources |

New migrations: `cd backend && ../.venv/bin/alembic revision --autogenerate -m "..."` against the running database, then review the file.

## Conventions enforced by tests

- Every geometry column has a GIST index; money columns are `Numeric`; no column may hold owner, applicant or buyer names.
- Every table appears in `docs/data-model.md`; the role matrix in `docs/permissions.md` equals `app/auth/permissions.py`.
- `config/sources.yaml`: blocked sources stay blocked; the planning source never requests applicant fields.
- Frontend: every entry in `src/lib/routes.ts` has a page, and every page shows the PSRA attribution.
