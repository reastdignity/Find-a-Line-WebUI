"""
Today's result page pinned, for the tests and tools that check it (step 3d of the result view, docs/line-volume/spec.md
section 5). A run opens in the result view or in today's page as viewer/src/result/view/SpotColumns.tsx `viewWanted`
says: until gate 2 today's page is the default and the view is asked for (`?view=b`); once `VIEW_DEFAULT` is true the
view is the default and today's page stays behind `?view=today`, remembered by the browser (localStorage
"findaline.view" = "today", the page's own key), and for the runs the view cannot show. A test or tool that checks
today's page opens it through this pin, so it holds with either default.

One answer in two forms, both the page's own (no new query word, no new key a user could reach):
- SCRIPT: an init script that leaves "today" in the browser (Playwright's `add_init_script`), so every load of the
  context, a later navigation and a run's map.html too, opens today's page; the address stays as the test wrote it
  (a copied or shared link is compared as before);
- `today(url)`: the address asks (`view=today` in its query, before the hash), for a browser started on an address
  (headless Edge's --dump-dom) and a page whose storage is blocked.

`view_default()`: the constant as the source has it (the built dist follows it: tests/test_viewer.py compares dist with
a fresh build), for the few checks of the default itself.
"""

import os
import re
from urllib.parse import urlsplit, urlunsplit

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO, "viewer", "src", "result", "view", "SpotColumns.tsx")
KEY = "findaline.view"  # SpotColumns.tsx VIEW_KEY
SCRIPT = "try { localStorage.setItem('findaline.view', 'today'); } catch (e) {}"
VIEW = "try { localStorage.setItem('findaline.view', 'b'); } catch (e) {}"  # the other answer: the view asked for
_LINE = re.compile(r"^export const VIEW_DEFAULT: boolean = (true|false);", re.M)


def view_default() -> bool:
    """Is the result view the default in this checkout (SpotColumns.tsx VIEW_DEFAULT)."""
    with open(SOURCE, encoding="utf-8") as f:
        found = _LINE.findall(f.read())
    if len(found) != 1:
        raise RuntimeError(f"{SOURCE}: {len(found)} lines 'export const VIEW_DEFAULT: boolean = ...;' (one expected)")
    return found[0] == "true"


def today(url: str) -> str:
    """The address asking for today's page: `view=today` in its query (another `view=` there replaced), the path and
    the hash as they were."""
    parts = urlsplit(url)
    query = [q for q in parts.query.split("&") if q and q.split("=")[0] != "view"] + ["view=today"]
    return urlunsplit(parts._replace(query="&".join(query)))
