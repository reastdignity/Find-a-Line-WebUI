# The truth check: the search against known highlines

The search is checked against the highlines people have rigged: SlackMap's known lines. One real search around each
cluster of known lines (the production path, as the regression set), the known lines matched to the lines it found,
and every miss diagnosed on the search's own grid with one reason. It measures recall (SlackMap holds known positives
only) per type, source, country, length and resolution, the reasons of the misses, and how many of them a no-fall
zone or A-frames would recover. Built on 2026-11-08 (the task `truth-check`); the first full pass ran on the evening
of 2026-11-08 and was analysed on 2026-11-09; the searches that had failed were repeated on 2026-11-10, and the
numbers below hold them.

The tools (all run by hand, none shipped in the image):

- `tools/slackmap_data.py`: SlackMap's files into the data folder's cache, `KnownLine`, the details of a line by its id.
- `tools/truth_study.py`: `fetch`, `cluster`, `places`, `run` (the searches and their captures), and `analyse` and
  `report`, which call `tools/truth_analysis.py`.
- `tools/truth_analysis.py`: the matching, the reasons of the misses, the zone × lift column, `study.md`/`study.json`.
- `tools/studylib.py`: the helpers shared with `tools/end_zone_study.py` (pixels, slopes, margins, profile chips, the
  data folder with a linked cache, the grid namespace `end_zone_study.diagnose_line` reads).

Every number below is an aggregate. Nothing of SlackMap's data is in this repository (section 1).

## 1. The data: SlackMap

[SlackMap](https://slackmap.com) is the International Slackline Association's (ISA) map of slacklines, filled by its
users. On 2026-11-08 it published, without authentication:

- `https://data.slackmap.com/geojson/lines/all.geojson` (CloudFront, gzip on the wire: 250 KB, 1.4 MB decoded; ETag
  and Last-Modified): 7 969 lines, each a two-point WGS84 LineString with the properties `id`, `ft`, `l` (the length as
  the user stated it, "42.0m" or a number), `lt` (the first letter of the type: 2 156 highlines, 1 924 longlines,
  1 296 parklines, 1 155 waterlines, 800 midlines, 208 tricklines, 164 rodeolines, 266 other or untyped) and `c` (the
  ISO country). No names, heights or dates.
- `https://data.slackmap.com/geojson/spots/all.geojson`: 2 098 spot polygons.
- `https://api.slackmap.com/line/<id>/details`: one line by its id (name, height, anchors, `isMeasured`, dates, ...).
  No query by area and no bulk export of the details.

The anchors are placed by hand: most coordinates have 5 decimals (about 1 m), some only 2-4, and some
stated lengths are far from the anchors' distance. `slackmap_data.KnownLine` keeps the anchors as written, the stated
and the geodesic length, the type, the country, the fewest decimals and the flags of a doubtful geometry:
`no_length`, `length_mismatch` (|geodesic - stated| > max(10 m, 20 % of the stated)) and `coarse_anchor` (at most 3
decimals).

**Fetching.** `truth_study.py fetch` (`slackmap_data.fetch`) gets both files with a conditional GET (If-None-Match /
If-Modified-Since from the cache's index row; a 304 only notes the check) and checks them again after `TTL_DAYS` (30).
The details are asked one after another, `DETAILS_INTERVAL` (1 s) apart, each id once (a 404 cached as
`{"missing": true}`). Every request goes through the pieces of `sources/net.py` (the host's slots of `HOST_SLOTS_OF`:
`data.slackmap.com` 2, `api.slackmap.com` 1, a courtesy cap, since SlackMap publishes no limit; `rate_turn`, the
thread's session, the backoff) with `cache.http_headers()`' User-Agent, counted by `servicecounts`. The files live in
the data folder's cache: `cache/slackmap/geojson/lines.geojson.gz`, `spots.geojson.gz` and
`cache/slackmap/details/<id>.json` (an upper-case letter of an id written as `^` and its lower case: Windows' file
names do not tell the cases apart), indexed in `cache/slackmap/index.sqlite` as every top-level folder; a new folder
under the existing layout, no migration.

**Licence.** None is published for the data: the code is GPL-3.0, the README says only that "the code and data are
never meant to be hidden ... available for people with good intentions and efforts", and the ISA's pages and its
SlackMap FAQ state no terms. The coordinates are facts, but the collection is a database the ISA has invested in, and
in the EU the sui generis database right covers extracting and re-using a substantial part of it. The user's decision
of 2026-11-08: a private validation copy in the data folder's cache, the ISA asked in parallel, nothing published.
So, until the ISA answers:

- nothing of SlackMap's data goes into the repository or onto the site: no copy, no ids, names or coordinates, no
  overlay, no pictures of the places (they show the lines' positions); a cluster's id and centre are made from its
  lines' coordinates, so they stay in the study's outputs as well (in `local/`, never committed);
- the tests use synthetic lines (`tests/test_slackmap_data.py`, `tests/test_truth_study.py`,
  `tests/test_truth_analysis.py`);
- the docs hold aggregate counts only, the use the mail describes and asks the ISA about.

**The mail to the ISA** (a draft of 2026-11-08 in `local/mail-drafts.md`, "International Slackline Association",
not sent yet): the licence or terms of the contributed data and what contributors agree to; whether the private
validation copy and aggregate statistics are fine; an optional overlay with their attribution; a bulk export with
heights, `isMeasured` and dates; the request rate acceptable on `api.slackmap.com`; whether they want our findings
back (misplaced anchors, lines at known spots that SlackMap lacks).

## 2. The method

### The clusters and their searches

`truth_study.py cluster` takes the known highlines and midlines (the user's decision of 2026-11-08: a midline is a
sub-class of a highline; every count is given as the total and per type; `--types` narrows it) in the countries the
catalogue has a source for (`Source.countries`) and clusters them per country, in the CRS of the country's source (the
UTM zone of a line where the country's regional sources differ): anchors within `LINK_M` (300 m) join their lines
(scipy's `cKDTree.query_pairs`, connected components), and a cluster whose circle would pass `RADIUS_MAX` (1 500 m) is
bisected along the longer side of its anchors' box until each part fits. Its centre is the anchors' box centre, its
radius the farthest anchor plus `MARGIN_M` (50 m), at least `RADIUS_MIN` (200 m). Each cluster's search:

    --lat --lon --radius, --min-length max(15, 0.8 x shortest), --max-length max(100, 1.1 x longest),
    --source <id>, <--extra>, --no-plot --yes --ortho never

the shortest and the longest over the lines' stated and geodesic lengths (the stated one alone on a length
mismatch), the source what `sources.choose_source("auto")` gives at the centre (`--country-from-lines`: the lines'
own country, Nominatim only for the regions of a country with regional sources), and everything else the search's
defaults (slope threshold 45°, height difference at most 5 % of the length and 50 m, the surface model "mark", the
source's default resolution, no end zone, no A-frames). The first pass added `--extra "--model sag"`.

On SlackMap's data of 2026-11-08: 1 912 known lines (1 333 highlines, 579 midlines) in 20 countries, 1 024 clusters,
941 of them at the minimum radius of 200 m, the largest 549 m; a cluster holds 1 known line in the median and 24 at
most; none was left out.

### The capture

`truth_study.py run` searches each cluster with `findaline.py` in a child process, with `search._lines`,
`search._anchors` and `helpers.find_significant_slopes` wrapped to write the capture: `grid.json` (the grid's
georeference, the run's parameters, model, rigging and fall allowance, the layers' files), `grids.npz` (the filled
terrain the search used, its obstacle surface, the masks of filled, joined, water and covered pixels, the search
area), `anchors.npy` (step 2's anchors) and `lines.npz` (every line found with its values, group and representative).
A search that ends without lines is a result, status `no_lines` (every known line a miss), not a failure. The
analysis never searches again (but `--profiles`): it reads the capture.

### Matching

In the grid's CRS a found line is a candidate of a known line when both its anchors lie within the known line's
tolerance of the known anchors, either way round, and its length lies within the tolerance of the known line's stated
length or of its anchors' distance (two ends moved inwards by up to the tolerance each would otherwise match a line
much shorter). The tolerance is `tol = max(10 m, 10 % of L)`, L the stated length (else the anchors' distance); for
coarse anchors at least the coordinate quantum, 1.11e5 × 10^-decimals m (111 m at 3 decimals). A line of a doubtful
geometry that is matched counts as matched with a doubtful geometry (its match says whether the nearest candidate
lies within the base tolerance as well). The match is the nearest candidate (the smallest sum of
the two anchor distances), the best match the candidate of the highest clearance (the best line the search offers
there: the report's clearance quantiles and over-trees share). Recall is matched / verifiable: a line with a doubtful
geometry (`coarse_anchor` or `length_mismatch`) is verifiable only when matched. The clean recall leaves those lines
out; the terrain recall takes the lines with no structure at either end (below).

### The reasons of a miss

A miss gets one reason, the first in this order whose test holds. "An end" is a known anchor, its pixel the grid's
pixel whose centre is nearest; "within tol" a distance from the exact known point of at most the tolerance; "steep" a
slope (the slope of `helpers.find_significant_slopes`) at or above the search's threshold; "anchor" a pixel of step 2's
anchors.

| reason | test |
| --- | --- |
| `unverifiable` | a doubtful geometry (`coarse_anchor` or `length_mismatch`) and no match |
| `outside_area` | an end's pixel lies outside the grid or outside the search area |
| `no_data` | an end's pixel has no height in the filled terrain the search used |
| `seam_pixel` | an end has no anchor within tol, and a steep pixel within tol lies at a seam of filled gaps or of a neighbour's data (`search.at_seams`): the search takes no anchor there |
| `water_pixel` | an end has no anchor within tol and its pixel is water |
| `structure_anchor` | an end has no anchor and no steep pixel inside the area within tol, and the obstacle surface the search used stands `STRUCTURE_M` (3 m) or more above the terrain at the end's pixel or within `STRUCTURE_PX` (1) pixel of it: a building, a tower or a tree, which the search never takes as an anchor |
| `no_steep_pixel` | an end has no anchor and no steep pixel inside the area within tol, and no structure |
| `anchor_filtered` | every end without an anchor within tol has a steep pixel there (left out by the elevation band, the prominence or the drop) |
| `length_range` | the rest have anchors within tol at both ends; of their pairs (at most `MAX_END_ANCHORS`, 400, per end, the nearest) of the known length (within tol of the stated length or the anchors' distance) none lies within the search's length range; also when no pair has the known length at all |
| `height_difference` | no pair within `linesearch._pairs`' limit, min(max_anchor_diff % of the length, max_anchor_diff_m) |
| `clearance_near_anchor` | of those pairs (at most `MAX_PAIRS`, 3 000, the smallest distance sums) none valid by `helpers.evaluate_line` with the run's model, end zone and lift; the first failing step of the pair of the largest clearance lies within max(10 m, 10 % of its length) of an end |
| `clearance_mid` | the same with the first failure farther in |
| `surface_obstacle` | under `--nmpt reject` only: no pair that passed the terrain passes the surface (under "mark", the default, the surface rejects nothing: such lines are found and marked) |
| `wall_angle` | `--max-wall-angle` set and no pair left within it |
| `unexplained` | a pair passes every test, another line limit (`--min-height` and the like) explains it, or no pixel lies between a pair's anchors (a note says which) |

Each record also holds the ends (slopes, the nearest pixel of 45, 40, 35 and 30° within tol, the anchors within tol,
the masks, the canopy, the structure), the funnel's counts, its best pair and its staircase, the best pair of any
pixels within 2 px of the known ends and the known pair's own verdict; a match its clearances, marks, representative,
wall angles and canopy.

**The zone × lift column.** A clearance miss is checked again at the end zones 0, 5, 10 and 20 m and the A-frame
lifts 0, 1, 2 and 3 m by the search's rule (`helpers.evaluate_line`'s bucket minima with the ladder of zones, a zone at
most 25 % of the line's length as the search caps it, `helpers.valid_at`; under `--nmpt reject` the surface too; the
pairs over the wall-angle limit left out): a cell counts the misses some pair of which is valid there. A column, not
the verdict: the verdict stays the run's rule, no zone and no lift by default.

### The model

The searches use the sag model (`--model sag`, the sag estimator with its default rigging: pretension 2.5 kN,
stretch 5 % at 10 kN, webbing 70 g/m, athlete 80 kg, a fall zone of 3 m below the sagged webbing): the user's
decision of 2026-11-08, after the pilot. The analysis evaluates with the run's envelope table and fall zone. The
formula model (the search's default, with a fall allowance of 6 m) is the comparison: the first 55 clusters were
searched with it before the switch (section 3, "The formula model against the sag model").

### What it measures and what not

SlackMap holds lines people rigged and reported: known positives. A known line the search misses is a miss of the
search (or of the data, or of SlackMap's anchors); a line the search finds that SlackMap lacks is not a false line.
So the check measures recall. The report's "spots without a known line" (found spots none of whose lines is a
candidate of a known line of a good geometry) is a precision proxy only, and a weak one: a good line may be unrigged,
unreported, out of reach or on private land; the circles are drawn around known lines, so the places are not a sample
of anything; and each search's length range runs up to 1.1 × its longest known line, so it finds spots at every scale
between. In the first pass 44 559 of the 46 272 spots found (96 %) have no known line.

## 3. Results of the first pass (2026-11-08 to 2026-11-10)

The sag model, SlackMap's data of 2026-11-08, the searches by the code of a4a514d (the search and the capture are
the same in 75b4a69), the analysis by 75b4a69's. 1 024 searches: 583 found lines, 438 none (316 "no lines", 122 "no
steep terrain"), 3 failed (below; 39 on the first evening, 36 of them searched again with success on 2026-11-09 and
2026-11-10). 1 906 known lines in the 1 021 places analysed; the 6 known lines of the failed places are left out.
Counts are given as total (highline / midline).

- **Recall**: highline 43 % (536 of 1 261), midline 11 % (56 of 532), all 33 % (592 of 1 793). Without the 30 m
  fallback (which matched none): highline 47 % (536 of 1 150), all 36 % (592 of 1 624).
- **Both ends on terrain** (no structure at either end): highline 47 % (322 of 688), midline 17 % (37 of 214), all
  40 % (359 of 902).
- **Misses at a structure** (`structure_anchor`): 444 (222 / 222), 34 % of the misses.
- **Clearance at the anchors** (`clearance_near_anchor`): 411 (286 / 125), 31 % of the misses; one fails mid-span. With
  a 5 m no-fall zone and no A-frames 239 of the 412 clearance misses have a valid pair, with a 5 m zone and 2 m
  A-frames 310.
- **Shown as a spot**: 34 of the 592 matched lines are their group's representative (the line the map shows); 361 have
  a representative among their candidates.

### Overall

| | highline | midline | all |
| --- | ---: | ---: | ---: |
| known | 1332 | 574 | 1906 |
| verifiable | 1261 | 532 | 1793 |
| matched | 536 | 56 | 592 |
| recall | 43% | 11% | 33% |
| clean geometry: known | 1212 | 527 | 1739 |
| clean geometry: matched | 487 | 51 | 538 |
| clean recall | 40% | 10% | 31% |
| both ends on terrain: known | 723 | 235 | 958 |
| both ends on terrain: verifiable | 688 | 214 | 902 |
| both ends on terrain: matched | 322 | 37 | 359 |
| terrain recall | 47% | 17% | 40% |
| matched with a doubtful geometry | 49 | 5 | 54 |
| matched: shown as a spot (the nearest match a representative) | 27 | 7 | 34 |
| matched: a representative among the candidates | 319 | 42 | 361 |
| matched: over trees (best match) | 34% | 36% | 34% |
| matched: clearance p10 / p50 / p90 (m, best match) | 0.6 / 3.55 / 12.65 | 0.26 / 1.32 / 3.15 | 0.54 / 3.17 / 11.94 |
| matched: wall angle p10 / p50 / p90 (deg, nearest match) | 16.94 / 42.66 / 75.59 | 15.9 / 33.9 / 59.62 | 16.64 / 42.02 / 74.56 |

The clearance quantiles and the over-trees share are those of each matched line's best match, the wall angles those
of its nearest match (the walls at the known anchors). 54 matches have a doubtful geometry (49 / 5), 37 of them with
the nearest match within the base tolerance as well.

### The reasons of the misses

| reason | highline | midline | all | share |
| --- | ---: | ---: | ---: | ---: |
| unverifiable | 71 | 42 | 113 | 9% |
| outside_area | 0 | 0 | 0 | 0% |
| no_data | 0 | 0 | 0 | 0% |
| seam_pixel | 0 | 0 | 0 | 0% |
| water_pixel | 15 | 13 | 28 | 2% |
| structure_anchor | 222 | 222 | 444 | 34% |
| no_steep_pixel | 137 | 98 | 235 | 18% |
| anchor_filtered | 0 | 0 | 0 | 0% |
| length_range | 2 | 3 | 5 | 0% |
| height_difference | 62 | 15 | 77 | 6% |
| clearance_near_anchor | 286 | 125 | 411 | 31% |
| clearance_mid | 1 | 0 | 1 | 0% |
| surface_obstacle | 0 | 0 | 0 | 0% |
| wall_angle | 0 | 0 | 0 | 0% |
| unexplained | 0 | 0 | 0 | 0% |

### Clearance misses with a no-fall zone or A-frames

Both clearance reasons (412 misses: 287 / 125); a cell counts the misses some pair of which is valid at that end zone
(rows) and A-frame lift (columns), total (highline / midline):

| zone \ lift | 0 m | 1 m | 2 m | 3 m |
| --- | ---: | ---: | ---: | ---: |
| 0 m | 0 (0 / 0) | 98 (74 / 24) | 239 (171 / 68) | 325 (220 / 105) |
| 5 m | 239 (174 / 65) | 286 (199 / 87) | 310 (213 / 97) | 335 (227 / 108) |
| 10 m | 273 (195 / 78) | 302 (209 / 93) | 324 (222 / 102) | 349 (236 / 113) |
| 20 m | 281 (200 / 81) | 312 (216 / 96) | 334 (229 / 105) | 356 (241 / 115) |

### By length (SlackMap's length bins)

| length | known | verifiable | matched | recall | clean recall | terrain recall | clearance p50 | over trees | wall angle p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0-30 | 392 (249 / 143) | 378 (245 / 133) | 107 (94 / 13) | 28% (38% / 10%) | 26% (36% / 9%) | 42% (51% / 19%) | 2.64 | 32% | 40.46 |
| 30-50 | 479 (291 / 188) | 447 (275 / 172) | 124 (108 / 16) | 28% (39% / 9%) | 26% (37% / 9%) | 35% (43% / 18%) | 2.63 | 35% | 42.3 |
| 50-100 | 624 (441 / 183) | 582 (411 / 171) | 198 (180 / 18) | 34% (44% / 11%) | 32% (42% / 9%) | 36% (43% / 14%) | 3.25 | 33% | 41.03 |
| 100-200 | 280 (233 / 47) | 261 (218 / 43) | 100 (93 / 7) | 38% (43% / 16%) | 36% (40% / 16%) | 44% (47% / 25%) | 3.86 | 39% | 41.48 |
| 200-500 | 117 (107 / 10) | 111 (101 / 10) | 52 (52 / 0) | 47% (51% / 0%) | 44% (48% / 0%) | 54% (58% / 0%) | 5.13 | 31% | 47.44 |
| 500+ | 14 (11 / 3) | 14 (11 / 3) | 11 (9 / 2) | 79% (82% / 67%) | 75% (78% / 67%) | 67% (71% / 50%) | 2.82 | 36% | 32.14 |

Reasons of the misses by length, total (highline / midline):

| length | unverifiable | water_pixel | structure_anchor | no_steep_pixel | length_range | height_difference | clearance_near_anchor | clearance_mid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0-30 | 14 (4 / 10) | 4 (1 / 3) | 129 (67 / 62) | 49 (20 / 29) | 1 (1 / 0) | 9 (6 / 3) | 79 (56 / 23) | 0 (0 / 0) |
| 30-50 | 32 (16 / 16) | 7 (4 / 3) | 132 (55 / 77) | 69 (38 / 31) | 4 (1 / 3) | 9 (6 / 3) | 102 (63 / 39) | 0 (0 / 0) |
| 50-100 | 42 (30 / 12) | 13 (6 / 7) | 131 (60 / 71) | 75 (47 / 28) | 0 (0 / 0) | 35 (29 / 6) | 129 (88 / 41) | 1 (1 / 0) |
| 100-200 | 19 (15 / 4) | 2 (2 / 0) | 39 (29 / 10) | 32 (24 / 8) | 0 (0 / 0) | 19 (16 / 3) | 69 (54 / 15) | 0 (0 / 0) |
| 200-500 | 6 (6 / 0) | 2 (2 / 0) | 13 (11 / 2) | 10 (8 / 2) | 0 (0 / 0) | 5 (5 / 0) | 29 (23 / 6) | 0 (0 / 0) |
| 500+ | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 3 (2 / 1) | 0 (0 / 0) |

### By resolution

| resolution | known | verifiable | matched | recall | clean recall | terrain recall | clearance p50 | over trees | wall angle p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 m | 1397 (964 / 433) | 1312 (907 / 405) | 464 (420 / 44) | 35% (46% / 11%) | 33% (44% / 10%) | 40% (48% / 16%) | 2.74 | 36% | 40.8 |
| 2 m | 35 (27 / 8) | 35 (27 / 8) | 12 (11 / 1) | 34% (41% / 12%) | 32% (41% / 0%) | 50% (50% / 50%) | 5.75 | 58% | 47.96 |
| 2.5 m | 3 (3 / 0) | 3 (3 / 0) | 2 (2 / 0) | 67% (67% / -) | 67% (67% / -) | 100% (100% / -) | 3.81 | 50% | 67.32 |
| 5 m | 288 (220 / 68) | 274 (213 / 61) | 114 (103 / 11) | 42% (48% / 18%) | 40% (47% / 18%) | 53% (57% / 32%) | 5.13 | 24% | 45.8 |
| 30 m | 183 (118 / 65) | 169 (111 / 58) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (0% / 0%) | - | - | - |

Reasons of the misses by resolution, total (highline / midline):

| resolution | unverifiable | water_pixel | structure_anchor | no_steep_pixel | length_range | height_difference | clearance_near_anchor | clearance_mid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 m | 85 (57 / 28) | 22 (12 / 10) | 257 (107 / 150) | 132 (65 / 67) | 5 (2 / 3) | 57 (44 / 13) | 375 (257 / 118) | 0 (0 / 0) |
| 2 m | 0 (0 / 0) | 0 (0 / 0) | 14 (9 / 5) | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 8 (6 / 2) | 0 (0 / 0) |
| 2.5 m | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| 5 m | 14 (7 / 7) | 3 (1 / 2) | 58 (33 / 25) | 52 (36 / 16) | 0 (0 / 0) | 18 (16 / 2) | 28 (23 / 5) | 1 (1 / 0) |
| 30 m | 14 (7 / 7) | 3 (2 / 1) | 114 (72 / 42) | 51 (36 / 15) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) |

### By source

| source | known | verifiable | matched | recall | clean recall | terrain recall | clearance p50 | over trees | wall angle p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| usa | 274 (173 / 101) | 251 (165 / 86) | 73 (60 / 13) | 29% (36% / 15%) | 26% (32% / 14%) | 29% (36% / 15%) | 1.93 | 0% | 40.46 |
| geoportal | 233 (175 / 58) | 223 (168 / 55) | 46 (44 / 2) | 21% (26% / 4%) | 20% (25% / 4%) | 43% (48% / 0%) | 2.76 | 43% | 33.11 |
| france | 206 (134 / 72) | 200 (129 / 71) | 95 (82 / 13) | 48% (64% / 18%) | 45% (62% / 15%) | 51% (58% / 29%) | 3.74 | 58% | 47.29 |
| spain | 191 (141 / 50) | 180 (136 / 44) | 58 (54 / 4) | 32% (40% / 9%) | 31% (38% / 9%) | 43% (50% / 16%) | 5.13 | 14% | 39.19 |
| europe | 183 (118 / 65) | 169 (111 / 58) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (0% / 0%) | - | - | - |
| england | 124 (74 / 50) | 120 (72 / 48) | 49 (45 / 4) | 41% (62% / 8%) | 39% (61% / 8%) | 50% (63% / 13%) | 2.23 | 22% | 43.45 |
| swisstopo | 115 (63 / 52) | 105 (56 / 49) | 32 (31 / 1) | 30% (55% / 2%) | 28% (52% / 2%) | 31% (50% / 0%) | 4.34 | 59% | 45.48 |
| spain_canarias | 97 (79 / 18) | 94 (77 / 17) | 56 (49 / 7) | 60% (64% / 41%) | 58% (62% / 41%) | 67% (67% / 67%) | 5.06 | 34% | 53.65 |
| new_zealand | 90 (76 / 14) | 86 (73 / 13) | 25 (22 / 3) | 29% (30% / 23%) | 24% (24% / 23%) | 24% (25% / 22%) | 1.63 | 40% | 39.27 |
| slovenia | 80 (73 / 7) | 73 (66 / 7) | 46 (45 / 1) | 63% (68% / 14%) | 60% (65% / 14%) | 63% (68% / 14%) | 3.61 | 0% | 49.53 |
| wales | 43 (36 / 7) | 43 (36 / 7) | 32 (27 / 5) | 74% (75% / 71%) | 74% (74% / 71%) | 77% (77% / 75%) | 2.32 | 31% | 31.36 |
| austria | 34 (31 / 3) | 28 (25 / 3) | 13 (13 / 0) | 46% (52% / 0%) | 44% (50% / 0%) | 67% (67% / -) | 3.36 | 69% | 35.75 |
| czechia | 32 (26 / 6) | 32 (26 / 6) | 11 (11 / 0) | 34% (42% / 0%) | 34% (42% / 0%) | 60% (60% / -) | 6.75 | 64% | 50.17 |
| slovakia | 29 (29 / 0) | 23 (23 / 0) | 10 (10 / 0) | 43% (43% / -) | 35% (35% / -) | 0% (0% / -) | 2.14 | 100% | 43.26 |
| baden_wurttemberg | 23 (9 / 14) | 22 (9 / 13) | 5 (5 / 0) | 23% (56% / 0%) | 23% (56% / 0%) | 67% (67% / -) | 16.67 | 80% | 36.14 |
| bavaria | 22 (18 / 4) | 20 (16 / 4) | 9 (8 / 1) | 45% (50% / 25%) | 45% (50% / 25%) | 67% (67% / -) | 3.59 | 56% | 48.51 |
| brandenburg | 22 (7 / 15) | 20 (6 / 14) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (0% / 0%) | - | - | - |
| queensland | 19 (17 / 2) | 19 (17 / 2) | 5 (5 / 0) | 26% (29% / 0%) | 26% (29% / 0%) | 26% (29% / 0%) | 3.37 | 0% | 37.88 |
| norway | 16 (14 / 2) | 14 (13 / 1) | 8 (8 / 0) | 57% (62% / 0%) | 57% (62% / 0%) | 50% (50% / -) | 4.72 | 38% | 40.45 |
| canada | 15 (12 / 3) | 15 (12 / 3) | 5 (5 / 0) | 33% (42% / 0%) | 33% (42% / 0%) | - (- / -) | 1.46 | 100% | 21.87 |
| british_columbia | 13 (7 / 6) | 12 (6 / 6) | 2 (2 / 0) | 17% (33% / 0%) | 17% (33% / 0%) | 33% (33% / -) | 3.78 | 100% | 61.34 |
| north_rhine_westphalia | 8 (1 / 7) | 8 (1 / 7) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (- / 0%) | - | - | - |
| malta | 7 (3 / 4) | 7 (3 / 4) | 3 (2 / 1) | 43% (67% / 25%) | 43% (67% / 25%) | 43% (67% / 25%) | 5.18 | 0% | 41.72 |
| saxony_anhalt | 6 (5 / 1) | 6 (5 / 1) | 5 (5 / 0) | 83% (100% / 0%) | 83% (100% / 0%) | 100% (100% / -) | 1.8 | 80% | 53.84 |
| denmark | 5 (0 / 5) | 5 (0 / 5) | 0 (0 / 0) | 0% (- / 0%) | 0% (- / 0%) | - (- / -) | - | - | - |
| scotland | 5 (3 / 2) | 4 (2 / 2) | 1 (1 / 0) | 25% (50% / 0%) | 25% (50% / 0%) | 50% (50% / -) | 12.04 | 0% | 6.36 |
| trento | 4 (3 / 1) | 4 (3 / 1) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (0% / -) | - | - | - |
| south_tyrol | 3 (3 / 0) | 3 (3 / 0) | 2 (2 / 0) | 67% (67% / -) | 67% (67% / -) | 100% (100% / -) | 3.81 | 50% | 67.32 |
| lower_saxony | 2 (1 / 1) | 2 (1 / 1) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | - (- / -) | - | - | - |
| tasmania | 2 (1 / 1) | 2 (1 / 1) | 0 (0 / 0) | 0% (0% / 0%) | 0% (0% / 0%) | 0% (0% / 0%) | - | - | - |
| finland | 1 (0 / 1) | 1 (0 / 1) | 1 (0 / 1) | 100% (- / 100%) | - (- / -) | 100% (- / 100%) | 1.51 | 0% | 11.82 |
| hesse | 1 (0 / 1) | 1 (0 / 1) | 0 (0 / 0) | 0% (- / 0%) | 0% (- / 0%) | - (- / -) | - | - | - |
| rhineland_palatinate | 1 (0 / 1) | 1 (0 / 1) | 0 (0 / 0) | 0% (- / 0%) | 0% (- / 0%) | - (- / -) | - | - | - |

Reasons of the misses by source, total (highline / midline):

| source | unverifiable | water_pixel | structure_anchor | no_steep_pixel | length_range | height_difference | clearance_near_anchor | clearance_mid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| usa | 23 (8 / 15) | 4 (0 / 4) | 0 (0 / 0) | 63 (24 / 39) | 3 (2 / 1) | 11 (10 / 1) | 97 (69 / 28) | 0 (0 / 0) |
| geoportal | 10 (7 / 3) | 1 (1 / 0) | 125 (83 / 42) | 18 (13 / 5) | 0 (0 / 0) | 2 (1 / 1) | 31 (26 / 5) | 0 (0 / 0) |
| france | 6 (5 / 1) | 1 (0 / 1) | 38 (3 / 35) | 4 (2 / 2) | 0 (0 / 0) | 5 (3 / 2) | 57 (39 / 18) | 0 (0 / 0) |
| spain | 11 (5 / 6) | 0 (0 / 0) | 53 (30 / 23) | 42 (28 / 14) | 0 (0 / 0) | 13 (12 / 1) | 14 (12 / 2) | 0 (0 / 0) |
| europe | 14 (7 / 7) | 3 (2 / 1) | 114 (72 / 42) | 51 (36 / 15) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| england | 4 (2 / 2) | 12 (10 / 2) | 22 (2 / 20) | 5 (3 / 2) | 0 (0 / 0) | 4 (1 / 3) | 28 (11 / 17) | 0 (0 / 0) |
| swisstopo | 10 (7 / 3) | 0 (0 / 0) | 15 (2 / 13) | 2 (0 / 2) | 1 (0 / 1) | 11 (6 / 5) | 44 (17 / 27) | 0 (0 / 0) |
| spain_canarias | 3 (2 / 1) | 3 (1 / 2) | 5 (3 / 2) | 10 (8 / 2) | 0 (0 / 0) | 5 (4 / 1) | 14 (11 / 3) | 1 (1 / 0) |
| new_zealand | 4 (3 / 1) | 0 (0 / 0) | 4 (2 / 2) | 18 (14 / 4) | 0 (0 / 0) | 9 (9 / 0) | 30 (26 / 4) | 0 (0 / 0) |
| slovenia | 7 (7 / 0) | 0 (0 / 0) | 0 (0 / 0) | 2 (0 / 2) | 0 (0 / 0) | 4 (4 / 0) | 21 (17 / 4) | 0 (0 / 0) |
| wales | 0 (0 / 0) | 0 (0 / 0) | 2 (1 / 1) | 0 (0 / 0) | 0 (0 / 0) | 2 (2 / 0) | 7 (6 / 1) | 0 (0 / 0) |
| austria | 6 (6 / 0) | 0 (0 / 0) | 5 (4 / 1) | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 9 (7 / 2) | 0 (0 / 0) |
| czechia | 0 (0 / 0) | 0 (0 / 0) | 14 (9 / 5) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 7 (6 / 1) | 0 (0 / 0) |
| slovakia | 6 (6 / 0) | 0 (0 / 0) | 2 (2 / 0) | 0 (0 / 0) | 0 (0 / 0) | 2 (2 / 0) | 9 (9 / 0) | 0 (0 / 0) |
| baden_wurttemberg | 1 (0 / 1) | 0 (0 / 0) | 11 (1 / 10) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) | 5 (2 / 3) | 0 (0 / 0) |
| bavaria | 2 (2 / 0) | 0 (0 / 0) | 4 (1 / 3) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 7 (7 / 0) | 0 (0 / 0) |
| brandenburg | 2 (1 / 1) | 3 (0 / 3) | 8 (1 / 7) | 8 (4 / 4) | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) |
| queensland | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 3 (1 / 2) | 0 (0 / 0) | 2 (2 / 0) | 8 (8 / 0) | 0 (0 / 0) |
| norway | 2 (1 / 1) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 3 (2 / 1) | 3 (3 / 0) | 0 (0 / 0) |
| canada | 0 (0 / 0) | 0 (0 / 0) | 4 (3 / 1) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 6 (4 / 2) | 0 (0 / 0) |
| british_columbia | 1 (1 / 0) | 0 (0 / 0) | 6 (0 / 6) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) | 3 (3 / 0) | 0 (0 / 0) |
| north_rhine_westphalia | 0 (0 / 0) | 0 (0 / 0) | 3 (1 / 2) | 3 (0 / 3) | 0 (0 / 0) | 0 (0 / 0) | 2 (0 / 2) | 0 (0 / 0) |
| malta | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 2 (0 / 2) | 0 (0 / 0) | 0 (0 / 0) | 2 (1 / 1) | 0 (0 / 0) |
| saxony_anhalt | 0 (0 / 0) | 0 (0 / 0) | 1 (0 / 1) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| denmark | 0 (0 / 0) | 0 (0 / 0) | 2 (0 / 2) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 3 (0 / 3) | 0 (0 / 0) |
| scotland | 1 (1 / 0) | 0 (0 / 0) | 2 (0 / 2) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) |
| trento | 0 (0 / 0) | 0 (0 / 0) | 1 (0 / 1) | 2 (2 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| south_tyrol | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| lower_saxony | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 0 (0 / 0) | 1 (0 / 1) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| tasmania | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 1 (1 / 0) | 1 (0 / 1) | 0 (0 / 0) |
| finland | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| hesse | 0 (0 / 0) | 0 (0 / 0) | 1 (0 / 1) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) |
| rhineland_palatinate | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 0 (0 / 0) | 1 (0 / 1) | 0 (0 / 0) |

### By country

| country | known | verifiable | matched | recall | clean recall | terrain recall | clearance p50 | over trees | wall angle p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ES | 288 (220 / 68) | 274 (213 / 61) | 114 (103 / 11) | 42% (48% / 18%) | 40% (47% / 18%) | 53% (57% / 32%) | 5.13 | 24% | 45.8 |
| US | 273 (172 / 101) | 250 (164 / 86) | 73 (60 / 13) | 29% (37% / 15%) | 26% (32% / 14%) | 29% (37% / 15%) | 1.93 | 0% | 40.46 |
| PL | 233 (175 / 58) | 223 (168 / 55) | 46 (44 / 2) | 21% (26% / 4%) | 20% (25% / 4%) | 43% (48% / 0%) | 2.76 | 43% | 33.11 |
| FR | 206 (134 / 72) | 200 (129 / 71) | 95 (82 / 13) | 48% (64% / 18%) | 45% (62% / 15%) | 51% (58% / 29%) | 3.74 | 58% | 47.29 |
| GB | 172 (113 / 59) | 167 (110 / 57) | 82 (73 / 9) | 49% (66% / 16%) | 48% (65% / 16%) | 58% (67% / 26%) | 2.31 | 26% | 35.47 |
| IT | 149 (94 / 55) | 136 (88 / 48) | 2 (2 / 0) | 1% (2% / 0%) | 1% (2% / 0%) | 2% (3% / 0%) | 3.81 | 50% | 67.32 |
| CH | 115 (63 / 52) | 105 (56 / 49) | 32 (31 / 1) | 30% (55% / 2%) | 28% (52% / 2%) | 31% (50% / 0%) | 4.34 | 59% | 45.48 |
| DE | 101 (48 / 53) | 96 (45 / 51) | 19 (18 / 1) | 20% (40% / 2%) | 20% (40% / 2%) | 33% (56% / 0%) | 5.06 | 68% | 48.51 |
| NZ | 90 (76 / 14) | 86 (73 / 13) | 25 (22 / 3) | 29% (30% / 23%) | 24% (24% / 23%) | 24% (25% / 22%) | 1.63 | 40% | 39.27 |
| SI | 80 (73 / 7) | 73 (66 / 7) | 46 (45 / 1) | 63% (68% / 14%) | 60% (65% / 14%) | 63% (68% / 14%) | 3.61 | 0% | 49.53 |
| AU | 46 (41 / 5) | 45 (40 / 5) | 5 (5 / 0) | 11% (12% / 0%) | 11% (12% / 0%) | 20% (24% / 0%) | 3.37 | 0% | 37.88 |
| AT | 34 (31 / 3) | 28 (25 / 3) | 13 (13 / 0) | 46% (52% / 0%) | 44% (50% / 0%) | 67% (67% / -) | 3.36 | 69% | 35.75 |
| CZ | 32 (26 / 6) | 32 (26 / 6) | 11 (11 / 0) | 34% (42% / 0%) | 34% (42% / 0%) | 60% (60% / -) | 6.75 | 64% | 50.17 |
| SK | 29 (29 / 0) | 23 (23 / 0) | 10 (10 / 0) | 43% (43% / -) | 35% (35% / -) | 0% (0% / -) | 2.14 | 100% | 43.26 |
| CA | 28 (19 / 9) | 27 (18 / 9) | 7 (7 / 0) | 26% (39% / 0%) | 26% (39% / 0%) | 33% (33% / -) | 2.48 | 100% | 32.63 |
| NO | 16 (14 / 2) | 14 (13 / 1) | 8 (8 / 0) | 57% (62% / 0%) | 57% (62% / 0%) | 50% (50% / -) | 4.72 | 38% | 40.45 |
| MT | 7 (3 / 4) | 7 (3 / 4) | 3 (2 / 1) | 43% (67% / 25%) | 43% (67% / 25%) | 43% (67% / 25%) | 5.18 | 0% | 41.72 |
| DK | 5 (0 / 5) | 5 (0 / 5) | 0 (0 / 0) | 0% (- / 0%) | 0% (- / 0%) | - (- / -) | - | - | - |
| FI | 1 (0 / 1) | 1 (0 / 1) | 1 (0 / 1) | 100% (- / 100%) | - (- / -) | 100% (- / 100%) | 1.51 | 0% | 11.82 |
| PR | 1 (1 / 0) | 1 (1 / 0) | 0 (0 / 0) | 0% (0% / -) | 0% (0% / -) | 0% (0% / -) | - | - | - |

### The failed searches

On the evening of 2026-11-08 the searches of 39 places (86 known lines: 75 / 11) stopped with a download or read
error:

| cause | places | known lines | searched again |
| --- | ---: | ---: | --- |
| ARSO's server for Slovenia's DMR 1 m sheets answered HTTP 503 ("No server is available to handle this request") on the evening of 2026-11-08, and again in the night of 2026-11-09 | 35 | 79 | 2026-11-10, when the server answered again: 29 found lines, 6 none |
| three Polish XYZ sheets begin with a UTF-8 byte order mark, which `np.loadtxt` in `sources/readers/sheetfile.py` reads as part of the first number ("could not convert string 'ï»¿6426840.00'"): a production bug, open | 3 | 6 | failed again on 2026-11-09 and 2026-11-10 |
| the Environment Agency's WCS answered HTTP 500 for one tile of its DSM | 1 | 1 | 2026-11-09: found lines |

`run --failed` searched them again (2026-11-09 from 01:08, when ARSO still answered 503, and 2026-11-10 with
`--parallel 2`; one Slovenian search the first repeat had left without a capture was searched by its id). Left out
of every number above: the 3 Polish places (6 known lines: 1 / 5), which fail until the reader is fixed.

### Reading the numbers

- **More than half of the misses are places without any line**: 721 of the 1 314 misses lie in the 438 places whose
  search found no line at all.
- **Structures as anchors**: 444 misses (34 %) have an end on a building, a tower or a tree, where the search, which
  anchors on steep terrain only, never looks; 43 % of the midline misses (222 of 518) and 28 % of the highline misses
  (222 of 796). Only 958 of the 1 906 known lines (50 %) stand on terrain at both ends as far as the surface models
  tell; on them the recall is 40 % (highline 47 %). Poland's misses are mostly structures (125 of 187). Two caveats:
  a source without a surface model sees no structure, so the USA's lines on structures count as `no_steep_pixel` (63
  of its misses, 39 of them midlines) and its terrain recall equals its recall (likewise Queensland, Tasmania,
  Finland and Slovenia, which have no surface model either); and at 30 m the "structure" is the coarse surface
  model's forest (114 of the fallback's misses).
- **The clearance rule at the anchors**: 411 misses have anchors within the tolerance at both ends, of the known
  length and height difference, and every such pair fails the clearance within max(10 m, 10 %) of an end (the fall
  zone below the webbing cuts into the rim right at the anchor); one fails mid-span. A no-fall zone recovers most of
  them: with 5 m and no A-frames 239 of the 412 clearance misses have a valid pair (58 %), with 20 m 281; A-frames
  alone 98 at 1 m, 239 at 2 m, 325 at 3 m; a 5 m zone with 2 m A-frames 310 (75 %). Each of them would be a candidate,
  so the recall would be about 46 % with a 5 m zone (592 + 239 of 1 793) and about 50 % with a 5 m zone and 2 m
  A-frames: an estimate from the analysis' funnel (at most 400 anchors per end, 3 000 pairs), not a search.
- **The 30 m fallback finds nothing**: 183 known lines lie where only FABDEM + Copernicus DEM (30 m) covers (Italy
  outside Trento and South Tyrol, Australia outside Queensland and Tasmania, the German Länder without a source of
  their own): none matched. A highline's anchor is a few metres of rock, which a 30 m pixel does not see (51
  `no_steep_pixel`, 114 `structure_anchor`). A known line there tells about the data, not the search.
- **Per source**, the highline recall: Wales 75 %, Slovenia 68 %, the Canaries 64 %, France 64 %, England 63 %, Switzerland 55 %,
  Austria 52 %, Bavaria 50 %, Czechia 42 %, Spain (5 m) 40 %, the USA 36 %, New Zealand 30 %, Queensland 29 %,
  Poland 26 % (48 % on terrain). The USA's misses are mostly the clearance at the anchors (97) and `no_steep_pixel`
  (63, structures among them); Spain's at 5 m hold 42 `no_steep_pixel` and 53 structures, New Zealand's 18
  `no_steep_pixel`, Slovenia's mostly the clearance at the anchors (21 of 34); Brandenburg (0 of 20) and North
  Rhine-Westphalia (0 of 8) hold mostly midlines on structures and flat land.
  Few lines per source make most of these rough: a source with fewer than about 30 verifiable lines moves by 3 % or more
  per line.
- **By resolution**: 1 m 35 %, 2 m 34 %, 5 m 42 % (all of it Spain), 30 m 0 %. The 5 m and 1 m places are different
  places: no comparison of resolutions on the same lines.
- **By length** the recall grows with the length: 28 % below 30 m, 28 % at 30-50 m, 34 % at 50-100 m, 38 % at
  100-200 m, 47 % at 200-500 m, 79 % above 500 m (14 lines). Short lines are more often on structures (129 of the
  misses below 30 m). 392 known lines are shorter than 30 m, which the search's default `--min-length` 30 leaves out;
  the study's searches set their own range.
- **Height difference**: 77 misses (62 / 15) have no pair within the search's limit of 5 % of the length (at most
  50 m): rigged lines with steeper ends exist; a hint for `--max-anchor-diff`.
- **The matched lines**: their best match has a median clearance of 3.2 m (highline 3.5 m), and 34 % of them are
  marked over trees or buildings: the mark fires on more than a third of the lines people rig (trees within the fall
  allowance below a real line, or the obstacle rule marking rock: to look at with `tools/obstacle_study.py`). Only 34 of
  the 592 are the representative of their group, so the map shows a spot there but mostly another of its lines. The
  wall angles at the known anchors: p10 17°, median 42°.
- **Midlines** hang below the fall allowance by construction; 56 of 532 matched under the sag model, where a short
  line's sag is small.

### The formula model against the sag model

The first 55 clusters of the same list (the most known lines first) were searched with the formula model before the
user's switch to the sag model (the 56th was interrupted by the stop; three Slovenian places failed on ARSO's 503
and one English place on the Environment Agency's 500, which the sag pass then searched). `analyse` and `report` of
those captures (2026-11-09, 23 s and 1 s) against the sag pass's records of the same 51 places, every known line the
same (the repeats of 2026-11-10 touch none of them):

| 51 places, 389 known lines (351 / 38) | formula | sag |
| --- | ---: | ---: |
| verifiable | 375 (338 / 37) | 380 (343 / 37) |
| matched | 65 (64 / 1) | 150 (143 / 7) |
| recall | 17 % (19 % / 3 %) | 39 % (42 % / 19 %) |
| both ends on terrain: verifiable | 188 (175 / 13) | 193 (180 / 13) |
| both ends on terrain: matched | 39 (39 / 0) | 86 (83 / 3) |
| terrain recall | 21 % (22 % / 0 %) | 45 % (46 % / 23 %) |
| `structure_anchor` / `no_steep_pixel` / `height_difference` | 89 / 44 / 20 | 89 / 44 / 20 |
| `clearance_near_anchor` | 154 (141 / 13) | 75 (67 / 8) |
| `clearance_mid` | 2 | 1 |
| `unverifiable` | 14 | 9 |
| clearance misses valid with a 5 m zone and no A-frames | 86 of 156 | 46 of 76 |
| matched: clearance p50 (m, best match) | 2.36 | 2.86 |
| matched: over trees (best match) | 32 % | 32 % |
| places with lines | 34 | 40 |
| lines found | 229 155 | 4 909 394 |
| spots found / without a known line | 2 941 / 2 830 | 10 028 / 9 582 |

Every line the formula model matched is matched under the sag model too; the sag model adds 85: 78 of the formula's
`clearance_near_anchor` misses, its 2 `clearance_mid` and 5 lines of a doubtful geometry. The reasons before the
clearance (structures, steep pixels, height difference) do not depend on the model. The sag model finds 21 times the
lines and 3.4 times the spots in these places.

### The pilot

Before the pass, 12 Polish clusters (92 known lines) with the formula model: recall 8 % (7 of 89). Its misses led to
the reason `structure_anchor` (48 of its 89 verifiable lines), the terrain recall (24 %), the zone × lift column (22 of
its 26 `clearance_near_anchor` misses valid with a 5 m zone and no A-frames), the length check in the matching and
one data folder per study.

### Costs (measured)

| step | measured |
| --- | --- |
| `fetch` | the two files, 374 KB on the wire: seconds |
| `cluster --country-from-lines` | about 5 min (Nominatim for the regions of countries with regional sources only; the agent's note, not timed) |
| `places` | seconds |
| `run`, 1 024 searches one at a time (a shared slot of the test lock), the tiles downloaded on the way | 4 h 20 min from the first capture to the last (15:56-20:17 UTC); 15 478 s of searches: done 553 (median 9.6 s), no_lines 432 (median 7.2 s), failed 39 (median 123 s: ARSO's retries); 8.8 s per cluster in the median, 23 s at p90, 169 s at most |
| the slowest sources (median per cluster) | swisstopo 36 s (its 36 requests a minute), British Columbia 33 s, Norway 17 s, geoportal 14 s, England 13 s, Spain 10 s, the USA 9 s, the 30 m fallback 2 s |
| the cache | about 45 GB more (read off the disk after the pass) |
| the saved runs | 31 GB of line files before `run` deleted them after each capture (`--keep-runs` keeps them); the runs' folder 14 MB afterwards (run.json and the viewer) |
| the captures | 7.5 GB for 1 024 places: `lines.npz` 4.1 GB (20 million lines found that evening; 21.1 million in the 1 021 places analysed after the repeats of 2026-11-10), `grids.npz` 3.4 GB, `anchors.npy` 0.15 GB; the pictures 288 MB |
| `analyse` | 630 s summed over the places (median 0.56 s a place, 0.35 s a known line) |
| `report` | about 1 s without pictures (the formula pass's 56 places) |
| `run --failed --parallel 2` on 2026-11-10 (a shared slot) | 37 searches, 34 of them Slovenian with their sheets downloaded, in about 13 min: 1 457 s of searches, 11 s a Slovenian place in the median, four of them 230-280 s |

The plan's estimates were 4-8 h for the pass, about 20 GB of new cache and 20-25 min for the analysis.

## 4. How to run it again

```
uv run tools/truth_study.py fetch --data-dir <data>
uv run tools/truth_study.py cluster --out <out> --data-dir <data> --country-from-lines --extra "--model sag"
uv run tools/truth_study.py places --out <out>
uv run --frozen python <main checkout>/tools/test_lock.py run --heavy -- uv run --frozen python tools/truth_study.py run --out <out> --data-dir <data> --parallel 4
uv run tools/truth_study.py run --out <out> --data-dir <data> --failed
uv run tools/truth_study.py analyse <out>
uv run tools/truth_study.py report <out> --no-pictures
```

- `<data>` is the real data folder: its cache holds SlackMap's files and the tiles, so a second pass downloads only
  what the first lacked. `<out>` lies outside the repository (a scratchpad, then `local/`): every file in it holds
  SlackMap's ids or coordinates.
- `run` is resumable: a cluster captured with the same options and known lines is not searched again (Ctrl+C and the
  same command go on); `--again` searches every chosen cluster again, `--failed` only the failed ones, `--status
  failed,no_lines` those of the given statuses; `--ids` (also `@FILE`), `--country`, `--source`, `--national-only` and
  `--max-clusters` choose; `--timeout S` is each search's own. `--parallel N` keeps N searches running in the one data
  folder `<out>/data` (its `cache/` linked to the real cache for the run, the runs' viewer and `runs.js` under
  `cache.runs_lock`, each child's work folder its own and removed when it ends); under `--heavy` of the test lock it
  measures nothing but takes the machine (the aim for a pass from the cache: 5-8 min with 4 at once, against about 40
  min one at a time).
- `cluster --types h,m,l` takes other types; `--auto` lets each search choose its source; a place of one's own:
  `run --out <out> --place NAME="<findaline.py options>" --known lines.json` (a JSON list of `KnownLine` dicts or a
  SlackMap-like FeatureCollection).
- `analyse --profiles` also computes production's profile of every known pair (`search.profile_of_line` with the saved
  run's run.json) as a cross-check of the grid's verdict; not run on the first pass. `report` without `--no-pictures`
  draws a hillshade per place and a profile chip per miss (they show the lines' positions: never published).

The outputs:

| file | what |
| --- | --- |
| `<out>/clusters.json` | every cluster with its known lines (`KnownLine` dicts), options, source and the clustering's parameters |
| `<out>/places.md` | the clusters ranked by known lines, overall and per country and source, with a ready `--lat --lon --radius` and the nearest regression test ("covered by" within 2 km) |
| `<out>/<cluster>/known.json` | the cluster's known lines |
| `<out>/<cluster>/output.log` | the search's stdout, then its stderr after `--- stderr ---` |
| `<out>/<cluster>/capture.json` | status (`done`, `no_lines`, `failed`), seconds, options, lines, anchors, source, the error's code and message, the saved run |
| `<out>/<cluster>/capture/` | `grid.json`, `grids.npz`, `anchors.npy`, `lines.npz`, `result.json` (the capture above) |
| `<out>/data/` | the study's data folder: `runs/<run>/run.json` of every saved run (for `--profiles`), `work/` while a search runs |
| `<out>/<cluster>/analysis.json`, `<out>/analysis.json` | every known line's record: outcome, reason, tolerance, ends, funnel, best pair, match, zone × lift |
| `<out>/study.json`, `<out>/study.md` | the report: the tables above, every place's counts, each miss's line, the failed searches |
| `<out>/pictures/` | a hillshade per place, a profile chip per miss |

## 5. Open

- **The failed searches**: 3 Polish places (6 known lines: 1 / 5) fail on the byte order mark of their sheets until
  `sources/readers/sheetfile.py` is fixed; then `run --failed`, `analyse`, `report`.
- **The ISA's answer**: whether the aggregate statistics may stay published, the overlay, a copy of the lines, the
  details' heights. Until then everything of section 1 holds.
- **The details** (`slackmap_data.py details`) of the misses and a sample of the matches are not fetched yet: their
  `isMeasured` heights would check the sag model's realism, their names nothing (never published).
- **The overlay** of known lines in the viewer (a layer on the pattern of `viewer/src/shoreLayer.ts`, served from our
  origin, a credit and an about-page paragraph), only with the ISA's permission.
- **The country layer**: whether the cells of Slovakia's cube that hold known highlines count lines in their length
  bin (phase 7 of the plan).
- **`analyse --profiles`** on the whole pass, the cross-check against production's profiles.
- **Production findings**, not fixed in the task: `findaline.py` on Windows cannot delete its work folder after a
  search that stops without lines (the memory-mapped grids are still referenced by the exception in flight; `run`
  removes the folders its children leave); `sources/readers/sheetfile.py` reads an XYZ sheet beginning with a UTF-8
  byte order mark as a number with three stray characters and fails (three Polish sheets); `helpers.zone_steps`
  rounds the 25 % cap of the end zone up one step on slightly diagonal lines (`ceil` of 15.000000000000002 gives 16
  steps).
- **Decisions the numbers prepare** (none taken): structures as anchors (34 % of the misses), the default end zone
  and A-frames, `--max-anchor-diff`, the 30 m fallback where it is all a search has, the obstacle mark on more than a
  third of the matched lines.
