---
paths:
  - "mapping.py"
  - "grouping.py"
  - "runs.py"
  - "saving.py"
  - "linestore.py"
  - "hypsometry.py"
  - "viewer/src/types.ts"
  - "viewer/src/result/load.ts"
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
- The run data written by `mapping.save_map` (`data.js`, `lines.js`; `ortho.wms_version` only when not 1.3.0,
  `ortho.wms_crs` only when not EPSG:4326), the list in `runs.write_index` (`runs.js`) and their types in
  `viewer/src/types.ts`. The run's `terrain` (`hypsometry.statistics`) is in run.json (and the `"findaline"` part of
  lines.geojson) and the heads of data.js and lines.js (`Terrain`, `RunData.terrain`, `RunLines.terrain`); runs saved
  before 2026-11-03 have none, and their lines pass the percentile filters (the line details say "percentile not
  known").
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
- The text of `lines.csv`, `lines.geojson`, `data.js` and `lines.js` is built column by column (`runs._rows`,
  `mapping.map_rows`: `runs.column_texts`, `runs.round_floats`), byte for byte what `csv.DictWriter` and `json.dumps`
  of the rows as Python values with `round()` wrote (not `np.round`: it differs in halfway cases);
  `tests/test_units.py::test_saved_text_as_before` keeps that old code as the reference. A new column goes into that
  reference too. The rows are ordered part by part (`runs.rep_positions`, `runs.row_order(groups, lo, hi, at)`: the
  old stable order, each representative first, then the other members in their order;
  `tests/test_units.py::_old_row_order` keeps the old lexsort as the reference). The children of `saving.py` write the
  same text from the memory-mapped copies of the columns and the profiles' batches (`hand_over`/`load`: `.tolist()` of
  a memmap gives the same Python values; run.json's values and the scripts' heads go through JSON, which keeps every
  float, int, null and NaN as it was): `test_saved_by_children_as_in_process` (50 000 synthetic lines, the hard
  floats, a batch's profiles and dict profiles) and `tests/test_offline.py::test_run_saved_by_children_as_in_process`
  (the Żabi Koń clip through `save_run`) compare the files byte for byte with one process's; a new column or a new
  kind of profile value goes into those too.
- The store (`linestore.py`, `lines.arrow`/`profiles.arrow`, docs/line-volume/spec-store.md 1.3) is the one schema
  of a run's lines: `linestore.COLUMNS` keeps each value at `mapping.map_rows`' decimals (the field's `decimals`; the
  grouping's values float64 unrounded) and the rows that round to -0.0 in `negative_zero`, so `linestore.export`
  writes the run's `lines.csv`/`lines.geojson` byte for byte (`tests/test_linestore.py`; `tests/regression.py` checks
  export = `lines.csv` on every entry until the text files end). A new column of the lines goes into `COLUMNS` and that
  test too; a change of `map_rows`' decimals changes the store's. `lines.csv` prints `water_m`/`filled_m` unrounded:
  the export matches only while the search keeps them at 0.1 m (`covered_metres`). A column no integer holds exactly
  is float64 of round(value, decimals) without `decimals` (the reader takes both). `save_run` writes the store after the text files and adds
  run.json's block `store` then (never in `lines.geojson`: `export` leaves it out); a store that fails leaves the run
  without one. `has_lines`: `lines.arrow` or `lines.js`. The head is `mapping.map_head`'s. Its media type
  `linestore.MEDIA_TYPE` = `web.py`'s `mimetypes` entry.
- The page's reader of the store (`result/load.ts` `readStore`, `storedProfiles`, `STORE_FORMAT`; `types.ts`
  `storedColumns`, `NULL_WHEN_MISSING`: data.js's null for clrN, prom, drop, NaN for the others) and
  `linestore.COLUMNS`/`profiles_table`/`FORMAT`: a new column, type, null rule or format goes into both
  (`tests/test_viewer.py::test_store_gives_the_rows_values` compares every value with data.js's); the page reads a store
  only when run.json's block `store` is in runs.js (`storeOf`), so `runs._listed` keeps that block; a store's file
  missing (404) falls back to data.js and lines.js, which runs keep until store wave 4.
- The result view's order (view B1, docs/line-volume/spec-view.md B.3): `mapping.view_columns`' `by_spot` (inside a
  spot by mean height as stored, clearance, length, then the row; NaN last) and the page's "first line" of a spot
  and "not beaten", which assume that order: change them together (`tests/test_view_columns.py`). The spots are
  `group_lines`' members, renumbered by sector; the result view does not regroup them (D-12 a).
- `top` (`mapping.top_level` = `tools/prune_study.py`'s `higher_wins`, `STACK_CELL`/`STACK_STEP`) and the text of
  "Top level only"'s count (the lines whose `top` is 0): a change of the rule changes that text's meaning.
- A row of `data.js` ends with the profile (`row[-1]`); new columns go before it (`toLine`, `lineColumns`' `ROW_FIELDS`
  or `EXTRA_FIELDS`, `lineAt` and `LineCursor` in `types.ts`); the head's
  `ends` names the values before the profile of a run with the no-fall zone or the A-frames (`runs.END_FIELDS` =
  `helpers.END_VALUES` = `types.ts` `END_VALUES`: `lift_needed`, `lift_no_zone`; a run without them has no such key,
  no such columns in `lines.csv`/`lines.geojson`, and today's bytes). A run made with the square rule
  (`--same-line-square`) has the lines' column `stands_for` (`samelines.COLUMN` = `runs.STANDS_FOR` = `types.ts`
  `STANDS_FOR`): the last column of `lines.csv`, the last property of a feature, the last name of `ends` and value
  before the profile, with `square` and `found` in the heads (`mapping.map_heads` from run.json's
  `params.same_line_side` and `summary.found`); `Line.stands_for` is never sent with a favourite.
- The access mark (`--access`, `access.py`): `access1`, `access2` (uint8: 0 hard access, 1 cannot tell, 2 easy
  access; `runs.ACCESS` = `linestore.ACCESS`) after the anchors' columns of `lines.csv` and a feature's properties,
  before `stands_for`; in `data.js`/`lines.js` values before the profile named in the heads' `ends` after the
  A-frame heights and before `stands_for` (`mapping._ends` from run.json's `params.access`); two uint8 columns
  (`"mark"`) of the store; `web.FavouriteLine` keeps them optional (`OPTIONAL`); a run without the option has none
  and today's bytes (`tests/test_units.py::test_saved_text_as_before`, `tests/test_access_search.py`). The page
  reads them by their names in `ends` and from the store's two columns (`types.ts` `ACCESS`, `Line.access1`/
  `access2`, null without; `favourites.ts` sends them only for a line that has them; viewer.md: the access mark). A
  mark asked but left out (the area too wide: `search._check_access`) makes the run of a search without the option
  plus `"access_skipped": "memory"` in run.json and every head (`mapping._ends`: data.js, lines.js, the store's) =
  `types.ts` `RunHead.access_skipped`.
- The uncertain shore: `sources.filling.shore_segments`' dict is run.json's and data.js's `shore`
  (`mapping.map_heads`, not lines.js; `runs._listed` leaves it out) and `Shore`/`ShoreSegment` of
  `viewer/src/types.ts` (`shore.ts`, `shoreLayer.ts`); runs saved before 2026-11-05 have none and show no layer. The
  3D patch's kinds (`search.encode_shore`: `sources.filling.shore_rows` on the patch's samples, one byte each,
  deflated after the heights; the meta's `shore_bytes`/`shore_sha256`, docs/3d-view-contract.md "Body") are split off
  by `view3d/decode.ts` `decodePatch` (`Patch.shore`) and checked by `web.patch_body`; the kinds' values (1 surface, 2
  sea) are `SHORE_SURFACE`/`SHORE_SEA` in both filling.py and `view3d/shore.ts`. A tiled search's `shore.json`
  (`search.SHORE_FILE`) is work state of the run folder: not in `web.RUN_FILES`.
- Where a run's terrain came from: `sources.filling.terrain_origins`' dict is run.json's `terrain_sources` (None when
  nothing was filled) and data.js's head only when known (`mapping.map_heads`: a run without it keeps the head of
  before; not lines.js; `runs._listed` leaves it out), and `TerrainSources` of `viewer/src/types.ts`; its land takes
  the statistics' rule (`water_with_data`) after the gap filling, so `land_km2` less the neighbours' and fallbacks'
  km² is the run's `terrain.km2` (the source's own land, counted before the filling).
- Favourite lines are known by the anchors of their rows in `data.js`/`lines.js` joined (`keys.lineCoords`, also the
  `#line=` of a map's link): a change of how `mapping.save_map` rounds the anchors loses everyone's favourites (decide
  their migration). Their values, `web.FavouriteLine`, are the fields of `Line` in `types.ts`
  (`lift_needed`/`lift_no_zone` optional: null on a run without the options) (`favourites.favouriteData` /
  `favouriteLine`): a new field of `Line` that the app's tab should show goes into all three. The derived
  `pct1`/`pct2` (the anchors' percentile ranks, from the run's terrain when it is loaded: `toLine`, `measuredLine`)
  are never stored: favourites leave them out (`favouriteLine` sets them null). The rules of folders (not into
  themselves or their own folders, `FOLDER_DEPTH_MAX`) are `jobs.Jobs.change_folder`/`add_folder` and
  `folders.FolderTree` (`canMove`, `canAdd`, `FOLDER_DEPTH_MAX`): change both.
