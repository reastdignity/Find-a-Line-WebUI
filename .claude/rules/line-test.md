---
paths:
  - "helpers.py"
  - "linesearch.py"
  - "lineprofiles.py"
  - "terrain.py"
  - "obstacles.py"
  - "sag.py"
  - "viewer/src/sag.ts"
  - "viewer/src/endzone.ts"
  - "tools/line_funnel_kernels.py"
  - "tools/perf_line_funnel.py"
  - "tests/test_end_zone.py"
---
# Anchors and the line test (the numba kernels)

What each module holds: docs/code-map/search.md (the tools: docs/code-map/tools.md). Related rules:
`search-pipeline.md` (steps 2-4 around the kernels), `country-layer.md` (the count mode shares `find_valid_lines`),
`view3d.md` (the reach mask follows `evaluate_line`).

## Must stay in sync

- `sag.py` and `viewer/src/sag.ts`: the same solver; results match to 1e-6 m. `tests/test_viewer.py` checks both pairs
  with Node, and that `viewer/dist` is built from `viewer/src`.
- `linesearch.covered_metres` (metres over water/filled gaps of every line, numba) and `helpers.line_profile`
  (`water_m`, `filled_m`) and `lineprofiles.line_profiles`: the same pixels and formula, rounded as Python's `round()`
  (`covered_metres` whole parts with `runs.round_floats`: `test_covered_metres_as_before` keeps the per-line code);
  `tests/test_units.py` compares them. Areas compute profiles only for the lines shown for groups (`search._lines`;
  the representative of a group joined across tiles gets `profile_of_line` in `search_lines`, the bar "profiles at
  tile edges": none on the Gozo coast's 5 km tiles, 10 on its 9 tiles of a VPS slot, 0.5 s each), circles for all.
- `helpers.line_profile` (one line: `search.profile_of_line`, `/api/profile`, the profiles at tile edges) and
  `lineprofiles._profiles`/`line_profiles` (the profiles of a search): the same pixels, limits (formula and sag, as
  `linesearch._evaluate`), end zone and lift (`helpers.end_zone_rule`), webbing height, thinning
  (`np.linspace(...).round()` keeping both anchors, i_min, i_max and j_min), metres over water and gaps, and the same
  rounding (Python's `round()` for the points, `water_m`/`filled_m` and the clearances; `np.round` for the distances
  of "min", "min_nmpt" and "max_height", which `line_profile` rounds as numpy floats).
  `tests/test_units.py::test_line_profiles_match_line_profile` compares them with `==` and their JSON text;
  `test_line_profiles_independent_of_threads` keeps the batch independent of the thread count. `LineTable.profiles`
  holds a `helpers.Profile` or a dict (tile files of before 2026-11-01, tile edges): read them through
  `helpers.profile_dict`.
- `helpers.max_safe_elevation` defines the clearance limit; `evaluate_line` and `line_profile` use it.
  `linesearch._line_ok` repeats it in numba (formula and sag table; twice, in the loop from the ends and in the
  bit-reversal loop of the middle) and `find_valid_lines` derives the weakest per-anchor limit from it (`gain`, `cap`,
  `offset`): change all three together. All three sample the pixels between the anchors as `r1 + rint(dr * t)` (the
  offset is rounded, not the position: `rint` rounds halves to even, which would make results depend on where the grid
  starts). The kernels may only pass too much, never too little (EPS); `evaluate_line` makes the final decision, so
  results equal the plain pixel-by-pixel search. That decision runs as `linesearch._evaluate` (numba, parallel), a
  copy of `evaluate_line` with the same arithmetic (`_interp` repeats `np.interp` to the last bit, `_interp_forward`
  too with its index walked forward along a line: `test_interp_forward_matches_interp`):
  `tests/test_units.py::test_evaluate_lines_matches_evaluate_line` compares them with `==`. The regression set
  compares the sha256 of `lines.csv` too (with totals: length, clearances), so such a change must leave every checksum
  as it was. The no-fall zone and the A-frames (`helpers.end_zone_rule`) change the comparison only, never the limit:
  a pixel passes when its strict margin exceeds `−lift − δ·[in the zone]`, the same expression in
  `linesearch._line_ok` (`strict`/`lenient`, `_margin_at`), `_evaluate`, `lineprofiles._profiles`,
  `helpers.evaluate_line` and `line_profile`, the zone's steps from `helpers.zone_steps` (its jitted twin
  `linesearch._zone_steps`, `tests/test_end_zone.py`) and the viewer's `endzone.ts` `zoneSteps` (the same integer
  arithmetic; `limits` is the chart's limit with the zone and the lift, `riggingNeed` the pill's reading of
  `lift_needed`/`lift_no_zone`); the ring screen's offsets (`linesearch.ring_offsets`) may pass too much, never too
  little; at `end_zone` 0 and `lift` 0 every float operation is today's (the regression checksums and the frozen
  references of `tools/line_funnel_kernels.py` hold there; `tools/perf_line_funnel.py analyse` refuses a capture with
  the options), and `tests/test_end_zone.py` compares `find_valid_lines` with the brute force over `evaluate_line` at
  the same settings (both models, a surface, `first`, `strong`, a wall limit; nesting over zones and lifts; the sink
  mode; the buckets). The ladder of per-line buckets (`zones`, `helpers.valid_at`) gives "valid at zone j, lift h"
  exactly from `zone_margins`; `lift_needed`/`lift_no_zone` (`helpers.lift_values`) are the two values a run keeps.
- Heights of the webbing above the terrain (`height_max`, `height_mean`, `high_pct` of `--high-above`) are the margin
  below `max_safe_elevation` plus `helpers.fall_allowance` (leash fall or fall zone) plus the A-frames' lift (added
  last and only when not 0: `helpers.webbing_height(margin, sag_table, lift)`, the same in `_evaluate`,
  `lineprofiles._profiles`, `line_profile`'s `max_height` and `Profile.tsx`'s "highest ... above terrain"):
  `helpers.webbing_height`, repeated in `_evaluate` and used by `line_profile` (`max_height`). The mean is summed one
  pixel after another in both (`np.cumsum`, not `np.mean` or `sum()`, which is compensated since Python 3.12). A
  change of `max_safe_elevation` changes the heights too.
- Wall angles: `helpers.downslope` (Horn 3 × 3 at each anchor) and `helpers.wall_angles` give the saved angles and the
  final decision of `--max-wall-angle` (`LineLimits`, in `evaluate_lines`); `_pairs` drops pairs earlier with the
  cosine of the limit, within EPS, so it may pass too many, never too few.
- The obstacle test reads `obstacles.obstacle_surface`, computed once in `search.prepare_data` after the water and gap
  filling (bare: water filled where the terrain had no data): `evaluate_line`, `linesearch._evaluate`,
  `lineprofiles._profiles` and `line_profile` get it as their surface, so they need no change of their own. Its reach
  (`obstacles.reach`, 2 pixels) stays within the grid's margin around the lines (`search._margin` plus the 2 pixels of
  a tile's overlap: tiles give the lines of one grid) and the profile grid's 10 pixels. A run records its rule
  (`Plan.obstacles` = `obstacles.RULE` as `params.obstacles` of run.json) and `search.profile_of_line` applies the
  run's (None, runs before it: the surface model as it is); a change of the rule's parameters goes into `RULE`.
  `Source.obstacles` is False where surface minus terrain is by construction trees and buildings (FABDEM +
  Copernicus). `tools/obstacle_study.py` captures with `obstacles.RULE = None` (the raw surface the rules are compared
  on).
- The line search's results are pinned by `tools/line_funnel_kernels.py`: `ref_line_ok`, `ref_free_rings` and
  `ref_pairs` are frozen copies of `linesearch._line_ok`/`_free_rings`/`_pairs` of 975a1b7, and the `self_check` of
  `tools/perf_line_funnel.py analyse` (also run by `tests/test_units.py::test_free_rings_match_reference`,
  `test_pairs_match_reference`, `test_line_ok_matches_reference`) stops when production differs from them: the rings
  must be the references' capped at `linesearch.largest_need` (`capped_rings`: every decision compares a ring with a
  need up to it); the useful anchors, the checked and found counts per anchor and the written pairs must be equal; the
  candidates must be the references' less the pairs N1 and F8c skip (`funnel_pairs`' `C_N1_CANDIDATES`,
  `C_F8C_CANDIDATES`: they fail the rings' test, which comes after the count, so "Candidate pairs" and F19's
  `candidates` dropped on 2026-11-01 and again on 2026-11-03 while open, checked and found did not); `funnel_pairs`'
  F8c is production's rule written out again (the tool's `_arc` is a copy of `linesearch._arc`,
  `tests/test_units.py::test_cell_sectors_hold_every_pixel` keeps them equal and every pixel's `_sector` within the
  cell's sectors; `test_f8c_skips_only_rings_failures` runs the self-check on random grids; `C_F8C_PARTNER_OWN`,
  `C_F8C_PARTNER_MASK`, `C_F8C_MASK_CANDIDATES` the parts of the rule). `rebuild` mirrors the set-up of
  `find_valid_lines`, and the tool reaches production only through `free_directions`, `pair_arguments` and
  `pair_chunk` (`production_directions`, `production_args`): change them together. A faster kernel must keep all of
  that: the order of the found pairs is part of the output (the stable sorts by length and of the groups carry it into
  `lines.csv`), so a skip rule may only skip pairs that fail before `_line_ok`, while `_line_ok` may test the pixels
  in any order (`funnel_pairs` simulates production's as the order "production": `LINE_ORDER_SPLIT`,
  `LINE_ORDER_MAX`). `pair_chunk` writes the pairs of the anchors that fit its buffer from the buffer and those of the
  others by a second pass with `offsets`: both keep the order of the visits per anchor and the anchors in the order of
  todo (`tests/test_units.py::test_pair_buffer_overflow_matches_reference` forces the second pass with buffers of 1
  and 3 pairs; the count mode's buffer of `SINK_PAIR_BUFFER` pairs per anchor writes the same pairs in the same order:
  `test_sink_pair_buffer_as_the_search_path`). The references change only by a decision that the counters may change
  (re-baselining the regression's open and checked counts and `ZABI_KON`).

## Pitfalls

- **numba** compiles `linesearch.py` on the first run (a few seconds, cached in `__pycache__`). Inside `@njit` code
  only numpy/math and module constants work; keep the float operations in `_line_ok` in the same order as
  `max_safe_elevation`. Results must not depend on the number of threads (`--threads`, `NUMBA_NUM_THREADS`): in a
  `prange` loop no float sum across iterations (its order follows the split between threads) and no `np.sum`/`mean` of
  an array inside `parallel=True` code; each iteration writes at its own index (count first, then offsets, as
  `_pairs`). `tests/test_units.py::test_kernels_independent_of_threads` keeps that. A new kernel, or new argument
  types of one (an optional array, a dtype, a view): a search of `warmup.SEARCHES` that gives them, or the public
  worker's first job after a start compiles it (`test_numba_warm_up` fails).
- **Open findings of the truth check** (2026-11-08, not fixed; listed in docs/known-bugs.md): `findaline.py` on
  Windows cannot delete its work folder after a search that stops without lines ("Could not delete the work folder":
  the memory-mapped grids are still referenced by the exception in flight; seen on the Żabi Koń clip too;
  `tools/truth_study.py run` removes the folders its children leave); `sources/readers/sheetfile.py` `_xyz_grid` reads
  an XYZ sheet with `np.loadtxt`, which takes a UTF-8 byte order mark for part of the first number (three Polish
  sheets: "could not convert string 'ï»¿640160.00'"), so the search fails; `helpers.zone_steps` takes the `ceil` of
  `min(end_zone, ZONE_CAP·L)·steps/L`, which on a slightly diagonal line under the cap gives 15.000000000000002 → 16
  steps, one more than 25 % (its twins `linesearch._zone_steps` and `endzone.ts` repeat it, so a fix changes all three
  and the end zone's results).

## Verifying changes

- A change of the anchors (step 2), the line test (`linesearch`, `helpers.evaluate_line`, the limits and their
  defaults) or the obstacle rule (`obstacles.RULE`) is also measured with the truth check (docs/truth-check.md): a
  pass of `tools/truth_study.py` from the cache before and after (`cluster` gives the same clusters on the same data),
  `analyse`, `report`, and the recall per type and source, the reasons and the zone x lift table compared; aggregates
  only in anything committed.
