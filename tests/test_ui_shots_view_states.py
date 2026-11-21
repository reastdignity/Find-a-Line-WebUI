"""tools/ui_shots.py's states of the result view added in step 3d (VIEW_STATES: the features joined in step 3c, the
lists of wave B's workers and of the screenshot gate) and the pin of today's page in every other page: the pure parts
(the pictures are taken by hand: .claude/rules/viewer.md)."""
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
}
SHORE = {"c-view-boxes", "c-view-chips-held", "c-view-box-coarser", "c-view-box-shore", "c-view-link-centre"}
CLICKS = {ui_shots.VIEW_DESKTOP, ui_shots.VIEW_PHONE, ".r-card .r-fold"}  # the only steps that are clicks


def test_every_listed_state_has_its_page():
    assert set(COVERED.values()) <= set(ui_shots.PAGES), set(COVERED.values()) - set(ui_shots.PAGES)
    assert set(ui_shots.VIEW_STATES) <= set(COVERED.values()) | {"c-view-measuring"}


def test_the_states_open_the_view():
    """Each state is a page of the view (the flag "b"; the app's result, a run's map.html or a share link's page),
    waits for the view first, needs the view's columns (the coast boxes' an uncertain shore), and is made of scripts,
    waits and only the clicks that keep a state to one kind of device."""
    for name, (ui, hash_, steps, *who) in ui_shots.VIEW_STATES.items():
        assert ui_shots.PAGES[name] == (ui, hash_, steps, *who) and ui_shots.VIEWS[name] == "b", name
        assert (ui, hash_) in (("c", "#run={run}"), ("map", ""), ("map", "#line={line}"), ("shared", "#line={line}")), name
        assert steps[0] == ui_shots.VIEW_READY and ui_shots.page_family(name) == "view-b", name
        assert ui_shots.NEEDS[name] == ("shore" if name in SHORE else "view"), name
        assert all(s.startswith(("js:", "wait:")) or s in CLICKS for s in steps), name
        assert "localStorage.setItem('findaline.view', \"b\")" in ui_shots.page_storage(name), name
    assert ui_shots.LAYOUTS["c-view-rails"] == ui_shots.LAYOUTS["c-result-rails"]
    # the clip's run (the view's columns, no shore) leaves out the coast boxes' states before any load
    assert set(ui_shots.left_out_by_run(ui_shots.VIEW_STATES, {"view"})) == SHORE
    # a desktop's state: a phone finds no header's middle; a phone's: a desktop has no pill
    desktop = [n for n, p in ui_shots.VIEW_STATES.items() if ui_shots.VIEW_DESKTOP in p[2]]
    phone = [n for n, p in ui_shots.VIEW_STATES.items() if ui_shots.VIEW_PHONE in p[2]]
    assert set(desktop) == {"c-view-other-run", "c-view-card", "c-view-card-folded", "c-view-rails"}
    assert set(phone) == {"c-view-chips-held", "c-view-box-coarser", "c-view-box-shore"}
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
