# Progress

Where the project stands and how it got here. **Update the snapshot and add a log entry at the end of every working session.** Open work lives in [task.md](task.md).

## Snapshot (2026-10-04)

| | |
|---|---|
| Phase | **5 complete, awaiting the owner's review** (search, area pages, saved searches and alerts, calculators, admin, estimate and comparables). P0 and P1 bugs from the review are fixed (D-057, D-058). |
| Branch | `phase-5`, 6 commits ahead of `origin/phase-5` (not pushed). `origin/main` = `origin/phase-5` before today's commits. |
| Live preview | https://ppr-map.vercel.app/ (static frontend only, no API; deploys from `main`) |
| Local data | Data version `2026-09-18.r35.a39`. Migrations at head `0017`. Services sign in as `ppr_app`, `ppr_pipeline` and `ppr_tiles`. |
| Dataset | 807,724 sales (2010-01-01 to 2026-09-18) on 728,462 properties. 73,808 areas. 65,789 POIs. 638,778 gazetteer features. |
| Geocoding | exact 100,981 (13.9%) · street 314,680 (43.2%) · locality 249,473 (34.2%) · routing key 26,625 (3.7%) · county 36,703 (5.0%) |
| Quality gates | lint, mypy strict, tsc, and 408 tests pass (backend 141, pipeline 119, frontend 148); Playwright: 60 route checks, 20 against the live stack |
| Next step | Owner reviews Phase 5 and the P0 and P1 fixes; then fix P2 bugs ([task.md](task.md)) |

## Phases

| Phase | What | Dates | Decisions |
|---|---|---|---|
| 0 | Research, data profile, architecture, open questions | 2026-09-26 (reviewed same day: Q-09 no, Q-10 yes) | D-001 to D-033 |
| 1 | Scaffold: FastAPI, Next.js, PostGIS in Docker, CI | 2026-09-26 | D-025 to D-029 |
| 2 | Data pipeline: PPR ingest, normalisation, dedupe, bulk flags, boundaries, geocoding cascade, enrichment, aggregates | 2026-09-26 to 27 | D-030 to D-037 |
| 3 | Tile functions, basemap, map explorer, property page, home page, API | 2026-09-27 | D-038 to D-040 |
| 4 | Accounts: register, sign in, reset, settings, wishlist and compare, history, export, deletion | 2026-09-27 | D-041, D-042 |
| — | Visual design, map legibility, relief and 3D | 2026-09-28 | D-043 to D-045 |
| — | Local street gazetteer (geocoding improvement) | 2026-09-30 | D-046 |
| 5 | Search, calculators, area pages, saved searches and alerts, jobs, removal requests and admin, estimate and comparables | 2026-09-30 to 10-01 | D-047 to D-053 |
| — | Map tile planning fix, `/sources` page, Vercel preview | 2026-10-01 to 03 | D-054 to D-056 |
| — | Phase 5 bug review (about 85 bugs found); P0 and P1 fixed | 2026-10-04 | D-057, D-058 |

## Log

### 2026-10-04: P1 bug fixes
- Fixed all 25 P1 bugs in three commits (security and data rules, wrong numbers and pipeline, UI), each with a regression test that fails without it. Migrations 0014 to 0017; D-058 has the details.
- The services no longer sign in as the Postgres superuser (`ppr_app`, `ppr_pipeline`, `ppr_tiles`). Caddy is now built with a rate-limit plugin and refuses unknown tile parameters.
- Found while testing: enrich had never been able to run in the worker (GDAL temp files), and the worker image still held old pipeline code. Its failed run emptied the vicinity table on dev, which was #21 itself. Both are fixed and the table is rebuilt (415,657 homes).
- A forced PPR reload moved 2,187 sales off properties whose keys had drifted from the current address rules, and retired 1,906 emptied properties. 1,900 of the new ones kept their position; 8 were geocoded (Nominatim started for that, then stopped). The aggregate was then rebuilt.
- Also fixed an e2e locator that the "Sales nearby" heading made ambiguous.

### 2026-10-04: P0 bug fixes and project handover files
- Seven agents reviewed the code and found about 85 bugs, sorted P0 to P3 (the list is in [task.md](task.md)).
- Fixed all seven P0 bugs, each with a regression test that fails on the old code:
  - the open redirect after sign-in;
  - `1e6` price filters silently dropped;
  - wrong sale counts and price changes under filters (migration 0012);
  - a 500 on the property page when a property has no location;
  - hidden properties staying in Martin's tile cache (`tilesVersion`, migration 0013);
  - towns placed on a house with the same name (1,979 properties re-placed);
  - hover cards returning 404 during the aggregate run (now one transaction; also fixes P1 #20).
- Ran on the dev data: one geocode run (5 min, no Nominatim needed) and four aggregate runs (about 130 s each). The aggregate tables now hold steady at about twice their live size (`property_summary` 1.6 GB).
- Added `goal.md`, `requirements.md`, `architecture.md`, `design.md`, `progress.md` and `task.md`.

### 2026-10-03
- Moved the public preview from GitHub Pages to Vercel. Old addresses redirect. Hashed assets are cached for a year (D-056).

### 2026-10-01 to 10-02
- Phase 5 marked complete.
- Area-filtered tiles no longer stall (force custom plans, D-054).
- Added the `/sources` methodology page (D-055).
- Fixes to the Pages preview and Mailpit.

### 2026-09-30
- Local street gazetteer from OSM, official places and DHLGH estates (D-046).
- Phase 5 features: search, calculators, area pages, saved searches with alerts and CSV export, RQ worker and scheduler, removal requests and admin.

### 2026-09-28 to 09-29
- New visual design (D-043).
- Map legibility and selection (D-044).
- Relief, buildings and 3D (D-045).
- New home headline.

### 2026-09-26 to 09-27
- Phases 0 to 4 built and reviewed.
