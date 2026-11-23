"""Step 3d, group G6: the result view (line volume's round 6) and the place map on the kit's controls, layers and
keyboard (docs/DESIGN.md rows 131 to 136): the view's closes, text actions and checkboxes the kit's; the profile's
texts without characters for words; the maps' layers box a disclosure for the keyboard, its rows the kit's boxes;
the map's own ring inside its box; the layers named in tokens.css at their numbers."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "viewer", "src")
# The result view's own files and the parts of today's page's files it renders (borrowed: step 3d G6, Q1 a)
VIEW = ["result/view/" + n for n in ("SpotList.tsx", "SpotDetails.tsx", "SpotActions.tsx", "SpotChooser.tsx", "SpotSummary.tsx",
                                     "MapBar.tsx", "ViewFilters.tsx", "Hint.tsx", "FanPanel.tsx", "RunActions.tsx",
                                     "ProfileDock.tsx", "ProfileCard.tsx", "FavouritePicker.tsx", "ResultSummary.tsx",
                                     "FilterBar.tsx", "LineDetails.tsx")] + ["Profile.tsx"]


def _code(rel: str) -> str:
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import ui_metrics
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return ui_metrics.strip_comments(f.read())


def test_view_closes_links_and_checkboxes_are_the_kits():
    """In the view's files (and the parts of today's it renders) every close is the kit's (`CloseButton` or
    `u-ib u-x`), every text action `u-link` (`u-inline` inside a sentence), every checkbox of the view `u-check`: no
    `r-note-x` button of its own look, no "×" drawn as text, no `r-link` without the kit's class (DESIGN.md row 131)."""
    for rel in VIEW:
        code = _code(rel)
        for m in re.finditer(r"<button\b[^>]*class=(\"[^\"]*\"|\{[^}]*\})", code):
            cls = m.group(1)
            assert "r-note-x" not in cls or "u-x" in cls or "r-fold" in cls, (rel, "a close of its own look", cls)
            assert "r-link" not in cls or "u-link" in cls, (rel, "a text action of its own look", cls)
        assert not re.search(r">\s*×\s*<", code), (rel, "a × drawn as text")
    for rel in ("result/view/RunActions.tsx", "result/view/ResultSummary.tsx", "Profile.tsx"):
        for box in re.findall(r"<input type=\"checkbox\"[^>]*>", _code(rel)):
            assert "u-check" in box, (rel, box)
    more = _code("result/view/FilterBar.tsx").split("export function MoreFilters", 1)[1]
    assert all("u-check" in box for box in re.findall(r"<input type=\"checkbox\"[^>]*>", more))


def test_profile_and_shares_write_words_not_characters():
    """The profile's readout, title and facts and the coarser terrain's shares join their values with words and "; ",
    never " · ", "→" or "Δh" (R9; the user's answers of 2026-11-23); the 1:1 scale keeps "×1.6" (kept as the 3D view's
    "×1"), in the catalogue only."""
    profile = _code("Profile.tsx")
    for sign in ("·", "→", "Δ", "×"):
        assert sign not in profile, sign
    assert "join(\"; \")" in profile
    assert '.join("; ")' in _code("coarser.ts") and "·" not in _code("coarser.ts")
    import json
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        en = json.load(f)
    assert en["ui.profile.scale_true"] == "1:1 scale (now vertical ×{{f}})"
    assert en["ui.profile.fact_ends"] == "A1 {{a1}} m, A2 {{a2}} m" and "difference" not in en["ui.profile.fact_ends"]
    assert "height difference" in en["ui.profile.title"]


@pytest.mark.skipif(not os.path.isdir(os.path.join(REPO, "viewer", "node_modules")), reason="needs npm install in viewer/")
def test_readout_marks_water_and_gaps_without_terrain(tmp_path):
    """The profile's readout (Profile.tsx readText) writes "(water)" and "(filled gap)" where the terrain has no value
    too, after the distance (as before G6: the code review's finding 2), and after the terrain's part where it has one."""
    import json
    import subprocess
    entry, bundle = tmp_path / "entry.ts", tmp_path / "profile.cjs"
    entry.write_text(f'export {{ readText }} from "{SRC.replace(os.sep, "/")}/Profile";\n', encoding="utf-8")
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], bundle: true, "
                                  "format: 'cjs', platform: 'node', loader: {'.css': 'empty', '.png': 'dataurl', '.svg': 'text', "
                                  f"'.woff2': 'empty'}}, outfile: {json.dumps(str(bundle))}}})"],
                   cwd=os.path.join(REPO, "viewer"), check=True)
    cases = [{"at": "12", "water": True}, {"at": "12", "gap": True, "limit": "310.0"},
             {"at": "12", "z": "300.0", "water": True, "gap": True}, {"at": "12", "z": "300.0"}]
    script = tmp_path / "readout.cjs"
    script.write_text(f"const m = require({json.dumps(str(bundle))});\n"
                      f"console.log(JSON.stringify({json.dumps(cases)}.map((v) => m.readText(v))));\n", encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == ["12 m from A1 (water)", "12 m from A1 (filled gap); safety limit: 310.0 m",
                                       "12 m from A1; terrain: 300.0 m (water) (filled gap)", "12 m from A1; terrain: 300.0 m"]


def test_level_switch_is_a_radio_group():
    """The map's level switch: one Tab stop and the arrows (ui/radios.ts), its buttons radios (DESIGN.md row 82)."""
    code = _code("result/view/MapBar.tsx")
    assert 'role="radiogroup"' in code and "onKeyDown={radioKeys}" in code and 'role="radio"' in code
    assert "aria-pressed={pressed === k}" not in code


def test_layers_named_at_their_numbers():
    """tokens.css names the layers G6 put on names at today's numbers (no stacking changed), and no CSS of the view
    or the profile writes a raw z-index (but `auto`)."""
    with open(os.path.join(SRC, "ui", "tokens.css"), encoding="utf-8") as f:
        tokens = f.read()
    for name, value in (("--z-below", "-1"), ("--z-frame-bar", "6"), ("--z-frame-sheet", "7"), ("--z-phone-bar", "8"),
                        ("--z-notice", "2000"), ("--z-map-box", "800"), ("--z-map-box-2", "810"), ("--z-map-top", "1100")):
        assert re.search(rf"{name}: {re.escape(value)};", tokens), name
    for rel in ("result/view/mapbar.css", "result/view/view.css", "profile.css"):
        with open(os.path.join(SRC, rel), encoding="utf-8") as f:
            raw = [v for v in re.findall(r"z-index:\s*([^;}]+)", f.read()) if not v.strip().startswith(("var(--z-", "auto"))]
        assert raw == [], (rel, raw)


# ---- in the browser: the place map's layers box and ring, the layers' computed values ------------------------------

from test_keyboard_app import DESKTOP, FRAMES, PHONE_KEYS, TOUCH, _open, site  # noqa: E402,F401
from test_shell_c_view_map import _tap  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

browser_test = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                  reason="needs Microsoft Edge and Playwright (group ui)")
BOX = ".leaflet-control-layers"
STATE = """() => { const box = document.querySelector('.leaflet-control-layers'), a = document.activeElement;
  return {open: box.classList.contains('leaflet-control-layers-expanded'), on: a.className || a.tagName,
          checked: !!(a.matches && a.matches('input:checked')), expanded: box.querySelector('.leaflet-control-layers-toggle').getAttribute('aria-expanded'),
          base: [...box.querySelectorAll('.leaflet-control-layers-base input')].findIndex((i) => i.checked)}; }"""


@browser_test
def test_layers_box_is_a_disclosure(site):
    """The place map's layers box (layersControl.ts, also the view's): Enter on its button opens it with the focus on
    the chosen row and `aria-expanded` true; Escape closes it with the focus back on the button; its rows are the kit's
    20 px boxes (.u-radio, .u-check: Q4 a); on a touch screen a second tap where the button stood within the guard does
    not switch the base map (A6)."""
    page = _open(site, "search", DESKTOP)
    try:
        page.focus(f"{BOX} .leaflet-control-layers-toggle")
        page.keyboard.press("Enter")
        page.evaluate(FRAMES)
        opened = page.evaluate(STATE)
        assert opened["open"] and opened["checked"] and opened["expanded"] == "true", opened
        sizes = page.evaluate("""() => [...document.querySelectorAll('.leaflet-control-layers-selector')].map((i) =>
          [i.type, i.classList.contains(i.type === 'radio' ? 'u-radio' : 'u-check'), i.getBoundingClientRect().width])""")
        assert sizes and all(kit and abs(w - 20) < 0.5 for _, kit, w in sizes), sizes
        page.keyboard.press("Escape")
        page.evaluate(FRAMES)
        closed = page.evaluate(STATE)
        assert not closed["open"] and "leaflet-control-layers-toggle" in closed["on"] and closed["expanded"] == "false", closed
    finally:
        page.context.close()
    page = _open(site, "search", {**PHONE_KEYS, **TOUCH})
    try:
        r = page.evaluate(f"() => {{ const b = document.querySelector('{BOX} .leaflet-control-layers-toggle').getBoundingClientRect();"
                          " return [b.left + b.width / 2, b.top + b.height / 2]; }")
        before = page.evaluate(STATE)["base"]
        # every click inside the box, and whether the box kept it from its row (the guard: Leaflet's preventDefault)
        page.evaluate("() => { window.G6_CLICKS = []; document.addEventListener('click', (e) => { if (e.target.closest?.('.leaflet-control-layers-list'))"
                      " G6_CLICKS.push(e.defaultPrevented); }); }")
        page.touchscreen.tap(*r)
        page.wait_for_timeout(150)
        page.touchscreen.tap(*r)  # where the button stood: the box's row now lies there
        page.evaluate(FRAMES)
        after = page.evaluate(STATE)
        clicks = page.evaluate("() => G6_CLICKS")
        assert after["open"] and after["base"] == before and clicks and all(clicks), (before, after, clicks)
    finally:
        page.context.close()


@browser_test
def test_map_ring_inside_its_box_and_layers_computed(site):
    """The place map's own keyboard ring (Leaflet's box takes the focus) lies inside its box: an outline 2 px in,
    no shadow outside, and none after a press (layersControl.ts pressMarks: A7); the layers' names compute to
    today's numbers in the app's CSS (Q5 a)."""
    page = _open(site, "search", DESKTOP)
    try:
        page.keyboard.press("Tab")  # a keyboard's focus: the next focus shows its ring (:focus-visible)
        page.evaluate("() => document.querySelector('.c-placemap').focus()")
        ring = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.c-placemap'));"
                             " return [s.outlineStyle, s.outlineWidth, s.outlineOffset, s.boxShadow]; }")
        assert ring == ["solid", "2px", "-2px", "none"], ring
        # a press focuses Leaflet's box too, and the browsers mark it :focus-visible: no ring after a press
        box = page.evaluate("() => { const r = document.querySelector('.c-placemap').getBoundingClientRect();"
                            " return [r.left + r.width / 2, r.top + r.height / 2]; }")
        page.mouse.click(*box)
        page.evaluate(FRAMES)
        pressed = page.evaluate("() => { const m = document.querySelector('.c-placemap'), s = getComputedStyle(m);"
                                " return [document.activeElement === m, s.outlineStyle, s.boxShadow]; }")
        assert pressed[1:] == ["none", "none"], pressed
        marked = page.evaluate("() => document.querySelector('.c-placemap').classList.contains('u-map-pressed')")
        page.keyboard.press("Shift")  # a key: the mark goes, the ring comes back while the box keeps the focus
        back = page.evaluate("() => [document.querySelector('.c-placemap').classList.contains('u-map-pressed'),"
                             " getComputedStyle(document.querySelector('.c-placemap')).outlineStyle]")
        assert pressed[0] and marked and back == [False, "solid" if page.evaluate("() => document.querySelector('.c-placemap').matches(':focus-visible')") else "none"], (pressed, marked, back)
        z = page.evaluate("""() => { const root = document.createElement('div'); root.className = 'ui';
          root.innerHTML = '<div class="v-result c-result-phone"><div class="c-phone-top"></div>'
            + '<div class="c-col-map"><div class="v-map"><div class="v-switch"></div><div class="v-toast"></div><div class="v-over"></div></div></div>'
            + '<div class="u-sheet"></div></div><div class="vl-sec"><div class="vl-cols"></div></div>';
          document.body.append(root);
          const z = (s) => getComputedStyle(root.querySelector(s)).zIndex;
          const out = {bar: z('.c-phone-top'), sheet: z('.c-result-phone .u-sheet'), box: z('.v-switch'),
                       toast: z('.v-toast'), over: z('.v-over'), heads: z('.vl-cols'),
                       ground: getComputedStyle(root.querySelector('.vl-cols'), '::before').zIndex};
          root.remove(); return out; }""")
        assert z == {"bar": "8", "sheet": "7", "box": "800", "toast": "810", "over": "1100", "heads": "1",
                     "ground": "-1"}, z
    finally:
        page.context.close()


# ---- in the browser: the result view (a run with a source's credits, and a second run) -----------------------------

from test_shell_c import BIG, add_credits, copy_clip, stub_page  # noqa: E402
from test_shell_c_view_map import (DESKTOP as VIEW_DESKTOP, OLD, SMALL_PHONE, WAIT,  # noqa: E402
                                   _open as _view, _state, view_clip)  # noqa: F401
from test_view_frame import HELP  # noqa: E402
from test_web import _server  # noqa: E402

LEVELS = ["auto", "area", "spots", "lines"]


@pytest.fixture
def kit_site(tmp_path, view_clip):
    """The clip's run with a source's data credits (BIG) and the same run again (OLD), served by the app."""
    folder = tmp_path / "data"
    copy_clip(view_clip, folder, BIG, "Clip")
    copy_clip(view_clip, folder, OLD, "Clip again")
    add_credits(folder, BIG)
    page_path = stub_page(folder, "kittest")
    with _server(folder) as port:
        yield f"http://127.0.0.1:{port}/{page_path}?ui=c"


# The map's bottom corners: each one's class, its raise (style.bottom) and whether it holds the scale or the credits
CORNERS = """() => [...document.querySelectorAll('.v-map .leaflet-bottom')].map((c) => [c.className, c.style.bottom,
  !!c.querySelector('.leaflet-control-scale, .leaflet-control-attribution')])"""


@browser_test
def test_map_corners_raised_where_their_controls_stand(site, kit_site):
    """On a phone the frame puts the scale in the credits' corner (over the credits); the corners raised above the
    sheet are those that hold the scale or the credits, read from where the frame put them (corners.ts cornersOf,
    the user's Q18 a), never a corner taken for the scale (the code review's finding 5: a fixed left corner passed
    every test), at the sheet's low stop and at half."""
    browser = site[1]  # the module's browser (test_keyboard_app's site)
    got = []
    page = _view(browser, kit_site + f"#run={BIG}", SMALL_PHONE, script=HELP)
    try:
        page.wait_for_function("() => F.snap() === 'peek' && F.rest()", timeout=WAIT)
        page.evaluate("() => T.frames()")
        got.append(page.evaluate(CORNERS))
        page.focus(".u-sheet-handle")
        page.keyboard.press("ArrowUp")
        page.wait_for_function("() => F.snap() === 'half' && F.rest()", timeout=WAIT)
        page.evaluate("() => T.frames()")
        got.append(page.evaluate(CORNERS))
        scale = page.evaluate("() => document.querySelector('.v-map .leaflet-control-scale')?.parentElement?.className")
        assert page.errors == []
    finally:
        page.context.close()
    print("the map's corners:", scale, got)
    assert scale == "leaflet-bottom leaflet-right", scale  # the phone's frame: the scale over the credits
    for corners in got:
        assert any(bottom for _, bottom, _ in corners), corners  # raised above the sheet
        assert all(not bottom or holds for _, bottom, holds in corners), corners


@browser_test
def test_level_switch_arrows_choose(site, kit_site):
    """The map's level switch as a radio group in the browser (T1): one Tab stop, the checked level; ArrowRight checks
    the next level and moves the focus to it; ArrowLeft back."""
    browser = site[1]  # the module's browser (test_keyboard_app's site)
    read = """() => { const all = [...document.querySelectorAll('.v-levels [role=radio]')];
      return {checked: all.filter((b) => b.getAttribute('aria-checked') === 'true').map((b) => b.dataset.level),
              stops: all.map((b) => b.tabIndex), focus: document.activeElement?.dataset?.level ?? null}; }"""
    page = _view(browser, kit_site + f"#run={BIG}", VIEW_DESKTOP, script=HELP)
    try:
        page.wait_for_selector(".v-levels [role=radio][aria-checked=true]", timeout=WAIT)
        page.focus(".v-levels [role=radio][aria-checked=true]")
        first = page.evaluate(read)
        page.keyboard.press("ArrowRight")
        page.evaluate("() => T.frames()")
        right = page.evaluate(read)
        page.keyboard.press("ArrowLeft")
        page.evaluate("() => T.frames()")
        left = page.evaluate(read)
        assert page.errors == []
    finally:
        page.context.close()
    assert len(first["checked"]) == 1 and sorted(first["stops"]) == [-1, -1, -1, 0], first
    k = LEVELS.index(first["checked"][0])
    assert right["checked"] == [LEVELS[(k + 1) % 4]] and right["focus"] == right["checked"][0], (first, right)
    assert left["checked"] == first["checked"] and left["focus"] == first["checked"][0], (first, left)
    assert sorted(right["stops"]) == [-1, -1, -1, 0], right


@browser_test
@pytest.mark.parametrize("forced", [False, True], ids=["colours", "forced"])
def test_folder_rows_ring_inside(site, kit_site, forced):
    """The folder picker's rows (FavouritePicker, `.u-item.r-folder`) draw the keyboard's ring inside them: their list
    scrolls and clipped one outside (the design review's F3); in forced colours their outline 2 px inside."""
    browser = site[1]  # the module's browser (test_keyboard_app's site)
    page = _view(browser, kit_site + f"#run={BIG}", {**VIEW_DESKTOP, **({"forced_colors": "active"} if forced else {})},
                 script=HELP)
    try:
        _state(page, "view.select(view.order[0]);")
        page.wait_for_selector(".v-result .r-fav", timeout=WAIT)
        page.focus(".v-result .r-fav")
        page.keyboard.press("Enter")
        page.wait_for_selector(".r-picker .r-folder", timeout=WAIT)
        for _ in range(8):
            if page.evaluate("() => !!document.activeElement?.classList.contains('r-folder')"):
                break
            page.keyboard.press("Tab")
        ring = page.evaluate("""() => { const e = document.activeElement, s = getComputedStyle(e);
          return {row: e.classList.contains('r-folder'), visible: e.matches(':focus-visible'), shadow: s.boxShadow,
                  outline: [s.outlineStyle, s.outlineOffset]}; }""")
        assert page.errors == []
    finally:
        page.context.close()
    assert ring["row"] and ring["visible"], ring
    if forced:
        assert ring["outline"][0] != "none" and ring["outline"][1] == "-2px", ring
    else:
        assert "inset" in ring["shadow"], ring


@browser_test
def test_one_key_listener_for_the_maps(site, kit_site):
    """The maps' press mark (layersControl.ts pressMarks) puts one key listener on the page, however many maps it
    made: a second run's map adds none (the code review's finding 4: one per map stayed with each removed map)."""
    browser = site[1]  # the module's browser (test_keyboard_app's site)
    count = """window.G6_KEYS = 0; (() => { const add = EventTarget.prototype.addEventListener;
      EventTarget.prototype.addEventListener = function (type, fn, opt) {
        if (this === document && type === 'keydown' && fn && String(fn).includes('u-map-pressed')) window.G6_KEYS++;
        return add.call(this, type, fn, opt); }; })();"""
    page = _view(browser, kit_site + f"#run={BIG}", VIEW_DESKTOP, script=HELP + count)
    try:
        page.wait_for_selector(".v-map .leaflet-control-layers", timeout=WAIT)
        first = page.evaluate("() => { window.G6_MAP = window.FINDALINE_MAP; return window.G6_KEYS; }")
        page.evaluate(f"() => {{ location.hash = '#run={OLD}'; }}")
        page.wait_for_function("() => window.FINDALINE_MAP && window.FINDALINE_MAP !== window.G6_MAP && "
                               "!!document.querySelector('.v-map .leaflet-control-layers')", timeout=WAIT)
        second = page.evaluate("() => window.G6_KEYS")
        assert page.errors == []
    finally:
        page.context.close()
    assert first == 1 and second == 1, (first, second)
