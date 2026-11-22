# USA: elevation products, coverage and the surface model

What USGS 3DEP offers beyond the 1 m DEM the `usa` source reads today: the lidar DEMs at their original resolution (OPR), the point clouds (LPC) and the ways to get a surface model (DSM). Measured on 2026-11-07/08 after a user reported five US places where expected lines were missing; USGS's table of surveys (WESM) and the Seamless 1 m DEM on 2026-11-22. The fixes are written up as tasks in [tasks-usa.md](tasks-usa.md). What the `usa`, `alaska`, `alaska_ifsar` and `usgs10m` sources do now is in the roadmap, "United States (USGS 3DEP)".

## Summary

- **Terrain.** The 1 m DEM covers 96 % of the land of the conterminous USA (CONUS). OPR DEMs (94 %) and point clouds (95 %) come from the same projects, so they add little: about 2 % of CONUS land has OPR or point clouds but no 1 m DEM. Western Oregon is one such place, and three of the five reported places were there. There the app silently fell back to the 10 m DEM. Alaska has almost no lidar (4–7 % of points) but a statewide IfSAR DTM and DSM.
- **Surface model.** There is no ready national 1 m DSM. Three ways remain:
  - **Our own DSM from the point clouds (best).** The EPT copy on AWS covers 89 % of CONUS land, and a window of 9 km² is read in about 4.5 min (323 MB). The trial at the Oregon cove works, but it needs a filter on height above the terrain: the point cloud has a layer of noise at 400–500 m in class 1 (unclassified), not in the noise classes.
  - **The Planetary Computer DSM (2 m).** It covers 50 % of CONUS land, from projects of 2008–2020, often older than the 1 m DEM. It is an IDW of all points, so it stands a median 3.8 m below our maximum under trees, and it keeps the noise.
  - **Alaska's IfSAR DSM (5 m).** It covers all of Alaska, but only as ZIP files of 0.8–1.6 GB.
- **The table of surveys (WESM).** USGS publishes one row per survey with its dates, pixel size, CRS codes and the status of each product ([below](#wesm-usgss-table-of-surveys)). It names the 357 lidar surveys that have an OPR DEM and no 1 m DEM, and it says which of them are in feet.
- **The Seamless 1 m DEM (S1M) is not used** (the user, 2026-11-22): it is built from the same surveys as the 1 m DEM, beyond them it is backfill from coarser DEMs, and where both exist it is the worse input ([below](#why-the-seamless-1-m-dem-s1m-is-not-used)).
- **Libraries for the point clouds:** laspy 2.7.0 (BSD-2, 2026-01) with lazrs 0.8.2 (MIT, 2026-07). Both have wheels up to Python 3.14 (lazrs 0.8.2 none for 3.15 on 2026-11-13, the Docker image's Python since that day) and no OSV advisories. The PDAL Python package is a source distribution that needs the native PDAL library.

## Coverage of the products

**Method:** a lattice of 1.5° over CONUS (as in the roadmap's count for the 1 m DEM) and of 2° over Alaska, plus six points on the Hawaiian islands. For each point, the TNM Access API was asked for a box of 0.01°.
- A point counts as US land where the 1/3″ DEM has a value there that is not 0. Read from the 1° file at that pixel, not from the product list: a 1° product also covers sea, Mexico and Canada.
- 26 such points in Mexico, Canada and the Great Lakes were removed by hand.
- That leaves 367 points in CONUS and 69 in Alaska.
- A "hit" means a product's footprint intersects the box.

| Product (TNM dataset) | CONUS (367) | Alaska (69) | Hawaii (6) |
| --- | --- | --- | --- |
| 1 m DEM (`Digital Elevation Model (DEM) 1 meter`) | 96 % | 0 % | all 6 |
| OPR DEM (`Original Product Resolution (OPR) Digital Elevation Model (DEM)`) | 94 % | 6 % (partly IfSAR) | not sampled |
| Point cloud (`Lidar Point Cloud (LPC)`) | 95 % | 4 % | all 6 (2017–2020) |
| Any of the three | 98 % | 7 % | all 6 |
| EPT copy on AWS (`usgs-lidar-public`, by its outlines) | 89 % | 6 % | – |
| Planetary Computer `3dep-lidar-dsm` | 50 % (12 points without an answer) | 1 % | – |
| IfSAR DSM (`Ifsar Digital Surface Model (DSM)`) | – | 100 % | – |

- **No lidar at all (8 CONUS points).** Tribal and restricted land: Tohono O'odham, Navajo, Hualapai, Uintah-Ouray, Fort Belknap, the Nevada ranges. Also western Oregon and a patch of Montana, both still in progress.
- **Point clouds or OPR but no 1 m DEM (6–7 points).** Western Oregon (`OR_Western_D23`, `OR_YAMBO_OLC_2010`), South Dakota (`SD_FY17_NRCS_Lidar_QSI_2017_D17`), Montana (`MT_DNRCphase1_2018_C21`), Colorado gaps (`CO_CONMGaps_D24`) and Mississippi (`NRCS_Lauderdale_MS_07m_NPS_LiDAR`). These are the only places where OPR or our own point-cloud work would add terrain.
- **1 m DEM but no point cloud or OPR listed (9–14 points).** The API lists only some products of these projects. This does not matter where the 1 m DEM exists.
- **Same project.** At 321 of 343 points the OPR DEM and the point cloud come from the same project. The point clouds can be paired with the terrain of the same survey.
- **Age of the point clouds.** The newest point cloud at a point is from 2016–2020 at 57 % of the points, and from 2021 or later at 40 %. At 47 % of the points there is more than one project, so a DSM has to be taken from the same project as the terrain.
- **Year of the EPT copy.** At 68 % of the points the newest EPT resource is from the same year as the newest DTM, or one year off. At 17 points it is 6 or more years older. The roadmap's note that it lags (Yosemite 2019, Colorado 2023 missing) still holds in places.

## OPR DEMs: formats

A sample of 30 OPR files, the newest at every 12th point:

| Property | Found |
| --- | --- |
| Resolution | 0.5 m (10), 1 m (13), 2 m (6), 3 m (1) |
| Horizontal units | metre (23), US survey foot (6), foot (1) |
| CRS | mostly NAD83(2011) / UTM; also State Plane in feet (California, Colorado, Kentucky, Illinois, Wisconsin, Michigan), Montana State Plane, Albers (EPSG:6350) |
| Vertical datum | 21 compound CRSs with NAVD88; 9 horizontal only, so the vertical unit has to be assumed (a State Plane in feet may also have heights in feet) |
| Tiles | 0.75–2.5 km, 1–27 MB; one exception, `Eastern_MN_State_LiDAR_Phases_3_4_and_5`: a single 3 m file of 36 351 px (3.4 GB) |
| Layout | GeoTIFF, tiled 256 or 512 px, so they can be read in windows by HTTP range requests like the 1 m DEM |

**Pixel origin.** At the Oregon coast (`CA_West_Coast_LiDAR_2016_B16`, 0.5 m) the pixel edges lie on whole metres. Other projects were not checked.

## WESM: USGS's table of surveys

USGS keeps one table of every lidar and IfSAR survey of 3DEP, the "Work unit Extent Spatial Metadata" (WESM): a row per work unit, which is a survey or one block of a large one. Read in full on 2026-11-22; nothing in the app uses it yet.

- **Where.** `https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/WESM.csv` (2.3 MB, 3308 rows) and, with the outlines, `WESM.gpkg` in the same folder (3.8 GB). Both carried that day's date: USGS says "A new WESM is written almost daily as more lidar projects are processed and published" (https://www.usgs.gov/ngp-standards-and-specifications/3dep-spatial-metadata).
- **Which row a file belongs to.** An OPR file's URL holds `/OPR/Projects/<project>/<workunit>/`, the row's `project` and `workunit`.
- **The 28 columns:** `workunit`, `workunit_id`, `project`, `project_id`, `collect_start`, `collect_end`, `ql`, `spec`, `p_method`, `dem_gsd_meters`, `horiz_crs`, `vert_crs`, `geoid`, then for the point cloud (`lpc_`) and the OPR DEM (`sourcedem_`) a `pub_date`, `update`, `category` and `reason` each, for the 1 m DEM (`onemeter_`) and the seamless DEM (`seamless_`) a `category` and `reason` each, and `lpc_link`, `sourcedem_link`, `metadata_link`.

**What it answers that the files and the TNM API do not, or only one file at a time:**

| Question | Column | Found on 2026-11-22 |
| --- | --- | --- |
| The survey's year | `collect_start`, `collect_end` | Filled for every row with an OPR link. The TNM API gives OPR products the publication date 1899-12-30 (the four files at the Oregon cove), so the year cannot come from there |
| How it was measured | `p_method` | linear-mode lidar 2773, IfSAR 432 (429 of them Alaska), Geiger-mode 60, topobathymetric 32, bathymetric 6, single photon 4, flash 1 |
| The horizontal CRS | `horiz_crs` (an EPSG code) | Among the 357 surveys below: 68 different ones; 2 are not EPSG codes (`102218`, an ESRI code, and `Custom`) |
| The unit of the heights | `vert_crs` (an EPSG code) | 5703 (NAVD88, metres), 6360 (NAVD88, US survey feet), 8228 (NAVD88, feet), and for the islands 6640 to 6642 (metres); a few rows say `Unknown`, `Ellipsoidal` or a local sea level |
| The OPR DEM's pixel | `dem_gsd_meters` | See the table below; empty in 113 rows with an OPR link |
| The point density | `ql` | Of all lidar rows with an OPR link: QL 2 1164, QL 1 801, QL 3 230, QL 0 9 |
| Which products the survey qualifies for | `sourcedem_category`, `onemeter_category`, `seamless_category` | "Meets", "Meets with variance", "Does not meet", "Pending publication" ("Expected to meet" for the OPR DEM), each with a reason |

**The surveys with an OPR DEM and no 1 m DEM.** A lidar row with a `sourcedem_link` whose `onemeter_category` is neither "Meets" nor "Meets with variance":

| | All lidar surveys with an OPR link (2207) | Of them without a 1 m DEM (357) |
| --- | --- | --- |
| Why no 1 m DEM | – | "LPC does not meet" 277; "Pending publication" (awaiting the vertical accuracy assessment) 54; "Source DEM does not meet" 23; others 3 |
| Heights in feet (`vert_crs` 6360 or 8228) | 767 | 184 |
| Vertical CRS unknown, ellipsoidal or local | – | 7 |
| Pixel | finer than 1 m 1118; 1 m 832; over 1 to 2 m 98; over 2 m 46; not given 113 | up to 0.76 m 77; to 1 m 98; to 2 m 97; over 2 m 46; not given 39 |
| Point density | QL 2 1164; QL 1 801; QL 3 230 | QL 3 230; QL 1 78; QL 2 45; other 4 |
| Flown (`collect_end`) | – | 2003 to 2016: 261; 2017 to 2023: 45; 2024 to 2026: 51 |
| Most rows | – | Indiana 70, Illinois 61, Minnesota 37, Kansas 15, Oklahoma 13, Missouri 13, Montana 12, North Carolina 11, Oregon 10 |

- The 277 are mostly old county lidar of the sparsest class. Much of it lies under newer surveys that have a 1 m DEM, so a row of this table does not mean a hole in the 1 m DEM: only the 1 m DEM's own coverage says where OPR adds terrain.
- The 54 pending ones are new surveys whose 1 m DEM USGS has not published yet. Western Oregon's `OR_Western_D23` (2024, 0.5 m) is among them; the Oregon cove's own survey, `CA_WestCoastElNinoUTM10_2016`, is "LPC does not meet".

**What it does not tell:**

- **"Meets" is not "published".** The surveys of 2021 to 2023 at Mount Juneau (`AK_Juneau_Landslide_*_2021`, `AK_SELandslides_2_D22`) are "Meets" or "Meets with variance" for the 1 m DEM, and the TNM API lists no file of the 1 m DEM anywhere in Alaska (0 in the box −170..−130, 54..71.5). A status is a hint; what exists is what the TNM API lists.
- **Where a survey lies.** The CSV has no outlines; they are in the 3.8 GB GeoPackage, or follow from the boxes of the survey's files in the TNM API.
- **The pixel of every file.** At the Oregon cove the files measured 0.5 m (above) and the row says 1 m. Not yet checked survey by survey: a file's header stays the authority.

**Alaska's lidar** is published as OPR only: 53 lidar rows with an OPR link, flown 2013 to 2025, at 0.5 m (22), 1 m (13), 3 feet (9) and 1.5 feet (7), two without a pixel size, QL 1 or QL 2 but for three. They cover Anchorage, the Fairbanks borough, the Matanuska-Susitna borough, Juneau and the south-east (Glacier Bay, Prince of Wales Island, the Tongass landslide surveys), blocks of the North Slope, the Yukon-Kuskokwim delta, Lake Peninsula, the west coast after typhoon Merbok, and native villages. Eleven older surveys (2007 to 2012) have no OPR link.

## Why the Seamless 1 m DEM (S1M) is not used

Decided by the user on 2026-11-22, on the findings below. What S1M is, its file names and how its tiles change: the roadmap, "United States (USGS 3DEP)", *Seamless 1 m DEM*.

**How USGS builds it** (a tile's own metadata, `S1M_<tile>_<date>.xml`, read 2026-11-22):
- "Only lidar projects that were Quality Level 2 (QL2) or better were used as the primary data source." The inputs are those surveys' OPR DEMs ("gathers the Original Product Resolution Source DEMs"), brought to NAVD88 with GEOID18 and to EPSG:6350 (Albers).
- "Large data voids, wider than 10 m, are backfilled with 1/9 arc-second or 1/3 arc-second DEMs", small ones interpolated bilinearly.
- Where surveys meet or a void was backfilled, the heights are blended over 10 m (a linear blend) or 50 m (the "backfill blend").
- Each tile comes with a small GeoPackage (`.gpkg`, 0.1 to 0.3 MB). Its layer `s1m_source_inputs` holds one outline per input with `workunit_name`, `data_type` ("linear-mode lidar", "1/9 Arc Second", …), `source_resolution_meters`, `percent_area`, `priority_rank` and the dates. A second layer, `s1m_blending_area_statistics`, gives the height differences of each pair of blended surveys. So the backfilled areas are marked, per tile.

**It covers no lidar the 1 m DEM lacks.**
- The 1 m DEM is made of the same surveys (QL2 or better). S1M has 17 030 tiles on 2026-11-22 (16 093 on 2026-10-30, 16 665 on 2026-11-14) of about 80 000 for CONUS: the southern Sierra and the California deserts, West Virginia, North Carolina, New York and more, none at Yosemite Valley, Moab, Boulder or the Oregon cove.
- A sample of 151 tiles spread over the whole index, each asked at its centre (the TNM API, a box of 0.01°): 146 have a 1 m DEM there. None has an OPR DEM without a 1 m DEM. Five have neither: two small tiles on the coast (3 and 9 MB), and three whole tiles in central North Carolina.
- One of those three was opened (`n1500e1460`): its only input is `ned19_n35x50_w079x75_nc_statewide_2003`, the 1/9″ DEM (3 m, lidar of 2003), over 100 % of the tile. So where S1M reaches beyond the 1 m DEM, it is the backfill at 1 m pixels, not 1 m lidar.
- WESM's `seamless_category` qualifies the same lidar surveys as `onemeter_category`, but for 2; whether that column means S1M or the older seamless layers was not looked up (Alaska's IfSAR qualifies in it), so it is no evidence either way.

**Where both exist it is the worse input for this app.**
- It is in Albers. The app's working grid is NAD83 UTM, onto which the per-project 1 m DEM is copied pixel for pixel; S1M would be resampled bilinearly, which smooths cliff edges (the sources rule's first pitfall: R2 lost 40 % of its lines to half a pixel of interpolation). How many lines it would cost here was not measured.
- Its heights near a seam are blended, not measured.
- It lags the surveys: Boulder's S1M is from the 2020 survey although 2023 and 2026 exist.
- Its tiles are 250 to 450 MB and are made again under new dated names.
- Putting it first would change every US result.

**What it would give:** one file per place instead of composing the surveys, smoothed seams, one geoid for all heights.

**The one place it has finer data than the app reads today** is its backfill from the 1/9″ DEM where no 1 m DEM exists (central North Carolina in the sample). That DEM is a TNM dataset of its own (`National Elevation Dataset (NED) 1/9 arc-second`, 8128 files in CONUS, zipped `.img` files of 0.25° that cannot be read in windows) and also lies under the Oregon cove and Indian Beach (`or_northcoast_2009`). Whether to read it, as a member between the OPR DEMs and the 1/3″ DEM, is open (not decided, not measured).

**When to look again:** if USGS retires the per-project 1 m DEM in favour of S1M (its pages, read 2026-11-22, say the 1 m dataset "will be expanding as new DEMs from 3DEP quality level 2 or better lidar data are acquired" and name no end), or if S1M tiles built from lidar appear where the 1 m DEM has none.

## Ways to a surface model

### Our own DSM from the point clouds (tested)

**Where the points come from.**
- **TNM's LAZ files.** The download URLs point to `rockyweb.usgs.gov`, which answered **429** to the first request of 2026-11-08, with no `Retry-After`. The same paths on `prd-tnm.s3.amazonaws.com` hold only the metadata of the point clouds.
- **The EPT copy on AWS** (`s3-us-west-2.amazonaws.com/usgs-lidar-public/<name>/ept.json`, outlines in `hobuinc/usgs-lidar` `boundaries/resources.geojson`). It is an octree of LAZ nodes in EPSG:3857. Its resource names differ from TNM's projects (`USGS_LPC_CA_WestCoastElNinoUTM10_2016_LAS_2017` for `CA_West_Coast_LiDAR_2016_B16`, projects split into `_1_`/`_2_` parts), so a resource is matched by its outline and year, not by name.

**The trial at the Oregon cove** (44.7675, −124.0703; a 3 × 3 km box in UTM 10N):
- **Reading.** The hierarchy (11 files) leads to the 1859 nodes over the box: 323 MB of LAZ, 65 million points, 254 s of downloads at 8 connections, plus 20 s to read them with laspy.
- **The DSM.** The highest point per 1 m pixel, classes 7 and 18 left out, on the grid of the OPR DEM of the same survey.
- **Heights.** The EPT's heights are NAVD88: ground points (class 2) minus the OPR DEM have a median of +0.02 m (p5 −0.23, p95 +0.43). The `ept.json` names only the horizontal CRS.
- **Classes.** 75 % of the points are class 1 (unclassified), 11 % class 2 (ground) and 8 % class 9 (water). No vegetation classes: the canopy is in class 1.
- **Noise.** A layer of points at 415–490 m above the sea is in class 1, and isolated filters do not remove it. Without a filter it put 4404 pixels of the cove "more than 100 m above the ground" and marked every line across the cove as over trees (1987 of 1987). A cap of 100 m above the terrain (sea 0 m) removes it all (0 pixels left). After the cap, 1967 of 1987 lines across the cove are clear (14 of 17 groups) and 27 % of all lines pass over trees, which matches the forest on the cliff tops.
- **The app needs no change for this.** The existing obstacle rule (`obstacles.py`: the terrain's envelope, rims) handles the cliff edges. Locally the DSM goes in as `--surface-file` with `--elevation-file`.

**Costs.** Points per km² vary by project, so download sizes vary too. The survey covers about a third of the box (31 % of its pixels have points: the coastal strip and the sea next to it). That is about 23 million points and 115 MB of LAZ per km² it covers. A 1 km circle at that density would be about 360 MB. The DSM itself is small: one float32 per pixel, so 4 MB per km² before compression.

### Planetary Computer `3dep-lidar-dsm`

- **What it is.** 2 m COGs, made with PDAL: `filters.range` drops class 7 only, then `writers.gdal` with `output_type: idw`, `window_size: 3`. So every non-noise point, ground under the trees included, is averaged into the pixel.
- **Access.** The STAC search needs no account. The blobs need a SAS token from `api/sas/v1/token/3dep-lidar-dsm`.
- **CRS.** The files carry a compound CRS (`NAD83 / UTM zone 10N + NAVD88 height`) even though the STAC items name none.
- **Against our DSM at the cove:** under trees (ours at least 3 m above the ground) it stands a median **3.8 m lower** (p10 −8.7, p90 −0.3). It also keeps the noise: over low ground, 9112 pixels stand more than 20 m above it and 689 more than 100 m.
- **Coverage.** 50 % of CONUS land points, from projects of 2008–2020; it ends with 2020. At the points where both exist, its newest project is 6 or more years older than the newest DTM at 56 of 183 points.
- **Use.** At most a fallback where neither the EPT copy nor the LAZ files can be read, and only for the "over trees" flag. Its height under trees is too low for the clearance margin.

### Alaska: the IfSAR DSM

- **Coverage.** The `Ifsar Digital Surface Model (DSM)` covers all 69 Alaska points: 281 cells of 2010–2019.
- **Files.** It exists only as ZIPs on `prd-tnm` (`StagedProducts/Elevation/DSM/TIFF/<cell>/TIFF/...zip`), a median of 818 MB and up to 1.6 GB, with no COG. Deflate cannot be read at random, so a search would download whole cells.
- **Quality.** It is a radar surface at 5 m, with the same limits as the IfSAR DTM (lines under about 30 m are not reliable).
- **Use.** Worth it only as a cached layer that is downloaded once per cell and cut into tiles, like the Slovak national ZIPs.

### Other options (from the roadmap, unchanged)

- **CHMv2** canopy heights: a flag only.
- **State DSMs:** Utah, Kentucky, Washington's portal.
- **OpenTopography:** academic or limited keys.

## What the five reported places showed

| Place | Data | What was missing and why |
| --- | --- | --- |
| Oregon cove, two points (44.7669, −124.0693; 44.7680, −124.0714) | no 1 m DEM: the app used the 10 m DEM | On the OPR lidar the lines across the cove (200–250 m, sag 250–300 m) and at the inlet (40–120 m) appear. On 10 m data neither a lower slope threshold (20°) nor `--end-zone` brings them back. |
| Indian Beach, Ecola (45.9307, −123.9796) | no 1 m DEM (it starts 6 km east) | On lidar the headland west of the point has lines up to 200 m (formula), up to 700–900 m (sag). On 10 m data nothing, once the Overpass coastline is used. A first run with Copernicus's water mask as the fallback coastline gave 4 lines. |
| Hole in the Ground (43.4105, −121.1978) | 1 m DEM (`OR_SouthEast_D22`) | The default sag rig (2.5 kN, 70 g/m, 5 %) is too soft for 1 km. Lines of 1044–1099 m appear from 4 kN with the default webbing, or already at 2.5 kN with Silk 99 (41 g/m, 2.1 %), at 1 m, 2 m and 5 m alike. The formula never finds them: the rim has no vertical lip. |
| Reservoir bluff, Missouri (38.2543, −93.4273) | 1 m DEM (`MO_7County_D23`) | A low bluff (10–25 m) with rounded edges. `--end-zone 5` gives the 16–49 m lines, 220–400 m east of the point. |

**Hole in the Ground at 2 m** (sag, `--max-length 1500`, `--resolution 2`):

| Rig | Lines | ≥ 1 km | Longest |
| --- | --- | --- | --- |
| default (2.5 kN) | 97 | 0 | 534 m |
| default webbing, 4 kN | 17 484 | 6603 | 1099 m |
| default webbing, 6 kN | 30 699 | 11 835 | 1099 m |
| Silk 99, T(L) | 26 124 | 11 181 | 1099 m |
| Silk 99, T(L), slope threshold 60° (the country band M2) | 6991 | 3192 | 1077 m |
| Silk 99, T(L), at 5 m | 2526 | 740 | 1072 m |

**2 m against 1 m.** 2 m finds the same 1 km lines as 1 m, a little longer (1099 against 1068 m) and in more groups. The 2 m slope over two pixels reaches the outcrops of the west wall more easily.

## Open questions

- Is rockyweb's 429 a lasting block of automated downloads or a short limit? Its terms and limits are not yet looked up (docs/data-sources.md, the row on usage limits). USGS's contact for TNM is tnm_help@usgs.gov.
- The EPT copy against TNM's projects: which newer projects are missing, by outline and year. Its own limits on requests are not known.
- The OPR files without a vertical CRS: WESM names each survey's vertical CRS, and with it the unit; whether it holds for the files is still to be checked against the 1/3″ DEM.
- The pixel origin of OPR projects other than the Oregon coast.
- Noise in the point clouds of other projects: is the high layer at the cove usual? Is a cap of 100 m above the terrain safe (the tallest trees in the USA reach about 115 m)?
