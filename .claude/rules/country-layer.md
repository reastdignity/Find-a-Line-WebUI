---
paths:
  - "country.py"
  - "countcube.py"
  - "relief.py"
  - "tools/band_study.py"
  - "tools/border_study.py"
  - "tools/perf_country.py"
  - "tests/test_country*.py"
  - "tests/test_count_mode.py"
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
  of before), which `countcube.TileCounter` does not read yet (cube v2); its anchors' prominence and drop come from a
  `linesearch.LazyAnchorValues` asked with each part's passing pairs, on crops of the grid, so `terrain.py` must give
  any subset of the anchors the values it has among all of them:
  `tests/test_units.py::test_prominence_and_drop_of_a_subset`, `tests/test_count_mode.py`); `find_valid_lines` with
  and without a sink gives the same lines and stats, the sink's parts evaluated by `evaluate_lines` as the others
  (`tests/test_count_mode.py`); `fixed_tiles` and `_tiles` build their grids through `tile_grid` with `_overlap`, so
  `count_tile` over fixed tiles gives one grid's lines (`test_count_tile_over_fixed_tiles`); `covered_pixels > 0`
  equals `covered_metres > 0` (the same kernel) at 0.5 m or coarser, the water flag of the cube. The memory of a
  counting worker is `country.COUNT_PIXEL_BYTES` with `WORKER_BASE` (not `search.PIXEL_BYTES`: a count keeps no
  lines): a change of what step 1 in strips (`filling.STRIP_PX`, the labels) or steps 2-3 hold per pixel or per anchor
  is measured again on the tiles' meta (`memory.stages` of `_MemorySampler`, `country profile`).
- The cube's bins and the layer's filters: `countcube.LENGTH_EDGES`, `EDGES`, the key's layout and `Filters`'
  semantics (an unknown prominence fails every limit, the wall is `max(angle1, angle2) < limit`, a filter at its first
  edge is off, as `viewer/src/filters.ts` filters a run) go with the page `#layer` (its choices from `cube.json`'s
  `edges`, its query `cellsQuery`: the keys of `Filters.parse`), the types `CountryCube`, `CountryBand`,
  `CountryCells`, `CountryHistogram`, `CountryOutline` of `viewer/src/app/api.ts` (mirroring `cube.json` of
  `countcube.build` and `country.py`'s `info`, and the answers of `web.py`'s `/api/countries*`: the histogram's 9
  length bins (`LENGTH_EDGES`) and 6 bins of each 3-bit dimension (the bins 0-4, `UNKNOWN` last), which
  `LayerHistograms.tsx` draws and turns into filters; the canned `KIT_CUBES`, `kitCells`, `kitHistogram` and
  `kitOutline` of `ui/Gallery.tsx` too, the source of `?ui=kit-layer`), the page's mirror of the server's cell guard
  (`layerState.ts` `requestCells`: the box clipped to a cube's bounds plus a degree, as `Cube.box`, under
  `REQUEST_CELLS_MAX` 16000 against `web.COUNTRY_CELLS_MAX` 20000) and the 400 whose message holds "too many cells",
  which the page matches. A change of the edges or the layout is a new `countcube.VERSION`: the tiles are counted
  again. A new parameter of the search goes into the cube when the count needs no extra computing for it (the user's
  rule of 2026-11-05: docs/country-precompute.md, section 6.3, with the eight waiting for the next recount). The next
  layout of the key (two int64: the eight new parameters, the border and partner fields, the cells of a global 30″
  lattice) and the counting across borders are the contract of docs/country-precompute/contract.md section 6
  (2026-11-05, not coded yet): a change of the key, the origin or the spot id is made there first.
- The country layer's runs: `country.config_hash` (the config and the outline, with the surface model also
  `obstacles.RULE`) and `countcube.VERSION` decide when tiles are counted again: a change of `COUNTRIES` or of the
  outline needs `country run <id> --redo`, and a change of what a band's search finds (the anchors, the line test)
  should change the config or the version too, or old tiles stay in the cube. `TileWork.count` calls
  `search.prepare_data(statistics=False, strips=True)`: the cube holds no terrain histogram. `country.form_params`
  gives `SearchParams` fields (cube.json's `params`, the app's search of a cell): a renamed field changes it.
  `web.Countries.cells`' rows (`[i, j, count, lat, lon of SW, SE, NE, NW]`) and `cut` (`Cube.cut`'s `km2` and `shape`)
  are `CountryCells` of `viewer/src/app/api.ts`, also the canned `kitCells`' `cut`; `tests/test_country_web.py` checks
  the answers against `countcube.Cube` and the page in Edge. A study area (`Country.study`, `cube.json`'s `study`) is
  never added to a country: the page counts `layerState.ts` `activeCubes`, and `_partition` neither cuts it nor cuts
  by it; `area.geojson` is written once, so `_partition` reaches only a country set up after its neighbour (a country
  set up before keeps its outline, and `_say_overlaps` warns).
