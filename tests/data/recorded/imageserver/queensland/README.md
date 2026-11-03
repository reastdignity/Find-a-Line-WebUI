# Recorded answers of Queensland's DEM time series ImageServer (exportImage)

Real answers of the State of Queensland's `Elevation/DEM_TimeSeries_AllUsers/ImageServer`
(`https://spatial-img.information.qld.gov.au/arcgis/rest/services/...`, ArcGIS Server 11.5), recorded once on
2026-11-02 by `record.py` (run by hand from the repository: `uv run python
tests/data/recorded/imageserver/queensland/record.py tests/data/recorded/imageserver/queensland`) for the offline
tests of the layers of `sources/catalogue/australia.py` (`tests/test_queensland.py`); `tests/http_server.py` serves
them again (matched by path and sorted query; named `exports.json`, not `answers.json`, so `tests/test_parts.py`
does not replay it as an index service's cassette). The requests are those of the layers' readers
(`export_params`): the lidar rule (`product_type = 8 AND res_value <= 1`, by ZOrder) or DEM-H's
(`product_type = 1`), `RSP_NearestNeighbor`, `noData=-9999`, `f=image`.

| Body | Request | What it shows |
| --- | --- | --- |
| `001-full.tif` | lidar, 16 x 16 px of 1 m on Mt Tibrogargan's east face, GDA94 / MGA 56 (`bboxSR=imageSR=28356`) | a TIFF in EPSG:28356 on exactly the pixels asked for (343-361 m) |
| `002-left.tif`, `003-right.tif` | its two halves (8 x 16 px) | equal to the whole box (the service's nearest neighbour is deterministic) |
| `004-isa.tif` | lidar, 16 x 16 px in Mount Isa, MGA 54 (`28354`) | the same service asked in another zone |
| `005-sea.tif` | lidar, 16 x 16 px east of Moreton Island | every pixel -9999 |
| `006-demh.tif` | DEM-H, 16 x 16 px of 30 m at Tibrogargan, MGA 56 | the 30 m gap filler |
| `007-bad-where.json` | a mosaic rule naming a field that does not exist | the error JSON (code 400), sent with HTTP 200 and `Content-Type: image/tiff` |

Origin and licence: data of the State of Queensland under CC BY-SA (the service's terms). Includes material ©
State of Queensland (Department of Natural Resources and Mines, Manufacturing, and Regional and Rural
Development); © Commonwealth of Australia (Geoscience Australia, The Australian Hydrographic Office); ©
www.deepreef.org 2026. In consideration of the State of Queensland permitting use of this data you acknowledge and
agree that the State gives no warranty in relation to the data (including accuracy, reliability, completeness,
currency or suitability) and accepts no liability (including without limitation, liability in negligence) for any
loss, damage or costs (including consequential damage) relating to any use of the data.
