# Final goal

**Make Ireland's Property Price Register (PPR) honestly explorable: every residential sale since 2010 on a fast map, with each sale's history, how precisely it is placed, and the context of its neighbourhood. No number on the site is invented or overstated.**

Working name: `ppr-map` (the product name and domain are not decided, Q-07).

## Who it is for

- **Home buyers and sellers** checking what homes on a street or in an area really sold for, and how prices moved.
- **Researchers, journalists and analysts** who need clean, citable figures (market sales only, provisional months flagged, small samples suppressed) and a shareable URL for every view.
- **Investors and the curious** comparing areas, trends and repeat-sale histories.

## What "done" looks like

The product is ready for a public launch when all of these hold:

1. **Core experience works on real data:** map, search, property pages, area pages, accounts, saved searches with alerts, calculators, estimate and comparables. *(Built through Phase 5; P1 bugs still open, see [task.md](task.md).)*
2. **The differentiators competitors lack are live** (see [docs/research/competitive-analysis.md](docs/research/competitive-analysis.md) §4):
   - location honesty on every point;
   - clean statistics;
   - repeat-sale histories;
   - planning applications next to prices;
   - an environment panel (radon, noise, zoning; flood as a link only);
   - precomputed vicinity;
   - an indicative rental yield;
   - our figures shown next to the CSO's;
   - a transparent estimate;
   - no ad-tech;
   - CSV export and research access;
   - sold-price alerts.
3. **Known bugs P0 to P2 are fixed** and every fix has a regression test.
4. **Legal and privacy groundwork is done before launch:**
   - a GDPR legitimate-interests assessment and DPIA (R-07);
   - ODbL handling of OSM-derived coordinates in exports (R-06);
   - final privacy and terms pages;
   - a working removal process (built, D-052).
5. **Hosting is chosen and running** (Q-04): the data server (PostGIS, API, Martin, workers, Redis), an EU email provider, and object storage for the basemap. The monthly pipeline runs on a schedule. The current Vercel preview is static only and its Hobby plan is non-commercial (D-056).
6. **Accessibility and performance targets are met:**
   - WCAG 2.1 AA;
   - hover card under 100 ms;
   - the map stays fast with every sale in Ireland.

## Principles that do not bend

These come from [CONVENTIONS.md](CONVENTIONS.md) and the owner:

- **Never fake data.** No invented bedrooms, floor areas, photos or coordinates. When a requirement conflicts with what the data allows, say so and propose an alternative.
- **Every location carries its confidence:** `exact`, `street`, `locality`, `routing_key`, `county` or `unmatched`. The UI shows it.
- **Default figures use market sales only.** Non-market and bulk sales are excluded by default, with a toggle to include them.
- **Small groups are suppressed:** no aggregate is shown for fewer than 5 sales.
- **Recent data is flagged:** the latest two months are provisional.
- **Privacy:**
  - no dataset that could identify owners or occupants is ever joined;
  - the hover card never calls a third party;
  - no third-party ad or tracking scripts.
- **Data comes through official channels only.** Nothing is scraped against a site's terms (D-016).
- **Ask the owner first** before any paid service, API sign-up or contact with a third party.

## Non-goals

- **Licensed listing attributes** (beds, m², BER, asking price): Q-09 answered no. We compete on the map, statistics, planning, environment and transparency instead.
- **A per-property flood flag:** blocked by the OPW CC BY-NC-ND licence, so the site links to the official maps instead (D-010).
- **Broadband availability:** there is no open data for it (D-014).
- **Valuations:** the estimate is an index calculation with a range, labelled as information, not a valuation (D-020, D-053).

## Decisions still with the owner

These are in [docs/RISKS-AND-QUESTIONS.md](docs/RISKS-AND-QUESTIONS.md). Each has a documented default that we work to until it is answered.

| Q | Question | Working default |
|---|---|---|
| Q-01 | Ask for an Eircode ECAD quote? (paid; it would give house-level points) | Build the free geocoding cascade |
| Q-02 | Is the product commercial? | Assume yes: no flood data, no agent advertising |
| Q-03 | May we contact OPW, Pobal and Tailte Éireann about licences? | Contact no one |
| Q-04 | Where to host, and which email and storage providers? | Local Docker only, plus the Vercel static preview |
| Q-07 | Product name and domain? | `ppr-map` |
