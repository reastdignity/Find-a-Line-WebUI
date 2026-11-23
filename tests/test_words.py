"""The interface's words against docs/DESIGN.md's R9 and R10 (step 3d, group G5: the user's answers of 2026-11-21 on
the wording review, docs/DESIGN.md choices 92 to 94).

- R10: no catalogue text over its kind's limit (a help text 40 words, an intro paragraph 30, a hint 25, an error 30,
  words split on spaces), by its key's kind (tools/ui_metrics.py `text_group`) and, for the texts whose key does not
  say their kind, by their role (BY_ROLE); today's result page keeps its intro (LEFT).
- R9: no character stands for a word (×, →, ≈, ≤, ≥, a "+" for "and", ...) in the catalogues, but what R9 allows or the
  user kept (R9_KEPT); none of ≤, ≥, × in the code that wrote them before (WRITTEN_OUT).
- G4's leftovers: plurals by the count, one wording for the about page, the report context's joints, the sheet's
  height in words.
"""

import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_metrics  # noqa: E402


def catalogue(rel: str = "locales/en.json") -> dict:
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return json.load(f)


# The limits by kind and the texts whose key does not say their kind ((catalogue, key) -> the limit of their role):
# tools/ui_metrics.py, whose "static" counts the texts over them with the same words (step 3d G2)
LIMITS = ui_metrics.R10_LIMITS
BY_ROLE = ui_metrics.R10_BY_ROLE
# Over a limit on purpose: {key: why}
LEFT = {"intro.result.spots": "today's result page (the user, 2026-11-19: it goes with line volume's round 6)",
        "intro.result.filters": "today's result page (as above)",
        "intro.result.check": "today's result page (as above)"}


def test_catalogue_texts_within_their_limit():
    over = [(x["key"], x["kind"], x["words"]) for x in ui_metrics.r10_over(REPO)
            if x["kind"] != "role" and x["key"] not in LEFT]
    assert over == [], over
    assert all(ui_metrics.text_group(k) in LIMITS for k in LEFT)  # a key named here is one the rule reads
    # the count of "static" is this test's: its texts over a limit are LEFT's, by kind, and none by role
    assert sorted(x["key"] for x in ui_metrics.r10_over(REPO)) == sorted(LEFT)


@pytest.mark.parametrize("rel,key", sorted(BY_ROLE))
def test_texts_by_role_within_their_limit(rel, key):
    text = catalogue(rel)[key]
    assert len(text.split()) <= BY_ROLE[(rel, key)], (key, len(text.split()), text)


# ---- R9: no character stands for a word in a text the user reads ---------------------------------------------------

R9_CHARS = "×→←≈≤≥‹›★▸▾↑↓Δ·"
PLUS_WORD = re.compile(r"(^|\s)\+\s")  # "+ Add a rig", "+ 2 more": a plus standing for "and" or "more"
# Kept, by key: {key: why} (docs/DESIGN.md row 47 and R9's allowed list; the rows of the user's answers)
R9_KEPT = {
    "ui.view3d.speed_value": "\"×1\": the 3D view's speed, a multiplier the user kept like a unit (row 47)",
    "ui.view3d.zoom_factor": "\"×8\": the eyes' zoom (row 47)",
    "ui.profile.scale_true": "\"×1.6\": the profile's vertical scale, kept like the 3D view's \"×1\" (the user, 2026-11-23)",
    "ui.view.chip.length_min": "≥ in a filter's chip (R9)", "ui.view.chip.length_max": "≤ in a filter's chip (R9)",
    "ui.view.chip.clearance_min": "≥ in a filter's chip (R9)", "ui.view.chip.height_min": "≥ in a filter's chip (R9)",
    "intro.result.spots": "today's result page (the user, 2026-11-19)",
    "intro.result.easy_within": "today's result page (the user, 2026-11-19)",
}
COVERAGE_KEPT = ("media.", "page.doc_title")  # the images' and videos' words (left for now), the page's title


def r9_hits(text: str) -> list:
    return [c for c in text if c in R9_CHARS] + (["+"] if PLUS_WORD.search(text) else [])


def test_no_character_for_a_word_in_the_catalogue():
    found = {k: r9_hits(v) for k, v in catalogue().items() if k not in R9_KEPT and r9_hits(v)}
    assert found == {}, found
    assert set(R9_KEPT) <= set(catalogue())  # each one named is there


@pytest.mark.parametrize("rel", ["locales/coverage/en.json", "locales/coverage/pl.json"])
def test_no_character_for_a_word_in_the_coverage_catalogue(rel):
    found = {k: r9_hits(v) for k, v in catalogue(rel).items()
             if isinstance(v, str) and not k.startswith(COVERAGE_KEPT) and r9_hits(v)}
    assert found == {}, found


# The free code that wrote ≤, ≥ or × before the user's answers (the layer's filters, ticks, bar titles, legend and
# sizes; the coverage tags, page and place map; the form's height difference): none of the three in its code (comments
# aside), nor an ASCII "<", ">", "<=" or ">=" before a template's value (`< ${x}`: 7 lines on main 4c56919c, the code
# review's pattern)
WRITTEN_OUT = ["viewer/src/app/c/LayerHistograms.tsx", "viewer/src/app/c/LayerPage.tsx", "viewer/src/app/c/layerState.ts",
               "viewer/src/coverage/page/card.tsx", "viewer/src/app/coverageLayer.ts", "viewer/src/search/SearchPanel.tsx",
               "viewer/src/Profile.tsx", "viewer/src/coarser.ts", "viewer/src/result/view/MapBar.tsx"]
ASCII_SIGN = re.compile(r"[<>]=?\s?\$\{")


@pytest.mark.parametrize("rel", WRITTEN_OUT)
def test_no_comparison_or_times_sign_in_the_code(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        code = ui_metrics.strip_comments(f.read())
    found = [(n, line.strip()) for n, line in enumerate(code.splitlines(), 1)
             if any(c in line for c in "≤≥×") or ASCII_SIGN.search(line)]
    assert found == [], found


# esbuild for Node with the page's assets as nothing and Leaflet as a stand-in that answers every use with itself
# (Leaflet reads the DOM when loaded; the modules extend its classes when loaded)
BUNDLE = """require('esbuild').build({entryPoints: [%s], bundle: true, format: 'cjs', platform: 'node', outfile: %s,
  loader: {'.css': 'empty', '.png': 'empty', '.svg': 'text', '.woff': 'empty', '.woff2': 'empty'},
  plugins: [{name: 'no-leaflet', setup(b) {
    b.onResolve({filter: /^leaflet$/}, () => ({path: 'leaflet', namespace: 'stub'}));
    b.onLoad({filter: /.*/, namespace: 'stub'}, () => ({loader: 'js', contents: 'const f = function () { return p; }; '
      + 'const p = new Proxy(f, {get: (t, k) => typeof k === "symbol" || k === "__esModule" ? undefined : p, '
      + 'apply: () => p, construct: () => p}); module.exports = p;'}));
  }}]}).catch(() => process.exit(1));"""


def node(tmp_path, entry: str, script: str):
    """viewer/<entry> bundled for Node (esbuild) and `script` run with it as `m`: its JSON output."""
    import shutil
    import subprocess
    if not shutil.which("node") or not os.path.isdir(os.path.join(REPO, "viewer", "node_modules")):
        pytest.skip("needs Node and viewer/node_modules")
    out = tmp_path / (os.path.basename(entry).split(".")[0] + ".cjs")
    subprocess.run(["node", "-e", BUNDLE % (json.dumps(entry), json.dumps(str(out)))],
                   cwd=os.path.join(REPO, "viewer"), check=True)
    path = tmp_path / "test.cjs"
    path.write_text("globalThis.document = {querySelector: () => null};  // app/api.ts reads the page's token\n"
                    f"const m = require({json.dumps(str(out))});\n{script}", encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def test_layer_limits_titles_and_sizes_in_words(tmp_path):
    """The layer's filters and chips say "at least", "under", "up to"; a chart's title carries the word its bare ticks
    need; a cell's size reads "by" (the user's answers of 2026-11-21, char-15 to char-21)."""
    found = node(tmp_path, "src/app/c/LayerHistograms.tsx", """
console.log(JSON.stringify([m.limitText("floor", "clearance", 5, true), m.limitText("below", "wall", 45, true),
  m.limitText("at_most", "lift_needed", 1, true), m.limitText("at_most", "lift_needed", 0, true),
  m.limitText("floor", "clearance", null, true), m.chartTitle("floor", "Clearance, m"), m.chartTitle("below", "Wall angle"),
  m.chartTitle("at_most", "A-frame, with zone, m")]));""")
    assert found == ["at least 5 m", "under 45°", "up to 1 m", "None needed", "Any", "Clearance, m (at\u00a0least)",
                     "Wall angle (under)", "A-frame, with zone, m (up\u00a0to)"]
    size = node(tmp_path, "src/app/c/layerState.ts", "console.log(JSON.stringify(m.sizeText(30 / 3600, 49.4)));")
    assert re.fullmatch(r"\d+\.\d by \d+\.\d km", size), size


# ---- G4's leftovers: plurals by the catalogue's rules, one wording, joints, the sheet's words ----------------------

PLURALS = [  # (key, the call that passes the count (its file and the code), {count: the text})
    ("ui.favourites.delete_folders", "viewer/src/app/c/FavouritesPage.tsx", 't("ui.favourites.delete_folders", {count:',
     {1: ", 1 folder in it", 3: ", 3 folders in it"}),
    ("ui.search.shapes", "viewer/src/search/SearchPanel.tsx", 't("ui.search.shapes", {count:',
     {1: "(1 shape)", 4: "(4 shapes; those that overlap or touch are one area)"}),
    ("ui.admin.limit_queue", "viewer/src/app/c/AdminC.tsx", 't("ui.admin.limit_queue", {count:',
     {1: "At most 1 search waiting or running.", 2: "At most 2 searches waiting or running."}),
    ("page.examples.spots", "web.py", "counted('page.examples.spots', spots)", {1: "1 spot", 12: "12 spots"}),
    ("page.examples.lines", "web.py", "counted('page.examples.lines', lines)", {1: "1 line", 2: "2 lines"}),
    ("ui.search.warnings", "viewer/src/search/SearchPanel.tsx", 't("ui.search.warnings", {count:',
     {1: "1 warning", 3: "3 warnings"}),
]


@pytest.mark.parametrize("key,rel,call,forms", PLURALS, ids=[p[0] for p in PLURALS])
def test_plurals_by_the_count(key, rel, call, forms):
    """One form for every number no more ("1 folders", "1 spots"): the catalogue's plural forms, the callers giving
    the count (the user's answers of 2026-11-21, left-01 to left-05)."""
    import messages
    assert {n: messages.text(key, count=n) for n in forms} == forms
    assert key not in catalogue()  # no bare key with one form beside the plural ones
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        assert call in f.read(), call


def test_examples_counts_on_the_sign_in_page():
    sys.path.insert(0, REPO)
    import web
    params = {"nmpt": None, "radius": 300, "resolution": 1, "slope_threshold": 60, "min_length": 20, "max_length": 200}
    page = web.demo_list([{"id": "r", "name": "A run", "summary": {"spots": 1, "lines": 1}, "has_map": False,
                           "params": params}])
    assert "1 spot · 1 line</span>" in page, page
    # a count that is no number (a summary written by hand): the text with what it has, never the bare key (the code
    # review's finding 5)
    odd = [{"id": "r", "name": "A run", "summary": {"spots": "3", "lines": None}, "has_map": False, "params": params},
           {"id": "s", "name": "B run", "summary": {"spots": "a few", "lines": "1"}, "has_map": False, "params": params}]
    page = web.demo_list(odd)
    assert "3 spots · 0 lines</span>" in page and "a few spots · 1 line</span>" in page, page


def test_one_wording_for_the_about_page():
    texts = catalogue()
    assert texts["page.about.title"] == texts["ui.account.about"] == "About and data licences"


def test_report_context_with_colons_and_semicolons():
    """A problem report's context on the admin page: labelled values ("page: result"), parts joined by "; " (the run's
    link holds a comma), never " · " between values (R9)."""
    texts = catalogue()
    assert [texts[f"ui.admin.context_{k}"] for k in ("page", "ui", "window")] == [
        "page: {{page}}", "interface: {{ui}}", "window: {{viewport}}"]
    with open(os.path.join(REPO, "viewer/src/app/c/AdminC.tsx"), encoding="utf-8") as f:
        code = f.read()
    context = code[code.index('class="u-small c-report-context"'):code.index("c-report-agent")]
    assert '{i > 0 && "; "}' in context and "·" not in context


def test_sheet_handle_says_its_height_in_words():
    texts = catalogue()
    assert [texts[f"ui.kit.sheet_state.{s}"] for s in ("peek", "half", "full")] == ["low", "half height", "full height"]
    with open(os.path.join(REPO, "viewer/src/ui/components.tsx"), encoding="utf-8") as f:
        code = f.read()
    assert 'state: stateWord(current)' in code and "state: current" not in code


def test_one_wording_for_report_a_problem_in_the_menus():
    """A menu item that opens a dialog ends with "…" in both menus (the account's and a search card's), the dialog's
    title without it (the user's answer of 2026-11-21, left-07)."""
    texts = catalogue()
    assert texts["ui.account.report"] == texts["ui.card.report"] == "Report a problem…"
    assert texts["ui.report.title"] == "Report a problem"
    with open(os.path.join(REPO, "viewer/src/app/c/Account.tsx"), encoding="utf-8") as f:
        assert 't("ui.account.report")' in f.read()


def test_the_users_words_after_the_reviews():
    """The user's four answers of 2026-11-21 after G5's reviews: the form's link says the dialog's title; the layer's
    notes and error say "chart" and "limit"; the admin's badge "waiting" (shown "Waiting" by c.css's ::first-letter)
    beside the heading's "waiting"; an at-most chart's last tick "over 2", "over" and its last value as its bar's title
    says it (`ui.layer.limit.over`), drawn 0.03 em tighter so it fits the 32 px of a bar (c.css)."""
    texts = catalogue()
    assert texts["intro.search.link"] == texts["intro.search.title"] == "How a search works"
    assert texts["ui.layer.hist.dimensions_note"] == ('Each chart applies every filter but its own. Click a bar to set '
                                                      'its limit ("?": the value is not known for the line).')
    assert texts["ui.layer.hist.dimensions_note_touch"] == texts["ui.layer.hist.dimensions_note"].replace("Click", "Tap")
    assert texts["ui.layer.hist.failed"] == "The charts could not be loaded."
    assert texts["ui.admin.user.pending"] == "waiting" and texts["ui.admin.users_waiting"] == "Users ({{n}} waiting)"
    assert texts["ui.layer.limit.over"] == "over {{value}}" and "ui.layer.hist.more" not in texts
    with open(os.path.join(REPO, "viewer/src/app/c/LayerHistograms.tsx"), encoding="utf-8") as f:
        assert 't("ui.layer.limit.over", {value: axisEdge(e[e.length - 1])}), "?"];' in f.read()
    with open(os.path.join(REPO, "viewer/src/app/c/c.css"), encoding="utf-8") as f:
        css = f.read()
    assert ".ui .c-admin .u-badge::first-letter { text-transform: uppercase; }" in css
    assert ('.ui .c-layer-hist[data-kind="at_most"] .c-layer-hist-axis span:nth-last-child(2) '
            '{ letter-spacing: -0.03em; }') in css


# ---- docs/wording.md: no word its first table rules out (the user, 2026-11-21: "what words are not to be used") ----

WORDING = os.path.join(REPO, "docs", "wording.md")
TICKED = re.compile(r"`([^`]+)`")


def wording_rows(heading: str) -> list:
    """The rows of the table under `## heading` in docs/wording.md, each a list of its cells."""
    with open(WORDING, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    part = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    lines = [line.strip() for line in part.split("\n") if line.startswith("| ")]
    return [[cell.strip() for cell in line.strip("|").split(" | ")] for line in lines[2:]]  # past the head


def readable_texts() -> dict:
    """{where: text} of what a person reads: the catalogues' values ("<file> <key>") and the server pages' text
    ("page <name>"), their {{placeholders}} and markup left out."""
    import html as html_lib
    sys.path.insert(0, REPO)
    import accounts as ac
    import web
    out = {f"{rel} {key}": value for rel in ("locales/en.json", "locales/coverage/en.json")
           for key, value in catalogue(rel).items() if isinstance(value, str)}
    waiting = ac.User(id=7, provider="github", subject="1", name="Ann", status="pending", admin=False)
    pages = {"sign-in": web.signin_page(["github", "google"], total=(5.0, 1)),
             "sign-in, waiting": web.signin_page(["github"], waiting, "token"),
             "about": web.about_page("admin@example.org", esri=True, ring=True),
             "privacy": web.privacy_page("admin@example.org", 30, ring=True)}
    for name, page in pages.items():
        out[f"page {name}"] = html_lib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ",
                                                                               page)))
    return {where: re.sub(r"<[^>]+>", " ", re.sub(r"\{\{[^}]*\}\}", " ", text)) for where, text in out.items()}


def test_no_word_the_wording_guide_rules_out():
    """docs/wording.md's first table: no catalogue value and no server page's text holds a word of its "Not" column
    (whole words, in any case) but the exceptions the doc lists, and each listed exception still holds its word."""
    nots = {w for row in wording_rows("Words to use and words not to use") for w in TICKED.findall(row[1])}
    assert {"walker", "slackliner", "histogram", "threshold", "pending", "How searching works",
            "About / data licences"} <= nots, nots  # the table read (a changed layout would read nothing)
    allowed = {(" ".join(TICKED.findall(row[0])), w) for row in wording_rows("Exceptions")
               for w in TICKED.findall(row[1])}
    hits = {(where, w) for where, text in readable_texts().items() for w in nots
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text, re.I)}
    assert sorted(hits - allowed) == [], "a word docs/wording.md rules out"
    assert sorted(allowed - hits) == [], "an exception of docs/wording.md no longer needed: remove its row"


# ---- The intro behind its link gives the focus back (the code review's finding 1, the design review's F2) ----------

INTRO_LINK = ".s-intro .n-intro-link"
ON_LINK = "() => document.activeElement?.matches('.s-intro .n-intro-link') === true"


def test_intro_gives_the_focus_back_to_its_link(tmp_path):
    """"How a search works" closed by Got it (a press), Escape, Enter on Got it, and on the iPhone's profile (WebKit,
    where a tap focuses no button) by a tap: the focus is back on the form's link each time, never on the page
    (`ui/Intro.tsx` `focusBack`: the opener, else the intro's own link)."""
    from test_web import EDGE, WAIT, _playwright, _search_page, _server
    if not os.path.exists(EDGE) or not _playwright():
        pytest.skip("needs Microsoft Edge and Playwright (group ui)")
    from playwright.sync_api import sync_playwright
    _search_page(tmp_path, "", folder_name="introtest")
    found = {}
    with _server(tmp_path) as port, sync_playwright() as p:
        url = f"http://127.0.0.1:{port}/runs/introtest/index.html?ui=c#new"

        def opened(page):
            page.wait_for_selector("dialog.n-intro[open]", timeout=WAIT)

        def closed(page) -> bool:
            page.wait_for_function("() => !document.querySelector('dialog.n-intro[open]')", timeout=WAIT)
            return page.evaluate(ON_LINK)

        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url)
            page.wait_for_selector(".s-panel .s-tabs", timeout=WAIT)
            page.click(INTRO_LINK)  # a press: Got it by the mouse
            opened(page)
            page.click("dialog.n-intro[open] button.u-pri")
            found["got it"] = closed(page)
            page.focus(INTRO_LINK)  # the keyboard: Enter opens it, Escape closes it
            page.keyboard.press("Enter")
            opened(page)
            page.keyboard.press("Escape")
            found["escape"] = closed(page)
            page.focus(INTRO_LINK)  # Enter on Got it
            page.keyboard.press("Enter")
            opened(page)
            page.focus("dialog.n-intro[open] button.u-pri")
            page.keyboard.press("Enter")
            found["enter"] = closed(page)
        finally:
            browser.close()
        browser = p.webkit.launch()
        try:
            iphone = {k: v for k, v in p.devices["iPhone 13"].items() if k != "default_browser_type"}
            page = browser.new_context(**iphone).new_page()
            page.goto(url)
            page.wait_for_selector(".s-panel .s-tabs", timeout=WAIT)
            page.tap(INTRO_LINK)
            opened(page)
            page.tap("dialog.n-intro[open] button.u-pri")
            found["tap"] = closed(page)
        finally:
            browser.close()
    assert found == {"got it": True, "escape": True, "enter": True, "tap": True}, found
