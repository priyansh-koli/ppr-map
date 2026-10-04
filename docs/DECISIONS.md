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

## D-031 Bulk and portfolio sales: same date and price, with evidence it is not a coincidence

- **Context:** The planned rule was "at least 3 rows with the same date, price and county, or the same date and a price above €5M". Checked on Dublin on 2026-09-26: groups of 3 at round prices were mostly coincidences, unrelated homes across the county on one busy day (for example three homes in Swords, Dublin 8 and Santry at €400,000 on 23 Aug 2024). Groups at odd prices were units in one scheme (three Mount Argus flats at €472,025 on 1 Apr 2020).
- **Choice:** A group is sales on the same date at the same price. It is flagged when:
  - the price is above €5M and at least 2 properties share it, in any county; or
  - at least 3 properties in one county share it, **and** either the price is not a whole €1,000 (apportioned prices do not happen by chance) or at least 3 of them are in the same locality (the last address part, ignoring `Co X`).
- **Result:** 34,668 sales (4.3%) in 5,207 groups; 4.5–5.6% per county.
- **Trade-off:** A real portfolio at a round price spread across several localities is missed, and stays in medians. A coincidence of 3 same-price sales in one locality on one day is flagged. Both are rare, and users can switch the filter off (Q-08).
- **Status:** Accepted (implementation detail). Group ids are a hash of (date, price, scope), so they are stable between runs.

## D-032 The OSM extract is downloaded on the host, then mounted into Nominatim

- **Context:** On 2026-09-26, TLS connections from containers to `download.geofabrik.de` failed (`SSL_ERROR_SYSCALL`), while other HTTPS sites worked from containers and Geofabrik worked from the host.
- **Choice:** `make osm-extract` downloads the Ireland extract to `data/osm/` on the host and checks Geofabrik's md5. Nominatim imports it through `PBF_PATH` from a read-only mount. `make geocoder` starts it.
- **Why:** This sidesteps the container network issue. It also pins one extract file that the amenities step (enrichment) will reuse, so geocoding and amenities come from the same OSM snapshot.
- **Status:** Accepted (implementation detail). The first extract used: `ireland-and-northern-ireland-260925.osm.pbf` (md5 `592c0cadcc5d5dd8b645646f745450d5`).

## D-033 Boundary layers, and how areas nest

- **Context:** Geocoding checks ("is the point inside the reported county?"), spatial joins and area stats all need official boundaries.
- **Choice:** Five layers from the Tailte Éireann open-data hub, pinned in `config/sources.yaml` and downloaded as File Geodatabases (about 230 MB, against 1.5 GB as GeoJSON), read with `pyogrio` (which bundles GDAL):

| `area.kind` | Layer | Features | Why this one |
|---|---|---|---|
| county | Counties, statutory, ungeneralised, 2026 | 26 (from 9,261 parts) | the 26 counties the PPR uses |
| electoral_division | CSO Electoral Divisions 2022, ungeneralised | 3,420 | matches Census 2022 and the Pobal index (D-011) |
| small_area | CSO Small Areas 2022, ungeneralised | 18,919 | matches Census 2022 SAPS |
| townland | Townlands, statutory, ungeneralised, 2026 | 50,575 | the finest named place for rural addresses (D-003 `locality`) |
| settlement | CSO Urban Areas 2022, ungeneralised | 867 | the 2022 successor to CSO settlements |

- **Nesting:** Small Area → ED by the CSO's `ED_GUID`. ED, townland and settlement → county by the county containing a point on their surface; the CSO labels EDs with 34 local-authority "counties" (FINGAL, CORK CITY, …), so a spatial parent is simpler and exact. Five coastal CSO shapes (the Dún Laoghaire-Salthill, Clontarf West D, Pembroke East A and Dundalk No. 2 Urban EDs, and Dungarvan town) run over harbour and foreshore past the statutory county line, so that point lands 20–150 m offshore; they take the nearest county within 2 km.
- **Geometry:** `geom_full` keeps the ungeneralised ITM shape for joins; `geom` is a simplified WGS84 copy for display (5–50 m tolerance by layer). A new `area_part` table (migration 0002) holds `ST_Subdivide` pieces of at most 256 vertices with a GIST index. Without it, assigning 50,575 townlands to counties ran for over 7 minutes and was cancelled; with it, the whole load takes about 4 minutes.
- **Names:** names that are mostly capitals are title-cased (`CARLOW RURAL` → `Carlow Rural`, `DUNDALK No. 2 URBAN` → `Dundalk No. 2 Urban`); names the publisher already cased (`Dún na nGall`) are kept as published.
- **Licence:** Tailte Éireann data-sharing policy (open, attribution); the townland metadata on data.gov.ie still says "No licence specified" (R-05).
- **Status:** Accepted (implementation detail).

## D-034 Public preview of the frontend on GitHub Pages

- **Context:** On 2026-09-27 the owner asked for the app to be reachable beyond `localhost`, deployed on GitHub, with the repository made public. GitHub Pages serves static files only, so it cannot run FastAPI, PostGIS, Redis or Martin.
- **Options:** (a) GitHub Pages for a static export of the frontend; (b) a hosted server for the full stack, which means signing up for a paid or third-party service (needs the owner's approval first); (c) stay local only.
- **Choice:** (a), for now. `STATIC_EXPORT=1` switches `next.config.ts` to `output: "export"` with a `basePath` from `PAGES_BASE_PATH`, and `.github/workflows/pages.yml` builds and deploys it on every push to `main`. Without the flag, the Docker build is unchanged (`standalone`, with the `/api` rewrite). The dynamic routes pre-render only their sample URLs (`/area/dublin`, `/property/example`) through `generateStaticParams`; the server build still renders any slug or id.
- **Why:** Free for a public repository, no new account or API, and the Phase 1 pages have no server dependencies.
- **Limits:** Anything that needs the API (map data, sign-in, search, admin) cannot work on Pages. When Phase 3 adds live data, the full stack needs a real host (option b), and this preview is either retired or kept as a docs site.
- **Status:** Accepted (owner request, 2026-09-27).
- **Update 2026-09-27:** Pages now deploys only after CI passes on `main` (`workflow_run`), and first runs the Playwright route smoke tests against the export served under the base path (`E2E_BASE_PATH`, `e2e/serve-export.mjs`). Before, a commit that failed lint or e2e was still published, and nothing tested the base path.
- **Update 2026-10-03:** superseded by D-056: the preview moved to Vercel, and the Pages workflow and base path are gone.

## D-035 Geocoding cascade as built, and what it achieved

- **Context:** D-003 set the plan: self-hosted Nominatim, our own gazetteers, a confidence level on every point. On a first sample, Nominatim's loose matching gave wrong answers with high scores: "Fenit, Tralee" returned Fenit *Road*, "Coosan" the *Coosan Heath* estate, "The Mall, Thurles" the Mall in Templemore, and "Athlone Rd, Longford" a road in County Cavan.
- **Choice:**
  - Each address is queried from its full form down to its town (`query_parts`, `ladder`), bounded to the county's box. A trailing bare county name ("…, Athenry, Galway") is tried with and without, because it is sometimes the town.
  - A result is accepted only if its name matches the queried part word for word (abbreviations expanded; a townland division such as "Big" may be added), it is a plausible feature for the level (a house number on the right street for `exact`; a street or estate for `street`; a village, townland or suburb for `locality`; never a city or county), and it lies within 5 km of the address's town (15 km for cities, 20 km for localities). Without a town, two same-named matches more than 3 km apart are ambiguous and rejected.
  - PostGIS rejects any point more than 2 km outside the reported county.
  - Fallbacks, recomputed on every run: a unique official townland or CSO settlement name in the county (`locality`); the median of exact and street points sharing the Eircode routing key, or the Dublin postal district when there is no Eircode (`routing_key`); a last part naming the county taken as the town of that name (`locality`, method `gazetteer:county_town`); a point inside the county (`county`).
  - A precise point more than 25 km from its routing key's median is logged as `routing_key_conflict` for review, not moved: PPR Eircodes are sometimes wrong (R-04).
  - Small Area, ED and H3 r8 are joined for exact and street points only; a town-centre point says nothing about which Small Area a house is in.
- **Result (first full run, 2026-09-27, 728,460 properties, 810k queries, 65 min):** exact 68,423 (9.4%), street 265,395 (36.4%), locality 324,320 (44.5%), routing key 28,864 (4.0%), county 41,458 (5.7%); 8,976 routing-key conflicts queued. Exact matches outside Dublin are 1–4%, as the Phase 0 sample predicted: OSM has few house numbers there. Only the Eircode lookup (D-003, a paid decision) would change that.
- **Status:** Accepted (implementation detail).

## D-036 Enrichment sources for the hover card

- **Context:** The hover card needs the nearest stop, schools, shops nearby and deprivation, precomputed (goal 1 in ARCHITECTURE.md).
- **Choice:**
  - **Stops:** the NTA GTFS feed; a stop is typed by the routes that call there (bus, Luas, DART, rail). 14,089 served stops.
  - **Amenities:** the same OSM extract Nominatim uses, read locally with GDAL's OSM driver (no Overpass). 51,700 points of interest.
  - **Schools:** OSM `amenity=school`, because gov.ie still refuses automated downloads of the Department of Education lists (403). A school is typed primary, post-primary or special only when its tags or name say so (3,018, 803 and 65); others are left out, not guessed. Replace with the official lists when they can be downloaded.
  - **Deprivation:** Pobal HP 2022 by ED, matched through the CSO ED id (Pobal drops leading zeros). All 3,417 EDs matched.
  - Distances are straight lines in metres and are labelled as such; there is no routing engine.
  - Vicinity values exist only for exact and street points (333,818). A distance from a town centre or a county point would be invented.
- **Status:** Accepted (implementation detail).

## D-037 Aggregates: what counts, and at which levels

- **Choice:**
  - Market sales only: not "not full market price", not in a bulk group (D-031), not a possible duplicate filing, not withdrawn.
  - `area_stats`: counties, settlements and EDs get month, quarter, year and a rolling 12 months ending each month; Small Areas and townlands get quarter and year only, which keeps the table at 2.6 million rows. Groups with n < 5 keep the count and drop every price. Periods ending on or after the first day of the month before the latest sale's month are provisional.
  - `price_hex`: H3 r8 cells from exact and street points, with their r7 and r6 parents recomputed from the sales (not averaged), over 12 and 36 months: 24,044 cells.
  - `property_summary`: one JSON row per property. The area line uses the settlement if it has unsuppressed 12-month stats, else the county. Flood is always the OPW link with no value (D-010).
  - `data_version` is the latest sale date and the PPR ingest run id (`2026-09-18.r1`). *Update 2026-09-30:* it now also names the aggregate run (`2026-09-18.r1.a18`): re-geocoding the same register kept the old version, so Martin and the hover-card cache would have served the old locations.
- **Status:** Accepted (implementation detail).

## D-038 Map tiles and the synced list, as built

- **Context:** D-004 planned grid aggregates below z12 and points from z12. Measured on the full data: a z12 tile of central Dublin points is 1.2 MB; at z14 it is 68 KB. Sales placed only at a town or townland centre (44% of properties, D-035) would stack hundreds of dots on one spot and read as one sale.
- **Choice:**
  - `sales_tiles` (migration 0004): below z14, 64 grid cells per tile side (about 75 m at z13) with count and median; from z14, one point per exact or street property, and one **stack** per coarser location with its count and median, drawn hollow with the count on it.
  - Cells are aligned to the tile and read only the sales inside it, so each sale is counted in exactly one cell of one tile (a test checks that four child tiles add up to their parent).
  - Tile URLs carry the data version (`?v=2026-09-18.r1`): Martin caches tiles by URL, so a monthly run is shown at once without restarting it.
  - The filters are parsed in SQL with defaults, so a malformed URL gives the default map, never a 500.
  - `/api/v1/properties` (the list view) calls the same `tile_matching_sales` function, so the list and the map cannot disagree. It refuses boxes larger than 0.6° × 0.4° and the UI asks the user to zoom in.
  - Timings on the dev stack (Postgres under emulation): a national z6 tile 2.7 s uncached, z10 55 ms, z14 110 ms; Martin caches tiles in memory.
  - Price colours: one blue hue in four steps, validated as an ordinal ramp against the basemap's land colour (the dataviz checks: monotone lightness, visible steps, light end at 2.25:1). Five steps did not pass.
- **Status:** Accepted (implementation detail; revises the zoom in D-004).

## D-039 Basemap and map library, as built

- **Choice:**
  - `make basemap` downloads the `pmtiles` CLI (v1.31.2), extracts Ireland to z15 from the pinned Protomaps build 20260926 (561 MB), and fetches the fonts and sprites at a pinned commit. Caddy serves them at `/basemap/` with range requests. Viewing the map calls no third party (D-021).
  - MapLibre GL 6 is ESM-only and starts its worker from a URL beside its module, which bundlers do not copy. A `predev`/`prebuild` step copies the worker and its shared chunk to `public/maplibre/<version>/` and the map calls `setWorkerUrl`.
  - Object storage and a CDN for production (D-005) remain an open, possibly paid, choice.
- **Status:** Accepted (implementation detail).

## D-040 API response conventions added in Phase 3

- **Choice:**
  - Money is `Decimal` in Python and a plain JSON number on the wire (`Money` in `app/schemas/base.py`).
  - Where Pydantic's camelCase generator would mangle a name (`shops_within1km` to `shopsWithin1Km`), the alias is explicit; a test guards the hover fields.
  - The frontend's types are generated from `frontend/openapi.json` (`make api-types`). A backend test fails if that file is stale, and CI's `npm run api:check` fails if the types are.
  - The property page shows the Eircode routing key, not the full Eircode: the address is shown already, and the full code adds nothing for buyers.
- **Status:** Accepted (implementation detail).

## D-041 Accounts as built (Phase 4)

- **Sessions (D-008):** a random 256-bit token in an httpOnly, SameSite=Lax cookie (`__Host-ppr_session` and Secure in production; `ppr_session` on http://localhost). Postgres stores only an HMAC of it under `SESSION_SECRET`, so a leaked table cannot be replayed. Sessions end after 14 days idle, 90 days in all, or at once on sign-out, password change or reset, and account deletion. Lookups are cached in Redis for 60 s, and revoking deletes the cache keys.
- **CSRF:** a signed double-submit token. Every API response sets `ppr_csrf` (`random.HMAC`) if missing; every POST, PUT, PATCH and DELETE must echo it in `X-CSRF-Token`. The signature stops a planted cookie.
- **Passwords:** argon2id; at least 10 characters, at most 128, and not the email address (length over composition rules, NIST SP 800-63B). An unknown email still costs one hash check, so sign-in timing does not reveal accounts.
- **No account enumeration:** registering an existing email and asking to reset an unknown one both answer the same 202; the email says what happened.
- **Rate limits:** fixed windows in Redis (sign-in 10 per 15 min per IP and email; registration and reset 5 per hour per IP; resend 3 per hour). If Redis is down, requests are allowed: the limits stop abuse, they do not guard correctness.
- **Email:** plain-text SMTP; Mailpit catches it in development. The production provider is still your choice (docs/external-services.md).
- **Data export** is a synchronous JSON download instead of the planned background job: one account's data is small.
- **Deletion:** closing an account deactivates it and ends its sessions at once; `python -m app.cli purge-deleted` removes accounts closed more than 30 days ago with everything they own. It needs a daily schedule once the scheduler exists.
- **History** records a property page visit only while history is on, counts repeat visits within 30 minutes once, and keeps 12 months.
- **Legal pages:** `/privacy` and `/terms` describe what the app does today and are marked as drafts until the operator's name and contact details are added and they are reviewed.
- **Status:** Accepted (implementation detail).

## D-042 Accounts: changes from the Phase 4 review

- **Context:** a review of Phase 4 (code reading, the test suite, and probing the running stack) found bugs and some claims in D-041 that did not hold.
- **Choice:**
  - **CSRF:** the signature only rejects tokens the server never issued; it is not tied to a session, so D-041's "the signature stops a planted cookie" was wrong. The protection is that another site cannot send the custom header without CORS, which the API does not allow. A refused request now gets a fresh token, and malformed (non-ASCII) tokens are a 403, not a 500.
  - **Timing:** argon2 runs in a small thread pool (4), never on the event loop. Registration hashes the password before looking up the email, and every email is sent after the response, so neither registration nor reset timing reveals an account.
  - **Sign-in limit:** 10 per 15 min per IP and address (a successful sign-in resets it; the address is hashed in the Redis key), plus 100 per 15 min per IP against spraying many addresses. Rate-limit keys get their TTL with `EXPIRE NX` on every call, so a lost first `EXPIRE` cannot lock a caller out for ever.
  - **Sessions:** revoking commits first, then deletes the cache keys and leaves a 2-minute "revoked" marker, so a lookup that raced the revocation cannot re-cache a dead session. Sign-out answers 204 and clears the cookie even when the session had already ended.
  - **Links:** a reset link is claimed with `SELECT … FOR UPDATE` (concurrent use of one link succeeded several times before). Changing the password voids open reset links.
  - **Closed accounts:** registering the address of a closed account sends "your account is closed; it is deleted on <date>, then you can register again", instead of "sign in", which could not work. Reactivation is not offered.
  - **Retention:** `app.cli purge-deleted` is the daily housekeeping job: closed accounts after 30 days, expired sessions, used or expired email links, and views older than 12 months. Views older than that are also never listed or exported. The audit-log trigger (migration 0005) now allows the one change a purge makes, `actor_user_id` becoming NULL; before, one audit entry blocked every purge.
  - **Input:** NUL characters are refused (422) in every API string (Postgres cannot store them; they were 500s). Names are trimmed, 1 to 200 characters, without control characters, because they are quoted in emails. Budgets fit `numeric(12,2)` and `budgetMin ≤ budgetMax`. `PATCH /me` changes only the fields sent, including inside `profile`, and null is refused. A marketing consent is recorded only when the choice changes. Caddy refuses API bodies over 1 MB.
  - **Wishlist and history:** a property withdrawn after a removal request (`is_suppressed`) disappears from the wishlist and history, and the export lists it without its address. Saving an item again answers 200 with the existing item (and a new note, if given), even when the wishlist is full. Adds and visits are serialised per user with advisory locks, so the 500-item cap and the 30-minute dedupe hold under concurrent requests.
  - **Export:** camelCase keys throughout, and it now includes the account timestamps, profile areas, consent and session IP hashes, API keys (name and prefix only), alerts sent and audit entries. Secret hashes stay out.
  - **Still open, for Phase 5:** unverified accounts have the full `user` role. Alerts must check `email_verified` themselves before sending (docs/permissions.md says `alert:receive` needs a verified email). The history list is capped at 200 rows without pagination.
- **Status:** Accepted (implementation detail; corrects D-041).

## D-043 Visual design: record windows on a survey sheet

- **Context:** the owner asked for a look in the spirit of sorted.place (dublin-job-finder.vercel.app), similar but not the same, with our own improvements. After a first pass they asked for its signature traits to go (the yellow highlight, the typeface, the patterned background). The Phase 1–4 pages used default system type on white.
- **Choice:**
  - **Shared with the reference, as a family resemblance:**
    - White cards with a small mono label bar. Ours say what they hold (`register · 2 sales`, `register · latest entries`) and carry a map pin, not window buttons.
    - A glass sticky header with the register's date; its provisional window opens from it.
    - A theme toggle (device, light or dark).
  - **Ours, and deliberately unlike it:**
    - **Type:** Fraunces, a soft serif, for headings. The one phrase that matters is set in its italic, in brand green; there is no highlighter. IBM Plex Sans is the text face and IBM Plex Mono the label face. Big figures stay in the sans, with tabular digits. All fonts are self-hosted by next/font, and there is no handwriting face.
    - **Background:** plain warm paper, with no repeating pattern. Faint map contour lines appear only behind the home hero, drawn from a fixed formula.
    - **Hero:** a left-aligned headline beside one "latest entries" ledger window, which lists the newest market sale in six towns (real, from the list endpoint). A green register stamp carries the real total. There are no tilted floating cards, sticky notes or stickers.
    - **Controls and tiles:** flat buttons with 10 px corners, not glossy pills. The status icon is a register page, not a pulsing "live" dot. County tiles use Irish number-plate index marks (D, C, KK…) with sales and median as plain figures, not red count bubbles.
    - **Colour:** green for the brand and actions, so blue stays reserved for data. The map's price scale (D-038) keeps its blues, and confidence marks everywhere are drawn as on the map: solid for house or street, a ring for town-level.
    - **Home sections:**
      - A monthly chart, with the provisional months as a lighter, labelled step and a table view.
      - The 26 county tiles, linking to the map.
      - A "what you will not find here" band, which turns the data's limits into a reason to trust it.
    - **New endpoint:** `GET /api/v1/stats/overview`. It returns national monthly counts (the county `area_stats` summed, market sales only) and each county's latest complete 12 months (count and median, n < 5 suppressed). It is held in memory per data version.
    - **Property page:** a "change" column against the previous sale. It appears only between two plain market sales (not VAT-exclusive, not full market price, bulk or a possible repeat filing), and says it is not adjusted for inflation or work done.
  - **Accessibility:**
    - Every token pair is checked for WCAG AA: text 4.5:1, and control borders 3:1 through a separate `--color-control` token.
    - Dark mode uses its own values, and an explicit choice is applied before first paint.
    - Motion stops under `prefers-reduced-motion`.
    - On phones the navigation folds into a menu sheet.
  - **The map stays on the light basemap in both themes:** the price ramp was validated against its land colour.
- **Status:** Accepted (implementation detail; awaiting the owner's review with Phase 4).

## D-044 Map legibility and selection

- **Context:** the owner found the zoomed-out map too crowded and the place names unreadable. Below z14, 64 cells per tile side put a dot every 8 px, so the map was an even carpet of overlapping dots. The sales layers were also drawn above the basemap's labels. Selecting a sale left no mark on the map. The pinned card stayed where the click was while the map moved. Sales drawn on one street point could not be told apart, and a click on a group did nothing useful.
- **Choice:**
  - **Coarser groups (migration 0006):** 16 cells per tile side (32 px), each drawn at the mean position of its sales rather than at the cell's centre. Groups now sit on the towns and streets they stand for. Each sale is still counted in one cell of one tile, and a test checks that every group lies inside its cell.
  - **Groups as bubbles:** they are sized by count on one log scale at every zoom, and coloured by their median in the D-038 bands. Counts of 10 or more are printed on the bubble (1.2k, 12k): in ink on the lightest band and in white on the others, each pair at least 4.5:1.
  - **Names above the data:** the sales layers are inserted beneath the basemap's first label layer. Town and neighbourhood names get a 2 px white halo and darker text; street names get a firmer halo. A count that would collide with a name is left out, so the name wins.
  - **Selection:**
    - Clicking a group zooms in towards it. Hovering it still shows its count and median.
    - Clicking a sale selects it. The selection is drawn above everything as a price-coloured dot with an ink ring and a soft halo, from its own GeoJSON source, so it stays visible at every zoom.
    - The card follows its sale as the map moves. It docks in the corner when the sale leaves the view, or on phones.
    - Clicking empty map or pressing Escape clears the selection.
    - The selected sale is marked (`aria-current`) and scrolled into view in the list. Choosing a sale in the list zooms in far enough to see it on its own.
  - **Sales on one spot:** when several sales overlap under the pointer, the card lists them to choose from. Their addresses come from the list endpoint for a small box round the spot, so it is one request to our own API, never a third party.
- **Status:** Accepted (implementation detail; revises the cell size in D-038).

## D-045 Relief, buildings and a 3D view

- **Context:** the owner found the zoomed-in map flat: no terrain, roads that barely showed and buildings that could hardly be seen. The Protomaps light flavour draws road casings in #e0e0e0 on land of #e2dfda, and buildings at half opacity in #ccc. The basemap carries no elevation.
- **Options for relief:**
  - (a) Hosted terrain tiles (MapTiler, Mapbox): these need a key and call a third party whenever the map is viewed (D-021). Rejected.
  - (b) AWS "Terrarium" PNG tiles packed ourselves: public, but unmaintained, and would need our own packing step.
  - (c) Mapterhorn's open terrain PMTiles, extracted for Ireland with the `pmtiles` CLI we already use (D-039).
- **Choice:** (c).
  - `make terrain` extracts Ireland to z11 (55 MB; about 23 m a pixel here, finer than the source), and Caddy serves it from `/basemap/`. Over Ireland the data is Copernicus DEM GLO-30, which is free and open with credit to DLR e.V. and Airbus Defence and Space, provided under COPERNICUS by the EU and ESA. The credit appears in the map's attribution. There is no sign-up and no view-time third-party call.
  - **Hill shading:** always on, beneath the roads, fading out at street zooms.
  - **3D view:**
    - A "3D view" button tilts the map to 60°. So does right-drag or a two-finger drag.
    - While the map is tilted the terrain is raised (×1.5, since Ireland's hills are low). It is laid flat again when the map looks straight down.
    - The compass shows the bearing and tilt. Tilt and bearing are kept in the URL.
    - A pale sky and fog fill the horizon.
    - The map works without the terrain file: it stays flat, with buildings and no relief.
  - **Buildings:**
    - Every footprint is drawn in a warmer grey with an edge, so a terrace reads as separate houses.
    - From z14, buildings are raised to their height **only where OpenStreetMap records one**. In sample tiles that is 8–35% of buildings, most of them in city centres. The rest stay flat: a guessed height could be read as a fact about a property ("Never fake data"). The key says so.
  - **Roads:** casings in #c9c2b5, so roads have edges. The land colour is unchanged, because the price ramp was validated against it (D-038).
  - **Tests:** the style is checked with MapLibre's own validator, with and without terrain. An invalid style (a stray `attribution: undefined`) had left the map blank with no error, so map errors other than tile errors are now logged.
- **Status:** Accepted (implementation detail).

## D-046 A local street gazetteer after Nominatim, and more open map data for it

- **Context:** the owner found places on the map that were wrong, and recent houses that were not on it. Measured on 2026-09-29:
  - **The register is current.** The PSRA site says "Register Last Updated: 23/09/2026". The `PPR-ALL.zip` we loaded is that release (807,724 sales to 2026-09-18), so no sale is missing from the data. Recent sales are missing from the *map*. About 10% of each month's sales are placed only at routing-key or county level, which the default filter hides. Another 44% are pooled into town-centre stacks.
  - **Nominatim reads an address as a hierarchy**, so one part it does not know stops the match. "8 Clover Avenue, Broom Heights, Midleton" found nothing and fell back to Midleton. "24 Knightswood Crescent, Knightswood, Williamstown" fell back to the county, though Knightswood Crescent is in OSM. The ladder (D-035) drops leading parts, never middle ones.
  - **A building's name was taken for an address:** 3,312 homes in Adamstown, Clonsilla and Sandymount sat on their railway stations, because the stations are named after the suburbs. Schools, hotels, offices and courthouses matched the same way.
  - Misspellings in the PPR ("Steplechase Hill") and estates never mapped in OSM stay at town level.
- **Options:**
  - (a) A full Nominatim re-run with a longer ladder: slower, and it fixes only the middle-part problem.
  - (b) Our own gazetteer, matched part by part in Python, needing no Nominatim.
  - (c) Paid Eircode lookup (D-003): still the owner's decision.
- **Choice:** (b), as a pass inside the fallback step, plus a rule fix.
  - **`gazetteer_feature`** (migration 0007), rebuilt by `ppr gazetteer` / `make gazetteer`:
    - **OSM**, from the extract we already have: named streets (segments of one name within 250 m merged), named residential estates and apartment buildings, 380k address points, and place nodes.
    - **Official places:** townlands and CSO settlements, each reaching as far as its area suggests (capped at 4 km).
    - **New source: the DHLGH National Housing Development Surveys 2011 and 2012.** These are 4,820 named developments with ITM coordinates, many built in 2005–2012 and never mapped in OSM. The 2013 and later surveys dropped the coordinates. Other sources were checked and not used:
      - Eircode routing-key boundaries exist only as an unofficial Small Area approximation. An Post says they cannot place a property.
      - Recent planning applications have no coordinates, and their addresses describe sites, not estate names.
      - logainm.ie needs an API key (ask first).
  - **Matching** (`geocode/local.py`): each part of the address is looked up on its own in its county. A street, estate or house number is accepted only if it lies near a place named *later* in the same address (the first later part that names one). Every other named place must also lie within 20 km.
    - **No anchor, no match:** "Main Street" is in every town.
    - **Cities never anchor:** Dublin has several Oak Parks. A city is still checked when it is named.
    - **Same-named candidates more than 1 km apart** are ambiguous and rejected.
    - **A name made only of street words** ("The Park", "The Green") is anchored only by the part right after it, usually its estate.
    - **A part that is itself a townland or village name** is left to the locality steps, even when an estate shares its name.
    - **One-letter misspellings** are forgiven only in a long, distinctive word of a name of two or more words, and only when exactly one such name exists in the county. Such matches are labelled `…_fuzzy`.
    - **A Nominatim street may become the exact house**, but only within 1.5 km of it.
  - **Methods:** `osm:address` (exact), `osm:street`, `osm:estate`, `nhds:estate`, with `_fuzzy` variants (street level). Every match is logged in `geocode_attempt` (method `local`, step 80). The results are recomputed on every run, like the other fallbacks.
  - **Rule fix:** a Nominatim building counts as a street-level match only if it is a residential type (apartments, house, terrace, residential, `yes`…). Stored results that break the new rule are re-checked on the next run and go through the later steps again.
- **Result (2026-09-30, run 17, 5 min):** precise points (exact or street) rose from 333,818 to 417,402 properties (45.8% to 57.3%): exact 68,423 → 100,967, street 265,395 → 316,435, locality 324,320 → 248,381, routing key 28,864 → 26,427, county 41,458 → 36,250. The local pass placed 32,544 at the house and 68,193 on the street; 3,667 Nominatim building matches were re-checked. The first attempt (29 Sept) never finished: see the next point.
- **Fix, 2026-09-30:** the fallbacks reset a third of all properties to `unmatched` inside one transaction, so the planner still believed there were almost none and re-ran the routing-key median once per property. The medians are now materialised and `property` is analysed after the reset.
- **Licence:** the surveys are **CC BY-SA 4.0**. We use them only to place estates, and the derived coordinates are published with the credit line in `config/sources.yaml`. Like ODbL for OSM (R-06), share-alike may apply to a database we distribute. **Owner to confirm.** Setting `nhds.use: false` and rebuilding removes them.
- **Status:** Accepted (implementation detail); the licence point awaits the owner.

---

*Phase 5 (search, area pages, saved searches, alerts, calculators, admin) decisions, from 2026-09-30.*

## D-047 Search: one matching function for the map, the list, search and alerts

- **Context:** the brief asks for search by county, area, Eircode routing key, radius, price, date, type, market flags, VAT and distance to transport or school, with results as a list and a map, synced, and a shareable URL. The map and its list already shared `tile_matching_sales` (D-038) for price, date, type and flags.
- **Options:** (a) a separate search query in the API; (b) extend the tiles' function and have everything call it.
- **Choice:** (b).
  - **Filters (migration 0008):** `county`, `area` (slugs of any area kind; a Small Area or ED matches only exact and street points, which are the only ones joined to them, D-035), `routingKey` (a Dublin key also matches addresses filed with only "Dublin 8"), `near` + `radiusM` (≤ 20 km), `vat`, `maxStopM`, `maxSchoolM`. Lists are one comma-separated parameter, as Martin passes query strings.
  - **Speed:** the function stays one plain SELECT that reads the parameters inline. Postgres inlines it, and the immutable parameter parsers on a known object fold to constants. A first version that parsed the parameters once in a CTE was ten times slower (z10 tile 1.7 s against 0.1 s), because the planner could no longer see the values.
  - **`/search`** calls the function over the smallest box the place filters allow (a county's box is widened by 0.05°, because a property may lie up to 2 km outside its county, D-035) and returns each property once with its latest matching sale, the total and the box of all matches. On the full data: 0.1 to 0.5 s for a place, 1.3 s for all of Ireland, 2.1 s sorted by price change.
  - **Price change** is shown and sortable only between two plain market sales (not "not full market price", not VAT-exclusive, not bulk, not a possible repeat filing), as on the property page (D-043), and is labelled as not adjusted for inflation or work done.
  - **Autocomplete** reads only our tables (D-006): areas by name, routing keys and Dublin districts ("d8", "Dublin 6W"), and addresses where every word appears (common short forms expanded). 0.13 to 0.3 s.
  - **Search history** records a search once the user has settled on it for 2.5 s, not every keystroke. Repeats move to the top. The coordinates of "my location" are never stored (docs/permissions.md); the entry keeps `near=my-location`. Both history lists are now paginated (closes that item of D-042).
  - **Rate limits** follow docs/permissions.md: 60 searches a minute per IP hash anonymously, 300 signed in; autocomplete 120 and 300.
  - **Pages:** `/search` has the place box, "Near my location" (asked only on click, with the reason), the filters, a sort, the results and a map of the same matches drawn from the same tiles. The home hero has the same place box. The map explorer shows place filters from a search and can remove them.
- **Also fixed:** Small Area slugs of merged areas contained a slash (`sa-268003013/268003018`), which cannot sit in one URL path segment. They now use a hyphen; migration 0008 rewrites the 2,082 stored slugs.
- **Status:** Accepted (implementation detail).

## D-048 Calculators and VAT estimates on verified, dated rates

- **Context:** the brief asks for a stamp duty and a mortgage affordability calculator with every rate in one config file, verified first (R-10). D-015 asks for a labelled VAT-inclusive estimate on new-build prices.
- **Verified on 2026-09-30** (`config/rates.yaml`, each value with its URL):
  - **Stamp duty** (Revenue, page updated 22 Oct 2025): 1% up to €1m, 2% from €1m to €1.5m, 6% above €1.5m, for instruments from 2 Oct 2024. On a new home the duty is on the VAT-exclusive price (Revenue's example: €400,000 including 13.5% VAT is €352,422.90). Not covered: three or more apartments in one block, the 15% rate on ten or more houses, reliefs.
  - **VAT on new homes:** the reduced rate, 13.5%, has applied since 1 Jan 2003, so for every PPR year. Since 8 Oct 2025 (to 31 Dec 2030) a *qualifying apartment* (in a multi-storey block of at least three apartments with shared access; not student or other rated accommodation) is at the second reduced rate, 9% (Revenue's Tax and Duty Manual; current rates page).
  - **Central Bank mortgage measures** (from 1 Jan 2023): loan-to-income 4 times gross income for first-time buyers and 3.5 for others, none for buy-to-let; loan-to-value 90% for both, 70% for buy-to-let; lenders may exceed the limits for 15% (10% buy-to-let) of their lending. The 8 Apr 2026 change exempts some bridging loans only.
- **Choice:**
  - The backend loads the file through a strict model: a null or missing value fails to load, and the calculators answer 503 instead of calculating. Every answer names its sources and their check dates, and the rules version.
  - **Affordability** is the lower of the income limit (plus the deposit) and the deposit limit, and says which one applies. It shows a monthly repayment only at a rate the user enters: quoting a "typical" rate would be advice we cannot keep current.
  - **VAT estimates:** a VAT-exclusive sale gets its price with VAT at the rate for its sale date. The PPR does not say whether a new home is an apartment, so from 8 Oct 2025 a second estimate at 9% is shown "if a qualifying apartment". Both are labelled estimates, never the price paid.
- **Upkeep:** re-check the file after each Budget (October) and Central Bank review (usually December); change `verified_on` and `rules_version` with it.
- **Status:** Accepted (implementation detail; the values are facts checked at source).

## D-049 Area pages: the brief's figures, Ireland as a real area, and honest small numbers

- **Context:** the brief asks for area pages (county, town, Small Area) with the median over time, sales volume, price distribution and a comparison with national figures.
- **Choice:**
  - **Ireland is an area.** The aggregate step adds `area` kind `country` (`ireland`, the counties' display shapes merged) and counts every market sale towards it, so national medians are real medians, not averages of county medians.
  - **Headline:** the latest complete 12 months (no provisional month) against the 12 months a year earlier, and against Ireland over the same months. Small Areas and townlands have yearly statistics only (D-037), so theirs is the latest complete calendar year.
  - **Series:** any period kind the area has, all or new or second-hand, with Ireland's line in grey (the "highlight one, grey the rest" pattern; blue and grey validated with the dataviz checks on both themes). Suppressed periods are gaps; provisional ones dashed. Rolling windows start in December 2010, the first with 12 months of register. Every value is in a table view.
  - **Distribution** is counted from market sales over the headline window in 15 bands, with Ireland's share per band as a tick. A band with fewer than 5 sales shows no count; if no band reaches 5, the page says so instead of drawing it.
  - **What else is known:** Pobal deprivation for EDs, and a Small Area's ED's, labelled as the ED's (D-011). Three EDs have no Pobal value and show nothing.
  - **Point-based areas:** Small Areas and EDs count only sales placed at their house or street (D-035); their pages say so.
  - **Links:** county tiles on the home page, the property page's area list and the area page's parents and children all link to area pages; each area links to its sales on the map and in search, and can be saved to the wishlist.
- **Not done:** a CSO comparison on area pages waits for the CSO index, which the price estimate loads (D-020).
- **Status:** Accepted (implementation detail).

## D-050 Saved searches and alerts: "new" means newly filed, and only verified addresses

- **Context:** the brief asks for saved searches with email alerts "when a new sale matches my filters", weekly or on each data update, and email verification before alerts are active. D-042 left open that unverified accounts hold the full `user` role.
- **What "new" means:** the PPR is filed weeks after a sale closes, and the register is re-published whole (D-001). A sale is new to a search when the ingest run that first saw it (`sale.first_seen_run_id`) is later than the run the search was last checked against (`saved_search.alerted_through_run_id`, migration 0009). A new saved search starts from the register as it is, so its first alert is not the whole back catalogue. The email says a new sale may be months old.
- **When:** only after the data is complete: the newest PPR ingest that a later aggregate run followed. Before geocoding, a new property has no location and matches nothing.
- **Frequencies:** "on each data update" (the scheduler checks every 15 minutes; nothing is due until an update completes) and "weekly" (Mondays 07:00, Irish time, covering any updates that week). Both send nothing when nothing new matches.
- **Who:** active accounts with a verified email and `alert:receive`; the job checks, not only the UI. Saving searches and setting alerts are allowed before verification, and the pages say alerts wait for it.
- **At most once:** `alert_delivery` is unique on (search, update), claimed before the email is sent, so two runs cannot double-send; a failed send is recorded as `failed` and not retried automatically.
- **Unsubscribe:** each email has a one-click link (and a `List-Unsubscribe` header) with an HMAC token for that search. The page asks before switching it off, so a mail scanner opening the link changes nothing.
- **CSV export:** the matches in the search's order, capped by role (500 rows and 10 a day for a user; docs/permissions.md), with the PSRA notice and the ODbL notice for coordinates (R-06) as leading `#` lines, and formula-like cells quoted.
- **Status:** Accepted (implementation detail; closes the alerts item of D-042).

## D-051 Jobs: RQ workers and a scheduler that only queues

- **Context:** D-007 chose RQ plus APScheduler; until now the worker container slept. Alerts, the daily purge (D-041) and admin-triggered pipeline runs need it.
- **Choice:**
  - `worker`: `rq worker pipeline default`. Pipeline steps run on `pipeline` (6-hour timeout), alerts and housekeeping on `default`. It mounts `data/`, so it uses the same downloads as the `make` targets.
  - `scheduler`: APScheduler in Europe/Dublin time, which only queues jobs: alerts every 15 minutes and Mondays at 07:00, housekeeping daily at 03:30, and the monthly pipeline on the 2nd at 02:00 only with `SCHEDULE_PIPELINE=true` (off by default: it downloads the register and needs the geocoder).
  - Pipeline jobs live in the pipeline package (`ppr_pipeline.jobs.run`) and are queued by name, so the API never imports the pipeline. Runs started for an admin record them in `ingest_run.triggered_by`.
- **Status:** Accepted (implementation of D-007).

## D-052 Removal requests and the admin area

- **Context:** the brief asks for a process for address removal and correction requests, and an admin area: ingest dashboard, manual geocode correction, request handling, and user management with role changes and an audit log.
- **Choice:**
  - **Requests** need no account (`POST /reports`, the `/report` page, linked from every property page). A hidden field traps simple bots without a CAPTCHA (no third-party script, D-021), and there are 5 an hour per IP. The requester gets a reference, and an email only if they give an address. Their email and message are deleted 12 months after the decision, by the daily housekeeping job.
  - **Deciding:** approving "stop showing this address" sets `is_suppressed`, which hides the property from the map, search, lists, pages and hover cards at once; its sales stay in area figures, because the PPR itself is public and removing them would bend the statistics. A decided request is final (a new request can be made). The audit log records status changes only, never the requester's email or message.
  - **Geocode review** lists what most needs a look: precise points far from their Eircode routing key, points placed only by routing key or county, and town-level ones, newest sales first. A correction re-joins the property's areas, locks it against later runs (`geocode_locked`), and changes its hover card at once; distances, price hexes and map tiles follow at the next runs. Admins are told to use only open or official sources for the point.
  - **Users:** activating and deactivating (which signs the account out everywhere), and role changes with the admin's own password again. Everyone keeps `user`; nobody can deactivate themselves; the last active admin cannot lose the role (docs/permissions.md). The first admin is made on the command line (`grant-role`), which is itself audit-logged.
  - **Ingest runs:** every run with its counts and stats, failed rows, and a form that queues a step for the worker (D-051), recording which admin asked.
- **Not built:** merging and splitting properties (the dedupe corrections in docs/api.md). The pipeline does not collect merge candidates yet either (D-030); both wait until the owner wants them.
- **Privacy policy:** updated (version 2026-09-30) for search history, saved searches, alerts and requests.
- **Status:** Accepted (implementation detail).

## D-053 The price estimate, comparable sales and the CSO index

- **Context:** D-020 (accepted with Q-10) asks for an index-based estimate with a range from the regional dispersion of repeat-sale errors; the brief asks for comparable sales ("same street and within 500 m, last 24 months"); D-049 left the CSO comparison on area pages until the index was loaded.
- **Index:** CSO table HPM09 (monthly RPPI, 2015 = 100, CC BY 4.0), loaded whole by `ppr ingest cso_rppi` (`make benchmarks`, also a worker step and part of the monthly run) into `benchmark_series` as `rppi:<CSO code>`. A changed layout or an empty file fails the run and keeps the old index. Checked 2026-09-30: 20 series, Jan 2005 (regions Jan 2010) to Jul 2026.
- **Which series:** the PPR does not say house or apartment. A property with a unit (Apt, Unit, Flat) follows Dublin apartments or national-excluding-Dublin apartments; the rest follow their region's house series (the CSO's regions, `app/services/rppi.py`). Dublin's four council-area house series are not used: an address does not say which council it is in.
- **Estimate:** the last plain market sale (not below market price, not bulk, not a possible repeat filing, VAT included) × index now / index in the sale's month. Not given when the home is placed less precisely than its street, has no such sale, sold within six months of the latest index month (that sale is the better guide), or sold before its series starts. Rounded to €1,000. The page leads with the range, gives the central figure second, and shows the sale, the index change and the range's basis. Information, not a valuation.
- **Range (calibration):** every pair of consecutive plain market sales of one exact- or street-placed property, at least six months apart, gives an error ln(second price / price the index implied). The 10th and 90th percentiles per series and band of years between sales (under 3, 3 to 7, 7+) set the range; a series with fewer than 150 pairs in a band uses all of Ireland's, and the page says so. Rebuilt with each index load into `estimate_calibration` (migration 0010).
- **Result (2026-10-01):** 40,004 pairs. Dublin houses, 7+ years apart: 8 in 10 between −18.9% and +46% of the index (4,463 pairs). Repeat sales land a median 0–11% above the index, more within 3 years, and the upper tail is long (+60% to +95%): homes that sell again soon have often been improved, which the index cannot know. The range shows this instead of the central figure absorbing it. 292,996 of 728,460 properties get an estimate; 311,058 are placed too roughly, 109,403 have no plain market sale, 15,003 sold too recently.
- **Comparables:** market sales (not below market price, bulk or possible repeats) of other exact- or street-placed homes within `radiusM` (default 500 m, 100 to 2,000) in the last `months` (default 24) of the register, the latest sale per home. Same street or estate first, then nearest. "Same street" means the addresses share a street or estate part (`address_street_parts`, migration 0010: every part but the town, without house numbers), so it is labelled "same street or place": rural addresses share townland names. Homes placed at the same street point show "same map point", not "0 m". The median leaves out VAT-exclusive prices. The page says these are sales nearby, not like-for-like homes: the register has no size or bedrooms (D-023). 0.2 s on the dev stack.
- **Area pages:** the region's index change over its latest 12 months next to the area's own median change, saying that the index allows for the mix of homes and a median does not. Ireland uses the national all-properties series. Area pages are cached per data version and index load, so a reload of the index alone shows at once.
- **Status:** Accepted (implementation of D-020; closes D-049's open item).

## D-054 Map filters are always planned with their values

- **Context:** after picking a place in search, "Open on the map" showed the basemap but no sales. With an `area` filter, `sales_tiles` took about 12 ms for a connection's first five tiles and over 30 s from the sixth. PL/pgSQL caches the plans of its statements, and Postgres then switched to a generic plan, where the `tile_param_*` calls no longer fold to constants (migration 0008 relies on that folding). Martin reuses its connections, so a few tiles in, every one of its connections was busy with a stuck tile and no tiles were served. The API had the same exposure: psycopg prepares a statement on its sixth run, and the list for an area went from 36 ms to 6 s on a generic plan.
- **Options:** (a) `plan_cache_mode = force_custom_plan` where the filters are planned; (b) rewrite the tile functions as dynamic SQL (`EXECUTE`); (c) restructure `tile_matching_sales` so that a generic plan is also fast.
- **Choice:** (a). `sales_tiles` carries the setting itself (migration 0011), which covers Martin without changing its connection string, and the API's engine sets it for its connections (`app/db.py`), which covers the list, `/search`, saved searches and alerts. A custom plan costs about a millisecond per query. (b) would mean rewriting every filter as quoted strings; (c) would give up the planning-time folding that made the function fast (0008).
- **Status:** Accepted (fix).

## D-055 The /sources page lists only what the site shows

- **Context:** `/sources` was still the Phase 2 placeholder ("arrives in Phase 2") in Phase 5, though the footer sends every visitor there for licences. `config/sources.yaml` lists every source the pipeline *may* use, and `use: true` only allows one: planning, zoning, CSO census and crime, EPA radon and noise and the Department of Education lists are allowed but not loaded, and two of them have a licence still to confirm.
- **Options:** (a) list every `use: true` source as in use; (b) derive "in use" from `ingest_run`, whose kinds do not map one to one onto the file's keys (OSM feeds geocoding, amenities and schools); (c) a `loaded` flag per source in the file.
- **Choice:** (c). `loaded: true` means the site shows data from the source; the pipeline refuses `loaded` without `use`, and a test refuses `loaded` without `verified`. `GET /api/v1/sources` reads the file and returns `inUse`, `planned` and `notUsed`; an unverified source has no check date. The page leads with the methodology (the register, how locations are placed, how prices are counted, the estimate, what the data cannot say), then the sources in use with their credit lines, the basemap and terrain credits, the planned sources and the ruled-out ones with their reasons. The `reason` lines of ruled-out sources are now written for the public; the decision numbers moved to comments. The static Pages preview has no API, so it shows the methodology without the list.
- **Status:** Accepted (implementation detail).

## D-056 The public preview moves to Vercel

- **Context:** on 2026-10-03 the owner asked to move the site to Vercel. The live site is the static preview of D-034 on GitHub Pages; nothing else is hosted (Q-04 is open). Vercel runs Next.js and static files, not FastAPI, PostGIS, Redis, the RQ workers, Martin or Nominatim, so the data server still needs a host of its own.
- **Options:** (a) the same static export on Vercel, built by Vercel's GitHub integration; (b) a Next.js server build on Vercel, which only helps once the API is reachable from the internet; (c) deploy from GitHub Actions with the Vercel CLI, which keeps D-034's "after CI" gate in the workflow but needs a Vercel token and project ids as repository secrets.
- **Choice:** (a). `frontend/vercel.json` builds with `STATIC_EXPORT=1`, and the Vercel project's Root Directory is `frontend`. Every push to `main` is a production deployment; other branches and pull requests get preview deployments. Vercel serves the site at the domain root, so the `PAGES_BASE_PATH` base path is gone. `make e2e-static` and a CI job on `main` (`Static preview`) run the route smoke tests against the export as Vercel serves it (`E2E_STATIC=1`, `e2e/serve-export.mjs`). `.github/workflows/pages.yml` is removed. GitHub Pages now serves only a redirect page (`.github/pages-redirect/`, deployed by `pages-redirect.yml`) that sends every old address, `/ppr-map/<path>`, to the same path on https://ppr-map.vercel.app, so old links keep working.
- **Serving:** `vercel.json` gives the content-hashed files (`/_next/static/`, and `/maplibre/<version>/`, whose path carries the MapLibre version) a one-year immutable `Cache-Control`; Vercel's default, `max-age=0, must-revalidate`, made browsers revalidate every script, stylesheet and font on every visit. HTML keeps the default, so a deployment shows at once. Every response carries the same security headers as Caddy in the Docker stack (`nosniff`, `strict-origin-when-cross-origin`, the Permissions-Policy). The Ignored Build Step skips a build when nothing under `frontend/` changed since the branch's last deployment (`VERCEL_GIT_PREVIOUS_SHA`); with no previous deployment, or if git cannot compare, it builds.
- **Gate:** Vercel's Deployment Checks hold a production deployment until the selected GitHub checks pass (Frontend, Playwright smoke tests, Static preview). This replaces D-034's `workflow_run` gate.
- **Why:** a one-off project setup, no secrets in the repository, preview deployments for branches, and the same tested export as before.
- **Cost:** the Hobby plan is free but for non-commercial use only. Q-02's default assumes the product is commercial, so a commercial launch on Vercel needs the Pro plan (**PAID**, ask first) or another host. A server build (b) waits until the data server has a host (Q-04).
- **Status:** Accepted (owner request, 2026-10-03).

## D-057 Fixes from the Phase 5 bug review (P0)

- **Context:** a review of Phase 5 found seven high-priority bugs that the gates did not catch. Each fix has a regression test that fails without it. Four of them change behaviour in ways worth recording.
- **Sale counts under filters:** `tile_matching_sales` counted only the sales that passed the filters, so with a date filter a property with four sales showed "1 sale", the CSV said 1, and sorting by biggest rise was all nulls (the earlier-sale lookup ran only when `n_sales > 1`). `n_sales` now counts every sale on the property that is not withdrawn, taken once per property after `DISTINCT ON` (migration 0012). `/search` materialises every match, so it leaves `n_sales` out there and counts it for the page only, and the earlier-sale lookup no longer needs the gate. On the full data the list is as fast as before or faster (all of Ireland 0.7 to 1.0 s, by change 1.7 s).
- **Hidden properties and Martin's cache:** approving a "stop showing this address" request hid the property from the database at once, but Martin kept serving cached tiles with its sale until the next monthly run, because the map's `v` parameter was the data version. `/meta` now also returns `tilesVersion`: the data version plus the latest `updated_at` of a hidden or admin-located property (a partial index, migration 0013, keeps it at about 2 ms). The map and the search map use it as `v`. It is read from the database rather than Redis, so losing Redis cannot send the map back to an old URL with stale tiles in Martin's cache. The approving API process forgets its cached `/meta` at once; other processes follow within a minute; a map already open keeps its tiles until it reloads.
- **Town parts matched to a house:** when an address's last part (its town) was queried on its own, there was no town to measure distance from, and a building with the same name counted as a street-level match. All 139 Athea sales sat on one house called "Athea" in Limerick city. A town part is often really a street (in "100 Burrin Manor, Tullow Rd, Carlow" it is "Tullow Rd"), so street and estate matches on it stay. A building matched only by name is now refused there (`building_named_like_town`), and the village or townland in the same answer wins at `locality`. A house number matched on its street is still `exact`. A normal `ppr geocode` run drops stored matches of this kind (`recheck_town_buildings`, next to the existing building recheck), and the gazetteer steps place those properties again without querying Nominatim: 1,979 properties on the dev data, Athea's now in Athea village. A whole address with only one part ("Athea, Co Limerick") has no town part, so it is not covered: 10 such matches remain.
- **The aggregate run in one transaction:** `property_summary` was truncated and refilled over 15 commits, so hover cards and wishlist comparisons returned 404 for about two minutes on every run, and a failed run left a part-filled table. `area_stats` and `price_hex` were truncated in a separate transaction that held an exclusive lock on area pages and hex tiles. The whole run, including marking it succeeded, is now one transaction, with `DELETE` instead of `TRUNCATE`. Readers keep the previous run's rows until the new rows and the new data version commit together, and a failure leaves the previous tables whole. This also fixes the P1 lock issue (#20). The cost is dead rows, so the run ends with `VACUUM (ANALYZE)` on the three tables. The space freed is reused by the next run, so the tables hold steady at about twice their live size (dev data, over four runs: `property_summary` 770 MB to 1.6 GB, `area_stats` 370 to 633 MB), in exchange for never being locked or empty. The run takes about 130 s, as before. On the dev stack, 1,047 hover cards (each a different property, so not served from Redis) and 1,047 area-stats requests made during a run all returned 200. While the run is open, an admin's hand placement waits for it to finish before it can update its hover card.
- **Also fixed (no decision needed):** the open redirect after sign-in (`/login?next=/..//evil.com`: the parser resolves dot segments into `//evil.com`, so the resolved path is now checked as well as the input); price filters in exponent form (`1e6`) that the tile functions ignored while the API echoed them back as applied (prices are now passed on in plain notation, with at most two decimal places); and the property page returning 500 for a property with no point.
- **Status:** Accepted (fixes).

## D-058 Fixes from the Phase 5 bug review (P1)

- **Context:** the P1 bugs from the same review (task.md), fixed in groups. Each fix has a regression test that fails without it. These are the ones that change behaviour or set a rule.
- **Database roles (#8):** the API, worker, scheduler and Martin all signed in as `POSTGRES_USER`, a superuser, so any SQL injection could run `COPY ... TO PROGRAM` or empty the audit log. Migration 0014 adds three roles: `ppr_app` (API, scheduler), `ppr_pipeline` (worker) and `ppr_tiles` (Martin). Docs/permissions.md, "Database roles", says what each can do. The data tables are owned by a group role, `ppr_data`, which `ppr_pipeline` belongs to. This is because Postgres 16 lets only an owner run VACUUM and ANALYZE, which the pipeline relies on (granting TRUNCATE alone was not enough). The account tables and the audit log stay with the superuser, so no service can drop or alter them. Options weighed: one non-superuser for every service (simpler, but Martin would then read sessions and password hashes); moving all ownership to the pipeline (the worker could then empty the audit log). The superuser now only runs migrations: `make migrate` passes its URL to `alembic` and to `app.cli db-roles` for that command alone. `db-roles` gives the roles their passwords from `.env`. The containers get each other's passwords blanked. Roles are shared by the whole cluster (the test database uses the same ones), so a downgrade revokes what 0014 granted and keeps the roles. Dropping a role would sign out a service still using it on another database. That happened once while testing: a test downgrade dropped `ppr_pipeline` in the middle of a dev aggregate run. A test fails if a new table is not put on one side or the other.
- **Tile limits (#9):** Caddy is built with the `caddy-ratelimit` plugin (`infra/caddy/Dockerfile`, pinned). Per IP, it allows 1,200 tile requests a minute, or 300 for tiles with filters, which are rendered for that filter alone and rarely cached. It refuses any query parameter that is not a map filter or `v`, since Martin caches by the whole URL and every junk value was a fresh 1.8 s render. A test keeps Caddy's list of names equal to `SalesFilter`. Martin's pool is cut from 20 to 8 connections, so a burst of uncached tiles cannot take the database from the API. Filter values can still vary, so the per-IP limit is what bounds the cost.
- **Other limits (#10, #11):** re-entering a password (change password, close account, admin role change) allows 5 wrong tries per account per 15 minutes; a right one resets the count. Each try is a 64 MiB argon2 verify on a 4-thread pool. `/properties` shares `/search`'s limit, and the hover summary has the documented 300 / 600 a minute.
- **Medians under 5 sales (#12, #13):** the comparables median was taken over the sales filed with VAT, which can be fewer than the count shown, and was given for any number of them. It now needs 5 and the API says how many it is of (`medianN`). The map's zoomed-out cells and its stacks of town-level sales carried a median for any count. Under 5 they now keep only their count (migration 0015) and are drawn grey, like suppressed hexes. A single sale at its address still shows its own price, as the register publishes it.
- **Hidden price bands (#14):** an area's price distribution hid bands under 5 sales but published the total and the empty bands, so a single hidden band was the total minus the rest. Once any band is hidden, empty bands are hidden too, then the smallest shown ones, until the hidden bands hold at least 5 sales between at least two of them (complementary suppression).
- **Same street (#15):** an address's last part was dropped as its town, but in "8 annesley park, ranelagh, dublin 6" or "…, clonard, co wexford" the last part is the district or county, so the suburb or town counted as a street. In a sample of 3,000 precisely placed homes, 44% had such a part (the review guessed 20%). Migration 0016 drops county and Dublin district parts in `address_street_parts`. The comparables query also leaves out parts named like a place within about 10 km (OSM places and official settlements and townlands), unless the part has a street word ("navan road"). Place names catch what text rules cannot ("ranelagh" looks like an estate). The cost is that an estate named exactly after its townland loses the flag, which only changes the order of the list.
- **12-month hexes (#16):** they counted sales after the first of the same month a year earlier, so 13 calendar months. They now use area_stats' rolling window: the 12 whole months ending with the register's latest month, and 36 for the long window.
- **School levels (#17):** any name with "Scoil" was primary, so "Scoil Phobail", "Pobalscoil", "Meánscoil", "Scoil Chuimsitheach", "Gairmscoil" and "Ardscoil" (community, secondary, comprehensive, vocational and high schools) were too. Those names are now post-primary, and an OSM `school=` tag now wins over the name. A plain "Scoil …" stays primary: nearly all are, and the post-primary exceptions are usually tagged.
- **Repeat filings (#18):** the map, list, search and alerts counted the 1,193 sales filed twice, which area stats leave out. `tile_matching_sales` and `n_sales` now leave out the flagged repeat and keep the first filing (migration 0017), and a refiled repeat no longer triggers an alert. The property page still lists both, marked.
- **Alerts and geocoding (#19):** a register update counted as ready for alerts once any aggregate run followed it. If the aggregate ran before geocoding, the new homes had no location, matched nothing, and the searches were marked as checked past that update, so those sales were never reported. Now an update is ready only when a geocode run started after the ingest finished, an aggregate run started after that geocode run finished, and no property with a sale from it is still waiting to be placed.
- **Enrich in one transaction (#21):** enrich emptied `property_enrichment` first, then loaded the sources and recomputed, so any failure left every property without vicinity values. This happened on the dev stack during this work: the worker's image still had the old code, and its OSM read failed. The sources are now read first. Then one transaction replaces the POIs, the deprivation values and the vicinity values (with DELETE, so readers keep the old rows until it commits), and a `VACUUM (ANALYZE)` follows. The same failure showed that enrich could never run in the worker: GDAL's OSM driver writes its temporary node index to the working directory, which the image cannot write to. `CPL_TMPDIR` now points at `data/work` (also for the gazetteer). On the dev data the run takes 84 s for the vicinity values of 415,657 homes.
- **One pipeline run at a time (#22):** the API refuses to queue a step while another is queued or running (409). The check and the enqueue share a Redis lock, so a double click queues one, and the admin button is disabled while its request is open. Every pipeline step (the worker's jobs and the `ppr` commands that write data) also holds a Postgres advisory lock for its whole run. That covers `make` runs beside the worker; Postgres frees the lock if the process dies. The monthly schedule logs and skips when a run is still going.
- **Re-keyed sales (#23):** a reload never moved a sale whose address now keys to another property, because the sale upsert only re-sees a sale. A sale is now moved to its new property, which unblocks fixing the address key (#36, #37). Where a sale goes, a hidden home stays hidden. A property left with no sales is retired: its wishlist entries, views and removal requests go to the home that took its latest sale, and the property is deleted. A new property that holds only one retired property's sales is the same home under a new key, so it keeps that home's position, including a hand placement. Its old public id stops working; a redirect was not worth a table while nothing links to it from outside.
- **Status:** Accepted (fixes).
