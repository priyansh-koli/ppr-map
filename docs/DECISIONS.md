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
  - `data_version` is the latest sale date and the PPR ingest run id (`2026-09-18.r1`).
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
