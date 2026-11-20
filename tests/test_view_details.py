"""Step 3c of the result view's details and list (viewer/src/result/view/SpotActions.tsx, SpotDetails.tsx, SpotList.tsx,
ViewFilters.tsx; FavouritePicker.tsx's `icon` and `onOpen`): today's features in the accepted mock-up's places (the
user's gate 1 of 2026-11-20: "11 a", "4 d", "10 a"). The star in the line's head with today's folder picker; the line's
actions under "Stands for" (3D view with the spot's passing lines as `&also=`, Copy link and its field, Profile after
the profile was closed; no "Zoom"); "Report this line" below the facts; a phone's profile dock under the four values;
the list's stars (the row button's sibling, the arrows' column, today's names and rule); the list's two help buttons;
the model's note first in the list (a link's, a favourite's failure, with today's x: the planner's choice). Playwright's
Edge over the app's server, offline, under the app's CSP, on the result view's clip run (clip_runs.view_clip). Every
wait is an event with a deadline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG, copy_clip, stub_page  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, WAIT, WORDS, _open, _state, site, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
PIXEL = {"viewport": {"width": 412, "height": 915}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}
DEVICES = [DESKTOP, PHONE]
IDS = ["desktop", "phone"]
OTHERS_MAX = 20  # view3d/page.ts OTHERS_MAX
# A line outside the run (as the 3D view's moved anchors give it): measured by the server, stubbed here (80 m)
OUTSIDE = "49.5,19.1,49.5004,19.1005"
PROFILE_STUB = """
const realFetchOfDetails = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile") || !String(url).includes("49.5004")) return realFetchOfDetails(url, init);
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
"""
# A favourite's save refused by the server (FAIL_SAVES set)
SAVE_STUB = """
const realFetchOfSaves = window.fetch;
window.fetch = (url, init) => {
  if (window.FAIL_SAVES && /\\/favourites$/.test(String(url)) && init && init.method === "POST") {
    return Promise.resolve(new Response(JSON.stringify({detail: "the test refuses it"}), {status: 500, headers: {"content-type": "application/json"}}));
  }
  return realFetchOfSaves(url, init);
};
window.REPORTS = [];
window.addEventListener("findaline-report", (e) => REPORTS.push(e.detail));
"""

# The page's helpers of the checks (after test_shell_c_view_map's T)
DETAILS = r"""
window.D = {
  v() { return window.FINDALINE_VIEW.view; },
  m() { return this.v().model; },
  size(el) { if (!el) return null; const b = el.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; },
  box(sel) { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; },
  // the star of the line's head (desktop: the details' head; phone: the sheet's head)
  star() { const b = document.querySelector('.vl-dhead .r-fav, .vl-sheet-row .r-fav');
    return b && {name: b.getAttribute('aria-label'), title: b.title, expanded: b.getAttribute('aria-expanded'), filled: !!b.querySelector('svg.u-fav'),
                 size: this.size(b), icon: b.classList.contains('u-ib'), text: b.textContent.trim(), head: !!b.closest('.vl-dhead, .vl-sheet-row'),
                 beforeClose: b.closest('.r-popwrap')?.nextElementSibling?.classList.contains('vl-dclose') ?? false}; },
  // the server's favourites of the run
  saved() { return fetch('/api/runs/' + encodeURIComponent(this.m().runId) + '/favourites').then((r) => r.json())
    .then((b) => Array.isArray(b) ? {lines: b, in: {}} : b); },
  link(row) { const m = this.m(); return m.lineLink(m.lineAt(row)); },
  // the 3D view's other lines of the selected line: its spot's passing lines but itself, in the spot's order, at most 20
  also() { const v = this.v(), s = v.selected; return Array.from(v.passingOf(s.spot)).filter((r) => r !== s.row).slice(0, %d).map((r) => this.link(r)); },
  // the details' parts in their order, by their first class
  parts() { const d = document.querySelector('.vl-details'); return d ? [...d.children].map((e) => e.className.split(' ')[0]) : null; },
  kids(sel) { const e = document.querySelector(sel); return e ? [...e.children].filter((c) => !c.hidden).map((c) => c.className.split(' ')[0]) : null; },
  // a list's rows: each item's children, the star's name, title, state, size and tab index
  stars(sel) { return [...document.querySelectorAll(sel + ' .vl-rows > li')].map((li) => { const s = li.querySelector(':scope > .vl-star');
    return {kids: [...li.children].map((c) => c.className.split(' ')[0]), row: +li.querySelector('.vl-main').dataset.row,
            star: s && {name: s.getAttribute('aria-label'), title: s.title, pressed: s.getAttribute('aria-pressed'), tab: s.tabIndex, size: this.size(s),
                        filled: !!s.querySelector('svg.u-fav')}, halo: !!li.querySelector('.vl-sw.vl-sw-fav')}; }); },
  focus() { const a = document.activeElement; return !a || a === document.body ? '' : a.className; },
  snap() { const s = document.querySelector('.u-sheet'); return s ? ['peek', 'half', 'full'].find((k) => s.classList.contains('u-' + k)) : null; },
  // a box's middle, px
  mid(el) { const b = el.getBoundingClientRect(); return (b.top + b.bottom) / 2; },
};
""" % OTHERS_MAX
SCRIPT = DETAILS + SAVE_STUB


def _view(page, phone: bool = False):
    """The view drawn, with its favourites known (the server answered: the stars are drawn), the hint dismissed."""
    page.wait_for_function("() => !!window.FINDALINE_VIEW && D.m().favouritesOn", timeout=WAIT)
    _state(page)


def _select(page, spot_js: str = "view.order[0]"):
    _state(page, f"view.select({spot_js});")
    page.wait_for_selector(".vl-details", timeout=WAIT)


def _sheet(page, stop: str):
    """A phone's sheet to a stop by its handle's arrow keys, awaited."""
    order = ["peek", "half", "full"]
    now = page.evaluate("() => D.snap()")
    while now != stop:
        page.focus(".u-sheet-handle")
        page.keyboard.press("ArrowUp" if order.index(stop) > order.index(now) else "ArrowDown")
        nxt = order[order.index(now) + (1 if order.index(stop) > order.index(now) else -1)]
        page.wait_for_function(f"() => D.snap() === '{nxt}'", timeout=WAIT)
        now = nxt


@pytest.mark.parametrize("device", DEVICES, ids=IDS)
def test_star_in_the_head_opens_the_picker(site, device):
    """The star (11 a) is an icon in the line's head, before its x (desktop: the details' head; a phone: the sheet's head,
    in reach at the low stop), with today's names ("Add to favourites", once a favourite "Favourite" titled "In
    Favourites"); it opens today's folder picker (a phone's sheet rises to full for it), inside the page's width and the
    details' column; Esc closes the picker, not the selection; a folder saves the line on the server, the star fills and
    the list's row of the spot shows it; "Remove from favourites" ends it."""
    from playwright.sync_api import sync_playwright
    phone = device is PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            _select(page)
            spot = page.evaluate("() => D.v().selected.spot")
            star = page.evaluate("() => D.star()")
            assert star == {"name": "Add to favourites", "title": "Add to favourites", "expanded": "false", "filled": False,
                            "size": [44, 44] if phone else [32, 32], "icon": True, "text": "", "head": True, "beforeClose": True}, star
            if phone:
                assert page.evaluate("() => D.snap()") == "peek" and page.evaluate("() => !!document.querySelector('.u-sheet-head .r-fav')")
            # today's worded button is not there: the details hold one star, in the head
            assert page.evaluate("() => document.querySelectorAll('.vl-details .r-fav, .u-sheet .r-fav').length") == 1
            page.click(".r-fav")
            page.wait_for_selector(".r-picker", timeout=WAIT)
            if phone:
                page.wait_for_function("() => D.snap() === 'full'", timeout=WAIT)
            page.wait_for_function("() => D.star().expanded === 'true'", timeout=WAIT)
            panel = page.evaluate("() => D.box('.r-pop')")
            assert panel[0] >= 0 and panel[2] <= page.viewport_size["width"], panel
            if not phone:
                column = page.evaluate("() => D.box('.c-col-details')")
                assert panel[0] >= column[0] and panel[2] <= column[2], (panel, column)
            folders = page.evaluate("() => [...document.querySelectorAll('.r-folder')].map((b) => b.textContent.trim())")
            assert folders[0] == "Favourites (top level)"
            assert page.evaluate("() => document.querySelector('.r-picker .u-h4').textContent") == "Save to a folder"
            # Esc (once the picker took the focus, a frame after it opened): the picker goes, the selection stays, the
            # focus back on the star
            page.wait_for_function("() => !!document.activeElement.closest('.r-pop')", timeout=WAIT)
            page.keyboard.press("Escape")
            page.wait_for_selector(".r-picker", state="detached", timeout=WAIT)
            assert page.evaluate("() => [D.v().selected?.spot, document.activeElement === document.querySelector('.r-fav')]") == [spot, True]
            # a folder: the line saved on the server, the star filled with today's name and title
            page.click(".r-fav")
            page.wait_for_selector(".r-picker .r-folder", timeout=WAIT)
            page.click(".r-picker .r-folder")
            page.wait_for_function("() => D.star().filled && D.star().name === 'Favourite'", timeout=WAIT)
            link = page.evaluate("() => D.m().lineLink(D.v().selected.line)")
            page.wait_for_function(f"() => D.saved().then((s) => s.lines.includes({link!r}))", timeout=WAIT)
            assert page.evaluate("() => D.star().title") == "In Favourites"
            # the list's row of the spot: its star pressed, its dash with the halo
            if phone:
                _sheet(page, "full")
            page.wait_for_function(f"() => D.stars('.vl-tree').concat(D.stars('.vl-topblock')).some((r) => r.row === D.v().selected.row && r.star.pressed === 'true' && r.halo)",
                                   timeout=WAIT)
            # "Remove from favourites" in the picker ends it (on the server too)
            page.click(".r-fav")
            page.wait_for_selector(".r-unfav", timeout=WAIT)
            page.click(".r-unfav")
            page.wait_for_function("() => !D.star().filled && D.star().name === 'Add to favourites'", timeout=WAIT)
            page.wait_for_function(f"() => D.saved().then((s) => !s.lines.includes({link!r}))", timeout=WAIT)
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


def test_line_actions_and_links(site):
    """A desktop. The line's actions stand in one row under "Stands for", above "Lines from anchor A1 / A2": "3D view"
    (its address the caller's, /view3d#run=…&line=…, with the spot's other passing lines in the spot's order as
    `&also=`, at most 20; none for a spot of one line), "Copy link" (today's words; the link on the clipboard, without
    ?ui=; where the clipboard refuses, today's field with the link selected). No "Zoom" (11 a), no dock (the desktop's
    profile is the frame's card), no "Report this line" on the local app (it has no report form)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=SCRIPT)
            _view(page)
            many = page.evaluate("() => { const v = D.v(); return Array.from(v.order).find((s) => v.passingCount(s) > 2); }")
            _select(page, str(many))
            parts = page.evaluate("() => D.parts()")
            assert parts.index("vl-stands") + 1 == parts.index("vl-lacts") == parts.index("vl-acts") - 1, parts
            assert "vl-dock" not in " ".join(page.evaluate("() => [...document.querySelectorAll('.vl-details > *')].map((e) => e.className)")), parts
            acts = page.evaluate("() => [...document.querySelectorAll('.vl-lacts > *')].map((e) => [e.className.split(' ').filter((c) => c.startsWith('r-'))[0], e.textContent])")
            assert acts == [["r-view3d", WORDS["ui.view3d.open"]], ["r-copy", "Copy link"]], acts
            assert not page.evaluate("() => [...document.querySelectorAll('.c-col-details button, .c-col-details a')].some((b) => b.textContent.trim() === 'Zoom')")
            assert not page.evaluate("() => !!document.querySelector('.r-report')")
            # the 3D view: the caller's address of the line, then the spot's other passing lines
            href, also, base = page.evaluate("""() => { const v = D.v(), m = D.m(), s = v.selected, a = document.querySelector('.r-view3d');
                return [a.getAttribute('href'), D.also(), '/view3d#run=' + encodeURIComponent(m.runId) + '&line=' + encodeURIComponent(m.lineLink(s.line))]; }""")
            n = page.evaluate("() => D.v().passingCount(D.v().selected.spot)")
            assert len(also) == min(OTHERS_MAX, n - 1) > 0
            from urllib.parse import quote
            assert href == base + "&also=" + quote(";".join(also), safe="-_.!~*'()"), (href, base)
            assert href.count("&also=") == 1 and "&also=" not in base
            # a spot of one passing line: its 3D view's address alone
            one = page.evaluate("() => { const v = D.v(); return Array.from(v.order).find((s) => v.passingCount(s) === 1) ?? null; }")
            if one is not None:
                _select(page, str(one))
                assert "&also=" not in page.evaluate("() => document.querySelector('.r-view3d').getAttribute('href')")
            else:
                print("the clip has no spot of one passing line: the address without others is not checked")
            # Copy link: on the clipboard (the stub's), "Link copied", the run's page without ?ui=
            _select(page, str(many))
            page.click(".r-copy")
            page.wait_for_function("() => document.querySelector('.r-copy').textContent === 'Link copied'", timeout=WAIT)
            copied = page.evaluate("() => [window.COPIED[window.COPIED.length - 1], document.querySelector('.r-copied').value, "
                                   "'#run=' + encodeURIComponent(D.m().runId) + '&line=' + encodeURIComponent(D.m().lineLink(D.v().selected.line))]")
            assert copied[0] == copied[1] and copied[0].endswith(copied[2]) and "ui=" not in copied[0], copied
            # the next line: "Copy link" again; the clipboard refuses: today's field with the link
            page.evaluate("() => { navigator.clipboard.writeText = () => Promise.reject(new Error('refused')); }")
            page.click(".vl-next")
            page.wait_for_function("() => document.querySelector('.r-copy').textContent === 'Copy link'", timeout=WAIT)
            page.click(".r-copy")
            page.wait_for_selector(".r-linkfield input", timeout=WAIT)
            # the field takes the focus a frame after it is drawn (LinkField's effect)
            page.wait_for_function("() => document.activeElement === document.querySelector('.r-linkfield input')", timeout=WAIT)
            field = page.evaluate("() => [document.querySelector('.r-linkfield input').value, D.m().lineLink(D.v().selected.line)]")
            assert field[0].endswith("&line=" + quote(field[1], safe="-_.!~*'()")), field
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


def test_map_page_keeps_todays_features(site):
    """A run's map.html (no 3D view there): the view's details have no "3D view", and a star exactly where today's page
    has its favourite button on the same page (the condition is today's: the page keeps favourites)."""
    from playwright.sync_api import sync_playwright
    base = site.split("/runs/")[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{base}/runs/{BIG}/map.html", DESKTOP, flag=False, script=SCRIPT)
            page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
            page.wait_for_load_state("networkidle")
            page.evaluate("() => { const m = window.FINDALINE_RESULT.model; m.select(m.rows[0].group); }")
            page.wait_for_selector(".r-copy", timeout=WAIT)
            today = page.evaluate("() => [!!document.querySelector('.c-col-details .r-fav'), !!document.querySelector('.r-view3d')]")
            page.context.close()
            page = _open(browser, f"{base}/runs/{BIG}/map.html", DESKTOP, script=SCRIPT)
            page.wait_for_load_state("networkidle")
            _select(page)
            view = page.evaluate("() => [!!document.querySelector('.vl-dhead .r-fav'), !!document.querySelector('.r-view3d'), !!document.querySelector('.r-copy')]")
            assert view == [today[0], False, True] and today[1] is False, (today, view)
            assert page.errors == []
        finally:
            browser.close()


@pytest.fixture
def report_site(tmp_path, view_clip):
    """The clip's run served by the app with a page whose user is not the local one (`canReport`: the public site's
    report form; nothing else of the public site), its address."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    page_path = stub_page(folder, "viewtest")
    index = folder / page_path
    html = index.read_text(encoding="utf-8")
    local = 'name="findaline-user" content="{&quot;local&quot;: true}"'
    assert local in html
    index.write_text(html.replace(local, 'name="findaline-user" content="{&quot;name&quot;: &quot;tester&quot;}"'), encoding="utf-8")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


@pytest.mark.parametrize("device", DEVICES, ids=IDS)
def test_report_below_the_facts(report_site, device):
    """Where the page has the report form, "Report this line" stands below the facts (11 a: the frame's `lineActions`
    slot after the details; a phone: between the details and the list); it sends today's request (the run and the
    line); none while "Lines from here" stands in the details' place."""
    from playwright.sync_api import sync_playwright
    phone = device is PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{report_site}#run={BIG}", device, script=SCRIPT)
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
            _select(page)
            page.wait_for_selector(".r-report", timeout=WAIT)
            holder = ".u-sheet-body" if phone else ".c-col-dbody"
            kids = page.evaluate(f"() => D.kids('{holder}')")
            assert kids == (["vl-details", "u-btn", "vl-list"] if phone else ["vl-details", "u-btn"]), kids
            assert page.evaluate("() => [document.querySelector('.r-report').textContent.trim(), "
                                 "document.querySelector('.vl-details').lastElementChild.className]") == ["Report this line", "vl-facts"]
            if phone:
                _sheet(page, "full")
            # "Lines from here" in the details' place: no Report; closed: Report again
            page.click(".vl-from-1")
            page.wait_for_selector(".vl-fan", timeout=WAIT)
            assert not page.evaluate("() => !!document.querySelector('.r-report')")
            page.click(".vl-fan-close")
            page.wait_for_selector(".r-report", timeout=WAIT)
            page.click(".r-report")
            page.wait_for_function("() => window.REPORTS.length === 1", timeout=WAIT)
            sent = page.evaluate("() => [window.REPORTS[0], D.m().runId, D.m().lineLink(D.v().selected.line), D.m().data.run.name]")
            assert sent[0]["category"] == "results" and sent[0]["context"] == {"run": sent[1], "line": sent[2]}
            assert sent[0]["about"] == f"a line of {sent[3]}"
            assert page.evaluate("() => window.CSP_VIOLATIONS") == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", [PHONE, PIXEL], ids=["390", "412"])
def test_phone_dock_under_the_values(site, device):
    """A phone (4 d): the selected line's profile dock stands right under the four values (its bar in view at the full
    stop), its title and "Rigging and layers" on one line; closed by its x it goes, "Profile" takes its place among the
    line's actions with the focus, and brings it back; a new selection shows it again. A desktop has no dock in the
    details."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            _sheet(page, "half")
            _select(page)
            parts = page.evaluate("() => D.parts()")
            assert parts[0] == "vl-tiles" and parts[1] == "r-dock" and "vl-dock" in page.evaluate("() => document.querySelector('.vl-details > .r-dock').className"), parts
            page.wait_for_selector(".vl-dock .fal-profile-chart", timeout=WAIT)
            # right under the tiles (the details' 16 px gap), its bar in view with the sheet at full (at half the
            # built sheet shows the tiles: its half stop is lower than the mock-up's)
            gap = page.evaluate("() => D.box('.vl-dock')[1] - D.box('.vl-tiles')[3]")
            assert 0 <= gap <= 17, gap
            _sheet(page, "full")
            seen = page.evaluate("() => { const bar = document.querySelector('.vl-dock .r-dock-bar').getBoundingClientRect(), "
                                 "body = document.querySelector('.u-sheet-body').getBoundingClientRect(); return [bar.top >= body.top, bar.bottom <= body.bottom]; }")
            assert seen == [True, True], seen
            # its bar: the title and "Rigging and layers" on one line, the hint under them
            bar = page.evaluate("() => { const t = document.querySelector('.vl-dock .r-dock-bar > b').getBoundingClientRect(), "
                                "c = document.querySelector('.vl-dock .r-dock-bar > .u-chip').getBoundingClientRect(); return Math.abs((t.top + t.bottom) / 2 - (c.top + c.bottom) / 2) < 12; }")
            assert bar
            # closed: the dock goes, "Profile" is there with the focus; pressed, the dock is back
            page.evaluate("() => { const b = document.querySelector('.vl-dock [aria-label=\"Close the profile\"], .vl-dock .fal-close'); b.focus(); b.click(); }")
            page.wait_for_function("() => !document.querySelector('.vl-dock') && !!document.querySelector('.vl-lacts .r-reprofile')", timeout=WAIT)
            page.wait_for_function("() => document.activeElement === document.querySelector('.r-reprofile')", timeout=WAIT)
            assert page.evaluate("() => [document.querySelector('.r-reprofile').textContent, D.m().profileClosed]") == ["Profile", True]
            page.click(".r-reprofile")
            page.wait_for_selector(".vl-dock .fal-profile-chart", timeout=WAIT)
            assert not page.evaluate("() => !!document.querySelector('.r-reprofile')")
            # closed again, then another spot selected: its profile shows
            page.evaluate("() => D.m().closeProfile()")
            page.wait_for_function("() => !document.querySelector('.vl-dock')", timeout=WAIT)
            _select(page, "view.order[1]")
            page.wait_for_selector(".vl-dock", timeout=WAIT)
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
            page.context.close()
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=SCRIPT)
            _view(page)
            _select(page)
            assert not page.evaluate("() => !!document.querySelector('.vl-details .r-dock')")
        finally:
            browser.close()


def test_phone_dock_gives_way_to_a_measured_line(site):
    """A phone: while the frame shows a measured profile (a link's line outside the run, measured; PanelProps.measured,
    which the frame passes on the stack of step 3c), the details draw no dock of their own: one profile at a time, as
    today's sheet. Passes on the stack (the frame's member is B3's)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", PHONE, script=SCRIPT + PROFILE_STUB)
            _view(page)
            _select(page)
            page.wait_for_selector(".vl-dock", timeout=WAIT)
            page.evaluate(f"() => {{ location.hash = '#run=' + encodeURIComponent(D.m().runId) + '&line=' + encodeURIComponent({OUTSIDE!r}); }}")
            page.wait_for_function("() => !!window.FINDALINE_VIEW.measured", timeout=WAIT)
            page.wait_for_function("() => !document.querySelector('.vl-details .vl-dock')", timeout=WAIT)
            assert page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", DEVICES, ids=IDS)
def test_list_stars(site, device):
    """A star at each row's end in "Best in view", "Start here" and the tree (B-3, 11 a; a phone keeps them: 10 a), also
    on a run with no favourite yet: the row button's sibling (a row stays one button), out of the tab order, 24 px on a
    desktop and 44 px on a phone, today's names and titles; the heads stand over the row's button. A press adds to the
    folder used last, or removes (today's rule; on the server); a favourite's dash wears the halo. The arrows: right
    from a row to its star, left back, up, down, Home and End from a star along the stars' column; Tab leaves the list
    from a star in one press; a star pressed by the keyboard whose row goes ("Favourites only") leaves the focus on a
    row. In a row of two lines the star stands on the values' line."""
    from playwright.sync_api import sync_playwright
    phone = device is PHONE
    side = [44, 44] if phone else [24, 24]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            if phone:
                _sheet(page, "half")
            assert page.evaluate("() => D.m().favouriteLines().length") == 0
            for block in (".vl-topblock", ".vl-tree"):
                rows = page.evaluate(f"() => D.stars('{block}')")
                assert rows, block
                for r in rows:
                    assert r["kids"] == ["vl-main", "vl-star"] and r["star"] == {"name": "Add to favourites", "title": "add to favourites",
                                                                                 "pressed": "false", "tab": -1, "size": side, "filled": False}, (block, r)
                    assert not r["halo"]
            # the heads over the row's button: "Lines" ends where the rows' counts end
            ends = page.evaluate("() => { const h = [...document.querySelectorAll('.vl-topblock .vl-cols > span')].pop().getBoundingClientRect(), "
                                 "n = document.querySelector('.vl-topblock .vl-n').getBoundingClientRect(); return [h.right, n.right]; }")
            assert abs(ends[0] - ends[1]) <= 1.5, ends
            # a press: a favourite on the server, the star pressed with today's other name, the dash's halo; again: gone
            first = page.evaluate("() => D.stars('.vl-topblock')[0].row")
            link = page.evaluate(f"() => D.link({first})")
            page.click(".vl-topblock .vl-rows > li:first-child > .vl-star")
            page.wait_for_function(f"() => D.saved().then((s) => s.lines.includes({link!r}))", timeout=WAIT)
            page.wait_for_function("() => D.stars('.vl-topblock')[0].star.pressed === 'true'", timeout=WAIT)
            row = page.evaluate("() => D.stars('.vl-topblock')[0]")
            assert row["star"]["name"] == "Remove from favourites" and row["star"]["title"] == "favourite" and row["star"]["filled"] and row["halo"], row
            page.click(".vl-topblock .vl-rows > li:first-child > .vl-star")
            page.wait_for_function(f"() => D.saved().then((s) => !s.lines.includes({link!r}))", timeout=WAIT)
            page.wait_for_function("() => D.stars('.vl-topblock')[0].star.pressed === 'false' && !D.stars('.vl-topblock')[0].halo", timeout=WAIT)
            # the folder used last: a new folder chosen once, then a row's star adds into it
            folder = page.evaluate("() => D.m().newFolder('Step 3c', null)")
            assert isinstance(folder, int)
            page.evaluate(f"() => {{ localStorage.setItem('findaline.lastFolder', '{folder}'); }}")
            page.click(".vl-topblock .vl-rows > li:nth-child(2) > .vl-star")
            second = page.evaluate("() => D.stars('.vl-topblock')[1].row")
            page.wait_for_function(f"() => D.m().folderOf(D.m().lineAt({second})) === {folder}", timeout=WAIT)
            page.wait_for_function(f"() => D.saved().then((s) => s.in[{page.evaluate(f'() => D.link({second})')!r}] === {folder})", timeout=WAIT)
            # the keys: right to the star, down and up the stars, End, Home, left back to the row; Tab leaves the list
            page.focus(".vl-topblock .vl-rows > li:first-child > .vl-main")
            stars = ".vl-topblock .vl-rows > li > .vl-star"
            at = f"() => [...document.querySelectorAll('{stars}')].indexOf(document.activeElement)"
            n = page.evaluate(f"() => document.querySelectorAll('{stars}').length")
            for key, want in (("ArrowRight", 0), ("ArrowDown", 1), ("ArrowDown", 2), ("ArrowUp", 1), ("End", n - 1), ("Home", 0)):
                page.keyboard.press(key)
                assert page.evaluate(at) == want, key
            page.keyboard.press("ArrowLeft")
            assert page.evaluate("() => document.activeElement === document.querySelector('.vl-topblock .vl-rows > li:first-child > .vl-main')")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Tab")
            assert page.evaluate("() => !!document.activeElement && !document.activeElement.closest('.vl-topblock .vl-rows')")
            # Enter on a star presses it; with "Favourites only" the row goes and the focus stays on a row
            page.focus(".vl-topblock .vl-rows > li:first-child > .vl-main")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("Enter")
            page.wait_for_function("() => D.stars('.vl-topblock')[0].star.pressed === 'true'", timeout=WAIT)
            page.evaluate("() => { const m = D.m(); m.setFilters({...m.filters, favOnly: true}); }")
            page.wait_for_function("() => D.v().counts.lines <= 2", timeout=WAIT)
            page.focus(".vl-tree .vl-rows > li:first-child > .vl-main")
            page.keyboard.press("ArrowRight")
            page.keyboard.press("Enter")
            page.wait_for_function("() => D.v().counts.lines <= 1", timeout=WAIT)
            page.wait_for_function("() => D.focus() !== ''", timeout=WAIT)
            assert "vl-" in page.evaluate("() => D.focus()") or "leaflet" in page.evaluate("() => D.focus()")
            page.evaluate("() => { const m = D.m(); m.clearFilters(); for (const l of m.favouriteLines()) m.toggleFavourite(l); }")
            page.wait_for_function("() => D.m().favouriteLines().length === 0 && !D.m().filters.favOnly", timeout=WAIT)
            # "Start here" (the Area level): stars too; a pick's star on its values' line (the row's second)
            page.evaluate("() => D.v().setLevel('area')")
            page.wait_for_selector(".vl-topblock .vl-pick > .vl-star", timeout=WAIT)
            picks = page.evaluate("() => [...document.querySelectorAll('.vl-topblock .vl-pick')].map((li) => [D.mid(li.querySelector('.vl-star .u-ic')), D.mid(li.querySelector('.vl-v'))])")
            assert picks and all(abs(a - b) <= 4 for a, b in picks), picks
            page.evaluate("() => D.v().setLevel('auto')")
            # a line over trees (marked in the page's columns, as test_tight_tile_and_over_trees_words): its star on the
            # values' line (the first)
            page.evaluate("""() => { const v = D.v(), c = v.model.data.columns; for (const s of Array.from(v.order).slice(0, 2)) c.over[v.shownOf(s)] = 1;
                v.setTopOnly(!v.topOnly); v.setTopOnly(!v.topOnly); window.FINDALINE_VIEW.map.refresh(); }""")
            page.wait_for_selector(".vl-tree .vl-over > .vl-star", timeout=WAIT)
            over = page.evaluate("() => [...document.querySelectorAll('.vl-tree .vl-over')].map((li) => [D.mid(li.querySelector('.vl-star .u-ic')), D.mid(li.querySelector('.vl-v'))])")
            assert over and all(abs(a - b) <= 4 for a, b in over), over
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", DEVICES, ids=IDS)
def test_list_help(site, device):
    """The list's two help buttons (the mock-up's item 7): one held to "Top level only" (in one box with the chip, so the
    two wrap together; "About Top level only"), opening the chip's help text in place under the chips; one in the first
    cell of the top block's heads ("About the columns"; a screen reader reaches it, the heads' words stay hidden from it;
    the tree's heads have none), opening today's words for the columns under the heads. Both say whether they are open
    and which text they open; no box around a text (R8); 24 px on a desktop, 44 px on a phone."""
    from playwright.sync_api import sync_playwright
    phone = device is PHONE
    side = [44, 44] if phone else [24, 24]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            if phone:
                _sheet(page, "half")
            top = page.evaluate("""() => { const b = document.querySelector('.vl-top-info');
                return [b.parentElement.className, [...b.parentElement.children].map((e) => e.className.split(' ').find((c) => c.startsWith('vl-'))),
                        b.getAttribute('aria-label'), b.getAttribute('aria-expanded'), b.getAttribute('aria-controls'), D.size(b)]; }""")
            assert top == ["vl-chipi", ["vl-top", "vl-info"], WORDS["ui.view.chip.top_about"], "false", "vl-help-top", side], top
            page.click(".vl-top-info")
            page.wait_for_selector("#vl-help-top", timeout=WAIT)
            text = page.evaluate("""() => { const h = document.querySelector('#vl-help-top'), s = getComputedStyle(h);
                return [h.textContent, h.previousElementSibling.classList.contains('u-chips'), document.querySelector('.vl-top-info').getAttribute('aria-expanded'),
                        s.borderTopWidth, s.backgroundColor, D.box('#vl-help-top')[1] >= D.box('.vl-filters .u-chips')[3] - 1]; }""")
            assert text == [WORDS["ui.view.chip.top_help"], True, "true", "0px", "rgba(0, 0, 0, 0)", True], text
            page.click(".vl-top-info")
            page.wait_for_selector("#vl-help-top", state="detached", timeout=WAIT)
            # the columns' help: in the top block's heads only
            cols = page.evaluate("""() => { const b = document.querySelector('.vl-topblock .vl-cols .vl-cols-info');
                return [b === b.parentElement.firstElementChild, !b.closest('[aria-hidden="true"]'), b.getAttribute('aria-label'), b.getAttribute('aria-expanded'),
                        b.getAttribute('aria-controls'), D.size(b), [...b.parentElement.querySelectorAll(':scope > span')].every((s) => s.getAttribute('aria-hidden') === 'true'),
                        document.querySelectorAll('.vl-tree .vl-cols-info').length]; }""")
            assert cols == [True, True, WORDS["ui.view.col.about"], "false", "vl-help-cols", side, True, 0], cols
            page.click(".vl-topblock .vl-cols-info")
            page.wait_for_selector("#vl-help-cols", timeout=WAIT)
            shown = page.evaluate("""() => [[...document.querySelectorAll('#vl-help-cols dt')].map((e) => e.textContent),
                [...document.querySelectorAll('#vl-help-cols dd')].map((e) => e.textContent), D.m().hasAccess,
                document.querySelector('#vl-help-cols').previousElementSibling.classList.contains('vl-cols'),
                getComputedStyle(document.querySelector('#vl-help-cols')).borderTopWidth]""")
            names = ["length", "mean"] + (["anchors"] if shown[2] else []) + ["lines"]
            want_dt = [WORDS["ui.list.col.length"], WORDS["ui.list.col.mean"], WORDS["ui.view.col.clear"]] + \
                ([WORDS["ui.list.col.anchors"]] if shown[2] else []) + [WORDS["ui.list.col.lines"]]
            want_dd = [WORDS[f"ui.list.col.{k}_title"] for k in ("length", "mean", "clear")] + \
                ([WORDS["ui.list.col.anchors_title"]] if shown[2] else []) + [WORDS["ui.list.col.lines_title"]]
            assert shown[0] == want_dt and shown[1] == want_dd and shown[3] and shown[4] == "0px", (shown, names)
            assert page.evaluate("() => document.querySelector('.vl-topblock .vl-cols-info').getAttribute('aria-expanded')") == "true"
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


@pytest.mark.parametrize("device", DEVICES, ids=IDS)
def test_note_first_in_the_list(site, device):
    """The model's note stands first in the list (item 8, 11 a: desktop the list's body, a phone the sheet's body, the
    sheet at half for a link: K a): a link to a line the filters hide, today's words with "clear filters", which opens
    it; a favourite the server refuses, its note closed by today's x (the planner's choice: it stays dismissable), the
    focus not on the page's body. No line passing: the sentence and "Clear all" first on a phone too."""
    from playwright.sync_api import sync_playwright
    phone = device is PHONE
    holder = ".vl-list" if phone else ".vl-body"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=SCRIPT)
            _view(page)
            target = page.evaluate("() => { const v = D.v(), row = v.shownOf(v.order[0]); return {row, link: D.link(row), len: v.values.len[row]}; }")
            page.evaluate(f"() => {{ const m = D.m(); m.setFilters({{...m.filters, lenMin: Math.ceil({target['len']}) + 1}}); "
                          f"location.hash = '#run=' + encodeURIComponent(m.runId) + '&line=' + encodeURIComponent({target['link']!r}); }}")
            page.wait_for_selector(".vl-lnote", timeout=WAIT)
            if phone:
                page.wait_for_function("() => D.snap() === 'half'", timeout=WAIT)
            note = page.evaluate(f"""() => [D.kids('{holder}')[0], document.querySelector('.vl-lnote-text').textContent,
                document.querySelector('.vl-lnote-act').tagName, document.querySelector('.vl-lnote-act').textContent,
                document.querySelector('.vl-lnote-x').getAttribute('aria-label'), D.size(document.querySelector('.vl-lnote-x')),
                getComputedStyle(document.querySelector('.vl-lnote')).backgroundColor]""")
            assert note[0] == "vl-lnote" and note[1] == WORDS["ui.link.hidden"] + " " + WORDS["ui.link.clear_filters"], note
            assert note[2:5] == ["BUTTON", WORDS["ui.link.clear_filters"], "Close"] and note[5] == ([44, 44] if phone else [24, 24]), note
            assert note[6] == "rgba(0, 0, 0, 0)", note  # no box (R8)
            assert not page.evaluate("() => !!document.querySelector('.vl-summary .r-note, .r-note')")
            page.click(".vl-lnote-act")
            page.wait_for_function(f"() => D.v().selected?.row === {target['row']} && !document.querySelector('.vl-lnote')", timeout=WAIT)
            page.evaluate("() => D.v().select(null)")
            # a favourite the server refuses: today's note, first; its x closes it, the focus stays on the page
            if phone:
                page.evaluate("() => { window.FAIL_SAVES = true; }")
                _sheet(page, "half")
            else:
                page.evaluate("() => { window.FAIL_SAVES = true; }")
            page.click(".vl-tree .vl-rows > li:first-child > .vl-star")
            page.wait_for_selector(".vl-lnote", timeout=WAIT)
            failed = page.evaluate(f"() => [D.kids('{holder}')[0], document.querySelector('.vl-lnote-text').textContent, !!document.querySelector('.vl-lnote-act')]")
            assert failed[0] == "vl-lnote" and failed[1].startswith("The favourite was not saved: ") and not failed[2], failed
            page.focus(".vl-lnote-x")
            page.keyboard.press("Enter")
            page.wait_for_function("() => !document.querySelector('.vl-lnote') && D.m().note === null", timeout=WAIT)
            page.wait_for_function("() => D.focus() !== ''", timeout=WAIT)
            # no line passes: first in the list (a phone: before the summary and the filters)
            page.evaluate("() => { const m = D.m(); m.setFilters({...m.filters, lenMin: 1e6}); }")
            page.wait_for_selector(".vl-none", timeout=WAIT)
            kids = page.evaluate(f"() => D.kids('{holder}')")
            assert kids[0] == "vl-none" and (not phone or kids[1:3] == ["r-summary", "r-filters"]), kids
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()
