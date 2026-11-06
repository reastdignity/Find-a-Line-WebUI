"""The window of the area download (tools/area_download_tui.py), driven headless by Textual's pilot: the mouse and the
keys, Start and Stop asking first, the state read from the state folder. What it starts is made up here; a start and
the links themselves are tests/test_area_rows.py's."""

import asyncio
import json
import os
import sys

import pytest

pytest.importorskip("textual")
from textual.widgets import Collapsible, Input  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import area_download as ad  # noqa: E402
import area_download_tui as tui  # noqa: E402
import area_rows as ar  # noqa: E402

SIZE = (112, 30)


def _row(name, title, continent="Europe", source="austria", km2=1000):
    return ar.Row(name, title, continent, f"osm:{title}", source, 1.0, True, km2)


ROWS = [_row("austria", "Austria", km2=84387), _row("czechia", "Czechia", source="czechia"),
        _row("germany-bavaria", "Germany: Bavaria"), _row("poland", "Poland", source="geoportal"),
        _row("utah", "United States: Utah", "North America", "usa"),
        _row("australia-tasmania", "Australia: Tasmania", "Oceania", "tasmania")]


@pytest.fixture
def settings(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    return ar.Settings(str(state), {"cache": ar.Target("cache", str(tmp_path / "app")),
                                    "NAS": ar.Target("NAS", str(tmp_path / "local"), str(tmp_path / "share"), 200.0)},
                       "cache", {"poland": {"target": "NAS"}})


class Started(list):
    """Stands in for ar.start."""

    def __call__(self, row, target, settings):
        self.append((row.name, target.label))
        return 1


def _app(settings, rows=ROWS, **more):
    started = Started()
    app = tui.Downloads(settings, rows, begin=started, **more)
    return app, started


def _state(settings, name, stage, **more):
    ad.write_state(settings.state_dir, name, {"name": name, "stage": stage, "tiles_done": 40, "tiles_total": 100,
                                              "mb": 2500.0, **more})


def _drive(app, body):
    async def run():
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await body(pilot)
            await app.workers.wait_for_complete()
            await pilot.pause()
    asyncio.run(run())


def _text(app, name):
    return str(app.row_of(name).query_one(".state").render())


def _shown(app):
    return [row.row.name for row in app.area_rows() if row.display]


async def _tick(pilot, name):
    await pilot.click(f"#box-{name}")
    await pilot.pause()


def test_the_whole_list_by_continent(settings):
    settings.extra = [{"name": "utah", "title": "United States: Utah", "continent": "North America",
                       "area": "osm:Utah", "source": "usa"}]
    settings.rows = {}
    app, _ = _app(settings, ar.rows_of(settings))

    async def body(pilot):
        groups = {group.id: group.title for group in app.query(Collapsible)}
        assert groups == {"group-europe": "Europe (37)", "group-north-america": "North America (9)",
                          "group-oceania": "Oceania (3)"}
        assert len(app.area_rows()) == 49
    _drive(app, body)


def test_a_click_ticks_a_row_and_the_counts_follow(settings):
    app, _ = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        assert app.row_of("austria").ticked
        assert "1 ticked (84 387 km²)" in str(app.query_one("#summary").render())
        assert app.query_one("#group-europe", Collapsible).title == "Europe (4, 1 ticked)"
        await _tick(pilot, "austria")
        assert not app.row_of("austria").ticked
        assert app.query_one("#group-europe", Collapsible).title == "Europe (4)"
    _drive(app, body)


def test_a_click_changes_where_the_tiles_go_and_it_is_kept(settings):
    app, _ = _app(settings)

    async def body(pilot):
        row = app.row_of("austria")
        assert row.target == "cache"
        await pilot.click(row.query_one(tui.TargetCell))
        await pilot.pause()
        assert row.target == "NAS" and row.query_one(tui.TargetCell).has_class("-share")
    _drive(app, body)
    assert ar.targets_chosen(settings) == {"austria": "NAS"}


def test_the_settings_give_the_first_target(settings):
    app, _ = _app(settings)

    async def body(pilot):
        assert app.row_of("poland").target == "NAS" and app.row_of("austria").target == "cache"
    _drive(app, body)


def test_where_a_download_goes_cannot_change_under_it(settings):
    _state(settings, "austria", "downloading")
    app, _ = _app(settings)

    async def body(pilot):
        row = app.row_of("austria")
        await pilot.click(row.query_one(tui.TargetCell))
        await pilot.pause()
        assert row.target == "cache"
    _drive(app, body)


def test_start_asks_first(settings):
    app, started = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        await _tick(pilot, "czechia")
        await pilot.click("#start")
        await pilot.pause()
        assert isinstance(app.screen, tui.Confirm)
        text = str(app.screen.query_one("#dialog-text").render())
        assert "Austria" in text and "Czechia" in text and "new" in text
        assert "keep running" in text
        assert started == []
        await pilot.click("#cancel")
        await pilot.pause()
        assert not isinstance(app.screen, tui.Confirm)
        assert started == [] and app.row_of("austria").ticked

        await pilot.click("#start")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert started == [("austria", "cache"), ("czechia", "cache")]
        assert not app.row_of("austria").ticked
        assert _text(app, "austria") == "starting"
    _drive(app, body)


def test_escape_cancels_the_question(settings):
    app, started = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, tui.Confirm)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, tui.Confirm)
    _drive(app, body)
    assert started == []


def test_start_with_nothing_ticked_asks_nothing(settings):
    app, started = _app(settings)

    async def body(pilot):
        await pilot.click("#start")
        await pilot.pause()
        assert not isinstance(app.screen, tui.Confirm)
    _drive(app, body)
    assert started == []


def test_a_download_running_is_not_started_again(settings):
    _state(settings, "austria", "downloading")
    app, started = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        await pilot.click("#start")
        await pilot.pause()
        assert not isinstance(app.screen, tui.Confirm)
    _drive(app, body)
    assert started == []


def test_a_stopped_download_resumes(settings):
    _state(settings, "austria", "stopped")
    app, started = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        await pilot.click("#start")
        await pilot.pause()
        assert "resumes" in str(app.screen.query_one("#dialog-text").render())
        await pilot.click("#yes")
        await pilot.pause()
    _drive(app, body)
    assert started == [("austria", "cache")]


def test_a_finished_area_cannot_be_ticked(settings):
    _state(settings, "czechia", "done")
    app, _ = _app(settings)

    async def body(pilot):
        assert app.row_of("czechia").box.disabled
        assert _text(app, "czechia") == "done, 2.5 GB"
    _drive(app, body)


def test_the_links_come_first_and_a_row_without_them_stays(settings):
    calls = []

    def links(needed, state_dir):
        calls.append(list(needed))
        return [link for link in needed if link.path.endswith("nmpt")]   # the UAC window was refused for one
    app, started = _app(settings, links=links)

    async def body(pilot):
        await _tick(pilot, "poland")
        await _tick(pilot, "austria")
        await pilot.click("#start")
        await pilot.pause()
        text = str(app.screen.query_one("#dialog-text").render())
        assert "2 tile folders linked to the share" in text and "NAS:" in text
        await pilot.click("#yes")
        await pilot.pause()
        await app.workers.wait_for_complete()
    _drive(app, body)
    assert len(calls) == 1 and len(calls[0]) == 2
    assert started == [("austria", "cache")]


def test_tiles_in_the_way_are_named_and_the_others_start(settings):
    folder = os.path.join(settings.targets["NAS"].data_dir, "cache", "poland", "nmt")
    os.makedirs(folder)
    with open(os.path.join(folder, "tile.tif"), "wb") as f:
        f.write(b"x")
    app, started = _app(settings)

    async def body(pilot):
        await _tick(pilot, "poland")
        await _tick(pilot, "austria")
        await pilot.click("#start")
        await pilot.pause()
        text = str(app.screen.query_one("#dialog-text").render())
        assert "Not started:" in text and "holds tiles on this disk" in text
        await pilot.click("#yes")
        await pilot.pause()
        await app.workers.wait_for_complete()
    _drive(app, body)
    assert started == [("austria", "cache")]


def test_stop_asks_first_and_leaves_the_stop_file(settings):
    _state(settings, "austria", "downloading")
    app, _ = _app(settings)
    stop_file = ad.state_file(settings.state_dir, "austria", ".stop")

    async def body(pilot):
        await _tick(pilot, "austria")
        await pilot.click("#stop")
        await pilot.pause()
        assert isinstance(app.screen, tui.Confirm) and not os.path.exists(stop_file)
        await pilot.click("#yes")
        await pilot.pause()
        assert os.path.exists(stop_file) and not app.row_of("austria").ticked
    _drive(app, body)


def test_stop_needs_a_download(settings):
    app, _ = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        await pilot.click("#stop")
        await pilot.pause()
        assert not isinstance(app.screen, tui.Confirm)
    _drive(app, body)


def test_the_state_comes_from_the_state_folder(settings):
    """Also for a download the window did not start, and it keeps coming."""
    app, _ = _app(settings)

    async def body(pilot):
        assert _text(app, "austria") == "-"
        _state(settings, "austria", "downloading")
        app.refresh_states()
        await pilot.pause()
        assert "40 %" in _text(app, "austria")
        assert "1 downloading" in str(app.query_one("#summary").render())
        _state(settings, "austria", "listing", index_done=12, index_total=2288)
        app.refresh_states()
        await pilot.pause()
        assert _text(app, "austria") == "listing, index 12 of 2,288"
    _drive(app, body)


@pytest.mark.parametrize("stage, message, failed, text", [
    ("needs attention", "3 tiles failed", 3, "needs attention: 3 tiles failed"),
    ("waiting", "index down", 0, "waiting: index down"),
    ("stopped", "", 0, "stopped"),
    ("done", "", 2, "done, 2.5 GB, 2 failed"),
])
def test_what_a_state_says(settings, stage, message, failed, text):
    _state(settings, "austria", stage, message=message, failed=failed)
    app, _ = _app(settings)

    async def body(pilot):
        assert _text(app, "austria") == text
    _drive(app, body)


def test_a_state_without_news_is_called_so(settings):
    """After a restart of the PC: its download is gone, so it can be started again."""
    _state(settings, "austria", "downloading")
    path = ad.state_file(settings.state_dir, "austria", ".state.json")
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    state["updated"] = "2026-01-01T00:00:00Z"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    app, started = _app(settings)

    async def body(pilot):
        assert _text(app, "austria").endswith(", no news")
        await _tick(pilot, "austria")
        await pilot.click("#start")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
    _drive(app, body)
    assert started == [("austria", "cache")]


def test_the_filter(settings):
    app, _ = _app(settings)

    async def body(pilot):
        await pilot.press("slash")
        await pilot.press(*"germ")
        await pilot.pause()
        assert _shown(app) == ["germany-bavaria"]
        assert app.query_one("#group-europe", Collapsible).display
        assert not app.query_one("#group-oceania", Collapsible).display
        await pilot.press("escape")
        await pilot.pause()
        assert len(_shown(app)) == len(ROWS) and app.query_one("#filter", Input).value == ""
        assert isinstance(app.focused, (tui.Box,)) or app.focused.__class__.__name__ == "CollapsibleTitle"
    _drive(app, body)


def test_a_click_on_a_continent_folds_it(settings):
    app, _ = _app(settings)

    async def body(pilot):
        group = app.query_one("#group-north-america", Collapsible)
        await pilot.click(group.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert group.collapsed
    _drive(app, body)


def test_everything_has_a_key(settings):
    """A text console has no mouse."""
    app, started = _app(settings)

    async def body(pilot):
        assert app.focused.id == "box-austria"
        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "box-czechia"
        await pilot.press("up")
        await pilot.pause()
        assert app.focused.id == "box-austria"
        await pilot.press("space")
        await pilot.pause()
        assert app.row_of("austria").ticked
        await pilot.press("t")
        await pilot.pause()
        assert app.row_of("austria").target == "NAS"
        await pilot.press("t")
        await pilot.pause()
        assert app.row_of("austria").target == "cache"
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("tab", "enter")
        await pilot.pause()
    _drive(app, body)
    assert started == [("austria", "cache")]


def test_up_and_down_pass_a_finished_area(settings):
    _state(settings, "czechia", "done")
    app, _ = _app(settings)

    async def body(pilot):
        await pilot.press("down")
        await pilot.pause()
        assert app.focused.id == "box-germany-bavaria"
    _drive(app, body)


def test_free_space_and_contact_in_the_header(settings):
    settings.contact = "someone@example.org"
    app, _ = _app(settings)

    async def body(pilot):
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = str(app.query_one("#top-free").render())
        assert "contact: set" in text and "someone" not in text
        assert "cache: ?" in text and "NAS: ?" in text   # neither folder exists
    _drive(app, body)


def test_a_target_called_like_its_drive(settings):
    settings.targets["Z:"] = ar.Target("Z:", settings.targets["NAS"].data_dir)
    app, _ = _app(settings)

    async def body(pilot):
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = str(app.query_one("#top-free").render())
        assert "Z: ?" in text and "::" not in text
    _drive(app, body)


def test_settings_that_cannot_be_used_end_with_their_text(tmp_path, capsys):
    assert tui.run(str(tmp_path / "none.json")) == 2
    assert "none.json" in capsys.readouterr().err
