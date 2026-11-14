---
paths:
  - "sources/catalogue/**"
  - "orthophoto.py"
  - "tools/sk_tiles.py"
---
# Providers: adding a source, their quirks, credits

What each catalogue module holds: docs/code-map/sources.md. The general rules of the sources
(`.claude/rules/sources.md`) load with the catalogue's files too.

## Pitfalls

- **New sources**: research and choose the access method with [docs/data-sources.md](docs/data-sources.md) (what to
  find out, files vs WCS vs own hosting, quick tests); first the provider's usage limits in numbers
  (docs/data-sources.md, section 1: swisstopo's table of 40 requests/min was found late, our downloads had exceeded
  it); before building, read the provider's current terms and its news or "services to be closed" lists, not only the
  survey's notes: Denmark's WCS answered normally on 2026-11-01 but was on Dataforsyningen's closing list (moving to
  Datafordeler with an API key), and its licence had changed in 2024; the researched countries are in the roadmap,
  "New data sources", and in the survey of 2026-10-31 ([docs/source-survey.md](docs/source-survey.md): 231 countries
  and regions, rows in `docs/source-survey/sources.json`); how many sources could be structured:
  [docs/sources-architecture.md](docs/sources-architecture.md) (a proposal).
- **Check georeferencing of every new source** against Copernicus DEM (shift search, see regression doc). Malta 2012
  is off by (-56 m E, -196 m N), corrected by `MALTA_2012_SHIFT`.
- **geoportal.gov.pl data comes from sheet files**, not WCS (`SheetTiles`): the EVRF2007 WCS takes 30–50 s per ASCII
  tile (generating the text, not downsampling, is the cost), its own downsampling leaves holes at coarse resolutions
  (Tatras at 5 m), its GeoTIFF output is an 8-bit picture, and the KRON86 coverages stop at 2019. Index answers are
  cached per 0.25° tile in `cache/poland/sheet-index/`. The sheet files on opendata.geoportal.gov.pl download at ~17
  MB/s; the geoportal pages give no request limits (technical contact sigservicedesk@geoportal.gov.pl). Sheet
  attributes and coverage are in docs/roadmap.md ("To check").
- **Our own Slovak tiles** come from the local mirror (`FINDALINE_MIRROR`, the folder above `slovakia/`) until they
  are on Hugging Face (`SLOVAK_TILES` in `sources/catalogue/slovakia.py`); without it `--source auto` falls back to
  `europe` and the Slovak regression test is skipped. `tools/sk_tiles.py extract` unpacks the TIFF first (GDAL's
  `/vsizip/` reads it about 60 times slower than Python's `zipfile` inflates it); `cut` reads full-width 2 km bands
  (several GB of RAM) and writes tiles on all cores: one cut at a time. `tools/sk_tiles.py average` writes `dmr5/2m`,
  `dmr5/5m` (and `dmp1/...`) next to `1m` in about 6.5 min per product on all cores (12 826 tiles with data: 23.6 and
  4.4 GB beside the DMR's 1 m folder, 26.7 and 4.9 GB beside the DMP's, measured 2026-11-04; in ZSTD since 2026-11-08,
  23.4, 4.3, 26.2 and 4.8 GB: `tools/sk_tiles.py recompress` rewrote the four folders' 51 304 files in 14.3 min and
  the cache's 26 242 copies in 6.5 min); without those folders a 2 m or 5 m grid reads the 1 m tiles as before
  (`GridResolutions.resolution`).
- **Credits** follow each provider's own wording (`tests/test_catalogue.py` keeps them: read the terms again before
  changing one); every run's ATTRIBUTION.txt, the about page and the map add `credit.PROCESSED_NOTE` (CC BY's
  "indicate if changed"; the map's copy is `viewer/src/layers.ts` `PROCESSED_NOTE`, kept equal by
  `test_processed_note_in_the_viewer`); an orthophoto's `attribution_url` makes its attribution a link (basemap.at
  requires one); `OSM_CREDIT` and the map's OSM tile credit carry the fixthemap link (FOSSGIS terms); Leaflet
  attribution HTML is built only from escaped text with http(s) links. Esri World Imagery was removed on 2026-11-01
  (its terms do not cover keyless use); it is back through ArcGIS Location Platform with the operator's key
  (`settings.WebKeys.esri_api_key`, `ESRI_API_KEY` or the web service's secret): the server puts the key into the page
  only (`FINDALINE_APP.esri_key` of the app's and share links' runs.js, locally a `/runs/runs.js` route appending it
  to the file, the app page's meta `findaline-esri-key` read by `layers.ts esriKey`), never into a file; maps from
  disk have no Esri layer; the about page lists it with the user-approved terms sentence (`web.esri_terms`). Esri does
  not enforce a key's referrer list for these tiles (checked 2026-11-01: a tile came for another site's referrer and
  for none), so a key copied from the page works elsewhere: short expiry, rotation, pay-as-you-go off. On a phone a
  run's data credits fold behind a "Data credits" button (`creditsHtml`, ui.css `.u-credits`); tile credits never
  fold. The map's attribution and scale are kept clear of the sheet, panel and profile (`result/view/corners.ts`).
- **USGS 3DEP (the USA)**: the 1 m DEM is published per project in 10 km files of 10–450 MB, and a newer project often
  covers only part of a tile (Yosemite x26y418: a 10 MB sliver of 2020 over the whole tile of 2019), so "newest file
  per tile" loses data: `TnmBlocks` composes each block newest first and reads an older file only while holes remain;
  the key in a block's name stands for its set of files (a new project changes it). All 3DEP files are tiled, so GDAL
  `/vsicurl/` reads windows (`_gdal_http` sets our User-Agent); never download a whole file. Old 1 m names have no
  zone (`USGS_one_meter_x..y..`, `USGS_1m_x..`): `_utm_zone_of`. Alaska's IfSAR files name only the GRS80 ellipsoid of
  Alaska Albers (`_same_crs` takes it as EPSG:3338); there is no 1 m DEM in Alaska (2026-10), so `alaska` switches to
  `alaska_ifsar` (`Source.instead_without_data`). Texts printed to the console stay in cp1250 (a Windows console):
  "1/3 arc-second", not ″, in names, descriptions and notes.
- **Saarland and British Columbia** (batch 4): LVGL's DGM1 and DOM1 hold patches at 0 m whose rims fall from the
  ground to them (327_5485: one pixel; 343_5457: a ramp of five pixels, 101-166 m from ground at 184 m): `SL_RING` 6.
  The token of LVGL's share changes (the 2025 link of others is 404): resolved from its stable redirect, never pinned;
  its archive names are fixed in the module (no WebDAV PROPFIND), so a new survey is set by hand. LidarBC's index is
  an "Access Only" layer with wrong entries (LAZ as `.tif`, "2011" paths that answer 404): the bucket listing filters
  them. Its 2022+ 1:20 000 sheets are one-row strips (about 30 MB read per 1 km block, against 2-4 MB for tiled
  files); its "PixelIsPoint" files of 2015-2018 and 2021-2022 lie half a pixel off the "Area" ones, which
  `GTIFF_POINT_GEO_IGNORE` does not fix (measured at the Chief and at Skaha). On BC's DSM (equal to its DTM on bare
  ground) `obstacles.RULE` misses about half of the lines over a tree at R64 (pines within its 2 px envelope of the
  walls).
- **geoportal orthophoto**: `ORTO/WMS/HighResolution` holds only sheets of 10 cm or finer (mostly towns) and answers
  elsewhere with a white JPEG (667 bytes), not an error; the gaps come from the base tiles (`OrthoService.base_url`:
  the `ORTO/WMTS/StandardResolution` GetTile in EPSG:3857, zoom 0–19). The `ORTO/WMS/StandardResolution` answers about
  half of the requests with 404, and its session cookie keeps a browser on the failing server: not used. A tile with
  white 8×8 blocks is on the edge of the coverage and is composed from the transparent PNG of the WMS over the base
  (`orthophoto.tile_content`).
