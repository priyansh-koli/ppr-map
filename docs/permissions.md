# Roles and permissions

- **Source of truth in code:** `backend/app/auth/permissions.py`. The idempotent command `python -m app.cli sync-permissions` (run by `make migrate`) writes `role`, `permission` and `role_permission` from that file. A unit test fails if this document and the code disagree.
- **Enforcement:** FastAPI dependencies, for example `require("wishlist:write")`. The frontend only hides UI; it never enforces anything.
- **Roles are additive:** `user` includes everything `anonymous` has, `pro` includes everything `user` has, and `admin` is separate. An admin also holds `user`.

## Permission codes

| Code | Meaning |
|---|---|
| `map:read` | tiles, property summary and detail, comparables |
| `search:read` | search and autocomplete |
| `area:read` | area pages and stats |
| `tools:use` | calculators |
| `report:create` | submit a correction or removal request |
| `wishlist:write` | CRUD on own wishlist and notes; compare |
| `history:write` | own view and search history (subject to the `history_enabled` setting) |
| `saved_search:write` | CRUD on own saved searches |
| `alert:receive` | alerts sent for saved searches (also needs a verified email) |
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
| auth: login | 10 per 15 min per IP+email | | |
| auth: register / forgot-password | 5 / h / IP | | |

## Rules outside the matrix

- **Ownership:** every `/me/*` resource is filtered by `user_id = current_user.id` in the query. Tests cover cross-user access and must return 404, not 403.
- **Admin role changes** need a second confirmation (re-entering the password) and write an `audit_log` entry. An admin can't remove their own admin role if they are the last admin.
- **Browser geolocation ("near me")** is only requested after the user clicks a "Use my location" button, which comes with a sentence explaining why and that the location is not stored. It is never requested on page load. The coordinates are used client-side to build a `near=` filter. They are not written to search history (the history stores "near my location" instead).
