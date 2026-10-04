# Design

The site's visual style and the rules behind it. Source of truth for the values: [frontend/src/app/globals.css](frontend/src/app/globals.css) (tokens), [frontend/src/app/fonts.ts](frontend/src/app/fonts.ts) (fonts), [frontend/src/lib/price-bands.ts](frontend/src/lib/price-bands.ts) and [frontend/src/components/map/layers.ts](frontend/src/components/map/layers.ts) (map). The reasoning is in D-043 (visual design), D-044 (map legibility), D-045 (relief and 3D) and D-038 (price scale).

## Concept: record windows on a survey sheet

The site reads like a public register laid out on a surveyor's desk:

- warm paper behind;
- crisp white "record windows" on top, each with a small mono label saying what it holds (`register · 2 sales`, `register · latest entries`);
- a green register stamp carrying the real totals.

It is calm, factual and quietly official. Everything on screen should look like it could be cited.

**Principles:**

1. **Honesty is visible.** Location confidence, provisional months, suppressed figures and estimates each have their own look. They are never hidden or styled as if they were firm.
2. **Green is for the brand and actions; blue is for data.** Blue appears only in the price scale, so the two never compete.
3. **Plain and flat.** No gloss, no gradients on controls, no decoration that carries no information.
4. **The map comes first on the map page.** Place names stay above the data, and selection stays visible at every zoom.

## Colour

Tokens live on `:root` and are used through Tailwind (`bg-surface`, `text-ink`, `text-accent`…). Dark mode has values chosen for dark, not inverted ones. It follows the device setting unless the theme toggle (device, light or dark) sets `data-theme`, which is applied before first paint.

| Token | Light | Dark | Use |
|---|---|---|---|
| `desk` | `#f4f1ea` | `#121412` | page background (warm paper) |
| `surface` | `#ffffff` | `#191c1e` | windows, cards, inputs |
| `surface-2` | `#f8f6f1` | `#202426` | window bars, alternate rows |
| `fill` | `#ece8de` | `#292e30` | quiet fills, chips |
| `ink` | `#16181d` | `#ecede8` | headings, main text |
| `ink-2` | `#3c4048` | `#c5c9c4` | secondary text |
| `muted` | `#555a62` | `#a3a9a4` | captions, labels, notes |
| `line` / `line-strong` | `#e2ddd1` / `#cbc5b7` | `#2c3134` / `#3e4448` | dividers, outlines |
| `control` | `#8a877e` | `#737980` | form-control borders (3:1 against the background) |
| `accent` | `#0f6b44` | `#4ccb8a` | brand green: primary buttons, links, focus ring, the key phrase |
| `accent-strong` | `#0b5234` | `#7fdcab` | hover and pressed states |
| `accent-wash` | `#e2f1e8` | `#16301f` | selected and highlighted backgrounds |
| `band` / `on-band` | `#16181d` / `#efeee9` | `#1d2123` / `#ecede8` | dark full-width band ("what you will not find here") |
| `glass` | paper at 86% | dark at 84% | the sticky header's backdrop |
| `sign` | `#c9302a` | `#bb342c` | a red in the palette; not used by components at present |

Every text pair is checked to at least 4.5:1, and control borders to 3:1.

## Typography

| Role | Face | Notes |
|---|---|---|
| Headings (`font-display`) | **Fraunces**, a soft serif | The one phrase that matters is set in Fraunces *italic* in `accent` green (e.g. "on the record."). There is no highlighter. |
| Body (`font-sans`) | **IBM Plex Sans** | Big figures stay in the sans with tabular digits (`tabular-nums`). |
| Labels (`font-mono`) | **IBM Plex Mono** | Window-bar labels and the `.eyebrow` (12 px, 0.04em tracking, muted). |

All fonts are self-hosted with next/font. There is no handwriting face. Headings are tight: page titles about `text-4xl`/`text-5xl` with `leading-[1.02]` and `tracking-[-0.015em]`.

## Shape, depth and layout

- **Radii:** windows 14 px (`--radius-window`), controls 10 px (`--radius-control`), chips fully rounded.
- **Window shadow:** a soft two-layer drop shadow plus a 1 px `line` outline. In dark mode it is deeper and black.
- **Content width:** reading pages use about `max-w-4xl` with `px-4` gutters. The map page is full bleed.
- **Header:** a sticky glass header with the register's date in a status pill. The provisional window opens from it. On phones the navigation folds into a menu sheet.
- **Home only:** faint map contour lines sit behind the hero, drawn from a fixed formula. Nothing else has a pattern.

## Components

| Component | Look |
|---|---|
| `.window` + `.window-bar` | White card with a mono label bar (`register · …`) and a map pin. The bar is not a fake title bar with window buttons. |
| `.btn-primary` | Flat green with white text and 10 px corners; darker green on hover. |
| `.btn-secondary` | White with a `line-strong` inset border. |
| `.btn-sm` | 36 px high. Default buttons are 44 px (touch target). |
| `.chip` | Small rounded label, e.g. the confidence chip. |
| `.eyebrow` | Mono kicker above titles (`register · county Carlow`). |
| Confidence chip / marks | Solid mark for `exact` and `street`; a ring for town-level (`locality`, `routing_key`, `county`); "Not located" for `unmatched`. Drawn the same everywhere as on the map. |
| County tiles | Irish number-plate index marks (D, C, KK…) with sales and median as plain figures. |
| Status icon | A register page, not a pulsing "live" dot. |
| Charts | Provisional months are a lighter, labelled step, and every chart has a table view. Suppressed points (n < 5) have no value and are never drawn as zero. Open bug P1 #31: sparse series are currently bridged across gaps. |

## The map

- **Basemap:** the Protomaps light flavour, self-hosted. It stays light in both themes, because the price scale was validated against its land colour (`#e2dfda`). Road casings are `#c9c2b5`. Buildings are warm grey with edges, and raised from z14 **only where OSM records a height**. Hill shading fades at street zoom. The 3D view tilts to 60° and raises the terrain ×1.5.
- **Price scale:** four blues, light to dark, all colour-blind-safe. Suppressed values are grey `#9a9690`.

| Band | Colour |
|---|---|
| Under €200k | `#5598e7` |
| €200k–€350k | `#2a78d6` |
| €350k–€550k | `#1c5cab` |
| €550k and over | `#0d366b` |

- **Groups (below z14):** bubbles sized by count on one log scale and coloured by their median. Counts of 10 or more are printed on the bubble (1.2k, 12k): ink on the lightest band, white on the rest.
- **Single sales (z14 and closer):** precise points are dots. Town-level points are hollow, as stacks.
- **Selection:** a price-coloured dot with an ink ring and a soft halo, drawn above everything. The card follows its sale and docks in a corner when the sale leaves the view (always docked on phones). Escape or a click on empty map clears it.
- **Labels:** the data layers sit beneath the basemap's labels. Town names get a 2 px white halo. A count that would collide with a name is dropped.

## Accessibility and motion

- WCAG 2.1 AA:
  - `:focus-visible` is a 3 px `accent` outline with a 2 px offset;
  - every hover has a tap and a keyboard equivalent;
  - the map always has a synced list;
  - selected rows carry `aria-current`.
- `prefers-reduced-motion` turns off animations and transitions.
- Geolocation is asked for only after a button press.

## Voice and copy

- Plain words and short sentences. Say where a number comes from and what it can't tell you (for example, "nearby sales, not like-for-like homes").
- Label estimates as estimates and provisional data as provisional. Calculators and the estimate say "information only".
- Don't oversell. The data's limits are presented as a reason to trust the site: the "what you will not find here" band on the home page.
- Every page shows the PSRA attribution.

## Avoid

These were tried and dropped, or ruled out, in D-043:

- the reference site's yellow highlighter, typeface or patterned background;
- glossy pill buttons;
- tilted floating cards, sticky notes or stickers;
- red count bubbles;
- a pulsing "live" dot;
- handwriting fonts;
- blue used for anything but data;
- guessed building heights;
- a dark basemap;
- any third-party font or tile request at view time.
