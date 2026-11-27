"""A line's link in the result view (viewer/src/result/view/viewlink.ts, SpotColumns.tsx; step 3c of
docs/line-volume/spec-view.md part B: `#line=` links select the line and open its spot): the view opened at a line's
link selects that line in its spot and puts it in view, in the app (#run=…&line=…), on a run's map.html and on a
share link's page (#line=…); Back, Forward and a hashchange open a link again; a line that "Top level only" alone
hides turns the chip off (the user's "6. a"); a line other filters hide, a line not in the run and a line outside it
that is measured behave as on today's page (model.openLinked's notes and words, "clear filters", measuredLink); the
selection goes into the hash in place (never a new history entry), from every way of selecting; the window crossing
the phone's width opens nothing again. Playwright's Edge over the app's server (the share page: over the public
site), offline, on the result view's clip run (clip_runs.view_clip), on a desktop and a phone. Every wait is an event
with a deadline (one exception: test_shell_c_view_map._tap). Run from PowerShell (.claude/rules/browser-tests.md)."""

import math
import os
import sys
import threading
import time
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_public import account_settings  # noqa: E402,F401
from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import (DESKTOP, PHONE, SIDE_PHONE, WAIT, WORDS, _crowded, _open, _state, _tap, _upright_then_hidden,  # noqa: E402,F401
                                   site, view_clip)
from test_web import EDGE, _playwright  # noqa: E402

# Every test but the words' starts a browser
BROWSER = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                             reason="needs Microsoft Edge and Playwright (group ui)")

# model.ts openLinked's notes: today's words, in the catalogue since step 3c (ui.link.*; viewlink.ts takes the same keys)
HIDDEN = "The line of the link is hidden by the filters."
NOT_HERE = "The line of the link is not in this run."
CLEAR = "clear filters"
# The length filter set above a line's length (the model's filters: the view follows them)
LONGER = "(len) => { const m = window.FINDALINE_VIEW.view.model; m.setFilters({...m.filters, lenMin: Math.ceil(len) + 1}); }"
# A line outside the run (as the 3D view's moved anchors give it): measured by the server, stubbed here (80 m)
OUTSIDE = "49.5,19.1,49.5004,19.1005"
PROFILE_STUB = """
window.PROFILE_ASKS = [];
const realFetchOfLinks = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile")) return realFetchOfLinks(url, init);
  PROFILE_ASKS.push(decodeURIComponent(String(url).split("line=")[1]));
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
"""

# The page's helpers of the checks (after test_shell_c_view_map's T)
LINKS = r"""
window.K = {
  v() { return window.FINDALINE_VIEW; },
  info(row) { const {view} = this.v(), m = view.model;
    return {row, spot: view.spotOf(row), link: m.lineLink(m.lineAt(row)), len: view.values.len[row]}; },
  // a passing line of a spot in the order that is not the spot's shown line (the link must select the row, not
  // only the spot), the k-th such
  deep(k = 0) { const {view} = this.v();
    for (const spot of Array.from(view.order)) { const shown = view.shownOf(spot);
      for (const row of Array.from(view.passingOf(spot))) if (row !== shown && k-- === 0) return this.info(row); }
    return null; },
  // a line that "Top level only" alone hides
  topLine() { const {view} = this.v(); for (let row = 0; row < view.count; row++) if (view.topOnlyHides(row)) return this.info(row);
    return null; },
  // topOnlyHides against what passes with the chip on and off: every line, the chip left on; `hidden` how many it hides
  topRule() { const {view} = this.v(), n = view.count, on = new Uint8Array(n), hides = new Uint8Array(n);
    view.setTopOnly(true);
    for (let r = 0; r < n; r++) { on[r] = view.passes(r) ? 1 : 0; hides[r] = view.topOnlyHides(r) ? 1 : 0; }
    view.setTopOnly(false);
    let bad = 0, hidden = 0;
    for (let r = 0; r < n; r++) { const off = view.passes(r); if (!!hides[r] !== (off && !on[r])) bad++; if (hides[r]) hidden++;
      if (view.topOnlyHides(r)) bad++; }  // the chip off hides nothing
    view.setTopOnly(true);
    return {bad, hidden, topHidden: view.counts.topHidden}; },
  // the part of the map a person sees that the bar leaves free: under the level switch, above the foot and a sheet
  room() { const box = window.FINDALINE_MAP.getContainer().getBoundingClientRect(), rect = (s) => { const e = document.querySelector(s);
      const r = e && e.getBoundingClientRect(); return r && r.width && r.height ? r : null; };
    const top = Math.max(box.top, rect(".v-map .v-switch")?.bottom ?? box.top);
    const bottom = Math.min(box.bottom, rect(".v-map .v-foot")?.top ?? box.bottom, rect(".u-sheet")?.top ?? box.bottom);
    return [box.left, top, box.right, bottom]; },
  // both anchors of a line in that part (in the viewport's pixels)
  inView(row) { const e = T.ends(row), box = T.box(), r = this.room();
    return [[e[0], e[1]], [e[2], e[3]]].every(([x, y]) => x + box.left >= r[0] && x + box.left <= r[2] && y + box.top >= r[1] && y + box.top <= r[3]); },
  state() { const {view, measured} = this.v(), m = view.model, sel = view.selected, note = document.querySelector(".vl-lnote");
    return {selected: sel && [sel.spot, sel.row], link: sel && m.lineLink(sel.line), topOnly: view.topOnly,
            chip: document.querySelector(".vl-top")?.getAttribute("aria-pressed") ?? null,
            hash: decodeURIComponent(location.hash), history: history.length,
            note: m.note && [m.note.text, m.note.action || null], shown: note && note.textContent,
            measuredLink: m.measuredLink, measured: measured ? Math.round(measured.len) : null,
            inView: sel ? this.inView(sel.row) : null, lenMin: m.filters.lenMin, snap: this.snap(), rest: this.rest()}; },
  // a phone's sheet at rest: its height drawn as its stop gives it
  rest() { const s = document.querySelector(".u-sheet"); return !!s && Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; },
  // a phone's sheet: its stop (none on a desktop)
  snap() { const s = document.querySelector(".u-sheet"); return s ? ["peek", "half", "full"].find((k) => s.classList.contains("u-" + k)) : null; },
};
"""


def test_note_words_are_models():
    """model.ts openLinked's three notes and the action of a line the filters hide come from the catalogue (the user's
    W10 a: today's words, unchanged), and viewlink.ts sets the note of a line the filters hide with the same two keys
    (no copy of its own)."""
    import json
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(repo, "viewer", "src", "result")
    with open(os.path.join(src, "view", "viewlink.ts"), encoding="utf-8") as f:
        link = f.read().replace("\r\n", "\n")
    with open(os.path.join(src, "model.ts"), encoding="utf-8") as f:
        model = f.read().replace("\r\n", "\n")
    with open(os.path.join(repo, "locales", "en.json"), encoding="utf-8") as f:
        words = json.load(f)
    opened = model[model.index("  openLinked("):]
    opened = opened[:opened.index("\n  }\n")]
    hidden = 'text: t("ui.link.hidden"), action: t("ui.link.clear_filters"), onAction:'
    assert "this.note = {" + hidden in opened and "model.setNote({" + hidden in link
    assert 'this.note = {text: t("ui.link.not_in_run")};' in opened
    assert 'this.note = {text: t("ui.link.not_measured", {error: (e as Error).message})};' in opened
    # no copy of the words in the code (a comment may name them)
    assert all('"The line of the link' not in src and 'action: "clear filters"' not in src for src in (opened, link))
    assert (words["ui.link.hidden"], words["ui.link.clear_filters"], words["ui.link.not_in_run"]) == (HIDDEN, CLEAR, NOT_HERE)
    assert words["ui.link.not_measured"] == "The line of the link could not be measured: {{error}}"


def _page(browser, url: str, context: dict, script: str = ""):
    """The page at `url` in the result view, with the checks' helpers."""
    return _open(browser, url, context, script=LINKS + script)


def _wait(page, check: str):
    """Wait until `check` holds of the state K.state() (a JS expression of `s`) and the map rests; the state."""
    from playwright.sync_api import TimeoutError as Timeout
    try:
        page.wait_for_function("() => { const s = K.state(); return !window.FINDALINE_MAP._animatingZoom && ("
                               + check + "); }", timeout=WAIT)
    except Timeout:
        raise AssertionError(f"{check} never held: {page.evaluate('() => K.state()')} {page.errors}") from None
    page.evaluate("() => T.frames()")
    return page.evaluate("() => K.state()")


def _app(site: str, line: str | None = None) -> str:
    """The app's page of the run, at a line's link (#run=…&line=…, the line encoded as runHash does)."""
    return f"{site}#run={BIG}" + (f"&line={urllib.parse.quote(line, safe='')}" if line else "")


def _facts(browser, url: str, context: dict) -> dict:
    """The lines the tests open, found in the view itself: two deep lines and one "Top level only" alone hides."""
    page = _page(browser, url, context)
    facts = page.evaluate("() => ({a: K.deep(0), b: K.deep(5), top: K.topLine(), rule: K.topRule()})")
    page.context.close()
    assert facts["a"] and facts["b"] and facts["a"]["row"] != facts["b"]["row"], facts
    assert facts["top"], "no line of the clip's run is hidden by 'Top level only' alone"
    return facts


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_open_by_link_and_write(site, device):
    """Opened at a line's link the view selects that line (its spot, the line its selected row) and puts it in view
    under the bar (above a phone's sheet); the hash names it. A selection made on the page writes its line's link in
    place (no new history entry), from a row of the list, a number on the map, "Start here", a line of "Lines from
    here" and the table of spots (a phone: a tap on a number); no selection writes the run's hash without a line.
    Back, Forward and a hashchange to a link open it again, also to the link opened before (only `nav` changed);
    nothing is written while the hash is not this run's page."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, _app(site), context)
            a, b = facts["a"], facts["b"]
            page = _page(browser, _app(site, a["link"]), context)
            s = _wait(page, "s.selected !== null")
            assert s["selected"] == [a["spot"], a["row"]] and s["inView"], s
            assert s["hash"] == f"#run={BIG}&line={a['link']}" and s["topOnly"], s
            assert s["snap"] == ("peek" if device == "phone" else None), s  # a link that opens its line: the low start
            entries = s["history"]

            def selected_writes(how: str):
                now = _wait(page, "s.selected !== null && s.hash === `#run=%s&line=${s.link}`" % BIG)
                assert now["history"] == entries, (how, now)
                return now
            if device == "desktop":
                # a row of the list: the top block's first row of another spot (the run in view)
                _state(page, "map.fitArea(T.v().map.options.padding());")
                spot = page.evaluate(f"() => +[...document.querySelectorAll('.vl-topblock .vl-main')]"
                                     f".find((b) => +b.dataset.spot !== {a['spot']}).dataset.spot")
                page.click(f".vl-topblock .vl-main[data-spot='{spot}']")
                by_row = selected_writes("row")
                assert by_row["selected"][0] == spot
                # a number on the map
                _state(page, "view.setLevel('spots'); map.fitArea(T.v().map.options.padding());")
                number = next(n for n in page.evaluate("() => T.numbersOf('B')") if n["spot"] != spot)
                page.mouse.click(number["x"], number["y"])
                assert selected_writes("number")["selected"] == [number["spot"], number["row"]]
                # "Start here" (the Area level's picks), with nothing selected
                _state(page, "view.setLevel('area'); view.select(null);")
                assert _wait(page, f"s.hash === '#run={BIG}'")["selected"] is None
                pick = page.evaluate("() => window.FINDALINE_VIEW.view.picks().at(-1)")
                page.click(f".vl-topblock .vl-pick .vl-main[data-row='{pick['row']}']")
                assert selected_writes("pick")["selected"] == [pick["spot"], pick["row"]]
                # a line of "Lines from here"
                _state(page, "view.setLevel('auto'); const r = view.shownOf(view.order[0]), c = view.model.data.columns; "
                             "view.openFan({lat: c.lat1.at(r), lng: c.lon1.at(r)}, {row: r, end: 1});")
                page.wait_for_selector(".vl-fan .vl-main", timeout=WAIT)
                row = page.evaluate("() => { const rows = [...document.querySelectorAll('.vl-fan .vl-main')]; "
                                    "return +rows[rows.length - 1].dataset.row; }")
                page.click(f".vl-fan .vl-main[data-row='{row}']")
                assert selected_writes("fan")["selected"][1] == row
                # the table of spots (several spots under the mouse)
                _state(page, "view.select(null);")
                crowded = _crowded(page, False)
                assert crowded and len(crowded["spots"]) > 1
                page.mouse.click(crowded["x"], crowded["y"])
                page.wait_for_selector(".vl-choose .vl-main", timeout=WAIT)
                chosen = page.evaluate("() => { const b = document.querySelectorAll('.vl-choose .vl-main')[1]; "
                                       "return [+b.dataset.spot, +b.dataset.row]; }")
                page.click(f".vl-choose .vl-main[data-spot='{chosen[0]}']")
                assert selected_writes("table")["selected"] == chosen
            else:
                # a tap on a number on the map
                _state(page, "view.setLevel('spots'); map.fitArea(T.v().map.options.padding());")
                number = next(n for n in page.evaluate("() => T.numbersOf('B')") if n["spot"] != a["spot"])
                _tap(page, number["x"], number["y"])
                assert selected_writes("tap")["selected"] == [number["spot"], number["row"]]
            # no selection: the run's hash without a line, in place
            page.keyboard.press("Escape")
            none = _wait(page, f"s.selected === null && s.hash === '#run={BIG}'")
            assert none["history"] == entries
            # a hashchange to the link opened before (the route's line is the same, only `nav` moves on): opened again
            page.evaluate("(hash) => { location.hash = hash; }", _app("", a["link"]))
            again = _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")
            assert again["selected"] == [a["spot"], a["row"]] and again["inView"] and again["history"] == entries + 1
            # another link, then Back and Forward between the two
            page.evaluate("(hash) => { location.hash = hash; }", _app("", b["link"]))
            assert _wait(page, f"s.selected !== null && s.selected[1] === {b['row']}")["inView"]
            page.go_back()
            back = _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")
            assert back["hash"] == f"#run={BIG}&line={a['link']}" and back["inView"], back
            page.go_forward()
            forward = _wait(page, f"s.selected !== null && s.selected[1] === {b['row']}")
            assert forward["hash"] == f"#run={BIG}&line={b['link']}", forward
            # a hash that is not this run's page any more (changed without a hashchange): a selection writes nothing
            page.evaluate("() => history.replaceState(history.state, '', '#home')")
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({a['spot']}, {a['row']})")
            assert _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")["hash"] == "#home"
            assert page.errors == []
        finally:
            browser.close()


@BROWSER
def test_crossing_the_phone_width_opens_nothing_again(site):
    """Desktop and Phone are made again for the same view when the window crosses the phone's width: the selection
    made after the link and the hash stay (the link is not opened again), both ways."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, _app(site), DESKTOP)
            a, b = facts["a"], facts["b"]
            page = _page(browser, _app(site, a["link"]), DESKTOP)
            _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({b['spot']}, {b['row']})")
            chosen = _wait(page, f"s.selected[1] === {b['row']} && s.hash === `#run={BIG}&line=${{s.link}}`")
            for width, layout in ((500, ".c-result-phone"), (1400, ".c-result:not(.c-result-phone)")):
                page.evaluate("() => { window.FINDALINE_VIEW.old = true; }")
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_selector(f"{layout} .leaflet-container", timeout=WAIT)
                page.wait_for_function("() => window.FINDALINE_VIEW && !window.FINDALINE_VIEW.old", timeout=WAIT)
                now = _wait(page, "true")
                assert now["selected"] == chosen["selected"] and now["hash"] == chosen["hash"], (width, now)
                assert now["history"] == chosen["history"]
            assert page.errors == []
        finally:
            browser.close()


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_top_level_only(site, device):
    """A link to a line that "Top level only" alone hides: the chip is turned off and the line selected. The view's
    rule of it (SpotView.topOnlyHides) is exactly the lines the chip hides among those every other filter passes,
    with no filter, a length filter and one kind of lines. A line the chip and a length filter both hide: today's
    note with "clear filters", the chip stays on; the action clears the filters, turns the chip off and selects it."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, _app(site), context)
            top, rule = facts["top"], facts["rule"]
            assert rule["bad"] == 0 and rule["hidden"] == rule["topHidden"] > 0, rule
            page = _page(browser, _app(site, top["link"]), context)
            s = _wait(page, "s.selected !== null")
            assert s["selected"] == [top["spot"], top["row"]] and s["inView"], s
            assert s["topOnly"] is False and s["chip"] in ("false", None) and s["note"] is None, s
            assert s["hash"] == f"#run={BIG}&line={top['link']}"
            if device == "desktop":  # the chip in the list's head (a phone's is in the sheet's body)
                assert s["chip"] == "false"
                # the rule under a length filter and with the lines over trees left out
                for change in ("m.setFilters({...m.filters, lenMin: Math.round(view.values.len[%d])});" % top["row"],
                               "m.setFilters({...m.filters, lenMin: null}); m.setState({...m.state, showOver: false});"):
                    got = page.evaluate("() => { const {view} = window.FINDALINE_VIEW, m = view.model; %s return K.topRule(); }" % change)
                    assert got["bad"] == 0 and got["hidden"] == got["topHidden"], (change, got)
                # ... and with "Only favourites" on: this line and a top-level line marked, the chip hides the first
                page.wait_for_function("() => window.FINDALINE_VIEW.view.model.favouritesOn", timeout=WAIT)
                got = page.evaluate("""async (rows) => { const {view} = window.FINDALINE_VIEW, m = view.model;
                    for (const row of rows) await m.toggleFavourite(m.lineAt(row));
                    m.setState({...m.state, showOver: true}); m.setFilters({...m.filters, favOnly: true});
                    return {...K.topRule(), favourites: m.favouriteLines().length}; }""", [top["row"], facts["a"]["row"]])
                assert got["favourites"] == 2 and got["bad"] == 0 and got["hidden"] == got["topHidden"] == 1, got
                page.context.close()
            # the chip and a length filter: the note, the chip on; "clear filters" opens the line
            page = _page(browser, _app(site), context)
            page.evaluate(LONGER, top["len"])
            page.evaluate("(hash) => { location.hash = hash; }", _app("", top["link"]))
            hidden = _wait(page, "s.note !== null")
            assert hidden["note"] == [HIDDEN, CLEAR] and hidden["selected"] is None, hidden
            assert hidden["topOnly"] is True, hidden
            assert hidden["hash"] == f"#run={BIG}&line={top['link']}", hidden  # kept while nothing is selected
            if device == "phone":  # the note stands in the sheet's body (the list's head): the link raised it to half
                hidden = _wait(page, "s.snap === 'half'")
            assert hidden["shown"].startswith(HIDDEN)
            page.click(f".vl-lnote button:text-is('{CLEAR}')")
            cleared = _wait(page, "s.selected !== null")
            assert cleared["selected"] == [top["spot"], top["row"]] and cleared["topOnly"] is False, cleared
            assert cleared["note"] is None and cleared["lenMin"] is None
            assert cleared["hash"] == f"#run={BIG}&line={top['link']}"
            assert page.errors == []
        finally:
            browser.close()


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_hidden_missing_and_measured(site, device):
    """As on today's page: a line other filters hide gets the note "hidden by the filters" with "clear filters" (the
    link kept while nothing is selected; the action opens it); a link to no line of the run gets "not in this run"
    and the hash drops it; a line outside the run is measured (the profile asked for, model.measuredLink, the line
    handed to the frame, no note, nothing selected, the link kept), and a selection ends it."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, _app(site), context)
            a = facts["a"]
            page = _page(browser, _app(site), context, PROFILE_STUB)
            entries = page.evaluate("() => history.length")
            page.evaluate(LONGER, a["len"])
            page.evaluate("(hash) => { location.hash = hash; }", _app("", a["link"]))
            hidden = _wait(page, "s.note !== null")
            assert hidden["note"] == [HIDDEN, CLEAR] and hidden["selected"] is None, hidden
            assert hidden["topOnly"] is True and hidden["hash"] == f"#run={BIG}&line={a['link']}", hidden
            if device == "phone":  # the note: the sheet at half shows it (pressed once the sheet rests, as a person would)
                _wait(page, "s.snap === 'half' && s.rest")
            page.evaluate("() => window.FINDALINE_VIEW.view.model.note.onAction()")
            opened = _wait(page, "s.selected !== null")
            assert opened["selected"] == [a["spot"], a["row"]] and opened["note"] is None and opened["topOnly"] is True
            assert opened["hash"] == f"#run={BIG}&line={a['link']}" and opened["lenMin"] is None and opened["inView"]
            # no line of the run: today's note, the line dropped from the hash
            page.keyboard.press("Escape")
            page.evaluate("(hash) => { location.hash = hash; }", f"#run={BIG}&line=1,2,3")
            missing = _wait(page, f"s.note !== null && s.hash === '#run={BIG}'")
            assert missing["note"] == [NOT_HERE, None] and missing["selected"] is None, missing
            if device == "desktop":
                assert missing["shown"].startswith(NOT_HERE)
            # a line outside the run: measured, kept by the frame, the link in the hash
            page.evaluate("(hash) => { location.hash = hash; }", _app("", OUTSIDE))
            measured = _wait(page, "s.measured !== null")
            assert measured["measuredLink"] == OUTSIDE and measured["measured"] == 80, measured
            assert measured["note"] is None, measured
            assert measured["selected"] is None and measured["hash"] == f"#run={BIG}&line={OUTSIDE}", measured
            assert page.evaluate("() => PROFILE_ASKS") == ["49.5000000,19.1000000,49.5004000,19.1005000"]
            # a move of the map, a level: the link stays
            _state(page, "view.setLevel('spots'); leaflet.panBy([30, 0], {animate: false});")
            assert page.evaluate("() => K.state()")["hash"] == f"#run={BIG}&line={OUTSIDE}"
            # a selection ends the measured line
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({a['spot']}, {a['row']})")
            ended = _wait(page, "s.measured === null && s.selected !== null")
            assert ended["measuredLink"] is None and ended["hash"] == f"#run={BIG}&line={a['link']}", ended
            assert ended["history"] == entries + 3
            assert page.errors == []
        finally:
            browser.close()


# The server's profile refused (a link outside the run cannot be measured)
PROFILE_FAILS = """
const realFetchOfFails = window.fetch;
window.fetch = (url, init) => String(url).startsWith("/api/profile")
  ? Promise.resolve(new Response(JSON.stringify({detail: "no profile here"}), {status: 400, headers: {"content-type": "application/json"}}))
  : realFetchOfFails(url, init);
"""


@BROWSER
def test_phone_note_raises_the_sheet(site):
    """A phone opened at a link that ends in a note raises its sheet from the low start to half, where the note stands:
    a line not in the run, a line outside it whose measurement fails (the note comes later); a link that opens its
    line keeps the low start (test_open_by_link_and_write)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for line, note in (("1,2,3", NOT_HERE), (OUTSIDE, "The line of the link could not be measured: ")):
                page = _page(browser, _app(site, line), PHONE, PROFILE_FAILS)
                s = _wait(page, "s.note !== null && s.snap === 'half'")
                assert s["note"][0].startswith(note) and s["selected"] is None and s["shown"].startswith(note), s
                assert page.errors == []
                page.context.close()
        finally:
            browser.close()


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_map_page(site, device):
    """A run's map.html over http: #line= opens the line; a selection writes #line=… in place, none leaves no hash; a
    hashchange opens the new link; a line "Top level only" alone hides turns the chip off."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    root = site.split("/runs/")[0]
    url = f"{root}/runs/{urllib.parse.quote(BIG)}/map.html"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, url, context)
            a, b, top = facts["a"], facts["b"], facts["top"]
            page = _page(browser, f"{url}#line={urllib.parse.quote(a['link'], safe='')}", context)
            s = _wait(page, "s.selected !== null")
            assert s["selected"] == [a["spot"], a["row"]] and s["inView"] and s["hash"] == f"#line={a['link']}", s
            entries = s["history"]
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({b['spot']}, {b['row']})")
            assert _wait(page, f"s.hash === '#line={b['link']}'")["history"] == entries
            page.keyboard.press("Escape")
            assert _wait(page, "s.selected === null && s.hash === ''")["history"] == entries
            page.evaluate("(hash) => { location.hash = hash; }", "#line=" + urllib.parse.quote(top["link"], safe=""))
            lifted = _wait(page, f"s.selected !== null && s.selected[1] === {top['row']}")
            assert lifted["topOnly"] is False and lifted["inView"] and lifted["hash"] == f"#line={top['link']}", lifted
            assert page.errors == []
        finally:
            browser.close()


TOKEN = "AbCdEf0123456789-viewlink_token-xyzXY01"  # a share link's token (token_urlsafe's alphabet)


@pytest.fixture
def share_site(tmp_path, view_clip, account_settings):
    """The public site with the view's clip run shared (/s/<TOKEN>/); yields the share page's address."""
    import uvicorn

    import accounts as ac
    import web
    from jobs import Jobs
    from settings import PublicSettings
    from test_public import copy_run, session_of
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site_url = f"http://localhost:{port}"
    data = tmp_path / "data"
    data.mkdir()
    jobs = Jobs(str(data))
    user_id, _, _ = session_of(data, account_settings, "a")
    copy_run(view_clip, data, BIG, "Shared clip")  # the share route serves the viewer from viewer/dist
    jobs.add_run(BIG, user_id, 1)
    jobs.set_share(BIG, ac.digest(TOKEN))
    settings = PublicSettings(public_url=site_url, trusted_proxy="127.0.0.1", contact="admin@example.org")
    app = web.create_app(str(data), public=settings, accounts=account_settings)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.05)
        yield f"{site_url}/s/{TOKEN}/map.html"
    finally:
        server.should_exit = True
        thread.join(10)


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_share_page(share_site, device):
    """A share link's page (/s/<token>/map.html) behaves as the map's: #line= opens the line in view; a selection
    writes #line=… in place, none leaves no hash; a hashchange opens the new link; a line "Top level only" alone hides
    turns the chip off; a link to no line of the run gets today's note; a line outside the run is measured (a share
    page asks profiles since 2026-11-26, D1/D3: as the map's); a line other filters hide gets today's note, whose "clear filters" opens it; Back and
    Forward open the links again."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    hash_of = lambda link: "#line=" + urllib.parse.quote(link, safe="")  # noqa: E731
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            facts = _facts(browser, share_site, context)
            a, b, top = facts["a"], facts["b"], facts["top"]
            page = _page(browser, f"{share_site}{hash_of(a['link'])}", context, PROFILE_STUB)
            s = _wait(page, "s.selected !== null")
            assert s["selected"] == [a["spot"], a["row"]] and s["inView"] and s["hash"] == f"#line={a['link']}", s
            assert page.evaluate("() => window.FINDALINE_RUNS === undefined || window.FINDALINE_RUNS.length === 0")
            entries = s["history"]
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({b['spot']}, {b['row']})")
            assert _wait(page, f"s.hash === '#line={b['link']}'")["history"] == entries
            page.keyboard.press("Escape")
            assert _wait(page, "s.selected === null && s.hash === ''")["history"] == entries
            page.evaluate("(hash) => { location.hash = hash; }", "#line=" + urllib.parse.quote(top["link"], safe=""))
            lifted = _wait(page, f"s.selected !== null && s.selected[1] === {top['row']}")
            assert lifted["topOnly"] is False and lifted["inView"] and lifted["hash"] == f"#line={top['link']}", lifted
            # no line of the run: today's note; the selection stays, and the hash names it again (as today's page)
            page.evaluate("(hash) => { location.hash = hash; }", "#line=1,2,3")
            missing = _wait(page, "s.note !== null")
            assert missing["note"] == [NOT_HERE, None] and missing["selected"] == lifted["selected"], missing
            assert missing["hash"] == f"#line={top['link']}", missing
            # a line outside the run: measured (the server's /s/runs.js sends profiles: true), no note, the link kept
            page.keyboard.press("Escape")
            page.evaluate("() => window.FINDALINE_VIEW.view.model.setNote(null)")
            page.evaluate("(hash) => { location.hash = hash; }", hash_of(OUTSIDE))
            outside = _wait(page, "s.measured !== null")
            assert outside["note"] is None and outside["measuredLink"] == OUTSIDE and outside["measured"] == 80, outside
            assert outside["selected"] is None and outside["hash"] == f"#line={OUTSIDE}", outside
            assert page.evaluate("() => PROFILE_ASKS") == ["49.5000000,19.1000000,49.5004000,19.1005000"]
            # hidden by another filter: today's note; its "clear filters" opens the line
            page.evaluate("() => window.FINDALINE_VIEW.view.model.setNote(null)")
            page.evaluate(LONGER, a["len"])
            page.evaluate("(hash) => { location.hash = hash; }", hash_of(a["link"]))
            hidden = _wait(page, "s.note !== null" + (" && s.snap === 'half'" if device == "phone" else ""))
            assert hidden["note"] == [HIDDEN, CLEAR] and hidden["selected"] is None, hidden
            assert hidden["hash"] == f"#line={a['link']}" and hidden["shown"].startswith(HIDDEN), hidden
            page.click(f".vl-lnote button:text-is('{CLEAR}')")
            cleared = _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")
            assert cleared["note"] is None and cleared["lenMin"] is None and cleared["hash"] == f"#line={a['link']}"
            # Back and Forward
            page.evaluate("(hash) => { location.hash = hash; }", hash_of(b["link"]))
            _wait(page, f"s.selected !== null && s.selected[1] === {b['row']}")
            page.go_back()
            back = _wait(page, f"s.selected !== null && s.selected[1] === {a['row']}")
            assert back["hash"] == f"#line={a['link']}" and back["inView"], back
            page.go_forward()
            forward = _wait(page, f"s.selected !== null && s.selected[1] === {b['row']}")
            assert forward["hash"] == f"#line={b['link']}" and forward["inView"], forward
            assert page.errors == []
        finally:
            browser.close()


# A share page's flags as the server sends them since 2026-11-26 (/s/runs.js: profiles on, D3), whatever this server
# sends; the profiles asked, each with its address and its X-Findaline-Share header; while REFUSE > 0 the answer is
# a 429 of a link's rate with Retry-After: 2 (the server's code and its {{wait}}: the page draws the catalogue's text)
RATE_WAIT = "1 min"  # the server's {{wait}} (a no-break space)
RATE_TEXT = WORDS["error.rate_link_profile"].replace("{{wait}}", RATE_WAIT)
SHARE_PROFILES = """
Object.defineProperty(window, "FINDALINE_APP", {configurable: true, get() { return window.__app; },
  set(v) { window.__app = v && {...v, profiles: true}; }});
window.SHARE_ASKS = [];
window.REFUSE = 0;
const realFetchOfShare = window.fetch;
window.fetch = (url, init) => {
  if (!String(url).startsWith("/api/profile")) return realFetchOfShare(url, init);
  const headers = (init && init.headers) || {};
  SHARE_ASKS.push({url: String(url), line: decodeURIComponent(String(url).split("line=")[1]),
                   share: headers["X-Findaline-Share"] ?? null, at: performance.now()});
  if (window.REFUSE > 0) {
    window.REFUSE--;
    return Promise.resolve(new Response(JSON.stringify({detail: {code: "rate_link_profile", params: {wait: "1\u00a0min"},
      message: "%s"}}), {status: 429, headers: {"content-type": "application/json", "Retry-After": "2"}}));
  }
  return Promise.resolve(new Response(JSON.stringify({d: [0, 20, 40, 60, 80], z: [300, 296, 292, 296, 301], min: [40, 7.5],
    water_m: 0, filled_m: 0}), {headers: {"content-type": "application/json"}}));
};
// the rows of the view's lines without a saved profile, and one with: the clip's run saves every line's profile (a
// circle), so four passing lines of four spots lose theirs as an area's lines do (no Line of them made yet)
window.S = {
  unsaved() { const {view} = window.FINDALINE_VIEW, m = view.model, out = [], spots = new Set();
    for (let row = view.count - 1; row >= 0 && out.length < 4; row--) {
      const spot = view.spotOf(row);
      if (view.passes(row) && !spots.has(spot) && !m.made.has(row)) { spots.add(spot); out.push([spot, row]); }
    }
    const source = m.data.columns.profiles, get = source.get.bind(source), rows = out.map((r) => r[1]);
    source.get = (i) => rows.includes(i) ? undefined : get(i);
    return out.filter(([, row]) => !m.lineAt(row).prof); },
  saved() { const {view} = window.FINDALINE_VIEW, m = view.model;
    for (let row = 0; row < view.count; row++) if (view.passes(row) && m.lineAt(row).prof) return [view.spotOf(row), row];
    return null; },
  // every answer of the model's profile(line), by the line's key: what the dock shows comes from it
  watch() { const m = window.FINDALINE_VIEW.view.model, real = m.profile.bind(m); window.OUTCOMES = [];
    m.profile = (l) => real(l).then((p) => { OUTCOMES.push({key: m.lineLink(l), error: null}); return p; },
                                    (e) => { OUTCOMES.push({key: m.lineLink(l), error: e.message}); throw e; }); },
  keyOf(row) { const m = window.FINDALINE_VIEW.view.model; return m.lineLink(m.lineAt(row)); },
  dock() { const d = document.querySelector(".r-dock"); if (!d) return null;
    return {error: d.querySelector(".r-error")?.textContent ?? null, ready: !!d.querySelector(".r-profile"),
            busy: !!d.querySelector("[aria-busy]")}; },
};
""" % RATE_TEXT


@BROWSER
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_share_page_profiles_and_3d(share_site, device):
    """A share link's page with the flags the server sends (profiles: true, D1, D3): a line with a saved profile asks
    nothing; one without asks /api/profile with X-Findaline-Share: <the page's token> and no token in the address;
    Measure is offered and a measurement asks so too; the "3D view" button's href is view3d#run=…&line=…, which
    resolves to /s/<token>/view3d. After a 429 with Retry-After: 2 no profile is asked for 2 s (the server's text
    shown in the dock), then again."""
    from playwright.sync_api import sync_playwright
    context = DESKTOP if device == "desktop" else PHONE
    base = share_site.rsplit("/", 1)[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _page(browser, share_site, context, SHARE_PROFILES)
            assert page.evaluate("() => window.FINDALINE_VIEW.view.model.canCompute") is True
            unsaved, saved = page.evaluate("() => S.unsaved()"), page.evaluate("() => S.saved()")
            assert len(unsaved) >= 4 and saved, (unsaved, saved)
            # a saved profile: nothing asked; the 3D button under the link
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({saved[0]}, {saved[1]})")
            page.wait_for_function("() => { const d = S.dock(); return d && d.ready; }", timeout=WAIT)
            page.wait_for_selector(".r-view3d", state="attached", timeout=WAIT)
            href, resolved, hash = page.evaluate("""() => { const a = document.querySelector('.r-view3d'), v = window.FINDALINE_VIEW.view;
                return [a.getAttribute('href'), new URL(a.getAttribute('href'), location.href).pathname,
                        '#run=' + encodeURIComponent(v.model.runId) + '&line=' + encodeURIComponent(v.model.lineLink(v.selected.line))]; }""")
            assert href.startswith("view3d" + hash) and resolved == f"/s/{TOKEN}/view3d", (href, resolved)
            assert page.evaluate("() => SHARE_ASKS") == []
            # no saved profile: asked with the header
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({unsaved[0][0]}, {unsaved[0][1]})")
            page.wait_for_function("() => { const d = S.dock(); return d && d.ready; }", timeout=WAIT)
            asks = page.evaluate("() => SHARE_ASKS")
            assert len(asks) == 1 and asks[0]["share"] == TOKEN and TOKEN not in asks[0]["url"], asks
            # Measure is offered; a measurement asks with the header
            actions = page.evaluate("() => [...document.querySelectorAll('.r-actions button')].map((b) => b.textContent.trim() || b.getAttribute('aria-label'))")
            assert WORDS["ui.actions.measure"] in actions, actions
            page.evaluate("() => window.FINDALINE_VIEW.view.model.measure([49.5, 19.1], [49.5004, 19.1005])")
            page.wait_for_function("() => SHARE_ASKS.length === 2", timeout=WAIT)
            measured = page.evaluate("() => SHARE_ASKS[1]")
            assert measured["share"] == TOKEN and measured["line"] == "49.5000000,19.1000000,49.5004000,19.1005000", measured
            # a 429: the server's text, nothing asked for 2 s, then asked again
            page.evaluate("() => { window.REFUSE = 1; }")
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({unsaved[1][0]}, {unsaved[1][1]})")
            page.wait_for_function("() => { const d = S.dock(); return d && d.error !== null; }", timeout=WAIT)
            assert RATE_TEXT in page.evaluate("() => S.dock().error")
            refused_at = page.evaluate("() => SHARE_ASKS[2].at")
            # during the wait: the selected line's own profile is refused with the text (its outcome, by its key, before
            # the dock is read: the dock keeps the line before's error until its effect ran), nothing asked
            page.evaluate("() => S.watch()")
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({unsaved[2][0]}, {unsaved[2][1]})")
            key = page.evaluate(f"() => S.keyOf({unsaved[2][1]})")
            page.wait_for_function("(key) => OUTCOMES.some((o) => o.key === key)", arg=key, timeout=WAIT)
            page.evaluate("() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))")
            during = page.evaluate("(key) => [SHARE_ASKS.length, OUTCOMES.find((o) => o.key === key).error, S.dock().error, "
                                   "performance.now()]", key)
            assert during[0] == 3 and RATE_TEXT in during[1] and RATE_TEXT in during[2], during
            assert during[3] - refused_at < 2000, during
            page.wait_for_function(f"() => performance.now() - {refused_at} > 2050", timeout=WAIT)
            page.evaluate(f"() => window.FINDALINE_VIEW.view.select({unsaved[3][0]}, {unsaved[3][1]})")
            page.wait_for_function("() => { const d = S.dock(); return d && d.ready; }", timeout=WAIT)
            again = page.evaluate("() => SHARE_ASKS")
            assert len(again) == 4 and again[3]["share"] == TOKEN, again
            assert all(TOKEN not in a["url"] for a in again) and base.endswith(TOKEN)
            assert page.errors == []
        finally:
            browser.close()


# The sheet's checks: the selected line against the part of the map a person sees (above the sheet), the sheet at
# rest (its height drawn as its stop gives it), the map's centre in its container's pixels
SHEET = r"""
window.S = {
  rest() { const s = document.querySelector(".u-sheet"); return !!s && !!s.style.height && Math.abs(s.getBoundingClientRect().height - parseFloat(s.style.height)) < 1; },
  snap() { const s = document.querySelector(".u-sheet"); return ["peek", "half", "full"].find((k) => s.classList.contains("u-" + k)); },
  // both anchors of the selected line in the part of the map a person sees (SpotMap's free part: above the sheet)
  seen() { const {view} = T.v(), sel = view.selected; if (!sel) return null; const e = T.ends(sel.row), f = T.free();
    return [[e[0], e[1]], [e[2], e[3]]].every(([x, y]) => x >= f[0] && x <= f[2] && y >= f[1] && y <= f[3]); },
  // ... and under the level switch (the phone's top bar and the switch cover the map's top)
  under() { const sel = T.v().view.selected; if (!sel) return null; const e = T.ends(sel.row);
    const top = document.querySelector(".v-map .v-switch").getBoundingClientRect().bottom - T.box().top; return e[1] >= top && e[3] >= top; },
  // ... and clear of the whole bar (under the switch, above the foot): K.inView
  clear() { const sel = T.v().view.selected; return sel ? K.inView(sel.row) : null; },
  // ... and above the data credits band (a press on an anchor there would open a credit's link)
  credits() { const sel = T.v().view.selected; if (!sel) return null; const e = T.ends(sel.row), c = this.creditsTop();
    return c === null || (e[1] <= c && e[3] <= c); },
  // the credits band's top, px of the map's box (null: no band)
  creditsTop() { const r = document.querySelector(".v-map .leaflet-control-attribution")?.getBoundingClientRect();
    return r && r.width && r.height ? r.top - T.box().top : null; },
  // the room a line is brought into: the map's width, from under the switch to the credits band's top (or the sheet)
  room() { const sw = document.querySelector(".v-map .v-switch").getBoundingClientRect(), top = Math.round(sw.bottom - T.box().top) + 4;
    const c = this.creditsTop(), f = T.free(); return {width: f[2], top, bottom: c !== null && c > top && c < f[3] ? c : f[3]}; },
  // the selected line's width and height on the screen, px
  extent() { const e = T.ends(T.v().view.selected.row); return [Math.abs(e[2] - e[0]), Math.abs(e[3] - e[1])]; },
  level() { const {view} = T.v(); return [view.level, view.auto]; },
  centre() { const c = window.FINDALINE_MAP.latLngToContainerPoint(window.FINDALINE_MAP.getCenter()); return [c.x, c.y]; },
  where() { const m = window.FINDALINE_MAP, c = m.getCenter(); return [c.lat, c.lng, m.getZoom()]; },
  // the lowest number on the map (B or P: a press selects its line): the line a sheet that rises covers first
  lowest() { const {view, map} = T.v(); return map.drawn().numbers.filter((n) => n.label[0] === "B" || n.label[0] === "P")
      .map((n) => ({label: n.label, x: (n.box.left + n.box.right) / 2, y: (n.box.top + n.box.bottom) / 2}))
      .sort((a, b) => b.y - a.y)[0] || null; },
};
"""


def _handle_tap(page):
    """A finger's tap on the sheet's handle: the sheet goes one stop up (from full: down to peek)."""
    box = page.locator(".u-sheet-handle").bounding_box()
    _tap(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _rested(page, snap: str) -> dict:
    """Wait until the sheet rests at `snap` and the frame has checked it (data-sheet-checks moved on); the checks."""
    page.wait_for_function(f"() => S.snap() === '{snap}' && S.rest()", timeout=WAIT)
    page.wait_for_function("(n) => +(document.querySelector('.v-map').dataset.sheetChecks || 0) > n",
                           arg=page.evaluate("() => window.CHECKS_BEFORE || 0"), timeout=WAIT)
    page.evaluate("() => T.frames()")
    return page.evaluate("() => ({seen: S.seen(), under: S.under(), clear: S.clear(), credits: S.credits(), "
                         "where: S.where(), snap: S.snap(), free: T.free(), room: S.room(), level: S.level(), "
                         "moves: window.MOVES, checks: +(document.querySelector('.v-map').dataset.sheetChecks || 0)})")


def _mark_checks(page):
    """Note the frame's count of sheet checks before a change of the sheet, and count the map's `move` events from
    now on (an animated pan fires one per frame, a jump one)."""
    page.evaluate("() => { window.CHECKS_BEFORE = +(document.querySelector('.v-map').dataset.sheetChecks || 0); "
                  "window.MOVES = 0; if (window.MOVES_ON !== window.FINDALINE_MAP) { window.MOVES_ON = window.FINDALINE_MAP; "
                  "window.FINDALINE_MAP.on('move', () => { window.MOVES++; }); } }")


@BROWSER
@pytest.mark.skipif(not _playwright(), reason="needs Playwright with Chromium and WebKit (group ui)")
@pytest.mark.parametrize("device, engine", [("iPhone 13", "webkit"), ("Pixel 7", "chromium")])
def test_sheet_rises(site, tmp_path, device, engine):
    """On both phones (Playwright's profiles, real touch taps): a line selected with a tap while the sheet is low,
    then the sheet raised to half by a tap on its handle: the line is in the part of the map a person sees (the
    least pan at the same zoom brings it there); at full, where the map shows nothing, the map does not move. A line
    the person moved out of sight before the sheet rose stays where the person left it. Pictures in tmp_path/shots."""
    from playwright.sync_api import sync_playwright
    shots = tmp_path / "shots"
    shots.mkdir()
    name = device.replace(" ", "-").lower()
    with sync_playwright() as p:
        kind = getattr(p, engine)
        if not os.path.exists(kind.executable_path):
            pytest.skip(f"Playwright's {engine} is not installed")
        browser = kind.launch()
        try:
            options = dict(p.devices[device])
            options.pop("default_browser_type", None)
            page = _page(browser, _app(site), options, SHEET)
            page.wait_for_function("() => S.snap() === 'peek' && S.rest()", timeout=WAIT)
            page.evaluate("() => T.frames()")
            # a tap on the lowest number while the sheet is low
            number = page.evaluate("() => S.lowest()")
            assert number, "no number on the map"
            _tap(page, number["x"], number["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.selected !== null", timeout=WAIT)
            page.evaluate("() => T.frames()")
            low = page.evaluate("() => ({seen: S.seen(), where: S.where(), free: T.free()})")
            page.screenshot(path=str(shots / f"{name}-1-low.png"))
            assert low["seen"], low
            # the sheet raised to half by a tap on its handle
            _mark_checks(page)
            _handle_tap(page)
            half = _rested(page, "half")
            page.screenshot(path=str(shots / f"{name}-2-half.png"))
            print(f"{device}: low {low}, half {half}")
            # in sight under the top bar and the switch and above the credits band, at the same zoom (clear of the foot
            # too where it fits there), by an animated pan (a move event per frame)
            assert half["seen"] and half["under"] and half["credits"] and half["where"][2] == low["where"][2], (low, half)
            assert half["where"] != low["where"]  # the map moved: the line was under the sheet (verified, 2026-11-20)
            assert half["moves"] >= 3, half
            # full: the map shows nothing above the sheet; it does not move
            _mark_checks(page)
            _handle_tap(page)
            full = _rested(page, "full")
            page.screenshot(path=str(shots / f"{name}-3-full.png"))
            assert full["where"] == half["where"], (half, full)
            # down to peek: the line stays in sight, nothing moves
            _mark_checks(page)
            _handle_tap(page)
            peek = _rested(page, "peek")
            assert peek["where"] == half["where"] and peek["seen"], peek
            # the person moves the line out of sight (a drag of the map), then raises the sheet: the map stays
            box = page.evaluate("() => { const b = T.box(); return [b.left + b.width / 2, b.top + b.height / 3]; }")
            # the drag's end: its last moveend (after Leaflet's inertia, which goes on once the finger is lifted)
            ended = "() => { window.DRAGGED = false; window.FINDALINE_MAP.once('moveend', () => { window.DRAGGED = true; }); }"
            cdp = page.context.new_cdp_session(page) if engine == "chromium" else None
            if cdp:
                points = [{"x": box[0], "y": box[1] + dy, "id": 1} for dy in range(0, 401, 40)]
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [points[0]]})
                for point in points[1:]:
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
                page.evaluate(ended)
                cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                page.evaluate("() => { window.TOUCHED = performance.now(); }")
            else:  # WebKit has no touch moves in Playwright: the map moved as a drag would (its own pan)
                page.evaluate(ended)
                page.evaluate("() => window.FINDALINE_MAP.panBy([0, -400], {animate: false})")
            page.wait_for_function("() => window.DRAGGED && S.seen() === false", timeout=WAIT)
            page.evaluate("() => T.frames()")
            moved = page.evaluate("() => S.where()")
            page.screenshot(path=str(shots / f"{name}-4-moved.png"))
            _mark_checks(page)
            _handle_tap(page)
            kept = _rested(page, "half")
            page.screenshot(path=str(shots / f"{name}-5-half-kept.png"))
            assert kept["where"] == moved and kept["seen"] is False, (moved, kept)
            # WebKit reports "ResizeObserver loop completed with undelivered notifications." at every change of the
            # sheet's stop, also without the frame's check (seen on view-seams' frame, 2026-11-20): not this test's
            assert [e for e in page.errors if not e.startswith("ResizeObserver loop")] == []
        finally:
            browser.close()


# A spot's shown line in view placed by the map's move: the shortest on the screen, its middle `up` px above the
# sheet (the line clear of the bar after the sheet rose); or the steepest, fitted into the part above the low sheet
# (too tall for the part above the sheet at half)
PLACE = r"""
window.P = {
  short(up) { const {view} = T.v(), f = T.free(); let best = null;
    for (const spot of Array.from(view.inView.spots)) { const row = view.shownOf(spot), e = T.ends(row), px = Math.hypot(e[2] - e[0], e[3] - e[1]);
      if (px > 4 && (!best || px < best.px)) best = {spot, row, px, mid: [(e[0] + e[2]) / 2, (e[1] + e[3]) / 2]}; }
    window.FINDALINE_MAP.panBy([best.mid[0] - f[2] / 2, best.mid[1] - (f[3] - up)], {animate: false});
    view.select(best.spot, best.row); return best; },
  steep() { const {view} = T.v(), c = view.model.data.columns; let best = null;
    for (const spot of Array.from(view.order)) { const row = view.shownOf(spot), dy = Math.abs(c.lat1.at(row) - c.lat2.at(row)),
        dx = Math.abs(c.lon1.at(row) - c.lon2.at(row)) * Math.cos(c.lat1.at(row) * Math.PI / 180), len = view.values.len[row];
      if (len > 60 && (!best || dy / (dx + 1e-9) > best.ratio)) best = {spot, row, ratio: dy / (dx + 1e-9)}; }
    const covered = T.box().height - T.free()[3];
    window.FINDALINE_MAP.fitBounds([[c.lat1.at(best.row), c.lon1.at(best.row)], [c.lat2.at(best.row), c.lon2.at(best.row)]],
                                   {paddingTopLeft: [20, 130], paddingBottomRight: [20, covered + 30], animate: false});
    view.select(best.spot, best.row); return best; },
};
"""


@BROWSER
@pytest.mark.skipif(not _playwright(), reason="needs Playwright with Chromium and WebKit (group ui)")
@pytest.mark.parametrize("device, engine", [("iPhone 13", "webkit"), ("Pixel 7", "chromium")])
def test_sheet_moves(site, device, engine):
    """The sheet's other ways: raised twice at once to full (the first stop's check never made) and lowered to half,
    the line selected low comes back into sight there; a short line near the sheet comes back clear of the whole bar
    (under the switch, above the foot); a line too tall for the room at half (under the switch, above the credits
    band) is fitted into it by the least zoom out (Leaflet's quarter steps) and is in sight."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        kind = getattr(p, engine)
        if not os.path.exists(kind.executable_path):
            pytest.skip(f"Playwright's {engine} is not installed")
        browser = kind.launch()
        try:
            options = dict(p.devices[device])
            options.pop("default_browser_type", None)

            def fresh():
                page = _page(browser, _app(site), options, SHEET + PLACE)
                page.wait_for_function("() => S.snap() === 'peek' && S.rest()", timeout=WAIT)
                page.evaluate("() => T.frames()")
                return page
            # up twice at once, then down to half
            page = fresh()
            number = page.evaluate("() => S.lowest()")
            _tap(page, number["x"], number["y"])
            page.wait_for_function("() => window.FINDALINE_VIEW.view.selected !== null", timeout=WAIT)
            low = page.evaluate("() => ({seen: S.seen(), where: S.where()})")
            assert low["seen"], low
            _mark_checks(page)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowUp")
            full = _rested(page, "full")
            assert full["where"] == low["where"], full  # no room at full: nothing moves
            _mark_checks(page)
            page.keyboard.press("ArrowDown")
            half = _rested(page, "half")
            assert half["seen"] and half["under"] and half["credits"] and half["where"][2] == low["where"][2], (low, half)
            page.context.close()
            # a short line just above the low sheet: clear of the whole bar at half, the same zoom
            page = fresh()
            placed = page.evaluate("() => P.short(40)")
            page.evaluate("() => T.frames()")
            before = page.evaluate("() => ({seen: S.seen(), where: S.where()})")
            assert before["seen"], (placed, before)
            _mark_checks(page)
            _handle_tap(page)
            clear = _rested(page, "half")
            assert clear["clear"] and clear["where"][2] == before["where"][2], clear
            assert clear["where"] != before["where"], clear  # it was under the sheet: the map moved
            page.context.close()
            # a line too tall for the room at half: the least zoom out that fits it there (16 px margins), in sight
            page = fresh()
            page.evaluate("() => P.steep()")
            page.evaluate("() => T.frames()")
            before = page.evaluate("() => ({seen: S.seen(), where: S.where(), extent: S.extent(), level: S.level()})")
            assert before["seen"], before
            _mark_checks(page)
            _handle_tap(page)
            fitted = _rested(page, "half")
            room = fitted["room"]
            need =math.log2(min((room["width"] - 32) / before["extent"][0], (room["bottom"] - room["top"] - 32) / before["extent"][1]))
            z0, z1 = before["where"][2], fitted["where"][2]
            print(f"{device}: zoom {z0} -> {z1} (the room needs {need:+.2f}: {room}); level {before['level']} -> {fitted['level']}")
            assert z0 + need - 0.25 - 1e-6 <= z1 <= z0 + need + 1e-6, (before, fitted, need)
            assert fitted["seen"] and fitted["under"] and fitted["credits"], fitted
            assert [e for e in page.errors if not e.startswith("ResizeObserver loop")] == []
        finally:
            browser.close()


def _sheet_page(browser, site, context):
    """The app's page of the run in the view, the sheet low and at rest, with the sheet's and the placing helpers."""
    page = _page(browser, _app(site), context, SHEET + PLACE + GLIDE)
    page.wait_for_function("() => S.snap() === 'peek' && S.rest()", timeout=WAIT)
    page.evaluate("() => T.frames()")
    return page


@BROWSER
@pytest.mark.parametrize("height", [375, 360])
def test_sheet_room_band(site, height):
    """A phone on its side (667 px wide): the room under the switch and above the credits band at half is smaller than
    a zoom needs (the code review's F2): a short line just above the low sheet comes into it at the same zoom. (Such a
    phone sees the notice to turn it upright over an inert page, the user's gate-2 answer 4 a: asserted first, then
    hidden for the band's checks, which still guard the sheet's room.)"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _sheet_page(browser, site, {**SIDE_PHONE, "viewport": {"width": 667, "height": height}})
            assert page.evaluate("() => [...document.querySelector('.v-upright').parentElement.children].filter((e) => !e.classList.contains('v-upright')).every((e) => e.inert)")
            _upright_then_hidden(page)  # (4 a: the notice over an inert page; the band's checks under it)
            page.evaluate("() => P.short(30)")
            page.evaluate("() => T.frames()")
            before = page.evaluate("() => ({seen: S.seen(), where: S.where()})")
            assert before["seen"], before
            _mark_checks(page)
            page.focus(".u-sheet-handle")
            page.keyboard.press("ArrowUp")
            half = _rested(page, "half")
            room = half["room"]["bottom"] - half["room"]["top"]
            print(f"{height}: room at half {room:.0f} px, zoom {before['where'][2]} -> {half['where'][2]}")
            assert room - 32 < 48, half  # the band: too small for a zoom
            assert half["where"][2] == before["where"][2] and half["seen"] and half["credits"], (before, half)
            assert page.errors == []
        finally:
            browser.close()


# A finger's drag as Leaflet fires it (movestart and dragstart, a pan, dragend; no moveend), then its glide (panBy
# without movestart, `ms` long), and the sheet's handle pressed at once: the code review's stand-in (F1)
GLIDE = r"""
window.G = {
  drag(dy, glide, ms) { const m = window.FINDALINE_MAP;
    window.GLIDE_END = null;
    m.fire('movestart'); m.fire('dragstart'); m._rawPanBy([0, dy]); m.fire('move'); m.fire('drag'); m.fire('dragend');
    m.once('moveend', () => { window.GLIDE_END = S.where(); });
    m.panBy([0, glide], {animate: true, duration: ms / 1000, easeLinearity: 0.2, noMoveStart: true});
    document.querySelector('.u-sheet-handle').click(); },
};
"""


@BROWSER
@pytest.mark.parametrize("ms", [100, 160])
def test_sheet_glide(site, ms):
    """A line in sight moved out of sight by a drag whose glide is still going when the sheet's handle is pressed: the
    person's move, kept (the map stays where the glide ends)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _sheet_page(browser, site, PHONE)
            page.evaluate("() => P.short(300)")
            page.evaluate("() => T.frames()")
            assert page.evaluate("() => S.seen()")
            _mark_checks(page)
            page.evaluate(f"() => G.drag(-400, -40, {ms})")
            page.wait_for_function("() => window.GLIDE_END !== null", timeout=WAIT)
            half = _rested(page, "half")
            assert half["where"] == page.evaluate("() => window.GLIDE_END") and half["seen"] is False, half
            assert page.errors == []
        finally:
            browser.close()


# The sheet slowed down to 6 s (the CSSOM: the page's CSP allows no style element), and when the frame's count of
# checks moves on: the time and whether the sheet rested then
SLOW = r"""() => { const col = document.querySelector('.v-map');
  window.CAP = {at: null, rest: null, tapped: performance.now(), col, checks: +(col.dataset.sheetChecks || 0)};
  new MutationObserver(() => { if (CAP.at === null) { CAP.at = performance.now(); CAP.rest = S.rest(); } })
    .observe(col, {attributes: true, attributeFilter: ['data-sheet-checks']});
  document.querySelector('.u-sheet').style.transition = 'height 6s linear';
  document.querySelector('.u-sheet-handle').click(); }"""


@BROWSER
def test_sheet_rest_cap(site):
    """A sheet that does not come to rest (its move slowed to 6 s): the check is made once SHEET_REST_MS (1.5 s) has
    passed, while the sheet still moves."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _sheet_page(browser, site, PHONE)
            page.evaluate(SLOW)
            page.wait_for_function("() => CAP.at !== null", timeout=WAIT)
            cap = page.evaluate("() => ({after: CAP.at - CAP.tapped, rest: CAP.rest})")
            assert 1400 <= cap["after"] < 5000 and cap["rest"] is False, cap
            assert page.errors == []
        finally:
            browser.close()


@BROWSER
def test_sheet_unmount_while_waiting(site):
    """The result page left (Home) while the check waits for the sheet to rest: no error, no move of the map and no
    check after. The one wait for a time here is the check's own limit (1.5 s, then 0.5 s more): only the time can
    show that nothing comes after it."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _sheet_page(browser, site, PHONE)
            page.evaluate("() => P.short(30)")  # a line the sheet at half covers
            page.evaluate("() => T.frames()")
            # the old map's moves and the hook's two ways of moving it, counted
            page.evaluate("""() => { const m = window.FINDALINE_MAP; window.OLD = {moves: 0, calls: 0};
                m.on('movestart', () => { OLD.moves++; });
                for (const name of ['panBy', 'fitBounds']) { const own = m[name]; m[name] = function (...a) { OLD.calls++; return own.apply(this, a); }; } }""")
            page.evaluate(SLOW)
            page.evaluate("() => { location.hash = '#home'; }")
            page.wait_for_function("() => !document.querySelector('.v-map') && !!document.querySelector('.c-home-main, .c-cards')",
                                   timeout=WAIT)
            page.wait_for_function("() => performance.now() - CAP.tapped > 2000", timeout=WAIT)
            assert page.evaluate("() => [OLD.moves, OLD.calls, CAP.at]") == [0, 0, None]
            assert page.errors == []
        finally:
            browser.close()
