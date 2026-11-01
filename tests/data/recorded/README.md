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
| `tnm/dem1m/` | The National Map Access API, products of the 1 m DEM | 48.75° N, 95.25° W (Lake of the Woods, the Canadian border) | USGS, public domain |
| `tnm/ifsar5m/` | The National Map Access API, products of Alaska's IfSAR DTM | 59.75° N, 141° W (the Gulf of Alaska) | USGS, public domain |

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
