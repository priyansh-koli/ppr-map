# PPR data profile (verified 2026-09-26)

Source: `PPR-ALL.zip` from propertypriceregister.ie, downloaded 2026-09-26.
The zip holds one file, `PPR-ALL.csv` (110.6 MB, file timestamp 2026-09-23).
Reproduce with `docs/research/scripts/profile_ppr.py`.

## File format

| Property | Actual value |
|---|---|
| Rows | 807,724 data rows + 1 header |
| Encoding | **Windows-1252**. The file is not valid UTF-8. `€` is byte `0x80`, and Irish fadas (á, í, Ó, …) are single cp1252 bytes. |
| Line endings | CRLF |
| Quoting | Every field is double-quoted. Every row has exactly 9 fields. |
| Date range | 2010-01-01 to 2026-09-18 |
| Date format | `dd/mm/yyyy`. All 807,724 parse. |
| Price format | `€343,000.00`: euro sign, comma thousands, 2 decimals. All rows match `^€[\d,]+\.\d{2}$`. |

### Columns (exact header text)

| # | Header | Notes |
|---|---|---|
| 1 | `Date of Sale (dd/mm/yyyy)` | The deed date as the filer entered it, not the filing date. |
| 2 | `Address` | Free text. 74% ALL CAPS. See "Address quality" below. |
| 3 | `County` | 26 values, one per county. Sometimes wrong (see below). |
| 4 | `Eircode` | **Not "mostly empty" any more.** See "Eircode coverage". |
| 5 | `Price (€)` | Header contains a cp1252 `€`. |
| 6 | `Not Full Market Price` | `Yes` / `No` |
| 7 | `VAT Exclusive` | `Yes` / `No` |
| 8 | `Description of Property` | Two English values and three Irish-language variants (49 rows). Three rows are mojibake (`Teach/?ras?n C?naithe Nua`). |
| 9 | `Property Size Description` | 93% empty. See below. |

## Values and distributions

**Prices:** minimum €5,001, 1st percentile €24,000, median €245,000, 99th percentile €1,425,000, maximum €387,665,198.
1,098 sales are under €10k and 249 are over €20M (portfolio deals).

**Description of Property**

| Value | Rows |
|---|---|
| Second-Hand Dwelling house /Apartment | 662,984 |
| New Dwelling house /Apartment | 144,691 |
| Teach/Árasán Cónaithe Atháimhe (second-hand, Irish) | 45 |
| Teach/Árasán Cónaithe Nua (new, Irish), including 1 mojibake row | 4 |

**VAT Exclusive vs new or second-hand:** every second-hand sale has `VAT Exclusive = No`. Of the new sales, 142,314 are VAT-exclusive and 2,381 are not.

**Not Full Market Price:** 41,150 rows (5.1%). The yearly count rose from about 1,100 in 2010 to about 4,000 in 2024.

**Property Size Description:** filled for 52,845 rows, **all of them new dwellings**. It is effectively only 2010–2018 data (fewer than 150 rows from 2019 on). Five bands appear, including two overlapping spellings (`greater than 125 sq metres` and `greater than or equal to 125 sq metres`) and Irish-language variants.
➡ It is not usable as a general size field. Show it only when present, with the band as written.

### Eircode coverage (the brief assumed "mostly empty")

| Year | % with Eircode |
|---|---|
| 2010–2019 | < 0.5% |
| 2020 | 0.8% |
| 2021 | 51.4% |
| 2022–2026 | 74–77% |

250,671 rows (31%) have an Eircode. Of sales since 2024, 75% do.
Some Eircodes are wrong: 1,153 Eircodes appear against addresses that normalise differently. One example is `A65F4E2`, which is used for three unrelated addresses in different towns.
➡ Treat the Eircode as a strong hint, not as ground truth. Validate it against the address and county.

### Address quality

- 167,427 addresses (21%) contain **no digit**. These are rural townland-style addresses such as `KILLULT, GORTAHORK, CO DONEGAL`. The best location they can get is townland level.
- 44,203 addresses look like apartments (`APT`, `Apartment`, `Unit`, `Flat`). Many units share one building location.
- Heavy abbreviation (`AVE`, `RD`, `ST`, `ST JAMESS RD`), placeholder junk (`N/A`), double spaces, and inconsistent `Co.` / `CO` / `Co ` prefixes.
- Dublin: 51% of Dublin addresses have no `Dublin N` postal district in the text.
- The `County` column disagrees with an explicit `Co. X` in the address in 335 rows. There are also silent county errors, for example `CLOONFUSH, TUAM, CO GALWAY` is filed with County = Mayo.

### Duplicates and repeat sales

- 1,188 rows exactly duplicate another row's date, address and price. These may be genuine duplicate filings, or multiple units filed with one address.
- 696,573 distinct addresses after crude normalisation (lowercase, alphanumerics only). 89,250 of them have more than one sale. This is a lower bound, because fuzzy matching will merge more.

### Bulk / portfolio sales

10,169 (date, price) groups have 5 or more rows, covering 71,039 rows. The largest is 268 rows at €8,000 on 2013-12-20, then 164 rows at €194,086 on 2014-10-06.
In portfolio sales the PPR often repeats one total or averaged price against every unit, so the per-unit price is meaningless.
➡ We need a `bulk_group` heuristic and a default filter that excludes these rows.

### Reporting lag

Monthly counts for 2025 and 2026:

```
2025: 3554 4114 4518 4681 5218 4938 5834 4925 5624 5878 5245 7563
2026: 3595 4105 4853 4520 4874 5091 5710 4511 2099 (Sep partial)
```

Sales appear in the register weeks after the deed date. The last complete-looking month in this file is roughly two months back.
➡ Mark the latest two months as **provisional** in every trend and median.

### Rows per county

Dublin 253,091 · Cork 89,415 · Kildare 44,080 · Galway 38,909 · Meath 33,563 · Limerick 29,590 · Wexford 28,245 · Wicklow 27,302 · Louth 22,742 · Waterford 22,107 · Kerry 21,901 · Tipperary 21,595 · Donegal 21,422 · Mayo 19,191 · Clare 18,048 · Westmeath 15,610 · Laois 13,446 · Kilkenny 13,047 · Cavan 11,910 · Sligo 11,754 · Roscommon 11,380 · Offaly 10,308 · Carlow 8,809 · Leitrim 7,100 · Longford 6,807 · Monaghan 6,352

## Geocoding feasibility sample (public Nominatim, 2026-09-26)

40 random addresses from 2024 to 2026, 10 per stratum. Each was sent to public Nominatim, sequentially at 1 request per 1.2 s. Raw addresses were used with no normalisation. If a query failed or matched only a county, one fallback query dropped the first comma-separated part.

| Stratum | exact (house number) | street / estate | locality / townland | no match or wrong type |
|---|---|---|---|---|
| Dublin, numbered | 5 | 4 | 1 | 0 |
| Other counties, numbered | 0 | 4 | 1 | 5 |
| Rural, no number | 0 | 3 | 4 | 3 (1 no match, 2 wrong feature) |
| Apartments | 1 | 4 | 0 | 5 |
| **Total** | **6 (15%)** | **15** | **6** | **13** |

Observations:
- OSM house-number coverage is reasonable in Dublin and poor elsewhere.
- Unnormalised input costs matches, for example `N/A`, `Apartment 92  Block A`, and dropped estate names.
- There was **at least one confident wrong match**: `MOYHENNA, BREAFFY, CASTLEBAR` became *Breaffy Road Business Park*. Every result therefore needs checks, for example "does it fall inside the reported county?" and "is the returned feature type a plausible dwelling or place?".
- Rural townland names often matched correctly. OSM Ireland has complete townland polygons.

Conclusion: free OSM geocoding alone gives roughly 15–25% house-level accuracy outside Dublin. Eircode lookup (licensed) is the only route to reliable house-level points. See `docs/DECISIONS.md` D-003.
