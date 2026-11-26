"""NOT FOR MERGE (branch bars-variants, brief BV of line volume round 7): the walk of the three status-bar variants
(viewer/src/ui/bars.ts, chosen by the page's port: 8444 A, 8445 B, 8446 C, any other today's code). The local app of
test_theme_bars' `site` on its own port; the variants' ports are only addresses the browser believes it is on
(Playwright routes every request of them to the app's real port: nothing listens on 8444-8446). Playwright's
Chromium, the iPhone 13 profile, the system light and dark: the app's Account, then Dark, Light, Auto; after each the
theme-color lines, <html>'s and <body>'s inline and computed background and colour scheme, and the variant's label.
Writes the table to the file named by BARS_WALK_OUT (default: the test's tmp folder) and prints it."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_public import clip_run  # noqa: E402,F401
from test_theme_bars import site  # noqa: E402,F401
from test_theme_bars import BARS_JS, _choose  # noqa: E402

VARIANTS = {"today": None, "A": 8444, "B": 8445, "C": 8446}
STATE_JS = """() => {
  const h = document.documentElement, b = document.body, hc = getComputedStyle(h), bc = getComputedStyle(b);
  const label = document.getElementById("fal-bars-variant");
  return {html_inline: [h.style.backgroundColor, h.style.colorScheme],
          html_computed: [hc.backgroundColor, hc.colorScheme],
          body_inline: b.style.backgroundColor, body_computed: bc.backgroundColor,
          label: label ? [label.textContent, getComputedStyle(label).pointerEvents, label.getAttribute("aria-hidden")]
                       : null};
}"""


@pytest.fixture(scope="module")
def iphone():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        launched = p.chromium.launch()
        try:
            yield {"browser": launched, "phone": {k: v for k, v in p.devices["iPhone 13"].items()
                                                  if k != "default_browser_type"}}
        finally:
            launched.close()


def _route(context, real: str, port: int):
    """Every request to 127.0.0.1:<port> answered by the app at `real`; the event stream refused (it never ends)."""
    fake = f"http://127.0.0.1:{port}"

    def handle(route):
        url = route.request.url
        if "/api/events" in url:
            route.abort()
            return
        response = route.fetch(url=real + url[len(fake):])
        route.fulfill(response=response)
    context.route(fake + "/**", handle)
    return fake


def test_walk(site, iphone, tmp_path):
    rows, errors = [], []
    for name, port in VARIANTS.items():
        for scheme in ("light", "dark"):
            context = iphone["browser"].new_context(**iphone["phone"], color_scheme=scheme, locale="en-US")
            context.add_init_script("try { for (const k of ['search', 'result']) "
                                    "localStorage.setItem('findaline.intro.' + k, 'seen'); } catch (e) {}")
            base = site["url"] if port is None else _route(context, site["url"], port)
            page = context.new_page()
            page.on("pageerror", lambda e, n=name, s=scheme: errors.append((n, s, str(e)[:300])))
            page.goto(base + "/#account")
            page.wait_for_selector(".c-app [role=radiogroup]", state="attached", timeout=60000)
            assert page.evaluate("() => location.port") == str(port or site["url"].rsplit(":", 1)[1])
            for step in ("start", "Dark", "Light", "Auto", "reload, Dark kept"):
                if step == "reload, Dark kept":  # a relaunch with a chosen theme: the call at the page's start
                    _choose(page, "Dark")
                    page.reload()
                    page.wait_for_selector(".c-app [role=radiogroup]", state="attached", timeout=60000)
                    page.wait_for_timeout(100)
                elif step != "start":
                    _choose(page, step)
                    page.wait_for_timeout(100)
                rows.append({"variant": name, "system": scheme, "step": step, "lines": page.evaluate(BARS_JS),
                             **page.evaluate(STATE_JS)})
            context.close()
    out = os.environ.get("BARS_WALK_OUT") or str(tmp_path / "walk.txt")
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print("\n".join(json.dumps(r) for r in rows))
    assert errors == [], errors
