"""The browser's bars in the ground of the theme the page shows (line volume round 7; the user's answer 21 to the
mock-up: an installed app's status bar is "its own strip in the page's ground"). Every page's head has two
theme-color lines, the light ground under the light scheme and the dark one under the dark (runs.HOME_SCREEN_HEAD);
a page that shows the theme chosen in the app (the app, the coverage map, a run's map.html, its disk notice) puts that
theme's ground into both (viewer/src/ui/bars.ts themeBars), and "auto" gives the head's values back. The function in
Node; the three pages in Playwright's Chromium with the system's scheme light and dark and the app's setting each
way: as the page starts, after a change of the setting, on the next page of the same tab, before the first frame;
pages without the lines and from disk."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runs as rn  # noqa: E402
import web  # noqa: E402
from test_public import TOKEN, clip_run, copy_run  # noqa: E402,F401

LIGHT, DARK = rn.GROUND_LIGHT, rn.GROUND_DARK
MEDIA = ("(prefers-color-scheme: light)", "(prefers-color-scheme: dark)")
RUN = "2026-11-25_100000_Bars_00000000000000d1"
THEME_KEY = "findaline-theme"  # viewer/src/ui/choice.ts


def bars(theme: str) -> list:
    """The two lines ([media, content]) as a page showing `theme` must have them."""
    if theme in ("light", "dark"):
        ground = LIGHT if theme == "light" else DARK
        return [[MEDIA[0], ground], [MEDIA[1], ground]]
    return [[MEDIA[0], LIGHT], [MEDIA[1], DARK]]  # the head's own


def _needs_node():
    if shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")):
        pytest.skip("needs Node and `npm install` in viewer/")


UNIT_SCRIPT = r"""
const fresh = () => { delete require.cache[require.resolve(BUNDLE)]; return require(BUNDLE); };
const asked = [];
const meta = (media, content) => {
  const m = {media, writes: 0, value: content};
  Object.defineProperty(m, "content", {get() { return this.value; }, set(v) { this.value = v; this.writes++; }});
  return m;
};
const page = (metas) => { globalThis.document = {querySelectorAll: (s) => { asked.push(s); return metas; }}; return metas; };
const lines = (metas) => metas.map((m) => [m.media, m.content, m.writes]);
const head = () => [meta("(prefers-color-scheme: light)", LIGHT), meta("(prefers-color-scheme: dark)", DARK)];
const out = {};
let m = fresh(), metas = page(head());
out.served = ["auto", "light", "dark", "light", "auto", "auto"].map((t) => { m.themeBars(t); return lines(metas); });
m = fresh(); metas = page(head());  // a page that starts with a stored choice: the head's values kept for "auto"
out.started = ["dark", "auto"].map((t) => { m.themeBars(t); return lines(metas); });
m = fresh(); page([]);
m.themeBars("dark");
out.none = "no error";
m = fresh(); delete globalThis.document;
m.themeBars("light");
out.no_document = "no error";
const others = {
  one: [meta("", "#ffffff")],
  three: [...head(), meta("", "#ffffff")],
  both_light: [meta("(prefers-color-scheme: light)", LIGHT), meta("(prefers-color-scheme: light)", DARK)],
  no_media: [meta("", LIGHT), meta("", DARK)],
};
out.others = Object.fromEntries(Object.entries(others).map(([k, v]) => { m = fresh(); page(v); m.themeBars("dark");
                                                                         return [k, lines(v)]; }));
m = fresh(); metas = [];  // the lines only after the first call: taken at the first call that finds them
globalThis.document = {querySelectorAll: () => metas};
m.themeBars("dark");
metas = head();
m.themeBars("dark");
out.later = lines(metas);
out.asked = [...new Set(asked)];
console.log(JSON.stringify(out));
"""


def test_the_function(tmp_path):
    """themeBars on made-up heads: the head as served under each setting and back to "auto" (no line written while
    it already holds its value), a page that starts with a chosen theme, a page without the lines or without a
    document (nothing, no error), heads not of exactly one light and one dark line (left as they are), the lines found
    only at a later call."""
    _needs_node()
    bundle = tmp_path / "bars.cjs"
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['src/ui/bars.ts'], bundle: true, "
                                  f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=VIEWER, check=True)
    script = tmp_path / "bars-test.cjs"
    script.write_text(f"const BUNDLE = {json.dumps(str(bundle))}, LIGHT = {json.dumps(LIGHT)}, "
                      f"DARK = {json.dumps(DARK)};\n" + UNIT_SCRIPT, encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8",
                                    check=True).stdout)
    lo, hi = MEDIA
    assert out["served"] == [[[lo, LIGHT, 0], [hi, DARK, 0]],
                             [[lo, LIGHT, 0], [hi, LIGHT, 1]],
                             [[lo, DARK, 1], [hi, DARK, 2]],
                             [[lo, LIGHT, 2], [hi, LIGHT, 3]],
                             [[lo, LIGHT, 2], [hi, DARK, 4]],
                             [[lo, LIGHT, 2], [hi, DARK, 4]]]
    assert out["started"] == [[[lo, DARK, 1], [hi, DARK, 0]], [[lo, LIGHT, 2], [hi, DARK, 0]]]
    assert out["none"] == out["no_document"] == "no error"
    assert out["others"] == {"one": [["", "#ffffff", 0]],
                             "three": [[lo, LIGHT, 0], [hi, DARK, 0], ["", "#ffffff", 0]],
                             "both_light": [[lo, LIGHT, 0], [lo, DARK, 0]],
                             "no_media": [["", LIGHT, 0], ["", DARK, 0]]}
    assert out["later"] == [[lo, DARK, 1], [hi, DARK, 0]]
    assert out["asked"] == ['meta[name="theme-color"]']


# ---- the pages in a browser -------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def site(clip_run, tmp_path_factory):
    """The local app on a real server (uvicorn in a thread) over a data folder with the clip's run (its store, its
    map.html as a search writes it today) and that page without the two lines (plain.html: a map.html saved before
    round 7): {"url", "folder" (the run's folder)}."""
    import uvicorn

    import mapping
    data = tmp_path_factory.mktemp("bars")
    folder = copy_run(clip_run, data, RUN, "Bars run")
    mapping.install_viewer(str(data / "runs"))
    rn.write_index(str(data / "runs"))
    page = (folder / "map.html").read_text("utf-8")
    assert page.count(rn.HOME_SCREEN_HEAD + "\n") == 1
    (folder / "plain.html").write_text(page.replace(rn.HOME_SCREEN_HEAD + "\n", ""), "utf-8")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(web.create_app(str(data), token=TOKEN, port=port, start_scheduler=False),
                                           host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "the server did not start"
        time.sleep(0.05)
    try:
        yield {"url": f"http://127.0.0.1:{port}", "folder": folder}
    finally:
        server.should_exit = True
        thread.join(10)


NOT_INSTALLED = "executable doesn't exist"  # Playwright's words for a browser not installed (as on CI)


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            launched = p.chromium.launch()
        except Exception as e:
            if NOT_INSTALLED in str(e).lower():
                pytest.skip(f"Playwright's browser is not installed: {str(e).splitlines()[0]}")
            raise
        try:
            yield {"browser": launched, "phone": {k: v for k, v in p.devices["Pixel 7"].items()
                                                  if k != "default_browser_type"}}
        finally:
            launched.close()


# The page's lines as the browser has them (the attributes it reads), and what the page shows: its root's --bg and the
# content of the line whose media matches the system's scheme now
BARS_JS = """() => [...document.querySelectorAll('meta[name="theme-color"]')]
  .map((m) => [m.getAttribute("media"), m.getAttribute("content")])"""
SHOWN_JS = """(root) => ({bg: getComputedStyle(document.querySelector(root)).getPropertyValue("--bg").trim(),
  bar: [...document.querySelectorAll('meta[name="theme-color"]')].filter((m) => matchMedia(m.media).matches)
    .map((m) => m.content)})"""

# Each page: its address, what shows it settled, its theme's root
PAGES = {"app": ("/", ".c-app .c-card", ".c-app"),
         "coverage": ("/coverage", ".cov [data-row]", ".ui.cov"),
         "map": (f"/runs/{RUN}/map.html", "#map .leaflet-container", "#map > .ui")}


def _context(browser, scheme: str, stored=None):
    """A phone's context with the system's scheme `scheme` and, when given, the app's setting kept before every
    page of it starts (the intros put away); in English (the coverage map takes the browser's language)."""
    context = browser["browser"].new_context(**browser["phone"], color_scheme=scheme, locale="en-US")
    keep = f"localStorage.setItem({json.dumps(THEME_KEY)}, {json.dumps(stored)});" if stored else ""
    context.add_init_script("try { " + keep + " for (const k of ['search', 'result']) "  # ui_shots.py INTROS
                            "localStorage.setItem('findaline.intro.' + k, 'seen'); } catch (e) {}")
    return context


def _open(context, url: str, settled: str):
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_selector(settled, state="attached", timeout=60000)
    return page


def _shown(page, root: str, theme: str) -> dict:
    """The page's lines and what it shows; the lines must say the ground of `theme` and the line the browser takes
    the page's own ground."""
    found = {"bars": page.evaluate(BARS_JS), **page.evaluate(SHOWN_JS, root)}
    assert found["bars"] == bars(theme) and found["bar"] == [found["bg"]], (page.url, theme, found)
    return found


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_bars_as_a_page_starts(site, browser, scheme):
    """The app, the coverage map and a run's map.html (the result view of its store), with the system's scheme
    light or dark and the app's setting not made, auto, light or dark: once settled, the two lines say the ground
    of the theme the page shows, the line the browser takes being the page's own --bg; the address's ?theme= of the
    app over the setting; a change of the system's scheme afterwards: "auto" follows it by the head's own lines, a
    chosen theme stays. No page error."""
    other = "dark" if scheme == "light" else "light"
    for stored in (None, "auto", "light", "dark"):
        context = _context(browser, scheme, stored)
        try:
            for name, (path, settled, root) in PAGES.items():
                page = _open(context, site["url"] + path, settled)
                shows = stored if stored in ("light", "dark") else "auto"
                _shown(page, root, shows)
                page.emulate_media(color_scheme=other)
                page.wait_for_function("(dark) => matchMedia('(prefers-color-scheme: dark)').matches === dark",
                                       arg=other == "dark")
                _shown(page, root, shows)
                assert page.errors == [], (name, stored, page.errors)
                page.close()
            if stored == "light":  # the address's theme over the kept one
                page = _open(context, site["url"] + "/?theme=dark", PAGES["app"][1])
                _shown(page, PAGES["app"][2], "dark")
                page.close()
        finally:
            context.close()


def _choose(page, label: str):
    """The theme `label` in the page's own control (the app's account, the coverage map's header)."""
    page.get_by_role("radiogroup", name="Theme").get_by_role("radio", name=label, exact=True).click()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_bars_follow_a_change_and_the_next_page(site, browser, scheme):
    """No setting kept at the start (a context without any): the app's account changes the theme, and the lines
    follow at once, no reload (read right after the click); the app's own pages (the hash) keep them; the next page
    of the same tab (a run's map.html, the coverage map) starts with them; the coverage map's own control changes
    them, "Auto" gives the head's values back, and the app opened again in the tab shows that."""
    context = _context(browser, scheme)
    try:
        app = PAGES["app"]
        page = _open(context, site["url"] + "/#account", ".c-app [role=radiogroup]")
        _shown(page, app[2], "auto")
        for label, theme in (("Dark", "dark"), ("Light", "light"), ("Auto", "auto"), ("Dark", "dark")):
            _choose(page, label)
            assert page.evaluate(BARS_JS) == bars(theme), (scheme, label)
            _shown(page, app[2], theme)
        for route in ("#home", "#favourites", "#home"):
            page.evaluate("(hash) => { location.hash = hash; }", route)
            page.wait_for_function("(hash) => location.hash === hash", arg=route)
            _shown(page, app[2], "dark")
        page.wait_for_selector(app[1], state="attached")
        for name in ("map", "coverage"):
            path, settled, root = PAGES[name]
            page.goto(site["url"] + path)
            page.wait_for_selector(settled, state="attached", timeout=60000)
            _shown(page, root, "dark")
        root = PAGES["coverage"][2]
        for label, theme in (("Light", "light"), ("Auto", "auto")):
            _choose(page, label)
            assert page.evaluate(BARS_JS) == bars(theme), (scheme, label)
            _shown(page, root, theme)
        page.goto(site["url"] + "/")
        page.wait_for_selector(app[1], state="attached", timeout=60000)
        _shown(page, app[2], "auto")
        assert page.errors == [], page.errors
    finally:
        context.close()


# Before the page's first script: at the first frame after the page's themed root entered the document, the lines as
# the browser has them then (a frame's animation callbacks run before it is drawn), the first such root's time and
# the first and the first contentful paint
FRAME_SCRIPT = """
window.__frame = null;
new MutationObserver((records, observer) => {
  if (!records.some((r) => [...r.addedNodes].some((n) => n.nodeType === 1
        && (n.matches('.ui[data-theme]') || n.querySelector('.ui[data-theme]'))))) return;
  observer.disconnect();
  const root = performance.now();
  requestAnimationFrame(() => { window.__frame = {root, frame: performance.now(),
    bars: [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => [m.getAttribute("media"),
                                                                                   m.getAttribute("content")])}; });
}).observe(document, {childList: true, subtree: true});
"""


def test_bars_before_the_first_frame(site, browser):
    """A page that starts with a theme kept against the system's (each page; dark on a light system, light on a dark
    one): at the first frame after its themed root entered the document, before that frame is drawn, the lines say
    that theme's ground already (the page's first render sets them, before any frame shows the page)."""
    for scheme, stored in (("light", "dark"), ("dark", "light")):
        context = _context(browser, scheme, stored)
        context.add_init_script(FRAME_SCRIPT)
        try:
            for name, (path, settled, _) in PAGES.items():
                page = _open(context, site["url"] + path, settled)
                page.wait_for_function("() => window.__frame !== null")
                frame = page.evaluate("window.__frame")
                assert frame["bars"] == bars(stored), (name, scheme, frame)
                page.close()
        finally:
            context.close()


def test_pages_without_the_lines_and_from_disk(site, browser, tmp_path):
    """A map.html saved before round 7 (no theme-color lines) over http with a theme kept: the result view as before,
    no line added, no page error. From disk (file://, no run loads: the disk notice in the kept theme): today's page
    gets the lines of its theme (dark kept; "auto" keeps the head's), the page of before none, neither an error."""
    folder = tmp_path / "runs" / RUN
    folder.mkdir(parents=True)
    for name in ("map.html", "plain.html"):
        shutil.copy(site["folder"] / name, folder / name)
    shutil.copytree(web.APP_DIST, tmp_path / "runs" / rn.VIEWER_FOLDER)
    context = _context(browser, "light", "dark")
    try:
        page = _open(context, site["url"] + f"/runs/{RUN}/plain.html", PAGES["map"][1])
        assert page.evaluate(BARS_JS) == [] and page.errors == [], page.errors
        assert page.evaluate("() => getComputedStyle(document.querySelector('#map > .ui')).getPropertyValue('--bg')"
                             ".trim()") == DARK
        page.close()
        for name, expected in (("map.html", bars("dark")), ("plain.html", [])):
            page = _open(context, (folder / name).as_uri(), f"#{rn.DISK_NOTICE}[data-theme=dark]")
            assert page.evaluate(BARS_JS) == expected and page.errors == [], (name, page.errors)
            page.close()
    finally:
        context.close()
    context = _context(browser, "dark", "auto")
    try:
        page = _open(context, (folder / "map.html").as_uri(), f"#{rn.DISK_NOTICE}")
        page.wait_for_function("() => document.readyState === 'complete'")
        assert page.evaluate(BARS_JS) == bars("auto") and page.errors == [], page.errors
        page.close()
    finally:
        context.close()
