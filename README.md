# PPR Map (working name)

The Property Price Register, made usable: every residential sale in Ireland since 2010 on a map, with honest geocoding, sale history and vicinity context.

**Status:** Phase 1 (scaffold) is ready for review. Phase 0 research and plan are in `docs/`.

**Live preview:** https://priyansh-koli.github.io/ppr-map/ is the frontend as a static site, rebuilt on every push to `main` (D-034). It has no API or database yet, so it shows the page scaffold only.

## Quick start

Prerequisites: Python 3.12, Node 22 LTS, and Docker (Docker Desktop or OrbStack).

```bash
make env          # .env with random local secrets
make install      # Python venv + npm packages
make up           # PostGIS, Redis, API, Martin, Next.js, Caddy, Mailpit
make migrate      # schema + roles/permissions
open http://localhost:8080
```

`make test` runs the unit tests; `make test-db` adds the live-database checks.

## Layout

| Folder | Contents |
|---|---|
| `backend/` | FastAPI app, SQLAlchemy models, Alembic migrations, management CLI |
| `pipeline/` | `ppr` CLI for ingest, geocoding, enrichment and aggregates (Phase 2) |
| `frontend/` | Next.js App Router, Tailwind, MapLibre; one page per route in `src/lib/routes.ts` |
| `infra/` | Docker Compose, Caddy, Martin, Postgres init |
| `config/` | `sources.yaml` (data sources and licences), `rates.yaml` (calculator rates, Phase 5) |
| `docs/` | plan, decisions, data model, API, permissions, research |

| Doc | What's in it |
|---|---|
| [docs/research/ppr-data-profile.md](docs/research/ppr-data-profile.md) | what the real PPR file contains, verified 2026-09-26 |
| [docs/research/competitive-analysis.md](docs/research/competitive-analysis.md) | competitor review, reusable open data, how we beat them |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | system diagram, stack, data flow |
| [docs/data-model.md](docs/data-model.md) | tables, fields, indexes |
| [docs/api.md](docs/api.md) | `/api/v1` endpoints |
| [docs/permissions.md](docs/permissions.md) | roles, permission matrix, rate limits |
| [docs/external-services.md](docs/external-services.md) | every data source and service, with licence and env var |
| [docs/DECISIONS.md](docs/DECISIONS.md) | decision log |
| [docs/RISKS-AND-QUESTIONS.md](docs/RISKS-AND-QUESTIONS.md) | open questions and risks |

## Data attribution

Contains Residential Property Price Register data from the Property Services Regulatory Authority (www.propertypriceregister.ie). © PSRA. The data may contain errors and is not a property price index.
