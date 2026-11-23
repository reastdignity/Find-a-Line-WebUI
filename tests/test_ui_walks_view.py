"""tools/ui_walks.py's walks of the result view (step 3d): each is today's result walk done in the view ("page":
"view", named by "mirrors"), and today's walks pin today's page (tools/today_page.py), so the two count the same task
on one tree whatever SpotColumns.tsx VIEW_DEFAULT is. The pure parts; the walks are run by hand (C3's summary)."""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import today_page  # noqa: E402
import ui_shots  # noqa: E402
import ui_walks as uw  # noqa: E402

VIEW = os.path.join(REPO, "viewer", "src", "result", "view")


def _source(*names) -> str:
    return "".join(open(os.path.join(VIEW, n), encoding="utf-8").read() for n in names)


def test_the_views_walks_mirror_todays():
    """Each view's walk names today's walk it mirrors: the same user, device and memory, its page "view"; every other
    walk opens today's page (the default "today"); the walks' data has no error."""
    assert set(uw.VIEW_WALKS) == {"VR2", "VF2", "VR3", "VR4"} and not set(uw.VIEW_WALKS) & set(uw.WALKS)
    for wid, walk in uw.VIEW_WALKS.items():
        today = uw.WALKS[walk["mirrors"]]
        assert walk["page"] == "view" and today.get("page", "today") == "today", wid
        assert (walk["user"], walk["device"], walk["memory"], walk["start"]) == \
            (today["user"], today["device"], today["memory"], today["start"]), wid
        assert walk.get("needs") == today.get("needs"), wid  # R3's fixture lacks a second run in both
    assert all(w.get("page", "today") == "today" for w in uw.WALKS.values())
    assert uw.walk_errors({**uw.WALKS, **uw.VIEW_WALKS}, ["admin", "walker"], ui_shots.DEVICES) == []
    assert uw.walk_errors({"X": {**uw.VIEW_WALKS["VR2"], "page": "b"}}, ["admin"], ui_shots.DEVICES) == \
        ["X: unknown result page 'b'"]


def test_each_result_page_has_its_init_script():
    """_context's init script per page: today's pinned ("today") or the view asked for ("b"), the page's own answers."""
    assert uw.RESULT_PAGES == {"today": today_page.SCRIPT, "view": today_page.VIEW}
    assert "'today'" in today_page.SCRIPT and "'b'" in today_page.VIEW


def test_the_view_has_what_its_walks_press():
    """The view's classes and names the walks rely on stand in its sources (a renamed one fails here, not as a dead end
    at the next run)."""
    src = _source("SpotList.tsx", "SpotDetails.tsx", "FanPanel.tsx", "ViewFilters.tsx", "SpotActions.tsx",
                  "FavouritePicker.tsx", "SpotColumns.tsx")
    for cls in ("vl-rows", "vl-main", "vl-dhead", "vl-sort", "r-filters", "r-fav", "r-newfolder"):
        assert re.search(rf'["\s]{cls}["\s]', src), cls
    # The names it presses, texts of the catalogue since step 3d's G6 (the sources call them by key).
    texts = json.load(open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8"))
    for key, name in (("ui.picker.label", "Favourite folders"), ("ui.picker.new_name", "New folder's name"),
                      ("ui.picker.add", "Add to favourites")):
        assert f'"{key}"' in src and texts[key] == name, key
    assert "VR4" == list(uw.VIEW_WALKS)[-1]  # it saves a favourite, as R4: last of its run


def test_the_views_walks_run_apart():
    """A run of every walk walks today's walks as before this round (R4 last); the view's only with --view or when
    --only names them, never with today's in one run (VR4 saves a favourite and a link, as R4 does)."""
    assert list(uw.walks_of()) == ["R1", "R2", "R3", "F1", "F2", "F3", "R4"] == list(uw.WALKS)
    assert list(uw.walks_of(view=True)) == ["VR2", "VF2", "VR3", "VR4"]
    assert list(uw.walks_of("VR4,VF2")) == ["VF2", "VR4"] and list(uw.walks_of("R2,F2")) == ["R2", "F2"]
    assert list(uw.walks_of("VR2", view=True)) == ["VR2"] and list(uw.walks_of("nothing")) == []
    for only, view in (("R2,VR2", False), ("R2", True)):
        try:
            uw.walks_of(only, view)
        except ValueError as e:
            assert "run apart" in str(e)
        else:
            raise AssertionError((only, view))
