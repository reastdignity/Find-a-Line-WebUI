# Code map: the web app, metrics

What the modules of this area hold, in detail: the web app, metrics. Moved out of CLAUDE.md on 2026-11-12; nothing
loads this file by itself, so read the entry of a module before a large change to it. What must stay in sync and the
pitfalls are in `.claude/rules/` (web-app, metrics).

## `web.py`

`findaline.py web`: FastAPI on 127.0.0.1 (`TrustedHostMiddleware`, Origin and session token for changes,
`SECURITY_HEADERS` incl. CSP; `--public`: the public host, trusted proxy, sign-in with GitHub/Google/Microsoft
(`/login/<provider>`, `/auth/<provider>`, `POST /logout`), the token of a change is the session's CSRF token, a
sign-in page (`signin_page`, no script, nothing that changes state but signing out) with the demo runs for visitors
and accounts not approved; who may open a run: `may_open` (owner, administrators, anyone for a demo), used by
`run_access` and `RunFiles`; favourite lines (`/api/runs/<run>/favourites`: GET the user's lines of a run with the
token a map's changes need, a map being a static page; POST marks or unmarks one (into a folder), its values checked
by `FavouriteLine` (`lift_needed`/`lift_no_zone` optional, `OPTIONAL`: null dropped), `/favourites/folder` moves one;
`/api/favourites`: all of them in runs the user may open, with the user's folders; `/api/favourites/folders`: make,
rename/move (POST `/<id>`), delete with what is in it; audit `favourite`, `favourite_folder`), the admin tab's
`/api/admin/*` (status, users, runs), `/api/osm` and the demo flag behind `require_admin`; the Admin page is
`viewer/src/app/c/AdminC.tsx` (public site only), the OSM extracts `app/c/OsmC.tsx` (locally and for administrators)),
the highline layer of a country (`Countries`: one `countcube.Cube` per version of
`<data>/countries/<id>/cube/cube.json`, its folder and mtime, ids `COUNTRY_ID` only, the arrays memory-mapped; a newer
build's Cube replaces the old one, which is closed (`Cube.close`) and kept in `_retired` until no computation maps it
(`Cube.mapped`), then `_tidy` runs `countcube.remove_stale` in the caller's thread of the pool (also at a folder's
first cube in the process), never raising, logging nothing; `GET /api/countries` (cube.json
without `config` and `origin`), `/api/countries/<id>/cells` (mode, `bbox` = Leaflet's `toBBoxString()`, else the
cube's bounds grown by the layer's reach (`Cube.reach_m`: the partner lines' cells beyond the outline); `level=auto` →
`Cube.auto_level`, an explicit level over `COUNTRY_CELLS_MAX` (20000) cells in view a 400 "too many cells"; the
filters of `countcube.Filters.parse` with `border=all|own` (all by default: the interior, owned and partner lines;
own: interior and owned) and `Countries.replaced` (the partners of cube.json's `neighbours` whose own cube is in the
data folder: readable, no study area, the same `profile`; their own lines replace this cube's partner lines); a row
per cell and side `[i, j, count, lat, lon of SW, SE, NE, NW, side]` (`Cube.cells(sides=True)`: side 0 the country's
own lines, 1-7 the partner index of its partner lines, so a cell the border cuts gives two rows) rounded to
`COUNTRY_DECIMALS`, `total`, `max`, `cut`: `"i,j"` a side-0 row's part inside the outline (`Cube.cut`), `"i,j,out"` a
partner row's part beyond it within the layer's reach (`Cube.cut_outside`), none for a whole cell),
`/api/countries/<id>/histogram` (the query of cells through `Countries._view`: `Cube.histogram(summary=True)` of the
cells reaching the bbox (`view=`, corners rounded to `COUNTRY_DECIMALS`) with `level` and `cell_deg`: each dimension's
bins, both modes' `totals` and the lines' `border` split, interior, owned, partner), `/api/countries/<id>/outline`
(`Cube.outline_simplified`; 404 also without its area.geojson), `/api/countries/<id>/request`
(`countcube.cell_request`), all `require_admin`, the work in `run_in_threadpool`, cells and histograms through
`LayerSlots` (at most `COUNTRY_SLOTS` at once, the others waiting without a thread `COUNTRY_WAIT_MAX` at most: 503;
`COUNTRY_SECONDS_MAX` each: 504; stopped between two chunks of rows when the client goes away, a task awaiting
`http.disconnect`: the page aborts its fetch on every move; the thread by `anyio.to_thread.run_sync(abandon_on_cancel=True)`,
so a request cancelled while it computes returns at once and its thread stops at its next chunk; every user alike;
`layer_answer`: a `countcube.CubeChanged` (the cube built again while the request computed, its old build's array not
mapped yet gone) answers from the new build once, 503 with `Retry-After` when no newer build is there); a
ValueError a 400 with its text, a
country without a readable cube 404; only countcube imported), the requests the page may send, SSE events
(`sse-starlette`: keep-alive, send timeout; `EventHub`: one poller per process, while a stream is open, reads the new
events of all jobs with their owners (`Jobs.owned_events`) and `worker_alive` once per `TICK` and hands each stream
its user's (`seen_by`); a stream reads by itself only from its start or `Last-Event-ID` to where the hub stood when it
subscribed, `Jobs.events(until=)`), `/api/estimate`, `/api/profile` (a line's profile computed again; `/api/patch`:
the 3D view's heights around a line from the quick lane, `patch_body` frames them as uint32 N | N bytes of JSON meta |
the deflated heights after checking their sha256, rate `patch_rate`, its own nginx route group `patch`; with
`part=canopy` the block of trees and buildings of the same grid, `search.canopy_of_line`, 400 `patch_no_surface`
without a surface model; `/api/reach`: the reach of one anchor, `search.reach_of_anchor`, the header
`X-Findaline-Reach`, the patch's checks and `reach_anchor`, its own rate `reach_rate`, framed by `patch_body` as the
patch; `/view3d`: the 3D view's page `VIEW3D_HTML`, visitors and accounts not approved sent to `/`, its CSP from
`page_csp` (the ring's origins, `ortho_origins`, only while `settings.ViewSettings.ring` is on), its
Permissions-Policy from `PAGE_PERMISSIONS` (the phone's motion sensors), `no-store`, or of two points measured on the
map: `search.profile_of_line`) and `/api/place` (the place box: `osm.places`) answered by the worker's quick lane;
`/api/usage` (the user's use of the quotas and the quotas: `Jobs.usage`; `search`: the limits of one search (area,
radius, longest line, box), null when unlimited; `area`: the km² of the user's finished searches, `Jobs.area`;
`country`: the account's; read-only, no audit event); `POST /api/me/time-zone` (the browser's IANA zone →
`users.country` through `accounts.country_of_zone`, audit `country` only when it changed, rate `time_zone_rate`;
locally nothing stored); the sign-in page's total of everyone's searched km² (`Jobs.area_of_everyone`, kept
`EVERYONE_SECONDS`); `/api/reports` (a problem report: `checked_report`, the User-Agent added by the server,
`report_rate`; `/api/admin/reports` lists, marks done and deletes them; audit `report`); the sign-in leaves
`WELCOME_COOKIE` for the beta notice; `/api/schema` also gives the form's labels, units, hints, choice labels and
topics (from the message catalogue, `messages.text`; the fields of each topic: `params.TOPICS`) and the presets
(`params.PRESETS`, `web.presets`: unavailable when a value is outside the user's bounds); the privacy and about pages
(`privacy_page`, `about_page`, `PAGE_HTML`; server-rendered, no script); `/coverage` (public in both modes,
`COVERAGE_HTML`: a shell of `dist/coverage.js`, nothing stored); `font/woff2` registered with `mimetypes` (Python on
Windows has no type for it); the audit log through `record`; the page is `viewer/src/app`

## `messages.py`, `locales/`

The message catalogue of the web interface: `locales/<language>.json` (English only now: `en.json`), flat namespaced
keys (`field.<name>.label`/`unit`/`help`, `choice.<field>.<value>`, `topic.<id>`, `preset.<id>`, `hint.*`,
`error.<code>`, `ui.*`), i18next's JSON v4 (`{{name}}`, plurals `_zero`/`_one`/`_other`); `messages.text` formats it
on the server as i18next does, `viewer/src/i18n.ts` (i18next core, no React bindings: `t`, `label`) in the page. The
CLI keeps its own texts (`params.py` descriptions). Coded errors and notes: `messages.UserError` (a ValueError),
`ServiceError` (a RuntimeError), `Note` (a str: a search's warning), `search.SearchError` and `jobs.QuotaExceeded`
carry `code` and `params` (`messages.Coded`): str() is the command line's text (option names), `web_text()` the
catalogue's `error.<code>` (a `field` parameter gives its `label`); `messages.user_error` unwraps pydantic's
`ValidationError`; HTTP errors answer `{message, code, params}` (`web.error_detail`), job errors keep the code in
`jobs.sqlite` `error_info`, estimate messages as a third element; the page renders them with `i18n.ts`
`errorText`/`detailMessage` (`api.ts` `ApiError`, `jobError`), the map of a run shows `message` (`errors.ts`, no
catalogue in its bundle)

## `accounts.py`

Accounts of the public site: `accounts.sqlite` (`users`: (provider, subject) with name and status
pending/approved/blocked, no e-mail, `country` of the browser's time zone (`set_country`, `country_of_zone`: tzdata's
`zone.tab` and the links of its `tzdata.zi`); `sessions`: sha256 of the token, CSRF token, created/seen;
`MIGRATIONS`), `Accounts` (`sign_in`, `new_session`, `session`, `revoke`, `set_status`, `set_unlimited`,
`first_admin`), `User.limited` (the tier: users without limits and administrators are not), `LOCAL` (the local app's
one user, an administrator), Authlib's OAuth clients (`oauth_clients`, `identity`), `local_path` (`next`)

## `audit.py`

The audit log of the public site: `audit.sqlite` (its own database: the web server and the worker write it, the worker
never opens `accounts.sqlite`), `Audit.log(action, user_id, target, detail)` with the actions of `ACTIONS`, no IP
addresses; `purge` after `KEEP_DAYS` (90) in `Scheduler.housekeeping`; no viewer, read with `sqlite3`

## `jobs.py`

The web app's job queue (`Jobs`, `jobs.sqlite` with the jobs and their owners (`user_id`), their area, country and
outline (`area_km2`, `country`, `area_outline`: `note_area` in `run_phase`'s download phase for every user, its lookup
outside the user's Nominatim quota, the outline from `area.outline_geojson`, simplified to about 50 m; `request_area`
filled those of before in migrations 13 and 14; `Jobs.area`, `area_of_everyone`), the requests of the worker's
processes to outside services (table `service_requests`, running totals per host and outcome: `add_service_requests`,
the writer of `servicecounts`, enabled in `run_phase` and `run_quick`) and the starts of their phases
(`downloading_at`, `computing_at`, set by `claim`; `ready_at` by `set(..., "ready")`), their source and resolution
(`set_search`, F19), the seconds of their computing steps (table `job_steps`: `set_steps`, `StepClock` from the
progress bars' states, `STEP_KEYS`; migration 16: `cpu_seconds` per step, table `job_stages` (seconds and CPU seconds
per `STAGE_KEYS`, the stages of steps 2 and 3) and table `job_funnel` (`FUNNEL_STEPS`, from `Plan.funnel`), from
`StepClock.cpu`/`stages`, written by `_write_statistics` after the phase, never failing it), the tiles of the layers
downloaded (table `layer_downloads`: `add_layer_downloads`, the writer of `servicecounts.tiles`, F18), the runs'
owners, visibility, share-link hash and size (table `runs`: `add_run`, `adopt_runs`, `runs_of`, `set_share`,
`shared_run`, `set_visibility`/`demo_runs`: private or demo), the events and the workers' leases; the favourite lines
(table `favourites`: `favourites`, `set_favourite`, `move_favourite`, at most `FAVOURITES_MAX` per user, deleted with
their run, the local user's (NULL) given to the first administrator by `adopt_runs`) the users' problem reports (table
`reports`: `add_report`, `reports`, `set_report_status`, `delete_report`; `REPORT_CATEGORIES`, `REPORT_TEXT_MAX`) and
the folders of favourites (table `favourite_folders`, nested: `folders`, `add_folder`, `change_folder`,
`delete_folder` with what is in it; `FOLDERS_MAX`, `FOLDER_DEPTH_MAX`, `FOLDER_NAME_MAX`; `folders.ts` repeats the
moves allowed); `add(..., check=)` runs a quota check in the job's insert transaction (`admission`: the user's quotas
and the server's safeguards, `QuotaExceeded` with its HTTP status), `use` counts Mpx, km² and uncached Nominatim
requests in the table `usage` (`charge_area`, `nominatim_quota` in the worker), `delete_run`; its schema steps in
`MIGRATIONS`) and the worker (`Scheduler`: in the `web` process or `findaline.py worker`; one process per job and
phase, `run_phase`: download, then compute (`save_run` → `add_run` → `_write_statistics` → "done" → the lines released
→ `_orthophoto_after`: the orthophoto for offline use with `ortho_confirm`, its messages and progress as events of the
job, its errors never touching the job or its run, then its seconds as the row `orthophoto` of `job_steps`, the other
rows as written at "done"); `Limits.download_slots`/`compute_slots` of each at once (`Scheduler.running`: a list per
phase; `_occupied`: a compute process whose job is done already, downloading the orthophoto, holds no slot
(`Jobs.statuses`, one query a tick), keeps its time limit (the kill ends the download only: the job's status is
guarded by `when`) and is killed by `stop` like the others; it holds its imports only, so `slot_memory` reserves
nothing for it), several compute slots each with `Scheduler.memory` = `search.slot_memory` passed to `run_phase` and
`run_quick` (an estimate's tiles as its job's); `Jobs.claim` takes the oldest waiting job of the user with the fewest
running jobs (NULL users as one), one `UPDATE` in a write transaction; cancelling through `cancel_requested`,
`kill_tree`; the quick lane: one long-lived process, `run_quick`, serving estimates and profiles and the 3D view's
patches (`quick_patch`; `Redact.RAW` keeps its base64url `heights` out of the key masking) from the table `quick`
(idle it only reads, `quick_waiting`, and claims with a write transaction when a task waits; `quick_take` reads before
it deletes); `Scheduler.housekeeping`: old events, `.part` files, work folders, the cache's size per top-level folder
(`write_cache_sizes` → `work/cache-sizes.json`), the coverage of the finished searches (`coverage` →
`work/coverage.json`: the union's km² on the ellipsoid, searches per 0.25° cell) and what the round removed
(`work/housekeeping.json`), all for `metrics.py`; `Scheduler.memory` is measured at the worker's start (`_begin`),
never by the public web process's scheduler, which does not run; `_begin` also starts the numba warm-up
(`warmup.warm_up`) in a daemonic process of its own when `Scheduler(warm_up=True)` (`findaline.py worker` and `web`:
`warm_up_wanted`, off with `FINDALINE_WARM_UP=0`; the tests leave it off), jobs claimed meanwhile, killed by `stop`,
its folder `work/warmup/` removed after a day by the housekeeping; `--public`: `Redact` of events, errors and answers,
"internal error, ref <id>" for unexpected exceptions)

## `servicecounts.py`

Counts of the requests to outside services (docs/monitoring.md F11) in the memory of a process by host and outcome
(`OUTCOMES`), with bytes and seconds, and of the tiles of the elevation layers (F18: `tiles` by layer and role,
`ROLES`, `role_of` a download label; counted in `sources.layer.download_layers`, pixels and km² from the cached file's
header by `_extent`); `request` (a context manager: `got(response)`, `add` for streamed bytes, `outcome` to override),
`get`, `call`, `record`; `flush` adds them to `jobs.sqlite` `service_requests` (a failed write keeps them); only after
`enable(writer)` (the worker's `run_phase` and `run_quick`, flushed at the end of each phase and task and every
`FLUSH_SECONDS` by a thread): the CLI and `tests/regression.py` count nothing. Hooked into `sources.net._get` (every
attempt), the listings of `sources/indexes/listings.py`, `WcsReader`'s DescribeCoverage, `Windows` (one per file read
for a block; GDAL's own requests unseen), `osm._ask`, the Overpass queries, `osmextract` (index, extract, pyosmium's
replication through `_replication_server`), `coast`'s world file and `orthophoto._get`; `tests/test_servicecounts.py`

## `metrics.py`

The application's metrics for the monitoring (docs/monitoring.md F1-F19): `Metrics`, a `prometheus_client` collector
with its own registry (`registry`), reading `jobs.sqlite` (also `service_requests`), `accounts.sqlite` and
`audit.sqlite` through read-only connections at each scrape (aggregates only, totals counted from the rows),
`work/cache-sizes.json`, `work/housekeeping.json` and `work/coverage.json` (written by `Scheduler.housekeeping`; their
metrics absent before its first round), the free disk and the web app's own counts: the quick lane
(`app.state.quick_answers`, `web.QUICK_RESULTS`), the requests per route template, method and status class
(`web.RouteCounts` in the `guard` middleware, `web.route_template`; `unmatched` without a route, methods outside
`HTTP_METHODS` as `other`, the event stream left out of the time) and the open event streams (`EventHub.listeners`);
F19: Mpx and seconds by resolution, seconds and CPU seconds per step (`findaline_compute_step_[cpu_]seconds`), per
stage of the line search (`findaline_compute_stage_[cpu_]seconds`) and its funnel (`findaline_line_funnel`), every
label value present; `serve`: `start_http_server` in a thread of `web` (`--metrics-port`, 8766 by default with
`--public`, `0.0.0.0` in the container; compose.yaml publishes `127.0.0.1:8766`, never behind nginx; locally only when
given, on 127.0.0.1); no label with a user id, IP address, title, place name or path (`tests/test_metrics.py`)

## `settings.py`

`Limits` (pydantic-settings, `FINDALINE_LIMIT_*`; nothing set means no limit, as locally): time limits of the worker's
phases and of the quick lane, the worker's slots (`compute_slots`, `download_slots`: 1 and 1 unless set, also on the
public site; compose.yaml sets them from `WORKER_COMPUTE_SLOTS`/`WORKER_DOWNLOAD_SLOTS` of `.env`), limits on request
values (`check_request`: the fields not allowed, on the raw names; `check_params`: the bounds of `BOUNDS`, radius and
resolution too, on the validated `SearchParams`; `bounds`, `not_allowed`; `Limits.load(public=True)` starts from
`PUBLIC`, time limits too, `None` instead of a `Limits` means unlimited), the cost of a search (`bbox_km_max`,
`area_km2_max` also for circles, ...), a user's quotas (`jobs_active_max`, `jobs_day_max`, `mpx_day_max`: km² /
resolution² (`jobs.plan_mpx`, the page shows it as km² at the search's resolution), `km2_day_max` (off on the public
site), `download_mb_day_max`, `runs_gb_max`, `nominatim_day_max`) and rates (`estimate_rate`, `profile_rate`,
`place_rate`, `report_rate`, `time_zone_rate`, `reach_rate`, `job_rate`: the `limits` library's notation), the
server's safeguards for everyone (`queue_max`, `free_disk_gb_min`, also checked by the worker before each phase),
`lines_early_stop` (F7, true unless set: the line search stops as soon as its lines are over `lines_max` or the
memory; false: refused at the end with their exact number); `PublicSettings` of `--public` (`FINDALINE_PUBLIC_URL`,
`_TRUSTED_PROXY`, `_CONTACT`, Docker secrets); `AccountSettings` of `web --public` (session secret, OAuth clients,
administrators, sign-up, `FINDALINE_ACCOUNTS_DIR`: the folder of `accounts.sqlite`, by default the data folder);
`ServiceKeys` (keys of data services; `ViewSettings` of the 3D view (`FINDALINE_3D_RING`, off, and
`FINDALINE_3D_RING_URL`: the ring of terrain from Mapterhorn's tiles; the environment only, read once by
`web.create_app`): `opentopography_api_key` (the default of `--opentopo-key`), `datafordeler_api_key`,
`lantmateriet_user`/`_password`, `nls_api_key`; each from the environment variable in upper case or the worker's
Docker secret of that name), `service_key(name)` (read when needed, never at import), `missing_keys`, `key_setting`,
`redact` (masks their values: used by `cache.clean_error`/`clean_url` and `jobs.Redact`). Named `settings.py`, not
`limits.py`: that would shadow the `limits` library
