"""tools/ui_metrics.py: the counters of "static" on small inputs of known counts; the page-measuring script on a page
of known sizes in Chromium (Playwright's Edge, as tests/test_web.py) and WebKit (the iPhone's engine); axe-core and its
failures; tools/ui_shots.py's loop on a small local site (a failing step, an early stop, the contexts' CSP); the pass's
loop with a failing state; the summary and --summarise."""

import inspect
import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
.ui .f { color: #FFF; background: #ffffff; border-color: rgb(0,0,0); outline-color: rgb(0, 0, 0); }
.ui .g { font: 600 var(--fs)/1.4 var(--font); }
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
export const C = () => <button aria-label="Close ×">×</button>;
export const U = () => <p>https://example.org · see ✓</p>;
"""
Y_TSX = """import { t } from "./i18n";
export const C = () => <b>{t("ui.x")}</b>;
"""
Z_TSX = """import { label } from "./i18n";
export const D = () => <span>Loading the run</span>;
export const E = () => <i>{label("x")}</i>;
"""
GALLERY_TSX = """export const G = () => <p>× · ✓</p>;
"""
CATALOGUE = {"intro.a": "One two three four five.", "intro.b": "One two three.", "hint.a": "Tap the map.",
             "field.x.help": "A help text of six words.", "ui.y.help": "Two words", "error.a": "It failed.",
             "ui.a": "Sort ▾", "ui.b": "12 m · 3 lines", "ui.c": "↑ × ✓", "field.x.unit": "", "rest.a": "Rest"}


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "viewer" / "src" / "ui").mkdir(parents=True)
    (tmp_path / "locales").mkdir()
    for name, text in (("viewer/src/ui/tokens.css", TOKENS_CSS), ("viewer/src/a.css", A_CSS),
                       ("viewer/src/x.tsx", X_TSX), ("viewer/src/y.tsx", Y_TSX), ("viewer/src/z.tsx", Z_TSX),
                       ("viewer/src/ui/Gallery.tsx", GALLERY_TSX)):
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "locales" / "en.json").write_text(json.dumps(CATALOGUE, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_css_counts(tree):
    """Font sizes (the shorthand too, a var() size as "unresolved", not a custom property's), radii, z-index, colours
    outside the tokens (normalised; a custom property's too, not a comment's), monospace with its uppercase (merged
    over a selector's rules), the four looks of a container and the characters of CSS content (an escape decoded)."""
    r = ui_metrics.static(str(tree))
    assert {x["value"]: x["count"] for x in r["font_sizes"]} == {"13px": 2, "11.5px": 1, "11px": 1, "unresolved": 1}
    assert r["font_sizes_px"] == [11, 11.5, 13]
    assert {x["value"]: x["count"] for x in r["radii"]} == {"10px": 1, "4px 4px 0 0": 1, "12px": 1, "8px": 1,
                                                            "999px": 1, "6px": 1}
    assert {x["value"]: x["count"] for x in r["z_index"]} == {"5": 2, "1000": 1}
    assert r["colours_outside_tokens"] == {"viewer/src/a.css": {"#aabbcc": 1, "#ff0000": 1, "#ffffff": 2,
                                                                "rgb(0, 0, 0)": 2, "rgb(1 2 3 / .5)": 1}}
    assert [(m["selector"], m["uppercase"]) for m in r["mono"]] == [(".ui .m", True), (".ui .m2, .ui .m3", False)]
    assert r["mono_uppercase"] == 1
    boxes = {b["selector"]: (b["surface"], b["border"], b["radius"], b["shadow"]) for b in r["boxes"]}
    assert boxes == {".ui .box": (True, True, True, True), ".ui .three": (True, True, True, False),
                     ".ui .br": (False, True, True, False)}
    assert r["boxes_totals"] == {"all four": 1, "three": 1, "two": 1, "border and radius only": 1}
    assert [(x["char"], x["selector"]) for x in r["chars_in_css_content"]] == [("▾", ".ui .c::after"),
                                                                                ("×", ".ui .d::before")]


def test_code_and_catalogue_counts(tree):
    """Characters in the code (not in comments or regular expressions; after a string holding "//", in a template, in
    JSX text after "https://"); inside an aria-label or a title apart as not shown; the demo pages left out unless
    asked for; in the catalogue; dense strings; the catalogue's texts by group; the .tsx files with English in code
    and without t(; colours in the code."""
    r = ui_metrics.static(str(tree))
    assert [(x["file"], x["line"], x["char"]) for x in r["chars_in_code"]] == [
        ("viewer/src/x.tsx", 4, "·"), ("viewer/src/x.tsx", 6, "×"), ("viewer/src/x.tsx", 7, "→"),
        ("viewer/src/x.tsx", 10, "×"), ("viewer/src/x.tsx", 11, "·"), ("viewer/src/x.tsx", 11, "✓")]
    assert [(x["line"], x["char"]) for x in r["chars_not_shown"]] == [(10, "×")]
    assert r["demos_left_out"] == ["viewer/src/ui/Gallery.tsx"]
    assert [(x["key"], x["char"]) for x in r["chars_in_catalogue"]] == [
        ("ui.a", "▾"), ("ui.b", "·"), ("ui.c", "↑"), ("ui.c", "×"), ("ui.c", "✓")]
    assert [d["where"] for d in r["dense_strings"]] == ["viewer/src/x.tsx:4", "viewer/src/x.tsx:11",
                                                        "locales/en.json:ui.b", "locales/en.json:ui.c"]
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
        "no t( at all": ["viewer/src/ui/Gallery.tsx", "viewer/src/x.tsx", "viewer/src/z.tsx"]}
    assert r["colours_in_code"] == {"viewer/src/x.tsx": {"#e10fd6": 1}}
    demos = ui_metrics.static(str(tree), with_demos=True)
    assert demos["demos_left_out"] == []
    assert [(x["file"], x["char"]) for x in demos["chars_in_code"]][:3] == [
        ("viewer/src/ui/Gallery.tsx", "×"), ("viewer/src/ui/Gallery.tsx", "·"), ("viewer/src/ui/Gallery.tsx", "✓")]


def test_set_attribute_is_not_shown(tmp_path):
    """A character in a setAttribute of aria-label or title (DOM code, not JSX) is not shown; one set as text is."""
    (tmp_path / "viewer" / "src" / "ui").mkdir(parents=True)
    (tmp_path / "locales").mkdir()
    (tmp_path / "viewer" / "src" / "ui" / "tokens.css").write_text("", encoding="utf-8")
    (tmp_path / "locales" / "en.json").write_text("{}", encoding="utf-8")
    (tmp_path / "viewer" / "src" / "dom.ts").write_text(
        'button.setAttribute("aria-label", "Close ×");\nbutton.setAttribute("title", `Next ›`);\n'
        'button.textContent = "×";\n', encoding="utf-8")
    r = ui_metrics.static(str(tmp_path))
    assert [(x["line"], x["char"]) for x in r["chars_not_shown"]] == [(1, "×"), (2, "›")]
    assert [(x["line"], x["char"]) for x in r["chars_in_code"]] == [(3, "×")]


def test_dense_strings_per_literal(tmp_path):
    """A dense string is one literal (a quoted string, a template, a run of JSX text) with two characters or more or a
    joint: two literals of one line with one character each are not one dense string."""
    (tmp_path / "viewer" / "src" / "ui").mkdir(parents=True)
    (tmp_path / "locales").mkdir()
    (tmp_path / "viewer" / "src" / "ui" / "tokens.css").write_text("", encoding="utf-8")
    (tmp_path / "locales" / "en.json").write_text("{}", encoding="utf-8")
    (tmp_path / "viewer" / "src" / "d.tsx").write_text(
        'const a = up ? "↓" : "↑";\nconst b = "↑ ↓";\nexport const C = () => <p>{n} · {m}</p>;\n'
        'const s = `${x} · ${y}`;\n', encoding="utf-8")
    r = ui_metrics.static(str(tmp_path))
    assert [(d["where"], d["text"]) for d in r["dense_strings"]] == [
        ("viewer/src/d.tsx:2", '"↑ ↓"'), ("viewer/src/d.tsx:3", "·"), ("viewer/src/d.tsx:4", "`${x} · ${y}`")]
    assert len(r["chars_in_code"]) == 6


def test_static_is_deterministic(tree, tmp_path_factory):
    """The same tree gives the same JSON and Markdown."""
    first, second = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    for out in (first, second):
        r = ui_metrics.static(str(tree))
        ui_metrics._write(str(out), "static", r, ui_metrics.static_markdown(r))
    for name in ("static.json", "static.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_strip_comments():
    """Comments become spaces (lines kept); strings, templates with ${} and regular expressions stay (or become
    spaces with blank_regex); "//" after "https:" in JSX text is no comment."""
    code = 'a = "//x"; // c\nb = `/* ${"}"} */`; /* d\n e */ f = /\\/\\//g; g = h / 2; // end\n<p>https://x.org ×</p>'
    stripped = ui_metrics.strip_comments(code)
    assert stripped.split("\n")[0].rstrip() == 'a = "//x";'
    assert '`/* ${"}"} */`' in stripped and "/\\/\\//g" in stripped and "h / 2;" in stripped
    assert "end" not in stripped and " d" not in stripped and stripped.count("\n") == 3
    assert stripped.split("\n")[3] == "<p>https://x.org ×</p>"
    blanked = ui_metrics.strip_comments(code, blank_regex=True)
    assert "/\\/\\//g" not in blanked and "h / 2;" in blanked and blanked.split("\n")[3].endswith("x.org ×</p>")
    odd = "z = [/ a\n×]"  # a "/" that opens no regular expression on its line: the lines stay as they are
    assert ui_metrics.strip_comments(odd, blank_regex=True) == odd
    # JSX text: a "/" after "}" or ">" opens no regular expression; "word:// note" is a comment, an arrow's regex is one
    jsx = "<p>{a} / {b} ×</p>\n<p>/ day ×</p>\nx = default:// note\nf = (s) => /×/.test(s)"
    lines = ui_metrics.strip_comments(jsx, blank_regex=True).split("\n")
    assert lines[:2] == ["<p>{a} / {b} ×</p>", "<p>/ day ×</p>"]
    assert lines[2].rstrip() == "x = default:" and "×" not in lines[3] and lines[3].endswith(".test(s)")


def test_font_size_and_colour_edges():
    """A font whose size is var() or calc() is "unresolved", "font: inherit" sets none; #FFF, #fff and #ffffff are one
    colour, so are rgb() with and without spaces."""
    assert ui_metrics.font_size_of("font", "600 var(--fs)/1.4 x") == "unresolved"
    assert ui_metrics.font_size_of("font", "calc(1em + 2px) x") == "unresolved"
    assert ui_metrics.font_size_of("font", "inherit") is None
    assert ui_metrics.font_size_of("font", "500 12px var(--mono)") == "12px"
    assert {ui_metrics._colour(c) for c in ("#FFF", "#fff", "#ffffff")} == {"#ffffff"}
    assert ui_metrics._colour("rgb(0,0,0)") == ui_metrics._colour("rgb( 0, 0 , 0 )") == "rgb(0, 0, 0)"


class _Fake:
    """Playwright's objects as far as ui_shots.shoot_all uses them with no pages."""
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
    shots, metrics = _Fake(), _Fake()
    ui_shots.shoot_all(shots, {}, [], ["desktop", "iphone"], ["light", "dark"], None, False, {}, [], [])
    assert ui_metrics.measure_all(metrics, {}, [], ["desktop", "iphone"], ["light", "dark"], None, io.StringIO()) == []
    assert len(shots.contexts) == len(metrics.contexts) == 4
    assert all("bypass_csp" not in c for c in shots.contexts)
    assert all(c["bypass_csp"] is True for c in metrics.contexts)
    assert "bypass_csp" not in inspect.getsource(ui_shots.main)


def _playwright() -> bool:
    import importlib.util
    return importlib.util.find_spec("playwright") is not None


def _launch(p, engine: str):
    """Edge for "chromium" (as tests/test_web.py), Playwright's WebKit for "webkit"; skipped when it is missing."""
    try:
        return p.chromium.launch(channel="msedge", headless=True) if engine == "chromium" else p.webkit.launch()
    except Exception as e:
        pytest.skip(f"{engine} not available: {type(e).__name__}")


BROWSER = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                             reason="needs Microsoft Edge and Playwright (group ui)")


def _measured(body: str, style: str = "", engine: str = "chromium", width: int = 800, height: int = 600) -> dict:
    """measure() of a small page of the test's own: `style` and `body`, no margins, 16 px text, no scrollbars."""
    from playwright.sync_api import sync_playwright
    html = ("<!doctype html><html lang='en'><head><style>::-webkit-scrollbar { width: 0; height: 0; } "
            "body { margin: 0; font-size: 16px; } button { font-size: 16px; } " + style + "</style></head><body>"
            + body + "</body></html>")
    with sync_playwright() as p:
        browser = _launch(p, engine)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html)
            return ui_metrics.measure(page, None)
        finally:
            browser.close()


@BROWSER
def test_signatures_keep_base_classes():
    """A state class leaves the signature (one control in two states is one signature); a base class that ends like a
    state (c-card-open, Home's run cards) stays, so the card is not merged with every bare link."""
    r = _measured('<a href="#r" class="c-card-open">Run</a><a href="#p">Plain</a>'
                  '<button class="seg u-on">x</button><button class="seg">y</button>',
                  "a, button { display: inline-block; width: 30px; height: 30px; }")
    assert r["controls_under"]["44"] == {"a": 1, "a.c-card-open": 1, "button.seg": 2}


@BROWSER
def test_reach_through_clipping_and_scrolling():
    """Reachable: an absolute control past an overflow-hidden box that is not its containing block counts; a control
    half clipped counts with its visible part; one clipped away wholly, one past an overflow-x hidden side of a panel
    that scrolls only vertically, and one before a scroller's origin are unreachable; one below a scroller's fold
    counts."""
    r = _measured(
        '<div class="cb"><div class="clip"><button class="abs">A</button></div></div>'
        '<div class="half"><button class="cut">C</button></div>'
        '<div class="gone2"><button class="out">O</button></div>'
        '<div class="sx"><button class="side">S</button></div>'
        '<div class="scr"><div class="pad"></div><button class="below">B</button></div>'
        '<div class="scr2"><button class="before">X</button></div>',
        ".cb { position: relative; } .clip { overflow: hidden; width: 50px; height: 50px; } "
        ".abs { position: absolute; left: 100px; top: 0; width: 30px; height: 30px; } "
        ".half { overflow: hidden; width: 20px; height: 60px; } .cut { display: block; width: 60px; height: 40px; } "
        ".gone2 { position: relative; overflow: hidden; width: 50px; height: 50px; } "
        ".out { position: absolute; left: 80px; top: 0; width: 30px; height: 30px; } "
        ".sx { position: relative; overflow-x: hidden; overflow-y: auto; width: 50px; height: 50px; } "
        ".side { position: absolute; left: 80px; top: 0; width: 30px; height: 30px; } "
        ".scr { overflow: auto; width: 100px; height: 50px; } .pad { height: 300px; } .below { width: 30px; height: 30px; } "
        ".scr2 { position: relative; overflow: auto; width: 100px; height: 50px; } "
        ".before { position: absolute; left: -200px; top: 0; width: 30px; height: 30px; }")
    assert r["controls_under"] == {"44": {"button.abs": 1, "button.below": 1, "button.cut": 1}, "24": {"button.cut": 1}}
    assert (r["control_examples"]["button.cut"]["w"], r["control_examples"]["button.cut"]["h"]) == (20, 40)
    assert r["unreachable"] == {"button.before": 1, "button.out": 1, "button.side": 1}


@BROWSER
def test_a_pseudo_element_grows_only_what_it_can():
    """An 18 px control with an ::after of inset -12 px measures 42, but 18 when the control clips it (its own
    overflow hidden), when the ::after is hidden, when a transform moves it (not seen) and when an ancestor clips the
    grown target back to 18."""
    r = _measured('<button class="hx h0">a</button><button class="hx h1">b</button><button class="hx h2">c</button>'
                  '<button class="hx h3">d</button><div class="tight"><button class="hx h4">e</button></div>',
                  ".hx { position: relative; width: 18px; height: 18px; border: 0; padding: 0; margin: 20px; } "
                  ".hx::after { content: ''; position: absolute; inset: -12px; } .h1 { overflow: hidden; } "
                  ".h2::after { visibility: hidden; } .h3::after { transform: translate(1px, 0); } "
                  ".tight { overflow: hidden; width: 18px; height: 18px; margin: 20px; } .tight .hx { margin: 0; }")
    sizes = {sig: (e["w"], e["h"]) for sig, e in r["control_examples"].items()}
    assert sizes == {"button.h0.hx": (42, 42), "button.h1.hx": (18, 18), "button.h2.hx": (18, 18),
                     "button.h3.hx": (18, 18), "button.h4.hx": (18, 18)}


@BROWSER
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_links_and_buttons_in_a_sentence(engine):
    """In a sentence: a link inside <strong> of a paragraph, a button inside a sentence (inline-block). Not: links
    joined only by separators (" · ", "|"), a link alone in its paragraph (the text half of the rule), a link in a
    flex row with words beside it (blockified: the display half), a button whose only neighbour is a drawing's label."""
    r = _measured('<nav><a href="#1" class="na">About</a> · <a href="#2" class="nb">Privacy</a> | </nav>'
                  '<p>Read <strong><a href="#3" class="st">this note</a></strong> first.</p>'
                  '<p>Go <button class="lk">back</button> to the list.</p>'
                  '<p><a href="#4" class="alone">Alone</a></p>'
                  '<div class="flex"><a href="#5" class="fl">One</a> two words</div>'
                  '<div><button class="bt">x</button><svg width="40" height="20"><text x="0" y="15">label</text></svg></div>',
                  "a, button { font-size: 10px; } .flex { display: flex; gap: 4px; }", engine=engine)
    inline = {c[0]: c[4] for c in r["control_sizes"]}
    assert inline == {"a.na": False, "a.nb": False, "a.st": True, "button.lk": True, "a.alone": False,
                      "a.fl": False, "button.bt": False}


@BROWSER
def test_covered_controls_apart():
    """A control whose centre another element covers is marked covered, with its cover, and still counted (a scroll
    or a closed bubble may uncover it); a cover that takes no clicks (pointer-events none) covers nothing; a
    checkbox's own label is no cover."""
    r = _measured('<button class="under">U</button><div class="lid"></div>'
                  '<button class="pass">P</button><div class="ghost"></div>'
                  '<label class="lb"><input type="checkbox"> label</label>',
                  ".under, .pass { position: absolute; top: 0; width: 30px; height: 30px; } .under { left: 0; } "
                  ".pass { left: 200px; } .lid, .ghost { position: absolute; top: 0; width: 100px; height: 100px; "
                  "background: #fff; } .lid { left: 0; } .ghost { left: 200px; pointer-events: none; } "
                  ".lb { position: absolute; top: 200px; left: 0; }")
    assert r["covered"] == {"button.under": 1} and r["covers"] == {"div.lid": 1} and r["controls"] == 3
    assert r["controls_under"]["44"] == {"button.pass": 1, "button.under": 1, "input[type=checkbox] (by its label)": 1}


@BROWSER
def test_text_in_a_maps_credits_and_scale_apart():
    """Text and controls inside a map's credits (Leaflet's attribution) or scale are marked and counted apart: their
    signatures carry the zone, the text under 12 px is given with and without them; every text keeps its nearest
    named ancestor."""
    r = _measured('<div class="leaflet-control-attribution"><a href="#o">OpenStreetMap</a> contributors</div>'
                  '<div class="leaflet-control-scale"><div class="line">50 m</div></div>'
                  '<section id="side"><p class="small">tiny text</p></section>',
                  ".leaflet-control-attribution, .leaflet-control-scale, .small { font-size: 10px; }")
    assert r["text_under"]["12"] == {"a [credits]": 13, "div.leaflet-control-attribution [credits]": 12,
                                     "div.line [scale]": 4, "p.small": 9}
    assert r["text_chars_under"]["12"] == 38 and r["text_chars_under_outside_credits"]["12"] == 9
    assert r["text_examples"]["p.small"]["within"] == "section#side"
    assert r["inline_links_under"]["24"] == {"a [credits]": 1}
    row = ui_metrics.summarise([{**r, "page": "p", "device": "iphone", "theme": "light",
                                 "seconds": {"load": 1, "steps": 0, "measure": 0}}])["per_device_theme"]["iphone light"]
    assert (row["text_chars_under_12"], row["text_chars_under_12_outside_credits"]) == (38, 9)


@BROWSER
def test_covered_by_the_seen_part():
    """The hit test takes the centre of the part of a control seen now: one below a scroller's fold (its box's centre
    over an element under the scroller) and one half clipped (its box's centre over a neighbour) are not covered; one
    out of the viewport is not tested; a class-less overlay inside a panel is named as itself, not as the panel."""
    r = _measured('<div class="scr"><div class="pad"></div><button class="b1">1</button></div><div class="under"></div>'
                  '<div class="clip"><button class="b2">2</button></div><div class="nb"></div>'
                  '<button class="far">F</button>'
                  '<div class="panel"><button class="pb">P</button><div></div></div>',
                  ".scr { position: absolute; left: 0; top: 0; width: 200px; height: 100px; overflow: auto; } "
                  ".pad { height: 150px; } .b1 { display: block; width: 60px; height: 60px; } "
                  ".under { position: absolute; left: 0; top: 100px; width: 200px; height: 200px; background: #eee; } "
                  ".clip { position: absolute; left: 300px; top: 0; width: 20px; height: 60px; overflow: hidden; } "
                  ".b2 { display: block; width: 60px; height: 60px; } "
                  ".nb { position: absolute; left: 320px; top: 0; width: 80px; height: 60px; background: #ddd; } "
                  ".far { position: absolute; left: 0; top: 2000px; width: 30px; height: 30px; } "
                  ".panel { position: absolute; left: 500px; top: 300px; width: 100px; height: 100px; } "
                  ".pb { width: 40px; height: 40px; } .panel > div { position: absolute; left: 0; top: 0; "
                  "width: 100px; height: 100px; background: #fff; }")
    assert r["covered"] == {"button.pb": 1} and r["covers"] == {"div": 1}
    assert {c[0] for c in r["control_sizes"]} == {"button.b1", "button.b2", "button.far", "button.pb"}


@BROWSER
def test_a_decorating_pseudo_element_grows_nothing():
    """An absolutely positioned ::before inside the control's box (a dot, the 3D view's .v3-opt-dot) is no growth:
    the control is "own", not "with ::before", and not counted in controls_grown."""
    r = _measured('<button class="dot">a</button>',
                  ".dot { position: relative; width: 18px; height: 18px; border: 0; padding: 0; } "
                  ".dot::before { content: ''; position: absolute; inset: 4px; background: red; }")
    assert r["control_examples"]["button.dot"]["how"] == "own" and r["controls_grown"] == 0


PAGE = """<!doctype html><html lang="en"><head><style>
::-webkit-scrollbar { width: 0; height: 0; }
body { margin: 0; font-size: 16px; } button { font-size: 16px; }
#b1 { width: 30px; height: 30px; } .tiny { width: 20px; height: 50px; }
a { display: inline-block; width: 50px; height: 50px; }
.lab { display: inline-block; width: 100px; height: 20px; }
.lab input { position: absolute; width: 1px; height: 1px; opacity: 0; margin: 0; }
.big { display: inline-block; width: 200px; height: 44px; }
.off { width: 10px; height: 10px; } .gone { display: none; }
.hint { position: relative; width: 18px; height: 18px; border: 0; padding: 0; box-sizing: border-box; }
.hint::after { content: ""; position: absolute; inset: -12px; }
.seg { width: 30px; height: 30px; }
.away { position: absolute; left: -5000px; top: 0; width: 20px; height: 20px; }
.tall { height: 2000px; } .low { width: 20px; height: 20px; }
.small { font-size: 10.5px; } .pan { width: 100px; height: 50px; overflow: auto; } .pan div { width: 300px; }
.chips { width: 100px; overflow-x: auto; overflow-y: hidden; white-space: nowrap; }
.card { width: 100px; height: 60px; background: #fff; border: 1px solid #ccc; border-radius: 10px;
  box-shadow: 0 1px 2px #0003; }
.plain { width: 100px; height: 60px; background: #eee; }
.wide { width: 2000px; height: 1px; }
</style></head><body>
<button id="b1">A</button><button class="tiny">B</button><a href="#x">Go</a>
<label class="lab"><input type="checkbox">Tick</label>
<label class="big"><input type="checkbox" class="vis">Show</label>
<button class="off" disabled>x</button><button class="gone">h</button>
<button class="hint">?</button><button class="seg u-on"></button><button class="seg"></button>
<button class="away">Off</button>
<p class="small">Small text here</p><p>Big</p>
<div class="pan"><div>wide</div></div>
<div class="chips">one two three four five six</div>
<div class="card"></div><div class="plain"></div>
<svg width="200" height="100" viewBox="0 0 100 50"><text x="0" y="20" font-size="10" class="lbl">Scaled</text></svg>
<div class="wide"></div><div class="tall"></div><button class="low">Low</button>
</body></html>"""


@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_measure_a_page(engine):
    """Controls by their target: a hidden checkbox and a visible one by their labels, a control grown by its ::after
    (18 px, inset -12 px: 42 px); one control in two states one signature; disabled and hidden ones left out; one at
    -5000 px apart as unreachable, one below the fold counted. Text by its rendered size (SVG text scaled to the
    screen). The document wider than its viewport; elements scrolling sideways by themselves (overflow-y hidden too).
    The rendered containers and grey boxes. With a modal dialog open only its controls count."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _launch(p, engine)
        try:
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.set_content(PAGE)
            r = ui_metrics.measure(page, None)
            page.evaluate("() => { const d = document.createElement('dialog'); d.innerHTML = "
                          "'<button class=\"in\">OK</button>'; document.body.append(d); d.showModal(); }")
            modal = ui_metrics.measure(page, None)
        finally:
            browser.close()
    assert r["controls"] == 9
    assert r["controls_under"] == {
        "44": {"button": 1, "button.hint": 1, "button.low": 1, "button.seg": 2, "button.tiny": 1,
               "input[type=checkbox] (by its label)": 1},
        "24": {"button.low": 1, "button.tiny": 1, "input[type=checkbox] (by its label)": 1}}
    assert r["control_examples"]["button.hint"] == {"w": 42, "h": 42, "text": "?", "how": "with ::after",
                                                     "zone": None, "within": None}
    assert r["control_examples"]["input[type=checkbox] (by its label)"]["w"] == 100
    assert r["controls_grown"] == 1
    assert r["unreachable"] == {"button.away": 1}
    assert r["text_chars"] == 75
    assert r["text_chars_under"] == {"12": 15, "11": 15, "10": 0}
    assert r["text_under"]["12"] == {"p.small": 15}
    assert r["text_examples"]["p.small"] == {"size": 10.5, "text": "Small text here", "zone": None, "within": None}
    assert r["document_over"] == 1200
    assert sorted((s["sig"], s["over"] > 0) for s in r["scrollers"]) == [("div.chips", True), ("div.pan", True)]
    assert [s["over"] for s in r["scrollers"] if s["sig"] == "div.pan"] == [200]
    assert r["containers"] == {"div.card": 1, "div.plain": 1} and r["grey_boxes"] == {"div.card": 1}
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


AXE_REJECTS = "window.axe = {run: () => Promise.reject(new Error('axe broke'))}"
AXE_HANGS = "window.axe = {run: () => new Promise(() => {})}"


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_axe_failure_keeps_the_measurements(monkeypatch):
    """axe-core rejecting or not answering in time: the state's "axe" holds the error, its own measurements stay."""
    from playwright.sync_api import sync_playwright
    monkeypatch.setattr(ui_metrics, "AXE_TIMEOUT_MS", 300)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            results = []
            for source in (AXE_REJECTS, AXE_HANGS):
                page = browser.new_page()
                page.set_content("<!doctype html><html lang='en'><body><button>OK</button><p>Some text</p></body></html>")
                results.append(ui_metrics.measure(page, source))
                page.close()
        finally:
            browser.close()
    rejected, hung = results
    assert "axe broke" in rejected["axe"]["error"] and rejected["controls"] == 1 and rejected["text_chars"] == 11
    assert hung["axe"] == {"error": "axe.run took over 300 ms"} and hung["controls"] == 1


def test_axe_missing(monkeypatch, tmp_path, capsys):
    """Without viewer/node_modules/axe-core/axe.min.js the axe part is left out with one line."""
    monkeypatch.setattr(ui_metrics, "AXE", str(tmp_path / "axe.min.js"))
    assert ui_metrics._axe_source() is None
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and "axe-core not found" in out


class _Site(BaseHTTPRequestHandler):
    """Every path: a small page under a strict CSP (the app's script-src 'self')."""
    def do_GET(self):
        body = (b"<!doctype html><html lang='en'><head><title>t</title></head><body><main><h1>Page</h1>"
                b"<button>OK</button><p>Some text</p></main></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


FAILING = {"one": ("/one", "", None, "visitor"),
           "bad": ("/bad", "", "js:(() => { throw new Error('step broke') })()", "visitor"),
           "slow": ("/slow", "", "wait:false", "visitor"),
           "miss": ("/miss", "", ".nothing-here", "visitor"),
           "slowmiss": ("/slowmiss", "", ["wait:false", ".nothing-here"], "visitor"),
           "two": ("/two", "", None, "visitor")}


def _site_of(url: str) -> dict:
    return {"url": url, "cookies": {}, "run": "r", "share": "s", "line": "l", "also": "a", "border": "b"}


def _chromium(p):
    try:
        return p.chromium.launch()
    except Exception as e:
        pytest.skip(f"Playwright's Chromium not installed: {type(e).__name__}")


@pytest.mark.skipif(not _playwright(), reason="needs Playwright (group ui)")
def test_contexts_and_the_csp_on_a_page(site):
    """On a page under a strict CSP the measuring pass's context (ui_shots.pass_context with bypass_csp) runs an
    injected script; a context made as ui_shots makes it cannot."""
    from playwright.sync_api import sync_playwright
    inject = ("() => { const s = document.createElement('script'); s.textContent = 'window.injected = 1'; "
              "document.head.append(s); return window.injected === 1; }")
    ran = {}
    with sync_playwright() as p:
        browser = _chromium(p)
        try:
            for name, extra in (("ui_shots", {}), ("ui_metrics", {"bypass_csp": True})):
                context = ui_shots.pass_context(browser, p, "desktop", "light", **extra)
                page = context.new_page()
                page.goto(site + "/one")
                ran[name] = page.evaluate(inject)
                context.close()
        finally:
            browser.close()
    assert ran == {"ui_shots": False, "ui_metrics": True}


@pytest.mark.skipif(not _playwright(), reason="needs Playwright (group ui)")
def test_measure_all_goes_on_after_failures(site, monkeypatch):
    """The pass's loop through ui_shots.shoot_all: a page whose step fails and one whose wait timed out are recorded
    as not measured with their reasons and count in no total; axe failing on the others keeps their measurements;
    a page the device does not show (its click finds nothing) and one the run lacks the feature of are recorded as
    left out with their reasons; every record is written to the log as it is made."""
    from playwright.sync_api import sync_playwright
    monkeypatch.setattr(ui_shots, "PAGES", FAILING)
    monkeypatch.setattr(ui_shots, "WAIT_MS", 400)
    log = io.StringIO()
    with sync_playwright() as p:
        _chromium(p).close()
        records = ui_metrics.measure_all(p, _site_of(site), list(FAILING), ["desktop"], ["light"], AXE_REJECTS, log,
                                         dropped={"why": "the run has no square rule"})
    assert [(r["page"], r.get("error", "").split(":")[0], r.get("left_out")) for r in records] == [
        ("why", "", "the run has no square rule"), ("one", "", None), ("bad", "failed", None),
        ("slow", "timed out", None), ("miss", "", "the device does not show .nothing-here"),
        ("slowmiss", "timed out", None), ("two", "", None)]
    assert "step broke" in records[2]["error"] and records[3]["error"] == "timed out: false"
    assert records[5]["error"] == "timed out: false"  # its click then found nothing: still not measured, no left-out
    assert not any("controls" in records[k] for k in (0, 2, 3, 4, 5))
    assert all(r["controls"] == 1 and "axe broke" in r["axe"]["error"] for r in (records[1], records[6]))
    assert [json.loads(line)["page"] for line in log.getvalue().splitlines()] == [
        "why", "one", "bad", "slow", "miss", "slowmiss", "two"]
    s = ui_metrics.summarise(records)
    row = s["per_device_theme"]["desktop light"]
    assert (row["states"], len(row["errors"]), len(row["left_out"]), row["axe_missing"], row["controls"]) ==         (2, 3, 2, 2, 2)
    assert s["left_out"] == {"why | the run has no square rule": ["desktop light"],
                             "miss | the device does not show .nothing-here": ["desktop light"]}
    assert "- why: the run has no square rule (desktop light)" in ui_metrics.pages_markdown(s)


@pytest.mark.skipif(not _playwright(), reason="needs Playwright (group ui)")
def test_run_pages_removes_its_temporary_folder(monkeypatch, tmp_path):
    """The temporary data folder is named as tools/clean_temp.py's ui-shots-* and removed also when setting up the
    site fails."""
    import clean_temp
    made = []

    def broken(data, run_folder=None, fresh=False, times=None):
        made.append(data)
        raise RuntimeError("no site")
    monkeypatch.setattr(ui_shots, "serve", broken)
    monkeypatch.setattr(ui_metrics, "AXE", str(tmp_path / "missing.js"))
    with pytest.raises(RuntimeError, match="no site"):
        ui_metrics.run_pages(str(tmp_path / "out"), "", ["desktop"], False, None)
    assert len(made) == 1 and not os.path.exists(made[0])
    os.makedirs(made[0])  # as a killed run would leave it
    try:
        with os.scandir(os.path.dirname(made[0])) as entries:
            kinds = [clean_temp._kind(e) for e in entries if e.name == os.path.basename(made[0])]
        assert kinds == ["ui-shots"]
    finally:
        os.rmdir(made[0])


def _state(page, device, n44, chars_small):
    return {"page": page, "device": device, "theme": "light", "controls": 3,
            "controls_under": {"44": {"button.x": n44}, "24": {}},
            "control_examples": {"button.x": {"w": 30, "h": 30, "text": "X", "how": "own"}},
            "unreachable": {"button.away": 1}, "controls_grown": 0,
            "text_chars": 100, "text_chars_under": {"12": chars_small, "11": 0, "10": 0},
            "text_under": {"12": {"span.s": chars_small}, "11": {}, "10": {}},
            "text_examples": {"span.s": {"size": 11.5, "text": "s"}}, "document_over": 0,
            "scrollers": [{"sig": "div.row", "over": 10}], "containers": {"div.card": 2}, "grey_boxes": {"div.card": 1},
            "axe": {"violations": [{"id": "color-contrast", "impact": "serious", "tags": ["wcag2aa"], "nodes": 2,
                                    "example": ".m"}], "incomplete": []},
            "seconds": {"load": 3.0, "steps": 1.0, "measure": 0.5}}


def test_summary_deduplicates():
    """The summary: totals per device and theme, signatures counted once per state over all states."""
    s = ui_metrics.summarise([_state("a", "iphone", 2, 10), _state("b", "iphone", 1, 30), _state("a", "desktop", 4, 0)])
    phone = s["per_device_theme"]["iphone light"]
    assert phone["controls_under_44"] == 3 and phone["control_signatures_under_44"] == 1
    assert phone["text_share_under_12"] == 0.2 and phone["axe_violations_nodes"]["serious"] == 4
    assert (phone["controls_unreachable"], phone["grey_boxes"], phone["containers"], phone["axe_missing"]) == (2, 2, 4, 0)
    assert phone["states_with_scrollers"] == ["a", "b"] and phone["states_document_sideways"] == []
    row = s["lists"]["controls_under_44_phones"][0]
    assert (row["signature"], row["states"], row["count"], row["pages"]) == ("button.x", 2, 3, 2)
    assert s["lists"]["controls_under_44_desktop"][0]["count"] == 4
    assert s["lists"]["axe"][0]["states"] == 3 and s["seconds_total"] == 13.5
    assert s["lists"]["grey_boxes"][0]["count"] == 3 and s["lists"]["unreachable"][0]["states"] == 3
    assert "| iphone light | 2 |" in ui_metrics.pages_markdown(s)


def _sized(page="a", device="iphone"):
    """A record with kept sizes: three controls (42 px, 30 × 20 px, a 60 × 15 px link in a sentence), three texts."""
    record = {"page": page, "device": device, "theme": "light", "controls": 3,
              "control_sizes": [["button.x", 42, 42, "own", False, "X"], ["button.y", 30, 20, "own", False, "Y"],
                                ["a", 60, 15, "own", True, "L"]],
              "text_sizes": [["p", 11.5, 10, "t"], ["span", 10.5, 4, "s"], ["h1", 20, 5, "h"]], "text_chars": 19,
              "unreachable": {}, "document_over": 0, "scrollers": [], "containers": {}, "grey_boxes": {},
              "seconds": {"load": 1.0, "steps": 0.0, "measure": 0.1}}
    return {**record, **ui_metrics.recut(record)}


def test_other_bounds_from_a_kept_log(tmp_path):
    """Every size is kept, so other bounds are answered from the log: --summarise --controls 40,24 --text 11 writes
    pages-c40-24-t11.json beside the default summary."""
    record = _sized()
    assert record["controls_under"]["44"] == {"button.x": 1, "button.y": 1}
    assert record["text_chars_under"] == {"12": 14, "11": 4, "10": 0}
    (tmp_path / "pages-states.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    ui_metrics.main(["pages", "--out", str(tmp_path), "--summarise", "--controls", "40,24", "--text", "11"])
    row = json.loads((tmp_path / "pages-c40-24-t11.json").read_text(encoding="utf-8"))["per_device_theme"]["iphone light"]
    assert (row["controls_under_40"], row["controls_under_24"], row["text_chars_under_11"]) == (1, 1, 4)
    assert "Text under 11 px" in (tmp_path / "pages-c40-24-t11.md").read_text(encoding="utf-8")


def test_links_in_a_sentence_apart():
    """A link inside a sentence (WCAG 2.5.8 exempts it) is counted apart from the other small controls; the count of
    before (with it) stays in the summary beside."""
    record = _sized()
    assert record["inline_links_under"] == {"44": {"a": 1}, "24": {"a": 1}}
    assert record["control_examples"]["a (inline link)"]["h"] == 15
    row = ui_metrics.summarise([record])["per_device_theme"]["iphone light"]
    assert (row["controls_under_24"], row["inline_links_under_24"], row["controls_under_24_with_inline"]) == (1, 1, 2)
    s = ui_metrics.summarise([record])
    assert s["lists"]["inline_links_under_24_phones"][0]["signature"] == "a"
    assert "Links in a sentence under 24 px" in ui_metrics.pages_markdown(s)


def test_families_by_name_prefix():
    """The summary's page families go by the prefix of a page's name: c-new-coverage is the app's, map-layers a run's
    map's, not the coverage page's or the layer explorer's."""
    names = ["page-coverage", "page-coverage-pl", "c-layer-cell", "c-new-coverage", "map-layers", "c-home",
             "page-about", "view3d"]
    s = ui_metrics.summarise([_state(n, "iphone", 1, 0) for n in names])
    families = s["per_device_theme"]["iphone light"]["families"]
    assert {k: v["states"] for k, v in families.items()} == {
        "coverage page": 2, "layer explorer": 1, "3D view": 1, "run's map": 1, "other pages": 1, "the app": 2}
    assert families["the app"]["controls"] == 6 and families["the app"]["controls_under_44"] == 2
    assert "| iphone light | coverage page | 2 |" in ui_metrics.pages_markdown(s)


def test_headline_counts_with_failures():
    """The headline: a state whose measuring failed (it keeps its seconds) is failed, not also measured; a state left
    out is neither."""
    failed = {"page": "b", "device": "iphone", "theme": "light", "error": "failed: E",
              "seconds": {"load": 1.0, "steps": 0.0, "measure": 0.2}}
    left = {"page": "c", "device": "iphone", "theme": "light", "left_out": "the device does not show .x"}
    s = ui_metrics.summarise([_state("a", "iphone", 1, 0), failed, left])
    assert (s["states"], s["states_failed"], s["states_left_out"]) == (1, 1, 1)
    assert "1 states measured, 1 failed, 1 left out" in ui_metrics.pages_markdown(s)


def test_exit_code(tmp_path):
    """0 when every state was measured or left out and every pass finished; 1 when a state was not measured or a pass
    did not finish (pages-run.json)."""
    ok = [_state("a", "iphone", 1, 0), {"page": "c", "device": "iphone", "theme": "light", "left_out": "x"}]
    (tmp_path / "pages-states.jsonl").write_text("".join(json.dumps(r) + "
" for r in ok), encoding="utf-8")
    assert ui_metrics.main(["pages", "--out", str(tmp_path), "--summarise"]) == 0
    (tmp_path / "pages-run.json").write_text(json.dumps({"passes": [{"device": "iphone", "theme": "light",
                                                                     "complete": False}]}), encoding="utf-8")
    assert ui_metrics.main(["pages", "--out", str(tmp_path), "--summarise"]) == 1


def test_summarise_again_from_the_log(tmp_path):
    """--summarise rebuilds pages.json and pages.md from pages-states.jsonl alone."""
    records = [_state("a", "iphone", 2, 10), {"page": "bad", "device": "iphone", "theme": "light", "error": "E"}]
    (tmp_path / "pages-states.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    assert ui_metrics.main(["pages", "--out", str(tmp_path), "--summarise"]) == 1  # a state not measured
    expected = json.loads(json.dumps(ui_metrics.summarise(records)))
    assert json.loads((tmp_path / "pages.json").read_text(encoding="utf-8")) == expected
    assert "1 states measured, 1 failed" in (tmp_path / "pages.md").read_text(encoding="utf-8")
