# Regression entries that fail: why, how to tell, what to do

What the audit of November 2026 found about the entries of `tests/regression.py` that kept failing, what was
decided and built on it, and how a red entry is read since. How to run the set and the rules for sessions are in
[regression-tests.md](regression-tests.md) ("How to run", "Which cache, and what to report", "When a number
differs"); failures that are known and left are in [known-bugs.md](known-bugs.md). This file is the story and the
reasons behind both.

## The short answer

- A regression entry compares a real search with stored counts and the sha256 of its CSV export. It fails for six
  kinds of reason, and only one of them is the code (the table below).
- In November 2026 five entries were red or unchecked in merge after merge (R17, R48, R56, R70, R87). None was a
  code regression: three differed only on caches other than the real one, one compared a dated file with a live
  service, one could not reach its provider.
- Two thirds of all regression runs named a cache other than the real one. Most failures, and nearly all the load
  on the data providers, came from those runs.
- Since 2026-11-24 the harness tells the reasons apart itself: three outcomes, a refusal of any cache but the real
  one, and a record of the data each baseline rests on.

## Why an entry fails

| Reason | How it showed before | How it shows now | What to do |
| --- | --- | --- | --- |
| The code changed a result | `DIFFERENT` | `DIFFERENT`, and under it `same data, other result` | A regression, or an intended change: look at lines on the map, then `--update --write-doc` in the same commit |
| The data changed (a provider replaced a survey, a `cache update`, OSM was edited) | `DIFFERENT`, read as a code fault (R48, a week) | `DIFFERENT`, and under it `data differs: <folder> N of M files, K new ...`, `coastline (...)` or `the search area's inputs (...)` | Compare old and new lines, re-baseline in the same step (`--update`); after `cache migrate`: `--update-data` |
| Another coastline source (a cache without the OSM world water polygons asks Overpass, then falls back to the Copernicus mask) | `DIFFERENT` (R56, R87, ten more) | Never on the real cache; on a scratch cache without the world file `unverified (coastline: ...)` | Run on the real cache; a scratch cache is seeded with the world file by `--cold` |
| A provider or an OSM service did not answer, or blocks | A failed search, or a wait of 15 minutes | `unverified (a data provider did not answer: ...)` within half a minute | Try again later, at most once a day; a block is a matter for the provider (R70) |
| The wrong cache (a worktree's own empty `cache/`, a scratch folder) | Everything downloaded again, other coastlines, other surveys | Refused without `--cold` | `--cache <main checkout>/cache` to verify; `--cold --cache <scratch>` to test a download |
| The environment (a key or the local mirror folder missing; another GDAL; too little memory for the access mark) | `skipped`, or a difference nobody could place | `skipped (reason)`; under a difference `; GDAL a -> b` or `the access mark left out` | Set what is missing; a library's change is re-baselined on purpose |

Apart from these, a red line in a session's report may be no regression entry at all: a browser or timing test of
pytest that fails now and then (known-bugs.md names them).

## Reading a run

- **Outcomes and exit codes**: `ok`; `DIFFERENT` (exit 1); `unverified` (exit 3: nothing different, but something
  could not be checked; it is no pass); `skipped (reason)`. An entry run by name only (R17, R70) is left out of
  `--all`.
- **The line under an entry that differs**: `same data, other result` points at the code; `data differs: ...`
  names what changed in the data; `same data where known (N files not known), other result` when some files have
  no checksum to compare; `data not known` when nothing could be compared. A library's version, the access mark
  and a resumed search's mixed sessions follow after `; `.
- **The run log**: one JSON line per run in `regression-runs.jsonl` beside the test lock's queue: each entry's
  outcome, reason, coastline, seconds, the requests and bytes per host, the tiles downloaded and found cached, and
  whether its data were the baseline's. "Which entry failed, how often and why" and "what did the runs ask of
  which provider" are queries on it.
- **`findaline.py cache status`** ends with the runs computed on data that has changed since, per file changed,
  re-encoded or not known; a run made before the record is counted by fetch times and marked approximate. The
  command only reads, so it may run at any time, also while searches run.
- **`tools/record_check.py`** runs an entry offline on a cache built only from its stored record: the check that
  the record names everything (regression-tests.md, "The completeness check").

## What the audit found (2026-11-01 to 2026-11-23)

Sources: the test lock's history of every run, the sessions' logs, 45 kept log folders, the real cache's index.

- **500 regression runs in 23 days**, on 18 of them; 182 ended with an exit code other than 0.

| Cache the run named | Runs | Failed |
| --- | --- | --- |
| The real cache | 169 | 29 (17 %) |
| A worktree's own `cache/` (no `--cache` given) | 136 | 94 (69 %) |
| Another `--cache` folder | 195 | 59 (30 %) |

- **On the real cache only two entries failed**, R17 and R70. In its last full run before the audit 91 of 93 were
  `ok`, R48, R56 and R87 among them.

| Entry | Cause |
| --- | --- |
| R17 (the Malta extract against Overpass) | A dated file compared with a live service: Overpass answered 502 or 504 to most tries (55 skips of 68 runs seen); its earlier differences were OSM edits made after the extract. Out of `--all` since 2026-11-24, run by name |
| R70 (Sint Eustatius) | basisdata.nl blocks a development network since 2026-11-15, after about 18 parallel window reads per island at 4 connections during the source's development; the real cache held none of its data |
| R48 (Dahn) | The Land replaced its survey of 2022 with one of 2026 between 2026-11-08 and 2026-11-16: the real cache held the old tiles, every fresh cache got the new ones (1 252 lines against 1 541, on the same rocks). Re-baselined |
| R56 (Helgoland), R87 (Deserta Grande) | The Copernicus coastline fallback on caches without the world file, when Overpass did not answer. Ten more coastal entries were seen flipping the same way |

- Two baselines had been stored on the fallback by mistake before (R85, R86). `--update` now refuses to store an
  unverified entry, a fallback coastline, or Overpass's text where the folder holds the world file.

## The load on data services

How many of the runs downloaded their data again is known only as a range for that time (no request was counted
then): between 607 and 1 218 entry runs, 6 to 12 full sets, tens of GB.

| Service | Its rule | What the regression runs sent in 23 days (estimated) | Within it? |
| --- | --- | --- | --- |
| Overpass (overpass-api.de) | Regular use under 100 queries a day, no parallel scripts, a pause after 429 | 300 to 1 000 queries; possibly over 100 on two days | Not reliably: the cap of 75 a day and the one-at-a-time lock are kept per cache folder, and about 100 folders were named |
| Nominatim | At most 1 request a second; results cached; an identifying User-Agent | 1 800 to 4 900 lookups of about 300 distinct questions | The rate within one folder yes; the caching rule no: each fresh cache asked the same questions again |
| Providers with a published rate (swisstopo, the Environment Agency, Géoplateforme, DAERA's tiles, our own data server) | 40 a minute to 40 a second | Any number of runs | Yes: one limiter for the whole PC, 10 % under each figure |
| OpenTopography | 50 calls a day per key | Fresh in at most 11 folders | Yes |
| About 50 other hosts | No figure on record | Tens of GB (a full set is at least 3.5 GB) | No known limit broken; it could not be checked |
| basisdata.nl | None published | Not the regression runs: the source's development | No: it blocked a development network. The provider drew the limit itself |

What changed for the load:
- **A warm run on the real cache sends no request** (measured: the run log's `hosts` is empty for a whole set).
- **A scratch cache is seeded** from the real one by `--cold` (the world water polygons, the OSM theme tiles,
  FABDEM, Copernicus and its water mask, the geoid by hard link; Nominatim's answers by copy), so a download test
  fetches its own source only and asks neither Overpass nor Nominatim.
- **Any cache but the real one needs `--cold`**: no accidental cold run.
- **basisdata.nl** is read at one connection and 54 requests a minute, through our own ranges; its operator is
  to be asked to free the address and to name the limits it wants (a mail of the project's owner).
- **A host that cannot be connected to fails in seconds** and a download stops asking it (it was 15 minutes).
- **Every regression run's requests and bytes per host are in the run log**: the next audit is a query.
- **A new source on a provider's own host starts slow** (one connection and a request rate until the provider's
  limits are known in numbers): development counts, not only searches.

Left open on purpose: Overpass's and Nominatim's limits are still kept per cache folder, not for the whole PC (the
user's decision of 2026-11-23: seeding first, then look at the run log's evidence).

## The data record

A regression entry that differed could not say whether the data or the code had changed. Since 2026-11-24 a search
records what it read (the key `identity` in run.json): each cached file's checksum from the cache index, the
coastline's world file edition or OSM tiles, the OSM tiles and Nominatim answers an area by coast, cliffs or name
was built from, local files' size and time, the versions of GDAL, PROJ and rasterio. The harness keeps each
entry's record in `tests/regression-data.json` and compares; `cache status` compares a saved run's record with the
cache as it is now. With the key removed a run.json is what it was; the public export never carries it.

A checksum in the record means "these bytes were read": each file of a layer is noted before the read and after
it (its stored checksum and its inode, time and size on disk), and a file whose two notes differ is recorded as
not known, never as one of the two contents. Not known reads as "same data where known", never as "differs".

Three options were weighed: the names of the files a run read (they would have named R48's cause, and miss a file
replaced under its name); names with the provider's own identity (ETag, date), which only a quarter of the cached
files have; and the search recording what it read. The user chose the last ("do it once and correct"), with the
cached file's own checksum as the identity: the index holds it for all but six files.

The record was shown complete by replaying 39 entries offline, covering every kind of data layer that has an
entry, on caches built only from their records: each `ok`. For seven of them one more stored answer steered the
search (Nominatim's for the country of the centre, or an index answer); each acts only by choosing the source or
the files, which the record holds. What the record does not see is listed in known-bugs.md ("The data record: what
it does not see").

## What was decided and built

| When | What | In `main` as |
| --- | --- | --- |
| 2026-11-23 | The audit; sixteen decisions of the user | (the report is not in the repository) |
| 2026-11-24 | Three outcomes and the `--update` guard; the refusal of an empty cache; seeding; the run log with requests per host; basisdata.nl's limits; a dead host fails fast; R48 re-baselined; the rules for sessions | tag `history/regression-failures` |
| 2026-11-24 | R17 by name only; `--cold` for every cache but the real one; a tiled search resumed with no tile left keeps its data record and credits (a fault found on the way) | tags `history/regression-cold`, `history/resume-record` |
| 2026-11-24 | The data record: run.json's `identity`, the harness's side file and line, `cache status` exact, the completeness check | tag `history/data-record-task` |
| 2026-11-24 | Two follow-ups of the data record: a layer's files noted before the read too (a file replaced while it is read is not known); `cache status` reading only as a whole, also beside a running search; the world coastline file found in a data folder whose path holds `[` | tag `history/data-record-followups` |
| 2026-11-25 | A data folder whose path holds `[`: every listing that starts at the data, cache or runs folder takes the folder's name as it is, the two comparisons of a listed path with a built one too; a test keeps new listings so (`tests/test_glob_folders.py`) | tag `history/glob-escape` |
| 2026-11-26 | R70 by name only and in no set, until its provider lifts the block: neither `--all` nor a set can ask basisdata.nl from a blocked network (one `--all` run had) | one commit |

## Still open

- **R17**: one run by name when Overpass answers, at most once a day: either its counts are stored again (OSM
  edits) or its two readers differ (a fault).
- **R70**: waits for the provider's answer; the islands' new read path has not met the real host yet. Until then
  it runs by name only and is in no set.
- **PC-wide limits for Overpass and Nominatim**, and a contact in the User-Agent of a development machine.
- **The data record's short windows that are left** (known-bugs.md, "The data record: what it does not see"): the
  OpenStreetMap tiles of a coastline or an area and the world file's edition are noted once, after their read
  (left so on the user's word of 2026-11-25).
