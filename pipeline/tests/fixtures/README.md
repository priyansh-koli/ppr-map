# Test fixtures

Small extracts of real data, so tests never run on invented addresses, prices or places.

| File | What it is | Source and licence |
|---|---|---|
| `ppr_sample.csv`, `ppr_bulk_sample.csv`, `ppr_carlow_2025.csv` | rows of the Property Price Register, unchanged (cp1252) | © Property Services Regulatory Authority, propertypriceregister.ie |
| `boundaries/*.gpkg` | County Carlow, the Carlow Rural ED, one Small Area, the Ballybannon townland and Carlow town | Tailte Éireann and CSO open data (attribution) |
| `nominatim/responses.json` | answers of our Nominatim (OSM extract of 2026-09-25) to the geocoder's queries for the test addresses, trimmed to the fields it reads | © OpenStreetMap contributors, ODbL 1.0 |
| `osm_pois_carlow.json` | the shops, schools and other points of interest around Carlow town, as loaded from the same extract | © OpenStreetMap contributors, ODbL 1.0 |
| `gtfs_carlow.zip` | the stops in and around Carlow town, with a sample of the trips that serve them | National Transport Authority GTFS, CC BY 4.0 |
| `pobal_carlow_rural.csv` | the Carlow Rural row of the deprivation index | Pobal HP Deprivation Index 2022 (Haase and Pratschke), CC BY 4.0 |
