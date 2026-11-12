---
paths:
  - "viewer/src/coverage/**"
  - "tools/coverage_*.py"
  - "locales/coverage/**"
  - "tests/test_coverage*.py"
---
# The coverage map (/coverage)

What each part holds: docs/code-map/viewer.md (`coverage/`) and docs/code-map/tools.md (`tools/coverage_*.py`).

## Must stay in sync

- The coverage map and the catalogue: a source that colours the map has a `coverage`, a gap filler none, one source
  per area; `viewer/src/coverage/coverage.json` is generated from them (`tools/coverage_data.py`, `--check` in
  `tests/test_coverage.py`), its schema is `viewer/src/coverage/types.ts` (with the outlines' and contrast.json's:
  change the tools and the types together). A new area needs its outline and a row in `tools/area_rows.py`
  (`OSM_NAMES`, a new country's title in `COUNTRIES`: `tests/test_area_rows.py::test_every_area_of_the_map_is_a_row`)
  (`tools/coverage_shapes.py`; `shapes.json` is LF everywhere (`.gitattributes`) and copied byte for byte to
  `dist/coverage-shapes.json`), a new region area `region.<id>`, a new note or survey code
  `note.<code>`/`survey.<code>`, in both `locales/coverage/en.json` and `pl.json` (the same keys; Polish plurals
  `_one`/`_few`/`_many`/`_other`). Code under `viewer/src/coverage/` uses `ct` of `coverage/i18n.ts`, never a function
  named `t` (`test_viewer_keys_in_catalogue` reads every `t("...")` against the app's catalogue). Counts in texts come
  from the data (`count.countries`, `media.verify.note`), never written in. After a change of a source's coverage or
  of the drawing, `tools/coverage_media.py readme` renders docs/images/coverage-* again (`STORIES`, `LENGTHS`,
  `FORMATS` and `GROUPS` of the tool repeat `FAL_MEDIA`'s lists: it stops when they differ); a change of the 30 m
  comparison is `tools/coverage_contrast.py` and the roadmap's table of priority 2.
