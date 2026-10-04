# Tasks

What is done and what is left. **Starting a new chat?** Read [CLAUDE.md](CLAUDE.md) (it loads CONVENTIONS.md), then [progress.md](progress.md), then this file. [goal.md](goal.md), [requirements.md](requirements.md), [architecture.md](architecture.md) and [design.md](design.md) give the background.

**Keep it current:** tick items as they land (with the commit or D-number), add new findings, and move finished work into the log in progress.md.

## Resume checklist

1. `git status`, then `git log --oneline -5`: the branch is `phase-5`. Check whether the last commits were pushed.
2. Start Docker Desktop, then run `make up` (http://localhost:8080; Mailpit on :8025). Check the migrations with `docker compose --env-file .env -f infra/docker-compose.yml exec api alembic current`, which should print `0013 (head)`.
3. Run the gates: `make lint && make typecheck && make test && make test-db`.
4. After frontend changes, rebuild the container: `docker compose --env-file .env -f infra/docker-compose.yml up -d --build frontend`.

## Now

- [ ] **Owner:** review Phase 5 and the P0 fixes (D-057). Phases are reviewed at a STOP checkpoint before the next one starts.
- [ ] **Owner:** decide whether to push `phase-5` (2 commits ahead) and merge it into `main`. A push to `main` deploys the Vercel preview.
- [ ] Fix the P1 bugs, in groups: security and operations, then data rules, then UI.

## Done

- [x] Phases 0–5 (see progress.md)
- [x] P0 #1 Open redirect after sign-in: `/..//evil.com` (1cd2fac)
- [x] P0 #2 Hidden properties stayed in Martin's tile cache: `tilesVersion` (1cd2fac, migration 0013)
- [x] P0 #3 Towns placed on a house with the same name; existing data re-placed (1cd2fac, 5261ff8)
- [x] P0 #4 Price filters like `1e6` silently dropped (1cd2fac)
- [x] P0 #5 Sale counts and price changes wrong under filters (1cd2fac, migration 0012)
- [x] P0 #6 Property page 500 without a location (1cd2fac)
- [x] P0 #7 Aggregate truncated hover-card data mid-run (1cd2fac)
- [x] P1 #20 Aggregate locked area pages and hex tiles for its whole run: fixed by #7's single transaction

## Bugs: P1 (important)

### Security and operations
- [ ] **#8** The API, worker, scheduler and Martin all connect as the Postgres superuser. Any SQL injection would get `COPY … TO PROGRAM` and could wipe the audit log. Fix: least-privilege roles. `infra/docker-compose.yml:42`
- [ ] **#9** Tiles have no rate limit, and a junk query parameter bypasses Martin's cache (about 1.8 s of DB time per request). `infra/caddy/Caddyfile:5`
- [ ] **#10** Password re-checks (change password, delete account, admin role change) have no attempt limit. Each try costs a 64 MiB argon2 verify on a shared 4-thread pool. `backend/app/api/v1/me.py:124`
- [ ] **#11** `/properties` and the hover summary have no rate limit; `sort=-change` over a large box is expensive and open to anonymous users. `backend/app/api/v1/properties.py:89`

### Data rules (CONVENTIONS.md) broken
- [ ] **#12** The comparables median is shown for fewer than 5 sales, and can be based on fewer sales than the count shown. `backend/app/services/properties.py:115`
- [ ] **#13** Sale-cell and stack tiles publish a median for fewer than 5 sales. Reported by one agent, not re-checked. Migrations 0004, 0006.
- [ ] **#14** A hidden (n < 5) price band can be worked out by subtraction, because the total and the zero bands are both shown. `backend/app/services/areas.py:281`

### Wrong numbers
- [ ] **#15** The comparables "same street" flag is wrong for about 20% of properties: in "…, co clare" or "…, dublin 6" the town is treated as a street. Migration 0010, line 28.
- [ ] **#16** The "last 12 months" price hexes actually cover 13 months. `pipeline/src/ppr_pipeline/aggregate.py:190`
- [ ] **#17** Any school with "Scoil" in its name is typed as primary; community schools such as "Scoil Phobail" are post-primary. `pipeline/src/ppr_pipeline/enrich/pois.py:119`
- [ ] **#18** `tile_matching_sales` doesn't exclude the 1,193 duplicate filings, so list, search and alert counts don't match the area stats. Migration 0008 (now 0012).

### Pipeline robustness
- [ ] **#19** Alerts can permanently miss sales if "aggregate" runs before "geocode". `backend/app/services/alerts.py:35`
- [x] **#20** The aggregate locked area pages and hex tiles for its whole run (fixed with P0 #7)
- [ ] **#21** A failed enrich leaves every property with no vicinity values. `pipeline/src/ppr_pipeline/enrich/run.py:92`
- [ ] **#22** Nothing stops two pipeline runs at once; a double click on "Queue" in admin starts two, and they corrupt each other. `backend/app/jobs.py:69`, `frontend/src/components/admin/panels.tsx:204`
- [ ] **#23** Re-ingest never moves a sale to its new property (`ON CONFLICT` doesn't update `property_id`). Blocks #36–#37. `pipeline/src/ppr_pipeline/ppr/load.py:130`

### Broken UI features
- [ ] **#24** The location-precision select shows "Exact address only" when the filter is `routing_key`. `frontend/src/components/map/filter-panel.tsx:226`
- [ ] **#25** Stop and school distance filters are applied on the map but are invisible there and can't be removed. `filter-panel.tsx`
- [ ] **#26** A slow list response overwrites the "zoom in" state, so the list shows sales from a view the map has left. `map-explorer.tsx:254`
- [ ] **#27** Pressing Enter in place search right after typing picks a suggestion for the previous text. `place-search.tsx:114`
- [ ] **#28** With a distance filter, hovering result rows reloads every tile on the results map. `results-map.tsx:143`
- [ ] **#29** The account budget fields block the whole Details form for any amount that isn't a multiple of €10,000 (`step=10000`). `account/settings.tsx:100`
- [ ] **#30** History "Show more" skips entries after a Remove, and the button then never goes away. `account/history.tsx:34`
- [ ] **#31** Area charts plot sparse series by index, so missing periods are squeezed out and bridged. When every area period is suppressed, the chart shows only the Ireland line. `area/area-charts.tsx:120`
- [ ] **#32** Admin user search deletes `_` and `%`, so searching for `jane_doe@…` finds nothing. `backend/app/api/v1/admin.py:677`
- [ ] **#33** "Saved." sticks after saving a search, so the next search can't be saved without a reload. `search/save-search.tsx:27`

## Bugs: P2 (edge cases, data quality)

- [ ] **#34** "St Lower" is read as Saint, so 321 real exact matches are rejected. `geocode/rules.py:179`
- [ ] **#35** A "No." prefix is stripped as if it were a unit, so those addresses can never be exact (0.2% exact vs 14% overall). `geocode/rules.py:22`
- [ ] **#36** The address key merges different houses: "1 25" and "125" give the same key (10 real groups). `pipeline/src/ppr_pipeline/address.py:182`. Needs #23 first.
- [ ] **#37** The address key drops letters with fadas, so one home becomes two properties (86 real groups). Same line as #36; needs #23 first.
- [ ] **#38** Turning alerts on later sends the whole backlog. `backend/app/api/v1/saved_searches.py:209`
- [ ] **#39** Some saved-search names (U+2028) make that search's alerts fail permanently. `saved_searches.py:84`
- [ ] **#40** `/alerts/unsubscribe` returns 500 on a non-ASCII token. `alerts.py:100`
- [ ] **#41** A YAML syntax error in config gives 500 instead of 503, and the file is re-read on every request. `backend/app/api/v1/tools.py:76`
- [ ] **#42** The audit trigger doesn't block `TRUNCATE`. Migration 0001, line 30.
- [ ] **#43** Missing security headers: no `X-Frame-Options` / `frame-ancestors`, so one-click admin actions could be clickjacked. `ENVIRONMENT` defaults to development, so a deploy that forgets it gets non-Secure cookies and dev secrets. `Caddyfile:28`, `backend/app/config.py:20`
- [ ] **#44** Personal data in logs: raw IPs and query strings in the access log, emails in app logs. This contradicts the privacy page. `docker-compose.yml:50`
- [ ] **#45** The last admin can close their own account, and two admins can demote each other at the same time, leaving no active admin. `me.py:161`
- [ ] **#46** Hover cards' "Earlier" sales include duplicates and non-market sales, with no flags. `aggregate.py:239`
- [ ] **#47** Suppressed properties are dropped from area stats, against D-052. Decide which is right, the code or the docs. `aggregate.py:51`
- [ ] **#48** Area slugs lose accented letters: "Dún Laoghaire" becomes `d-n-laoghaire`. These are permanent URLs, so fix before launch. `pipeline/src/ppr_pipeline/boundaries.py:106`
- [ ] **#49** `TRAILING_TOWN` cuts "Village"/"Town" off estate names ("5 The Village" becomes "5 The"). `geocode/rules.py:121`

## Bugs: P3 (hardening, polish, docs)

**Backend**
- [ ] Stale roles can stay in the session cache for up to 60 s
- [ ] Forgot-password timing hints whether an account exists
- [ ] Spam or phishing can be sent through the report and registration emails
- [ ] IPv6 clients can rotate addresses past the per-IP rate limits
- [ ] Two partial `PATCH /me` calls can store `budgetMin > budgetMax`
- [ ] The "account closed" email can give the wrong date
- [ ] Stamp duty isn't rounded down to the euro (needs a check against Revenue)
- [ ] Estimates use float maths
- [ ] `area=ireland` matches nothing
- [ ] One-letter autocomplete queries skip the trigram index

**Pipeline**
- [ ] Calibration and the estimate put gaps of exactly 36 or 84 months in different bands
- [ ] Estimates can start from sales under €10k
- [ ] Ireland's merged shape is never refreshed
- [ ] Vicinity values aren't checked against the property's current confidence
- [ ] The parser peaks at 1.2 GB of RAM
- [ ] Refilings that differ only in punctuation aren't flagged as duplicates
- [ ] "Apt 3.10" splits into the wrong unit and house number
- [ ] `--refresh --limit` leaves stale area ids
- [ ] Strict cp1252 decoding fails the whole run on one bad byte
- [ ] *(new, 2026-10-04)* `geocode --refresh` blanks every point at the start, so the map and property pages have no locations for the whole 1–2 hour run. Keep the old point until the new one is written.
- [ ] *(new, 2026-10-04)* An address that is only a town name ("Athea, Co Limerick") can still land on a house with that name (10 left; D-057)

**DB**
- [ ] `ed_id`, `townland_id` and `settlement_id` have no indexes
- [ ] PARALLEL SAFE functions call PARALLEL UNSAFE helpers
- [ ] Six env vars are missing from `.env.example`
- [ ] Weak fallback database and Nominatim credentials

**Frontend**
- [ ] Inverted price or date ranges give a misleading error
- [ ] The heading stays "Searching…" after a failure
- [ ] Clicking a stack at high zoom zooms out
- [ ] Hovering before the map loads floods the console
- [ ] Map errors never clear
- [ ] Selects show the wrong option for valid but unlisted URL values
- [ ] Rounding at unit boundaries ("€1000k", "1000 m")
- [ ] Hex mode still says "Only sales in…" though place filters don't apply
- [ ] The header still shows you signed in after a password reset
- [ ] History sections have no accessible name (the heading id contains a space)
- [ ] Admin pagers vanish when the current page empties
- [ ] A failed ingest-run detail shows "Loading…" forever
- [ ] The static preview leaves the calculators blank
- [ ] The ingest "Kind" filter is missing kinds
- [ ] The wishlist note keeps showing "Save note" after a save when it has a trailing space

**Docs**
- [ ] `/me/api-keys` is documented but has no route

## Features not built yet

These come from the brief and the plan; see requirements.md.

- [ ] Planning applications near a property, with applicant fields stripped (D-017)
- [ ] Environment panel: radon, noise, zoning (D-018)
- [ ] Indicative gross yield from RTB rents; routing-key medians next to the CSO's (D-019)
- [ ] Crime on area pages at Garda-station level (D-012); BER at county level (D-013)
- [ ] Admin merge and split of properties (D-052); dedupe candidate queue (D-030)
- [ ] Pro tier: API keys and research access
- [ ] Google sign-in (deferred)

## Before a public launch

- [ ] Owner answers Q-01, Q-02, Q-03, Q-04 and Q-07 ([docs/RISKS-AND-QUESTIONS.md](docs/RISKS-AND-QUESTIONS.md))
- [ ] Production host for the data server, an EU email provider and object storage (Q-04; anything paid needs approval)
- [ ] GDPR legitimate-interests assessment and DPIA (R-07); ODbL handling in exports (R-06); final privacy and terms pages
- [ ] A commercial Vercel plan or another frontend host (the Hobby plan is non-commercial, D-056)
- [ ] All P0–P2 bugs closed
