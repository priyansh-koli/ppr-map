# Decision log

Format: each decision records its context, the options, the choice and why, and its status.
Status is one of **Proposed** (awaiting review), **Accepted**, or **Superseded by D-xxx**.
Everything below is **Proposed** until the Phase 0 review.

---

## D-001 Ingest the full `PPR-ALL.csv` every run and diff by row hash

- **Context:** The PSRA republishes the whole register and can amend or remove historical rows. The per-year and per-county CSVs are subsets of the same data.
- **Options:** (a) download only the current year's CSV and append; (b) download `PPR-ALL.zip` (19 MB) each run and diff it against what we hold.
- **Choice:** (b). Each row gets `source_row_hash` = sha256 of the 9 normalised raw fields plus an occurrence index, which keeps the 1,188 exact duplicate rows distinct. Rows that are new get inserted. Rows missing from the new file get `withdrawn_at` set and are never hard-deleted, so we can explain disappearances.
- **Why:** This is idempotent and re-runnable, and it picks up PSRA corrections. At 19 MB, the cost of a full download is trivial.

## D-002 Decode as cp1252 and keep raw text

- **Context:** Verified that the file is Windows-1252, not UTF-8. It contains Irish-language enum values and a few mojibake rows.
- **Choice:** Decode as `cp1252`. Store each raw field verbatim (`raw_*` columns) next to the parsed and normalised values. Map description variants to the enum `new | second_hand`.
- **Why:** We can always re-parse later without re-downloading history, and we never silently lose data.

## D-003 Geocoding strategy: a free local cascade now, licensed Eircode lookup as an upgrade (NEEDS YOUR DECISION)

- **Context:** The data has no coordinates. 31% of all rows (75% of recent rows) carry an Eircode, but Eircode→coordinate lookup needs a paid ECAD licence. In the 40-address sample, public Nominatim gave 15% house-level matches and at least one confident wrong match (see `research/ppr-data-profile.md`).
- **Options:**

| Option | Accuracy on PPR | Cost | Limits / licence |
|---|---|---|---|
| Public OSM Nominatim | Low: ~15% exact in sample, worse outside Dublin | Free | 1 request/s, and bulk geocoding is discouraged by policy. 800k rows would take about 9 days and breach the spirit of the policy. **Not viable for batch use.** |
| Self-hosted Nominatim (Ireland extract) | Same data as public, so same accuracy, but no rate limit, and our own normalisation and cascade on top. | Server only: ~4 GB RAM, a few GB disk for the Ireland extract | ODbL. Results stored in our DB need attribution. Follow the OSMF Geocoding Guideline (R-06). |
| Photon (self-hosted) | Similar to Nominatim, better fuzzy and typo handling | Server only | ODbL. Better suited to user-facing autocomplete. |
| Eircode ECAD via an Eircode Provider (e.g. Autoaddress, Loqate) or directly | ~Rooftop for rows with a valid Eircode (~250k rows now, ~75% of new sales) | Eircode's own 2015 price list: €0.01–0.05 per transaction, or per-user or corporate licences (€30k/yr ECAD Corporate). A one-off 250k lookup is roughly €2.5k–€8k plus annual fees. **The price list is 11 years old; get a current quote.** | Direct End User licence forbids resale. Publishing coordinates on a public website needs the website or Provider licence. Terms must be read before committing. |
| Google Geocoding API | Good | Pay-per-use | Terms forbid showing results on non-Google maps and limit caching. **Incompatible with MapLibre and precomputation.** Rejected. |

- **Choice (proposed):**
  1. **Phase 2 builds the free cascade** on self-hosted Nominatim plus our own gazetteers. Each step has its own confidence level:
     `exact` (house number matched) → `street` (street or estate) → `locality` (townland, village or town, using OSM and Tailte Éireann townland polygons plus CSO settlements) → `routing_key` (centroid of our own already-geocoded points sharing the Eircode routing key) → `county` (county centroid) → `unmatched`.
  2. **Sanity checks** run on every candidate: the point must fall inside the reported county (with a 2 km buffer), otherwise downgrade it and log a `county_conflict`; the OSM feature type must be plausible; and the result must be consistent with the Eircode routing key when one is present.
  3. **Eircode ECAD upgrade as a separate, paid decision.** The pipeline gets a pluggable `EircodeGeocoder` interface with a no-op default, so the paid lookup can slot in later without schema changes.
- **Why:** This ships with zero paid dependencies, is honest about accuracy (the confidence is shown on the map), and leaves a clean upgrade path. **I need your go/no-go on requesting an Eircode quote.**

## D-004 Map tiles: Martin serving a PostGIS function source; aggregate at low zoom

- **Context:** About 700k property points. Filters (price, date, flags) must change what the map shows, and the target is 60 fps.
- **Options:**
  - (a) Static PMTiles built monthly with tippecanoe and filtered in the client. This is fast and cheap, but client-side filters give wrong cluster counts.
  - (b) `ST_AsMVT` inside FastAPI. This works, but tile serving then competes with the API for workers.
  - (c) **Martin** (Rust tile server) calling a PostGIS function `sales_tiles(z, x, y, query_params)`.
- **Choice:** (c).
  - At z < 12 the function returns **grid-aggregated cells**: count, median price and price band, computed with the filters applied.
  - At z ≥ 12 it returns individual Property points, one per property, carrying the latest matching sale.
  - Martin sits behind the reverse proxy at `/api/v1/tiles/…`. Tiles are cached by (z, x, y, filter-hash). Tiles for the default filters are pre-warmed after each ingest.
  - Client-side MapLibre clustering is not used for the national view.
- **Why:** Counts stay correct under filters, the browser stays light, and data changes only monthly, so caching is very effective.

## D-005 Basemap: self-hosted Protomaps PMTiles

- **Options:** MapTiler, Stadia, or self-hosted Protomaps.
- **Choice:** A Protomaps basemap extract for Ireland, stored as a PMTiles file on object storage behind a CDN. MapTiler's free key is allowed for local development only.
- **Why:** There is no per-view fee, no key to leak, and costs stay predictable if traffic spikes (for example from a news story). The data is ODbL, so we must show OSM attribution.

## D-006 Address autocomplete runs against our own database, not an external geocoder

- **Choice:** Postgres `pg_trgm` and full-text search over `property.address_normalised`, `area.name` and the Eircode routing keys. No third-party call happens per keystroke.
- **Why:** This is free and fast, and results are always places we actually have data for. Photon can be added later if people need to search arbitrary addresses.

## D-007 Background jobs: RQ plus one APScheduler process

- **Options:** Celery, RQ, or APScheduler only.
- **Choice:** RQ workers for queued work (ingest steps, enrichment, alert emails, data exports). One small scheduler process uses APScheduler to enqueue the monthly and weekly jobs.
- **Why:** The workload is a handful of batch jobs, and Celery's broker and result machinery adds operational weight we don't need. RQ uses the Redis we already have.

## D-008 Auth sessions: opaque server-side sessions instead of JWT access/refresh (challenges the brief)

- **Context:** The brief lists `/auth/refresh`. The frontend and API share one site behind a reverse proxy.
- **Choice:** An opaque random session ID in a `__Host-` httpOnly, Secure, SameSite=Lax cookie. The session row lives in Postgres and is cached in Redis. Expiry is sliding: 14 days idle and 90 days absolute. CSRF uses a double-submit token on every state-changing request. `/auth/refresh` is dropped.
- **Why:** Logout, password change and account deletion revoke sessions instantly, with no token-expiry window and less code. Revisit only if a mobile app or third-party API clients need tokens; Pro API keys cover the latter anyway.

## D-009 The heatmap is a precomputed hexagon layer

- **Choice:** Precompute median price and count per H3 cell (resolutions 6–8) per rolling 12 months, and serve them as a vector-tile layer. This replaces the JSON `GET /map/heatmap?bbox=` endpoint with `GET /tiles/price-hex/{z}/{x}/{y}.pbf`. Cells with fewer than 5 sales are suppressed.
- **Why:** This follows the same tile pipeline as sales, needs no large JSON payload, and small-number suppression avoids misleading medians.

## D-010 Flood risk: no computed flag until the licence is resolved (deviates from the brief)

- **Context:** OPW NIFM and CFRAM flood extents are published under **CC BY-NC-ND 4.0** on data.gov.ie (verified on the NIFM dataset page). NC conflicts with a Pro paid tier. ND arguably conflicts with deriving a per-property "in flood zone" flag.
- **Choice:** The hover card and property page show "Check flood maps for this location →", linking to floodinfo.ie at the point's coordinates. The flood WMS overlay stays out of the map until OPW confirms our use. We email flood_data@opw.ie to ask (needs your OK, since it is outbound contact on the project's behalf).
- **Why:** We don't build on a licence we can't meet.

## D-011 Deprivation index at Electoral Division level, not Small Area (deviates from the brief)

- **Context:** The Pobal HP 2022 index is open (CC BY 4.0) at **ED level** (3,400+ EDs). Small Area scores are only available under licence from the authors.
- **Choice:** Use ED level and label it "Deprivation (Electoral Division)". Asking for the SA licence is an open question.

## D-012 Crime: area pages only, at Garda station level with caveats, never in the hover card

- **Context:** CSO table CJA07 (verified via the PxStat API) gives recorded incidents by 564 Garda stations × 14 offence groups × year for 2003–2025. It is CC BY 4.0 and marked "under reservation". It includes no station coordinates and no station catchment boundaries.
- **Choice:** Show a per-station, per-year table on area pages for the stations whose names match the area, with the CSO "under reservation" caveat and a per-capita warning. No crime metric appears on property cards.
- **Why:** Without catchment boundaries, "crime near this house" would imply a precision the data doesn't have.

## D-013 BER: county-level aggregates only

- **Context:** SEAI publishes two BER datasets. The **public** anonymised Research Tool download needs registration and has no precise location. The Eircode-level dataset is restricted: it needs a trusted-partner agreement and homeowner consent.
- **Choice:** Use the public dataset for county-level distributions by dwelling type and period only. We never attach a BER to a property.

## D-014 Broadband: out of scope for v1

- **Context:** I found no open bulk download of National Broadband Plan coverage, only the NBI per-Eircode lookup map. Scraping it would breach the spirit of the service.
- **Choice:** Drop it from v1 and revisit if NBI or ComReg publish open data.

## D-015 VAT display for new builds

- **Choice:** Show the PPR price as filed. For `vat_exclusive = true`, also show a labelled estimate "≈ €X incl. VAT (estimated at 13.5%)". The VAT rate comes from a **dated rate table** in `config/rates.yaml`, because rates can change by date and dwelling type. Rates get verified before Phase 5, and the estimate is never presented as the price paid.

---

*The decisions below were added after the competitor and data-source review on 2026-09-26. See `research/competitive-analysis.md`.*

## D-016 Data acquisition policy: official channels only, no scraping against terms

- **Context:** You asked me to scrape relevant sites. The review found:
  - Daft forbids automated access and database-building in its terms.
  - LandDirect forbids scraping and reuse, and exposes owner names.
  - propertymap.ie's content is agents' and portals' copyright.
  - The OPW State property register is restricted to public bodies.
- **Choice:** Pipeline sources must be (a) official open-data downloads or APIs with a recorded licence, or (b) data we have a written licence for.
  - Every source has a row in `external-services.md` and an `ingest_run.kind`.
  - The pipeline sends a descriptive User-Agent, respects robots.txt, and caches results.
- **Why:** This is legal certainty, and it's also better engineering. The open equivalents (planning, zoning, boundaries) come from the original publishers, have schemas, and update on schedule.

## D-017 Planning applications as a first-class enrichment, with personal data stripped

- **Source:** National Planning Applications FeatureServer (CC BY 4.0, weekly, 507,751 rows).
- **Choice:**
  - Ingest weekly with an **explicit `outFields` allow-list** that excludes `ApplicantForename`, `ApplicantSurname` and `ApplicantAddress`.
  - A unit test asserts that those fields never appear in stored rows or logs.
  - Link each application to properties by (a) the same normalised address or Eircode, giving "planning history of this address", and (b) distance, giving "applications within 250 m", plus large schemes (≥ 10 units) within 1 km.
  - Show `FloorArea` and `NumResidentialUnits` only as planning facts, never as the property's size.
- **Why:** No competitor puts planning activity next to sold prices, and the combination is very useful to buyers.

## D-018 Environment layers: radon (EPA), noise (EPA Round 4), zoning (GZT); flood stays a deep link (D-010)

- All open (CC BY). They are precomputed per property as `Sourced` values: `radon_high_area` (bool plus grid %), `road_noise_lden_band` (only where mapped; otherwise "not mapped", **never "quiet"**), and `gzt_zone`.
- GZT always carries a "not statutory, check the development plan" note.

## D-019 Official benchmarks: CSO RPPI, routing-key medians, RTB rents

- Load the CSO PxStat tables (the RPPI, the median-by-Eircode-routing-key table, and RIQ02 rents).
- Area pages show our median next to the CSO's, and an **indicative gross yield** = (RTB average rent × 12) / our median price, at town level only, labelled indicative.

## D-020 Price estimate: transparent, index-based, only where a prior market sale exists

- **Method:** estimate = last market sale price × (CSO RPPI for its region and type today / RPPI at the sale month), shown as a range using the regional dispersion of repeat-sale errors, with the method shown inline.
- No estimate is given for properties whose only sales are non-market or bulk, or whose confidence is below `street`.
- Framed as "what the index implies", not a valuation. It is not financial advice.
- Built in Phase 5.
- **Status: Accepted** (owner, 2026-09-26, Q-10).
- **Why:** Competitors offer black-box "instant valuations". Ours is explainable and reproducible from open data.

## D-021 No third-party ad or tracking scripts

- **Choice:** no ad networks or third-party analytics. Use cookieless, self-hosted analytics (e.g. Plausible or Umami self-hosted) or none at all.
- **Why:** It is a differentiator against Daft (139 partners) and houseprice.ie (210). It also fits GDPR data minimisation, and it removes the need for a consent wall.

## D-022 Pin external dataset URLs in config and alert on moves

- **Context:** GeoHive has announced that some hubs will be retired or migrated from September 2026.
- **Choice:** Every source URL lives in `config/sources.yaml` with its expected schema hash. Ingest fails loudly on a 404 or schema change, and the admin dashboard shows it.

## D-023 No licensed listing data (beds, m², BER, asking price)

- **Context:** Q-09 asked whether to approach Daft or MyHome for a data licence.
- **Choice:** No. We show only what the PPR and open sources hold, and compete on the map, clean statistics, planning, environment, transparency and privacy (`research/competitive-analysis.md` §4).
- **Status: Accepted** (owner, 2026-09-26).

---

*Phase 1 (scaffold) decisions, 2026-09-26.*

## D-024 H3 cells stored as `bigint`, computed in Python (no `h3-pg` extension)

- **Context:** The stock `postgis/postgis` image has no `h3-pg`. Adding it means maintaining a custom Postgres image.
- **Choice:** Compute H3 ids and hexagon polygons in the pipeline with the `h3` Python library, and store them as `bigint` and PostGIS polygons.
- **Why:** This keeps the stock image and gives identical results. The extension can be revisited if ad-hoc SQL on H3 becomes common.
- **Status:** Accepted (implementation detail).

## D-025 Roles and permissions synced by command, not seeded by migration

- **Choice:** `python -m app.cli sync-permissions` upserts roles, permissions and the matrix from `app/auth/permissions.py`, and removes stale grants. `make migrate` runs it after `alembic upgrade head`.
- **Why:** Seeding in migrations freezes old matrices into history and drifts from the code. The command is idempotent and tested, and a unit test keeps `docs/permissions.md` identical to the code.
- **Status:** Accepted (implementation detail).

## D-026 One origin in development through Caddy

- **Choice:** Caddy on `localhost:8080` routes `/api/v1/tiles/*` to Martin, `/api/*` to FastAPI, and everything else to Next.js. This mirrors production, so cookies, CSRF and CORS behave the same everywhere. There is no CORS configuration at all.
- **Status:** Accepted (implementation detail).

## D-027 Initial migration rendered from the models, verified offline

- **Context:** No database was available while scaffolding (Docker not yet installed).
- **Choice:** `0001_initial_schema` was rendered from the SQLAlchemy models with Alembic's operation renderer. Enum types are created explicitly up front, and the migration adds the `audit_log` append-only trigger.
  - Tests render the full upgrade and downgrade SQL offline on every run.
  - CI (and `make test-db` locally) applies it to real PostGIS and runs `alembic check`, which fails if the models and migrations ever diverge.
- **Status:** Accepted. First live run on 2026-09-26 found that the offline render wrote Boolean defaults as `1`/`0`, which Postgres rejects; fixed to `sa.true()`/`sa.false()`.

## D-028 Frontend starts on the current stable majors

- **Context:** The scaffold assumed Next.js 15. By 2026-09-26, Next.js 16.3 is stable and 15.x is maintenance-only.
- **Choice (owner, 2026-09-26):** Latest stable of every package, at the newest versions their peers allow:
  - Next 16.3, React 19.3, MapLibre GL 6.11, Tailwind 4.3, Vitest 5, Playwright 1.63
  - ESLint 9.39, because `eslint-config-next` 16 does not support ESLint 10 yet
  - TypeScript 6.0, the newest the lint tooling accepts
  - Node 22 LTS (official nodejs.org build)
- **Consequences:** The ESLint config uses Next 16's native flat config (no `@eslint/eslintrc` compatibility layer), and the frontend package is ESM (`"type": "module"`).
- **Status:** Accepted.

## D-029 Official PostGIS image under emulation on Apple Silicon

- **Context:** `postgis/postgis:16-3.5` publishes no `linux/arm64` image, so `make up` failed on an Apple Silicon Mac.
- **Options:** (a) pin `platform: linux/amd64` and run the official image under Rosetta; (b) switch to a community multi-arch build (for example `imresamu/postgis`).
- **Choice:** (a). Local development uses the same image as CI, and no third-party image is added. Emulation is slower, which matters most for bulk loads in Phase 2.
- **Status:** Accepted. If Phase 2 ingest proves too slow locally, revisit (b).

## D-030 Addresses without a house number or unit are not merged across sales

- **Context:** The first full load (2026-09-26) merged on the exact address key. Keys with no house number and no unit (townlands and estate names such as `KNOCKROE, CASTLEREA, CO ROSCOMMON`) collected up to 28 sales. Of 120,217 such keys, 6,362 had 4 or more sales and 8,853 had two sales less than a year apart; the Knockroe pair sold six weeks apart at €145,400 and €56,000. Numbered keys looked plausible: 544 of 549,439 had 4 or more sales.
- **Options:** (a) merge them anyway; (b) merge them only when the sales "look like" one house (few sales, far apart); (c) never auto-merge them, and send candidates to the review queue.
- **Choice:** (c). Each such sale gets its own Property. Repeat filings of the same sale (same date, address and price) still share one. The address key keeps the plain key before a `~` suffix, so review-queue matching can find the candidates.
- **Why:** A wrong merge invents a sale history, which would also feed the price estimate (D-020). Splitting loses some genuine repeat sales of named houses, but that is recoverable by review, while a silent false merge is not visible to anyone.
- **Result:** 728,509 properties from 807,724 sales; 70,440 with more than one sale; at most 6 sales for one property.
- **Status:** Accepted (implementation detail; revisit if the review queue shows many genuine repeats).
