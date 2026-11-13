---
paths:
  - "country.py"
  - "countcube.py"
  - "countkernels.py"
  - "relief.py"
  - "tools/band_study.py"
  - "tools/border_study.py"
  - "tools/perf_country.py"
  - "tests/test_country*.py"
  - "tests/test_count_mode.py"
  - "tests/test_countcube.py"
  - "viewer/src/app/c/LayerPage.tsx"
  - "viewer/src/app/c/LayerHistograms.tsx"
  - "viewer/src/app/c/layerState.ts"
  - "viewer/src/app/c/cellsLayer.ts"
---
# The country layer (counts of lines and spots per cell)

What each module holds: docs/code-map/country.md (the tools: docs/code-map/tools.md); the contract:
docs/country-precompute/contract.md; the measurements: docs/country-precompute.md, docs/performance.md.

## Must stay in sync

- The country layer's count mode and the search (docs/country-precompute/contract.md): `search._lines` and
  `search.count_tile` share step 2 (`_anchors`) and step 3's arguments (`_pair_search`), so a change of the anchors,
  the limits or `find_valid_lines`' arguments reaches both (the end zone and the lift too: a country's `options` may
  carry `end_zone`/`anchor_lift`, `country.form_params`; the count mode passes the search's `zones` ladder, so each
  part handed to its sink carries `lift_needed`/`lift_no_zone` (no bucket minima; at 0 / 0 no ladder and the columns
  of before), which `countcube.TileCounter` bins into word B; its anchors' prominence and drop come from a
  `linesearch.LazyAnchorValues` asked with each part's passing pairs, on crops of the grid, so `terrain.py` must give
  any subset of the anchors the values it has among all of them:
  `tests/test_units.py::test_prominence_and_drop_of_a_subset`, `tests/test_count_mode.py`); `find_valid_lines` with
  and without a sink gives the same lines and stats, the sink's parts evaluated by `evaluate_lines` as the others
  (`tests/test_count_mode.py`); `fixed_tiles` and `_tiles` build their grids through `tile_grid` with `_overlap`, so
  `count_tile` over fixed tiles gives one grid's lines (`test_count_tile_over_fixed_tiles`); `covered_pixels > 0`
  equals `covered_metres > 0` (the same kernel) at 0.5 m or coarser, the water flag of the cube. Across a border
  (docs/country-precompute/contract.md section 6, "The borders"): `search._pair_search`'s marks (the partners and the
  country's anchors outside the core), `TileCounter`'s core skip of a line with a border and
  `countkernels.select(border=)` go together (a line across is found by the tile whose core holds its anchor in the
  country and kept there whatever its first anchor in pixel order: `tests/test_count_mode.py`, owned + partner = one
  grid's lines across the split); `search._BorderSides` and `TileCounter` take the anchors to WGS84 through the same
  transformer (`countcube._to_wgs84`), so both pick the same first anchor by (lon, lat); without `Plan.partners` no
  array reaches the kernel and the pairs are those of before. The memory of a counting worker is
  `country.COUNT_PIXEL_BYTES` (`COUNT_SURFACE_PIXEL_BYTES` with a surface model) with `WORKER_BASE` (not
  `search.PIXEL_BYTES`: a count keeps no lines): a change of what step 1 in strips (`filling.STRIP_PX`, the labels) or
  steps 2-3 hold per pixel or per anchor is measured again on the tiles' meta (`memory.stages` of `_MemorySampler`,
  `country profile`).
- The cube's bins and the layer's filters: `countcube.LENGTH_EDGES`, `EDGES`, `KINDS`, the key's layout (two words)
  and `Filters`' semantics (a floor passes at or above its edge, a "below" under it, an at_most at most it; a filter
  at its first edge (a "below" but the wall) is off; an unknown value fails every filter that is on; the wall is
  `max(angle1, angle2) < limit`; `border` all or own with `replaced`; as `viewer/src/filters.ts` filters a run) go
  with the page `#layer` (its controls and charts from `cube.json`'s `edges` and `kinds`: the sixteen dimensions by
  topic, `layerState.ts` `TOPICS`, `limitOn`, `limitEdges`, `SEVEN` open and the others in the fold; its query
  `filtersQuery` (`cellsQuery`): the keys of `Filters.parse`, each dimension by its name, `border`), the types
  `CountryCube`, `CountryBand`, `CountryCells`, `CountryHistogram`, `CountryOutline` of `viewer/src/app/api.ts`
  (mirroring `cube.json` of `countcube.build` and `country.py`'s `info`: `cell_deg`, `edges`, `kinds`, `neighbours`
  (the partner index k, 1-6, is the k-th, in `Source.neighbours`' order through `country.NEIGHBOUR_CUBES`; 7 unknown),
  `totals.border` (`{lines, spots}` each `{owned, partner}`), `profile` (a sha256); and the answers of `web.py`'s
  `/api/countries*`: the rows' side (0 the country's own lines, border 0 and 1; else the partner index of its border-2
  lines: a cut cell under `border=all` is two rows), the `cut` keys `"i,j"` and `"i,j,out"`, the histogram's 9 length
  bins and each dimension's `bins_of` + 1 (6, 7 for an at_most; `UNKNOWN` last), its `totals` and `border`, which
  `LayerHistograms.tsx` draws and turns into filters; the canned `KIT_CUBES`, `kitCells`, `kitHistogram` and
  `kitOutline` of `ui/Gallery.tsx` too, the source of `?ui=kit-layer`), the page's mirror of the server's cell guard
  (`layerState.ts` `requestCells`: the box clipped to a cube's bounds plus a degree, as `Cube.box`, in cells of the
  lattice, under `REQUEST_CELLS_MAX` 16000 against `web.COUNTRY_CELLS_MAX` 20000), its mirror of
  `web.Countries.replaced` (`layerState.ts` `replacedPartners`, `summedWith`: listed, no study area, the same profile)
  and the 400 whose message holds "too many cells", which the page matches. A change of the edges or the layout is a
  new `countcube.VERSION`: the tiles are counted again; a line's border field decides both the counter's core skip
  (`TileCounter`, `countkernels.select(border=)`) and the web's mode (`border_kept`), so a change of its values
  changes both. A new parameter of the search goes into the cube when the count needs no extra computing for it (the
  user's rule of 2026-11-05: docs/country-precompute.md, section 6.3). The key v2 (wave A: the eight parameters, the
  border and partner fields, the global 30″ lattice), the counting across borders (wave B) and the web's border and
  its two rows of a cut cell (wave C) are the contract of docs/country-precompute/contract.md section 6: a change of
  the key, the origin or the spot id is made there first.
- The country layer's runs: `country.config_hash` (the config, the profile's sha256 and the outline, with the surface
  model also `obstacles.RULE`) and `countcube.VERSION` decide when tiles are counted again: a change of `PROFILE`, of
  `COUNTRIES` or of the outline needs `country run <id> --redo` (every `country.json` written before the profile is
  refused: `--redo`), `NEIGHBOUR_CUBES` names every source of any `Source.neighbours` (`test_neighbour_cubes`), and a
  change of what a band's search finds (the anchors, the line test) should change the config or the version too, or
  old tiles stay in the cube. `TileWork.count` calls `search.prepare_data(statistics=False, strips=True)`: the cube
  holds no terrain histogram. `country.form_params` gives `SearchParams` fields (cube.json's `params`, the app's
  search of a cell): a renamed field changes it. `web.Countries.cells`' rows
  (`[i, j, count, lat, lon of SW, SE, NE, NW, side]`) and `cut` (`Cube.cut`'s and `Cube.cut_outside`'s `km2` and
  `shape`, keyed `"i,j"` and `"i,j,out"`) are `CountryCells` of `viewer/src/app/api.ts` (`cellsLayer.ts` `rowSide`,
  `cutKey`), also the canned `kitCells`' rows and `cut`; `tests/test_country_web.py` checks the answers against
  `countcube.Cube` and the page in Edge. A study area (`Country.study`, `cube.json`'s `study`) is never added to a
  country: the page counts `layerState.ts` `activeCubes`, and `_partition` neither cuts it nor cuts by it;
  `area.geojson` is written once, so `_partition` reaches only a country set up after its neighbour (a country set up
  before keeps its outline, and `_say_overlaps` warns).
- `tests/cube_oracle.py` is `Cube.cells`/`Cube.histogram` of b45b950 frozen, the oracle the lean code's answers are
  compared with (`test_lean_answers_equal_the_oracle`, `test_answers_equal_the_oracle`): a change of what an answer
  means (the filters' semantics, the key) changes it in the same commit, a change of speed or memory never does.
- A cube's arrays are never replaced in place (`Cube` maps them; Windows refuses to replace or remove a mapped file,
  and on Linux a file overwritten or truncated under its map kills the web process, SIGBUS: copy a cube by hand only
  into a new folder):
  `countcube.build` writes each build into a new folder of `BUILD_PATTERN` and `cube.json`, naming it (`arrays`), last;
  `remove_stale` (the builder at its end, `web.Countries` once it dropped an old build's maps) removes only build
  folders older than the named one and a cube built before's `ARRAY_FILES`, never a link; `deploy/push-cube.sh` copies
  the named build by the same pattern (`tests/test_deploy.py::test_push_cube_copies_the_named_build`).
