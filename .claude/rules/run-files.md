---
paths:
  - "mapping.py"
  - "grouping.py"
  - "runs.py"
  - "linestore.py"
  - "hypsometry.py"
  - "viewer/src/types.ts"
  - "viewer/src/result/load.ts"
  - "viewer/test/rows.ts"
  - "tests/old_scripts.py"
  - "viewer/src/grouping.ts"
  - "viewer/src/keys.ts"
  - "viewer/src/favourites.ts"
  - "viewer/src/folders.ts"
  - "viewer/src/shore.ts"
  - "viewer/src/shoreLayer.ts"
---
# A run's files, grouping, terrain statistics

What each module holds: docs/code-map/search.md and docs/code-map/viewer.md. Related rules: `web-app.md` (`RUN_FILES`,
`FavouriteLine`, the folders' rules in `jobs.py`), `view3d.md` (the patch's shore kinds), `sources.md`
(`shore_segments`, `water_with_data`).

## Must stay in sync

- `mapping.group_lines` (Python) and `groupLines` (`viewer/src/grouping.ts`): the same greedy algorithm with the same
  cell index and the same order of the lines (`_rank` / `compare`: clearance, longest, height); the browser must
  produce the same groups. Values used for grouping are passed to the viewer unrounded. The viewer may show another
  line of a group than its representative (chosen by the user: `chosen` in `result/model.ts`, keys from `keys.ts`),
  but never changes the members of a group. Python's grouping is `mapping._cell_index` and `grouping.greedy` (numba):
  the same cells, candidates and float64 tests (`dx*dx + dy*dy <= d2`, x first) as `grouping.ts`;
  `tests/test_units.py::test_grouping_as_before` keeps the dict version of 792efad as the reference,
  `test_grouping_matches_python` compares Python with the browser.
- The run's head (`mapping.map_head`: the store's metadata; `ortho.wms_version` only when not 1.3.0, `ortho.wms_crs`
  only when not EPSG:4326), the list in `runs.write_index` (`runs.js`) and their types in `viewer/src/types.ts`
  (`RunHead`, `RunInfo`). The run's `terrain` (`hypsometry.statistics`) is in run.json (and the `"findaline"` part of
  lines.geojson) and the head (`Terrain`, `RunData.terrain`); runs saved before 2026-11-03 have none, and their lines
  pass the percentile filters (the line details say "percentile not known"). Since store wave 4's item 5 no page reads
  a run's data.js or lines.js; `tests/old_scripts.py` keeps a frozen copy of their writers for the tests (the tools'
  old runs, the Node units' rows: `viewer/test/rows.ts`).
- `hypsometry.statistics` and the viewer's `percentileRank` (`viewer/src/types.ts`): `quantiles[p]` is the lower edge
  of the first 0.1 m bin whose cumulative count reaches max(1, ceil(p·n/100)), and the rank of a height z is max{p :
  quantiles[p] <= z} (0 below `quantiles[0]`), Python's `(100 * C[bin(z)]) // n` for a saved height
  (`tests/test_viewer.py::test_percentile_rank_matches_python`): a change of the bins or of that definition changes
  both, and old runs keep the quantiles they were saved with. `sources.filling.water_with_data` (the lakes of the
  water body mask, the shore zone at most `SEA_LEVEL_TOLERANCE` high or within `SEA_FILL_EPS` of `Source.sea_fill`) is
  both the water with data that `fill_water` keeps in its water mask and what the statistics leave out of the land
  (`tests/test_hypsometry.py::test_water_with_data_is_fill_waters_rule`); on the surface model it is the sea surface
  that `fill_shore_from_surface` leaves to `fill_water` (the exact shoreline), and the pixels it fills above it are
  filled data (`Data.covered`, with the gaps), never `water` and never a seam.
- The text of `lines.csv` and `lines.geojson` (and of the frozen `tests/old_scripts.py`'s data.js and lines.js) is
  built column by column (`runs._rows`, `map_rows`: `runs.column_texts`, `runs.round_floats`), byte for byte what
  `csv.DictWriter` and `json.dumps`
  of the rows as Python values with `round()` wrote (not `np.round`: it differs in halfway cases);
  `tests/test_units.py::test_saved_text_as_before` keeps that old code as the reference. A new column goes into that
  reference too. The rows are ordered part by part (`runs.rep_positions`, `runs.row_order(groups, lo, hi, at)`: the
  old stable order, each representative first, then the other members in their order;
  `tests/test_units.py::_old_row_order` keeps the old lexsort as the reference). Since store wave 4 a run keeps no
  text file: `lines.csv`/`lines.geojson` are this text made by `linestore.export` (the command `export`, a download).
- The store (`linestore.py`, `lines.arrow`/`profiles.arrow`, docs/line-volume/spec-store.md 1.3) is the one schema
  of a run's lines: `linestore.COLUMNS` keeps each value at the decimals data.js printed (the field's `decimals`; the
  grouping's values float64 unrounded) and the rows that round to -0.0 in `negative_zero`, so `linestore.export`
  writes what the run's `lines.csv`/`lines.geojson` held before store wave 4 byte for byte (`tests/test_linestore.py`;
  `tests/regression.py` checked export = `lines.csv` on every entry until wave 4 and pins the export's sha256). A new column of the lines goes into `COLUMNS` and that
  test too; a change of a column's decimals changes the store's. `lines.csv` prints `water_m`/`filled_m` unrounded:
  the export matches only while the search keeps them at 0.1 m (`covered_metres`). A column no integer holds exactly
  is float64 of round(value, decimals) without `decimals` (the reader takes both). `save_run` writes the store first,
  then `map.html`, `ATTRIBUTION.txt` and `run.json` last with its block `store` (never in the export's `lines.geojson`:
  `export` leaves it out): a folder without run.json is a run being saved. Anything failing between the folder and run.json
  fails the search (`run_not_saved`, no run kept; a tiled run keeps its work state); view columns that fail leave a
  store without them and run.json's `view_columns_failed`. run.json is written whole (`cache.replacing`).
  `has_lines`: `lines.arrow`. The head is `mapping.map_head`'s. Its media type
  `linestore.MEDIA_TYPE` = `web.py`'s `mimetypes` entry.
- The page's reader of the store (`result/load.ts` `readStore`, `storedProfiles`, `STORE_FORMAT`; `types.ts`
  `storedColumns`, `NULL_WHEN_MISSING`: null for clrN, prom, drop as data.js had them, NaN for the others) and
  `linestore.COLUMNS`/`profiles_table`/`FORMAT`: a new column, type, null rule or format goes into both
  (`tests/test_viewer.py::test_store_gives_the_rows_values` compares every value with `linestore.read`'s); the page
  reads the store named by run.json's block `store` in runs.js (`storeOf`, keyed on the run's folder), so
  `runs._listed` keeps that block (a run the list does not name or names without it, and a share link, ask for the
  store's files directly: `STORE_PROBE`); a store that cannot be fetched (a 404: a run without one) or read is a
  `StoreFailed` (`ui.result.store_failed`): since store wave 4's item 5 nothing falls back to data.js or lines.js.
- The result view's columns (view B1, docs/line-volume/spec-view.md B.3) and the page's reader of them (step 3b:
  `result/load.ts` `viewColumns`, `types.ts` `ViewColumns`/`hasView`, the gate `result/spots.ts` `viewOf`):
  `mapping.view_columns`' `by_spot` (inside a spot by mean height as stored, clearance, length, then the
  row; NaN last) and the page's "first line" of a spot and "not beaten" (`spots.ts` `show`, `notBeatenOf`), which
  assume that order; `spot` uint32, `top` uint8, `by_spot` uint32 (`linestore.VIEW`: another type or a missing
  value and the page reads no view), the store head's `sectors` ([{"word", "spots"}] in sector
  order), `box` ([x min, y min, x max, y max], m, the grid CRS), `lengths` ([shortest, longest], m): change both
  sides together (`tests/test_view_columns.py`, `tests/test_view_units.py`). The gate opens today's page for a
  store whose head disagrees with its columns (the sectors' spots not adding up, an anchor outside `box` by more
  than 1e-6 m: `box` is of the unrounded anchors, as the columns are). The spots are `group_lines`' members,
  renumbered by sector; the result view does not regroup them (D-12 a).
- `top` (`mapping.top_level` = `tools/prune_study.py`'s `higher_wins`, `STACK_CELL`/`STACK_STEP`) and the text of
  "Top level only"'s count (the lines whose `top` is 0), still to be built: a change of the rule changes its meaning.
- A row of the tests' `data.js` ends with the profile (`row[-1]`); new columns go before it (`viewer/test/rows.ts`
  `toLine`, `lineColumns`; `types.ts` `ROW_FIELDS` or `EXTRA_FIELDS`, `lineAt` and `LineCursor`); the head's
  `ends` names the values before the profile of a run with the no-fall zone or the A-frames (`runs.END_FIELDS` =
  `helpers.END_VALUES` = `types.ts` `END_VALUES`: `lift_needed`, `lift_no_zone`; a run without them has no such key,
  no such columns in `lines.csv`/`lines.geojson`, and today's bytes). A run made with the square rule
  (`--same-line-square`) has the lines' column `stands_for` (`samelines.COLUMN` = `runs.STANDS_FOR` = `types.ts`
  `STANDS_FOR`): the last column of `lines.csv`, the last property of a feature, the last name of `ends` and value
  before the profile, with `square` and `found` in the head (`mapping.map_head` from run.json's
  `params.same_line_side` and `summary.found`); `Line.stands_for` is never sent with a favourite.
- The access mark (`--access`, `access.py`): `access1`, `access2` (uint8: 0 hard access, 1 cannot tell, 2 easy
  access; `runs.ACCESS` = `linestore.ACCESS`) after the anchors' columns of `lines.csv` and a feature's properties,
  before `stands_for`; names in the head's `ends` after the A-frame heights and before `stands_for` (`mapping._ends`
  from run.json's `params.access`; in the tests' data.js rows the values at those places); two uint8 columns
  (`"mark"`) of the store; `web.FavouriteLine` keeps them optional (`OPTIONAL`); a run without the option has none
  and today's bytes (`tests/test_units.py::test_saved_text_as_before`, `tests/test_access_search.py`). The page
  reads them by their names in `ends` and from the store's two columns (`types.ts` `ACCESS`, `Line.access1`/
  `access2`, null without; `favourites.ts` sends them only for a line that has them; viewer.md: the access mark). A
  mark asked but left out (the area too wide: `search._check_access`) makes the run of a search without the option
  plus `"access_skipped": "memory"` in run.json and the store's head (`mapping._ends`) =
  `types.ts` `RunHead.access_skipped`.
- An old run (docs/line-volume/spec-store.md 2.2) is what `runs.run_state` does not call "current" (no
  lines.arrow of `FORMAT` with `VIEW`'s columns, but for run.json's `runs.VIEW_FAILED`: today's run whose view
  columns failed): `runs.old_runs` sorts the runs of `findaline.py runs remove-old` by it, so a new `FORMAT` or view
  column makes every run of before old (removed on the user's word, never converted). A read error is never "old"
  (`linestore.store_state` "cannot_read": skipped). A removal renames the folder first (`runs.park_run` to
  `_removing-<id>` under the runs lock, then the rows, then `runs.finish_removal` outside it): `Jobs.delete_run` and
  `runs_main` alike. The dry run writes nothing in the data folder (`jobs.run_facts` reads a checked copy).
  `tests/old_runs.py` makes the runs of before for those tests (no store, their text files, BASE's `MAP_HTML`
  without the disk notice).
- The uncertain shore: `sources.filling.shore_segments`' dict is run.json's and the head's `shore`
  (`mapping.map_head`; `runs._listed` leaves it out) and `Shore`/`ShoreSegment` of
  `viewer/src/types.ts` (`shore.ts`, `shoreLayer.ts`); runs saved before 2026-11-05 have none and show no layer. The
  3D patch's kinds (`search.encode_shore`: `sources.filling.shore_rows` on the patch's samples, one byte each,
  deflated after the heights; the meta's `shore_bytes`/`shore_sha256`, docs/3d-view-contract.md "Body") are split off
  by `view3d/decode.ts` `decodePatch` (`Patch.shore`) and checked by `web.patch_body`; the kinds' values (1 surface, 2
  sea) are `SHORE_SURFACE`/`SHORE_SEA` in both filling.py and `view3d/shore.ts`.
- Where a run's terrain came from: `sources.filling.terrain_origins`' dict is run.json's `terrain_sources` (None when
  nothing was filled) and the head's only when known (`mapping.map_head`: a run without it keeps the head of
  before; `runs._listed` leaves it out), and `TerrainSources` of `viewer/src/types.ts`; its land takes
  the statistics' rule (`water_with_data`) after the gap filling, so `land_km2` less the neighbours' and fallbacks'
  km² is the run's `terrain.km2` (the source's own land, counted before the filling).
- A tiled search keeps what `save_run` needs of step 1 in its run folder, written after step 1 and read back by a
  search resumed with no tile left (it skips step 1): `shore.json`, `terrain_sources.json` and `data_used.json`
  (`search.SHORE_FILE`, `ORIGINS_FILE`, `USED_FILE`: the shore, the terrain's origins, `src.used_data` for run.json's
  `data` and credits and the profiles at tile edges); a run without `data_used.json` runs step 1 once more. Anything
  else `save_run` or the edge profiles take from step 1 is kept there too
  (`tests/test_offline.py::test_resumed_area_keeps_step_one`). They are work state: never in `web.RUN_FILES`.
- A run's record of the data it read is the key `identity` (a data entry's `sha256` parallel to its `paths`, a local
  file's `size`/`modified`, the coastline's `edition` or tiles; the `area` block's OSM tiles and Nominatim answers;
  the top level's library versions, `slope_file`, `mixed`): with every `identity` removed run.json is what it was
  before; `runs.without_identity` is its one exit (`public_meta`, `_listed`, a country tile's data), so nothing that
  leaves a run carries it (`tests/test_data_record.py`). `data_used.json` is `{"data", "mixed"}` (a list of before:
  not mixed); a resumed session that read other data marks the run `mixed` (`search._record_differs`). The checksums
  come from `cache.touch`'s SELECT of `fetched_at` (entries keep `fetched`, `cache status` reads both); the touch runs
  after the mosaic read the files, so a file replaced in between is recorded as read (a known limit).
- Favourite lines are known by their anchors joined (`keys.lineCoords`, also the `#line=` of a map's link): the
  store's int32 of 1e-7 degree, the same doubles as the 7 decimals data.js and lines.js had: a change of
  how the store keeps the anchors loses everyone's favourites (decide their migration). Their values, `web.FavouriteLine`, are the fields of `Line` in `types.ts`
  (`lift_needed`/`lift_no_zone` optional: null on a run without the options) (`favourites.favouriteData` /
  `favouriteLine`): a new field of `Line` that the app's tab should show goes into all three. The derived
  `pct1`/`pct2` (the anchors' percentile ranks, from the run's terrain when it is loaded: `toLine`, `measuredLine`)
  are never stored: favourites leave them out (`favouriteLine` sets them null). The rules of folders (not into
  themselves or their own folders, `FOLDER_DEPTH_MAX`) are `jobs.Jobs.change_folder`/`add_folder` and
  `folders.FolderTree` (`canMove`, `canAdd`, `FOLDER_DEPTH_MAX`): change both.
