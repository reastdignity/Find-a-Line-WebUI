# Tasks: lines missed in the USA

Five tasks that fix what a user's report of five US places showed (measurements and background: [usa-data.md](usa-data.md)). Each task is meant to be handed to one session or agent as it stands. Each runs on its own branch from `main`, under the rules of CLAUDE.md: test lock, regression set, sync pairs, and a decision on migrating stored data. The order is a suggestion. 1–3 are small and independent; 4 and 5 are larger, and 5 builds on what 4 learns about TNM projects.

The places, as regression candidates (the next free ids from R65):

| Id | Place | Centre | What it checks |
| --- | --- | --- | --- |
| R65 | Oregon cove (Otter Crest) | 44.767488, −124.070346 | no 1 m DEM; terrain from OPR (task 4); trees from the point cloud (task 5) |
| R66 | Hole in the Ground, Oregon | 43.410471, −121.197848, `--max-length 1500` | 1 km lines with the sag model (task 2) |
| R67 | Reservoir bluff, Missouri | 38.254301, −93.427283, `--min-length 15` | short lines on a rounded bluff (task 3) |

Indian Beach (45.930699, −123.979594) is a second check for task 4. It is not a regression case: its result depends on the coastline (Overpass against the Copernicus fallback).

---

## Task 1: say when the terrain came from a fallback

**Goal.** A user sees, in the run's messages, `run.json` and the map, when most of the search area's terrain comes from a coarser fallback layer, not from the source the run names.

**Why.**
- At the Oregon cove the run said `Data: USGS 3DEP (1 m DEM)` and saved that source in `run.json`.
- The only hint that all of it came from the 1/3″ DEM (10 m) was the line `Elevation data: 0.00% of the search area from USGS 3DEP (1 m DEM)`.
- Three of the five reported places were this case. The report would have explained itself.

**Where.**
- `search.py` around the `Elevation data:` message (`prepare_data`, about line 969): `with_data` is the share of the main layer. Gap filling reports its own km² later (`Filled … km² of gaps in the data from …`).
- `messages.Note` (the `no_surface` warning in the same function is the pattern), `locales/en.json`.
- `run.json`'s `source` and `data` (`search.save_run`, `_merged_data`), and the result view's notices in `viewer/src`.
- `sources/choose.py`: `instead_without_data` (used by `alaska`, which switches to `alaska_ifsar` when `has_data_near` finds no 1 m data within 2 km).

**Decisions for the user.**
1. **The threshold for the warning**, e.g. less than 50 % of the area's land from the main layer. Should it hold for every source or only for sources with a much coarser fallback?
2. **Should `usa` also get `instead_without_data="usgs10m"`?** A centre with no 1 m data within 2 km would then be named honestly as the 1/3″ source. The run's notes and its resolution limits would then fit. Task 4 changes the answer for places with OPR.
3. **The warning's wording and where it shows**: messages only, or also the map's notices and the run list.

**Steps.**
1. Compute the share of the area's land from the main layer and from each filler.
2. Emit a `messages.Note` with its own code when the main layer's share is under the threshold.
3. Record the shares in `run.json` (a new field: decide whether the viewer reads it).
4. On the public site the text goes through `Jobs(public=True)` like the other notes.

**Stored data.** A new optional field in `run.json`, read only when present. Older runs show nothing, so no migration (state it in the commit).

**Sync.**
- `run.json`/`data.js` against `viewer/src/types.ts` if the map shows it.
- `locales/en.json` is bundled into `app.js`, so rebuild `viewer/dist`.

**Verification.**
- The cove (R65's centre) shows the warning with about 0 % from the 1 m DEM.
- R22–R24 show none.
- `pytest`; a unit test with a grid partly without data.

---

## Task 2: a sag rig that fits long lines

**Goal.** The sag model's default rig, or a preset, finds the 1 km lines that are rigged in reality, and agrees with the country precompute.

**Why.**
- At Hole in the Ground the default rig (2.5 kN, 70 g/m, 5 % stretch) finds at most 558 m (1 m grid) or 534 m (2 m).
- With the rig of the country precompute (`country.COUNTRIES["slovakia"]`: T(L) = 2.5 kN at 300 m, 6 kN at 1500 m, 15 kN at 5000 m; Silk 99, 41 g/m, 2.1 %) it finds parallel lines of 1044–1099 m: 8357 lines of at least 1 km at 1 m, 11 181 at 2 m.
- Each half alone is enough: the default webbing from 4 kN (3 kN: at most 790 m), or Silk 99 at 2.5 kN.
- Tension was tested only up to 6 kN.

**Where.**
- `params.py`: `pretension`, `stretch`, `webbing_weight` (`rigging` topic, `PRESETS`/`PRESET_FIELDS` for the form's presets).
- `sag.py`: `TensionTable`, `tension_at`. It is used today only by `country.tension_table`, while `search._sag_table` builds an `EnvelopeTable` with one pretension.
- `search._lines`/`_sag_table`, `lineprofiles`, `profile_of_line`: profiles must use the same table.
- `viewer/src/sag.ts` and `Profile.tsx`: the profile in the map.
- `web.schema`, `settings.Limits`/`BOUNDS` for any new field; README's options table.

**Decisions for the user.**
1. **Defaults or a preset?** Change the sag defaults to T(L) and Silk 99 for everyone (the regression checksums of every sag case change: R3, R5, R16, …), or add a rig preset ("long lines") and keep the defaults?
2. **T(L) as a field?** A list of (span, kN) points in the form and CLI (`--tension 300:2.5,1500:6,5000:15`), or fixed in code like the country precompute?
3. **Webbing.** Silk 99 only, or a choice of a few webbings by name (weight and stretch)?
4. **The limit on tension** in `BOUNDS` for the public site (6 kN was the highest tested).

**Steps.**
1. Let a search build a `TensionTable` when T(L) is given (`search._sag_table` keyed by it).
2. Make the profile code use it (`lineprofiles`, `profile_of_line`, run.json's `params.rigging`).
3. Give `viewer/src/sag.ts` the same T(L): the profile in the map must match Python to 1e-6 m (`tests/test_viewer.py`).
4. Then the form, CLI, README and limits.

**Stored data.** `run.json`'s `params.rigging` gets T(L). A profile of an older run uses its single pretension as before. No migration.

**Sync.**
- `sag.py` with `viewer/src/sag.ts`.
- `params.py` help with README.
- `settings.Limits` with README's limits table and the form.
- `PUBLIC` defaults.

**Verification.**
- R66 finds lines of at least 1 km with the new rig and none with the old one.
- The sag cases of the regression set keep their checksums if the defaults stay (decision 1).
- `tests/test_viewer.py` for the solver pair.

---

## Task 3: point to the end zone when edges are rounded

**Goal.** When a search finds nothing (or nothing near the centre) because no anchor has free space below it, the user learns that `--end-zone` and `--anchor-lift` exist for such edges.

**Why.**
- On the Missouri bluff the formula found nothing. `--end-zone 5` gives 16–49 m lines; `--anchor-lift 1` alone gives nothing.
- At Hole in the Ground the sag model with the default rig finds 558 m. With `--end-zone 5` and the country rig it finds 1.7 million lines (up to 1118 m).
- The log shows the cause, but only in numbers: `Anchors with an open direction: 45 of 5480`.

**Where.**
- `search._lines` (the `no_lines` `SearchError`) and the funnel counts (`_count`, `plan.funnel`: anchors, anchors with an open direction, pairs).
- `locales/en.json` `error.no_lines`, `messages.py`; the README section on the clearance and the end zone.

**Decisions for the user.**
1. **When the hint shows**: only on "no lines", or also when few anchors have an open direction (e.g. under 5 %)?
2. **Should the hint also name the sag model?** It found lines at every one of the five places where the formula found fewer or none.
3. **On the public site** `--end-zone` is capped at 5 m (`END_ZONE_MAX`). Raise it after measuring the cost (the end zone multiplies the pairs: 13 million candidate pairs at the crater against 0.4 million)?

**Steps.**
1. Give `no_lines` a second form, or a separate `Note`, when the share of anchors with an open direction is low.
2. Pass the counts as message parameters, like `shore_uncertain` does.
3. Test it on the bluff (R67) and in a unit test with a synthetic rounded rim.

**Stored data.** None.

**Sync.** `locales/en.json` is bundled, so rebuild `viewer/dist`.

**Verification.**
- R67 without `--end-zone` gives the hint; with `--end-zone 5` it gives its lines (record the numbers).
- `tests/test_web.py`: the error text reaches the page through `Jobs(public=True)`.

---

## Task 4: OPR DEMs as a terrain layer of the `usa` source

**Goal.** Where USGS has lidar but no 1 m DEM (about 2 % of CONUS land, including western Oregon), the `usa` source reads the OPR DEM before falling back to the 1/3″ DEM.

**Why.**
- At the Oregon cove and at Indian Beach the app used the 10 m DEM.
- The OPR lidar of the same places (`CA_West_Coast_LiDAR_2016_B16`, 0.5 m) shows the reported lines: across the cove 200–250 m (formula) and 250–300 m (sag), 40–120 m at the inlet, and on Indian Beach's headland.
- On the 10 m DEM no setting brings them back.

**Where.**
- `sources/layers/tnm.py`: `TnmBlocks`, `Usgs1mBlocks`, `IfsarBlocks` (an `IndexedTiles` over the TNM Access API, blocks cached on a fixed grid per file CRS, projects composed per block, newest first).
- `sources/catalogue/usa.py`: the `usa` source, `fallback`/`more_fallbacks`, `instead_without_data`.
- `sources/filling.py` `fill_gaps_chain`. `sources/indexes/listings.py` `TnmProducts` (recorded answers in `tests/data/recorded/`, `tools/record_answers.py`).

**What the data looks like** (usa-data.md, "OPR DEMs: formats"):
- 0.5–3 m.
- UTM in metres, but also State Plane in US survey feet and Albers.
- 9 of 30 files have no vertical CRS.
- Tiles of 0.75–2.5 km and 1–27 MB. One 3.4 GB file (eastern Minnesota).
- All tiled GeoTIFFs, so window reads work.

**Decisions for the user.**
1. **An OPR layer in the fallback chain** (`usa`: 1 m → OPR → 1/3″) or only where the 1 m layer has no data? Keep the 1 m DEM first wherever it exists?
2. **Projects not in metres or not in UTM**: resample them (bilinear onto the UTM working grid, with feet converted), or skip them in the first version and accept the gap?
3. **Files without a vertical CRS**: assume NAVD88 in the horizontal unit, or check each project against the 1/3″ DEM first and refuse it on a large offset?
4. **The block size and cache layout**: `usa/opr/<epsg>/...` like `usa/3dep-1m`? It is a new cache folder, so no migration (`cache/LAYOUT` unchanged if only a folder is added: check `cache.py`).

**Steps.**
1. An `OprBlocks` layer on `TnmBlocks`:
   - the dataset name;
   - the year from the project name (`_survey_year`);
   - the CRS and units read from each file;
   - blocks in the file's CRS, resampled onto the working grid when it differs.
2. Recorded TNM answers for the tests.
3. The data checks of CLAUDE.md for a new source:
   - georeference against Copernicus (shift search);
   - share of valid pixels at 5 m;
   - a few tiles against the files.
4. One check per kind of CRS: UTM metres, State Plane feet, Albers.
5. R65 (the cove) as a regression case; Indian Beach as a manual check.

**Stored data.** A new cache folder. Runs record the files read (`source_files`). No migration.

**Sync.** The README sources table (`ReadmeRow`) and the about page are built from `SOURCES` credits: check that the OPR credit appears.

**Verification.**
- R65 on an empty cache: the terrain from OPR (the warning of task 1 does not fire), lines across the cove as measured.
- R22–R24 unchanged, checksums included.
- `pytest` offline with recorded answers.

---

## Task 5: a surface model for the USA from the point clouds

**Goal.** US runs mark lines over trees and buildings, as runs elsewhere do. The surface model is computed from the 3DEP point clouds of the same project as the terrain.

**Why.**
- The `usa` source has no DSM, so a line over forest counts as clear.
- At the Oregon cove 27 % of the lines (formula) pass over trees on the cliff tops.
- A trial DSM from the EPT copy, used with `--surface-file`, marks them correctly with the existing obstacle rule. The lines across the cove stay clear (1967 of 1987).

**What the trial showed** (usa-data.md, "Our own DSM from the point clouds"):
- **Reading.** EPT on AWS (`usgs-lidar-public`) covers 89 % of CONUS land. 9 km² took 323 MB and 4.5 min at 8 connections.
- **Matching.** The resource names differ from TNM's projects, so a resource is matched by its outline (`hobuinc/usgs-lidar` `resources.geojson`) and year.
- **Heights.** NAVD88 like the DEMs (ground minus OPR: median +0.02 m).
- **Classes.** The vegetation is in class 1 (unclassified), so the DSM takes every class except 7 and 18.
- **Noise.** A noise layer at 415–490 m above the sea was in class 1. A cap of 100 m above the terrain removed it; without it every line across the cove was "over trees".
- **TNM's LAZ files** (`rockyweb.usgs.gov`) answered 429 at once.
- **The Planetary Computer DSM** is 3.8 m too low under trees (IDW of all points) and keeps the noise: a fallback at most.

**Where.**
- A new layer kind in `sources/layers/` (points to raster).
- `sources/catalogue/usa.py` (`nmpt=` of `usa`).
- `obstacles.py` (unchanged rule), `search.prepare_data` (the surface is prepared like other layers).
- `net.HOST_SLOTS_OF`/`HOST_RATES_OF` for the AWS host.
- `pyproject.toml`/`uv.lock` (laspy, lazrs), the Dockerfile (wheels up to cp314; the image is 3.13).

**Decisions for the user.**
1. **The library.** laspy 2.7.0 + lazrs 0.8.2 (pure pip, wheels up to cp314, no OSV advisories), or PDAL (needs the native library: conda or a system package; it has `readers.ept` and filters ready)? The CLAUDE.md rule "libraries first" asks for the comparison: laspy reads the nodes, and our code walks the EPT hierarchy (about 60 lines in the trial).
2. **The source of the points.** EPT on AWS only, or also TNM's LAZ files where EPT lacks a project (after asking USGS about rockyweb's 429)?
3. **The DSM rule.** The highest point per pixel, classes 7/18 out, capped at N m above the terrain: N = 100 m as in the trial, or 120 m (coast redwoods reach about 115 m)? A minimum number of points per pixel against single birds?
4. **The cache.** Store only the computed DSM blocks (about 4 MB per km² before compression) and delete the LAZ nodes after use, as the roadmap planned?
5. **Alaska.** The IfSAR DSM (5 m, ZIPs of 0.8–1.6 GB per cell) as a cached layer later, or not at all?
6. **The public site.** The point downloads are heavy (hundreds of MB per km² in dense projects), so a quota (`download_mb_day_max` exists) or a smaller limit for US surface areas?

**Steps.**
1. An index from the EPT outlines, cached per 0.25° tile like the TNM answers, with the year from the name.
2. Pair the resource with the terrain's project. Refuse a pair whose years differ by more than one, since two surveys make false obstacles.
3. Read the nodes over each block in parallel, under a host limit.
4. Build the capped maximum on the working grid, then cache the block.
5. The data checks:
   - ground points against the 1 m DEM (median near 0);
   - the canopy share against CHMv2 on gentle ground (roadmap, "CHMv2");
   - a forested and a bare place.
6. R65 with the surface: record how many lines are over trees.

**Stored data.** A new cache folder for the DSM blocks. Runs gain the surface layer in `data`. No migration.

**Sync.**
- README's sources table and the note `USA_NOTE` ("no surface model for the USA yet") change.
- The privacy and about pages are built from `SOURCES`.
- `docs/deployment.md` if the image needs a system library: no, if laspy/lazrs are chosen. Check with `ldd` as CLAUDE.md asks after a dependency change.

**Verification.**
- R65: the same lines as without the surface, over-trees counts as in the trial (about 27 % formula).
- R22 (Yosemite, forest below the walls) as a second check.
- `pytest` offline with a small recorded EPT node set in `tests/data`.
