# Recorded answers of IGN's WMS-R

Real GetMap answers of the Géoplateforme's WMS-R (`https://data.geopf.fr/wms-r/wms`, OGC WMS 1.3.0, raw heights as
float32 GeoTIFF), recorded on 2026-11-02 for the offline tests of `sources/readers/wmsr.py` and
`sources/layers/wmsr.py` (`tests/test_wmsr.py`): `tests/http_server.py` serves them again (the test's fixture
`service` adds each answer at its path and query, whatever its host), matched by the exact query, so the reader
must write the same parameters (the BBOX's numbers too). The lists are `requests.json`, not `answers.json`, so
`tests/test_parts.py` does not take them for the cassettes of an index. Each request was made once, one at a time,
with the parameters the reader writes (a request the server answered with a transient error was asked again, see
`errors/003.xml`).

| Folder | Requests | Place |
| --- | --- | --- |
| `verdon/` | LiDAR HD MNT: a 32 m box at 0.5 m on the data's pixel edges (`001`), its left and right halves (`002`, `003`), the box one pixel (0.5 m) further east (`004`), the box at 1 m (`005`), the MNS of the box (`006`), the box without `FORMAT_OPTIONS=compression:deflate` (`007`, uncompressed) | The Verdon, above the Escalès cliffs (43.7655° N, 6.358° E; Lambert-93 970339.75-970371.75 E, 6302000.25-6302032.25 N) |
| `rgealti/` | RGE ALTI 1 m (`RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS`), the same place on whole metres | The Verdon |
| `sea/` | LiDAR HD MNT, 32 m at 0.5 m: HTTP 200, every pixel -9999 | The Channel off Étretat (494390.75 E, 6961600.25 N) |
| `errors/` | `001`: 5011 px wide (more than MaxWidth 5010: HTTP 400, `InvalidParameterValue`); `002`: an unknown layer (HTTP 400, `LayerNotDefined`); `003.xml` (a body only, not in `requests.json`): the server's `LayerNotDefined` (HTTP 400) to the MNS request of `verdon/006`, an answer IGN's servers give now and then for a layer they have (twice in eleven requests while recording, none in 240 afterwards; once a 502 of nginx too) | The Verdon |

Files of a case: `requests.json` (the date, the recorded host and every request in order: method, URL, status,
content type, body file) and the bodies (`001.tif`, `002.xml`...). Recorded with a script of the session that
added the reader (not kept in the repository): `requests.get` of each URL with the parameters as in
`requests.json`, 0.5 s apart.

Licence: IGN's LiDAR HD and RGE ALTI, [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/)
(Etalab): source IGN, data of the Géoplateforme as served on 2026-11-02.
