# Recorded answers of the index services

Real answers of the services our indexes ask, recorded once by `tools/record_answers.py` (2026-10-31) for
the offline tests of `tests/test_parts.py`: `tests/http_server.py` serves them again (the recorded hosts
replaced by its own address) and the code must write `expected.json` byte for byte, the index answer the
code that recorded them wrote. Each case asks for one 0.25° tile at the edge of the data, so the answers
stay small.

| Folder | Service | Tile (south-west corner) | Origin and licence |
| --- | --- | --- | --- |
| `wfs/geoportal-nmt/` | geoportal.gov.pl WFS sheet index of the NMT (GetCapabilities, GetFeature per year) | 54.75° N, 18.5° E (the Hel peninsula, the sea) | Główny Urząd Geodezji i Kartografii (GUGiK), [geoportal.gov.pl terms](https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/): free use, source stated |
| `wfs/geoportal-error/` | geoportal.gov.pl WFS sheet index of the NMT: its exception report to a GetFeature of a layer that does not exist (`gugik:SkorowidzNMT1900`; answered with HTTP 400, recorded 2026-11-01) | 54.75° N, 18.5° E | Główny Urząd Geodezji i Kartografii (GUGiK), [geoportal.gov.pl terms](https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/): free use, source stated |
| `stac/swisstopo-swissalti3d/` | swisstopo STAC API, items of swissALTI3D (two pages) | 47.75° N, 8.5° E (Schaffhausen, the German border) | © swisstopo, [OGD terms](https://www.swisstopo.admin.ch/en/conditions-geodata): free use, source stated |
| `stac/lgln-dgm1/` | LGLN STAC API, items of the DGM1 (one page; 15 tiles of 1 km with two surveys each) | 52.75° N, 11.5° E (the Elbe, the eastern edge of Lower Saxony) | © GeoBasis-DE/LGLN 2026, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| `tnm/dem1m/` | The National Map Access API, products of the 1 m DEM | 48.75° N, 95.25° W (Lake of the Woods, the Canadian border) | USGS, public domain |
| `tnm/ifsar5m/` | The National Map Access API, products of Alaska's IfSAR DTM | 59.75° N, 141° W (the Gulf of Alaska) | USGS, public domain |
| `arcgis/lidarbc-dem/` | LidarBC's index, an ArcGIS FeatureServer (`LiDAR_BC_S3_Public`, query of the DEM layers 6 and 5 over the tile, recorded 2026-11-03), then GeoBC's S3 bucket (`nrs.objectstore.gov.bc.ca/gdwuts`, ListObjectsV2) under each sheet and survey folder the index named: two hosts, the bucket's addresses in `expected.json` | 48.25° N, 124.5° W (the south-west coast of Vancouver Island, the edge of the data) | Province of British Columbia (GeoBC), [Open Government Licence – British Columbia](https://www2.gov.bc.ca/gov/content/data/policy-standards/open-data/open-government-licence-bc) (the bucket's file names, dates and ETags); the index item is "Access Only": its answers are kept here only as test data of our own queries |
| `wfs/sardinia-dtm/` | Regione Sardegna's GeoServer WFS of the coastal lidar's tiles (`dbu:QU2k_fasciacostiera2008_DTM_DSM1m`, GetFeature as GeoJSON with the footprints in EPSG:32632, 85 features; recorded 2026-11-15) | 40.25° N, 9.5° E (the Gulf of Orosei, Cala Gonone) | Regione Autonoma della Sardegna, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (record R_SARDEG:BFPNM) |
| `inegi/mexico-dtm/` | INEGI's download viewer (elevacionesmex), the JSON of one sheet of the 5 m lidar terrain model per request (`getF10KDescarga.do`; recorded 2026-11-15): `expected.json` is `{sheet: items}` of the answers cached per sheet (`InegiIndex.answer`), read back by `tests/test_mexico.py` | sheets G14C15B2 (El Potrero Chico) and G14C15B1 | INEGI, [Términos de Libre Uso de la Información del INEGI](https://www.inegi.org.mx/inegi/terminos.html): free use, "Fuente: INEGI" |
| `wfs/tuscany-lidar/` | Regione Toscana's cartoteca, its WFS feature type of the lidar sheets (`rt_cartoteca.lidar2k`, not in the capabilities; GetFeature as GML 3.1.1 with the footprints in EPSG:3003, 26 features of which 26 surveys kept; recorded 2026-11-15) | 43° N, 12° E (Cortona and the Umbrian border: surveys of Regione Toscana and of the Ministry of the Environment, 1 m and 2 m) | Regione Toscana, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (the index of the cartoteca's download layer; the sheets' data are not in the answer) |

`bucket1m/usgs-1m/` (recipe `bucket1m-usgs`, recorded 2026-11-22): USGS's bucket `prd-tnm` listed as
`sources/layers/tnmbucket.py` lists it (ListObjectsV2: the 1 m projects, then the `TIFF/` folders of
`ME_Umbagog_2016` and `UT_StrawberryRiver_2019`) and The National Map Access API's 1 m products over two boxes
around them: `expected.json` is the list of the files the index does not list that `make_unlisted` made of them
(no 0.25° tile, no header read), read back by `tests/test_usa_unlisted.py`. USGS, public domain. The recipe's
own code (`record_answers._bucket1m`, one request at a time) has no test of its own: it was checked by recording
the case (2026-11-22, 5 answers, 70 kB, 4 items) and by `test_recorded_bucket_and_index` replaying it, the same
requests in the same order and the same items (fix round 2 of the USA's wave A).

Files of a case: `answers.json` (the recipe, the date, the tile, the recorded hosts and every request in
order: method, URL, status, content type, body file), the bodies (`001.xml`, `002.json.gz`...: gzipped above
64 kB) and `expected.json`; an error case (`raises` in `answers.json`: the exception the code raised) has no
`expected.json`, its test checks that nothing is cached, also when the same report comes with HTTP 200.
Record again with `uv run tools/record_answers.py [recipe]`; a new recording changes `expected.json` only
when the service's data changed.

`nominatim/reverse.json`: Nominatim's reverse answers (`osm.reverse`, zoom 3 and 8) of seven points in Wales,
England, Lower Saxony, Saxony-Anhalt, South Tyrol and Trentino (mountains, forest, a coast, the sea off a cliff),
recorded once on 2026-11-01 for the offline tests of the regions of `--source auto` (`tests/test_regions.py`):
each row the query, the time and the answer as `osm.reverse` stored it. Data © OpenStreetMap contributors,
[ODbL 1.0](https://osm.org/copyright).

`lerc/`: tiles of two Esri elevation tile caches as they answered on 2026-11-15 (`<level>_<row>_<col>.lerc`, the
bodies of `<service>/tile/<level>/<row>/<col>`, LERC1 blobs of 257 x 257 samples), for `tests/test_lerc_tiles.py`:
`northern-ireland/` four tiles of level 17 of DAERA's `Full_NI_Elevation` (Fair Head, its east and south neighbours,
and a tile of the sea without a valid sample, 70 bytes; DAERA, Bluesky, [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)),
`rio-de-janeiro/` four tiles of level 15 of IPP's 5 m DTM (Pão de Açúcar, its east and south neighbours, and a tile
off Barra da Tijuca with the sea's artefacts down to -348 m; Instituto Pereira Passos (PCRJ),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). `expected.json`: what each decoded to then (valid samples,
valid zeros, minimum, maximum, a few samples).

`zipsheets/osni-dtm10/`: OSNI's Open Data 10 m DTM of Northern Ireland as OpenDataNI served it on 2026-11-15, for
`tests/test_zipsheets.py`: `directories.json`, the central directories of the six sheet archives (each member's name,
method, flags, CRC-32, compressed and uncompressed sizes and local header's offset, as
`sources/indexes/zipdir.py` read them by Range), and `Sheet011av2.txt.gz`, one member read whole (a beach west of
sheet 11: "x y z" lines of 10 m cell centres). Land & Property Services (OSNI),
[OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

`bremen/directories.json.gz`: the central directories of Landesamt GeoInformation Bremen's four XYZ archives (the DGM1
and DOM1 of Bremen 2017 and of Bremerhaven 2015) as `sources/indexes/zipdir.py` read them by Range on 2026-11-15: each
archive's length and ETag, each member's name, method, flags, CRC-32, compressed and uncompressed sizes and local
header's offset, for `tests/test_bremen.py` (the member names against the layers' expressions). Landesamt
GeoInformation Bremen, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`tokyo/`: the Tokyo Digital Twin's 0.5 m grid sheets as Tokyo's bucket served them on 2026-11-15, for
`tests/test_japan.py`: `09RD8410.zip` as published (an island sheet off Mikurajima: EPSG:6677, nodata 1.70141e38,
7 668 pixels of seabed at -12.2 to -6.5 m), `09LD1649.zip` a ward sheet (Shinjuku) with its TIFF header as published
(a CRS without an EPSG code, AREA_OR_POINT=Point, nodata -32767) and its pixels replaced in place by 8 x 8 blocks of
its heights and a 16 x 16 corner of -32767 (so the ZIP is small), and `toushobu/12/3636/1637.pbf`, the islands'
index vector tile over Mikurajima (fields MESH_NO, URL). Tokyo Metropolitan Government, 東京都デジタルツイン 島しょ地域点群データ /
区部点群データ, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja) (modified: the ward sheet).

`shizuoka/`: the heads of two of VIRTUAL SHIZUOKA's LP grid sheets as its bucket served them on 2026-11-16 (through
`net._get`), for `tests/test_japan.py`: `08MC4919_2025.zip` the first 300 lines of FY2025's `08mc4919_0.5g.txt`
("n,x,y,z,flag", decimetres) and `08OF0485_2019.zip` the first 300 of FY2019's `08OF0485_DEM.txt` ("x y z"), the lines
untouched, each re-zipped alone. VIRTUAL SHIZUOKA point cloud data (Shizuoka Prefecture),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (modified: cut).

`yamanashi/`: three of Yamanashi Prefecture's 0.5 m ground-model sheets (folder `03`) as the bucket
`japan-pointcloud` served them on 2026-11-26, unchanged, for `tests/test_japan.py`: `08KD1638.zip` a border sheet
(158 x 222 px of its 800 x 600, 22 877 valid), `08LD4359.zip` a sliver (1 x 3 px), `08LE9188.zip` mid Lake Motosu
(800 x 600 px, none valid). Yamanashi Prefecture, 山梨県点群データ（航空LP・MMS）,
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`kanagawa/`: two of Kanagawa Prefecture's 0.5 m MESH grid sheets as the bucket `kanagawa-pointcloud` served them on
2026-11-27, unchanged, for `tests/test_japan.py`: `09MC9132.zip` (folder 2024/01) mid Lake Ashi (-9999 but 330
cells at 725.0-725.3 m) and `09MD5023.zip` (2021/01) a sheet without a valid cell (-1111 but 12 cells of -9999); each
a `.lem` member and its cp932 `.csv` header. Kanagawa Prefecture, 神奈川県 3次元点群データ, データ提供：（神奈川県環境農政局緑政部
森林再生課）, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`miyagi/`: Miyagi Prefecture's 1 m grid as served on 2026-11-27, for `tests/test_japan.py`: two of its sheets from
the bucket `gic-miyagi`, unchanged, `10QE3444.zip` (183 rows of a sheet's 750 000, all flag 1) and `10QE1532.zip`
(578 rows on the coast, 7 of them flagged -9999 with heights of -0.4 to 0.2 m); `grid_list_rows.csv`, the header
and six rows of the portal's grid list (resource 1523, `040002_point_cloud_url_1mcsv.csv`, UTF-8 with a BOM),
10PE0822's two rows among them, the rows untouched. Miyagi Prefecture, 【宮城県】3次元点群データ_データ一覧_グリッドデータ_CSV_2023
(https://miyagi.dataeye.jp/resources/1523), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

`hong_kong/`: CEDD's 2020 lidar sheets as the CSDI Portal served them on 2026-11-16, for `tests/test_hong_kong.py`:
`sheets.json`, rows of the index (the FeatureServer's layers DTM_2020 and DSM_2020 as `tools/hong_kong_sheets.py`
keeps them: code, file name, URL, footprint in EPSG:2326), 23 terrain and 4 surface sheets spread over the 17 maps;
`2NE20D_dtm.head.bin` and `2NE20D_dtm.tail.bin`, the TIFF of the terrain sheet on the Shenzhen River without its
pixels: the 1 214 bytes before its first tile and the 3 048 after its last (the IFD and the GeoTIFF keys), as
published (EPSG:2326, 0.5 m, nodata -9999, 120 tiles of 128 x 128 float32, uncompressed, in order); the tests put
their own pixels between them, so no height of CEDD's is kept here (the CSDI terms name reproducing, not modifying).
LiDAR Data (2020), Civil Engineering and Development Department, © the Government of the Hong Kong Special
Administrative Region, from the Common Spatial Data Infrastructure (CSDI) Portal under its
[terms and conditions](https://portal.csdi.gov.hk/csdi-webpage/doc/TNC).
`nominatim/reverse-hong-kong.json`: Nominatim's reverse answers (zoom 3 and 8) of Lion Rock, Chek Lap Kok and Tung Lung
Chau, recorded on 2026-11-16 (`osm.reverse`): "cn" at zoom 3, ISO3166-2-lvl3 CN-HK at zoom 8. Data © OpenStreetMap
contributors, [ODbL 1.0](https://osm.org/copyright).

`forest/`: the Forestry Agency's DEM of Kitaise (Mie) as served on 2026-11-27, for `tests/test_japan_forest.py`:
`dem_06ne4_2025_pieces.zip`, pieces of `dem_06ne4_2025.tif` (380 489 100 bytes) byte for byte, each a member named
by its first byte: the first 65 536 bytes (the header: every tile's offset and byte count, no heights) and the nine
tiles under the 500 m block x 33 500-34 000, y -118 000..-117 500 of zone VI (seven empty, two of 13 569 and 4 588
bytes with 4 832 and 1 032 valid pixels, outside that block), and `size`; `dem_06ne4_2025_empty_tiles.zip`, two
more tiles of that file the tool decodes for its classes, both empty (nodata only): the full tile 0, 0 (1 626 bytes
at 56 509) and the last row's first (1 390 bytes at 372 989 429); `kitaise_081_rows.json`, five of the record's
resources in its package_show answer (title, ids, sizes, addresses). 出典：国土交通省土地・建設産業局地籍整備課、東海農政局木曽川
水系土地改良調査管理事務所、三重県森林・林業経営課、津市農林水産部林業振興室、菰野町産業観光課・三重県（北伊勢森林計画区）DEM（林野庁加工）
（https://www.geospatial.jp/ckan/dataset/kitaise_081）、PDL1.0（https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）.
