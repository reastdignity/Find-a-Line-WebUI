# Recorded answers of the Metalink indexes

Real Metalink 4 documents (RFC 5854) of the two download services the listing of
`sources/indexes/metalink.py` reads, recorded on 2026-11-02 for the offline tests of `tests/test_bavaria_rp.py`:
`tests/http_server.py` serves them again at a path of its own (the test names it). The statewide documents the
sources read (`09.meta4` of Bavaria's DGM1: 22 MB; the seven Regierungsbezirke of its DOM20; `dgm1_tif_07.meta4`
and `dom1_tif_07.meta4` of Rhineland-Palatinate: 12 and 7.6 MB) are too large to keep: the documents of one
Gemeinde have the same form. The list is `requests.json`, not `answers.json`, so `tests/test_parts.py` does not
take it for the cassette of an index. Each was asked once with `curl --compressed` and our User-Agent.

| File | Request | What it holds |
| --- | --- | --- |
| `001-bavaria-dgm1.meta4` | `https://geodaten.bayern.de/odd/a/dgm/dgm1/meta/metalink/09472190.meta4` | LDBV's DGM1 1 m of one Gemeinde in the Landkreis Bayreuth (82 files of 1 km, `<Ekm>_<Nkm>.tif`, two mirror URLs each, sha-256 and size, no dates) |
| `002-bavaria-dom20.meta4` | `https://geodaten.bayern.de/odd/a/dom20/meta/DOM/metalink/09472190.meta4` | LDBV's DOM20 0.2 m of the same Gemeinde (82 files `32<E>_<N>_20_DOM.tif`) |
| `003-rlp-dgm1.meta4` | `https://geobasis-rlp.de/data/dgm1/current/meta4/dgm1_tif_07340009.meta4` | LVermGeo RP's DGM1 1 m of the Gemeinde Dahn (20 `.tif` and 20 `.tfw`, the survey year in the names, one URL each, a `published` date that is not RFC 3339) |
| `004-rlp-dom1.meta4` | `https://geobasis-rlp.de/data/dom1/current/meta4/dom1_tif_07340009.meta4` | LVermGeo RP's DOM1 1 m of Dahn (20 `.tif`) |
| `005-bavaria-404.html` | `https://geodaten.bayern.de/odd/a/dom20/meta/DOM/metalink/09.meta4` | HTTP 404 (no statewide DOM20 document), Apache's page |
| `006-rlp-404.html` | `https://geobasis-rlp.de/data/dgm1/current/meta4/dgm1_tif_070340009.meta4` | HTTP 404, the GeoBasis-RLP page |

Licences: Bayerische Vermessungsverwaltung – www.geodaten.bayern.de, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
(001, 002, 005); ©GeoBasis-DE / LVermGeoRP 2026, [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0),
www.lvermgeo.rlp.de (003, 004, 006).
