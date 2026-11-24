"""
The site's icons for a phone's home screen ("Add to home screen", line volume round 7's extra B8): the logo's mark
(viewer/src/ui/logo/mark.svg, its own drawing) on white, in the light theme's colours (the mark's classes as
viewer/src/ui/ui.css colours them, from the tokens of viewer/src/ui/tokens.css), drawn by Chromium (Playwright) and
saved by Pillow as opaque PNG (an iPhone draws a transparent pixel black) into viewer/src/ui/logo/:

- apple-touch-icon.png, 180 px: an iPhone's icon (opaque and square; the phone rounds its corners);
- icon-192.png and icon-512.png: the manifest's icons ("any");
- icon-maskable-512.png: the manifest's maskable icon, the mark inside the middle 80 % that every mask keeps.

The mark's square (its viewBox) stands in the tile's middle at SHARE of its width (MASKABLE_SHARE in the maskable
one), as the accepted mock-up drew it (local/line-volume-7-2026-11-23/MU1, points 18 to 21). viewer/build.mjs
copies the four files into viewer/dist beside the manifest it writes; the pages link them (runs.HOME_SCREEN_HEAD).
Run again after a change of the mark, of its classes' colours or of those tokens: tests/test_home_screen.py compares
the files with a fresh drawing.

    uv sync --group ui; uv run playwright install chromium   (once)
    uv run tools/home_screen_icons.py [--out <folder>]
"""

import argparse
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(REPO, "viewer", "src", "ui", "logo")
MARK = os.path.join(LOGO, "mark.svg")
UI_CSS = os.path.join(REPO, "viewer", "src", "ui", "ui.css")
TOKENS = os.path.join(REPO, "viewer", "src", "ui", "tokens.css")

GROUND = "#ffffff"  # the tile's ground: white (the user's answer to point 18, 2026-11-24)
SHARE = 0.70  # the mark's square as a part of the tile's width: the iPhone's icon and the manifest's "any"
MASKABLE_SHARE = 0.56  # in the maskable icon: the square's corners 0.396 of the width from the middle, inside 0.40
SAFE_RADIUS = 0.40  # the maskable icon's safe zone: a circle of 40 % of the width around the middle
# name: (size in px, the mark's share)
ICONS = {"apple-touch-icon.png": (180, SHARE), "icon-192.png": (192, SHARE), "icon-512.png": (512, SHARE),
         "icon-maskable-512.png": (512, MASKABLE_SHARE)}


def light_tokens(text: str) -> dict:
    """The light theme's tokens of tokens.css (its first `.ui { ... }` block): {"--name": "value"}."""
    block = re.search(r"^\.ui \{(.*?)^\}", text, re.S | re.M)
    if not block:
        raise ValueError("tokens.css has no .ui block")
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+?)\s*;", block.group(1)))


def mark_colours(css: str, tokens: dict) -> dict:
    """The mark's classes as ui.css colours them in the light theme: {"u-li": ("fill", "#16262a"), ...}."""
    found = {}
    for name, prop, token in re.findall(r"^\.ui \.(u-l[a-z]+) \{ (fill|stroke): var\((--[\w-]+)\); \}", css, re.M):
        found[name] = (prop, tokens[token])
    return found


def icon_svg(size: int, share: float, mark: str | None = None, css: str | None = None,
             tokens_css: str | None = None) -> str:
    """The icon as an SVG document of `size` px: a white square with the mark's own drawing in its middle, its
    viewBox square `share` of the width, its classes coloured as ui.css does in the light theme. The texts default
    to the files' (MARK, UI_CSS, TOKENS)."""
    def read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    mark = read(MARK) if mark is None else mark
    css = read(UI_CSS) if css is None else css
    tokens = light_tokens(read(TOKENS) if tokens_css is None else tokens_css)
    box = re.search(r'viewBox="([^"]+)"', mark)
    inner = re.search(r"<svg[^>]*>(.*)</svg>", mark, re.S)
    if not box or not inner:
        raise ValueError("mark.svg: no viewBox or no drawing")
    x, y, w, h = (float(v) for v in box.group(1).split())
    colours = mark_colours(css, tokens)
    used = set(re.findall(r'class="([^"]+)"', inner.group(1)))
    if not used or used - set(colours):
        raise ValueError(f"ui.css colours none of the mark's classes {sorted(used - set(colours))}")
    style = "".join(f".{name}{{{prop}:{colour}}}" for name, (prop, colour) in sorted(colours.items()) if name in used)
    scale = 100 * share / max(w, h)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">'
            f"<style>{style}</style>"
            f'<rect width="100" height="100" fill="{GROUND}"/>'
            f'<g transform="translate(50 50) scale({scale:.6f}) translate({-(x + w / 2):.6f} {-(y + h / 2):.6f})">'
            f"{inner.group(1)}</g></svg>")


def draw(icons: dict | None = None) -> dict:
    """The icons drawn by Playwright's Chromium (one pixel per CSS pixel), as opaque RGB pictures (Pillow):
    {name: PIL.Image}."""
    from PIL import Image
    from playwright.sync_api import sync_playwright

    pictures = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, (size, share) in (icons or ICONS).items():
                page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
                page.set_content('<!doctype html><html><head><style>html, body { margin: 0; background: #ffffff; } '
                                 'svg { display: block; }</style></head><body>' + icon_svg(size, share)
                                 + "</body></html>")
                shot = page.screenshot(clip={"x": 0, "y": 0, "width": size, "height": size})
                page.close()
                pictures[name] = Image.open(io.BytesIO(shot)).convert("RGB")
        finally:
            browser.close()
    return pictures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--out", default=LOGO, help="the folder of the PNG files (default: viewer/src/ui/logo)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name, picture in draw().items():
        path = os.path.join(args.out, name)
        picture.save(path, optimize=True)
        print(f"{path}  {picture.width} x {picture.height}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, REPO)
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    sys.exit(main())
