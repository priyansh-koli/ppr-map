# Competitive analysis and reusable data (2026-09-26)

**Scope:** the six sites you named, plus houseprice.ie (formerly irishhouses.ie), found during research.

**Method:** I visited each site in a browser and read its terms of use and robots.txt. For open-data sources I queried the actual services.

**Rule applied:** we reuse data only through an official open-data channel or a licence. We do not scrape sites whose terms forbid it. Where a site's underlying data is published openly elsewhere, we take it from the official source instead, which is also more reliable than scraping.

## 1. Site-by-site

### daft.ie: the main competitor for sold prices
- **What it is:** Ireland's largest listings portal (buy, rent, share, new homes, commercial). It has a newer **"House Prices / Sold"** section with 691,498 PPR sales, search by Eircode or address, and an "instant price estimate" tool.
- **Strength:** it joins PPR sales to **its own listing history**. Each sale shows asking vs sold price, beds, baths, m², dwelling type, BER and the selling agent. Nobody else has this, and we can't legally get it.
- **Weaknesses:**
  - The Sold section is list-first, with no sold-price map exploration.
  - It is heavily ad-funded: the consent banner lists 139 ad partners, and the page carries agent branding and upsells.
  - There are no repeat-sale histories, area analytics, or vicinity or environment context.
  - The methodology sits behind the cookie wall.
- **Reuse:** ❌ **Forbidden.** The terms ban robots and spiders, scraping and mirroring, and indexing content to build a database. robots.txt disallows `/api` and blocks named property bots. The only route is a commercial data partnership (see Q-09).

### houseprice.ie (formerly irishhouses.ie): the closest like-for-like
- **What it is:** a PPR search site with:
  - a Leaflet sold-price map
  - county and town medians
  - price-to-salary ratio
  - a heatmap and trends
  - instant valuation
  - a mortgage calculator
  - a journalist page and a methodology page
- **Data:** PPR, updated weekly, **from 2020 only on the map**. Beds, baths and type come from "other sources matched to the address" and are missing for many sales.
- **Weaknesses:**
  - The map shows only sales that have coordinates, and only the **50 most recent** per "Search this area". It is not a full-density map.
  - Unplaced sales fall back to town level silently.
  - Headline medians **include non-market sales**.
  - The headline "2026 vs 2025" compares a partial year with a full year, which is distorted by seasonality and the 2–3 month filing lag.
  - It is ad-funded (Google AdSense; the consent banner lists 210 partners).
- **Reuse:** we don't need its data. Everything it has that we could legally use comes from the PPR itself.

### propertymap.ie: for-sale listings on a map
- **What it is:** 13,883 **for-sale** listings aggregated from MyHome, DNG, SherryFitz and FindQO. It has:
  - a Leaflet map with county clusters
  - filters for location, price, beds, m² and house/apartment
  - map layers for satellite, dark, Irish Rail and Luas, and supermarkets
- **Weaknesses:**
  - No sold prices, PPR data, history, analytics or accounts.
  - Its CARTO basemap was showing an **"API KEY REQUIRED"** watermark during my visit (a broken third-party dependency).
- **Reuse:** ❌ robots.txt allows crawling, but the content (photos, descriptions, details) belongs to the agents and portals it aggregates. Re-scraping it would reuse third-party copyright without a licence. We won't.
- **Lesson:** active listings are a different product. Our map is about **what sold**. A "for sale nearby" layer only makes sense with a licensed feed.

### myplan.ie: planning data portal (Dept of Housing)
- **What it is:** a planning GIS portal with:
  - the National Planning Application map
  - zoning (GZT)
  - a Dublin housing supply pipeline
  - unfinished housing estates
  - solar safeguarding zones
- **Reuse:** ✅ **Open data, CC BY 4.0.** This is our best new enrichment source. Details are in section 2.

### landdirect.ie: Land Registry (Tailte Éireann)
- **What it is:** folios, title plans, and a registry map. Folios name **the registered owners**. Documents are paid per item.
- **Reuse:** ❌ **Forbidden and off-limits.** The terms ban automated access, scraping, data mining, and reusing the data on another website. Owner names would also break our core privacy rule.
- **Our use:** a "Look up this property on landdirect.ie" deep link at most, with no data pulled.

### maps.opw.ie/property: OPW Property Mapping Register Viewer
- **What it is:** a register of **State-owned** property, for public-service bodies only. Access needs registration via OPW, under Circular 11/15.
- **Reuse:** ❌ Not public, and not relevant to residential sales.

### geohive.ie: national geospatial hub (Tailte Éireann)
- **What it is:** a catalogue and map viewer for State geospatial data, with links to the Surveying Open Data Portal, the Valuation Open Data API, historic maps and imagery.
- ⚠ **Some GeoHive-hosted data hubs are being retired or migrated from September 2026.** The pipeline must pin dataset URLs in config and fail loudly when they move.
- **Reuse:** ✅ Tailte Éireann states its released data is **free to reuse, commercially too, with attribution (Creative Commons)**. This largely resolves my earlier open question about the townlands licence. Useful datasets are listed in section 2.

## 2. New open data we can legitimately use

| Source | What it gives us | Access | Licence | Verified |
|---|---|---|---|---|
| **National Planning Applications** (DHLGH, via MyPlan) | 507,751 applications since 2012, weekly. Fields: description, address, ITM coordinates, status, decision and dates, appeal, land use, site area, **number of residential units, one-off house flag, floor area**, and a link to the council file. | ArcGIS FeatureServer `services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer` (2,000 per page), plus a GeoJSON download | CC BY 4.0 | ✅ schema and count queried; last edit ≈ 2026-09-23 |
| ⚠ ↳ the same dataset contains **`ApplicantForename`, `ApplicantSurname`, `ApplicantAddress`** | – | – | – | **We must not ingest these columns.** The query `outFields` list excludes them; they are never stored or logged. |
| **Zoning: Generalised Zoning Types (GZT)** | a consistent zoning class for Development Plans and Local Area Plans | data-housinggovie ArcGIS hub (GeoJSON, SHP, REST) | CC BY 4.0 | ✅ LAP dataset. GZT is **not statutory**, so show it with a "check the development plan" caveat. |
| **EPA Radon Risk Map** | % of homes above the reference level, per 10 km grid (the high radon area flag) | data.gov.ie / EPA WMS and JSON | CC BY 4.0 | ✅ per search result; confirm the file in Phase 2 |
| **EPA strategic noise maps (Round 4, 2021)** | road, rail and airport noise contours (Lden, Lnight) for Dublin, Cork, Limerick and major roads | data.gov.ie / EEA | open (confirm the exact licence) | partly |
| **CSO RPPI and median price by Eircode routing key** (PxStat HPM tables) | the official price index and per-routing-key medians | PxStat API | CC BY 4.0 | table IDs to confirm in Phase 2 |
| **RTB Average Monthly Rent (CSO RIQ02)** | average rent by town, beds and type, quarterly | PxStat API | CC BY 4.0 | ✅ dataset exists |
| **Tailte Éireann Valuation Open Data API** | commercial rateable properties (use, floor area, NAV, ITM coordinates) for revalued local authorities | REST (CSV, JSON, GeoJSON) | CC BY | ✅ per the Tailte page. **Nice-to-have only:** mostly shops and offices, which helps with the "high street nearby" context. |
| Tailte Éireann Surveying Open Data | townlands (2026), EDs, Small Areas, settlements | data-osi ArcGIS hub | CC BY (per Tailte's data-sharing policy) | ✅ policy |

## 3. Where competitors are strong and we can't match (honestly)

- **Beds, baths, m², type, BER, and asking vs sold price.** Daft has these from its own listings. houseprice.ie has partial matches from "other sources". The PPR doesn't contain them, and every legal route to them is a commercial licence from a listings portal (Q-09).
  - Until then we show exactly what the register holds.
  - For new builds, the planning register sometimes gives a development's unit count and the floor area of one-off houses. We show that **only as planning data, labelled as such, never as the house's size**.

## 4. How we beat them

| # | Differentiator | Daft Sold | houseprice.ie | propertymap.ie | MyPlan |
|---|---|---|---|---|---|
| 1 | **Every sale since 2010 on a fast vector-tile map** with filters that change the map | list only | 2020+, 50 at a time | listings only | – |
| 2 | **Location honesty:** every point shows its geocode confidence; low-confidence sales are hollow markers or aggregate-only, never silently placed | – | silent town fallback | n/a | n/a |
| 3 | **Clean statistics:** non-market and bulk sales excluded by default (toggle); provisional months flagged; like-for-like year-on-year (same months); n and interquartile range shown | – | includes non-market; partial vs full year | – | – |
| 4 | **Repeat-sale history per property** with % change and annualised growth, plus a street-level and area repeat-sales view | partial | partial | – | – |
| 5 | **Planning next to prices:** planning history at or near this address and applications within 250 m (e.g. "42-unit scheme granted 300 m away, 2025"), plus zoning | – | – | – | map only, no prices |
| 6 | **Environment and risk panel:** radon, noise and flood (deep link), each with source and date | – | – | – | – |
| 7 | **Precomputed vicinity:** nearest stop by mode with walking distance, schools, amenities within 1 km | – | – | overlays only | – |
| 8 | **Investor view:** area median price vs RTB average rent gives an indicative gross yield (area level, labelled indicative) | – | – | – | – |
| 9 | **Cross-checked with official stats:** our routing-key medians shown next to the CSO's, so users can trust the numbers | – | – | – | – |
| 10 | **Transparent estimate:** "last sale × CSO regional index change since then", with a range and a method link. Only for properties with a prior market sale. No black box. | black box | undocumented | – | – |
| 11 | **No ad-tech:** no third-party trackers, so no consent wall; essential cookies only | 139 partners | 210 partners | – | – |
| 12 | **Research-grade access:** CSV export, API (Pro), a methodology page, citations, a shareable URL for every view | – | journalist page | copy link | open data |
| 13 | **Sold-price alerts:** "email me when a house sells on this street or matches this search" | ? | – | – | – |
| 14 | **Accessibility and mobile:** WCAG 2.1 AA, a list view synced with the map, a colour-blind-safe scale, tap cards | ? | ? | ? | ? |
| 15 | **Resilience:** self-hosted basemap (their CARTO key failure can't happen to us) | – | – | ❌ broken today | – |
