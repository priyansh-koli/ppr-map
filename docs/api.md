# API (Phase 0 draft)

- REST, all under `/api/v1`.
- OpenAPI is served at `/api/v1/openapi.json`, with docs at `/api/v1/docs`.
- JSON is camelCase on the wire and snake_case in Python. Pydantic aliases handle the conversion.
- Errors use the RFC 9457 problem+json format: `{type, title, status, detail, errors?}`.
- Auth is a session cookie (D-008), or `Authorization: Bearer <api key>` for Pro.
- State-changing requests need the `X-CSRF-Token` header to match the `csrf` cookie.
- Permission codes are listed in [permissions.md](permissions.md). Rate limits apply per IP for anonymous callers and per user otherwise, using a Redis sliding window.

## Common types

- **`SearchFilter`** (**built in Phase 5**, D-047): the same query parameters on `/tiles/sales`, `/properties`, `/search` and in saved searches, parsed by one SQL function (`tile_matching_sales`), so the map, the list and search results cannot disagree. Lists are one comma-separated parameter. Anything the API cannot use is a 422; the tile server ignores it and draws the default map.
  - `county=cork,kerry`; `area=<area slugs>` (a county, town, ED, townland or Small Area); `routingKey=D08,A63` (a Dublin routing key also matches addresses filed with only the postal district, "Dublin 8")
  - `near=lat,lng` and `radiusM` (100 to 20,000; default 1,000)
  - `priceMin`, `priceMax`, `dateFrom`, `dateTo`
  - `type=new|second_hand|any`
  - `excludeNonMarket=true` (default), `excludeBulk=true` (default), `vat=exclusive|inclusive|any`
  - `maxStopM`, `maxSchoolM` (50 to 10,000): straight-line distance to the nearest stop or school, known only for exact and street locations (D-036), so they also leave out everything placed less precisely
  - `minConfidence=exact|street|locality|routing_key|county` (default `locality`)
- **Sort** (`/search`, `/properties`): `-date` (default), `date`, `-price`, `price`, `-change` (biggest rise since the previous plain market sale), `change`.
- **`Confidence`:** `exact | street | locality | routing_key | county | unmatched`.
- **`Sourced<T>`:** `{ value: T, source: string, asOf: date, note?: string }`. Every enriched value uses this shape.

## Meta
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness: DB and Redis ping |
| GET | `/meta` | **Built (Phase 3).** `{dataVersion, pprMaxSaleDate, provisionalFrom, lastIngestAt}`, used by the status pill in the header |
| GET | `/sources` | licences and attributions for each data source |

## Stats

| Method | Path | Notes |
|---|---|---|
| GET | `/stats/overview` | the home page's national overview (D-043): `totalSales`, `totalProperties`, `firstSaleDate`; `monthly` (the last 24 months of market sales, with `provisional`); `counties` (each county's latest complete 12 months, `windowStart` to `windowEnd`: `sales` and `medianPriceEur`, null when n < 5, plus a point inside the county for the map). From `area_stats`; held in memory per data version. |

## Auth

**Built in Phase 4** (D-041), plus `GET /auth/policies` for the terms and privacy versions that registration accepts. Every POST, PUT, PATCH and DELETE needs the `X-CSRF-Token` header.
| Method | Path | Body / notes | Limit |
|---|---|---|---|
| POST | `/auth/register` | `{fullName, email, password, age18Plus: true, acceptTerms: true, termsVersion, privacyVersion, profile?: {userType?, counties?, budgetMin?, budgetMax?, propertyInterest?}, marketingOptIn?: false}`. Always answers 202 so it doesn't reveal whether an account exists. | 5/h/IP |
| POST | `/auth/login` | `{email, password}` → sets the session cookie | 10/15 min per IP+email (reset by a successful sign-in), 100/15 min per IP |
| POST | `/auth/logout` | revokes the current session; 204 and clears the cookie even if the session had already ended | |
| POST | `/auth/logout-all` | revokes all of the user's sessions | |
| POST | `/auth/verify-email` | `{token}` | |
| POST | `/auth/resend-verification` | | 3/h |
| POST | `/auth/forgot-password` | `{email}` → always 202 | 5/h/IP |
| POST | `/auth/reset-password` | `{token, password}` → revokes all sessions | |
| ~~POST~~ | ~~`/auth/refresh`~~ | dropped (D-008) | |

## Me

**Built in Phase 4**, except saved searches (Phase 5) and search history (Phase 5, D-047). `/me/export` is a direct JSON download, not a job. `POST /me/history/views {propertyId}` records a property page visit. `POST /me/history/searches {query, label?}` records a search the user settled on: the filters are validated and stored as URL parameters; a repeat moves to the top; the coordinates of "my location" are replaced by `my-location` (the client marks them with `nearSource=geolocation`). Both history lists are pages (`page`, `pageSize` ≤ 100) of `{items, total, page, pageSize}`, newest first, 12 months at most; search history keeps the newest 200.
| Method | Path | Notes |
|---|---|---|
| GET/PATCH | `/me` | profile, preferences, `historyEnabled`, notification settings |
| POST | `/me/password` | `{currentPassword, newPassword}`; signs out every other session and voids open reset links |
| DELETE | `/me` | needs the password; soft-deletes the account, hard-purges after 30 days, and revokes sessions |
| GET | `/me/export` | everything stored about the account (GDPR access request), as a JSON download |
| GET/POST | `/me/wishlist` · PATCH/DELETE `/me/wishlist/{id}` | add a property or area with a note (201; 200 with the existing item if already saved). At most 500 items. |
| GET | `/me/wishlist/compare?ids=a,b,c,d` | up to 4 items |
| GET/DELETE | `/me/history/views` · DELETE `/me/history/views/{id}` | |
| GET/DELETE | `/me/history/searches` · DELETE `/me/history/searches/{id}` | |
| GET/POST | `/me/saved-searches` · GET/PATCH/DELETE `/me/saved-searches/{id}` | **Built (Phase 5, D-050).** `{name, query, alertFrequency: off | on_data_update | weekly}`; `query` is the search's URL parameters, validated like `/search`. At most 50 per user. `alertsActive` is false until the email is verified. Changing `query` restarts its alerts from the register as it is. |
| GET | `/me/saved-searches/{id}/export.csv` | **Built (Phase 5).** The matches in the search's order, up to 500 rows for a user (50,000 for pro and admin), 10 exports a day (100). Leading `#` lines carry the PSRA and ODbL notices (R-06); a cell starting with `= + - @` is quoted against spreadsheet formulas. |
| POST | `/alerts/unsubscribe` | **Built (Phase 5).** `{token}` from an alert email's link switches that alert off without signing in; the token is an HMAC of the saved search's id. |
| GET/POST/DELETE | `/me/api-keys` | Pro only |

## Map
| Method | Path | Notes |
|---|---|---|
| GET | `/tiles/sales/{z}/{x}/{y}?{SearchFilter subset}` | **Built (Phase 3).** Martin calling `sales_tiles` (migration 0004). Below z14: layer `cells` (`n`, `median`). From z14: layer `sales` (points for exact and street locations) and layer `stacks` (`n`, `median`, `confidence`: every coarser location, one feature each). Filters: the whole `SearchFilter` (Phase 5, D-047); anything unparseable falls back to the default (D-038). |
| GET | `/tiles/price-hex/{z}/{x}/{y}?window=&segment=` | **Built (Phase 3).** Layer `hexes` (`n`, `median`, `suppressed`); H3 r6 up to z7, r7 for z8-9, r8 from z10 (D-009). |
| GET | `/tiles/planning/{z}/{x}/{y}.pbf?since=&minUnits=` | planning application points layer |
| GET | `/tiles/environment/{kind}/{z}/{x}/{y}.pbf` | radon, noise and zoning (GZT) overlays |
| GET | `/tiles/pois/{z}/{x}/{y}.pbf?types=` | layer toggles for schools, transport and amenities |

The `sales` point layer carries: `id`, `price`, `date` (yyyymmdd int), `isNew`, `nfmp`, `vatx`, `bulk`, `confidence`, `nSales`.

## Properties
| Method | Path | Notes |
|---|---|---|
| GET | `/properties?bbox=w,s,e,n&{SearchFilter}&sort=&page=&pageSize=` | **Built (Phase 3; full filters and `change` in Phase 5).** The list synced with the map: `/search` limited to the box. A box wider than 0.6° or taller than 0.4° is refused (422, "Zoom in to list sales"). Each item has `change` (`previousDate`, `previousPriceEur`, `changePct`) when its latest and previous sales are both plain market sales. |
| GET | `/properties/{id}/summary` | **Built (Phase 3).** The hover card. Reads only Redis (`summary:{id}:{dataVersion}`) or `property_summary`: 10 ms uncached, 3 ms cached on the dev stack. |
| GET | `/properties/{id}` | **Built (Phase 3).** Every sale, location precision and method, areas, vicinity, the most local 12-month median series, and caveats. The full Eircode is not returned, only its routing key. |
| GET | `/properties/{id}/comparables?radiusM=500&months=24&limit=20` | **Built (Phase 5, D-053).** Market sales of other homes within `radiusM` (100 to 2,000) in the last `months` (6 to 60) of the register, the latest per home, same street or estate first (`sameStreet`), then nearest (`distanceM`); `total` and `medianEur` (VAT-inclusive prices only) cover all of them. Only between `exact` and `street` points: otherwise `available: false` with a `reason`. |
| GET | `/properties/{id}/planning?radiusM=250&years=5` | planning at this address plus nearby; no applicant fields exist to return |
| GET | `/properties/{id}/estimate` | **Built (Phase 5, D-020, D-053).** `{eligible, lowEur, midEur, highEur, basedOn {date, priceEur}, series {key, label, source}, indexMonth, indexChangePct, calibration {yearsBetween, pairs, pooled, lowPct, medianPct, highPct}, method}`; an ineligible home answers 200 with `eligible: false` and a `reason` (404 only for an unknown id). |
| POST | `/reports` | **Built (Phase 5, D-052).** A public correction or removal request `{propertyId?, address, requestType, relationship, reason?, email?}` → `removal_request`, answered 202 with a reference (`R-…`); 5 an hour per IP; a hidden `website` field traps bots (answered as accepted, nothing stored); an acknowledgement is emailed if an address is given. |

Summary shape (draft):
```json
{
  "id": "p_8Kx2",
  "address": "36 Shanowen Avenue, Santry, Dublin 9",
  "confidence": "exact",
  "latestSale": {"date": "2025-03-14", "priceEur": 465000, "isNew": false,
                  "flags": {"notFullMarketPrice": false, "vatExclusive": false, "bulk": false}},
  "previousSales": [{"date": "2014-06-02", "priceEur": 240000}],
  "vicinity": {
    "nearestStop": {"value": {"name": "…", "type": "bus_stop", "distanceM": 180}, "source": "NTA GTFS", "asOf": "2026-09-20"},
    "nearestPrimarySchool": {"value": {"name": "…", "distanceM": 650}, "source": "Dept of Education", "asOf": "…"},
    "shopsWithin1km": {"value": 14, "source": "OpenStreetMap", "asOf": "…"},
    "deprivation": {"value": "Marginally below average", "source": "Pobal HP 2022 (Electoral Division)", "asOf": "2022"},
    "flood": {"value": null, "note": "Check OPW flood maps", "link": "https://www.floodinfo.ie/map/floodmaps/"}
  },
  "area": {"name": "Dublin 9", "median12m": 455000, "change12mPct": 6.1, "n": 812, "provisional": true},
  "dataVersion": "2026-09-18"
}
```
(The values above illustrate the shape only. They are not real figures.)

## Search and geocode
| Method | Path | Notes |
|---|---|---|
| GET | `/search?{SearchFilter}&bbox=&sort=&page=&pageSize=` | **Built (Phase 5, D-047).** `{items, total, page, pageSize, bbox, query, places}`: each property once, with its latest matching sale; `bbox` covers every match; `query` is the search as URL parameters; `places` names the `area` slugs. 60/min anonymous (per IP hash), 300/min signed in. On the full data: 0.1 to 0.5 s for a place, 1.3 s for all of Ireland, 2.1 s sorted by change. |
| GET | `/geocode/autocomplete?q=&limit=` | **Built (Phase 5).** Counties, towns, EDs and townlands by name; routing keys and Dublin districts ("d8", "Dublin 6W"); addresses where every word matches (`rd` means road). Our own tables only (D-006). 2 to 100 characters, at most 10 answers; 120/min anonymous, 300/min signed in. |

## Areas

**Built in Phase 5** (D-049). Slugs: `ireland`, a county's code (`dublin`), `sa-<code>` for Small Areas, and name plus a short hash for towns, EDs and townlands. Answers are held in memory per data version.

| Method | Path | Notes |
|---|---|---|
| GET | `/areas/{slug}` | `kind`, `name`, `nameGa`, `parents` (nearest first, ending with Ireland), `bbox`, simplified GeoJSON `geometry`, `headline` and `national` (the latest complete 12 months, or the latest complete year for Small Areas and townlands: `n`, median, p25, p75, `changePct` against a year earlier), `attributes` (Pobal deprivation for an ED; a Small Area shows its ED's, labelled so), `children` (a county's towns, Ireland's counties, an ED's Small Areas, busiest first), `periodKinds`, `pointBased` (Small Areas and EDs count only exact and street points), `priceIndex` (the CSO RPPI change over its latest 12 months for the area's region, D-053; Ireland's is the national all-properties series; null until the index is loaded) |
| GET | `/areas/{slug}/stats?periodKind=&segment=` | the series from `area_stats` (`month`, `quarter`, `year`, `rolling_12m`; Small Areas and townlands only `quarter` and `year`, otherwise 422) with Ireland's for the same periods; suppressed (n < 5) and provisional flags; rolling windows start in Dec 2010, the first with 12 months of register |
| GET | `/areas/{slug}/distribution` | market sales over the latest complete 12 months in 15 price bands (€0 to €1.5m+), a band's count left out (null) below 5 sales, with Ireland's share per band |

## Tools

**Built in Phase 5** (D-048). Rates come from `config/rates.yaml`, each with its official source and the date it was checked; a missing value is a 503, never a guess. Every answer carries `rulesVersion`, `sources` (name, url, verifiedOn) and a "not financial advice" note.

| Method | Path | Notes |
|---|---|---|
| GET | `/tools/rules` | the rules in use, their sources and check dates |
| GET | `/tools/stamp-duty?price=&isNew=&vatInclusive=true&qualifyingApartment=false` | residential rates from 2 Oct 2024 (1% to €1m, 2% to €1.5m, 6% above), band by band; a new home's VAT-inclusive price has VAT taken out first (13.5%, or 9% for a qualifying apartment from 8 Oct 2025) |
| GET | `/tools/affordability?grossIncome=&secondIncome=&buyer=first_time_buyer|second_and_subsequent|buy_to_let&deposit=&termYears=30&ratePct=` | the lower of the income limit (LTI 4 or 3.5 times gross income, none for buy-to-let) plus the deposit, and the deposit limit (LTV 90%, or 70% for buy-to-let); `limitedBy` says which; a monthly repayment only for a rate the user enters; `firstTimeBuyer=true|false` is accepted as a shorthand |

The property page's sales carry `vatEstimates` for VAT-exclusive prices (D-015): the price with VAT at the rate for the sale date, and a second figure at 9% where the home could be a qualifying apartment.

## Admin (requires `admin:*` permissions; every write is audit-logged)

**Built in Phase 5** (D-052). The first admin is made with `python -m app.cli grant-role <email> admin`.

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/overview` | open requests, locations to check, accounts, the latest run of each step, the data version |
| GET | `/admin/ingest-runs?kind=&page=` · GET `/admin/ingest-runs/{id}` | every pipeline run with rows read, loaded, withdrawn and failed and its stats (a geocode run's success by confidence level); the detail adds up to 200 failed rows |
| POST | `/admin/ingest-runs` | `{step: ppr | gazetteer | geocode | enrich | aggregate | monthly}` queues the step for the worker (202 with the job); 503 if the queue is down |
| GET | `/admin/jobs` | recent pipeline jobs and their status |
| GET | `/admin/geocode/queue?kind=conflict|low|locality|locked&county=&page=` | properties to check, most recently sold first; `conflict` is a precise point more than 25 km from its routing key's median (D-035) |
| PUT | `/admin/properties/{id}/geocode` | `{lat, lng, confidence: exact|street|locality, note}` places a property by hand, re-joins its areas, locks it against later geocoding runs, and updates its hover card; says whether the point is in the county it was filed under |
| GET/PATCH | `/admin/removal-requests?status=open|…` · `/admin/removal-requests/{id}` | `{status: in_review | approved | rejected, decisionNote}`; approving "stop showing" hides the property at once; a decided request cannot be changed; the requester is emailed the outcome |
| GET/PATCH | `/admin/users?q=` · `/admin/users/{id}` | `{isActive?, roles?, password}`: role changes need the admin's own password; everyone keeps `user`; nobody can deactivate themselves; the last active admin cannot lose the role; deactivating signs the account out |
| GET | `/admin/audit-log?actor=&targetKind=&target=` | newest first |

Merging and splitting properties (dedupe corrections) are not built yet.
