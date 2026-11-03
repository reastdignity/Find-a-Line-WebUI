# Recorded answers of the ZIP directories

The end of one of LVGL Saarland's district archives as `sources/indexes/zipdir.py` reads it (`read_directory`: one
Range of the archive's last 64 KiB + 22 B, which holds this archive's end of central directory record and its whole
central directory), recorded on 2026-11-03 for the offline test `tests/test_saarland.py::test_recorded_directory`:
the test serves the bytes again at their offsets of the real archive (559 134 521 B), nothing else. The bytes of the
range before the central directory (the end of the last member's compressed data, not part of the ZIP's structure)
are zeroed, so the file stays small. Asked through the app's code (`zipdir.share_token`, `head`, `ranged`) with its
User-Agent; the list is `requests.json` (the share's token replaced by `<token>`), not `answers.json`, so
`tests/test_parts.py` does not take it for the cassette of an index.

| File | Request | What it holds |
| --- | --- | --- |
| `001-tail.bin.gz` | `Range: bytes=559068964-559134520` of `.../OD_DGM1_2025_tif_LK/DGM1_tif_NK_EPSG-25832_Entstehung-2025.zip` | The central directory (34 802 B, 311 entries: the folder `DGM1_tif_NK/` and 310 tiles `dgm1_32_<E>_<N>_1_SL_2025.tif`, deflated, with data descriptors: flag 8) and the end record, no ZIP64 |

Licence: © GeoBasis DE/LVGL-SL 2026, [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0) (the names, sizes and
checksums of the DGM1 2025's files).
