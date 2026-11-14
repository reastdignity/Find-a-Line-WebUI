---
paths:
  - "web.py"
  - "jobs.py"
  - "accounts.py"
  - "audit.py"
  - "settings.py"
  - "messages.py"
  - "locales/en.json"
  - "tests/test_public.py"
  - "tests/test_web.py"
---
# The web app: server, job queue, accounts, limits, texts

What each module holds: docs/code-map/web.md. Related rules: `run-files.md` (what a run's files and favourites hold),
`view3d.md` (`/api/patch`, `/api/reach`, `page_csp`), `country-layer.md` (`/api/countries*`), `metrics.md`
(`RouteCounts`, the tables the metrics read), `search-pipeline.md` (the limits in the worker), `browser-tests.md` (the
tests that start Edge).

## Must stay in sync

- The message catalogue `locales/en.json` and its users: every field the web may set has `field.<name>.label`, `.unit`
  and `.help`, every choice of a choice field (but the sources' names, from `sources.SOURCES`)
  `choice.<field>.<value>`, every topic of `params.TOPICS` and preset of `params.PRESETS` its title
  (`tests/test_units.py::test_labels_topics_and_presets`); every literal key of `t("...")` in `viewer/src` exists
  (`test_viewer_keys_in_catalogue`). `messages.py` and `viewer/src/i18n.ts` format alike (interpolation, plural forms:
  `tests/test_viewer.py::test_messages_match_python`). A new language is one more `locales/<language>.json` with the
  same keys. The coverage map has its own catalogue, `locales/coverage/<language>.json` (English and Polish), read
  only by `viewer/src/coverage/i18n.ts`. Every code of a coded error or note in the Python modules has its
  `error.<code>` text, and no `error.*` text names a command-line option or a snake_case field
  (`tests/test_units.py::test_error_codes_in_catalogue`, which reads the codes from the source with `ast`: give a code
  as a literal, a conditional of literals, or `f"rate_{kind}"`/`f"quota_use_{kind}"`, whose kinds it lists); a text
  the web page shows goes through a code, never a text with `--option`. `error_info` holds no personal data (a code
  and the values of the request or the search; redacted on the public site as `error`).
- `settings.Limits` (fields, `PUBLIC`, `BOUNDS`), the table "Limits of the web app" in README.md and the form:
  `web.schema(limits)` gives the form `min`/`max` and leaves out what `not_allowed` forbids, `search/SearchPanel.tsx`
  puts them on its inputs (`Setting`, the ranges of radius, buffer and the key fields). A new limit on a request value
  is a field plus an entry in `BOUNDS` (or its own check in `check_request`) and a README row; a new quota or rate is
  a field, a `PUBLIC` default, its check (`Jobs.admission`, `Jobs.use`, `web.within_rate`) and a README row.
- The tiers of the accounts: `accounts.User.limited` (not an administrator, not `users.unlimited`) decides in one
  place; `web.user_limits` (request values and the form), `jobs.unlimited` / `quick.unlimited` (the worker's search
  limits and quotas: `run_phase`, `run_quick`), `Jobs.admission(limited=)` and `web.within_rate` follow it. The
  safeguards (`queue_max`, `free_disk_gb_min`, time limits, a compute slot's memory budget and F7's early stop at it:
  `Plan.early_stop`, which `run_phase` sets from the server's `Limits` also when the user's limits are None) never
  depend on it. Locally the one user is `LOCAL` and `FINDALINE_LIMIT_*` apply as before (`web.unlimited` is False
  without `--public`).
- `web.RUN_FILES` (the files of a run the public site serves) and what `mapping.save_map` and `runs.save_results`
  write (`map.html`, `data.js`, `lines.js`, `lines.csv`, `lines.geojson`, `ATTRIBUTION.txt`): a new file a map needs
  goes into both, a file with the owner's details (`run.json`) or work state (`progress.json`, `tiles/`) into neither.
  `web.SIZED_FILES` carry `web.SIZE_HEADER`, the name `viewer/src/download.ts` `SIZE_HEADER` reads
  (`tests/test_viewer.py::test_run_script_parsed_and_body_sized`). `window.FINDALINE_APP` (`profiles`: may the map
  compute profiles and measure; `favourites`: may it mark favourite lines) is written by the dynamic `runs.js` of
  `web.py` and read by `viewer/src/result/model.ts` (declared in `types.ts`); undefined means as before (from a server
  yes, from disk no).
- The privacy page (`web.privacy_page`) states what is stored and for how long:
  `accounts.SESSION_DAYS`/`IDLE_DAYS`/`OAUTH_SECONDS`, `Limits.keep_events_days`, `jobs.DAY` (usage),
  `audit.KEEP_DAYS`, a search's area and country (`jobs.area_km2`/`country`), the account's country of its time zone
  (`users.country`), the operator's statistics without personal data and without a time limit (the metrics:
  docs/monitoring.md, "Privacy", holds the accepted wording), no IP addresses; a new stored field, cookie or retention
  changes it too. A credit, orthophoto or note naming `sources.YEAR` is filled with the year of the run wherever a
  run's credits are written (`search.save_run`: run.json, lines.geojson, ATTRIBUTION.txt, data.js) and reads
  `YEAR_TEXT` where no run exists (the about page); a new place that shows a credit fills it too. Every state-changing
  endpoint of the public site records an `audit` event (`web.record`), refusals by a quota or rate too (`queue`,
  `within_rate`, `Jobs.use`). The about page is built from `sources.SOURCES` credits (and their layers'), so a new
  source needs no change there.

## Pitfalls

- **Every endpoint checks who asks, through its dependencies**: `current_user` (signed in and approved; locally
  `accounts.LOCAL`, an administrator), `require_admin`, `run_access`, and those built on them (`visible_job`: own
  jobs, an administrator's all; `own_job`: edit and run again, own only). Never an ad-hoc check inside the endpoint:
  `tests/test_public.py::test_every_route_has_its_access_rule` fails for a route outside `web.PUBLIC_ROUTES` without
  one. Another user's job or run answers 404, not 403. Jobs carry `user_id` (NULL: the local app's or from before the
  accounts); the event stream filters by it (`Jobs.events(user_id=...)`), at most `SSE_PER_USER` streams per user;
  `_search_hash` includes the owner (`Plan.owner`; None locally, so the hash of before).
- **Run folders are never served statically on the public site**: `/runs` is `web.RunFiles` (a `StaticFiles` subclass:
  only `RUN_FILES` of a run the request's user may open, `_viewer/` for anyone, served from the code's `viewer/dist`,
  never from `runs/_viewer`, which the worker writes; 404 for everything else, an empty path part too; Starlette's
  path checks, ETag and Range); `/runs/runs.js` is generated per user (own runs) and `/runs/index.html` redirects to
  the app (the public worker writes neither file: `Plan.index_runs`). The owners are the table `runs` of `jobs.sqlite`
  (the worker adds the row when a job saves its run; at the start of `web --public`, `Jobs.adopt_runs` gives runs
  without a row or owner to the first administrator of `FINDALINE_ADMINS`, whose user row is made then if needed).
  Locally `/runs` is the plain folder as before (tests put their test pages there). Share links: `/s/<token>/<file>`
  is another `RunFiles` (the run found by the sha256 of the token, `Jobs.shared_run`; none once its owner is blocked),
  `/s/_viewer/` the viewer, `/s/runs.js` sets only `FINDALINE_APP = {profiles: false}` (no `FINDALINE_RUNS`: the map
  shows its own run only), `/s/index.html` redirects to `/`; the map's `../../cache/...` lands on `/cache/`
  (orthophoto tiles, open to anyone). The owner makes, renews (`POST /api/runs/<id>/share`, the link is shown once)
  and revokes (`DELETE`) the link; a share page must never reach another run.
- **Sign-in** (`accounts.py`): Authlib keeps state, nonce and PKCE verifier in `request.session`, the signed cookie
  `__Host-findaline-oauth` of Starlette's `SessionMiddleware` (10 min); never configure Authlib's cache (it moves the
  state out of the browser's cookie). The callback address comes from `FINDALINE_PUBLIC_URL`, `next` only through
  `accounts.local_path`. Our session cookie `__Host-findaline` holds a token whose sha256 is the row in `sessions`;
  the CSRF token of the page is the session's, compared with `secrets.compare_digest`. Errors of the ID token's checks
  are `joserfc` errors (`JoseError`), not `OAuthError`. `__Host-` cookies need `Secure`: tests use an `https://`
  `base_url`.
- **The web worker** runs each phase in a `spawn` process; its stdout becomes `info` events, and
  `progress.TEXT_INTERVAL` is set to infinity there (progress goes as events). A `spawn` process makes its own
  streams, in the Windows code page when they are redirected (a local app started with its output in a pipe or file):
  no "²", and the quick lane's bars printed `fill_water`'s "sea 0.31 km²" as text, a `UnicodeEncodeError` (a
  `ValueError`, answered as the request's 400) in every 3D view and profile of a run with water filling. The worker's
  process targets call `progress.utf8_output()` as `findaline.py` does, and `run_quick` and `run_phase` answer a
  `UnicodeError` as an internal error (`tests/test_web.py::test_quick_lane_output_in_utf8`, with
  `PYTHONIOENCODING=cp1250` on every OS). Every script that prints does the same in its `if __name__ == "__main__":`
  block (or among its module-level statements without one); a script on the standard library alone
  (`tools/job_stats.py` runs with the VPS host's `python3`, `tools/test_lock.py`, the reports in `docs/`) reconfigures
  its two streams inline: `tests/test_entry_points.py` reads every `.py` of the repository. The tests start their
  processes without `PYTHONIOENCODING`/`PYTHONUTF8` (`tests/conftest.py` drops a calling shell's), so they write as
  for a user; git's output (paths) is read with `encoding="utf-8"`. The worker may be another process than the web
  server (`web --no-worker` + `worker`, the public setup): the two talk only through `jobs.sqlite` (claims,
  `cancel_requested`, the `workers` leases), never through memory. Only jobs of a worker whose lease expired (`LEASE`,
  renewed every `HEARTBEAT`) are failed as interrupted, so restarting `web` never touches a running job; a phase ends
  a job only if it is still in that phase's status (`Jobs.set(..., when=...)`), so a cancelled or failed job stays so.
  A status change writes its event in the same write transaction (`Jobs._insert_event` in `add`, `claim`, `set`,
  `request_cancel`): written after it, the download phase's "ready" could land after the worker's "computing" and the
  page showed the job ready while it computed. The web process does no search work: estimates and profiles are rows of
  the table `quick`, which one process of the worker answers one after another (so `search`/`sources` state is never
  shared between threads); the endpoint waits with `asyncio.sleep`, and answers 503 without a worker. A tiled area
  stopped by cancelling or closing the app resumes on the next start of the same search. On the public site every text
  that reaches the page goes through `Jobs(public=True)` (`event`, `set(error=...)`, `quick_answer`): write new
  messages through these, never around them. The page is drawn again on every queue event: form fields must not take
  their value from state that changes only on `change` (text fields: `onInput`; number fields: `defaultValue`), or
  typing is reset.
- **Limits are checked on validated values**: `web.checked_request` validates the request (`SearchParams`) and
  `Limits.check_params` compares what pydantic read ("5_e3" is 5000 there, and `float()` refuses it), never the raw
  JSON; the worker repeats the bounds (`search._check_params` in `plan_search`). A bound that needs the resolution
  takes the parsed one.
- **Heavy work and network only in the worker**: the web process validates and queues; estimates and profiles go to
  the quick lane; it never imports `search` or `numba` (`tests/test_public.py` checks it), so it needs no numba cache.
  A check that can refuse cheaply (rates, quotas: `Jobs.precheck`) comes before validating a request.
- **Every waiting loop has a deadline**: `web.quick` waits at most `QUICK_WAIT_MAX` (the lane's time limit per task
  ahead) and stops when the client goes away (a task awaiting `http.disconnect`: `Request.is_disconnected` never sees
  it behind the `guard` middleware, a `BaseHTTPMiddleware`); an event stream re-checks its session every
  `SESSION_CHECK` seconds; the worker's phases and the quick lane have time limits on the public site (`PUBLIC`). A
  new loop that waits for another process or a client needs the same, and polls the database once per process, not
  once per client: the event streams wait on their `web.EventHub` queue (with the session check as its timeout), the
  hub stops with the last stream and at shutdown (lifespan).

## Running it

- `python findaline.py web --no-browser --port 8799 --data-dir <scratch>` runs the web app for tests (start it in the
  background). Headless Edge waits for the open event stream: stub `EventSource` in a test page (see
  docs/regression-tests.md) or use `--timeout` for screenshots.
- `web --public` / `worker --public`: the public site behind a reverse proxy (`settings.PublicSettings`:
  `FINDALINE_PUBLIC_URL`, `FINDALINE_TRUSTED_PROXY`, `FINDALINE_CONTACT`, also from Docker secrets in `/run/secrets`);
  refuses to start without them; `web --public` also needs `settings.AccountSettings` (`FINDALINE_SESSION_SECRET`, at
  least 32 characters; `FINDALINE_<GITHUB|GOOGLE|MICROSOFT>_CLIENT_ID`/`_SECRET`, a provider without both is not
  offered (the providers: `accounts.CLIENTS`, their names `settings.PROVIDERS`); `FINDALINE_ADMINS` as
  `github:<numeric id>,google:<sub>,microsoft:<sub>`; `FINDALINE_SIGNUP=approval|open|closed`); `web --public` never
  runs the worker, and `--host` other than loopback needs `--public`. Tests:
  `PublicSettings(public_url="http://localhost:<port>", ...)` and a `TestClient` with that `base_url`
  (`tests/test_public.py`); sign-in against fake providers: `FakeProviders` there (an `httpx2.MockTransport` passed as
  `create_app(oauth_transport=...)`, which Authlib's clients take through `client_kwargs`),
  `sign_in(client, providers, user)`.
