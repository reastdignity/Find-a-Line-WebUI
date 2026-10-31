# Elevation sources: Oceania (survey of 2026-10-31)

Notes of the survey in [../source-survey.md](../source-survey.md), one section per group of countries as researched; the rows are in [sources.json](sources.json).

## Australia (g10-au): elevation sources, researched 2026-10-31

Scripts: `scripts/g10-au/` (`cog_window.py`, `imageserver_export.py`, `zip_cd.py`, `tile.py`, `tas_slope.py`, `write_json.py`). Samples: `dl/g10-au/` (ELVIS page, Cocos 5 m zip, NSW/QLD exports, Vicmap docx files and their text, the SA ELVIS catalogue, orthophoto tiles).

**Summary.** The lidar of the states and territories is collected in **ELVIS** (elevation.fsdf.org.au, run by GA for ICSM), but ELVIS is an ordering portal: you draw an area, pick tiles and get a link by e-mail. There is no documented API. Its search API answered 403 to our User-Agent (a CloudFront WAF), and the page's JavaScript is not served to us either. Third-party notes say the files sit in **requester-pays** S3 buckets per state; anonymous 403 is confirmed for nsw-elvis, sa-elvis, tas-elvis, act-elvis and ga-elvis.

Data with automatic access does exist:
- **Queensland**: a public ImageServer with 0.5–1 m lidar DTM, licensed CC BY-SA.
- **Tasmania**: a statewide 2 m DEM as one 95 GB COG on source.coop, a third-party copy under CC BY 3.0 AU.
- **GA's 1-second DEMs** (SRTM, 30 m, CC BY 4.0) as national COGs on DEA's public S3.
- **GA's national 5 m lidar DEM**, but only as zips per UTM zone of up to 10.8 GB.
- **NSW's statewide 5 m photogrammetric DEM**, as 100k-sheet zips of ASCII grids or through a slow ImageServer.

Victoria's 1 m DEM is licensed for a fee, and WA's lidar is too. No state publishes an open DSM raster except SA's 2011–2015 projects, which are in ELVIS only.

### au: national (GA / ICSM: ELVIS, 5 m DEM, 1 second DEMs)
- **Data**
  - *ELVIS* aggregates state, territory and Commonwealth lidar (point clouds and DEMs, 1–5 m), GA's 5 m DEM, the drainage-catchment 5 m DEMs (built from ELVIS tiles, one zip per catchment) and the SRTM 1 s DEMs. NSW added 97 085 km² in 2025.
  - *National 5 m DEM derived from lidar*: 236 surveys, 2001–2015, >245 000 km² (populated coast, Murray-Darling floodplains, towns). No national lidar programme exists; coverage comes from state partnerships.
  - *SRTM-derived 1 second DEM v1.0* (2011, from SRTM 2000): DEM (vegetation offsets removed), DEM-S (smoothed) and DEM-H (hydrologically enforced).
- **Access**
  - The 5 m DEM comes as 12 zips per UTM zone on `https://elevation-direct-downloads.s3-ap-southeast-2.amazonaws.com/5m-dem/national_utm_mosaics/<zone>.zip`. The AHD (Ausgeoid) set is 31.8 GB in all; Quasigeoid variants exist for the Murray-Darling Basin. Each zip holds one TIFF (ZIP64, Deflate). A WCS/WMS exists at `services.ga.gov.au/gis/services/DEM_LiDAR_5m_2025/MapServer`, but services.ga.gov.au answered 403 to us (CloudFront "Request blocked").
  - The 1 s DEMs are COGs on DEA's public bucket: `https://dea-public-data.s3.ap-southeast-2.amazonaws.com/projects/elevation/ga_srtm_dem1sv1_0/{dem1sv1_0,dems1sv1_0,demh1sv1_0}.tif` (34–38 GB each).
  - ELVIS ordering: per a third-party write-up (resuly/property-scores, 2026-07), it works like this:
    - `GET https://api.elevation.fsdf.org.au/elevation/downloadables?polygon=<WKT>` lists the tiles, 10 000 per query. It needs browser Origin/Referer headers.
    - An order is a JSON put into S3 bucket `ga-elvis-uploads-prod`, using credentials from an unauthenticated Cognito identity pool, followed by `POST .../initiateJob`.
    - About 26 s later an e-mail brings a public `https://elvis-downloads.s3.amazonaws.com/DATA_<n>.zip`.
  - We did not try the ordering flow: it means emulating the web app, and the WAF blocks honest clients.
- **Licence**: CC BY 4.0 (5 m and 1 s DEMs); "© Commonwealth of Australia (Geoscience Australia)".
- **Orthophoto**: no national open orthophoto. DEA has Sentinel-2 at 10 m only. Nearmap and Esri are commercial. Use the state services (below).
- **Quick tests (2026-10-31)**
  - *DEA 1 s COG*: DEM-S via `/vsicurl/` opens in 1.7 s. 147600×122400 px, EPSG:4326, DEFLATE, 512 px blocks, 8 overviews. A 1 km window at the Three Sisters reads in 2.3 s, 100% valid. Pixel edges are at whole arc-seconds minus half a pixel, i.e. centres on whole seconds.
  - *5 m zips*: the HEADs answer 200. The central directory of `nationalz56_ag.zip` (10.6 GB) holds one TIFF and the metadata docx.
  - *Cocos zip* (2.6 MB) downloaded: the TIFF is 5 m, 128 px tiles, uncompressed inside, nodata -3.4e38. Its CRS is GDA94 / MGA 47 (WKT name "Map_Grid_of_Australia_Zone_47_GDA_94"), with edges on whole metres up to float noise.
  - *OpenTopography* lists only 3 small Australian datasets.
- **Fit**
  - *DEM-H or DEM-S as a CC BY 4.0 gap filler*: window reads of one national COG, a small `DegreeBlocks`-like subclass. Like the USA's 1/3″ choice, it keeps a run's licence open instead of FABDEM's NC-SA. It is SRTM C-band from 2000, so it is not more detailed than FABDEM; to be compared.
  - *5 m*: own hosting after one download per zone (L), for the old lidar areas only.
  - *ELVIS lidar*: either own hosting of ordered tiles, or a requester-pays S3 driver signed with our own AWS account, paying the egress. Both are unverified, and both need the user's decision.
- **Open questions**
  - Ask GA (elevation@ga.gov.au / ICSM) whether an automated, documented access to ELVIS exists for a non-commercial site, and whether the requester-pays buckets are meant for that.
  - Is DEM-H better than FABDEM at Australian cliffs? Compare them at the Three Sisters.
- **Links**: https://elevation.fsdf.org.au/ · https://www.ga.gov.au/scientific-topics/national-location-information/digital-elevation-data · https://ecat.ga.gov.au/geonetwork/srv/api/records/22be4b55-2465-4320-e053-10a3070a5236 · https://pid.geoscience.gov.au/dataset/ga/72759 · https://dea-public-data.s3.ap-southeast-2.amazonaws.com/projects/elevation/ga_srtm_dem1sv1_0/README.txt · https://github.com/resuly/property-scores/blob/main/docs/national-lidar-bake-handoff.md (third-party)

### au-nsw: New South Wales (DCS Spatial Services)
- **Data**
  - *Lidar DEM*: 1 m on the coast and in towns, 2 m in the ranges, as 2 km tiles via ELVIS. Users report that most of the eastern ranges (the Blue Mountains included) have 2 m or 1 m.
  - *Statewide 5 m DEM*: photogrammetric, with gaps at steep slopes and shadows interpolated. That is weak exactly at cliffs.
  - No DSM raster; the point clouds are on ELVIS.
- **Access**
  - *Lidar*: ELVIS order only. The third-party notes name the requester-pays bucket `nsw-elvis`.
  - *5 m*:
    - index FeatureServer `https://portal.spatial.nsw.gov.au/server/rest/services/Hosted/Elevation_Index_Public/FeatureServer/0` (field `dems5mid`, per 1:100k sheet);
    - files at `https://portal.spatial.nsw.gov.au/download/dem/<zone>/<dems5mid>.zip` (S3). Each zip holds an ESRI ASCII grid, e.g. Katoomba: 301 MB zip, 874 MB .asc;
    - ImageServer `https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_5M_Elevation/ImageServer` (EPSG:3857, F32).
- **Licence**: ELVIS lists the NSW data as CC BY; the NSW FSDF DEM record says CC BY 3.0 AU. Attribution: "© State of New South Wales (Spatial Services)".
- **Orthophoto**: SIX Maps `https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{y}/{x}`: EPSG:3857, cache levels to 23, sharp, no watermark. Its terms of use were not found (the copyright text says "© Department of Customer Service 2020").
- **Quick tests (2026-10-31)**
  - *ImageServer*: exportImage of 600 m at the Three Sisters took **42 s** for 120×120 px: 623–979 m, 100% valid, max pixel slope 85°.
  - *Index and files*: the index query gave Katoomba-DEM-AHD_56_5m. The HEAD of its zip answered 200, 301 MB. The central directory holds the .asc, the .prj and a metadata html.
  - *Orthophoto*: a z18 tile came back as a 19 kB JPEG.
- **Fit**
  - Lidar: own hosting of tiles ordered from ELVIS (Blue Mountains first), or the requester-pays driver.
  - The 5 m sheets are ASCII zips: no window reads, so own hosting or nothing. The ImageServer is too slow and reprojects to 3857.
- **Open questions**
  - Which Blue Mountains lidar exists (years, 1 m vs 2 m)? This needs the ELVIS search, which is blocked for us. The user could look in a browser.
  - Licence version per dataset.
- **Links**: https://data.nsw.gov.au/data/dataset/1-a9acf411599c4d0c8c91fc2ef0f99f5f · https://data.gov.au/data/dataset/8f73f5ca-4f7f-4707-bfe2-0efbb9027107 · https://www.spatialsource.com.au/?p=44190 · https://maps.ozultimate.com/wiki/_export/raw/nsw_download_dems

### au-vic: Victoria (Vicmap Elevation)
- **Data**
  - *Vicmap Elevation 1m DEM*: a virtual mosaic of the Vicmap LiDAR DEMs collection (COG sources, since 2006, Coordinated Imagery Program). About 60% of the land and 95–98% of populated areas (2024). GDA2020 (VicGrid EPSG:7899, MGA), AHD (the Ausgeoid of each survey).
  - *Vicmap Elevation DEM 10m*: statewide, CC BY 4.0, vertical accuracy only 5 m.
- **Licence**: "Vicmap 1m DEM is subject to licensed use. Data Access License Agreements (DALA) provide the terms and conditions of use, including license fees." The free "Sample" services (Mt Bogong, Mt Buffalo, Wilsons Promontory, Great Ocean Road...) are hillshade pictures for preview. The footprints are open (WFS).
- **Orthophoto**: Vicmap Basemaps WMTS (`AERIAL_WM_256`, `AERIAL_VG2020`) is "a licensed service ... An annual license fee is payable": not usable.
- **Quick tests**: the product description and the sample-service guide were read (docx in `dl/g10-au/vic/`). There are no open elevation services to test. land.vic.gov.au answered 403 to WebFetch; its docx files downloaded fine.
- **Fit**: none now. The Grampians and Arapiles stay on FABDEM unless DTP grants a non-commercial licence.
- **Open questions**: does DTP offer a free or non-commercial licence for derived, displayed products? Are any Victorian lidar DEMs in ELVIS under CC BY? We could not check.
- **Links**: https://land.vic.gov.au/maps-and-spatial/spatial-data/vicmap-catalogue/vicmap-elevation/1m-dem · https://discover.data.vic.gov.au/dataset/vicmap-elevation-dem-10m

### au-qld: Queensland (QSpatial)
- **Data**
  - *Lidar DTM 0.5/1 m* from the Coordinated LiDAR Program, 2006–2024 (536 catalogue items, mostly 2009–2014), over SRTM DEM-H elsewhere.
  - Lidar newer than 3 years costs a fee; older lidar is free in ELVIS. The lidar DSM is for a fee.
- **Access**
  - *QldDem* (`https://spatial-img.information.qld.gov.au/arcgis/rest/services/Elevation/QldDem/ImageServer`): newest data per area, exportImage up to 4096×2048 px. The service is EPSG:3857, but any SR can be requested.
  - *DEM_TimeSeries_AllUsers*: the same data plus a Catalog. Item queries return name, year, capture dates and resolution (e.g. Brisbane 2009/2014/2019). Single projects can be picked with a mosaic rule.
- **Licence**: the service's item info says "available publicly under Creative Commons Attribution-Share-Alike licence (CC BY-SA)". The copyright text and a no-warranty acknowledgement must be shown.
- **Orthophoto**: `https://spatial-img.information.qld.gov.au/arcgis/rest/services/Basemaps/LatestStateProgram_AllUsers/ImageServer/tile/{z}/{y}/{x}`: sharp, no watermark, terms unclear.
- **Quick tests (2026-10-31)**
  - *Kangaroo Point Cliffs*: 500×500 m at 0.5 m (1000×1000 px, 4.2 MB) in 20 s. -2.9 to 34.3 m, max pixel slope 88°, 69% of values on whole cm.
  - *Near Mt French*: the same request took 5.7 s. My point was off the crag; heights matched DEM-S.
  - *TimeSeries*: the catalogue query returned 5 items at Kangaroo Point.
  - *Orthophoto*: a z17 tile at the Glass House Mountains came back fine.
- **Fit**: a new driver, ArcGIS ImageServer exportImage on a fixed tile grid in the MGA zone with nearest-neighbour resampling (a `WcsTiles` analogue). Versions are optional, from the TimeSeries catalogue.
- **Open questions**
  - Does CC BY-SA (share-alike) bind the derived lines of a run?
  - The datum shift of GDA2020 projects (a 7-parameter transformation for display).
  - Whether requesting EPSG:28356 gives the projects' own pixels.
- **Links**: https://spatial-qld-support.atlassian.net/wiki/spaces/QSUITE/pages/260538373/Elevation+and+LiDAR · https://www.data.qld.gov.au/dataset/queensland-elevation-dem-public-time-series-service

### au-tas: Tasmania (theLIST / Mineral Resources Tasmania)
- **Data**: the Tasmania Statewide 2 m DEM (14-08-2021) covers all land. About 65% is from lidar; the rest is interpolated from contours (effective 10 m). Lidar 1 m tiles (Climate Futures 2008 coast and newer projects) are on ELVIS. No DSM was found.
- **Access**: officially by ELVIS order. Alex Leith put a **COG copy on source.coop** (2023-11-29): `https://data.source.coop/alexgleith/tasmania-dem-2m/Tasmania_Statewide_2m_DEM_14-08-2021.tif` (95 GB, anonymous).
- **Licence**: "Creative Commons Attribution 3.0 Australia Licence with attribution to 'The LIST ©State of Tasmania'". That allows redistribution, so we could host our own copy.
- **Orthophoto**: `https://services.thelist.tas.gov.au/arcgis/rest/services/Basemaps/Orthophoto/MapServer/tile/{z}/{y}/{x}`: EPSG:3857, zoom 0–19, no watermark, **CC BY-NC-ND 3.0 AU**. Fine for a non-commercial site that shows tiles unchanged.
- **Quick tests (2026-10-31)**
  - *COG*: opens in 1.2 s. EPSG:28355, LZW, 512 px blocks, LAYOUT=COG. A 1 km window at Cape Hauy reads in 2.5 s (34% valid, sea), up to 144 m.
  - *Cliff detail*: in 800 m windows Cape Hauy has a max pixel slope of 87° and 5.5% of pixels steeper than 60° (lidar-like detail); Cape Raoul 83°.
  - *Lidar index*: the Climate Futures lidar index has no tile at Cape Hauy or Cape Raoul, so their lidar comes from another project (unclear which).
  - *Orthophoto*: a tile at Cape Hauy came back fine.
- **Fit**
  - Window reads of one big COG (a small `DegreeBlocks`-like subclass), or own hosting copied from it.
  - The origin is **not on whole metres** (x = -30597.398, y = 5687852.9), so the grid needs an origin offset.
  - Note which areas are lidar-based and which contour-interpolated (no mask found).
- **Open questions**
  - Is there a lidar/interpolated mask?
  - Does Land Tasmania publish the 2 m DEM itself (data.thelist.tas.gov.au download)?
  - Do the newer Tasmanian lidar projects exceed 2 m?
- **Links**: https://source.coop/alexgleith/tasmania-dem-2m · https://data.gov.au/data/dataset/dc463cd1-9b03-48fd-875b-a554f983e69a · https://services.thelist.tas.gov.au/arcgis/rest/services/Public/TopographyAndRelief/MapServer/27

### au-wa: Western Australia (Landgate)
Landgate's lidar and DEMs (1–20 m over 80% of WA) are supplied on request with fees, under a Personal Use Licence; the lidar index (LGATE-351) is open. The only open fine data is GA's 5 m zone zips (`waz50.zip` 2.2 GB: Perth and the SW coast). Kalbarri, Karijini and the Stirling Range stay on FABDEM. Landgate imagery is also licensed. https://www.landgate.wa.gov.au/location-data-and-services/discovering-landgate-data/lidar-data/

### au-sa: South Australia (DEW)
- DEW's ELVIS catalogue lists 16 lidar datasets, mostly 1 m: Eyre Peninsula coastline 2018, Kangaroo Island 2015/2020, Fleurieu coast 2020, Yorke Peninsula 2020, Adelaide metro 2018–19 (Morialta) and the SE coast 2018. The 2011–2015 projects include DSMs. It is a GeoJSON with bounding boxes, CC BY 4.0 inside the zip.
- The Flinders Ranges (Moonarie) are not covered.
- Access is by ELVIS order only, so own hosting would be needed. https://data.sa.gov.au/data/dataset/elvis-digital-elevation-model-imagery-catalog

### au-nt: Northern Territory
Only GA's 5 m (Darwin, Kakadu 2011 lidar, towns) as zone zips (`ntz52`/`ntz53`). Kings Canyon and Katherine Gorge stay on FABDEM.

### au-act: Australian Capital Territory
Whole-territory lidar from 2015 and 2020 (Aerometrex, 12 pts/m², 1 m DEM, AHD), CC BY 4.0, "(c) Australian Capital Territory and Aerometrex Limited". Access is ELVIS only. It is small (2 400 km², Booroomba Rocks), so one order plus own hosting would do. https://www.planning.act.gov.au/professionals/survey-spatial/spatial-information/lidar-data

## New Zealand (g11-nz): elevation sources, researched 2026-10-31

Scripts: `scripts/g11-nz/` (`peek_collection.py`, `cog_places.py`, `capture.py`, `survey_tile.py`, `points_in_capture.py`, `ortho_tile.py`). Samples and outputs: `dl/g11-nz/` (catalog and collection JSONs, the composite's `capture-area`/`capture-dates` GeoJSONs, `basemaps_elevation.json` (the composite's layer stack), the bucket's `LICENSE.txt`, `*.txt` outputs of the scripts, Basemaps tiles of Castle Hill and its WMTS capabilities).

**Summary.** One national source covers the whole country. LINZ publishes every council lidar survey as COGs in a public S3 bucket, plus a national composite of them as a DEM and a DSM, all CC BY 4.0. It covers about 87% of the land, including every tested climbing area except Milford Sound / inner Fiordland and parts of rural Otago. No regional row is needed: the regions deliver their data through this same bucket.

### nz: LINZ National Elevation Programme (nz-elevation bucket)
- **Data**
  - *Per-survey DEM and DSM*, 1 m, from airborne lidar flown to the National Aerial LiDAR Base Specification.
    - About 110 DEM collections, 2008–2026, named `<region>/<survey>_<years>/{dem_1m,dsm_1m}/2193/`.
    - Every survey has a DSM except tauranga_2022, kaikoura_2016-2017 and tasman_2008-2015.
  - *National composite* "New Zealand LiDAR 1m DEM" and "… 1m DSM" (`new-zealand/new-zealand/{dem_1m,dsm_1m}/2193/`).
    - One COG per Topo50 sheet (24 × 36 km): 424 sheets.
    - Its `capture-dates.geojson` holds 82 non-overlapping polygons, each naming the survey, the flight dates and the licensor that is visible there.
  - *Coverage*: the DEM covers 233,063 km² and the DSM 232,716 km², of about 268,000 km² of land (≈87%).
    - Gaps: inner Fiordland (Milford Sound, no lidar; the Darran Mountains / Homer Tunnel are covered), and parts of Otago (Hospital Flat near Wanaka, the Dunedin coast).
    - Otago Regional Council (June 2026): an Otago-wide programme brings full regional coverage by 2027–28; the first Queenstown-Lakes data are due "from late 2026".
  - *Repeat surveys* are under way over cities and regions (Canterbury 2010 → 2016-17 → 2020-23; Wellington City 2013-14 → 2019-20 → 2025; Hamilton 2019/2023/2025).
  - *8 m DEM*: "New Zealand Contour-Interpolated 8m DEM" (Geographx, 2012), interpolated from 20 m contours, same bucket and sheets, CC BY 4.0. LINZ itself says "Suitable for cartographic visualisation purposes only. Not suitable for terrain analysis." It is open and covers the whole country, so it could serve as a gap filler instead of FABDEM (licence CC BY instead of NC-SA). Its cliffs are smoothed by the contour interpolation.
  - *Topo-bathymetry*: a separate `nz-coastal` bucket ([linz/coastal](https://github.com/linz/coastal)). Not examined.
- **Access**
  - Public S3 bucket `s3://nz-elevation`, `https://nz-elevation.s3.ap-southeast-2.amazonaws.com/`, listed in the Registry of Open Data on AWS. No key, no requester-pays.
  - A **static** STAC catalogue (`catalog.json` → `collection.json` → items). There is **no STAC API / search**: a place is found from the tile grid.
    - Composite items are `<sheet>.json`/`.tiff`. The Topo50 sheet follows from NZTM: E origin 988 000, N origin 6 810 000, 24 km × 36 km, two letters from `ABCDEFGHJKLMNPQRSTUVWXYZ` (no I, O) for the row, two digits for the column. Checked on AS21 and six places.
    - Survey tiles are `<sheet>_10000_<row><col>`, the 1:10k index (5 × 5 per sheet, 4.8 × 7.2 km). A composite item's `derived_from` links list the survey tiles it was made from.
  - LINZ Data Service (data.linz.govt.nz) offers the same layers as exports behind a login, which the bucket makes unnecessary.
  - No fair-use rules found for the bucket.
- **Format**
  - COG, float32, nodata -9999, 512 px blocks, `SPARSE_OK` (empty blocks omitted).
  - LERC with `MAX_Z_ERROR` 0.001 m at full resolution (overviews 0.1 m): near-lossless within 1 mm, by LINZ's [TIFF specification](https://github.com/linz/elevation/blob/master/docs/tiff-specification.md).
  - Composite sheets are 0.2–1.7 GB (always window reads); survey tiles 16–40 MB.
  - CRS EPSG:2193 only. Heights are NZVD2016 (EPSG:7839): "NZVD2016 is not recorded in the GeoTIFF metadata".
  - All files are PixelIsArea (LINZ standardised them), and the pixel edges sit on whole metres.
- **Versions**
  - Surveys overlap in parts of 1:10k tiles: the Castle Hill tile BW21_10000_0505 exists in christchurch-and-selwyn_2015 (16 MB) and in canterbury_2020-2023 (40 MB). So, as in the USA, "newest file per tile" would be wrong.
  - The composite does the composing itself. A weekday cron (`cron-national-dem.yaml`, `cron-national-dsm.yaml` in linz/topo-workflows) merges the layer list of `linz/basemaps-config/config/tileset/elevation.json`, a curated order with older surveys below newer ones, and rewrites the sheet files in place. The item's `updated` time and `file:checksum` change; Castle Hill's BW21 was updated 2025-09-25.
  - About 28 older surveys are fully hidden in the composite.
  - Per-pixel provenance comes only as polygons (capture-dates), not as a raster.
- **Licence**
  - The bucket's `LICENSE` is the CC BY 4.0 text, and every collection says `"license": "CC-BY-4.0"`.
  - Copyright belongs to the licensor of each survey (regional councils, Queenstown-Lakes District Council, Regional Software Holdings for Auckland 2024, the Ministry for Cities, Environment, Regions and Transport for 2026 surveys).
  - Attribution ([LINZ](https://www.linz.govt.nz/products-services/data/licensing-and-using-data/attributing-elevation-or-aerial-imagery-data)): "Sourced from the LINZ Data Service and licensed by (insert the licensor) for re-use under the Creative Commons Attribution 4.0 International licence". The short web form is "Sourced from LINZ. CC BY 4.0", linked to that page.
  - Commercial use and redistribution are allowed. A public site may cache tiles and show derived lines with the attribution.
- **Orthophoto**
  - LINZ Basemaps aerial: `https://basemaps.linz.govt.nz/v1/tiles/aerial/WebMercatorQuad/{z}/{x}/{y}.{jpeg|webp|png}?api=<key>`, also WMTS (`…/WMTSCapabilities.xml`) and NZTM2000Quad. Imagery is composed dynamically from the nz-imagery surveys (0.075–0.3 m, Sentinel 10 m base).
  - CC BY 4.0. Terms: "Your product must always visibly show attribution and link to the LINZ Basemap custom attribution data", and access may be revoked on overuse.
  - **A key is required.** Without one the server answers 400 "API Key Invalid: missing".
    - *Standard keys* are `c` + a ULID that the website generates in the browser. They are rate-limited (1,000 tiles/min, 1,000,000/month, 429 above) and documented as renewed every 90 days; the server's expiry check is commented out.
    - *Developer keys* (`d…`) are static, have no rate limit ("reasonable use") and are restricted to a nominated site. They come on request from basemaps@linz.govt.nz.
  - A public site would want a developer key, kept like the OpenTopography key (a secret). Raw imagery COGs are also in the open `nz-imagery` bucket (EPSG:2193, no key); we would have to render our own tiles from them.
- **Quick tests (2026-10-31)**
  - Catalogue: 226 collections (66 kB).
  - Composite COG windows of 500 m, DEM and DSM:

    | Place | Sheet | Time per window | Valid share | Size of the sheet files |
    | --- | --- | --- | --- | --- |
    | Castle Hill | BW21 | 1.5–3.6 s | 1.000 | 1.5–1.55 GB |
    | Paynes Ford | BP24 | 1.1–1.2 s | 1.000 | 1.6–1.7 GB |
    | Whanganui Bay | BH35 | 1.1 s | 1.000 | 1.2–1.4 GB |
    | Remarkables | CC11 | 1.2–2.9 s | 1.000 | 0.4 GB |
    | Wanaka (Mt Iron) | CB12 | 1.7–2.1 s | 1.000 | 0.22 GB |
    | Milford Sound | CB08 | 1.1 s | 0.000 (no lidar) | |

  - Every file: EPSG:2193, 1 m, edges on whole metres, LERC.
  - Precision: values on whole mm everywhere; the share on whole cm depends on the survey (Castle Hill and the Remarkables 1.00, Wanaka 0.80, Whanganui Bay 0.79, Paynes Ford 0.10).
  - 8 m DEM sheets: 24–32 MB, 1.1–3.5 s per 2 km window.
  - Coverage of the capture area at 18 climbing places: all covered except Milford Sound, Hospital Flat (Wanaka) and Long Beach (Dunedin). Wharepapa, Darran Mountains, Aoraki/Mt Cook village, Arthur's Pass, Port Hills, Kaikoura, Charleston and Piha are covered.
  - Basemaps tile at Castle Hill, with a standard key made as the website makes one: z18 webp 4 kB / jpeg 8 kB, z20 and z22 answered 200 but are upsampled (native ≈ z19 there). Real imagery, no watermark, CloudFront, max-age 7 days. The WMTS lists zooms 0–24.
- **Fit**: a new subclass for the bucket, effort M. Two options to decide:
  - **(a) The composite** (DegreeBlocks-like, on the fixed Topo50 grid in EPSG:2193).
    - URL from the sheet code; read windows of the 0.2–1.7 GB sheet COGs. The item JSON is a small cached index (TTL), and its `file:checksum` goes into the cached block's key.
    - Pros: one file per place, already composed, no per-survey index.
    - Cons: files are rewritten in place (check the ETag between reads); LINZ's curated order rather than a strict "newest"; the licensor per area must come from `capture-dates.geojson` for the attribution; no year per pixel.
  - **(b) Per-survey 1:10k tiles composed newest first** (TnmBlocks-like).
    - Index: the composite item's `derived_from` links, or the survey collections and capture-dates. The tiles are small enough (16–40 MB) to download whole, as in Switzerland, or to read in windows.
    - Pros: immutable files, the survey year and licensor known per block.
    - Cons: more index work, and our own order of surveys.
  - Either way:
    - work in EPSG:2193 (`Source.crs`), `grid_origin` 0, heights in NZVD2016 (geoid-based, close to EGM2008: check against Copernicus);
    - gap filling: the 8 m contour DEM (CC BY) or FABDEM (CC BY-NC-SA);
    - orthophoto through Basemaps with a key in `ServiceKeys`.
- **Open questions**
  - Shift and offset against Copernicus GLO-30 / FABDEM (not done: NZVD2016 vs EGM2008).
  - Whether the composite's stack ever puts an older survey above a newer one at a climbing area.
  - Whether a read of a composite sheet during its rebuild is a practical problem.
  - A developer Basemaps key for findaline.lukawski.org (e-mail LINZ).
  - Whether the 8 m DEM beats FABDEM at the edges of the lidar.
  - When the Queenstown-Lakes / Otago gap data appear (late 2026–2028).
- **Links**: see `links` in [sources.json](sources.json). The key ones:
  - [Registry of Open Data](https://registry.opendata.aws/nz-elevation/) and [catalog.json](https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json)
  - [linz/elevation](https://github.com/linz/elevation): its [TIFF spec](https://github.com/linz/elevation/blob/master/docs/tiff-specification.md) and [usage](https://github.com/linz/elevation/blob/master/docs/usage.md)
  - The composite's [cron](https://github.com/linz/topo-workflows/blob/master/workflows/cron/cron-national-dem.yaml) and [layer stack](https://github.com/linz/basemaps-config/blob/master/config/tileset/elevation.json)
  - [Attribution](https://www.linz.govt.nz/products-services/data/licensing-and-using-data/attributing-elevation-or-aerial-imagery-data)
  - [Basemaps keys and limits](https://www.linz.govt.nz/data/linz-data/linz-basemaps/linz-basemaps-documentation) and the [key check](https://github.com/linz/basemaps/blob/master/packages/shared/src/api.ts)
  - [ORC Otago programme](https://www.orc.govt.nz/your-council/latest-news/news/2026/june/funding-boost-for-otago-wide-mapping-programme)
