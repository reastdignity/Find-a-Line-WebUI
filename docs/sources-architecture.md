# Data sources at scale: how to add many countries (proposal, 2026-10-31)

A proposal, not a description of the code. **Decided 2026-10-31** (the user): option B, with steps 1–3 (the
refactoring and the tools) before new sources; see the roadmap, "New data sources". The goal is to support as many countries as possible
at a cost per country that stays low, with code that others can read and extend. The numbers come from the
survey of 2026-10-31 ([source-survey.md](source-survey.md): 231 sources in Europe, the Americas, Oceania and
Asia). Decisions taken from it go into the roadmap.

## How a source is added today
- **One module**, `sources.py` (2285 lines): the layer classes, one per access pattern (`WcsTiles`;
  `IndexedTiles` with `SheetTiles`, `StacTiles` and `TnmBlocks` (+ `Usgs1mBlocks`, `IfsarBlocks`); `GridTiles`;
  `DegreeTiles`, `OpenTopographyTiles`, `DegreeBlocks`; `FileLayer`), the credits, the orthophoto services, the
  13 `Source` entries of `SOURCES`, the automatic choice (`country_code` by Nominatim reverse at zoom 3,
  `OFFLINE_BOXES`, `Source.countries` + `bbox`, `instead_without_data`), mosaics, water and gap filling.
- **A source is a constructor call**: a `Source` with its layers, CRS, credit, orthophoto and notes. Quirks live
  in the layer's arguments (`axes`, `fetch_res`, `shift`, `grid_origin`, `local_crs`) or in a subclass.
- **Measured cost** (git history, code and docs, without the research):

  | Country | Access | What was new | Lines added | Files |
  | --- | --- | --- | --- | --- |
  | Spain (2026-10-23) | WCS | nothing: `WcsTiles` as it was | 68 | 4 |
  | Slovakia (2026-10-26) | own hosted tiles | `GridTiles` with a mirror; `tools/sk_tiles.py` (300 lines) and ~2 days of downloads and cutting | 69 (+ 450 for the tool) | 7 |
  | Switzerland (2026-10-26) | STAC | `StacTiles`, `IndexedTiles` split out of `SheetTiles`, an orthophoto without a WMS (viewer too) | 398 | 16 |
  | USA (2026-10-30) | API + HTTP range reads | `TnmBlocks`, `DegreeBlocks`, `local_crs`, `more_fallbacks`, `instead_without_data` | 923 | 11 |

  A source whose pattern exists costs tens of lines; a new pattern costs hundreds.
- **Where the time goes**: the research (`docs/data-sources.md` §1–3) and the data checks (shift against
  Copernicus, valid share at 5 m, a cached tile against its file, the grid alignment, each time with throw-away
  scripts), the regression test and the documentation, more than the code.
- **Lists kept by hand**, which grow with every source: the help of `--source` in `params.py` (names the
  countries), README's "Data sources" table, the `--source` row of the options table and "Data", the
  `OFFLINE_BOXES`, CLAUDE.md's code map, `setup-for-regular-folk.md`. The about page is already generated from
  `SOURCES`.
- **At run time**: one source per search; `--source auto` picks by ISO 3166-1 country code and a box; the gaps
  are filled from `fallback` and `more_fallbacks` in turn. Regions inside a country are only possible through
  `bbox` (Alaska); a search across a border gets the neighbour's side from FABDEM.

## What the survey changes
- **Many sources, one by one small**: 19 sources of high priority and 41 of medium (55 separate deliveries:
  Canada's provinces come through the federal catalogue, Greenland through ArcticDEM, the Azores through the
  mainland's portal).
- **Each source is two independent choices**: how the files of an area are found (the *index*) and how the
  heights are read (the *reader*). The 55 deliveries use 9 kinds of index and 8 of reading, in 21 combinations:

  | Index (how files are found) | Sources | | Reader (how heights are read) | Sources |
  | --- | --- | --- | --- | --- |
  | a fixed grid (tile name → URL, or any box of a service) | 21 | | whole files (GeoTIFF; zipped ASCII grid or XYZ) | 16 |
  | an index file or a bucket/directory listing | 6 | | windows of tiled/COG files (HTTP range requests) | 15 |
  | one big file | 6 | | WCS GetCoverage | 9 |
  | STAC | 4 | | ArcGIS ImageServer exportImage | 5 |
  | WFS | 3 | | WMS-R GetMap as GeoTIFF (France) | 1 |
  | Metalink (`.meta4`) | 2 | | XYZ elevation tiles (Japan) | 1 |
  | ATOM feed | 2 | | own hosted copy | 4 |
  | ArcGIS FeatureServer | 2 | | manual only | 4 |
  | a service's own search API | 2 | | | |

- **Today's classes are combinations**: `WcsTiles` = grid + WCS, `SheetTiles` = WFS + whole files, `StacTiles` =
  STAC + whole files, `TnmBlocks` = API + windows (composed newest first), `DegreeBlocks` = grid + windows,
  `DegreeTiles`/`GridTiles` = grid + whole files. Only 5 of the 21 combinations exist (19 sources), and even
  those need options (WCS 1.1.1 for the Caribbean Netherlands, multipart answers in Saxony-Anhalt, the sea stored
  as 0 in Mecklenburg-Vorpommern, a token for Denmark, zipped XYZ in Saxony and Baden-Württemberg, a WFS of another
  schema in Tuscany). The other 36 need **16 new combinations**, but only **8 new parts**: 5 indexes (one file,
  listing, Metalink, ATOM, FeatureServer; plus a small adapter per search API) and 3 readers (ImageServer, WMS-R,
  XYZ tiles). The ImageServer reader alone serves 5 sources (Czechia, Sicily, Ontario, Queensland, Colombia).
- **Regions are common**: 78 of the 231 rows are regions (Germany's Länder, Italy's regions and provinces,
  Canada's provinces, the UK's nations, Australia's states, Belgium, Brazil, Japan...), 33 of them high or medium.
  `--source auto` cannot tell them apart today except by a box.
- **Other needs, each in several sources**: accounts or tokens (Portugal, Sweden, Denmark, Finland; New Zealand's
  orthophoto), versions composed per block (Scotland, British Columbia, New Zealand's surveys, Canada's projects;
  as for the USA), yearly editions (Austria), heights above the ellipsoid (ArcticDEM), whole-metre values (Espírito
  Santo), half-pixel origins (France, Tasmania, Bolzano), no surface model (15 of the 60), no open orthophoto
  (the UK, Canada, Australia).
- **Services break**: on the survey day Romania's portal was down after a ransomware attack, Italy's national portal
  was in maintenance, Thuringia's server answered every request with an error page, Quebec's closed every TLS
  connection, Argentina's IGN did not resolve, and the EU INSPIRE geoportal's certificate had expired. With tens of
  sources, breakage must be found by a check, not by users.

## Requirements for many sources
1. **A source whose parts exist is one small, self-contained change**: its declaration, a regression entry and
   its notes; no edits of lists elsewhere.
2. **A new access pattern is a new part, reused**: an index or a reader written once, tested once against a
   fake server, used by every source of that kind.
3. **Regions are first-class**: several sources per country, chosen by ISO 3166-2 or an outline.
4. **Borders**: a search across a border uses the neighbour's national data before FABDEM.
5. **Maintenance of many services**: moved URLs, outages, new survey cycles and changed terms are detected.
6. **Credentials** (accounts, tokens, keys) are secrets of the server, never in results or logs, and a source
   without its credentials is unavailable rather than broken (as Slovakia without its mirror).
7. **Readable for contributors**: the facts of one country in one place, the mechanics of one access pattern in
   another.
8. **No change of results**: every restructuring leaves the regression checksums as they are.

## Options

| | A. As today | B. Parts + one module per source | C. Declarative catalogue (YAML/TOML) | D. Our own copy of everything | E. GDAL virtual mosaics |
| --- | --- | --- | --- | --- | --- |
| Idea | one `sources.py`, a class per access combination, a constructor call per source | `sources/` package: indexes and readers composed by a generic layer; `catalogue/<id>.py` per source, data-only Python | as B, but the sources are YAML/TOML files validated by pydantic | convert every source once into our tiles (as Slovakia), one reader | let GDAL mosaic remote files (GTI tile index, STACIT, WCS driver, `/vsicurl/`) |
| Cost of a source with known parts | tens of lines, in the 2000-line module | one file of ~30–60 lines | one file of ~30–60 lines | download, convert, upload, host: days and storage | one index or VRT definition |
| Cost of a new access pattern | a new class per combination (~16 for the survey's candidates) | a new part (~8), reused | a new part, plus its schema in the catalogue format | none in the app; a converter per source | often none; but see the cons |
| Maintenance | every change touches the core module; index and window code repeated across classes | changes stay in one part or one source file; parts tested once | as B; quirks escape into Python hooks, so two places | storage (Slovakia: 134 GB for 49 000 km² at 1 m; France at 0.5 m alone would be several TB), re-conversion for every new survey or yearly edition | GDAL's own HTTP cache instead of ours: no `index.sqlite`, TTL, sha256, missing tiles, versions or offline use |
| Readable for others | must read 2000+ lines to add a country | a country file next to similar ones; parts documented once | easiest to read and review for non-programmers | the converter per source | GDAL options are terse |
| Licences | as published | as published | as published | needs redistribution rights: unclear for 74 of the 231 rows, refused for some | as published |
| Migration | none | the largest refactoring of `sources.py`: in steps, checksums unchanged | B plus a loader and a schema | none in the code, but the hosting | rewrite of downloading and caching |
| Risk | grows with every source | indirection; a part may not fit an odd source (it may still subclass) | the format grows into a language; worse error messages | hosting cost, lagging updates | loss of exact pixel copying, versions and the cache |

Notes on the options:
- **B and C differ in the language only.** Constructor calls with keyword arguments are as declarative as YAML and
  keep type checking, the IDE's help and the existing pydantic conventions (`params.py`); a test can keep the
  catalogue modules free of logic (no `def`/`class` but the hooks allowed). C would add a second format and a
  loader for no gain in what can be expressed.
- **D stays what it is today**: the way for sources that publish only huge archives or deliver on request
  (Wallonia, Croatia, Hong Kong, New South Wales' lidar), one by one, when their licence allows it.
- **E as helpers, not as the architecture**: GDAL already does the window reads (`/vsicurl/`) and could mosaic
  the cached files (GTI, GDAL ≥ 3.9; rasterio 1.5.2 ships GDAL 3.12 with GTI, STACIT and WCS). It cannot replace
  the cache, the index answers, the choice of the newest survey, the composing per block or `cache update`.

## Ready implementations of the interfaces
The rule (the user, 2026-10-31): for every interface a part speaks, first a maintained library or a GDAL driver
that ships already; where none fits, the existing implementations become the source of the tests (their recorded
answers, and the library itself as an oracle in a test), and our own code follows the interface's official
documentation, our own knowledge only where it is silent.

Checked 2026-10-31: PyPI (version, releases, licence), OSV (all advisories listed are fixed in these versions), the
libraries' and GDAL's own documentation; GDAL 3.12 as shipped by rasterio 1.5.2 and pyogrio 0.13.0, both installed
already (pyogrio through geopandas).

| Interface | Sources (survey) | Ready implementations | At run time | For the tests | Our own code from |
| --- | --- | --- | --- | --- | --- |
| STAC API search (paging, GET/POST, CQL2) | Switzerland (today), Lower Saxony, Sweden, Canada, ArcticDEM | `pystac-client` 0.9.1 (2026-10-20, Apache-2.0; pystac, requests, python-dateutil) | **use**: paging by `next` links, POST and CQL2, our headers; replaces the paging of `StacTiles`, the cached index JSON unchanged | its recorded cassettes; a recorded swisstopo page must give today's JSON | – |
| Static STAC catalogue | New Zealand | `pystac` 1.15.2 (2026-07, Apache-2.0, comes with pystac-client) | **use** | – | – |
| WFS 2.0 GetFeature (bbox, paging, GML) | Poland (today: regex), France's tile index, Tuscany | GDAL's WFS driver through pyogrio; `OWSLib` 0.36.0 (BSD-3: builds the request, the parsing stays ours) | **use pyogrio**: paging, GML geometries, axis order | GDAL's WFS test data (MIT), OWSLib's recorded capabilities (BSD-3); a recorded geoportal answer must give the same sheets with pyogrio as with today's regex before the switch | – |
| ArcGIS FeatureServer query | Ireland, Colombia's catalogue | GDAL's ESRIJSON driver through pyogrio (`FEATURE_SERVER_PAGING`); `esridump` 1.13 (MIT, no release since 2023-02); `arcgis` 2.4.4 (Esri Master License Agreement, 15 MB and 32 dependencies) | **use pyogrio**; not `arcgis` (licence, size) | the fixtures of esridump and GDAL (MIT) | – |
| ArcGIS ImageServer exportImage | Czechia, Sicily, Ontario, Queensland, Colombia | only `arcgis` (as above); GDAL's WMS driver speaks to a MapServer's `export` (rendered pictures), not to exportImage of heights | **own** | recorded small answers of two services; consistency tests (a box and its halves give the same pixels; a request on the service's grid returns its raw values) | [Esri REST API: Export Image](https://developers.arcgis.com/rest/services-reference/enterprise/export-image/) |
| WCS 1.0.0 / 1.1.1 / 2.0.1 GetCoverage | Spain, Malta (today), Hesse, MV, Saxony-Anhalt, Bolzano, Liguria, Denmark, England, Bulgaria, Caribbean NL (1.1.1), Norway (1.0.0) | GDAL's WCS driver (in rasterio: a block-cached remote raster, versions 1.0.0–2.0.1, switches for server quirks, a cache folder of its own); `OWSLib` (builds requests) | **keep our `WcsTiles`**: it works and the regression set covers it; the driver's cache would be a second one outside `cache/` | GDAL's recorded DescribeCoverage and GetCoverage of ArcGIS, GeoServer, MapServer and Rasdaman for every version (113 files, MIT): our reader and the GDAL driver read the same local server and must give the same pixels | [OGC WCS](https://www.ogc.org/standards/wcs/) 2.0.1 Core and KVP binding, 1.1.1, 1.0.0 |
| WMS GetMap as raw GeoTIFF | France (WMS-R) | GDAL's WMS driver (its own block grid, so resampling); `OWSLib` (builds the URL) | **own**: one GET; exact pixels need each tile's own box | recorded IGN answers; the survey's shift test (a one-pixel shift gives the same values) | [OGC WMS](https://www.ogc.org/standards/wms/) 1.3.0, IGN's Géoplateforme documentation |
| Atom feeds (INSPIRE predefined download service) | Norway, Thuringia, Austria's editions, Czechia, MV | `feedparser` 6.0.14 (BSD-2, maintained, GeoRSS; depends on `sgmllib3k`, no release since 2010; a lenient parser of web feeds with HTML sanitising we do not need) | **own**: a small fixed schema (entries, `describedby`/`alternate` links, georss polygons, dataset identifiers) with the standard library | feedparser as the oracle of a test (entries, links, polygons of recorded feeds of Norway and Austria) | [RFC 4287](https://www.rfc-editor.org/rfc/rfc4287), [INSPIRE Technical Guidance for Download Services](https://inspire.ec.europa.eu/documents/technical-guidance-implementation-inspire-download-services) |
| Metalink 4 (`.meta4`) | Bavaria, Rhineland-Palatinate | `metalink` 0.3.8 (GPL-3.0, first release 2026-10-12) | **own**: the licence (the project has none declared, GPL would bind it) and two weeks of history | recorded files of both Länder, the RFC's examples | [RFC 5854](https://www.rfc-editor.org/rfc/rfc5854) |
| S3 bucket listing (ListObjectsV2) | Scotland, Shizuoka, New Zealand's surveys | `obstore` 0.12.1 (MIT, Rust, 5.9 MB, very active); `s3fs`, `boto3` (large) | **use obstore** (decided; anonymous access, its parallel reads available later) | recorded listings | – |
| Index files (shapefile, GeoPackage, GeoJSON) | Trento, British Columbia, Tokyo | pyogrio | **use** (XML and HTML listings: own, small) | – | – |
| Windows of COGs over HTTP | Austria, Wales, Norway, Canada, New Zealand (USA today) | rasterio `/vsicurl/` | **use**, as today | – | – |
| Whole files (GeoTIFF, ASCII grid, XYZ, ZIP) | most Länder, Trento, Shizuoka (Poland today) | rasterio (AAIGrid, XYZ), `zipfile` | **use**, as today | – | – |
| XYZ elevation tiles | Japan (GSI PNG) | tile maths: `mercantile` 1.2.1 (in the lock through contextily, no release since 2021), `morecantile` 7.1 (MIT, maintained), and `orthophoto.py`'s own; no decoder of GSI's tiles | **own** decoder, tile maths as `orthophoto.py` | GSI's text tiles of the same tile as the decoder's oracle | [GSI elevation tile specification](https://maps.gsi.go.jp/development/demtile.html) |
| A service's own search API | USGS TNM (today), Portugal's CDD, INEGI | none (pystac-client if the CDD proves STAC-conformant) | **own** adapters | recorded answers | the providers' documentation |

Not a fit: `odc-stac` and `stackstac` load STAC items into xarray cubes; the app needs files on its own grid.

**Decided** (the user, 2026-10-31): `pystac-client` for STAC indexes, pyogrio for WFS and FeatureServer indexes,
`obstore` for bucket listings, and the tests as below, in full; the rest own code from the documents named.

Effect on the dependencies: `pystac-client` (with `pystac` and `python-dateutil`, pure Python) and `obstore` join the
run time; `pyogrio` is declared directly, since the code uses it; `feedparser` only in a development group of oracles.
Each is added with the source that first needs it, after a check of its current version and advisories.
GDAL's HTTP in pyogrio takes our User-Agent as `/vsicurl/` does (`_gdal_http`).

### Tests before our own code
- **Order per interface**: (1) the official document gives the list of requests and answers the code must handle;
  (2) fixtures from it, from the libraries' tests and from the services; (3) the tests, failing; (4) the code, with
  the section of the document it implements named in its docstring.
- **Recorded answers** in `tests/data/recorded/<interface>/`, with a README naming origin, date and licence (GDAL's
  test data MIT, OWSLib BSD-3, esridump MIT, pystac-client Apache-2.0; samples of the services under their data
  licences, a few hundred kB in all).
- **A local HTTP server** in the tests (standard library, with Range requests) serves them to our code (requests)
  and to GDAL (`/vsicurl/`, pyogrio) alike, so the GDAL oracles and readers run offline too. `pytest-httpserver`
  1.2.0 (MIT, on Werkzeug) has no Range support of its own, so it would save little.
- **Oracles** that are not run-time dependencies (`feedparser`) go into a development group of `pyproject.toml`,
  like `ui`; GDAL is installed anyway.
- Today's hand-written fakes (`tests/test_sources.py`) stay for the edge cases (coverage edges, 404); the recorded
  answers add what real servers do.

## Improvements whatever the choice
1. **`tools/check_source.py`**: the data checks of a new source as one command (shift against Copernicus/FABDEM,
   valid share at 1 and 5 m, a cached tile against its file, the grid alignment, the median vertical offset, the
   share of whole-metre values). This is the slowest part of each source today.
2. **A source probe** (`findaline.py sources check [id]`): ask each source's index or capabilities and read one
   small window; run by hand before a release and weekly on the server; report moved or broken services.
3. **Generated lists**: README's "Data sources" table and `--source` choices, the help of `--source` (without
   country names), `OFFLINE_BOXES`, from the catalogue; a test keeps README in step (like `viewer/dist`).
4. **Regions**: `Source.regions` with ISO 3166-2 codes (Nominatim's reverse answer has `ISO3166-2-lvl4` at a finer
   zoom than the 3 used now) and an optional outline instead of `bbox`; a region's source is preferred to its
   country's.
5. **Neighbours across borders**: the national sources of the neighbours as fallbacks before FABDEM
   (`more_fallbacks` exists; gap filling already reprojects): the Tatras, the Alps, the Pyrenees.
6. **Credentials as secrets**: `ServiceKeys` per source (accounts, tokens, keys), Docker secrets on the server,
   `Layer.unavailable` when one is missing.
7. **Open gap fillers per region** where FABDEM's non-commercial licence matters: Canada's MRDEM-30 (OGL),
   Australia's DEM-H (CC BY 4.0), as the USA's 1/3″ DEM already is.
8. **A vertical correction option** for sources with ellipsoidal heights (ArcticDEM; Slovakia's WCS was one).

## Recommendation and steps
**B** (parts composed by a generic layer, one data-only Python module per source), with improvements 1–3 early
because they pay off from the next source on. D only per source, as today; E only inside readers.

Each step its own branch; refactoring commits never change results (the regression checksums stay as they are):
1. **Package without behaviour change**: `sources/` with `__init__.py` re-exporting the names used today (so
   `import sources as src` keeps working), `core.py` (`Layer`, `Source`, `Credit`, `Fetched`, HTTP helpers),
   `filling.py` (mosaics, water, gaps), `choose.py` (`country_code`, `choose_source`), one module per existing
   layer class, and `catalogue/` with the 13 sources of today.
2. **Parts inside**: the index and reader halves of the existing classes split out (`IndexedTiles` is already an
   index base; `TnmBlocks` and `DegreeBlocks` share the window reads); the old class names stay as compositions.
   `pystac-client` and pyogrio take over the STAC paging and Poland's WFS parsing here, each only after a test on
   recorded answers shows the same cached index (see "Ready implementations of the interfaces").
3. **Generated lists, `tools/check_source.py`, the source probe.**
4. **Regions and neighbours** (a behaviour change: new regression entries at borders).
5. **Sources by value and cost**: first those whose parts exist (England, Lower Saxony, Saxony-Anhalt, Hesse,
   Bolzano, Austria, Wales, Luxembourg, Denmark with a token), then each new part with the sources it unlocks:
   ImageServer (Czechia, Sicily, Ontario, Queensland, Colombia), STAC + windows (Canada, ArcticDEM), WFS + WMS-R
   (France), Metalink (Bavaria, Rhineland-Palatinate), ATOM (Norway, Thuringia), listings (Trento, North
   Rhine-Westphalia, Scotland, British Columbia, Tokyo), XYZ tiles (Japan); the survey's tables give the order
   within each group.

Rough costs, from the sources added so far: steps 1–2 two to three days with full regression runs, step 3 one to
two days; a source with existing parts half a day with its checks; a new part one to two days with its fake-server
test.
