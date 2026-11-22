"""One control family (step 3d, group G3; docs/DESIGN.md rows 96 to 99): the kit's text action, close button, badge,
checkbox, row, collapse tab, the bin and the stop icons, and the free screens on them (the user's picks of
2026-11-22 from the picture sheets: Q7 to Q11 a, C8 "No edge, one look", C6 "24 px, every page").

The sources are read (viewer/src without line volume's round 6, today's result page and the kit's demo pages); one
check draws the checkbox's ring in Playwright's WebKit, which drew none on a native checkbox before (an outline it
draws, a shadow it does not)."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_viewer import _css_rules  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "viewer", "src")
# not free (round 6's and today's result page's files, the shore's and coarser terrain's controls) or the kit's demos
NOT_FREE = ("result/", "Profile.tsx", "profile.css", "profilechart.ts", "PlaceMap.ts", "layersControl.ts",
            "coarserLayer.ts", "shoreLayer.ts", "ui/Gallery.tsx", "ui/sidepanel.css")


def _read(rel: str) -> str:
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return f.read()


def _css(rel: str) -> str:
    return re.sub(r"/\*.*?\*/", "", _read(rel), flags=re.S)


def _free(exts: tuple) -> dict:
    """{path under viewer/src: text} of the free source files with these endings."""
    out = {}
    for root, _, files in os.walk(SRC):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), SRC).replace(os.sep, "/")
            if name.endswith(exts) and not any(rel.startswith(n) or rel.endswith(n) for n in NOT_FREE):
                out[rel] = _read(rel)
    return out


def _rule(css: str, selector: str, media: str = "") -> str:
    """The body of the rule with exactly this selector (inside the @-block whose prelude holds `media`, or none)."""
    found = [b for s, b, at in _css_rules(css) if s == selector and (media in at if media else not at)]
    assert len(found) == 1, (selector, media, len(found))
    return found[0]


def test_text_action_is_one_kit_class():
    """Q7 a: the kit's text action (.u-link) is accent text at a label's weight with no underline at rest, underlined
    under the mouse and the keyboard's focus, a 24 px target (44 px on a touch screen), and none of its own inside a
    sentence (.u-inline); the free screens' text actions take it and keep no look of their own (c-link and s-link are
    gone, n-intro-link, cov-link, s-reset are hooks of tests and ui_shots only)."""
    ui = _css("ui/ui.css")
    rest = _rule(ui, ".ui .u-link")
    assert "color: var(--accent)" in rest and "text-decoration: none" in rest and "min-height: 24px" in rest
    assert "text-decoration: underline" in _rule(ui, ".ui .u-link:hover, .ui .u-link:focus-visible")
    assert "min-height: 44px" in _rule(ui, ".ui .u-link", "pointer: coarse")
    assert "min-height: 0" in _rule(ui, ".ui .u-link.u-inline")
    code = _free((".tsx", ".ts"))
    for old in ("c-link", "s-link"):
        assert not [p for p, t in code.items() if re.search(r"""["'` ]%s["'` ]""" % old, t)], old
    hooks = {"n-intro-link": "ui/Intro.tsx", "cov-link": "coverage/page/AreaList.tsx", "s-reset": "search/SearchPanel.tsx"}
    for hook, where in hooks.items():
        assert re.search(r"u-link[^\"]*%s" % hook, code[where]), hook
    for rel, text in _free((".css",)).items():  # no own colour or underline on a text action's hook
        for selector, body, _ in _css_rules(re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
            if re.search(r"\.(n-intro-link|cov-link|cov-name-link|s-reset|c-link|s-link)\b", selector):
                assert not re.search(r"\b(color|text-decoration|background)\s*:", body), (rel, selector, body)


def test_one_close_button():
    """Q9 a: one close of a box in the free files, the kit's plain icon button (.u-ib.u-x) of 24 px, 44 px on a touch
    screen: the coverage card's, the 3D view's notice and "About this view"; their own looks are gone."""
    ui = _css("ui/ui.css")
    x = _rule(ui, ".ui .u-ib.u-x")
    assert "width: 24px" in x and "height: 24px" in x and "background: transparent" in x
    assert "width: 44px" in _rule(ui, ".ui .u-ib.u-x", "pointer: coarse")
    assert 'class="u-ib u-x cov-x"' in _read("coverage/page/card.tsx")
    assert '"u-ib u-x v3-activity-dismiss"' in _read("view3d/chrome.ts")
    assert '"u-ib u-x v3-infobox-close"' in _read("view3d/info.ts")
    for rel, sel in (("coverage/page/page.css", "cov-x"), ("view3d/view3d.css", "v3-activity-dismiss"),
                     ("view3d/view3d.css", "v3-infobox-close")):
        assert not [s for s, _, _ in _css_rules(_css(rel)) if sel in s], (rel, sel)


def test_close_icon_means_close_only():
    """Q10 a: Delete… and Remove take the kit's bin, Cancel the search the stop square; the close mark stands for no
    menu item (Home's card menu, the Favourites page's folder and line menus)."""
    icons = _read("ui/icons.tsx")
    assert re.search(r"^  bin: '", icons, re.M) and re.search(r"^  stop: '<rect ", icons, re.M)
    for rel in ("app/c/Home.tsx", "app/c/FavouritesPage.tsx"):
        items = re.findall(r'<Icon name="(\w+)" />\{t\("([\w.]+)"\)\}', _read(rel))
        assert items, rel
        want = {"ui.common.delete_ask": "bin", "ui.common.remove": "bin", "ui.card.remove": "bin", "ui.card.cancel": "stop"}
        for icon, key in items:
            assert icon != "close", (rel, key)
            if key in want:
                assert icon == want[key], (rel, key, icon)


def test_badges_neutral_but_a_count():
    """Q8 a: the kit's badge is a neutral pill; a user's state its soft fill (.u-ok, .u-warn, .u-bad); the accent only
    for a count on the bottom bar; no badge of the free screens is the accent's fill and none says u-n any more."""
    ui = _css("ui/ui.css")
    badge = _rule(ui, ".ui .u-badge")
    assert "background: var(--surface-2)" in badge and "color: var(--ink-2)" in badge
    for tone in ("ok", "warn", "bad"):
        assert f"background: var(--{tone}-soft); color: var(--{tone})" in _rule(ui, f".ui .u-badge.u-{tone}")
    assert "background: var(--accent)" in _rule(ui, ".ui .u-bnav-item .u-badge")
    for rel, text in _free((".css",)).items():
        for selector, body, _ in _css_rules(re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
            if "u-badge" in selector or "c-user-" in selector:
                if selector != ".ui .u-bnav-item .u-badge":
                    assert "var(--accent)" not in body and not re.search(r"background:\s*var\(--(ok|warn|bad)\)", body), (rel, selector)
    assert not [p for p, t in _free((".tsx", ".ts")).items() if re.search(r"u-badge u-n\b", t)]
    admin = _read("app/c/AdminC.tsx")
    assert '{approved: " u-ok", pending: " u-warn", blocked: " u-bad"}' in admin


def test_one_checkbox():
    """Q11 a and B5: every checkbox of the free screens is the kit's (.u-check: 20 px, the accent, its keyboard ring
    an outline 2 px off the box, which WebKit draws); the coverage box's drawn tick takes the same look (the accent's
    fill and the kit's check mark)."""
    ui = _css("ui/ui.css")
    box = _rule(ui, ".ui .u-check")
    assert "width: 20px" in box and "height: 20px" in box and "accent-color: var(--accent)" in box
    ring = _rule(ui, ".ui .u-check:focus-visible")
    assert "outline: 2px solid var(--accent)" in ring and "outline-offset: 2px" in ring and "box-shadow: none" in ring
    for rel, text in _free((".tsx",)).items():
        for tag in re.findall(r'<input\b[^>]*type="checkbox"[^>]*>', text):
            assert 'class="u-check' in tag, (rel, tag)
    tick = _css("app/coverageLayer.css")
    assert "M5 12l5 5 9-10" in tick  # the kit's check icon (ui/icons.tsx ICONS.check) drawn in the ticked box
    assert "inset 0 0 0 2px" not in tick  # the old gap inside the edge


def test_collapse_tab_one_look():
    """C8 "No edge, one look": the kit's collapse tab is raised (the surface and --shadow, no edge), 24 px wide with
    8 px corners, its keyboard ring beside its shadow (today's result page showed none: the tab's own shadow won); the
    highline layer's copy is gone."""
    ui = _css("ui/ui.css")
    tab = _rule(ui, ".ui .u-split-tab")
    for part in ("width: 24px", "border-radius: var(--r-2)", "border: 1px solid transparent", "box-shadow: var(--shadow)"):
        assert part in tab, part
    assert "box-shadow: var(--shadow), var(--focus)" in _rule(ui, ".ui .u-split-tab:focus-visible")
    assert not [s for s, _, _ in _css_rules(_css("app/c/c.css")) if "u-split-tab" in s]


def test_rows_and_toggles_are_the_kits():
    """C1: the free screens' own button classes are only marks and rows named in DESIGN (row 96); the menus', the tree's,
    the favourites', the rigs', More settings' and a chart's name are the kit's row (.u-item), a favourite's star and
    the tree's fold the kit's icon button, the account button the kit's button."""
    code = _free((".tsx", ".ts"))
    kept = {"c-layer-bar", "v3-opt-dot", "v3-other", "v3-opt-sort", "s-card", "s-sum", "c-rail", "n-coverage-btn", "cov-row"}
    kit = {"u-btn", "u-ib", "u-chip", "u-chip-x", "u-hint", "u-split-tab", "u-bnav-item", "u-sheet-handle",
           "u-credits-toggle", "u-link", "u-item"}
    own = set()
    for rel, text in code.items():
        for cls in re.findall(r'<button\b[^>]*?class="([^"]*)"', text, flags=re.S):
            names = cls.split()
            if names and not kit & set(names):
                own.add(names[0])
        for cls in re.findall(r'el\(\s*"button"\s*,\s*"([^"]*)"', text):
            names = cls.split()
            if names and not kit & set(names):
                own.add(names[0])
    assert own <= kept | {"u-on", "u-plain", ""}, sorted(own - kept)
    for rel, needle in (("app/c/Home.tsx", 'class="u-item c-menu-item"'), ("app/c/FavouritesPage.tsx", 'class="u-item c-tree-name"'),
                        ("app/c/FavouritesPage.tsx", 'class="u-ib u-plain u-round c-fav-star"'),
                        ("app/c/FavouritesPage.tsx", 'class="u-ib u-plain c-tree-fold"'),
                        ("search/BasicPane.tsx", 'class="u-item s-rig-item"'), ("search/SearchPanel.tsx", 'class="u-item s-more-head"'),
                        ("app/c/LayerHistograms.tsx", 'class="u-item c-layer-hist-name"'), ("app/c/Account.tsx", "`u-btn c-account-btn")):
        assert needle in code[rel], (rel, needle)


def test_no_characters_as_icons_in_free_css():
    """C9 (R9): no CSS of the free screens draws a character as an icon (the credits' ▸/▾ are the icon set's arrow,
    turned while open); C10: the rig window's "More" shows the icon set's arrow, not the browser's triangle."""
    for rel, text in _free((".css",)).items():
        for selector, body, _ in _css_rules(re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
            for content in re.findall(r"(?<![-\w])content:\s*([^;]+)", body):
                assert not re.search(r""""[^"]+"|'[^']+'""", content), (rel, selector, content)  # no drawn text
    assert "u-credits-mark" in _read("layers.ts") and "ICONS.next" in _read("layers.ts")
    ui = _css("ui/ui.css")
    assert "rotate(90deg)" in _rule(ui, '.ui .u-credits-toggle[aria-expanded="true"] .u-credits-mark')
    search = _css("search/search.css")
    assert "list-style: none" in _rule(search, ".ui .s-rig-more > summary")
    assert "display: none" in _rule(search, ".ui .s-rig-more > summary::-webkit-details-marker")
    assert '<Icon name="next" class="s-rig-more-mark" />' in _read("search/BasicPane.tsx")


def test_page_titles_a_step_above_their_sections():
    """C6 "24 px, every page": every page's title (an h1 of the kit's heading: Admin, Home's searches, the map pages')
    is --fs-6, one step above its sections' titles (--fs-5); Admin's "Open" has its arrow after the word."""
    assert "font-size: var(--fs-6)" in _rule(_css("ui/ui.css"), ".ui .u-h.u-title")
    for rel, text in _free((".tsx",)).items():
        for tag in re.findall(r"<h1 [^>]*>", text):
            if 'class="u-h' in tag:
                assert "u-title" in tag, (rel, tag)
    assert 'kind="ghost" iconRight="next" href={runHash(r.run_id)}' in _read("app/c/AdminC.tsx")


# ---- in a browser ---------------------------------------------------------------------------------------------------

from test_keyboard_app import _open, site, wsite  # noqa: E402,F401  (the keyboard tests' server, Edge and WebKit)
from test_web import EDGE, _playwright  # noqa: E402


@pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright (group ui)")
def test_webkit_draws_the_checkbox_ring(wsite):
    """Q11 a (docs/known-bugs.md, G1's "WebKit draws no focus on a native checkbox"): in WebKit a Tab onto the search
    form's checkbox draws the accent's ring around the box: pixels of the accent in the band 2 to 4 px outside it,
    none before the focus."""
    page = _open(wsite, "more", {"viewport": {"width": 1024, "height": 768}})
    box = page.locator(".s-check").first
    box.scroll_into_view_if_needed()
    page.evaluate("() => { const b = document.querySelector('.s-check'); b.focus(); }")
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement === document.querySelector('.s-check')")
    accent = page.evaluate("""() => { const c = document.createElement('i'); c.style.color = 'var(--accent)';
      document.querySelector('.ui').append(c); const v = getComputedStyle(c).color; c.remove(); return v; }""")
    want = [int(v) for v in re.findall(r"\d+", accent)[:3]]

    def ring_pixels() -> int:
        from io import BytesIO

        from PIL import Image
        r = box.bounding_box()
        shot = Image.open(BytesIO(page.screenshot(clip={"x": r["x"] - 6, "y": r["y"] - 6, "width": r["width"] + 12,
                                                        "height": r["height"] + 12}))).convert("RGB")
        w, h = shot.size
        band = [(x, y) for x in range(w) for y in range(h)
                if not (4 <= x < w - 4 and 4 <= y < h - 4) and (2 <= x < w - 2 and 2 <= y < h - 2)]
        return sum(1 for x, y in band if all(abs(a - b) <= 40 for a, b in zip(shot.getpixel((x, y)), want)))

    focused = ring_pixels()
    page.evaluate("() => document.activeElement.blur()")
    assert focused >= 40 and ring_pixels() == 0, (focused, accent)
    page.context.close()
