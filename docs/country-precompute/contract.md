# Contract of the Slovakia pilot (waves 1 and 2)

The shared names and behaviours of the country layer, fixed before the agents start, so that each
agent can build its part alone. The plan this follows (Polish, approved 2026-11-02):
`C:/Users/Krzysiek/.claude-prywata/plans/praca-nad-nowym-pomys-em-linear-cake.md`. The report behind
it: `docs/country-precompute.md`. Anything this contract does not settle is a question for the lead,
not a decision of an agent: stop that part and report it.

## What is built

The whole of a country is searched offline in fixed tiles. Each tile keeps only **counts**, never
the lines. The counts are kept in a sparse **counter cube**: for each 1 km cell of the country's
CRS and each combination of filter bins, the lines and the spots. The cube is summed into 2, 4 and
8 km cells, and the local app shows it as a filterable map layer (page `#layer`).

Lines are searched in length **bands**, each on its own grid:

| Band | Lengths (m) | Grid | Model | Anchors (slope) | Tile core | In the layer |
| --- | --- | --- | --- | --- | --- | --- |
| S | [30, 300) | 1 m | formula | 60° | 5000 m | yes |
| M | [300, 1000) | 2 m | sag, T(L) | 60° | 10000 m | yes |
| L | [1000, 5000] | 5 m | sag, T(L) | 45° | 20000 m | yes |
| M2 | [1000, 2000) | 2 m | sag, T(L) | 60° | 10000 m | no: a control band |

- A band is searched with `min_length` = its low end and `max_length` = its high end, because
  `_pairs` accepts `min <= length <= max`. The counter then drops lines that are exactly at the high
  end, except in the band whose high end is the last length edge (5000). So a line of exactly
  1000 m is counted in L only.
- The control band M2 is counted only to compare it with L's part of [1000, 2000) (`country compare`).
- Rig: Silk 99, `webbing_weight` 41.0 g/m and `stretch` 2.1 %; other rigging fields at their
  defaults.
- T(L): the pretension grows with the span, linearly between (300 m, 2.5 kN), (1500 m, 6 kN) and
  (5000 m, 15 kN), clamped at both ends.
- Other options: `water fill`, `coastline copernicus` (never Overpass), `fill_gaps on` (as the app).
  The anchor height difference stays at its defaults.
- **The pilot runs without the DSM** (`nmpt off`; the user's decision of 2026-11-02, as C: has no room
  for the 73 GB of DMP). The trees dimension stays in the cube; for Slovakia every line is "not over
  trees", and the page says the surface model was not used (`dsm: false`).
- Spot: a pair of 50 m anchor clusters with at least one line (below). It is coarser than the app's
  groups and is counted on the fly, without grouping.
- Only lines with both anchors inside the country are counted: anchors come from the area mask.
  Lines across a border are left for a later layer of several countries.

## Ownership

Each agent works only in its own worktree and branch, which the lead has created from
`country-precompute` after this contract was committed:

| Agent | Wave | Worktree (under `C:/Users/Krzysiek/Documents/Prywata/Find-a-Line/.claude/worktrees/`) | Branch | Files it owns |
| --- | --- | --- | --- | --- |
| A | 1 | `country-precompute-a` | `country-precompute-a` | `linesearch.py`, `sag.py`, `search.py`, `tools/perf_country.py`, `tests/test_count_mode.py` (new) |
| B | 1 | `country-precompute-b` | `country-precompute-b` | `countcube.py` (new), `tests/test_countcube.py` (new) |
| C | 1 | `country-precompute-c` | `country-precompute-c` | `viewer/src/**` (the page `#layer` and what it touches; `ui/Gallery.tsx` for its demo), `locales/en.json` (only if it adds `t()` keys), `viewer/dist/**` (rebuilt) |
| D | 2 | `country-precompute-d` | `country-precompute-d` | `country.py` (new), `findaline.py`, `.gitignore`, `.dockerignore`, `tests/test_country.py` (new) |
| E | 2 | `country-precompute-e` | `country-precompute-e` | `web.py`, `tests/test_country_web.py` (new), `tools/ui_shots.py` |

- Nobody else edits these files. Any other file needs the lead first.
- The lead writes the shared documents: `CLAUDE.md`, `README.md`, `docs/**` (this contract too) and
  `docs/roadmap.md`. An agent puts the text it wants there (a code-map row, a README row) into its
  report.
- Not allowed:
  - new coded errors (`messages` codes, `error.*` catalogue texts): the country CLI prints plain
    English and the endpoints answer `HTTPException(400|404, "<plain text>")`;
  - any change of the search without a sink. `find_valid_lines` without `sink`, the numba kernels,
    `_tiles`, `_lines` and the saved files must give exactly what they give now, because the
    regression set compares checksums;
  - any change of stored data outside `countries/`;
  - a new dependency (`pyproject.toml` / `uv.lock`, `viewer/package.json`);
  - in the viewer: `style=` attributes or `<style>` in HTML strings (CSP `style-src 'self'`; use
    classes, the CSSOM or Preact's `style` prop).

## 1. Count mode of the search (agent A)

### `linesearch.py`
```python
SINK_CHUNK = 2048     # anchors per pair_chunk call with a sink: PAIR_BUFFER pairs each fit PAIR_BUFFER_BYTES
SINK_PART = 1 << 20   # at most this many pairs per evaluated part handed to a sink

def find_valid_lines(..., check=None, sink: Optional[Callable[[sh.LineTable], None]] = None
                     ) -> Optional[sh.LineTable]
def covered_pixels(a1: np.ndarray, a2: np.ndarray, mask: Optional[np.ndarray]) -> np.ndarray  # int64
```
- **With `sink`:**
  - Steps 1 and 2 are as now.
  - The todo anchors go through `pair_chunk` in slices of `SINK_CHUNK`, in todo's order.
  - A slice's pairs wait until at least `EVAL_PART` pairs are pending (or the anchors end). Then all
    pending pairs are evaluated (`evaluation_parts(pending, SINK_PART)`, `evaluate_lines`, the same
    arguments as now), and each evaluated `LineTable` goes to `sink` at once. It holds `"a1"`,
    `"a2"` (pixels) and the `LINE_VALUES`.
  - Nothing is joined, sorted or kept, and the function returns `None`.
  - `stats` gets the same keys and counts as without a sink.
  - Without a terminal it shows only the bar `"anchor pairs"` (no new bar names; with postfix
    `valid=`).
  - The summary lines are printed as now.
  - `sink` together with `check` raises `ValueError`.
- **Without `sink`:** unchanged, byte for byte.
- **`covered_pixels`:** for each line, the number of its pixels set in `mask` (anchors excluded),
  i.e. the pixels `helpers.line_profile` and `covered_metres` sample. It is all zeros when `mask` is
  None. It works in parts of `COVERED_PART` lines. `covered_pixels(...) > 0` equals
  `covered_metres(...) > 0` for every resolution of 0.5 m or more. `covered_metres` stays as it is
  (it may call `covered_pixels` only if its results stay identical).

### `sag.py`
```python
def parse_tension(text: str) -> List[Tuple[float, float]]        # "300:2.5,1500:6" -> sorted (span, kN)
def tension_at(points: Sequence[Tuple[float, float]], span: float) -> float  # np.interp, clamped
class TensionTable(EnvelopeTable):
    def __init__(self, rig: Rigging, min_span: float, max_span: float,
                 tension: Sequence[Tuple[float, float]]): ...
```
- `TensionTable` is the envelope table whose sags at each span are solved with the pretension
  `tension_at(tension, span)`. Everything else is as in `EnvelopeTable`: `rig` is kept for
  `fall_zone`, with the same bar "sag estimator table".
- With a single point it equals `EnvelopeTable` for that pretension, bit for bit.
- `tools/perf_country.py` uses these (`parse_tension`, `tension_at` re-exported under their old
  names). Its `tension_table` keeps working and `tests/test_perf_country.py` passes unchanged.

### `search.py`
```python
def plan_search(..., memory=None, tiled: bool = True) -> Plan
def count_tile(plan: Plan, data: Data, core: Optional[tuple], sink: Callable[[sh.LineTable], None],
               sag_table=None) -> Dict[str, int]

@dataclass
class FixedTile:
    name: str                                   # "E<left>_N<bottom>": the core's corner in whole metres of the CRS
    core: Tuple[float, float, float, float]     # left, bottom, right, top
    grid: gd.Grid                               # the core with _overlap around it, clipped to plan.grid

def fixed_tiles(plan: Plan, core_m: float) -> List[FixedTile]
```
- **`plan_search(tiled=False)`:** an area gets no tiles (`tiles=None`, `tile_core=None`, no
  `tile_core_size`); everything else is as now (`grid.area_shape` set).
- **Step 2 moves out of `_lines`** into a helper, with the same messages, errors, funnel counts and
  results. `_lines` and its output must not change.
- **`count_tile`** runs steps 2 and 3 without step 4, with the same anchors, `first` mask (`core`),
  limits and arguments as `_lines`.
  - The model "sag" uses `sag_table` when given, or `sg.EnvelopeTable(plan.rigging, ...)` when None.
    "formula" uses no table.
  - It never raises "no steep terrain", "no prominent anchors" or "no lines": an empty grid simply
    hands nothing to `sink`.
  - There is no `_early_check` and no `_check_lines`. `limits.anchors_max` stays.
  - Each part reaches `sink` with one more column, `"water_px"`: int64, `covered_pixels` of
    `data.water`.
  - Returns `plan.funnel` with this call's counts added (as `_lines` does).
- **`fixed_tiles`:**
  - The cores are squares of `core_m` at whole multiples of `core_m` in `plan.crs` (`math.floor`,
    so negative Krovak coordinates work). Only the cores intersecting `plan.grid.area_shape` are
    kept; a core is never clipped.
  - Each grid is `gd.make_grid` of the core with `_overlap(params, res)` around it, clipped to
    `plan.grid.bounds`, with `plan.source.grid_origin`. Its `area_shape` is the area's.
  - Factor the grid of a tile into one function used by `_tiles` too, without changing `_tiles`'
    results.
  - Order: rows from the north, west to east.
  - The name uses the core's left and bottom as integers, e.g. `E-560000_N-1235000`.

### Tests of A (`tests/test_count_mode.py`; offline, the Żabi Koń clip)
- The sink's parts (concatenated, sorted by anchors) equal the table without a sink, for the
  formula, the sag model and a `TensionTable`. The `stats` are equal too.
- The parts' multiset does not depend on the threads.
- `covered_pixels > 0` equals `covered_metres > 0`.
- `TensionTable` with one point equals `EnvelopeTable`; `parse_tension` and `tension_at` work.
- `fixed_tiles`: on multiples, negative coordinates (a plan in EPSG:8353), names, cover the area.
- `count_tile` over fixed tiles gives exactly the lines of one grid (the same anchors' coordinates
  and values), as `test_area_in_tiles` does (water and gap filling off).
- The existing suite is unchanged: `tests/test_units.py`, `tests/test_offline.py`,
  `tests/test_perf_country.py`.

## 2. The counter cube (agent B): `countcube.py`

Pure numpy, plus `pyproj` and `shapely` where needed, and `cache.replacing` for atomic files. It
never imports numba, `linesearch`, `search` or `country` (the web process imports it). Data on
disk: `<data>/countries/<id>/` (section 3).

```python
VERSION = 1           # tile files and cubes of another version are refused (computed again, no migration)
CELL_M = 1000.0
LEVELS = (1, 2, 4, 8)  # a level's cell: L * CELL_M
ALIGN_M = 8000.0      # a country's origin: its grid's left/bottom floored to a multiple of this
CLUSTER_M = 50.0      # a spot's anchor clusters
LENGTH_EDGES = (30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000)  # 9 bins [e_k, e_k+1); 5000 in the last
EDGES = {             # lower edges of the 3-bit dimensions; below the first: bin 0; the last bin open upwards
    "prominence": (0, 5, 10, 20, 50),   # of the weaker anchor: np.minimum(prom1, prom2)
    "wall": (0, 30, 45, 60, 90),        # of the steeper anchor: np.maximum(angle1, angle2)
    "clearance": (0, 2, 5, 10, 20),     # "clearance" over the terrain
    "height": (0, 10, 20, 50, 100),     # "height_max" of the webbing over the terrain
}
UNKNOWN = 7           # a 3-bit dimension whose value is NaN
```

### Key (int64, 53 bits), from bit 0
| Bits | Field |
| --- | --- |
| 0-1 | water: bit 0 "a line not over water", bit 1 "a line over water" (`water_px > 0`) |
| 2-3 | trees: bit 2 "a line not over trees/buildings", bit 3 "a line over them" (`clearance_nmpt <= 0`; NaN: not over) |
| 4-6 | height bin |
| 7-9 | clearance bin |
| 10-12 | wall bin |
| 13-15 | prominence bin |
| 16-24 | length mask: bit 16+k for length bin k |
| 25-38 | cell row `j` (from the origin's south edge) |
| 39-52 | cell column `i` (from the origin's west edge) |

- `RECORD_BITS = 25`: the low bits, a spot's **record**.
- A line has exactly one bit of each flag pair and one length bit.
- The cell of a line is that of its **first anchor**, as `mapping.first_anchor` takes it (the smaller
  x, then y). Its column is `i = floor((x - X0) / CELL_M)` and its row is `j = floor((y - Y0) / CELL_M)`.
  `(X0, Y0)` is the country's origin.
- A level's cube uses the same layout with `i // L`, `j // L`.

### Spot id and record
- **Clusters:** `cx = floor((x - X0) / CLUSTER_M)` and `cy = floor((y - Y0) / CLUSTER_M)` for both
  anchors.
- **Order:** `p` is the smaller of the two `(cx, cy)` in lexicographic order and `q` the other. Then
  `dx = q.cx - p.cx` (0..101) and `dy = q.cy - p.cy` (-101..101).
- **id:** `p.cx << 35 | p.cy << 16 | dx << 8 | (dy + 128)`.
- **The spot's cell:** `(p.cx // 20, p.cy // 20)`.
- **Merging two records of one id:**
  - length mask, trees and water bits: OR;
  - prominence, clearance and height bins: the largest, with UNKNOWN taken as -1 (UNKNOWN only when
    every line's is);
  - wall bin: the smallest, with UNKNOWN taken as +8.
- A spot passes a filter when its record does. With one filter that is exact ("some line of the
  spot passes"). With several it is an upper bound, because each dimension's best value may come
  from another line; the page says so.

### API
```python
def origin_of(bounds: Tuple[float, float, float, float]) -> Tuple[float, float]  # (left, bottom) floored to ALIGN_M

class TileCounter:
    """The counts of one tile, fed part by part by search.count_tile (a LineTable with "a1", "a2",
    the LINE_VALUES and "water_px")."""
    def __init__(self, grid, origin: Tuple[float, float], core: Optional[Tuple[float, float, float, float]],
                 lengths: Tuple[float, float], last: bool): ...
    def __call__(self, part) -> None: ...
    def result(self) -> "TileCounts": ...

@dataclass
class TileCounts:
    line_keys: np.ndarray     # int64, sorted, unique
    line_counts: np.ndarray   # int64
    spot_ids: np.ndarray      # int64, sorted, unique
    spot_records: np.ndarray  # int64 (RECORD_BITS)
    lines: int                # lines counted
    dropped: int              # lines left out: outside lengths or with the first anchor outside core

def save_tile(path: str, counts: TileCounts, meta: Dict) -> None      # np.savez_compressed via cache.replacing; meta as JSON text
def load_tile(path: str) -> Tuple[TileCounts, Dict]                   # ValueError for another VERSION
def merge_spots(ids: np.ndarray, records: np.ndarray) -> Tuple[np.ndarray, np.ndarray]  # sorted unique ids, merged records
def build(tiles: Iterable[str], out_dir: str, info: Dict) -> Dict     # the cube (below); returns cube.json's content

@dataclass(frozen=True)
class Filters:
    length: Tuple[float, float] = (30, 5000)  # metres, both edges of LENGTH_EDGES
    prominence: float = 0      # >= (0: no filter, UNKNOWN passes only then)
    wall: Optional[float] = None  # < (None: no filter, UNKNOWN passes only then)
    clearance: float = 0       # >=
    height: float = 0          # >=
    trees: str = "all"         # all | no (some line not over trees) | only (some line over them)
    water: str = "all"         # all | land (some line not over water) | water (some line over water)
    @classmethod
    def parse(cls, query: Mapping[str, str]) -> "Filters": ...  # ValueError (a plain message) for a value off the edges

def select(keys: np.ndarray, filters: Filters) -> np.ndarray   # a boolean mask of the keys passing

class Cube:
    def __init__(self, folder: str): ...   # cube.json; each .npy read into memory when first used (not mapped:
                                           # Windows would refuse the next build's replacing a mapped file)
    info: Dict                             # cube.json
    def box(self, west: float, south: float, east: float, north: float) -> Tuple[float, float, float, float]  # WGS84 → CRS (densified)
    def auto_level(self, box: Tuple[float, float, float, float], most: int = 4000) -> int  # the finest level with at most `most` cells over box
    def cells(self, mode: str, level: int, box: Optional[Tuple[float, float, float, float]], filters: Filters
              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]   # i, j, count of the cells with count > 0
    def corners(self, level: int, i: np.ndarray, j: np.ndarray) -> np.ndarray  # (n, 4, 2) [lat, lon]: SW, SE, NE, NW

def cell_request(cube: Cube, band: str, level: int, i: int, j: int) -> Dict   # a SearchRequest: {"params", "geometry"}
```
- **`TileCounter`** first drops lines whose first anchor lies outside `core` (left <= x < right,
  bottom <= y < top, as `search.line_coordinates`) and lines outside `lengths` (`lo <= length < hi`,
  or `<= hi` when `last`). It takes x and y from `grid.pixel_to_xy`.
  - Lines: their keys are reduced as they come.
  - Spots: reduced per id as they come. Reduce again when the pending arrays grow (more than about
    4 M entries), so a tile of 10^8 lines stays within a few hundred MB.
- **`build`:**
  - Merges every given tile file: the layer bands only, which the caller picks.
  - Lines: keys summed. Spots: merged per id over **all** tiles and bands (a spot whose lines lie in
    two tiles or two bands is counted once), then counted per key.
  - Then the levels 2, 4, 8, summed from level 1.
  - Writes `out_dir/lines_<L>.npy` and `spots_<L>.npy`: (n, 2) int64 `[key, count]`, sorted by key.
  - Writes `cube.json` last, with `info` plus `version`, `edges`, `levels`, `cell_m`, `cluster_m`,
    `totals` (`lines`, `spots`, the keys of each file) and `built` (UTC ISO).
- **`Cube.cells`:** the keys of the cells inside `box` (the CRS rectangle), passing `filters`,
  summed per cell. Columns with `i` in range are one contiguous range of the sorted keys.
- **`cell_request`:**
  - Geometry: the level's square, buffered by the band's `max_length` and intersected with the
    country's outline (`area.geojson` in the cube folder), in WGS84, as a GeoJSON Polygon or
    MultiPolygon.
  - Params: the band's `params` from cube.json.
  - A `ValueError` for a band not in the layer, or a cell outside the country.

### cube.json (the `info` that `country build` gives, and what `build` adds)
```json
{"version": 1, "id": "slovakia", "name": "Slovakia", "crs": "EPSG:8353", "origin": [-600000.0, -1336000.0],
 "cell_m": 1000, "levels": [1, 2, 4, 8], "cluster_m": 50, "bounds_wgs84": [16.83, 47.73, 22.57, 49.61],
 "edges": {"length": [30, 60, ...], "prominence": [0, 5, 10, 20, 50], "wall": [...], "clearance": [...], "height": [...]},
 "bands": [{"name": "S", "lengths": [30, 300], "resolution": 1.0, "model": "formula", "slope_threshold": 60,
            "core_m": 5000, "layer": true, "tiles": 0, "done": 0, "seconds": 0.0,
            "params": {"source": "slovakia", "min_length": 30, "max_length": 300, "resolution": 1.0,
                       "model": "formula", "slope_threshold": 60, "nmpt": "off", "water": "fill",
                       "coastline": "copernicus", "fill_gaps": "on", "pretension": 2.5, "stretch": 2.1,
                       "webbing_weight": 41.0}}],
 "dsm": false, "water": true, "partial": false, "study": false, "config": "<sha256 of the country's config>",
 "totals": {"lines": 0, "spots": 0, "keys": {"lines_1": 0, "spots_1": 0}}, "built": "2026-11-03T10:00:00Z",
 "credits": [{"...": "as run.json's credits, years filled"}], "notes": ["..."]}
```
- `params` are `SearchParams` fields that prefill the app's form for a search of one cell. For a sag
  band, `pretension` is T at the band's `max_length`: the most tension and the least sag, so the
  search finds a superset of the lines T(L) gives.
- The cube folder also holds `area.geojson`: the outline, WGS84.
- `study`: a study area (`Country.study`). The page shows it alone, never added to a country. Cubes
  built before 2026-11-05 have no such field and none of them is one, so they need no migration.

### Tests of B (`tests/test_countcube.py`)
- Keys pack and unpack back.
- Bins at, below and above the edges, and NaN to UNKNOWN.
- `TileCounter` against a brute-force count of random lines (rows):
  - lines per key;
  - spots: a dict per id;
  - the core and length filters.
- `merge_spots` is commutative.
- Two tiles sharing a spot: the spot is counted once in `build`.
- Levels: a level's counts are the sums over level 1.
- `select` and `Cube.cells` against brute force with random filters.
- `corners` with pyproj.
- `cell_request`: the buffer intersected with the outline.
- Importing `countcube` in a fresh interpreter loads no `numba`, `linesearch` or `search`.

## 3. The country driver (agent D, wave 2): `country.py`

```
findaline.py country run <id> [--data-dir D] [--processes K] [--bands S,M,L,M2] [--max-tiles N] [--redo] [--yes]
findaline.py country status <id> [--data-dir D]
findaline.py country build <id> [--data-dir D] [--partial]
findaline.py country compare <id> [--data-dir D] [--control M2] [--against L]
findaline.py country worker <id> --slot K [--data-dir D]      # started by run, one per process
```
- `findaline.py` dispatches the first argument `country` to `country.main(sys.argv[2:]) -> int`, as
  it does for `web`.
- `COUNTRIES = {"slovakia": Country(...)}`. `Country` and `Band` are frozen dataclasses with the
  fields of the table above:
  - `Country`: `id`, `name`, `source`, `area` (`"osm:Slovensko"`), `bands`, `tension`, `rig`
    (webbing fields), `options` (`nmpt`, `water`, `coastline`, `fill_gaps`, and for tests
    `elevation_file`);
  - `Band`: `name`, `lengths`, `resolution`, `model`, `slope_threshold`, `core_m`, `layer`.
- **`country.json`** holds the config as JSON and its sha256.
  - `run` writes it the first time from `COUNTRIES` and checks it afterwards. A different config is
    refused unless `--redo`, which deletes `tiles/`, `cube/` and the manifest.
  - Workers and the other commands read only `country.json`. Tests write a `country.json` of their
    own country, whose id is not in `COUNTRIES`.
- **The outline** comes once from `area.from_spec(country.area, ..., whole=True)` and is saved as
  `area.geojson`. Every band's `plan_search` then uses that file (`area=<path>`), so a resumed run
  gets the same tiles. The config hash covers the file's sha256.
  - It is never simplified: `osm.search(whole=True)` keeps an outline above `MAX_ANSWER_BYTES` as it
    came, on a row of its own. Two neighbours simplified apart would no longer share their border.
  - Countries are a partition (`_partition`, 2026-11-05): a point of the map is one country's, the
    first to hold it. A new outline loses what the countries set up before it hold, and the file's
    `properties.less` names them. Outlines of one OSM share their borders exactly (Slovakia and its
    five neighbours: no overlap), so this cuts only an outline of another date or a hand-made one.
    Gaps between outlines stay. It happens only when `area.geojson` is written, so a country set up
    earlier keeps its outline.
  - A study area (`Country.study`: the option `within`, a box of a country, `tools/band_study.py`)
    lies in its country by design: it is neither cut nor cuts another.
  - `run` names the other areas an outline overlaps by `OVERLAP_KM2` (0.01 km²) or more
    (`_say_overlaps`): a plain line for a study area, a warning for two countries.
- **Manifest** `manifest.sqlite` (WAL, `cache.migrate`, `MIGRATIONS` of schema v1):
  - table `tiles`: `band`, `name`, `core` (JSON), `status`
    (`pending`/`running`/`done`/`failed`), `attempts`, `worker`, `started_at`, `finished_at`,
    `seconds`, `lines`, `spots`, `error`; primary key `(band, name)`.
  - Claims use `BEGIN IMMEDIATE`. A failed tile goes back to `pending` once, then stays `failed`.
- **`run`:**
  1. Takes `run.lock` (filelock, not blocking; another run is refused).
  2. Creates the config, the outline and each band's plan (`plan_search(tiled=False)`), and its
     `fixed_tiles` into the manifest (`INSERT OR IGNORE`).
  3. Sets the `running` rows back to `pending`: stale ones, since the lock is held.
  4. Checks the free disk.
  5. Prefetches the data over the country (`src.download_layers` of the terrain, the surface when
     used and the water mask, on a grid of the outline with the largest overlap).
  6. Warms numba: a tiny count of each model, so the kernels are compiled once before the workers
     start.
  7. Starts K `country worker` processes. K comes from the memory
     (`search.memory_needed(<largest tile's px>, 0)` plus a margin) and is at most the physical
     cores. `--processes 0` runs the tiles in this process (tests).
  8. Prints a progress line every 30 s: tiles done/total per band, lines, the time left.
  9. On Ctrl+C: `jobs.kill_tree` of each worker (started in a new process group on Windows), their
     tiles back to `pending`, exit 130.
  10. Builds the cube when every layer band is done.
- **`worker`:** claims tiles until none is left. For each tile:
  - its plan is `dataclasses.replace(band_plan, grid=tile.grid, paths=Paths(data,
    work/country-<id>/<band>-<name>), tiles=None, funnel={})`, with `params.threads` from the logical
    cores and the workers still busy;
  - `search.prepare_data`, then `search.count_tile` with a `countcube.TileCounter` and the band's
    `sag.TensionTable` (made once per band per process);
  - `countcube.save_tile` to `tiles/<band>/<name>.npz`, with meta: `version`, `config`, `band`,
    `tile`, `core`, grid size, `lines`, `spots`, `dropped`, `funnel`, seconds of prepare and count,
    threads, commit, `data` (`sources.used_data` of the tile), times;
  - then the manifest row is set done, the work folder removed and `sources.used_data` cleared.
- **`status`:** per band, the tiles by status, lines and spots so far, seconds (sum and median), and
  errors.
- **`build`:**
  - `countcube.build` over the layer bands' tiles. It refuses while tiles are missing unless
    `--partial` (cube.json `partial: true`).
  - `info` (cube.json) gets: `bands` with their counts of tiles and seconds, and their `params`
    (section 2); `dsm`; `credits` (the tiles' `data` merged as `search._merged_data` does and
    deduplicated as `search._credits` does, years filled with the build's year, plus OSM for the
    outline); `notes`.
- **`compare`:**
  - Compares the control band against its part of the other band (lengths [1000, 2000)), per cell of
    1 and 4 km: lines and spots and their ratio, the Spearman correlation of spots per cell (cells
    with any line of either, zeros included), and the share of the control's cells with a spot where
    the other has none ("lost"). It also gives the seconds of both bands' tiles.
  - Prints a table and writes `compare.json`.
- **Data layout** (new; no migration of anything older; manifest schema v1 with `cache.migrate`):
```
<data>/countries/<id>/  country.json, area.geojson, manifest.sqlite, run.lock, logs/run.log, logs/worker-<k>.log,
                        tiles/<band>/<name>.npz, cube/{lines,spots}_<L>.npy, cube/area.geojson, cube/cube.json, compare.json
<data>/work/country-<id>/<band>-<name>/    a tile's grids, removed after the tile
```
- `/countries/` goes into `.gitignore` (the data folder defaults to the repository). In
  `.dockerignore`, only if its allowlist would not leave it out already.
- **Tests of D** (`tests/test_country.py`, offline):
  - A country of the Żabi Koń clip reprojected to EPSG:8353 (negative coordinates), with
    `elevation_file`, `water off`, `fill_gaps off`, `nmpt off`.
  - Bands S (30-150 m, 1 m, formula, 45°, core 200 m) and M (150-300 m, 2 m, sag with T(L), core
    400 m), at least 2 × 2 tiles.
  - The cube from the tiles equals the counts of one grid (`count_tile` with `core=None` and a
    `TileCounter`).
  - Resuming (`--max-tiles 1`, then the rest) gives the same cube, and so does `--processes 2`.
  - A tile failing once is retried; failing twice it is `failed`, and `status` shows it.
  - `build` refuses a partial cube without `--partial`.

## 4. The web endpoints (agent E, wave 2): `web.py`

Every endpoint depends on `require_admin` (locally the user is `LOCAL`, an administrator). The cube
of a request is cached per process (`Cube` keyed by the folder and the mtime of cube.json). The
work runs in `run_in_threadpool`. The web process imports `countcube` only, never `country`,
`search` or numba.

```
GET /api/countries
  → {"countries": [<cube.json without "config" and "origin">, ...]}   (the cubes under <data>/countries/*/cube/)
GET /api/countries/{id}/cells?mode=lines|spots&bbox=<west>,<south>,<east>,<north>&level=auto|1|2|4|8
                             &length=<lo>-<hi>&prominence=<p>&wall=<w>&clearance=<c>&height=<h>&trees=all|no|only&water=all|land|water
  → {"level": 2, "cell_m": 2000, "total": 12345, "max": 678, "cells": [[i, j, count, lat_sw, lon_sw, lat_se, lon_se,
     lat_ne, lon_ne, lat_nw, lon_nw], ...],          (coordinates rounded to 6 decimals; only cells with count > 0)
     "cut": {"<i>,<j>": {"km2": 0.62, "shape": [[[[lat, lon], ...], ...], ...]}, ...}}   (those the outline cuts: Cube.cut)
GET /api/countries/{id}/request?band=S|M|L&level=<L>&i=<i>&j=<j>
  → {"params": {...}, "geometry": {GeoJSON}}       (a SearchRequest for the app's form)
```
- **`bbox`** is Leaflet's `map.getBounds().toBBoxString()`.
- **Defaults:** `mode=lines`, `level=auto`, no filters (`wall` absent).
- **`level=auto`** is `Cube.auto_level` of the view (at most 4000 cells by geometry).
- **Errors:**
  - an explicit level whose view holds more than 20000 cells answers 400 ("too many cells: zoom in
    or choose a coarser level");
  - a value off the bins' edges, an unknown mode, level or band, or a bad bbox answers 400 with
    `Filters.parse`'s plain message;
  - an unknown country answers 404.
- **Tests of E** (`tests/test_country_web.py`):
  - TestClient on a small cube made with `countcube` from synthetic `TileCounts`.
  - Each endpoint and its errors, and the access rule (`test_every_route_has_its_access_rule`
    passes).
  - Locally, and as a non-admin on the public site: 403.
  - No numba in the web process.
  - The page `#layer` in headless Edge on the real server (stubbed `EventSource`, as `tests/test_web.py`
    does): the cells drawn and no CSP violations.
  - `tools/ui_shots.py` gets the pages `c-layer` and `d-layer`, with a sample cube in its scratch
    data folder.

## 5. The page `#layer` (agent C)

Routes of `viewer/src/app/c/route.ts`:
- `{page: "layer"; country: string | null}` from `#layer` or `#layer&country=<id>`;
- `{page: "new"; edit: string | null; cell: string | null}` with `#new&cell=<id>:<band>:<level>:<i>:<j>`.

The new search fetches `api.countryRequest(id, band, level, i, j)` and uses it as `initial`, as
"Edit & run again" does with a job's request. Its title is "Search a cell".

`viewer/src/app/api.ts` gets these (types of section 4):
```ts
export interface CountryBand { name: string; lengths: [number, number]; resolution: number; model: string;
                               slope_threshold: number; core_m: number; layer: boolean; tiles: number; done: number;
                               seconds: number; params: Record<string, unknown> }
export interface CountryCube { id: string; name: string; crs: string; cell_m: number; levels: number[];
                               cluster_m: number; bounds_wgs84: [number, number, number, number];
                               edges: Record<"length" | "prominence" | "wall" | "clearance" | "height", number[]>;
                               bands: CountryBand[]; dsm: boolean; water: boolean; partial: boolean;
                               totals: {lines: number; spots: number}; built: string;
                               credits: Credit[]; notes: string[] }   // Credit of viewer/src/types.ts (run.json's "attribution"),
                                                                        // shown with layers.ts creditsHtml
export interface CountryCells { level: number; cell_m: number; total: number; max: number; cells: number[][] }
api.countries(): Promise<{countries: CountryCube[]}>
api.countryCells(id, query: Record<string, string>, signal?): Promise<CountryCells>
api.countryRequest(id, band, level, i, j): Promise<SearchRequest>
```

**The page** is a `MapPage` (`app/c/Account.tsx`): the panel on the left, the map on the right; on
phones the map is on top. It is reached from the account menu ("Highline layer") for the local user
and administrators, in the shells C and D.

The panel has:
- the country, when there are several, and the built date, with "partial: k of n tiles" when partial;
- mode, Lines or Spots;
- the length range: two choices from `edges.length`;
- thresholds on the bins' edges:
  - prominence of the weaker anchor ≥;
  - wall angle of the steeper anchor <, or any;
  - clearance ≥;
  - webbing height ≥;
- over trees and buildings: any, not over, only over. It is disabled with a note when `dsm` is false;
- over water: any, land, water.

Under the filters:
- a legend: a sequential, single-hue scale of the density per km² (the count divided by the
  cell's km²), in log classes that stay fixed while panning, one set for lines and one for spots.
  Load the `dataviz` skill and validate the colours with its script, in light and dark;
- the total in view, the level and cell size, with a choice of level (auto, 1, 2, 4, 8 km);
- the selected cell: its count and coordinates, and one "Search here" button per layer band
  (`#new&cell=…`);
- notes:
  - spots are pairs of 50 m anchor clusters, not the app's groups;
  - with several filters, spots are an upper bound;
  - both anchors lie inside the country;
  - each band has its own grid (S 1 m, M 2 m, L 5 m);
  - "no surface model" when `dsm` is false;
- the data credits (the cube's `credits`).

The cells are polygons on a canvas renderer that is safe on removal (as `SafeCanvas` in
`result/ResultMap.ts`), filled from the classes, with the selected cell outlined. The cells are
fetched again 300 ms after a pan, zoom or filter change, the previous request aborted (as
`useEstimate`). On a 400 "too many cells", the page asks to zoom in.

There is also a demo `?ui=kit-layer` in `ui/Gallery.tsx` with canned data (no server), for reviews
and Edge.

Checks of C:
- `npm run check` (or `node node_modules/typescript/bin/tsc --noEmit`), then `node build.mjs`;
  `viewer/dist` is committed.
- `tests/test_viewer.py` passes (the bundle is built from the sources).
- A look in headless Edge, from PowerShell, at the demo on a desktop window and a narrow one, light
  and dark, with no CSP violations. Show the screenshots in the report.

### The page as built: the Highline Explorer (2026-11-04, branch `layer-explorer`)

The prototype above was replaced by a browsing page of every country's cube at once (the plan of
2026-11-04; mock-ups on claude.ai). `#layer` keeps its access rule (the local user and
administrators) and its place in the account menu of C and D.

**Layout.** `MapPage` with a right `aside` (`.c-mappage-3`: `400px minmax(0,1fr) 320px`): the
filters, the legend, the total in view, the level, the selected cell, the notes and the credits on
the left (`LayerPage.tsx`); the map in the middle (`cellsLayer.ts`); the histograms on the right
(`LayerHistograms.tsx`, a second Preact tree rendered into the aside: never a portal of
`preact/compat`). On phones the map (34vh) on top, then the panel, then the histograms, in one
scrolling column.

**The hash** (`layerState.ts`, `parseState`/`stateParams`; `route.ts` `layerHash`):
```
#layer[&country=<id>][&view=<lat>,<lon>,<zoom>][&mode=lines|spots][&length=<lo>-<hi>][&prominence=<p>][&wall=<w>]
      [&clearance=<c>][&height=<h>][&trees=all|no|only][&water=all|land|water][&level=auto|1|2|4|8][&scale=fit|fixed]
```
- What is absent is the default (lines, the full length range, no thresholds, auto, fit); an invalid
  value falls back to it, checked against the first cube's edges.
- `view` wins over `country`; without either the page fits the first cube's bounds.
- The page writes the hash in place (never a history entry) on every change and `moveend`.
  `hashchange` from outside (Back, a pasted link) applies it. `ShellC` treats a change within
  `#layer` as no navigation, and `AppC` keys the page by a constant, never by the hash.

**Two more endpoints** beside section 4's, with the same query, errors, `require_admin` and thread
pool (`web.Countries._view`):
```
GET /api/countries/{id}/histogram?<the query of /cells>
  → {"level", "cell_m", "total", "length": [9 ints], "prominence": [6], "wall": [6], "clearance": [6], "height": [6]}
GET /api/countries/{id}/outline
  → {"tolerance": 0.005, "area_km2": <the outline's km² in the cube's CRS>, "geometry": <GeoJSON, 4 decimals>}
```
- The histogram is `countcube.Cube.histogram`: each dimension is counted under every filter but its
  own (`select(skip=)`), so the bars show what a threshold cuts.
- With a bbox, the histogram counts only the cells reaching the view (`Cube.reaching`). Those are
  the cells whose corners, rounded as `/cells` rounds them, have a box intersecting the bbox, edges
  included, as Leaflet's `LatLngBounds.intersects`. So its total is the page's total in view.
  - Without this, the view's box in the cube's CRS holds more cells where the CRS turns against the
    meridians: 13 % more lines than the cells in view on Slovakia's real cube over the Tatras
    (809 M against 913 M, 2026-11-04). The 3-bit dimensions give the bins
  0-4, then UNKNOWN (the page draws it as "?", not pickable).
- A line has one length bit, so in lines mode the length bins partition the total. A spot's record
  ORs the length bits of its lines, so in spots mode the per-bin counts are upper bounds and may sum
  above `total`; the page says so under the length histogram and beside the total.
- The outline is `Cube.outline_simplified(OUTLINE_TOLERANCE)`: Slovakia's `area.geojson` is 2.08 MB,
  10 KB simplified. It is no field of the listing.
- In `api.ts` these are `CountryHistogram`, `CountryOutline`, `api.countryHistogram` and
  `api.countryOutline`. The page reads them through a `LayerSource` (`countries`, `cells`,
  `histogram`, `outline`): the server, or the canned data of `?ui=kit-layer` (`ui/Gallery.tsx`
  `KIT_CUBES`, `kitCells`, `kitHistogram`, `kitOutline`).

**A round** runs 300 ms after the last move or change. It aborts the round before (one
`AbortController`) and asks every active cube whose `bounds_wgs84` reach the view. All rows are drawn, each
remembering its cube for the card and `#new&cell=`. The histograms are summed, and the credits of
the cubes in view are deduplicated.

**The level** is chosen by the client for all cubes in view (`autoLevel`) and sent explicitly; the
server's `auto_level` stays for the API.
- First view: the finest level with at most 4000 cells (the view clipped to the cubes' bounds,
  `cellsAt`).
- Afterwards, with hysteresis: finer only when the finer level stays under 900 cells, coarser only
  above 2400.
- Then coarser while one cube's request would exceed `REQUEST_CELLS_MAX` (16000), the server's
  20000 with a margin (`largestRequest`, `requestCells`). Those count the box clipped to the cube's
  bounds grown by a degree, as `Cube.box` does.
- An explicit level is sent as it is; a 400 "too many cells" shows the too-many state.

**The colour scale** is `scale=fixed` (`CLASS_BREAKS`, a colour means the same everywhere) or
`scale=fit` (the default):
- Fit takes four breaks evenly in log10 between the 2nd and 98th percentile of the densities per km²
  of the cells of a **padded box** (`quantileBreaks`). The padded box is the view plus one view's
  width and height on every side, less where a request would exceed 16000 cells (¾, ½, ¼, none).
- When the view left the cached box (or the level, a filter or the mode changed), the round asks the
  cells of the padded box. They are drawn too and cached with their box, level and filters.
- A pan or zoom that stays inside the box at the same level sends no `/cells` request and keeps the
  breaks; only the histograms of the view are asked again.
- Leaving the box refits. At a refit, the breaks shown ease from the old ones to the new over 0.5 s
  in log10 (cubic in-out; none under `prefers-reduced-motion`; a timer ends it where no frames come),
  the cells and the legend redrawn each frame.
- The cells stay sharp squares (no blur, no heat map, no hexagons: roadmap, "Country layer").
- The total in view (`.c-layer-total`) is the sum of the drawn cells that reach the view. It equals
  the histograms' total, which are always those of the view's bbox.

**Outline mode** applies below an 8 km cell of 4 px, more than `OUTLINE_MPP` (2000) metres per pixel
at the view's centre.
- The round asks each cube in view for its histogram over the whole country (no bbox, level 8) and
  its outline (cached per id).
- The outlines are polygons on the same canvas, filled by the class of `total / area_km2` under the
  fixed breaks, each with a permanent label of its total; a click zooms to the country.
- The panel says "k countries in view" with the summed total.

**Cells on a border** (2026-11-05). A cell the country's outline cuts is drawn over its part inside
the country, and its density is the count over that part's km² (`cut` of `/cells`, `cellsLayer.ts`
`cellKm2`, `cellShape`): the anchors of a country lie inside its outline, so a full km² would
understate it. The cells of two countries meet at their border, and a click beside the country
picks nothing.
- `Cube.cut` works out all levels at the first request, a quadtree from a cell holding the whole
  outline: a cell's piece is cut out of its parent's, and a branch ends at a cell wholly inside or
  outside. It keeps them. Nothing is added to the cube: old cubes get it, no recount.
- Measured on Slovakia's cube (43 k points): 0.3 s for 1860, 894, 418 and 205 cut cells at 1, 2, 4
  and 8 km. Cells with lines: 88 at 1 km, with 4.8 % of the lines, a median of 65 % inside; 43 at
  8 km, with 40 % of the lines, 78 % inside. The density of those at 1 km rises by a median factor
  of 1.5.
- The km² come from the exact outline, the shape drawn is simplified by the cell's side over
  `CUT_SIMPLIFY` (250: 4 m at 1 km, a median of 11 points a cell, about 300 B of an answer).
- No floor under the km²: the smallest parts with lines hold about 1 % of a cell and their densities
  stay within those of whole cells (1 km: at most 41.6 M per km² against 32.1 M).

**Study areas** (2026-11-05). A cube with `study` is a part of a country, so adding it to that
country would count its lines twice (measured on a copy of the real cube: 1491 M lines in a view of
the Tatras instead of 746 M). `layerState.ts` `activeCubes` gives the cubes a round asks: every
country, or a study area alone when it is the one chosen in the select (`#layer&country=<id>`,
"<name> (study area)"), which then says what it is. `countriesFirst` puts the countries first, so
the page opens on a country whatever the ids sort like.

**The notes** under the cell card are the page's own: spots are cluster pairs, spots are an upper
bound under several filters, and a cell on a border counts over its part inside the country. Then
each cube's bands and its `notes`: `country build` writes "Only lines with both anchors inside
<name> are counted." and, without the surface model, its note, so the page repeats neither.

**The right panel** shows:
- the total in view;
- the 9 length bins: a click sets the bin, shift-click extends the range to it;
- four small histograms (prominence, wall, clearance, height). A click sets the threshold: the bin's
  lower edge, or for the wall the bin's upper edge, the last bin "any".

Each bar is a button with `aria-pressed` and `data-value`, of class `.c-layer-hist`. Its height is
log10(1 + n) over log10(1 + max), set through the CSSOM.

**Tests:** `tests/test_country_web.py`:
- the endpoints against `Cube` over two sample cubes (`slovakia`, and `testland` west of it);
- `test_layer_page_in_edge` (shell C; B and D were removed on 2026-11-04): the cells, a picked cell, a
  cell the outline cuts clicked inside and outside the country, the five histograms against the
  intercepted `/histogram` answers, a length bar into the hash and the next `/cells` query, both
  cubes at 2 km adding up, the outlines when zoomed out;
- `test_cells_cut_by_the_outline` (`cut` against `Cube.cut`, which `tests/test_countcube.py::test_cut_cells`
  compares with each cell cut alone) and `test_study_area_in_edge` (a country and a study area
  inside it: only the one in force is asked).

`tools/ui_shots.py` has `c-layer`, `c-layer-world` (both cubes), `c-layer-study` (the study area alone),
`c-layer-end` (the phones' column scrolled to the histograms) and `c-layer-cell` (a cell selected).

## 6. Cube v2: the parameters, the borders, the global lattice, the profile (contract of 2026-11-05)

The user's decisions of 2026-11-05 after the border analysis (`tools/border_study.py`, docs/roadmap.md
"Lines across a border"): lines across a border are counted on both sides (R3), every cube's cells lie
on one global lattice (R4), the countries share one layer profile (R7), and a common computing CRS of
a region is rejected (R6: resampling every pixel; the measured difference of 2-11 % of the spots and
the half-pixel pitfall). These, and the eight new parameters of docs/country-precompute.md section
6.3, change the key and the origin of the cube, so they go into **one `countcube.VERSION` and one
recount**, after the band study has landed in `main` (its bands become the profile). This section is
the contract of that work; nothing of it is coded yet. The waves start from the `main` that holds the
band study, in their own worktrees, as section "Ownership" says.

### Step 0, before the code of R3: the resampling of the partner's data, measured (2026-11-05)

A line across a border is tested on the owner's grid with the neighbour's pixels reprojected onto it
(`sources.mosaic._place`: the average where the data are finer than 0.75 of the grid's resolution,
bilinear otherwise; a correction of this section's first version, which named bilinear alone). The
two grids disagree: in the Tatras the SK grid found 1 561 cross-border spots of the M band, the PL
grid 1 310; 97.9 % of the PL grid's have a match on the SK grid, 89.2 % the other way.

**Built** (tag `history/partner-resampling`): `sources.mosaic.build_mosaic(resampling=)` and
`prepare_layer(resampling=)` with `RESAMPLINGS` (nearest, bilinear, cubic, average; None is the own
choice, the default, unchanged), `sources.filling.NEIGHBOUR_RESAMPLING` for the neighbours' rasters
only, `tools/border_study.py run --resampling` and its report's comparison (`resampling_rows`: each
run against the run on the other source's grid, the lines and spots with both anchors on that
reference's side). **Measured** at the Tatras (PL-SK), the Wetterstein (DE-AT), the Elbe
Sandstone (DE-CZ) and, for a neighbour coarser than the grid, the Zillertal ridge (AT-IT), the S and
M bands; every table, the conditions and the costs are in
docs/performance.md, "The resampling of a neighbour's data". In short, for the neighbour's side
against its own grid:

| Case | bilinear | cubic | nearest | average |
| --- | ---: | ---: | ---: | ---: |
| S band (1 m on 1 m; own choice bilinear), four directions: lines | 58-112 % | 74-119 % | 96-123 % | 73-112 % (two) |
| ... the reference's spots the run has | 88.8-97.2 % | 94.1-98.9 % | 98.3-99.5 % | 93.7-97.2 % (two) |
| ... the run's spots the reference has | 90.5-100.0 % | 90.9-99.9 % | 90.6-99.8 % | 90.5-98.0 % (two) |
| M band (1 m on 2 m; own choice the average), three places: spots | 90-97 % | 98-104 % | 110 % | 94-101 % |
| ... the reference's spots the run has | 98.6-99.6 % | 99.3-99.8 % | 99.7-99.9 % | 99.2-99.7 % |
| ... the run's spots the reference has | 99.8-99.9 % | 99.5-99.8 % | 98.4-99.5 % | 99.7-99.9 % |

(The values above 100 % and the 90.5 % are the Wetterstein on Bavaria's grid, where 6 % of the
Austrian side lies on Bavaria's own data, which find more than Austria's.) The lines across the
border hardly depend on the method (M: under 1 % of the lines, 0.5 points of the spots' shares;
S: the same but for one line in three of four directions, since the owner's data reach beyond the
border farther than the band's longest line): the 2-11 % between the two grids is their data and the side an
anchor on the ridge falls to, not the reprojection. No method costs CPU or memory beyond the noise.

**Decided by the user (2026-11-05) and built** (tag `history/partner-resampling`):
- finer data (M, L against a 1 m neighbour): the average stays;
- the grid's own resolution (`mosaic.FINER` 0.75 to `mosaic.SAME` 1.1 of it; S against a 1 m
  neighbour): **nearest** instead of bilinear, `filling.NEIGHBOUR_SAME_RESOLUTION`, for a
  neighbour's rasters only (`build_mosaic(same_resolution=)`). It holds for every search at a
  border, not for the layer alone: the regression tests whose neighbour lies at the grid's
  resolution were re-baselined with it (docs/regression-tests.md). A run saved before keeps its
  lines; a profile computed again for one of its lines over the neighbour's pixels
  (`search.profile_of_line`) reads the new reprojection (no migration: the difference is that of
  the two methods at a cliff's edge);
- a neighbour coarser than the grid: bilinear stays. Measured on the user's order at the Zillertal
  ridge (South Tyrol's 2.5 m data on Austria's grid): nearest turns every step between two coarse
  pixels into a wall (on the 1 m grid 73 867 lines where South Tyrol's own grid finds 28; on the 2 m
  grid, at 1.25 of its resolution, 1.7 times the lines and 2.5 times the spots), bilinear follows
  the reference (99.7 % of its spots found, 98.6 % of the run's present in it). Hence `SAME` 1.1:
  between the measured 1.0 (nearest right) and 1.25 (nearest wrong);
- native anchors for the partner's side: not needed (98.3-99.7 % of the reference's spots found).

**Found on the way** (the user's word on each, 2026-11-05):
- *The owner's pixels beyond the outline are partners too* (accepted: "The borders" below says
  so now). The first version let a partner anchor stand only on pixels the neighbour's source
  filled. The S lines across the border in the Tatras (637) and on Bavaria's grid in the
  Wetterstein (9 682) are the same under every method, so no reprojected pixel decides them: their
  far anchors stand on the owner's own data, which reach beyond the border (14.4 % of the Polish
  side of the Tatras box is Slovak data), and that rule would have dropped them all.
- *A neighbour's rough boxes must reach the border* (done 2026-11-06: `Source.border_boxes`, see
  the end of this point). `neighbour_window` asked a neighbour only inside its `offline`/`bbox` boxes.
  `tools/border_study.py boxes` lists, for every declared pair, the share of the neighbour's land
  within 5 km of the border that lies inside them (the coverage map's outlines; 108 of the 112
  declared directions, `alaska_ifsar` has no outline). 91 directions reach 97 % or more; the
  others: Scotland for England 1 %, Rhineland-Palatinate for Luxembourg 3 %, Czechia for Slovakia
  20 %, for Saxony 22 %, for Poland 31 %, for Bavaria 35 %, for Austria 42 % (its boxes are kept
  inside the country: Saxony's grid got the 30 m fallback at Hřensko, 93.7 % of the Czech side),
  Denmark for Schleswig-Holstein 31 % and back 60 %, the USA for British Columbia 39 % and for
  Canada 72 %, Norway for Finland 68 %, Saarland for Luxembourg 70 %, Slovenia for Austria 77 %,
  British Columbia for the USA 89 %, Rhineland-Palatinate for Saarland 90 %, Nunavut for Canada
  93 %. Built on 2026-11-06, ahead of wave B, since it holds for every search: the `offline` boxes
  cannot be widened (they decide `--source auto` offline and keep off a neighbour's land on
  purpose), so a source has a second set, `Source.border_boxes`, read by `neighbour_window` only
  (`Source.rough_boxes`): Czechia (13 strips around the country), Scotland, Rhineland-Palatinate,
  Saarland, Schleswig-Holstein, Denmark, Norway, Slovenia, British Columbia and Nunavut. Two of the
  17 were the measure's own: the USA's outline held Alaska, whose border is the source `alaska`'s
  (the tool now takes a country's outline less the regions other sources cover). Every declared
  direction is at 98 % or more, and a test keeps them at 97 %. At Hřensko the Saxon grid's Czech
  side (1.93 km² of a 900 m circle) now comes from ČÚZK's 2 m model: 100 570 anchors at 1 m where
  the fallback gave 76 343, 25 055 against 18 065 at 2 m; the lines stay (1 314 at 1 m, 6 122
  against 6 121 at 2 m), so there the gain is the heights, not the count.
- *Slovakia's averaged tiles on a grid of another CRS* (accepted and built).
  `GridResolutions.resolution` gave a grid of exactly 2 m or 5 m the averaged tiles whatever its
  CRS; Poland's 2 m grid then reprojected them bilinearly (averaged, then smoothed): 87.7 % of the
  Slovak side's spots against 95.7 % with the 1 m tiles averaged by the mosaic. Now only a grid of
  the tiles' CRS reads the averaged tiles (`resolution(grid_res, grid_crs)`); the country layer's
  own bands are unchanged.

### The key v2: two int64 a row

A row of the cube is `[key_a, key_b, count]`; the tiles' `.npz` carry both words. `RECORD_BITS`
covers both: a spot's record is the pair. `pack_keys`/`unpack_keys` and `select` read both words.

| Word, bits | Field |
| --- | --- |
| A 0-15 | as the key of section 2: water (0-1), trees (2-3), height (4-6), clearance (7-9), wall (10-12), prominence of the weaker anchor (13-15) |
| A 16-24 | length mask, as section 2 |
| A 25-26 | border: 0 interior (both anchors in the country), 1 across the border and owned, 2 across the border and the partner's (see "The borders") |
| A 27-29 | partner: 0 none, 1-6 the index into cube.json's `neighbours` (the partner's cube id), 7 unknown (the owner's data beyond the outline where no declared neighbour's boxes reach) |
| A 30-45 | cell row `j` (16 bits, from the origin) |
| A 46-61 | cell column `i` (16 bits) |
| B 0-2 | metres over water: `water_px × res`, edges (0, 5, 20, 50, 100) |
| B 3-5 | height of the lower anchor: `min(elev_a1, elev_a2)`, edges (0, 500, 1000, 2000, 3000) |
| B 6-8 | height of the upper anchor: `max(elev_a1, elev_a2)`, the same edges |
| B 9-11 | mean height of the webbing: `height_mean`, edges (0, 20, 50, 100, 200) |
| B 12-14 | prominence of the stronger anchor: `max(prom1, prom2)`, edges (0, 5, 10, 20, 50) |
| B 15-17 | drop below both anchors: `min(drop1, drop2)`, edges (0, 40, 60, 80, 100) |
| B 18-20 | share of the line high above the terrain: `high_pct`, edges (0, 75, 90, 95, 98) |
| B 21-23 | height difference of the anchors: `|elev_a1 - elev_a2|`, edges (0, 2, 5, 10, 25) |
| B 24-26 | clearance over trees and buildings: `clearance_nmpt`, edges (0, 1, 2, 5, 10); UNKNOWN without a surface model |
| B 27-29 | A-frame needed with the no-fall zone: `lift_needed` (the smallest lift at both ends that validates the line with the country's `end_zone`), edges (0, 0.5, 1, 1.5, 2); a ceiling (a filter "needs at most h"); bin 0 is a line that stands without A-frames; UNKNOWN for a country counted without the options |
| B 30-32 | A-frame needed without the zone: `lift_no_zone`, the same edges; a line of a bin above the last edge needs the zone whatever the A-frame |
| B 33-62 | reserved (0) |

- The edges of word B are **chosen** (the user, 2026-11-08): wave A's recommendation of its second round
  (`local/country-perf-2026-11-07/stage3/A/sk-r2/analysis.md`), measured on 58 tiles of Slovakia's layer
  bands (185 M lines) for each bin's share of the lines and spots and the keys each set adds; the
  measurement of 2026-11-05 (section 6.3's table) had used working values (the lower anchor's and the
  upper anchor's heights 0, 500, 1000, 1500, 2000; the mean height 0, 10, 20, 50, 100; the drop 0, 20,
  50, 100, 200; the high share 0, 25, 50, 75, 90; the height difference 0, 5, 10, 20, 50; the
  clearance over trees as the clearance's), which left bins empty or overfull. The sample's arrays at
  all levels: 91.9 MB at these edges against 40.3 MB at the working values (24 B a row); Slovakia's
  cube about 775 MB (*est.*: that ratio applied to the working values' about 340 MB, without the
  growth of the clearance over trees and of the A-frame fields, which the sample did not hold). The
  growth is still to be checked on a second country. A change of an edge is a change of this table
  and a recount.
- `merge_spots` on word B, as section 6.3's rule (a filter passes when some line of the spot does):
  a floor's field (metres over water, the lower anchor's height, the mean height, the stronger
  prominence, the drop, the high share, the clearance over trees) takes the largest bin, a ceiling's
  field (the upper anchor's height, the height difference, the two A-frame fields) the smallest;
- the two A-frame fields (added 2026-11-07, the end-zone task: docs/roadmap.md "Done: the no-fall zone at
  the ends and the A-frames") exist only when a country is counted with `end_zone`/`anchor_lift` in its
  `options` (`country.form_params`): the count then runs at the superset (every line valid with the zone
  and the largest lift), and the two values per line come from the bucket minima that
  `find_valid_lines(zones=(0, end_zone))` returns (`helpers.lift_values`), which the count mode
  asks for since round 5's Z1 (each part handed to the sink carries `lift_needed` and `lift_no_zone`;
  at 0 / 0 no ladder and no columns); the cost is extra computing, so by the rule of 2026-11-05 it is
  decided by the user on the measurement of docs/performance.md, "The no-fall zone and the A-frames",
  "The country layer". Today's lines are those of bin 0 of both fields, so a cube counted at the
  superset shows today's layer under the filter "no A-frame needed, without the zone";
  UNKNOWN as in section 2. Word A's border and partner fields of a spot: the border field of its
  lines ORed as a 2-bit mask would lose the owner, so a spot's border is that of its first line and
  a spot with lines of two border values is split into two spots by the border value (an id of a
  spot is then `(id, border, partner)`); the counts of spots per cell add them.
- `Filters` gains one field per new dimension with the semantics of the existing ones (a floor
  passes at or above its edge, a ceiling below it, the first edge off, UNKNOWN fails every limit);
  `DIMENSIONS` lists them; `Cube.histogram` counts each (6 bins) under every filter but its own.
- The levels 2, 4 and 8 keep `i // L`, `j // L` on word A's cell bits.

### The global lattice (R4)

- The cell of a line is that of its first anchor **by (lon, lat)** (the smaller lon, then lat; the
  same rule as the owner of a line across a border): `i = floor(lon × 120) - I0`,
  `j = floor(lat × 120) - J0`. A cell is 30″ × 30″ (0.93 km north-south everywhere, 0.61 km
  east-west at 49°). The country's origin `(I0, J0)` is the south-west corner of its outline's box
  less the L band's `max_length`, floored to a multiple of 8 cells (1/15°); cube.json's `origin`
  becomes `[I0, J0]` in cells and `cell_m` becomes `cell_deg: 1/120`.
- The clusters of a spot: `cx = floor(lon × 2400) - 20 I0`, `cy = floor(lat × 2400) - 20 J0`
  (20 clusters a cell: 46 m north-south, 30 m east-west at 49°). The id: `p.cx << 42 | p.cy << 22 |
  dx << 11 | (dy + 1024)` with `cx`, `cy` of 20 bits and `dx`, `dy` of 11 bits (a 5 km line at 78°
  spans 520 clusters east-west; at 85° 1 100: the Arctic sources keep L bands under that, or the
  tile refuses with a plain error). Spots merge across cubes by the lattice alone.
- `TileCounter` transforms the anchors once per tile (`pyproj`, the unique pixels of a part's
  `a1`/`a2`, not every line): below 1 % of a tile's time (est.; measured in wave A on one tile of
  each band).
- `Cube`: `box`, `_range`, `corners`, `reaching` and `cell_request` on lon/lat rectangles without
  pyproj; `corners` gives the rectangle; the km² of a whole cell from its latitude (the page gets it
  as `km2` per row, or computes it from the corners); `cut` keeps the exact outline projected to the
  cube's CRS for the km² of a cut cell, its pieces cut on the lattice's rectangles.
- The page: `L.rectangle` for whole cells, the texts "30″ cells (about 0.9 × 0.6 km)" and the
  levels "1′, 2′, 4′"; `cellsAt`, `requestCells` and `autoLevel` in cells of 1/120°; the kit demo
  (`ui/Gallery.tsx`) on the same lattice.
- A cube of another `version` is refused as today (`Cube.__init__`); no migration of v1 cubes, they
  are counted again.

### The borders (R3)

- **What `main` f8aaff5 (round 4, stage 3's B5, 2026-11-05) changed before the counter, and wave B
  builds on:** `search._anchors(deferred=True)` in `count_tile`
  computes the prominence and the drop at a tile's first line (with a limit `min_prominence`,
  `min_prominence_both` or `min_drop` as before, before the pairs); `linesearch.evaluate_lines` and
  `_sink_lines` take `anchor_values` as a function called once (since round 5's C1 a
  `linesearch.LazyAnchorValues`: the anchors of each part's lines, each once, after four parts every
  useful anchor not known yet in the rows still to come; the same values bit for bit); the columns `prom1`, `prom2`,
  `drop1`, `drop2` reach the counter unchanged. `Plan.border` False means more than "no neighbour":
  the full mask without burning the outline and no coverage counted, on the assumption that the
  tile's grid lies wholly inside the outline (`country._at_border`). R3 keeps that assumption: a grid
  inside the outline has no partner strip, so nothing changes for it; a border tile keeps
  `Plan.border` True, the burned mask and the neighbour fill (and its "Elevation data" line in the
  tile's log, which a tile with `Plan.border` False no longer prints). The partner anchors need the
  prominence and the drop as the others do: the deferred computation covers them (they are anchors
  of the grid). A tile's private memory stands at 1.23 GiB in S and 1.15 GiB in M2 since that commit
  (the prominence beside the pair search's memory; the budgets of 1.6 and 2.1 GiB unchanged): the
  partner strip's anchors add to the same peak, so wave B measures it again on the border tiles.
- **Anchors.** `search._anchors` keeps the anchors outside the outline that lie within the L band's
  `max_length` of it and on pixels of a neighbour's source or of the owner's own source (step 0:
  the owner's data reach beyond the border, and every S line across it ends on them); never on
  the fallback's pixels. `Data.partner` is a uint8 grid in the work folder, 0 inside the outline
  and on the fallback's pixels, else the partner index of the pixel: for a pixel a neighbour
  filled, that neighbour's (`fill_from_neighbours` writes it), for a pixel of the owner's source
  the first neighbour of `Source.neighbours` whose rough boxes hold it, else 7, "unknown" (a border
  with a country without a source in the catalogue). The first-anchor mask of the kernel
  (`find_valid_lines(first=)`) is (core ∩ outline) ∪ partner anchors.
- **Kernel.** `linesearch._pairs` takes one more optional uint8 array, `partner`: when the first
  anchor is a partner, a partner as the other end is skipped before the rings and the pixel test
  (partner-partner pairs are the neighbour's own lines: in the Tatras 194 M against 836 M of SK's).
  Without the array the kernel is byte for byte what it is (the regression set, `test_pairs_match_reference`).
- **Counter.** A line is kept when exactly one anchor lies in the outline and that anchor lies in
  the tile's core (the owner tile is unique), or both lie in the outline and the first (pixel order)
  in the core, as today. A cross-border line is `border = 1` when its first anchor by (lon, lat) is
  the one in the country, else 2; `partner` is `Data.partner` at the other anchor's pixel, its
  indices 1-6 those of cube.json's `neighbours` (the neighbour sources' cube ids, in the order of
  `Source.neighbours`, by `country.NEIGHBOUR_CUBES`: source id → cube id; no source of the
  catalogue declares more than six). A neighbour without a source in the catalogue gives partners
  only where the owner's data reach beyond the border (partner 7); cube.json's `notes` say which
  borders stay hard beyond that.
- **Tiles.** `fixed_tiles` and the grids are unchanged: a tile's grid reaches `_overlap` beyond its
  core, which holds every partner within `max_length`; the border tiles ask the neighbour today
  already (`Plan.border`). Cost: the partner strip's anchors in step 2 and the cross-border pairs in
  step 3: +3-6 % of the tiles' time (est.); RAM, downloads unchanged; the tiles' files +3 % (est.).
- **cube.json.** `neighbours: [cube ids]`, `totals.border: {owned, partner}` for lines and spots,
  `notes` for the hard borders. `countcube.build` sums as today; the border field is part of the key.
- **The web.** `/api/countries` lists every cube; `/cells` and `/histogram` take `border=own|all`
  (default `all`: interior + owned + partner lines whose partner is unknown (7) or has no cube in
  this data folder;
  `own`: interior + owned). The page asks `all` and says under the notes which neighbours are
  counted from this country's data ("Lines across the border with Poland: from Slovakia's data until
  Poland has a layer"). When the partner's cube exists, the partner's own set replaces it (the two
  differ by the measured 2-11 % of the spots, which step 0 showed to be the two grids' data, not
  the reprojection).
- **"Search here."** `cell_request` buffers the cell by `max_length` and no longer intersects the
  outline, so the app's search (which fills the neighbour's data at the border already) finds the
  same lines the layer counted.

### The profile (R7)

- `country.PROFILE`: the bands (name, lengths, resolution, model, slope threshold, core_m, layer),
  `tension` T(L) and `rig`, one for every country, fixed from the band study's result. `Country` keeps
  `id`, `name`, `source`, `area`, `options` (`nmpt`, `water`, `coastline`, `fill_gaps`, `within`);
  `COUNTRIES` lists countries only. A study area (`within`) may override the bands (tools/band_study.py's
  areas): `Country.bands` falls back to `PROFILE.bands`.
- cube.json: `profile`: the sha256 of the profile's JSON; `config_hash` covers it. `/api/countries`
  passes it; the page sums only the cubes of the profile of the first country listed and shows the
  others apart with a note (`layerState.ts activeCubes`); the surface model may differ (today's note).

### What stays byte for byte

The search without a sink, the kernels without the partner array, every saved file of a search
(`tests/regression.py` R13, R14, R16 and the set of docs/regression-tests.md), `tools/border_study.py`'s
classes AA/BB/AB on the same code (its sink keeps its own `TileCounter`s).

### Tests

- `tests/test_count_mode.py`: with the partner array and without, the same lines and funnel inside
  a country; a grid split by an outline with partners: owned + partner = the lines of one grid
  across the split, interior = the lines of the clipped grid.
- `tests/test_border_study.py`: AA + BB + AB of the Żabi Koń clip split by `BORDER_LON` equal the
  one-grid count, as today; AB = the new counter's owned + partner.
- `tests/test_countcube.py`: the key v2 packed and unpacked, the lattice (cells of known lon/lat,
  the origin's floor, the levels), the spot ids (dx of 11 bits), `merge_spots` on word B and the
  split by border, `select`/`histogram` of every new dimension against brute force, `cut` on the
  lattice, a v1 cube refused.
- `tests/test_country.py`: `NEIGHBOUR_CUBES`, the profile's hash in cube.json and the refusal of a
  tile of another profile, a study area overriding the bands.
- `tests/test_country_web.py`: `border=own|all` with and without the partner's cube in the data
  folder, the histogram of a new dimension, the page in Edge (a cell on the border, the note).
- On the real data: the Tatras box through `tools/border_study.py` equals the new counter's owned +
  partner within a few per cent (29.1 M AB lines of `local/border-study-2026-11-05/study.json`);
  Slovakia counted again, its interior cells compared with the v1 cube per cell (the lattice differs,
  so by sums over 8 km boxes).

### Waves (after the band study is in `main`)

| Wave | Agent | Files |
| --- | --- | --- |
| 0 | done 2026-11-06, measured, decided by the user and built (tag `history/partner-resampling`) | `sources/mosaic.py` and `sources/filling.py` (the resampling option), `tools/border_study.py` (`--resampling`, `boxes`), `sources/layers/gridtiles.py`, the runs at four places, the numbers in step 0 above and docs/performance.md |
| A | key, lattice, spots | `countcube.py`, `tests/test_countcube.py` |
| B | anchors, kernel, counter, driver | `linesearch.py` (`partner`), `search.py` (`_anchors`, `Data.partner`, `count_tile`), `sources/filling.py` (the source mask), `country.py` (`PROFILE`, `NEIGHBOUR_CUBES`, the origin, cube.json's fields), `tests/test_count_mode.py`, `tests/test_country.py`, `tests/test_border_study.py` |
| C | web and page | `web.py`, `viewer/src/app/api.ts`, `viewer/src/app/c/*`, `viewer/src/ui/Gallery.tsx`, `locales/en.json`, `tests/test_country_web.py`, `tools/ui_shots.py` |
| lead | docs, the recount | this file, docs/country-precompute.md, docs/roadmap.md, CLAUDE.md, README; Slovakia counted again (1-1.5 h plus the band study's bands, est.), the comparison with the v1 cube |

A and B share `countcube.TileCounter`'s input (the parts' columns): A owns the counter, B hands it the
columns `elev_a1`, `elev_a2`, `drop1`, `drop2`, `height_mean`, `high_pct`, `partner` (per line, the
partner index of the non-owner anchor, 0 inside) and `border`. The waves' reports name every number
measured (the key's growth, the transforms' time, the border tiles' time).

## Wave 1 as built (2026-11-02; read this before sections 3 and 4)

**`search.py`**
- `plan_search(..., tiled=False)`.
- `count_tile(plan, data, core, sink, sag_table=None) -> Dict` returns `plan.funnel` with this call's
  counts. It has **no "lines" key**, because the core filter belongs to the sink: use
  `TileCounter.lines`.
- `FixedTile(name, core, grid)` and `fixed_tiles(plan, core_m)`. A core is kept when it has area in
  common with the outline; one that only touches it is left out.
- `tile_grid(grid, core, overlap, res, origin)`.
- Step 2 is `_anchors(plan, data, quiet)`, which returns `Anchors`. Step 3's arguments are
  `_pair_search`.

**`linesearch.py`**
- `find_valid_lines(sink=)` returns None.
- `SINK_CHUNK = 2048`, `SINK_PART = 1 << 20`. An evaluated part holds up to about 1 M lines, roughly
  100+ MB with its temporaries: count it in a worker's memory.
- `covered_pixels`.

**`sag.py`**
- `parse_tension`, `tension_at`, `TensionTable(rig, min_span, max_span, tension)`.
- `EnvelopeTable._rig_at(span)` is the hook it overrides.

**`countcube.py`**
- As in section 2, plus `pack_keys`, `unpack_keys`, `line_records`, `length_bin`, `spot_ids`,
  `spot_cells`, `sum_keys`, `count_keys`, `Filters.length_mask()`, `Cube.array(mode, level)`
  (ValueError for an unknown mode or level), `Cube.cell_count(level, box)` and `Cube.outline()`.
- `Cube` reads each array into memory when first used (not mapped).
- `Cube.box` clips the view to `bounds_wgs84` widened by 1°. Away from the country it returns an
  empty box (left > right): no cells.
- `Filters.parse` ignores keys it does not know and empty values.
- `build` removes `cube.json` first and writes it last. It does **not** check that the tiles share
  one origin or config.
- In cube.json, `cell_m` and `cluster_m` are floats.

**The page**
- `cellsQuery` sends:
  - `mode`;
  - `level` (`auto` or a number);
  - `length` as `lo-hi`;
  - `prominence`, `clearance`, `height` (always; 0 is off), `trees`, `water`;
  - `wall` only when set;
  - `bbox` = Leaflet's `toBBoxString()`.
- It matches a 400 whose message contains "too many cells" (any case).
- "Search here" goes to `#new&cell=<id>:<band>:<level>:<i>:<j>`, which calls `api.countryRequest`
  for the layer bands.
- The legend's classes are fixed per km²: lines 10 / 300 / 10 k / 300 k, spots 1 / 10 / 100 / 1000.

**For D (section 3)**
- Every tile's meta also holds:
  - `origin` (the country's) and `config` (the hash), both checked by `country build` before
    `countcube.build`;
  - `lines` (`TileCounter.lines`) and `dropped`;
  - the worker's peak memory (`psutil`: `peak_wset` on Windows, `ru_maxrss` elsewhere), so the
    memory per pixel of a count can be measured in the pilot.
- `origin` = `countcube.origin_of(<the outline's bounds in the country's CRS>)`, computed once and
  stored in `country.json`. Every anchor lies inside the outline, so every cell and cluster index
  is non-negative. It does not depend on any band's grid.

**For E (section 4)**
- Keep one `Cube` per (folder, mtime of cube.json).
- The 20000-cell check uses `Cube.cell_count`.
- `Filters.parse(request.query_params)` and the `Cube` methods raise `ValueError`: answer 400 with
  its message.
- The local app shows no Notices link under the credits (`/about` is the public site's).

## Environment (every agent)
- **Windows; Git Bash and PowerShell.** Run headless Edge (pytest's browser tests too) from
  **PowerShell**: started from Git Bash it prints empty pages.
- **Python:** `uv run --frozen <command>` from your worktree. It builds the worktree's own `.venv`
  the first time (about 1-2 min). numba compiles on the first search (cached in `__pycache__`).
- **Test lock:** every pytest, build or search runs under the shared test lock, run from the main
  checkout's path while your command runs in your worktree:
  ```bash
  LOCK="C:/Users/Krzysiek/Documents/Prywata/Find-a-Line/.venv/Scripts/python.exe C:/Users/Krzysiek/Documents/Prywata/Find-a-Line/tools/test_lock.py"
  cd <your worktree> && $LOCK run --owner country-<agent> --timeout 3600 -- uv run --frozen pytest -q tests/test_countcube.py
  ```
  - Shared mode is the default and right for tests and builds.
  - `--expect 60` for short new commands.
  - Never `--exclusive` without asking the lead.
  - `$LOCK status` shows the queue.
  - Killing the wrapper leaves its command running: stop the command.
- **Viewer:**
  - `viewer/node_modules` of your worktree is a directory junction to the main checkout's (the lead
    made it). Never delete through it; only `cmd /c rmdir viewer\node_modules` would remove the link.
  - Build with `node build.mjs`; `npm` is not found under the lock.
- **Data:** never write into the main checkout or its data folder. Searches in tests use `tmp_path`
  or a scratch `--data-dir` in your scratchpad.
- **The main checkout** (`C:/Users/Krzysiek/Documents/Prywata/Find-a-Line`): read nothing there
  except the lock script above.

## Git
- Commit on your branch only, in your worktree. Never push, rebase, merge or touch `main` or
  `country-precompute`; the lead integrates.
- Message style as in `git log`: a subject `<module>: <what>`, a body saying why, the stored-data
  decision ("No stored data changes" or the new files and their versioning), and the last line
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Before your final commit:
  - your own tests;
  - the files of the suite your change can affect;
  - then the full `uv run --frozen pytest -q`, all under the lock.

## Report (your final message)
1. What was built: files, the public names with their signatures, and any behaviour this contract
   left open that you settled, with the reason.
2. Tests: the commands and their results (passed, skipped and why), and the full suite's result.
3. Deviations from this contract: there should be none. If one was unavoidable, why, and what the
   other agents must know.
4. Text for the lead's documents: CLAUDE.md's code-map row(s) and "Things that must stay in sync",
   README rows, roadmap items.
5. Open questions and risks.
