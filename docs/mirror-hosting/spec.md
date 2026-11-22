# Mirror hosting: the implementation specification

2026-11-15, second version (after a scope review and a builder's read of the first). The specification of a data
server ("the mirror") from which every Find-a-Line installation downloads the tiles of the sources that cannot be
read from their provider on demand. Built on 2026-11-16 (the task `mirror-hosting-build`); the text describes what
exists, the sentences the build changed name the decision (U27-U57) or the planner's ruling behind them. What is
still open is listed in section 9, never hidden.

## 1. How to read it

Sections 2-3 say what was decided and how the parts fit. Sections 4-7 are the four solutions (A the mirror stack,
B the address contract and the publish tool, C the client, D the site's switch, the monitoring and the docs), each
with: Decision, Behaviour, Data and interfaces, Files and pairs, Tests, Acceptance, Risks, Needs the user's word.
Section 8 is security and misuse, 9 what is still open, 10 the order of building with the files each agent owns,
11 the rollout, 12 the definition of done, 13 the later payloads this design must not block. Whether a provider has
replaced a dataset's files or published a successor, and what such a report leads to (a new edition, U24):
[watch.md](watch.md), "The providers watched" (`tools/mirror_watch.py`, monthly in GitHub Actions).

**Names.** "A.5" is behaviour 5 of solution A. U1-U57 are the user's decisions (U27-U57 taken during the build),
P1-P28 the planner's, S1-S17 the
security rows, M2, M4, E1 and E2 the items of section 9. `<host>` stands for the mirror's host name, `mirror.findaline.lukawski.org` (U23).

**Sources.** The user's decisions are quoted with their date; "(planner)" marks a decision taken without the
user's own word, which the user can overturn. Facts about the code were read on `main` 47c5fa7. "(wave 0: ...)"
names the research of 2026-11-15 a number or claim comes from: *sizes* (`tools/mirror_sizes.py` on the master),
*publish* (transport and licences, each licence quote checked against the saved provider page by a reviewer),
*server* (the image comparison and a prototype behind a stand-in for SWAG, with its reviewer's corrections).
A number without a source is an estimate and says so. Effort is Claude effort: low, medium or high.

**Measured sizes** (wave 0: sizes; MB and GB decimal; the mirror's part of a search only, without the margin a
real search adds). A Slovak search at 1 m, terrain and surface: a 2 km square 8 requests and 46 / 56 / 61 MB
(median / 90th percentile / largest), 5 km 24-32 requests and 127 / 189 / 238 MB, 10 km 72 and 409 / 492 / 530 MB,
20 km 242 and 1367 / 1623 / 1753 MB. A tile: about 5-6.5 MB at 1 m (largest 8.2), 2 MB at 2 m, 0.4 MB at 5 m; each
Slovak `index.json` about 1.2 MB. Whole datasets: Slovakia 201.2 GB in 76 956 tiles, Valle d'Aosta 1.46 GB in
914, Madeira 0.33 GB in 235.

## 2. What was decided

### 2.1 By the user (2026-11-15; U27-U57 during the build, 2026-11-15 to 17; U68 and U75-U80 2026-11-18/19; U86-U89 2026-11-21; U93, U94 2026-11-22)
| Id | Question | The user's answer |
| --- | --- | --- |
| U1 | Who may download | "Any installation, anonymous" |
| U2 | Which machine | "Another machine": "Home server or NAS" (its platform was named too; by U16 that stays in the task's private notes) |
| U3 | What answers on ports 80/443 | "An existing reverse proxy": "SWAG (linuxserver)" |
| U4 | The public site's own worker | "Always from the mirror" |
| U5 | The master copy on Z: | "No, another machine" (data are copied to the server) |
| U6 | The mirror does not answer | "Fall back at the start, fail in the middle" |
| U7 | Mirror down at the start, tiles in the cache | "a: fall back anyway" |
| U8 | Integrity anchor | "a: trust the served index" |
| U9 | Home address visibility | "a: direct" |
| U10 | Host name | "a: under the project's domain" |
| U11 | Madeira: ask the owner first, or publish on the catalogue's statement | "publish" |
| U12 | Valle d'Aosta: publish on the CC BY 4.0 document, or ask the region first | "publish" |
| U13 | The two privacy texts of D | "yes" |
| U14 | The log's 14 days: A a daily cleanup in the stack, B a size-based wording | "A" |
| U15 | May the mirror's host name stand in the code | "yes" |
| U16 | Facts of the user's own system | "Do not put excact information about my system into repo - keep them local." |
| U17 | The file-server image | "a": nginx in its unprivileged image |
| U18 | The mirror's Docker network | "a": a network of its own, internal, that SWAG joins as a second network |
| U19 | The caps | "c with higher limit for VPS.": the fast profile, the site's server above it |
| U20 | The publish transport | "b": rclone over SFTP |
| U21 | The visitors' total, since 5 requests fit only two installations | "a": 8 requests at 4 MB/s each |
| U22 | The log's status, request time and refusing limit against the privacy sentence | "a": kept, and named in the sentence |
| U23 | The mirror's host name | "mirror.findaline.lukawski.org" |
| U24 | A recut with other values: a new folder name, or always swap in place | "new folder" |
| U25 | The site's server: 16 MB/s per request, 32 MB/s in practice | "ok" |
| U26 | The rule "personal data never in a log": name the mirror's log as its one exception | "ok" |
| U27 | E2: how the publishing key reaches the home server, and what it may write | "SFTP container" (a small SSH/SFTP container that mounts only the mirror's root and listens on the LAN alone) |
| U28 | rclone on the PC (1.76 or newer) | "Yes, with winget" |
| U29 | The PC free for the build's heavy runs | "Free, the state is right" |
| U30 | The exact line of `CLAUDE.md` for U26 | approved as shown: "Keys, tokens and personal data never in the repository, a run's files, a printed text or a log; the one exception: the mirror's request log (`deploy/mirror`) holds addresses, for 14 days." |
| U31 | Slovakia's `PUBLISHABLE` row | "a" (approve; CC BY 4.0 by the owner's own terms) |
| U32 | The publishing container's image | "Own minimal image": Alpine and OpenSSH built in the repository, with a command gate |
| U33 | Where its compose file lives | "Own project in the repo": `deploy/mirror/publish/` |
| U34 | A rename the server does as a copy | "a": a README requirement only (one mount; the door refuses a rename it cannot do); no timing bound in the tool |
| U35 | The sha256 check trusts the rclone config, not the server | "a": the tool hashes its own lock file on the server right after writing it and refuses if that fails |
| U36 | The whole master hashed before every publish and resume | "a": kept, no flag to skip it |
| U37 | Turning the data server off on Windows (an empty value deletes the variable there) | "a": the setting also accepts `off`; the privacy sentence then names `off`, its exact words shown to the user first |
| U38 | The start check when the local folder holds the dataset | "a": as built, no request and no fall-back (the mixed case named) |
| U39 | A busy server (429) at the start check | "a": the start check stops at the first 429 and counts it as answering |
| U40 | 3D views of a finished run while the server is down | "a": accepted, with a clear message that the data server does not answer |
| U41 | The one failing test of `tests/test_web.py` | "a": the client agent adds the one line |
| U42 | How SWAG is attached to the mirror's network | "a": a command that attaches the running SWAG container, repeated after SWAG is recreated, with a check that shows when it is missing; the other way described with its risk |
| U43 | The publishing container's own log (the PC's LAN address, the key's fingerprint) | "a": kept, and said in the README |
| U44 | One log word (`conn`) for two limits | "a": accepted |
| U45 | The request log has no size bound | "a": the hourly cleanup also caps the log folder's size, the oldest files first; the number brought to the user after measuring; under a flood fewer than 14 days |
| U46 | The privacy text's last sentence, with `off` | "To never contact the data server, set `FINDALINE_MIRROR_URL` to `off`; the regions it serves then use coarser data." |
| U47 | "It keeps this for 14 days" (a flood can make the log hold less) | "It keeps this for at most 14 days", and the same two words in the `CLAUDE.md` line of U30 |
| U48 | The log's size bound (hourly; the oldest days first; today's file emptied whole and started again when it alone passes it) | 2 GB |
| U49 | CI's job `mirror` (about 75 minutes with its self-test) | it runs only when the mirror's files or its check script change, plus by hand |
| U50 | A dataset that reads the mirror but is not on the data server (Porto Santo, the Desertas, the Selvagens) | "a": the client reads the server's dataset list first and treats an unlisted dataset as unavailable, as it was before the mirror; a dataset starts working by itself when it is published |
| U53 | Madeira's islets: limit Madeira's source to its island (an islet then falls to the coarse source), publish the islets, both, or leave them | "b": publish Porto Santo, the Desertas and the Selvagens; their three `PUBLISHABLE` rows are brought to the user for approval before they are written; Madeira's source is not limited |
| U54 | The data server's host name in the public site's failure texts: keep it or hide it | "a": keep it |
| U55 | The islets' three `PUBLISHABLE` rows (the basis of Madeira's row, U11; against it the regional order's price of Porto Santo's 5 m model) | "a": all three approved as drafted (porto-santo, desertas, selvagens), 2026-11-17 |
| U56 | The islets' served cards (two left out a change under "Changes made": the Desertas' replaced reference-system label, Porto Santo's float64 to float32) | "a": both fixed first; the new card texts shown to the user before anything is published |
| U57 | Keeping the master's `README.md` files in step with the served cards (Porto Santo's and the Desertas' on the master are older than their cards of U56) | both: the publish tool notes a dataset's `README.md` that is missing or differs from the card it serves, at every `publish` and every `verify` of a master folder; the two files are rewritten once on the master by the cutting tool (`mirror_tiles.py cut`, which cuts nothing for a finished dataset), on the user's word |
| U68 | The door's path from the publishing PC | "a": Husarnet as a sidecar in the door's own compose project; `sftp` runs in its network namespace (`network_mode: service:husarnet`); no port published on the home server at all; `PUBLISH_ADDRESS` and `PUBLISH_PORT` dropped; only the door's port 2222 reached, by the user's Husarnet peers (history: the sidecar dropped by U89) |
| U75 | The door's Husarnet sidecar image (Husarnet's newest stable image is 2.0.180 of October 2023, on old OS libraries) | "Own image, fresh OS": a small Dockerfile on a current Debian slim with Husarnet's package from Husarnet's apt repository, checked first that the repository serves it (history: the sidecar dropped by U89) |
| U76 | The door left stopped after the sidecar was down for more than about 30 s, or after a reboot | "README line only": no scheduled `up -d`; `docker compose ps`, then `docker compose up -d` when a publish finds the door down (history: the sidecar dropped by U89) |
| U77 | The door worker's choices (own start script, healthy only with a peer of the user's so the PC joins first, `sftp` restarting itself, the sidecar as root with default capabilities and `NET_ADMIN`) | "Accept all"; memory and process limits added to the sidecar (history: the sidecar dropped by U89) |
| U78 | The stable repository serves only 2.0.180 (statically linked, October 2023) | "look for Husarnet 3": Husarnet 3.0 moved its control plane on 2025-12-08; its daemon is the nightly line only; 2.0.180 works through a compatibility layer to be shut down (history: the sidecar dropped by U89) |
| U79 | The sidecar's health after a restart with the join done once | "Drop 'joined'": health = a connection to Husarnet's base and control servers, and a peer other than Husarnet's own on the allow list (history: the sidecar dropped by U89) |
| U80 | The door's Husarnet daemon line | "Nightly 2.0.349": the 3.0-protocol daemon from Husarnet's nightly apt repository on the own Debian image, its version pinned; the PC's client a nightly too (history: the sidecar dropped by U89) |
| U86 | The door at all (2026-11-21) | "lets change how we do it - it is too complicated. Scrap door idea." The user makes a VPN link of their own between the PC and the home server; then "SSH straight to box": no door container; the publish tool's rclone SFTP remote aimed at the home server's own sshd at its address on that link; the home server hashes (`sha256sum`); the WireGuard sidecar (U81-U85) dropped (history: superseded by U89) |
| U87 | The door code already built | the sidecar removed, not `publish/` (as revised by U89): Husarnet's sidecar (`husarnet.sh`, `husarnet-sidecar.Dockerfile`, its compose service and settings), its checks, CI steps and README text removed from the build; `publish/`'s `sftp` kept; the WireGuard door's branch kept unmerged; the Husarnet door removed from the home server |
| U88 | Claude's use of the home server's address over the link | "Publishing only": rclone only (publishing and its checks); commands on the home server stay with the user |
| U89 | The door, revised (2026-11-21) | the user: "keep docker with sftp, but no door": the sftp container stays (gate, read-only, one mount), its port published on PUBLISH_ADDRESS, reached over the user's own VPN link; no sidecar (Husarnet's U68/U75-U80 and the WireGuard U81-U85 dropped) |
| U93 | Keeping SWAG on the mirror's network across SWAG's updates (2026-11-22; an update had dropped the attachment and the mirror answered 502) | "1": a scheduled job on the home server attaches SWAG again when it is missing, every 5 minutes (the network in SWAG's platform template was tried and failed: on some Docker releases the default bridge cannot be combined with the mirror's network, README "SWAG") |
| U94 | The numbers of A.5, C.3 and C.6 after M2 | kept as they are: "ok, do step 4" after M2's results and the planner's advice to keep them (the VPS's two connections had not met their mark at the time of the measurement) |

History, not in this branch: U81-U85 (2026-11-20/21), a WireGuard sidecar in place of Husarnet's for the door, was built and dropped (U86, U89).

The request itself: "specification, architecture and DoD for mirror hosting inside docker compose", "possible issues
with security, missuse", "For now it will host only data which is requiring mirror, but later on also country
precompute CUBEs and (maybe) data downloaded for country precompute".

### 2.2 By the planner (each can be overturned by the user)
| Id | Choice | Taken |
| --- | --- | --- |
| P1 | The mirror's log | per request: time, address, dataset, bytes, status, request time, the limit that refused, client version; never the tile path or the rest of the User-Agent (confirmed by U22) |
| P2 | Bans | none in version 1: limits only |
| P3 | Monitoring | black-box from the VPS, a byte summary at home |
| P4 | Hugging Face | dropped for now; the list of bases keeps a second base possible |
| P5 | A neighbour's data while the mirror is down | skipped, as an unavailable neighbour is today |
| P6 | Compose placement | a separate project `findaline-mirror` in `deploy/mirror/`, as monitoring is |
| P7 | Where the limits live | inside the mirror's container, keyed on the address SWAG passes |
| P8 | Refusals from the mirror | `net._get`'s existing longer back-off on 429/503 (three attempts), then the search fails; no extra pause mechanism |
| P9 | The index on the client | in memory, never stored (follows from U7 and U8) |
| P10 | Who asks whether the mirror answers | only the first planning of a search, an estimate, a country run's main process and the probe; later phases use the source the first one chose; a country run whose own source does not answer stops instead of falling back; a busy mirror (429) counts as answering (C.3) |
| P11 | How long an answer is kept | an index 300 s; a "does not answer" 60 s, and only for the next start check (C.2, C.3) |
| P12 | Averaged resolutions over HTTP | available whenever a remote base is set, as today; the publish tool guarantees them and a missing index is an error (C.5) |
| P13 | How config reaches the container | an image built from the pinned base image with the config, the pages and the start script copied in (A.1) |
| P14 | The trusted addresses | from `.env` through the start script, which accepts single IPv4 addresses only and refuses to start otherwise (A.5) |
| P15 | Whose address header is believed | any sender on the project's own network: only SWAG and the mirror are on it (A.5) |
| P16 | Several byte ranges in one request | refused (416) |
| P17 | Refusal status | 429 for every limit, `Retry-After: 10` |
| P18 | The server's error log | at its "critical" level: ordinary error lines quote the tile's path |
| P19 | The log's place | a folder of the host beside the public one (`<root>/logs`), so `stats` reads it over the publish remote |
| P20 | The cleanup | hourly; a log file whose date is 14 or more days back is deleted |
| P21 | The dataset card on the mirror | written by `publish` from the tool's card texts, not copied from the master |
| P22 | A dataset's attribution in `PUBLISHABLE` | not a second copy: read from the catalogue's `Credit` of the source |
| P23 | Empty facts in a `PUBLISHABLE` row | the word "none" where a dataset has no licence document or prescribed credit (Madeira) |
| P24 | Timeouts | server: headers 10 s, send 30 s, keep-alive 15 s; client: connect 10 s, the start check's index 20 s, two attempts |
| P25 | The client's own limits | 2 connections and 600 requests a minute to the mirror |
| P26 | The alert's wait | 45 minutes |
| P27 | Margins of the publish tool | 10 GB free beyond the need; rclone 1.76 or newer; trash kept 7 days by `clean` |
| P28 | `http://` mirror addresses | accepted (tests, a mirror on a LAN); the default address is `https://` |

### 2.3 Decisions of the roadmap this changes
- 2026-10-25, "a public Hugging Face dataset only, no copy on the user's NAS (no maintenance, no load on the home
  uplink)": reversed by U2. Maintenance and the uplink's load are real costs now, bounded by the caps (A.5) and
  the monthly item (D.4).
- "Storage: ... no object storage (only with a second machine)": a second machine exists now, for static data only.
- "Public hosting: a VPS that runs nothing else": stands; the mirror is not on the VPS.

## 3. Architecture

```
PC (cuts datasets, master on Z:) ── tools/mirror_publish.py + rclone (SFTP) ──▶ HOME SERVER
                                                                 <root>/staging  <root>/public  <root>/trash  <root>/logs
                                                                          │ public read-only, logs writable
                                                    container findaline-mirror-files (no published port)
                                                                          │ the project's own internal network
                                                    SWAG (TLS; the only door to the internet; already running;
                                                          attached to that network as its second one)
                                                                          │ https://<host>/v1/...
                       ┌──────────────────────────────────────────────────┴───────────────┐
             VPS: the site's worker (downloads)                       any other installation
             VPS: Telegraf asks /v1/datasets.json, alert               (self-hosted, the user's PCs without Z:)
```

- The PC that holds `FINDALINE_MIRROR` keeps reading the folder; HTTP serves every machine without it.
- The PC reaches `<root>` through the publishing door: a second compose project on the home server
  (`deploy/mirror/publish/`, an SFTP container with a command gate, its one port published on `PUBLISH_ADDRESS`,
  the server's address the PC reaches: on the LAN, or over a VPN or WireGuard link of the operator's own, never
  the internet; U27, U32, U33, U89; no sidecar since U89).
- The VPS's worker has no local copy any more (U4): it is the mirror's heaviest correct client and gets a class
  of its own in the limits.
- One host name under the project's domain (U10), pointing straight at the home address (U9). No AAAA record
  until the limits count an IPv6 /64 as one visitor.

## 4. Solution A: the mirror stack (`deploy/mirror/`)

### Decision
U1, U2, U3, U14, U17, U18, U19; P1, P2, P6, P7, P13-P20, P24.

### Behaviour
1. **The project.** One compose project `findaline-mirror` with one service `files`, built by
   `deploy/mirror/Dockerfile` from nginx's unprivileged image (`nginx/nginx-unprivileged`, a tag of the stable
   Alpine line, pinned by digest through an `ARG` as the site's Dockerfile pins its bases), with the server's
   config, the landing page, `robots.txt` and the start script copied in (P13). It mounts `<root>/public`
   read-only and `<root>/logs` writable (owned by the image's uid 101), and nothing else of the host; it publishes
   no port. Its only network is one the project makes itself, marked `internal` (no route out of the host), with a
   fixed subnet (`MIRROR_SUBNET`); SWAG's container is attached to it as a second network (U18), by default with
   `docker network connect findaline-mirror_mirror swag` on the running SWAG, repeated after SWAG is recreated, with
   a check that prints `NOT ATTACHED` (U42), so the mirror's only neighbour is SWAG and it can reach nothing else.
   The publishing door is a project of its own (`findaline-mirror-publish` in `deploy/mirror/publish/`, one service
   `sftp`: Alpine and OpenSSH, key only, a command gate allowing the SFTP server and `sha256sum` of one file under the
   mounted `<root>`; U27, U32, U33); "one service, no published port" holds for the mirror's project, and the door
   publishes one port on one address of the server (`PUBLISH_ADDRESS`, required: the address the publishing PC
   reaches, on the LAN or over the operator's own VPN or WireGuard link; U89). No sidecar: Husarnet's (U68,
   U75-U80) and the WireGuard one (U81-U85) were dropped (U86, U87, U89). Hardening as the site's containers: the non-root user,
   read-only root, a tmpfs for `/tmp`, all capabilities dropped, no-new-privileges, memory and pid limits with
   `memswap_limit` equal to `mem_limit`, json-file logs with a size cap, a healthcheck, `restart: unless-stopped`,
   `init: true` (the start script's loop is reaped). The start script is the image's entry point: it writes what
   it generates (the trusted list, the landing page with the contact, the heartbeat) into the tmpfs, which the
   config includes, starts the cleanup loop and then the server. `<root>/logs` is made by the README's install
   step, owned by uid 101 (Docker would make a missing folder as root, and the server could not write).
   The healthcheck asks `robots.txt` on 127.0.0.1 and looks at the cleanup's heartbeat file (7); its requests are
   not logged.
2. **What is served.** `GET` and `HEAD` only (anything else 405; a request body is never read; a request with a
   body over 1 KB sent to the mirror itself is answered 413 before the limits, while through SWAG its own 405 or 413
   comes first: the planner's ruling). Every refusal (404, 400, 405, 416) passes the limits as any request does (the
   code review's F1). Exactly these
   paths, by regular expressions written in the config and built in the tests from `grid_tile_name` and
   `gridtiles.res_name`:
   - `/` (the landing page), `/robots.txt` (disallow all), `/v1/datasets.json`;
   - `/v1/tiles/<dataset>/README.md`, with `<dataset>` = `[a-z0-9_-]+`;
   - `/v1/tiles/<dataset>/<product>/<res>m/index.json`, with `<product>` = `[a-z0-9_-]+` and `<res>` =
     `[0-9]+(\.[0-9]+)?` ("1m", "0.5m");
   - `/v1/tiles/<dataset>/<product>/<res>m/<a>_<b>/<i>_<j>.tif`, the four numbers `-?[0-9]+`.
   Every other path, a path ending in `/`, a dot-file, a `.part` file and a symlink: 404. A request with a query
   string: 400. It never answers 401 or 403 (ban rules of proxies count them). The `Server` header says "nginx"
   without a version.
3. **Types and headers.** `image/tiff` for `.tif`, `application/json` for `.json` (sent gzip-compressed when the
   client accepts it: an index is about 1.2 MB), `text/plain; charset=utf-8` for `.md` and `robots.txt`,
   `text/html; charset=utf-8` for the landing page. On every answer: `X-Content-Type-Options: nosniff`,
   `Cross-Origin-Resource-Policy: same-origin`, `X-Robots-Tag: noindex`; no `Access-Control-*` header. `ETag` and
   `Last-Modified` on files; `Cache-Control: no-cache` on `index.json` and `datasets.json`, `max-age=86400` on
   tiles (a dataset may be swapped, U8).
4. **Byte ranges.** One range per request is served (206); a request for several is refused (416; P16).
5. **Limits**, all inside the container, keyed on the visitor's address from `X-Real-IP`, which is believed from
   any sender on the project's own network (P15: only SWAG is there, and SWAG overwrites what a visitor sends):

   | | Visitors | The trusted class (the site's server) |
   | --- | --- | --- |
   | bytes per second per request | 4 MB/s | 16 MB/s |
   | concurrent requests per address | 4 | 4 |
   | concurrent requests of the class together | 8, at most 32 MB/s for all visitors | its own 4, outside the visitors' total; the client's 2 tile connections make 32 MB/s |
   | requests per second per address | 20, burst 40, no queueing | not limited |

   The visitors' numbers are U21 (four installations with two connections each fit; it replaced U19's 5 requests
   at 6 MB/s, which fitted two); the trusted class's numbers are the planner's reading of U19's "higher limit for
   VPS", confirmed by U25. One address can take a whole dataset in a day (Slovakia in about 3.5 h at 16 MB/s): accepted, the
   data are open. Visitors and the site's server together can ask for more than the home uplink carries; the user
   chose it knowing that. Every refusal is a 429 with `Retry-After: 10` (P17).
   The trusted addresses come from `MIRROR_TRUSTED_ADDRESSES` in the project's `.env`: the start script accepts a
   comma-separated list of at most four single IPv4 addresses, writes them into the config in the tmpfs, and
   refuses to start on anything else (a network such as `0.0.0.0/0` would take every visitor out of the total).
   The mirror sends `X-Accel-Buffering: no` on every answer: without it the proxy's default buffering swallows a
   file at once into its temporary files, the mirror's connection ends in milliseconds and the connection caps
   count nothing (wave 0: server, measured once against a stand-in with SWAG's `proxy.conf` lines: the cap was
   passed without the header and held with it).
6. **Timeouts** for a slow visitor (P24): headers 10 s, sending 30 s between two writes, keep-alive 15 s.
7. **The log** (P1, P19, P20), one JSON line per request: time, status, bytes sent, request time, the dataset (the
   first path part after `/v1/tiles/`, only for a request of a served shape and at most 40 characters, else `-`),
   the visitor's address, the limit that refused (or `-`; `rate`, `conn` for both a visitor's limits on concurrent
   requests (U44), `trusted`), and the client's version (the `Find-a-Line/<version>` token of the User-Agent by the
   planner's rule: two or three numbers of at most three digits, optionally `a`, `b`, `rc`, `.dev` or `.post`
   without its number, a local label dropped; `unknown` as it is; else `other`). Never the tile's path, the query or
   the rest of the User-Agent. One file per day (UTC) in `<root>/logs`; a loop started by the start script beside
   the server deletes, every hour, each file whose date is 14 or more days back, then the oldest days' files while
   the folder is above `LOG_CAP_BYTES`, 2 GB (today's file emptied in place when it alone is above it; U45, U48:
   under a flood the log may hold fewer than 14 days, hence the privacy text's "at most", U47), and touches a heartbeat file the healthcheck reads (a dead loop makes the
   container unhealthy). Nothing of the requests goes
   to the container's stdout, so Docker's own log holds no visitor data; the server's error log runs at its
   "critical" level (P18; wave 0: server, a refused symlink wrote the full request at error level).
   This log holds addresses by design. The project's rule is "personal data never in a log"; what the user
   approved is the privacy text that says the server writes the address down, and its 14 days (U13, U14, U22).
   The rule's line in `CLAUDE.md` names this log as its one exception (U26).
8. **What SWAG must do**, in the one file `deploy/mirror/swag/findaline-mirror.subdomain.conf`: answer `<host>`
   (an explicit `server_name`) with SWAG's certificate; pass every request to `files` with SWAG's standard
   `proxy.conf` (it sets `X-Real-IP` itself); refuse every method but `GET` and `HEAD` itself and accept a request
   body of at most 1 KB (SWAG's sample confs allow any size and would write a posted body to SWAG's disk before
   the mirror's 405); set no `proxy_ignore_headers`; write no access log for this host; listen on IPv4 only (no
   AAAA record, section 3: the code review's F4). SWAG's own log would hold
   the tile paths, and its three ban rules that read it then never see the mirror's visitors, which is P2.
9. **The landing page** says what the server is, lists the published datasets with their credits (it reads
   `/v1/datasets.json` in the browser), carries the privacy text (D), and names a contact for abuse and takedown:
   `MIRROR_CONTACT` from `.env`, put into the page by the start script (never in the repository).
10. **For tests and for a mirror on the PC**: `deploy/mirror/compose.test.yaml` adds a stand-in proxy (plain nginx
    with SWAG's `proxy.conf` lines) that publishes `127.0.0.1:<port>`; `compose.yaml` alone never publishes.

**Why nginx** (wave 0: server). Of nginx, Caddy and static-web-server it is the only one with every limit built
in (Caddy: a request rate only through an unofficial plugin and a custom build, no cap on connections found;
static-web-server: no limit per address), and it is the software SWAG and the site's own proxy run. The other
two's cells rest on second-hand quotes: strong for nginx, indicative for them. The prototype passed 74 checks
(content, headers, ranges, refusals, each cap, the forged header, the log, the container's hardening); its
reviewer found the checks that each cap refuses beyond its number, the forged-header and the content checks to
test what they claim, and eight others without a real control (Tests), among them "not refused below the request
rate" and the trusted class's requests really overlapping. Not proven there: the timeouts, the memory and pid
limits, the nosniff header, symlink and traversal refusals against targets that exist outside the root, the
start script with a read-only root, the day in the log file's name, the cleanup's date arithmetic, a Linux host
(it ran on Docker Desktop), the real SWAG.

### Data and interfaces
The service stores only its log. `deploy/mirror/.env.example`: `MIRROR_ROOT` (the host path holding `public` and
`logs`), `MIRROR_SUBNET` (with a default), `MIRROR_TRUSTED_ADDRESSES`, `MIRROR_CONTACT` (required), `MIRROR_MEMORY`.
The limits' numbers are constants of the config in the repo, not settings; so is the log's size bound
(`LOG_CAP_BYTES` in the start script, U45). The door's `publish/.env.example`: `MIRROR_ROOT`, `PUBLISH_KEYS`,
`PUBLISH_ADDRESS`, `PUBLISH_PORT`.

### Files and pairs
New: `deploy/mirror/Dockerfile`, `compose.yaml`, `compose.test.yaml`, `.env.example`, the server's config and
start script, `swag/findaline-mirror.subdomain.conf`, `landing/index.html`, `robots.txt`, `README.md` (install on
a server that runs plain docker compose, the attachment of SWAG to the project's network and how to make it
lasting, the certificate step, the pinned image's update, the check commands, the publishing door), the door's
`publish/` (Dockerfile, `sshd_config`, `gate.sh`, `compose.yaml`, `.env.example`; U32, U33, U89), the check script's
`test/` files; `tests/test_mirror_deploy.py`;
`tests/mirror_check.sh`; a CI job `mirror`. The site's `compose.yaml` services and `tests/test_deploy.py` are not
touched. Pairs: the served patterns ↔ `grid_tile_name`, `res_name` and the publish tool's layout; the log's keys
↔ `mirror_publish.py stats` ↔ the privacy texts (D); the limits ↔ the client's entries (C.6; the test is wave
2's `tests/test_mirror_pairs.py`).

### Tests
- `tests/test_mirror_deploy.py` (static, offline): the hardening list of
  `test_monitoring.py::test_compose_hardening`, written out again here (no shared helper), with the digest looked
  for in the Dockerfile (its `ARG` or its `FROM`); no `ports` in `compose.yaml`; `public` read-only; the one network internal; the
  SWAG conf's lines of 8 (the two methods only, the 1 KB body, no access log, no `proxy_ignore_headers`).
- `tests/mirror_check.sh` (CI job `mirror`, Docker, with `compose.test.yaml` and a fixture tree): one line
  PASS/FAIL per behaviour of 2-7 and 9, among them: each limit refusing beyond its number and not below; the
  trusted class at its number and one beyond, with a file large enough that the requests overlap; the trusted
  class not counted in the visitors' total; a forged address header from a visitor not believed; a bad
  `MIRROR_TRUSTED_ADDRESSES` (a network, a fifth address, a word) refusing to start; names built by
  `grid_tile_name` served, also negative and "0.5m"; the log line's keys exactly, read from the lines of the very
  requests just sent (a marker in the User-Agent's version); files dated 13, 14 and 15 days back after the
  cleanup ran (kept, gone, gone); no request line on stdout.
- **Every check has its control.** The prototype's review found checks that pass with the behaviour broken; the
  build's script must not repeat them: a symlink whose target exists outside the served root; a traversal path
  that would resolve to an existing file outside it; the `Server` header asked of the mirror itself; the request
  rate without a burst hiding the boundary; `HEAD` with its status and an empty body; "no way out" beside a
  control container on an ordinary network that does reach the address. The script's self-test runs the checks
  against a second config with each behaviour switched off and expects FAIL.
- `mirror_check.sh --live https://<host>`: what needs no fixture, against the real mirror through SWAG, run from
  the PC. It must show that the real SWAG honours `X-Accel-Buffering` (the per-address cap refuses a request while
  slow downloads are held open) and that SWAG refuses a `POST` itself.

### Acceptance
Every line of `mirror_check.sh` PASS in CI and `--live`; on the home server the README's commands show a read-only
root, no capability, no published port, no route out, and no log file older than 14 days.

### Risks
- **Adding a name to SWAG's certificate is not a quiet step** (wave 0: server; SWAG's certificate init script,
  read by the worker and by its reviewer). When any of ten settings changed (the names among them, and the
  staging switch too) the script revokes the existing certificate (a failed revoke is ignored), deletes the
  certificate folders, saves the new settings, and asks for a new certificate; where SWAG validates over HTTP it
  uses the validation's own listener on port 80; when no certificate results it prints an error and waits
  forever. Inferred, not in the script's text: SWAG's web server is not running during this, so every site behind
  SWAG is down for that time, and stays down after a failed validation until a restart succeeds (a restart asks
  again without a second revoke). The README makes it a planned step in a maintenance stop: the new name's DNS
  record in place and answering first, the validation's way in checked from outside. **No trial with SWAG's
  staging switch on a live SWAG**: switching it on is itself one of the ten changes and would revoke and delete
  the production certificate, and switching back would do it again.
- SWAG's second network: a recreated SWAG container (an update) drops it, and the mirror is unreachable until it
  is attached again: an outage, never an exposure (SWAG answers 502, its other sites go on). The README attaches it
  by a command by default, again after every SWAG update, with a check; the lasting way (an external network in
  SWAG's own compose file) is described with its risk, SWAG and its sites not starting while that network is
  missing (U42).
- SWAG's connections are shared by all its sites, and a proxied request takes two; the mirror's totals (8 visitors
  and 4 trusted) are far below SWAG's default of 1024 per worker (wave 0: server, from SWAG's base config).
- A pinned image gets no automatic security updates, and a compose plugin skips digest-pinned images in its
  update checks: the digest is edited by hand, a monthly item in the docs (D.4).
- The public folder, staging, trash and the logs must lie on one file system and on a path that does not pass a
  FUSE layer (renames must be atomic, and many small files served fast), on storage that never spins down (the
  client's start check allows 30 s). The README says so.

### Needs the user's word
M2's result (section 11, step 3; given: the numbers kept, U94). E2 (the publishing account) was answered by U27, U32 and U33.

## 5. Solution B: the address contract and the publish tool

### Decision
U1, U5, U8, U10, U11, U12, U20; P21, P22, P23, P27.

### Behaviour: the address contract
- The paths of A.2 under `https://<host>`: the mirror folder's layout (`tools/sk_tiles.py`,
  `tools/mirror_tiles.py`) below `/v1/tiles/`.
- `/v1/datasets.json`: `{"version": 1, "generated": <UTC>, "datasets": [{"id", "title", "licence", "attribution",
  "source", "products": [{"path": "slovakia/dmr5/1m", "tiles": n, "bytes": b, "index_sha256": h}]}]}`. `id` is the
  mirror folder; `title`, `licence` and `source` (the page that states the basis) come from the dataset's
  `PUBLISHABLE` row, `attribution` from the catalogue (P22); `products` are all folders with an `index.json`
  (the averaged ones too), `tiles` the tiles with data, `bytes` those tiles plus the index, both taken from the
  server's copy. The client's start check reads it (C.3, U50): a product is published when its mirror folder is a
  `datasets[].products[].path` (the pair: `tests/test_mirror_pairs.py`
  `test_the_clients_reading_of_the_list_the_tool_writes`).
- `/v1/cubes/` and `/v1/cache/` are reserved and answer 404.
- A later change of the layout gets `/v2/`; `/v1/` keeps answering as long as releases that know only it are in
  use, then 410.
- **A recut with other values gets a new edition** (U24, "new folder"): a new folder name in the catalogue for
  the mirror path and for the cache, as the cache's folders already carry the edition. Installations keep
  downloaded tiles in their cache for good, so a swap in place would leave every installation that already
  holds tiles of an area with the old ones, and results would differ between installations without a sign. The
  old edition stays published while releases that name it are in use. Only a re-encoding with the same values
  is swapped in place (U8); a client then takes the index again after a mismatch. `publish` cannot tell the two
  apart: it refuses to replace a published dataset unless `--same-values` is given, and the README says what
  that promises.

### Behaviour: `tools/mirror_publish.py` (run on the PC)
- `verify <folder or remote>`: for every `index.json` below it: every listed tile exists and has its sha256, no
  tile file that the index does not list, not `partial`. On a folder the tool hashes itself; on an rclone remote
  the server hashes (`rclone checksum sha256` against a SUM file made from the indexes). Exit code 1 and the list
  of faults otherwise. An index that is not what the cutting tools write (its keys, the sha256 as 64 hex digits,
  `"block"` present and 10, the client's `BLOCK`) is a fault (the planner's ruling, fix round 1).
- `publish <dataset> --to <remote>:<root>`: refuses when the dataset has no approved row in `PUBLISHABLE`, when
  `verify` fails on the master (hashed on every publish and every resume, U36), or when a resolution the catalogue
  declares for the source (`GridTiles(averaged=)`) has no folder (P12). Then:
  1. takes the lock (`<root>/staging/.lock`, a file that names the PC, the time, the command and a token of the run,
     read back after writing; a second publish or unpublish refuses while it exists; `--break-lock` after a crash).
     Under the lock it refuses, the lock released: a server whose sha256 of the lock file is not the tool's own
     (U35; not with `--read-back`), a dataset already published unless `--same-values`, and a `<root>` with less
     free space than the bytes not staged yet plus 10 GB (rclone's free blocks, which on Linux include root's
     reserve);
  2. copies exactly the files the indexes list, the indexes and nothing else into `<root>/staging/<dataset>/`
     (`rclone copy --files-from`; a rerun skips what is there), and writes the card `README.md` there from the
     tool's card text for the dataset (P21); a master's own `README.md` that is missing or differs from that
     card is noted before the copy, never refused (U57; `verify` of a master folder notes it too);
  3. verifies the staged copy on the server against the master's indexes;
  4. moves `<root>/public/v1/tiles/<dataset>` to `<root>/trash/<dataset>-<UTC>` if it exists, then staging to
     `<root>/public/v1/tiles/<dataset>` (`rclone moveto`, a rename on the server), and after each move checks
     that the source is gone and the target's file count is the expected one (a move that fell back to copying
     would show here; the tool then stops with the dataset in whichever place is complete). The README requires one
     mount for `<root>`, and the door refuses a rename it cannot do instead of copying (U34);
  5. writes `datasets.json` from the server's copy of every published dataset (through a name outside the served
     patterns and a rename), releases the lock.
  A folder with content cannot be replaced by one rename, so between the two moves of 4 the dataset is absent for
  a moment; the client's rule covers it (C.2).
- `unpublish <dataset> --to ...`: the dataset to trash, `datasets.json` rewritten; one command (a takedown).
- `clean --to ... [--keep-days 7]`: removes trash older than that (P27).
- `stats --from <remote>:<root>/logs`: requests and bytes per day and dataset, refusals per limit, client versions
  (by the server's version rule, A.7: `client_version`); its output never holds an address.
- rclone (U20): found on `PATH` or by `FINDALINE_RCLONE`; the tool refuses a version below 1.76 and a remote that
  does not report sha256 among its hashes, and falls back to hashing by reading back
  (`rclone checksum --download`) only with `--read-back` (E1). The remote (an SFTP one with the server's
  `sha256sum` as its hash command) is set up once in the user's own rclone config, which holds the address and
  the key; the tool never prints rclone's raw output (it may name the remote's host and user: U16), only its own
  lines and counts.
- **`PUBLISHABLE`**, in `tools/mirror_publish.py`, one row per dataset; a row with an empty field or without
  `approved` is refused: `dataset`, `source_id` (the catalogue's source, for the attribution), `title`,
  `basis_kind` (licence, metadata statement, written permission), `licence`, `licence_url`, `basis_url`,
  `basis_quote` (the original sentence), `basis_checked` (date), `changes` (per product, the averaging too),
  `not_endorsed` (the sentence), `notes`, `approved` (the user's word and its date). A field without a fact holds
  the word "none" (P23). The rows of today, six (wave 0: publish, quotes dated 2026-11-15; the islets'
  2026-11-17), each with the user's approval it rests on:

  | Dataset | Basis | Notes for the row |
  | --- | --- | --- |
  | Slovakia (DMR 5.0, DMP 1.0) | CC BY 4.0 (the owner's terms: "Autor ÚGKK SR / Licencia CC-BY 4.0"); approved by U31 | the card's "Changes made" must name the 2 m and 5 m averaging (today only under "Layout") |
  | Valle d'Aosta (DTM 2005/2008) | CC BY 4.0 by the region's licence PDF the catalogue already records ("distribuire ... Modificare ... anche commerciale"); approved by U12 | a second PDF on the same server says CC BY 2.5 Italia, and its own sentence does not name distributing |
  | Madeira (DTM 2 m) | a metadata statement, **weak**: the national catalogue's record says "No conditions apply"; `licence` and `licence_url` "none"; approved by U11 | against, all in the regional order 36/2022: obtaining the owner's products "is subject to payment", its price table lists "MDT 2 m (folha)" at 42 €, use licences are to be published by the owner (not found), commercial use is named only for the region's own services; whether today's free file is that priced product is not established. `unpublish` answers an objection |
  | Porto Santo (DTM 5 m) | a metadata statement, **weak**: the same national catalogue record and sentences as Madeira's (the record of the 5 m model of every island, "No conditions apply"); `licence` and `licence_url` "none"; approved by U55 (2026-11-17) | against, sharper than for Madeira: the regional order 36/2022's price table lists "MDT 5 m (Porto Santo)" at 500 €; whether the record's free file is that priced product is not established. The card names the float64 values stored as float32 (U56). `unpublish` answers an objection |
  | The Desertas (DTM 5 m) | as Porto Santo's; approved by U55 (2026-11-17) | against: the same order's "MDT 5 m (folha)" at 37 € a sheet. The file's reference-system label (EPSG:3061) is replaced by the system its coast fits (PTRA08, EPSG:5016), nothing reprojected; the card names it (U56) |
  | The Selvagens (DTM 5 m) | as Porto Santo's; approved by U55 (2026-11-17) | against: the same order's "MDT 5 m (folha)" at 37 € a sheet |

  Not rows of the tool: Wallonia (batch 6; CC BY 4.0, "Il peut publier les données et l'œuvre dérivée à condition de citer les sources"; the terrain model's record also asks for "mention explicite des modifications"), its row written with batch 6; Hong Kong (batch 6; **none found**: no sentence allows a changed copy on the internet), no row: not publishable (section 11, step 7).

Compared and not chosen for the transport: the tool's own tar over SSH with `sha256sum -c` (no new program; the
planner's recommendation), a share with read-back, robocopy and rsync (no sha256).

### Data and interfaces
The public folder is new stored data on the home server, made by `publish`; it is not the app's data and has no
migration. The master's layout does not change. rclone is an external program, not a Python dependency:
`uv.lock` does not change; before it is used, its 1.76 docs are read for every command above (the project's rule
for a dependency), and these are proven first on a throw-away SFTP server: sha256 among the SFTP backend's
hashes with a hash command, `moveto` as a rename, `about` for free space, `--files-from` with nested paths, and
reading the server's copy for `datasets.json` and `verify` (a listing with sizes, an index's content and hash).
None of rclone's behaviour above was tried in the research; where a command does not do what this section
assumes, the builder reports it before going on.

### Files and pairs
New: `tools/mirror_publish.py`, `tests/test_mirror_publish.py`. Changed: the card texts only, `CARD` in
`tools/sk_tiles.py` and `MADEIRA_CARD`, `AOSTA_CARD` in `tools/mirror_tiles.py` (and the tests that pin them).
Pairs: `PUBLISHABLE`'s datasets ↔ `tools/mirror_tiles.py` `DATASETS` plus Slovakia; `source_id` ↔ the catalogue;
the layout ↔ `grid_tile_name`; the resolutions required ↔ `GridTiles(averaged=)`.

### Tests
On fixture mirrors in `tmp_path`, with a folder as the rclone remote (rclone's local backend; skipped where
`rclone` is not installed, and CI installs the tested version in its Linux and Windows jobs, pinned with its
sha256): an unlisted, an unapproved, a partial and a damaged dataset and one lacking a declared resolution are
each refused with the reason; a stray `.part` beside the tiles is not copied; an interrupted publish (rclone
stopped after n files by a wrapper) resumes and the public tree never held a partial dataset (asserted after
every step); a staged file changed after the copy is caught before any move; a second publish refuses on the
lock; `unpublish` leaves no file of the dataset under `public` and no entry in `datasets.json`; `verify` finds a
flipped byte, a missing tile and an unlisted file; `datasets.json`'s `index_sha256` equals the master's; `stats`
on a recorded log prints no address; a missing or too old `rclone` is refused with the text; no line of the
tool's output holds the remote's name.

### Acceptance
After each real publish: `verify` on the remote passes, every served `index.json` has the sha256 of the master's
(`mirror_check.sh --live` compares through HTTPS), `datasets.json` lists the dataset.

### Risks
- rclone's behaviour on a refused rename is not established (E1): step 4's checks are the guard.
- The owner of a dataset objects: `unpublish`, and the row's `approved` is withdrawn.

### Needs the user's word
Each dataset's first publication (section 11).

## 6. Solution C: the client

### Decision
U4, U6, U7, U8; P4, P5, P8-P12, P24, P25, P28.

### Behaviour
1. **Where the tiles come from.** `TileBases.bases()`: the local folder when `FINDALINE_MIRROR` is set and holds
   the dataset (unchanged), then `<MIRROR_URL>/v1/tiles/<mirror path>` (e.g. `.../v1/tiles/slovakia/dmr5/1m`),
   then the catalogue's `urls` (still empty). `MIRROR_URL` is the origin only (`https://<host>`), a constant in
   `sources/readers/tilebases.py`, overridden by the environment's `FINDALINE_MIRROR_URL`; `off` (in any case) or
   an empty value turns the mirror off (U37: Windows deletes an empty variable, and the default would be used); any
   other value that is not an `http://` or `https://` address, or one with a user or a password, is an error
   (`MirrorUrlError`), refused at every search's start. The text for "no base at all" names both settings.
2. **Index-driven over HTTP**, the rules of a local folder: a tile whose key is null, or beyond the extent of a
   complete index, is "no data" without a request; an index that says `partial` or lacks the key inside its
   extent sends the tile to the next base; a listed tile is downloaded and its sha256 compared **before** the
   file is written into the cache or opened by a raster library. A 404 for a listed tile is an error, never "no
   data", and writes no "missing" row. On a 404 of a listed tile, a 404 of the index or a mismatch, the client
   waits `net`'s usual pause (`net._sleep`), fetches the index again once and the tile once more (this heals a
   dataset being swapped, B); if that fails the next base is tried, and after the last base the search fails
   with a text naming the tile and the data server by its host only, with the kind of failure in fixed words
   ("Could not download <layer> tile <name>: the data server at <host> does not answer (<kind>)", or "is busy
   (HTTP 429)" after a 429; U40). The kinds (`tilebases._failure_kind`): "HTTP <status>", "its answer was not the
   data" (a 200 that was not), "its certificate was refused", "no answer in time", "the connection broke",
   "waited too long for its turn" (the host's rate turn) and "no answer". Every text of a failure names the data
   server by its host alone, never its address, a path or a query (U40): "index.json is not on the server at
   <host> (HTTP 404) ...", "the tile is not on the server at <host> ...", "the data server at <host> does not
   answer (<kind>)". An index is fetched when a download or an estimate (7) first needs it (under a lock per base:
   eight threads download), is kept in memory for 300 s (P11) and then taken again; the start check never asks it
   (3). Index requests take the host's rate turn; tile requests take the host's slot as today.
3. **The start check** (U6, U7, P10). `unavailable()` stays as it is today: no request, and it knows only "no
   base at all" (a wrong setting raises `MirrorUrlError` there, C.1). The question "does the mirror answer" is a second one, `reach`, asked only where a caller
   passes `reach=True`; everywhere else the default is off, so nothing new can ask by accident.
   When the local folder comes first (it holds the dataset), `reach` answers without a request and nothing falls
   back (U38); a folder without the averaged tiles then reads them from the server with no start check, and a
   server that does not answer fails the phase (the mixed case).
   `reach` asks the data server for its list of datasets, `/v1/datasets.json` (written by `mirror_publish.py`
   after every publish and unpublish, B), never a product's index: one request for all products of a process,
   `timeout=(10, 20)` (10 s to connect, 20 s for each read), two attempts, kept in memory for 300 s as an index
   is, and fetched once for the threads that wait for it (they take its answer, a failure too).
   - **Listed**: a product whose mirror folder is a `path` of the list answers.
   - **Not listed** (U50): the product is not published there, and the source is unavailable as it was before
     the mirror, with "<layer>: <product's folder> is not published on the data server at <host>, and no local
     copy is set up":
     `--source auto` takes the next source of the place, a named source is an error. Nothing is remembered as the
     server's failure, and a dataset starts working by itself once it is published (at the latest 300 s later,
     when the kept list is taken again).
   - **No list** ("does not answer"): no HTTP answer, any 5xx (a 503 too: the mirror itself refuses only with 429,
     so a 503 comes from the proxy in front and means the mirror behind it is not reachable), a 404 of the list (a
     server that publishes nothing has none) or a list that cannot be read. A failure is remembered for 60 s,
     and only for later `reach` calls (so a quick lane that lives long neither repeats the wait at every estimate
     nor keeps an outage). The source counts as unavailable with "<layer>: the data copy at <host> does not
     answer (<detail>)", also when the cache holds every tile (U7): `--source auto` takes the next source as
     today, a source named by `--source` is an error as today.
   - **A 429**: an answer at once (the start check stops at the first 429 with no further attempt or pause,
     `net._get(stop_on=)`; U39), and the product counts as listed; the download's own retries deal with the busy
     server.
   A listed product whose index is missing or cannot be read fails its phase at the index (U6's "fail in the
   middle", as an index that disappears during a search; after a 429 an unlisted product the same). Another
   remote base (a catalogue URL, none today) is asked for its index as before. Where the catalogue gives a
   region's next source (Madeira's for its islets), `auto` takes it, as `main` does with a local copy holding
   Madeira but no islet: the run names Madeira's source and the gap filling fills the islet.
   Who passes `reach=True`, and nobody else:
   - **the first planning of a search**: the command line's search, and a web job's first phase. The reason of a
     fall-back is in that phase's messages, which the page shows.
   - **Estimates** in the worker's quick lane, so an estimate says what a search would do.
   - **A country run's main process**, once, for the country's own source: in `country.run` between the setup and
     the band plans (never inside `band_plan`, which the workers share). Down is an error and the run does not
     start, as an unavailable own source already stops it today; that holds for a resume whose tiles are all
     cached too (a country counted on the fall-back's data would be useless, and the rule stays one rule).
   - **The probe** (`findaline.py sources check`): its row for these layers shows the start check's state and
     reads the first tile the product's index lists with data; a product the list does not name is a row with
     that note, not a failure.
   Who never does:
   - **Later phases of the same job never choose again**: `plan_search` gets the first phase's source as an
     argument of its own (the job's stored `source`, which the first phase already writes and which holds
     "europe" after a fall-back). `params.source` stays as the user gave it, so the search's hash, a tiled
     area's resume and `run.json` do not change. The argument is ignored when an elevation file is given, and a
     job without a stored source chooses as today, without `reach`. The later phase's "Data:" line names the
     source as "chosen when the search started" (the two readers of that line, `tests/regression.py` and
     `tools/obstacle_study.py`, still match it); the reason itself is not stored (no migration). A tile the phase still needs is
     downloaded then; if the mirror does not answer, the phase fails (U6's "in the middle") and running it again
     resumes from the cache. This is the part to trace first; its review runs at high effort.
   - **A finished run's profiles and 3D views** (they plan through `plan_search` at `search.py:2569`, `:2648` and
     `:2781` and choose the run's source by name at `:2633` and `:2768`): they work from the cache while the
     mirror is down, and a remembered failure never touches them.
   - **Neighbours** (`filling.py:1325`, `country.py:1454`): no check of their own. A neighbour whose download
     fails is skipped by the code as it is today (`filling.py:1335`: "Gaps at the border not filled from ...",
     after `net._get`'s attempts), which is P5.
   - **A country run's workers**: they plan with `reach` off. After a failed prefetch "the tiles download what
     they need", as today (`country.py:1538`).
   - **The web process**: it reads names, credits and orthophoto addresses of the catalogue only; a test asserts
     that building the form's schema, the about page, the privacy page and `ortho_origins` makes no request.
4. **Fail in the middle.** A tile that cannot be downloaded after `net._get`'s attempts (429 and 503 with its
   longer back-off) ends the phase with the existing "Could not download ..." text, naming the data server by its
   host (C.2); running it again resumes from the cache. A refusal because the mirror is full (A.5's totals: a fifth installation at the same time) is
   such a failure (P8).
5. **Averaged resolutions** (Slovakia's 2 m, 5 m) are available over HTTP whenever a remote base is set, as today
   (P12): the choice must be the same in every phase and process, so it cannot depend on a request. `publish`
   guarantees the folders; an averaged index that is missing is an error with a clear text, never a silent
   switch to the 1 m tiles (about 15 times the bytes). A local folder that holds the 1 m tiles but not the
   averaged ones then reads the averaged ones from the mirror: the values are the same (an averaged tile is the
   block mean of the native ones, byte for byte), it only costs downloads.
6. **Good manners** (P25). `net.HOST_SLOTS_OF` gets the mirror's host with 2 connections and `net.HOST_RATES_OF`
   with 600 requests a minute: half a visitor's per-address numbers, so two installations behind one address
   fit. A data server under another address (a LAN, the test stack) takes the same manners (`net.LIMITS_AS`,
   `net.limits_host`). Index requests take no slot, so an installation can have 2 tiles and an index or two under way: within
   the 4 requests an address may have at once, for visitors and for the trusted class alike. Accepted: several
   processes of one machine fetching indexes at the same moment can pass 4, and a request refused three times
   then fails its phase, which is run again (rare: an index is fetched once per process and 300 s). Requests to the
   mirror pass `timeout=(10, 300)` (today one 300 s value serves as both: a dead home server would cost 3 x
   300 s a tile).
7. **Estimates.** For a remote base `GridTiles.estimate` uses the product's index: the kept one, or fetched when
   tiles are to be downloaded (`TileBases.index_for_estimate`; the start check keeps none), so null tiles are not
   counted. That fetch has the start check's manners (`timeout=(10, 20)`, two attempts, a 429 ending it at once),
   so it waits at most `ESTIMATE_WAIT_MAX`, 96 s, below the quick lane's 120 s; when it fails it counts every
   tile of the grid that is not cached, an upper bound, and never
   fails. A local folder's estimate stays as it is today.
8. **Tests and tools.** `tests/conftest.py` sets `FINDALINE_MIRROR_URL` to `off` for every test (U37).
   `tests/regression.py` sets it to `off` too unless `--mirror-url <address>` is given; an entry with
   `needs_path` runs when the folder exists (as today) or when `--mirror-url` is given. Tools that are online by
   nature (`check_source`, the studies) use the default address.

### Data and interfaces
None stored: the index lives in memory, the cache's layout, paths and rows are as today ("Stored data: none").
The tiles the VPS's cache already holds stay valid (the same values; its 2 m and 5 m ones in the older lossless
encoding, compared bit for bit when the master was rewritten). `FINDALINE_MIRROR_URL` (README's options, the two
env examples). New: `Layer.reach()` and `Reader.reach()` (default: None, "answers"), `ComposedLayer.reach` (its
reader's), `ResolutionBases.reach` (the native reader's), `TileBases.reach`; `choose.source_unreachable(source)`
(the layers' `reach`); `choose_source(..., reach=False)`, which asks it after `source_unavailable` where today's
three lines ask that (`choose.py:84, 97, 100`); `search.plan_search(..., reach=False, source_id=None)`;
`net._get` gets `binary_types=("json",)` from the index's caller, a `retries=` keyword (default as today), a
`stop_on=` tuple of statuses that end the attempts at once (the start check's 429, U39), and the timeout as a tuple
(no change for other callers). Also new: `tilebases.MirrorUrlError`, `OFF`, `IndexMissing`, `IndexUnreadable` (an
index of another shape or another `"block"` than `BLOCK`, treated as a mismatch), `net.LIMITS_AS` and
`net.limits_host` (C.6), `net.TurnTimeout` (a rate turn not had in time); for U50 `tilebases.DATASETS_PATH`
(`v1/datasets.json`), `tilebases.NotPublished` (reach's answer for an unlisted product: a text, not a failure),
`tilebases._published(origin)` (the kept list of an origin's product paths) and `_checked_list` (the paths of a
`datasets.json`, else `IndexUnreadable`), `TileBases.index_for_estimate()` (C.7). `source_unavailable` and its other callers
(`filling.py:1325`, `country.py:1454`, `probe.py:600`) do not change, except that the probe also asks `reach`.

### Files and pairs
`sources/readers/tilebases.py`, `sources/layers/gridtiles.py`, `sources/composed.py`, `sources/layer.py`,
`sources/choose.py`, `country.py` (the main process's one reach), `search.py` (`plan_search`'s two new arguments
and the call of `choose_source`), `findaline.py` (the command line's search passes `reach=True`), `jobs.py` (only
what passes `reach=True` in the first phase and the quick lane's estimate, and the stored source to the later
phase), `sources/probe.py`, `sources/net.py`, the texts of the sources that read the mirror in the catalogue ("from the local
mirror" becomes "from the project's data server or a local copy") and with them the generated table of
`README.md` (by `tools/source_docs.py`, which C changes only if the texts need it; the rest of README is wave
2's); tests: `conftest.py`, `http_server.py` (a list of the requests it served, if it has none), `regression.py`,
`regression.json` (only if a `needs_*` entry changes), `test_regression_needs.py`, `test_sources.py`,
`test_madeira_aosta.py`, `test_rates.py` (its two pinned dicts, and `test_catalogue_hosts_named` reading
`tilebases.py` too), `test_probe.py`, a new `tests/test_mirror_client.py`.
Pairs of `.claude/rules/sources.md` and `providers.md` to keep: the patched names (`net._get`, `net._sleep`
called and patched through their module); every request path to a rated host takes its turn; a new numeric limit
goes into the dicts with its source; the mirror's `origin` ↔ `GridTiles(origin=)`; the client's reading of
`datasets.json` ↔ `mirror_publish.write_datasets`' format (U50; `.claude/rules/mirror.md`).

### Tests
With `tests/http_server.py` serving a fixture mirror: the same cache files as from the folder, byte for byte;
null and beyond-extent tiles make no request (the server's request list is asserted); 404 of a listed tile is an
error and leaves no row and no file; a tile, then an index, with a wrong hash; a swap between index and tile
(old index, new tiles) heals by one refetch; the index 404 for a moment heals after the pause; `partial` goes to
the next base; the server down at the first planning: unreachable with the reason within the timeouts (the
test's clock is the timeout's value, never a wait), `auto` falls back, a named source raises; a 429 at the
list is "answers" (the product counts as listed; an unlisted product then fails its phase with no file and no
row) and a 503 is "does not answer"; the list asked once for two products and by eight threads, and its failure
taken by the threads that wait; an unlisted product under `auto` (passed over, the next source, nothing
remembered, no index request) and named (refused with the text), also the catalogue's islet on a server
publishing only Madeira; the list's 404, 503, no answer, and a list that is not `datasets.json`; the list kept
300 s and a dataset published meanwhile starting by itself; a later phase asking no list; the estimate after a
start check with the index's numbers (the upper bound when its index fails); the probe's row of an unlisted
product (not a failure); each failure text as the public site stores it holding the host alone; a remembered
failure expires after 60 s and an index after 300 s of the patched clock; a later phase with the mirror down and the tiles cached completes on the first phase's source, with the
search's hash and `run.json`'s `source` as the user gave it; a job that fell back in its first phase computes on
the fall-back's source although the mirror is back; down in the middle: the phase's error, and a second run
completes from the cache; a finished run's profile and 3D patch with the mirror down and the tiles cached, also
within 60 s of a failed estimate in the same process; an averaged grid over HTTP reads the averaged tiles, and
without their index fails clearly; eight threads fetch the index once; `FINDALINE_MIRROR_URL` `off` or empty: no
request at all; the local folder wins; a neighbour whose mirror is down is skipped with today's text; a country run's
main process reaches once, stops when its own source does not answer, and its workers never reach; the web
process's pages make no request.

### Acceptance
- Results pinned: regression rows R13, R21, R34, R80, R81, R86, R87 and R88 from an empty cache with
  `--mirror-url` (the mirror's
  test stack on the PC, serving a copy on a local disk of exactly the tiles those rows need with their indexes:
  Docker Desktop showed the mapped network drive as empty) give the counts and the `lines.csv` sha256 of the
  baseline. No baseline changes. The copy is made by running those rows once from the folder into an empty
  scratch cache and copying, from the master, the tiles whose names that cache then holds, with every
  `index.json` of their product folders unchanged (tiles an index lists but the copy lacks are never asked for
  by these rows).
- One Slovak search on a 5 m grid over HTTP gives the `lines.csv` sha256 of the same search from the folder (no
  regression row covers an averaged grid over HTTP).
- `findaline.py sources check slovakia madeira aosta_valley` and `tools/check_source.py` for the three sources on
  an empty scratch cache pass over HTTP.
- Full pytest green on the final tree.

### Risks
- A release with the mirror's address must never precede the index-driven client: both arrive in one commit
  (every release so far has empty URL lists, so no old client can meet the mirror).
- A short outage at a search's start gives a coarser result (U7), and border strips depend on the mirror's state
  at that moment (P5): the run records both.
- When the mirror's visitor total is full (four installations downloading at once), a further installation's
  phase fails after about a minute of retries (an estimate from `net._get`'s pauses; P8) and is run again.
- Index traffic: about 1.2 MB per Slovak product and process before compression, a few percent of a small
  search; A.3's gzip cuts it. The start check adds one small request per process (the list, kept 300 s); an
  estimate that has tiles to download takes the product's index, which the download then reuses.
- A dataset cut but not yet published (U50) is unavailable without a local copy until it is published; the next
  source of the place takes over (for an islet Madeira's when Madeira's is available, by the catalogue's order).

### Needs the user's word
Nothing before the build; the numbers of 3 and 6 were confirmed after M2 (U94).

## 7. Solution D: the site's switch, the monitoring and the docs

### Decision
U4, U13, U15, U16; P3, P26.

### Behaviour
1. **The switch.** On the VPS `FINDALINE_MIRROR_DIR` is taken out of `.env`; the worker's `/mirror` is then the
   empty volume and the worker downloads from the mirror. `/srv/findaline-mirror` is removed only on the user's
   word (section 11). The comments at the compose file's mirror mount and in `.env.example` say that a local copy
   is now optional.
2. **The check.** Telegraf on the VPS asks `https://<host>/v1/datasets.json` every minute (status, time, that the
   body names `"datasets"`) and reads the certificate's expiry of `<host>`. The address stands in
   `telegraf.conf` (U15), equal to the client's `MIRROR_URL` (a test). Both inputs carry names of their own
   (`mirror_http_response`, `mirror_x509_cert`) so that the site's rules, which group by host, never see them.
   CI's monitoring job runs the real `telegraf.conf` and so asks the mirror a few times per run: accepted.
3. **The rules** (to the site's contact point; ids the next free ones of the site's group, titles starting with
   the id as the pinned set requires): "Mirror down", no good answer for 45 minutes (P26: short maintenance stops
   of the home server are normal and must not page), written so that a vanished series alerts too, as the
   existing "source silent" rule is, and as one alert instance (one series without labels: each host's best
   result code of the last 3 minutes, then the worst host; 1 when no samples came), so that one wait runs through a
   gap of the samples in an outage (the code review's S1); one good answer within 3 minutes resets the wait; "Mirror certificate", as the site's. One row on the *Site* dashboard: up,
   answer time, certificate days; the *Overview* has two tiles of them beside the site's (its test asks a tile
   for every row with a rule). The VPS's own traffic to the mirror shows in the existing per-host counts.
4. **The monthly item** in `docs/deployment.md`: check the mirror's base image for a newer digest (the door's
   too), run `mirror_publish.py stats` and `clean`; after every SWAG update, attach SWAG to the mirror's network
   again and run the README's check (U42). Nothing reminds automatically.
5. **The privacy page** (`web.privacy_page`, whose texts are in `web.py` itself) gets one entry, always shown,
   pinned in the privacy test of `tests/test_public.py`.
6. **The docs**: `docs/deployment.md` (a new section for the mirror machine; that file's section 10, the VPS's
   copy, becomes optional and its section 16 is brought in line), `README.md` (the option
   `FINDALINE_MIRROR_URL`, publishing with rclone, the privacy note; not its generated table, which C made),
   `setup-for-regular-folk.md` (these sources work with no setup), `docs/data-sources.md`,
   `docs/monitoring.md` (the new rows), `docs/roadmap.md` (2.3 and the parked items of section 13 here),
   `docs/code-map/*`, the rules `deploy.md`, `providers.md`, `sources.md`, `metrics.md`, `web-app.md` (the new
   pairs named in A, B, C and below), and `CLAUDE.md`'s line on personal data in logs (A.7, U26).

### Privacy texts (approved by the user on 2026-11-15: U13 "yes", U22 "a"; the last two sentences as changed on 2026-11-16: U46, U47; used word for word)
A visitor of the public site never reaches the mirror: the site's server asks it.
- Privacy page, a new entry with its title and its text as the page's other entries have them. Title:
  "Elevation data from the project's data server". Text: "The elevation data of some regions come from a data
  server run by the project. This site's server asks it for them; your browser and your address never reach it."
- README and the mirror's landing page: "An installation that downloads from the project's data server shows it
  its address and which tiles it asks for. The server writes down the time, the address, the dataset (not the
  tile), the size, whether the request was served or refused, how long it took, and the Find-a-Line version of
  each request. It keeps this for at most 14 days, to hold the service within its limits, and uses it for nothing
  else. To never contact the data server, set `FINDALINE_MIRROR_URL` to `off`; the regions it serves then use
  coarser data."
The pair to keep: these texts ↔ the log's keys and its 14 days (A.7); another key or period changes the texts,
with the user's yes. (The log's status and "the limit that refused" are "whether the request was served or
refused"; the log has no other key than the sentence names.)

### Data and interfaces
No stored data changes on the site. `findaline.env.example` gains the commented `FINDALINE_MIRROR_URL`.

### Files and pairs
`deploy/monitoring/telegraf.conf`, `grafana/provisioning/alerting/rules.yaml`, the *Site* and *Overview* dashboards,
`tests/test_monitoring.py` (its pinned sets of rules, inputs and tags), a new `tests/test_mirror_pairs.py` (the
server's limits against the client's entries; Telegraf's address against `MIRROR_URL`; the SWAG conf's and the
server config's host) and the one line of `tests/conftest.py` that exempts that module from the emptying of the
rate table (the fixture exempts by module name), `web.py` (`privacy_page` only) and
the privacy test in `tests/test_public.py`, `.env.example`, `findaline.env.example`, the comment at the mirror
mount in `compose.yaml`, the step that installs rclone in the test jobs of `.github/workflows/ci.yml`, the docs
and rules of 6. The pairs of `.claude/rules/metrics.md` (a new field changes telegraf.conf, the panels and the
rules together).

### Tests and acceptance
`tests/test_monitoring.py` and `tests/test_mirror_pairs.py` green; on the Grafana test stack "Mirror down" fires
when the local mirror stack is stopped (with the wait shortened for the trial) and clears when it is back, and
the site's own rules stay quiet meanwhile.

### Risks
The VPS's update installs the new Telegraf inputs before the mirror answers under `<host>`: until then "Mirror
down" would fire after its wait. The rollout publishes the mirror first (section 11).

### Needs the user's word
Nothing before the build.

## 8. Security and misuse

| # | Threat or misuse | What the design does | What stays |
| --- | --- | --- | --- |
| S1 | One address scrapes everything, again and again | A.5: connections, rate and requests per address | a patient scraper gets the open data once: allowed by their licences |
| S2 | Many addresses fill the home uplink | A.5: the visitors' total; the site's server in its own class | a packet flood below HTTP hits the home line (U9 accepted this); the totals together can fill the uplink (U19) |
| S3 | A free tile CDN for others | no CORS headers, `Cross-Origin-Resource-Policy`, `robots.txt`, limits, the log; tokens can be added later under the same address | hot-linking from servers within the limits |
| S4 | Slow readers hold connections | A.6 timeouts; the caps bound what one address and all together can hold; SWAG's shared connections are far above the totals | a reader just above the timeouts holds its slots; no minimum-speed rule exists |
| S5 | Range and query tricks | A.4 one range; A.2 a query is refused; no cache in front | - |
| S6 | Reading outside the data | only `<root>/public` served, read-only; A.2's patterns; symlinks, dot-files, `.part` refused; staging and trash outside the served tree | - |
| S7 | The home network | no published port of the mirror's project (the publishing door: one port on one address of the server, `PUBLISH_ADDRESS`, reached by the PC on the LAN or over the operator's own VPN or WireGuard link, never forwarded from the internet; U27, U33, U89); an internal network with SWAG as the only neighbour; nothing mounted but public data and the log folder; no secret in the container | SWAG and the router, as before the mirror; the home address is now tied to the project's name (U9); the operator's link, outside the repository |
| S8 | A dataset without the right to redistribute | B's `PUBLISHABLE` with the user's approval is the only way in; cards and the landing page carry the credits; `unpublish` | a wrong row, reviewed like code; Madeira's weak basis (U11) |
| S9 | Damaged, cut-short or mixed tiles | C.2: sha256 before any use; B: staging, verify, moves | a re-encoding published with `--same-values` that does change values: the promise is the publisher's |
| S10 | The home server taken over serves crafted tiles | U8: the mirror is trusted as every provider is; TLS; the worker on the VPS runs in its hardened container | every installation trusts the home server's files (the user's decision; pinning hashes in the repo was the alternative) |
| S11 | Privacy of those who download | A.7's log; SWAG's access log off for the host; the texts of D | the operator can see live traffic; said in the text; the door's own log holds the publishing PC's address (on the LAN or the operator's link) and the key's fingerprint (U43, U89) |
| S12 | The site depends on a home server | U6, U7; later phases and finished runs work from the cache (C.3); D's alert | coarser results on mirrored ground while it is down |
| S13 | A limit set wrong throttles the site or opens the line | the site's class; the client at half the limits; the pair's test; the start script refuses a bad trusted list | several installations behind one address share one allowance; a fifth installation at the same time fails its phase and repeats it |
| S14 | An old image nobody updates | digest pin; the monthly item (D.4) | a manual step at home |
| S15 | The public copy fills the storage | B: the free-space check before a publish; `clean` | - |
| S16 | A request body or an odd method reaches SWAG's disk | A.8: SWAG refuses other methods and bodies above 1 KB itself; the mirror answers 413 to a body above 1 KB sent to it directly (A.2) | - |
| S17 | The publishing key or the PC is taken over: whoever can write `<root>/public` decides what every installation downloads (with U8, the same outcome as S10) | the README requires a key used for publishing only, never placed on the VPS or in the repository; the key opens only the publishing door (U27, U32, U33): SFTP and `sha256sum` under `<root>`, nothing else of the server, its port on one address of the server (`PUBLISH_ADDRESS`, U89), reached over the LAN or the operator's own link; the public folder is read-only for the container | the PC that publishes is a trusted machine; the key can read the door container's own host key; the setuid bit over SFTP is not refused by the door (the README names `nosuid`: the planner's ruling) |

## 9. Still open

| Id | What | Who | When |
| --- | --- | --- | --- |
| M2 | On the real server through SWAG, from the VPS and from one outside address: the first byte of a tile after ten idle minutes under 2 s; two connections sustain at least 80 % of twice the class's rate; the per-address cap refuses through the real SWAG; a 5 km Slovak search's tiles (189 MB) arrive within 45 s at a visitor's limits (24 s by the numbers). Numbers of A.5, C.3 and C.6 confirmed or corrected with the user | closed in rollout step 3 (2026-11-22): from one outside address the first byte 0.11 s, two connections 7.41 MB/s (mark 6.40), the cap 4 served and 4 refused through the real SWAG, the 189 MB in 25.5 s; from the VPS the first byte, the cap and the 45 s mark met, the two connections' mark not met at the time of the measurement; the numbers kept as they are (U94); LV17 through the real SWAG left to M4 | - |
| M4 | LV17 of `mirror_check.sh --live` through the real SWAG: held downloads show that SWAG streams a tile (`X-Accel-Buffering`) instead of buffering it; it needs tiles of 16 MB or more | when the first dataset with such tiles is published (batch 6's 0.5 m tiles, about 22 MB) | that dataset's publishing |
| E1 | rclone's behaviour on a refused rename (the door's `sha256sum` is its own, U32; the tool proves the server's hashing on its lock file before any copy, U35) | closed in rollout step 1 (2026-11-20): the four folders on one device and one mount, and a folder moved from `staging` to `trash` by a server-side move through the door; the README requires one mount (U34) | - |
| E2 | Which account the publishing key opens on the server | closed by U27, U32, U33: the publishing door, an SFTP container of the repository's own (`deploy/mirror/publish/`) | - |
| - | The home server's facts (platform, uplink, the proxy's certificates, storage, how the PC reaches it, power and maintenance, the VPS's transfer quota) | answered by the user on 2026-11-15 and, by U16, kept out of the repository; what they set stands above as requirements | - |

Dropped from the plan, with the reason: the measurement of the site's demand (M3): the VPS's transfer allowance is
ample and the site has a class of its own, so no number depends on it. Decided at the gates and no longer open:
the image, the network, the transport, the licences of Madeira and Valle d'Aosta, the privacy texts, the visitors'
total (U21), the log's keys (U22).

## 10. The order of building

In a later session, under `docs/agent-workflow.md`. Before wave 1 the planner writes the contract; the server agent's README needs E2's answer (how the
publishing key reaches only the mirror's folders), given by U27, U32 and U33 (the server agent built the door too).

| Wave | Agent | Builds | Owns |
| --- | --- | --- | --- |
| 1 | server | solution A | `deploy/mirror/**`, `tests/test_mirror_deploy.py`, `tests/mirror_check.sh`, the job `mirror` of `.github/workflows/ci.yml` (the only edit of that file in wave 1) |
| 1 | publish | solution B | `tools/mirror_publish.py`, `tests/test_mirror_publish.py`, the card texts in `tools/sk_tiles.py` and `tools/mirror_tiles.py` with the tests that pin them |
| 1 | client | solution C | the files of C's "Files and pairs" |
| 2 | site | solution D; the pair tests; CI's rclone; the docs, the rules and this text in line with the build | the files of D's "Files and pairs"; `docs/code-map/tools.md` gets the publish tool's row here |
| 2 | accept | the regression and `check_source` acceptance over HTTP against the test stack (split from "site" by the planner, 2026-11-16) | nothing in the repository |

Wave 1's three agents touch no common file. The publish tests are skipped in CI until wave 2 installs rclone
there (it does: the test parts of CI install rclone 1.76.0 by its sha256); the publish agent runs them on the PC. Effort: A medium, B medium, C high (the search's source choice
across phases, results pinned), D medium. Every build passes the scope reviewer and the code reviewer (high for
C). Milestones that come first in the briefs: B proves its rclone commands on a throw-away SFTP server; C
traces the two phases in `jobs.py` and writes the later-phase test before the change.

Two merges into `main`, each on the user's word: first this specification with `tools/mirror_sizes.py` (the
measuring tool of wave 0, reviewed) and the roadmap's pointer; later the build, as the squash of section 11's
step 4.

## 11. Rollout (each step on the user's word)

The whole build enters `main` as one squash at step 4. Steps 1-3 therefore run the mirror stack and the publish
tool from the task's branch: `deploy/mirror/` is copied to the home server from that branch.

1. The DNS record of `<host>`; the stack on the home server from A's README; SWAG attached to its network
   (`docker network connect findaline-mirror_mirror swag`, U42); the name added to SWAG's certificate in a
   maintenance stop (A's Risks); the publishing door (`PUBLISH_ADDRESS`, the server's address on the
   operator's own link (U89), `PUBLISH_PORT`, `PUBLISH_KEYS`; its binding checked with
   `docker compose port sftp 2222`; one mount for `<root>`, U34); `mirror_check.sh --live`
   with an empty public folder; E1. `--live`'s cap check through the real SWAG (LV15: eight requests at once from
   one address) needs a tile of 1 MB or more, so it runs after the first publish (Madeira's tiles are about
   1.8 MB); LV17 (held downloads: SWAG streams instead of buffering) needs tiles of 16 MB, which no dataset has
   today (M4).
2. Publish Madeira (0.33 GB), check; then its islets Porto Santo, the Desertas and the Selvagens (U53, U55; 3.5 MB
   in all); then Valle d'Aosta, then Slovakia; `verify` on the remote after each. Step 1's cap
   check (LV15) keeps Madeira's tiles: no islet has a tile of 1 MB.
3. M2 on the real path; the user confirms or corrects the numbers; a rework round if they change.
4. The squash into `main` (the client and the address in one commit), push; the VPS updated (its Telegraf then
   checks a mirror that already answers).
5. The VPS's `.env` switched (D.1); one Slovak search compared with the same search of before (counts and
   `lines.csv` sha256).

Follow-ups, not part of the build's definition of done:
6. After a number of good days the user names: `/srv/findaline-mirror` removed from the VPS.
7. Batch 6 (planned in its own task, 2026-11-15) with the same tool when its tiles are cut: datasets at a native
   0.5 m (a "0.5m" folder: A.2's pattern serves it; tiles of an estimated 22 MB, about 6 s at a visitor's rate and
   still within the in-memory download), several products under one dataset folder with one card, folders with
   a hyphen in their name. By that task's reading of the terms (2026-11-15): Wallonia, Valle d'Aosta's surface
   model, Saint Vincent, South Australia and the Australian Capital Territory can be published on a licence;
   New South Wales cannot be published
   until its owner answers; Hong Kong cannot, and is planned as an ordinary on-demand source, so it needs no
   mirror dataset. A dataset that cannot be published and is kept as an own copy would reach the site only by a
   local copy on the VPS, an exception to U4 that the user decides then. Each new dataset needs its
   `PUBLISHABLE` row with the user's approval, and the storage for it (Wallonia an estimated 90 GB per model).

## 12. Definition of done

**The first merge** (this specification, `tools/mirror_sizes.py`, the roadmap's line) is done when:
- [ ] `pytest tests/test_mirror_sizes.py tests/test_entry_points.py tests/test_instructions.py` green, and the
      full pytest on the squash tree (with the viewer's packages installed in that tree, so its tests run);
- [ ] `docs/code-map/tools.md` has the tool's section; the squash's message has the stored-data line ("none");
- [ ] the scope review's and the builder's read's last rounds are answered in the text, and the user gave the word.

The build is done when every line below holds; each names its test or command.

**The mirror stack (A)**
- [ ] `pytest tests/test_mirror_deploy.py` green.
- [ ] `tests/mirror_check.sh` in CI's job `mirror`, a workflow of its own (`.github/workflows/mirror.yml`: run when
      the mirror's files, the check script, its static test or the workflow change, and by hand: U49; at most 150
      minutes): every line PASS, and its self-test FAILs every check with the behaviour switched off.
- [ ] `tests/mirror_check.sh --live https://<host>`: every line PASS (the cap through the real SWAG among them,
      LV15, from 1 MB tiles); LV17 a SKIP until a dataset has tiles of 16 MB (M4).
- [ ] On the home server the README's check commands: read-only root, no capability, no published port, no route
      out, no log file older than 14 days; SWAG attached (U42); the door's port on `PUBLISH_ADDRESS` only (`docker compose port sftp 2222`, U89).

**The address contract and the publish tool (B)**
- [ ] `pytest tests/test_mirror_publish.py` green on the PC and in CI's Linux and Windows jobs with rclone.
- [ ] Every published dataset has its approved `PUBLISHABLE` row; its served card states the changes (Slovakia's
      names the averaging).
- [ ] After each real publish: `mirror_publish.py verify <remote>` passes; `mirror_check.sh --live` finds every
      served `index.json` equal to the master's and the dataset in `datasets.json`.

**The client (C)**
- [ ] `pytest tests/test_mirror_client.py tests/test_sources.py tests/test_madeira_aosta.py tests/test_rates.py
      tests/test_probe.py tests/test_regression_needs.py` green; no test asks the real mirror.
- [ ] `tests/regression.py --mirror-url ...` for R13, R21, R34, R80, R81, R86, R87, R88 from an empty cache: the
      baseline's
      counts and `lines.csv` sha256; the 5 m Slovak search equal to the folder's.
- [ ] `findaline.py sources check slovakia madeira aosta_valley porto_santo desertas selvagens` and
      `tools/check_source.py` for the six pass over HTTP.
- [ ] `git log`: the client and `MIRROR_URL` enter `main` in the same commit.

**The site and the docs (D)**
- [ ] `pytest tests/test_monitoring.py tests/test_mirror_pairs.py tests/test_public.py` green; "Mirror down"
      fired and cleared on the test stack while the site's rules stayed quiet.
- [ ] The docs and rules of D.6 written; the privacy texts word for word as approved; the roadmap's changed
      decisions recorded.
- [ ] Nothing of the home server's own facts in the repository: the planner greps the diff for every value of
      the task's private facts file before the squash.
- [ ] Full pytest green on the squash tree; the commit's stored-data line says "none" (the public folder and the
      mirror's log are not the app's data).

**Rollout**
- [ ] Steps 1-5 of section 11 done, each on the user's word; M2's marks met, or the numbers confirmed or corrected by the user.

## 13. Later payloads: what this design keeps possible

- **Country cubes** (about 5 GB a country, arrays up to 1.7 GB): they need a manifest with a sha256 per array, a
  streamed and resumable download (`net._get` reads a body into memory), a swap into a new build folder (a mapped
  file must never be overwritten), and a decision on publishing them at all (administrators only today; Slovakia's
  carries a FABDEM credit). The address `/v1/cubes/` is reserved; one range per request (A.4) already allows
  resuming.
- **The cache of a country precompute** (Poland about 1.75 TB): a permission per source to redistribute, and a
  machine with that disk. The address `/v1/cache/` is reserved; the host name of its own (U10) lets the mirror
  move to such a machine without a change in any installation.
- **A second base** (P4): `TileBases` keeps a list of bases; a second address is one entry.
- **Tokens** (if anonymous access is abused): a header checked by the server under the same addresses. CC BY
  forbids "technological measures" that restrict others; limits under which anyone still gets every file are not
  that (the research's reading, not legal advice), a token gate is a closer call and the user's decision then.
- **Slovakia's second survey cycle** at 0.5 m, published by its owner by lots under CC BY 4.0: a later dataset,
  as a new edition.
