"""
Screenshots of the app for a visual review of a UI change (.claude/rules/viewer.md, "Verifying changes"): every page of
PAGES on a desktop (Chromium, 1400 × 900) and on two phones (Playwright's device profiles: iPhone 13 on
WebKit, Safari's engine; Pixel 7 on Chromium), each with its viewport, pixel ratio, touch and user agent,
in the light theme and optionally the dark one.

The site is the public one (signed in as an administrator, so Admin and the OSM extracts are there;
the "-limited" pages as an approved user with the site's limits), run
from a scratch data folder with a run of the Żabi Koń clip (tests/data, computed offline), the highline
layer of two sample cubes of made-up counts (tests/test_country_web.py's sample_cube), a problem report and
a worker of this process (the estimates of a new search need its quick lane). It is served over
HTTPS with a certificate made for the run: WebKit, unlike Chromium, sends no Secure cookie (the session's
`__Host-` cookie) to http://localhost.

    uv sync --group ui
    uv run playwright install chromium webkit
    uv run tools/ui_shots.py --out <folder> [--only c-] [--exclude <part>] [--dark | --themes light|dark|both]
                             [--data-dir <scratch>] [--timings <file>.json] [--strict]
    uv run tools/ui_shots.py --list [--only ...] [--data-dir <scratch>]

`--run <folder>` shows a saved run instead of the clip's (copied into the data folder's runs/ unless it is there;
the data folder then needs the run's cache, e.g. a link to the real one) and `--line <lat1,lon1,lat2,lon2>` its line
on the pages of a line ("c-line", the 3D view's); the search's other pages stay as they are.

The "map" pages are a run's own map.html (from the server and by its share link). The files are
<page>-<device>-<theme>.png; a page whose click finds nothing on a device is left out, and so is a page whose
feature (NEEDS: a no-fall zone or A-frames, an uncertain shore, the square rule) the run lacks (run_features, from
its run.json, before any browser starts). Phone screenshots of the viewport only (the app scrolls inside, not the
page). `--only` takes the pages whose name contains one of its comma-separated parts, `--exclude` then drops those
whose name contains one of its; `--list` prints the selected pages and which the run leaves out (it makes the data
folder ready, but starts no browser). `--dark` is `--themes both`.

A data folder given with `--data-dir` is kept and can be used again: its marker ui-shots.json holds the clip run
shown there and a key (data_key: the sha256 of the repository's root *.py, this tool, tests/test_country_web.py and
the clip's two files, and of the repository's path: the clip run names the clip's files by it, so a folder is kept
for the checkout that made it). A start whose key is the marker's keeps the clip run and the three cubes (4 s of a 13 s
desktop start on 2026-11-16 with numba's cache warm; more when it is cold); another key, no marker (a folder of
before) or `--fresh` makes them anew, and the clip run the marker names is removed then (folder and row: one clip
run in a kept folder; a `--run` start removes nothing; one whose removal fails is named in the marker and tried
again at every start), and the problem report is made again for the run shown. Each start ends the sessions of the
tool's users before it makes theirs, so Admin's counts stay the same: one run at a time per data folder (a second
start ends the first one's sessions). The default data folder is a temporary one, removed at the end.

For a caller that measures the prepared pages instead of shooting them: shoot_all (the passes' loop, rows and pass
records kept as they are made, `on_row` called with each row), pass_context (a pass's browser context, with the caller's options such as
`bypass_csp`) and shoot_page's `act` (called on the open page in place of the screenshot, its dict in the row).

No fixed sleeps: after a page's load and after each click, script or scroll the tool waits until the page is settled
(settled: for QUIET_MS in a row no request in flight, no map tile loading and no map moving, no CSS animation, no busy
spinner, no animation frame or short timer of the page pending or asked for, and the mark of the page's family:
page_family, PAGE_STATE), at most 30 s after a load and 10 s after a step; a page still busy then is shot all the same
and noted "not settled" with what was busy (a note, like "map tiles still loading"). After a "wait:" step: two
animation frames and nothing busy. A "wait:" waits at most 10 s, a page's first-draw mark (FIRST_DRAW: the 3D view's
ready mark, the estimate's, the result's) 30 s, "c-basic-sea"'s estimate 240 s (SLOW_MARKS: its first "Sea cliffs"
estimate in a fresh data folder fetches the coastline); a mark that can no longer come (GIVE_UP: the estimate
failed) ends its wait at once, as a wait that did not come true. A map tile that failed to load is not waited for.

Each saved picture is printed with its seconds; at the end a summary: the set-up's parts, the seconds of each pass
(a device and a theme), the ten slowest pages, the pages left out with their reasons, every wait that timed out and
every failed step, the pages not settled; `--timings` writes all of it as JSON (a record per page and pass: the seconds
of the load, the settled wait after it ("settle"; "tiles" 0, the tiles are in it), each step and the shot; the outcome;
"unsettled"). A wait that timed out once gets a quarter of its limit for the rest of the pass (a settled wait: per
family, after a load or a step); a step that raises (a click that cannot be done: 10 s, a script's error) fails its
page, and the run goes on; `--strict` stops at the first timeout or failed step. The exit code is 1 when a "wait:" timed
out or a step failed ("not settled" and "map tiles still loading" are notes only). A page whose later step finds nothing after a wait
timed out is "timed out", not "left out": nobody knows then what the device shows. A whole page too tall for its picture at the
device's pixel ratio (WebKit's 32767 px: the coverage page on the iPhone) is taken at one pixel per CSS pixel and
noted ("scale": "css").

With ESRI_API_KEY set, the pages showing Esri's imagery ("map-esri", the "view3d" pages but "view3d-shaded" and
"view3d-edges") are for the review only: Esri's terms forbid storing or passing its imagery on, so delete them after
looking and never publish them.
"""

import argparse
import gc
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# Dummy settings of the public site: nobody signs in through a provider, the session is made here;
# every provider, so the sign-in page shows all their buttons
ACCOUNTS = {"FINDALINE_SESSION_SECRET": "ui-shots-" * 5, "FINDALINE_ADMINS": "github:1",
            **{f"FINDALINE_{p}_CLIENT_{k}": "dummy" for p in ("GITHUB", "GOOGLE", "MICROSOFT") for k in ("ID", "SECRET")}}

# name -> (interface ("map": the run's map.html, "shared": it by its share link), hash, actions after loading or None: a CSS selector to click, "scroll:<selector>" to
# scroll that element (or the page) to its end, "js:<expression>" to evaluate it in the page, "low:<selector>" to click the last one scrolled to the
# bottom of its panel (a "?" near the bottom: its bubble opens upwards), "wait:<expression>" to wait until it is true,
# "need:<expression>" to wait until it is true and leave the page out when it is not (the run does not have it),
# or a list of such steps[, the user: "admin" (default), "walker", an approved user with the site's limits, one of
# RIGGERS (with saved rigs), or "visitor", not signed in]); a step "full" takes the whole page, not only the viewport;
# "{run}" is the clip's run, "{line}" its first line (keys.lineCoords); an interface starting with "/" is a path of
# web.py's pages (the server-rendered ones and the 3D view's)
# Leaflet's layer control opened as its expand() does (hover on a desktop, a tap on a phone: neither is the
# same click on every device)
LAYERS_OPEN = "document.querySelector('.leaflet-control-layers').classList.add('leaflet-control-layers-expanded')"
ESRI_ON = ("[...document.querySelectorAll('.leaflet-control-layers-base label')].find((l) => "
           "l.textContent.trim() === 'Esri World Imagery')?.querySelector('input').click()")
# The coverage page: a click on an area of the flat view (by its key)
COVERAGE_CLICK = "document.querySelector('.cov-shape[data-key=\"{key}\"]').dispatchEvent(new MouseEvent('click', {{bubbles: true}}))"
GLOBE = ".cov-bar .u-seg button:nth-child(3)"  # the globe view: it turns by itself until touched (SPINS)
# The place map zoomed out (its zoom's animation and tiles: settled)
ZOOM_OUT = "window.FINDALINE_PLACE.map.setZoom(5)"
# The section "Anchors" of a result's More filters in view: its terrain line in the middle (the anchors'
# heights and percentiles around it), else its heading at the top
ANCHORS_SHOWN = ("(() => { const t = document.querySelector('.r-terrain'); if (t) return t.scrollIntoView({block: 'center'}); "
                 "[...document.querySelectorAll('.r-more-sec > h3')].find((h) => h.textContent === 'Anchors')"
                 "?.scrollIntoView({block: 'start'}); })()")
# The filter of a run with a no-fall zone or A-frames ("A-frame needed at most", FilterBar.tsx LiftFilter) in view
RIGGING_SHOWN = "document.querySelector('.r-lift')?.scrollIntoView({block: 'center'})"
# The uncertain shore's control shown (shoreLayer.ts), and its chip unfolded (a click whether the chip is shown or not:
# from 768 px up it is hidden and the box is open anyway). A run without uncertain shore (the clip's) has no control:
# its shore pages are left out (NEEDS before any load; "need:" as the second line of defence), not shot empty after a
# wait or failed on the chip's click
# (zoomed out: a coast at the area's edge; the control follows the map's "moveend" at once, shoreLayer.ts, and the
# tiles are settled)
SHORE_SHOWN = ["js:window.FINDALINE_MAP.zoomOut(1, {animate: false})",
               "need:document.querySelector('.u-shore-ctl:not([hidden])')"]
SHORE_UNFOLD = "document.querySelector('.u-shore-chip')?.click()"
# What a "need:" step waits for before it tests its expression once: the result's map made (the shore's control is
# added before it is set: ResultColumns.tsx, KitResult.tsx)
NEED_READY = "window.FINDALINE_RESULT"
# The limits of the waits (the user's choice at gate 2 of 2026-11-17; stage 2 measured every wait but the estimate
# under 0.1 s after the old fixed 2.5 s, the 3D view's ready mark once 7.7 s under load). A wait that reaches its limit
# in a pass gets a quarter of it for the rest of the pass (Pass.limit)
WAIT_MS = 10000  # a "wait:" step (FIRST_DRAW_MS for a page's first-draw mark)
FIRST_DRAW_MS = 30000  # the first-draw marks (FIRST_DRAW: the 3D view's ready mark, the estimate's, the result's)
SETTLE_LOAD_MS = 30000  # settled after a page's load (then the page is shot and noted "not settled")
SETTLE_STEP_MS = 10000  # settled after a step
CLICK_MS = 10000  # the pages' default timeout (a click; Playwright's own is 30 s)
LOAD_MS = 30000  # a page's load and its screenshot (Playwright's default, kept)
# The profile of the selected line in view (phones: further down the sheet; a desktop's card is over the map)
PROFILE_IN_VIEW = "document.querySelector('.r-dock .fal-profile-chart')?.scrollIntoView({block: 'center'})"
# A click at the map's centre on what is there (the cells' canvas: Leaflet finds the cell under it)
CELL_AT_CENTRE = ("(() => { const map = window.FINDALINE_PLACE.map, box = map.getContainer().getBoundingClientRect(); "
                  "const p = map.getSize().divideBy(2), x = box.left + p.x, y = box.top + p.y; "
                  "const init = {bubbles: true, clientX: x, clientY: y}, e = document.elementFromPoint(x, y); "
                  "e.dispatchEvent(new MouseEvent('mousemove', init)); e.dispatchEvent(new MouseEvent('click', init)); })()")
ADVANCED = ".s-tabs [data-tab=advanced]"  # the search form's tab Advanced (a new search opens Basic)
MORE = [ADVANCED, ".s-more-head", ".s-topic:nth-of-type(2) > summary"]  # More settings, Anchors opened (Lines is)
# The Basic search form (spec-search 1.6): the centre set at the clip's place, so the bar shows the receipt
POINT = "js:window.FINDALINE_PLACE.map.fire('click', {latlng: {lat: 50.1559508, lng: 19.7562722}})"
READY = "wait:document.querySelector('.s-bar')?.dataset.estimate === 'ready'"  # the source and grid in the bar
SEA_VIEW = "js:window.FINDALINE_PLACE.map.setView([36.055, 14.20], 14, {animate: false})"  # a coast in view (Gozo, Dwejra)
FORM_END = "scroll:.c-form"  # the rig's row at the end of Basic (phones)
RETURN = ["js:(window.FINDALINE_SEARCH.setValue('pretension', 4), window.FINDALINE_SEARCH.setValue('min_drop', 50))",
          ".s-tabs [data-tab=basic]"]  # two values Basic cannot show, then back to Basic: its dialog
# The users with saved rigs (the Basic form's states; approved, without the site's limits): name -> (subject, rigs)
TARGET_RIG = {"pretension": 2.5, "stretch": 5, "webbing_weight": 70, "athlete_mass": 80, "fall_zone": 6, "end_zone": 5,
              "anchor_lift": 2}
STARTING_RIG = {**TARGET_RIG, "anchor_lift": 0}
LONG_RIG = {**TARGET_RIG, "pretension": 4, "stretch": 3, "webbing_weight": 60, "anchor_lift": 3}
THREE_RIGS = [("My rig", TARGET_RIG), ("Park lines", STARTING_RIG), ("Long lines", LONG_RIG)]
RIGGERS = {"one-rig": ("21", THREE_RIGS[:1]), "three-rigs": ("22", THREE_RIGS),
           "ten-rigs": ("23", THREE_RIGS + [(f"Rig {n}", STARTING_RIG if n % 2 else TARGET_RIG) for n in range(4, 11)])}
# The highline layer's selected cell at the top of its panel, the notes under it ("c-layer-border")
BORDER_CARD_SHOWN = "document.querySelector('.c-layer-cell')?.scrollIntoView({block: 'start'})"
# The highline layer's fold "More filters" in view ("c-layer-chips", "c-layer-fold")
FOLD_SHOWN = "document.querySelector('.c-layer-more')?.scrollIntoView({block: 'start'})"
# The 3D view drawn (its terrain and the found line's profile: view3d/main.ts) and its imagery loaded
VIEW3D_READY = ("wait:document.getElementById('view3d')?.dataset.ready === '1' && "
                "(document.querySelector('.v3-activity')?.classList.contains('v3-hidden') !== false || "
                "document.querySelector('.v3-activity').classList.contains('v3-activity-notice'))")
# Round 2's tools of the strip (view3d/chrome.ts): a click on one, then what it shows
TOOL = ".v3-tool[data-tool={}]".format
REACH_SHOWN = "wait:document.getElementById('view3d')?.dataset.reach === '1'"
TREES_SHOWN = "wait:document.getElementById('view3d')?.dataset.trees === 'on'"
PROFILE_SHOWN = "wait:!!document.querySelector('.v3-card svg')"
# A click on the terrain where the first anchor's handle stands (view3d/point.ts: a press and release in place)
POINT_CLICK = ("(() => { const r = document.querySelector('.v3-handle').getBoundingClientRect(), "
               "c = document.querySelector('.v3-canvas'), at = {clientX: r.left + r.width / 2, "
               "clientY: r.top + r.height / 2, pointerId: 7, button: 0, bubbles: true, isPrimary: true}; "
               "c.dispatchEvent(new PointerEvent('pointerdown', at)); c.dispatchEvent(new PointerEvent('pointerup', at)); })()")
POINT_SHOWN = "wait:Number(document.getElementById('view3d')?.dataset.point) > 0"
OTHERS_SHOWN = "wait:Number(document.getElementById('view3d')?.dataset.others) > 0"
# The profile's card folded again (its state is kept in the browser, and the page before may have opened it)
CARD_FOLDED = "js:document.querySelector('.v3-tool[data-tool=profile][aria-pressed=true]')?.click()"
SHADED_ON = ("js:[...document.querySelectorAll('.v3-toolbar [role=radio]')].find((b) => "
             "b.textContent.trim() === 'Shaded')?.click()")
# The "Edges" look chosen and drawn (view3d/scene.ts sets data-edges)
EDGES_ON = ("js:[...document.querySelectorAll('.v3-toolbar [role=radio]')].find((b) => "
            "b.textContent.trim() === 'Edges')?.click()")
EDGES_DRAWN = "wait:document.getElementById('view3d')?.dataset.edges === 'on'"
VIEW3D = "#run={run}&line={line}"
# The first-draw marks: a page's first draw waited for (FIRST_DRAW_MS; a page of SLOW_MARKS its own limit)
FIRST_DRAW = (VIEW3D_READY[5:], READY[5:], NEED_READY)
# A page whose first-draw marks (and settled waits after its steps) may take longer: page -> its limit. "c-basic-sea":
# the first "Sea cliffs" estimate in a fresh data folder fetches the view's coastline from Overpass (160 s in stage 2's
# run, 33 s on 2026-11-17; then cached in the folder)
SLOW_MARKS = {"c-basic-sea": 240000}
# A mark that can no longer come: expression -> (what says so, the words of the note). Its wait ends there, as a wait
# that did not come true (the picture shows the page as it is; exit code 1), without its limit and without a quarter
# for the rest of the pass. The estimate's bar after a failed request: "unavailable" (no answer; Overpass's 502 Bad
# Gateway on 2026-11-17 kept c-basic-sea waiting its whole 240 s) or "refused" (search/useSearch.ts; "paused" asks
# again by itself)
GIVE_UP = {READY[5:]: ("['unavailable', 'refused'].includes(document.querySelector('.s-bar')?.dataset.estimate)",
                       "the estimate failed (unavailable or refused)")}
# The phone's motion (view3d/views.ts; its button only on touch screens): held upright facing north, then turned
# 40 degrees right and tilted 10 degrees up: two events with DeviceOrientationEvent's angles (WebKit on Windows
# cannot construct one)
MOTION_TURN = ("js:for (const [alpha, beta] of [[0, 90], [-40, 100]]) "
               "dispatchEvent(Object.assign(new Event('deviceorientation'), {alpha, beta, gamma: 0}))")
PAGES = {
    "c-home": ("c", "", None),
    "c-home-limited": ("c", "", None, "walker"),  # the usage meters of a user with the site's limits
    "c-menu": ("c", "", ".c-account-btn"),        # the account menu (desktop: a popover)
    "c-account": ("c", "#account", None),         # the account page (phones)
    "c-account-end": ("c", "#account", "scroll:.c-main"),
    "c-new": ("c", "#new", None),
    "c-new-hint": ("c", "#new", ".u-hint"),       # the first "?" of the search panel, its bubble open
    "c-new-intro": ("c", "#new", ".s-intro .n-intro-link"),  # "How a search works" (ui/Intro.tsx)
    "c-new-more": ("c", "#new", MORE),
    "c-new-more-hint": ("c", "#new", MORE + [".s-topics details[open] .u-hint"]),  # a setting's "?" (no bounds: admin)
    "c-new-low-hint": ("c", "#new", MORE + ["low:.s-topics details[open] .u-hint"]),  # the last "?" at the bottom: its bubble above it
    "c-new-limited": ("c", "#new", ".s-intro .n-intro-link", "walker"),  # the intro with the limits
    "c-new-limited-hint": ("c", "#new", MORE + [".s-topics details[open] .u-hint"], "walker"),  # a "?" with the bounds
    "c-favourites": ("c", "#favourites", None),
    "c-admin": ("c", "#admin", None),
    "c-layer-cell": ("c", "#layer", "js:" + CELL_AT_CENTRE),  # the highline layer's cell under the map's centre selected
    "c-osm": ("c", "#osm", None),
    "c-result": ("c", "#run={run}", None),
    "c-line": ("c", "#run={run}&line={line}", None),  # a line selected: its details, the profile's card over the map
    "c-line-profile": ("c", "#run={run}&line={line}", ["wait:document.querySelector('.r-dock .fal-profile-chart')",
                                                        "js:" + PROFILE_IN_VIEW]),  # its profile in view (phones)
    "c-result-intro": ("c", "#run={run}", ".r-filters .n-intro-link"),  # "How to read the result"
    "c-result-more": ("c", "#run={run}", [".r-filters .u-chip.u-add", "js:" + ANCHORS_SHOWN]),  # More filters: Anchors
    # More filters: Rigging (a run with a no-fall zone or A-frames, --run; the clip's has no such section)
    "c-result-rigging": ("c", "#run={run}", [".r-filters .u-chip.u-add", "wait:document.querySelector('.r-lift')",
                                              "js:" + RIGGING_SHOWN]),
    # a run made with the square rule (--run): "Why so many?" opened under the head's counts
    "c-result-why": ("c", "#run={run}", ".r-why-link"),
    "c-result-unfold": ("c", "#run={run}", ".r-rows .r-unfold"),  # the first spot's lines unfolded, in its order
    # More filters: Grouping, its "Show per spot" ("Highest on average" first)
    "c-result-grouping": ("c", "#run={run}", [".r-filters .u-chip.u-add",
                                               "js:document.querySelector('.r-by')?.scrollIntoView({block: 'center'})"]),
    "c-result-rails": ("c", "#run={run}&line={line}", None),  # both panels collapsed to rails (LAYOUTS)
    "c-result-card": ("c", "#run={run}&line={line}", None),  # the card narrowed from the left (LAYOUTS)
    "c-result-credits": ("c", "#run={run}", ".u-credits-toggle"),  # the data credits unfolded (phones: no card)
    # a run with an uncertain shore in view (--run): phones fold its box into a chip; unfolded, and with its "?" text
    # opened (scrolling inside the box); a desktop shows the box, always open
    "c-result-shore-folded": ("c", "#run={run}", SHORE_SHOWN),
    "c-result-shore": ("c", "#run={run}", SHORE_SHOWN + ["js:" + SHORE_UNFOLD]),
    "c-result-shore-help": ("c", "#run={run}", SHORE_SHOWN + ["js:" + SHORE_UNFOLD,
                                                 "js:document.querySelector('.u-shore-ctl .u-shore-help').click()"]),
    "c-layer": ("c", "#layer", None),             # the highline layer of the sample cube (tests/test_country_web.py)
    "c-layer-world": ("c", "#layer&view=49.42,19.66,8", None),  # both sample cubes in view (Slovakia, Testland)
    "c-layer-study": ("c", "#layer&country=sk-part", None),  # the study area, alone
    "c-layer-end": ("c", "#layer", "scroll:.c-mappage-3"),  # phones: the histograms at the end of the column
    "c-layer-collapsed": ("c", "#layer", None),   # the left panel collapsed to its rail (LAYER_LAYOUTS)
    # two filters of the fold "More filters" set: the closed fold names them as chips; opened
    "c-layer-chips": ("c", "#layer&drop=60&elevation_low=1000", "js:" + FOLD_SHOWN),
    "c-layer-fold": ("c", "#layer&drop=60&elevation_low=1000", [".c-layer-more > summary", "js:" + FOLD_SHOWN]),
    # a cell the border cuts selected at the map's centre (its part inside the country), the card and the notes in view
    "c-layer-border": ("c", "{border}", ["js:" + CELL_AT_CENTRE, "wait:document.querySelector('.c-layer-search-hint')",
                                         "js:" + BORDER_CARD_SHOWN]),
    "map": ("map", "", None),
    "map-line": ("map", "", ".r-rows .r-row"),  # a spot selected: its details and profile
    "map-shared": ("shared", "", None),
    "map-credits": ("map", "", ".u-credits-toggle"),  # the data credits unfolded (phones: on a desktop no button)
    "map-layers": ("map", "", "js:" + LAYERS_OPEN),  # the base layers (Esri with ESRI_API_KEY set)
    "map-esri": ("map", "", "js:" + ESRI_ON),  # the satellite layer shown (ESRI_API_KEY set; else as "map")
    "map-shared-credits": ("shared", "", ".u-credits-toggle"),
    "c-new-coverage": ("c", "#new", [".n-coverage-btn", "js:" + ZOOM_OUT]),  # the data coverage on the place map
    # The Basic search form (spec-search 1.6): the first visit (no rig saved: the starting rig), a saved rig, three
    # rigs, the rig chooser, ten rigs, each goal, the rig's window (the first, a change), Advanced, the dialog of going
    # back to Basic, the size word's "?", the phones' compact bar unfolded
    "c-basic-first": ("c", "#new", [POINT, READY]),
    "c-basic-rig": ("c", "#new", [POINT, READY], "one-rig"),
    "c-basic-rigs": ("c", "#new", [POINT, READY, FORM_END], "three-rigs"),
    "c-basic-chooser": ("c", "#new", [POINT, READY, ".s-rig-pick", FORM_END], "three-rigs"),
    "c-basic-ten": ("c", "#new", [POINT, READY, ".s-rig-pick", FORM_END], "ten-rigs"),
    "c-basic-long": ("c", "#new", [POINT, READY, "[data-goal=long]", READY], "one-rig"),
    "c-basic-firstline": ("c", "#new", [POINT, READY, "[data-goal=first]", READY], "one-rig"),
    # the map moved to a coast (Gozo's west) first: "Sea cliffs" takes the view as its limit (the clip's place has none)
    "c-basic-sea": ("c", "#new", [POINT, READY, SEA_VIEW, "[data-goal=sea]", READY], "one-rig"),
    "c-basic-everything": ("c", "#new", [POINT, READY, "[data-goal=everything]", READY], "one-rig"),
    "c-basic-window": ("c", "#new", [POINT, READY, ".s-rig-change0"]),
    "c-basic-window-edit": ("c", "#new", [POINT, READY, ".s-rig-change", ".s-rig-more > summary"], "three-rigs"),
    "c-basic-advanced": ("c", "#new", [POINT, READY, ADVANCED, READY], "one-rig"),
    "c-basic-advanced-rigging": ("c", "#new", [POINT, READY, ADVANCED, READY, ".s-more-head", ".s-topic[data-topic=rigging] > summary",
                                               "js:document.querySelector('.s-rig-save')?.scrollIntoView({block: 'center'})"],
                                 "one-rig"),
    "c-basic-return": ("c", "#new", [POINT, READY, ADVANCED] + RETURN + [READY], "one-rig"),
    "c-basic-size": ("c", "#new", [POINT, READY, ".s-size .u-hint"], "one-rig"),
    "c-basic-compact": ("c", "#new", [POINT, READY, ".s-sum"], "one-rig"),
    "page-signin": ("/", "", None, "visitor"),
    "page-privacy": ("/privacy", "", None),
    "page-about": ("/about", "", None),
    # the coverage map (viewer/src/coverage/page): a visitor, its three views, a card, the table, Polish
    "page-coverage": ("/coverage?lang=en", "", None, "visitor"),
    "page-coverage-full": ("/coverage?lang=en", "", "full", "visitor"),
    "page-coverage-card": ("/coverage?lang=en", "", "js:" + COVERAGE_CLICK.format(key="pl"), "visitor"),
    "page-coverage-partly": ("/coverage?lang=en", "", ["js:" + COVERAGE_CLICK.format(key="de")], "visitor"),
    "page-coverage-europe": ("/coverage?lang=en", "", ".cov-zoombar button:nth-child(2)", "visitor"),
    "page-coverage-leaflet": ("/coverage?lang=en", "", [".cov-bar .u-seg button:nth-child(2)",
                                                        ".cov-zoombar button:nth-child(2)"], "visitor"),
    "page-coverage-globe": ("/coverage?lang=en", "", [GLOBE, ".cov-zoombar button:nth-child(2)"], "visitor"),
    "page-coverage-stars": ("/coverage?lang=en", "", [".cov-scale button:nth-child(3)",
                                                      "js:" + COVERAGE_CLICK.format(key="es")], "visitor"),
    "page-coverage-life": ("/coverage?lang=en", "", [".cov-scale button:nth-child(2)",
                                                     "js:" + COVERAGE_CLICK.format(key="us-ak")], "visitor"),
    "page-coverage-pl": ("/coverage?lang=pl", "", ["js:" + COVERAGE_CLICK.format(key="cz"), "full"], "visitor"),
    # the 3D view of the first line at the device's level (a coarse pointer: the phone's), then at the other one;
    # its imagery Esri's with ESRI_API_KEY set (the clip's run has no orthophoto), else the terrain shaded
    "view3d": ("/view3d", VIEW3D, VIEW3D_READY),
    "view3d-shaded": ("/view3d", VIEW3D, [VIEW3D_READY, SHADED_ON]),
    "view3d-edges": ("/view3d", VIEW3D, [VIEW3D_READY, EDGES_ON, EDGES_DRAWN]),  # the terrain on paper with its edges
    "view3d-phone": ("/view3d?level=phone", VIEW3D, VIEW3D_READY),
    "view3d-full": ("/view3d?level=full", VIEW3D, VIEW3D_READY),
    # the walker's views (view3d/views.ts): its eyes, behind it
    "view3d-eyes": ("/view3d", VIEW3D, [VIEW3D_READY, ".v3-views [data-view=eyes]",
                                        "wait:document.getElementById('view3d')?.dataset.view === 'eyes'"]),
    "view3d-behind": ("/view3d", VIEW3D, [VIEW3D_READY, ".v3-views [data-view=behind]",
                                          "wait:document.getElementById('view3d')?.dataset.view === 'behind'"]),
    "view3d-motion": ("/view3d", VIEW3D, [VIEW3D_READY, ".v3-views [data-view=eyes]", ".v3-motion", MOTION_TURN,
                                          "wait:document.getElementById('view3d')?.dataset.motion === 'on'"]),
    # round 2: the profile's card (both levels), and at the full level the reach of "Only valid lines" and the
    # canopy of "Trees and buildings" (the run is given the clip's surface model: clip_run)
    "view3d-profile": ("/view3d", VIEW3D, [VIEW3D_READY, TOOL("profile"), PROFILE_SHOWN]),
    "view3d-valid": ("/view3d?level=full", VIEW3D, [VIEW3D_READY, CARD_FOLDED, TOOL("valid"), REACH_SHOWN]),
    "view3d-trees": ("/view3d?level=full", VIEW3D, [VIEW3D_READY, CARD_FOLDED, TOOL("trees"), TREES_SHOWN]),
    # the lines from a point (a click on the terrain at anchor 1) and the address's other lines
    "view3d-point": ("/view3d?level=full", VIEW3D, [VIEW3D_READY, CARD_FOLDED, TOOL("point"), "js:" + POINT_CLICK,
                                                    POINT_SHOWN]),
    "view3d-others": ("/view3d", VIEW3D + "&also={also}", [VIEW3D_READY, CARD_FOLDED, OTHERS_SHOWN]),
}

# The layout of C's result kept in localStorage ("findaline.layout", result/view/layout.ts) for a page; every other
# page starts from none (the defaults)
LAYOUTS = {
    "c-result-rails": {"v": 1, "list": {"w": 340, "open": False}, "details": {"w": 380, "open": False},
                       "profile": {"h": 260, "folded": False, "l": 12, "r": 12}},
    "c-result-card": {"v": 1, "list": {"w": 340, "open": True}, "details": {"w": 380, "open": True},
                      "profile": {"h": 300, "folded": False, "l": 200, "r": 12}},
}

# The pages that show something only some runs have (run_features, read from the run's run.json before any browser
# starts): a page whose feature the run lacks is left out without a load
NEEDS = {
    "c-result-rigging": "lift",
    "c-result-shore-folded": "shore", "c-result-shore": "shore", "c-result-shore-help": "shore",
    "c-result-why": "found",
}
LACKS = {"lift": "the run has no no-fall zone or A-frames", "shore": "the run has no uncertain shore",
         "found": "the run was not made with the square rule"}

# The "low:" step: the last matching element is scrolled to just above the bottom of the visible part of
# its scrolling panel (or above a bar that stays there, data-hint-floor), then marked for the click
LOWEST = """(sel) => {
  const all = [...document.querySelectorAll(sel)].filter((e) => e.checkVisibility({visibilityProperty: true}));
  const e = all[all.length - 1];
  if (!e) return;
  let box = e.parentElement;
  while (box && !/auto|scroll/.test(getComputedStyle(box).overflowY)) box = box.parentElement;
  box = box || document.scrollingElement;
  let bottom = Math.min(box.getBoundingClientRect().bottom || innerHeight, innerHeight);
  for (const f of box.querySelectorAll("[data-hint-floor]")) {
    if (getComputedStyle(f).position === "sticky") bottom = Math.min(bottom, f.getBoundingClientRect().top);
  }
  box.scrollTop += e.getBoundingClientRect().bottom - (bottom - 24);
  e.setAttribute("data-shot-low", "");
}"""

# The highline layer's side panels kept in localStorage ("findaline.layer.layout", result/view/layout.ts) for a page;
# every other page starts from none (the defaults)
LAYER_LAYOUTS = {
    "c-layer-collapsed": {"v": 1, "left": {"w": 400, "open": False}, "right": {"w": 620, "open": True}},
}

INTROS = ("search", "result")  # the intros of ui/Intro.tsx (localStorage "findaline.intro.<name>")

# Settled (settled): a page is shot once, for QUIET_MS in a row, no request is in flight (Requests), no map tile loads,
# no map moves, no finite CSS animation or transition runs, no busy spinner shows, no animation frame or short timer
# of the page is pending or was asked for (WATCH), and the page's family (page_family) says it is drawn (PAGE_STATE).
# QUIET_MS by trial (2026-11-17, the whole set, 3 devices, both themes, stage 2's data folder, the shared lane): 150,
# 250 and 400 ms gave the same 496 pictures (each the same as stage 2's but its unstable pages, which come out settled,
# and noise) in 1267, 1363 and 1459 s: the shortest. The page's own short waits are watched (WATCH), not outlasted
QUIET_MS = 150
POLL_MS = 50  # between two looks at the page
SHORT_TIMER_MS = 1000  # a page's timer up to this long is waited for (the coverage page's 150 ms remount, debounces)
EVENTS = "/api/events"  # the event stream: never ends, not a request in flight
TILES_NOTE = "map tiles still loading"
# The steps after which the page's animation frames are not waited for: the globe turns by itself until touched
# (coverage/page/globe.ts); the next step's click stops it
SPINS = {GLOBE}
# The page's animation frames and short timers watched (an init script of every page, before the page's own scripts):
# how many are pending, and how many were asked for (a frame or a timer asked for and run between two looks counts)
WATCH = """(() => {
  if (window.__uiShots) return;
  const s = window.__uiShots = {frames: 0, timers: 0, asked: 0, timed: 0};
  const frames = new Set(), timers = new Set();
  const raf = window.requestAnimationFrame, caf = window.cancelAnimationFrame;
  const st = window.setTimeout, ct = window.clearTimeout;
  window.requestAnimationFrame = function (fn) {
    s.asked++;
    const id = raf.call(window, (t) => { frames.delete(id); s.frames = frames.size; fn(t); });
    frames.add(id); s.frames = frames.size;
    return id;
  };
  window.cancelAnimationFrame = function (id) { frames.delete(id); s.frames = frames.size; return caf.call(window, id); };
  window.setTimeout = function (fn, ms, ...rest) {
    if (typeof fn !== "function" || (Number(ms) || 0) > %d) return st.call(window, fn, ms, ...rest);
    s.timed++;
    const id = st.call(window, () => { timers.delete(id); s.timers = timers.size; fn(...rest); }, ms);
    timers.add(id); s.timers = timers.size;
    return id;
  };
  window.clearTimeout = function (id) { if (timers.delete(id)) s.timers = timers.size; return ct.call(window, id); };
})();""" % SHORT_TIMER_MS
# What is still busy in the page (a list of words, empty when nothing is) and the counts of frames and timers asked
# for. The families' marks: "result" window.FINDALINE_RESULT (ResultColumns.tsx, KitResult.tsx) and with a line in
# the address its profile's chart; "view-b" window.FINDALINE_VIEW (the result view of line-volume round 4, set after its
# first full draw); "search" the bar's estimate neither waiting nor loading (search/useSearch.ts; its 800 ms debounce
# is a short timer too); "layer" the histograms not waiting and the total not "Counting…" (LayerPage.tsx,
# LayerHistograms.tsx); "coverage" its status gone (coverage/page/CoveragePage.tsx); "view3d" the activity's pill
# hidden or a notice (view3d/main.ts, as VIEW3D_READY); "home" no "Loading…" (Home.tsx, FavouritesPage.tsx, Trip.tsx),
# no mini map loading in view (Thumb.tsx: its tiles are SVG images, requests), the OSM page's list or its error
# (OsmC.tsx); "static" nothing of its own
PAGE_STATE = """({family, line, frames}) => {
  const busy = [], s = window.__uiShots || {frames: 0, timers: 0, asked: 0, timed: 0};
  const has = (sel) => !!document.querySelector(sel);
  const shows = (e) => e.checkVisibility({visibilityProperty: true});
  const inView = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight; };
  if (document.readyState !== "complete") busy.push("the page loading");
  // a tile image that failed is complete but never "loaded" (Leaflet marks only a load without error)
  if ([...document.querySelectorAll(".leaflet-tile:not(.leaflet-tile-loaded)")].some((t) => t.tagName !== "IMG" || !t.complete))
    busy.push("%s");
  if (has(".leaflet-zoom-anim, .leaflet-pan-anim")) busy.push("a map moving");
  for (const a of document.getAnimations()) {
    if (a.playState !== "running" && !a.pending) continue;
    if (a.effect?.getComputedTiming().endTime !== Infinity) { busy.push("an animation"); break; }
    const target = a.effect.target;
    if (target && shows(target)) { busy.push("a spinner"); break; }
  }
  if (frames && s.frames) busy.push("animation frames");
  if (s.timers) busy.push("short timers");
  if (family === "result") {
    if (!window.FINDALINE_RESULT) busy.push("the result not drawn");
    if (line && !has(".r-dock .fal-profile-chart")) busy.push("the profile not drawn");
  } else if (family === "view-b") {
    if (!window.FINDALINE_VIEW) busy.push("the result view not drawn");
  } else if (family === "search") {
    const bar = document.querySelector(".s-bar");
    if (!bar) busy.push("no estimate bar");
    else if (bar.dataset.estimate === "waiting" || bar.dataset.estimate === "loading") busy.push("the estimate");
  } else if (family === "layer") {
    if (has(".c-layer-right.c-layer-waiting") || has(".c-layer-total > span.u-small")) busy.push("the layer counting");
  } else if (family === "coverage") {
    if (has(".cov-status")) busy.push("the coverage loading");
  } else if (family === "view3d") {
    const pill = document.querySelector(".v3-activity");
    if (pill && !pill.classList.contains("v3-hidden") && !pill.classList.contains("v3-activity-notice")) busy.push("the 3D view's activity");
  } else if (family === "home") {
    if ([...document.querySelectorAll("p.u-small")].some((p) => p.textContent === "Loading…")) busy.push("Loading…");
    if ([...document.querySelectorAll(".c-thumb[data-thumb=loading]")].some(inView)) busy.push("a mini map loading");
    const osm = document.querySelector(".c-osm");
    if (osm && !osm.querySelector(".c-error") && osm.lastElementChild?.tagName === "H2") busy.push("the regions list");
  }
  return {busy, asked: frames ? s.asked : 0, timed: s.timed};
}""" % TILES_NOTE
TWO_FRAMES = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"

DESKTOP = {"viewport": {"width": 1400, "height": 900}, "device_scale_factor": 1}
DEVICES = {"desktop": ("chromium", None), "iphone": ("webkit", "iPhone 13"), "pixel": ("chromium", "Pixel 7")}


def clip_run(data: str) -> str:
    """A run of the Żabi Koń clip in this data folder (offline, as tests/test_public.py's fixture)."""
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
           "PYTHONIOENCODING": "utf-8"}
    clip = os.path.join(REPO, "tests", "data", "zabi_kon_nmt.tif")
    runs = os.path.join(data, "runs")
    before = set(os.listdir(runs)) if os.path.isdir(runs) else set()
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", clip, "--northing", "254608", "--easting", "553966",
         "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
         "--nmpt", "off", "--name", "Żabi Koń clip", "--data-dir", data],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env=env)
    if result.returncode:
        sys.exit(result.stdout + result.stderr)
    made = [d for d in os.listdir(runs) if d not in before and os.path.isfile(os.path.join(runs, d, "run.json"))]
    if len(made) != 1:  # the run just made, never another of a data folder used before
        sys.exit(f"the clip's search made {len(made)} runs in {runs}, not one")
    run = made[0]
    with_credits(os.path.join(runs, run, "data.js"))
    with_surface(os.path.join(runs, run, "run.json"))
    return run


def with_surface(path: str):
    """The run's run.json as if it had been searched with the clip's surface model (as tests/test_reach.py's
    with_surface): the 3D view then offers "Trees and buildings" and its reach marks lines over trees. The lines
    of the run stay those found without it (a run.json that has the layer already keeps its one)."""
    import obstacles
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["params"]["nmpt"] = "mark"
    meta["params"]["obstacles"] = dict(obstacles.RULE)
    if not any(entry.get("layer") == "Surface file" for entry in meta["data"]):
        meta["data"].append({"layer": "Surface file", "file": os.path.join(REPO, "tests", "data", "zabi_kon_nmpt.tif")})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f)


def first_line(data: str, run: str, k: int = 0) -> str:
    """The first line of a run (or its line `k`, the last one beyond the end) as its links name it (keys.lineCoords:
    the anchors of its data.js row)."""
    with open(os.path.join(data, "runs", run, "data.js"), encoding="utf-8") as f:
        rows = json.loads(f.read().partition(" = ")[2].rstrip().rstrip(";"))["lines"]
    return ",".join(str(v) for v in rows[min(k, len(rows) - 1)][:4])


def with_credits(path: str):
    """The credits of a run of geoportal.gov.pl filled with FABDEM in its data.js, its store's head (the page reads
    the store when the run has one) and run.json (a run of local files has none), so the map's and the 3D view's
    attribution are as long as a real run's (on a phone: folded behind their button)."""
    import sources as src
    with open(path, encoding="utf-8") as f:
        prefix, _, text = f.read().partition(" = ")
    data = json.loads(text.rstrip().rstrip(";"))
    data["attribution"] = [c.as_dict() for c in src.SOURCES["geoportal"].credits] + [src.FABDEM_CREDIT.as_dict()]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{prefix} = {json.dumps(data, ensure_ascii=False)};\n")
    # the same in its run.json, which the 3D view's patch gives on (search.patch_of_line)
    meta_path = os.path.join(os.path.dirname(path), "run.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["attribution"] = data["attribution"]
    if meta.get("store"):
        meta["store"] = with_store_head(os.path.dirname(path), {"attribution": data["attribution"]})
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def with_store_head(folder: str, values: dict) -> dict:
    """The run's lines.arrow written again with `values` in its head (the schema's metadata `findaline`, as
    linestore.write writes it); run.json's block "store" of it."""
    import hashlib
    import pyarrow as pa
    import linestore
    path = os.path.join(folder, linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    meta["head"].update(values)
    table = table.replace_schema_metadata({linestore.META_KEY: json.dumps(meta, ensure_ascii=False).encode("utf-8")})
    linestore._write_file(path, table)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:16]
    return {"format": meta["format"], "lines": table.num_rows,
            "bytes": sum(os.path.getsize(os.path.join(folder, name)) for name in linestore.FILES), "sha256": sha}


def border_view(data: str) -> str:
    """#layer at 30" cells centred on the part inside Slovakia of one of the sample cube's cells the border cuts that
    has a row of partner lines too (the cell of the most lines among those cut to about half)."""
    import countcube as cc
    cube = cc.Cube(os.path.join(data, "countries", "slovakia", "cube"))
    i, j, side, n = cube.cells("lines", 1, None, cc.Filters(replaced=(2,)), sides=True)
    sides, counts = {}, {}
    for a, b, s, c in zip(i.tolist(), j.tolist(), side.tolist(), n.tolist()):
        sides.setdefault((a, b), set()).add(s)
        counts[a, b] = counts.get((a, b), 0) + c
    cut = cube.cut(1)
    whole = {key: cube.cell_km2(1, [key[1]])[0] for key in cut}
    found = [key for key in cut if {0, 1} <= sides.get(key, set()) and 0.3 < cut[key]["km2"] / whole[key] < 0.7]
    if not found:
        return "#layer"
    key = max(found, key=lambda k: counts[k])
    import shapely
    part = shapely.MultiPolygon([shapely.Polygon([(lon, lat) for lat, lon in polygon[0]]) for polygon in cut[key]["shape"]])
    point = part.representative_point()
    return f"#layer&view={point.y:.5f},{point.x:.5f},14&level=1"


def certificate(folder: str):
    """A self-signed certificate of localhost for this run: (certificate file, key file)."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = os.path.join(folder, "localhost.pem"), os.path.join(folder, "localhost-key.pem")
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_file, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return cert_file, key_file


def saved_run(data: str, folder: str) -> str:
    """A saved run's folder in this data folder's runs/ (copied there unless it is already in it): its id."""
    run = os.path.basename(os.path.normpath(folder))
    target = os.path.join(data, "runs", run)
    if os.path.normcase(os.path.abspath(folder)) != os.path.normcase(os.path.abspath(target)):
        shutil.copytree(folder, target, dirs_exist_ok=True)
    return run


def run_features(run_folder: str) -> set:
    """What a run has of NEEDS' features, from its run.json (read once, before any browser starts): "lift" a no-fall
    zone or A-frames (params "end_zone", "anchor_lift": the head's, mapping._ends), "shore" an uncertain shore (a
    segment of run.json's "shore": shore.ts hasShore), "found" the square rule (params "same_line_side")."""
    with open(os.path.join(run_folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    params = meta.get("params") or {}
    features = set()
    if params.get("end_zone") or params.get("anchor_lift"):
        features.add("lift")
    if any(segment.get("m", 0) > 0 for segment in (meta.get("shore") or {}).get("segments") or []):
        features.add("shore")
    if params.get("same_line_side"):
        features.add("found")
    return features


def left_out_by_run(pages, features: set) -> dict:
    """The pages of `pages` whose feature (NEEDS) the run lacks: name -> the reason."""
    return {name: LACKS[NEEDS[name]] for name in pages if name in NEEDS and NEEDS[name] not in features}


MARKER = "ui-shots.json"  # in a kept data folder: the key of the code that made it, the clip's run shown there
KEYED = [os.path.join("tools", "ui_shots.py"), os.path.join("tests", "test_country_web.py"),
         os.path.join("tests", "data", "zabi_kon_nmt.tif"), os.path.join("tests", "data", "zabi_kon_nmpt.tif")]
REPORT = "The lake in the profile is 3 m too high near the second anchor."  # Admin's problem report


def data_key() -> str:
    """The sha256 over the contents of the files a data folder's clip run and cubes come from: the repository's
    root *.py (sorted by name), this tool, tests/test_country_web.py and the clip's two files; and over the
    repository's path, since the clip run names the clip's files by it (a kept folder used from another checkout
    is built anew: the checkout that made it may be gone, and the 3D view reads those files)."""
    digest = hashlib.sha256(os.path.normcase(os.path.abspath(REPO)).encode("utf-8") + b"\0")
    names = sorted(n for n in os.listdir(REPO) if n.endswith(".py")) + KEYED
    for name in names:
        digest.update(name.replace(os.sep, "/").encode("utf-8") + b"\0")
        with open(os.path.join(REPO, name), "rb") as f:
            digest.update(hashlib.sha256(f.read()).digest())
    return digest.hexdigest()


def read_marker(data: str) -> dict:
    """The data folder's marker (MARKER), {} without one."""
    try:
        with open(os.path.join(data, MARKER), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


CUBES = ("slovakia", "testland", "sk-part")  # sample_cubes' countries


def sample_cubes(data: str):
    """The highline layer's pages (#layer): two cubes and a study area, as tests/test_country_web.py's fixture."""
    sys.path.insert(0, os.path.join(REPO, "tests"))
    from test_country_web import OUTLINE2, OUTLINE_STUDY, sample_cube
    sample_cube(data)
    sample_cube(data, "testland", "Testland", seed=3, outline=OUTLINE2, neighbours=("slovakia",))
    sample_cube(data, "sk-part", "High Tatras", seed=5, outline=OUTLINE_STUDY, study=True)


class timed:
    """A part of the set-up timed into `times` (name -> seconds)."""

    def __init__(self, times: dict, name: str):
        self.times, self.name = times, name

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, *exc):
        self.times[self.name] = self.times.get(self.name, 0) + time.perf_counter() - self.start


def prepare(data: str, settings, run_folder: str | None = None, fresh: bool = False, times: dict | None = None):
    """The data folder's users, run, cubes, share link and problem report (serve's set-up, without the server):
    (session cookies by user, the run shown, the run's share token, the Jobs). A data folder whose marker has
    data_key()'s key keeps its clip run (when its folder is there) and its cubes; another key, no marker or `fresh`:
    built anew, the marker written at the end. `run_folder`: a saved run shown instead of the clip's (saved_run); the
    clip is then not made and the marker keeps the clip run it named."""
    import accounts as ac
    from jobs import Jobs

    times = {} if times is None else times
    with timed(times, "accounts and jobs"):
        users = ac.Accounts(data, settings)

        def session(user) -> str:  # one session a user: those of a start before ended (Admin's counts stay)
            users.revoke(user.id)
            return users.new_session(user.id)[0]
        admin = users.sign_in("github", "1", "admin")
        climber = users.sign_in("github", "11", "a climber")  # a user waiting for approval, in Admin's list
        walker = users.sign_in("github", "12", "a walker")  # approved, with the limits of the site
        users.set_status(walker.id, "approved")
        cookies = {"admin": session(admin), "walker": session(walker)}
        jobs = Jobs(data, public=True)
        for name, (subject, rigs) in RIGGERS.items():  # the Basic form's users with saved rigs
            rigger = users.sign_in("github", subject, name)
            users.set_status(rigger.id, "approved")
            users.set_unlimited(rigger.id, True)
            have = {rig["name"] for rig in jobs.rigs(rigger.id)}  # a --data-dir used before: its rigs are there
            for rig_name, values in rigs:
                if rig_name not in have:
                    jobs.add_rig(rigger.id, rig_name, values)
            cookies[name] = session(rigger)
    with timed(times, "the marker"):
        key = data_key()
        marker = read_marker(data)
    runs = os.path.join(data, "runs")
    same = not fresh and marker.get("key") == key  # the cubes made by this code
    clip = marker.get("run")  # the clip's run of a kept folder: kept while the code that made it is the same
    made_by = marker.get("run_key", marker.get("key"))
    stale = list(marker.get("stale") or [])  # clip runs replaced whose removal failed: tried again at every start
    replaced = []
    if not run_folder and clip and (fresh or made_by != key or
                                    not os.path.isfile(os.path.join(runs, clip, "run.json"))):
        stale.append(clip)  # one clip run in a kept folder: the one made before goes (its folder and its row)
        replaced, clip = [clip], None
    if stale and not run_folder:  # a --run start removes nothing (the run it shows may be one of them)
        with timed(times, "the old clip runs' removal"):
            for old in list(stale):
                try:
                    jobs.delete_run(old, runs)
                    stale.remove(old)
                except OSError as error:
                    print(f"the clip run {old} made before stays (tried again at the next start): {error}")
    if run_folder:  # a saved run shown: the clip stays as it is
        with timed(times, "the saved run's copy"):
            run = saved_run(data, run_folder)
    else:
        if not clip:
            with timed(times, "the clip's search"):
                clip = clip_run(data)
            made_by = key
        run = clip
    if not (same and all(os.path.isfile(os.path.join(data, "countries", country, "cube", "cube.json"))
                         for country in CUBES)):
        with timed(times, "the cubes"):
            sample_cubes(data)
    with timed(times, "accounts and jobs"):
        jobs.add_run(run, admin.id, 1)
        share = "ui-shots-share-" + "x" * 30
        digest = ac.digest(share)
        holder = jobs.shared_run(digest)  # the token is UNIQUE: taken from the run shown before
        if holder and holder != run:
            jobs.set_share(holder, None)
        jobs.set_share(run, digest)
        ours = [r for r in jobs.reports() if r["text"] == REPORT]
        if replaced:  # the report named the clip run replaced: made again for the run shown now
            for report in ours:
                jobs.delete_report(report["id"])
            ours = []
        if not ours:  # once per data folder
            jobs.add_report(climber.id, "water", REPORT,
                            {"run": run, "page": f"#run={run}", "ui": "c", "viewport": "390x844",
                             "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"})
    with timed(times, "the marker"):
        with open(os.path.join(data, MARKER), "w", encoding="utf-8") as f:
            json.dump({"key": key, "run": clip, "run_key": made_by if clip else None, "stale": stale}, f, indent=1)
    return cookies, run, share, jobs


def serve(data: str, run_folder: str | None = None, fresh: bool = False, times: dict | None = None):
    """The public site on a free port of 127.0.0.1, with a worker, over a data folder made ready by prepare;
    (address, session cookies by user, run, the run's share token, stop). `run_folder`: a saved run shown instead
    of the clip's (saved_run); `fresh`: the data folder's clip run and cubes made anew; `times`: the set-up's parts
    timed into it."""
    times = {} if times is None else times
    with timed(times, "the server's modules"):  # the web app's imports, its settings and a free port
        import uvicorn

        import web
        from jobs import Scheduler
        from settings import AccountSettings, PublicSettings

        os.environ.update(ACCOUNTS)
        settings = AccountSettings.load()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    site = f"https://localhost:{port}"
    cookies, run, share, jobs = prepare(data, settings, run_folder, fresh, times)
    start = time.perf_counter()
    scheduler = Scheduler(jobs, public=True)
    scheduler.start()
    public = PublicSettings(public_url=site, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(data, public=public, accounts=settings)
    cert_file, key_file = certificate(data)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           ssl_certfile=cert_file, ssl_keyfile=key_file))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)
    times["the server's start"] = time.perf_counter() - start

    def stop():
        server.should_exit = True
        scheduler.stop()
        thread.join(timeout=10)
    return site, cookies, run, share, stop


def select_pages(only: str = "", exclude: str = "") -> dict:
    """The pages of PAGES whose name contains one of `only`'s comma-separated parts (all for none), less those
    whose name contains one of `exclude`'s."""
    wanted = [w for w in only.split(",") if w]
    dropped = [w for w in exclude.split(",") if w]
    return {n: p for n, p in PAGES.items()
            if (not wanted or any(w in n for w in wanted)) and not any(w in n for w in dropped)}


def page_steps(steps) -> list:
    """A page's actions as a list of steps (one step, a list or None)."""
    return [steps] if isinstance(steps, str) else list(steps or [])


def page_storage(name: str) -> str:
    """The init script of a page: its kept layouts (LAYOUTS, LAYER_LAYOUTS) set, or removed for the defaults."""
    kept, layer = LAYOUTS.get(name), LAYER_LAYOUTS.get(name)
    return "try { " + (
        f"localStorage.setItem('findaline.layout', {json.dumps(json.dumps(kept))}); " if kept
        else "localStorage.removeItem('findaline.layout'); ") + (
        f"localStorage.setItem('findaline.layer.layout', {json.dumps(json.dumps(layer))}); " if layer
        else "localStorage.removeItem('findaline.layer.layout'); ") + "} catch (e) {}"


def page_url(site: dict, ui: str, hash_: str) -> str:
    """A page's address on the site (`site`: url, run, share, line, also, border)."""
    start = {"map": f"/runs/{site['run']}/map.html", "shared": f"/s/{site['share']}/map.html"}.get(
        ui, ui if ui.startswith("/") else f"/?ui={ui}")
    return f"{site['url']}{start}{hash_.format(run=site['run'], line=site['line'], also=site['also'], border=site['border'])}"


def page_family(name: str) -> str:
    """The family of a page, from its interface and hash: what says it is drawn (PAGE_STATE). The result view of
    line-volume round 4 (a table VIEWS beside LAYOUTS) is to be "view-b" here."""
    ui, hash_ = PAGES[name][:2]
    if ui.startswith("/view3d"):  # also "/view3d?level=..."
        return "view3d"
    if ui.startswith("/coverage"):
        return "coverage"
    if ui.startswith("/"):  # sign-in, privacy, about: the load event
        return "static"
    if ui in ("map", "shared") or hash_.startswith("#run="):
        return "result"
    if hash_.startswith("#new"):
        return "search"
    if hash_.startswith("#layer") or hash_ == "{border}":
        return "layer"
    return "home"  # Home, the menu, the account, favourites, Admin, OSM


class Requests:
    """A page's requests in flight, from Playwright's page events (the event stream EVENTS ignored: it never ends; the
    page's document too);
    `started` counts every request begun, so one that starts and ends between two looks is seen."""

    def __init__(self, page):
        self.flying, self.started = set(), 0
        page.on("request", self.start)
        page.on("requestfinished", self.end)
        page.on("requestfailed", self.end)

    def start(self, request):
        # the page's own document: the load waits for it, and WebKit never reports its end
        if EVENTS in request.url or request.is_navigation_request():
            return
        self.flying.add(request)
        self.started += 1

    def end(self, request):
        self.flying.discard(request)

    def words(self) -> list:
        """The requests in flight for a note: their addresses without the query (no key or token in a log)."""
        return sorted({r.url.split("?")[0] for r in self.flying})[:3]


def settled(page, family: str, limit_ms: int, quiet_ms: int = QUIET_MS, requests: Requests | None = None,
            line: bool = False, frames: bool = True) -> list:
    """Wait until the page is settled (QUIET_MS in a row with nothing busy: PAGE_STATE of its family, `requests`
    none in flight and none begun, no animation frame or short timer asked for, the frames not with `frames` False);
    at most `limit_ms`. [] when it settled, else what was still busy at the limit. A look every POLL_MS (the page's
    wait_for_timeout: Playwright's events of the requests come in during it)."""
    began = time.perf_counter()
    quiet_since, last = None, None
    while True:
        state = page.evaluate(PAGE_STATE, {"family": family, "line": line, "frames": frames})
        now = time.perf_counter()
        busy = list(state["busy"])
        if requests is not None and requests.flying:
            busy.append("requests in flight (" + ", ".join(requests.words()) + ")")
        counts = (state["asked"], state["timed"], requests.started if requests is not None else 0)
        if busy or (last is not None and counts != last):
            quiet_since = None
        elif quiet_since is None:
            quiet_since = now
        last = counts
        if quiet_since is not None and now - quiet_since >= quiet_ms / 1000:
            return []
        if now - began >= limit_ms / 1000:
            return busy or ["frames, timers or requests begun"]
        page.wait_for_timeout(POLL_MS)


class Watch:
    """What settles one page (shoot_page): its family, whether its address names a line, its requests; each wait
    that ends at its limit is noted in the row ("unsettled": after what, what was busy; the tiles also as
    "tiles_loading") and gets a quarter of its limit for the rest of the pass."""

    def __init__(self, page, name: str, state: "Pass", row: dict, label: str):
        self.page, self.name, self.state, self.row, self.label = page, name, state, row, label
        self.family, self.line = page_family(name), "&line=" in PAGES[name][1]
        self.requests = Requests(page)

    def settle(self, after: str, load: bool = False, frames: bool = True, quiet_ms: int | None = None):
        key = f"settled ({self.family}) after " + ("the load" if load else "a step")
        quiet = QUIET_MS if quiet_ms is None else quiet_ms
        busy = settled(self.page, self.family, self.state.limit(key, self.name), quiet, self.requests, self.line, frames)
        if busy:
            self.state.timed_out.add(key)
            self.row["unsettled"].append({"after": after, "busy": busy})
            self.row["tiles_loading"] = self.row["tiles_loading"] or TILES_NOTE in busy
            print(f"{self.label}: not settled after {short(after, 60)}: {', '.join(busy)}")

    def after_wait(self, step: str):
        """After a "wait:" or "need:" step: no quiet time (the step proved the state), two animation frames (a frame
        the state asked for is drawn: the 3D view's flags), then nothing busy."""
        self.page.evaluate(TWO_FRAMES)
        self.settle(step, quiet_ms=0)


class Pass:
    """One pass of the pages (a device and a theme): the waits that timed out in it (their later waits in the pass
    get a quarter of their limit) and whether a timeout or a failed step stops the run (--strict)."""

    def __init__(self, device: str, theme: str, strict: bool = False):
        self.device, self.theme, self.strict = device, theme, strict
        self.timed_out = set()

    def limit(self, expression: str, page: str | None = None) -> int:
        """The limit of a wait for `expression` on `page` (ms): WAIT_MS, FIRST_DRAW_MS for the first-draw marks
        (SLOW_MARKS' for its pages), the settled waits' (Watch's keys) SETTLE_LOAD_MS or SETTLE_STEP_MS (after a
        step of a page of SLOW_MARKS its limit: the settled wait after its click waits for the same estimate); a quarter
        after the expression's first timeout in the pass."""
        if expression.startswith("settled ("):  # a page of SLOW_MARKS: its steps' too (its family's mark is slow)
            base = SETTLE_LOAD_MS if expression.endswith("the load") else SLOW_MARKS.get(page, SETTLE_STEP_MS)
        elif expression in FIRST_DRAW:
            base = SLOW_MARKS.get(page, FIRST_DRAW_MS)
        else:
            base = WAIT_MS
        return base // 4 if expression in self.timed_out else base


def error_line(error: BaseException) -> str:
    """An error's first line (Playwright's messages go on with a call log)."""
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__


def short(step: str, size: int = 100) -> str:
    """A step as printed (its first `size` characters)."""
    return step if len(step) <= size else step[:size - 1] + "…"


def wait_until(page, expression: str, state: Pass, label: str, row: dict) -> bool:
    """Wait until `expression` is true in the page (at most the pass's limit for it): True when it came true; a
    timeout is printed, kept in `row["timeouts"]` and shortens the expression's later waits in the pass. A wait that
    GIVE_UP ends (its mark can no longer come) is printed and kept too, with its words, at once and without a quarter.
    Another error (the expression raised) goes on to the caller."""
    give_up, words = GIVE_UP.get(expression, (None, None))
    try:  # a function: an expression would need eval, which the CSP forbids
        page.wait_for_function(f"() => ({expression})" if give_up is None else f"() => ({expression}) || ({give_up})",
                               timeout=state.limit(expression, row.get("page")))
        if give_up is None or page.evaluate(f"!!({expression})"):
            return True
        print(f"{label}: gave up waiting for {expression}: {words}")
        row["timeouts"].append(f"{expression} (gave up: {words})")
        return False
    except Exception as error:
        if type(error).__name__ != "TimeoutError":  # playwright.sync_api.TimeoutError (not imported here)
            raise
    print(f"{label}: still waiting for {expression}")
    state.timed_out.add(expression)
    row["timeouts"].append(expression)
    return False


def run_step(page, step: str, label: str, state: Pass, row: dict, watch: Watch | None = None) -> str | None:
    """One step of a page (PAGES' actions) on a Playwright page: "missing" when the page is left out (a click
    finds nothing to click, a "need:" is false; the reason in `row`), "timeout" when a wait timed out, else None.
    After it the page is settled (`watch`: after a click, a script or a scroll the quiet time; after a wait two
    frames and nothing busy; none without a watch). What the page raises (a click Playwright cannot do, a script's
    error) goes on to the caller."""
    def settle(**kwargs):
        if watch is not None:
            watch.settle(step, **kwargs)
    if step.startswith("scroll:"):
        page.evaluate("(sel) => { const e = document.querySelector(sel) || "
                      "document.scrollingElement; e.scrollTop = e.scrollHeight; }", step[7:])
        settle()
        return None
    if step.startswith("js:"):
        page.evaluate(step[3:])
        settle()
        return None
    if step.startswith("wait:"):  # the 3D view: its terrain, then its imagery
        came = wait_until(page, step[5:], state, label, row)
        if watch is not None:
            watch.after_wait(step)
        return None if came else "timeout"
    if step.startswith("need:"):  # what the page shows, absent in this run: no page
        ready = wait_until(page, NEED_READY, state, label, row)  # the result drawn, then the expression once
        if not page.evaluate(f"!!({step[5:]})"):
            print(f"{label}: left out, this run does not have {step[5:]}")
            row["reason"] = f"the run does not have {step[5:]}"
            return "missing"
        if watch is not None:
            watch.after_wait(step)
        return None if ready else "timeout"
    if step.startswith("low:"):  # the last one, at the bottom of its panel
        page.evaluate(LOWEST, step[4:])
        step = "[data-shot-low]"
    target = page.query_selector(step)
    if not (target and target.is_visible()):
        row["reason"] = f"the device does not show {step}"
        return "missing"
    if step != "[data-shot-low]":
        target.scroll_into_view_if_needed()
    target.click()
    settle(frames=step not in SPINS)
    return None


TOO_LARGE = "Cannot take screenshot larger than"  # Playwright's error for a picture over its size limit


def shoot_page(context, site: dict, name: str, device: str, theme: str, out: str | None, state: Pass,
               act=None) -> dict:
    """One page from its load to its screenshot in a browser context: its record (seconds of the load, the settled
    wait after it, each step and the shot; the waits not settled; the outcome "saved", "left out" (on this device: a click
    finds nothing, or a "need:" is false), "timed out" (a wait timed out: the picture saved all the same, but not
    with --strict, and not when a later step then finds nothing: after a timeout that is no "left out", the reason
    kept) or "failed" (a step, the load or the shot raised: no picture); the picture's path; "scale":
    "css" when a whole page was too tall for its picture at the device's pixel ratio). `act(page, name, device,
    theme) -> dict`, for a caller that measures the prepared pages: called in place of the screenshot (the page
    open, after the last step; not for a page left out, nor with --strict after a timeout), its dict the row's
    "result", the outcome "done" (or "timed out"), `out` then unused; an exception from it fails only its page."""
    ui, hash_, steps, *who = PAGES[name]
    row = {"page": name, "device": device, "theme": theme, "outcome": None, "reason": None, "path": None,
           "load": None, "settle": None, "tiles": None, "tiles_loading": False, "steps": [], "shot": None,
           "seconds": None, "timeouts": [], "error": None, "unsettled": []}
    label = f"{name} ({device})"
    began = time.perf_counter()
    page = None
    try:
        context.clear_cookies()
        user = who[0] if who else "admin"
        if user != "visitor":
            context.add_cookies([{"name": "__Host-findaline", "value": site["cookies"][user],
                                  "domain": "localhost", "path": "/", "secure": True,
                                  "httpOnly": True, "sameSite": "Lax"}])
        page = context.new_page()  # a fresh page each: no menu or route of the one before
        page.set_default_timeout(CLICK_MS)
        page.set_default_navigation_timeout(LOAD_MS)
        page.add_init_script(page_storage(name))
        page.add_init_script(WATCH)
        watch = Watch(page, name, state, row, label)
        start = time.perf_counter()
        page.goto(page_url(site, ui, hash_))
        row["load"], start = time.perf_counter() - start, time.perf_counter()
        # settled (the event stream stays open: no "network idle"); the maps' tiles are part of it (OpenTopoMap can be
        # slow: an empty map is no finding, TILES_NOTE a note), so "tiles" stays 0. The 3D view: its first step waits
        # for its ready mark (FIRST_DRAW_MS), then it is settled
        if watch.family != "view3d":
            watch.settle("the load", load=True)
        row["settle"], row["tiles"] = time.perf_counter() - start, 0.0
        full = False
        for step in page_steps(steps):
            if step == "full":
                full = True
                continue
            start = time.perf_counter()
            try:
                result = run_step(page, step, label, state, row, watch)
            except Exception as error:
                row["steps"].append({"step": step, "seconds": time.perf_counter() - start, "outcome": "failed"})
                row["outcome"], row["error"] = "failed", error_line(error)
                print(f"{label}: step failed: {short(step)}: {row['error']}")
                return row
            row["steps"].append({"step": step, "seconds": time.perf_counter() - start, "outcome": result or "done"})
            if result == "missing":  # this device does not show it; after a wait that timed out, nobody knows
                row["outcome"] = "timed out" if row["timeouts"] else "left out"
                return row
            if result == "timeout" and state.strict:
                row["outcome"] = "timed out"
                return row
        start = time.perf_counter()
        if act is None:
            path = os.path.join(out, f"{name}-{device}-{theme}.png")
            try:
                page.screenshot(path=path, full_page=full, timeout=LOAD_MS)
            except Exception as error:
                if not (full and TOO_LARGE in str(error)):
                    raise
                # a whole page too tall at the device's pixel ratio (WebKit: at most 32767 picture pixels): one
                # picture pixel per CSS pixel; still too tall, a failure
                page.screenshot(path=path, full_page=True, timeout=LOAD_MS, scale="css")
                row["scale"] = "css"
                print(f"{label}: too tall at the device's pixel ratio, taken at one pixel per CSS pixel")
            row["path"] = path
        else:  # a caller's measurement in place of the picture
            row["result"] = act(page, name, device, theme)
        row["shot"] = time.perf_counter() - start
        row["outcome"] = "timed out" if row["timeouts"] else "saved" if act is None else "done"
    except Exception as error:  # the load, the shot or `act`
        row["outcome"], row["error"] = "failed", error_line(error)
        print(f"{label}: failed: {row['error']}")
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        row["seconds"] = time.perf_counter() - began
    return row


def failed(rows: list) -> bool:
    """Whether a wait of the pages timed out or a step failed (the exit code 1)."""
    return any(r["timeouts"] or r["outcome"] == "failed" for r in rows)


CLOSING = ("Playwright's stop", "the server's stop", "the temporary folder's removal")  # the summary's closing parts


def summary(times: dict, passes: list, rows: list, dropped: dict, total: float) -> list:
    """The lines printed at the end: seconds per part of the set-up and per pass, the ten slowest pages, the pages
    left out (those the run lacks once, by name; those a device does not show by page and passes), every timeout
    and failed step."""
    lines = [f"Summary: {total:.1f} s, {sum(1 for r in rows if r['path'])} pictures"]
    closing = [part for part in times if part.startswith("close ") or part in CLOSING]
    lines.append("Set-up: " + ", ".join(f"{part} {seconds:.1f} s" for part, seconds in times.items()
                                        if part not in closing))
    if closing:
        lines.append("Closing: " + ", ".join(f"{part} {times[part]:.1f} s" for part in closing))
    for p in passes:
        lines.append(f"Pass {p['device']} {p['theme']}: {p['seconds']:.1f} s, {p['saved']} saved, "
                     f"{p['left_out']} left out" + ("" if p.get("complete", True) else ", not finished"))
    slow = sorted((r for r in rows if r["seconds"] is not None), key=lambda r: -r["seconds"])[:10]
    if slow:
        lines.append("Slowest pages: " + ", ".join(f"{r['page']} ({r['device']} {r['theme']}) {r['seconds']:.1f} s"
                                                   for r in slow))
    for name, reason in dropped.items():
        lines.append(f"Left out: {name}: {reason}")
    out = {}
    for r in rows:
        if r["outcome"] == "left out":
            out.setdefault((r["page"], r["reason"]), []).append(f"{r['device']} {r['theme']}")
    for (name, reason), where in out.items():
        lines.append(f"Left out: {name}: {reason} ({', '.join(where)})")
    for r in rows:
        for expression in r["timeouts"]:
            lines.append(f"Timed out: {r['page']} ({r['device']} {r['theme']}): {expression}")
        if r["timeouts"] and r["reason"]:  # a later step then found nothing: not shot, and not "left out"
            lines.append(f"Timed out: {r['page']} ({r['device']} {r['theme']}): then {r['reason']}, no picture")
        if r["outcome"] == "failed":
            step = next((s["step"] for s in r["steps"] if s["outcome"] == "failed"), "the load or the shot")
            lines.append(f"Failed: {r['page']} ({r['device']} {r['theme']}): {short(step)}: {r['error']}")
    if any(r.get("scale") == "css" for r in rows):
        lines.append("Taken at one pixel per CSS pixel, too tall at the device's (a note): " + ", ".join(
            f"{r['page']} ({r['device']} {r['theme']})" for r in rows if r.get("scale") == "css"))
    if any(r["tiles_loading"] for r in rows):
        lines.append("Map tiles still loading (a note): " + ", ".join(
            f"{r['page']} ({r['device']} {r['theme']})" for r in rows if r["tiles_loading"]))
    unsettled = [(r, u) for r in rows for u in r.get("unsettled") or []]
    if unsettled:
        lines.append("Not settled, shot at the limit (a note): " + "; ".join(
            f"{r['page']} ({r['device']} {r['theme']}) after {short(u['after'], 60)}: {', '.join(u['busy'])}"
            for r, u in unsettled))
    return lines


def account_settings():
    """The dummy settings of the public site (ACCOUNTS) in the environment, and its AccountSettings."""
    from settings import AccountSettings
    os.environ.update(ACCOUNTS)
    return AccountSettings.load()


CONTEXT_SCRIPT = ("try {{ localStorage.setItem('findaline-theme', {theme}); "
                  + "".join(f"localStorage.removeItem('findaline.{key}'); " for key in
                            ("coverage.view", "coverage.scale", "coverage.lang", "layer.coverage"))
                  + "".join(f"localStorage.setItem('findaline.intro.{intro}', 'seen'); " for intro in INTROS)
                  + "}} catch (e) {{}}")


def themes_of(dark: bool, themes: str | None) -> list | None:
    """The themes of the passes from --dark (both) and --themes (light, dark or both; default light); None when
    the two differ."""
    if dark and themes not in (None, "both"):
        return None
    return ["light", "dark"] if dark or themes == "both" else [themes or "light"]


def pass_context(browser, pw, device: str, theme: str, **extra):
    """A pass's browser context: the device's profile (DESKTOP for the desktop), the theme, HTTPS errors of the run's
    certificate ignored, Chromium's motion sensors as a phone that allows them ("view3d-motion"; WebKit has no such
    permission), and CONTEXT_SCRIPT: the theme, the intros put away (ui/Intro.tsx: the "-intro" pages open them),
    the coverage page's choices and the place map's coverage layer as on a first visit. `extra` goes on to
    new_context (a caller's `bypass_csp=True`)."""
    engine, profile = DEVICES[device]
    options = dict(pw.devices[profile]) if profile else dict(DESKTOP)
    options.pop("default_browser_type", None)
    sensors = ["accelerometer", "gyroscope", "magnetometer"] if engine == "chromium" else []
    context = browser.new_context(**options, color_scheme=theme, ignore_https_errors=True, permissions=sensors,
                                  **extra)
    context.add_init_script(CONTEXT_SCRIPT.format(theme=json.dumps(theme)))
    return context


def shoot_all(pw, site: dict, shown: list, devices: list, themes: list, out: str | None, strict: bool, times: dict,
              rows: list, passes: list, act=None, on_row=None, **extra):
    """Every page of `shown` in a pass per device and theme (shoot_page; `act` and `extra` for a caller that measures
    the prepared pages: shoot_page's and pass_context's; `on_row(row)` called with each row once it is in `rows`,
    an error of it going on to the caller): each row added to `rows` as it is made, each pass's record
    to `passes` (its seconds from after its context is made, its pictures and pages left out; "complete" False
    when it was interrupted), so an interrupt keeps what was done. Launches, contexts and their closing are timed
    into `times`. `strict`: the run stops after the first row with a timeout or a failure."""
    stop = False
    for device in devices:
        engine = DEVICES[device][0]
        with timed(times, f"launch {engine} ({device})"):
            browser = getattr(pw, engine).launch()
        try:
            for theme in themes:
                with timed(times, f"context {device} {theme}"):
                    context = pass_context(browser, pw, device, theme, **extra)
                start, first, complete = time.perf_counter(), len(rows), False
                state = Pass(device, theme, strict)
                try:
                    for name in shown:
                        row = shoot_page(context, site, name, device, theme, out, state, act)
                        rows.append(row)
                        if on_row:
                            on_row(row)
                        if row["path"]:
                            print(f"{row['path']}  ({row['seconds']:.1f} s)")
                        if strict and failed([row]):
                            stop = True
                            break
                    complete = not stop
                finally:
                    done = rows[first:]
                    passes.append({"device": device, "theme": theme, "seconds": time.perf_counter() - start,
                                   "saved": sum(1 for r in done if r["path"] or "result" in r),
                                   "left_out": sum(1 for r in done if r["outcome"] == "left out"),
                                   "complete": complete})
                    close(context.close, times, f"close {device} {theme}")
                if stop:
                    break
        finally:
            close(browser.close, times, f"close {engine} ({device})")
        if stop:
            break


def close(call, times: dict, part: str, *args):
    """A closing call timed as `part`; while an error (Ctrl+C) is on its way out, an error of the call is printed and
    dropped, so the first one reaches the caller."""
    on_its_way = sys.exc_info()[0] is not None
    with timed(times, part):
        try:
            call(*args)
        except Exception as error:
            if not on_its_way:
                raise
            print(f"{part}: {error_line(error)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", help="folder of the screenshots (required but with --list)")
    parser.add_argument("--only", default="", help="pages whose name contains this (comma-separated)")
    parser.add_argument("--exclude", default="", help="then without the pages whose name contains this (comma-separated)")
    parser.add_argument("--devices", default="desktop,iphone,pixel", help="of: " + ", ".join(DEVICES))
    parser.add_argument("--themes", choices=("light", "dark", "both"), help="the themes (default: light)")
    parser.add_argument("--dark", action="store_true", help="the dark theme too (= --themes both)")
    parser.add_argument("--data-dir", help="a scratch data folder (default: a new temporary one, removed at the end); "
                                           "used again, it keeps its clip run and cubes while the code is the same; "
                                           "one run at a time per folder (a second start ends the first one's sessions)")
    parser.add_argument("--fresh", action="store_true", help="the data folder's clip run and cubes made anew")
    parser.add_argument("--run", help="a saved run's folder to show instead of the clip's (its cache in the data folder)")
    parser.add_argument("--line", help="the line of the line's pages (lat1,lon1,lat2,lon2; default: the run's first)")
    parser.add_argument("--list", action="store_true", help="list the pages (and those the run leaves out), no browser")
    parser.add_argument("--timings", help="a JSON file of the set-up's parts and every page's seconds and outcome")
    parser.add_argument("--strict", action="store_true", help="stop at the first wait that times out or failed step")
    args = parser.parse_args()
    if not args.out and not args.list:
        parser.error("the following arguments are required: --out")
    themes = themes_of(args.dark, args.themes)
    if themes is None:
        parser.error(f"--dark (both themes) and --themes {args.themes} differ")
    devices = args.devices.split(",")
    for device in devices:
        if device not in DEVICES:
            parser.error(f"unknown device {device!r} (of: {', '.join(DEVICES)})")
    pages = select_pages(args.only, args.exclude)

    began = time.perf_counter()
    data = args.data_dir or tempfile.mkdtemp(prefix="ui-shots-")
    times, passes, rows, dropped, stop = {}, [], [], {}, None
    try:
        if args.list:
            _, run, _, _ = prepare(data, account_settings(), args.run, args.fresh, times)
            dropped = left_out_by_run(pages, run_features(os.path.join(data, "runs", run)))
            for name in pages:
                print(f"{name}  left out: {dropped[name]}" if name in dropped else name)
            return 0
        os.makedirs(args.out, exist_ok=True)
        site, cookies, run, share, stop = serve(data, args.run, args.fresh, times)
        with timed(times, "the run's lines and border cell"):
            line = args.line or first_line(data, run)
            also = ";".join(first_line(data, run, k) for k in (40, 200))  # two other lines ("view3d-others")
            border = border_view(data)  # a cell of the sample cube the border cuts at the map's centre ("c-layer-border")
        site_of = {"url": site, "cookies": cookies, "run": run, "share": share, "line": line, "also": also,
                   "border": border}
        with timed(times, "the run's features"):
            dropped = left_out_by_run(pages, run_features(os.path.join(data, "runs", run)))
        for name, reason in dropped.items():
            print(f"{name}: left out, {reason}")
        shown = [name for name in pages if name not in dropped]
        with timed(times, "Playwright's start"):
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright()
            pw = playwright.__enter__()
        try:
            shoot_all(pw, site_of, shown, devices, themes, args.out, args.strict, times, rows, passes)
        finally:
            close(playwright.__exit__, times, "Playwright's stop", *sys.exc_info())
    finally:
        interrupted = sys.exc_info()[0] is not None
        if stop:
            close(stop, times, "the server's stop")
        if not args.data_dir:  # the folder made above (tools/clean_temp.py removes those of runs that did not end)
            with timed(times, "the temporary folder's removal"):
                gc.collect()  # SQLite connections left in reference cycles keep their files open on Windows
                shutil.rmtree(data, ignore_errors=True)
        total = time.perf_counter() - began
        code = 1 if failed(rows) else 0
        if not args.list:
            print("\n".join(summary(times, passes, rows, dropped, total)))
            if args.timings:
                with open(args.timings, "w", encoding="utf-8") as f:
                    json.dump({"setup": times, "left_out_by_run": dropped, "passes": passes, "pages": rows,
                               "total": total, "exit": code, "interrupted": interrupted}, f, indent=1)
    return code


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    sys.exit(main())
