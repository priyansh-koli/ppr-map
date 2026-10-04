# Product requirements (PRD)

What the product must do, and where each requirement stands. The goal and principles are in [goal.md](goal.md); decisions are referenced as D-xxx ([docs/DECISIONS.md](docs/DECISIONS.md)). Status as of **2026-10-04**.

**Status key:** ✅ Built · 🟡 Partly built · ⬜ Not built · ⛔ Blocked (licence or data)

## 1. Problem

The PPR is a 19 MB CSV of more than 800,000 sales. It has no coordinates, it has inconsistent addresses, and non-market and bulk sales sit mixed in with ordinary ones. Existing sites either show it as a list (Daft Sold), show only recent years (houseprice.ie, which starts at 2020), or fall back to town centres without saying so. Nobody shows how sure they are of a location, or keeps non-market sales out of the figures.

## 2. Users and core jobs

| User | Job |
|---|---|
| Buyer or seller | "What did homes on this street, or in this estate, sell for, and when?" |
| Researcher or journalist | "Give me clean, citable medians and counts for an area, with the method shown." |
| Investor | "How do areas compare on price trend and yield?" |
| Anyone | "Tell me when a home matching this search sells." |

## 3. Functional requirements

### Map explorer (`/map`)
| Requirement | Status | Ref |
|---|---|---|
| Every sale since 2010 on vector tiles; grouped bubbles at low zoom, single sales from z14 | ✅ | D-004, D-038, D-044 |
| Colour by price band (colour-blind-safe blues); confidence shown as a solid mark (house or street) or a ring (town level) | ✅ | D-038, D-043 |
| Hover or tap card in under 100 ms, from a precomputed summary | ✅ | ARCHITECTURE |
| A list synced with the map, for keyboard access; selection syncs both ways | ✅ | D-044 |
| Filters change the map (the same filters as search) | ✅ | D-047 |
| Hill shading, 3D view, buildings (heights only where OSM records them) | ✅ | D-045 |
| A hexagon price layer | ✅ | D-009 |
| Several sales on one spot open a chooser | ✅ | D-044 |

### Search (`/search`)
| Requirement | Status | Ref |
|---|---|---|
| Filters for county, area, Eircode routing key, radius from a point, price, date, new or second-hand, VAT, market-sale flags, distance to a stop or school | ✅ | D-047 |
| Sort by date, price, or change since the previous sale; a shareable URL for every search | ✅ | D-047 |
| Place autocomplete from our own database, with no third-party geocoder | ✅ | D-006 |

### Property page (`/property/[id]`)
| Requirement | Status | Ref |
|---|---|---|
| Full sale history, with a change column between plain market sales | ✅ | D-043 |
| Location confidence, method and caveats | ✅ | D-035 |
| Areas, area trend, vicinity (stops, schools, shops within 1 km, deprivation), each with source and date | ✅ | D-036 |
| Index-based estimate with a range (only for a prior market sale placed at street level or better) | ✅ | D-020, D-053 |
| Comparable sales nearby | ✅ | D-053 |
| VAT-inclusive estimates for new builds, labelled as estimates | ✅ | D-015, D-048 |
| Planning applications at or near the address | ⬜ (source verified, not loaded) | D-017 |
| Environment panel: radon, noise, zoning | ⬜ | D-018 |
| Flood risk | ⛔ link to OPW maps only | D-010 |

### Area pages (`/area/[slug]`)
| Requirement | Status | Ref |
|---|---|---|
| Median over time against Ireland; volume; price distribution; children (towns, EDs, Small Areas) | ✅ | D-049 |
| The CSO index change for the region next to our median | ✅ | D-053 |
| Our routing-key medians next to the CSO's | ⬜ | D-019 |
| Indicative gross yield (RTB rents) | ⬜ | D-019 |
| Crime at Garda-station level, with caveats | ⬜ | D-012 |
| BER at county level | ⬜ | D-013 |
| Deprivation (ED level) | ✅ | D-011, D-036 |

### Accounts and personal features
| Requirement | Status | Ref |
|---|---|---|
| Register with email confirmation, sign in, password reset, settings, data export, account deletion | ✅ | D-041, D-042 |
| Wishlist and compare; view and search history (kept 12 months) | ✅ | D-041 |
| Saved searches with alerts (on data update or weekly), one-click unsubscribe, CSV export | ✅ | D-050 |
| Google sign-in | ⬜ deferred | external-services |
| Pro tier: API keys (`/me/api-keys` is documented but has no route) | ⬜ | api.md |

### Tools, trust and admin
| Requirement | Status | Ref |
|---|---|---|
| Stamp duty and mortgage affordability calculators, on dated rates verified against their sources | ✅ | D-048 |
| `/sources`: methodology and licences of the sources in use | ✅ | D-055 |
| Public correction or removal request; admin queue; hiding a property | ✅ | D-052 |
| Admin: users and roles, ingest runs, geocode correction queue, audit log | ✅ | D-052 |
| Admin: merge and split properties | ⬜ | D-052 |

## 4. Data requirements

- **Ingest:** the full `PPR-ALL` file every run, diffed by row hash (D-001). Decode as cp1252 and keep the raw fields (D-002).
- **Deduplication:** sales are deduplicated into properties by exact key only. Addresses without a house number or unit are never merged (D-030).
- **Geocoding:** the free cascade (D-003, D-035, D-046). Every attempt is logged. Admin corrections are locked against later runs.
- **Bulk and portfolio sales:** flagged (D-031) and excluded by default together with "not full market price" sales.
- **Statistics:**
  - groups with n < 5 are suppressed;
  - the latest two months are provisional;
  - year-on-year changes compare complete months only.
- **New builds:** prices are VAT-exclusive as filed. Any VAT-inclusive figure is labelled an estimate.
- **Enriched values:** each one is `Sourced<T>` (value, source, as-of date).
- **Refresh:** the monthly pipeline runs ingest, gazetteer, geocode, enrich, benchmarks, then aggregate.

## 5. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Hover card under 100 ms (measured 3–10 ms). Search 0.1–0.5 s for a place, about 1 s for all of Ireland. Tiles are cached by URL (`tilesVersion`). |
| Accessibility | WCAG 2.1 AA. A list synced with the map. Every hover has a tap and keyboard equivalent. Colour-blind-safe scale. `prefers-reduced-motion` respected. |
| Privacy | No owner or occupant data joined. History deleted after 12 months. Hashed IPs. Essential cookies only. Removal process. GDPR DPIA before launch. |
| Security | Opaque server-side sessions with argon2id (D-008). CSRF protection. Rate limits per IP and per user. Audit log. Role-based permissions (docs/permissions.md). |
| Reliability | A failed pipeline step leaves the previous data in place (aggregate is one transaction, D-057). Pinned source URLs that fail loudly when they move (D-022). |
| Quality | Tests are written with each feature. Lint, mypy strict, tsc, pytest, Vitest and Playwright run in CI. Every schema change is a reversible Alembic migration. |
| Openness | Attribution footer, `/sources` page, a shareable URL for every view, CSV export. |

## 6. Out of scope

- Licensed listing data (Q-09).
- Scraping Daft, landdirect or propertymap (D-016).
- Broadband (D-014).
- A per-property flood flag (D-010).
- Live transport data.
- Guessed building heights.
