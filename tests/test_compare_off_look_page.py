"""One look for every switched-off box of Compare (line volume's round 7, the user's answer 5 of 2026-11-25, "One look
for all": "Every switched-off box is drawn from the app's colours"). A box that is off because its run is too large for
the browser or made by a newer Find-a-Line and never had the focus (natively disabled) and a box that went off under
the focus (aria-disabled, its presses ignored) are drawn alike from the tokens (the kit's rule in ui/ui.css), in the
light and the dark theme; the focus ring shows only on the box that has the focus; both differ from an active box (the
browser's own box). The look's hook is the kit's class `u-off`, which only Compare puts on a box: no other checkbox of
the app changes its look (Leaflet's layers control disables its own boxes by zoom, so `:disabled` is not matched).

Playwright's Edge over the public app on a thread (test_rename_home_page's `rename_site`; test_compare_causes_page's
runs and stand-ins), offline. Run from PowerShell (.claude/rules/browser-tests.md)."""

import io
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_compare_causes_page import (AT, BOX_STATE, NAME_NEW, NAME_TOO, RUN_NEW, RUN_TOO, TOO_LARGE, WAIT_MS,  # noqa: E402
                                      add_run, open_compare, rgb, settled)
from test_public import RUN_A, RUN_B, account_settings  # noqa: E402,F401
from test_rename_home_page import Browser, rename_site  # noqa: E402,F401
from test_shell_c_view_map import DESKTOP, view_clip  # noqa: E402,F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "viewer", "src")
# The tokens of the light theme as tokens.css writes them (the dark run must read other values)
LIGHT = {"--line": "#b3c1c2", "--surface-2": "#e5ebeb"}

# A box's drawing as the browser computed it: its edge (each side's width, style and colour), corners, fill, size and
# the ring (an outline: drawn only where its style is not "none" and its width not 0), and the tokens its .ui root holds
LOOK = """(id) => { const box = document.querySelector(`.r-pop input[data-other="${id}"]`);
  const s = getComputedStyle(box), r = box.getBoundingClientRect(), ui = getComputedStyle(box.closest('.ui'));
  const sides = ['top', 'right', 'bottom', 'left'];
  return {edge: sides.map((k) => [s.getPropertyValue(`border-${k}-width`), s.getPropertyValue(`border-${k}-style`),
                                   s.getPropertyValue(`border-${k}-color`)]),
          corners: sides.map((k, i) => s.getPropertyValue(`border-${['top-left', 'top-right', 'bottom-right', 'bottom-left'][i]}-radius`)),
          fill: s.backgroundColor, appearance: s.appearance, opacity: s.opacity, size: [r.width, r.height],
          ring: [s.outlineStyle, s.outlineWidth], focused: box.matches(':focus-visible'),
          box: [r.x, r.y, r.width, r.height], classes: box.className,
          tokens: {line: ui.getPropertyValue('--line').trim(), surface2: ui.getPropertyValue('--surface-2').trim(),
                   surface: ui.getPropertyValue('--surface').trim(), r1: ui.getPropertyValue('--r-1').trim()}}; }"""


def _pixels(page, box) -> list:
    """The box's 20 x 20 px as the page draws them: rows of (r, g, b)."""
    from PIL import Image
    x, y, w, h = box
    shot = page.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
    image = Image.open(io.BytesIO(shot)).convert("RGB")
    return [[image.getpixel((i, j)) for i in range(image.width)] for j in range(image.height)]


def _luminance(rgb_: tuple) -> float:
    """WCAG 2's relative luminance of an sRGB colour."""
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb_)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple, b: tuple) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _edge(pixels: list, ground: tuple) -> tuple:
    """The box's left edge at its middle row: of the first four pixels the one farthest from the panel's ground."""
    row = pixels[len(pixels) // 2][:4]
    return max(row, key=lambda p: contrast(p, ground))


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c)


def _parse(color: str) -> tuple:
    m = re.fullmatch(r"rgba?\((\d+), (\d+), (\d+)(?:, [\d.]+)?\)", color)
    assert m, color
    return tuple(int(v) for v in m.groups())


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_off_box_has_one_look(rename_site, view_clip, theme):
    """Compare's list with RUN_B (active, unticked), a run too large for the browser and a run of a newer store
    format. The newer run's box switched by a script's press while the focus is on RUN_B's box: off, natively
    disabled, never focused. The too large run's box ticked with the keyboard (focused, Space): off under the focus,
    aria-disabled. Both have the kit's off look: no native drawing, a 1 px solid edge of --line, the fill of
    --surface-2, the corners of --r-1, 20 x 20 px, full opacity, and the same pixels; the ring (a 2 px solid
    outline) only on the focused one. RUN_B's box is the browser's own: another appearance and other pixels. A
    script's press and a script's change on either off box load nothing and leave both as they were. The measured
    colours and the contrast between an off and an active box's edge are printed (no threshold)."""
    site, data = rename_site
    add_run(view_clip, data, RUN_TOO, NAME_TOO)
    add_run(view_clip, data, RUN_NEW, NAME_NEW)
    path = data / "runs" / RUN_NEW / "run.json"  # its store's format one higher (runs.js lists run.json's block)
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["store"]["format"] += 1
    path.write_text(json.dumps(meta), encoding="utf-8")
    with Browser(site) as browser:
        page = browser.page({**DESKTOP, "color_scheme": theme}, "a", TOO_LARGE % RUN_TOO)
        page.set_default_timeout(WAIT_MS)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        page.wait_for_function("() => !!window.FINDALINE_VIEW")
        open_compare(page)
        # the newer run's box: a script's press while the focus is on RUN_B's box (never focused itself)
        page.locator(f".r-pop input[data-other='{RUN_B}']").focus()
        page.evaluate("(id) => document.querySelector(`.r-pop input[data-other=\"${id}\"]`).click()", RUN_NEW)
        settled(page, NAME_NEW)
        # the too large run's box: ticked with the keyboard, off under the focus
        page.locator(f".r-pop input[data-other='{RUN_TOO}']").focus()
        page.keyboard.press("Space")
        settled(page, NAME_TOO)
        page.mouse.move(1, 1)  # no hover on a row
        at = page.evaluate(AT)
        held, never, active = (page.evaluate(LOOK, run) for run in (RUN_TOO, RUN_NEW, RUN_B))
        states = {run: page.evaluate(BOX_STATE, run) for run in (RUN_TOO, RUN_NEW, RUN_B)}
        pixels = {run: _pixels(page, look["box"]) for run, look in ((RUN_TOO, held), (RUN_NEW, never), (RUN_B, active))}
        # a script's press and a script's change on either off box load nothing and leave it as it is
        asked = []
        page.on("request", lambda r: asked.append(r.url) if r.url.endswith(".arrow") else None)
        for run in (RUN_TOO, RUN_NEW):
            page.evaluate("(id) => { const box = document.querySelector(`.r-pop input[data-other=\"${id}\"]`); box.click();"
                          " box.dispatchEvent(new Event('change', {bubbles: true})); }", run)
        page.evaluate("() => fetch('/api/usage').then((r) => r.status)")  # a request after them, answered
        scripted = {run: page.evaluate(BOX_STATE, run) for run in (RUN_TOO, RUN_NEW)}
    # the two kinds of off box, as the existing tests know them
    assert at == RUN_TOO, at
    assert (states[RUN_TOO]["aria"], states[RUN_TOO]["disabled"], states[RUN_TOO]["checked"]) == ("true", False, False), states
    assert (states[RUN_NEW]["aria"], states[RUN_NEW]["disabled"], states[RUN_NEW]["checked"]) == (None, True, False), states
    assert (states[RUN_B]["aria"], states[RUN_B]["disabled"], states[RUN_B]["checked"]) == (None, False, False), states
    tokens = held["tokens"]
    if theme == "dark":  # the dark run reads the dark tokens, not the light ones twice
        assert tokens["line"] != LIGHT["--line"] and tokens["surface2"] != LIGHT["--surface-2"], tokens
    else:
        assert (tokens["line"], tokens["surface2"]) == (LIGHT["--line"], LIGHT["--surface-2"]), tokens
    # one look: drawn from the tokens, alike in both kinds
    for name, look in (("held", held), ("never focused", never)):
        assert "none" in look["appearance"], (name, look)
        assert look["edge"] == [["1px", "solid", rgb(tokens["line"])]] * 4, (name, look)
        assert look["fill"] == rgb(tokens["surface2"]) and look["corners"] == [tokens["r1"]] * 4, (name, look)
        assert look["size"] == [20, 20] and look["opacity"] == "1", (name, look)
    assert {k: held[k] for k in ("edge", "corners", "fill", "appearance", "opacity", "size")} == \
        {k: never[k] for k in ("edge", "corners", "fill", "appearance", "opacity", "size")}, (held, never)
    assert pixels[RUN_TOO] == pixels[RUN_NEW], "the two off boxes are drawn differently"
    assert "u-off" in held["classes"].split() and "u-off" in never["classes"].split(), (held, never)  # the kit's hook
    # the ring only on the box with the focus
    assert held["focused"] and held["ring"] == ["solid", "2px"], held
    assert not never["focused"] and (never["ring"][0] == "none" or never["ring"][1] == "0px"), never
    # an active box: the browser's own, other pixels
    assert "none" not in active["appearance"] and "u-off" not in active["classes"].split(), active
    assert pixels[RUN_B] != pixels[RUN_TOO], "an active box is drawn as an off one"
    ground = _parse(rgb(tokens["surface"]))
    off_edge, active_edge = _edge(pixels[RUN_TOO], ground), _edge(pixels[RUN_B], ground)
    print(f"\n{theme}: off box edge {_hex(off_edge)} (--line {tokens['line']}), fill {tokens['surface2']}; "
          f"active box edge {_hex(active_edge)}; panel ground {tokens['surface']}; "
          f"off/active edge contrast {contrast(off_edge, active_edge):.2f}:1; "
          f"off edge/ground {contrast(off_edge, ground):.2f}:1, active edge/ground {contrast(active_edge, ground):.2f}:1")
    assert off_edge != active_edge, (off_edge, active_edge)
    assert asked == [] and {run: (s["aria"], s["disabled"], s["checked"]) for run, s in scripted.items()} == \
        {RUN_TOO: ("true", False, False), RUN_NEW: (None, True, False)}, (asked, scripted)


def test_the_off_look_is_compares_alone():
    """The kit's off look (ui/ui.css) is matched by aria-disabled or the class `u-off`, never by `:disabled` (every
    other checkbox of the app keeps the browser's look when disabled: Leaflet's layers control disables its boxes out
    of a layer's zooms), and `u-off` is put on a box only by Compare (result/view/RunActions.tsx)."""
    from test_viewer import _css_rules
    with open(os.path.join(SRC, "ui", "ui.css"), encoding="utf-8") as f:
        ui = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    checks = [(selector, body) for selector, body, _ in _css_rules(ui) if ".u-check" in selector]
    off = [selector for selector, body in checks if "appearance: none" in body]
    assert off == ['.ui .u-check[aria-disabled="true"], .ui .u-check.u-off'], off
    assert not [selector for selector, _ in checks if ":disabled" in selector], checks
    users = []
    for root, _, files in os.walk(SRC):
        for name in files:
            if name.endswith((".ts", ".tsx", ".css")):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    if re.search(r"\bu-off\b", f.read()):
                        users.append(os.path.relpath(os.path.join(root, name), SRC).replace(os.sep, "/"))
    assert sorted(users) == ["result/view/RunActions.tsx", "ui/ui.css"], users
