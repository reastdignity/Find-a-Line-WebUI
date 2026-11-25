"""tools/ui_shots.py's states of the result view added in step 3d (VIEW_STATES: the features joined in step 3c, the
lists of wave B's workers and of the screenshot gate) and line volume's round 7 (A3: the filters' panels open), and the
pin of today's page in every other page: the pure parts (the pictures are taken by hand: .claude/rules/viewer.md)."""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_shots  # noqa: E402

# Each state of the workers' lists (SESSION/B1/report.md, B2/report.md, B3/gate/index.md) and of brief C3 (the card,
# the coast boxes and chips, the rails, map.html and a share link's page in the view): the state that takes it. The
# gate's 1024 x 768 pictures (G9's desktop column, X3) are no device of the tool; X2 is a sheet of G2's pictures
COVERED = {
    "B1 area": "c-view-area-outline", "B1 c-view-fav": "c-view-fav", "B1 c-view-lines-fav-selected": "c-view-lines-fav-selected",
    "B1 c-view-measured": "c-view-measured", "B1 c-view-other-run": "c-view-other-run",
    "B2 line": "c-view-line", "B2 picker": "c-view-picker", "B2 fav": "c-view-line-fav", "B2 closed": "c-view-closed",
    "B2 copied": "c-view-copied", "B2 stars": "c-view-stars", "B2 help-top": "c-view-help-top",
    "B2 help-cols": "c-view-help-cols", "B2 note": "c-view-note", "B2 none": "c-view-none", "B2 share": "c-view-shared",
    "B2 refused": "c-view-refused", "B2 report": "c-view-report",
    "G1": "c-view", "G2": "c-view-line", "G3": "c-view-share", "G4a": "c-view-measured", "G4b": "c-view-link",
    "G4c": "c-view-link-centre", "G5": "c-view-area-outline", "G6": "c-view-stars", "G7": "c-view-other-run",
    "G8": "c-view-help", "G9 phones": "c-view-chips-held", "G10": "c-view-refused", "X1 coarser": "c-view-box-coarser",
    "X1 shore": "c-view-box-shore",
    "card open": "c-view-card", "card folded": "c-view-card-folded", "boxes": "c-view-boxes", "chips": "c-view-boxes",
    "rails": "c-view-rails", "map.html": "c-view-map", "map.html line": "c-view-map-line", "share link": "c-view-shared",
    # round 7's PG: the header's Rename box open, a refused name in it, its button's focus ring, Compare's causes (a desktop)
    "PG rename": "c-view-rename", "PG rename refused": "c-view-rename-refused", "PG rename focus": "c-view-rename-focus",
    "PG Compare's causes": "c-view-compare-causes",
    # C4's (step 3d: the spot stepper, the sort's direction, the star's picker on a phone)
    "C4 stepper, desktop": "c-view-stepper", "C4 stepper, phone at half": "c-view-stepper-half",
    "C4 stepper, phone low": "c-view-stepper-low", "C4 Previous off": "c-view-stepper-first",
    "C4 Next off": "c-view-stepper-last", "C4 smallest first": "c-view-sort-asc",
    "C4 picker, phone": "c-view-picker-low",
    # round 7's A3: a main filter's editor open, More filters open (every device)
    "A3 editor": "c-view-editor", "A3 More filters": "c-view-more",
}
SHORE = {"c-view-boxes", "c-view-chips-held", "c-view-box-coarser", "c-view-box-shore", "c-view-link-centre"}
CLICKS = {ui_shots.VIEW_DESKTOP, ui_shots.VIEW_PHONE, ".r-card .r-fold"}  # the only steps that are clicks


def test_every_listed_state_has_its_page():
    assert set(COVERED.values()) <= set(ui_shots.PAGES), set(COVERED.values()) - set(ui_shots.PAGES)
    assert set(ui_shots.VIEW_STATES) <= set(COVERED.values()) | {"c-view-measuring"}


def test_the_states_open_the_view():
    """Each state is a page of the view (the flag "b"; the app's result, a run's map.html or a share link's page),
    waits for the view first, needs the view's columns (the coast boxes' an uncertain shore), and is made of scripts,
    waits and only the clicks that keep a state to one kind of device; keys only in c-view-rename-focus (Shift+Tab and
    Tab: the keyboard's focus ring follows only a person's key)."""
    keys = {"key:Shift+Tab", "key:Tab"}
    for name, (ui, hash_, steps, *who) in ui_shots.VIEW_STATES.items():
        assert ui_shots.PAGES[name] == (ui, hash_, steps, *who) and ui_shots.VIEWS[name] == "b", name
        assert (ui, hash_) in (("c", "#run={run}"), ("map", ""), ("map", "#line={line}"), ("shared", "#line={line}")), name
        assert steps[0] == ui_shots.VIEW_READY and ui_shots.page_family(name) == "view-b", name
        assert ui_shots.NEEDS[name] == (("view", "shore") if name in SHORE else "view"), name
        assert all(s.startswith(("js:", "wait:")) or s in CLICKS or (name == "c-view-rename-focus" and s in keys)
                   for s in steps), name
        assert "localStorage.setItem('findaline.view', \"b\")" in ui_shots.page_storage(name), name
    assert ui_shots.LAYOUTS["c-view-rails"] == ui_shots.LAYOUTS["c-result-rails"]
    # the clip's run (the view's columns, no shore) leaves out the coast boxes' states before any load; a coastal run
    # saved before the view's columns leaves out every state of the view, the coast ones too (no wait for a view that
    # never comes)
    assert ui_shots.left_out_by_run(ui_shots.VIEW_STATES, {"view"}) == {n: ui_shots.LACKS["shore"] for n in SHORE}
    no_view = {n: ui_shots.LACKS["view"] for n in ui_shots.VIEW_STATES}
    assert ui_shots.left_out_by_run(ui_shots.VIEW_STATES, {"shore"}) == no_view
    assert ui_shots.left_out_by_run(ui_shots.VIEW_STATES, {"view", "shore"}) == {}
    # a desktop's state: a phone finds no header's middle; a phone's: a desktop has no pill
    desktop = [n for n, p in ui_shots.VIEW_STATES.items() if ui_shots.VIEW_DESKTOP in p[2]]
    phone = [n for n, p in ui_shots.VIEW_STATES.items() if ui_shots.VIEW_PHONE in p[2]]
    assert set(desktop) == {"c-view-other-run", "c-view-card", "c-view-card-folded", "c-view-rails", "c-view-stepper",
                            "c-view-rename", "c-view-rename-refused", "c-view-rename-focus", "c-view-compare-causes"}
    assert set(phone) == {"c-view-chips-held", "c-view-box-coarser", "c-view-box-shore", "c-view-stepper-half",
                          "c-view-stepper-low", "c-view-picker-low"}
    assert ui_shots.select_pages("c-view-") and set(ui_shots.VIEW_STATES) <= set(ui_shots.select_pages("c-view"))


def test_no_favourite_reaches_the_site():
    """A state that marks a favourite answers its request in the page first (the site's favourites stay as Home,
    Favourites and the walks see them); the refused one answers with the server's refusal."""
    for name, (_, _, steps, *_) in ui_shots.VIEW_STATES.items():
        marks = [k for k, s in enumerate(steps) if re.search(r"toggleFavourite|saveTo|\.vl-star'\)\?\.click|\.r-fav", s)]
        if not marks:
            continue
        stub = ui_shots.VIEW_FAV_REFUSED if name == "c-view-refused" else ui_shots.VIEW_FAV_STUB
        assert stub in steps and steps.index(stub) < marks[0], name
    assert "init.method === 'POST'" in ui_shots.VIEW_FAV_STUB and r"/\/favourites(\/folder)?$/" in ui_shots.VIEW_FAV_STUB
    assert "status: 500" in ui_shots.VIEW_FAV_REFUSED and "/api/profile" in ui_shots.VIEW_PROFILE_STUB


def test_todays_pages_are_pinned():
    """Every page that is not the view's pins today's page in the browser (tools/today_page.py: "today", the page's own
    answer), so the pictures of today's page stay today's whatever SpotColumns.tsx VIEW_DEFAULT is."""
    import today_page
    for name in set(ui_shots.PAGES) - set(ui_shots.VIEWS):
        script = ui_shots.page_storage(name)
        assert f"localStorage.setItem('{today_page.KEY}', \"today\")" in script and "removeItem('findaline.view')" not in script, name
    assert json.dumps("today") in today_page.SCRIPT.replace("'", '"')


def test_the_owners_header_has_edit_and_run_again():
    """G3: c-view-share's page gets a finished job of its run in the app's list (answered in the page, after the storage
    of its init script), so the header has "Edit & run again"; so do round 7's (PG) view states of the owner's header:
    the Rename box, a refused name in it, Compare's causes (its stub last, after its runs' script); no other page has
    the stub. The other init scripts are round 7's (PG: tests/test_ui_shots_round7.py)."""
    owners = ("c-view-share", "c-view-rename", "c-view-rename-refused", "c-view-rename-focus", "c-view-compare-causes")
    assert set(ui_shots.PAGE_SCRIPTS) == {*owners, "c-card-menu-search", "c-card-menu-low", "map-failed",
                                          "map-failed-shared", "map-too-large", "c-run-failed", "c-run-loading",
                                          "c-run-loading-gb"}
    for name in owners:
        assert ui_shots.page_storage(name).endswith(ui_shots.VIEW_JOB_STUB), name
    assert all(ui_shots.VIEW_JOB_STUB not in ui_shots.page_storage(n) for n in ui_shots.PAGES if n not in owners)
    assert "pathname !== '/api/jobs'" in ui_shots.VIEW_JOB_STUB and "init.method !== 'GET'" in ui_shots.VIEW_JOB_STUB
    assert "Edit & run again" in ui_shots.PAGES["c-view-share"][2][1]


def test_c4s_states():
    """C4's states: the stepper's pair waited for (the tree's second spot: both on), each end's button waited for off
    (the tree's first and last spot); the picker opened from the low stop waits for its focus inside it; the tree
    smallest first by the direction button, after the states that keep filters (its "Clear all" first) and last of
    all (the direction is kept in the browser)."""
    steps = {n: ui_shots.PAGES[n][2] for n in ("c-view-stepper", "c-view-stepper-half", "c-view-stepper-low",
                                               "c-view-stepper-first", "c-view-stepper-last")}
    for name in ("c-view-stepper", "c-view-stepper-half", "c-view-stepper-low"):
        assert ui_shots.VIEW_TREE_PICK % "1" in steps[name] and steps[name][-1] == ui_shots.VIEW_STEPPER, name
    assert ui_shots.VIEW_TREE_PICK % "0" in steps["c-view-stepper-first"]
    prev_off, next_off = ui_shots.VIEW_STEP_OFF("prev"), ui_shots.VIEW_STEP_OFF("next")
    assert steps["c-view-stepper-first"][-1] == prev_off and "vl-spot-prev" in prev_off
    assert ui_shots.VIEW_TREE_PICK % "tree.length - 1" in steps["c-view-stepper-last"]
    assert steps["c-view-stepper-last"][-1] == next_off and "disabled === true" in next_off
    assert "view.sectors.flatMap" in ui_shots.VIEW_TREE_PICK and "view.select(tree[" in ui_shots.VIEW_TREE_PICK
    picker = ui_shots.PAGES["c-view-picker-low"][2]
    assert "js:" + ui_shots.VIEW_HALF not in picker and picker[-1] == "wait:!!document.activeElement?.closest('.r-pop')"
    names, sort = list(ui_shots.VIEW_STATES), ui_shots.PAGES["c-view-sort-asc"][2]
    assert names[-1] == "c-view-sort-asc" and names.index("c-view-none") < names.index("c-view-sort-asc")
    assert sort[1] == "js:" + ui_shots.VIEW_PRESS % ".vl-clear"
    assert "wait:window.FINDALINE_VIEW.view.desc === false" in sort
    assert "js:" + ui_shots.VIEW_PRESS % ".vl-tree .vl-dir" in sort


# A step that changes the model's filters, which the page keeps in the browser ("findaline.filters") for the pass's
# later pages: a filter set or cleared, the kinds of lines shown, "Clear all"
FILTERS_CHANGED = re.compile(r"setFilters|clearFilters|setState|\.vl-clear")


def test_the_filters_panels_open():
    """A3 (line volume's round 7): a main filter's editor (the first chip's, Length) and More filters open on every
    device, each by its chip's press after a phone's sheet is raised to full (the stop of the list: at half the editor
    runs on under the screen's edge) and waited for open. That is all they do: no step of theirs changes a filter, and
    no page of the pass before them does (they show the chips and lines a run opens with), so they stand before
    c-view-note, the first state that sets one; c-view-sort-asc stays last."""
    editor, more = ui_shots.PAGES["c-view-editor"][2], ui_shots.PAGES["c-view-more"][2]
    half, press = "js:" + ui_shots.VIEW_HALF, "js:" + ui_shots.VIEW_PRESS
    assert editor == [ui_shots.VIEW_READY, half, half, press % ui_shots.VIEW_EDIT_CHIP, ui_shots.VIEW_EDITOR]
    assert more == [ui_shots.VIEW_READY, half, half, press % ui_shots.VIEW_MORE_CHIP, ui_shots.VIEW_MORE]
    # the first chip of the bar that opens an editor (Length's: no filter is set, so it is one button); the editor
    # waited for under its pressed chip, More filters' section in the list's flow under the chips
    assert ui_shots.VIEW_EDIT_CHIP == ".vl-filters .u-chips > .u-chip[aria-expanded]"
    assert "[aria-expanded=true]" in ui_shots.VIEW_EDITOR and ".vl-filters .r-editor" in ui_shots.VIEW_EDITOR
    assert ui_shots.VIEW_MORE_CHIP == ".vl-filters .u-chip.u-add" and "> section.r-more" in ui_shots.VIEW_MORE
    pages = list(ui_shots.PAGES)
    changing = [n for n in pages if any(FILTERS_CHANGED.search(s) for s in ui_shots.page_steps(ui_shots.PAGES[n][2]))]
    assert {"c-view-note", "c-view-none", "c-view-sort-asc"} <= set(changing)
    assert pages.index("c-view-editor") < pages.index("c-view-more") < min(pages.index(n) for n in changing)
    names = list(ui_shots.VIEW_STATES)
    assert names.index("c-view-more") + 1 == names.index("c-view-note") and names[-1] == "c-view-sort-asc"
