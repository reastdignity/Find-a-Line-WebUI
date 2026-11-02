# Recorded answers of an ArcGIS ImageServer (exportImage)

Real answers of ČÚZK's ImageServers `dmr5g` and `dmp1g` (`https://ags.cuzk.gov.cz/arcgis2/rest/services/...`,
ArcGIS Server 12), recorded once on 2026-11-02 by `record.py` (run by hand: `python record.py <folder>`) for the
offline tests of `sources/readers/imageserver.py` (`tests/test_imageserver.py`); `tests/http_server.py` serves
them again (`add_cassette`: the requests matched by path and sorted query, so the reader must write every
parameter as recorded).

| Body | Request | What it shows |
| --- | --- | --- |
| `001-dmr5g-json.json` | the service's description (`?f=json`) | extent, 2 m pixels, `maxImageWidth` 15000 / `maxImageHeight` 4100, WKID 102067 (= EPSG:5514) |
| `002-full.tif` | DMR 5G, 16 x 16 px of 2 m at Adršpach on its grid (edges at 0.4 / 1.88 m modulo 2) | a TIFF in `LOCAL_CS["S-JTSK / Krovak East North"]`, nodata -9999, LZW |
| `003-left.tif`, `004-right.tif` | its two halves (8 x 16 px) | equal to the whole box |
| `005-shift.tif` | the box one pixel east | the same values one pixel further |
| `006-dmp.tif` | DMP 1G, 16 x 16 px on its own grid (1.69 / 1.98 m modulo 2) | the surface model |
| `007-poland.tif` | a box in Poland, inside the service's extent | every pixel -9999 |
| `008-beyond.tif` | a box west of the service's extent (Bavaria) | every pixel -9999 |
| `009-too-high.json` | 16 x 4101 px (above `maxImageHeight`) | the error JSON, sent with HTTP 200 and `Content-Type: image/tiff` |

Every request: `bboxSR=imageSR=5514`, `format=tiff`, `pixelType=F32`, `noData=-9999`,
`interpolation=RSP_NearestNeighbor`, `compression=LZ77`, `f=image`.

Origin and licence: © ČÚZK, data under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ("Podmínky
poskytování prostorových dat ČÚZK"; credit "ČÚZK, 2026").
