---
paths:
  - "sources/catalogue/**"
  - "orthophoto.py"
  - "tools/sk_tiles.py"
  - "tools/mirror_tiles.py"
  - "tools/mirror_publish.py"
  - "sources/readers/tilebases.py"
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
- **Our own Slovak tiles** come from a local copy (`FINDALINE_MIRROR`, the folder above `slovakia/`) when it holds
  them, else from the project's data server (`FINDALINE_MIRROR_URL`, `off` for none: then `--source auto` falls back
  to `europe` and the Slovak regression test is skipped without the folder; `SLOVAK_TILES` in
  `sources/catalogue/slovakia.py`). `tools/sk_tiles.py extract` unpacks the TIFF first (GDAL's
  `/vsizip/` reads it about 60 times slower than Python's `zipfile` inflates it); `cut` reads full-width 2 km bands
  (several GB of RAM) and writes tiles on all cores: one cut at a time. `tools/sk_tiles.py average` writes `dmr5/2m`,
  `dmr5/5m` (and `dmp1/...`) next to `1m` in about 6.5 min per product on all cores (12 826 tiles with data: 23.6 and
  4.4 GB beside the DMR's 1 m folder, 26.7 and 4.9 GB beside the DMP's, measured 2026-11-04; in ZSTD since 2026-11-08,
  23.4, 4.3, 26.2 and 4.8 GB: `tools/sk_tiles.py recompress` rewrote the four folders' 51 304 files in 14.3 min and
  the cache's 26 242 copies in 6.5 min); without those folders a 2 m or 5 m grid reads the 1 m tiles as before
  (`GridResolutions.resolution`).
  Madeira's and Valle d'Aosta's tiles (`tools/mirror_tiles.py`) share the mirror.
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
- **Batch 5** (2026-11-15): Nominatim names every French overseas territory "fr" and Caribbean Netherlands and Sint
  Maarten "nl" (their ISO 3166-2 codes only at zoom 8-10): those sources are chosen by bbox, and a new "fr" or "nl"
  source must keep its boxes off the others' islands. IGN's overseas RGE ALTI layers differ in alignment (Guadeloupe,
  Martinique, SPM: centres on whole metres; Guiana and the mainland: edges); check with a GetMap at half the resolution
  (2 x 2 blocks). The AHN's Caribbean files name only a LOCAL_CS (`force_crs`); basisdata.nl went silent for this PC
  after parallel reads at 4 connections. TINITALY's WCS and GA's 5 m WCS answer 0 without a nodata tag where they
  hold nothing (`zero_is_nodata`); GA's covers about 3 % of Australia: `auto` picks `australia` only where its static
  cells mask has data (`tools/au_coverage.py`, refreshed by hand). Sardinia's WFS keeps footprints in EPSG:3003: ask
  with SRSNAME 32632. Italian regional sources fall back on `tinitaly`, so a run it fills alone is CC BY. Queensland
  (CC BY-SA) is never a neighbour of a source filled by FABDEM. IDE Uruguay's sheets each have an origin off whole
  metres (`check_source`'s alignment WARN is expected).
- **Batch 5 wave 2** (2026-11-15): INEGI's per-sheet JSON (`getF10KDescarga.do`) is undocumented: a 404 for a cell
  of the mask means a moved endpoint, never "no sheet"; its GRIDs name no CRS (Mexico ITRF92 / UTM of the zone) and
  reach 100-400 m beyond their cells with TIN edges up to 73 m off (cut to the cell + 10 m). Tuscany: the WFS type
  `rt_cartoteca.lidar2k` is not in the capabilities; the files' URLs carry a hash only a GetFeatureInfo gives, one
  survey per point; the GetFeatureInfo's owner is wrong for 351 co-owned MATTM sheets (the licence PDF in the ZIP
  decides); surveys of 2016 and 2017 have 0 in their sheet boxes; a MATTM run is CC BY-SA, so its chain never takes
  FABDEM (copernicus). DLS's INSPIRE folder (Cyprus) is slow (about 0.8 MB/s); Estonia's host is
  geoportaal.maaruum.ee (maaamet.ee 302s to it). Valle d'Aosta's ZIP is Deflate64 (7-Zip, not zipfile), its ASCII
  grid has decimal commas, and its firewall answers 500 to a Range beyond about 1e8 bytes. A mirror dataset's
  `origin` in `tools/mirror_tiles.py` `DATASETS` equals its layer's `GridTiles(origin=)`. Spain's offline box holds
  Madeira: `portugal` comes before `spain`. Replacing a file on the Z: share needs a retry (`_replace`, WinError 5).
  OpenDataNI's links redirect to signed R2 URLs: never store or print them (`cache.clean_url` masks X-Amz-*). OSNI's
  members: sheets 51-100 under a folder, a space before ".txt", sheet 11's extra "011a" west of its box, no 287 or
  290, a sheet 293 off the grid (box from its points). DAERA's tiles at 54/min (`HOST_RATES_OF`: the mail's
  promise) until DAERA answers. IPP's Rio layer is a city project's and may vanish (europe then).
- **geoportal orthophoto**: `ORTO/WMS/HighResolution` holds only sheets of 10 cm or finer (mostly towns) and answers
  elsewhere with a white JPEG (667 bytes), not an error; the gaps come from the base tiles (`OrthoService.base_url`:
  the `ORTO/WMTS/StandardResolution` GetTile in EPSG:3857, zoom 0–19). The `ORTO/WMS/StandardResolution` answers about
  half of the requests with 404, and its session cookie keeps a browser on the failing server: not used. A tile with
  white 8×8 blocks is on the edge of the coverage and is composed from the transparent PNG of the WMS over the base
  (`orthophoto.tile_content`).

## The project's data server: the publish tool and the client (docs/mirror-hosting/spec.md B, C)

- `tools/mirror_publish.py` `PUBLISHABLE`: its datasets are `mirror_tiles.DATASETS`' folders and Slovakia, each
  `source_id` a catalogue source (its credit is the row's attribution), its required folders `GridTiles(averaged=)`,
  each card states the changes; a new dataset needs its row with the user's approval and date. A recut with other
  values is a new edition (a new folder name, U24). `BLOCK` 10 in `sk_tiles`, `mirror_tiles`, `mirror_publish` and
  `tilebases` (`tests/test_mirror_pairs.py`).
- The client (`tilebases.py`): `MIRROR_URL`'s host is the key of `net.HOST_SLOTS_OF`/`HOST_RATES_OF` (another address
  takes its manners through `net.LIMITS_AS`) and Telegraf's address; `off` (or empty) turns it off, also in conftest,
  `tests/regression.py` and the privacy sentence; a test never sets it empty (Windows deletes the variable: the real
  host): `off`. `reach` only where the specification's C.3 passes `reach=True`; a later phase takes the job's stored
  source (`plan_search(source_id=)`). `net._get(stop_on=)` is the start check's 429 rule; `_server_failed`'s text
  reaches the page through `error.download_failed`.
- An index's rules (null: no data; beyond a complete index's extent: no data; `partial`; `"block"` 10) are what
  `sk_tiles`/`mirror_tiles` write, what `mirror_publish verify` checks and what `tilebases` reads
  (`test_the_tools_indexes_pass_the_check`, `test_indexes_written_by_the_tools_pass_verify`). `REACH_TIMEOUT`
  (10 s, 20 s a read) rests on the server's 10 s header timeout and storage that never spins down (spec A's risks).
  The later phase's "Data: <name> (chosen when the search started)" keeps the form `tests/regression.py` `PATTERNS`
  and `tools/obstacle_study.py` read; `regression.py --mirror-url` runs the `needs_path` entries without the folder.
- `tests/http_server.py` `peak()` counts a request from its arrival to just before its answer's headers leave; the
  client's connection tests read the host's 2 connections from it (`test_two_connections_whatever_address`,
  `test_a_tile_falling_through_a_local_folder_takes_a_slot`): where a request ends changes them together.
