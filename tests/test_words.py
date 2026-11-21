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


LIMITS = {"help": 40, "intro": 30, "hint": 25, "error": 30}
# Texts whose key does not say their kind: (catalogue, key) -> the limit of their role
BY_ROLE = {
    ("locales/en.json", "ui.search.draw_hint"): 25,          # a hint under the drawing tools
    ("locales/en.json", "ui.osm.intro"): 30,                  # the OSM page's intro paragraph
    ("locales/en.json", "basic.size.factors"): 40,            # in the size word's "?"
    ("locales/en.json", "ui.access.easy_means"): 40,          # rows of the access key's "?"
    ("locales/en.json", "ui.access.cannot_tell_means"): 40,
    ("locales/en.json", "ui.access.hard_means"): 40,
    ("locales/en.json", "ui.layer.scale_fit_note"): 25,       # the layer's notes
    ("locales/en.json", "ui.layer.scale_fixed_note"): 25,
    ("locales/en.json", "ui.layer.hist.strip_note"): 25,
    ("locales/en.json", "ui.layer.search_border"): 25,
    ("locales/en.json", "ui.layer.search_border_any"): 25,
    ("locales/en.json", "ui.layer.search_partner"): 25,
    ("locales/en.json", "ui.layer.search_partner_any"): 25,
    ("locales/coverage/en.json", "page.lead"): 30,            # the coverage page's lead
    ("locales/coverage/pl.json", "page.lead"): 30,
}
# Over a limit on purpose: {key: why}
LEFT = {"intro.result.spots": "today's result page (the user, 2026-11-19: it goes with line volume's round 6)",
        "intro.result.filters": "today's result page (as above)",
        "intro.result.check": "today's result page (as above)"}


def test_catalogue_texts_within_their_limit():
    over = [(k, ui_metrics.text_group(k), len(v.split())) for k, v in catalogue().items()
            if ui_metrics.text_group(k) in LIMITS and k not in LEFT and len(v.split()) > LIMITS[ui_metrics.text_group(k)]]
    assert over == [], over
    assert all(ui_metrics.text_group(k) in LIMITS for k in LEFT)  # a key named here is one the rule reads


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
# aside)
WRITTEN_OUT = ["viewer/src/app/c/LayerHistograms.tsx", "viewer/src/app/c/LayerPage.tsx", "viewer/src/app/c/layerState.ts",
               "viewer/src/coverage/page/card.tsx", "viewer/src/app/coverageLayer.ts", "viewer/src/search/SearchPanel.tsx"]


@pytest.mark.parametrize("rel", WRITTEN_OUT)
def test_no_comparison_or_times_sign_in_the_code(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as f:
        code = ui_metrics.strip_comments(f.read())
    found = [(n, line.strip()) for n, line in enumerate(code.splitlines(), 1) if any(c in line for c in "≤≥×")]
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
    ("page.examples.spots", "web.py", "page_text('page.examples.spots', count=", {1: "1 spot", 12: "12 spots"}),
    ("page.examples.lines", "web.py", "page_text('page.examples.lines', count=", {1: "1 line", 2: "2 lines"}),
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
