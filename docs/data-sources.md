# Finding and adding a data source

How to research a country's elevation data and decide how Find-a-Line gets it. Learned with Poland, Malta, Spain (2026-10-23/25), with Switzerland, Slovakia and Greece (2026-10-25) and with the USA (2026-10-26/30; see the roadmap, "New data sources"). The mechanics of adding a `Source` are in README.md, "Adding a country"; the data checks after it are in docs/regression-tests.md, "Data checks for a new source".

## 1. What to find out
For the terrain model (DTM, ground only) and the surface model (DSM, trees and buildings) separately:

| Question | Why it matters | Bad answers seen |
| --- | --- | --- |
| Resolution and coverage; survey years; is a newer cycle under way? | 1–2 m is the useful range; a partial newer cycle means versions per area | Slovakia: 0.5 m 2nd cycle in 16 of 73 lots |
| The program's own status map and plans (coverage now, next year) | where the data really is, what is restricted or in progress; links for the roadmap | USGS 3DEP: FY26 status and FY27 partnership maps; "some areas are restricted" (tribal lands) |
| Does a newer survey replace a whole tile, or only part of it? | "newest file per tile" is right only for whole tiles | USA: a 2020 project a 10 MB sliver of a tile whose 2019 file covers it all |
| Is there a seamless product built from the surveys? | one file per place, but it may lag the surveys and use another CRS | USGS S1M: 20% of CONUS, Albers, older than the newest projects |
| File layout: tiled or COG, file size | tiled files can be read in windows over HTTP, so huge files are no obstacle | USA: 10–450 MB tiles, Alaska 900 MB cells, all tiled |
| Licence and who may get it | must allow automatic download (and, for a public site, redistribution) | Greece: public bodies only |
| CRS and **vertical datum**, as the files name them | heights shown to users; gap filling against Copernicus; the working grid | Slovakia WCS: ellipsoidal heights, 43 m above sea level; Slovakia's TIFFs: a `LOCAL_CS` only; Alaska's IfSAR: Albers on "GRS80, datum not specified" |
| Value precision (cm, mm, whole metres) | whole metres make slopes and clearances coarse | Malta 2018 and Spain's WCS GeoTIFF: whole metres |
| Pixel alignment (edges or centres on whole metres) | `grid_origin`; half a pixel off smooths cliff edges | Poland's sheets: centres on whole metres (`grid_origin` 0.5) |
| Is the service being shut down, replaced or moved? Read the provider's news, migration or "services to be closed" lists and the terms page **as of today**, not only the service's capabilities | a source built on a service due to close breaks within months; licences also change (a survey's notes age) | Denmark (checked 2026-11-01): Dataforsyningen's `dhm_wcs_DAF` and `orto_foraar_DAF` answered normally, but its list "Oversigt over tjenester der lukkes på Dataforsyningen" (updated 2026-10-06) closes them for the modernised Datafordeler (an API key; the old access ends 2027-01-15), and the licence had changed to CC BY 4.0 in May 2024 while the survey of 2026-10-31 still quoted the 2022 terms |
| Access methods (below), with the source's own recommendations and its **usage limits in numbers**: the API or download service's terms page (requests per minute, day or year, parallel connections, volume), whom to tell before large downloads, the backoff it asks for, whether whole datasets come on a storage medium. Look for it first, before any code, and put the numbers and the URL in the report; the numbers go into `sources.net.HOST_RATES_OF` (a rate) or `HOST_SLOTS_OF` (connections), with the quote, URL and date | how to download without being blocked; the numbers set our concurrency and a per-host rate | swisstopo: the FSDI terms, section 2.3 (https://www.geo.admin.ch/en/general-terms-of-use-fsdi, binding in German): 40 requests/min on *.geo.admin.ch (data.geo.admin.ch has no row of its own), 1200/min WMTS; contact info@geo.admin.ch before exceeding; backoff with jitter up to 64 s; whole datasets on a storage medium through geodata@swisstopo.ch. Found late (2026-11-01): our downloads had exceeded it |
| Does a DSM exist and is it reachable the same way? | without it, lines over trees are not marked | Slovakia: DSM only in 155 GB ZIPs |
| Orthophoto WMS/WMTS: CRS (EPSG:4326 or 3857), terms, watermarks | the map background, offline tiles | Greece: watermark; EPSG:900913 gives blank images |

Start with the survey of 2026-10-31 ([source-survey.md](source-survey.md)): what was found for 231 countries and regions of Europe, the Americas, Oceania and Asia, with links, quick tests and open questions; check that it still holds. Where to look: the national mapping agency's geoportal and its "download" or "open data" pages; the INSPIRE geoportal of the country (CSW search for "Elevation"); data.europa.eu with a country filter; the JRC survey of open LiDAR in Europe (publications.jrc.ec.europa.eu, JRC126223); OpenTopography's catalogue for small LiDAR sets. Read the terms page itself, and the licence files inside downloads (Slovakia's ZIPs carry a PDF).

## 2. Ways to get the data, best first

| Way | Use when | Pros | Cons | In the code |
| --- | --- | --- | --- | --- |
| **Files per sheet/tile, found through an index** (WFS sheet index, STAC API) | the source publishes ready files | fast static downloads (Poland 17 MB/s, Switzerland 40 MB/s), full precision, versions visible (year in the name), what sources recommend for offline use | whole sheets even for a small area; versions to choose and prune; an index to query (cache its answers) | `SheetTiles` (Poland: `WfsSheets`, our WFS requests with the GML read by pyogrio, + `SheetFile`), `StacTiles` (Switzerland: `StacItems`, a search of pystac-client, + `Download`); both `IndexedTiles` (a `CachedIndex` with `NewestPerSheet`) |
| **Windows of big tiled files over HTTP** (GDAL `/vsicurl/`, range requests) | files of hundreds of MB that are tiled or COG | only the blocks over the area (El Capitan: 15 MB instead of 560 MB), full precision, no conversion, exact pixels | a block per request round (about 2 s per 1 km); versions must be composed when surveys cover parts of tiles; each file's CRS must be checked | `TnmBlocks` (USA, through the TNM API: `TnmProducts`, `ComposedBlocks`), `DegreeBlocks` (1° files at a fixed URL: `TenthDegreeTiling`), `FileBlocks` (fixed files on a metric grid or one national COG: `FileBlockTiling`, Austria); all read by `Windows` |
| **Files on a fixed grid** (URL from the tile name) | tiles on a known grid, one version | simplest, no index | no version information | `DegreeTiles` (Copernicus, FABDEM: `DegreeTiling` + `Download`) |
| **WCS 2.0** | no files, or files only as huge archives | any box, small requests | the server generates every tile (slow: Poland 30–50 s per 2 km); server-side downsampling may lose data or average oddly; size limits (~2000 px, Slovakia fails at 20 km); 404 beyond the coverage (clip to DescribeCoverage); GeoTIFF output may be 8-bit or whole metres (prefer ASCII grid or float GeoTIFF; ask for DEFLATE) | `WcsTiles` (`WcsTiling` + `WcsReader`) with `fetch_res` = native resolution |
| **Our own hosted copy** (when the licence allows redistribution) | only huge archives (one compressed file per country) or e-mail exports | small tiles on our terms, one mechanism for DTM and DSM | download, convert and host once; keep it up to date; attribution | `GridTiles` (`MetricTiling` + `TileBases`: Slovakia) |
| Rendered WMS images, hillshades, viewer tiles | never for elevation | – | pictures, not heights | – |

Rules of thumb:
- Ask for the native resolution and downsample locally (`fetch_res`); never trust server-side downsampling without checking the share of valid pixels at 5 m.
- Read every download with a byte cap: some servers ignore HTTP Range and stream the whole file (Wallonia's 50 GB ZIPs, an English survey tile, seen 2026-10-31).
- When a service refuses scripts (403, a CAPTCHA, a firewall), note it and ask the agency; never work around it with another User-Agent.
- Try older protocol versions before giving up: Norway's WCS 2.0.1 answers 400 where 1.0.0 works.
- A WCS may refuse a request with HTTP 200 and an XML exception report (Geonorge's ArcGIS WCS 1.0.0), and its
  DescribeCoverage's size limit may not be the one it enforces (3840 × 2160 advertised, 4096 a side enforced): find the
  real limit, and make sure a refusal fails as a raster and is never stored.
- Files named other than `.tif` are refused by our GDAL settings ("does not exist in the file system":
  `CPL_VSIL_CURL_ALLOWED_EXTENSIONS` in `net._gdal_http`, `.tif,.tiff` since LINZ's sheets).
- Check the global fallback in a new region: FABDEM's groups of 170-180° E end at "W180", which nobody had hit
  before New Zealand.
- The coarse overviews of a COG mosaic may show data its full resolution does not have (HRDEM's cell 5_3): check
  coverage at full resolution.
- A national mosaic in a conformal conic with far-apart standard parallels (Canada's EPSG:3979, 49 and 77° N)
  has several per cent of scale error: keep its native grid only when resampling would be worse (data already
  resampled once), and say the error in the description.
- A `FileBlocks` block must lie inside one file: when the files' edges are not multiples of the wanted block size from
  0, an `origin` puts the blocks on them (New Zealand's 8 m DEM: 4 km blocks from (0, 2000)).
- A WMS can be a data service (IGN's WMS-R): check that its GeoTIFF holds the raw values (float32, the nodata value,
  identical to the source on pixel-aligned boxes; halves and one-pixel shifts give the same values), and before
  reading a coarser resolution through it, that the server's coarser answer is an exact mean (IGN's is: a quarter
  of the volume).
- Some servers answer intermittent errors that look permanent (IGN's LayerNotDefined for a layer it has): probe a
  few hundred requests before trusting one error.
- An ArcGIS ImageServer may answer an error with HTTP 200 and the content type of the image asked for (ČÚZK: JSON
  as `image/tiff`): check the answer's magic bytes, never its content type; and it answers 0 without a nodata tag
  outside its data unless `noData` is given.
- Two models of one provider may lie on different grids (ČÚZK's DMR 5G and DMP 1G, 0.71 m apart): find each
  model's pixel edges, put the working grid on the terrain model and let the mosaic resample the surface model.
- A ZIP whose members' names carry a survey year cannot be read through `/vsizip/` without knowing the names: match
  the members by a regex and merge them (`SheetFile(members=...)`); a DOM may name a compound CRS (horizontal +
  DHHN2016): force the layer's horizontal CRS. A Nextcloud public share (GeoSN) answers HEAD with 401 but GET
  normally: probe with a ranged GET.
- A Land's WCS can be worse than its downloads (LGL: whole metres on 1.002 m pixels).
- Recorded answers of a reader must not be named `answers.json` under `tests/data/recorded/`: `tests/test_parts.py`
  replays every such file as an index cassette.
- A Metalink of a whole region (RFC 5854: names, sizes, SHA-256, mirrors) is a cheap and complete index: fetch it
  once per TTL, never once per tile; files without dates are versioned by their checksum (`ShaPerTile`).
- A product with no 1 m file but a finer one (Bavaria's DOM20 at 0.2 m) is averaged on its own pixels before caching
  (`Download(average=...)`); bilinear resampling of a finer grid is wrong for this.
- A server may stream an XML declaration alone as its first chunk (MapServer): never decide on the first chunk.
- An open S3 bucket is listed anonymously with `?list-type=2&prefix=` over plain HTTP (no SDK); ask per place prefix
  (tile names), not per collection; S3 keeps a key and replaces its content on re-upload, so the ETag goes into the
  version key. A portal's catalogue API (SRSP's) gives each collection's flight dates and its credit wording when its
  web pages are JavaScript only.
- A third-party verbatim copy (Tasmania's DEM on Source Cooperative) is fine when the licence allows redistribution:
  credit the licensor in its own wording, name the copy in the notice, and give the cache folder a date (nothing
  promises updates). An ArcGIS MapServer's Copyright Text (`?f=json`) can be the licence its service terms point to.
- A coastal regression's numbers depend on the coastline source (Overpass, the world file or the Copernicus mask):
  check "Coastline: OpenStreetMap coastline" in the log before accepting them, and with a scratch `--cache` link the
  real cache's `osm/water-polygons` read-only.
- Look at the edges of the data: South Tyrol's WCS blends the pixels next to its nodata edge with 0 (false steps of more than 1000 m; `edge_px`), Saxony-Anhalt's answers 0 without nodata outside the Land (`zero_is_nodata`), and the Environment Agency answers HTTP 500 outside its coverage.
- Clip requests to the coverage extent; a `missing` tile at the edge of the data is suspicious (Malta's north coast of Gozo was lost this way).
- Compressed archives (ZIP Deflate/Deflate64) cannot be read in parts; a TIFF inside may still be tiled, so after one extraction it reads fast. Python's `zipfile` cannot read Deflate64: use 7-Zip.
- Huge ZIPs: read the central directory with range requests first (the end of the file, then the ZIP64 record): the compression method of each member (8 = Deflate: Python's `zipfile` and GDAL `/vsizip/` read it; 9 = Deflate64: neither does, extract with 7-Zip) and the sizes inside. Extract a huge member once instead of reading it through `/vsizip/`: for Slovakia's 122 GB TIFF GDAL managed about 7 MB/s, `zipfile` inflates 400 MB/s (13 min), and the plain file reads in any order.
- Archives of many small tiles (a district's or a city's 1 km GeoTIFFs in one ZIP of a GB) need no download either when the server answers Range with 206 (Nextcloud does, though it sends no `Accept-Ranges`): the central directory once per TTL, then one Range per member (`ZipMemberTiles`: Saarland, about 2 MB a tile). Never through GDAL's `/vsizip//vsicurl/`, whose requests bypass `sources.net`; a share's token from its stable redirect, never pinned.
- An index that is an ArcGIS FeatureServer (`sources/indexes/arcgis.py` `query_features`) may list files that do not exist (LidarBC: LAZ as `.tif`, wrong years): confirm its entries with a listing of the files (S3 ListObjectsV2 per sheet) and take their ETags from there.
- Before downloading whole files, open one with rasterio through `/vsicurl/` and look at `block_shapes` and the `LAYOUT=COG` tag: a tiled file needs no download, only windows (`TnmBlocks`, `DegreeBlocks`). Old 3DEP files with the IFD at the end still read fine.
- Versions that cover parts of tiles: compose newest first, read an older file only while holes remain, and put a key of the set of files into the cached file's name, so a new survey over a block makes it read again and the older file can be deleted. "Newest file per tile" (Poland, Switzerland) is right only when a survey replaces whole tiles.
- Work in the CRS of the files when they are metric (`Source.crs`, or `Source.local_crs` for a CRS per zone such as NAD83 / UTM): blocks on the files' own pixels are copied onto the grid as they are; anything else is resampled and smooths cliff edges.
- Compare CRSs by their parameters, not by name: a file may name only the ellipsoid of the expected datum (`sources._same_crs`); check the first real file, not only the documentation.
- Fill the gaps from data with the same licence where there is any (the USA: the USGS 1/3″ DEM, not FABDEM, keeps a run public domain). A source may fill from several, in turn (`Source.more_fallbacks`).
- A WMS that answers 1.3.0 EPSG:4326 requests with a white image may read the axes as lon-lat: try 1.1.1 with
  `SRS=EPSG:4326` before giving up (GURS; `OrthoService.wms_version`).
- A frozen survey's tile index (a map layer of the provider) can live in the module as a compact table of runs
  (Slovenia's 21 263 tiles in 11 kB); a tile outside it is missing without a request.
- A small server can stall under four parallel connections from one IP while two run at full speed (ARSO): the host
  cap holds per data folder, so tests from two data folders at once exceed it.
- A service whose rasters are stored in Web Mercator has no own pixels in a metric CRS: ask it in the zone of the
  place (`ImageServerTiles(zones=...)` with `Source.local_crs`), nearest neighbour, and check that a box equals its
  halves. An ArcGIS mosaic's `product_type` may mix lidar with photogrammetric DEMs and bathymetry: read the
  catalogue's attributes (`query` with `returnGeometry=false`) before choosing a `where`.
- Copy a Copyright Text from each service's JSON: two services of one provider differ in punctuation.
- Check a server's TLS chain with Python, not curl: curl on Windows completes a missing intermediate through AIA,
  Python and the worker's container do not (LVermGeo SH: the intermediate goes into `sources/certs/`, trusted for that
  host only, with its fingerprint and expiry in the file and a test).
- Read a WCS's DescribeCoverage extent for noise digits (LGB: 466000.00001003): a hair past a tile edge makes that tile
  reach into the coverage and fail instead of being missing.
- A download link with the survey year in it goes stale when a tile is surveyed again: find what the server answers
  then (LVermGeo SH: HTTP 200 with HTML) and make it an error that reads the index again, never a cached tile.
- A model may fill the sea with a constant instead of leaving gaps (LVermGeo SH's North Sea: 1.30 m, one value over
  whole tiles): look at the sea pixels far from the shore (their distinct values, second differences), not at the
  shore's strip, and set `Source.sea_fill` when the constant is above `SEA_LEVEL_TOLERANCE`.
- Pick a regression centre where the steep pixels are (an anchor map, or a quick search with a small radius): the
  research's Rüdersdorf point lay 1 km from the quarry's walls, Tibrogargan's dome gave 9 lines.
- Heights above the ellipsoid (ArcticDEM; the sea lies at 27-32 m there) go into the cache above a geoid
  (`FileBlocks(geoid=...)`, `sources/vertical.py`). Never let PROJ do it: pyproj's transformation to EGM2008 heights
  gives N = 0 without a word when its grid is missing. Check N against GeographicLib's GeoidEval at a few points, and
  the corrected heights against Copernicus GLO-30 (EGM2008 heights too) with `tools/check_source.py`.
- A shift search against GLO-30 on walls of 1000 m is noise (Tasermiut and Uummannaq disagree, each fits badly at its
  best shift): judge it where GLO-30 fits (median |d| of a few metres), or against lidar.
- Check the size of a new region's Geofabrik extract before it reaches the VPS (`osm.catalogue_extracts`): Nunavut's
  is 1.5 GB, mostly coastline, and is left out like Canada's (`OSM_EXTRACTS_SKIP` of `deploy/vps.sh`).
- A file name computed from the position (ArcticDEM's subtiles) is checked against the provider's own listing (its
  STAC items) at a few places, and a place without a file must answer 404 (a missing block, not an error).
- A WMS may serve Web Mercator only (a MapCache: its WMTS matrix set named "EPSG:3857" need not be Google's tiling):
  ask it with each XYZ tile's Mercator box (`OrthoService.wms_crs`). It may also answer PNG to a JPEG request,
  transparent where it has no imagery: the cache converts such answers to JPEG over white.
- Check that the wheels' GDAL decodes a file's compression, on Windows and in the Docker image (IslandsDEM's ZSTD
  with predictor 2: yes, rasterio 1.5.2 / GDAL 3.12.2).
- Measure an orthophoto service's time per tile before relying on it: gis.natt.is takes about 1 s a tile, so the
  orthophoto of a 700 m circle with 727 spots (12 498 tiles) took 51 min.
- A provider's terms may except one service by name (the Norwegian Polar Institute: CC BY 4.0, but its orthophoto
  service in EPSG:25833 CC BY-NC 4.0): quote the exception and name the service used in the module.
- Names, descriptions and notes of sources are printed to the console: keep them in characters of cp1250 (a Windows console), e.g. "1/3 arc-second", not ″.
- When more than one product would be needed (a gap filler, a second region, a seamless model), present the options with a recommendation and let the user decide before writing it.
- For own hosting: COG tiles of 1 km in the source grid, LERC_ZSTD with `MAX_Z_ERROR=0.005` (5 mm) was the smallest and fastest (Slovak DSM 0.5 m: 5.5 MB per km², 0.2 s per tile); a JSON index with checksums; attribution and licence file next to the data.

## 3. Quick tests before writing code
- **Tables of limits may be invisible to HTML-to-text readers** (WebFetch and similar): geo.admin.ch renders its fair-use table from the page's Nuxt data, so the text showed "specified in the table below" and no table. Read the raw page (`curl -sL <url> | tr '\n' ' ' | grep -o '.\{0,300\}requests per.\{0,1500\}'`) and the JSON payload in it, and check the binding language version (FSDI: German).
Scripts from the 2026-10-25 research lived in the session scratchpad; the commands are short enough to redo:
- **STAC**: `GET <api>/collections/<id>/items?bbox=W,S,E,N&limit=100` and the `HEAD` of one asset (size, checksum, server); the code asks it with pystac-client (`ItemSearch(..., method="GET").pages_as_dicts()`), which follows the `next` links.
- **WFS sheet index**: `GetCapabilities` (the layers), one `GetFeature` with a `BBOX` and the attributes needed (`PROPERTYNAME`), read with pyogrio as the code does (`pyogrio.raw.read(io.BytesIO(answer), layer=0, DOWNLOAD_SCHEMA="NO")`, so GDAL asks nothing itself): the attributes, the CRS and which axis comes first in the outline (GDAL gives easting first); note the status of an error answer (geoportal: an `ows:ExceptionReport` with HTTP 400; one with HTTP 200 is caught too). Not GDAL's WFS driver: it pages by 100 and sends requests of its own.
- **WCS**: `GetCapabilities`, `DescribeCoverage` (axis labels, extent, CRS), then a 500 × 500 m `GetCoverage` at native resolution: check content type, pixel size and origin, value precision (fraction of values on whole centimetres), nodata, and time per request; try 2 km and larger to find the size limit; request one box crossing the coverage edge to see the 404.
- **Archives**: read a ZIP's central directory with HTTP range requests (the last 64 kB, then the directory) to list members, compression methods and sizes, and fetch small members (licence, info, `.tfw`) without downloading the archive.
- **Index APIs** (USGS TNM Access: `/api/v1/products?datasets=<name>&bbox=W,S,E,N&max=…&offset=…`): list the products at a few known places (climbing areas), note how many files a tile has and their sizes; for coverage, sample a lattice of points over the country (a point counts where a gap filler exists, so sea and neighbours fall out) and compare with the program's status map.
- **Window reads**: open a remote file with `rasterio.open("/vsicurl/<url>")` under `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`: CRS, transform (pixel edges on whole units?), block shapes, compression, nodata, and the time to read a 1 km window.
- **Orthophoto**: one `GetMap` in EPSG:4326 (WMS 1.3.0 axis order lat, lon) and, for WMTS, one tile in EPSG:3857; look at the image (watermarks, blank tiles).
- Then the data checks of docs/regression-tests.md, all of them one command once the source is declared: `uv run tools/check_source.py <id> --lat .. --lon .. --data-dir <scratch>` (shift against FABDEM / Copernicus, valid pixels at 1 and 5 m, cached tiles against the source files, the grid alignment, whole-metre heights, tiles without data).

## 4. After adding a source
- The source's `listing` (its row of README's "Data sources", then `uv run tools/source_docs.py`), its `offline` boxes (the country without a lookup) and its `sample` point (with data in every layer), and `tools/check_source.py` on its sample and a characteristic place, the numbers in docs/regression-tests.md.
- `findaline.py sources check <id>` (and `--deep`): the probe asks its index and files at the sample point; run it for all sources now and then, services change their addresses.
- A regression test in a characteristic place (cliffs, coast, border), with the coverage and `empty_tiles` values stored; a pytest against a fake server for new download code (see `tests/test_sources.py`).
- Attribution in the map (`OrthoService.attribution`, the source's `note`) and in README's "Data" section; the licence in the roadmap's licence list.
- Update policy (cache.py `TTL_DAYS`): versioned releases never, "live" services after their interval, sheet indexes after 180 days.
- `cache status` and `cache update <folder>` on a scratch data folder with the index rows aged by hand (`checked_at` in `cache/<top>/index.sqlite`, with a time zone, e.g. `2024-01-01T00:00:00+00:00`).
- New download code that uses GDAL's network access: read one window inside the Docker image too (HTTPS certificates of the slim image), and a job through the web app's queue.
- The whole regression set: the other countries' checksums must not change.
