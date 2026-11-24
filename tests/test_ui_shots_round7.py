"""tools/ui_shots.py's states of line volume's round 7 (PG): renaming a run (Home's card, the result view's header),
Compare's runs that cannot be shown, and a run's page that cannot load or still loads (RunLoading). The pure parts;
the pictures are taken by hand (.claude/rules/viewer.md)."""
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_shots  # noqa: E402

ROUND_7 = ["c-card-menu", "c-card-rename", "c-card-rename-refused", "c-view-rename", "c-view-compare-causes",
           "map-failed", "map-failed-shared", "c-run-failed", "c-run-loading"]
# The name parts the tool's other tests select pages by (tests/test_ui_shots.py: --only, --exclude): none picks a state
# of round 7, so their pages stay as they were
PARTS = "c-home,c-menu,c-account,c-line,map-shared,c-result,c-favourites,view3d-full,credits,profile,more,limited"
# What a later page of the pass would see (one data folder and one browser storage for every page of a pass): a filter
# set or cleared, the kinds of lines shown, a run shared or deleted, anything kept in the browser
CHANGES = re.compile(r"setFilters|clearFilters|setState|\.vl-clear|/share|DELETE|localStorage|sessionStorage|indexedDB")
SAVES = re.compile(r"submit|'Enter'", re.IGNORECASE)  # a form sent: Save pressed, or Enter in its field


def test_round_7s_states_change_nothing():
    """The nine states are pages of the tool, and none leaves anything for the pass's later pages: no step or init
    script of theirs sets or clears a filter, shares or deletes, or keeps anything in the browser. Only
    c-card-rename-refused sends a form (the rename's Save, once it is on), after typing a name with a tab, which the
    server refuses (runs.run_name, coded "run_name": nothing is renamed); then it waits for the refusal's line. The
    view's two states stand before c-view-editor, so before every page that sets a filter. The run's pages that never
    draw a result are the family "run-wait", drawn once RunLoading's box shows a failure or a bar of a known amount.
    No name part of the tool's other tests picks one of them."""
    from messages import UserError
    from runs import run_name

    assert set(ROUND_7) <= set(ui_shots.PAGES)
    assert not set(ROUND_7) & set(ui_shots.select_pages(PARTS))
    for name in ROUND_7:
        texts = ui_shots.page_steps(ui_shots.PAGES[name][2]) + [ui_shots.PAGE_SCRIPTS.get(name, "")]
        assert not [t for t in texts if CHANGES.search(t)], name
    sending = [n for n in ROUND_7 if any(SAVES.search(s) for s in ui_shots.page_steps(ui_shots.PAGES[n][2]))]
    assert sending == ["c-card-rename-refused"]
    steps = ui_shots.PAGES["c-card-rename-refused"][2]
    typed = [k for k, s in enumerate(steps) if json.dumps(ui_shots.CARD_REFUSED_NAME) in s]
    saved = [k for k, s in enumerate(steps) if SAVES.search(s) and s.startswith("js:")]
    assert len(typed) == len(saved) == 1 and typed[0] < saved[0] and steps[-1].startswith("wait:") and "[role=alert]" in steps[-1]
    assert "\t" in ui_shots.CARD_REFUSED_NAME
    with pytest.raises(UserError) as refused:
        run_name(ui_shots.CARD_REFUSED_NAME)
    assert refused.value.code == "run_name"
    pages = list(ui_shots.PAGES)
    assert max(pages.index("c-view-rename"), pages.index("c-view-compare-causes")) < pages.index("c-view-editor")
    assert set(ui_shots.RUN_WAITS) == {"map-failed", "map-failed-shared", "c-run-failed", "c-run-loading"}
    assert {ui_shots.page_family(n) for n in ui_shots.RUN_WAITS} == {"run-wait"}
    assert {ui_shots.page_family(n) for n in ("c-card-menu", "c-card-rename", "c-card-rename-refused")} == {"home"}
    assert 'family === "run-wait"' in ui_shots.PAGE_STATE and ".c-result-wait p.c-error" in ui_shots.PAGE_STATE
    assert ".c-result-wait .c-loading .u-prog:not(.u-busy)" in ui_shots.PAGE_STATE
