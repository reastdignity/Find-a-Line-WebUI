"""tools/ui_metrics.py: the counters of "static" on small inputs of known counts, the page-measuring script on a page
of known sizes (Playwright's Edge, as tests/test_web.py), and the contexts of tools/ui_shots.py's loop (bypass_csp
only when asked for)."""

import inspect
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import ui_metrics  # noqa: E402
import ui_shots  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

TOKENS_CSS = """.ui { --surface: #fff; --line: #d2dad4; --mono: ui-monospace, monospace; }
"""
A_CSS = r"""/* .x { font-size: 99px; color: #123456; border-radius: 3px } */
@import "./ui/tokens.css";
.ui .p { font: 600 13px/1.2 var(--display); border-radius: 10px; z-index: 5; color: #abc; }
.ui .q { font-size: 13px; border-radius: 4px 4px 0 0; z-index: 1000; background: rgb(1 2 3 / .5); }
@media (max-width: 600px) { .ui .p { font-size: 11.5px; z-index: 5; } }
.ui .box { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: var(--shadow); }
.ui .three { background: var(--surface-2); border: 1px solid var(--line);
  border-radius: 8px; }
.ui .br { border: 1px solid var(--line); border-radius: 999px; }
.ui .no { border: 2px solid var(--line); border-radius: 6px; }
.ui .m { font: 500 11px var(--mono); }
.ui .m { text-transform: uppercase; }
.ui .m2, .ui .m3 { font-family: Consolas, monospace; }
.ui .c::after { content: "\25BE"; }
.ui .d::before { content: "×"; }
.ui .e { --local: #ff0000; }
"""
X_TSX = """// a comment with × and ▾ that does not count
import { t } from "./i18n";
const url = "https://example.org/a";  // × in a comment after a string holding //
const tpl = `${url} · ${"x"}`;
/* block × comment */
export const A = () => <div title="Close the panel">×</div>;
export const B = () => <p>A1 12.3 m → A2 10.1 m</p>;
const re = /[▾]/;
const colour = "#e10fd6";
"""
Y_TSX = """import { t } from "./i18n";
export const C = () => <b>{t("ui.x")}</b>;
"""
Z_TSX = """import { label } from "./i18n";
export const D = () => <span>Loading the run</span>;
export const E = () => <i>{label("x")}</i>;
"""
CATALOGUE = {"intro.a": "One two three four five.", "intro.b": "One two three.", "hint.a": "Tap the map.",
             "field.x.help": "A help text of six words.", "ui.y.help": "Two words", "error.a": "It failed.",
             "ui.a": "Sort ▾", "ui.b": "12 m · 3 lines", "ui.c": "↑ × ✓", "field.x.unit": "", "rest.a": "Rest"}


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "viewer" / "src" / "ui").mkdir(parents=True)
    (tmp_path / "locales").mkdir()
    for name, text in (("viewer/src/ui/tokens.css", TOKENS_CSS), ("viewer/src/a.css", A_CSS),
                       ("viewer/src/x.tsx", X_TSX), ("viewer/src/y.tsx", Y_TSX), ("viewer/src/z.tsx", Z_TSX)):
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "locales" / "en.json").write_text(json.dumps(CATALOGUE, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_css_counts(tree):
    """Font sizes (the shorthand too, not a custom property's), radii, z-index, colours outside the tokens (a
    custom property's too, not a comment's), monospace with its uppercase (merged over a selector's rules), the
    four looks of a container and the characters of CSS content (an escape decoded)."""
    r = ui_metrics.static(str(tree))
    assert {x["value"]: x["count"] for x in r["font_sizes"]} == {"13px": 2, "11.5px": 1, "11px": 1}
    assert r["font_sizes_px"] == [11, 11.5, 13]
    assert {x["value"]: x["count"] for x in r["radii"]} == {"10px": 1, "4px 4px 0 0": 1, "12px": 1, "8px": 1,
                                                            "999px": 1, "6px": 1}
    assert {x["value"]: x["count"] for x in r["z_index"]} == {"5": 2, "1000": 1}
    assert r["colours_outside_tokens"] == {"viewer/src/a.css": {"#abc": 1, "#ff0000": 1, "rgb(1 2 3 / .5)": 1}}
    assert [(m["selector"], m["uppercase"]) for m in r["mono"]] == [(".ui .m", True), (".ui .m2, .ui .m3", False)]
    assert r["mono_uppercase"] == 1
    boxes = {b["selector"]: (b["surface"], b["border"], b["radius"], b["shadow"]) for b in r["boxes"]}
    assert boxes == {".ui .box": (True, True, True, True), ".ui .three": (True, True, True, False),
                     ".ui .br": (False, True, True, False)}
    assert r["boxes_totals"] == {"all four": 1, "three": 1, "two": 1, "border and radius only": 1}
    assert [(x["char"], x["selector"]) for x in r["chars_in_css_content"]] == [("▾", ".ui .c::after"),
                                                                                ("×", ".ui .d::before")]


def test_code_and_catalogue_counts(tree):
    """Characters in the code (not in comments, also after a string holding "//" and in a template and a regular
    expression), in the catalogue; dense strings; the catalogue's texts by group; the .tsx files with English in
    code and without t(; colours in the code."""
    r = ui_metrics.static(str(tree))
    assert [(x["file"], x["line"], x["char"]) for x in r["chars_in_code"]] == [
        ("viewer/src/x.tsx", 4, "·"), ("viewer/src/x.tsx", 6, "×"), ("viewer/src/x.tsx", 7, "→"),
        ("viewer/src/x.tsx", 8, "▾")]
    assert [(x["key"], x["char"]) for x in r["chars_in_catalogue"]] == [
        ("ui.a", "▾"), ("ui.b", "·"), ("ui.c", "↑"), ("ui.c", "×"), ("ui.c", "✓")]
    assert [d["where"] for d in r["dense_strings"]] == ["viewer/src/x.tsx:4", "locales/en.json:ui.b",
                                                        "locales/en.json:ui.c"]
    assert r["texts"] == {
        "intro": {"texts": 2, "words": 8, "median": 4, "p90": 5, "longest": 5},
        "hint": {"texts": 1, "words": 3, "median": 3, "p90": 3, "longest": 3},
        "help": {"texts": 2, "words": 8, "median": 4, "p90": 6, "longest": 6},
        "error": {"texts": 1, "words": 2, "median": 2, "p90": 2, "longest": 2},
        "ui": {"texts": 3, "words": 10, "median": 3, "p90": 5, "longest": 5},
        "rest": {"texts": 1, "words": 1, "median": 1, "p90": 1, "longest": 1}}
    assert r["texts_empty"] == 1 and r["texts_total"] == 11
    assert [x["key"] for x in r["longest_texts"][:2]] == ["field.x.help", "intro.a"]
    assert r["tsx_without_t"] == {
        "english, no t(": ["viewer/src/x.tsx", "viewer/src/z.tsx"],
        "english, no t( nor label(, errorText(, quantity(, detailMessage(": ["viewer/src/x.tsx"],
        "two English texts or more, no t(": ["viewer/src/x.tsx"],
        "no t( at all": ["viewer/src/x.tsx", "viewer/src/z.tsx"]}
    assert r["colours_in_code"] == {"viewer/src/x.tsx": {"#e10fd6": 1}}


def test_static_is_deterministic(tree, tmp_path_factory):
    """The same tree gives the same JSON and Markdown."""
    first, second = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    for out in (first, second):
        r = ui_metrics.static(str(tree))
        ui_metrics._write(str(out), "static", r, ui_metrics.static_markdown(r))
    for name in ("static.json", "static.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_strip_comments():
    """Comments become spaces (lines kept); strings, templates with ${} and regular expressions stay."""
    code = 'a = "//x"; // c\nb = `/* ${"}"} */`; /* d\n e */ f = /\\/\\//g; g = h / 2; // end'
    stripped = ui_metrics.strip_comments(code)
    assert stripped.split("\n")[0].rstrip() == 'a = "//x";'
    assert '`/* ${"}"} */`' in stripped and "/\\/\\//g" in stripped and "h / 2;" in stripped
    assert "end" not in stripped and " d" not in stripped and stripped.count("\n") == 2


class _Fake:
    """Playwright's objects as far as prepared_pages uses them with no pages."""
    def __init__(self):
        self.contexts = []
        self.devices = {"iPhone 13": {"viewport": {"width": 390, "height": 664}, "default_browser_type": "webkit"}}
        self.chromium = self.webkit = self

    def launch(self):
        return self

    def new_context(self, **options):
        self.contexts.append(options)
        return self

    def add_init_script(self, script):
        pass

    def close(self):
        pass


def test_bypass_csp_only_when_asked():
    """The screenshot tool's contexts never bypass the CSP; the measuring pass's do (constraint 2)."""
    for options, bypass in ((None, None), ({"bypass_csp": True}, True)):
        pw = _Fake()
        assert list(ui_shots.prepared_pages(pw, "https://x", {}, "r", "s", "l", "a", "b", {}, ["desktop", "iphone"],
                                            ["light", "dark"], options)) == []
        assert len(pw.contexts) == 4 and all(c.get("bypass_csp") is bypass for c in pw.contexts)
    assert "bypass_csp" not in inspect.getsource(ui_shots.main)


def _playwright() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


PAGE = """<!doctype html><html lang="en"><head><style>
body { margin: 0; font-size: 16px; } button { font-size: 16px; }
#b1 { width: 30px; height: 30px; } .tiny { width: 20px; height: 50px; }
a { display: inline-block; width: 50px; height: 50px; }
.lab { display: inline-block; width: 100px; height: 20px; }
.lab input { position: absolute; width: 1px; height: 1px; opacity: 0; margin: 0; }
.off { width: 10px; height: 10px; } .gone { display: none; }
.small { font-size: 10.5px; } .pan { width: 100px; height: 50px; overflow: auto; } .pan div { width: 300px; }
.wide { width: 2000px; height: 1px; }
</style></head><body>
<button id="b1">A</button><button class="tiny">B</button><a href="#x">Go</a>
<label class="lab"><input type="checkbox">Tick</label>
<button class="off" disabled>x</button><button class="gone">h</button>
<p class="small">Small text here</p><p>Big</p>
<div class="pan"><div>wide</div></div>
<svg width="200" height="100" viewBox="0 0 100 50"><text x="0" y="20" font-size="10" class="lbl">Scaled</text></svg>
<div class="wide"></div>
</body></html>"""


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_measure_a_page():
    """Controls by box (a hidden checkbox by its label; disabled and hidden ones left out), text by its rendered size
    (SVG text scaled to the screen), sideways scroll of a panel and of the document."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.set_content(PAGE)
            r = ui_metrics.measure(page, None)
            # an open modal dialog: the page behind it is inert, its own controls only count
            page.evaluate("() => { const d = document.createElement('dialog'); d.innerHTML = "
                          "'<button class=\"in\">OK</button>'; document.body.append(d); d.showModal(); }")
            modal = ui_metrics.measure(page, None)
        finally:
            browser.close()
    assert r["controls"] == 4
    assert r["controls_under"] == {
        "44": {"button": 1, "button.tiny": 1, "input[type=checkbox] (by its label)": 1},
        "24": {"button.tiny": 1, "input[type=checkbox] (by its label)": 1}}
    assert r["control_examples"]["input[type=checkbox] (by its label)"]["w"] == 100
    assert r["text_chars"] == 37
    assert r["text_chars_under"] == {"12": 15, "11": 15, "10": 0}
    assert r["text_under"]["12"] == {"p.small": 15}
    assert r["text_examples"]["p.small"] == {"size": 10.5, "text": "Small text here"}
    assert r["sideways"] == [{"sig": "div.pan", "over": 200}]
    assert r["document_over"] == 1200
    assert "axe" not in r
    assert modal["controls"] == 1 and modal["controls_under"]["44"] == {"button.in": 1}


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright() or not os.path.exists(ui_metrics.AXE),
                    reason="needs Microsoft Edge, Playwright (group ui) and axe-core (npm ci in viewer)")
def test_axe_on_a_page():
    """axe-core's violations of a page with an image without alt and no lang: its rules with their impacts."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page()
            page.set_content('<!doctype html><html><head><title>t</title></head><body><main>'
                             '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="20" height="20">'
                             '</main></body></html>')
            r = ui_metrics.measure(page, ui_metrics._axe_source())
        finally:
            browser.close()
    rules = {x["id"]: x for x in r["axe"]["violations"]}
    assert rules["image-alt"]["impact"] == "critical" and rules["image-alt"]["nodes"] == 1
    assert rules["image-alt"]["example"] == "img"
    assert rules["html-has-lang"]["impact"] == "serious"


def test_summary_deduplicates():
    """The summary: totals per device and theme, signatures counted once per state over all states."""
    def state(page, device, n44, chars_small):
        return {"page": page, "device": device, "theme": "light", "controls": 3,
                "controls_under": {"44": {"button.x": n44}, "24": {}},
                "control_examples": {"button.x": {"w": 30, "h": 30, "text": "X"}},
                "text_chars": 100, "text_chars_under": {"12": chars_small, "11": 0, "10": 0},
                "text_under": {"12": {"span.s": chars_small}, "11": {}, "10": {}},
                "text_examples": {"span.s": {"size": 11.5, "text": "s"}}, "document_over": 0, "sideways": [],
                "axe": {"violations": [{"id": "color-contrast", "impact": "serious", "tags": ["wcag2aa"], "nodes": 2,
                                        "example": ".m"}], "incomplete": []},
                "seconds": {"load": 3.0, "steps": 1.0, "measure": 0.5}}
    s = ui_metrics.summarise([state("a", "iphone", 2, 10), state("b", "iphone", 1, 30), state("a", "desktop", 4, 0)])
    phone = s["per_device_theme"]["iphone light"]
    assert phone["controls_under_44"] == 3 and phone["control_signatures_under_44"] == 1
    assert phone["text_share_under_12"] == 0.2 and phone["axe_violations_nodes"]["serious"] == 4
    row = s["lists"]["controls_under_44_phones"][0]
    assert (row["signature"], row["states"], row["count"], row["pages"]) == ("button.x", 2, 3, 2)
    assert s["lists"]["controls_under_44_desktop"][0]["count"] == 4
    assert s["lists"]["axe"][0]["states"] == 3 and s["seconds_total"] == 13.5
    assert "| iphone light | 2 |" in ui_metrics.pages_markdown(s)
