# The providers watched

2026-11-23. The mirror serves our own tiles of datasets whose providers publish them only as huge files (ÚGKK's
national ZIPs of 150-200 GB, SPW's province ZIPs, DROTe's and Valle d'Aosta's single ZIPs). Nothing in the cutting
or publishing tools asks a provider again: `cache update` covers the cached tiles of on-demand sources only, and
`tools/mirror_tiles.py` treats changed inputs as a new edition without ever looking for them. `tools/mirror_watch.py`
does that look, for every dataset on the mirror (the user's words of 2026-11-22: "implement strategy for all data,
which is provided on mirror"; "Implement if for every data set in the mirror."). It never downloads a data file and
never recuts: a report is for the user, and a new edition is his decision.

## Two kinds of change, two checks

1. **The same file replaced** (a correction at the same address, as SPW's of 2024-01-23):
   - `File`: a HEAD of the file, its size (Content-Length), Last-Modified and ETag against the baseline. Equal size
     and equal ETag (a weak and a strong form of one tag count as equal) is the same file; a Last-Modified that
     differs alone is reported too (a file rewritten at the same size may show only in its date: a report costs a
     look, a missed change costs stale tiles). An HTML page answering instead of the file (a challenge or a login
     page served with 200) is "not checkable", never a change.
   - `Feed`: where a HEAD gives no size or date (SPW's ZIPs), the provider's ATOM feed: the entry of our files (by
     its id), its `updated` and each enclosure's `length`. The feed's own `updated` is not compared.
2. **A successor published at another address** (ÚGKK's second cycle, a new Walloon campaign, a new DROTe model),
   which a HEAD on the old file never sees:
   - `Listing`: a page, feed or record reduced to the sorted set of the strings its patterns extract (links,
     titles, dates, a count); a string added or removed is reported.

Whatever was readable is compared: a piece missing from an answer (a size, an enclosure's length, an entry's date)
is named beside a change found in the rest, and makes the signal "not checkable" only when nothing readable differs.
Nothing that only follows from an unreadable piece is a change: a province ZIP's length "gone" because its enclosure
lost its address, or entries "gone" because one lost its id, are that piece missing. The three ETag cases: a weak
and a strong form of one tag are the same; an ETag gone alone is a missing piece (not checkable); an ETag appearing
where the provider sent none when the record was adopted is a change, "(a new field)", every month until it is
adopted, since the baseline has nothing to compare it with before the user adopts it. An answer cut short (by its
Content-Length, or where HTTP cannot tell, by its own structure: an XML answer must parse, an HTML page end with
`</html>`), larger than 20 MB, or that a reader cannot parse is "not checkable" for that signal alone: the other
datasets' lines and the result file follow as always. Each request waits at most 60 s a step, and never past the
run's 10 minutes; a host that drips its headers a byte at a time can still hold a run until the job's 15 minutes end
it red.

## The rows

One per dataset on the mirror, or cut for it (`WATCH`); a dataset is published only with a row
(`tests/test_mirror_pairs.py` `test_every_published_dataset_is_watched`). A signal several datasets share is read
once a run, and each address is asked once. The baseline, `tools/mirror_watch.json`, holds one record per signal and
is committed: its changes show in git.

| Dataset | Check 1: the same file replaced | Check 2: a successor published |
| --- | --- | --- |
| slovakia | `File` × 2: `DMR5_0_sjtsk03_bpv.zip`, `DMP1_0_sjtsk03_bpv.zip` (opendata.skgeodesy.sk/static/LLS/) | `Listing`: ÚGKK's provision page (www.skgeodesy.sk/geoportal/zbgis/lls/poskytovanie/), its data ZIPs under `static/LLS/`: the national models and the lots of the second cycle (DMR 6.0, DMP 2.0), 66 links on 2026-11-23 (16 lots); a new lot or a national second-cycle ZIP is the change. Left out: the footprint archives (`LLS/Footprints/`), the overview archives (on www.skgeodesy.sk) and the INSPIRE copies under `static/INSPIRE/` (the same models in another CRS) |
| madeira | `File`: `MDT_2m.zip` (irig-storage.madeira.gov.pt) | `Listing`: the SNIG record abba9a83 (its ISO 19139 XML): its dates and its download links (`WWW:DOWNLOAD` resources), 13 items on 2026-11-23. Left out: the contacts' and organisations' links, the viewer and the WMS |
| porto-santo, desertas, selvagens | `File`: `mdt_5m.zip`, one request for the three | the same SNIG record, one request for the four datasets |
| aosta | `File`: `DTM0508_002_UNICO.zip` (geoprodotti.regione.vda.it) | `Listing`: the region's geoportal page of DTM products (geoportale.regione.vda.it/download/dtm/): the download keys (`carta=`) and the products' information sheets. On 2026-11-22 it already lists a DTM 2022 of the Dora Baltea valley (`DTM2022_DORA`) beside the 2005/2008 one we cut (a candidate in docs/roadmap.md) |
| wallonia | `Feed` × 2: SPW's ATOM feeds of the MNT and the MNS 2021-2022, the entry `..._GEOTIFF_3812_PROV` and its five province ZIPs' lengths | `Listing` × 3: both feeds' entry ids (MNT 3, MNS 2), and SPW's catalogue Metawal (its CSW: the dataset records titled "Relief" and "Wallonie", 24, with their count) |
| portugal, when it is published | `tools/cdd_fetch.py plan` again where the fetch folder is, compared with its `done.jsonl` (the fetch counts the items a new plan lists with another version or size) | the CDD's collection list |

## The commands

    python tools/mirror_watch.py check [dataset ...] [--json] [--json-out FILE] [--previous FILE]
    python tools/mirror_watch.py adopt dataset ...
    python tools/mirror_watch.py list

`check` prints one line per dataset: `same`, `changed: <what>: <from> -> <to>; ...`, or `not checkable: <signal>:
<why>` (no answer, a refusal, a status other than 200, an answer cut short, a missing field, a page the patterns
find nothing in, the run's 10 minutes up). A provider that does not answer is never a change, and a change is never
hidden by another signal's failure: a dataset with both says both. Exit code 1 when any dataset changed, else 3 when
any is not checkable, else 0; 2 for usage. `--previous` reads the previous run's `--json-out`: a dataset not
checkable now that was checkable (or absent) then says `not checkable (first time)` and does not make the exit code
3. "Not checkable" is judged per dataset, not per signal: one signal failing one month and another the next count as
twice. `--json-out` is written after the lines; when it cannot be written a line says so. `adopt` reads the signals
of the datasets named and rewrites their records; it refuses when one is not checkable or lacks a piece its record
needs. `list` shows the rows and the baseline's dates.

## Where it runs

The user's words of 2026-11-22: "Yes, GitHub Actions monthly", to the question "A workflow on the 1st of each month
(and startable by hand). A provider that does not answer is reported only when it also failed the month before."
`.github/workflows/mirror-watch.yml` runs `check --previous previous/result.json --json-out result.json` with the
runner's own `python3` (no project dependency), keeps `result.json` as an artifact for 90 days and reads the
previous run's before the check. "The previous run" is the newest unexpired result of an earlier run of this
repository's branch (a run that left none, or a fork's, is skipped). None found, or a look-up that fails (GitHub's
API, the download): a warning; one that hangs is stopped after 3 minutes; either way the check runs as with no
previous result (the user's choice of 2026-11-23, "Check anyway"). The one action beside checkout is `actions/upload-artifact`, pinned by its commit (accepted by the user on
2026-11-23): only an action can keep a file from one run for the next. It starts by hand from the repository's
Actions tab ("Run workflow").

- **A failed run** (GitHub mails it) means: a provider changed something (exit 1, the summary names it), or a
  provider was not checkable two runs in a row (exit 3). A first "not checkable" is a warning on a passing run.
- **What to do with a change:** look at it (the provider's page, the new file's date). Then either a new edition
  (below) or, when nothing that matters changed (a date that moved over the same file, a link of no new data),
  `python tools/mirror_watch.py adopt <dataset>` and a commit of `tools/mirror_watch.json`. The next run says
  `same`.
- **Not checkable twice:** the provider may refuse GitHub's addresses (or have moved the page). Run `check` by hand
  from another network: `same` there means the refusal is GitHub's; else fix the row and `adopt`.
- **GitHub's rules** (docs.github.com, "Events that trigger workflows", read 2026-11-23): "Scheduled workflows will
  only run on the default branch." "In a public repository, scheduled workflows are automatically disabled when no
  repository activity has occurred in 60 days." So the workflow runs once it is pushed to the default branch, and a
  quiet repository needs it enabled again by hand (the Actions tab) after 60 days without activity.

## What a report leads to

The user decides. A change of values is a new edition (U24, "new folder"): fetch the new files, cut them under a new
folder name, `mirror_publish.py verify`, publish it beside the old one, switch the catalogue to the new folder,
unpublish the old one once no release names it; then `adopt` the dataset and commit the baseline. Only a re-encoding
with the same values is swapped in place (`--same-values`).

## What it cannot see

- A provider that replaces a file and keeps its size, date and ETag (a File signal), or an entry's date and its
  lengths (a Feed).
- A successor announced only on a page no row reads, or left out of a row's pattern (ÚGKK's INSPIRE copies; a
  Walloon record titled without "Relief" or "Wallonie"; a SNIG link that is not a download).
- A record or page whose set is cut by the provider (Metawal's answer holds at most 100 records: its count is part of
  the set, so a growing count shows).

## Not tested yet

The workflow has not run on GitHub: nothing of this work was pushed. Its command line was run locally as the job
runs it (a copy of the tool and the baseline alone, `python -I`, the shell's `-e`); the first run on GitHub (by hand
or scheduled) is the first test of the artifact steps and of the providers' answers to GitHub's addresses.
