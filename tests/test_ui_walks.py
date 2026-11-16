"""tools/ui_walks.py: the walks' data, the counting on pages of the test's own (Playwright's Edge, as
tests/test_web.py), a dead end, the totals and the guard against starting a search. The walks themselves run by
hand (the tool's docstring)."""

import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import ui_shots  # noqa: E402
import ui_walks as uw  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USERS = list(ui_shots.RIGGERS) + ["admin", "walker"]
SHORT = 3000  # ms: a missing element's dead end comes after this (a bound, never a pause)


def _playwright() -> bool:
    return importlib.util.find_spec("playwright") is not None


browser_test = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                  reason="needs Microsoft Edge and Playwright (group ui)")


@pytest.fixture(scope="module")
def page():
    """A page of Playwright's Edge, 800 × 600, for the test's own HTML."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            yield browser.new_page(viewport={"width": 800, "height": 600})
        finally:
            browser.close()


def test_walks_data_has_a_known_shape():
    """Every walk of WALKS: a known user, device and memory, a path, steps of known kinds with their fields; the
    walk with "skip" says why. A broken walk is named with what is wrong."""
    assert uw.walk_errors(uw.WALKS, USERS, ui_shots.DEVICES) == []
    assert all(w["user"] in USERS + [uw.VISITOR] for w in uw.WALKS.values())
    assert {w["device"] for w in uw.WALKS.values()} <= set(ui_shots.DEVICES)
    assert list(uw.WALKS)[-1] == "R4"  # it saves a favourite: the walks before it see Home as served
    broken = {"X": {"title": "x", "user": "nobody", "device": "fridge", "memory": "some", "start": "home",
                    "steps": [{"kind": "jump"}, uw.tap(""), uw.sign_in("visitor", "/"), "tap"]},
              "Y": {"title": "y", "user": "admin", "device": "desktop", "memory": "new", "start": "/",
                    "steps": [uw.screen("Home")]}}
    assert uw.walk_errors(broken, USERS, ui_shots.DEVICES) == [
        "X: unknown user 'nobody'", "X: unknown device 'fridge'", "X: unknown memory 'some'",
        "X: the start is not a path", "X step 1: unknown kind 'jump'", "X step 2: tap without target",
        "X step 3: unknown user 'visitor'", "X step 4: unknown kind 'tap'", "Y: no action"]


def test_the_guard_refuses_only_the_starts_of_work():
    """FORBIDDEN: a new job, a job again and an OSM extract; not the estimate, the job list or a cancel."""
    def refused(method, path):
        return any(method == m and p.search(path) for m, p in uw.FORBIDDEN)
    assert refused("POST", "https://localhost:1/api/jobs") and refused("POST", "https://localhost:1/api/jobs/")
    assert refused("POST", "https://localhost:1/api/jobs/20261116-1-abc/again")
    assert refused("POST", "https://localhost:1/api/osm")
    assert not refused("GET", "https://localhost:1/api/jobs")
    assert not refused("POST", "https://localhost:1/api/estimate")
    assert not refused("POST", "https://localhost:1/api/jobs/20261116-1-abc/cancel")


@browser_test
def test_the_guard_is_installed_in_every_context(page):
    """_context: a page of the site that posts a new job gets it refused (and listed); an estimate goes on."""
    site = "https://walks.test"
    browsers = {"chromium": page.context.browser}  # the Edge of the module's fixture, not a browser of its own
    context, refused = uw._context(None, browsers, "desktop", "returning", None, site)
    try:
        context.route(site + "/", lambda route: route.fulfill(status=200, content_type="text/html",
                                                              body="<!doctype html><title>t</title>"))
        p = context.new_page()
        p.goto(site + "/")
        said = p.evaluate("""async () => {
            const tried = async (path) => { try { await fetch(path, {method: 'POST', body: '{}'}); return 'answered'; }
                                            catch (e) { return 'failed'; } };
            return [await tried('/api/jobs'), await tried('/api/jobs/x/again'), await tried('/api/estimate')]; }""")
        assert said[:2] == ["failed", "failed"]
        assert refused == [f"POST {site}/api/jobs", f"POST {site}/api/jobs/x/again"]  # not the estimate
    finally:
        context.close()


def _act(n, kind, controls, words, seconds=0.1, settled=True, **more):
    return {"n": n, "kind": kind, "measured": {"controls": controls, "words": words, "settled": settled,
                                              "scope": "viewport", "list": ["c"] * controls},
            "seconds": seconds, **more}


def test_totals_of_a_record():
    """totals: taps (with the one not made), keystrokes (characters and keys), changes of hand, decision points,
    words before the first action and over the screens, waits over 300 ms and those without feedback."""
    record = {"dead_end": None, "steps": [
        {"n": 1, "kind": "screen", "name": "first", "measured": {"controls": 7, "words": 40}},
        _act(2, "tap", 7, 40),
        _act(3, "type", 3, 12, text="100", settled=False),
        _act(4, "key", 3, 12, seconds=0.5, key="Enter", feedback="none"),
        {"n": 5, "kind": "note", "text": "a note"},
        {"n": 6, "kind": "screen", "name": "second", "measured": {"controls": 2, "words": 9}},
        _act(7, "swipe", 2, 9, seconds=1.2, feedback="busy"),
        {"n": 8, "kind": "unmade", "measured": {"controls": 7, "words": 20, "scope": "viewport", "list": ["c"] * 7},
         "made": False},
        {"n": 9, "kind": "end", "measured": {"controls": 5, "words": 20}}]}
    t = uw.totals(record)
    assert (t["screens"], t["pointer"], t["keystrokes"], t["switches"]) == (2, 3, 4, 2)
    assert (t["decisions"], t["max_controls"], t["words_first"], t["words_screens"]) == (2, 7, 40, 49)
    assert t["decision_surfaces"] == 1  # steps 2 and 8: the same surface, counted once
    assert (t["unsettled"], t["error"]) == (1, False)
    assert t["waits"] == [{"step": 4, "seconds": 0.5, "feedback": "none"}, {"step": 7, "seconds": 1.2, "feedback": "busy"}]
    assert (t["no_feedback"], t["not_made"], t["dead_end"]) == (1, 1, None)
    assert uw.totals(record, desktop=False)["switches"] is None  # phones: no keyboard to leave
    again = {"dead_end": None, "steps": [dict(s, measured=dict(s["measured"], words=s["measured"]["words"] + 1,
                                                               settled=True))
                                         if s.get("measured") and s["n"] == 3 else s for s in record["steps"]]}
    a = [{"id": "Z", "totals": t, "steps": record["steps"]}]
    b = [{"id": "Z", "totals": uw.totals(again), "steps": again["steps"]}]
    assert uw.compare(a, a) == []
    assert uw.compare(a, b) == ["Z unsettled: 1 / 0", "Z step 3 words: 12 / 13", "Z step 3 settled: False / True"]
    md = uw.markdown([{"id": "Z", "title": "t", "user": "admin", "device": "desktop", "memory": "new",
                       "totals": t, "dead_end": None, "steps": record["steps"]}])
    assert md.count("\n## Z t") == 1 and md.startswith(uw.COUNTED)
    assert "3. type '100' into [3 controls, 12 words; not settled]" in md
    broken = {"dead_end": {"step": 2, "why": "error: Error: gone", "error": True}, "steps": record["steps"][:2]}
    tb = uw.totals(broken)
    assert (tb["error"], tb["dead_end"]) == (True, 2)
    row = [line for line in uw.markdown([{"id": "E", "title": "e", "user": "admin", "device": "desktop",
                                          "memory": "new", "totals": tb, **broken}]).splitlines()
           if line.startswith("| E e")][0]
    assert row.endswith("| 2 (error) |")


# A page of known controls and words: visible and enabled 5 (two buttons, a link, a text field, a styled radio's
# label), 1 disabled and 1 inside an inert box; hidden 6 (display:none, visibility:hidden, below the viewport, clipped
# by its box, covered by a panel, opacity 0 without a label). Words: those of the visible texts only.
PAGE = """<!doctype html><html><body style="margin:0;font:16px sans-serif">
<p>Alpha beta · gamma 12 ⋯</p>
<button id="one">Open it</button> <button>Two</button> <a href="#x">A link</a>
<input value="two words"> <button disabled>Off</button>
<label><input type="radio" name="r" style="opacity:0;position:absolute"> Pick me</label>
<div inert><button>Inert</button></div>
<button style="display:none">Gone</button> <button style="visibility:hidden">Ghost</button>
<input type="checkbox" style="opacity:0">
<button style="position:absolute;top:2000px">Far away</button>
<div style="overflow:hidden;height:20px;width:200px"><div style="height:40px"></div><button>Clipped</button></div>
<div style="position:relative;height:40px"><button style="position:absolute;top:0">Covered</button>
  <div style="position:absolute;inset:0;background:#fff">Panel text</div></div>
</body></html>"""


@browser_test
def test_counting_on_a_known_page(page):
    """MEASURE: exact numbers of visible enabled controls, disabled ones, and words (a word holds a letter or a digit;
    hidden, clipped, covered and off-screen text is none)."""
    page.set_content(PAGE)
    m = uw.measure(page)
    assert m["scope"] == "viewport" and m["settled"]
    assert sorted(m["list"]) == sorted(["button: Open it", "button: Two", "a: A link", "input: two words",
                                        "radio label: Pick me", "(disabled) button: Off", "(disabled) button: Inert"])
    assert (m["controls"], m["disabled"]) == (5, 2)
    # Alpha beta gamma 12 / Open it / Two / A link / Off / Pick me / Inert / Panel text / the field's "two words"
    assert m["words"] == 4 + 2 + 1 + 2 + 1 + 2 + 1 + 2 + 2, m["text"]


@browser_test
def test_pointer_events_none_neither_hides_its_words_nor_shows_what_it_covers(page):
    """A unit label with pointer-events: none beside a field counts its word; an opaque such panel over a button hides
    the button and counts its own words; a transparent such wrapper over a button hides nothing; the page's styles are
    as before afterwards."""
    page.set_content("""<!doctype html><body style="margin:0;font:16px sans-serif">
        <div style="position:relative;width:200px"><input aria-label="Height" style="width:150px">
          <span id="unit" style="position:absolute;right:8px;top:2px;pointer-events:none">m</span></div>
        <div style="position:relative;height:40px"><button style="position:absolute;top:0">Hidden</button>
          <div id="cover" style="position:absolute;inset:0;background:#fff;pointer-events:none">Cover</div></div>
        <div style="position:relative;height:40px"><button style="position:absolute;top:0">Seen</button>
          <div style="position:absolute;inset:0;pointer-events:none"></div></div>
        <div role="separator" tabindex="0" aria-label="Width of the list" style="height:8px;background:#ccc"></div>
        <svg width="100" height="40"><rect class="fal-hover" role="slider" tabindex="0" aria-label="Point"
          width="100" height="40" fill="transparent"/></svg></body>""")
    m = uw.measure(page)
    assert sorted(m["list"]) == sorted(["input: Height", "button: Seen"]), m["list"]
    assert sorted(m["text"].split()) == sorted(["m", "Cover", "Seen"]), m["text"]
    assert page.evaluate("document.getElementById('cover').style.pointerEvents") == "none"
    assert page.evaluate("document.getElementById('unit').getAttribute('style').includes('auto')") is False


@browser_test
def test_a_reading_that_never_settles_is_marked(page):
    """Text that keeps changing: the reading comes back after the settling time, marked not settled."""
    page.set_content("""<p id="t">0</p><script>let i = 0;
        setInterval(() => { document.getElementById('t').textContent = 'tick ' + i++; }, 30)</script>""")
    assert uw.measure(page, settle_ms=600)["settled"] is False
    page.set_content("<p>Still</p>")
    assert uw.measure(page, settle_ms=600)["settled"] is True


@browser_test
def test_counting_inside_a_modal_dialog(page):
    """With a modal dialog open only what is in it counts; the page behind is none."""
    page.set_content(PAGE + """<dialog id="d"><p>Hello there, friend</p><button>Yes</button><button>No</button>
        <a href="#">Read more</a><div style="max-height:30px;overflow:auto"><div style="height:60px"></div>
        <p>Scrolled out of view</p></div></dialog>""")
    page.evaluate("document.getElementById('d').showModal()")
    m = uw.measure(page)
    assert m["scope"] == "dialog:modal"
    assert (m["controls"], m["disabled"], m["words"]) == (3, 0, 3 + 1 + 1 + 2), m
    assert m["words_in_scope"] == 7 + 4  # what the dialog gives to read, its scrolled-out part too
    page.evaluate("document.getElementById('d').close()")
    assert uw.measure(page)["words_in_scope"] is None  # no dialog, no such count


@browser_test
def test_counting_inside_a_popover_and_the_map(page):
    """An open popover (.r-pop) alone counts; a Leaflet map (tabindex=0, as Leaflet makes it) is one control listed as
    the map, its panes' controls and words none, its corner controls and attribution each."""
    page.set_content("""<button>Outside</button><p>Words outside</p>
        <div class="leaflet-container" tabindex="0" style="position:relative;width:300px;height:200px">
          <div class="leaflet-map-pane"><a href="#m" style="position:absolute;top:50px">Marker label</a>
            <span style="position:absolute;top:90px">Pane words</span></div>
          <div class="leaflet-control-container"><button style="position:absolute;top:0">Zoom in</button>
            <a href="#osm" style="position:absolute;bottom:0">OpenStreetMap</a></div></div>""")
    m = uw.measure(page)
    assert sorted(m["list"]) == sorted(["button: Outside", "map: the map", "button: Zoom in", "a: OpenStreetMap"])
    assert m["words"] == 1 + 2 + 2 + 1, m["text"]  # Outside / Words outside / Zoom in / OpenStreetMap
    page.evaluate("""document.body.insertAdjacentHTML('beforeend', '<div class="r-pop" role="dialog" tabindex="-1">' +
        '<b>Save to a folder</b><button>Favourites</button><button>New folder</button></div>')""")
    m = uw.measure(page)
    assert (m["scope"], m["controls"], m["words"]) == (".r-pop", 2, 4 + 1 + 2), m


@browser_test
def test_feedback_of_a_slow_step(page):
    """A step slower than 300 ms: "none" when nothing changed on the screen within 300 ms, "busy" with a busy mark,
    "text" when the visible text changed, each within 300 ms of the click reaching the page (the page's own timers
    decide, not the test's clock); a fast step has no entry, or "text" when the machine made it slow."""
    page.set_content("""<button id="quiet" onclick="setTimeout(() => document.body.insertAdjacentHTML('beforeend',
          '<p id=a>Done</p>'), 800)">Quiet</button>
        <button id="busy" onclick="this.setAttribute('aria-busy', 'true'); setTimeout(() =>
          document.body.insertAdjacentHTML('beforeend', '<p id=b>Done</p>'), 800)">Busy</button>
        <button id="told" onclick="document.getElementById('say').textContent = 'Working'; setTimeout(() =>
          document.body.insertAdjacentHTML('beforeend', '<p id=c>Done</p>'), 800)">Told</button>
        <button id="fast" onclick="document.body.insertAdjacentHTML('beforeend', '<p id=d>Done</p>')">Fast</button>
        <p id="say">Ready</p>""")
    walk = {"steps": [uw.tap(f"#{name}", f"!!document.getElementById('{p}')")
                      for name, p in (("quiet", "a"), ("busy", "b"), ("told", "c"), ("fast", "d"))]}
    r = uw.run_walk(page, walk, timeout=SHORT)
    assert r["dead_end"] is None
    assert [s.get("feedback") for s in r["steps"][:3]] == ["none", "busy", "text"]
    assert r["steps"][3].get("feedback") in (None, "text")
    assert r["totals"]["no_feedback"] == 1 and [w["step"] for w in r["totals"]["waits"]][:3] == [1, 2, 3]


@browser_test
def test_a_walk_and_its_dead_end(page, tmp_path):
    """run_walk: a click and its expected state are counted; a step whose element is missing ends the walk as a dead
    end with that step named, the steps after it neither made nor counted; an "unmade" tap is counted, never made."""
    page.set_content("""<button id="go" onclick="setTimeout(() => document.body.insertAdjacentHTML('beforeend',
        '<p id=done>Done now</p>'), 50)">Go</button><button id="start" onclick="document.title = 'started'">Start</button>
        <input id="f">""")
    walk = {"id": "T", "title": "test", "user": "admin", "device": "desktop", "memory": "new", "steps": [
        uw.screen("the page"),
        uw.tap("#go", "!!document.getElementById('done')"),
        uw.tap("#f"), uw.type_("#f", "abc"), uw.key("Enter"),
        uw.unmade("role=button[name='Start']"),
        uw.tap("#missing"),
        uw.tap("#go")]}
    r = uw.run_walk(page, walk, out=str(tmp_path), timeout=SHORT)
    assert r["dead_end"] == {"step": 7, "why": "no visible element #missing"}
    assert [s["n"] for s in r["steps"]] == [1, 2, 3, 4, 5, 6, 7]  # step 8 neither made nor recorded
    assert page.title() != "started" and page.input_value("#f") == "abc"
    t = r["totals"]
    assert (t["screens"], t["pointer"], t["keystrokes"], t["not_made"], t["dead_end"]) == (1, 3, 4, 1, 7)
    assert t["switches"] == 2  # click, click | type, Enter | the Start tap
    assert r["steps"][1]["measured"]["controls"] == 3 and r["steps"][1]["seconds"] is not None
    assert os.path.exists(os.path.join(tmp_path, "02-tap.png")) and os.path.exists(os.path.join(tmp_path, "07-dead.png"))


@browser_test
def test_a_start_that_stays_disabled_is_a_dead_end(page):
    """An "unmade" Start must be enabled: a disabled one ends the walk there."""
    page.set_content("<button disabled>Start search</button>")
    walk = {"steps": [uw.unmade("role=button[name='Start search']")]}
    r = uw.run_walk(page, walk, timeout=SHORT)
    assert r["dead_end"]["step"] == 1 and r["totals"]["not_made"] == 0


@browser_test
def test_an_error_inside_a_walk_ends_it_with_its_step(page, monkeypatch):
    """An exception under a measurement (a navigation, a page gone) ends the walk as an error at its step; the steps
    before it are kept."""
    page.set_content("<button id='a'>A</button><button id='b'>B</button>")
    calls, real = [], uw.measure

    def failing(p, settle_ms=uw.SETTLE_MS):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Execution context was destroyed")
        return real(p, settle_ms)
    monkeypatch.setattr(uw, "measure", failing)
    r = uw.run_walk(page, {"steps": [uw.tap("#a"), uw.tap("#b"), uw.tap("#a")]}, timeout=SHORT)
    assert r["dead_end"] == {"step": 2, "why": "error: RuntimeError: Execution context was destroyed", "error": True}
    assert [s["n"] for s in r["steps"]] == [1, 2] and r["steps"][0]["seconds"] is not None
    assert (r["totals"]["pointer"], r["totals"]["error"]) == (1, True)


@browser_test
def test_an_action_takes_the_walks_timeout(page):
    """A click on a button under a panel that takes the clicks: it fails after the walk's timeout (not Playwright's
    30 s), as a dead end of that step."""
    page.set_content("""<div style="position:relative;height:40px"><button id="under">Under</button>
        <div style="position:absolute;inset:0;opacity:0.01">over</div></div>""")
    r = uw.run_walk(page, {"steps": [uw.tap("#under")]}, timeout=SHORT)
    assert r["dead_end"]["step"] == 1 and f"Timeout {SHORT}ms exceeded" in r["dead_end"]["why"], r["dead_end"]


@browser_test
def test_a_share_link_is_masked(page, tmp_path):
    """A share link's token: masked in the words and the controls' names, and its field covered in the screenshot."""
    Image = pytest.importorskip("PIL.Image")
    link = "https://localhost:1/s/abcdefghijklmnopqrstuvwxyz012345/map.html"
    page.set_content(f"""<div class="r-pop" role="dialog" style="padding:20px"><p>Copy this link: {link}</p>
        <input id="link" style="width:500px;height:30px" value="{link}"></div>""")
    m = uw.measure(page)
    assert "abcdefghijklmnop" not in m["text"] + " ".join(m["list"])
    assert "/s/<token>" in m["text"] and any("/s/<token>" in c for c in m["list"])
    r = uw.run_walk(page, {"steps": [uw.screen("the link")]}, out=str(tmp_path), timeout=SHORT)
    box = page.locator("#link").bounding_box()
    pixel = Image.open(r["steps"][0]["shot"]).convert("RGB").getpixel((int(box["x"] + box["width"] / 2),
                                                                         int(box["y"] + box["height"] / 2)))
    assert pixel == (255, 0, 255)  # Playwright's mask


def test_main_refuses_a_data_folder_with_a_job_before_serving(tmp_path, monkeypatch):
    """A --data-dir holding a job: main() stops before serve() can start its worker."""
    pytest.importorskip("playwright")
    from jobs import Jobs
    (tmp_path / "data").mkdir()
    Jobs(str(tmp_path / "data")).add({"params": {}}, "a waiting search", None)

    def serve(*args, **kwargs):
        raise AssertionError("serve() started with a job waiting")
    monkeypatch.setattr(ui_shots, "serve", serve)
    monkeypatch.setattr(sys, "argv", ["ui_walks.py", "--out", str(tmp_path / "out"),
                                      "--data-dir", str(tmp_path / "data")])
    for name in ("ESRI_API_KEY", "DATAFORDELER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="has jobs before the walks"):
        uw.main()


def test_main_stops_the_site_and_cleans_up_when_a_step_after_serving_fails(tmp_path, monkeypatch):
    """first_line failing after serve(): the site is stopped and the temporary data folder removed."""
    pytest.importorskip("playwright")
    temp, stopped = tmp_path / "ui-walks-x", []
    monkeypatch.setattr(uw.tempfile, "mkdtemp", lambda prefix="": (temp.mkdir(), str(temp))[1])
    monkeypatch.setattr(ui_shots, "serve", lambda data: ("https://localhost:1", {}, "run", "share",
                                                        lambda: stopped.append(1)))

    def first_line(*args):
        raise ValueError("no lines")
    monkeypatch.setattr(ui_shots, "first_line", first_line)
    monkeypatch.setattr(sys, "argv", ["ui_walks.py", "--out", str(tmp_path / "out")])
    for name in ("ESRI_API_KEY", "DATAFORDELER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="no lines"):
        uw.main()
    assert stopped == [1] and not temp.exists()
