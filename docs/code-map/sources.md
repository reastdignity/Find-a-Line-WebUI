# Code map: data sources, cache, OSM

What the modules of this area hold, in detail: data sources, cache, OSM. Moved out of CLAUDE.md on 2026-11-12; nothing
loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync and the
pitfalls are in `.claude/rules/` (sources, providers, osm).

## `sources/`

Data sources, a package (`__init__.py` re-exports what the app uses; its modules import only those before them: net,
vertical, credit, layer, composed, readers, indexes, source, layers, catalogue, choose, mosaic, filling): `net.py`
HTTP (`_get` with retries, `_sleep`; `session()`: a keep-alive `requests.Session` per thread; `HOST_CA_OF` and
`verify`: a host's missing intermediate certificate from `sources/certs/` on top of certifi's roots, for its requests
only), `host_slot` and `tile_lock`, the `.part` names, `_gdal_http` (GDAL's settings for remote reads: retry codes
with 0, one thread) and `gdal_errors` (GDAL's errors of a thread, also of reads that returned); `credit.py` `Credit`
and the shared licences (`YEAR`, `{year}` in an attribution, notice, orthophoto attribution or note: the run's year,
filled by `search.save_run` with `dated`/`dated_credit`; `YEAR_TEXT` on the about page); `layer.py` `Layer` (one
elevation model cached in tiles) with the cache's writer (`_write_tile`: float32, NaN, 256 px blocks, LERC_ZSTD within
`MAX_Z_ERROR` 5 mm; `max_z_error=None` the lossless deflate of before, the tests' tiles of before) and the conversion
of tiles cached before it (`Layer.rewrites`/`Reader.rewrites`: the cached file is ours to write again, not the Slovak
mirror's copies; `old_encoding`: a one-band float GeoTIFF that is not LERC, from the header; `reencode` under
`tile_lock`, the replace tried `REPLACE_SECONDS` where another process has the file open on Windows, then left;
`reencode_paths` with a memo per process, called at the end of `download_layers` (not with `reencode_cached=False`:
`tools/area_download.py`) and by `relief.fetch_relief_tiles`) and `download_layers` (the tiles of all layers of a
search in one pool of `DOWNLOAD_THREADS`, an entry (layer, label, grid) a layer over a grid of its own (the country
prefetch's neighbours), the layers' indexes asked at once (`each_layer`; `estimate_layers` the same for
`Layer.estimate`); a `serial` layer's tiles in `squares` of `SERIAL_SQUARE` blocks, one task each, its tiles one after
another (GDAL's cache of ranges finds the tiles neighbours share); `group_m` (the country prefetch): the layers whose
`groups` is true in squares of group_m, `ComposedLayer._download_group` each (the reader's `fetch_group` under one
host slot and no lock, then each tile under its `tile_lock` if still due, recorded as `_download_and_record` records
it; a group that cannot be read: its tiles one by one), each under `tile_lock` and a `host_slot`); `source.py`
`Source`, `OrthoService` and `Coverage` (how the coverage map shows a source: provider, `added`, areas, `partial`,
`rest` resolutions, `level`, survey, trees, `min_length`, note codes; `box` splits a country's uncovered rest off its
outline; `Source.coverage_boxes`: the `offline` boxes and `bbox`, without `border_boxes`, which may hold a neighbour's
land, what an area download clips its outline to; `rough_boxes` adds the border boxes) (`wms_version`: 1.3.0, or 1.1.1
for a WMS taking EPSG:4326 in lon-lat order only (GURS); `wms_crs`: EPSG:4326, or EPSG:3857 for a WMS serving Web
Mercator only (gis.natt.is), each tile's own Mercator box: `orthophoto._get_map`, `data.js`'s `ortho.wms_version` /
`ortho.wms_crs`, `viewer/src/layers.ts`); `vertical.py` `Geoid` (a geoid grid from PROJ's CDN downloaded once into
`cache/geoid/<model>/` under a lock, checked against its sha256 and read by rasterio, bilinear on its points; never
through PROJ: pyproj gives N = 0 without a word when it lacks the grid; `undulation` of a block on a lattice of
`LATTICE` points; `EGM2008`; `GeoidMissing`, never N = 0)

## `sources/composed.py`

A layer of parts: `Index` (tiles over a grid, the cached file of a tile, the `request` for the reader, `tile_of`,
`bounds_wgs84`, `has_data_near`), `Reader` (`fetch(request, path)`, `url` for the host slots, `unavailable`) and
`ComposedLayer`, the `Layer` delegating to its `index` and `reader`; a new source combines parts, a new kind of
service is one new part (tests: `tests/test_parts.py`)

## `sources/readers/`

How one tile is fetched: `download.py` `Download` (a whole file per GET, optionally checked against a sha256; a
one-band float raster then written again through `_write_tile`, overviews dropped, an integer raster or anything else
saved as it came; `average`: an integer factor, each block's mean of valid pixels written at the coarser size
(Bavaria's DOM20); `crs`: written in that CRS's name (a compound CRS); both read back from the `.part` on disk),
`wcsreader.py` `WcsReader` (GetCoverage, clipped to DescribeCoverage, multipart with CRLF or bare LF; `origin` for
pixel edges off multiples of the resolution (South Tyrol 1.25 m, folder suffix `-o<x>_<y>`), `params` (extra
GetCoverage parameters), `key_params` (a key put into each request when it is made), `version` (2.0.1, or 1.0.0:
COVERAGE/CRS/BBOX/WIDTH/HEIGHT, `describe_params`/`coverage_params`), `edge_px` (pixels next to nodata dropped, each
tile requested that much larger, folder suffix `-e<n>`); the extent read to the millimetre (LGB's has 0.01 mm of
noise); a tile wholly outside the coverage extent is missing after any error or 404 and not requested once the extent
is known, a box straddling its edge asked again clipped to it after a failure too; `split_on_error`: a box answered
HTTP 5xx after `net._get`'s retries asked again as a quadtree of pieces down to `SPLIT_MIN_PX` (250 px) composed on
the tile's pixels, a piece failing at the floor left without data, a tile none of whose pieces answered an error as
before, never missing, one printed line per split tile; England's two layers: the Environment Agency's 500 is
positional, for any box not wholly covered by its granules, which follow England's outline, so a 2 km tile of real
land at the Welsh border (Hay-on-Wye, 161_121) failed whole and in quarters while 500 and 250 px pieces on its English
side answered, and 16 px boxes fail on their own; measured 2026-11-08), `tilebases.py` `TileBases` (our own tiles: the
mirror, then URLs; `grid_tile_name`, `MIRROR_ENV`), `sheetfile.py` `SheetFile` (zipped ASCII grid or XYZ sheets; with
`members`, a regex: every matching member of one ZIP (GeoTIFF, XYZ, ASCII grid) merged on its pixels (`_merge`) in the
request's CRS, `max_bytes`/`member_bytes` caps; a ZIP without a matching member and without any raster member
(`RASTER_MEMBERS`: .tif, .tiff, .asc, .xyz) is missing with a printed note naming its members (LGL's DOM1 ZIPs of
three tiles on Baden-Württemberg's border hold two CSV lines of metadata, the licence PDF and a Meta-...txt,
2026-11-08), one holding a raster of another name an error as before), `wmsr.py` `WmsrReader` (a GetMap (WMS 1.3.0) of
raw heights as GeoTIFF, IGN's WMS-R: the box written exactly, an answer on other pixels or not a TIFF an error, the
CRS forced, all nodata or a 404 missing, more than `max_px` refused before asking; `TRANSIENT` answers
(LayerNotDefined, 502-504) get `TRANSIENT_ROUNDS` more rounds of `net._get`), `imageserver.py` `ImageServerReader` (an
ArcGIS ImageServer's exportImage on the service's own pixels: numbers written exactly (`number`), data only with TIFF
magic bytes (`readers.TIFF_MAGIC`; errors come as HTTP 200 with the image's type), the asked CRS forced (ArcGIS writes
`LOCAL_CS`), noData pixels NaN, an all-nodata tile missing; `sr`, `mosaic_rule`, `lock_raster_ids`, `params`
optional), `windows.py` `Windows` (a `BlockRequest` read from windows of remote files newest first: `_read_block`
(filling and tags by `_apply`/`_finish`, shared with `read_group`; `serial`: GDAL_HTTP_MULTIRANGE SERIAL through
GDAL's cache of ranges, `net.RANGE_CACHE_BYTES` set in the environment at import: Austria, Luxembourg, British
Columbia, where it was faster too), `read_group`/`fetch_group` (blocks of one CRS composed in memory as `_read_block`
composes each, round by round over the blocks' file lists, each file opened once through `ranges.open_remote` and read
in one window over the blocks that need it (`_group_values`: sliced where the block is on the file's pixels,
`_coincide`, else `_read_window`, yielded block by block and applied at once: a full group of 10 km at 1 m peaked at
1.5 GB)), `ranges.py` (`RangeFile`: a remote file for GDAL through rasterio's opener,
`rasterio.abc.MultiByteRangeResourceContainer`: GDAL asks a window's tiles in one `get_byte_ranges` up to some size,
beyond it tile by tile in plain reads, so `read_group` reads a window in strips of `windows.STRIP_ROWS` on rows of
tiles (`_read_strips`) and `prefetch`es each strip's tiles beforehand (`_tile_ranges`: the header's
BLOCK_OFFSET/BLOCK_SIZE with `TILE_PAD` bytes on either side, GDAL reads a row's last 4 bytes beyond it), runs merged
across `MERGE_GAP`, both kinds of read served from them; each run asked by `get_range`, taken only whole (206, the
Content-Range asked, its length), else asked again, counted by servicecounts; never raises into GDAL (an exception in
rasterio's callbacks stays set): `error` checked after every open and read; with GDAL_NUM_THREADS > 1 GDAL's /vsicurl/
took a tile cut short for zeros without an error, measured 2026-11-04), `_same_crs` (also a compound CRS by its
horizontal part: British Columbia's EPSG:6653/6654 with CGVD2013 heights); a listed file in another CRS than its
block's is not used (`WrongCrs`, said) while another file of the block serves it (the USA's 1 m DEM lists the
neighbouring zone's files too), and a block none of whose files could be read for that reason fails (`_read_block`
raises; `read_group` raises for the group, read one by one then), never missing: ArcticDEM over Jan Mayen gave "0 of
1252 tiles" without a word on a box whose PROJ may not resolve EPSG:3413 (2026-11-08); `_read_file` raises
`Incomplete` when GDAL signalled an error, read again up to `RETRIES` after `rasterio.cache.invalidate`, never
cached), `zipmember.py` `ZipMember` (one member of a remote ZIP archive (PKWARE's APPNOTE 6.3.10) by one Range of its
local header and data, the local lengths its own, a second small Range only when short; methods 0 and 8; its CRC-32
checked, asked again `RETRIES` times, never cached; a 404 or a moved member calls `renew`) and `ranged` (a Range GET
through `net`: 206 with the asked Content-Range only, a 200 `RangeRefused` and closed unread, never fewer than
`RANGE_MIN` bytes), `drop_below(floor, ring)` (pixels below a floor and a square ring around them as no data:
Saarland's 0 m patches)

## `sources/indexes/`

Which tiles cover a grid: `tilings.py` fixed tilings (`WcsTiling`, `MetricTiling`, `DegreeTiling`,
`TenthDegreeTiling`, `FileBlockTiling`: blocks on the pixels of big fixed files, a grid of COGs (`files(i, j)`) or one
national COG (its URL), `origin` for pixel edges on x.5; `_outline`: a grid's `area_shape` in the tiling's CRS,
prepared by shapely on a copy of its own for the test of every tile: 0.9 s a coarse tile of the country layer
otherwise; `cells_under`: with an outline, the cells of each part's own bounds (one more on every side: a cell
touching an edge intersects) within the grid's box (`within`: a grid smaller than its outline, a country layer's tile,
gets its own box's tiles; from 2026-11-08 to 11-11 every interior tile of Slovakia listed the 12 715 of the whole
country), tested in strips of `STRIP_CELLS` by shapely 2's vectorised `intersects`, exactly the cells of the loop over
the whole box in the class's order (`MetricTiling`, `TenthDegreeTiling`, `FileBlockTiling` rows outer, `WcsTiling` i
outer; Canada's box at 1 km took 25 M Python tests; `tests/test_units.py::test_tilings_per_part_as_the_whole_box`
keeps the brute force as the reference, `test_tilings_within_the_grids_box` that of grids smaller than their outline);
`remembered`: each tiling keeps the last grid's tiles (one entry: CRS, bounds, resolution and the outline object, a
copy given) since `Layer.to_download` asks twice and an area download's pass more; `WcsTiling.tiles` with an outline
scans the whole box since 2026-11-08 (its row loop reached half the grid's width from the centre, the circle's reach,
so a tall area lost its top and bottom rows to the gap filler: Norway's mainland entirely, England and Hesse their
rows; a circle's tiles as before, `tests/test_sources.py::test_wcs_tiles_of_a_tall_area`)); `cached.py` `CachedIndex`
(a `Listing`'s answers cached per 0.25° tile in `<top>/sheet-index/<prefix>/`, TTL (`ttl_days`: the sheet index's
unless set, LidarBC's 30; update.py reads it), offline fallback, `update_tile`; a `Versions` policy;
`IndexUnavailable`; `index_tiles(grid)`: the 0.25° tiles the versions ask for a grid: a circle's whole box, an area's
only those of the grid's box under its outline (per part of `grid.area_shape` in WGS84, its box grown by
`INDEX_MARGIN_DEG` 0.01° and kept within the grid's box, the tiles whose grown box intersects the outline; a part
spanning more than 180° of longitude crosses the antimeridian and takes the box's tiles of its latitude band,
`osm.tiles` with west > east giving both sides): the same files, since a file under the outline is listed in a tile
under it; the USA's box held 680 152 tiles, 99.9 % without its land; used by `NewestPerSheet.query`,
`ComposedBlocks.query` (`_items_of`; `_items` for `update_tile` and `has_data_near`) and `ShaPerTile.query`, whose
outlines are prepared; the "index not available" line ends with the error's text (`cache.clean_error`), which an area
download's passes need); `listings.py` `WfsSheets` (our GetCapabilities/GetFeature through requests, the GML read by
pyogrio, an OWS exception report is `IndexUnavailable`; a tile's year layers `WFS_THREADS` (4) at once, each under
`host_slot` (`HOST_SLOTS_OF` caps mapy.geoportal.gov.pl at 4) on `net.session()`, the answers read in the layers'
order; the year layers kept in `<top>/sheet-index/<prefix>.capabilities.json` (no index row, `CAPABILITIES_DAYS` 30,
so a new year layer is seen within a month; asked again with update "all", once per process, and when a GetFeature
fails on layers from the file), the folder given by `use(index, cache_dir, update)`; `threads = 1` in
`tools/record_answers.py`), `StacItems` (pystac-client's `ItemSearch`; its `APIError` becomes `IndexUnavailable`;
`item`: a regex of the item ids with year, east, north; `asset`: the one asset read when the items name no gsd, LGLN),
`TnmProducts` (requests); pyogrio and pystac-client imported inside `fetch` (the web process imports `sources`); their
JSON must stay byte for byte: recorded answers in `tests/data/recorded/` (an error case: `raises`),
`tools/record_answers.py`; `versions.py` `NewestPerSheet` (`Sheet`, `_sheet_order`; `prune` asks about the files
through `existing`: one listing of a folder from `LISTING_FROM` paths in it, kept for its second question
(`listings=`), the answers of `os.path.exists`, since every question to a network share takes a round trip; per
resolution for STAC; `_answers`: the 0.25° tiles `tiles_at_once` at a time when the listing says so (`WfsSheets`),
merged in the tiles' order) and `ComposedBlocks` (`Block`, newest first, the key of a block's files); `metalink.py`
`MetalinkFiles` (Metalink 4 / RFC 5854 documents of a whole region, read once per TTL and kept in
`<top>/metalink/<key>.json.gz`, each 0.25° tile picked from them; `parse_metalink`), `MetalinkIndex`, `ShaPerTile` (a
file known by its SHA-256: `<E//10>_<N//10>/<E>_<N>[_<year>]_<sha8>.tif`, the newest year per place, a changed file
read again and the older deleted); `s3listing.py` `list_objects` (S3 ListObjectsV2 by `requests`: `continuation-token`
pages; an `<Error>` (also with 200), a non-listing, a truncated page without a new token or more than `MAX_PAGES`
pages is `IndexUnavailable`; 5xx asked again) and `S3Objects` (the keys under the prefixes of a 0.25° tile);
`osgrid.py` (OS National Grid names → extent, `os_prefixes`); `geojsonfiles.py` `GeoJsonFiles` (a whole Land's GeoJSON
index of file links, a `MetalinkFiles` read once per TTL, streamed with a byte cap, kept as
`<top>/geojson/<key>.json.gz`; `forget`: LVermGeo SH); `zipdir.py` `ZipDirectories` (the central directories of remote
ZIP archives read by Range from their ends: the EOCD in the last 64 KiB + 22 B, the ZIP64 locator and record, the
directory in one Range of at most `DIRECTORY_MAX`; kept per TTL in `<top>/zipdir/<key>.json.gz` with each archive's
ETag and length, an unchanged archive keeps its directory; a share's token from its stable redirect, `share_token`,
resolved again after the TTL and a 404; the first archive wins a tile) and `ZipPerTile`/`ZipTile` (a member's CRC-32
its version: `<e>_<n>_<year>_<crc8>.tif`); `arcgis.py` `query_features` (an ArcGIS FeatureServer query through `net`:
paged by `resultOffset`, `QUERY_BYTES_MAX` an answer, an error JSON also with HTTP 200 or a non-JSON answer
`IndexUnavailable`)

## `sources/layers/`

One module per kind of layer, each a thin `ComposedLayer` building its parts with the constructor and attributes the
catalogue uses: `wcs.py` `WcsTiles` (`WcsTiling` + `WcsReader`), `degree.py` `DegreeTiles`, `OpenTopographyTiles`
(`DegreeTiling` + `Download`), `indexed.py` (`IndexedTiles`: a `CachedIndex`; `update_index_tile`, `index_path`),
`sheets.py` `SheetTiles` (`WfsSheets`, `NewestPerSheet`, `SheetFile`), `stac.py` `StacTiles` (`StacItems`,
`NewestPerSheet` per resolution, `Download` with sha256 when the item has one: swisstopo, Lower Saxony),
`gridtiles.py` `GridTiles` (`MetricTiling` + `TileBases`: Slovakia; a tile beyond the rectangle of the mirror
index.json's keys (tools/sk_tiles.py lists every tile of the raster's extent) is missing as a null entry, without a
request (a country layer's border footprint reaches such tiles), unless the index says `partial` (sk_tiles still
cutting or averaging: not cut yet, looked for further); `averaged`: the factors (2, 5) the dataset also keeps the
tiles at (`averaged_bytes` their tiles' sizes for `estimate`: the mirror's, 1.8/0.34 MB DMR and 2.0/0.37 MB DMP
against 4.8 and 5.7 MB at 1 m), `GridResolutions` one tiling per resolution and `ResolutionBases` one `TileBases` per
resolution, a tile `(res, i, j)`: a grid of the tiles' CRS at exactly an averaged resolution whose folder the mirror
or a URL has reads it (the cache folder, mirror and URL named by `renamed`: `-1m-` → `-2m-`, `/1m` → `/2m`), any other
grid the native tiles, also a grid of another CRS at 2 m or 5 m (a neighbour's: the mosaic would reproject the
averaged tiles bilinearly on top; `resolution(grid_res, grid_crs)`)), `blocks.py` `DegreeBlocks` (`TenthDegreeTiling` +
`Windows`: USGS 3DEP's 1/3″ DEM), `fileblocks.py` `FileBlocks` (`FileBlockTiling` + `Windows`: Austria's 50 km COGs;
Wales and Luxembourg next; `serial` passed to `Windows`; `geoid`: files of heights above the ellipsoid cached as
heights above that geoid, h - N in `_read_block`, the folder named `-<tag>`, the grid made ready before the tile's
lock: ArcticDEM), `tnm.py` `TnmBlocks` (`TnmProducts`, `ComposedBlocks`, `Windows`: its 1 m DEM and Alaska's IfSAR),
`files.py` (a local raster), `wmsr.py` `WmsrTiles` (`ResolutionTiling`: one `WcsTiling` per fetch resolution, the
coarsest not coarser than the grid, + `WmsrReader`: France), `imageserver.py` `ImageServerTiles` (`WcsTiling` at
`native_res` with an `origin` + `ImageServerReader`: Czechia; `zones`: a service that reprojects on request asked in
the working grid's CRS, `ZonedTiling`/`ZonedReader`, a tile `(crs, (res, i, j))`, `readers` per CRS: Queensland's MGA
54-56), `zipped.py` `ZippedTiles` (`ZipTiling`: a `MetricTiling` with an `origin`, the ZIP at `url(left, bottom)`
(None: no file, missing without a request), `tile_of`; + `SheetFile` with members: Saxony's and Baden-Württemberg's 2
km ZIPs; without members, plain files: Trento's ASCII grids, Slovenia's `x;y;z` text), `metalink.py` `MetalinkTiles`
(`MetalinkFiles` + `ShaPerTile` + `Download` with SHA-256: Bavaria, Rhineland-Palatinate), `s3blocks.py` `S3Blocks`
(`S3Objects`, `ComposedBlocks` newest collection first, `Windows`; `collections` (prefix, year), `names`/`extent`
callables, the ETag in an item's name: Scotland), `geojson.py` `GeoJsonTiles` (`GeoJsonFiles` + `XyzPerTile` +
`XyzFile`: plain XYZ files, `text/plain` only, a byte cap; an outdated link's HTML page (`StaleLink`) makes the index
be read again at once (`_stale`, once per `STALE_REREAD_SECONDS` for every stale link of a pass): the tile is missing
when the index still names the same link (LVermGeo SH answers the page also for files it no longer has: five tiles of
2007 in the outer Flensburg Fjord, 2026-11-08) and an error when it names another, used by the next search:
Schleswig-Holstein), `zipmembers.py` `ZipMemberTiles` (members of remote district ZIPs, `ZipDirectories` +
`ZipPerTile` + `ZipMember`, `floor`/`ring`; `_renew` forgets the 0.25° answers and reads the directories again:
Saarland), `lidarbc.py` `LidarBcBlocks` (an `S3Blocks`: `LidarBcFiles` asks the FeatureServer `LiDAR_BC_S3_Public`
(DEM layers 6 and 5, DSM 3 and 1), then lists the bucket under each (sheet, survey folder) it names and keeps the
listed keys only (the index lists LAZ files as `.tif` and paths that answer 404), the ETag in an item's name; each
file's CRS from its name (`_utmNN`), its `projection` or its footprint (`file_crs`); `bc_utm_crs`: British Columbia)

## `sources/catalogue/`

The sources, one module per family (`poland`, `switzerland`, `slovakia` (ÚGKK SR's DMR 5.0 / DMP 1.0 as our own 2 km
tiles, `GridTiles` with `AVERAGED` = (2, 5): the mirror's `dmr5/2m` and `dmr5/5m` written by
`tools/sk_tiles.py average`, the block mean of the valid 1 m pixels, read by a grid of its CRS at exactly 2 m or 5 m
(the country layer's bands M, M2 and L): at 2 m byte for byte the mosaic GDAL averaged from the 1 m tiles, at 5 m one
float32 ULP apart in 7 ppm of the pixels, measured 2026-11-04), `malta`, `spain`, `usa` (Hawaii's offline box since
2026-11-08: TNM lists 1 m DEM files over every main island), `austria`, `uk` (England: WCS with `split_on_error`, its
tiles at the edge of the data answered HTTP 500 whole and asked again in pieces, `zero_is_nodata` False although the
service answers 0.0 without a nodata tag over Welsh land and open sea where granules hold nothing (docs/roadmap.md,
"To check"); Wales: one national COG; Scotland: the SRSP's S3 bucket, `S3Blocks`), `germany` (Hesse,
Mecklenburg-Vorpommern, Saxony-Anhalt: WCS; Lower Saxony: STAC; Saxony and Baden-Württemberg: zipped 2 km tiles,
`ZippedTiles`; Bavaria (DGM1, DOM20 averaged to 1 m) and Rhineland-Palatinate: 1 km GeoTIFFs listed by Metalinks,
`MetalinkTiles`; North Rhine-Westphalia: WCS; Brandenburg with Berlin: LGB's WCS; Schleswig-Holstein: XYZ files listed
by a GeoJSON index, `GeoJsonTiles`, its server's intermediate certificate in `sources/certs/`; Saarland: LVGL's DGM1 /
DOM1 2025, members of 6 + 6 district ZIPs on its Nextcloud share by Range, heights below `SL_FLOOR` (100 m) and
`SL_RING` (6) pixels around them no data, before `rhineland_palatinate` in SOURCES: its offline box holds the Land),
`italy` (South Tyrol: WCS 2.5 m; Trento: 500 m ASCII grids of its LiDAR 2014, `ZippedTiles` without members),
`luxembourg` (one national COG of 0.5 m), `denmark` (Datafordeler's WCS 1.0.0 with an API key), `finland` (NLS's 2 m
sheets on CSC's Paituli mirror, read in blocks; `tm35_sheet`), `france` (IGN's LiDAR HD MNT/MNS by WMS-R GetMaps in
Lambert-93, IGN's 1 km tiles fetched at 1 m; `france_rgealti` RGE ALTI 1 m as its gap filler), `slovenia` (ARSO's LSS
DMR 1 m of 2011-2015, `x;y;z` text tiles of 1 km, each tile's block from the static table `SI_BLOCKS`; GURS's DOF050
over WMS 1.1.1; before `austria` in FAMILIES), `czechia` (ČÚZK's DMR 5G / DMP 1G 2 m from its ImageServers, EPSG:5514,
each model on its own grid; first in FAMILIES: its offline boxes lie inside Poland's and Slovakia's), `norway`
(Kartverket's NHM DTM 1 / DOM 1 from Geonorge's keyless WCS 1.0.0, EPSG:25833 for the whole country, 0.0 as no data,
HTTP 200 XML exceptions as errors), `canada` (NRCan's HRDEM mosaic 1 m in its own EPSG:3979 without resampling,
`FileBlocks` on 500 km COGs named by formula, larger cells in `LARGER_1M`/`LARGER_2M` read first; gaps `canada_2m`
then `mrdem30` instead of FABDEM; `british_columbia` before it: GeoBC's LidarBC DEM / DSM 1 m, region `ca-bc`,
`LidarBcBlocks` in NAD83(CSRS) / UTM of the place (`bc_utm_crs`), its gaps from `canada`, `canada_2m`, `mrdem30`,
never FABDEM; not `canada`'s neighbour (R41, pinned to `--source canada`, would fill its border pixels from LidarBC)),
`new_zealand` (LINZ's national 1 m DEM/DSM: one LERC COG per Topo50 sheet, `topo50_sheet` (a sheet holds its south
edge), 1 km blocks; `nz8m` the contour-interpolated 8 m DEM on the same sheets as its gap filler; `bbox` keeps the
Chatham Islands out), `australia` (Tasmania: the State's 2 m DEM, one COG on Source Cooperative read in `FileBlocks`
of 2 km, pixel edges off whole metres, region `au-tas`; theLIST's orthophoto tiles under CC BY-NC-ND 3.0 AU;
Queensland: the State's DEM time series ImageServer, its lidar DTMs newest first in GDA94 / MGA of the place
(`mga_crs`, `ImageServerTiles(zones=...)`), `queensland_demh` (DEM-H 30 m of the same service) for the gaps, never
FABDEM (CC BY-SA), region `au-qld`), `arctic` (ArcticDEM v4.1's 2 m mosaic (PGC), `FileBlocks` of 2 km on the COGs of
PGC's bucket named from the position (`arcticdem_files`, EPSG:3413, a missing subtile 404), heights moved to EGM2008
(`geoid=EGM2008`), no surface model, gaps from the `copernicus` source, never FABDEM: `greenland`, `svalbard` (regions
`no-21`, `no-22`; the Norwegian Polar Institute's orthophoto tiles in Web Mercator) and `nunavut` (region `ca-nu`,
gaps from `mrdem30`, `canada` its neighbour); before `canada` in FAMILIES: Canada's offline box holds north-western
Greenland and Nunavut's), `iceland` (the source `iceland` on ArcticDEM's layer, its gaps from `islandsdem10`
(IslandsDEM v1.0 10 m of the Natural Science Institute of Iceland, one national COG in EPSG:8088 read in 5 km
`FileBlocks`, also a source by hand), then `copernicus`; the orthophoto Grunnkort - Loftmynd from the institute's
mapcache, a WMS in EPSG:3857), `world`: FABDEM, Copernicus DEM (also the source `copernicus`, GLO-30 alone: the open
gap filler of the Arctic), NASADEM and the water mask), each with its services, credits, orthophotos and a list
`SOURCES`; `__init__.py` joins them in `FAMILIES` (the order `--source auto` tries them) into `SOURCES` and holds
`AREA_NAMES` (each area of the coverage map, `Source.map_areas`, by its name for Nominatim: the area downloads'
outlines and the country layer's territories)

## `sources/choose.py`, `mosaic.py`, `filling.py`

The source of a search (`choose_source`, `country_code` (zoom 3), `region_codes` (zoom `REGION_ZOOM` = 8, asked only
for a country with a source that has `Source.regions`: every `ISO3166-2-lvl*` code; offline the region boxes),
`OFFLINE_BOXES` (a region's box, `gb-wls`, gives its country and the region)); layers on the working grid
(`prepare_layer`, `build_mosaic`: the cached files opened with `GDAL_NUM_THREADS` = `WARP_THREADS`, so their
compressed blocks decode in parallel (remote reads keep one thread: `net._gdal_http`), a window read once as float32
(`_read_band`: a float32 band with NaN as its nodata, every cached tile of ours, without GDAL's mask, which decoded
each block a second time, its NaN pixels set to `np.nan` and `layer._clean`'s test in the same pass, the masked read's
bits: `tests/test_units.py::test_read_band_without_the_mask`) and put into the pixels without a value in place
(`_put`), where no raster wrote before (`_first_here`: the parts written, a list per mosaic) a copy, and such a
float32 raster on the grid read by GDAL straight into the mosaic's window (`src.read(out=)`, no array per file;
`test_mosaic_of_float_tiles_as_before`); no listing of a file's folder on its opening
(`GDAL_DISABLE_READDIR_ON_OPEN=TRUE`: GDAL finds a sidecar by its name, `test_mosaic_reads_sidecars`; the listing took
1.6 of the 2.8 ms an opening took); a categorical mosaic (the water body mask) is uint8 with `mosaic.NODATA` (255)
where no raster reaches, reprojected in float32 as before (GDAL's chunks depend on the bytes per pixel);
`tests/test_units.py::test_mosaics_as_before`; a raster off the grid is reprojected by the average where it is finer
than `FINER` (0.75) of the grid's resolution and bilinearly otherwise, or by `build_mosaic(resampling=)`, one of
`RESAMPLINGS` (heights only; a raster on the grid is copied either way), or with `same_resolution=` by that method
where it lies at about the grid's resolution (`FINER` to `SAME`, 1.1, of it) (`test_mosaic_resampling_methods`); every
reprojection with `mosaic.WARP_KWARGS` (rasterio's `num_threads=1`, its ChunkAndWarpImage, and the warp option
`NUM_THREADS=WARP_THREADS`: GDAL's kernel on its pool's threads, the same values; never `num_threads > 1`, the pitfall
"GDAL's warper on Windows": `test_mosaic_warps_without_a_thread_per_chunk`); `used_data`); water and gap filling
(`near`: a mask grown by n = ceil(metres / res) pixels, two passes of `scipy.ndimage.maximum_filter1d`, exactly the n
3 × 3 dilations of before (`tests/test_units.py::test_near_matches_the_dilation`); `water_body_mask` (uint8 in
`work/wbm.npy`: `OCEAN` where a tile is missing, `mosaic.NODATA` where none reaches; a lone tile holding one category
all around the grid, `CONSTANT_MARGIN` of its pixels, written as that category without the reprojection:
`constant_category`, `_constant_mosaic`, the nearest reprojection's own result
(`tests/test_filling.py::test_constant_water_mask_as_built`; 858 of Slovakia's 2122 S tiles, 62 of 575 M, 42 of 575 M2
and 1 of 163 L, dry land, each equal to the built mask)), `fill_water` (the sea counts as water where its data are at
most `SEA_LEVEL_TOLERANCE` or a source's constant `Source.sea_fill`: LVermGeo SH's 1.30 m; that rule and the lakes
with data are `water_with_data`, which the terrain statistics share), `fill_shore_from_surface` (before `fill_water`:
in the sea zone, where the terrain has no data, the surface model's sea surface (`water_with_data` on it: the exact
shoreline) stays for the sea fill, and the pixels above it reached from the terrain's data edge downwards, each at
most `FACE_TOLERANCE` (1.5 m) above the neighbour it is reached from, take the surface model's heights (a sea cliff's
face without ground returns: Malta's DTM lacks the lower 5-15 m of its cliffs; a ship, a mole or a boulder standing up
from the water is never reached); the candidates found strip by strip (`rows`), then numpy on their indices, no numba
(the quick lane); `search.prepare_data` joins its mask with the gaps' into `covered.npy` (`Data.covered`,
`Data.filled_pixels()`: what `filled_m` and the map's filter count), never into the seams of `at_seams` (the anchors
at a cliff's top edge stand right next to its face: R15 lost 605 of 606 lines when it did); `tests/test_filling.py`),
the uncertain shore after `fill_water`: `shore_rows` (uint8 kinds of rows of the grid: `SHORE_SURFACE` on the face
from the surface model, `SHORE_SEA` on a water pixel whose neighbour with terrain data stands more than
`SHORE_RIM_MIN` (5 m) above it: the terrain model ends on a cliff above the water and the fill stands in for its foot,
what a person sees in the 3D view as a wall straight down to the water) and `shore_segments` (the kinds grown by
`SHORE_BAND` pixels into bands, outlined strip by strip with rasterio's `shapes`, joined and `normalize`d, simplified
by `SHORE_SIMPLIFY` pixels in WGS84, each band's length the longer side of a rectangle of its area and outline less
the growth, under `SHORE_MIN_M` left out of the list: `{rim_min, segments: [{kind, px, m, ring}], totals}`),
`fill_gaps_chain`: `Source.more_fallbacks` in turn; `fill_from_neighbours` before them: `Source.neighbours` where
`border_gaps` (gaps on land reaching the edge of the search footprint, at least 2500 m²) lie in the neighbour's rough
boxes (`Source.rough_boxes`: its `offline` boxes, its `bbox` and its `border_boxes`, the border strips its offline
boxes keep off; `neighbour_window`), fetched on a sub-grid around those gaps, credited only when it filled pixels; the
count mode across a border (`search.prepare_data` with `Plan.partners`): `partner_zone` (the pixels beyond the outline
within reach, `near`'s square), `partner_grid` (`PARTNER_OWN` on the source's own data there before any filling),
`fill_from_neighbours(partner=)` marking where a neighbour filled terrain, `resolve_partners` after the filling (0
outside the zone and on a fallback's pixels, water or no data; the source's own data and a neighbour's fill alike the
declared neighbour of the smallest `Territory` holding the pixel's centre, `territory_grid`, else `PARTNER_UNKNOWN` 7:
by territory since 2026-11-12, never by which file filled it or by the tile's grid,
`tests/test_count_mode.py::test_partners_by_territory`); `border_gaps` computed once, not before a neighbour whose
rough boxes reach the grid (`_box_ranges` not empty: none at a border without a neighbour's data), again only after a
neighbour wrote pixels into either grid (`fill_gaps` returns `(path, terrain pixels filled, pixels written)`) or
failed midway; no neighbours: nothing done; a neighbour's rasters at the grid's own resolution are reprojected by
`NEIGHBOUR_SAME_RESOLUTION`, nearest (bilinear at one resolution smooths every cliff edge: 25-42 % of the neighbour's
lines lost in the Tatras and the Wetterstein, nearest 0-4 %; finer data stay averaged, coarser ones bilinear: nearest
makes a wall of every step between two coarse pixels, South Tyrol's 2.5 m data gave 73 867 lines on Austria's 1 m grid
where their own grid finds 28, so `SAME` lies between the measured 1.0 and 1.25; docs/performance.md, "The resampling
of a neighbour's data"), all of them by `NEIGHBOUR_RESAMPLING` when set (`tools/border_study.py run --resampling`, to
measure the methods); the fallbacks keep the mosaic's choice
(`tests/test_neighbours.py::test_neighbours_resampled_as_set`); `_fill` (the offsets of the gaps) computes its slopes
in place and releases the gradients, `tests/test_units.py::test_gap_fill_as_before` keeps the code of before as the
reference; `prepare_layer(quiet=True)` for them: no "tiles without data" line); every operation of step 1 takes `rows`
(None: the whole grid at once, today's code; a number: strips of that many rows, `STRIP_PX`, `strip_rows`, `strips`,
with a halo of its reach, for the area of a tiled search): `near_rows`, `fill_water` (`_fill_water_rows`; `bare_path`:
the pixels filled, obstacles.py's bare; a dry strip, no sea zone and no lake within `SHORE_BUFFER`, left out of both
passes: `test_fill_water_rows_dry_strips`), `fill_gaps`/`_fill` (`_fill_rows`: the matched pixels in `both.npy`, the
overall offset an exact selection on the float32 bit patterns of the differences read strip by strip, `_keys`,
`_median_of`, `_select`, np.median's value (the two middle values of an even count in the same passes while they share
a bin, `_select(pair=True)`; the keys compared as int32, `_keys32`: `test_select_pair_as_two_selections`,
`test_keys32_as_keys_before`); the ring pixels collected for `ndimage.median` (the dilation only over the columns
within `GAP_RING` of a gap, strips without one skipped); one int32 array of labels), `fill_gaps_chain`, `border_gaps`
(`_border_gaps_rows`: the footprint burned into `footprint.npy`), `neighbour_window`, `fill_from_neighbours`,
`water_body_mask`; the masks `new_mask`/`remove_grid` (a new mask is all False: `_gaps_rows`, `near_rows`,
`_fill_water_rows`, `_border_gaps_rows` and `coast.sea_mask_rows` inland write only the strips with a pixel to mark,
and `_fill_water_rows` labels nothing without a lake to fill); `mosaic.flush_grid` a grid that is done (flushed, or
its view kept in `HELD_GRIDS`, the list of a `country worker`); `rasterize_into` burns geometries into a memory-mapped
mask whole (GDAL's all_touched burn is not the same strip by strip; also the area mask and coast.py's);
`build_mosaic(rows=)` warps a raster covering more rows than that in destination strips (`_warp`): a raster of the
grid's CRS is bit for bit the whole mosaic's, a cross-CRS warp (FABDEM, the water mask) differs within GDAL's
approximate transformer, as a tile's extent made it differ before; each strip version equals the whole-grid function
(`tests/test_units.py::test_near_rows_as_near`, `test_fill_rows_as_before`, `test_fill_water_rows_as_before`,
`test_border_gaps_rows_as_whole`, `test_rasterize_into_as_whole`, `test_median_of_rows_is_np_median`,
`test_mosaic_rows_as_whole`)

## `sources/probe.py`

The source probe (`findaline.py sources check`): per source and layer at `Source.sample` on a tiny grid, the index
through `Layer.estimate` into a temporary cache, one byte of the first tile (a WCS: DescribeCoverage and a 16 × 16 px
GetCoverage), the orthophoto's base tile or GetCapabilities, `--deep` the first tile downloaded; `STRATEGIES` per kind
of layer (`window`: 16 × 16 px of a `FileBlocks` file, and its geoid grid cached or its size by a HEAD; `getmap`: a 16
× 16 px GetMap of a `WmsrTiles` layer's first tile; `imageserver`: the service's description and a 16 × 16 px
exportImage (a layer with zones: its default CRS); `text`: the first KB of a `GeoJsonTiles` XYZ file, first in
`STRATEGIES`; `zip`: the local header of a `ZipMemberTiles` layer's first member, a Range of a few hundred bytes;
`blocks`: a `LidarBcBlocks` layer's index, then 16 × 16 px at the centre of its first block from the newest file,
never a byte range 0-0); nothing written to the cache, its own requests under `host_slot`; 120 s per source (a daemon
thread); `tests/test_probe.py`

## `cache.py`

Data folder (`cache/`, `runs/`, `work/`), cache layout, `index.sqlite` per top-level folder (`due` of one file on one
connection, `due_many` of a layer's tiles on one per top-level folder: `Layer.missing`; the answers of before,
`tests/test_units.py::test_cache_due_many_answers_as_due`; `states` likewise for `state`: `prepare_layer`,
`water_body_mask`); `migrate` (schema versions of the SQLite databases, `PRAGMA user_version`); `reencoded` (a tile
written again in the current encoding: the row's sha256 only, its times kept); `runs_lock` (`runs/_runs.lock`, a
filelock: `mapping.install_viewer` and `runs.write_index` take it, one process at a time; two compute slots saving
their runs at once had moved their copies of `runs/_viewer` over each other, a `PermissionError` on Windows that
failed the job, and the later `runs.js` could leave out the other run; stored data: only the empty lock file, no
migration)

## `update.py`

`findaline.py cache status/update`, `cache migrate [folder] [--dry-run]` (every tile still in the older encoding
written again: `migrate`, `old_tiles`, `rewriting_layer`; exit code 1 when a tile stayed open elsewhere) and
`osm download/update`: which cached data can change, checks, runs on changed data

## `orthophoto.py`

Orthophoto tile cache (XYZ tiles requested from a WMS in EPSG:4326, or in EPSG:3857 with each tile's box
(`OrthoService.wms_crs`, `mercator_box`); an answer that is not a JPEG (gis.natt.is answers PNG) cached as JPEG over
white; each attempt takes `net.rate_turn`, backoff with jitter; a `requests.Session` per download thread, `_session`);
`tiles_to_cache` (the overview zooms of the area and `strip_tiles(lines, zooms, scale)`: the tiles at any zooms of the
strips of `BUFFER_M` × scale around the lines, also the obstacle study's orthophoto judge) tests each strip within its
own bounding box (`_tiles_in` vectorised with shapely 2: the same tiles as the union of the strips over the union's
box, which held mostly empty tiles on a long coast; `tests/test_offline.py::test_orthophoto_tiles_per_strip` keeps the
old code as the reference)

## `osm.py`

OSM themes in 0.25° tiles (`coastline`, `cliff`) from Overpass or the extracts, cached Nominatim answers
(`nominatim.sqlite`: `search` areas (`whole=True`: a large outline never simplified, on a row of its own keyed by
`WHOLE_KEY`: the country layer's), `places` of the place box, `reverse`; schema steps in `MIGRATIONS`); the shared
limits of both services; the theme `landcover` (woods, forests, bare rock and scree as ways and relations: the
obstacle study's judge, `tools/study_landcover.py`) from Overpass only (`osmextract.EXTRACT_THEMES`); a relation's
member roles in `properties["roles"]` (`feature`, written by `fetch_tile` and `osmextract._take_features`; tiles of
before have none: every part outer); `polygons(features)` the areas of a theme's features (closed ways; a relation's
outer rings less its inner ones, an island in a hole kept; made valid)

## `coast.py`

Sea mask: OSM coastline (theme tiles from Overpass or extracts, or the world file) or the Copernicus water mask; the
world file's polygons read once per box and CRS in a process (`_world_water`, one entry): a tile of an area passes the
whole search's grid as `extent` (`search.Plan.search_grid`) and rasterizes the polygons whose box reaches it, the same
pixels as those read for the tile alone (`tests/test_units.py::test_world_water_read_once_for_the_tiles`; the country
layer's tiles still do, a tiled search's step 1 runs once on the whole grid); `sea_mask_rows` the same for the area of
a tiled search and for the country layer's tiles (`extent` as `sea_mask`'s): the Copernicus sea given by rows, the
polygons and the coastline's faces burned whole into a memory-mapped mask (`sources.filling.rasterize_into`), each
face's share of the mask's sea counted strip by strip (`_sea_from_coastline_rows`, `_faces` shared with
`_sea_from_coastline`)

## `osmextract.py`

Geofabrik OSM extracts: download, replication diffs (pyosmium), theme features, theme tiles built from extracts; only
the themes of `EXTRACT_THEMES` (`coastline`, `cliff`): Poland's land cover made its `themes.json` 936 MB (8.8 MB
before), 6.2 GB of memory to load in every process building a tile and 199 s to take instead of about 10 s (measured
2026-11-03); `build_tile` False for another theme and for a theme an old `themes.json` lacks; `update` takes the
features again from an extract up to date that lacks an extract theme (`_missing_themes`);
`_take_features(theme_names=)`
