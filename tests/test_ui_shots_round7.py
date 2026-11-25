"""tools/ui_shots.py's states of line volume's round 7 (PG): renaming a run (Home's card, the result view's header),
Home's card menus (a run with its search, a card low on the screen), Compare's runs that cannot be shown, and a run's
page that cannot load or still loads (RunLoading). The pure parts; the pictures are taken by hand
(.claude/rules/viewer.md)."""
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_shots  # noqa: E402

CARDS = ["c-card-menu", "c-card-menu-search", "c-card-menu-low", "c-card-rename", "c-card-rename-refused"]
VIEW = ["c-view-rename", "c-view-rename-refused", "c-view-compare-causes"]
WAITS = ["map-failed", "map-failed-shared", "map-too-large", "c-run-failed", "c-run-loading", "c-run-loading-gb"]
ROUND_7 = CARDS + VIEW + WAITS
# The name parts the tool's other tests select pages by (tests/test_ui_shots.py: --only, --exclude): none picks a state
# of round 7, so their pages stay as they were
PARTS = "c-home,c-menu,c-account,c-line,map-shared,c-result,c-favourites,view3d-full,credits,profile,more,limited"
# What a later page of the pass would see (one data folder and one browser storage for every page of a pass): a filter
# set or cleared, the kinds of lines shown, a run shared or deleted, anything kept in the browser
CHANGES = re.compile(r"setFilters|clearFilters|setState|\.vl-clear|/share|DELETE|localStorage|sessionStorage|indexedDB")
SAVES = re.compile(r"submit|'Enter'", re.IGNORECASE)  # a form sent: Save pressed, or Enter in its field


def test_round_7s_states_change_nothing():
    """The states are pages of the tool, and none leaves anything for the pass's later pages: no step or init script
    of theirs sets or clears a filter, shares or deletes, or keeps anything in the browser. Only the two refused
    renames (Home's card, the view's box) send a form (the rename's Save, once it is on), after typing a name with a
    tab, which the server refuses (runs.run_name, coded "run_name": nothing is renamed); then each waits for the
    refusal's line. The view's states stand before c-view-editor, so before every page that sets a filter. The run's
    pages that never draw a result are the family "run-wait", drawn once RunLoading's box shows a failure or a bar of a
    known amount. No name part of the tool's other tests picks one of them."""
    from messages import UserError
    from runs import run_name

    assert set(ROUND_7) <= set(ui_shots.PAGES)
    assert not set(ROUND_7) & set(ui_shots.select_pages(PARTS))
    for name in ROUND_7:
        texts = ui_shots.page_steps(ui_shots.PAGES[name][2]) + [ui_shots.PAGE_SCRIPTS.get(name, "")]
        assert not [t for t in texts if CHANGES.search(t)], name
    sending = [n for n in ROUND_7 if any(SAVES.search(s) for s in ui_shots.page_steps(ui_shots.PAGES[n][2]))]
    assert sending == ["c-card-rename-refused", "c-view-rename-refused"]
    for name in sending:
        steps = ui_shots.PAGES[name][2]
        typed = [k for k, s in enumerate(steps) if json.dumps(ui_shots.REFUSED_NAME) in s]
        saved = [k for k, s in enumerate(steps) if SAVES.search(s) and s.startswith("js:")]
        assert len(typed) == len(saved) == 1 and typed[0] < saved[0], name
        assert steps[-1].startswith("wait:") and "[role=alert]" in steps[-1], name
    assert ui_shots.PAGES["c-view-rename-refused"][2] == ui_shots.PAGES["c-view-rename"][2] + ui_shots.VIEW_RENAME_REFUSED
    assert "\t" in ui_shots.REFUSED_NAME
    with pytest.raises(UserError) as refused:
        run_name(ui_shots.REFUSED_NAME)
    assert refused.value.code == "run_name"
    pages = list(ui_shots.PAGES)
    assert max(pages.index(n) for n in VIEW) < pages.index("c-view-editor")
    assert set(ui_shots.RUN_WAITS) == set(WAITS)
    assert {ui_shots.page_family(n) for n in ui_shots.RUN_WAITS} == {"run-wait"}
    assert {ui_shots.page_family(n) for n in CARDS} == {"home"}
    assert 'family === "run-wait"' in ui_shots.PAGE_STATE and ".c-result-wait p.c-error" in ui_shots.PAGE_STATE
    assert ".c-result-wait .c-loading .u-prog:not(.u-busy)" in ui_shots.PAGE_STATE


def test_round_7s_pages_are_made_in_the_page():
    """What each state makes up, it makes in the page. Compare's causes: the owner's header (the job stub, last) waited
    for before Compare opens, and its three runs added to every list of runs the page reads, by the document's capturing
    "load" listener of the list's script (not a property of the window, which load.ts forgetRunList deletes). Home's
    card of a run with its search: the jobs answered with a finished job of the run the page's own /api/runs lists,
    and the menu waited for with "Edit & run again". The low card: /api/runs padded with five made-up runs, the last
    card's button placed above the bottom bar and clicked as a person's click. A store too large: Back and the
    sentence, no "Try again". The loading line in GB: its sizes give a bar of 22 % (17 % in MB)."""
    compare = ui_shots.PAGES["c-view-compare-causes"][2]
    assert compare.index(ui_shots.VIEW_OWNER) < compare.index(ui_shots.VIEW_ACTION % "Compare")
    assert ui_shots.PAGE_SCRIPTS["c-view-compare-causes"] == ui_shots.COMPARE_CAUSES_RUNS + ui_shots.VIEW_JOB_STUB
    runs = ui_shots.COMPARE_CAUSES_RUNS
    assert "document.addEventListener('load'" in runs and "}, true);" in runs and "'/runs/runs.js'" in runs
    assert "defineProperty(window" not in runs and "list.push(" in runs and "!list.some((r) => r.id === id)" in runs
    search = ui_shots.PAGES["c-card-menu-search"][2]
    assert search[1] == ".c-card[data-run][data-job] .c-card-menu" and "'Edit & run again'" in search[-1]
    assert "!== '/api/jobs'" in ui_shots.HOME_JOB_STUB and "f('/api/runs', init)" in ui_shots.HOME_JOB_STUB
    low = ui_shots.PAGES["c-card-menu-low"][2]
    assert low == ["wait:document.querySelectorAll('.c-card[data-run] .c-card-menu').length >= 6", "js:" + ui_shots.CARD_LAST_LOW,
                   "[data-shot-last]", "wait:document.querySelector('.c-card[data-run] [role=menu]')"]
    assert ".u-bnav" in ui_shots.CARD_LAST_LOW and "all[all.length - 1]" in ui_shots.CARD_LAST_LOW
    assert "!== '/api/runs'" in ui_shots.HOME_MORE_RUNS and "init.method !== 'GET'" in ui_shots.HOME_MORE_RUNS
    assert '"Sample ridge"' in ui_shots.HOME_MORE_RUNS and "shared: false" in ui_shots.HOME_MORE_RUNS
    assert ui_shots.PAGES["map-too-large"] == ("map", "", ui_shots.RUN_TOO_LARGE)
    assert "!document.querySelector('.c-result-wait .c-retry')" in ui_shots.RUN_TOO_LARGE
    assert "this.shotsTooLarge ? null" in ui_shots.RUN_STORE_TOO_LARGE
    for sizes, script, wait, percent in ((ui_shots.RUN_STORE_SIZES, ui_shots.RUN_STORE_LOADING, ui_shots.RUN_LOADING, 17),
                                         (ui_shots.RUN_STORE_SIZES_GB, ui_shots.RUN_STORE_LOADING_GB, ui_shots.RUN_LOADING_GB, 22)):
        assert round(100 * sum(d for _, d in sizes.values()) / sum(t for t, _ in sizes.values())) == percent
        assert json.dumps(sizes) in script and wait.endswith(f"=== {percent}")
