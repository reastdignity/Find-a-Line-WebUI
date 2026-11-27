# Resampling: bringing elevation data onto the search's grid

Everything known in this project about resampling a raster of heights: where the app does it, the methods that
exist, what their documentation and the literature say, what was measured here, what the user decided and what is
open. Started on 2026-11-24 during the task "OPR DEMs for the USA" (task 4 of [tasks-usa.md](tasks-usa.md)) and
kept up to date while that task runs; the date of the last change is at [State](#state).

Why it matters here: an anchor needs a steep pixel (45° by default) and a line is tested against the heights under
it. A method that smooths removes cliff edges, and with them anchors and lines; a method that sharpens or copies
pixels can make steps that are not in the ground, and with them lines that do not exist. The usual measures of the
literature (the error of a height, of a slope) do not say which of the two a method does to a search.

Every statement carries where it comes from:

- **(code)**: read in the code of `main` c9add3ce (2026-11-24); no line of resampling changed up to df07f46e
  (2026-11-27).
- **(measured, reviewed)**: a measurement of this task whose numbers a second agent recomputed.
- **(repository)**: a measurement written up in the repository's docs before this task; taken from there, not
  recomputed.
- **(measured, not reviewed)**: a worker's numbers, not recomputed yet.
- **(library docs)**: read in the documentation of GDAL or rasterio on 2026-11-24.
- **(literature)**: from abstracts and search summaries only. Three guidance pages (Esri, USDA NRCS, a GDAL ticket)
  answered 403 and were not read at all.
- **(general)**: textbook knowledge, not checked in this project.

## State

Last change: 2026-11-26 (rounds 5 and 6 of the comparison and their reviews are in: a monotone cubic, and GDAL's
methods with and without the widened kernel at 0.76 and 0.91 m; and what a search on several grid resolutions
would take; the user chose cubic for the USA's lidar files of 0.75 to 1.0 m that are not on the grid, and a
point in the roadmap for the general rule, and kept GDAL's widening for those files). The method question of
this task is closed ([Decisions](#decisions)); nothing of it is built yet. No measurement is running.

## Summary

- **The app's rule** (code): data on the grid's own pixels are copied; reprojected data are averaged when finer than
  0.75 of the grid's pixel and interpolated bilinearly otherwise; a neighbour country's data at about the grid's
  pixel size (0.75 to 1.1 of it) are reprojected by nearest (the user, 2026-11-05).
- **Bilinear at the same pixel size smooths.** Half a pixel off the grid it is a 2 by 2 average. Measured on real
  data at two borders it loses 25–42 % of the lines and 4–11 % of the spots the data's own grid finds (repository);
  in the simulated studies of this task it finds the fewest true spots at every size (average ties with it near
  1 m), and none of its spots is false from 0.9 m up.
- **Cubic** finds more than bilinear everywhere it was measured, and its spots are real: 94–99 % of the own grid's
  spots at the two borders, 0 false spots at 0.91 and 1.0 m in the check cells, a few more false ones than bilinear
  at 0.76 m.
- **Nearest** finds the most, and whether it invents depends on the geometry: at 1.0 m nothing false on a lattice
  that is only shifted, 1 false spot per model when it is turned 1°, 19 and 33 when it is turned 3°; false spots in
  every position at 0.76 and 0.91 m, and at any size coarser than the grid. On real data turned 4.4° (the Tatras)
  97–98 % of its spots were real under a looser matching rule; the difference to the simulated 3° case (87 % under
  that rule) is not explained.
- **Lanczos** finds a few more spots than cubic at every size with the same false spots: "the same as cubic" by
  the margin fixed before the runs. It overshoots more than cubic at a step.
- **The literature's methods** (splines of order 3 and 5, kriging) equal cubic at 0.91 and 1.0 m; at 0.76 m they
  find more and invent more. GDAL's cubic spline finds a third to a half fewer spots than cubic: it smooths.
- **A monotone cubic** (PCHIP) never overshoots. It equals cubic at 0.91 and 1.0 m; at 0.76 m it finds a little
  more and invents a little more than cubic, and less than the spline of order 3.
- **GDAL widens its kernels when the source is finer than the grid** (a little averaging; two warp options turn
  it off), the methods outside GDAL sample single points. At 1.0 m there is no widening. At 0.91 m it changes
  next to nothing. At 0.76 m it matters: without it bilinear finds as much as the widened cubic (201 against 207
  of 228) with as few false spots (7 against 6); cubic and Lanczos find a little more (217 and 218) and their
  false spots double (12 and 13). With every method at single points, the higher-order ones find the same and
  bilinear a little less; bilinear invents the fewest, the monotone cubic is next.
- **Average** is the right method for data clearly finer than the grid; at the grid's own size it equals bilinear;
  on data coarser than the grid it invents (11 % false spots at 3 m in a patch).
- **Coarser data resampled to a finer grid lose many of their lines**: 3 m data in a 1 m search find 62–68 % of the
  spots at cliff places by bilinear (68–73 % by cubic) and almost nothing on ground without cliffs. The same data searched
  on their own 3 m grid find 96 % at cliff places, and many false spots on mine ground.
- **The literature** recommends bilinear or cubic for elevation and warns against nearest; higher-order
  interpolation is reported as more accurate than bilinear. It measures heights and slopes, not lines.
- **Decided:** the rules of the first bullet; the OPR wave reads surveys of 1 m or finer (the user, 2026-11-24).
  **Not decided:** the method for surveys of 0.75 to 1.0 m off the grid.

## Where the app resamples

All (code). The search's grid is metric, in the source's CRS (for the USA the UTM zone), 1 m by default. A coarser
grid (2 m, 5 m, 30 m) takes its heights through the same mosaic: data finer than 0.75 of its pixel are averaged.

The list below is every place where heights for a search are resampled (the tracked Python files outside `tests/`
searched for `reproject(` and `Resampling.` on 2026-11-24). Outside `sources/` nothing resamples heights:
`orthophoto.py` scales image tiles, `relief.py` takes block statistics of slopes for the country layer's
estimate, and the study tools resample for their own pictures and measures (`tools/obstacle_study.py` by maximum
and median, `tools/check_source.py`, `tools/study_ortho.py`).

### The mosaic of a search (`sources/mosaic.py`)

`build_mosaic` places every raster of a layer onto the grid (`_place`). A raster whose pixels coincide with the
grid's is copied, value by value: Poland, Malta, the USA's 1 m DEM and most sources at 1 m take this path, and
nothing below applies to them. Any other raster is reprojected by rasterio's `reproject` (GDAL's warper), one strip
at a time (`_warp`), with the method `_resampling` picks from the raster's pixel in metres (`src_pixel_m`) and the
grid's:

| The raster | Method | Constant |
| --- | --- | --- |
| categorical (the water mask) | nearest | |
| a method was asked for (`build_mosaic(resampling=)`) | that method | `RESAMPLINGS`: nearest, bilinear, cubic, average |
| pixel under 0.75 of the grid's | average | `FINER = 0.75` |
| pixel from 0.75 to 1.1 of the grid's, and the caller named a method for that case (`same_resolution=`) | that method | `SAME = 1.1` |
| everything else | bilinear | |

- Only the neighbour fill names a method for the same-resolution case today (below). A source's own reprojected
  data at about the grid's size are bilinear.
- `SAME = 1.1` lies between the two measured cases of nearest for a neighbour's data: right at 1.0 of the grid's
  pixel, wrong at 1.25 ([performance.md](performance.md), "The resampling of a neighbour's data").
- The warp runs with one thread (`WARP_KWARGS`; a crash of GDAL's threaded warper on Windows) and with rasterio's
  default error threshold for the coordinate transform (see [Settings of the warp](#settings-of-the-warp)).
- The source is read with a margin of three of its pixels around the strip; its invalid values are made empty
  before the resampling (`_read_band`), not after.

Known faults of `src_pixel_m`:
- **A CRS in feet counts its pixel in feet.** A 2.5 ft pixel (0.762 m) counts as 2.5, a 3 ft pixel as 3: bilinear
  where the rule in metres says the same, but a 1.5 ft (0.457 m) or 2 ft (0.61 m) pixel is not averaged. No source
  of the catalogue is known to read a CRS in feet today; the OPR wave fixes it. For the same reason the neighbour rule's range can only catch
  files in metres.
- **A degree counts as 111 320 m both ways**, so a geographic raster counts too coarse east-west by the cosine of
  the latitude ([roadmap.md](roadmap.md), "A geographic raster's pixel counted at 111 320 m both ways"; not
  assigned).

### A neighbour's data at a border (`sources/filling.py`)

`fill_from_neighbours` reprojects the neighbour source's rasters onto the grid with
`same_resolution=NEIGHBOUR_SAME_RESOLUTION`, which is `"nearest"`: at 0.75 to 1.1 of the grid's pixel by nearest,
finer data averaged, coarser data bilinear. `NEIGHBOUR_RESAMPLING` (unset) would force one method for all of a
neighbour's rasters; `tools/border_study.py --resampling` uses it to measure.

### When a block or a file is read (`sources/readers/`)

- `windows.py` `_read_window`: a file read onto a block of its own CRS is copied when the pixels coincide (the
  usual case) and resampled **bilinearly** otherwise.
- `windows.py` `_warp_window` (`Windows(warp=)`): a file kept in another CRS than the blocks'. Cyprus is the one
  user: the terrain by **nearest**, the surface model (0.5 m onto 1 m) by **average**
  (`sources/catalogue/cyprus.py`). Those tiles are resampled twice, once by the provider.
- `sheetfile.py` `_xyz_grid`: a text file of points that holds several grids is written on its finest one, the
  others filling in **bilinearly**.
- `wcsreader.py`: an answer of a WCS that is not on the asked pixels is brought onto them by **nearest**.
- A product finer than the 1 m that is cached is **averaged** on its own pixels before caching
  (`Download(average=...)`: Bavaria's 0.2 m surface model; [data-sources.md](data-sources.md)).
- `mosaic.load_slope_file` (a slope raster given by the user): **average**.

### What is cached, and what it costs

The cache holds the data as delivered; the grid is built in every search, and nothing resampled is kept
([roadmap.md](roadmap.md), "Resampling to the working resolution", measured 2026-10-26: 0–13 % of a 1 m search's
time; decided: no cache of resampled tiles).

## The methods

### In the library the app uses

rasterio 1.5.2 with GDAL 3.12.2 offers for a warp: nearest, bilinear, cubic, cubic spline, Lanczos, average, RMS,
mode, minimum, maximum, median, the first and third quartile, sum (library docs). rasterio's enum also lists
`gauss`, which the warper does not take.

| Method | What it does | Passes through the source's values | Can leave the range of the neighbouring pixels |
| --- | --- | --- | --- |
| nearest | the value of the source pixel under the target pixel's centre | yes, each value is a copy | no |
| bilinear | weighted mean of 2 by 2 pixels | only when the centres coincide | no |
| cubic | cubic convolution, 4 by 4 kernel | only when the centres coincide | yes: the kernel has negative weights |
| cubic spline | cubic B-spline approximation, 4 by 4 kernel | no: it smooths even when the centres coincide | no: all weights are positive |
| Lanczos | windowed sinc, 6 by 6 kernel | only when the centres coincide | yes, more than cubic |
| average | mean of the source pixels that fall into the target pixel | no | no |
| RMS, mode, min, max, median, quartiles, sum | one statistic of the source pixels in the target pixel | no | no |

The kernel sizes and names are GDAL's (library docs); the two right-hand columns are (general), and both were seen
in this project's numbers (round 4, stage 1: cubic spline never overshoots and has the largest error; cubic and
Lanczos overshoot).

What each does to a search, in short:
- **Nearest** keeps every step of the data as sharp as it was and moves each pixel by up to half a pixel. Where
  the two lattices drift against each other (another pixel size, a turn) the pick jumps by a pixel now and then:
  a row or a column is doubled or dropped. Each doubled row of a coarse pixel is a small wall.
- **Bilinear** cannot make a step that is not there; it flattens the ones that are. Half a pixel off the grid it
  averages 2 by 2 pixels ("the half-pixel pitfall").
- **Cubic and Lanczos** flatten less than bilinear and pay with over- and undershoot beside a step.
- **Average** is a low-pass filter of the size of the target pixel: right when the source is finer, the same as
  bilinear weighting at an equal pixel size, and no interpolation at all when the source is coarser (it then
  copies coarse pixels, as nearest does).

### Outside the warper

- **Interpolating splines of order 3 and 5** (`scipy.ndimage.map_coordinates`; scipy is a dependency of the app).
  A prefilter makes the spline pass through the source's values. Order 5 is the nearest library equivalent of the
  literature's biquintic interpolation, not the same scheme. They sample single points: they do not widen when the
  source is finer than the grid (see below). In the app they would need a read path of their own beside the
  mosaic's.
- **Kriging**: a weighted mean of the neighbouring pixels with weights from a fitted variogram; an exact
  interpolator without a nugget, a smoother with one. Not in the app's libraries. PyKrige 1.7.3 (2025-10-16, BSD,
  needs numpy and scipy) and GSTools 1.7.0 (2025-04-28, LGPL, six further packages) were looked at on 2026-11-24;
  the user chose PyKrige for a measurement only, which is in [What was measured
  here](#the-literatures-methods-and-a-turn-of-1-2026-11-24-reviewed).
- **A Hopfield neural network** (Minh et al. 2024): a downscaler from a coarse grid to a finer one. Not defined
  for a pixel ratio near 1 as far as its abstract says; a candidate only for coarse data (the 3 m DEM), never
  implemented here.
- **Shape-preserving (monotone) cubics**: cannot overshoot. The mathematics is standard; no terrain study was
  found. Not a method of GDAL's warp; scipy has it as `RegularGridInterpolator(method="pchip")`, a tensor product
  of one-dimensional PCHIP (Fritsch-Carlson), whose value stays within the four pixels around the position
  (library docs). Measured on 2026-11-26:
  [A monotone cubic, and point sampling at 0.76 m](#a-monotone-cubic-and-point-sampling-at-076-m-2026-11-26-reviewed).
- **Breakline and edge-preserving methods, constrained triangulations**: for building a DEM from points, not for
  resampling a finished raster.
- **No resampling**: a search on the data's own grid. It is what the app does for every source in its own CRS, and
  what "keep a DEM in its original coordinate system as long as possible" (Esri, literature) means. It cannot serve
  a patch of one survey inside another's grid: see the next section.

### A search on several grids

The user's question of 2026-11-26: what would it take to have the same search on two or more grid resolutions.
Read from the code on that day (code); nothing here is planned or decided, and the efforts are estimates.

What a search is today: one grid per search (`search.Plan.grid`, `resolution`, `crs`), north-up, metric, 1 m at
the finest (`sources.source.MIN_RESOLUTION`); every layer is brought onto it. Anchors are pixels of that grid; the
line test walks the pixels between two anchors through one height array with one pixel size
(`helpers.evaluate_line(a1, a2, elevation, res, ...)`); a large area is cut into tiles of the same grid, and a
line belongs to the tile of its first anchor. A run records one resolution and one CRS, and the profile of a line,
the 3D view, the terrain statistics, the access mark, the "Coarser terrain" layer and the limits of the public
site (pixels, pairs) all read them. The country layer already searches one country on three grids, 1 m, 2 m and
5 m, but each grid has its own range of lengths (the bands), so no line is found twice.

Three ways, from the smallest:

1. **Two searches, joined afterwards** (possible by hand today: the same search with `--resolution 1` and
   `--resolution 2`, both runs drawn together by Compare). To make it one result: a join that tells one line found
   on both grids from two lines (the squares of `samelines.py` have a common corner for every grid, but their side
   grows with the pixel; the matcher of this task's measurements exists only as a script), a rule for which grid's
   line is kept, and spots grouped across both. Effort: medium. It removes no resampling: both grids are filled by
   the same warp.
2. **One search that holds several whole-area grids** (the bands' design with overlapping lengths): the same join,
   plus a run with more than one grid in its files and in every reader named above. Effort: high.
3. **A patchwork: each data set on its own lattice** (the only way that removes resampling; a finer UTM grid alone
   does not, since a survey turned or shifted against it is still resampled). Anchors can be found per data set on
   its own pixels. Missing: a line between an anchor on one lattice and an anchor on another, or a line that
   crosses a second lattice, needs a line test that samples heights by position from several rasters (the numba
   kernels of `linesearch.py` and `helpers.evaluate_line`, which decides, take one array); a lattice in feet or in
   a CRS that is not metric cannot be searched as it is; step 1's slope on pixels of different sizes (below); the
   run's files and readers as in 2; every pinned result of a place with two data sets changes. Effort: high, in
   the core of the search.

What applies to all three:
- **The wall angle means something else on each pixel size**: a slope over 2 m or 3 m pixels is flatter than over
  1 m pixels for the same rock, so one threshold finds other anchors on each grid (the slope study in
  docs/roadmap.md, *A slope threshold for the resolution*, gives the equivalents).
- **What was measured** ([Coarser data](#coarser-data-their-own-grid-against-a-1-m-grid-2026-11-23-and-24-reviewed)):
  on their own grid 2 m and 3 m data find 96-97 % of the 1 m spots at cliffs and invent lines on some other
  ground, so a second, coarser grid adds false lines as well as true ones; and for 1 m data in another CRS the
  border study found nearest closest to the own grid.
- **Cost**: the pixels and pairs of every grid add up; a 0.76 m lattice holds 1.7 times the pixels of the 1 m grid
  over the same ground.

### Settings of the warp

- **The kernel widens when the source is finer than the grid** (library docs: the warp options `XSCALE` and
  `YSCALE`, "the number of source pixels … considered by the resampling algorithm", computed per chunk, below one
  for downsampling). So GDAL's bilinear, cubic and Lanczos at 0.76 m onto 1 m already average a little, and a
  point sampler such as scipy's spline does not. Measured (not reviewed): at 0.762 m a point-sampling bilinear
  differs from GDAL's by up to 1.3–3.5 m at single pixels (99.9th percentile 0.3 m); at 1.0 m the two are equal to
  0.03 mm. What it does to a search at 0.76 m is measured (reviewed):
  [point sampling at 0.76 m](#a-monotone-cubic-and-point-sampling-at-076-m-2026-11-26-reviewed). Passed as 1
  through rasterio's `reproject(..., XSCALE=1, YSCALE=1)`, the two options turn the widening off: GDAL's
  bilinear, cubic and Lanczos then equal the plain kernels at single points (rasterio 1.5.2, GDAL 3.12.2;
  reviewed: [GDAL's methods without the widened kernel](#gdals-methods-without-the-widened-kernel-2026-11-26-reviewed)).
- **The coordinate transform is approximated** to within 0.125 source pixel by default (library docs: `-et`;
  rasterio's `tolerance`); 0 gives the exact transform. The app does not set it. Measured (not reviewed): against
  the exact transform the default moves heights by up to 3 mm (1.0 m pixels) and 34 mm (0.762 m) when the survey's
  lattice is only shifted, and by up to 47 and 59 mm when it is turned 3°. Its effect on a search is not measured.
- **An empty source pixel under the target's centre gives an empty target pixel** for the kernel methods, whatever
  the neighbours hold (library docs).

## What the literature says

All (literature): abstracts and search summaries.

- **Agencies: bilinear or cubic for elevation, not nearest.** USGS's specification for elevation-derived
  hydrography asks for bilinear when a DEM is brought to 1 m. USDA NRCS ("Raster Mastery"): bilinear or cubic
  convolution for continuous data, the difference usually small, look at a hillshade for artefacts. Esri: bilinear
  stays within the data's range, cubic may go slightly beyond it; nearest leaves stair-steps and stripes that show
  in the slope.
- **Papers.** Rees 2000: bilinear or bicubic is adequate when interpolating to a finer grid. Kidner 2003 and Shi
  et al. 2005: higher-order interpolation, up to biquintic, is more accurate than bilinear and worth its cost.
  Minh et al. 2024: bicubic and a Hopfield network beat bilinear and kriging for heights, slope and aspect. Not
  unanimous: Takagi 1998 found nearest the most accurate for aspect; a University of Waterloo study found cubic
  smoothing more than bilinear.
- **Lanczos**: no study on elevation data found; its ringing beside an abrupt change is general knowledge.
- **What it does not cover.** The studies measure the error of heights or of slope, mostly from a coarse grid to a
  finer one or the reverse. None found treats a reprojection at about the same pixel size, cliffs, or features a
  method invents. The warning against nearest fits this project's numbers where the pixel sizes differ or the
  lattice is turned, and does not fit the case of a pure shift at one pixel size, where nearest is a copy.

## What was measured here

### Words

- **Spot**: one group of lines (the search's grouping). **Found**: the share of the reference's spots a run has.
  **Real**: the share of a run's spots the reference has; the others are **false**.
- **S1, S2**: the two matching rules of this task's studies. S1, the strict one: a spot is matched when one of
  its lines has a line of the other run with both anchors within 25 m. S2, the looser one: the midpoints of the
  two spots' representative lines lie within 25 m. A spot false under S1 and real under S2 is a near miss. The
  border study of 2026-11-05 used a looser rule still (clusters with about 60 by 46 m of play: the reviewer's
  reading of `tools/border_study.py`).
- **Two references.** "The truth" is the 1 m data a simulated survey was made from. "The survey on its own grid" is
  the survey searched without any resampling: the border study's reference. A simulated survey is made by averaging
  the truth, which removes lines before any method runs, so shares of the truth are lower than shares of the
  survey for every method.
- **Error** is the difference of a resampled height from the truth. **Overshoot** is a resampled height outside the
  range of the source pixels around it. A method can have the smallest error and overshoot.

### Real data at borders (2026-11-05, repository)

[performance.md](performance.md), "The resampling of a neighbour's data"; `tools/border_study.py`. One country's
1 m data on the neighbour's 1 m grid in another CRS, against the data's own grid, 2,000 to 13,000 spots per
direction; the Tatras turned 4.4°, the Wetterstein hardly turned.

- At the same pixel size: bilinear finds 89–97 % of the own grid's spots, cubic 94–99 %, nearest 98–99.5 %; of each
  method's spots 97–100 % are the own grid's (about 91 % in one direction for all three). Bilinear loses 25–42 % of
  the lines, nearest 0–4 %.
- Finer data (1 m on a 2 m grid): the average finds 99.2–99.7 %; no method is better by more than half a point.
- Coarser data (2.5 m data, the Zillertal ridge): by nearest on a 2 m grid, a ratio of 1.25, 1.7 times the lines
  and 2.5 times the spots; on a 1 m grid 73 867 lines where the data's own grid finds 28.
- Decided from it: the neighbour rule of [Where the app resamples](#a-neighbours-data-at-a-border-sourcesfillingpy).

### Coarser data: their own grid against a 1 m grid (2026-11-23 and 24, reviewed)

- At nine cliff places, data averaged to 2 m and 3 m and searched on their own grid find 97 % and 96 % of the 1 m
  spots; the same data resampled bilinearly to a 1 m grid find 74 % and 66 %
  ([roadmap.md](roadmap.md), "A slope threshold for the resolution").
- Off the grid (sizes in feet, a turned lattice) the bilinear shares are about the same: 73 % at 2 m and 62 % at
  3.05 m on those nine places.
- **The own grid invents on other ground.** On five cells of mine ground and lakeside rock in Minnesota, the 1 m
  truth averaged to 3 m and searched on the 3 m grid gives 13 to 187 spots where the truth has 5 to 20 (real 3 m
  surveys of 2011: 5 to 216). The same average brought back to 1 m bilinearly gives 0 or 1 (a real survey 35 at
  one cell, where the ground had changed since).
- **On ground without cliffs 3 m data in a 1 m search find nothing.** At a valley side in West Virginia whose
  lines are all long, the real 1/9″ DEM (3 m) and a simulated 3.05 m survey find 0 of 18 spots by bilinear and by
  cubic; the 3 m grid finds 18 of 18. The anchors with an open direction fall from 1,303 to 64–455.

### Surveys of 0.5 to 3 m in a 1 m search (2026-11-24, reviewed)

26,464 searches at 14 places; surveys simulated from finer data at the pixel sizes USGS's lidar DEMs really have
(0.5 m to 3.05 m, sizes in feet among them), in a CRS turned against the grid: by 1.5° at the places outside the
USA (a transverse Mercator made for it) and by the place's State Plane zone at the five US places (2.1° at the
two whose record was read; the other three not read). Shares of the truth's spots (S1), at 45°; the share of
real spots is 98–100 % where not given.

**A patch of the survey inside 1 m data** (found %; pooled over 14 places by spots, two places carry 62 %; averaged
per place bilinear is 81 / 79 / 74 / 67 / 47 % and the 10 m fill 16 %):

| Pixel | Bilinear | Cubic | Average (real %) | Nearest (real %) |
| --- | --- | --- | --- | --- |
| 1.0 m | 90 | 93 | 90 | 95 (97) |
| 1.22 m | 87 | 90 | 90 (98) | 96 (95) |
| 1.52 m | 84 | 88 | 93 (97) | 98 (92) |
| 2 m | 78 | 83 | 94 (96) | 98 (89) |
| 3.05 m | 68 | 73 | 95 (89) | 99 (83) |
| the 10 m DEM in the same patch | 27 | | | |

- By the kind of place, bilinear at 1 / 1.52 / 2 / 3.05 m: walls 75 / 66 / 56 / 42 %, small rocks and rims
  92 / 86 / 80 / 71 %.
- The slope threshold (60° to 25°) and the model (formula or sag) move the bilinear shares by 0–2 points on the
  large pools, up to 4 on the four small places.

**The whole circle from the survey, like for like** (found %, average / bilinear / nearest / cubic):

| Pixel | Four places with 0.5 m data (108 spots) | Seven places, every size (1,163 spots) |
| --- | --- | --- |
| 0.5 m | 90 / 83 / 98 / 87 | 95 / 92 / 100 / 95 |
| 0.61 m | 87 / 83 / 97 / 88 | 94 / 92 / 99 / 95 |
| 0.76 m | 84 / 82 / 99 / 89 | 94 / 92 / 99 / 95 |
| 0.91 m | 82 / 82 / 95 / 86 | 92 / 91 / 97 / 94 |
| 1.0 m | 79 / 79 / 95 / 86 | 91 / 91 / 96 / 94 |
| 1.22 m | 75 / 71 / 97 / 80 | 90 / 87 / 97 / 91 |
| 1.52 m | 90 / 63 / 96 / 71 | 93 / 83 / 98 / 88 |
| 2 m | 89 / 54 / 97 / 62 | 94 / 75 / 98 / 82 |
| 3.05 m | 88 / 35 / 98 / 44 | 96 / 64 / 99 / 70 |

- Nearest's real share falls with the pixel size: 86–93 % below 1.5 m, 72 % at 3.05 m on the four places (89 % on
  the seven).
- Every survey here is turned 1.5° to about 2°, so the nearest columns are a turned case: at 1.0 m 93–97 % of its
  spots are real at these cliff places, where the check cells of the next section, turned 3°, hold all of its
  false spots. No unturned survey was run in this study.
- Average equals bilinear near 1 m (an area-weighted average at an equal pixel size is bilinear weighting).
- The survey's position alone moves the found share by up to 13 points at one place, 1–5 elsewhere.
- A survey made from 1 m data instead of 0.5 m data reads 0–8 points lower: the simulation is a lower bound.
- Averaging a file of 0.5 or 0.61 m instead of interpolating it bilinearly gains 2–6 points; that is what the
  feet fault of `src_pixel_m` costs.
- Weak: the sub-metre rows rest on 108 spots; no independent real pair of a foot-sized survey and a 1 m DEM with
  more than one spot was found; both sides of every seam come from one survey.

### Five methods at 0.76 to 1.0 m (2026-11-24, reviewed)

Six cells chosen because a coarse grid invents lines there (four of mine ground, one of lakeside rock, one valley
side); 5 to 20 true spots per cell in the formula model, 76 in all (118 with sag); lines of 30 to 400 m; surveys
made by averaging the 1 m truth; three positions of the survey: two only shifted (turned 0.08° or less), one
turned 3°. Sums over the six cells and the three positions (228 true spots), formula model, true spots found /
false spots (S2):

| Pixel | Bilinear | Cubic | Nearest | Average | Lanczos |
| --- | --- | --- | --- | --- | --- |
| 0.762 m | 159 / 3 | 207 / 6 | 211 / 45 | 198 / 6 | 210 / 7 |
| 0.914 m | 133 / 0 | 155 / 0 | 208 / 81 | 137 / 0 | 165 / 0 |
| 1.0 m | 128 / 0 | 149 / 0 | 173 / 19 | 128 / 0 | 163 / 0 |

- The sag model gives the same order (false: 9 / 14 / 68 / 21 / 14 at 0.762 m; 0 / 0 / 112 / 0 / 0; 0 / 0 / 33 / 0 / 0).
- **Nearest at 1.0 m invents only when the lattice is turned**: 0 false spots in the two shifted positions, all 19
  (33 with sag) in the turned one, in all six cells. In a shifted position it finds what cubic finds (56 against
  58 of 76); its lead in the sums comes from the turned position (68 against 48), the same runs that hold its false
  spots.
- **Nearest at 0.76 and 0.91 m invents in every position.** Those sizes are finer than the grid, so nearest drops
  rows of the survey (one in 3.2 and one in 10.6); at 0.91 m the false spots' anchors sit at such a jump more often
  than chance.
- **The smooth methods' false spots** (S2) are at 0.762 m only, in four of the six cells (average in a fifth), and
  mostly near misses that bilinear makes too: every false spot of bilinear is also cubic's, and 84 of Lanczos's 85 (S1) are cubic's.
- Of nearest's 773 false spots under S1, 222 have nothing of the truth within 100 m (cubic: 10 of 77).
- **Cubic against bilinear**: 48 / 22 / 21 more true spots at the three sizes, 3 more false ones at 0.762 m, none
  above. The rule fixed before the runs (cubic's false spots at most one above bilinear's per cell and size) fails
  once: one cell, 0.762 m, sag (2 against 4).
- **Against the survey on its own grid** (nearest in a shifted position at 1.0 m as its stand-in): bilinear keeps
  88.8 % of its spots, cubic 94.0 %, Lanczos 95.7 %. That is the border study's result for bilinear and cubic.
- **Under the border study's matching rule**: nearest at 1.0 m is 100 / 100 / 86.9 % real in the three positions,
  cubic 100 %; at 0.914 m nearest 84–90 %, at 0.762 m 89–92 % (cubic 95–98 %). The Tatras, turned 4.4°, gave
  nearest 97–98 %: a gap the review could not close. Possible reasons, none shown: thousands of spots in alpine
  ground take an extra anchor into an existing spot, a handful of spots on mine benches cannot.
- **The angle of real surveys** against the UTM grid (the reviewer's estimate over the State Plane zones of the
  states with such files): median 1.1°, 30 % above 2°, at most 5.5°; Albers 1.6–9°. Most surveys of exactly 1.0 m
  are in UTM metres already (67 of 74), so they are shifted at most.
- **Lanczos and overshoot**: on a synthetic 30 m step turned 3°, Lanczos goes 1.3–2.0 m beyond the source's local
  range and cubic 0.9–1.2 m (bilinear and nearest 0); on a 70° wall 0.06–0.09 m. Its error against the truth is the
  smallest all the same.
- Weak: six cells, four of one kind; every cell under 30 true spots in the formula model, so one spot is 5–20 % of
  a cell; the sums count the same places up to 18 times; the surveys are simulated and smoothed.

### The larger sizes on the same cells (2026-11-24, reviewed)

Bilinear and cubic at 1.22 to 3.05 m: no false spot (S2) in any cell, model or position. Average: 1 at 1.22 m,
then 52, 145 and 470 at 1.52, 2 and 3.05 m (formula, the three positions summed). At 3.05 m bilinear and cubic
find 0 to 6 of 76 (118 with sag) true spots. At 0.91 and 1.0 m no smooth method has a false spot, average
included, so nothing in these cells could have shown a smooth method inventing at those sizes.

### The literature's methods, and a turn of 1° (2026-11-24, reviewed)

Round 4, on the same six cells, sizes, positions and settings: GDAL's cubic spline, scipy's interpolating splines
of order 3 and 5, ordinary kriging, and a fourth position turned 1° (at 1.0 m only, every method). 552 searches.
The reviewer recomputed every count from the exports; the checks of the rasters themselves could not be recomputed, the rasters being
gone: they are marked "not reviewed" where they stand.

Sums over the six cells and the three positions of the earlier round, true spots found (of 228 in the formula
model, of 354 with sag) and false spots (S2):

| Pixel, model | Bilinear | Cubic | Lanczos | Nearest | Cubic spline | Spline 3 | Spline 5 | Kriging |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.762 m, formula | 159 / 3 | 207 / 6 | 210 / 7 | 211 / 45 | 91 / 0 | 219 / 15 | 219 / 16 | 216 / 12 |
| 0.762 m, sag | 264 / 9 | 308 / 14 | 313 / 14 | 336 / 68 | 204 / 2 | 338 / 30 | 335 / 32 | 337 / 25 |
| 0.914 m, formula | 133 / 0 | 155 / 0 | 165 / 0 | 208 / 81 | 101 / 0 | 166 / 1 | 168 / 1 | 164 / 0 |
| 0.914 m, sag | 236 / 0 | 269 / 0 | 276 / 0 | 329 / 112 | 197 / 0 | 278 / 1 | 278 / 1 | 274 / 1 |
| 1.0 m, formula | 128 / 0 | 149 / 0 | 163 / 0 | 173 / 19 | 83 / 0 | 156 / 0 | 160 / 0 | 150 / 0 |
| 1.0 m, sag | 213 / 0 | 249 / 0 | 260 / 0 | 276 / 33 | 172 / 0 | 254 / 0 | 258 / 0 | 250 / 0 |

The position turned 1°, at 1.0 m (found of 76 and of 118; false S2 / S1):

| Model | Nearest | Bilinear | Cubic | Lanczos | Cubic spline | Spline 3 | Spline 5 | Kriging |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| formula | 60, 1 / 9 | 42, 0 / 0 | 55, 0 / 0 | 61, 0 / 0 | 26, 0 / 0 | 57, 0 / 0 | 59, 0 / 0 | 51, 0 / 0 |
| sag | 95, 1 / 6 | 73, 0 / 0 | 88, 0 / 0 | 91, 0 / 0 | 60, 0 / 0 | 90, 0 / 0 | 90, 0 / 0 | 87, 0 / 0 |

How a method was to be read against cubic was fixed before the searches. "Finds more": more true spots in all six
pairs (three positions, two models), and over the three positions at least 10 more of 228 in the formula model
and 15 more of 354 with sag. "Invents more": false spots (S2) above cubic's by more than one in any cell and size,
or by more than three in a size's sum. By that rule:

| Method | 0.762 m | 0.914 m | 1.0 m |
| --- | --- | --- | --- |
| Lanczos (read by the rule after its runs) | the same (+3 / +5) | the same (+10 / +7) | the same (+14 / +11; the sag margin of 15 is not met) |
| cubic spline | finds fewer (−116 / −104) | finds fewer (−54 / −72) | finds fewer (−66 / −77) |
| spline of order 3 | finds more (+12 / +30), invents more (S2 +9 / +16) | the same (+11 / +9) | the same (+7 / +5) |
| spline of order 5 | finds more (+12 / +27), invents more (+10 / +18) | the same (+13 / +9) | the same (+11 / +9) |
| kriging | the same (+9 / +29), invents more (+6 / +11) | the same (+9 / +5) | the same (+1 / +1) |

- **Nearest and the turn, at 1.0 m.** False spots (S2, formula + sag): 0 unturned, 1 + 1 at 1°, 19 + 33 at 3°.
  Under S1: 9 + 6 at 1°, all of them near misses, and 29 + 57 at 3°. Under the border study's looser rule all of
  nearest's spots at 1° are real (169 of 169), 86.9 % at 3°. At 1° nearest finds what Lanczos finds (60 and 61 of
  76) and 5 more than cubic.
- **Cubic spline** finds 27–56 % fewer spots than cubic and never invents more: it is a smoothing spline (its error
  against the truth is the largest of all methods, 0.53–0.91 m at the 99.9th percentile).
- **The splines and kriging at 0.762 m: the order or the sampling?** There the three find more and invent more
  than cubic, mostly in two cells. They sample single points, while GDAL's cubic and Lanczos widen their kernels at
  that ratio. The three invent about the same although their orders differ, GDAL's two kernels equal each other,
  and the excess shrinks with the ratio (large at 0.762 m, one spot at 0.914 m, none at 1.0 m): that points to the
  point sampling (the reviewer's estimate). Not settled: a point-sampling bilinear was searched only at 1.0 m; 36
  searches of it at 0.762 m would tell.
- **What the kriging was.** PyKrige 1.7.3's ordinary kriging system from the 16 nearest survey pixels, solved in
  batches (equal to PyKrige's own result to 3e-13 m at 2,000 positions, by the worker's check; the reviewer found
  the matrix, the neighbours and the variogram function the same in PyKrige's source). The variogram was fitted
  per survey at lags of 1 to 8 pixels; a power model won all 60 (exponent 1.60–1.84), with no nugget to speak of
  except in one survey. As a method that is an exact local interpolator close to a slightly softer cubic
  convolution (the reviewer's synthetic test: it overshoots a step like cubic and keeps a little less of fine
  detail). So "kriging equals cubic" holds for this one setting; it is no verdict on kriging in general or on Minh
  et al.'s setting, which is not known here. A raster of 2 million pixels took 16–27 s.
- **The path of the splines is right** where it can be compared: a point-sampling bilinear through it equals GDAL's
  exact bilinear to 0.03 mm at 1.0 m (not reviewed), and searched against the app's bilinear of the same survey it
  gives the same spots in 12 of 12 runs, lines differing by 0–4 (reviewed).
- **Overshoot at 1.0 m** (share of pixels outside the range of the 4 by 4 source pixels around them, largest
  excursion; not reviewed): cubic 0.16–0.61 %, up to 0.21 m; Lanczos 0.24–0.61 %, 0.30 m; spline 3 0.24–0.63 %,
  0.23 m; spline 5 0.27–0.89 %, 0.23 m; kriging 0.27–0.72 %, 0.30 m; cubic spline and bilinear none.
- **Error against the truth** (99.9th percentile; not reviewed): spline 5 and Lanczos 0.23–0.37 m; spline 3,
  kriging and cubic 0.24–0.43 m; bilinear 0.41–0.63 m; cubic spline 0.53–0.91 m.
- **Against the survey on its own grid**, unturned (the one position where that reference is the run's own
  survey): with sag, Lanczos and spline 5 keep 97.3 % of its spots, spline 3 and kriging 95.9 %, cubic 94.5 %,
  bilinear 86.3 %, cubic spline 58.9 %; in the formula model every smooth method but cubic spline keeps 40 of 43,
  so it does not separate them. The shares of the other positions were scored against the unturned survey and mix
  the method with the lattice (20–30 % of the difference is lattice against lattice, the reviewer's estimate):
  they are not used here.
- **What each would take in the app.** Lanczos and cubic spline: one more entry in `mosaic.RESAMPLINGS`. Cubic is
  in it. The splines: a read path of their own (exact positions, a prefilter over a footprint without empty
  pixels). Kriging: that path, a library the app does not have and a variogram fit per file.
- Weak, as before: six cells, four of one kind; under 30 true spots per cell in the formula model; the sums count
  the same places three times; the surveys are the 1 m truth averaged; one turned angle of 1° and one of 3°, the
  1° only at 1.0 m.

### A monotone cubic, and point sampling at 0.76 m (2026-11-26, reviewed)

The user's request ("Can you try Shape-preserving (monotone) cubic?"), on the bench of the two sections above: 120
searches of the monotone cubic (three sizes, three positions and the 1° turn at 1.0 m, both models, six cells) and
36 of a point-sampling bilinear at 0.762 m, the control the review of the round before had named. Every count
below was recomputed by the reviewer and is equal.

- **The method as measured**: PCHIP (Fritsch-Carlson) as a tensor product on the 4 by 4 survey pixels around a
  position, along the columns of each of the four rows first, then along the rows. It equals scipy's
  `RegularGridInterpolator(method="pchip")` to 2.3e-13 m, at random positions and at hard ones (the steepest
  pixels, slope sign changes, equal neighbours). The library's own call is too slow for a raster (about 281 s,
  an estimate), so the rasters were made by the same formula per point: about 2 s a raster against 1.2–1.6 s for
  the spline of order 3 (not reviewed; measured beside other work).
- **No overshoot**: not one pixel outside the range of the 2 by 2 survey pixels around its position.
- **Error against the truth** at 1.0 m, unturned: 99.9th percentile 0.26–0.41 m, at or under cubic's
  (0.26–0.43 m). Its largest error is above cubic's in three of the six cells: a few pixels where the survey's
  averaging cut a crest and a method that cannot leave the range of its neighbours cannot reach it (shown against
  the spline of order 3; for cubic by analogy).

True spots found, and false spots (S2), summed over the six cells and three positions (228 true spots in the
formula model, 354 with sag):

| Pixel, model | Bilinear | Cubic | Lanczos | Nearest | Spline 3 | Monotone cubic |
| --- | --- | --- | --- | --- | --- | --- |
| 0.762 m, formula | 159, 3 | 207, 6 | 210, 7 | 211, 45 | 219, 15 | 217, 11 |
| 0.762 m, sag | 264, 9 | 308, 14 | 313, 14 | 336, 68 | 338, 30 | 335, 21 |
| 0.914 m, formula | 133, 0 | 155, 0 | 165, 0 | 208, 81 | 166, 1 | 167, 0 |
| 0.914 m, sag | 236, 0 | 269, 0 | 276, 0 | 329, 112 | 278, 1 | 277, 0 |
| 1.0 m, formula | 128, 0 | 149, 0 | 163, 0 | 173, 19 | 156, 0 | 158, 0 |
| 1.0 m, sag | 213, 0 | 249, 0 | 260, 0 | 276, 33 | 254, 0 | 254, 0 |

- **Read against cubic by the rule fixed before round 4**: "the same as cubic" at 0.914 and 1.0 m (a few more
  true spots, no false one); at 0.762 m "finds more" and "invents more", both thin: the formula model's +10 is
  exactly the rule's margin, and of its +5 false spots one cell gives +3.
- **Turned 1° at 1.0 m**: 57 of 76 and 91 of 118 found, nothing false (cubic 55 and 88).
- **Against the spline of order 3** it finds the same and invents less at 0.762 m (11 and 21 against 15 and 30).
- Under the strict rule (S1) it has 111 false spots, 103 of them at 0.762 m and none at 1.0 m: 71 near misses,
  26 between two true spots, 14 with nothing within 100 m (cubic: 77, as 49, 18 and 10).
- **In the app** it would be a read path of its own beside the warp (exact positions, a footprint without empty
  pixels, the formula in numpy); no new dependency.

**Point sampling at 0.76 m.** GDAL widens its kernels when the survey's pixel is finer than the grid's
([Settings of the warp](#settings-of-the-warp)); the methods built outside GDAL sample single points. The control
sets the two apart (0.762 m; found and false S2 in the formula model / with sag; the false spots of the three
positions merged into distinct places within 25 m, the reviewer's count):

| Method at 0.762 m | Found | False | Distinct false places |
| --- | --- | --- | --- |
| Bilinear, GDAL's widened kernel (the app's) | 159 / 264 | 3 / 9 | 2 / 2 |
| Bilinear, single points | 201 / 310 | 7 / 15 | 3 / 4 |
| Cubic, GDAL's widened kernel | 207 / 308 | 6 / 14 | 3 / 3 |
| Spline of order 3, single points | 219 / 338 | 15 / 30 | 10 / 11 |
| Monotone cubic, single points | 217 / 335 | 11 / 21 | 6 / 8 |

- **Found**: sampling single points lifts bilinear by 42 and 46 true spots, to cubic's level; the higher order
  under the widened kernel lifts it by 48 and 44; both together by 60 and 74. Either cause alone gives nearly all
  of it.
- **False**: neither cause alone adds much (4 and 6; 3 and 5); together they add 12 and 21. The "invents more" of
  the splines and of kriging at 0.76 m comes from the two together.
- **Overshoot is not needed for it**: the monotone cubic has none and is above cubic and above the point-sampling
  bilinear; with overshoot absent the excess is about half the spline's (an estimate on small counts). Which
  property of the kernels makes the difference cannot be told.
- With sag one cell holds most of every method's false spots (12 of the point-sampling bilinear's 15, 12 of
  cubic's 14, 15 of the monotone cubic's 21, 18 of the spline's 30).
- **What this says about the tables above**: at 0.76 m the columns of bilinear, cubic and Lanczos are GDAL's
  widened kernels and the columns of the splines, kriging and the monotone cubic are point samplers: not like for
  like. At 0.91 m the widening is smaller (set apart in the next section). At 1.0 m there is none: the point-sampling
  bilinear equals GDAL's there (0.03 mm; the same spots in 12 of 12 runs). Nearest takes one pixel in either case.
  GDAL's cubic and Lanczos without the widening are in the next section.
- Weak, as before, and: nothing was measured between 0.762 and 0.914 m, where the monotone cubic's false spots
  go from 11 and 21 to none; the 1° turn only at 1.0 m; the simulated surveys are the 1 m truth resampled, so they
  hold no detail finer than 1 m, and what the widening does with real detail of a 0.76 m survey is not measured.

### GDAL's methods without the widened kernel (2026-11-26, reviewed)

The user's question after the section above ("So that means that presented billear results are not the best
ones? Does that appply to other methods as well?"). GDAL's bilinear, cubic and Lanczos through the app's own
path with the warp options `XSCALE=1` and `YSCALE=1`, at 0.762 and 0.914 m, three positions, both models, the six
cells: 216 searches. Every count was recomputed by the reviewer and is equal.

- **The options give the plain kernels at single points**: on a synthetic 0.762 m raster (one CRS, no turn, exact
  transform) GDAL's bilinear, cubic and Lanczos with the options equal a bilinear, a cubic convolution
  (a = −0.5, 4 by 4) and a normalised Lanczos (radius 3) written out by hand to 1e-11 (Lanczos: 99.9th percentile
  9e-12, 38 of 176,400 pixels above 1e-4 of a field of ±100, cause not looked into). Without the options all three
  differ from the plain kernels: the widening is on by default for all three. In the searches the bilinear with
  the options equals the point-sampling bilinear of the section above in every count.
- **At 1.0 m the options change nothing**: the raster is the same bit for bit (bilinear and cubic, unturned and
  turned 3°, two cells; Lanczos and the other cells not compared).

True spots found, and false spots (S2), summed over the six cells and three positions (228 true spots in the
formula model, 354 with sag); "widened" is GDAL's default, as in every table above:

| Pixel, model | Bilinear widened | single points | Cubic widened | single points | Lanczos widened | single points |
| --- | --- | --- | --- | --- | --- | --- |
| 0.762 m, formula | 159, 3 | 201, 7 | 207, 6 | 217, 12 | 210, 7 | 218, 13 |
| 0.762 m, sag | 264, 9 | 310, 15 | 308, 14 | 337, 27 | 313, 14 | 337, 28 |
| 0.914 m, formula | 133, 0 | 141, 0 | 155, 0 | 164, 0 | 165, 0 | 168, 1 |
| 0.914 m, sag | 236, 0 | 241, 0 | 269, 0 | 276, 1 | 276, 0 | 279, 0 |

- **At 0.76 m, by the rule fixed before round 4**: bilinear at single points finds more and invents more than
  the widened bilinear, and reads "the same" as the widened cubic (201 and 310 against 207 and 308; false 7 and
  15 against 6 and 14). Cubic at single points finds more than the widened cubic (the formula model's +10 is
  exactly the margin) and invents more: its false spots double. Lanczos at single points reads "the same" in
  found as the widened Lanczos (+8, two under the margin) and invents more.
- **At 0.91 m** every method at single points reads "the same" as its widened form: 3 to 9 more true spots, no
  or one false spot. Cubic's gain over bilinear is unchanged (+22 and +33 widened, +23 and +35 at single points).
- **With every method at single points, at 0.76 m** (found; false):

  | | Bilinear | Monotone cubic | Cubic | Lanczos | Spline 3 |
  | --- | --- | --- | --- | --- | --- |
  | Formula | 201; 7 | 217; 11 | 217; 12 | 218; 13 | 219; 15 |
  | Sag | 310; 15 | 335; 21 | 337; 27 | 337; 28 | 338; 30 |

  In found, bilinear stands apart and the other four read the same. In false, bilinear has the fewest and the
  monotone cubic is next (each of the three others invents more than it by the rule, cubic only by the sag sum);
  cubic, Lanczos and the spline cannot be told apart. Cubic's gain over bilinear is smaller in found than between
  the widened forms (+16 and +27 against +48 and +44) and comes with more false spots (+5 and +12).
- **The false spots sit in few cells**: with sag 61–89 % of every method's are in one cell; in the formula model
  the rise from widened to single points sits mostly in a second one. Without those two cells the false spots
  are 4 to 6 per method in the formula model (no order left) and 0 for bilinear against 2 to 4 with sag.
- **Error against the truth** at 0.76 m: single points are nearer the truth for bilinear (99.9th percentile lower
  by 0.10–0.18 m) and for cubic (within 0.03 m), farther for Lanczos (by 0.04–0.05 m). This cannot rank the forms
  for real lidar: the simulated survey is the 1 m truth averaged onto 0.76 m pixels, it holds no detail finer than
  1 m, so a kernel that smooths at the 1 m scale is rewarded by how the bench is built.
- **In the app** the two options would go into `mosaic.WARP_KWARGS` (which feeds every warp) or be set per method
  or layer. Not measured: what they do to average and nearest, to sources coarser than the grid, to real
  sub-metre files, and which pinned results would move.
- **The surveys rebuilt for this round are the ones the earlier rounds searched**: the widened cubic rebuilt at
  0.762 and 0.914 m (unturned and turned 3°, two cells) and searched again gives round 3's exports byte for byte,
  8 of 8 (the worker's check, the checksums compared a second time by the session; no reviewer). Lanczos and the
  other four cells were not searched again.
- Weak, as before.

## Decisions

| Date | Decision | By |
| --- | --- | --- |
| 2026-10-26 | No cache of resampled tiles | the roadmap, "Resampling to the working resolution" |
| 2026-11-05 | A neighbour's data at the grid's own pixel size (0.75 to 1.1 of it) by nearest; finer averaged, coarser bilinear | the user, from the border study |
| 2026-11-05 | Slovakia's averaged 2 m and 5 m tiles go only to a grid of their own CRS | the user |
| 2026-11-24 | The OPR wave reads surveys of 1 m or finer, by the file's own pixel; coarser surveys are not read | the user ("(a) 1 m or finer") |
| 2026-11-24 | Pixels from data coarser than 1 m are to be shown on the map's "Coarser terrain" layer and in each line's metres, with the pixel size in the legend; built with the 3 m DEM, not with the OPR wave | the user ("On the map and per line") |
| 2026-11-26 | USGS lidar files of 0.75 to 1.0 m that are not on the 1 m grid come into a search by cubic (not built yet) | the user ("Cubic (Recommended)"), after the comparisons of 2026-11-24 to 26 |
| 2026-11-26 | GDAL's widening of the kernel stays for those files (the warp's default; no `XSCALE` or `YSCALE` set) | the user ("Keep the widening (Recommended)") |
| 2026-11-26 | Cubic is for those files of the USA only; a change of the general rule (every reprojected layer at about the grid's pixel size, the border rule with it) is a point of docs/roadmap.md, "Resampling to the working resolution", to be evaluated | the user ("for this session 1 - save a roadmap point to evalute global change") |

Planned for the OPR wave and not a decision of the user's: the pixel of a CRS in feet counted in metres, so that
files finer than 0.75 m are averaged as the rule says.

## Open questions

- Closed on 2026-11-26 ([Decisions](#decisions)): the method for surveys of 0.75 to 1.0 m that are not on the
  grid. The user chose cubic on 2026-11-24, then asked for nearest, the literature's methods and a monotone cubic
  to be compared and whether the widened kernel hid something, and with all four comparisons in chose cubic
  again, for the USA's files only, with GDAL's widening kept.
- **Cubic as the general rule** (every reprojected layer at about the grid's pixel size, and nearest at borders
  with it): a point of docs/roadmap.md, "Resampling to the working resolution", with what has to be evaluated
  first (the results it moves, the border study again, the widening, real sub-metre lidar).
- **If the widening were turned off in the app: for which data.** It would move every result where a source finer
  than the grid is interpolated and not averaged (0.75 to 1.0 of the grid's pixel); what the options do to average
  and nearest and to sources coarser than the grid is not measured.
- **Real sub-metre lidar**: every survey of these rounds is 1 m data resampled, without detail finer than 1 m. What
  the widening, or its absence, does with the real detail of a 0.76 m survey is not measured.
- **Sizes between 0.76 and 0.91 m**: the false spots of the point samplers go from some to none between the two;
  where is not measured.
- **How 3 m data enter a 1 m search** (the 1/9″ DEM, the last step of the USA's order): resampled they find almost
  nothing away from cliffs, on their own grid they invent on some ground. Not decided, not planned.
- **The warp's error threshold**: whether the exact transform changes a search's results, and what it costs in time.
- **Why nearest invents at 3° in the check cells and hardly at 4.4° in the Tatras.**
- **A geographic raster's east-west pixel** in `src_pixel_m` (the roadmap's entry).

## Sources

Read in full: [gdalwarp](https://gdal.org/en/stable/programs/gdalwarp.html), [GDAL's warp
API](https://gdal.org/en/stable/api/gdalwarp_cpp.html), [rasterio's resampling
methods](https://rasterio.readthedocs.io/en/stable/api/rasterio.enums.html).

Abstracts or search summaries only:
[USGS, elevation-derived hydrography specification](https://www.usgs.gov/ngp-standards-and-specifications/elevation-derived-hydrography-data-acquisition-specifications-13);
[USDA NRCS, Raster Mastery, issue 2](https://www.nrcs.usda.gov/sites/default/files/2023-01/rastermastery-issue2.pdf)
(not opened);
[Esri, Properly reprojecting elevation rasters](https://esri.com/about/newsroom/?p=179912) (not opened);
[Kidner 2003](https://informahealthcare.com/doi/abs/10.1080/0143116031000086835);
[Rees 2000](https://data.zhenzhi.com/details/1/896437165) and
[Shi et al. 2005](https://data.zhenzhi.com/details/1/880295406) (secondary copies of the abstracts);
[University of Waterloo, DEM-derived topographic attributes](https://uwaterloo.ca/geospatial-intelligence/sites/default/files/uploads/files/a_study_on_dem-derived_primary_topographic_attributes_for_hydrologic_applications_sensitivity_to_elevation_data_resolution.pdf);
[Minh et al. 2024, Remote Sensing 16(5) 819](https://mdpi.com/2072-4292/16/5/819);
[Takagi 1998](https://www.infra.kochi-tech.ac.jp/takagi/Papers/ISPRS98.pdf);
[Lanczos resampling](https://en.wikipedia.org/wiki/Lanczos_resampling).

This project's measurements: [performance.md](performance.md) ("The resampling of a neighbour's data") and
[roadmap.md](roadmap.md) ("A slope threshold for the resolution", "Resampling to the working resolution") for what
is in the repository; the studies of 2026-11-24 are in the task's private folder
(`local/opr-usa-2026-11-22/`: `gate0c`, `gate0e`, `gate0f`), not in the repository.
