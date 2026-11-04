# How Find-a-Line works, in diagrams

Diagrams of the program from the whole to the detail. Each file is a level or a part; each starts
with a plain-words diagram or paragraph for a reader who has never seen the code, then the
technical diagrams, then a table of where each box is in the code. The diagrams are Mermaid blocks,
which GitHub renders; `tests/test_architecture_docs.py` checks every name of the tables against the
code, so a diagram that names a function that no longer exists fails the tests.

## From the whole to the detail

| Level | File | What it shows |
| --- | --- | --- |
| 0 | [context.md](context.md) | who uses the program, the outside services it asks, what it keeps on disk |
| 1 | [processes.md](processes.md) | the commands of `findaline.py`, the processes of the web app, the worker and the country layer, the stores they share |
| 2 | [search.md](search.md) | one search from the request to the saved map: plan, estimate, download, the five steps, a large area in tiles |
| 2 | [search-vs-country.md](search-vs-country.md) | where the country layer forks off a search, and a country run |
| 2 | [web-jobs.md](web-jobs.md) | a web job's states, the hand-overs between the browser, the web process and the worker, the quick lane |
| 2 | [decisions.md](decisions.md) | the decision trees: which source, one grid or tiles, where the sea is, what is filled from where, the thresholds |
| 3 | step1.md, step3.md, step5.md | the inside of step 1 (the filling), step 3 (the kernels) and step 5 (the saving): to come |

## The parts beside the search

| File | What it shows |
| --- | --- |
| [download.md](download.md) | how the data is downloaded: the download phase, the life of one tile, the readers and indexes, the limits of the providers, OpenStreetMap, the orthophoto, the cache's updates |
| [sources.md](sources.md) | the data sources: how one is chosen, what a source declares, how a layer is composed, the gap filling, the world family |
| [view3d.md](view3d.md) | the 3D view of a line: the patch, the page's modules, the views, the orthophoto composition |
| [coverage.md](coverage.md) | the coverage map: from the catalogue to the page's files, the page, the contrast study, the media |
| [monitoring.md](monitoring.md) | the public site on the VPS and its monitoring: nginx, the containers, Telegraf, VictoriaMetrics, Grafana, the application's metrics |
| [tools.md](tools.md) | the tools of `tools/`: what measures, generates and checks what |

## How to read a diagram

| Shape and colour | Meaning |
| --- | --- |
| blue box | a step, a function, a process |
| amber diamond | a decision; the edges out of it are its answers |
| green box or cylinder | a file or a store that is written |
| grey box | a person or an outside service |
| a dashed edge | the branch taken less often, or a loop back |
| a number in a box | a constant that decides a branch, with its name in the code |

The names in the boxes are the names in the code (`plan_search`, `jobs.sqlite`, `Step 1/5`), so a
search of the repository for a box's name finds its implementation. The documents behind the
diagrams: [README](../../README.md) (the options and the algorithm), [roadmap.md](../roadmap.md)
(the decisions), [performance.md](../performance.md), [monitoring.md](../monitoring.md),
[country-precompute/contract.md](../country-precompute/contract.md) and
[3d-view-contract.md](../3d-view-contract.md).

The prototypes the form was chosen from are in [prototypes/](prototypes/).
