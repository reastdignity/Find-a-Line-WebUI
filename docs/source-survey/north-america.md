# Elevation sources: North America (survey of 2026-10-31)

Notes of the survey in [../source-survey.md](../source-survey.md), one section per group of countries as researched; the rows are in [sources.json](sources.json).

## Canada (g8-ca): elevation sources, researched 2026-10-31

Scripts: `scripts/g8-ca/` (`stac_query.py`, `cog_window.py`, `places_coverage.py`, `list_projects.py`, `gpkg_peek.py`, `imageserver_export.py`, `write_json.py`). Samples: `dl/g8-ca/` (the hrdem-lidar item list `hrdem-lidar-items.json`, the HRDEM spec and guide PDFs, `fp/Datasets_Footprints.zip`, two ImageServer exports, one ortho JPEG).

**Summary.** NRCan's federal STAC already holds the open lidar of every province and territory: 950 projects from AB, BC, MB, NB, NL, NS, NU, NWT, ON, PEI, QC, SK, YT, Parks Canada, cities and NRCan's own flood-hazard projects (FHIMP). Each has a DTM and a DSM, as COGs on a public S3 bucket. So **one driver could serve most of Canada**. Provincial services add native-CRS files (BC), 0.5 m resolution (Ontario) or a newer province-wide DSM (NB). Only BC's files have been read in windows so far; Ontario and NB were tested through their ImageServers. The catch: every federal COG is reprojected into EPSG:3979 (Canada Atlas Lambert), so the data has been resampled once already. The native UTM tiles sit only on a very slow legacy FTP server.

### ca: federal (NRCan CanElevation: HRDEM, HRDEM Mosaic, MRDEM-30)
- **Data**
  - *HRDEM DTM and DSM* from airborne lidar, 1 m (2 m where the pulse density is below 2 pts/m²). Distributed by project, with "no integration or edge-matching done between projects" (spec 3.3).
  - *Projects*: 950 in collection `hrdem-lidar`, acquired 2005–2025:
    - provinces: QC 270, ON 123, SK 70, MB 49, BC 48, AB 43, NB 40, NS 28, PEI 2, NL 3;
    - territories: YT 40, NWT 27, NU 23;
    - others: NRCAN 136, Parks Canada 5, AAFC 11, cities, conservation authorities.
  - *HRDEM Mosaic* (`hrdem-mosaic-1m`, `hrdem-mosaic-2m`): one DTM and DSM per 500 km tile in EPSG:3979. "In case of overlap between data sources, pixel values are set according to the most recent source." The 2 m mosaic adds the ArcticDEM-derived 2 m DSM in the north (DSM only there).
  - *MRDEM-30*: one DTM, DSM and "source" COG for the whole country, 30 m, published 2026-06.
  - *CDEM/CDSM* are marked legacy.
- **Status**: the acquisition plan has two parts. South of the "productive forest line", lidar is gathered through partnerships, so coverage is patchy but growing; north of it, a 2 m DSM from optical imagery (spec Fig. 1). Projects keep arriving (2025 items exist; mosaic tile 2_4 was rebuilt on 2026-10-26).
- **Access**
  - STAC API `https://datacube.services.geo.ca/stac/api`. Items carry a `proj:*` transform, and the item geometry is the project's footprint MultiPolygon. Each item has assets `dtm`, `dsm` (COG), `*-vrt`, `coverage` (GPKG, one valid-data polygon), `extent` and `thumbnail`.
  - Files on `https://canelevation-dem.s3.ca-central-1.amazonaws.com/`: COG, float32, LZW, 512 px blocks, overviews, nodata -32767. A project file is 1–2 GB (Squamish 2016: 1.85 GB); a 1 m mosaic tile is 152.7 GB. Window reads only.
  - Legacy distribution of the original UTM 10 km tiles (20 km for 2 m): `https://ftp.maps.canada.ca/pub/elevation/dem_mne/highresolution_hauteresolution/{dtm_mnt|dsm_mns}/{1m|2m}/<provider>/<project>/utm<zone>/dtm_1m_utm<zone>_<e|w>_<x>_<y>.tif`.
    - Index: `Datasets_Footprints.zip`, a shapefile of 43 169 datasets with direct URLs, and `Projects_Footprints.zip`.
    - The index's URLs point to `download-telecharger.services.geo.ca`, which answers 403; the files are on `ftp.maps.canada.ca`.
    - The tiles are strip TIFFs (one row per strip, LZW, 10000 × 10000 px, about 100 MB).
    - The server is very slow: 12 s to the first byte, about 40 kB/s.
- **Versions**
  - Like the USA: several projects per place, each covering part of the others. Squamish has 3 (2016, 2018/19, 2020), Saguenay 5, Fundy 5, Bon Echo 4.
  - At Stawamus Chief the 2016 project is 72% valid in a 1 km window, while the mosaic is 100% valid (newer projects fill the rest).
  - The mosaic resolves the versions itself (newest per pixel), but gives no per-pixel source or year, and it is rebuilt in place. A cache key would come from the item's `updated` or the file's ETag.
- **Licence**: Open Government Licence – Canada 2.0 ("You are free to copy, modify, publish, translate, adapt, distribute or otherwise use the Information in any medium, mode or format for any lawful purpose"). Attribution: "Contains information licensed under the Open Government Licence – Canada." Commercial use and redistribution are allowed. https://open.canada.ca/en/open-government-licence-canada
- **CRS / heights**: EPSG:3979, 1 m pixels with edges on whole metres. Heights are CGVD2013 orthometric (EPSG:6647). Values are not on whole centimetres (0.3%), a sign of resampling when the projects were reprojected from UTM/MTM. The method is not stated.
- **Orthophoto**: no national orthophoto service. Ontario's ImageServer was tested (see ca-on). The STAC has only small imagery collections (Banff 2025, NAPL air photos).
- **Quick tests (2026-10-31)**
  - STAC: 52 collections; `hrdem-lidar` listed in full (950 items, 10 pages, 16 s); a bbox query takes 0.7 s.
  - 1 km windows at Stawamus Chief:
    - mosaic-1m DTM and DSM: 1.7 s each, 100% valid;
    - project COG: 1.9 s.
  - 600 m windows of the mosaic at 19 places:
    - 100% valid at Squamish, Bon Echo, Val-David, Saguenay (Cap Trinité), Percé, Signal Hill, Fundy, PEI, Skaha, Whitehorse, Yellowknife, Winnipeg, Regina, and at Lion's Head on land;
    - 95% at Canmore (Ha Ling) and 70% at Cape Breton (sea in the window);
    - 0% at Kananaskis (Barrier Lake) and inland Gros Morne (Western Brook Pond): no lidar project there;
    - Iqaluit: 0% in the 1 m mosaic; the 2 m DSM is 100% valid.
  - MRDEM-30 COG (83.9 GB) read at Gros Morne in 1.0 s.
  - Legacy UTM tile: 2 MB took 54 s; a 1 km window did not finish within 300 s.
- **Fit**: options for the user to decide.
  1. **Mosaic as a fixed grid of huge COGs** (a `DegreeBlocks`-like subclass on the 500 km grid of EPSG:3979, blocks cached, the version key from `updated` or ETag).
     - For: simplest, and newest-per-pixel is already done.
     - Against: no source years; the whole tile changes when NRCan rebuilds it.
  2. **Projects through STAC, composed newest first** (`TnmBlocks` pattern: StacTiles-style index per 0.25° tile + block reads of each project COG).
     - For: years and source files known per block, as for the USA.
     - Against: more code; no gain over the mosaic in pixels.
  3. **Legacy native UTM tiles**: no resampling, but the server is too slow for on-demand use, and the index's host gives 403.
- **Working grid** for options 1 and 2:
  - EPSG:3979 itself copies the blocks as they are, but its scale factor is 0.97 at 60–64° N, 0.99–1.00 at 49–51° N and 1.018 at 45° N. Lengths in grid units would then be off by up to 3%, unless the code accounts for the scale.
  - Resampling to NAD83(CSRS)/UTM means a second resampling.
- **Gap filler**: MRDEM-30 (OGL-Canada, one COG for the whole country) could replace FABDEM (CC BY-NC-SA). Runs would then stay under one open licence, as the USA's 1/3″ DEM keeps US runs public domain.
- **Open questions**
  - The resampling method of the EPSG:3979 COGs: compare a window with a LidarBC native-UTM file (row ca-bc) and with the slow FTP tile.
  - The shift against Copernicus.
  - Whether NRCan publishes per-pixel source information for the mosaic.
  - Fair-use expectations for the S3 bucket (none found).
- **Links**: https://datacube.services.geo.ca/stac/api/collections, https://ftp.maps.canada.ca/pub/elevation/dem_mne/highresolution_hauteresolution/HRDEM_Product_Specification.pdf (edition 1.7, 2026-05-19), HRDEM_Download_Instructions.pdf (same folder), https://open.canada.ca/en/open-government-licence-canada

### ca-bc: British Columbia (LidarBC, GeoBC)
- **Data**
  - DEM (bare earth) at 1 m per BCGS 1:20 000 sheet and survey year, 2016–2025; 100 526 DEM tiles in the index.
  - DSM for some projects (`dsm/` folders: 2016 many files, 2019 only 6 in 092G).
  - Point clouds and orthophoto folders per project.
- **Access**
  - Public S3-compatible bucket `https://nrs.objectstore.gov.bc.ca/gdwuts/`, listing allowed. Layout: `<NTS block>/<250k sheet>/<year>/{dem,dsm,pointcloud,orthophoto}/bc_<sheet>_<x..1m>_utm<zone>_<date>.tif`.
  - Index: shapefiles in `gdwuts/index/` (`lidar_dem_index_112720.shp`, EPSG:3005, fields `s3Url`, `year`, `maptile`, `oper_name`). The DEM index's dbf is 284 MB, updated 2026-09-15.
  - KMLs of coverage per programme.
- **Files**:
  - GeoTIFF float32, tiled 512 px, DEFLATE, some with overviews, 26–540 MB, in NAD83(CSRS) UTM (EPSG:3157 at Squamish), pixel edges on whole metres.
  - The 2016 file holds centimetres and is tagged `AREA_OR_POINT=Point`, though its transform is integral: check the half-pixel question.
  - The 2019 file is not on centimetres. Nodata is -9999 or -32767.
- **Versions**: several surveys per sheet, each covering part of it. Sheet 092g065 at the Chief has 2016 (NDMP Fraser), 2018 (BCTS Chinook) and 2019 (NDMP VI), 74–79% valid each in a 1 km window: the US composing pattern again.
- **Licence**: Open Government Licence – British Columbia (attribution "Contains information licensed under the Open Government Licence – British Columbia"); commercial use and redistribution allowed.
- **Orthophoto**: none found as an open tile service (maps.gov.bc.ca `web_mercator_cache` is a basemap). The LidarBC per-project orthophoto folders were not tested.
- **Quick tests (2026-10-31)**:
  - bucket listing works;
  - the DEM index read through `/vsicurl/` with a 600 m bbox took 66 s (3 tiles);
  - window reads of the 2019 (60 MB) and 2016 (26 MB) tiles took 2.4 s and 1.6 s per 1 km.
- **Fit**: `TnmBlocks`-like (index from the BC shapefile, cached per 0.25° tile; window reads; composed newest first; native UTM, no reprojection). It is an alternative to the federal copy in BC: native pixels and centimetre values, maybe more projects. Not checked: how many of BC's projects are missing from the federal 48.
- **Open questions**:
  - vertical datum per project (CGVD28 vs CGVD2013);
  - the `Point` tag;
  - whether the DSM covers the Sea-to-Sky.
- **Links**: https://nrs.objectstore.gov.bc.ca/gdwuts/index/ , https://www2.gov.bc.ca/gov/content/data/policy-standards/open-data/open-government-licence-bc

### ca-ab: Alberta
- **Data**: provincial lidar is licensed, not open (GeoDiscover Alberta). NRCan has bought open licences for existing lidar (ACAN notices for surveys of 2013–2015 and 2022). The federal collection has 43 AB projects, 2015–2023.
- **Coverage at test places**: Canmore (AB-Upper_Bow_River 2015 and BC East Kootenay 2015) 95% valid; Kananaskis (Barrier Lake) none.
- **Also**: ABMI publishes its own 1 m bare-earth DEM tiles.
- **Fit**: the federal source.

### ca-sk, ca-mb, ca-pe: federal only (prairies, PEI)
- SK has 70 federal projects (2012–2025), MB 49 (2006–2025; MLI also publishes per-project DEM grids, not tested), PEI two island-wide surveys (2008, 2020).
- Few cliffs. Mosaic 100% valid at Regina, Winnipeg and Cavendish. Fit: federal.

### ca-on: Ontario (Geospatial Ontario)
- **Data**:
  - Ontario DTM and DSM (Lidar-Derived) at 0.5 m, 2014–2024;
  - FRI_DTM_SPL / FRI_DSM_SPL (single-photon lidar of the forest inventory);
  - provincial imagery-derived DEMs.
  - 1 km tiles are also downloadable as ZIP packages from GeoHub.
- **Access**: ArcGIS ImageServers at `https://ws.geoservices.lrc.gov.on.ca/arcgis5/rest/services/Elevation/` (`Ontario_DTM_LidarDerived`, `Ontario_DSM_LidarDerived`, `FRI_DTM_SPL`, `FRI_DSM_SPL`, ...).
  - Capabilities: Catalog, Pixels, Download, Image; up to 30 000 px.
  - The service CRS is EPSG:3857 with CGVD2013 heights; exports come in any CRS.
  - The catalog gives each source raster's project and years.
  - The default mosaic method is NorthWest, not newest: a request would need `mosaicRule` ByAttribute (year).
- **Licence**: Open Government Licence – Ontario. The ImageServer itself has no terms of use.
- **Orthophoto**: `AerialImagery/GEO_Imagery_Data_Service_2023to2027` ImageServer, 0.16 m pixels. One 500 m export was sharp with no watermark. Licence unclear (GEO imagery programme).
- **Quick tests (2026-10-31)** at Mazinaw Rock (Bon Echo):
  - catalog 0.8 s: Eastern Ontario 2021-22 (0.5 m) and Belleville 2022;
  - exportImage of 500 × 500 m at 0.5 m in EPSG:2959: 3.0 s, 4.2 MB float32, 100% valid, 55% of values on whole cm.
- **Fit**: a new ImageServer driver (`WcsTiles`-like requests on a UTM grid at native 0.5 m) for the 0.5 m data. The alternative is the federal copy (123 ON projects at 1 m, including Bruce Peninsula 2023 and Perth 2024).
- **Open questions**:
  - the server's resampling and mosaicking against a package tile;
  - the terms for automated use;
  - the ortho licence.

### ca-qc: Quebec (MRNF)
- **Data**:
  - MNT 1 m per 1:20 000 sheet, nearly all of Quebec south of 52° N, 2007–2025;
  - no provincial MNS found: the federal 270 QC projects carry an NRCan-made DSM.
- **Access**:
  - GPKG/FGDB tile indexes `https://diffusion.mern.gouv.qc.ca/diffusion/RGQ/Imagerie/MNT/_Index/Index_MNT_GPKG.zip`;
  - download map `https://lidar-telechargement.portailcartographique.gouv.qc.ca/`;
  - a WMS of the index.
- **Licence**: CC BY 4.0 (from the Données Québec CKAN API).
- **Quick tests (2026-10-31)**:
  - the CKAN API answered;
  - `diffusion.mern.gouv.qc.ca` closed every TLS connection (curl/schannel and Python/OpenSSL; port 80 timed out), so neither the index nor any file could be read. Geo-blocking or a server problem.
  - The federal STAC covers Val-David (3 projects), the Saguenay fjord (5) and Percé (1), all 100% valid.
- **Fit**: the federal source. The provincial files (SheetTiles-like: GPKG index + files) only if the server becomes reachable.

### ca-nb: New Brunswick (GeoNB)
- **Data**:
  - province-wide DEM 1 m (2017 mosaic plus 2025 tiles);
  - a 2025 DSM from 2016–2024 first returns.
- **Access**: ImageServers `https://gis-erd-der.gnb.ca/server/rest/services/LidarProducts/{DEM,DSM}/ImageServer` (EPSG:2953 NB Stereographic, CGVD2013); 1 km lidar tiles via the GeoNB index.
- **Licence**: GeoNB open licence.
- **Quick tests**: catalog and a 500 m export at Cape Enrage took 2.8 s; values in cm.
- **Fit**: the federal source (40 NB projects incl. Moncton 2025), or the ImageServer driver for the province-wide DSM. Few cliffs (Fundy coast): low.

### ca-ns: Nova Scotia (NSGI)
- **Data**: DEM, DSM, CHM and intensity on a 10k tiling, from the Elevation Explorer (manual, one tile at a time), NAD83(CSRS)v6 UTM 20, CGVD2013.
- **Licence**: unclear (open / unrestricted licence PDFs).
- **Access**: `nsgiwa.novascotia.ca` did not answer (connect timeout).
- **Fit**: federal (28 NS projects, 2010–2020).

### ca-nl: Newfoundland and Labrador
- Federal only:
  - NL 2019 projects (Humber, Exploits, Churchill);
  - NRCan FHIMP coastal projects of 2023–2024 (West, NorthWest, South coasts; Newfoundland UTM21/22).
- Signal Hill is covered (St John's 2020, FHIMP 2024). Inland Gros Morne (Western Brook Pond) has nothing.
- Sea cliffs: medium priority.

### ca-yt, ca-nt, ca-nu: territories
- Federal lidar around communities and corridors: YT 40 projects, NWT 27, NU 23 communities. Whitehorse (Miles Canyon) and Yellowknife are covered.
- Elsewhere only the 2 m ArcticDEM-derived DSM (Iqaluit: DSM yes, DTM no). It has possible artefacts on steep relief (spec 2.8.5). The Baffin big walls are only in that DSM.
- Low priority.

### Comparison with the USA
- `hrdem-lidar` is the 3DEP pattern exactly: per-project files that overlap partly; a public bucket; tiled COGs read by range requests (as `TnmBlocks`).
- The index is a STAC API instead of TNM Access: an item's geometry is the project footprint, so a bbox query returns only the projects that touch the place.
- Unlike 3DEP, the files are one per project (not 10 km tiles) and all share one national CRS (EPSG:3979, reprojected).
- NRCan also publishes the composed result, the mosaic. The USA's S1M is the analogue, but this one covers all available lidar.

## g9: Mexico, Greenland, ArcticDEM, global DTMs, Central America and the Caribbean (2026-10-31)

Scripts: `scripts/g9-mx-gl-carib/`, samples: `dl/g9-mx-gl-carib/`. Rows: [sources.json](sources.json) (39).

### Mexico (INEGI): sheet ZIPs through the elevation viewer's endpoints
- **Data**: two programmes on the 1:10 000 sheet grid (3'20" x 3'45", about 5.6 x 6.9 km, with an overlap strip, "faja de excedencia"):
  - *Modelos Digitales de Elevación de Alta Resolución LiDAR, 5 m*, Terreno (DTM) and Superficie (DSM): **26 334 sheets** (about 1.0 M km², half of the country, lat 14.5–32.7). LiDAR of 2006–2012; the sheet of El Potrero Chico (G14C15B2) was flown in 2007 with a Leica ALS50 II at 0.052 pts/m², **0.012 ground points/m²** (one per ~80 m²): the 5 m grid is an interpolation and will smooth cliffs.
  - *Modelo digital de elevación tipo terreno / superficie, 1.5 m*: **1 843 sheets** (~70 000 km²), edition 2021, **photogrammetric from stereo satellite images** of 2017–2019 (not LiDAR). Its own metadata warns of triangulated interpolation on slopes near 90°, shadows, dense vegetation and cloud holes.
  - Climbing places: El Potrero Chico 5 m only; Huasteca (Monterrey), El Salto (NL), El Chico (Hidalgo) and Los Dinamos (CDMX) have 5 m and 1.5 m; Copper Canyon (Divisadero), Basaseachi and Sumidero canyon: no sheet in either.
  - The CEM 3.0 (Continuo de Elevaciones Mexicano, 15 m) is not worth it (errors up to 140 m in an evaluation).
- **Access**: the viewer https://www.inegi.org.mx/app/geo2/elevacionesmex/ uses two POST endpoints that work without a session:
  - `getFormato10k.do` (`res=5|1.5`, `mod=T|S`): all sheets of a product as `[{cve, x, y}]` (centroids in EPSG:3857, 1.8 MB for 5 m); the grids also as GeoJSON (`js/capas/malla10k_T5_min.geojson` etc.);
  - `getF10KDescarga.do` (`res`, `mod`, `cve`): per sheet the UPC, edition, datum, `url_descarga` and the files with sizes, e.g. 5 m T: `.../1_10_000/lidar/Terreno_ASCII/702825397364_as.zip` (9.2 MB) and `.../Terreno_GRID/702825397371_gr.zip` (3.9 MB); 1.5 m: `.../lidar/1_5m/terreno/889463852827_t.zip` (TIFF, 53 MB) and `_b.zip` (BIL, 52 MB).
  - Files are static on www.inegi.org.mx (IIS, range requests answer 206; HEAD answers text/html without a length), about 1 MB/s. No key, no fair-use rules beyond "buen uso" of the site.
- **Versions**: one edition per sheet and product (the index gives the year).
- **Licence**: Términos de libre uso de la información del INEGI: "Puede explotar comercialmente la información", copies allowed "sin alterar ni suprimir sus metadatos"; credit "Fuente: INEGI, <producto>" and notify users of transformations; no endorsement; terms may change. Comparable to CC BY. https://www.inegi.org.mx/inegi/terminos.html
- **Orthophoto**: WMS https://gaia.inegi.org.mx/NLB/tunnel/wms/wms61? layer `Ortofotos` (1:10 000 orthophotos, EPSG:4326 and 3857). GetMap at Potrero Chico (1.1.1, lon/lat) and Monterrey (1.3.0, lat/lon) fine; one 1.3.0 request at Potrero Chico returned a white image (not reproduced). Image date unknown; looks like ~2000s imagery.
- **Quick tests** (2026-10-31): sheet lists of all four products; downloads of G14C15B2 5 m GRID (4 MB in 4 s): float32, 1194 x 1463 px, 97.6% valid, values in cm (only 1% whole metres), pixel edges on whole 5 m, **no CRS in the GRID**; its auxiliary text says ITRF92 UTM 14, **NAVD88** heights, "16S" and vertical resolution 1.00 (the ASCII/BIL variants may be whole metres: unchecked). 1.5 m TIFF ZIP of G14C25B4 (55.8 MB): central directory by range requests: Deflate members, a plain 42.9 MB float32 TIFF + 13 MB `.ovr`, metadata (ITRF2008 UTM 14N, orthometric heights on GGM10, 0.01 m); pixel edges on multiples of 1.5 m. The whole 1.5 m ZIP (>50 MB) was not downloaded.
- **Fit**: a new driver on the `SheetTiles` pattern: index = the sheet list (cache per product; or compute the 1:10 000 nomenclature), files = ZIP per sheet, extracted once (GRID through GDAL's AIG driver or the ASCII grid for 5 m, the TIFF for 1.5 m), CRS assigned from the sheet's UTM zone and datum (ITRF92 vs ITRF2008), the overlap strips of neighbouring sheets handled by the mosaic. Special: heights in NAVD88 (5 m) vs GGM10 (1.5 m); 1.5 m preferred where it exists, 5 m elsewhere; 55 MB per 1.5 m sheet even for a small circle.
- **Open questions**: precision of the ASCII variant; age and resolution of the WMS orthophoto; whether INEGI plans new LiDAR (none announced); whether the 1.5 m photogrammetry is usable on Monterrey's walls (compare with the 5 m LiDAR and with a known line).
- **Links**: https://www.inegi.org.mx/app/geo2/elevacionesmex/ · https://www.inegi.org.mx/programas/mde/ · https://inegi.org.mx/contenidos/temas/relieve/continental/doc/fichas_tecnicas.pdf · https://www.inegi.org.mx/servicios/wsinfogeo/

### Greenland: no national model; ArcticDEM is the only fine data
- **Data**: Asiaq (Greenland's survey) gives free town data since 2018 at https://kortforsyning.asiaq.gl/files/ (78 towns and settlements: base maps with contours in GDB/SHP/DWG, PDFs, 10 cm orthophotos as ECW, 222 MB at Nanortalik) — no DTM rasters, nothing outside settlements. opendem.info lists a 2 m DSM of Greenland from SDFI (2023); not found on dataforsyningen.dk (it may be ArcticDEM reprocessed: open question). Research DEMs (GIMP 30 m, 1978–87 aerial 25 m, ICESat-2) are too coarse.
- **Access/licence**: ArcticDEM as below (CC BY 4.0); Asiaq under its terms of use (PDF, https://www.asiaq.gl/wp-content/uploads/2026/04/EN_Terms_of_use_for_Asiaq_geodata.pdf; "Public and private users can now download and use this data freely").
- **Orthophoto**: only Asiaq's town ECW files and the NunaGIS viewer; no WMS/WMTS found.
- **Quick tests**: ArcticDEM at Tasermiut (Ketil area, 86.8% data in the tile, 100% in the window) and Uummannaq (100%).
- **Fit**: the ArcticDEM source. **Open questions**: SDFI's 2 m DSM (product, licence, access); Asiaq's terms for automatic use of town data.

### ArcticDEM (PGC): 2 m surface model of the Arctic, COGs on AWS with STAC
- **Data**: a **surface model** (DSM) from stereo pairs of Maxar satellite images (WorldView, GeoEye). Mosaic v4.1 (Aug 2023, data ~2007–2021) at 2 m (25 km tiles, 25 100 px incl. a 100 m overlap), 10 m and 32 m; strips s2s041 at 2 m to 2024 (8–46 strips per point at the places tested). Coverage: land north of about 60° N and all of Alaska: Greenland, Iceland, Svalbard, Norway north of ~60° (Sognefjord yes, Preikestolen no), Sweden, Finland, Canada north of 60 (Whitehorse yes, Torngat at 58.5° no), Russia. Alaska data acquired after mid-2022 is not public (EOCL contract); the v4.1 mosaic covers Alaska (Ruth Gorge tested).
- **Access**: STAC API https://stac.pgc.umn.edu/api/v1 (12 collections, e.g. `arcticdem-mosaics-v4.1-2m`; an item per tile with assets `dem`, `mad`, `count`, `maxdate`, `mindate`, `datamask`, `hillshade`; properties `pgc:data_perc`, start/end dates); files in the public S3 bucket `pgc-opendata-dems` (us-west-2), also a VRT of all tiles. COG float32, LZW + predictor 3, 512 px blocks, overviews; 1.28 GB per 2 m tile, so windows only.
- **CRS and heights**: EPSG:3413 (polar stereographic, pixel edges on even metres); **heights above the WGS84 ellipsoid** (Greenland +20…+60 m vs EGM2008): convert with the EGM2008 grid before filling gaps from Copernicus/FABDEM (fill_gaps allows ±3 m around one offset) and before showing heights. Values in steps of 1/128 m.
- **Licence**: CC BY 4.0 (STAC collections; AWS registry: "Creative Commons Attribution 4.0 International"). Acknowledgement: "DEMs provided by the Polar Geospatial Center under NSF-OPP awards 1043681, 1559691, 1542736, 1810976, and 2129685", citation Porter et al. 2023 (doi:10.7910/DVN/3VDC4W).
- **Quick tests** (2026-10-31): STAC item queries 0.7 s each at Tasermiut, Lofoten, Vestrahorn, Svalbard, Baffin (Auyuittuq), Kilpisjärvi, Kebnekaise; HEAD 1.28 GB (AmazonS3); windows of 500 m–1 km in 0.5–1.3 s, 100% valid at Tasermiut, Presten (Lofoten), Vestrahorn, Ruth Gorge, Uummannaq.
- **Fit**: new driver: a STAC index (as `StacTiles`) whose items are read in windows (as `TnmBlocks`: blocks cached on a fixed grid in EPSG:3413), one mosaic version (no composing); resampled to the UTM working grid; geoid correction. Effort M.
- **Role**: the only fine data in Greenland, Svalbard (NPI's own DTM is 5 m) and much of arctic Canada; elsewhere (Norway, Finland, Sweden, Iceland's IslandsDEM which is itself built from ArcticDEM, Alaska's IfSAR/lidar, Canada's HRDEM which includes ArcticDEM-based tiles) the national data is better, so ArcticDEM there is at most a gap filler, still better than 30 m.
- **Risks**: a photogrammetric DSM: voids and blunders on near-vertical faces and in shadow, snow/ice and multi-year blending, trees and buildings included (no DTM to separate them; in bare Arctic rock DSM ≈ terrain). Check against national lidar (e.g. Lofoten) before trusting cliff edges.
- **Links**: https://www.pgc.umn.edu/data/arcticdem/ · https://registry.opendata.aws/pgc-arcticdem/ · https://stac.pgc.umn.edu/api/v1/collections · https://www.pgc.umn.edu/guides/user-services/acknowledgement-policy/

### FathomDEM and GEDTM30 (newer global DTMs)
- **FathomDEM** v1.0 (30 m, 2025): CC BY-NC-SA 4.0 like FABDEM, and its Zenodo files are restricted (log in and request access; commercial licences from Fathom). Not better licensed than FABDEM and not downloadable automatically: no reason to switch.
- **GEDTM30** (OpenGeoHub, 2025): CC BY 4.0 (more open than FABDEM), DTM trained on ICESat-2/GEDI; one global COG at 0.00025° (~27 m; the "30 m" name is approximate), int32 decimetres, EGM2008: `https://s3.opengeohub.org/global/edtm/gedtm_rf_m_30m_s_20060101_20151231_go_epsg.4326.3855_v20250611.tif` (vsicurl window at Potrero Chico in 1 s). Also on OpenTopography (OTSDEM.082025.4326.1). Zenodo v1.2.0 (2026-03) holds only 120/240 m layers. v1 carries "use for testing purposes only".
- **Fit**: windows of one global COG (`DegreeBlocks`-like). Open question: is GEDTM30 closer to the lidar than FABDEM at cliffs (compare at a US or Swiss site)? It would make gap-filled runs CC BY instead of NC-SA.

### Haiti: national lidar DTM 1.5 m on OpenTopography, whole metres, no licence
- **Data**: Haiti DTM 2014–2016 (World Bank, HaitiData; IGN FI + IMAO), 1.5 m, whole country (29 239 km²); orthophotos 0.25 m exist; no DSM on OT.
- **Access**: VRT https://opentopography.s3.sdsc.edu/raster/Haiti_16/Haiti_16_be.vrt over 10 km tiles (512 px blocks), so windows by vsicurl work (500 m in 3.6 s). EPSG:32618, EGM96.
- **Problems**: **UInt16 whole metres**; OT lists the licence as "Not Provided". Low priority.

### Caribbean Netherlands (Bonaire, Sint Eustatius, Saba): 0.5 m lidar, CC BY 4.0, WCS
- **Data**: the first lidar of the BES islands (2023, AHN programme, Het Waterschapshuis): DTM and DSM at 50 cm, CC BY 4.0, in the "Dataroom Caribisch Nederland" (https://www.beeldmateriaal.nl/dataroom-caribisch-nederland).
- **Access**: WMS/WMTS/WCS per product hosted by Ellipsis Drive (`https://api.ellipsis-drive.com/v3/ogc/wcs/<id>`); the listed whole-island GeoTIFFs on basisdata.nl answer 404 (2026-10-31). WCS 1.1.1 needs `format=geotiff`, `GridBaseCRS`, `GridOffsets` and `GridOrigin`; the answer is multipart (XML + GeoTIFF part) with two float32 bands (height, mask), NaN outside. CRSs: island systems EPSG:10641 (Saba), 10745 (Statia), 10759 (Bonaire), new in EPSG (autumn 2024), or EPSG:3857. Native offsets 0.50004 m (not exactly 0.5). Vertical datum not stated.
- **Quick test**: Saba DTM 500 x 500 m in EPSG:3857 at 0.5 m: 0.2 s, 1001 x 1001 px, 100% valid, 206 m near The Bottom.
- **Fit**: `WcsTiles` with a WCS 1.1.1 variant (grid parameters, multipart). Saba's sea cliffs and Statia's Quill crater are small but real; Bonaire is flat. Medium.

### Saint Vincent: USGS lidar 0.6/1 m, CC0
- USGS data release (doi:10.5066/P13ZHRG3): bare-earth DEMs 0.6 m and 1 m of St Vincent from lidar of Dec 2021–Feb 2022 (cloud gaps), CC0. Whole-island rasters on ScienceBase (not opened); own hosting if wanted. Low (volcano, few climbers).

### French territories (Guadeloupe, Martinique, Saint-Martin, Saint-Barthélemy, Saint-Pierre-et-Miquelon)
- Belong to IGN's products (Etalab 2.0). Not confirmed here whether RGE ALTI 1 m covers them (Earth Engine's copy is mainland only); LiDAR HD was contracted for Guadeloupe and Martinique (tenders 2024 and 2025), publication not confirmed (Réunion was the first overseas territory published). Decide with the France row: if IGN's service covers them, they come for free.

### Short rows (nothing usable beyond global models)
- **Guatemala**: only UAV surveys of 2024 near the Motagua (OpenTopography). **Belize**: Caracol/Chiquibul archaeology lidar (OT, manual). **Honduras, El Salvador, Nicaragua, Panama, Dominican Republic**: nothing open found. **Costa Rica**: CRDTM2020 (NASADEM corrected, 30 m), La Selva 2009 lidar (research). **Cuba**: nothing (Viñales would be interesting). **Jamaica, Trinidad and Tobago, Barbados**: surveys exist but no open release found.
- **Small islands** (Antigua and Barbuda, Saint Kitts and Nevis, Anguilla, Montserrat, Turks and Caicos, Bahamas, Aruba, Sint Maarten): nothing open. **Curaçao**: lidar flown in 2026, no release. **Dominica, Grenada, Saint Lucia**: CHARIM (World Bank) maps; Grenada had a lidar tender (0.5 m), delivery not confirmed; Saint Lucia's CHARIM DEM is from 10 m contours. **BVI**: USGS EAARL 2014 of Anegada (flat). **Cayman**: bathymetry only. **Bermuda**: NOAA coastal DEMs at 30/90 m.
- OpenTopography catalogue query (bbox 118–58° W, 7–33° N) found nothing else in these countries.
