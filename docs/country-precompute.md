# A country-wide layer of highline counts: feasibility for Slovakia, Poland, Switzerland and Utah

Report of 2026-11-02 on the branch `country-precompute` (from `main` 221dd10, which holds the faster
line search of `line-order` and the 24 sources of `new-sources`). The numbers are measured on this PC
and extrapolated as described in [section 7](#7-method-samples-and-uncertainty); they are rough. The
data behind them is in [country-precompute/](country-precompute/): the inputs, both machines'
benchmarks, the relief of the countries and the samples' cells, the estimate, and the research notes
with quotes and links. The measuring tool is `tools/perf_country.py`.

## Summary

**A country can be computed offline on either machine, but not with today's search as it is.** The
download decides the calendar in Poland; the long lines in high mountains decide the computing and,
above all, the memory.

| Country | DSM | Download | Cache | Download time | 30-2000 m (S 1 m, M 2 m) | 30-5000 m (+ L 5 m) | 2000-5000 m (L 5 m) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Slovakia | yes | 0.14 TB | 0.14 TB | 5 min (a local copy) | 1.6 h (1.1 h-2.0 h) / 4.3 h (2.9 h-5.3 h) | 1.8 h (1.3 h-2.2 h) / 4.9 h (3.4 h-5.9 h) | 13 min / 32 min |
| Slovakia | no | 0.06 TB | 0.06 TB | 2 min (a local copy) | 1.6 h (1.0 h-1.9 h) / 4.2 h (2.8 h-5.2 h) | 1.8 h (1.2 h-2.1 h) / 4.7 h (3.2 h-5.7 h) | 12 min / 29 min |
| Poland | yes | 7.33 TB | 1.75 TB | 14.4 days | 5.1 h / 14 h | 6.5 h / 17 h | 1.3 h / 3.2 h |
| Poland | no | 3.40 TB | 0.81 TB | 6.7 days | 4.7 h / 13 h | 5.9 h / 16 h | 1.2 h / 2.9 h |
| Switzerland | yes | 1.39 TB | 1.39 TB | 1.7 days | 3.6 d (39 h-5.0 d) / 9.3 d (4.3 d-13 d) | 3.7 d (41 h-5.2 d) / 9.7 d (4.5 d-13 d) | 3.7 h (2.1 h-5.6 h) / 9.6 h (5.4 h-15 h) |
| Switzerland | no | 0.73 TB | 0.73 TB | 0.9 days | 3.6 d (39 h-5.0 d) / 9.3 d (4.3 d-13 d) | 3.7 d (41 h-5.2 d) / 9.7 d (4.5 d-13 d) | 3.7 h (2.1 h-5.6 h) / 9.6 h (5.4 h-15 h) |
| Utah | none exists | 0.66 TB | 0.40 TB | 1.1 days | 24 h (14 h-31 h) / 2.7 d (36 h-3.3 d) | 26 h (15 h-33 h) / 2.8 d (39 h-3.6 d) | 1.8 h (1.1 h-2.0 h) / 4.7 h (2.8 h-5.3 h) |

Computing: 9900X / 5650G, mid (bootstrap range of the places). "-": not measured yet.

- **Slovakia, the first step** (the user's choice of 2026-11-02): our own 2 km tiles of ÚGKK SR's 1 m
  terrain and surface models are on this PC (133 GB), so nothing is downloaded and the pilot tests the
  counting, the spots, the driver and the layer on a whole country at once; computing S, M and L
  (30-5000 m) takes about 1.8 h on the 9900X and 4.9 h on the 5650G (30-2000 m: 1.6 h and 4.3 h), and
  the cache holds 0.14 TB, a copy of the mirror.
- **Poland**: the download takes two weeks for terrain and surface models at the 5.9 MB/s that
  geoportal.gov.pl gave us (one week for the terrain model alone); computing then takes hours,
  because nine tenths of Poland are flat and the grids, not the lines, take the time.
- **Switzerland**: 1.7 days to download at swisstopo's request rate; the M band (300-2000 m) at 2 m
  takes 3.6 days on the 9900X (1.6-5.0 by the bootstrap) and 9 days on the 5650G, because the Alps
  hold about 190 billion such lines (10 to 23 million per km² in the steepest strata).
- **Utah**: a day to download, a day to compute S and M at 1 and 2 m on the 9900X (2.7 days on the 5650G);
  the canyons of the Colorado Plateau are as dense as the Alps.
- **The L band (2-5 km)**: at 5 m it adds 3-27 % to a country's time (13 min for Slovakia, 1.3 h
  for Poland, 1.8 h for Utah, 3.7 h for Switzerland on the 9900X, about 2.5 times as long on the
  5650G), so 30-5000 m costs about what 30-2000 m does. Its lines are as combinatorial as the M band's: up to 0.6 million
  per km² at 5 m, 102 million in Lauterbrunnen's valley (293 km²). Canyonlands at 5 m is scaled from
  10 m for now (section 7).
- **What has to be built first** (section 6.5): a counting mode of the line search (each evaluated
  part of lines goes into the counts and is dropped: today a tile of the Alps' steepest terrain at 2 m
  would hold 260 GB of lines), a spot that can be counted on the fly, a country driver (a fixed tile
  grid, K tiles at once, resume), and pretension by length in the search itself.
- **Resolution** (section 1): S at 1 m, M at 2 m, L at 5 m. A 2 m grid keeps the ranking of the S
  band's cells (Spearman 0.96-0.98) with half its lines; 5 m is a different search for the M band
  (4 % of the lines, 15 % of the cells with a spot lost) and needs anchors from 45° instead of 60°.
- **The counts themselves**: in big-wall terrain every anchor on one wall pairs with thousands on
  the other, so a raw line count measures the walls more than the highlines. The layer needs a
  coarser spot (anchor clusters) and its filters (prominence, height, wall angle) as floors.
- **Legality** (section 5): allowed for all three; GUGiK's NMT and NMPT need no request, swisstopo
  asks for contact before a load above its limits (36 a minute stays below them; the e-mail is in
  `local/mail-drafts.md`), USGS asks for a description of the processing. Filling gaps from FABDEM
  binds the project to non-commercial use.

## The idea and what was decided

A country is searched offline in tiles of a fixed size. A tile does not keep its lines: it keeps the
**number of lines and of spots** per cell (for example 1 km), split into the bins of the filters, and
the cells are summed into larger ones (2, 4, 8 km...) without computing anything again. The app
shows the cells as a map layer that can be filtered. Line positions and profiles are not stored; a
user who wants the lines of a cell runs an ordinary search there.

Decided with the user (2026-11-01/02):

| Topic | Decision |
| --- | --- |
| Countries | Poland (GUGiK NMT/NMPT), Switzerland with Liechtenstein (swisstopo), Utah (USGS 3DEP 1 m, no DSM); Slovakia (ÚGKK SR's DMR 5.0 / DMP 1.0 from the local copy of our tiles) added on 2026-11-02 as the first step |
| Length variants | 30-2000 m, 30-5000 m, 2000-5000 m, computed as three bands: **S** 30-300 m, **M** 300-2000 m, **L** 2000-5000 m |
| Clearance model | the formula below 300 m; the sag estimator from 300 m, its pretension growing with the length (T(L)): 300 m 2.5 kN, 1500 m 6 kN, 5000 m 15 kN, linear between |
| Webbings | Silk 99, Axiom MK2 (Balance Community), Tiger (Slackhouse), each as main and backup: the main's weight plus the backup's (5-7 % longer), the main's stretch at 10 kN, no hardware: 41.0 g/m and 2.1 %, 66.2 g/m and 1.8 %, 61.7 g/m and 2.8 %. Silk 99 sags least at every length from 600 m, so runs use it and the others become filters |
| Fixed limits | the anchors' height difference at most 5 % and 50 m; anchors on pixels of 60° or steeper on 1-2 m grids (coarser grids: section 1.3) |
| Filters of the layer | length, pretension and webbing, prominence and drop, wall angle, over trees or buildings, over water, clearance and the webbing's height |
| Counted | lines and spots |
| Surface model (DSM) | both variants: with it and without it |
| Where it is shown | locally first, later on the public site |
| Data | kept (a NAS or another disk); the internet link about 1 Gb/s |
| Machines | this PC (Ryzen 9 9900X, 12 cores, 62 GB, about 50 GB for the task) and a Ryzen 5 PRO 5650G (6 cores, 64 GB, 40-50 GB for the task, Unraid, 1.6 TB free on its SSD) |
| Precision | rough (±50 %), up to about 20 GB of new samples |

## Bottlenecks and the roadmap

In the order they limit a country run, with the [roadmap](roadmap.md) items that address them and
what is missing from it.

| # | Bottleneck | Measured | Roadmap | Missing |
| --- | --- | --- | --- | --- |
| 1 | **Lines in big-wall terrain (M band)**: millions of lines per km² that today's search keeps in memory (450 B each) and groups on one core | Lauterbrunnen at 2 m: 7.2 million lines per km², 94 min of grouping for 50 km², its run lost while saving; Zion at 2 m out of memory; Zion at 5 m 0.96 million per km² | "Large runs" (a)-(c) shrink what a line costs in a saved run, not in a search; "Prominent lines" (a minimum prominence cut the lines 40-fold at Montserrat) | A counting mode of the line search and a spot counted on the fly (6.2, 6.5): the precondition of the M band at 2 m and of anything at 1 m |
| 2 | **Downloading Poland** | 5.9 MB/s with 8 connections to opendata.geoportal.gov.pl, 1.2 MB/s with one: 14.4 days for NMT and NMPT (7.3 TB), 6.7 for NMT (3.4 TB) | Sheets instead of WCS (done), host slots (done) | A local copy kept as a mirror (as for Slovakia) so that a second run downloads nothing; GUGiK's 5 m grid for the L band; a courtesy e-mail |
| 3 | **swisstopo's rate and its DSM** | 36 requests a minute (FSDI: 40) for two layers of 41,445 tiles: 1.7 days; the 0.5 m DSM is 0.66 TB, the 2 m DTM 0.05 TB | Host rates (done, 8832023); "Obstacles lowered by averaging the DSM" | The obstacle layer (DSM − DTM at the data's resolution, its maximum per grid pixel): 1 % of the DSM's size (6.5) |
| 4 | **Steps 1-2 on one core** (stitching, filling, anchors, prominence) | Most of the time of the S band and of flat country: in Poland 13-25 core-hours of grids per band against at most an hour of pair search | "Tiles of a large area in parallel processes", deferred for the public site (2026-10-31) | A country driver running K tiles at once (6.1, 6.5); one step 1 for several bands |
| 5 | **Tile memory** for long lines on fine grids | An L tile of 10 km at 2 m holds about 10 GB of grids, at 1 m 42 GB | - | Coarser grids for longer bands (section 1) |
| 6 | **Disk** | Caches with the DSM: Poland 1.75 TB, Switzerland 1.39 TB, Utah 0.40 TB | - | LERC with 5 mm precision: 48 % (NMT) and 40 % (NMPT) less for the Polish sheets; the obstacle layer for Switzerland |
| 7 | **3DEP's 1 m windows for coarse bands** | A 5 m band reads the same 1 m windows as a 1 m one | - | The COGs' overviews: 5.4 times fewer bytes at 2 m, 16 at 4 m, 44 at 8 m (measured in Zion) |
| 8 | **Quality of coarse grids** | S at 2 m keeps the ranking of the cells; M at 5 m is a different search (section 1) | "Interpolating to a finer grid lowers the number of lines" (to check) | - |

The pilot's runs were profiled on 2026-11-04 (docs/performance.md, "Round 4": the wall of a run is
its heaviest tile at 3 threads, step 1 is 40-56 % of the tile seconds and all of an empty tile's, the
border gaps of inland tiles, 60 B/px per worker); its stages 1-3 address bottleneck 4 and the memory
per worker. The line search of `line-order` (in `main` since 5026838: its CPU −51-78 %) is in every
number of this report. Its order of tests was measured to be close to the best, so more speed has to come from
doing less (bands, grids, counting), not from the kernels.

## 1. Resolution

### 1.1 What the sources offer

The terrain models of the catalogue (README, "Data sources") at their native resolution:

| Resolution | Sources |
| --- | --- |
| 0.4-1 m | **Poland** (NMT 1 m, partly 0.5 m; NMPT 0.5-1 m on about 85 % of the country), **Switzerland and Liechtenstein** (swissALTI3D 0.5 m, also published at 2 m; swissSURFACE3D Raster 0.5 m), **the USA** (3DEP 1 m: in Utah at 82 of 92 points of a 0.5° lattice, about 89 %; elsewhere the 1/3″ DEM, about 10 m), Slovakia, Malta, Austria, Wales, England, Hesse, Mecklenburg-Vorpommern, Saxony-Anhalt, Lower Saxony, Luxembourg (0.5 m), Denmark (0.4 m) |
| 2-2.5 m | Finland (2 m), South Tyrol (2.5 m) |
| 5 m | Spain and the Canary Islands, Alaska (IfSAR); Poland's photogrammetric 5 m grid (GUGiK, "Siatka 5m", not in the catalogue) |
| 10-30 m | the USGS 1/3″ DEM, FABDEM, Copernicus DEM, NASADEM |

"1 m everywhere" is possible in the three countries of this report, not in Finland, South Tyrol or
Spain; a layer meant to grow to them needs bands that work at 2-5 m anyway. Utah has no surface model
(3DEP publishes none), so its counts never know trees or buildings.

### 1.2 What a coarser grid changes

`compare` counts the lines and spots per 1 km cell of the same search at two resolutions (the same
area, parameters and data; spots are today's groups): the ratio of the totals, the Spearman
correlation of the spots per cell (over the cells with a line in either run) and the share of the
finer run's cells with a spot that the coarser run loses.

| Band | Place | Grids | Lines | Spots | Spots per cell: ρ | Cells lost |
| --- | --- | --- | --- | --- | --- | --- |
| S | Tatras | 2 m / 1 m | 0.76 | 1.46 | 0.96 | 8 % |
| S | Tatras | 5 m / 1 m | 0.30 | 1.53 | 0.87 | 0 % |
| S | Lauterbrunnen | 2 m / 1 m | 0.44 | 1.25 | 0.98 | 0 % |
| S | Lauterbrunnen | 5 m / 1 m | 0.11 | 0.81 | 0.96 | 7 % |
| S | Zion | 2 m / 1 m | 0.60 | 1.38 | 0.98 | 0 % |
| S | Zion | 5 m / 1 m | 0.15 | 1.66 | 0.93 | 0 % |
| M | Tatras | 5 m / 2 m | 0.038 | 0.27 | 0.95 | 15 % |
| L | Lauterbrunnen valley | 10 m / 5 m | 0.067 | 0.32 | 0.97 | 8 % |

- **The S band at 2 m** keeps 44-76 % of the lines and the ranking of the cells (ρ 0.96-0.98); it
  has more spots, because fewer lines break today's greedy groups into more pieces. The shortest
  lines suffer most: 30-60 m keep 43-81 % at 2 m and 8-23 % at 5 m.
- **The S band at 5 m** keeps 11-30 % of the lines; the cells still rank alike (ρ 0.87-0.96), but
  lines of 30-60 m are mostly gone, as README warns for Spain's 5 m data.
- **The M band at 5 m** keeps 4 % of the lines of 2 m and 27 % of the spots, and 15 % of the cells
  with a spot at 2 m have none at 5 m: at 5 m a 60° anchor needs a wall of about 17 m or more (the
  Horn gradient spans 10 m), so many rims of 2 m disappear. 5 m is a different search, not a thinner
  one.
- **The M band at 1 m was not measured**: at 2 m the Lauterbrunnen sample produced 363 million lines
  in 50 km² (94 minutes of grouping on one core; its run was lost while saving) and Zion ran out of
  memory. 1 m holds four times the pixels and, judging by the S band, about twice the lines; it is
  out of reach until lines are counted without being kept.
- **Which grid is right?** None is the truth: finer grids see narrower rims and more of the
  clearance's detail, coarser ones smooth both. For a count layer the cells must rank alike, and the
  counts must be labelled with the grid they come from.

### 1.3 The slope threshold on coarse grids

Anchors are pixels of at least 60° (the user's choice for 1 and 2 m). On 2 m grids 45° adds little;
on 5 m grids it adds a lot:

| Place | Grid | Lines 45° / 60° | Spots | ρ (spots per cell) |
| --- | --- | --- | --- | --- |
| Jura, S | 2 m | 1.24 | 1.17 | 0.96 |
| Lauterbrunnen, S | 2 m | 1.08 | 1.03 | 1.00 |
| Zion, S | 2 m | 1.02 | 1.01 | - |
| Lauterbrunnen, M | 5 m | 4.95 | 3.01 | 0.96 |

At 5 m the Horn gradient averages a wall over 10 m, so a 60° pixel needs a wall of about 17 m; with
45° the 5 m grid finds 29 % of the lines of the 2 m grid at Lauterbrunnen instead of 6 %. For bands
on 5 m grids the threshold should be 45° (50° is queued, not measured yet).

### 1.4 Recommendation

- **S (30-300 m) at 1 m.** The data is 1 m anyway (Poland, Utah), or the 0.5 m files cost no more
  requests than the 2 m ones (Switzerland: the same 41,445 files, request-limited); the computing is
  hours. 2 m is the fallback where 1 m data is missing (ρ ≥ 0.96).
- **M (300-2000 m) at 2 m**, with the counting mode. Without it, 5 m with 45° anchors and small
  tiles is the only M band today's code can hold, and it is a coarser search.
- **L (2000-5000 m) at 5 m** (10 m keeps 7 % of its lines and a third of its spots, though the cells rank alike (ρ 0.97);
  5 m costs minutes to hours a country, so there is no reason to go coarser).
- That is the strategy "split 1/2/5 m" of the tables below; "split 2/5/10 m" is what runs in hours
  but sees much less.

## 2. Data size

Per km², from what the app downloads and caches today (orthophotos left out):

| Country | Layer | Published as | Download MB/km² | Cache MB/km² | How it was measured |
| --- | --- | --- | --- | --- | --- |
| Poland | NMT (DTM) 1 m, partly 0.5 m | ASCII sheets (`.asc`, some `.xyz.zip`), cached as GeoTIFF | 10.9 | 2.6 | the sheet index of 12 tiles of 0.25° spread over the country (sheets, their resolution and size), the cache's GeoTIFFs |
| Poland | NMPT (DSM) 0.5-1 m, about 85 % of the country | ASCII sheets | 12.6 | 3.0 | as above |
| Switzerland | swissALTI3D 0.5 m (grids finer than 2 m) | COG per 1 km tile, kept as it is | 17.6 | 17.6 | the cache (swisstopo: "770 GB / full coverage") |
| Switzerland | swissALTI3D 2 m (grids of 2 m and coarser) | COG per 1 km tile | 1.24 | 1.24 | the cache ("44 GB / full coverage") |
| Switzerland | swissSURFACE3D Raster 0.5 m (no coarser version) | COG per 1 km tile | 15.9 | 15.9 | the cache ("335 GB / halbe Schweiz") |
| Slovakia | DMR 5.0 (DTM) 1 m | our 2 km COGs (LERC, 5 mm) on this PC, copied into the cache with their sha256 | 1.26 | 1.26 | the mirror: 12,826 tiles, 64.6 GB |
| Slovakia | DMP 1.0 (DSM) 1 m | as above | 1.52 | 1.52 | the mirror: 12,826 tiles, 77.9 GB |
| Utah | 3DEP 1 m DEM (about 89 % of the state) | 1 km blocks read from 10 km COGs | 3.1 | 1.9 | the internal tiles a 1 km block touches, from the headers of the 8 files of the samples: 1.0-6.8 MB per block (the files hold 0.5-3.5 MB per km²); GDAL may fetch more when it merges ranges |

For each country, by the finest grid of a strategy and with or without the DSM:

| Country | Grids of | DSM | Download | Cache | Download time |
| --- | --- | --- | --- | --- | --- |
| Slovakia | 1 m and finer | yes | 0.14 TB | 0.14 TB | 5 min (a local copy) |
| Slovakia | 1 m and finer | no | 0.06 TB | 0.06 TB | 2 min (a local copy) |
| Poland | 1 m and finer | yes | 7.33 TB | 1.75 TB | 14.4 days |
| Poland | 1 m and finer | no | 3.40 TB | 0.81 TB | 6.7 days |
| Switzerland | 1 m and finer | yes | 1.39 TB | 1.39 TB | 1.7 days |
| Switzerland | 1 m and finer | no | 0.73 TB | 0.73 TB | 0.9 days |
| Switzerland | 2 m and coarser | yes | 0.71 TB | 0.71 TB | 1.7 days |
| Switzerland | 2 m and coarser | no | 0.05 TB | 0.05 TB | 0.9 days |
| Utah | 1 m and finer | none exists | 0.66 TB | 0.40 TB | 1.1 days |

- **Poland's ASCII sheets** are four times larger than the GeoTIFFs the app keeps: the transfer, not
  the disk, costs. NMPT is about as large as NMT again.
- **Switzerland's DSM** exists only at 0.5 m, so any run with trees and buildings downloads 0.66 TB,
  even on a 5 m grid; without it a run of 2 m or coarser needs 0.05 TB (the 2 m DTM). An obstacle
  layer made from the DSM once (DSM − DTM, its maximum per 2 m pixel: 1.8 MB for 12 tiles against
  about 190 MB of their DSM) keeps what the DSM is used for at 1 % of the size.
- **Utah** has no DSM. The COGs carry overviews: their 2 m level fetches 5.4 times fewer bytes than
  1 m, the 4 m level 16 times, the 8 m level 44 times (one Zion file, a window of 2 × 2 km).
- **Disk savings**: the Polish sheets re-encoded as LERC (5 mm) take 48 % less (NMT) and 40 % less
  (NMPT) than the cache's DEFLATE GeoTIFFs (12 sheets each); lossless DEFLATE with the floating-point
  predictor gains nothing over them.
- **Keeping everything**, as decided: 3.5 TB of caches for the three countries with the DSM (1.75 +
  1.39 + 0.40), 1.9 TB without. Prepared grids (6.4) add about 2 MB per km² at 2 m uncompressed
  (0.7 TB for Poland), less with LERC.

### Every source of the catalogue (2026-11-04)

The data of every main source of `main` (037862e) for the layer's bands (S at 1 m, M at 2 m, L at 5 m: the finest
data a source gives for 1 m), the gap fillers left out (FABDEM and Copernicus at the borders, RGE ALTI, `canada_2m`,
`usgs10m`, `nz8m`, IslandsDEM, DEM-H). Rough: ±50 %. The link is 1 Gb/s, the host slots and rates are the app's.
How it was estimated:
- **MB/km² cached**: samples of the real cache, bytes over the km² with data (`cache_density.py` in
  `local/data-volume-2026-11-03/`).
- **MB/km² downloaded**: the report's measurements (Poland, Switzerland, Slovakia, Utah), the Metalinks' exact
  sizes (Bavaria, Rhineland-Palatinate), the window measurements of 2026-11-04 (Austria, Canada), else the formats
  and sizes the catalogue's comments give (ASCII grids, XYZ text, uncompressed WCS answers, windows of COGs at
  their file's density times the tiles a block touches).
- **Time per host**: max(requests / rate, bytes / bandwidth). The rate is the one the app reached in the cache's
  download bursts (`fetch_rates.py`), the report's measurement, or the slots x 0.6 / the seconds a tile takes in the
  catalogue's comments (0.6: Poland's 8 connections gave 4.9 times one). A country's time is its hosts one after
  another; a continent's and the total, all hosts at once: the slowest host, unless the link is slower.

| Country | km² with data (thousands) | Download, terrain (TB) | Download, with the surface (TB) | Cache, terrain / with the surface (TB) | Download time, terrain | With the surface | Basis |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Poland | 313 | 3.41 | 6.76 | 0.81 / 1.61 | 6.7 d | 14.4 d | M |
| Germany (13 Länder; no Hamburg, Bremen) | 343 | 1.62 | 5.59 | 0.77 / 1.55 | 1.4 d | 2.5 d | A, E, F, O |
| France | 535 | 1.50 | 3.00 | 1.01 / 2.15 | 3.9 d | 7.8 d | O |
| Norway (with Svalbard, Jan Mayen: ArcticDEM) | 385 | 1.36 | 2.65 | 0.72 / 1.53 | 1.1 d | 2.0 d | A, F |
| United Kingdom (England, Wales, ~7.5 % of Scotland) | 156 | 0.73 | 1.46 | 0.32 / 0.67 | 7.8 h | 15.5 h | F, O |
| Switzerland, Liechtenstein | 41 | 0.78 | 1.44 | 0.78 / 1.44 | 1.7 d | 2.5 d | M |
| Austria | 84 | 0.46 | 0.92 | 0.15 / 0.33 | 11.6 h | 23.3 h | M |
| Slovenia (no surface model) | 20 | 0.53 | 0.53 | 0.04 | 6.1 h | 6.1 h | F |
| Italy (South Tyrol at 2.5 m, Trento) | 14 | 0.18 | 0.35 | 0.04 / 0.09 | 2.1 h | 4.1 h | F, O |
| Denmark | 43 | 0.17 | 0.34 | 0.10 / 0.21 | 1.2 h | 2.5 h | F |
| Spain (5 m, with the Canary Islands) | 506 | 0.16 | 0.32 | 0.04 / 0.09 | 5.9 h | 11.7 h | A |
| Finland (no surface model) | 338 | 0.29 | 0.29 | 0.17 | 2.4 d | 2.4 d | O |
| Czechia (2 m) | 79 | 0.07 | 0.15 | 0.04 / 0.09 | 2.3 h | 4.6 h | F |
| Slovakia (the local mirror) | 49 | 0.06 | 0.14 | 0.06 / 0.14 | 2 min | 5 min | M |
| Iceland (ArcticDEM) | 103 | 0.10 | 0.10 | 0.03 | 3.4 h | 3.4 h | A |
| Luxembourg | 3 | 0.03 | 0.06 | 0.02 / 0.04 | 54 min | 1.8 h | O |
| Malta | 0.3 | <0.01 | <0.01 | <0.01 | 1 min | 2 min | O |
| **Europe** | **3,012** | **11.5** | **24.1** | **5.1 / 10.2** | **6.7 d** | **14.4 d** | |
| Canada (lidar, ~1.6 M km² assumed; Nunavut: ArcticDEM) | 3,693 | 17.0 | 31.9 | 4.3 / 8.4 | 13.6 d | 24.4 d | A |
| USA (48 states, PR, VI: ~90 % with 1 m; Alaska: IfSAR 5 m) | 8,388 | 21.8 | 21.8 | 13.2 | 35.1 d | 35.1 d | A, M |
| Greenland (ArcticDEM) | 2,166 | 2.17 | 2.17 | 0.58 | 3.0 d | 3.0 d | A |
| **North America** | **14,248** | **41.0** | **55.8** | **18.1 / 22.2** | **34.8 d** | **34.8 d** | |
| New Zealand | 233 | 1.05 | 2.10 | 0.40 / 0.81 | 1.3 d | 2.5 d | A |
| Australia (Tasmania; Queensland's lidar, ~300 000 km² assumed) | 368 | 1.42 | 1.42 | 0.69 | 14.7 d | 14.7 d | A, F |
| **Oceania** | **601** | **2.47** | **3.52** | **1.1 / 1.5** | **14.5 d** | **14.5 d** | |
| **All** | **17,861** | **54.9** | **83.5** | **24.3 / 33.9** | **34.8 d** | **34.8 d** | |

Basis: M measured (this report, or the window measurements of 2026-11-04), E exact (the Metalinks' sizes), O the
app's rate seen in the cache, F the formats and sizes of the catalogue's comments, A assumed.

- One host after another, the countries take 86 days (terrain) or 115 (with the surface models); all hosts at once,
  the USA's blocks decide (138 a minute measured, 250 seen in the cache: 19 days); the link alone would carry the
  bytes in 5.4 or 8.2 days.
- The largest uncertainties: Canada's lidar area (~1.6 M km², summed from the survey's descriptions of the
  provinces), the USA's share with a 1 m DEM (Utah's 89 % taken for all), Queensland's lidar area and its seconds a
  tile.
- Where the bytes go (downloaded against cached, 49.5 TB): about 37 TB windows of big remote files (Canada 22.8,
  the USA 8.6, ArcticDEM 3.2, New Zealand 1.3, Austria 0.6), 6.5 TB text formats (Poland's ASCII sheets 5.2), 3 TB
  Bavaria's DOM20 (0.2 m, 3.12 TB by its Metalinks), 2.5 TB uncompressed WCS answers.
- The windows: a block of 1000 px reads every tile of 512 px it touches, 2.35 times the file's bytes
  (docs/performance.md, "Window reads"). The country prefetch now reads them in groups (B); Austria, Luxembourg and
  British Columbia read range by range in squares everywhere (C). With groups of 10 km
  (`country.PREFETCH_GROUP_M`) the model of docs/performance.md ("The size of a group") puts the window sources
  at about 35 of their 59.5 TB: about 39 TB to download for the terrain and 59 TB with the surface models instead
  of 54.9 and 83.5 (the caches stay as they are). On one thread a group read a km² 1.25 (the USA) to 1.5 (Canada)
  times as fast as the blocks, a full group of 10 km in Canada 2.2-2.7 times: the USA's 35 days become about 28 at
  most, and they still decide when all hosts run at once.

## 3. Download time

Orthophotos left out. Measured with `tools/perf_download.py` on an empty cache (2026-11-02, this PC,
about 1 Gb/s):

| Service | Measured | What decides | The index of the whole country |
| --- | --- | --- | --- |
| opendata.geoportal.gov.pl (Poland) | 863 MB of 71 sheets in 146 s with 8 connections: 5.9 MB/s; one connection 1.2 MB/s | the server's speed per connection (no limit published) | 757 tiles of 0.25° × 2 WFS queries of 2.8 s (24 measured): 1.2 h |
| data.geo.admin.ch (Switzerland) | 33 files (469 MB) in 53 s | 36 requests a minute (the app's limit under swisstopo's 40) | 114 tiles × about 40 s (two STAC searches of up to 14 pages at 36 a minute; 32 s measured for a new tile): 1.3 h |
| prd-tnm (USGS, Utah) | 30 blocks of 1 km in 13 s with 8 connections: 138 a minute | the block reads (several range requests each) | 405 tiles × about 8 s (TNM, two samples): 0.9 h |

The download time of each country (data and index, for the coarsest data a strategy can use) is the
last column of the table in section 2.

- **Slovakia** downloads nothing: its tiles are copied from the local mirror at disk speed (about
  5 minutes for 142 GB at 500 MB/s); on the 5650G they have to cross the network first (about 20
  minutes at 1 Gb/s). A country driver could read the mirror directly instead of copying it into the
  cache.
- **Poland** is the long one: two weeks for NMT and NMPT at 5.9 MB/s, one week for NMT alone. The
  link (118 MB/s) is twenty times faster than the server gives; more connections would help until
  the server says no, and GUGiK publishes no limit (section 5): ask first.
- **Switzerland** is limited by the request rate, not the bytes: 1 km files at 36 a minute make
  2,160 an hour, so two layers of 41,445 tiles take 38 hours whatever their resolution.
- **Utah** at 8 connections takes about a day, at uGet's three connections (USGS's own batch tool)
  about three. The COGs' overviews would cut the bytes of coarse bands (section 2).
- Downloading and computing overlap: a country driver computes the tiles whose data is in while the
  next ones download, so a run takes about the longer of the two, not their sum.

## 4. Compute time

### 4.1 The machines

| | Ryzen 9 9900X (this PC) | Ryzen 5 PRO 5650G |
| --- | --- | --- |
| Cores | 12 (24 threads) | 6 (12 threads) |
| Memory for the task | about 50 GB | 45 GB |
| One core (single-threaded stages of `bench`) | 1 | 1.54 times as long |
| Pair search: CPU seconds | 1 | 1.13 times as many |
| Pair search: busy threads | 21.0 | 9.1 |
| Pair search: wall time | 1 | 2.6 times as long |

Both from `bench` (the same offline searches on each machine). On the 5650G the data and the work
folder belong on its SSD: the first bench, on the Unraid array (FUSE), waited on I/O.

### 4.2 What a country run computes

Per tile: step 1 (stitching the layers, filling water and gaps), step 2 (anchors, prominence and
drop), step 3 (the pair search) and the counts; not the coordinates, profiles, map files or
`lines.csv`. Steps 1-2 run on one core, step 3 on all of them. The times assume:

- **lines counted, not kept**: today's search keeps every line until it is saved; in the densest
  M stratum at 2 m (10-23 million lines per km²) even a tile of 2 km would hold 40 GB of lines, a
  tile of 5 km 260 GB;
- **spots not grouped as today**: today's grouping is single-threaded and grows with the lines; it
  would add 18 h to Switzerland's M band on the 9900X if the lines fitted at all;
- **K tiles at once**: as many as the memory allows at 100 B per pixel of the grids, at most one per
  physical core, each process keeping 85 % of a core; the fastest tile core of 2-60 km is chosen.

### 4.3 Per country

The time on each machine with the DSM (Utah has none): "mid" (the plain estimate) and in brackets the
range of a bootstrap over the places where it differs by more than 15 %; the lines and spots of the
mid estimate; the tiles chosen on the 9900X (core size × tiles at once). "-": a band at a resolution
that was not measured (M at 1 m, L at 2 m: out of reach today).

| Slovakia: variant | Grids | 9900X | 5650G | Lines (mid) | Spots (mid) | Tiles (9900X) |
| --- | --- | --- | --- | --- | --- | --- |
| 30-2000 m | 1 m | - | - | - | - | not measured |
| 30-2000 m | 2 m | 1.4 h (53 min-1.8 h) | 3.7 h (2.3 h-4.7 h) | 2.4 bn | 5.8 M | S 10 km ×12, M 10 km ×9 |
| 30-2000 m | 5 m | 24 min | 1.1 h | 92 M | 1.7 M | S 30 km ×12, M 20 km ×12 |
| 30-2000 m | split 1/2/5 m | 1.6 h (1.1 h-2.0 h) | 4.3 h (2.9 h-5.3 h) | 2.4 bn | 5.7 M | S 5 km ×12, M 10 km ×9 |
| 30-2000 m | split 2/5/10 m | 25 min | 1.2 h | 96 M | 1.7 M | S 10 km ×12, M 20 km ×12 |
| 30-5000 m | 1 m | - | - | - | - | not measured |
| 30-5000 m | 2 m | - | - | - | - | not measured |
| 30-5000 m | 5 m | 37 min | 1.7 h | 178 M | 3.4 M | S 30 km ×12, M 20 km ×12, L 20 km ×12 |
| 30-5000 m | split 1/2/5 m | 1.8 h (1.3 h-2.2 h) | 4.9 h (3.4 h-5.9 h) | 2.5 bn | 7.4 M | S 5 km ×12, M 10 km ×9, L 20 km ×12 |
| 30-5000 m | split 2/5/10 m | 34 min | 1.5 h | 101 M | 2.2 M | S 10 km ×12, M 20 km ×12, L 40 km ×12 |
| 2000-5000 m | 1 m | - | - | - | - | not measured |
| 2000-5000 m | 2 m | - | - | - | - | not measured |
| 2000-5000 m | 5 m | 13 min | 32 min | 86 M | 1.6 M | L 20 km ×12 |
| 2000-5000 m | split 1/2/5 m | 13 min | 32 min | 86 M | 1.6 M | L 20 km ×12 |
| 2000-5000 m | split 2/5/10 m | 8 min | 22 min | 5.8 M | 526 k | L 40 km ×12 |

| Poland: variant | Grids | 9900X | 5650G | Lines (mid) | Spots (mid) | Tiles (9900X) |
| --- | --- | --- | --- | --- | --- | --- |
| 30-2000 m | 1 m | - | - | - | - | not measured |
| 30-2000 m | 2 m | 4.0 h | 10 h | 467 M | 1.6 M | S 10 km ×12, M 10 km ×9 |
| 30-2000 m | 5 m | 2.5 h | 7.2 h | 18 M | 528 k | S 30 km ×12, M 20 km ×12 |
| 30-2000 m | split 1/2/5 m | 5.1 h | 14 h | 469 M | 1.5 M | S 5 km ×12, M 10 km ×9 |
| 30-2000 m | split 2/5/10 m | 2.6 h | 7.3 h | 19 M | 509 k | S 10 km ×12, M 20 km ×12 |
| 30-5000 m | 1 m | - | - | - | - | not measured |
| 30-5000 m | 2 m | - | - | - | - | not measured |
| 30-5000 m | 5 m | 3.8 h | 10 h | 41 M | 949 k | S 30 km ×12, M 20 km ×12, L 20 km ×12 |
| 30-5000 m | split 1/2/5 m | 6.5 h | 17 h | 492 M | 2.0 M | S 5 km ×12, M 10 km ×9, L 20 km ×12 |
| 30-5000 m | split 2/5/10 m | 3.5 h | 9.7 h | 21 M | 646 k | S 10 km ×12, M 20 km ×12, L 40 km ×12 |
| 2000-5000 m | 1 m | - | - | - | - | not measured |
| 2000-5000 m | 2 m | - | - | - | - | not measured |
| 2000-5000 m | 5 m | 1.3 h | 3.2 h | 23 M | 422 k | L 20 km ×12 |
| 2000-5000 m | split 1/2/5 m | 1.3 h | 3.2 h | 23 M | 422 k | L 20 km ×12 |
| 2000-5000 m | split 2/5/10 m | 53 min | 2.4 h | 1.6 M | 136 k | L 40 km ×12 |

| Switzerland: variant | Grids | 9900X | 5650G | Lines (mid) | Spots (mid) | Tiles (9900X) |
| --- | --- | --- | --- | --- | --- | --- |
| 30-2000 m | 1 m | - | - | - | - | not measured |
| 30-2000 m | 2 m | 3.6 d (39 h-4.9 d) | 9.3 d (4.2 d-13 d) | 190 bn | 356 M | S 10 km ×12, M 5 km ×12 |
| 30-2000 m | 5 m | 2.0 h (1.1 h-2.7 h) | 5.3 h (2.9 h-7.1 h) | 7.3 bn | 101 M | S 30 km ×12, M 20 km ×12 |
| 30-2000 m | split 1/2/5 m | 3.6 d (39 h-5.0 d) | 9.3 d (4.3 d-13 d) | 191 bn | 355 M | S 5 km ×12, M 5 km ×12 |
| 30-2000 m | split 2/5/10 m | 2.1 h (1.1 h-2.8 h) | 5.4 h (2.9 h-7.3 h) | 7.5 bn | 100 M | S 10 km ×12, M 20 km ×12 |
| 30-5000 m | 1 m | - | - | - | - | not measured |
| 30-5000 m | 2 m | - | - | - | - | not measured |
| 30-5000 m | 5 m | 5.7 h (3.1 h-8.3 h) | 15 h (8.2 h-22 h) | 14 bn | 226 M | S 30 km ×12, M 20 km ×12, L 20 km ×12 |
| 30-5000 m | split 1/2/5 m | 3.7 d (41 h-5.2 d) | 9.7 d (4.5 d-13 d) | 197 bn | 481 M | S 5 km ×12, M 5 km ×12, L 20 km ×12 |
| 30-5000 m | split 2/5/10 m | 2.3 h (1.2 h-3.1 h) | 6.0 h (3.3 h-8.0 h) | 7.9 bn | 141 M | S 10 km ×12, M 20 km ×12, L 40 km ×12 |
| 2000-5000 m | 1 m | - | - | - | - | not measured |
| 2000-5000 m | 2 m | - | - | - | - | not measured |
| 2000-5000 m | 5 m | 3.7 h (2.1 h-5.6 h) | 9.6 h (5.4 h-15 h) | 6.8 bn | 125 M | L 20 km ×12 |
| 2000-5000 m | split 1/2/5 m | 3.7 h (2.1 h-5.6 h) | 9.6 h (5.4 h-15 h) | 6.8 bn | 125 M | L 20 km ×12 |
| 2000-5000 m | split 2/5/10 m | 12 min (8 min-16 min) | 31 min (22 min-43 min) | 461 M | 40 M | L 40 km ×12 |

| Utah: variant | Grids | 9900X | 5650G | Lines (mid) | Spots (mid) | Tiles (9900X) |
| --- | --- | --- | --- | --- | --- | --- |
| 30-2000 m | 1 m | - | - | - | - | not measured |
| 30-2000 m | 2 m | 23 h (13 h-30 h) | 2.5 d (34 h-3.2 d) | 49 bn | 129 M | S 10 km ×12, M 10 km ×9 |
| 30-2000 m | 5 m | 1.9 h | 5.3 h | 1.9 bn | 37 M | S 30 km ×12, M 20 km ×12 |
| 30-2000 m | split 1/2/5 m | 24 h (14 h-31 h) | 2.7 d (36 h-3.3 d) | 49 bn | 128 M | S 5 km ×12, M 10 km ×9 |
| 30-2000 m | split 2/5/10 m | 2.0 h | 5.4 h | 2.0 bn | 37 M | S 10 km ×12, M 20 km ×12 |
| 30-5000 m | 1 m | - | - | - | - | not measured |
| 30-5000 m | 2 m | - | - | - | - | not measured |
| 30-5000 m | 5 m | 3.7 h (2.9 h-4.0 h) | 10.0 h (7.8 h-11 h) | 4.9 bn | 92 M | S 30 km ×12, M 20 km ×12, L 20 km ×12 |
| 30-5000 m | split 1/2/5 m | 26 h (15 h-33 h) | 2.8 d (39 h-3.6 d) | 52 bn | 183 M | S 5 km ×12, M 10 km ×9, L 20 km ×12 |
| 30-5000 m | split 2/5/10 m | 2.6 h | 7.0 h | 2.2 bn | 55 M | S 10 km ×12, M 20 km ×12, L 40 km ×12 |
| 2000-5000 m | 1 m | - | - | - | - | not measured |
| 2000-5000 m | 2 m | - | - | - | - | not measured |
| 2000-5000 m | 5 m | 1.8 h (1.1 h-2.0 h) | 4.7 h (2.8 h-5.3 h) | 3.0 bn | 55 M | L 20 km ×12 |
| 2000-5000 m | split 1/2/5 m | 1.8 h (1.1 h-2.0 h) | 4.7 h (2.8 h-5.3 h) | 3.0 bn | 55 M | L 20 km ×12 |
| 2000-5000 m | split 2/5/10 m | 37 min | 1.7 h | 202 M | 18 M | L 40 km ×12 |

- **Slovakia**: 1.6 h (1.1-2.0 h) for 30-2000 m on the 9900X, 4.3 h on the 5650G. Its M band holds
  about 2.4 billion lines, 2 billion of them in 88 km² of the High Tatras' steepest strata, which take
  the density of all steep cells (mostly Lauterbrunnen's and Zion's); with the Polish Tatras' own
  density there (5.1 million lines per km² instead of 23) it would be about 0.8 billion lines and an
  hour. The pilot itself will tell.
- **Poland** is grid-bound: 13-25 core-hours of steps 1-2 per band against an hour of pair search;
  twelve tiles at once make it hours. Without the NMPT 8-9 % less.
- **Switzerland's M band at 2 m** is the pair search in the Alps: 85 h on the 9900X (39-119 h), 9 days
  on the 5650G. The same band at 5 m takes 2 h but sees a few per cent of the lines (section 1).
- **Utah's S and M bands at 1 and 2 m**: 24 h (14-31 h) on the 9900X, 22 h of it the M band's pair
  search; the canyon country (Zion's cells, scaled from 5 m: section 7) is as dense as the Alps' walls.
- **The L band at 5 m** takes 13 min (Slovakia) to 3.7 h (Switzerland) on the 9900X; its pair
  search costs 40 µs a line, the most of the three bands, because a 2-5 km line has the most pixels
  to check.

### 4.4 The time models

From the places measured at each band and grid: the grid's seconds per Mpx (median; steps 1-2
without the download), the pair search's CPU seconds per km² as a + b × lines per km² (least squares
over the places) and the metres over water per line.

| Band, grid | Places | Steps 1-2: s per Mpx | Pair search: CPU s per km² | Over water: per line |
| --- | --- | --- | --- | --- |
| S 1 m | 8 | 0.18 | 0.232 + 25.6 µs × lines per km² | 0.26 µs |
| S 2 m | 4 | 0.48 | 0.239 + 19 µs × lines per km² | 0.22 µs |
| S 5 m | 3 | 3.65 | 0.0574 + 14 µs × lines per km² | 0.18 µs |
| M 2 m | 7 | 0.40 | 0.0326 + 33.6 µs × lines per km² | 0.28 µs |
| M 5 m | 4 | 1.94 | 0.103 + 18.2 µs × lines per km² | 0.22 µs |
| L 5 m | 8 | 1.67 | 0 + 40.2 µs × lines per km² | 0.27 µs |
| L 10 m | 2 | 6.08 | 0.0571 + 22.9 µs × lines per km² | 0.24 µs |

A line costs 14-34 µs of pair search CPU whatever the place, and a coarser grid costs more per Mpx
because it reads the same fine data: steps 1-2 at 5 m take 3.65 s per Mpx of the grid (0.15 s per Mpx
of 1 m data read). One step 1 for all bands, at the finest grid, and the coarser grids averaged from
it, would save most of that (6.5).

### 4.5 The strata of each country

The country's km² per stratum (the steep share of 30 m pixels of 45° or more around each 1 km block;
where that is below 0.5 %, the relief), the samples' cells in it and their lines and spots per km²:

| Poland, S at 1 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 296,413 | 86.3 | 1 | 0.1 |
| steep < 0.5 %, relief 100-250 m | 13,302 | 24.9 | 92 | 3.6 |
| steep < 0.5 %, relief >= 250 m | 1,952 | 22.2 | 43 | 2.5 |
| steep 0.5-1 % | 82 | 15.8 | 1,078 | 12.0 |
| steep 1-2 % | 53 | 12.8 | 1,130 | 25.7 |
| steep 2-5 % | 33 | 30.6 | 817 | 16.8 |
| steep 5-10 % | 23 | 22.8 | 8,173 | 68.8 |
| steep 10-20 % | 23 | 37.4 | 31,005 | 225.7 |
| steep >= 20 % | 5 | 46.0 | 137,311 | 623.5 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 1.6 M / 3.3 M / 4.6 M; spots 76 k / 86 k / 109 k.

| Poland, M at 2 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 278,585 | 27.1 | 0 | 0.0 |
| steep < 0.5 %, relief 100-300 m | 25,731 | 45.1 | 742 | 12.6 |
| steep < 0.5 %, relief >= 300 m | 7,375 | 5.4 | 2,001 | 24.1 |
| steep 0.5-1 % | 64 | 2.8 | 109,448 | 755.9 |
| steep 1-2 % | 31 | 15.8 | 135,987 | 703.9 |
| steep 2-5 % | 50 | 31.8 | 419,170 | 2,314.5 |
| steep 5-10 % | 35 | 29.0 | 1,253,899 | 4,447.8 |
| steep >= 10 % | 15 | 69.5 | 23,350,322 | 40,109.1 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 255 M / 466 M / 606 M; spots 1.0 M / 1.5 M / 1.7 M.

| Poland, L at 5 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-150 m | 284,917 | 7.3 | 0 | 0.0 |
| steep < 0.5 %, relief 150-400 m | 19,914 | 24.3 | 0 | 0.0 |
| steep < 0.5 %, relief >= 400 m | 6,860 | 1.0 | 0 | 0.0 |
| steep 0.5-1 % | 34 | 8.8 | 778 | 53.0 |
| steep 1-2 % | 38 | 32.3 | 5,265 | 240.6 |
| steep 2-5 % | 80 | 123.0 | 90,065 | 1,481.3 |
| steep 5-10 % | 29 | 129.7 | 238,170 | 4,298.4 |
| steep >= 10 % | 15 | 198.6 | 594,700 | 11,027.9 |

Places: ch-alps-area, pl-jura, pl-tatry, ut-canyonlands, ut-wasatch, ut-zion. Lines low / mid / high: 16 M / 23 M / 30 M; spots 334 k / 422 k / 445 k.

| Switzerland, S at 1 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 7,886 | 86.3 | 1 | 0.1 |
| steep < 0.5 %, relief 100-250 m | 8,206 | 24.9 | 92 | 3.6 |
| steep < 0.5 %, relief >= 250 m | 5,810 | 22.2 | 43 | 2.5 |
| steep 0.5-1 % | 2,057 | 15.8 | 1,078 | 12.0 |
| steep 1-2 % | 2,401 | 12.8 | 1,130 | 25.7 |
| steep 2-5 % | 4,032 | 30.6 | 817 | 16.8 |
| steep 5-10 % | 3,881 | 22.8 | 8,173 | 68.8 |
| steep 10-20 % | 4,185 | 37.4 | 31,005 | 225.7 |
| steep >= 20 % | 2,988 | 46.0 | 137,311 | 623.5 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 52 M / 581 M / 936 M; spots 1.2 M / 3.3 M / 4.4 M.

| Switzerland, M at 2 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 1,776 | 27.1 | 0 | 0.0 |
| steep < 0.5 %, relief 100-300 m | 9,098 | 45.1 | 742 | 12.6 |
| steep < 0.5 %, relief >= 300 m | 6,570 | 5.4 | 2,001 | 24.1 |
| steep 0.5-1 % | 2,019 | 2.8 | 109,448 | 755.9 |
| steep 1-2 % | 2,620 | 15.8 | 135,987 | 703.9 |
| steep 2-5 % | 5,526 | 31.8 | 419,170 | 2,314.5 |
| steep 5-10 % | 6,149 | 29.0 | 1,253,899 | 4,447.8 |
| steep >= 10 % | 7,685 | 69.5 | 23,350,322 | 40,109.1 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 87 bn / 190 bn / 264 bn; spots 199 M / 352 M / 437 M.

| Switzerland, L at 5 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-150 m | 1,501 | 7.3 | 0 | 0.0 |
| steep < 0.5 %, relief 150-400 m | 9,059 | 24.3 | 0 | 0.0 |
| steep < 0.5 %, relief >= 400 m | 5,750 | 1.0 | 0 | 0.0 |
| steep 0.5-1 % | 1,752 | 8.8 | 778 | 53.0 |
| steep 1-2 % | 2,408 | 32.3 | 5,265 | 240.6 |
| steep 2-5 % | 6,091 | 123.0 | 90,065 | 1,481.3 |
| steep 5-10 % | 7,216 | 129.7 | 238,170 | 4,298.4 |
| steep >= 10 % | 7,669 | 198.6 | 594,700 | 11,027.9 |

Places: ch-alps-area, pl-jura, pl-tatry, ut-canyonlands, ut-wasatch, ut-zion. Lines low / mid / high: 3.8 bn / 6.8 bn / 10 bn; spots 60 M / 125 M / 139 M.

| Slovakia, S at 1 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 21,660 | 86.3 | 1 | 0.1 |
| steep < 0.5 %, relief 100-250 m | 18,624 | 24.9 | 92 | 3.6 |
| steep < 0.5 %, relief >= 250 m | 7,539 | 22.2 | 43 | 2.5 |
| steep 0.5-1 % | 514 | 15.8 | 1,078 | 12.0 |
| steep 1-2 % | 304 | 12.8 | 1,130 | 25.7 |
| steep 2-5 % | 216 | 30.6 | 817 | 16.8 |
| steep 5-10 % | 87 | 22.8 | 8,173 | 68.8 |
| steep 10-20 % | 55 | 37.4 | 31,005 | 225.7 |
| steep >= 20 % | 36 | 46.0 | 137,311 | 623.5 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 2.7 M / 11 M / 16 M; spots 65 k / 146 k / 155 k.

| Slovakia, M at 2 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 12,778 | 27.1 | 0 | 0.0 |
| steep < 0.5 %, relief 100-300 m | 15,972 | 45.1 | 742 | 12.6 |
| steep < 0.5 %, relief >= 300 m | 19,022 | 5.4 | 2,001 | 24.1 |
| steep 0.5-1 % | 570 | 2.8 | 109,448 | 755.9 |
| steep 1-2 % | 356 | 15.8 | 135,987 | 703.9 |
| steep 2-5 % | 181 | 31.8 | 419,170 | 2,314.5 |
| steep 5-10 % | 67 | 29.0 | 1,253,899 | 4,447.8 |
| steep >= 10 % | 88 | 69.5 | 23,350,322 | 40,109.1 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 1.2 bn / 2.4 bn / 3.2 bn; spots 3.7 M / 5.6 M / 6.2 M.

| Slovakia, L at 5 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-150 m | 13,428 | 7.3 | 0 | 0.0 |
| steep < 0.5 %, relief 150-400 m | 15,718 | 24.3 | 0 | 0.0 |
| steep < 0.5 %, relief >= 400 m | 18,548 | 1.0 | 0 | 0.0 |
| steep 0.5-1 % | 676 | 8.8 | 778 | 53.0 |
| steep 1-2 % | 338 | 32.3 | 5,265 | 240.6 |
| steep 2-5 % | 180 | 123.0 | 90,065 | 1,481.3 |
| steep 5-10 % | 58 | 129.7 | 238,170 | 4,298.4 |
| steep >= 10 % | 90 | 198.6 | 594,700 | 11,027.9 |

Places: ch-alps-area, pl-jura, pl-tatry, ut-canyonlands, ut-wasatch, ut-zion. Lines low / mid / high: 53 M / 86 M / 130 M; spots 929 k / 1.6 M / 1.8 M.

| Utah, S at 1 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 102,094 | 86.3 | 1 | 0.1 |
| steep < 0.5 %, relief 100-250 m | 64,046 | 24.9 | 92 | 3.6 |
| steep < 0.5 %, relief >= 250 m | 22,712 | 22.2 | 43 | 2.5 |
| steep 0.5-1 % | 4,430 | 15.8 | 1,078 | 12.0 |
| steep 1-2 % | 4,785 | 12.8 | 1,130 | 25.7 |
| steep 2-5 % | 6,567 | 30.6 | 817 | 16.8 |
| steep 5-10 % | 4,777 | 22.8 | 8,173 | 68.8 |
| steep 10-20 % | 2,879 | 37.4 | 31,005 | 225.7 |
| steep >= 20 % | 528 | 46.0 | 137,311 | 623.5 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 35 M / 223 M / 385 M; spots 828 k / 1.9 M / 2.6 M.

| Utah, M at 2 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-100 m | 45,395 | 27.1 | 0 | 0.0 |
| steep < 0.5 %, relief 100-300 m | 69,950 | 45.1 | 742 | 12.6 |
| steep < 0.5 %, relief >= 300 m | 60,660 | 5.4 | 2,001 | 24.1 |
| steep 0.5-1 % | 9,116 | 2.8 | 109,448 | 755.9 |
| steep 1-2 % | 9,172 | 15.8 | 135,987 | 703.9 |
| steep 2-5 % | 11,538 | 31.8 | 419,170 | 2,314.5 |
| steep 5-10 % | 5,501 | 29.0 | 1,253,899 | 4,447.8 |
| steep >= 10 % | 1,487 | 69.5 | 23,350,322 | 40,109.1 |

Places: ch-alps, ch-plateau, pl-jura, pl-niz, pl-tatry, ut-sevier, ut-wasatch, ut-zion. Lines low / mid / high: 25 bn / 49 bn / 63 bn; spots 72 M / 126 M / 161 M.

| Utah, L at 5 m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |
| --- | --- | --- | --- | --- |
| steep < 0.5 %, relief 0-150 m | 40,974 | 7.3 | 0 | 0.0 |
| steep < 0.5 %, relief 150-400 m | 64,857 | 24.3 | 0 | 0.0 |
| steep < 0.5 %, relief >= 400 m | 64,044 | 1.0 | 0 | 0.0 |
| steep 0.5-1 % | 11,865 | 8.8 | 778 | 53.0 |
| steep 1-2 % | 12,108 | 32.3 | 5,265 | 240.6 |
| steep 2-5 % | 13,021 | 123.0 | 90,065 | 1,481.3 |
| steep 5-10 % | 5,005 | 129.7 | 238,170 | 4,298.4 |
| steep >= 10 % | 944 | 198.6 | 594,700 | 11,027.9 |

Places: ch-alps-area, pl-jura, pl-tatry, ut-canyonlands, ut-wasatch, ut-zion. Lines low / mid / high: 1.6 bn / 3.0 bn / 3.4 bn; spots 28 M / 55 M / 55 M.

## 5. Legality

A reading of the providers' texts on 2026-11-01/02, not legal advice. The quotes, links and the
pages that failed are in [notes/legal.md](country-precompute/notes/legal.md).

### 5.1 Downloading a whole country

| Provider | Licence of the data | Bulk download | Limits and etiquette | What to do |
| --- | --- | --- | --- | --- |
| **GUGiK** (Poland) | No fee and no licence for NMT and NMPT (art. 40a ust. 2 and art. 40c ust. 5 of the Geodetic and Cartographic Law, Dz.U. 2026 poz. 1389); the source must be stated in published works (art. 40c ust. 3); "Dane NMT są dostępne bezpłatnie i możliwe do dowolnego wykorzystania" | NMT and NMPT are on GUGiK's list of data "udostępniane nieodpłatnie bez konieczności składania wniosku": a country downloaded sheet by sheet needs no request. GUGiK calls the sheet index WFS "ułatwieniem do pobierania NMT dla większych obszarów" and ships a QGIS plugin that downloads sheets in bulk. No country package of NMT exists; a request with the applicant's own disk (more than 20 GB only so) is possible but optional | None published, no robots.txt; "The user can download any required data, without any limitations" (GUGiK's English page) | Our User-Agent with a contact, modest parallelism, nights and weekends; optionally a courtesy e-mail (the draft is in the notes) |
| **swisstopo** (Switzerland, Liechtenstein) | OGD terms: "Open use. Must provide the source"; use, distribution, processing and commercial use allowed | The FSDI terms send offline and database use to the download service (`data.geo.admin.ch`, the one the app uses); scripts are allowed. A delivery on a medium can be ordered (geodata@swisstopo.ch, a paid offer, 1-2 weeks) | FSDI fair use: 40 requests a minute on `*.geo.admin.ch` (the app keeps 36 since 8832023); "if limit overruns become foreseeable, contact info@geo.admin.ch before going live"; excessive use may be restricted | Send the e-mail of `local/mail-drafts.md` (does 40 a minute cover the files, is a 1.4 TB download welcome), then download at 36 a minute: 1.7 days |
| **ÚGKK SR** (Slovakia) | CC BY 4.0, author ÚGKK SR (the licence in the national ZIPs; the WMS capabilities say the same) | Done: the national ZIPs of geoportal.sk were downloaded once (2026-10-26) and cut into our tiles, the local mirror | - | Credit "© ÚGKK SR" with the licence and an indication of changes (as every run does) |
| **USGS 3DEP** (Utah) | Public domain, "There are no restrictions"; acknowledgment requested; whoever modifies the data must describe the modifications | `prd-tnm` is offered for "Direct access ... via standard HTTP clients"; for batches USGS points to uGet with URL lists, which downloads three files at a time | None published | Three to eight connections, windowed reads (as the app does), our User-Agent; optionally tnm_help@usgs.gov |

No torrent, Hugging Face or other mirror holds these national models (searched 2026-11-01).
OpenTopography has swissALTI3D, swissSURFACE3D and 3DEP, but for academics only (50 calls a day, 250
km² per 1 m request). The only global mirror is FABDEM at 30 m.

### 5.2 Publishing the counts

| Data | Counts per km² cell | Duty |
| --- | --- | --- |
| swisstopo | Allowed: the FSDI terms let data be "aufbereitet, analysiert und publiziert" | The source in the documentation of the publication ("derived from swissALTI3D and swissSURFACE3D Raster, © swisstopo"); published under our own name |
| GUGiK | Allowed ("dowolnego wykorzystania") | "Informacje o źródle pochodzenia" (art. 40c ust. 3); no prescribed wording |
| ÚGKK SR | Allowed (CC BY 4.0) | "© ÚGKK SR", the licence link and that the data was changed (`credit.PROCESSED_NOTE`) |
| USGS 3DEP | Allowed (public domain) | Acknowledgment ("Map services and data available from U.S. Geological Survey, National Geospatial Program") and a description of the processing (a methods page) |
| Copernicus GLO-30 (gap filling; the relief strata of this report) | Allowed (adaptation and combination) | The notice for adapted data and the liability sentence; no suggestion of endorsement |
| FABDEM (gap filling, CC BY-NC-SA 4.0) | Most likely allowed: a count holds none of FABDEM's contents, so ShareAlike does not attach | **NonCommercial binds our own use**: downloading the tiles of a country is extraction, so the project and the site must stay non-commercial, or the gaps are filled from Copernicus only |
| OpenStreetMap (sea mask, Poland only) | A count map is a Produced Work (ODbL 4.5 b) | "© OpenStreetMap contributors" with the link; the open code covers 4.6 (the method of the alterations) |

Keeping the raw data on a NAS is allowed for all of them; mirroring it publicly is allowed with the
source references (FABDEM non-commercial only). The counts are statistics, not heights or geometry,
so the layer is simpler to publish than the search results the app already shows. Two duties need
work when the layer is built: a methods page (USGS asks for a description of the modifications) and
a combined credit block (a draft is in [notes/legal.md](country-precompute/notes/legal.md), section 4).

## 6. Further points

### 6.1 Tiles: a fixed grid, their size, how many at once

- **A fixed tile grid per country**, in the source's CRS (EPSG:2180, LV95, UTM 12N), with cores of
  whole kilometres: the 1 km cells of the layer never straddle two tiles, a later run (new data, a
  new band) produces the same tiles, and a tile's result can be replaced alone. A line belongs to the
  tile whose core holds its first anchor (the rule `search.search_lines` applies already), so no line
  is counted twice; a spot whose lines start in two tiles is counted in both (6.2).
- **The overlap** is the longest line + 300 m (prominence span) + 2 pixels around the core: 0.6 km
  for S, 2.3 km for M, 5.3 km for L. A tile's grid work grows with ((core + 2 × overlap) / core)², so
  small tiles waste time in their overlaps (an L tile of 10 km computes 4.3 times its core) and large
  ones need memory (100 B per pixel of the grids: an M tile of 10 km at 2 m holds 5.3 GB).
- **Tiles at once**: steps 1-2 run on one core, the pair search on all of them, so a country run
  runs K tiles at once, each with its own pair-search threads. The web worker's slots do this for
  jobs; a country driver needs it for tiles (roadmap: "Tiles of a large area in parallel processes",
  deferred for the public site, where the slots are full anyway; offline it pays).

### 6.2 The result: a sparse counter cube, and what a spot is

- **Lines** are counted exactly: each line adds 1 to its key (cell, bin of length, bin of each
  filter). A filter of the layer sums the keys whose bins pass, a coarser cell sums cells: nothing is
  computed again.
- **Spots** need care. Today a spot is a group of lines (greedy grouping by the distance of both
  anchors, `mapping.group_lines`), made after all lines of a tile are found, on one core, with all
  lines in memory. For a country layer:
  1. **It does not scale to the M band in big-wall terrain**: Lauterbrunnen at 2 m has 7 million
     lines per km² (Zion probably more), and grouping its 50 km² took 94 minutes. A country run must
     count lines without keeping them, so a spot must be something that can be counted on the fly.
  2. **Today's spot is fine-grained there**: the M band at 2 m has 10,000-40,000 spots per km² in the
     steepest strata (one per 25-100 m²), because the grouping distance is 20 m. As a
     count that tells about the walls, not about the places a person would rig.
  3. **A filter changes the spots**: in the app a filter acts before grouping. A cube can keep, per
     spot, the best value of each filter among its lines (a spot passes when any of its lines
     could): exact for one filter, an upper bound when several are combined, because the best
     clearance and the best wall angle may come from different lines. Exact counts need the spot's
     Pareto front of lines (more keys), or fewer filters.
- **A spot that can be counted on the fly**: cluster the *anchors* first (after step 2, cheap; 50-100
  m, a parameter of the run), and call a spot a pair of anchor clusters with at least one valid line.
  The pair search then marks a pair of clusters instead of storing lines (a hash set of 8-byte keys
  per tile: millions of entries, not billions of lines). It is not today's group, so the layer's spot
  counts will not equal the app's; the layer should say so.
- **The size of the cube** (measured with `cube` on eight samples, 1 km cells, 12 bytes per key):

  | Keys per km² | Length only | Length, prominence, wall angle, clearance | All seven filters |
  | --- | --- | --- | --- |
  | Lines | 0.6-5.3 | 2-85 | 3-208 |
  | Spots | 0.5-4.8 | 1-64 | 1.4-112 |

  At most 2.5 KB per km² for the lines with all seven filters, so a band of Switzerland takes
  some tens of MB and a country with three bands and nine rigs (6.3) a few hundred MB at worst; flat
  country takes nearly nothing. Coarser cells (2, 4, 8 km) are sums, a few per cent more.

### 6.3 The filters: what each one costs

| Filter | Where its value comes from | Cost in the run | Bins (example) | Effort |
| --- | --- | --- | --- | --- |
| Length | the pair | none | 30, 60, 100, 150, 300, 600, 1000, 2000, 3000, 5000 m | low |
| Prominence and drop | step 2 (`terrain.py`), per anchor; a line takes its weaker anchor | none (computed anyway) | 0, 5, 10, 20, 50 m | low |
| Wall angle | per anchor (`helpers.downslope`); a line takes its steeper anchor | none | 0, 30, 45, 60° | low |
| Clearance and height of the webbing | the final check (`linesearch._evaluate`) | none | 0, 2, 5, 10, 20 m; 0, 10, 20, 50, 100 m | low |
| Over trees or buildings | the check against the DSM in `_evaluate` | the DSM's grid (DSM runs only) | yes / no | low (after the threshold of the Wales finding in the roadmap) |
| Over water | `covered_metres` (step 4, numba) | a pass over each line's pixels | yes / no | low |
| Pretension and webbing | the run uses the superset (T(L) and Silk 99, which sags least from 600 m); every other rig needs its own clearance test | one more pixel test per rig for the lines that pass the superset, from the ends inwards (most fail early) | e.g. 3 webbings × 3 pretensions (T(L) at 60, 80 and 100 %) | medium: the kernel tests a list of rigs and writes a bit mask |

Measured on Lauterbrunnen's M band at 5 m (the same T(L)): Axiom MK2 keeps 97.5 % of Silk 99's lines
and 97.8 % of its spots, Tiger 97.7 % and 97.8 % (ρ of the spots per cell 0.9996 and 0.9994). Between
these webbings the choice hardly matters where long lines hang far above the valley floor; a filter
by webbing pays only where lines are low. The pretension matters more (the sag grows about as 1/T),
but the samples measured only T(L).

Filters as floors of the search (a minimum prominence of 5 m and a webbing height of 20 m on
Lauterbrunnen's M band) are queued to be measured; at Montserrat a minimum prominence of 10 m cut
the lines 40-fold (roadmap, "Prominent lines").

### 6.4 A partial product: re-parametrising without the full cost

| Change | What it costs |
| --- | --- |
| Any filter of 6.3 within its bins; a coarser cell; a region's total | nothing: sums of the cube |
| Other bins, another spot cluster size | the pair search again; with the prepared grids, no download and no step 1 |
| Another slope threshold, height difference, sag inputs (mass, fall zone) or length band | the pair search again; with the prepared grids, no download and no step 1 |
| New data (a new survey) | the tiles whose input files changed (6.6) |

**Prepared grids** are the partial product worth keeping: per tile, the stitched and filled terrain,
the obstacle height (DSM − DTM, 6.5) and the water mask at the band's resolution, compressed (LERC,
1 cm). They skip the download and step 1, which is most of the time of the S band and of flat country
(section 4); for the M band in the mountains the pair search dominates and a re-run costs about as
much as the first. At 2 m they take about 2 MB per km² uncompressed (0.7 TB for Poland), at 5 m a
sixth of that.

### 6.5 What the current code lacks for a country run

1. **A country driver**: the fixed tile grid, K tile processes, a result file per tile (the cube's
   keys), resume after a stop, the inputs of each tile recorded (6.6). The web worker's job queue has
   the wrong shape (one search per job, its results saved as a run).
2. **A counting mode** of `linesearch.find_valid_lines`: it evaluates the pairs it found in parts
   already (`evaluation_parts`, at least 10,000 a part) and then joins the parts into one `LineTable`
   (`join_tables`). A sink that bins each part into the cube and drops it removes the 450 B per line;
   evaluating each chunk of pairs as soon as it is found (they are held until then, 16 B a pair: up to
   9 GB in a 5 km tile of the densest stratum) bounds a tile by its grids. Counts need no order of the
   lines, which today's results keep. With the spots of 6.2 (a cluster pair per line, a set per tile).
   Effort: medium, not a new kernel.
3. **Pretension by length** (T(L)): only in the measuring tool, which swaps `sag.EnvelopeTable` for
   one with a rig per span. `linesearch` reads only the table's minimum and the rig's fall zone (line
   723), so the change is small, and the results equal the plain search at a constant pretension
   (`tests/test_perf_country.py`).
4. **Several rigs in one check** (6.3).
5. **One step 1 for several bands**: the S, M and L bands read the same files; today each band would
   stitch them again, and a coarse grid costs more per pixel than a fine one (4.4).
6. **Coarse data for coarse grids**: 3DEP's overviews (2, 4, 8 m: 5-44 times fewer bytes) and GUGiK's
   5 m grid (photogrammetric, "Siatka 5m", about 25 times less data than the 1 m sheets; its quality on
   cliffs not checked).
7. **An obstacle layer instead of the DSM** (roadmap: "Obstacles lowered by averaging the DSM"): DSM
   − DTM at the data's resolution, its maximum per grid pixel, added to the DTM: 0.66 TB of Swiss
   DSM files become about 6 GB.
8. **Gap filling without FABDEM** for a public layer (non-commercial terms, section 5): Copernicus only.

### 6.6 Updates and the layer's licence

- The data changes: GUGiK publishes new surveys per sheet, swisstopo updates its tiles survey by
  survey, USGS adds 3DEP projects. `cache update` finds new surveys of cached tiles already. A tile of
  the layer records its input files (path and survey date); after an update, only the tiles whose
  inputs changed are computed again, and their keys replace the old ones.
- The layer is our own work (statistics, not the providers' data); its page carries the credits of
  section 5 and a methods page. Its own licence is the user's choice.

## 7. Method, samples and uncertainty

### 7.1 The samples

Searches of `main` at 221dd10, recorded by `tools/perf_country.py profile` on this PC, one at a time
under the exclusive test lock, with the user's T(L) and Silk 99 for the sag bands, 60° anchors, the
default height difference and the DSM where the source has one; `--lean` runs keep only the columns
the counts need. A search that found no lines is a sample too (zero counts, its stages). "Wall"
includes the download of data that was not cached yet. Lauterbrunnen's M band at 2 m was rebuilt from
its output (its run was lost while saving); Zion's at 2 m ran out of memory and is not a sample;
Canyonlands' L band at 5 m and the variants of 45° and 50° at 10 m, 50° at 5 m and the filters as floors
are queued (the test lock's queue was full on 2026-11-02) and will be added.

| Sample | Place | Band | Grid | Variant | Area | Lines | Spots | Lines per km² | Wall | CPU | Peak |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pl-jura-S-1m` | Jura, Dolinki Krakowskie (50.190, 19.735) | S | 1 m |  | 50.3 km² (r = 4 km) | 2 351 | 95 | 47 | 50 s | 32 s | 1.8 GB |
| `pl-jura-S-1m-nodsm` | Jura, Dolinki Krakowskie (50.190, 19.735) | S | 1 m | no DSM | 50.3 km² (r = 4 km) | 2 351 | 91 | 47 | 10 s | 21 s | 1.5 GB |
| `pl-jura-S-2m` | Jura, Dolinki Krakowskie (50.190, 19.735) | S | 2 m |  | 50.3 km² (r = 4 km) | 1 043 | 98 | 21 | 10 s | 17 s | 0.6 GB |
| `pl-jura-S-2m-45` | Jura, Dolinki Krakowskie (50.190, 19.735) | S | 2 m | 45° anchors | 50.3 km² (r = 4 km) | 1 291 | 115 | 26 | 8 s | 19 s | 0.6 GB |
| `ch-alps-S-1m` | Lauterbrunnen (46.550, 7.882) | S | 1 m |  | 50.3 km² (r = 4 km) | 384 810 | 7 834 | 7 656 | 32 s | 96 s | 1.9 GB |
| `ch-alps-S-2m` | Lauterbrunnen (46.550, 7.882) | S | 2 m |  | 50.3 km² (r = 4 km) | 169 580 | 9 807 | 3 374 | 163 s | 69 s | 0.6 GB |
| `ch-alps-S-2m-45` | Lauterbrunnen (46.550, 7.882) | S | 2 m | 45° anchors | 50.3 km² (r = 4 km) | 182 813 | 10 125 | 3 637 | 14 s | 58 s | 0.8 GB |
| `ch-alps-S-5m` | Lauterbrunnen (46.550, 7.882) | S | 5 m |  | 50.3 km² (r = 4 km) | 42 237 | 6 318 | 840 | 12 s | 21 s | 0.3 GB |
| `pl-niz-S-1m` | Lowland near Gorzów (52.740, 15.355) | S | 1 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 6 s | 10 s | 0.8 GB |
| `ut-sevier-S-1m` | Sevier Desert (39.350, -112.550) | S | 1 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 15 s | 16 s | 0.7 GB |
| `ch-plateau-S-1m` | Swiss Plateau (47.200, 7.700) | S | 1 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 183 s | 35 s | 0.8 GB |
| `ch-plateau-S-1m-nodsm` | Swiss Plateau (47.200, 7.700) | S | 1 m | no DSM | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 6 s | 12 s | 0.7 GB |
| `pl-tatry-S-1m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | S | 1 m |  | 50.3 km² (r = 4 km) | 44 397 | 1 498 | 883 | 531 s | 150 s | 3.2 GB |
| `pl-tatry-S-2m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | S | 2 m |  | 50.3 km² (r = 4 km) | 33 914 | 2 187 | 675 | 18 s | 38 s | 0.9 GB |
| `pl-tatry-S-5m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | S | 5 m |  | 50.3 km² (r = 4 km) | 13 356 | 2 290 | 266 | 12 s | 19 s | 0.6 GB |
| `ut-wasatch-S-1m` | Wasatch, Little Cottonwood (40.570, -111.680) | S | 1 m |  | 50.3 km² (r = 4 km) | 1 145 | 64 | 23 | 60 s | 57 s | 2.7 GB |
| `ut-zion-S-1m` | Zion Canyon (37.260, -112.950) | S | 1 m |  | 50.3 km² (r = 4 km) | 7 304 748 | 30 405 | 145 323 | 123 s | 321 s | 2.7 GB |
| `ut-zion-S-2m` | Zion Canyon (37.260, -112.950) | S | 2 m |  | 50.3 km² (r = 4 km) | 4 418 200 | 42 015 | 87 897 | 45 s | 160 s | 1.4 GB |
| `ut-zion-S-2m-45` | Zion Canyon (37.260, -112.950) | S | 2 m | 45° anchors | 50.3 km² (r = 4 km) | 4 503 797 | 42 390 | 89 600 | 20 s | 146 s | 1.8 GB |
| `ut-zion-S-5m` | Zion Canyon (37.260, -112.950) | S | 5 m |  | 50.3 km² (r = 4 km) | 1 067 184 | 50 514 | 21 231 | 13 s | 41 s | 0.7 GB |
| `pl-jura-M-2m` | Jura, Dolinki Krakowskie (50.190, 19.735) | M | 2 m |  | 50.3 km² (r = 4 km) | 33 514 | 569 | 667 | 11 s | 22 s | 0.6 GB |
| `ch-alps-M-2m` | Lauterbrunnen (46.550, 7.882) | M | 2 m |  | 50.3 km² (r = 4 km) | 362 730 032 | 752 549 | 7 216 282 | 6 652 s (from its output) |  s |  |
| `ch-alps-M-5m` | Lauterbrunnen (46.550, 7.882) | M | 5 m |  | 50.3 km² (r = 4 km) | 21 153 814 | 384 648 | 420 842 | 363 s | 797 s | 15.2 GB |
| `ch-alps-M-5m-45` | Lauterbrunnen (46.550, 7.882) | M | 5 m | 45° anchors | 50.3 km² (r = 4 km) | 104 762 644 | 1 158 792 | 2 084 186 | 2 227 s | 4 331 s | 44.7 GB |
| `ch-alps-M-5m-axiom` | Lauterbrunnen (46.550, 7.882) | M | 5 m | Axiom MK2 | 50.3 km² (r = 4 km) | 20 633 689 | 376 320 | 410 494 | 213 s | 658 s | 16.3 GB |
| `ch-alps-M-5m-tiger` | Lauterbrunnen (46.550, 7.882) | M | 5 m | Tiger | 50.3 km² (r = 4 km) | 20 659 128 | 376 096 | 411 000 | 214 s | 660 s | 16.4 GB |
| `pl-niz-M-2m` | Lowland near Gorzów (52.740, 15.355) | M | 2 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 6 s | 8 s | 0.3 GB |
| `ut-sevier-M-2m` | Sevier Desert (39.350, -112.550) | M | 2 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 3 s | 2 s | 0.3 GB |
| `ch-plateau-M-2m` | Swiss Plateau (47.200, 7.700) | M | 2 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 77 s | 21 s | 0.3 GB |
| `pl-tatry-M-2m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | M | 2 m |  | 50.3 km² (r = 4 km) | 41 485 959 | 188 804 | 825 337 | 573 s | 2 131 s | 13.7 GB |
| `pl-tatry-M-5m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | M | 5 m |  | 50.3 km² (r = 4 km) | 1 567 632 | 51 349 | 31 187 | 28 s | 75 s | 1.7 GB |
| `ut-wasatch-M-2m` | Wasatch, Little Cottonwood (40.570, -111.680) | M | 2 m |  | 50.3 km² (r = 4 km) | 16 565 037 | 56 181 | 329 551 | 175 s | 781 s | 4.5 GB |
| `ut-wasatch-M-5m` | Wasatch, Little Cottonwood (40.570, -111.680) | M | 5 m |  | 50.3 km² (r = 4 km) | 533 844 | 13 998 | 10 620 | 7 s | 31 s | 0.5 GB |
| `ut-zion-M-5m` | Zion Canyon (37.260, -112.950) | M | 5 m |  | 50.3 km² (r = 4 km) | 48 460 289 | 559 938 | 964 086 | 626 s | 1 676 s | 22.8 GB |
| `ut-canyonlands-L-10m` | Dead Horse Point (38.470, -109.740) | L | 10 m |  | 314.2 km² (r = 10 km) | 2 145 899 | 166 486 | 6 831 | 141 s | 192 s | 4.2 GB |
| `pl-jura-L-5m` | Jura, Dolinki Krakowskie (50.190, 19.735) | L | 5 m |  | 50.3 km² (r = 4 km) | 0 | 0 | 0 | 6 s | 11 s | 0.3 GB |
| `ch-alps-area-L-5m` | Lauterbrunnen valley (drawn area) | L | 5 m |  | 272.5 km² (area) | 102 367 760 | 2 083 742 | 375 725 | 3 964 s | 6 602 s | 44.9 GB |
| `ch-alps-area-L-10m` | Lauterbrunnen valley (drawn area) | L | 10 m |  | 272.5 km² (area) | 6 895 453 | 673 507 | 25 309 | 478 s | 371 s | 22.2 GB |
| `pl-niz-L-5m` | Lowland near Gorzów (52.740, 15.355) | L | 5 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 2 s | 2 s | 0.3 GB |
| `ut-sevier-L-5m` | Sevier Desert (39.350, -112.550) | L | 5 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 2 s | 2 s | 0.2 GB |
| `ch-plateau-L-5m` | Swiss Plateau (47.200, 7.700) | L | 5 m |  | 19.6 km² (r = 2.5 km) | 0 | 0 | 0 | 4 s | 4 s | 0.2 GB |
| `pl-tatry-L-5m` | Tatras, Hala Gąsienicowa (49.235, 20.000) | L | 5 m |  | 50.3 km² (r = 4 km) | 43 667 | 2 949 | 869 | 13 s | 30 s | 0.6 GB |
| `ut-wasatch-L-5m` | Wasatch, Little Cottonwood (40.570, -111.680) | L | 5 m |  | 50.3 km² (r = 4 km) | 503 011 | 17 207 | 10 007 | 8 s | 44 s | 0.7 GB |
| `ut-zion-L-5m` | Zion Canyon (37.260, -112.950) | L | 5 m |  | 50.3 km² (r = 4 km) | 25 469 179 | 318 953 | 506 693 | 297 s | 1 444 s | 13.5 GB |

### 7.2 From samples to a country

1. **The country's relief** (`relief`): Copernicus DEM GLO-30 over the country's OpenStreetMap
   outline, in blocks of about 1 km: the share of pixels of 45° or more and the relief (highest minus
   lowest point), over windows of 1, 3 and 5 blocks (the reach of the S, M and L lines). Of nine
   candidate proxies, the steep share correlates best with the samples' lines per 1 km cell
   (Spearman 0.77-0.84 for S, 0.80 for M at 2 m); where hardly a pixel is steep (below 0.5 %: 99.9 %
   of Poland), the relief splits the strata (the Jura's limestone rocks are invisible at 30 m, its
   valleys are not).
2. **The samples' cells**: each sample's 1 km cells with their area inside the search area, the
   share of their lines' partners that lie inside it (Monte Carlo over the cell; cells below 0.5, for
   L 0.3, are left out, the others corrected by it), their lines and spots, their stratum.
   Lauterbrunnen's M band at 2 m takes its 5 m cells scaled to its own totals; Zion's M band at 2 m
   takes its 5 m cells times the median ratio of the places measured at both (26.5 for lines, 3.68
   for spots: Tatras, Lauterbrunnen, Wasatch); Canyonlands' L band at 5 m takes its 10 m cells times
   Lauterbrunnen's ratio (14.8 for lines, 3.09 for spots), until it is measured.
3. **Counts**: per stratum the lines (spots) per effective km² of all cells in it, times the country's
   km² in it; the water inside the outline (the Baltic's territorial sea, the Great Salt Lake) comes
   off the flattest stratum. A stratum without cells takes its neighbour's. The range is the 10th and
   90th percentile of a bootstrap over the places (400 draws of the places with replacement; a band's
   range is taken alone, so a variant's range of several bands is a little wide); "mid" is the plain
   estimate.
4. **Other resolutions**: a band's counts at another grid are scaled by the median ratio of the places
   measured at both (S at 2 and 5 m from S at 1 m, M at 5 m from M at 2 m).
5. **Time**: section 4.4's models; a tile of core C and overlap V computes (C + 2V)² of grid; K tiles
   at once; the pair search keeps the measured threads busy; grids and pairs overlap but for a quarter
   of the shorter; the fastest core of 2-60 km wins.
6. **Download**: volume / min(service, link) or files / requests per minute, whichever is longer,
   plus the index (section 3).

### 7.3 What the numbers can and cannot say

- **The times** are measured on these machines and scale with the tiles; the main uncertainty is the
  M band's lines in big-wall terrain, where the pair search is the cost. Where the bootstrap's range
  is narrow (Poland) the times hold to about ±50 %; where it is wide (Switzerland, Utah), its range is
  the honest answer and the true spread is larger.
- **The counts** depend on where the samples are: eight places stand for three countries. They were
  chosen where highlines are (Tatras, Jura, Lauterbrunnen, Zion, Wasatch) and where they are not
  (lowland, plateau, desert). The strata correct for how much of a country is steep, not for the rock:
  a steep slope of Polish flysch is not Jura limestone, and the Tatras' steepest cells take the
  density of all steep cells (mostly Lauterbrunnen's and Zion's). The bootstrap shows how much the
  places alone move the totals.
- **Spots** are today's groups; a country run would count another kind of spot (6.2), so the spot
  counts here are an order of magnitude, not a forecast.
- **Not measured**: the M band at 1 m and the L band at 2 m (out of reach today), the 5650G on real
  searches (its bench only), other pretensions than T(L).

### 7.4 How to update the estimate

After a change of the search, a new machine or more samples: run the searches of
[country-precompute/samples.sh](country-precompute/samples.sh) again (one at a time under the
exclusive test lock), then `relief` (the Copernicus tiles stay cached) and `estimate`, and rebuild this
report and its page from the estimate: [country-precompute/report/README.md](country-precompute/report/README.md).

## 8. The band study

The Slovak pilot's control band M2 (1-2 km on 2 m at 60°) against the layer's L (5 m at 45°) lost 3.9 % of
the 1 km cells with a spot and cost half as much (`country compare`, 2026-11-03). Before the world is
counted (for now the sources of 2 m or finer), the user chose to measure more variants first
(2026-11-03): data first, the criterion of the choice later. `tools/band_study.py` sets them up and
compares them.

**Areas.** Stage 1 in Slovakia, from the local mirror, with the surface model marking lines over trees
(its 73 GB do not fit for the whole country, a few GB for the squares): the High and Belianske Tatras
(20 km around 49.19, 20.15), Slovenský raj (20 km around 48.93, 20.38), Malá Fatra (20 km around
49.21, 19.05) and Súľovské skaly with Manínska tiesňava (12 km around 49.155, 18.56), each clipped to
the country. Stage 2 counts the variants that pass stage 1 in Lauterbrunnen, Zion, Lysefjord, Gozo
and the Jura or Saxon Switzerland. Each area is a country of its own (`countries/<area>/`), counted by
`findaline.py country run <area>`.

**Bands and pairs.** Every area counts every band; the reference of each length range is its finest
grid at 60°, the current layer's bands (S, M, and L split at 2 km so that each part has its own cost)
are the area's layer bands, so its cube shows the layer as it is.

| Lengths | Reference | Current | Variants |
| --- | --- | --- | --- |
| 30-300 m | S1m60: 1 m, 60° | S1m60 | S2m60: 2 m (sources of 2 m) |
| 300-1000 m | M1m60: 1 m, 60° | M2m60: 2 m, 60° | (the current band; per bin 300-600 and 600-1000 m, so also an S/M edge at 600 m) |
| 1-2 km | L1-2m60: 2 m, 60° (the pilot's M2) | L1-5m45: 5 m, 45° | L1-5m50, L1-5m55: 5 m at 50° and 55°; L1-3m55: 3 m at 55° |
| 2-5 km | L2-5m45: 5 m, 45° | L2-5m45 | L2-10m45: 10 m, 45° |

**What is compared.** The numbers of spots cannot be compared alone: a coarser grid makes other spots
(Zion's 30-300 m lines gave 30 000 spots on 1 m, 42 000 on 2 m and 51 000 on 5 m). `analyse` compares
each variant with its reference by where they lie, over all lines and over the lines not over trees
(the layer's filter, which depends on the surface model's rule on walls, so stage 1 waits for the
user's check of that rule; the obstacle rule is part of a country's hash): the spots of the reference
with a spot of the variant within one 50 m cluster at both ends (recall) and the other way round
(precision), the 1 and 4 km cells with a spot that the variant loses and adds, the Spearman
correlation of spots per cell, per length bin, and the bands' tile seconds, CPU seconds and memory.
It writes `study.json`, `study.md` and a picture of the cells of each pair.

    uv run python tools/band_study.py setup --data-dir <data>
    uv run python findaline.py country run sk-tatry --data-dir <data> --yes   (each area in turn)
    uv run python tools/band_study.py analyse --data-dir <data> --out <folder>
