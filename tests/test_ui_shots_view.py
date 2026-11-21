"""tools/ui_shots.py's states of the result view (docs/line-volume/spec-view.md part B): the page's flag per state
(VIEWS, page_storage), the feature a run needs for them (the view's columns in its store) and their steps. The
pure parts; the pictures are taken by hand (.claude/rules/viewer.md)."""
import json
import os
import sys

import pyarrow as pa

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import ui_shots  # noqa: E402


def _run(folder, columns, store=True) -> str:
    """A run's folder with a lines.arrow of the named columns and a run.json (with the block "store" or without)."""
    folder.mkdir()
    table = pa.table({name: pa.array([0, 1, 2], type=pa.uint32()) for name in columns})
    with pa.OSFile(str(folder / "lines.arrow"), "wb") as sink, pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    meta = {"params": {}, **({"store": {"format": 1, "lines": 3, "bytes": 1, "sha256": "0" * 16}} if store else {})}
    (folder / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    return str(folder)


def test_a_run_has_the_view_when_its_store_holds_the_columns(tmp_path):
    with_columns = _run(tmp_path / "view", ["len", "spot", "top", "by_spot"])
    assert ui_shots.run_features(with_columns) == {"view"} and ui_shots.store_has_view(with_columns)
    assert ui_shots.run_features(_run(tmp_path / "before", ["len"])) == set()  # a store saved before the view's columns
    # a store the page would not read (no block in run.json: the run opens from data.js, in today's page)
    assert ui_shots.run_features(_run(tmp_path / "unlisted", ["len", "spot"], store=False)) == set()
    old = tmp_path / "old"
    old.mkdir()
    (old / "run.json").write_text(json.dumps({"params": {}, "store": {"format": 1}}), encoding="utf-8")
    assert ui_shots.run_features(str(old)) == set() and not ui_shots.store_has_view(str(old))  # no lines.arrow
    (old / "lines.arrow").write_bytes(b"not an Arrow file")
    assert not ui_shots.store_has_view(str(old))


def test_the_views_states():
    """Every state of the view is a page of the app's result with the flag "b", left out for a run without the
    view's columns, and waits for the view to be drawn before anything else; every other page pins today's page."""
    assert ui_shots.VIEWS and set(ui_shots.VIEWS) <= set(ui_shots.PAGES) and set(ui_shots.VIEWS.values()) == {"b"}
    for name in set(ui_shots.VIEWS) - set(ui_shots.VIEW_STATES):  # step 3d's: tests/test_ui_shots_view_states.py
        ui, hash_, steps = ui_shots.PAGES[name][:3]
        assert (ui, hash_) == ("c", "#run={run}") and steps[0] == ui_shots.VIEW_READY == "wait:window.FINDALINE_VIEW", name
        assert ui_shots.NEEDS[name] == "view" and all(step.startswith(("js:", "wait:")) for step in steps), name
        assert "localStorage.setItem('findaline.view', \"b\")" in ui_shots.page_storage(name)
    assert "view" in ui_shots.LACKS
    for name in set(ui_shots.PAGES) - set(ui_shots.VIEWS):  # today's page pinned (tools/today_page.py)
        script = ui_shots.page_storage(name)
        assert "localStorage.setItem('findaline.view', \"today\")" in script and "\"b\")" not in script, name
    # a run without the columns: the view's states are left out before any load, with the reason
    left = ui_shots.left_out_by_run(ui_shots.PAGES, {"lift", "found"})
    assert set(ui_shots.VIEWS) <= set(left) and left["c-view"] == ui_shots.LACKS["view"]
    assert not set(ui_shots.VIEWS) & set(ui_shots.left_out_by_run(ui_shots.PAGES, {"view", "shore"}))
    # the steps' scripts name the page's own objects
    assert "window.FINDALINE_VIEW" in ui_shots.VIEW_AT and "map.zoomOf(1)" in ui_shots.VIEW_AT % 1
    # c-view-area: the line then in the middle of the map's part between the switch and the bar's foot (a phone's
    # foot covers the middle of the map's box: its number was not drawn)
    assert ui_shots.PAGES["c-view-area"][2][-1] == "js:" + ui_shots.VIEW_FREE
    assert ".v-switch" in ui_shots.VIEW_FREE and ".v-foot" in ui_shots.VIEW_FREE and "panBy" in ui_shots.VIEW_FREE
    assert "map.pickAt(" in ui_shots.VIEW_CROWDED and "view.setBest(30)" in ui_shots.VIEW_DO % "view.setBest(30)"
    # one state raises a phone's sheet to half (the view opens with it low)
    assert "js:" + ui_shots.VIEW_HALF in ui_shots.PAGES["c-view-half"][2] and "ArrowUp" in ui_shots.VIEW_HALF
