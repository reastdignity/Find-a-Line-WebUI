"""The result view's default (step 3d, viewer/src/result/view/SpotColumns.tsx VIEW_DEFAULT, viewWanted, opensView): one
constant decides whether a run opens in the view; the address asks (`?view=b` the view, `?view=today` today's page)
and the browser remembers an answer other than the default under today's key ("findaline.view": "b" or "today"),
while an answer equal to the default forgets the kept one. With the constant false that is today's behaviour exactly
(`?view=b` remembered, `?view=today` ends it); with it true the view opens unless the address or the browser says
"today". A run the view cannot show (a store without the view's columns; a grid whose fit lies over FIT_MAX from an
anchor) opens today's page in both, with the same words as without the view, and the console says why. With the
browser's storage blocked the default holds and the address decides each load, and nothing throws.

The switch of the test: both settings are built here, each its own scratch bundle of app.js and viewer.js (esbuild with
a plugin that sets the constant's one line in SpotColumns.tsx; the build fails unless the line is there exactly once),
and Playwright serves them in place of /app/app.js and the map's _viewer/viewer.js (each test counts that it did). So
the test holds whatever dist holds, and no word of the address and no key of the browser switches it: a person has
only the page's own answers. Playwright's Edge over the app's server, offline, on the desktop and a phone. Run from
PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright, _server  # noqa: E402
import today_page  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
VIEWER = os.path.join(REPO, "viewer")
OLD = "2026-10-26_090000_Old_00000000000000a1"  # the clip's run with a store saved before the view's columns
FAR = "2026-10-26_090000_Far_00000000000000a2"  # the clip's run with one anchor 3 m off its grid: no fit within 0.5 m
DEVICES = {"desktop": DESKTOP, "phone": PHONE}
READY = "() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)"
WHICH = "() => window.FINDALINE_VIEW ? 'view' : window.FINDALINE_RESULT ? 'today' : null"
KEPT = "() => { try { return localStorage.getItem('findaline.view'); } catch (e) { return 'blocked'; } }"
BLOCKED = "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"
# The page's words outside the map (its attribution follows the run's credits, fetched by themselves)
TEXT = "() => { const b = document.body.cloneNode(true); b.querySelectorAll('.leaflet-container').forEach((e) => e.remove()); return b.textContent; }"
STILL = f"() => {{ const t = ({TEXT})(), same = t === window.STILL_TEXT; window.STILL_TEXT = t; return same; }}"

# The scratch build: app.js and viewer.js as viewer/build.mjs makes them, the constant's line set by a plugin (its
# count of the files it changed is printed; a source without the line exactly once fails the build)
BUILD = r"""
const esbuild = require("esbuild"), fs = require("fs");
const [out, value] = JSON.parse(process.argv[1]);
let hits = 0;
const flip = {name: "view-default", setup(build) {
  build.onLoad({filter: /[\\/]SpotColumns\.tsx$/}, (args) => {
    const text = fs.readFileSync(args.path, "utf8"), line = /export const VIEW_DEFAULT: boolean = (true|false);/g;
    const found = text.match(line) || [];
    if (found.length !== 1) throw new Error(found.length + " lines of VIEW_DEFAULT in " + args.path);
    hits++;
    return {contents: text.replace(line, "export const VIEW_DEFAULT: boolean = " + value + ";"), loader: "tsx"};
  });
}};
esbuild.build({entryPoints: {app: "src/app/app.tsx", viewer: "src/map/main.tsx"}, bundle: true, minify: true,
               format: "iife", target: "es2020", outdir: out, assetNames: "[name]-[hash]",
               loader: {".png": "dataurl", ".svg": "text", ".woff2": "file"}, logLevel: "warning", plugins: [flip]})
  .then(() => console.log(JSON.stringify({hits})), (e) => { console.error(String(e)); process.exit(1); });
"""


@pytest.fixture(scope="module")
def bundles(tmp_path_factory):
    """{default: its scratch folder with app.js and viewer.js} for both settings of the constant."""
    if not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")):
        pytest.skip("esbuild missing: npm ci in viewer/")
    built = {}
    for value in (False, True):
        out = tmp_path_factory.mktemp(f"default-{str(value).lower()}")
        done = subprocess.run(["node", "-e", BUILD, json.dumps([str(out), "true" if value else "false"])], cwd=VIEWER,
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout.strip().splitlines()[-1])["hits"] == 1, done.stdout
        assert (out / "app.js").is_file() and (out / "viewer.js").is_file()
        built[value] = out
    return built


def _far(folder):
    """The run's store with the first line's first anchor moved 3 m north (its latitude only; its grid place and the
    head's box as they were): the view's fit of the grid cannot come within 0.5 m of it (spots.ts FIT_MAX)."""
    import pyarrow as pa
    import linestore
    from test_web import store_with
    with pa.OSFile(str(folder / linestore.LINES_FILE), "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    field = table.schema.field("lat1")
    lat = table.column("lat1")[0].as_py() / 10 ** int(field.metadata[b"decimals"])
    store_with(folder, first={"lat1": lat + 3 / 111_195})


@pytest.fixture(scope="module")
def site(tmp_path_factory, view_clip):
    """A data folder with the clip's run (BIG), the same run saved before the view's columns (OLD) and with an anchor
    off its grid (FAR), served by the app; yields the address of the app's page (its query ?ui=c)."""
    import old_runs
    folder = tmp_path_factory.mktemp("view-default-data")
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, OLD, "Old clip")
    old_runs.drop_view(folder / "runs" / OLD)
    copy_clip(view_clip, folder, FAR, "Far clip")
    _far(folder / "runs" / FAR)
    page_path = stub_page(folder, "defaulttest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c", f"http://127.0.0.1:{port}"


def _context(browser, bundles, default: bool, device: str, script: str = ""):
    """A context of the device whose app.js and viewer.js are the scratch build of `default`; its page, the count of
    the bundles served and the page's errors and console lines."""
    ctx = browser.new_context(**DEVICES[device])
    served = []

    def serve(name):
        def answer(route):
            served.append(name)
            route.fulfill(path=str(bundles[default] / name), content_type="text/javascript; charset=utf-8")
        return answer
    ctx.route("**/app/app.js", serve("app.js"))
    ctx.route("**/_viewer/viewer.js", serve("viewer.js"))
    if script:
        ctx.add_init_script(script)
    page = ctx.new_page()
    page.served, page.errors, page.said = served, [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.on("console", lambda m: page.said.append(m.text))
    return page


def _load(page, address: str) -> str:
    """The page at the address (loaded anew: about:blank first), once a run is drawn: "view" or "today"."""
    page.goto("about:blank")
    page.goto(address)
    page.wait_for_function(READY, timeout=WAIT)
    return page.evaluate(WHICH)


def _with(address: str, query: str) -> str:
    """The address with `query` added to its query (before its hash)."""
    if not query:
        return address
    head, _, hash_ = address.partition("#")
    return f"{head}{'&' if '?' in head else '?'}{query}" + (f"#{hash_}" if hash_ else "")


@pytest.mark.parametrize("device", list(DEVICES))
@pytest.mark.parametrize("default", [False, True], ids=["default-today", "default-view"])
def test_the_default_and_the_answers(site, bundles, default, device):
    """The run without an answer opens in the default; `?view=b` and `?view=today` decide their load and the next
    ones; the browser keeps an answer only where it differs from the default ("b" kept with the constant false,
    "today" with it true; the other answer forgets it); a run's map.html follows the same answers."""
    from playwright.sync_api import sync_playwright
    app, origin = site
    run = f"{app}#run={BIG}"
    other = "b" if not default else "today"  # the answer the browser keeps
    expected = [  # (the address's query, the page, the browser's kept answer)
        ("", "view" if default else "today", None),
        ("view=b", "view", "b" if other == "b" else None),
        ("", "view", "b" if other == "b" else None),
        ("view=today", "today", "today" if other == "today" else None),
        ("", "today", "today" if other == "today" else None),
        ("view=b", "view", "b" if other == "b" else None),
        ("", "view", "b" if other == "b" else None),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _context(browser, bundles, default, device)
            for query, want, kept in expected:
                address = _with(run, query)
                assert (_load(page, address), page.evaluate(KEPT)) == (want, kept), address
            # the run's own map.html: the browser's answer (the view, kept or the default), then today's by its address,
            # which the app's page then keeps too
            map_html = f"{origin}/runs/{BIG}/map.html"
            assert _load(page, map_html) == "view"
            assert _load(page, _with(map_html, "view=today")) == "today"
            assert _load(page, run) == "today" and page.evaluate(KEPT) == ("today" if default else None)
            assert "app.js" in page.served and "viewer.js" in page.served
            assert page.errors == []
            # the pin of today's page (tools/today_page.py), in a fresh context: both of its forms open today's page
            pinned = _context(browser, bundles, default, device, today_page.SCRIPT)
            assert _load(pinned, run) == "today" and _load(pinned, map_html) == "today"
            assert _load(_context(browser, bundles, default, device), today_page.today(run)) == "today"
        finally:
            browser.close()


@pytest.mark.parametrize("device", list(DEVICES))
def test_runs_the_view_cannot_show(site, bundles, device):
    """A run saved before the view's columns and one whose grid has no fit within 0.5 m open today's page with either
    default, also when the view is asked for; the console says why; the page's words are the same with both defaults
    (the fallback adds no note)."""
    from playwright.sync_api import sync_playwright
    app, origin = site
    words = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for default in (False, True):
                for run, why in ((OLD, "no columns"), (FAR, "lies up to")):
                    for query in ("", "view=b"):
                        page = _context(browser, bundles, default, device)  # nothing kept from the load before
                        assert _load(page, _with(f"{app}#run={run}", query)) == "today", (default, run, query)
                        said = [t for t in page.said if "result view cannot show the run" in t]
                        if default or query:
                            assert said and all(run in t and why in t for t in said), (default, run, query, said)
                        else:
                            assert said == [], said  # the view not wanted: the run is not even checked
                        if query == "":
                            page.wait_for_function("() => !!document.querySelector('.r-rows [role=option]')", timeout=WAIT)
                            # the words once they hold still (the first fit of the map changes the legend's and the
                            # list's words for a moment): the same at two looks 400 ms apart
                            page.wait_for_function(STILL, polling=400, timeout=WAIT)
                            words[(default, run)] = page.evaluate(TEXT)
                        assert _load(page, f"{origin}/runs/{run}/map.html") == "today", (default, run, query)
                        served = {"app.js", "viewer.js"} <= set(page.served)  # both from the scratch build
                        assert page.errors == [] and served, (default, run, query, page.errors, page.served)
                        page.context.close()
            for run in (OLD, FAR):
                a, b = words[(False, run)], words[(True, run)]
                k = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                assert a == b, (run, a[max(0, k - 200):k + 300], b[max(0, k - 200):k + 300])
        finally:
            browser.close()


@pytest.mark.parametrize("default", [False, True], ids=["default-today", "default-view"])
def test_storage_blocked(site, bundles, default):
    """With the browser's storage blocked the default holds, the address decides its own load only, a run's map.html
    too, and nothing throws (the desktop; a phone takes the same function)."""
    from playwright.sync_api import sync_playwright
    app, origin = site
    run = f"{app}#run={BIG}"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _context(browser, bundles, default, "desktop", BLOCKED)
            seen = [_load(page, _with(run, q)) for q in ("", "view=today", "", "view=b", "")]
            first = "view" if default else "today"
            assert seen == [first, "today", first, "view", first]
            map_html = f"{origin}/runs/{BIG}/map.html"
            assert [_load(page, _with(map_html, q)) for q in ("", "view=today", "view=b")] == [first, "today", "view"]
            assert page.evaluate(KEPT) == "blocked" and page.errors == []
            assert {"app.js", "viewer.js"} <= set(page.served), page.served
        finally:
            browser.close()


def test_the_pin_of_todays_page():
    """tools/today_page.py: the address asks for today's page before its hash, another `view=` replaced; the default
    is read from the source's one line."""
    assert today_page.today("/?ui=c#run={run}") == "/?ui=c&view=today#run={run}"
    assert today_page.today("http://h:1/runs/x/map.html#line=1,2,3,4") == "http://h:1/runs/x/map.html?view=today#line=1,2,3,4"
    assert today_page.today("http://h:1/?ui=c&view=b#run=r") == "http://h:1/?ui=c&view=today#run=r"
    assert today_page.today("runs/t/index.html") == "runs/t/index.html?view=today"
    assert today_page.view_default() in (False, True)
    assert "'findaline.view', 'today'" in today_page.SCRIPT
