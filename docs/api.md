# API (Phase 0 draft)

- REST, all under `/api/v1`.
- OpenAPI is served at `/api/v1/openapi.json`, with docs at `/api/v1/docs`.
- JSON is camelCase on the wire and snake_case in Python. Pydantic aliases handle the conversion.
- Errors use the RFC 9457 problem+json format: `{type, title, status, detail, errors?}`.
- Auth is a session cookie (D-008), or `Authorization: Bearer <api key>` for Pro.
- State-changing requests need the `X-CSRF-Token` header to match the `csrf` cookie.
- Permission codes are listed in [permissions.md](permissions.md). Rate limits apply per IP for anonymous callers and per user otherwise, using a Redis sliding window.

## Common types

- **`SearchFilter`:** used as query params on `/search`, and stored as JSON in saved searches.
  - `county[]`, `areaId[]`, `routingKey[]`
  - `near=lat,lng&radiusM` (≤ 20 km)
  - `priceMin`, `priceMax`, `dateFrom`, `dateTo`
  - `type=new|second_hand|any`
  - `excludeNonMarket=true` (default), `excludeBulk=true` (default), `vat=exclusive|inclusive|any`
  - `maxStopM`, `maxSchoolM`
  - `minConfidence=exact|street|locality|…`
  - `sort=price|-price|date|-date|change`
  - `page`, `pageSize` (≤ 100)
- **`Confidence`:** `exact | street | locality | routing_key | county | unmatched`.
- **`Sourced<T>`:** `{ value: T, source: string, asOf: date, note?: string }`. Every enriched value uses this shape.

## Meta
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness: DB and Redis ping |
| GET | `/meta` | **Built (Phase 3).** `{dataVersion, pprMaxSaleDate, provisionalFrom, lastIngestAt}`, used by the freshness banner |
| GET | `/sources` | licences and attributions for each data source |

## Auth

**Built in Phase 4** (D-041), plus `GET /auth/policies` for the terms and privacy versions that registration accepts. Every POST, PUT, PATCH and DELETE needs the `X-CSRF-Token` header.
| Method | Path | Body / notes | Limit |
|---|---|---|---|
| POST | `/auth/register` | `{fullName, email, password, age18Plus: true, acceptTerms: true, termsVersion, privacyVersion, profile?: {userType?, counties?, budgetMin?, budgetMax?, propertyInterest?}, marketingOptIn?: false}`. Always answers 202 so it doesn't reveal whether an account exists. | 5/h/IP |
| POST | `/auth/login` | `{email, password}` → sets the session cookie | 10/15 min per IP+email |
| POST | `/auth/logout` | revokes the current session | |
| POST | `/auth/logout-all` | revokes all of the user's sessions | |
| POST | `/auth/verify-email` | `{token}` | |
| POST | `/auth/resend-verification` | | 3/h |
| POST | `/auth/forgot-password` | `{email}` → always 202 | 3/h/IP |
| POST | `/auth/reset-password` | `{token, password}` → revokes all sessions | |
| ~~POST~~ | ~~`/auth/refresh`~~ | dropped (D-008) | |

## Me

**Built in Phase 4**, except saved searches (Phase 5) and search history (with search, Phase 5). `/me/export` is a direct JSON download, not a job. `POST /me/history/views {propertyId}` records a property page visit.
| Method | Path | Notes |
|---|---|---|
| GET/PATCH | `/me` | profile, preferences, `historyEnabled`, notification settings |
| POST | `/me/password` | `{currentPassword, newPassword}` |
| DELETE | `/me` | needs the password; soft-deletes the account, hard-purges after 30 days, and revokes sessions |
| POST | `/me/export` | starts a GDPR export job → 202 `{jobId}` |
| GET | `/me/export/{jobId}` | status, and a download URL when ready (expires after 24 h) |
| GET/POST | `/me/wishlist` · PATCH/DELETE `/me/wishlist/{id}` | add a property or area with a note |
| GET | `/me/wishlist/compare?ids=a,b,c,d` | up to 4 items |
| GET/DELETE | `/me/history/views` · DELETE `/me/history/views/{id}` | |
| GET/DELETE | `/me/history/searches` · DELETE `/me/history/searches/{id}` | |
| GET/POST | `/me/saved-searches` · GET/PATCH/DELETE `/me/saved-searches/{id}` | alerts are set with `alertFrequency` |
| GET | `/me/saved-searches/{id}/export.csv` | row cap by role |
| GET/POST/DELETE | `/me/api-keys` | Pro only |

## Map
| Method | Path | Notes |
|---|---|---|
| GET | `/tiles/sales/{z}/{x}/{y}?{SearchFilter subset}` | **Built (Phase 3).** Martin calling `sales_tiles` (migration 0004). Below z14: layer `cells` (`n`, `median`). From z14: layer `sales` (points for exact and street locations) and layer `stacks` (`n`, `median`, `confidence`: every coarser location, one feature each). Filters: `priceMin`, `priceMax`, `dateFrom`, `dateTo`, `type`, `excludeNonMarket`, `excludeBulk`, `minConfidence`; anything unparseable falls back to the default (D-038). |
| GET | `/tiles/price-hex/{z}/{x}/{y}?window=&segment=` | **Built (Phase 3).** Layer `hexes` (`n`, `median`, `suppressed`); H3 r6 up to z7, r7 for z8-9, r8 from z10 (D-009). |
| GET | `/tiles/planning/{z}/{x}/{y}.pbf?since=&minUnits=` | planning application points layer |
| GET | `/tiles/environment/{kind}/{z}/{x}/{y}.pbf` | radon, noise and zoning (GZT) overlays |
| GET | `/tiles/pois/{z}/{x}/{y}.pbf?types=` | layer toggles for schools, transport and amenities |

The `sales` point layer carries: `id`, `price`, `date` (yyyymmdd int), `isNew`, `nfmp`, `vatx`, `bulk`, `confidence`, `nSales`.

## Properties
| Method | Path | Notes |
|---|---|---|
| GET | `/properties?bbox=w,s,e,n&{SearchFilter subset}&sort=&page=&pageSize=` | **Built (Phase 3).** The list synced with the map: the latest matching sale per property in the box, using the same SQL as the tiles, so they always agree. A box wider than 0.6° or taller than 0.4° is refused (422, "Zoom in to list sales"). |
| GET | `/properties/{id}/summary` | **Built (Phase 3).** The hover card. Reads only Redis (`summary:{id}:{dataVersion}`) or `property_summary`: 10 ms uncached, 3 ms cached on the dev stack. |
| GET | `/properties/{id}` | **Built (Phase 3).** Every sale, location precision and method, areas, vicinity, the most local 12-month median series, and caveats. The full Eircode is not returned, only its routing key. |
| GET | `/properties/{id}/comparables?radiusM=500&months=24` | same street plus nearby, market sales only; only `exact` and `street` confidence are used for the distance test |
| GET | `/properties/{id}/planning?radiusM=250&years=5` | planning at this address plus nearby; no applicant fields exist to return |
| GET | `/properties/{id}/estimate` | the D-020 index estimate: `{low, mid, high, method, basedOnSale, indexSeries}`, or 404 with a reason if ineligible |
| POST | `/properties/{id}/report` | public correction or removal request → `removal_request` (rate limited, CAPTCHA-free honeypot) |

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
| GET | `/search?{SearchFilter}` | `{items: PropertyListItem[], total, bbox}`; syncs the list and map through the shared filter. Limited to 60/min anonymous, 300/min user. |
| GET | `/geocode/autocomplete?q=` | searches our own properties, areas, routing keys and Dublin districts with pg_trgm (D-006); ≥ 3 chars, max 10 results |

## Areas
| Method | Path | Notes |
|---|---|---|
| GET | `/areas/{idOrSlug}` | name, kind, parent chain, simplified geometry, census, deprivation and crime `Sourced` values |
| GET | `/areas/{idOrSlug}/stats?periodKind=&segment=` | the time series from `area_stats`, with provisional and suppressed flags |

## Tools
| Method | Path | Notes |
|---|---|---|
| GET | `/tools/stamp-duty?price=&isNew=&vatInclusive=` | rates come from `config/rates.yaml` and are verified before Phase 5 |
| GET | `/tools/affordability?grossIncome=&secondIncome=&firstTimeBuyer=&deposit=&termYears=&ratePct=` | Central Bank LTI and LTV rules from the same config; the response includes `rulesVersion` and `rulesSource` |

## Admin (requires `admin:*` permissions; every write is audit-logged)
| Method | Path | Notes |
|---|---|---|
| GET | `/admin/ingest-runs` · GET `/admin/ingest-runs/{id}` (includes row errors) | |
| POST | `/admin/ingest-runs` | `{kind}` triggers a run |
| GET | `/admin/geocode/queue?confidence=&county=` | low-confidence properties and dedupe review candidates |
| PUT | `/admin/properties/{id}/geocode` | `{lat, lng, confidence, note}` sets `geocode_locked` |
| POST | `/admin/properties/merge` · `/admin/properties/{id}/split` | dedupe corrections |
| GET/PATCH | `/admin/removal-requests` · `/admin/removal-requests/{id}` | approve suppresses the property |
| GET/PATCH | `/admin/users` · `/admin/users/{id}` | activate or deactivate; change roles |
| GET | `/admin/audit-log?actor=&target=` | |
