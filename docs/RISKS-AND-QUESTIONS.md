# Risks and open questions (Phase 0)

## Open questions for you

| # | Question | Why it matters | My default if you don't decide |
|---|---|---|---|
| Q-01 | Should I request a quote for Eircode ECAD lookups (via an Eircode Provider or Eircode directly)? | It is the only route to reliable house-level points for about 250k+ sales, and 75% of new ones. | Build the free cascade; keep the ECAD hook as a no-op. |
| Q-02 | Is the product commercial (Pro tier, ads, agent listings)? | It decides whether we can use the OPW flood data (NC licence). It also touches the PSRA condition against using the data for the principal purpose of advertising or promoting a particular product or service. | Assume commercial, so no flood data and no agent advertising. |
| Q-03 | May I email OPW (flood licence), the Pobal index authors (Small Area licence) and Tailte Éireann (townlands licence)? | These are outbound contacts made on the project's behalf. | Don't contact anyone; use the fallbacks in D-010, D-011 and D-003. |
| Q-04 | Hosting: one VM (e.g. Hetzner in the EU) or managed cloud? Which email and object storage providers? | Cost, and GDPR data residency (keep it in the EU). | Local Docker Compose only until you choose. The static frontend preview is on Vercel (D-056); this question is about the data server. |
| Q-05 | May I drop `/auth/refresh` in favour of opaque sessions (D-008)? | It changes the brief's API list. | Proceed with sessions. |
| Q-06 | Minimum geocode confidence shown as a map **point**: should `locality`, `routing_key` and `county` points be hidden from the point layer and counted only in aggregates? | Otherwise thousands of rural sales pile onto one townland or county centroid and look precise. | Show `exact` and `street` as points. Show `locality` as points with a hollow marker and a jitter-free stack. Include `routing_key` and `county` in aggregates and lists only. |
| Q-07 | Is the product name or domain decided? | Needed for the Nominatim User-Agent, email sender and Terms. | Placeholder `ppr-map`. |
| Q-09 ✅ **Answered 2026-09-26: No.** | Do you want to approach a listings portal (Daft, MyHome) about **licensing** listing attributes (beds, m², BER, asking price)? | It is the only legal way to match Daft and houseprice.ie on property details. | No. We compete on the map, stats, planning, environment and transparency instead. |
| Q-10 ✅ **Answered 2026-09-26: Yes.** | Include the index-based price estimate (D-020)? | It is useful and competitors have one, but it carries a reputational risk if people misread it as a valuation. | Yes, with a range, the method shown, and a restriction to properties with a prior market sale at ≥ street confidence. |
| Q-08 | Default filters: exclude non-market and bulk sales by default? | This changes every headline median. | Yes, both excluded by default, with a visible toggle. |

## Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-01 | **Geocoding accuracy.** The sample gave 15% house-level via OSM. Rural addresses without numbers (21%) can't be better than townland level, and there are confident wrong matches. | High / High | Confidence on every point; county and feature-type checks; admin correction queue; hollow markers for low confidence; ECAD upgrade (Q-01). Phase 2 reports real per-county rates. |
| R-02 | **Portfolio and bulk sales distort medians.** 71k rows sit in same date-and-price groups of 5 or more. | High / Medium | `bulk_group` heuristic (D-031), excluded by default, reviewed on Dublin on 2026-09-26: 34,668 sales (4.3%) in 5,207 groups. |
| R-03 | **Reporting lag** makes recent months look like a price or volume drop. | Certain / Medium | Mark the latest two months provisional. Compute the 12-month change on complete months only. |
| R-04 | **PPR data errors:** wrong county (e.g. a Tuam address filed as Mayo), wrong Eircodes (1,153 shared across different addresses), typos. | Certain / Medium | Keep raw values; store both reported and geocoded county; treat the Eircode as a hint; user "report an error" link; PSRA disclaimer. |
| R-05 | **Licences:** OPW flood (NC-ND), the PSRA advertising clause, the Tailte Éireann townlands licence unspecified, SEAI BER unverified. | Medium / High | Blocked or fallback per D-010 to D-014. `/sources` page. A licence check is a Phase 2 exit criterion for each source. |
| R-06 | **ODbL share-alike.** Coordinates derived from OSM and published through CSV export or the Pro API could make our property-coordinate table a derivative database that must be offered under ODbL. | Medium / Medium | Follow the OSMF Geocoding Guideline. Exports include coordinates only with ODbL attribution and notice. Get legal review before Pro launches. |
| R-07 | **GDPR.** The PPR has no names, but address + price relates to identifiable households. Re-publishing it on a map with enrichment is processing personal data, and the DPC's remit applies. | Medium / High | Documented legitimate-interests assessment and a DPIA before public launch. Suppression process (removal requests). No joins that could identify owners. History retention of 12 months. Minimal sign-up data. Cookie consent only needed if non-essential cookies are ever added (the plan has none). |
| R-08 | **Apartments** share one building point, so hovering is impossible when points stack. | Certain / Medium | At z ≥ 16, stacked points expand into a list popover ("12 sales at this building"). |
| R-09 | **Cost of the geocoder and tile cache under traffic spikes** (e.g. media coverage). | Low / Medium | Tiles cached at the CDN keyed by data version; hover payloads precomputed; Nominatim runs only in batch. |
| R-10 | **Calculators give wrong advice** if stamp duty or Central Bank rules change. | Medium / High | Rates in one versioned config with source URLs and `verified_on` dates; values verified on 2026-09-30 (D-048); a missing value stops the calculator (503); "not financial advice" notice; no suggested interest rate. Re-check after each Budget and Central Bank review. |
| R-11 | **Deduplication mistakes** could merge two different houses and create fake repeat-sale histories. | Medium / Medium | Auto-merge only exact keys; never merge addresses without a house number or unit (D-030); Eircode and fuzzy candidates go to admin review; merge and split tools are audited. |
| R-12 | **Enrichment staleness** (e.g. a school closed, a GTFS stop moved). | Medium / Low | `asOf` shown on every enriched value; refresh schedules per source. |

| R-13 | **Upstream URL churn:** GeoHive hubs are being retired or migrated from Sept 2026. | High / Medium | D-022: pinned URLs, schema hashes, loud failures. |
| R-14 | **Personal data inside open datasets:** the planning register includes applicant names and addresses. | Certain / High | D-017 field allow-list, a test that the fields are absent, and no raw dumps in logs. |
| R-15 | **Competitors have property attributes we lack** (beds, m², BER). | Certain / Medium | Differentiate (see `research/competitive-analysis.md` §4); Q-09. |

## Where the brief differs from the real data (summary)

1. **Eircode is not mostly empty:** 74–77% of sales from 2022 on have one, but it is sometimes wrong.
2. **The size description is almost always empty**, and is only ever present for new builds, mostly 2010–2018.
3. **Flood data can't be used as planned** (NC-ND licence).
4. **Deprivation is open at ED level only**, not Small Area.
5. **Crime has no spatial catchments**, so it goes on area pages only.
6. **Broadband has no open data**, so it is dropped from v1.
7. **SEAI BER public data** can only give county-level context.
