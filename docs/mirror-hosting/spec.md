# Mirror hosting: the implementation specification

2026-11-15. The specification of a data server ("the mirror") from which every Find-a-Line installation downloads
the tiles of the sources that cannot be read from their provider on demand. Nothing of it is built. The bar:
complete enough that a later session's agents build it without new decisions; what is still open is listed in
section 9, never hidden.

## 1. How to read it

Sections 2-3 say what was decided and how the parts fit. Sections 4-7 are the four solutions (A the mirror stack,
B the address contract and the publish tool, C the client, D the site's switch and the monitoring), each under the
same headings: Decision, Behaviour, Data, Interfaces, Files and pairs, Tests, Acceptance, Risks, Needs the user's
word. Section 8 is security and misuse, 9 what is still open, 10 the order of building with the files each agent
owns, 11 the rollout, 12 the definition of done, 13 the later payloads this design must not block.

**Measured sizes** (wave 0: sizes, `tools/mirror_sizes.py` on the master, 2026-11-15; MB and GB decimal; the
mirror's part of a search only, without the margin a real search adds). A Slovak search at 1 m, terrain and
surface: a 2 km square 8 requests and 46 / 56 / 61 MB (median / 90th percentile / largest), 5 km 24-32 requests
and 127 / 189 / 238 MB, 10 km 72 and 409 / 492 / 530 MB, 20 km 242 and 1367 / 1623 / 1753 MB. A tile: about
5-6.5 MB at 1 m (largest 8.2), 2 MB at 2 m, 0.4 MB at 5 m; each Slovak `index.json` about 1.2 MB. Whole
datasets: Slovakia 201.2 GB in 76 956 tiles, Valle d'Aosta 1.46 GB in 914, Madeira 0.33 GB in 235.

**Sources.** The user's decisions are quoted with their date; "(planner)" marks a recommendation taken without the
user's own word, which the user can overturn. Facts about the code were read on `main` 47c5fa7. "(wave 0: server)",
"(wave 0: publish)", "(wave 0: sizes)" name the research agent whose table a number or a claim comes from; a
number without a source is an estimate and says so. Effort is Claude effort: low, medium or high.

## 2. What was decided

### 2.1 By the user (2026-11-15)
| Id | Question | The user's answer |
| --- | --- | --- |
| U1 | Who may download | "Any installation, anonymous" |
| U2 | Which machine | "Another machine": "Home server or NAS", "Unraid or TrueNAS" |
| U3 | What answers on ports 80/443 | "An existing reverse proxy": "SWAG (linuxserver)" |
| U4 | The public site's own worker | "Always from the mirror" |
| U5 | The master copy on Z: | "No, another machine" (data are copied to the server) |
| U6 | The mirror does not answer | "Fall back at the start, fail in the middle" |
| U7 | Mirror down at the start, tiles in the cache (C12) | "a: fall back anyway" |
| U8 | Integrity anchor (C10) | "a: trust the served index" |
| U9 | Home address visibility (C4) | "a: direct" |
| U10 | Host name (C3) | "a: under the project's domain" |
| U11 | Madeira: ask the owner first, or publish on the catalogue's statement | "publish" |
| U12 | Valle d'Aosta: publish on the CC BY 4.0 document, or ask the region first | "publish" |
| U13 | The two privacy texts of section 7 | "yes" |
| U14 | The log's 14 days: A a daily cleanup in the stack, B a size-based wording | "A" |
| U15 | May the mirror's host name stand in the code | "yes" |
| U16 | Facts of the user's own system | "Do not put excact information about my system into repo - keep them local." |
| U17 | The file-server image (C2) | "a": nginx in its unprivileged image |
| U18 | The mirror's Docker network (N1) | "a": a network of its own, internal, that SWAG joins as a second network |
| U19 | The caps (C5) | "c with higher limit for VPS.": the fast profile, the site's server above it |
| U20 | The publish transport (C8) | "b": rclone over SFTP |

The request itself: "specification, architecture and DoD for mirror hosting inside docker compose", "possible issues
with security, missuse", "For now it will host only data which is requiring mirror, but later on also country
precompute CUBEs and (maybe) data downloaded for country precompute".

### 2.2 Taken as recommended (planner)
| Id | Choice | Taken |
| --- | --- | --- |
| P1 (C6) | The mirror's log | time, status, bytes, dataset, address, client version; never the tile path or the rest of the User-Agent; 14 days |
| P2 (C7) | Bans | none in version 1: limits only |
| P3 (C9) | Monitoring | black-box from the VPS, a byte summary at home |
| P4 (C11) | Hugging Face | dropped for now; the list of bases keeps a second base possible |
| P5 (C15) | A neighbour's data while the mirror is down | skipped, as an unavailable neighbour is today |
| P6 | Compose placement | a separate project `findaline-mirror` in `deploy/mirror/`, as monitoring is |
| P7 | Where the limits live | inside the mirror's container, keyed on the address SWAG passes |
| P8 | Refusals from the mirror | `net._get`'s existing longer back-off on 429/503, then the search fails; no extra pause mechanism (simpler than the plan's wording) |
| P9 | The index on the client | kept in memory per process, fetched at the start of a search; nothing new is stored (follows from U7 and U8) |

### 2.3 Decisions of the roadmap this changes
- 2026-10-25, "a public Hugging Face dataset only, no copy on the user's NAS (no maintenance, no load on the home
  uplink)": reversed by U2. Maintenance and the uplink's load are real costs now, bounded by the caps (A) and the
  update item (8, S14).
- "Storage: ... no object storage (only with a second machine)": a second machine exists now, for static data only.
- "Public hosting: a VPS that runs nothing else": stands; the mirror is not on the VPS.

## 3. Architecture

```
PC (cuts datasets, master on Z:) ── tools/mirror_publish.py ──▶ HOME SERVER (Unraid or TrueNAS)
                                                                 <root>/staging  <root>/public  <root>/trash
                                                                          │ read-only mount of <root>/public
                                                    container findaline-mirror-files (no published port)
                                                                          │ SWAG's Docker network
                                                    SWAG (TLS; the only door to the internet; already running)
                                                                          │ https://<mirror host>/v1/...
                       ┌──────────────────────────────────────────────────┴───────────────┐
             VPS: the site's worker (downloads)                       any other installation
             VPS: Telegraf asks /v1/datasets.json, alert               (self-hosted, the user's PCs without Z:)
```

- The PC that holds `FINDALINE_MIRROR` keeps reading the folder; HTTP serves every machine without it.
- The VPS's worker has no local copy any more (U4): it is the mirror's heaviest correct client and gets a class
  of its own in the limits.
- One host name under the project's domain (U10), pointing straight at the home address (U9). No AAAA record
  until the limits count an IPv6 /64 as one visitor.

## 4. Solution A: the mirror stack (`deploy/mirror/`)

### Decision
U1, U2, U3, U14, U17, U18, U19, P2, P6, P7.

### Behaviour
1. One compose project `findaline-mirror` with one service `files`: a static file server. It mounts the public
   folder read-only and nothing else of the host, and publishes no port. Its only network is one the project
   makes itself, marked `internal` (no route out of the host), with a fixed subnet; SWAG's container is attached
   to it as a second network (U18), so the mirror's only neighbour is SWAG and it can reach nothing else. The
   visitor-address header is believed from that subnet only. Hardening as the site's containers: a non-root user, read-only root, all
   capabilities dropped, no-new-privileges, memory and pid limits with `memswap_limit` equal to `mem_limit`,
   json-file logs with a size cap, a healthcheck, the image pinned by digest, `restart: unless-stopped`.
2. It answers `GET` and `HEAD` only (anything else 405; a request body is never read). It serves exactly:
   `/` (the landing page), `/robots.txt` (disallow all), `/v1/datasets.json`, and under `/v1/tiles/` the files
   `index.json`, `README.md` and tiles named `<a>_<b>/<i>_<j>.tif` (integers, a minus sign allowed). Every other
   path, a path ending in `/`, a dot-file, a `.part` file and a symlink: 404. A request with a query string: 400.
   It never answers 401 or 403 (ban rules of proxies count them).
3. Content types: `image/tiff` for `.tif`, `application/json` for `.json`, `text/plain; charset=utf-8` for `.md`
   and `robots.txt`, `text/html; charset=utf-8` for the landing page. Headers on every answer:
   `X-Content-Type-Options: nosniff`, `Cross-Origin-Resource-Policy: same-origin`, `X-Robots-Tag: noindex`; no
   `Access-Control-*` header. `ETag` and `Last-Modified` on files; `Cache-Control: no-cache` on `index.json` and
   `datasets.json`, `max-age=86400` on tiles (a dataset may be swapped, U8).
4. Byte ranges: one range per request is served (206); a request for several ranges is refused (416).
5. Limits, all inside the container, keyed on the visitor's address from the one header SWAG sets
   (`X-Real-IP`; believed only from the proxy's own address on the shared network; the same header sent by a
   visitor is overwritten by SWAG, and one sent by another container is not believed): concurrent requests per
   address, concurrent requests of all visitors together, requests per second per address, bytes per second per
   request. A second class for the addresses named in the project's `.env` (`MIRROR_TRUSTED_ADDRESSES`: the VPS)
   with its own numbers and outside the visitors' total. Every refusal is a 429 with `Retry-After` (the server
   has one status for all its limits). The numbers (U19: the fast profile, the site's server above it):

   | | Visitors | The trusted class (the VPS) |
   | --- | --- | --- |
   | bytes per second per request | 6 MB/s | 16 MB/s |
   | concurrent requests per address | 4 | 4 |
   | concurrent requests of the class together | 5 (so at most 30 MB/s for all visitors) | its own 4, outside the visitors' 5 |
   | requests per second per address | 20, burst 40 | not limited |

   The client's own numbers are half the visitors' (C6): 2 connections, so a normal installation gets 12 MB/s
   and the site's server 32 MB/s. The trusted class's 16 MB/s per request is the session's reading of "higher
   limit for VPS" (the user gave no number). Visitors and the site's server together can ask more than the home
   uplink carries: the user chose this profile knowing it; the line is then full for that time.
   The mirror sends `X-Accel-Buffering: no` on every
   answer: without it the proxy's default buffering swallows a file at once into its temporary files, the
   mirror's connection ends in milliseconds and the connection caps count nothing (wave 0: server, measured:
   the cap was passed with SWAG's defaults and held with the header; SWAG's conf needs no change for it).
6. Timeouts for a slow visitor: headers 10 s, sending 30 s between two writes, keep-alive 15 s.
7. The log (P1), one JSON line per request: time, status, bytes sent, request time, the dataset (the first path
   part after `/v1/tiles/`, else `-`), the visitor's address, the limit that refused (or `-`), and the client's
   version (the `Find-a-Line/<version>` token of the User-Agent, else `other`). Never the tile's path, the query
   or the rest of the User-Agent. It is kept 14 days and no longer (U14): one file per day on a volume of the
   project's own (the only thing the container writes), and the stack itself deletes a file once it is older
   than 14 days, daily, with no job on the host. Nothing of the requests goes to the container's stdout, so
   Docker's own log holds no visitor data; the server's error log runs at its "critical" level, because its
   ordinary error lines quote the request with the tile's path (wave 0: server, seen on a refused symlink).
   How the daily file and the cleanup are made is the build's choice within these words; a way to try first:
   the day in the log file's name from the server's time variable, the cleanup a loop started beside the server
   in the same container. The image's root stays read-only: the log volume and a tmpfs are all it writes.
8. What SWAG must do, in the one file `deploy/mirror/swag/findaline-mirror.subdomain.conf`: answer the mirror's
   host name (an explicit `server_name`: SWAG's `<name>.*` pattern fits only its own domain) with SWAG's
   certificate, pass every request to `files` with SWAG's standard `proxy.conf` (it sets `X-Real-IP` itself),
   refuse every method but `GET` and `HEAD` itself and accept a request body of at most 1 KB (SWAG's sample
   confs allow any size and would write a posted body to SWAG's disk before the mirror's 405), set no
   `proxy_ignore_headers` (it would switch off the mirror's `X-Accel-Buffering`), and write no access log for
   this host: SWAG's own log would hold the tile paths, and
   its three ban rules that read it (bad bots, probe paths, 401) then never see the mirror's visitors, which is
   P2. The mirror never answers 401 or 403, the statuses SWAG's other ban rules count.
9. The image (U17): nginx in its unprivileged image (`nginx/nginx-unprivileged`, the stable Alpine line, pinned by
   digest; uid 101, a tmpfs for `/tmp`; about 5 MiB of memory in use). Compared with Caddy and static-web-server
   (wave 0: server): it is the only one with every limit built in (Caddy: a request rate only through an
   unofficial plugin and a custom build, no cap on connections found; static-web-server: no limit per address),
   and it is the software SWAG and the site's own proxy run. The comparison's cells for the other two rest on
   second-hand quotes and several "not found"; it is strong for nginx, indicative for the others. A prototype
   behind a stand-in for SWAG passed 74 checks of the behaviours 2-8; its reviewer found the caps, the forged
   header, the content and the log checks sound and eight checks without a real control (see Tests). Not proven
   there and left to the build's tests: the timeouts of 6, the memory and pid limits, the trusted class at its
   full number, the nosniff header, the symlink and traversal refusals against targets outside the root, the
   behaviour on a Linux host (the prototype ran on Docker Desktop).

### Data
Nothing stored by the service but its log. The public folder is written only by the publish tool (B).

### Interfaces
`deploy/mirror/.env.example`: `MIRROR_PUBLIC_DIR` (the host path of `<root>/public`), `MIRROR_SUBNET` (the
project network's subnet, with a default), `MIRROR_TRUSTED_ADDRESSES`, `MIRROR_MEMORY`. The limits' numbers are constants of the server's config in
the repo, not settings (a wrong setting must not open the home line).

### Files and pairs
New: `deploy/mirror/compose.yaml`, `.env.example`, the server's config, `swag/findaline-mirror.subdomain.conf`,
`landing/index.html`, `robots.txt`, `README.md` (install on Unraid and on TrueNAS, update of the pinned image);
`tests/test_mirror_deploy.py`; `tests/mirror_check.sh`; a CI job `mirror` in `.github/workflows/ci.yml`.
Pairs to keep: the file patterns served ↔ `sources.readers.tilebases.grid_tile_name` and the publish tool's
layout (a test builds a name with `grid_tile_name` for negative and large numbers and asks the server); the log's
keys ↔ `tools/mirror_publish.py stats`; the limits ↔ the client's `net.HOST_RATES_OF`/`HOST_SLOTS_OF` entry for
the mirror host (the client at no more than half; a test reads both). `compose.yaml` of the site and
`tests/test_deploy.py` are not touched.

### Tests
- `tests/test_mirror_deploy.py` (static, offline): the hardening list of `test_monitoring.py::test_compose_hardening`
  applied to `deploy/mirror/compose.yaml`; no `ports`; the data mount read-only; the one network internal; the
  limits' pair with the client.
- `tests/mirror_check.sh` (CI job `mirror`, Docker): the project started with a fixture tree behind a stand-in
  proxy container that sets the address header as SWAG does; one line PASS/FAIL per behaviour of 2-7, including:
  each limit refusing beyond its number and not below; the trusted class not counted in the visitors' total; a
  forged address header from a visitor not believed; `grid_tile_name` names served; the log line's keys exactly,
  no tile path in it; a log file dated 15 days back is gone after the cleanup ran and one of 13 days is kept;
  the container's stdout holds no request line.
- **Every check has its control**: the review of the prototype found checks that pass with the behaviour broken,
  and the build's script must not repeat them. Required: a symlink whose target exists outside the served root
  (not a dangling one); a traversal path that would resolve to an existing file outside the root; the
  `Server` header asked of the mirror itself, not of the proxy in front; the trusted class's cap with a file
  large enough that its number of requests really overlap, at the cap and one beyond; the request rate without
  a burst hiding the boundary; `HEAD` with its status and an empty body; "no way out" with a control container
  on an ordinary network that does reach the address (so a failure means isolation, not a PC without internet);
  the log checks on the lines of the very requests just sent (a marker in the request). For each check the
  script's self-test flips the config (a second config with the behaviour off) and expects FAIL.
- The same script with `--live https://<mirror host>` leaves out what needs the fixture and runs against the real
  mirror through SWAG (acceptance on the machine; run from the PC). It must show that the real SWAG honours the
  mirror's `X-Accel-Buffering` (the per-address cap refuses a request while two slow downloads are held open):
  the prototype proved it only against a stand-in with a subset of SWAG's settings.

### Acceptance
Every line of `mirror_check.sh` PASS in CI and live; `docker inspect` of the running container on the home server
shows read-only root, no capabilities, no published port (the README's check command).

### Risks
- A FUSE share (Unraid's `/mnt/user`) may serve many small files slowly and rename across disks by copying
  (wave 0: server): the README names the path to use.
- Disks that spin down would delay the first byte beyond the client's start check: the README requires storage
  that never spins down for the public folder; measurement M2 confirms the first byte's time.
- The pinned image gets no automatic security updates: the README has a dated "check the image" step, and the
  site's monitoring reminds (D). A compose plugin skips digest-pinned images in its update checks: the digest is
  edited by hand.
- **Adding the mirror's name to SWAG's certificate is not a quiet step** (wave 0: server; SWAG's certificate
  init script, read line by line by the worker and by its reviewer). What the script does when any of ten
  settings changed (the names among them, and also the staging switch): it revokes the existing certificate (a
  failed revoke is ignored), deletes the certificate folders, saves the new settings, and asks for a new
  certificate with the validation's own listener on port 80; when no certificate results it prints an error
  and waits forever. Inferred, not in the script's text: SWAG's web server is not running during this (the
  validation needs port 80 for itself), so every site behind SWAG is down for that time, and stays down after
  a failed validation until a restart succeeds (a restart asks again without a second revoke). The README makes
  it a planned step in a maintenance stop: the new name's DNS record in place and answering first, port 80
  reaching SWAG checked from outside. **No trial with SWAG's staging switch on the live SWAG**: switching it
  on is itself one of the ten changes and would revoke and delete the production certificate, and switching
  back would do it again.
- The mirror's network (U18): a network of the project's own, marked internal, that SWAG joins as its second
  network, gives the container no way out and no neighbour but SWAG (proven in the prototype). Where a platform
  drops a container's second network when that container is updated, the mirror is unreachable until it is
  attached again: an outage, never an exposure. The README says how to make the attachment lasting on the
  platform and how to check it.
- Serving from a share that passes through a FUSE layer is slower and may rename by copying: the README names
  the pool's direct path for the public folder, staging and trash (one file system, so the swap's renames are
  atomic).

### Needs the user's word
The trusted class's number, if 16 MB/s per request is not what "higher limit" meant; the measurement M2 on the
real server before the numbers are final (section 11, step 3).

## 5. Solution B: the address contract and the publish tool

### Decision
U1, U5, U8, U10, U11, U12, U20.

### Behaviour: the address contract
- `https://<mirror host>/v1/tiles/<dataset>/<product>/<res>m/index.json` and `.../<i//10>_<j//10>/<i>_<j>.tif`:
  the mirror folder's layout (`tools/sk_tiles.py`, `tools/mirror_tiles.py`) under `/v1/tiles/`.
  `<dataset>/README.md` is the dataset's card.
- `/v1/datasets.json`: `{"version": 1, "generated": <UTC>, "datasets": [{"id", "title", "licence", "attribution",
  "source", "products": [{"path": "slovakia/dmr5/1m", "tiles": n, "bytes": b, "index_sha256": h}]}]}`.
- `/v1/cubes/` and `/v1/cache/` are reserved and answer 404.
- A later change of the layout gets `/v2/`; `/v1/` keeps answering as long as releases that know only it are in
  use, then 410.
- A published dataset may be replaced as a whole (U8): clients take the index again at each search's start and
  after a mismatch.

### Behaviour: `tools/mirror_publish.py` (run on the PC)
- `verify <folder>`: for every `index.json` below it: every listed tile exists and has its sha256; no tile file
  that the index does not list; not `partial`. Exit code 1 and the list of faults otherwise. Works on the master
  and on the server's copy.
- `publish <dataset> --to <root>`: refuses when the dataset has no row in `PUBLISHABLE` (below), when `verify`
  fails on the master, or when `<root>` has less free space than the dataset plus 10 GB. Copies into
  `<root>/staging/<dataset>/` (resumable: a file already there with the index's sha256 is kept), verifies the
  staged copy against the master's indexes, then: `<root>/public/v1/tiles/<dataset>` → `<root>/trash/<dataset>-<UTC>`
  (if it exists), staging → `<root>/public/v1/tiles/<dataset>`, then writes `datasets.json` (through a `.part`
  outside the served tree and a rename). A folder with content cannot be replaced by one rename, so between the
  two the dataset is absent for a moment (both renames on one file system: milliseconds). The client's rule
  covers it: a 404 for the index or for a listed tile is asked again after `net`'s usual pause (C, behaviour 2),
  so a search that meets the window goes on. Every rename on a share goes through a retry as
  `tools/mirror_tiles.py` `_replace` does (WinError 5 on the Z: share is known). Old trash is removed by `clean`.
- `unpublish <dataset> --to <root>`: the dataset → trash, `datasets.json` rewritten; one command (a takedown).
- `stats <log file>`: bytes and requests per day and dataset, refusals per limit, from the server's log lines.
- `PUBLISHABLE`, one row per dataset, beside `DATASETS`; `publish` refuses a dataset without a row or with an
  empty field: `dataset`, `products`, `basis_kind` (licence, metadata statement, written permission), `licence`
  and `licence_url`, `basis_url`, `basis_quote` (the original sentence), `basis_checked` (date), `attribution`
  and `attribution_url`, `changes` (per product, the averaging too), `not_endorsed` (the sentence), `notes`,
  `approved` (the user's word and its date). The rows of today (wave 0: publish, quotes dated 2026-11-15):

  | Dataset | Basis | Attribution | To settle before its row is written |
  | --- | --- | --- | --- |
  | Slovakia (DMR 5.0, DMP 1.0) | CC BY 4.0 (ÚGKK SR's terms: "Autor ÚGKK SR / Licencia CC-BY 4.0") | "ÚGKK SR" | the card's "Changes made" must name the 2 m and 5 m averaging (today only under "Layout") |
  | Valle d'Aosta (DTM 2005/2008) | CC BY 4.0 by the region's licence PDF that the catalogue already records ("distribuire ... Modificare ... anche commerciale"). A second PDF on the same server says CC BY 2.5 Italia and its own sentence names consulting, extracting, reproducing and changing, not distributing (that would rest on the licence's legal text, not fetched) | "Dati estratti dal Modello Digitale del Terreno (DTM) della Regione Autonoma Valle d'Aosta." | published on the CC BY 4.0 PDF by U12 ("publish"); the row's `notes` name the second PDF |
  | Madeira (DTM 2 m) | **weak**, published by the user's decision U11 ("publish") on the national catalogue's "No conditions apply" (`basis_kind`: metadata statement). No licence document was found. Against, all in the regional order 36/2022: obtaining the owner's products "is subject to payment", its price table lists "MDT 2 m (folha)" at 42 €, use licences are to be published by the owner (not found), and commercial use is named only for the region's own services. Whether today's free file is that priced product is not established. `unpublish` is the answer to an objection | none found; changes must be told to end users | the row's `notes` carry the points against; `approved` quotes U11 |
  | Wallonia (batch 6) | CC BY 4.0, "Il peut publier les données et l'œuvre dérivée à condition de citer les sources" | with the row | - |
  | Hong Kong (batch 6) | **none found**: no sentence allows a changed copy on the internet; it would need the owner's written word | - | not publishable; stays a local-folder dataset (L3) |

- Transport to `<root>` (U20: rclone over SFTP; wave 0: publish). The refusals, the order of the steps and the
  local `verify` are the tool's own code; rclone carries the bytes and asks the server for the hashes.
  `--to` is an rclone remote and path (`<remote>:<root>`; the remote, an SFTP one with the server's
  `sha256sum` as its hash command, is set up once in the user's own rclone config, which holds the address and
  the key: nothing of it is in the repository or printed). The steps: `rclone copy` of the dataset into
  `<root>/staging/<dataset>` (a rerun skips what is there; several transfers at once); `rclone checksum sha256`
  of the staged copy against a SUM file the tool writes from the master's indexes (hashed on the server, so
  nothing is read back through the PC); the two renames and `datasets.json` with `rclone moveto` (a rename on
  the server within one file system); free space from `rclone about`. The tool refuses to start when `rclone`
  is missing or older than the version it was tested with (1.76), and when the remote reports no sha256
  support. Compared and not chosen: the tool's own tar over SSH with `sha256sum -c` (no new program; the
  session's recommendation), a share with read-back, robocopy and rsync (no sha256).
  rclone is an external program, not a Python dependency: `uv.lock` does not change; the README's setup for
  publishing names it. To confirm at the first install (not established by the research): that the server's
  shell has `sha256sum`, and how rclone behaves when a rename on the server is refused once.

### Data
The public folder is new stored data on the home server: created by `publish`, no migration. The master's layout
does not change.

### Files and pairs
New: `tools/mirror_publish.py`, `tests/test_mirror_publish.py`, the row in `docs/code-map/tools.md`.
Pairs: `PUBLISHABLE`'s ids ↔ the datasets of `tools/mirror_tiles.py` `DATASETS` plus Slovakia (a test); its
attribution ↔ the catalogue's `Credit` of the same source (a test compares the texts); the layout ↔
`grid_tile_name`.

### Tests
On fixture mirrors in `tmp_path`, with a folder as the rclone remote (rclone's local backend; the tests are
skipped where `rclone` is not installed, and CI installs the tested version in its Linux and Windows jobs, pinned
with its sha256): an unlisted, a partial and a damaged dataset are each refused with the reason; an interrupted
publish (rclone stopped after n files by a wrapper) resumes and the public tree never held a partial dataset
(asserted after every step); a staged file changed after the copy is caught by the checksum step before any
rename; a missing or too old `rclone` is refused with the text; `unpublish` leaves no file of the dataset under `public` and no entry in
`datasets.json`; `verify` finds a flipped byte, a missing tile and an unlisted file; `datasets.json`'s
`index_sha256` equals the master's; `stats` on a recorded log.

### Acceptance
After each real publish: `verify` on the server's copy passes, and every served `index.json` has the sha256 of the
master's (the live check script compares through HTTPS).

### Needs the user's word
Each dataset's first publication (rollout, section 11).

## 6. Solution C: the client

### Decision
U4, U6, U7, U8, P4, P5, P8, P9.

### Behaviour
1. **Where the tiles come from.** `TileBases.bases()`: the local folder when `FINDALINE_MIRROR` is set and holds
   the dataset (unchanged), then the mirror's address for the same path, `<base>/<mirror path>` (e.g.
   `.../v1/tiles/slovakia/dmr5/1m`), then the `urls` of the catalogue (still empty; a later second base). `<base>`
   is one constant, `MIRROR_URL`, overridden by the environment's `FINDALINE_MIRROR_URL`; an empty value turns the
   mirror off. `http://` is accepted (tests, a LAN mirror).
2. **Index-driven over HTTP**, the rules of a local folder: the base's `index.json` is fetched once per process
   and kept in memory; a tile whose key is null, or beyond the extent of a complete index, is "no data" without a
   request; an index that says `partial` or lacks the key inside its extent sends the tile to the next base; a
   listed tile is downloaded and its sha256 compared **before** the file is written into the cache or opened by a
   raster library. A 404 for a listed tile is an error, never "no data", and writes no "missing" row. On a 404 of
   a listed tile, a 404 of the index itself or a sha256 mismatch, the client waits `net`'s usual pause between
   attempts, fetches the index again once and the tile once more (this heals a dataset being swapped, B); then
   the search fails with a text naming the tile and the mirror.
3. **Fall back at the start** (U6, U7). `sources.choose.source_unavailable(source, reach=True)` asks every layer
   that has a remote base to fetch its native index now (`TileBases.reach()`: a short connect timeout, two
   attempts; the answer, an index or a reason, is kept for the process). No index: the source is unavailable with
   the reason "the data copy at <host> does not answer" (or its HTTP status), also when the cache holds every tile
   (U7), and `--source auto` takes the next source as today; a source named by `--source` is an error as today.
   The callers with `reach=True`: `choose_source` (search.py's three call sites go through it), the neighbour
   checks of `sources/filling.py` and `country.py` (P5: a neighbour is skipped), the probe's `skip_reason`.
   `unavailable()` itself never makes a request: it returns the kept reason. The web process never calls either
   (it reads names and credits only), and a test asserts that importing `sources` and building the page's schema
   and about page makes no request.
4. **Fail in the middle.** A tile that cannot be downloaded after `net._get`'s attempts (429 and 503 with its
   longer back-off) ends the search with the existing "Could not download ..." text; running it again resumes from
   the cache.
5. **Averaged resolutions** (Slovakia's 2 m, 5 m): available over HTTP only when that resolution's own index was
   fetched; without it the native tiles are used, as with a local mirror that lacks the folder
   (`GridTiles`' `available`, today true for any URL).
6. **Good manners.** `net.HOST_SLOTS_OF` gets the mirror's host with 2 connections and `net.HOST_RATES_OF` with
   600 requests a minute: half the server's 4 and 20 a second per address (A5), so two installations behind one
   address fit and a correct client is never refused. Requests to the mirror use a connect timeout of 10 s
   (today one 300 s value serves as both: a dead home server would cost 3 x 300 s a tile); the start check of 3
   allows 10 s to connect and 20 s for the index, two attempts. M2 confirms these on the real path.
7. **Tests never ask the real mirror**: `tests/conftest.py` sets `FINDALINE_MIRROR_URL` to empty for every test.
   `tests/regression.py`: an entry with `needs_path` runs when the folder exists (as today) or when
   `FINDALINE_MIRROR_URL` is set by the caller and `FINDALINE_MIRROR` is not.

### Data
None stored: the index lives in memory, the cache's layout, paths and rows are as today ("Stored data: none"). The
tiles the VPS's cache already holds stay valid (the same values; its 2 m and 5 m ones in the older lossless
encoding).

### Interfaces
`FINDALINE_MIRROR_URL` (README's options table, `.env.example`, `findaline.env.example`). `TileBases.reach()`,
`source_unavailable(source, reach=False)`.

### Files and pairs
`sources/readers/tilebases.py`, `sources/layers/gridtiles.py`, `sources/choose.py`, `sources/filling.py` and
`country.py` (their call sites only), `sources/probe.py`, `sources/net.py` (the host's entries, the connect
timeout), the catalogue files of the three sources (comments), `tests/conftest.py`, `tests/regression.py`,
`tests/test_sources.py`, `tests/test_madeira_aosta.py`, `tests/test_rates.py`, `tests/test_probe.py`,
`tests/test_public.py` (the no-request assertion).
Pairs of `.claude/rules/sources.md` and `providers.md` to keep: the patched names (`net._get` called and patched
through its module); every request path to a rated host takes its turn; a new numeric limit goes into the dicts
with its source; the mirror's `origin` ↔ `GridTiles(origin=)`. New pair for the rules: the server's limits ↔ the
client's entries (A).

### Tests
With `tests/http_server.py` serving a fixture mirror: the same cache files as from the folder, byte for byte;
null and beyond-extent tiles make no request (the server's request log is asserted); 404 of a listed tile is an
error and leaves no row and no file; a tile, then an index, with a wrong hash; a swap between index and tile (old
index, new tiles) heals by one refetch; `partial` goes to the next base; the server down at the start: unavailable
with the reason within the connect timeout (the test's clock is the timeout's value, not a wait), `auto` falls
back, a named source raises; down in the middle: the search's error, and a second run completes from the cache;
an averaged resolution without its index uses the native tiles; `FINDALINE_MIRROR_URL` empty: no request at all;
the local folder wins; a neighbour with the mirror down is skipped.

### Acceptance
- Results pinned: regression rows R13, R21, R34, R80 and R81 from an empty cache over HTTP (the mirror container on
  the PC serving a copy, on a local disk, of exactly the tiles those rows need with their indexes: Docker Desktop
  showed the mapped network drive as empty) give the counts and the `lines.csv` sha256 of the baseline. No
  baseline changes.
- `findaline.py sources check slovakia madeira aosta_valley` passes over HTTP.
- Full pytest green on the final tree.

### Risks
- A release with the mirror's address must never precede the index-driven client: both arrive in one commit
  (every release so far has empty URL lists, so no old client can meet the mirror).
- A short outage at a search's start gives a coarser result (U7): the run records the reason.
- Border strips depend on the mirror's state at that moment (P5): recorded in the run's notes as today.

### Needs the user's word
Nothing before the build; the numbers of 6 are confirmed or corrected after M2.

## 7. Solution D: the site's switch and the monitoring

### Decision
U4, P3.

### Behaviour
1. The VPS: `FINDALINE_MIRROR_DIR` is taken out of its `.env`; the worker's `/mirror` is then the empty volume and
   the worker downloads from the mirror. `/srv/findaline-mirror` is removed only on the user's word (section 11).
2. Telegraf on the VPS asks `<mirror>/v1/datasets.json` every minute (status, time, that the body names
   `"datasets"`) and reads the certificate's expiry of the mirror's host; the address comes from the monitoring's
   environment file, not from the repo's config.
3. Grafana rules: "mirror down" (no good answer for 45 min: short maintenance stops of the home server are
   normal and must not page) and "mirror certificate"
   (as the site's), to the same contact point; one row on the *Site* dashboard: up, answer time, certificate days.
   The VPS's own traffic to the mirror shows in the existing per-host service counts.
4. The docs' monthly item: the home server's image check and `mirror_publish.py stats`.

### Files and pairs
`deploy/monitoring/telegraf.conf`, `grafana/provisioning/alerting/rules.yaml`, the *Site* dashboard,
`tests/test_monitoring.py` (its pinned sets of rules and inputs), `docs/monitoring.md`; the pairs of
`.claude/rules/metrics.md` (a new field changes telegraf.conf, the panels and the rules together).
Docs: `docs/deployment.md` (a section for the mirror machine; section 16's VPS copy becomes the switch),
`README.md`, `setup-for-regular-folk.md`, `docs/data-sources.md`, `docs/roadmap.md` (2.3 and the parked items of
12), the rules `deploy.md`, `providers.md`, `sources.md`.

### Tests and acceptance
`tests/test_monitoring.py` green with the new rows; on the Grafana test stack the rule fires when the local
mirror container is stopped and clears when it is back.

### Needs the user's word
The privacy texts below; the alert's patience.

### Privacy texts (approved by the user on 2026-11-15, U13: "yes"; used word for word)
A visitor of the public site never reaches the mirror: the site's server asks it. So the site's privacy page
gains one entry, and the note for those who run their own installation goes into the README and onto the
mirror's landing page.
- Privacy page (`web.privacy_page`, a new entry): title "Elevation data from the project's data server", text
  "The elevation data of some regions come from a data server run by the project. This site's server asks it for
  them; your browser and your address never reach it."
- README and the landing page: "An installation that downloads from the project's data server shows it its
  address and which tiles it asks for. The server writes down the time, the address, the dataset (not the tile),
  the size and the Find-a-Line version of each request. It keeps this for 14 days, to hold the service within its
  limits, and uses it for nothing else. To never contact the data server, set `FINDALINE_MIRROR_URL` to empty;
  the regions it serves then use coarser data."
The pair to keep (a new bullet for `.claude/rules/web-app.md` and `deploy.md`): these texts ↔ the log's keys and
its 14 days (A7); a new key or another period changes the texts, with the user's yes.

## 8. Security and misuse

| # | Threat or misuse | What the design does | What stays |
| --- | --- | --- | --- |
| S1 | One address scrapes everything, again and again | A5: connections, rate and requests per address | a patient scraper gets the open data once: allowed by their licences |
| S2 | Many addresses fill the home uplink | A5: the visitors' total; the VPS in its own class | a packet flood below HTTP hits the home line (U9 accepted this) |
| S3 | A free tile CDN for others | no CORS headers, `Cross-Origin-Resource-Policy`, `robots.txt`, limits, the log; tokens can be added later under the same address | hot-linking from servers within the limits |
| S4 | Slow readers hold connections | A6 timeouts; the caps bound what one address and all together can hold | a reader just above the timeouts holds its slots; no minimum-speed rule exists |
| S5 | Range and query tricks | A4 one range; A2 a query is refused; no cache in front | - |
| S6 | Reading outside the data | only `<root>/public` mounted, read-only; A2's patterns; symlinks, dot-files, `.part` refused; staging and trash outside the served tree | - |
| S7 | The home network | no published port; nothing mounted but public data; no secret in the container; SWAG stays the only door | SWAG and the router, as before the mirror |
| S8 | A dataset without the right to redistribute | B's `PUBLISHABLE` is the only way in; cards and the landing page carry the credits; `unpublish` | a wrong row, reviewed like code |
| S9 | Damaged, cut-short or mixed tiles | the client's rule 2 (solution C): sha256 before any use; B: staging, verify, swap | - |
| S10 | The home server taken over serves crafted tiles | U8: the mirror is trusted as every provider is; TLS; the worker on the VPS runs in its hardened container | every installation trusts the home server's files (the user's decision; pinning hashes in the repo was the alternative) |
| S11 | Privacy of those who download | P1's log; SWAG's access log off for the host; the texts of D | the operator can see live traffic; said in the text |
| S12 | The site depends on a home server | U6, U7; D's alert | coarser results on mirrored ground while it is down |
| S13 | A limit set wrong throttles the site | the VPS's class; the client at half the limits; the pair's test | several installations behind one address share one allowance |
| S14 | An old image nobody updates | digest pin; the monthly item; D's reminder | a manual step at home |
| S15 | The public copy fills the pool | B: the free-space check before a publish; `clean` | - |

## 9. Still open

| Id | What | Who | When |
| --- | --- | --- | --- |
| C2, C5, C8, N1 | the image, the caps, the transport, the network | decided at gate 1: U17, U19, U20, U18 | - |
| V1 | the trusted class's rate: 16 MB/s per request is the session's reading of "higher limit for VPS" | the user, a number if another was meant | before A is built |
| M2 | on the real server through SWAG: the first byte's time, sustained MB/s to the VPS and to an outside address, the caps holding with the real SWAG's buffering | measured at rollout step 3; the numbers of A5 and C6 are confirmed or corrected with the user | rollout |
| E1 | the server's shell has `sha256sum` (inferred from its package list, not seen) | checked at the first install; without it the transport falls back to the tool's own check | rollout step 1 |
| F1-F7 | the home server's facts (platform, uplink, the proxy's certificates, storage, how the PC reaches it, power and maintenance, the VPS's transfer quota) | answered by the user on 2026-11-15; by the user's rule they are kept out of the repository (the task's private notes). What they set stands here as requirements: the platform runs plain docker compose; the proxy adds the mirror's name as one more certificate name; the public folder is on storage that never spins down; the PC publishes over SSH; the alert waits longer than a normal maintenance stop | - |
| T1, L1, L2 | the privacy texts; Madeira's and Valle d'Aosta's basis | decided: U13, U11, U12 | - |
| L3 | Hong Kong (batch 6): no right to republish found; local folder only, or ask the owner | the user | with batch 6 |
| L4 | If tokens are ever added: CC BY forbids "technological measures" that restrict others; limits under which anyone still gets every file are not that (the research agent's reading, not legal advice), a token gate is a closer call | the user | only with tokens |

## 10. The order of building

(wave 0's results first; then, in a later session, under `docs/agent-workflow.md`.)

| Wave | Agent | Builds | Owns |
| --- | --- | --- | --- |
| 1 | server | solution A | `deploy/mirror/**`, `tests/test_mirror_deploy.py`, `tests/mirror_check.sh`, the job `mirror` of `.github/workflows/ci.yml` |
| 1 | publish | solution B | `tools/mirror_publish.py`, `tests/test_mirror_publish.py`, the step that installs rclone in the Linux and Windows test jobs of `.github/workflows/ci.yml` (the server agent owns only the job `mirror` there: the two edit different jobs, and the contract names the lines) |
| 1 | client | solution C | the files of C's "Files and pairs" |
| 2 | site | solution D, the docs, the HTTP regression acceptance | `deploy/monitoring/**`, `tests/test_monitoring.py`, `docs/**`, `README.md`, `setup-for-regular-folk.md`, `.claude/rules/*`, `docs/code-map/*` |

Wave 1's three agents touch no common file. The pair "server limits ↔ client entries" is tested in
`tests/test_mirror_deploy.py` (server) against constants the client agent adds: the contract of wave 1 fixes their
names (`net.HOST_RATES_OF[<host>]`, `net.HOST_SLOTS_OF[<host>]`, the host from `tilebases.MIRROR_URL`) before the
agents start. Effort: A medium, B medium, C high (the search's source choice, results pinned), D medium. Every
build passes the scope reviewer and the code reviewer (high for C).

## 11. Rollout (each step on the user's word)

1. The stack on the home server from A's README; `mirror_check.sh --live` with an empty public folder.
2. Publish Madeira (0.33 GB), check; then Valle d'Aosta, then Slovakia; `verify` on the server after each.
3. M2 on the real path (the first byte's time, sustained MB/s to the VPS and to an outside address, the caps
   through the real SWAG); the user confirms or corrects the numbers of A5 and C6.
4. The client (C) and the address into `main` in one squash; push; the VPS updated.
5. The VPS's `.env` switched (D1); one Slovak search compared with the same search of before (counts and
   `lines.csv` sha256).
6. After the agreed number of good days: `/srv/findaline-mirror` removed from the VPS.
7. Batch 6 with the same tool when its tiles are cut: Wallonia can be published (CC BY 4.0). Hong Kong cannot
   (L3): it stays a dataset of the local folder, so the site has it only if the VPS gets a copy in its
   `FINDALINE_MIRROR_DIR` again, which the compose file keeps supporting for exactly this.

## 12. Definition of done

The build is done when every line holds; each names where its detail and its test are.

**The mirror stack (A)**
- [ ] `tests/test_mirror_deploy.py` green: hardening, no port, read-only data, an internal network, the limits'
      pair with the client.
- [ ] `tests/mirror_check.sh` in the CI job `mirror`: every behaviour of A2-A8 PASS, and every check's control
      FAILs with the behaviour switched off.
- [ ] The same script `--live` against the real mirror through SWAG: all PASS, among them the cap holding
      through the real SWAG and a log file of 15 days gone.
- [ ] On the home server the running container shows a read-only root, no capability, no published port, and no
      route out (the README's check commands).

**The address contract and the publish tool (B)**
- [ ] `tests/test_mirror_publish.py` green in the Linux and Windows jobs with rclone installed.
- [ ] Every published dataset has its `PUBLISHABLE` row with the user's approval quoted; its card states the
      changes (Slovakia's names the averaging).
- [ ] After each real publish: `verify` passes on the server's copy; every served `index.json` has the master's
      sha256; `datasets.json` lists it.

**The client (C)**
- [ ] The unit tests of C green; no test asks the real mirror (`FINDALINE_MIRROR_URL` empty in `conftest.py`).
- [ ] R13, R21, R34, R80 and R81 over HTTP from an empty cache: the baseline's counts and `lines.csv` sha256.
- [ ] `findaline.py sources check slovakia madeira aosta_valley` passes over HTTP.
- [ ] The web process makes no request to the mirror (the test of C3).
- [ ] The client and the mirror's address reach `main` in one commit.

**The site and the docs (D)**
- [ ] `tests/test_monitoring.py` green with the mirror's rows; the rule fires and clears on the test stack.
- [ ] The docs and rules of D's "Files and pairs" written; the two privacy texts word for word; the roadmap's
      changed decisions (2.3) recorded; nothing of the home server's own facts in the repository (U16).
- [ ] Full pytest green on the squash tree; the stored-data line in the commit ("none").

**Rollout (11)**
- [ ] Each of its seven steps done on the user's word; M2's numbers confirmed or corrected by the user; one
      Slovak search of the site from the mirror compared with the same search of before.

## 13. Later payloads: what this design keeps possible

- **Country cubes** (about 5 GB a country, arrays up to 1.7 GB): they need a manifest with a sha256 per array, a
  streamed and resumable download (`net._get` reads a body into memory), a swap into a new build folder (a mapped
  file must never be overwritten), and a decision on publishing them at all (administrators only today; Slovakia's
  carries a FABDEM credit). The address `/v1/cubes/` is reserved; one range per request (A4) already allows
  resuming.
- **The cache of a country precompute** (Poland about 1.75 TB): a permission per source to redistribute, and a
  machine with that disk. The address `/v1/cache/` is reserved; the host name of its own (U10) lets the mirror
  move to such a machine without a change in any installation.
- **A second base** (P4): `TileBases` keeps a list of bases; a second address is one entry.
- **Tokens** (if anonymous access is abused): a header checked by the server under the same addresses.
