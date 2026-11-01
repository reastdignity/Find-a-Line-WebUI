# Research notes of the 3D view (2026-11-01)

The evidence behind [../3d-view.md](../3d-view.md): one line per claim with a short quote, its URL, the access date
and VERIFIED (read on the page) or UNVERIFIED (secondary, inference). The deciding quotes were re-checked against
the saved pages by the coordinator; the pages themselves, the downloaded packages and the browser profiles were not
kept (third-party content).

| File | What |
| --- | --- |
| [brief.md](brief.md) | The brief of the research wave: requirements, stack facts, the parts |
| [step0.md](step0.md) | The knock-out table: which services fail a gate, with the deciding quotes |
| [r1.md](r1.md) | Google: Map Tiles API in the EEA, 3D Maps (`Map3DElement`), terms, keys, hard stop, Google Earth and KML |
| [r2.md](r2.md) | Esri for 3D, the other services, open terrain (Mapterhorn, AWS, swisstopo), the CORS probe, the vertical datum of every source |
| [r3.md](r3.md) | Rendering libraries (bundled and run in headless Edge), CSP, sizes, data per open, phones, geoid and frames |
| [r4.md](r4.md) | Law: GDPR roles, the Munich Google Fonts judgment, Prawo komunikacji elektronicznej art. 399, terms to pass on, data licences, donations, licence notices |
| `scripts/r2/` | Small helpers of R2 (attribution lookup, CORS request URLs, `proj.db` queries) |
| `scripts/r3/` | R3's measurements: `bundle.mjs` (each library bundled like `viewer/build.mjs`), `edge_run.py` with `site/` (test scenes under a given CSP in headless Edge), `dem_sizes.py`, `rtin_count.py`, `geoid_diff.py`, `geoid_use.py`, `frame_shift.py`, `proj_grids.py`, `osv.mjs`, `cadence.mjs`; `entries/` what a 3D view would import |
| `results/` | Their outputs: bundle sizes, DEM patch sizes, mesh sizes, geoid differences, frame shifts, PROJ grids, advisories, the CORS table |

To run the scripts again: the test site expects the bundles (`three-own.js`, `cesium-widget.js` from
`scripts/r3/bundle.mjs`), a 1025 px terrain-RGB tile in `site/dem/` and orthophoto tiles in `site/tiles/`, which
were made from the local cache and are not kept here; heavy commands go under `tools/test_lock.py run`.
