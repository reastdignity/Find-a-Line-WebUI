# Recorded answers of Brandenburg's WCS and Schleswig-Holstein's download server

Real answers recorded on 2026-11-02 (curl with our User-Agent) for the offline tests of `tests/test_bb_sh.py`:
`tests/http_server.py` serves them again at paths of its own (the test names them). No `answers.json`, so
`tests/test_parts.py` does not take the folder for the cassette of an index.

| File | Request | What it holds |
| --- | --- | --- |
| `001-sh-dgm1.geojson` | `https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/single.php?file=DGM1_SH__Massendownload.geojson&id=4` (`application/txt`, 9 MB) | LVermGeo SH's index of the DGM1, **trimmed** to the 27 features of Helgoland (424-428 / 6002-6006 km, 2005 and 2025) and two inland tiles; the features as they came, the document's header kept, one feature per line |
| `002-sh-stale.html` | `.../massen.php?file=dgm1_32_426_6005_1_sh_2024.xyz&id=2&live=2024&km=32420_6000` (a year the index does not give) | HTTP 200, `text/html; charset=UTF-8`: "Die verwendete Massendownload-Datei ist veraltet" |
| `003-bb-dgm1-describe.xml` | `https://inspire.brandenburg.de/services/el_dgm1_wcs?SERVICE=WCS&VERSION=2.0.1&REQUEST=DescribeCoverage&COVERAGEID=el_elevationgridcoverage` | LGB's DescribeCoverage: the extent 248000.00001 5689999.99999997 - 466000.00001003 5936000 |
| `004-bb-beyond.html` | its GetCoverage of `x(466000,468000)`, `y(5800000,5802000)` | HTTP 400, `text/html`: LGB's error page for a box beyond the extent |

Licences: © GeoBasis-DE/LGB, [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0); ©GeoBasis-DE/LVermGeo SH/[CC BY
4.0](https://creativecommons.org/licenses/by/4.0/) (Quelle verändert: trimmed).
