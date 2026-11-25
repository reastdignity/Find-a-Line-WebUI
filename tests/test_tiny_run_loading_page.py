"""The loading line of a tiny run on the page (line volume's round 7, the user's answer 3 of 2026-11-25, "Two
decimals"; the units: test_tiny_run_loading.py): while a run whose two files hold under 50 000 bytes downloads, the
app's page of the run counts both numbers in MB with two decimals.

Playwright's Edge over the public app on a thread (test_home_size_page's set-up: test_rename_home_page's `rename_site`,
tools/ui_shots.py's stand-in of the run's two downloads), offline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_home_size_page import DESKTOP_UTC, LOADING, REPO, Browser, opened, rename_site  # noqa: E402,F401
from test_public import RUN_A, account_settings  # noqa: E402,F401
from test_shell_c_view_map import view_clip  # noqa: E402,F401
from test_size_units import NBSP  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
# The deadline of every wait for the page, ms (lowered through the variable for a run against a page without the
# change, where the wait runs out)
WAIT = int(os.environ.get("FINDALINE_TINY_PAGE_WAIT", 30_000))


def test_the_loading_line_of_a_tiny_run(rename_site):
    """While the run's two files download (tools/ui_shots.py's stand-in for their requests: 25 000 and 15 000 bytes,
    10 000 and 6 000 of them in) the app's page of the run reads "Downloading the run… 0.02 of 0.04 MB" (a no-break
    space before the unit), its bar at 40, with the Back "Home"."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    from ui_shots import RUN_STORE_LOADING_OF
    sizes = {"lines.arrow": [25_000, 10_000], "profiles.arrow": [15_000, 6_000]}
    script = RUN_STORE_LOADING_OF.replace("SIZES;", json.dumps(sizes) + ";")
    assert script != RUN_STORE_LOADING_OF
    site, _ = rename_site
    with Browser(site) as browser:
        page = opened(browser, DESKTOP_UTC, script=script)
        page.set_default_timeout(WAIT)
        page.goto(f"{site}/?ui=c#run={RUN_A}")
        page.wait_for_function("() => document.querySelector('.c-result-wait .c-loading .u-prog:not(.u-busy)')"
                               "?.getAttribute('aria-valuenow') === '40'")
        seen = page.evaluate(LOADING)
    assert seen == {"line": f"Downloading the run… 0.02 of 0.04{NBSP}MB", "now": "40", "back": "Home"}, seen
