# Tasks

What is done and what is left. **Starting a new chat?** Read [CLAUDE.md](CLAUDE.md) (it loads CONVENTIONS.md), then [progress.md](progress.md), then this file. [goal.md](goal.md), [requirements.md](requirements.md), [architecture.md](architecture.md) and [design.md](design.md) give the background.

**Keep it current:** tick items as they land (with the commit or D-number), add new findings, and move finished work into the log in progress.md.

## Resume checklist

1. `git status`, then `git log --oneline -5`: the branch is `phase-5`. Check whether the last commits were pushed.
2. Start Docker Desktop, then run `make up` (http://localhost:8080; Mailpit on :8025). Check the migrations with `docker compose --env-file .env -f infra/docker-compose.yml exec db psql -U pprmap -d pprmap -c 'SELECT version_num FROM alembic_version'`, which should print `0019` (the api container signs in as `ppr_app`, which cannot read `alembic_version`). After pulling, run `make env` (adds the database role passwords an older `.env` lacks), then `make up` and `make migrate`.
3. Run the gates: `make lint && make typecheck && make test && make test-db`.
4. After frontend changes, rebuild the container: `docker compose --env-file .env -f infra/docker-compose.yml up -d --build frontend`. After pipeline changes, rebuild the worker the same way (`--build worker`): its image holds the pipeline code, only `backend/app` is mounted.

## Now

- [ ] **Owner:** review Phase 5, the P0 fixes (D-057) and the P1 fixes (D-058). Phases are reviewed at a STOP checkpoint before the next one starts.
- [ ] **Owner:** decide whether to push `phase-5` (7 commits ahead once the P2 commit lands) and merge it into `main`. A push to `main` deploys the Vercel preview.
- [ ] **Owner:** decide whether to re-run Nominatim for the ~19k non-exact properties whose addresses the P2 geocoding fixes touch (#34, #35, #49). See D-059 and the progress log of 2026-10-04.

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
- [x] P1 #8–#14 Security, operations and data rules: database roles (migration 0014), tile and password limits, medians under 5, hidden price bands (0609336, migration 0015)
- [x] P1 #15–#19, #21–#23 Wrong numbers and pipeline robustness: same street, 12-month hexes, school levels, repeat filings, alerts after geocoding, atomic enrich, one pipeline run at a time, re-keyed sales (88bfa0b, migrations 0016, 0017)
- [x] P1 #24–#33 UI: map filter panel, synced list, place search, results map, budgets, history paging, area charts, admin user search, save search (99e95a9)
- [x] P2 #34–#49 Edge cases and data quality: address key, geocoding rules, slugs, hover-card sales, area stats, alerts, config files, audit TRUNCATE, deploy defaults, logs, last admin (D-059, migrations 0018, 0019; 0019 also fixes enrich never finishing on real data since P1 #21)

## Bugs: P2 (edge cases, data quality)

- [x] **#34** "St Lower" is read as Saint, so 321 real exact matches are rejected. `geocode/rules.py:179`
- [x] **#35** A "No." prefix is stripped as if it were a unit, so those addresses can never be exact (0.2% exact vs 14% overall). `geocode/rules.py:22`
- [x] **#36** The address key merges different houses: "1 25" and "125" give the same key (10 real groups). `pipeline/src/ppr_pipeline/address.py:182`. Needs #23 first.
- [x] **#37** The address key drops letters with fadas, so one home becomes two properties (86 real groups). Same line as #36; needs #23 first.
- [x] **#38** Turning alerts on later sends the whole backlog. `backend/app/api/v1/saved_searches.py:209`
- [x] **#39** Some saved-search names (U+2028) make that search's alerts fail permanently. `saved_searches.py:84`
- [x] **#40** `/alerts/unsubscribe` returns 500 on a non-ASCII token. `alerts.py:100`
- [x] **#41** A YAML syntax error in config gives 500 instead of 503, and the file is re-read on every request. `backend/app/api/v1/tools.py:76`
- [x] **#42** The audit trigger doesn't block `TRUNCATE`. Migration 0001, line 30.
- [x] **#43** Missing security headers: no `X-Frame-Options` / `frame-ancestors`, so one-click admin actions could be clickjacked. `ENVIRONMENT` defaults to development, so a deploy that forgets it gets non-Secure cookies and dev secrets. `Caddyfile:28`, `backend/app/config.py:20`
- [x] **#44** Personal data in logs: raw IPs and query strings in the access log, emails in app logs. This contradicts the privacy page. `docker-compose.yml:50`
- [x] **#45** The last admin can close their own account, and two admins can demote each other at the same time, leaving no active admin. `me.py:161`
- [x] **#46** Hover cards' "Earlier" sales include duplicates and non-market sales, with no flags. `aggregate.py:239`
- [x] **#47** Suppressed properties are dropped from area stats, against D-052. Decide which is right, the code or the docs. `aggregate.py:51`
- [x] **#48** Area slugs lose accented letters: "Dún Laoghaire" becomes `d-n-laoghaire`. These are permanent URLs, so fix before launch. `pipeline/src/ppr_pipeline/boundaries.py:106`
- [x] **#49** `TRAILING_TOWN` cuts "Village"/"Town" off estate names ("5 The Village" becomes "5 The"). `geocode/rules.py:121`

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
- [ ] *(new, 2026-10-04, P1 work)* The test database shares the cluster's roles with the dev database: a test that changes a role (as `db-roles` does) changes it for the running stack. The test puts the password back; keep it that way, or give tests their own cluster.
- [ ] *(new, 2026-10-04, P1 work)* A retired property's public id (#23) stops working (404). Add a redirect table if outside links to property pages start to matter.
- [ ] *(new, 2026-10-04, P2 work)* Stored Nominatim answers are redone only for properties queued again: `ppr geocode` has no way to re-queue a subset without `--refresh` blanking every point. Add a `--recheck WHERE`-style option, or keep old points during `--refresh` (the item above).
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
- [ ] *(new, 2026-10-04)* The resume checklist's `alembic current` broke when the services got their own roles (P1 #8); fixed in this file, worth a `make db-version` target

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
