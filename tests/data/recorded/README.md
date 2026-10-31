# Recorded answers of the index services

Real answers of the services our indexes ask, recorded once by `tools/record_answers.py` (2026-10-31) for
the offline tests of `tests/test_parts.py`: `tests/http_server.py` serves them again (the recorded hosts
replaced by its own address) and the code must write `expected.json` byte for byte, the index answer the
code that recorded them wrote. Each case asks for one 0.25° tile at the edge of the data, so the answers
stay small.

| Folder | Service | Tile (south-west corner) | Origin and licence |
| --- | --- | --- | --- |
| `wfs/geoportal-nmt/` | geoportal.gov.pl WFS sheet index of the NMT (GetCapabilities, GetFeature per year) | 54.75° N, 18.5° E (the Hel peninsula, the sea) | Główny Urząd Geodezji i Kartografii (GUGiK), [geoportal.gov.pl terms](https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/): free use, source stated |
| `stac/swisstopo-swissalti3d/` | swisstopo STAC API, items of swissALTI3D (two pages) | 47.75° N, 8.5° E (Schaffhausen, the German border) | © swisstopo, [OGD terms](https://www.swisstopo.admin.ch/en/conditions-geodata): free use, source stated |
| `tnm/dem1m/` | The National Map Access API, products of the 1 m DEM | 48.75° N, 95.25° W (Lake of the Woods, the Canadian border) | USGS, public domain |
| `tnm/ifsar5m/` | The National Map Access API, products of Alaska's IfSAR DTM | 59.75° N, 141° W (the Gulf of Alaska) | USGS, public domain |

Files of a case: `answers.json` (the recipe, the date, the tile, the recorded hosts and every request in
order: method, URL, status, content type, body file), the bodies (`001.xml`, `002.json.gz`...: gzipped above
64 kB) and `expected.json`. Record again with `uv run tools/record_answers.py [recipe]`; a new recording
changes `expected.json` only when the service's data changed.
