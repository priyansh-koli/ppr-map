# Roles and permissions

- **Source of truth in code:** `backend/app/auth/permissions.py`. The idempotent command `python -m app.cli sync-permissions` (run by `make migrate`) writes `role`, `permission` and `role_permission` from that file. A unit test fails if this document and the code disagree.
- **Enforcement:** FastAPI dependencies, for example `require("wishlist:write")`. The frontend only hides UI; it never enforces anything.
- **Roles are additive:** `user` includes everything `anonymous` has, `pro` includes everything `user` has, and `admin` is separate. An admin also holds `user`.

## Permission codes

| Code | Meaning |
|---|---|
| `map:read` | tiles, property summary and detail, comparables, the index estimate |
| `search:read` | search and autocomplete |
| `area:read` | area pages and stats |
| `tools:use` | calculators |
| `report:create` | submit a correction or removal request |
| `wishlist:write` | CRUD on own wishlist and notes; compare |
| `history:write` | own view and search history (subject to the `history_enabled` setting) |
| `saved_search:write` | CRUD on own saved searches |
| `alert:receive` | alerts sent for saved searches (also needs a verified email; the alert job checks both, D-050) |
| `export:csv` | CSV export of search results, capped by role |
| `api_key:manage` | create and revoke own API keys |
| `api:access` | use the API with a key |
| `analytics:advanced` | advanced analytics views (future) |
| `admin:ingest` | view and trigger ingest runs |
| `admin:geocode` | correct geocodes; merge and split properties |
| `admin:removals` | handle removal and correction requests |
| `admin:users` | view users; change roles; deactivate |
| `admin:audit` | read the audit log |

## Matrix

| Permission | Anonymous | User | Pro (future) | Admin |
|---|:-:|:-:|:-:|:-:|
| map:read, search:read, area:read, tools:use, report:create | ✅ (rate-limited) | ✅ | ✅ | ✅ |
| wishlist:write, history:write, saved_search:write | – | ✅ | ✅ | ✅ |
| alert:receive | – | ✅ (verified email) | ✅ | ✅ |
| export:csv | – | ✅ 500 rows / export, 10 exports / day | ✅ 50,000 rows, 100 / day | ✅ |
| api_key:manage, api:access | – | – | ✅ 10k requests / day | – |
| analytics:advanced | – | – | ✅ | ✅ |
| admin:ingest, admin:geocode, admin:removals, admin:users, admin:audit | – | – | – | ✅ |

## Rate limits (initial values, tune after load testing)

| Scope | Anonymous (per IP) | User | Pro |
|---|---|---|---|
| search | 60 / min | 300 / min | 600 / min |
| property summary (hover) | 300 / min | 600 / min | 1,200 / min |
| autocomplete | 120 / min | 300 / min | 600 / min |
| auth: login | 10 per 15 min per IP+email (a successful sign-in resets it); 100 per 15 min per IP | | |
| auth: register / forgot-password | 5 / h / IP | | |
| password re-check (change password, close account, admin role change) | | 5 wrong per 15 min per account (a right one resets it) | |
| list view (`/properties`) | shares the search limit | | |
| map tiles (Caddy, per IP) | 1,200 / min; 300 / min for tiles with filters | | |

Map tiles are served by Martin through Caddy, which applies the tile limits (the `rate_limit` plugin, `infra/caddy/Dockerfile`) and refuses any query parameter that is not a map filter or `v`: Martin caches a tile by its whole URL, so a junk parameter would make every request a fresh render. Martin renders at most 8 tiles at once (`pool_size`).

## Database roles (migration 0014)

No service connects as the Postgres superuser. `POSTGRES_USER` owns the account tables and the audit log, and runs migrations (`make migrate`).

| Role | Used by | Can |
|---|---|---|
| `ppr_app` | API, scheduler | read every table; write the account tables; only add to `audit_log`; update `property` and `property_summary` and add `geocode_attempt` rows (admin hide and move) |
| `ppr_pipeline` | worker (pipeline steps, alerts, housekeeping) | everything `ppr_app` can, and own the data tables through `ppr_data` (TRUNCATE, VACUUM, ANALYZE, scratch tables) |
| `ppr_tiles` | Martin | read the data tables; nothing about accounts |

None of them can run `COPY ... TO PROGRAM`, change or empty the audit log, or alter the account tables. Passwords come from `APP_DB_PASSWORD`, `PIPELINE_DB_PASSWORD` and `TILES_DB_PASSWORD` in `.env`; `make migrate` sets them (`python -m app.cli db-roles`). A test fails if a new table is not given to one side: account tables in `ACCOUNT_TABLES` (`backend/tests/test_migrations.py`), every other table owned by `ppr_data`.

## Rules outside the matrix

- **Ownership:** every `/me/*` resource is filtered by `user_id = current_user.id` in the query. Tests cover cross-user access and must return 404, not 403.
- **Admin role changes** need a second confirmation (re-entering the password) and write an `audit_log` entry. An admin can't remove their own admin role if they are the last admin.
- **Browser geolocation ("near me")** is only requested after the user clicks a "Use my location" button, which comes with a sentence explaining why and that the location is not stored. It is never requested on page load. The coordinates are used client-side to build a `near=` filter. They are not written to search history (the history stores "near my location" instead). Saving such a search keeps the point, because its alerts need it; the save form says so.
