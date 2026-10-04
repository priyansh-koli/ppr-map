# PPR Map (working name)

The Property Price Register, made usable: every residential sale in Ireland since 2010 on a map, with honest geocoding, sale history and vicinity context.

**Status:** Phase 5 (search, area pages, saved searches and alerts, calculators, admin, estimate and comparables) is complete and awaiting review; the P0 bugs from its review are fixed (D-057). See [progress.md](progress.md) and [task.md](task.md).

**Live preview:** https://ppr-map.vercel.app/ is the frontend as a static site on Vercel, deployed from `main` (D-056; it replaced the GitHub Pages preview of D-034). It has no API or database yet, so it shows the page scaffold only.

## Quick start

Prerequisites: Python 3.12, Node 22 LTS, and Docker (Docker Desktop or OrbStack).

```bash
make env          # .env with random local secrets
make install      # Python venv + npm packages
make up           # PostGIS, Redis, API, Martin, Next.js, Caddy, Mailpit
make migrate      # schema + roles/permissions
open http://localhost:8080
```

In development no email leaves your computer: verification, password reset and alert emails are caught by Mailpit at http://localhost:8025, whatever address you register with.

To fill the map with real data (first run: about 2 hours, mostly geocoding):

```bash
.venv/bin/ppr ingest tailte_boundaries   # counties, EDs, Small Areas, townlands, towns
make geocoder     # self-hosted Nominatim (first start imports Ireland; Docker memory >= 12 GB)
make pipeline     # PPR ingest, street gazetteer, geocode, enrich, aggregate
make basemap      # the Ireland basemap, terrain, fonts and sprites (~650 MB)
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
| [goal.md](goal.md), [requirements.md](requirements.md) | the final goal and the PRD, with each feature's status |
| [architecture.md](architecture.md), [design.md](design.md) | structure, stack and integrations at a glance; the visual style |
| [progress.md](progress.md), [task.md](task.md) | where the project stands; what is done and what is next |
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
