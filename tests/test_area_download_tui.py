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
    country, _, region = title.partition(": ")
    return ar.Row(name, title, continent, country, region or f"Whole country · {source}", f"osm:{title}", source, 1.0,
                  True, km2)


ROWS = [_row("austria", "Austria", km2=84387), _row("czechia", "Czechia", source="czechia"),
        _row("germany-bavaria", "Germany: Bavaria"), _row("germany-hesse", "Germany: Hesse", source="hesse"),
        _row("poland", "Poland", source="geoportal"),
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


def _group(app, *names):
    return app.query_one("#" + tui.Downloads.group_id(*names), Collapsible)


async def _unfold(pilot, name):
    """The row's country group unfolded (folded at start without a state), if it has one."""
    group = pilot.app.row_of(name).parent.parent   # Contents, then its group
    group.collapsed = False
    await pilot.pause()


async def _tick(pilot, name):
    """A click on the row's box."""
    await _unfold(pilot, name)
    await pilot.click(f"#box-{name}")
    await pilot.pause()


def test_the_whole_list_by_continent_and_country(settings):
    """A territory under its country (Saint-Barthélemy under France in Europe, Puerto Rico under the United States);
    a group only for a country of two or more rows (the United States with the extra Utah), a country of one row its
    row by its title in the continent, in the countries' order."""
    settings.extra = [{"name": "utah", "title": "United States: Utah", "continent": "North America",
                       "area": "osm:Utah", "source": "usa"}]
    settings.rows = {}
    app, _ = _app(settings, ar.rows_of(settings))

    async def body(pilot):
        groups = {group.id: group.title for group in app.query(Collapsible)}
        assert groups == {
            "group-europe": "Europe (49)", "group-europe-finland": "Finland (2)", "group-europe-germany": "Germany (16)",
            "group-europe-italy": "Italy (6)", "group-europe-norway": "Norway (3)", "group-europe-spain": "Spain (2)",
            "group-europe-united-kingdom": "United Kingdom (4)",
            "group-north-america": "North America (18)", "group-north-america-canada": "Canada (3)",
            "group-north-america-france": "France (5)", "group-north-america-netherlands": "Netherlands (3)",
            "group-north-america-united-states": "United States (5)", "group-oceania": "Oceania (4)",
            "group-oceania-australia": "Australia (3)", "group-south-america": "South America (3)",
            "group-asia": "Asia (1)", "group-africa": "Africa (2)", "group-africa-france": "France (2)"}
        assert len(app.area_rows()) == 77
        assert [row.row.name for row in _group(app, "North America", "France").query(tui.AreaRow)] == [
            "france-guadeloupe", "france-martinique", "saint-barthelemy", "saint-martin-france",
            "saint-pierre-and-miquelon"]
        assert app.row_of("france").parent.parent.id == "group-europe"   # France's only row in Europe: flat
        assert str(app.row_of("france").query_one(".name").render()) == "France"
        assert app.row_of("france-french-guiana").parent.parent.id == "group-south-america"
        assert str(app.row_of("france-french-guiana").query_one(".name").render()) == "France: French Guiana"
        assert str(app.row_of("netherlands-saba").query_one(".name").render()) == "Saba"
        assert [row.row.name for row in _group(app, "North America", "United States").query(tui.AreaRow)] == [
            "united-states", "united-states-alaska", "puerto-rico", "u-s-virgin-islands", "utah"]
        assert str(app.row_of("italy").query_one(".name").render()) == "Whole country · tinitaly"
        assert str(app.row_of("germany-bavaria").query_one(".name").render()) == "Bavaria"
        assert str(app.row_of("portugal-madeira").query_one(".name").render()) == "Portugal: Madeira"
        assert str(app.row_of("austria").query_one(".name").render()) == "Austria"
        europe = _group(app, "Europe").query_one("Contents").children
        assert [child.id for child in europe[:9]] == [
            "row-austria", "row-czechia", "row-denmark", "row-estonia", "row-faroe-islands", "group-europe-finland",
            "row-france", "group-europe-germany", "row-iceland"]
    _drive(app, body)


def test_folded_at_start_but_a_country_with_a_download(settings):
    """Only a country's group folds; a row of a country of one row is always on the screen."""
    app, _ = _app(settings)

    async def body(pilot):
        assert _folds(app) == {"group-europe": False, "group-europe-germany": True, "group-north-america": False,
                               "group-oceania": False}
        assert app.focused.parent.id == "group-europe"   # the first title: nothing of the list is above it
        assert app.row_of("austria").region.height == 1
    _drive(app, body)
    _state(settings, "germany-hesse", "stopped")
    app, _ = _app(settings)

    async def opened(pilot):
        assert not _group(app, "Europe", "Germany").collapsed
    _drive(app, opened)


def test_a_continent_without_rows_has_no_group(settings):
    """Africa is in CONTINENTS before any row lies there: no group for it, until a row does, in its place."""
    assert "Africa" in ar.CONTINENTS
    settings.rows = {}
    catalogue = [row for row in ar.rows_of(settings) if row.continent != "Africa"]   # as before La Réunion
    app, _ = _app(settings, catalogue)

    async def none(pilot):
        assert "group-africa" not in [group.id for group in app.query(".continent")]
    _drive(app, none)
    other = ar.Row("x-other", "X", "Other", "X", "X", "osm:X", "usa", 1.0, False, 1)
    rows = sorted(catalogue + [_row("reunion", "France: Réunion", "Africa", "france"), other], key=ar.order_of)
    app, _ = _app(settings, rows)

    async def body(pilot):
        assert [group.id for group in app.query(".continent")] == [
            "group-europe", "group-north-america", "group-oceania", "group-south-america", "group-asia",
            "group-africa", "group-other"]
    _drive(app, body)


def test_two_spellings_of_a_country_open_as_one_group(settings):
    """An extra row's "france" beside the catalogue's France (two groups of one id: the window would not open)."""
    settings.rows = {}
    settings.extra = [{"name": "brittany", "title": "Brittany", "country": "france", "continent": "Europe",
                       "area": "osm:X", "source": "france"},
                      {"name": "corsica", "title": "Corsica", "country": "FRANCE", "continent": "europe",
                       "area": "osm:Y", "source": "france"}]
    app, _ = _app(settings, ar.rows_of(settings))

    async def body(pilot):
        france = _group(app, "Europe", "France")
        assert [row.row.name for row in france.query(tui.AreaRow)] == ["france", "brittany", "corsica"]
        assert france.title == "France (3)"
        assert len(app.query("#group-europe")) == 1
    _drive(app, body)


def test_everything_open_at_start_when_asked(settings, monkeypatch):
    monkeypatch.setattr(tui, "FOLD_AT_START", False)
    app, _ = _app(settings)

    async def body(pilot):
        assert not any(group.collapsed for group in app.query(Collapsible))
    _drive(app, body)


def test_a_country_of_one_row_with_its_own_level(settings, monkeypatch):
    """The switch on: every country a group, every row by its label."""
    monkeypatch.setattr(tui, "SINGLE_ROW_COUNTRY_LEVEL", True)
    app, _ = _app(settings)

    async def body(pilot):
        assert _folds(app) == {
            "group-europe": False, "group-europe-austria": True, "group-europe-czechia": True,
            "group-europe-germany": True, "group-europe-poland": True, "group-north-america": False,
            "group-north-america-united-states": True, "group-oceania": False, "group-oceania-australia": True}
        assert app.row_of("austria").parent.parent.id == "group-europe-austria"
        assert str(app.row_of("austria").query_one(".name").render()) == "Whole country · austria"
        assert str(app.row_of("utah").query_one(".name").render()) == "Utah"
    _drive(app, body)


def test_a_country_of_one_row_sits_in_its_continent(settings):
    app, _ = _app(settings)

    async def body(pilot):
        assert app.row_of("austria").parent.parent.id == "group-europe"
        assert str(app.row_of("austria").query_one(".name").render()) == "Austria"
        assert str(app.row_of("utah").query_one(".name").render()) == "United States: Utah"
        assert str(app.row_of("germany-hesse").query_one(".name").render()) == "Hesse"
    _drive(app, body)


@pytest.mark.parametrize("level, many", [(False, False), (True, False), (False, True)])
def test_the_columns_line_up_with_the_header(settings, monkeypatch, level, many):
    """At a country's deeper indent and at a continent's; the right ones too, with the list's scrollbar shown or not
    (the list keeps its gutter, the header a padding as wide)."""
    monkeypatch.setattr(tui, "SINGLE_ROW_COUNTRY_LEVEL", level)
    more = [_row(f"spain-{k}", f"Spain: Region {k}", source="spain") for k in range(40)] if many else []
    app, _ = _app(settings, ROWS + more)

    async def body(pilot):
        for group in app.query(Collapsible):
            group.collapsed = False
        await pilot.pause()
        assert app.query_one("#areas").show_vertical_scrollbar == many
        head = app.query_one("#head")
        for cell in (".res", ".layers", ".km2", ".state", ".target"):
            x = head.query_one(cell).region.x
            assert app.row_of("germany-bavaria").query_one(cell).region.x == x, cell
            assert app.row_of("austria").query_one(cell).region.x == x
        assert app.row_of("germany-bavaria").query_one(".name").region.x == head.query_one(".name").region.x
    _drive(app, body)


def test_a_tick_after_the_window_closed_does_nothing(settings):
    """The intervals and the free-space thread can call in after the screen's widgets were removed (a loaded CI runner
    hit the state interval so: NoMatches '#summary'); each of them is called here once the window is gone."""
    app, _ = _app(settings)

    async def body(pilot):
        assert app.query_one("#summary").render()
    _drive(app, body)
    assert not app.area_rows()   # what the CI runner saw: the rows already removed
    app.refresh_states()
    app.refresh_summary()
    app._set_free({"cache": 10.0, "NAS": None})


def test_a_click_ticks_a_row_and_the_counts_follow(settings):
    app, _ = _app(settings)

    async def body(pilot):
        await _tick(pilot, "austria")
        assert app.row_of("austria").ticked
        assert "1 ticked (84 387 km²)" in str(app.query_one("#summary").render())
        assert app.query_one("#group-europe", Collapsible).title == "Europe (5, 1 ticked)"
        assert _group(app, "Europe", "Germany").title == "Germany (2)"
        await _tick(pilot, "germany-bavaria")
        assert app.query_one("#group-europe", Collapsible).title == "Europe (5, 2 ticked)"
        assert _group(app, "Europe", "Germany").title == "Germany (2, 1 ticked)"
        await _tick(pilot, "austria")
        assert not app.row_of("austria").ticked
        assert app.query_one("#group-europe", Collapsible).title == "Europe (5, 1 ticked)"
        assert _group(app, "Europe", "Germany").title == "Germany (2, 1 ticked)"
    _drive(app, body)


def test_a_click_changes_where_the_tiles_go_and_it_is_kept(settings):
    app, _ = _app(settings)

    async def body(pilot):
        row = app.row_of("austria")
        assert row.target == "cache"
        await _unfold(pilot, "austria")
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


def test_the_question_names_a_region_by_its_full_title(settings):
    app, _ = _app(settings)

    async def body(pilot):
        await _tick(pilot, "germany-bavaria")
        await pilot.click("#start")
        await pilot.pause()
        assert "Germany: Bavaria" in str(app.screen.query_one("#dialog-text").render())
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


def _folds(app):
    return {group.id: group.collapsed for group in app.query(Collapsible)}


def test_the_filter(settings):
    """The groups with a match shown and open, the others hidden; cleared, the folds from before come back."""
    app, _ = _app(settings)

    async def body(pilot):
        _group(app, "Oceania").collapsed = True
        await pilot.pause()
        before = _folds(app)
        assert before["group-europe-germany"]
        await pilot.press("slash")
        await pilot.press(*"germ")
        await pilot.pause()
        assert _shown(app) == ["germany-bavaria", "germany-hesse"]
        assert app.query_one("#group-europe", Collapsible).display
        assert _group(app, "Europe", "Germany").display and not _group(app, "Europe", "Germany").collapsed
        assert not app.row_of("austria").display
        assert not app.query_one("#group-oceania", Collapsible).display
        await pilot.press("space", "b", "a", "v")   # "germ bav"
        await pilot.pause()
        assert _shown(app) == ["germany-bavaria"]
        await pilot.press("escape")
        await pilot.pause()
        assert len(_shown(app)) == len(ROWS) and app.query_one("#filter", Input).value == ""
        assert _folds(app) == before
        assert all(group.display for group in app.query(Collapsible))
        assert app.focused.__class__.__name__ == "CollapsibleTitle"
        assert app.focused.parent.id == "group-europe"   # the first thing shown after the filter
    _drive(app, body)


def test_the_filter_finds_a_country_and_its_territories(settings):
    rows = ROWS + [ar.Row("puerto-rico", "Puerto Rico", "North America", "United States", "Puerto Rico",
                          "osm:Puerto Rico", "usa", 1.0, False, 9000)]
    app, _ = _app(settings, rows)

    async def body(pilot):
        app.query_one("#filter", Input).value = "united states"
        await pilot.pause()
        assert _shown(app) == ["utah", "puerto-rico"]
        assert not _group(app, "North America", "United States").collapsed
        app.query_one("#filter", Input).value = ""
        await pilot.pause()
        assert _group(app, "North America", "United States").collapsed
    _drive(app, body)


def test_a_click_on_a_continent_folds_it_and_its_countries_keep_theirs(settings):
    app, _ = _app(settings)

    async def body(pilot):
        group = app.query_one("#group-europe", Collapsible)
        country = _group(app, "Europe", "Germany")
        await pilot.click(group.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert group.collapsed
        await pilot.click(group.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert not group.collapsed and country.collapsed
        await pilot.click(country.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert not country.collapsed and app.row_of("germany-hesse").region.height == 1
        await pilot.click(country.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert country.collapsed and not group.collapsed
    _drive(app, body)


async def _keys(pilot, *keys):
    for key in keys:
        await pilot.press(key)
        await pilot.pause()


def _at(app):
    """What has the focus: a box's id, or the group of a title."""
    focused = app.focused
    return focused.id if isinstance(focused, tui.Box) else f"title {focused.parent.id}"


def test_everything_has_a_key(settings):
    """A text console has no mouse. Up and down walk the titles and the boxes on the screen; Enter folds a title."""
    app, started = _app(settings)

    async def body(pilot):
        assert _at(app) == "title group-europe"
        await _keys(pilot, "down")
        assert _at(app) == "box-austria"
        await _keys(pilot, "down", "down")
        assert _at(app) == "title group-europe-germany"
        await _keys(pilot, "down")
        assert _at(app) == "box-poland"   # Germany's boxes folded
        await _keys(pilot, "up", "enter", "down")
        assert _at(app) == "box-germany-bavaria"
        await _keys(pilot, "up", "up", "up")
        assert _at(app) == "box-austria"
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
        await _keys(pilot, "down")
        assert _at(app) == "box-austria"
        await _keys(pilot, "down")
        assert _at(app) == "title group-europe-germany"
        await _keys(pilot, "up")
        assert _at(app) == "box-austria"
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
