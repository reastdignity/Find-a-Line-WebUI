# Elevation sources: Asia (survey of 2026-10-31)

Notes of the survey in [../source-survey.md](../source-survey.md), one section per group of countries as researched; the rows are in [sources.json](sources.json).

## East Asia (g14-asia-east): elevation sources, researched 2026-10-31

Japan is the only country of the group with fine, open, automatically reachable elevation data: GSI's DEM1A (1 m from airborne lidar, about half of the land, growing) as XYZ tiles and, through a third-party mirror, as GeoTIFF per mesh; two prefectures publish 0.5 m lidar grids (Shizuoka, Tokyo) under CC BY. Everywhere else fine elevation data is restricted by security rules: South Korea (survey results may not leave the country; the open DEM is 90 m), Taiwan (1 m and 5 m are "general official secrets"; 20 m open), China (classified). Hong Kong has open-licensed territory-wide lidar (2010, 2020), but behind an order portal.

Scripts: `scripts/g14-asia-east/gsi_tiles.py` (decode GSI PNG/text tiles), `tile_vs_fgd.py` (tile against the FGD GeoTIFF), `rinfo.py` (raster info, local or `/vsicurl/`), `sheet.py` (Japanese national basic map 1/500 sheet code of a point), `ckan.py` (CKAN search). Samples in `dl/g14-asia-east/`.

---

### Japan, national (GSI) - high
- **Data**: 基盤地図情報 数値標高モデル. DEM1A: 1 m mesh (0.04" x 0.04", ~1.2 x 1.0 m) from airborne lidar, released since 2023-11-30; coverage 4% -> 46% of 3rd-order meshes (2025-03-31) -> 61% (2025-10-31; "実整備面積は国土の５割弱"), extended again 2026-07-31 (parts of Aomori, Yamagata, Yamanashi, Nagano were planned). DEM5A (5 m lidar), DEM5B/5C (5 m photogrammetry), DEM10B (10 m from contours) cover the rest. Accuracy DEM1A 0.3 m where a ground point falls in the cell, else 2.0 m. **No national DSM.**
- **Access**:
  - *Elevation tiles* (no key): `https://cyberjapandata.gsi.go.jp/xyz/dem1a_png/{z}/{x}/{y}.png` (z <= 17), `dem5a_png`, `dem5b_png`, `dem5c_png` (z <= 15), `dem_png` (DEM10B, z <= 14); text tiles `dem5a/…txt` stopped updating in 2024-10. PNG encoding: x = R·2^16 + G·2^8 + B; x < 2^23: h = 0.01·x; x = 2^23: no data; else h = 0.01·(x − 2^24). Values at the top zoom are "最も近い４つの標高点の値を線形的に平滑化": bilinear at each Web Mercator pixel centre; lower zooms average 4 pixels. Served from S3 (AmazonS3), ~1.2-1.6 s per tile here.
  - *GeoTIFF mirror* (third party, UN Smart Maps Group, `optgeo/japan-geotiff-dem`): `https://data.source.coop/smartmaps/japan-geotiff-dem/{1,5,10}/FG-GML-<mesh>-DEM1A-<YYYYMMDD>.tif`, one file per 3rd-order mesh (30" x 45", ~1 km), float32, EPSG:6668, ZSTD, 512 px tiles; manifests `latest_file_list.csv.gz` / `obsolete_file_list.csv.gz` (url,size,md5). 1 m: 291 779 files, 330 GB, ~1.1 MB each. Holds Survey Act approval R8JHf51.
  - *Originals*: 基盤地図情報ダウンロードサービス, JPGIS GML zips per mesh; "ダウンロードページでユーザ登録とログインが必要" (not automatable).
- **Versions**: GSI publishes an updated mesh as a new file with a date in the name; the mirror's manifests say which is current. The date seems to be the release date (2025/2026 for all files), not the survey year. Tiles are replaced in place.
- **Licence**: GSI's DEM is a basic survey result under the Survey Act, not a content licence. GSI's Q&A: tiles loaded in real time by a website or app: "出典の明示のみで申請不要でご利用いただけます" (Q1-12); copies made public need an Art. 29 (copy) / 30 (use) approval, and for 基盤地図情報 "営利・非営利に関わらず…無償で承認されます" (Q5-4); processing takes 7-14 days. A public site that caches tiles and shows derived lines is not named explicitly. Attribution 「国土地理院」/「地理院タイル」 with a link to the tile list; edited material marked as edited.
- **Orthophoto**: `https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg`, EPSG:3857, up to z18 (z19 404), no watermark; photos are not basic survey results (Q1-20), GSI content terms.
- **Quick tests** (2026-10-31): Jogasaki dem1a z17: 0.98 m/px on the ground, 5.5% no data (sea), cm values, max slope 78.6°; Ogawayama dem1a z17: no gaps, 2191-2379 m, max slope 80.6°; dem1a z18 404; dem5b 404 at Jogasaki (5A there). Mirror: `/vsicurl/` DEM1A at Jogasaki 1.27 MB, 1125 x 750, 1.111e-5° pixels, edges on 139.125 E / 34.9 N, nodata -9999, cm values; tile vs file at Ogawayama: the tile equals bilinear of the file at tile pixel centres (median |d| 3 mm inside the mesh; the tile's right part lies in the next mesh).
- **Fit** (options, not decided):
  1. New driver "XYZ elevation tiles" (dem1a_png z17 with dem5a_png z15 where 1A has no data): simplest, official, no login, attribution only. Heights are already resampled once (bilinear onto Web Mercator), then again onto our UTM grid: cliff edges smooth a little.
  2. New IndexedTiles subclass over the mirror's manifest (newest file per mesh): native values; geographic CRS (0.04" pixels), so still resampled onto the working grid; depends on a volunteer mirror.
  3. Own hosting from the GML originals: login, Art. 29 approval needed to publish.
  Vertical datum JGD2011 (T.P.); gaps of DEM1A filled by DEM5A/5B, then FABDEM.
- **Open questions**: does the cached, derived use on the public site need an Art. 30 approval (ask GSI, free)? DEM1A coverage map as data (the mirror's manifest is one); survey year per mesh (file dates are release dates).
- **Other sources seen, no row**: Hyogo (2021 lidar 0.5 m on G-Spatial, AIST serves 1 m DSM/DEM tiles), Osaka, Tottori and the Forestry Agency's prefecture DEMs on G-Spatial (CS立体図, DEM, DCHM); worth a look only where GSI has no DEM1A.
- **Links**: https://maps.gsi.go.jp/development/ichiran.html, https://maps.gsi.go.jp/development/hyokochi.html, https://www.gsi.go.jp/gazochosa/gazochosa61009.html, https://www.gsi.go.jp/kiban/, https://www.gsi.go.jp/LAW/2930-qa.html, https://source.coop/smartmaps/japan-geotiff-dem, https://github.com/optgeo/japan-geotiff-dem, https://web.pref.hyogo.lg.jp/kk26/3dgeo.html

### Japan, Shizuoka (VIRTUAL SHIZUOKA) - high
- **Data**: airborne lidar (>= 16 pts/m² ground), bathymetric lidar and MMS over ~7 200 of 7 777 km², FY2019-2025 by area (2019: SE Fuji and east Izu incl. Jogasaki; 2020: west Izu; 2021: Fuji and east/mid-west; later: north and south). Products per FY folder: `LP/Grid` (0.5 m ground DEM), `Ground`, `Original` (LAS), `Contour`, `Ortho`, `MicroRelief`. No DSM raster.
- **Access**: public S3 bucket `virtual-shizuoka` (ap-northeast-1), anonymous ListObjectsV2: `https://virtual-shizuoka.s3.ap-northeast-1.amazonaws.com/2019/LP/Grid/08/OF/04/08OF0485.zip`. Path = zone / 1/50000 sheet letters / 1/5000 digits / sheet code. The sheet code of a point is computable (`scripts/g14-asia-east/sheet.py`; X from -160 km by 40 km columns A-H, Y from +300 km by 30 km rows A-T, then 10 x 10 of 4 x 3 km, then 10 x 10 of 400 x 300 m).
- **Format**: ZIP (~2 MB) with an XYZ text file of 800 x 600 points at 0.5 m, mm values, EPSG:6676.
- **Versions**: FY folders; a sheet may exist in more than one (not checked); the Jogasaki sheet only in 2019.
- **Licence**: "distributed a dual license: CC-BY 4.0 and ODbL" (README of `aigidjp/opendata_virtualshizuoka`); the prefecture: open data, commercial use allowed.
- **Orthophoto**: per-sheet ortho zips (~7.5 MB) in the bucket, or GSI seamlessphoto.
- **Quick tests**: Jogasaki 08OF0485 (2019): 480 000 points, x 58000.25-58399.75, y -122699.75..-122400.25 (edges on whole metres), -0.51..36.67 m, no gaps (sea filled near 0), max slope 84.8° (GSI tile at the same place: 78.6° at 1 m).
- **Fit**: new driver (computed sheet grid + ZIPped XYZ text converted to GeoTIFF in the cache; close to SheetTiles) or own hosting (CC BY allows it). Works in EPSG:6676 directly: no resampling.
- **Open questions**: overlapping FYs; vertical datum (presumably T.P.); attribution wording the prefecture wants.
- **Links**: https://registry.opendata.aws/virtual_shizuoka/, https://github.com/aigidjp/opendata_virtualshizuoka, https://www.pref.shizuoka.jp/machizukuri/1049255/1052183.html

### Japan, Tokyo (Tokyo Digital Twin point clouds) - medium
- **Data**: airborne lidar (>= 16 pts/m²; island coasts with bathymetric lidar), Tama and islands published 2023-09, 23 wards 2024-10. Grids 0.5 m (spec) and 0.25 m ("参考データ"); DSM only as LAS ("平均サイズが約200MB…最も大きなファイルは約1GB").
- **Access**: static files `https://gic-tokyo.s3.ap-northeast-1.amazonaws.com/2023/dig/grd50/<sheet>.zip`; bucket listing denied; index as vector tiles `…/Vectortile/{tama,toushobu}/grd50/{z}/{x}/{y}.pbf` (`2024/…/23ku/` for the wards) with `MESH_NO` and `URL` per sheet, or the 索引図 zip on the CKAN datasets `tokyopc-tama-2023`, `tokyopc-shima-2023`, `tokyopc-23ku-2024`.
- **Format**: ZIP with one uncompressed float32 GeoTIFF 800 x 600 (1.9 MB), EPSG:6677, edges on whole metres, nodata 1.7e38.
- **Licence**: CC BY (CKAN).
- **Quick tests**: index tile z14 at Okutama listed 72 sheets; 09KC6361: 332-523 m, 100% valid; the computed sheet code matched.
- **Fit**: SheetTiles-like driver with the vector-tile or zip index (or computed codes; same sheet grid as Shizuoka, zone IX), or own hosting.
- **Highline**: Okutama gorges, Izu Islands sea cliffs (Hachijō, Ōshima, Kōzu).
- **Links**: https://www.geospatial.jp/ckan/dataset/tokyopc-tama-2023, https://www.geospatial.jp/ckan/dataset/tokyopc-shima-2023, https://www.metro.tokyo.lg.jp/information/press/2024/10/2024103126

### South Korea (NGII) - none
- **Data**: the open "공개DEM" is the 2015 90 m DEM (RMSE 6.2 m); data.go.kr 15059920 (2024-09, "이용허락범위 제한 없음", free, IMG) does not state its resolution; download on map.ngii.go.kr after login with a large-file transfer program. Finer DEMs (5 m) are not open to foreigners; export of survey results needs the inter-ministerial export council (Google's 1:5,000 base map approved 2026-02-27 under strict conditions, "contour lines excluded"). Spatial data security rules (국가공간정보 보안관리규정) classify data as 비공개/공개제한/공개.
- **Tests**: map.ngii.go.kr 400 to a plain request; vworld tiles need an API key. No automatic path.
- **Highline**: Bukhansan (Insubong), Seoraksan (Ulsanbawi), Jeju: high, but nothing beyond FABDEM.
- **Open questions**: the exact rule (article) on DEM grid spacing and export; whether a 5 m DEM is available to registered foreigners.
- **Links**: https://www.data.go.kr/data/15059920/fileData.do, https://www.newsis.com/view/NISX20150103_0013391823, https://www.khan.co.kr/article/202602271403001

### Taiwan (MOI) - low
- **Data**: 20 m DTM (2024 edition; 2025 edition with partial updates) and 20 m DSM, Open Government Data License v1. 1 m / 5 m lidar DEMs exist but "解析度5M與1M以下圖資因屬一般公務機密，僅開放政府機關透過申請進行介接" (dtm.moi.gov.tw).
- **Access**: data.gov.tw 169807 gives a CSV of 20 ZIP links on TGOS (whole Taiwan, per county). TGOS answered **403** to HEAD, ranged GET and its home page (Google front end): geo-blocking or a bot filter; not retried.
- **Orthophoto**: NLSC WMTS `https://wmts.nlsc.gov.tw/wmts/PHOTO2/default/GoogleMapsCompatible/{z}/{y}/{x}`, z18-20 OK at Long Dong, with an "NLSC 2024" watermark in the tile.
- **Fit**: none now; own hosting of the 20 m model would beat FABDEM a little (20 m vs 30 m) if TGOS can be reached.
- **Highline**: Long Dong sea cliffs, Taroko Gorge.
- **Links**: https://data.gov.tw/dataset/169807, https://data.gov.tw/dataset/169808, https://dtm.moi.gov.tw/Home/About

### Hong Kong (CEDD / LandsD) - medium
- **Data**: territory-wide airborne LiDAR 2010-11 (fixed wing) and 2019-12..2020-02 (helicopter): LAS 1.4, DTM and DSM (0.5 m in 2010; 2020 grid size not confirmed), HK1980 Grid (EPSG:2326) and HK Principal Datum. LandsD's open 5 m DTM: one ASCII grid, "±5m", includes "elevated roads and bridges", whole metres.
- **Access**: CEDD Spatial Data Portal `https://sdportal.cedd.gov.hk/` orders tiles (from its JS: `POST /webapi/submit {LutProductTileId, OrgType}`, then `/webapi/download/download-<id>.zip`; products DTM, DSM, LAS in GeoTIFF/ASCII). Not tried (an order). 5 m: `https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip` (28.7 MB).
- **Licence**: GEO open data T&C: use "for both commercial and non-commercial purposes on a free-of-charge basis", may "distribute, reproduce … the Data", naming the Government and the GEO Data Portal; the portal's own order terms not read (2012 order forms required consent before distribution).
- **Orthophoto**: LandsD `https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/imagery/WGS84/{z}/{x}/{y}.png`, z17-20 OK, clear, no watermark.
- **Quick tests**: 5 m DTM: 12751 x 9601, cellsize 5, xllcorner 799997.5 (centres on whole 5 m: `grid_origin` 0.5), sea 0, -19..948 m, 100% whole metres. 2020 metadata XML read.
- **Fit**: own hosting (GridTiles) of DTM/DSM ordered once from the portal, if its terms match the open data T&C; effort L.
- **Highline**: Lion Rock, Kowloon Peak, Shek O, Tung Lung Chau sea cliffs, Lantau.
- **Open questions**: portal terms; 2020 grid resolution; tile size and how many tiles; whether orders are anonymous.
- **Links**: https://portal.csdi.gov.hk/csdi-webpage/dataset/cedd_rcd_1629267205233_87895, https://www.ginfo.cedd.gov.hk/GEOOpenData/eng/LIDAR.aspx, https://www.ginfo.cedd.gov.hk/GEOOpenData/eng/TnC.aspx, https://data.gov.hk/en-data/dataset/hk-landsd-openmap-5m-grid-dtm

### China - none
No open fine DEM. Large-scale surveying results are state secrets under 测绘地理信息管理工作国家秘密范围的规定 (MNR and the National Administration of State Secrets Protection, in force 2020-07-01; a Beijing catalogue lists 1:10 000 DEMs as secret; a draft standard requires public DEMs degraded to no better than 15 m in elevation); foreign surveying needs approval. Yangshuo, Zhangjiajie, Enshi stay on FABDEM. Links: https://www.gov.cn/zhengce/zhengceku/2020-07/08/5525075/files/08e817f622814c4799255f2464bf9ed5.pdf

### Macau - none
No open elevation data found (DSCC); tiny, urban, no cliffs.

### Mongolia - none
No open national DEM found; OpenTopography has only fault-scarp surveys. Altai and Terelj granite stay on FABDEM.

### North Korea - none
No data.

## g15: Southeast Asia (2026-10-31)

Scripts: `scripts/g15-asia-southeast/` (`cog.py` window reads, `make_json.py` the rows), samples: `dl/g15-asia-southeast/`. Rows: [sources.json](sources.json) (11).

Summary: no country of the group publishes an open, automatically downloadable national DTM. The only open fine data is the Philippines' **Taal Open LiDAR** (1 m DTM/DSM, static GeoTIFFs on S3), which has little highline terrain. The famous karst areas (Railay/Tonsai, Ha Long/Cat Ba, Vang Vieng, Hpa-An, El Nido) stay on FABDEM / Copernicus GLO-30. Nothing for the group in OpenTopography's catalogue (only Sinabung and LUSI volcano surveys in Indonesia) or in Mapterhorn's source list.

### Thailand (RTSD / GISTDA / LDD): nothing open
- **Data**: no open national DTM or DSM. Fine elevation data belongs to the Royal Thai Survey Department (กรมแผนที่ทหาร), a military agency. A search snippet shows two RTSD LiDAR elevation datasets on data.go.th (1 m, vertical accuracy better than 15 cm, central river basins, updated 2023/2024, offered as shapefiles), not Krabi; I could not open them (see Access). GISTDA and the Royal Irrigation Department flew LiDAR on the lower Chao Phraya; GISTDA prepared "elevation data" for Hat Yai in 2025 (news), no product. The 2016 national geo-informatics master plan lists LiDAR and drone acquisition.
- **Access**: data.go.th (CKAN) answers an HTML "Access Denied" page to our User-Agent and 403 to WebFetch: it refuses automated clients. opendata.gistda.or.th (CKAN) works: 37 datasets, none with elevation (2 m satellite basemaps, 3D buildings LOD1/LOD2 as 3D Tiles behind an API key, one point cloud of a collapsed building).
- **Licence**: nothing to license. GISTDA's datasets say "Open Data Common".
- **Orthophoto**: GISTDA Basemap 2 m (Ziyuan-3, Gaofen-1, SPOT-6, THEOS mosaic) as XYZ `https://api-gateway.gistda.or.th/api/2.0/resources/tiles/basemap_latest/{z}/{x}/{y}.png?api_key=<key>`, with a free key from api-gateway.gistda.or.th. Untested (no key). 2 m is coarse for spotting anchors.
- **Quick tests**: GISTDA CKAN searches (DEM, LiDAR, elevation, Thai ความสูง): no elevation data. data.go.th: blocked.
- **Fit**: none (FABDEM). **Highline**: Railay / Tonsai / Phra Nang has an established highline scene; Ko Phi Phi, Ko Yao, Crazy Horse (Chiang Mai). Very high relevance with no data. 30 m models do not resolve the towers.
- **Open questions**: what the RTSD LiDAR listings on data.go.th hold and under what terms (a person in a browser could check). Whether a GISTDA key's terms allow a public site.
- **Links**: https://opendata.gistda.or.th/api/3/action/package_show?id=2-gistda, https://data.go.th/en/dataset?tags=LiDAR, https://un-ggim-ap.org/sites/default/files/media/meetings/Plenary05/201607/W020161026584902554813.pdf

### Vietnam: nothing open
The Department of Survey, Mapping and Geographic Information planned a 1:10 000 national database with a DEM (2008–2011, UN-GGIM country report), but it is not public. Open Development Mekong has only a 30 m SRTM-derived DEM (2000–2011), some of it non-commercial. Ha Long / Lan Ha / Cat Ba and Huu Lung would rank very high. Priority none.

### Philippines (Phil-LiDAR / LiPAD; NAMRIA): Taal open, the rest on request
- **Data**:
  - *Phil-LiDAR 1/2 and DREAM* (UP TCAGP, DOST, 2012–2017): 1 m DTM and DSM, classified LAZ and orthophotos of the major river basins and floodplains, mostly lowlands. 1 km tiles in WGS 84 / UTM 51N.
  - *Taal Open LiDAR* (released 2020-01-28 after the eruption): DTM, DSM, LAZ and 0.5 m orthophoto within 20 km of Taal, flown 2014–2017. The index has 1 608 cells of 1 km: 1 275 with DTM+DSM (about 1 275 km²), 438 with the orthophoto.
  - *NAMRIA IfSAR* (2013): 5 m DTM and DSM of the whole country (~300 000 km², 1 m RMSE).
- **Access**:
  - Taal: an index `https://phillidar-dad.github.io/data/taal-20km-grid.js` (GeoJSON assigned to a JS variable: `GRIDREF`, `MINX/MINY/MAXX/MAXY`, flags `DTM/DSM/ORTHO/LAZ`) and static files on S3: `https://phil-lidar-taal-s3.s3.us-east-2.amazonaws.com/Taal_DTM/<GRIDREF>_DTM.tif` (likewise `Taal_DSM/..._DSM.tif`, `Taal_ORTHO/..._ORTHO_PL1.tif`, `Taal_LAZ/..._LAZ_PL1.laz`). The bucket listing is denied, so the index is needed. No key, no stated fair use.
  - The rest of Phil-LiDAR: LiPAD (https://lipad.dream.upd.edu.ph/) has been "under maintenance" since 2019. You register through a Google Form, file a data request form, then e-mail a formal letter and an area shapefile. Approved users get an account, free for government, academe and research. Private or commercial use goes to the Business Development Officer. Flood hazard maps download without an account (lipad-fmc GeoNode/GeoServer).
  - NAMRIA IfSAR: a formal letter to the NAMRIA Administrator. FOI requests for it were redirected there. The 2026 Citizen's Charter lists DSM/DTM among the free products; a 2023 "proposed" fee schedule charges per hectare. namria.gov.ph refused connections today.
- **Versions**: one survey per cell.
- **Licence**: Taal: "We don't have a final license yet but for now think of it as CC-SA-BY". Cite UP TCAGP and the PHIL-LiDAR Program, keep derived products open, do not sell the data. The rest is under request terms for the stated project. https://dream.upd.edu.ph/news/up-tcagp-releases-taal-open-lidar-data/
- **Orthophoto**: only the Taal 0.5 m GeoTIFFs (uncompressed, 2000 × 2000 px); no WMS/WMTS of our own to use.
- **Quick tests** (2026-10-31): cell E303N1550: DTM HEAD 4.85 MB (AmazonS3, 2020-01-24). `/vsicurl/` DTM and DSM: EPSG:32651, 1100 × 1100 float32, origin (302950, 1550050), 1 m pixels, nodata −3.4e38. Files are uncompressed with one-row strips and no overviews (a whole file per read, ~1–2 s). A 500 × 500 window was 100% valid, 280–302 m, values not rounded to cm. The orthophoto is RGB 0.5 m.
- **Fit**: Taal only. A small IndexedTiles subclass: a static index (parse the JSON out of the JS file, or freeze the list of cells) and a GeoTIFF per cell. Crop the 50 m buffer: cells overlap, the name is the core's top-left km (E303N1550 = x 303–304 km, y 1549–1550 km). Edges sit on whole metres, so `grid_origin` 0. The vertical datum is not in the files (DREAM reports: MSL via EGM2008-referred benchmarks); check against Copernicus. Effort S, but the payoff is small.
- **Highline**: Taal caldera rim and island: low. Climbing areas elsewhere are high relevance: Wawa Gorge / Montalban (Rizal), Cantabaco (Cebu), Atimonan, and the El Nido and Coron limestone (Palawan). Whether Phil-LiDAR covers them is unknown, since the coverage map is in LiPAD.
- **Open questions**: Phil-LiDAR coverage over the climbing areas. Whether an approved LiPAD account could serve a public site (probably not). The final Taal licence. Whether NAMRIA's IfSAR 5 m is free to private requesters, and on what terms.
- **Links**: https://lipad.dream.upd.edu.ph/, https://lipad-fmc.dream.upd.edu.ph/help/, https://phillidar-dad.github.io/taal-open-lidar.html, https://dream.upd.edu.ph/news/up-tcagp-releases-taal-open-lidar-data/, https://namria.gov.ph/Downloads/CitizensCharter/2026/External/Request%20for%20Free%20Products%20and%20Services.pdf, https://foi.gov.ph/requests/digital-elevation-model-with-5m-resolution

### Malaysia (JUPEM): LiDAR of flood basins, not reachable
- **Data**: JUPEM flies airborne LiDAR and makes DSM, DEM and DTM from it (ACRS 2020 paper). The government open-data archive lists, among others, "Digital Terrain Model (DTM) Lidar Bagi Kawasan/Lembar Lembangan Sungai Kelantan Dan Terengganu 2016" and the matching DSM (JUPEM; created 2018, updated 2021). Resolution, format and licence are unknown. There is no national fine DTM.
- **Access**: archive.data.gov.my refused connections today (ECONNREFUSED, also for WebFetch). JUPEM separates non-restricted data (from the website) from restricted data, which need security vetting and defence clearance (UN-GGIM 2016).
- **Fit**: none. **Highline**: Batu Caves and Damai Wall, the Gunung Lang / Ipoh towers, Langkawi (Machincang), Kinabalu. Priority low: a listing exists but cannot be reached and is probably restricted.
- **Open questions**: whether the archived DTM resources were real downloads, and their licence; whether the new data.gov.my carries them.
- **Links**: https://archive.data.gov.my/data/en_US/dataset/?tags=DTM, https://a-a-r-s.org/./proceeding/ACRS2020/o8rs4v.pdf, https://ggim.un.org/meetings/2016-Malaysia/documents/02%20Dato'%20Jagjit%20Singh.pdf

### Singapore (SLA): national LiDAR, not published
SLA's National 3D Mapping (2014, 2019) has a DTM, a DSM and point clouds of the whole country, shared with government and research but not published. data.gov.sg has nothing on elevation, and OneMap3D is a viewer. The orthophoto would be OneMap Satellite XYZ `https://www.onemap.gov.sg/maps/tiles/Satellite/{z}/{x}/{y}.png` (z18 and z19 at Bukit Timah: a clear aerial image, ~15 kB PNG; terms page not read). Highline relevance very low. Priority none.

### Indonesia (BIG): DEMNAS 8 m, account needed
- **Data**: DEMNAS, 0.27 arc-second (~8 m), built from IFSAR 5 m, TerraSAR-X 5 m and ALOS PALSAR 11.25 m plus stereo-plotted mass points, heights on EGM2008 (BIG product page). Radar sources make it largely a surface model over forest. A UGM thesis says small islands are missing; a Karimunjawa study measured RMSE 6.3 m and LE90 10.5 m. No open LiDAR (OpenTopography holds only volcano surveys: Sinabung 2014/2018, LUSI 2018).
- **Access**: Ina-Geoportal https://tanahair.indonesia.go.id/portal-web/ (a React app; API base `https://tanahair.indonesia.go.id/api-inageo/`, `/auth/signin`, `/auth/signup`, OTP by e-mail or WhatsApp). Registration needs a name, e-mail, WhatsApp number and password. Downloads per tile as GeoTIFF float32. The third-party "BIG Downloader" plugin (QGIS/ArcGIS, 2026-09) takes the `accessToken` of the sign-in response, valid about 1–2 h, so an automatic client would have to sign in again regularly. The old `tides.big.go.id/DEMNAS/` named on BIG's page times out. The national DEM index is on data.go.id as a WMS, marked "Terbuka" (open).
- **Licence**: unclear. No terms found for the DEM itself; data.go.id's "Terbuka" covers the index listing.
- **Orthophoto**: none open found.
- **Quick tests** (2026-10-31): portal HTML and main JS bundle (610 kB) list only the auth endpoints; `/demnas/` is an empty page. With no account, no file was tested.
- **Fit**: new driver: a tile grid behind a sign-in token. Gain over FABDEM is modest: 8 m vs 30 m, but a radar surface model in forest. Effort M.
- **Highline**: Harau Valley (West Sumatra), the Siung / Gunung Kidul sea cliffs, Rammang-Rammang / Maros karst, Tebing Parang, Uluwatu (Bali): high. Priority low.
- **Open questions**: the licence (ask BIG); tile grid and file size; whether accounts are open to foreigners (WhatsApp OTP).
- **Links**: https://big.go.id/en/content/produk/demnas, https://data.go.id/dataset/dataset/indeks_dem_nasional, https://github.com/ahzastudio/bigtools-web, https://plugins.qgis.org/plugins/big_downloader_toolbox/

### Laos: nothing open
Only global models (SRTM, the Global Map 30″ DEM). Mekong River Commission floodplain LiDAR is for member agencies. Vang Vieng and Thakhek karst (high relevance) stay on FABDEM.

### Cambodia: nothing open
A 30 m SRTM-derived DEM on Open Development Cambodia; no national fine DEM found. Low relevance (Battambang, Kampot limestone).

### Myanmar: nothing open
Only 30 m global DEMs (Open Development Myanmar). Hpa-An karst (Zwegabin, Kyauk Kalat) is of medium relevance.

### Brunei: nothing open
Nothing found; very few cliffs.

### Timor-Leste: nothing open
Nothing found; low relevance (Ramelau, Atauro).

## South and Central Asia, Russia (g16): elevation data survey, 2026-10-31

Summary: no country of this group publishes fine elevation data that a public site could download automatically. India, Russia and Kazakhstan restrict fine relief by law or policy; Nepal's only lidar is in the flat Terai; the national geoportals of Nepal, Kyrgyzstan, Bhutan and Russia did not answer from here. The one cross-border candidate is NASA's **High Mountain Asia 8 m DEM** (a DSM from stereo satellite imagery, 2002–2016), which covers every mountain climbing area of the group from the Tien Shan to Bhutan, behind a free Earthdata Login (row `hma`). Sri Lanka has a CC BY 4.0 national 20 m DEM and a 0.5 m patch, as archives only.

Scripts: `scripts/g16-asia-south-central/` (`get.py` capped GET/HEAD, `zipdir.py` remote ZIP directory, `otcat.py` OpenTopography catalogue per country, `pgcstac.py` EarthDEM at climbing places, `cmr_hma.py` HMA granules at climbing places, `pdfgrep.py`). Samples: `dl/g16-asia-south-central/`.

### India (in): Survey of India, ISRO/NRSC
- **Data**:
  - Survey of India sells a "1:50K Digital Terrain Model", a 10 m DEM from the contours of the Open Series Maps, per sheet (OVSF/50K/11, IMG or TIFF, Rs 3300, "Single User").
  - SoI also holds project DEMs: 1 m for river buffers (National Hydrology Project: UP, Bihar, WB, Goa; Clean Ganga 10 km buffer, about 73,000 km² together) and 0.5 m for the 7 km coastal strip (ICZM, 73,575 km²). The page says they are "available with SOI for Government agencies/organizations, which can be obtained in offline mode" (as of 2023-05).
  - ISRO/NRSC: CartoDEM v3 R1 (1″, ~30 m) is a free download from Bhuvan/Bhoonidhi after login, but it is a DSM in whole metres and no better than FABDEM. CartoDEM 10 m costs the base price. CartoDSM 2.5 m (Cartosat-1 stereo, 2024, 7.5′ tiles, about 1% gaps) is newer.
- **Access**: everything goes through manual portals: the SoI online maps portal with a cart, and Bhoonidhi, whose STAC-based API needs a token after login (`bhoonidhi-api.nrsc.gov.in/data/collections` answers 401 "Invalid session"). Bhuvan limits downloads to 10 tiles a day (help page; an older text says 20).
- **Licence**:
  - NRSC: "IRS Satellite derived DEM with 30m or coarser posting shall be made available as free download". 10 m DEMs go at the base price. "Other private, foreign and other users, may obtain the data after necessary clearance from the competent ISRO/DOS committee"; restricted areas need HRC clearance even at 10 m.
  - Geospatial Data Guidelines (15 Feb 2021) and NGP 2022: data finer than 1 m horizontal / 3 m vertical accuracy may be owned only by Indian entities and must be stored and processed in India. So neither own hosting nor a cache on a VPS abroad is possible for fine data.
- **Orthophoto**: no open service found. The Bhuvan WMS (`bhuvan-vec1.nrsc.gov.in/bhuvan/wms`, 6679 layers, Fees NONE) has only thematic vector layers; its "Elevation" layers are vectors of single projects.
- **Quick tests**: Bhoonidhi API 401; Bhuvan WMS GetCapabilities 10 MB in 20 s with no elevation raster or imagery; SoI price list read.
- **Fit**: none (FABDEM). The Himalayan part (Ladakh, Himachal, Uttarakhand, Sikkim) is covered by HMA 8 m; Hampi, Badami and the Sahyadri are not.
- **Highline**: Hampi granite, Badami sandstone, the Sahyadri forts of Maharashtra (a local highline scene), Himalaya: high terrain, no data.
- **Open questions**: does Bhoonidhi register foreign users for the free 30 m CartoDEM (irrelevant next to FABDEM)? The price and terms of CartoDSM 2.5 m.
- **Links**: https://onlinemaps.surveyofindia.gov.in/Digital_Product_Show.aspx, https://onlinemaps.surveyofindia.gov.in/PricingPolicy.aspx, https://surveyofindia.gov.in/pages/availability-of-ori-and-dem, https://www.nrsc.gov.in/nrscnew/Dataproducts_Thematic_cartodem.php, https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/, https://www.nrsc.gov.in/sites/default/files/pdf/ebooks/UIM-2024/12_UIM_2024.pdf, https://dst.gov.in/sites/default/files/Final%20Approved%20Guidelines%20on%20Geospatial%20Data.pdf

### Nepal (np): Survey Department
- **Data**: the department's lidar project in the Western Terai (Chitwan to Kanchanpur, about 20,000 km²) produced a 1 m DTM and a 0.15 m orthophoto. Acquisition was complete in 2022 and processing ongoing; the data went to the local governments. A lidar survey of the whole country is "planned". Older 20 m DEMs come from the contours of the 1:25K/1:50K maps. The Terai is flat: no cliffs.
- **Access**: the National Geoportal (`nationalgeoportal.gov.np`, data "Free / Paid" per a FIG 2023 talk) refused connections or timed out from here. No public download of the lidar is documented.
- **Licence**: unclear; the department sells data (price list in its Journal on Geoinformatics).
- **Quick tests**: the geoportal is unreachable. OpenTopography has 4 research sets (faults in Western Nepal 2021, Gorkha landslides 2015), none at climbing areas.
- **Fit**: none (FABDEM); HMA 8 m covers the whole Himalaya (Khumbu tile 677, Annapurna 641).
- **Links**: https://nepjol.info/index.php/NJG/article/view/39481, https://events.development.asia/sites/default/files/materials/2022/10/202210-survey-department-national-mapping-agency-nepal.pdf, https://fig.net/resources/proceedings/fig_proceedings/7_2023/ppt/se06/SE06_oli_pudasaini_et_al_12353_ppt.pdf

### Pakistan (pk)
No open DEM: Survey of Pakistan supplies data "on-demand as may be prescribed" (UN-GGIM country report), and only the 30″ Global Map DEM of 2007 is public. OpenTopography has only a research set of the 2013 Balochistan earthquake. The Karakoram (Hunza tile 336, Trango 370) is in HMA 8 m.

### Kyrgyzstan (kg)
- **Data**: no open national DEM.
  - A Kyrgyz-Norwegian project has flown 23,000 km² of aerial photography since 2018, for a geoportal "for providing access to ortho-photo maps for state and other bodies" (ADB 2022). The geoportal it names, `kyrgyzmap.kg`, timed out.
  - The Ministry of Emergencies bought DTMs under RESILAND (carececo.org; its TLS chain failed for the fetcher).
  - The CAIAG GeoNode offers only an ASTER GDEM v2 DEM and a 30 m shaded relief (ODbL): worse than FABDEM.
- **Quick tests**: the GeoNode API lists 52 layers, two of them elevation. OpenTopography has about 20 research sets (fault scarps at Chon Kemin, Chon Aksu, Naryn, At-Bashi, Song Kul; satellite point clouds; "Bishkek city 2013" Pleiades), none at Ala Archa or Karavshin.
- **Fit**: none; HMA 8 m has mosaic tiles at Ala Archa (106) and Karavshin (200), and AT/CT strips at Ala Archa (3 cross-track pairs, 2012).
- **Links**: https://events.development.asia/sites/default/files/materials/2022/10/202210-national-spatial-data-infrastructure-kyrgyzstan.pdf, https://geonode.caiag.kg/layers/geonode:kyrg_shaded_rel_30m_geotiff

### Kazakhstan (kz)
- No open DEM. The NSDI state geoportal runs under Law 166-VII ZRK of 2022 (parts in force 2025); a DTM "for flood management" is a target system of the plan (ADB 2024). The rules of the National Cartographic-Geodetic Fund refer to the Law on State Secrets; the exact regime for relief is unclear.
- OpenTopography has research sets around Almaty (range front fault, city DSMs from Pleiades/SPOT 2014/2017) and on the Dzhungarian fault, none at Charyn. HMA 8 m covers Charyn (tile 109) and the Zailiysky Alatau.
- **Links**: https://events.development.asia/system/files/materials/2024/11/202411-kazakhstan-national-center-geodesy-and-spatial-information_0.pdf, https://leap.unep.org/en/countries/kz/national-legislation/law-no-166-vii-zrk-republic-kazakhstan-geodesy-cartography-and

### Russia (ru): full row, replaces the short row of g7
- **Data**:
  - Rosreestr / PPK Roskadastr run the Federal Spatial Data Fund (FFPD) and, since 2024, the National Spatial Data System (NSPD, `nspd.gov.ru`, also the public cadastral map).
  - The unified electronic cartographic base (EEKO) is shown on `portal.fppd.cgkipd.ru`. Roskadastr makes orthophotos and DEMs to order.
  - Roscosmos' "Digital Earth" sells imagery and thematic products through individual or collective access.
  - No open DEM and no open regional elevation data was found.
- **Legal limits**: Federal Law 431-FZ, art. 24, binds geodetic and mapping work to the protection of state secrets. Topographic maps are public only at 1:100,000 and smaller, with secret objects removed (Bellona), and high-resolution maps are withheld from foreigners (The Week, older). Treat fine relief of Russia as not publishable.
- **Access from abroad**: `nspd.gov.ru` gave no answer in 60 s and `cgkipd.ru` timed out. The FFPD portal presents a certificate of the "Russian Trusted Sub CA" (Ministry of Digital Development), which standard clients do not trust; I did not bypass the verification.
- **ArcticDEM**: covers the north (Kola/Khibiny, Putorana, Kamchatka, Chukotka); see the row `arcticdem` of g9. EarthDEM's public strips (PGC STAC, CC BY 4.0) lie only around the Great Lakes: none here. HMA's box ends at 46° N, so none of Russia.
- **Fit**: none (FABDEM); ArcticDEM north of ~60° N.
- **Highline**: Krasnoyarsk Stolby, Ergaki, Caucasus (Dombay, Arkhyz, Elbrus region), Karelian lake cliffs; Khibiny, Putorana and Kamchatka are in ArcticDEM.
- **Links**: https://www.consultant.ru/document/cons_doc_LAW_191496/4b630a314af3145726f6c9e9605caff2aa224571/, https://bellona.org/?p=15549, https://theweek.com/articles/524086/don146t-look-closely, https://t-j.ru/nspd/

### High Mountain Asia 8 m DEM (hma): NASA/NSIDC, cross-border
- **Data**: HMA_DEM8m_MOS v1 (D. Shean 2017) is an 8 m mosaic of DEMs from stereo Maxar imagery (WorldView-1/2/3, GeoEye-1, QuickBird-2) of 2002–2016, over lat 26–46° N and lon 67–103° E. The per-pair strips HMA_DEM8m_AT (along-track) and HMA_DEM8m_CT (cross-track) carry dates. It is a surface model (snow, glaciers, trees), with possible voids in steep shadowed walls. NSIDC gives EPSG:4326; the vertical datum is not stated (probably the WGS84 ellipsoid).
- **Access**:
  - The NASA CMR granule search needs no login (`short_name=HMA_DEM8m_MOS&bounding_box=...`) and gives tiles `HMA_DEM8m_MOS_20170716_tile-<n>.tif` on `data.nsidc.earthdatacloud.nasa.gov`.
  - A GET needs an Earthdata Login (a free account; a bearer token works for scripts). An unauthenticated HEAD goes through: tile-106 is 304,610,903 bytes on CloudFront/S3 with `Accept-Ranges: bytes`.
- **Licence**: NASA open data; the page asks only "As a condition of using these data, you must cite the use of this data set" (doi:10.5067/KXOVQ9L172S2). The imagery behind it was NGA NextView-licensed, so commercial use and redistribution stay "unclear".
- **Quick tests**: a mosaic tile at every mountain place tried (Ala Archa 106, Karavshin 200, Charyn 109, Hunza 336, Trango 370, Fann 199, Chimgan 135, Khumbu 677, Annapurna 641, Thimphu 680, Manali 503); none at Hampi. Sizes are 83–370 MB. Whether the files are tiled or COG is not checked (needs a login).
- **Fit**: an `IndexedTiles` layer with CMR as index and `/vsicurl/` windows with the token (`GDAL_HTTP_HEADERS`), as `TnmBlocks`, if the files are tiled; otherwise own hosting. At 8 m it is between 5 m ("coarse but usable") and 10 m ("poor"): better than FABDEM in steep walls only if the voids are few.
- **Open questions**: the tiling, CRS and vertical datum of a real file (a login test); a void check at Ala Archa against FABDEM; whether NSIDC is happy with on-demand reads from a public site.
- **Links**: https://nsidc.org/data/hma_dem8m_mos/versions/1, https://nsidc.org/data/HMA_DEM8m_CT/versions/1, https://catalog.data.gov/dataset/high-mountain-asia-8-meter-dem-mosaics-derived-from-optical-imagery-v001

### Sri Lanka (lk)
- The World Bank / ESA EO4SD (VaeSSA, 2014–2016) published a national 20 m DEM and a 0.5 m "precise DEM" from Pleiades tri-stereo (380 km² of flood catchments, ±2 m), under **CC BY 4.0** (energydata.info CKAN; the landing page answers 403 to the fetcher, the API works).
- Both are ERDAS IMG in SLD99 (EPSG:5235) in ZIPs: 20 m 32 MB, 0.5 m 6.5 GB (Deflate, ZIP64; members `.img`, a 3.1 GB `.rde`, `.rrd`, `.ige`). Read from the central directories by range requests.
- Own hosting would be legal, but 20 m hardly beats FABDEM and the 0.5 m area has no notable cliffs. Ella, World's End and Sigiriya stay on FABDEM. Priority low.

### Short rows
- **Bhutan (bt)**: the NLCS GeoPortal (GeoNetwork `cgi-gn.nlcs.gov.bt`) timed out. JICA's aerial survey produced a DTM and 1:25K/1:5K maps (handed over 2025), with access unclear. HMA 8 m covers it (Thimphu tile 680).
- **Bangladesh (bd)**: nothing open; flat delta.
- **Maldives (mv)**: nothing; atolls at 1–2 m, no highline terrain.
- **Tajikistan (tj)**: nothing national. The Fann mountains (tile 199) and the Pamir are in HMA 8 m.
- **Uzbekistan (uz)**: nothing national; Chimgan is in HMA 8 m (tile 135).
- **Turkmenistan (tm)**: nothing; OpenTopography has research point clouds of the Kopet Dag.
- **Afghanistan (af)**: nothing (AGCHO; USGS's 2013 project had only SRTM 90 m); HMA 8 m covers the area east of 67° E.

## Group g17-asia-west: elevation sources (researched 2026-10-31)

Western Asia: Turkey, the Levant, the Arabian Peninsula and Iran. Summary: **nothing usable beyond FABDEM/Copernicus anywhere in the group.** Fine elevation data is held by defence or national survey agencies (HGM in Turkey, NSA in Oman, MAPI in Israel, RJGC in Jordan, NCC in Iran, GEOSA in Saudi Arabia). It is sold, given out on request, or shown only as rendered maps. No national product of 5–30 m that beats Copernicus GLO-30 is open either. Many government hosts refuse or drop foreign/automated clients (Turkey, Israel, Oman, Saudi Arabia, Iran, UAE), so even a future open product may need a check from another network. OpenTopography's catalogue (25–63° E, 12–43° N) holds one small LiDAR set (Israel's Sharon sea cliffs, 2006, no licence) and research satellite DSMs of fault zones (Iran, Saudi Arabia).

The Turkish row replaces the short row of g7-southeast-east. Scripts: `scripts/g17-asia-west/` (`make_json.py`); samples: `dl/g17-asia-west/` (OpenTopography catalogue answers, the GEOSA open-data page).

---

### Turkey (HGM, TKGM, CBSGM, municipalities): nothing open
- **Data**: HGM (General Directorate of Mapping, Ministry of National Defence) makes the national products: DTED-2 (1″, about 30 m), described in 2018 as "the densest countrywide grid", and a "local DEM" digitised from the contours of the 1:25,000 series. A 2018 study proposed a 5 m national DEM (32-bit GeoTIFF); no such product has been published. No national LiDAR programme was found (TKGM or HGM). Istanbul (İBB, Harita Şube Müdürlüğü) has a LiDAR DSM/DTM/nDSM per 1:1000 sheet and a 2 m DTM per district. These are listed **in a price list**, not on its open-data portal.
- **Access**: no open service. HGM sells (harita.gov.tr refused connections from here; HGM Atlas needs an account). The CBSGM/ULASAV open data of the Ministry of Environment includes only a WMS of **SRTM 90 m** (`tucbs-public-api.csb.gov.tr/trk_srtm_wms`, layer `srtm_tr_90m`, rendered pictures; listed in JOSM's imagery list with "ULASAV Açık Veri" attribution). The İBB open-data portal (data.ibb.gov.tr, CKAN) has no elevation dataset, according to the reports and search results.
- **Licence**: sale (HGM, İBB). ULASAV has an open licence (`ulasav.csb.gov.tr/license`, not reachable), but there is nothing worth using under it.
- **Orthophoto**: HGM Atlas (account; terms unclear). TKGM shows orthophotos in its parcel viewer. A TKGM document of 2020 discusses OGC WMS for orthophotos and whether they should be paid; no open WMTS was found.
- **Quick tests** (2026-10-31): harita.gov.tr ECONNREFUSED. data.ibb.gov.tr TCP timeout. tucbs-public-api.csb.gov.tr timed out (21 s). ulasav.csb.gov.tr has no DNS (also from the web fetcher). tkgm.gov.tr answers, but its front page links no open data or elevation. OpenTopography has no Turkish dataset.
- **Fit**: none (FABDEM/Copernicus). This hurts: Geyikbayırı, the Antalya coast and Olympos, Cappadocia's tuff valleys, Aladağlar, Kaçkar and the Taurus gorges are prime highline terrain.
- **Open questions**: does HGM sell 5 m DEMs or LiDAR to foreigners, and on what terms (likely no redistribution)? Would Antalya or other metropolitan municipalities share LiDAR on request? Are the Turkish hosts reachable from a Turkish/EU network (they may filter by country)?
- **Links**: https://josm.openstreetmap.de/wiki/Maps/Turkey, https://uploads.ibb.istanbul/uploads/Harita_Sube_Mudurlugu_d22c561767.pdf, https://www.acarindex.com/international-journal-of-engineering-and-geosciences/-685199, https://turkiye.gov.tr/harita-genel-mudurlugu, https://www.tkgm.gov.tr/sites/default/files/2020-10/19.pdf

### Israel (Survey of Israel, MAPI): no open DTM; a contested 3D release
- **Data**: MAPI makes 50 cm DSM/DTM by photogrammetry (ISPRS 2022) and has an old 25 m national DTM (proprietary; academic use under a signed agreement, 2008). In July 2025 MAPI announced a new GovMap with public 3D models (no registration). This drew public objections on security grounds (Calcalist 2025-07-20; N12/mako 2025-08), and the outcome was not found. OpenTopography hosts the **Sharon sea-cliff LiDAR of 2006**: 29 km² along 30 km of coast from Herzliya to Olga, 1 m DTM and DSM, EPSG:2039. Its licence is "Not Provided" and its vertical datum unknown.
- **Access**: data.gov.il, organisation `israel_mapping_center`, has 117 datasets, all read through its CKAN API. They are cadastre, map indexes, roads, gazetteer, tree canopy and 2 m orthophotos of 2015 per 1:50k sheet (ZIP). **None is elevation**, and the licence field of the orthophoto sheets is empty. gov.il, data.gov.il and govmap.gov.il answer our client with 403 (CloudFront) or a 404 error page. The API was read through the third-party web fetcher.
- **Licence**: older GovMap terms say MAPI holds all copyright, and uses must be requested from the Survey's director.
- **Orthophoto**: GovMap viewer (terms unclear); the 2 m ZIP sheets of 2015 (too coarse, no licence).
- **Quick tests** (2026-10-31): CKAN `q=DTM`: 0 hits; the organisation listing has no elevation. HEAD of an orthophoto ZIP: 403 CloudFront. OpenTopography catalogue: the Sharon set only.
- **Fit**: none. The OT Sharon set is small, unlicensed and of low highline interest (sandstone cliffs up to 50 m).
- **Open questions**: did the 2025 GovMap 3D release go ahead, and does it include a DTM/DSM with reuse terms? Watch MAPI announcements.
- **Links**: https://data.gov.il/api/3/action/package_search?fq=organization:israel_mapping_center&rows=100, https://portal.opentopography.org/raster?opentopoID=OTSDEM.102016.2039.1, https://www.calcalist.co.il/calcalistech/article/rkqwhlulxx, https://www.mako.co.il/news-columns/2025_q3/Article-409f6f214806891027.htm, https://isprs-archives.copernicus.org/articles/XLIII-B4-2022/363/2022/isprs-archives-XLIII-B4-2022-363-2022.pdf, https://community.openstreetmap.org/t/using-publicly-available-government-maps/50310

### Jordan (RJGC): nothing open
RJGC sells maps and orthophotos (research projects bought them). Its only public DEM is 30″ (2006). opendata.gov.jo holds an RJGC table of spot heights only; it is not CKAN, and the dataset page answered 404. Wadi Rum, Petra, Wadi Mujib and Dana are excellent highline terrain, but they stay on FABDEM. Links: https://geodata.libraries.mit.edu/record/gisogm:edu.columbia:34680475a37f

### Oman (NSA, Ministry of Defence): DEM/DSM on request only
The NSA geoportal has a request form listing a DEM, a DSM and roads; a humanitarian research request was seen. The NSA runs ONGD17 and OMANGEOID, and bought a mobile mapping system. data.gov.om (Open Government Licence – Oman) has no elevation. The NSA geoportal answers "Request Rejected" (F5 WAF) to our client on every path, so nothing could be tested. Very high highline value (Jebel Akhdar, Jebel Shams, Snake Canyon, the Musandam fjords), but defence-held data: an e-mail request is the only route, and a public site is unlikely to be allowed. Links: https://gisserver.nsaomangeoportal.gov.om/en/about-nsa, https://www.omanobserver.om/article/1136726/oman/nsa-obtains-mobile-mapping-system

### Iran (NCC): a rendered WMS only
Since May 2025 the national SDI (`https://iransdi.ncc.gov.ir/layersf`) serves the NCC DEM of "different zones" as a GeoServer WMS (ImagePyramid). These are pictures with no stated resolution or terms. The hosts fail TLS from here (curl exit 35). Sanctions make any use doubtful. OpenTopography has only research satellite DSMs of fault zones. Links: https://ana.ir/en/news/8945/iran-digitizes-elevation-mapping

### Lebanon: nothing
No open DEM. Vendors sell 20–90 m (Beirut 5–10 m); AUB's contour data is for AUB members only. Qadisha and Baatara stay on FABDEM. Links: https://scholarworks.aub.edu.lb/items/41d85657-7399-48e0-a722-384d16578736

### United Arab Emirates: nothing found
No elevation in Dubai Pulse, Dubai Municipality's open data, Bayanat or the Abu Dhabi SDI. The federal geoportal (geoportal.fgic.gov.ae) is a JS app with no public REST, OWS or CSW path. dubaipulse.gov.ae and geoportal.abudhabi.ae did not connect from here. Ras Al Khaimah's Hajar (Jebel Jais, Wadi Shawka) stays on FABDEM. Links: https://geoportal.fgic.gov.ae/, https://u.ae/en/about-the-uae/digital-uae/data/geospatial-data-platforms

### Saudi Arabia (GEOSA): elevations in the national platform, not open
"Elevations" is one of 15 fundamental layers of the National Geospatial Platform (geoportal.sa), shared "in accordance with a defined publication policy". The open-data page offers "Information on Digital Surface and Terrain Models": information about them, not the models; its list is loaded by script. GEOSA's open data is free of restrictions per dataset licence, but no elevation dataset is among it. geoportal.sa answers "Request Rejected" (WAF). Tuwaiq escarpment, Asir and AlUla stay on FABDEM. Open question: does geoportal.sa give registered users a DEM download, and on what terms? Links: https://geosa.gov.sa/en/About/Pages/Open_data.aspx, https://www.geosa.gov.sa/en/Pages/nationalgeospatialplatform.aspx

### Short rows: Palestine, Syria, Iraq, Qatar, Bahrain, Kuwait, Yemen
No open national elevation data found:
- **Palestine**: GeoMOLG shows orthophotos; no DEM download.
- **Syria**, **Iraq** (incl. Kurdistan's gorges): nothing open.
- **Qatar**, **Bahrain**, **Kuwait**: flat; only a 250 m SRTM-derived Gulf DEM on HDX (ODC-BY) and Bahrain's 30″ DEM of 2008.
- **Yemen**: nothing. Socotra's cliffs stay on FABDEM.

All stay on FABDEM/Copernicus.
