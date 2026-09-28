# External services and data sources

- **Checked on:** 2026-09-26.
- **Status meanings:** "Verified" means I read the licence or access method at the source or on data.gov.ie. "Unverified" means it still needs a human check before we depend on it.
- **Cost:** nothing here is paid unless marked **PAID**. Per the working rules, no paid service is added without your approval.

## Data sources (batch, no per-request runtime calls)

| Source | Purpose | Access | Licence | Update cadence | Env var | Status |
|---|---|---|---|---|---|---|
| **PSRA Residential Property Price Register** | core sales data | `PPR-ALL.zip` (19 MB) from propertypriceregister.ie, no key | PSRA re-use terms (PSI regulations): free re-use in any format, commercial allowed. Conditions: acknowledge the source and PSRA copyright, reproduce accurately, don't use it misleadingly, and **don't use it for the principal purpose of advertising or promoting a particular product or service**. The Dublin subset on data.gov.ie is labelled CC BY 4.0. | File refreshed frequently (timestamp 3 days before download). Sales filed with a lag of weeks. | `PPR_DOWNLOAD_URL` | Verified (psr.ie re-use page, last updated 2022-07-29) |
| **OpenStreetMap (Geofabrik Ireland & NI extract)** | Nominatim geocoding; amenities (shops, pharmacies, parks, gyms, restaurants); schools fallback | download `.osm.pbf`, no key | ODbL 1.0: attribution required; share-alike for derivative databases we publicly distribute (see R-06) | daily extracts; we refresh monthly | `OSM_EXTRACT_URL` | Verified: downloaded and md5-checked 2026-09-26 (D-032); used for Nominatim, amenities and schools (D-036) |
| Overpass API | ad-hoc amenity queries during development only | public endpoint | ODbL | live | `OVERPASS_URL` | Not used in production: we have the extract |
| **NTA GTFS (Transport for Ireland)** | bus, Luas, DART and rail stops | `https://www.transportforireland.ie/transitData/Data/GTFS_All.zip` (155 MB), no key | CC BY 4.0 | daily | `GTFS_URL` | Verified (data.gov.ie `nta-gtfs`; HTTP 200 on the file) |
| NTA GTFS-Realtime | not needed (no live data on cards) | API key at developer.nationaltransport.ie | – | – | – | Not used |
| **CSO Census 2022 SAPS** | population, age profile, households per Small Area | CSO SAPS CSV downloads / PxStat API | CC BY 4.0 (CSO standard) | per census; the next census is 2027, with results later | `CSO_SAPS_URL` | Access verified; per-table licence line to confirm in Phase 2 |
| **Tailte Éireann boundaries** | counties, EDs, Small Areas 2022, townlands 2026, settlements | data.gov.ie / Tailte Éireann ArcGIS open-data hub (GeoJSON, GPKG) | Tailte Éireann's data-sharing policy says released data is free to reuse, commercially too, with attribution (Creative Commons). The townlands 2026 page on data.gov.ie shows "No licence specified" in its metadata. | townlands updated 2026-04-01; SAs per census | `BOUNDARIES_BASE_URL` | Licence OK per the Tailte policy. ⚠ GeoHive hubs are being migrated from Sept 2026 (D-022). |
| **Pobal HP Deprivation Index 2022** | deprivation band | data.gov.ie CSV/XLS | CC BY 4.0 at **Electoral Division** level. Small Area level only by licence from the authors. | per census (2022 index published Nov 2023) | `POBAL_URL` | Verified (ED); the CSV is pinned in `config/sources.yaml`; loaded into `area_attribute` (D-036). SA level is an open question |
| **Dept of Education school lists** | school locations, type, enrolment | gov.ie "Data on individual schools" spreadsheets; the data.gov.ie copy is Dublin-only, 2019/20 | expected CC BY 4.0 (the department's data.gov.ie datasets are) | annual | `SCHOOLS_PRIMARY_URL`, `SCHOOLS_POST_PRIMARY_URL` | **Unverified**: gov.ie still answers 403 to automated requests (checked 2026-09-27). Phase 2 uses the OSM fallback, `amenity=school`, typed primary or post-primary only when its tags or name say so (D-036). A manual download of the national lists would replace it. |
| **OPW flood maps (NIFM, CFRAM)** | flood-risk flag | floodinfo.ie Open Spatial Data Catalogue / data.gov.ie shapefiles / WMS | **CC BY-NC-ND 4.0** (verified on the NIFM dataset). NC blocks the Pro tier; ND likely blocks deriving a per-property flag. | irregular (NIFM 2021) | `FLOOD_WMS_URL` | Verified. **Blocked** pending permission from OPW (D-010). |
| **SEAI BER Research Tool (public, anonymised)** | county-level BER distribution | registration at ndber.seai.ie; Excel/CSV export | believed CC BY 4.0 | nightly | `SEAI_BER_EXPORT_PATH` (manual download) | **Unverified** licence and location fields. The Eircode-level dataset is restricted (trusted partner + homeowner consent) and **must not be used**. |
| **CSO recorded crime CJA07** | incidents by Garda station, offence, year | PxStat API `…/ReadDataset/CJA07/CSV/1.0/en`, no key | CC BY 4.0; **"Statistics under reservation"** | annual (2003–2025 present) | `CSO_PXSTAT_BASE` | Verified. No station locations or catchments (D-012). |
| **National Planning Applications** (DHLGH / MyPlan) | planning history at or near a property; large schemes nearby | ArcGIS FeatureServer `services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer/0`, no key, 2,000 rows/page | CC BY 4.0 | weekly | `PLANNING_FEATURESERVER_URL` | Verified (507,751 rows). **Applicant name and address fields must be excluded (D-017).** |
| **Zoning: GZT** (DHLGH / MyPlan) | generalised zoning class at the property | data-housinggovie ArcGIS hub (REST, GeoJSON, SHP) | CC BY 4.0 | irregular (LAP dataset updated 2023-08-23) | `GZT_DEV_PLAN_URL`, `GZT_LAP_URL` | Verified (LAP). Not statutory: caveat required. |
| **EPA Radon Risk Map** | high radon area flag | data.gov.ie / EPA WMS | CC BY 4.0 | rare | `EPA_RADON_URL` | Licence per data.gov.ie; confirm the download format in Phase 2 |
| **EPA strategic noise maps, Round 4** | road, rail and air noise band where mapped | data.gov.ie / EEA | open (confirm the exact licence) | every 5 years (2021 data) | `EPA_NOISE_URL` | Partly verified |
| **CSO RPPI and median by Eircode routing key** | official benchmarks; the basis of the index estimate (D-020) | PxStat API, no key | CC BY 4.0 | monthly | `CSO_PXSTAT_BASE` | Table IDs to confirm in Phase 2 |
| **CSO RIQ02: RTB average monthly rent** | indicative gross yield by town | PxStat API, no key | CC BY 4.0 | quarterly | `CSO_PXSTAT_BASE` | Dataset exists; verify in Phase 2 |
| Tailte Éireann Valuation Open Data API | commercial properties nearby (optional) | REST (CSV, JSON, GeoJSON) | CC BY | periodic | `TAILTE_VALUATION_API_URL` | Per the Tailte page; low priority |
| ❌ daft.ie, ❌ landdirect.ie, ❌ propertymap.ie, ❌ OPW Property Mapping Register | – | – | Terms forbid scraping or reuse, or content is third-party copyright, or access is restricted | – | – | **Not used** (D-016). A licensed feed from a listings portal is an open question (Q-09). |
| National Broadband Plan (NBI) | broadband availability | interactive map only | – | – | – | No open data found. Out of scope (D-014). |

## Runtime services

| Service | Purpose | Free tier / cost | Licence / terms | Env var | Status |
|---|---|---|---|---|---|
| Self-hosted **Nominatim** (Docker, Ireland extract) | batch geocoding | free; ~4–8 GB RAM while importing | ODbL data, GPL software | `NOMINATIM_URL` | Proposed (D-003) |
| **Protomaps basemap** (PMTiles on object storage) | map background | free data; storage and CDN egress cost only | ODbL (OSM) attribution; fonts OFL | `NEXT_PUBLIC_BASEMAP_PMTILES_URL` (unused while served locally) | In use locally (D-039): `make basemap` extracts Ireland from the pinned build 20260926 and serves it, its fonts and sprites from our own origin. Object storage for production is still your choice. |
| **Mapterhorn terrain** (PMTiles) | hill shading and the 3D view | free data; storage and CDN egress cost only | Copernicus DEM GLO-30 licence (free and open; credit DLR e.V. and Airbus Defence and Space, provided under COPERNICUS by the EU and ESA), credited on the map | – | In use locally (D-045): `make terrain` extracts Ireland to z11 (55 MB) and serves it from our own origin. No sign-up. |
| MapTiler Cloud (dev only) | quick basemap for local dev | free tier for non-commercial / development use | MapTiler terms | `NEXT_PUBLIC_MAPTILER_KEY` | Optional; ask before signing up |
| Object storage + CDN (e.g. Cloudflare R2, S3 + CloudFront) | basemap, exports | **PAID** at scale; small free tiers | – | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Needs your choice |
| Transactional email (e.g. Postmark, SES, Resend) | verification, reset, alerts | **PAID** beyond small free tiers | provider DPA needed (GDPR) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | Needs your choice. Local dev uses Mailpit (no account needed). |
| Error tracking (Sentry) | error reporting | free developer tier | EU data region needed | `SENTRY_DSN` | Optional; ask first |
| Google sign-in (later) | OAuth login | free | Google API terms | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Deferred |
| **Eircode ECAD** via a provider (Autoaddress, Loqate, or direct) | Eircode → coordinates | **PAID**. The 2015 price list gives €0.01–€0.05 per transaction or €30k/yr corporate. A current quote is needed. | provider licence; display on a public website needs the right licence type | `EIRCODE_PROVIDER`, `EIRCODE_API_KEY` | **Decision needed** (D-003) |
| Google Maps / Geocoding | – | – | terms forbid use with non-Google maps and long caching | – | Rejected |

## App secrets (not external, listed for `.env.example`)

`DATABASE_URL`, `REDIS_URL`, `SESSION_SECRET`, `CSRF_SECRET`, `IP_HASH_SALT`, `APP_BASE_URL`, `ENVIRONMENT`.
