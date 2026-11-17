---
paths:
  - "tools/mirror_publish.py"
  - "sources/readers/tilebases.py"
  - "tests/test_mirror_pairs.py"
  - "tests/test_mirror_client.py"
  - "tests/test_mirror_publish.py"
---
# The project's data server: the publish tool and the client

The specification: docs/mirror-hosting/spec.md (B the publish tool, C the client). The server's side (`deploy/mirror/`)
is in `.claude/rules/deploy.md`, the VPS's checks of it (C7, C8) in `metrics.md`; cutting the datasets in
`providers.md` (`tools/sk_tiles.py`, `tools/mirror_tiles.py`). What the modules hold: docs/code-map/sources.md
(`tilebases.py`), docs/code-map/tools.md (`mirror_publish.py`).

## Must stay in sync

- `tools/mirror_publish.py` `PUBLISHABLE`: every row names a dataset the tools cut (`mirror_tiles.DATASETS` or
  Slovakia) with its product folders among `GridTiles(averaged=)`'s required ones, and a catalogue `source_id` (its
  credit is the row's attribution); each card states the changes. A cut dataset gets a row only with the user's
  approval and date, and until then is not published (the islets of batch 6 today; the pair test names them). A recut with other
  values is a new edition (a new folder name, U24). `BLOCK` 10 in `sk_tiles`, `mirror_tiles`, `mirror_publish` and
  `tilebases` (`tests/test_mirror_pairs.py`).
- The client (`tilebases.py`): `MIRROR_URL`'s host is the key of `net.HOST_SLOTS_OF`/`HOST_RATES_OF` (another address
  takes its manners through `net.LIMITS_AS`) and Telegraf's address; `off` (or empty) turns it off, also in conftest,
  `tests/regression.py` and the privacy sentence; a test never sets it empty (Windows deletes the variable: the real
  host): `off`. `reach` only where the specification's C.3 passes `reach=True`; it reads the data server's
  `datasets.json`, never a product's index (an estimate fetches the index: `index_for_estimate`); a later phase takes
  the job's stored source (`plan_search(source_id=)`).
- The client's reading of `datasets.json` (`tilebases._checked_list`: `datasets[].products[].path` against a
  product's mirror folder; an unlisted product is `NotPublished`, U50) and `mirror_publish.write_datasets`' format
  go together (`test_the_clients_reading_of_the_list_the_tool_writes`). `net._get(stop_on=)` is the start check's 429 rule; `_server_failed`'s text
  reaches the page through `error.download_failed`.
- An index's rules (null: no data; beyond a complete index's extent: no data; `partial`; `"block"` 10) are what
  `sk_tiles`/`mirror_tiles` write, what `mirror_publish verify` checks and what `tilebases` reads
  (`test_the_tools_indexes_pass_the_check`, `test_indexes_written_by_the_tools_pass_verify`). `REACH_TIMEOUT`
  (10 s, 20 s a read) rests on the server's 10 s header timeout and storage that never spins down (spec A's risks).
  The later phase's "Data: <name> (chosen when the search started)" keeps the form `tests/regression.py` `PATTERNS`
  and `tools/obstacle_study.py` read; `regression.py --mirror-url` runs the `needs_path` entries without the folder.
- `tests/http_server.py` `peak()` counts a request from its arrival to just before its answer's headers leave; the
  client's connection tests read the host's 2 connections from it (`test_two_connections_whatever_address`,
  `test_a_tile_falling_through_a_local_folder_takes_a_slot`): where a request ends changes them together.
