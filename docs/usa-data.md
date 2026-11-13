# USA: elevation products, coverage and the surface model

What USGS 3DEP offers beyond the 1 m DEM the `usa` source reads today: the lidar DEMs at their original resolution (OPR), the point clouds (LPC) and the ways to get a surface model (DSM). Measured on 2026-11-07/08 after a user reported five US places where expected lines were missing. The fixes are written up as tasks in [tasks-usa.md](tasks-usa.md). What the `usa`, `alaska`, `alaska_ifsar` and `usgs10m` sources do now is in the roadmap, "United States (USGS 3DEP)".

## Summary

- **Terrain.** The 1 m DEM covers 96 % of the land of the conterminous USA (CONUS). OPR DEMs (94 %) and point clouds (95 %) come from the same projects, so they add little: about 2 % of CONUS land has OPR or point clouds but no 1 m DEM. Western Oregon is one such place, and three of the five reported places were there. There the app silently fell back to the 10 m DEM. Alaska has almost no lidar (4–7 % of points) but a statewide IfSAR DTM and DSM.
- **Surface model.** There is no ready national 1 m DSM. Three ways remain:
  - **Our own DSM from the point clouds (best).** The EPT copy on AWS covers 89 % of CONUS land, and a window of 9 km² is read in about 4.5 min (323 MB). The trial at the Oregon cove works, but it needs a filter on height above the terrain: the point cloud has a layer of noise at 400–500 m in class 1 (unclassified), not in the noise classes.
  - **The Planetary Computer DSM (2 m).** It covers 50 % of CONUS land, from projects of 2008–2020, often older than the 1 m DEM. It is an IDW of all points, so it stands a median 3.8 m below our maximum under trees, and it keeps the noise.
  - **Alaska's IfSAR DSM (5 m).** It covers all of Alaska, but only as ZIP files of 0.8–1.6 GB.
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
- The OPR files without a vertical CRS: the vertical unit, checked against the 1 m DEM where both exist.
- The pixel origin of OPR projects other than the Oregon coast.
- Noise in the point clouds of other projects: is the high layer at the cove usual? Is a cap of 100 m above the terrain safe (the tallest trees in the USA reach about 115 m)?
