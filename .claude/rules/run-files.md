---
paths:
  - "mapping.py"
  - "grouping.py"
  - "runs.py"
  - "saving.py"
  - "hypsometry.py"
  - "viewer/src/types.ts"
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
- A row of `data.js` ends with the profile (`row[-1]`); new columns go before it (`toLine` in `types.ts`); the head's
  `ends` names the values before the profile of a run with the no-fall zone or the A-frames (`runs.END_FIELDS` =
  `helpers.END_VALUES` = `types.ts` `END_VALUES`: `lift_needed`, `lift_no_zone`; a run without them has no such key,
  no such columns in `lines.csv`/`lines.geojson`, and today's bytes).
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
