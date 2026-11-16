---
paths:
  - "sources/catalogue/**"
  - "orthophoto.py"
  - "tools/sk_tiles.py"
  - "tools/mirror_tiles.py"
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
  Madeira's, Valle d'Aosta's and the islets' tiles (`tools/mirror_tiles.py`) share the mirror. A product is cut once,
  when complete, in a staging folder and made final by one rename into `<dataset>/<product>/<res>m/`: `TileBases`
  takes a dataset as there once that folder exists, so nothing unfinished may sit there; changed inputs are a new
  edition, never a recut; every write is a `WRITE_SITES` entry with its stop test.
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
- **Batch 6, France, Germany and Madeira** (2026-11-15/16): IGN's overseas RGE ALTI 1 m layers (Guadeloupe,
  Martinique, French Guiana, SPM, Réunion's filler, Mayotte) take `nodata_below=OVERSEAS_FLOOR` (-1 m, the user's sea floor rule); the
  mainland's layers and LiDAR HD never. Réunion's LiDAR HD is EPSG:2975 (the answers name EPSG:32740), its pixel
  edges at k x 0.5 m (the mainland's at .25/.75); Nominatim names Réunion and Mayotte "fr": chosen by bbox. Hamburg's
  member origins carry float noise (552999.9999999999: `TransformFix(snap=)`); the Elbe is a constant 2.00 m. Bremen
  and Bremerhaven are two sources on two grids, both DE-HB, chosen by bbox, each its own area (`de-hb`, `de-hb-bhv`):
  Bremen's XYZ points on whole metres are pixel centres (`grid_origin` 0.5); Bremerhaven's DGM1 lies at x.5 with the
  zone in its eastings (`TransformFix(offset=-32 000 000)`), its DOM1 on whole metres is moved half a pixel onto it
  (`TransformFix.shift`, clipped to its km: neighbours' shared columns differ). GDAL's XYZ driver refuses columns with points missing (`xyz_rows`) and keeps
  one column cache per process (`COLUMNS_LOCK`). Lower Saxony declares six neighbours already: none added. The city
  of Bremen's overseas port (7.6 km², inside Bremerhaven) is in neither download row. Madeira's 5 m ZIP holds a raster
  per island group, each its own mirror dataset: Porto Santo's is EPSG:3061 with the sea written as 0, the Desertas'
  file says EPSG:3061 but is PTRA08 (EPSG:5016); the island sources come before `madeira` in pt-30, chosen by their
  boxes; their floor of -1 m is set at the cut (`floor=` in `DATASETS`), not by a layer.
- **Batch 6, Japan and Hong Kong** (2026-11-15/16): Tokyo's bucket answers 403 for a key it does not have, so the
  static table (`tokyo_sheets.npz`, `tools/tokyo_sheets.py`) decides what exists and a listed 403 is asked once and
  is an error; the wards' sheets name no EPSG code and are point-registered; 85 sheets lie in both folders (2024
  first, 2023 fills). Shizuoka: LP grids only (the ALB grids hold the seabed), surveys composed newest first; one
  owner index tile per sheet (the 0.25° tile of its centre) decides its sets, key, prune and 404; ETags change in
  place (they are in the sheet's key); the CSV variant "n,x,y,z,flag" keeps every row. `MetricCellTiling(cell=(w,
  h))` serves Japan's and Hong Kong's sheets; its right and top edges are exclusive. Hong Kong: Nominatim "cn" with
  CN-HK (zoom 8), the map area `hk`; map 17's file names are a kilometre off their boxes (kept as published);
  heights above HKPD, lowered 1.30 m on the grid (`height_offset`: the user's decision; no floor, Kowloon has land
  to -6 m); Tokyo's island sheets take a -1 m floor (`TokyoSheets.floor_of`), the mainland never (land to -4.42 m);
  the credit names the Government and the CSDI Portal as source, the terms linked;
  no hosted copy without CEDD's yes; no orthophoto (LandsD's API requires its logo on the map). A URL captured from
  a Windows program's output keeps a trailing CR: re-ask a "missing listed file" with a clean URL before concluding.
- **Batch 6, Ontario** (2026-11-16): package ZIPs read by Range (420 terrain, 451 surface packages; a directory of
  65 kB in one tail read); the footprints miss tiles by up to 968 m (`MARGIN_DEG` 0.02); three member formats
  (GeoTIFF Area, GeoTIFF PixelIsPoint with the tie point at the first pixel's centre, ERDAS .img read as EPSG:26917):
  the zone's CRS is forced (15-18: EPSG:3159, 3160, 2958, 2959). LEAP 2009's DSM members are 1.2 km (cut to the box)
  and LEAP is CGVD28 beside CGVD2013 data; Muskoka's CGVD28 copies are left out (`ON_EXCLUDE`). Version order: the
  member's year, the project's date (`ON_PROJECT_DATES`: a new project goes there), the larger member; an older
  provincial survey fills an incomplete newest tile before `canada`. CLOCA 2018's and SNC 2018-19's terrain members
  are Deflate64, not listed. `ontario` only where the province has a tile within 2 km, else `canada`; offline, south
  of 49.4° N the USA's box wins.
- **geoportal orthophoto**: `ORTO/WMS/HighResolution` holds only sheets of 10 cm or finer (mostly towns) and answers
  elsewhere with a white JPEG (667 bytes), not an error; the gaps come from the base tiles (`OrthoService.base_url`:
  the `ORTO/WMTS/StandardResolution` GetTile in EPSG:3857, zoom 0–19). The `ORTO/WMS/StandardResolution` answers about
  half of the requests with 404, and its session cookie keeps a browser on the failing server: not used. A tile with
  white 8×8 blocks is on the edge of the coverage and is composed from the transparent PNG of the WMS over the base
  (`orthophoto.tile_content`).
