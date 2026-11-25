"""Renaming a run in the result view, and the run's name everywhere after a rename (line volume's round 7, step 2g's
page half; the accepted mock-up's points 5, 7 to 12 and 25): a desktop's header has an icon button after the run's
name (the kit's pencil, "Rename the run") for the run's owner on the public site, which opens the rename form in a box
under the title (only the form: the field, Save and Cancel), with the waiting state and the server's refusals; no
button for another user, the administrator, a run's map.html, a share link, a phone or the local app. The view's head
shows the run's name from the list of runs (run.json's), not the store's head's; after a rename, on Home or in the
view, the head, Home's card, Compare's row, the phone's pill and a report's "about" show the new name without a
reload, and a run's map.html (its own address, a share link's) takes the new name from its title.

Playwright's Edge over the public app on a thread (uvicorn) with the real route POST /api/runs/<id>, offline; the
fixture and helpers are tests/test_rename_home_page.py's. Run from PowerShell (.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_public import RUN_A, RUN_B, account_settings  # noqa: E402,F401
from test_rename_home_page import (FORM, NAME_A, NAME_B, REFUSED, SHARE_TOKEN, WORDS, Browser, card,  # noqa: E402,F401
                                   kit_icon, open_home, open_rename, rename_site, the_held)
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, PHONE, view_clip  # noqa: E402,F401
from test_shell_c_view_map import WAIT as PAGE_WAIT  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
# ms: the deadline of every wait for the page (lowered through the variable only to see the tests fail sooner on a
# checkout without the change)
WAIT = int(os.environ.get("RENAME_VIEW_WAIT_MS", PAGE_WAIT))
NEW = "North face"  # a new name with nothing of the old ones in it
BUTTON = ".c-run-title .c-rename-btn"  # the view's Rename button (also where there must be none)
BOX = ".c-run-title .r-pop"  # its box
FIELD = BOX + " .c-rename input"
TITLE = ".c-run-title .c-run-name"  # the name in a desktop's header
PILL = ".c-pill .c-pill-name"  # the name in a phone's pill
TEXT = "(sel) => { const e = document.querySelector(sel); return e ? e.textContent : null; }"
GONE = "(sel) => document.querySelector(sel) === null"
FOCUSED = "(sel) => document.activeElement !== null && document.activeElement === document.querySelector(sel)"
FRAMES = "() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(ok, 0))))"
COUNT = "(sel) => document.querySelectorAll(sel).length"
BOX_FACTS = """(sel) => { const p = document.querySelector(sel), t = document.querySelector('.c-run-title');
  const b = p.getBoundingClientRect(), tb = t.getBoundingClientRect();
  return {role: p.getAttribute('role'), label: p.getAttribute('aria-label'), kids: [...p.children].map((c) => c.tagName + '.' + c.className),
          inputs: p.querySelectorAll('input').length, buttons: p.querySelectorAll('button').length,
          heads: p.querySelectorAll('.u-h4, b, h1, h2, h3').length, labels: p.querySelectorAll('label').length,
          left: b.left, titleLeft: tb.left, top: b.top, titleBottom: tb.bottom}; }"""
LINE_UNDER = """(sel) => { const f = document.querySelector(sel + ' .c-rename'), row = f.querySelector('.u-row'), line = f.querySelector('[role=alert]');
  return {after: row.nextElementSibling === line, under: line.getBoundingClientRect().top >= row.getBoundingClientRect().bottom}; }"""


def renamed(response, run: str = RUN_A) -> bool:
    """The answer of the run's rename (POST /api/runs/<id>)."""
    return response.request.method == "POST" and response.url.endswith(f"/api/runs/{run}")


def page_of(browser, device: dict = DESKTOP, who: str | None = "a", script: str = ""):
    """The model's page (signed in as `who`, the view's flag set) with this file's deadline."""
    page = browser.page(device, who, script)
    page.set_default_timeout(WAIT)
    return page


def settled(page, js: str, arg=None):
    """`js`'s value once it is true, or as it stands when WAIT ran out (the assertion after it then shows it): for what
    the page does a moment after an event (an effect after the paint, a focus put back in a timer, a list asked for
    again)."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_function(js, arg=arg)
    except PlaywrightTimeout:
        pass
    return page.evaluate(js, arg)


def view_of(page, run: str):
    """The view of `run` drawn in the page (its header's name there)."""
    page.wait_for_function("(run) => !!window.FINDALINE_VIEW && window.FINDALINE_VIEW.view.model.runId === run", arg=run)
    page.wait_for_selector(PILL if page.viewport_size["width"] < 768 else TITLE)


def open_view(page, site: str, run: str = RUN_A):
    """The app's result view of `run`."""
    page.goto(f"{site}/?ui=c#run={run}")
    view_of(page, run)


def open_box(page):
    """The view's Rename pressed (it stands there once the list of runs answered): the box's field, once the form's
    effects ran (the focus in the field)."""
    page.click(BUTTON)
    page.wait_for_selector(FIELD)
    settled(page, FOCUSED, FIELD)
    return page.locator(FIELD)


def rename_in_view(page, name: str):
    """`name` typed in the view's box and saved with Enter: the answer, once the box closed."""
    field = open_box(page)
    field.fill(name)
    with page.expect_response(renamed) as answer:
        page.keyboard.press("Enter")
    page.wait_for_selector(BOX, state="detached")
    return answer.value


def rename_on_home(page, name: str, run: str = RUN_A):
    """`name` typed in the card's panel on Home and saved with Enter: the answer, once the panel closed."""
    field = open_rename(page, run)
    field.fill(name)
    with page.expect_response(lambda r: renamed(r, run)) as answer:
        page.keyboard.press("Enter")
    page.wait_for_selector(f"{card(run)} .c-card-panel", state="detached")
    return answer.value


def press_map(page):
    """A press on the middle of the map (outside the box)."""
    box = page.locator(".c-col-map .c-leaflet").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def head_name(data, run: str) -> str:
    """The run's name in its store's head (lines.arrow's metadata), which a rename leaves as it was."""
    import pyarrow as pa
    import linestore
    with pa.OSFile(str(data / "runs" / run / linestore.LINES_FILE), "rb") as f:
        meta = pa.ipc.open_file(f).schema.metadata[linestore.META_KEY]
    return json.loads(meta.decode("utf-8"))["head"]["run"]["name"]


def test_the_rename_button_and_its_box(rename_site):
    """The owner's desktop view: right after the run's name in the header stands an icon button named and titled
    "Rename the run", drawn with the kit's "edit" icon, at least 24 px each way, once the list of runs answered. A
    press opens a box under the title (a dialog named "Rename the run", its left edge the title's) that holds only the
    form: the field named "The run's name" with the whole name selected and the focus in it, Save and Cancel, no
    heading and no label. Save is off while the field is unchanged (also with spaces added) or empty. Esc closes the
    box with the focus back on the button; a press outside it (on the map) closes it, and so does Cancel."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_view(page, site)
        page.wait_for_selector(BUTTON)
        button = page.evaluate("""(sel) => { const b = document.querySelector(sel), r = b.getBoundingClientRect();
            const name = document.querySelector('.c-run-title .c-run-nameline .c-run-name');
            return {after: !!name.nextElementSibling && name.nextElementSibling.firstElementChild === b,
                    beside: r.left >= name.getBoundingClientRect().right, header: !!b.closest('.c-result-top'),
                    label: b.getAttribute('aria-label'), title: b.getAttribute('title'), svg: b.querySelector('svg').innerHTML,
                    size: [r.width, r.height]}; }""", BUTTON)
        named = page.get_by_role("button", name="Rename the run", exact=True)
        by_role = [named.count(), named.first.evaluate("(b, sel) => b === document.querySelector(sel)", BUTTON)]
        field = open_box(page)
        box = page.evaluate(BOX_FACTS, BOX)
        opened = page.evaluate(FORM, ".c-run-title")
        field.fill("  A's   run ")
        spaced = page.evaluate(FORM, ".c-run-title")
        field.fill("")
        empty = page.evaluate(FORM, ".c-run-title")
        field.fill("   ")
        blank = page.evaluate(FORM, ".c-run-title")
        field.fill("Another name")
        typed = page.evaluate(FORM, ".c-run-title")
        page.keyboard.press("Escape")
        escaped = [settled(page, GONE, BOX), settled(page, FOCUSED, BUTTON)]
        open_box(page)
        press_map(page)
        outside = settled(page, GONE, BOX)
        open_box(page)
        page.click(f"{BOX} button:has-text('Cancel')")
        cancelled = settled(page, GONE, BOX)
        name = page.evaluate(TEXT, TITLE)
    assert WORDS["ui.rename.title"] == "Rename the run" and WORDS["ui.rename.name"] == "The run's name"
    assert button["after"] and button["beside"] and button["header"], button
    assert button["label"] == button["title"] == WORDS["ui.rename.title"] and by_role == [1, True], (button, by_role)
    assert f'd="{kit_icon("edit")}"' in button["svg"], button["svg"]
    assert min(button["size"]) >= 24, button["size"]
    assert box["role"] == "dialog" and box["label"] == WORDS["ui.rename.title"], box
    assert box["kids"] == ["FORM.c-rename"] and box["inputs"] == 1 and box["buttons"] == 2, box
    assert box["heads"] == 0 and box["labels"] == 0, box
    assert abs(box["left"] - box["titleLeft"]) <= 1 and box["top"] >= box["titleBottom"], box
    assert opened["value"] == NAME_A and opened["focus"] and opened["selected"] == [0, len(NAME_A)], opened
    assert opened["label"] == WORDS["ui.rename.name"] and opened["labels"] == 0, opened
    assert opened["buttons"] == ["Save", "Cancel"] and opened["off"] == [True, False] and not opened["line"], opened
    assert [spaced["off"], empty["off"], blank["off"], typed["off"]] == [[True, False]] * 3 + [[False, False]], (spaced, empty, blank, typed)
    assert escaped == [True, True], escaped
    assert outside and cancelled, (outside, cancelled)
    assert name == NAME_A, name


def test_enter_saves_in_the_view(rename_site):
    """Enter in the view's box saves: the title shows the name as the server stored it (runs of spaces joined, the ends
    trimmed) at once, in the same page (no reload); the box is closed, the focus is on the Rename button, the address
    is the one before, and run.json holds the name."""
    site, data = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_view(page, site)
        page.evaluate("() => { window.KEPT = 'this page'; }")
        before = page.evaluate("() => location.hash")
        field = open_box(page)
        field.fill("  The north   side ")
        with page.expect_response(renamed) as answer:
            page.keyboard.press("Enter")
        closed = settled(page, GONE, BOX)
        shown = page.evaluate(TEXT, TITLE)
        focus = settled(page, FOCUSED, BUTTON)
        after = page.evaluate("() => [location.hash, window.KEPT]")
        sent, status = answer.value.request.post_data_json, answer.value.status
    assert status == 200 and sent == {"name": "  The north   side "}, (status, sent)  # as typed: the server's rule decides
    assert closed and shown == "The north side", (closed, shown)
    assert focus, "the focus is not on the Rename button"
    assert after == [before, "this page"], (before, after)
    with open(data / "runs" / RUN_A / "run.json", encoding="utf-8") as f:
        assert json.load(f)["name"] == "The north side"


def test_the_view_waits_and_shows_refusals(rename_site):
    """While the request waits the field cannot be changed, both buttons are off and Save is busy with the ring; Esc
    does not close the box and neither does a press outside it. A 409 shows "The run is in use. Try again in a
    moment." under the buttons, the typed name kept and Save on again; a name with a tab, refused by the server (400),
    shows the catalogue's words of error.run_name; the box stays open and the title keeps the name."""
    site, _ = rename_site
    held = []
    with Browser(site) as browser:
        page = page_of(browser)
        open_view(page, site)
        field = open_box(page)
        page.route(f"**/api/runs/{RUN_A}", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
        field.fill("Waiting name")
        page.keyboard.press("Enter")
        page.wait_for_function("(sel) => document.querySelector(sel).readOnly", arg=FIELD)
        waiting = page.evaluate(FORM, ".c-run-title")
        page.keyboard.press("Escape")
        page.evaluate(FRAMES)
        after_esc = page.evaluate(COUNT, BOX)
        press_map(page)
        page.evaluate(FRAMES)
        after_press = page.evaluate(COUNT, BOX)
        the_held(page, held).fulfill(status=409, content_type="application/json",
                                     body=json.dumps({"detail": "the run is in use: try again in a moment"}))
        page.wait_for_selector(f"{BOX} .c-rename [role=alert]")
        in_use = page.evaluate(FORM, ".c-run-title")
        in_use_place = page.evaluate(LINE_UNDER, ".c-run-title")
        page.unroute(f"**/api/runs/{RUN_A}")
        field.fill("Tab\there")
        page.wait_for_selector(f"{BOX} .c-rename [role=alert]", state="detached")
        with page.expect_response(renamed) as answer:
            page.keyboard.press("Enter")
        page.wait_for_selector(f"{BOX} .c-rename [role=alert]")
        refused = page.evaluate(FORM, ".c-run-title")
        refused_place = page.evaluate(LINE_UNDER, ".c-run-title")
        still = [page.evaluate(COUNT, BOX), page.evaluate(TEXT, TITLE)]
        status = answer.value.status
    assert waiting["readonly"] and waiting["off"] == [True, True] and waiting["busy"] == "true" and waiting["ring"], waiting
    assert waiting["value"] == "Waiting name", waiting
    assert after_esc == 1 and after_press == 1, (after_esc, after_press)
    assert in_use["line"] == WORDS["ui.rename.in_use"] == "The run is in use. Try again in a moment.", in_use
    assert in_use["value"] == "Waiting name" and in_use["off"] == [False, False] and not in_use["readonly"], in_use
    assert in_use_place == {"after": True, "under": True}, in_use_place
    assert status == 400, status
    assert refused["line"] == REFUSED == "Give the run a name of 1 to 100 characters, with no tab or invisible character.", refused
    assert refused["value"] == "Tab\there" and refused["off"] == [False, False], refused
    assert refused_place == {"after": True, "under": True}, refused_place
    assert still == [1, NAME_A], still


def test_who_gets_the_rename_button(rename_site):
    """Only the run's owner on a desktop's app page has Rename in the view's header. None, once the view is drawn and
    the list of runs answered: for another user on the owner's demo run, for the administrator on it, for a visitor on
    the run's own map.html, on the share link's page (a visitor, the owner too), and on a phone, where the owner's pill
    keeps the run's name and has no Rename."""
    site, _ = rename_site
    seen = {}
    with Browser(site) as browser:
        owner = page_of(browser)
        open_view(owner, site)
        owner.wait_for_selector(BUTTON)  # the control: the owner's desktop has it
        for name, who, path in (("another user", "b", f"/?ui=c#run={RUN_A}"), ("administrator", "admin", f"/?ui=c#run={RUN_A}"),
                                ("visitor's map.html", None, f"/runs/{RUN_A}/map.html"),
                                ("share link, a visitor", None, f"/s/{SHARE_TOKEN}/map.html"),
                                ("share link, the owner", "a", f"/s/{SHARE_TOKEN}/map.html")):
            page = page_of(browser, who=who)
            page.goto(site + path)
            view_of(page, RUN_A)
            page.wait_for_load_state("networkidle")  # the list of runs answered (the owner check)
            seen[name] = [page.evaluate(COUNT, ".c-rename-btn"), page.evaluate(COUNT, TITLE)]
        phone = page_of(browser, PHONE)
        open_view(phone, site)
        phone.wait_for_selector(".c-pill [aria-label='Share']")  # the list answered: the owner's Share is in the pill
        phone.wait_for_load_state("networkidle")
        pill = [phone.evaluate(COUNT, ".c-rename-btn"), phone.evaluate(TEXT, PILL)]
    assert all(got == [0, 1] for got in seen.values()), seen
    assert pill == [0, NAME_A], pill


def test_the_local_app_has_no_rename_in_the_view(tmp_path, view_clip):
    """The local app's result view (a desktop) has no Rename button: renaming is the public site's; the head shows the
    run's listed name."""
    from test_web import _server
    data = tmp_path / "local"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, NAME_A)
    with _server(data) as port:
        site = f"http://127.0.0.1:{port}"
        with Browser(site) as browser:
            page = page_of(browser, who=None)
            open_view(page, site)
            page.wait_for_load_state("networkidle")
            got = [page.evaluate(COUNT, ".c-rename-btn"), page.evaluate(TEXT, TITLE)]
    assert got == [0, NAME_A], got


def test_the_view_shows_the_listed_name(rename_site):
    """Before any rename the view's head shows the name the list of runs gives (run.json's), not the one of the
    store's head (the name of the saving): a desktop's title and a phone's pill."""
    site, data = rename_site
    head = head_name(data, RUN_A)
    with Browser(site) as browser:
        desktop = page_of(browser)
        open_view(desktop, site)
        phone = page_of(browser, PHONE)
        open_view(phone, site)
        shown = [desktop.evaluate(TEXT, TITLE), phone.evaluate(TEXT, PILL)]
    assert head != NAME_A, head  # (else the test would not tell the two apart)
    assert shown == [NAME_A, NAME_A], f"shown {shown}; run.json's {NAME_A!r}, the store's head's {head!r}"


def test_a_rename_on_home_reaches_the_view(rename_site):
    """A run renamed on Home and then opened from its card in the same page (no reload): the view's title shows the
    new name; the browser's Back to Home: the card still shows it."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        page.evaluate("() => { window.KEPT = 'this page'; }")
        saved = rename_on_home(page, NEW).json()
        page.click(f"{card(RUN_A)} a.c-card-open")
        view_of(page, RUN_A)
        title = page.evaluate(TEXT, TITLE)
        page.evaluate("() => history.back()")
        page.wait_for_selector(card(RUN_A))
        home = settled(page, "([sel, name]) => document.querySelector(sel + ' .c-card-name').textContent === name", [card(RUN_A), NEW])
        named = page.evaluate(TEXT, f"{card(RUN_A)} .c-card-name")
        kept = page.evaluate("() => [window.KEPT, location.hash]")
    assert saved == {"ok": True, "name": NEW}, saved
    assert title == NEW, title
    assert home and named == NEW, named
    assert kept == ["this page", ""], kept


def test_a_rename_in_the_view_reaches_home_and_compare(rename_site):
    """A run renamed in the view, then the header's "Home" in the same page: the run's card shows the new name (Home
    lists the runs again); the other run opened from its card: Compare's row of the renamed run shows the new name."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_view(page, site)
        page.evaluate("() => { window.KEPT = 'this page'; }")
        rename_in_view(page, NEW)
        back = page.evaluate(TEXT, ".c-result-top .c-back")
        page.click(".c-result-top .c-back")
        page.wait_for_selector(card(RUN_A))
        home = settled(page, "([sel, name]) => document.querySelector(sel + ' .c-card-name').textContent === name", [card(RUN_A), NEW])
        named = page.evaluate(TEXT, f"{card(RUN_A)} .c-card-name")
        page.click(f"{card(RUN_B)} a.c-card-open")
        view_of(page, RUN_B)
        page.click(".c-result-top button:has-text('Compare')")
        page.wait_for_selector(".r-pop .r-other")
        rows = page.evaluate("() => [...document.querySelectorAll('.r-pop .r-other .u-grow')].map((r) => r.firstChild.textContent)")
        kept = page.evaluate("() => window.KEPT")
    assert back.strip() == WORDS["ui.app.home"] == "Home", back
    assert home and named == NEW, named
    assert rows == [NEW], rows
    assert kept == "this page", kept


def test_a_report_after_a_rename_is_about_the_new_name(rename_site):
    """After a rename in the view, "Report this line" of a selected spot opens the report's dialog with what it is
    about: a line of the run under its new name."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser)
        open_view(page, site)
        rename_in_view(page, NEW)
        page.evaluate("() => { window.ABOUT = []; addEventListener('findaline-report', (e) => window.ABOUT.push(e.detail.about)); "
                      "const {view} = window.FINDALINE_VIEW; view.select(view.order[0]); }")
        page.wait_for_selector(".r-report")
        page.click(".r-report")
        page.wait_for_selector("dialog.n-report[open] .n-attached")
        attached = page.evaluate(TEXT, "dialog.n-report .n-attached")
        about = page.evaluate("() => window.ABOUT")
    words = WORDS["ui.report.sent_about"].replace("{{about}}", WORDS["ui.spot.report_about"].replace("{{run}}", NEW))
    assert words == "what it is about: a line of North face", words
    assert about == ["a line of North face"], about
    assert words in attached and NAME_A not in attached, attached


def test_a_phone_after_a_rename_on_home(rename_site):
    """A phone: a run renamed on Home and then opened from its card in the same page: the view's pill shows the new
    name."""
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser, PHONE)
        open_home(page, site)
        page.evaluate("() => { window.KEPT = 'this page'; }")
        rename_on_home(page, NEW)
        page.click(f"{card(RUN_A)} a.c-card-open")
        view_of(page, RUN_A)
        pill = page.evaluate(TEXT, PILL)
        kept = page.evaluate("() => window.KEPT")
    assert pill == NEW and kept == "this page", (pill, kept)


def test_a_runs_map_takes_the_name_of_its_title(rename_site):
    """After a rename the run's map.html, loaded anew, shows the new name, which its title carries (the store's head
    keeps the old one): the share link's page for a visitor (it has no list of runs) and the run's own address for the
    owner; the page's title starts with it on both."""
    site, data = rename_site
    old = head_name(data, RUN_A)
    with Browser(site) as browser:
        page = page_of(browser)
        open_home(page, site)
        saved = rename_on_home(page, NEW).json()
        shown = {}
        for name, who, path in (("share link, a visitor", None, f"/s/{SHARE_TOKEN}/map.html"), ("own address, the owner", "a", f"/runs/{RUN_A}/map.html")):
            other = page_of(browser, who=who)
            other.goto(site + path)
            view_of(other, RUN_A)
            shown[name] = [other.evaluate(TEXT, TITLE), other.evaluate("() => document.title")]
    assert saved == {"ok": True, "name": NEW}, saved
    assert head_name(data, RUN_A) == old != NEW, old
    for name, (title, page_title) in shown.items():
        assert title == NEW and page_title.startswith(NEW), (name, title, page_title)


def test_edit_and_run_again_has_the_circular_arrow_in_the_header(rename_site):
    """The desktop header's "Edit & run again" (the owner's run with its search) is drawn with the kit's circular
    arrow ("refresh"), as in the phone's pill and the card's menu: the pencil is the Rename button's beside the name."""
    from test_rename_home_page import jobs_stub
    site, _ = rename_site
    with Browser(site) as browser:
        page = page_of(browser, script=jobs_stub(RUN_A))
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        page.wait_for_selector(".c-result-top a[href*='edit']")
        page.wait_for_selector(BUTTON)
        edit = page.evaluate("() => { const a = document.querySelector(\".c-result-top a[href*='edit']\"); "
                             "return [a.textContent.trim(), a.querySelector('svg').innerHTML]; }")
        pencil = page.evaluate("(sel) => document.querySelector(sel + ' svg').innerHTML", BUTTON)
    assert edit[0] == "Edit & run again" and f'd="{kit_icon("refresh")}"' in edit[1], edit
    assert f'd="{kit_icon("edit")}"' not in edit[1] and f'd="{kit_icon("edit")}"' in pencil, (edit, pencil)


# A desktop-wide window with a touch screen (a tablet on its side, a touch laptop): the view's desktop frame with a
# coarse pointer, whose icon buttons are 44 px
TOUCH_DESKTOP = {"viewport": {"width": 1280, "height": 800}, "has_touch": True}


@pytest.mark.parametrize("pointer", ["mouse", "touch"])
def test_the_header_keeps_its_height_when_the_rename_button_comes(rename_site, pointer):
    """The Rename button is drawn only once the list of runs has answered. Before it (the answer held) and after it the
    owner's desktop header is as high and the list under it starts as low: nothing under the header moves when the
    button comes. A visitor's header on the run's map.html, which never has the button, has that height too. With a
    mouse the button is 32 px, in the name's line and centred on it; on a desktop-wide touch screen (a coarse pointer)
    it is 44 px, beside the name and the date and centred on the two lines, clear of both. Either way it stands inside
    the header, the name and the date do not move when it comes, and with the keyboard's focus its ring is drawn inside
    it (the kit's inner ring): none outside, where it would touch the name and cross the date's line."""
    site, _ = rename_site
    device = DESKTOP if pointer == "mouse" else TOUCH_DESKTOP
    box = """() => { const r = (sel) => { const e = document.querySelector(sel); return e && e.getBoundingClientRect(); };
      const top = r('.c-result-top'), cols = r('.c-cols'), b = r('.c-run-title .c-rename-btn'), n = r('.c-run-title .c-run-name'),
            d = r('.c-run-title > .u-small'), mid = (x) => (x.top + x.bottom) / 2;
      return {coarse: matchMedia('(pointer: coarse)').matches, header: top.height, list: cols.top, name: [n.left, n.top], date: [d.left, d.top],
              button: b && [b.width, b.height], inside: b && b.top >= top.top && b.bottom <= top.bottom,
              on_name: b && Math.abs(mid(b) - mid(n)) <= 1, on_lines: b && Math.abs(mid(b) - (n.top + d.bottom) / 2) <= 1,
              after_name: b && b.left - n.right, after_date: b && b.left - d.right}; }"""
    held, answered = [], []

    def lists(route):  # the page's requests for the user's runs: held until `answered` says to let them through
        if route.request.method == "GET" and not answered:
            held.append(route)
        else:
            route.continue_()
    with Browser(site) as browser:
        page = page_of(browser, device)
        page.goto("about:blank")
        page.route("**/api/runs", lists)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        view_of(page, RUN_A)
        assert held, "the page asked for no list of runs"  # (its answers stay held: the owner is not known yet)
        before = page.evaluate(box)
        answered.append(True)
        for route in held:
            route.continue_()
        page.wait_for_selector(BUTTON)
        after = page.evaluate(box)
        page.focus(BUTTON)
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")  # the keyboard's way onto the button: its ring is drawn
        ring = page.evaluate("(sel) => { const b = document.querySelector(sel), s = getComputedStyle(b); "
                             "return {on: document.activeElement === b && b.matches(':focus-visible'), shadow: s.boxShadow, "
                             "token: getComputedStyle(b.closest('.ui')).getPropertyValue('--focus-in').trim()}; }", BUTTON)
        visitor = page_of(browser, device, who=None)
        visitor.goto(f"{site}/runs/{RUN_A}/map.html")
        view_of(visitor, RUN_A)
        visitor.wait_for_load_state("networkidle")
        other = visitor.evaluate(box)
    assert before["coarse"] == after["coarse"] == other["coarse"] == (pointer == "touch"), (before, after, other)
    assert before["button"] is None and other["button"] is None, (before, other)
    assert before["header"] == after["header"] == other["header"], (before, after, other)
    assert before["list"] == after["list"] == other["list"], (before, after, other)
    assert before["name"] == after["name"] and before["date"] == after["date"], (before, after)  # the title's words stay put
    assert after["inside"], after
    if pointer == "mouse":
        assert after["button"] == [32, 32] and after["on_name"] and after["after_name"] >= 0, after
    else:  # 44 px, beside both lines: clear of the name and of the date
        assert after["button"] == [44, 44] and after["on_lines"], after
        assert after["after_name"] >= 0 and after["after_date"] >= 0, after
    assert ring["on"] and "inset" in ring["shadow"] and ring["shadow"].count("rgb") == 1, ring  # one ring, inside
    assert ring["token"].startswith("inset"), ring
