"""
Screenshots of the app for a visual review of a UI change (CLAUDE.md, "Verifying changes"): every page of
PAGES on a desktop (Chromium, 1400 × 900) and on two phones (Playwright's device profiles: iPhone 13 on
WebKit, Safari's engine; Pixel 7 on Chromium), each with its viewport, pixel ratio, touch and user agent,
in the light theme and optionally the dark one.

The site is the public one (signed in as an administrator, so Admin and the OSM extracts are there;
the "-limited" pages as an approved user with the site's limits), run
from a scratch data folder with a run of the Żabi Koń clip (tests/data, computed offline), the highline
layer of a sample cube of made-up counts (tests/test_country_web.py's sample_cube), a problem report and
a worker of this process (the estimates of a new search need its quick lane). It is served over
HTTPS with a certificate made for the run: WebKit, unlike Chromium, sends no Secure cookie (the session's
`__Host-` cookie) to http://localhost.

    uv sync --group ui
    uv run playwright install chromium webkit
    uv run tools/ui_shots.py --out <folder> [--only d-] [--dark]

The "map" pages are a run's own map.html (from the server and by its share link). The files are
<page>-<device>-<theme>.png; a page whose click finds nothing on a device is left out.
Phone screenshots of the viewport only (the shells scroll inside, not the page).

With ESRI_API_KEY set, the pages showing Esri's imagery ("map-esri", the "view3d" pages but "view3d-shaded" and
"view3d-edges") are for the review only: Esri's terms forbid storing or passing its imagery on, so delete them after
looking and never publish them.
"""

import argparse
import gc
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
# or a list of such steps[, the user: "admin" (default), "walker", an approved user with the site's limits, or "visitor",
# not signed in]); a step "full" takes the whole page, not only the viewport;
# "{run}" is the clip's run, "{line}" its first line (keys.lineCoords); an interface starting with "/" is a path of
# web.py's pages (the server-rendered ones and the 3D view's)
# Leaflet's layer control opened as its expand() does (hover on a desktop, a tap on a phone: neither is the
# same click on every device)
LAYERS_OPEN = "document.querySelector('.leaflet-control-layers').classList.add('leaflet-control-layers-expanded')"
ESRI_ON = ("[...document.querySelectorAll('.leaflet-control-layers-base label')].find((l) => "
           "l.textContent.trim() === 'Esri World Imagery')?.querySelector('input').click()")
# The coverage page: a click on an area of the flat view (by its key), and a wait for moving maps and tiles
COVERAGE_CLICK = "document.querySelector('.cov-shape[data-key=\"{key}\"]').dispatchEvent(new MouseEvent('click', {{bubbles: true}}))"
SETTLE = "new Promise((done) => setTimeout(done, 2500))"
ZOOM_OUT = "(window.FINDALINE_PLACE.map.setZoom(5), new Promise((done) => setTimeout(done, 2500)))"
# The section "Anchors" of a result's More filters in view: its terrain line in the middle (the anchors'
# heights and percentiles around it), else its heading at the top
ANCHORS_SHOWN = ("(() => { const t = document.querySelector('.r-terrain'); if (t) return t.scrollIntoView({block: 'center'}); "
                 "[...document.querySelectorAll('.r-more-sec > h3')].find((h) => h.textContent === 'Anchors')"
                 "?.scrollIntoView({block: 'start'}); })()")
# A click at the map's centre on what is there (the cells' canvas: Leaflet finds the cell under it)
CELL_AT_CENTRE = ("(() => { const map = window.FINDALINE_PLACE.map, box = map.getContainer().getBoundingClientRect(); "
                  "const p = map.getSize().divideBy(2), x = box.left + p.x, y = box.top + p.y; "
                  "const init = {bubbles: true, clientX: x, clientY: y}, e = document.elementFromPoint(x, y); "
                  "e.dispatchEvent(new MouseEvent('mousemove', init)); e.dispatchEvent(new MouseEvent('click', init)); })()")
MORE = [".s-more-head", ".s-topic:nth-of-type(2) > summary"]  # More settings, Anchors opened (Lines is)
# The 3D view drawn (its terrain and the found line's profile: view3d/main.ts) and its imagery loaded
VIEW3D_READY = ("wait:document.getElementById('view3d')?.dataset.ready === '1' && "
                "![...document.querySelectorAll('.v3-toolbar [role=status]')].some((e) => !e.hidden)")
SHADED_ON = ("js:[...document.querySelectorAll('.v3-toolbar [role=radio]')].find((b) => "
             "b.textContent.trim() === 'Shaded')?.click()")
# The "Edges" look chosen and drawn (view3d/scene.ts sets data-edges)
EDGES_ON = ("js:[...document.querySelectorAll('.v3-toolbar [role=radio]')].find((b) => "
            "b.textContent.trim() === 'Edges')?.click()")
EDGES_DRAWN = "wait:document.getElementById('view3d')?.dataset.edges === 'on'"
VIEW3D = "#run={run}&line={line}"
# The phone's motion (view3d/views.ts; its button only on touch screens): held upright facing north, then turned
# 40 degrees right and tilted 10 degrees up: two events with DeviceOrientationEvent's angles (WebKit on Windows
# cannot construct one)
MOTION_TURN = ("js:for (const [alpha, beta] of [[0, 90], [-40, 100]]) "
               "dispatchEvent(Object.assign(new Event('deviceorientation'), {alpha, beta, gamma: 0}))")
PAGES = {
    "d-home": ("d", "", None),
    "d-home-limited": ("d", "", None, "walker"),  # the usage meters of a user with the site's limits
    "d-menu": ("d", "", ".c-account-btn"),        # the account menu (desktop: a popover)
    "d-account": ("d", "#account", None),         # the account page (phones)
    "d-account-end": ("d", "#account", "scroll:.c-main"),
    "d-new": ("d", "#new", None),
    "d-new-hint": ("d", "#new", ".u-hint"),       # the first "?" of the search panel, its bubble open
    "d-new-intro": ("d", "#new", ".s-intro .n-intro-link"),  # "How a search works" (ui/Intro.tsx)
    "d-new-more": ("d", "#new", MORE),
    "d-new-more-hint": ("d", "#new", MORE + [".s-topics details[open] .u-hint"]),  # a setting's "?" (no bounds: admin)
    "d-new-low-hint": ("d", "#new", MORE + ["low:.s-topics details[open] .u-hint"]),  # the last "?" at the bottom: its bubble above it
    "d-new-limited": ("d", "#new", ".s-intro .n-intro-link", "walker"),  # the intro with the limits
    "d-new-limited-hint": ("d", "#new", MORE + [".s-topics details[open] .u-hint"], "walker"),  # a "?" with the bounds
    "d-result": ("d", "#run={run}", None),
    "d-result-intro": ("d", "#run={run}", ".r-filters .n-intro-link"),  # "How to read the result"
    "d-result-more": ("d", "#run={run}", [".r-filters .u-chip.u-add", "js:" + ANCHORS_SHOWN]),  # More filters: Anchors
    "d-result-credits": ("d", "#run={run}", ".u-credits-toggle"),  # the data credits unfolded (phones)
    "d-line": ("d", "#run={run}&line={line}", None),  # a line selected: its details, the "3D view" button
    "d-favourites": ("d", "#favourites", None),
    "d-admin": ("d", "#admin", None),
    "d-layer": ("d", "#layer", None),             # the highline layer of the sample cube (tests/test_country_web.py)
    "d-layer-cell": ("d", "#layer", "js:" + CELL_AT_CENTRE),  # its cell under the map's centre selected
    "d-osm": ("d", "#osm", None),
    "b-search": ("b", "#search", None),
    "b-search-hint": ("b", "#search", ".u-hint"),
    "b-search-low-hint": ("b", "#search", "low:.u-hint"),  # the last "?" at the bottom: its bubble above it
    "b-searches": ("b", "#searches", None),
    "b-result": ("b", "#run={run}", None),
    "b-admin": ("b", "#admin", None),
    "b-osm": ("b", "#osm", None),
    "c-home": ("c", "", None),
    "c-result": ("c", "#run={run}", None),
    "c-layer": ("c", "#layer", None),
    "map": ("map", "", None),
    "map-line": ("map", "", ".r-rows .r-row"),  # a spot selected: its details and profile
    "map-shared": ("shared", "", None),
    "map-credits": ("map", "", ".u-credits-toggle"),  # the data credits unfolded (phones: on a desktop no button)
    "map-layers": ("map", "", "js:" + LAYERS_OPEN),  # the base layers (Esri with ESRI_API_KEY set)
    "map-esri": ("map", "", "js:" + ESRI_ON),  # the satellite layer shown (ESRI_API_KEY set; else as "map")
    "map-shared-credits": ("shared", "", ".u-credits-toggle"),
    "d-new-coverage": ("d", "#new", [".n-coverage-btn", "js:" + ZOOM_OUT]),  # the data coverage on the place map
    "page-signin": ("/", "", None, "visitor"),
    "page-privacy": ("/privacy", "", None),
    "page-about": ("/about", "", None),
    # the coverage map (viewer/src/coverage/page): a visitor, its three views, a card, the table, Polish
    "page-coverage": ("/coverage?lang=en", "", None, "visitor"),
    "page-coverage-full": ("/coverage?lang=en", "", "full", "visitor"),
    "page-coverage-card": ("/coverage?lang=en", "", "js:" + COVERAGE_CLICK.format(key="pl"), "visitor"),
    "page-coverage-partly": ("/coverage?lang=en", "", ["js:" + COVERAGE_CLICK.format(key="de")], "visitor"),
    "page-coverage-europe": ("/coverage?lang=en", "", ".cov-zoombar button:nth-child(2)", "visitor"),
    "page-coverage-leaflet": ("/coverage?lang=en", "", [".cov-bar .u-seg button:nth-child(2)", "js:" + SETTLE,
                                                        ".cov-zoombar button:nth-child(2)", "js:" + SETTLE], "visitor"),
    "page-coverage-globe": ("/coverage?lang=en", "", [".cov-bar .u-seg button:nth-child(3)",
                                                      ".cov-zoombar button:nth-child(2)", "js:" + SETTLE], "visitor"),
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
}

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

INTROS = ("search", "result")  # the intros of ui/Intro.tsx (localStorage "findaline.intro.<name>")

DESKTOP = {"viewport": {"width": 1400, "height": 900}, "device_scale_factor": 1}
DEVICES = {"desktop": ("chromium", None), "iphone": ("webkit", "iPhone 13"), "pixel": ("chromium", "Pixel 7")}


def clip_run(data: str) -> str:
    """A run of the Żabi Koń clip in this data folder (offline, as tests/test_public.py's fixture)."""
    env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
           "PYTHONIOENCODING": "utf-8"}
    clip = os.path.join(REPO, "tests", "data", "zabi_kon_nmt.tif")
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", clip, "--northing", "254608", "--easting", "553966",
         "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
         "--nmpt", "off", "--name", "Żabi Koń clip", "--data-dir", data],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env=env)
    if result.returncode:
        sys.exit(result.stdout + result.stderr)
    runs = os.path.join(data, "runs")
    run = next(d for d in os.listdir(runs) if os.path.isfile(os.path.join(runs, d, "run.json")))
    with_credits(os.path.join(runs, run, "data.js"))
    return run


def first_line(data: str, run: str) -> str:
    """The first line of a run as its links name it (keys.lineCoords: the anchors of its data.js row)."""
    with open(os.path.join(data, "runs", run, "data.js"), encoding="utf-8") as f:
        row = json.loads(f.read().partition(" = ")[2].rstrip().rstrip(";"))["lines"][0]
    return ",".join(str(v) for v in row[:4])


def with_credits(path: str):
    """The credits of a run of geoportal.gov.pl filled with FABDEM in its data.js and run.json (a run of local
    files has none), so the map's and the 3D view's attribution are as long as a real run's (on a phone: folded
    behind their button)."""
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
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


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


def serve(data: str):
    """The public site on a free port of 127.0.0.1, with a worker; (address, session cookies by user, run,
    the run's share token, stop)."""
    import uvicorn

    import accounts as ac
    import web
    from jobs import Jobs, Scheduler
    from settings import AccountSettings, PublicSettings

    os.environ.update(ACCOUNTS)
    settings = AccountSettings.load()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site = f"https://localhost:{port}"
    users = ac.Accounts(data, settings)
    admin = users.sign_in("github", "1", "admin")
    cookie, _ = users.new_session(admin.id)
    climber = users.sign_in("github", "11", "a climber")  # a user waiting for approval, in Admin's list
    walker = users.sign_in("github", "12", "a walker")  # approved, with the limits of the site
    users.set_status(walker.id, "approved")
    cookies = {"admin": cookie, "walker": users.new_session(walker.id)[0]}
    jobs = Jobs(data, public=True)
    run = clip_run(data)
    sys.path.insert(0, os.path.join(REPO, "tests"))
    from test_country_web import sample_cube
    sample_cube(data)  # the highline layer's pages (#layer)
    jobs.add_run(run, admin.id, 1)
    share = "ui-shots-share-" + "x" * 30
    jobs.set_share(run, ac.digest(share))
    jobs.add_report(climber.id, "water", "The lake in the profile is 3 m too high near the second anchor.",
                    {"run": run, "page": f"#run={run}", "ui": "d", "viewport": "390x844",
                     "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"})
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

    def stop():
        server.should_exit = True
        scheduler.stop()
        thread.join(timeout=10)
    return site, cookies, run, share, stop


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="folder of the screenshots")
    parser.add_argument("--only", default="", help="pages whose name contains this (comma-separated)")
    parser.add_argument("--devices", default="desktop,iphone,pixel", help="of: " + ", ".join(DEVICES))
    parser.add_argument("--dark", action="store_true", help="the dark theme too")
    parser.add_argument("--data-dir", help="a scratch data folder (default: a new temporary one, removed at the end)")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    os.makedirs(args.out, exist_ok=True)
    data = args.data_dir or tempfile.mkdtemp(prefix="ui-shots-")
    site, cookies, run, share, stop = serve(data)
    line = first_line(data, run)
    wanted = [w for w in args.only.split(",") if w]
    pages = {n: p for n, p in PAGES.items() if not wanted or any(w in n for w in wanted)}
    themes = ["light", "dark"] if args.dark else ["light"]
    try:
        with sync_playwright() as pw:
            for device in args.devices.split(","):
                engine, profile = DEVICES[device]
                browser = getattr(pw, engine).launch()
                options = dict(pw.devices[profile]) if profile else dict(DESKTOP)
                options.pop("default_browser_type", None)
                for theme in themes:
                    # Chromium's motion sensors as a phone that allows them ("view3d-motion"; WebKit has no such
                    # permission)
                    sensors = ["accelerometer", "gyroscope", "magnetometer"] if engine == "chromium" else []
                    context = browser.new_context(**options, color_scheme=theme, ignore_https_errors=True,
                                                  permissions=sensors)
                    # the theme, and the intros put away (ui/Intro.tsx): the "-intro" pages open them; the
                    # coverage page's choices and the place map's coverage layer as on a first visit
                    context.add_init_script(f"try {{ localStorage.setItem('findaline-theme', {json.dumps(theme)}); "
                                            + "".join(f"localStorage.removeItem('findaline.{key}'); " for key in
                                                      ("coverage.view", "coverage.scale", "coverage.lang", "layer.coverage"))
                                            + "".join(f"localStorage.setItem('findaline.intro.{intro}', 'seen'); "
                                                      for intro in INTROS) + "} catch (e) {}")
                    for name, (ui, hash_, steps, *who) in pages.items():
                        context.clear_cookies()
                        user = who[0] if who else "admin"
                        if user != "visitor":
                            context.add_cookies([{"name": "__Host-findaline", "value": cookies[user],
                                                  "domain": "localhost", "path": "/", "secure": True,
                                                  "httpOnly": True, "sameSite": "Lax"}])
                        page = context.new_page()  # a fresh page each: no menu or route of the one before
                        start = {"map": f"/runs/{run}/map.html", "shared": f"/s/{share}/map.html"}.get(
                            ui, ui if ui.startswith("/") else f"/?ui={ui}")
                        page.goto(f"{site}{start}{hash_.format(run=run, line=line)}")
                        page.wait_for_timeout(2500)  # the event stream stays open: no "network idle"
                        try:  # the maps' tiles (OpenTopoMap can be slow): an empty map is no finding
                            page.wait_for_function("!document.querySelector('.leaflet-tile:not(.leaflet-tile-loaded)')",
                                                   timeout=10000)
                        except Exception:
                            print(f"{name} ({device}): map tiles still loading")
                        missing = full = False
                        for step in ([steps] if isinstance(steps, str) else steps or []):
                            if step == "full":
                                full = True
                                continue
                            if step.startswith("scroll:"):
                                page.evaluate("(sel) => { const e = document.querySelector(sel) || "
                                              "document.scrollingElement; e.scrollTop = e.scrollHeight; }", step[7:])
                                page.wait_for_timeout(400)
                                continue
                            if step.startswith("js:"):
                                page.evaluate(step[3:])
                                page.wait_for_timeout(600)
                                continue
                            if step.startswith("wait:"):  # the 3D view: its terrain, then its imagery
                                try:  # a function: an expression would need eval, which the CSP forbids
                                    page.wait_for_function(f"() => ({step[5:]})", timeout=60000)
                                except Exception:
                                    print(f"{name} ({device}): still waiting for {step[5:]}")
                                page.wait_for_timeout(600)
                                continue
                            if step.startswith("low:"):  # the last one, at the bottom of its panel
                                page.evaluate(LOWEST, step[4:])
                                step = "[data-shot-low]"
                            target = page.query_selector(step)
                            if not (target and target.is_visible()):
                                missing = True
                                break
                            if step != "[data-shot-low]":
                                target.scroll_into_view_if_needed()
                            target.click()
                            page.wait_for_timeout(600)
                        if missing:  # this device does not show it
                            page.close()
                            continue
                        path = os.path.join(args.out, f"{name}-{device}-{theme}.png")
                        page.screenshot(path=path, full_page=full)
                        page.close()
                        print(path)
                    context.close()
                browser.close()
    finally:
        stop()
        if not args.data_dir:  # the folder made above (tools/clean_temp.py removes those of runs that did not end)
            gc.collect()  # SQLite connections left in reference cycles keep their files open on Windows
            shutil.rmtree(data, ignore_errors=True)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main()
