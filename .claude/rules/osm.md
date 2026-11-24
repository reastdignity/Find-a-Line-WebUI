---
paths:
  - "osm.py"
  - "osmextract.py"
  - "coast.py"
  - "tools/study_landcover.py"
---
# OSM data and the coastline

What each module holds: docs/code-map/sources.md (`osm.py`, `coast.py`, `osmextract.py`).

## Must stay in sync

- OSM themes and their two readers: `osm.fetch_tile` (Overpass's "out geom", `osm.THEME_TAGS`) and
  `osmextract._take_features` (the extracts, the themes of `EXTRACT_THEMES` only) write the same GeoJSON features
  through `osm.feature`: a relation's member ways in the same order, their roles in `properties["roles"]` ("" for
  none: `osm._geometry` and `_take_features`), which `osm.polygons` reads
  (`tests/test_osm.py::test_overpass_relations_keep_their_roles`, `test_extract_features_with_roles`). A theme taken
  from the extracts is in `EXTRACT_THEMES`: adding one makes `osm update` take every extract's features again
  (`_missing_themes`), and `build_tile` builds no tile of a theme a `themes.json` lacks.
- A source's region inside a larger Geofabrik extract is named in `osm.GEOFABRIK_OF_CODE` (its ISO code → that
  extract: it-23 nord-ovest, pt-30 portugal, it-52 centro, gb-nir ireland-and-northern-ireland), a source covering
  part of a region in `GEOFABRIK_OF_SOURCE` (rio_de_janeiro → sudeste, the French overseas): `osm.catalogue_extracts`
  then lists that extract, which the VPS downloads (`deploy/vps.sh` `osm_data`, `OSM_EXTRACTS_SKIP`;
  `tests/test_osm.py`). Check the name in Geofabrik's index.
- The texts `tests/regression.py` reads: `coast.py`'s coastline sources (`SOURCE_*`, stored as each entry's
  `coastline` in `tests/regression.json`) and `FALLBACK_WARNING`, `osm.DAY_MAX_TEXT`, `net.UNREACHABLE_TEXT`. It
  tells a changed result from an unverified one by them: a reword of a source text stores the baselines' `coastline`
  again in the same commit (`test_every_stored_coastline_is_a_named_text` fails until then).
- R17 (the Malta extract's coastline and cliff tiles against Overpass's) is left out of `--all` (`"by_name": true`):
  after a change of `osm.py`'s theme tiles or `osmextract.py` run it by name, at most once a day while Overpass does
  not answer (12 queries a run), and report it as not checked until it has run.
- `osm update` of an extract rebuilds the theme tiles built from it: the regression entries that take an area from
  them (`--area coast`: R16, R18, R83, Malta) run on the real cache afterwards, and are re-baselined if OSM changed.

## Pitfalls

- **Public services are flaky**: Overpass is often overloaded and slow (30–70 s per 0.25° theme tile; the world file
  in `cache/osm/water-polygons/` is used instead when present; inland areas skip the coastline); an OpenTopography key
  allows 50 calls a day (200 for academics), one user, one key; Nominatim allows 1 request/s. Both limits hold across
  all processes of a data folder (CLI, web, worker, phase processes): Nominatim requests go through `osm._ask` (a
  pyrate-limiter `SQLiteBucket` in `cache/osm/nominatim-rate.sqlite`, one per 1.1 s; cached answers never touch it),
  Overpass queries through `osm._overpass_turn` (`filelock` on `cache/osm/overpass.lock`, one at a time,
  `requests.Timeout` after 10 min); never call either service around them. Tile downloads of the elevation layers
  (`Layer._download_and_record`) take one of `HOST_SLOTS` (8; `HOST_SLOTS_OF` per host) slots of their host
  (`sources.host_slot`: lock files `cache/locks/hosts/<host>.<n>.lock`, tried in turn, polled while all are taken) and
  the tile's lock (`sources.tile_lock`: one of `TILE_LOCKS` files in `cache/locks/tiles/` by the path, so a second
  search waits and then finds the tile cached: `download_layers` checks `cache.due` again under it; the cached index
  answers of `IndexedTiles._index_tile` too); both are OS locks (a killed process releases them) on a fixed number of
  files (filelock leaves them on Linux, deletes them on Windows); `cache/locks` is no dataset (`cache.LOCKS`, left out
  of `cache status`). A user's quota of uncached Nominatim requests is `osm.BEFORE_REQUEST`, set by the web worker per
  job or quick task (`jobs.nominatim_quota`); it raises `jobs.QuotaExceeded` (a `ValueError`, so an optional lookup
  such as a run's place name goes on without it) before the request. Every request sends `cache.http_headers()` (one
  User-Agent; the operator's contact from `FINDALINE_CONTACT` on a public site). Failed Nominatim lookups are asked
  again after 30 days; outlines above 5 MB are stored simplified.
- **pyosmium**: the extracts are read in three filtered passes (tagged objects, ways of relations, nodes by id)
  instead of `with_locations()`, whose node index for Poland would take gigabytes; Poland (2.1 GB) takes about 10 s. A
  theme tile comes from the extracts when the part outside their outlines lies in no other country of the Geofabrik
  index (open sea); a coastal tile is rarely covered whole by a country's outline. Overpass is one server,
  overpass-api.de (`FINDALINE_OVERPASS_URL` replaces it; maps.mail.ru was dropped after it answered 504 to everything
  on 2026-11-01), at most `osm.OVERPASS_DAY_MAX` (75, the user's choice; the OSM wiki asks below 100 a day summed over
  all users of an app) queries per UTC day per data folder (`FINDALINE_OVERPASS_DAY_MAX`, counted in
  `cache/osm/overpass-day.sqlite` under the query lock); over it `osm.OverpassDayMax` (a coded `requests` error,
  `overpass_day_max`): the coastline falls back to the Copernicus mask, `--area coast/cliffs` are refused; after a
  429/406 a pause of at least 30 s for all processes; the VPS keeps the world water polygons and the catalogue's
  Geofabrik extracts (`deploy/vps.sh` `osm_data`, `osm.catalogue_extracts`), so the public site rarely asks Overpass.
  Geofabrik keeps dated extracts (`<region>-YYMMDD.osm.pbf`), handy for testing the diffs. The OSM world water
  polygons are regenerated daily, so they are only checked after a year (a check means a 900 MB download).
- **OSM land cover never comes from the extracts**: woods, forests, bare rock and scree are about 100 times the other
  themes (Poland's `themes.json` 8.8 MB → 936 MB, 6.2 GB of memory and 9 s to load in every process building a theme
  tile, 199 s to take instead of about 10 s; measured 2026-11-03), so `osmextract.EXTRACT_THEMES` holds `coastline`
  and `cliff` only and `landcover` comes from Overpass, one query per new 0.25° tile under the daily cap (75): a study
  of many places fills its tiles over a day or two (kept a year, `cache.TTL_DAYS["osm-theme"]`). OSM maps land cover
  unevenly: a wood without a polygon is `NONE`, not rock, so only `FOREST` and `ROCK` of `tools/study_landcover.py`
  say something.
