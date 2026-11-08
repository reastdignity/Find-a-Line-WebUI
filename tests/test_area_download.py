"""The download of a whole area (tools/area_download.py), offline: sources.download_layers going on after a failed
tile only when asked, a pass over a made-up layer (the tiles failing, an index out of reach, too many failures in a
row, the disk), the supervisor's passes, and what is shown of them."""

import dataclasses
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import area_download as ad  # noqa: E402
import cache  # noqa: E402
import sources as src  # noqa: E402
from sources.layer import Fetched, Layer  # noqa: E402


class FakeLayer(Layer):
    """Tiles 0..n-1, each a small file; those in `bad` fail, as a sheet the server cannot give."""
    description = "fake terrain"
    folder = "fake/tiles"

    def __init__(self, n, bad=()):
        self.n, self.bad, self.fetched = n, set(bad), []

    def tiles(self, grid):
        return list(range(self.n))

    def tile_path(self, cache_dir, tile):
        return os.path.join(cache_dir, self.folder, f"{tile}.tif")

    def tile_url(self, tile):
        return None

    def download_tile(self, tile, path):
        if tile in self.bad:
            raise RuntimeError(f"tile {tile} cannot be read")
        self.fetched.append(tile)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * 1000)
        return Fetched(2_000_000)


class NoIndex(FakeLayer):
    """A layer whose index could not be reached (CachedIndex.tiles remembers None)."""

    def tiles(self, grid):
        return None

    def to_download(self, grid, cache_dir, update):
        return [], None


def _grid():
    return SimpleNamespace(crs="EPSG:2180", bounds=(0, 0, 1000, 1000), width=1000, height=1000, res=1.0,
                           area_shape=None)


class EmptyLayer(FakeLayer):
    """A layer whose tiles in `empty` have no data (the sea): recorded as missing, no file."""

    def __init__(self, n, empty=(), bad=()):
        super().__init__(n, bad)
        self.empty = set(empty)

    def download_tile(self, tile, path):
        if tile in self.empty:
            return Fetched(0)
        return super().download_tile(tile, path)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """An area over a made-up plan: `setup(layer)` gives the Area, the plan's search never runs."""
    data, state = tmp_path / "data", tmp_path / "state"
    (data / "cache").mkdir(parents=True)
    state.mkdir()
    area = ad.Area("land", "osm:Land", "fake", 1.0, str(data), str(state), min_free_gb=0)  # whatever this disk has

    def make(*layers):
        plan = SimpleNamespace(layers=list(layers), grid=_grid(), paths=SimpleNamespace(cache=str(data / "cache")))
        monkeypatch.setattr(ad, "plan_of", lambda _: plan)
        return area
    return make


def test_first_failure_stops_unless_asked(tmp_path):
    """Without on_error the first failed tile raises, as always; with it every other tile is downloaded."""
    cache_dir = str(tmp_path)
    with pytest.raises(RuntimeError, match="cannot be read"):
        src.download_layers([(FakeLayer(5, bad=[2]), "terrain")], _grid(), cache_dir)
    layer = FakeLayer(5, bad=[2])
    seen = []
    src.download_layers([(layer, "terrain")], _grid(), str(tmp_path / "other"),
                        on_error=lambda failed, tiles, error: seen.append((failed, list(tiles), str(error))))
    assert sorted(layer.fetched) == [0, 1, 3, 4]
    assert seen == [(layer, [2], "tile 2 cannot be read")]


def test_the_prune_runs_after_a_stop(tmp_path):
    """What on_error raises ends the pool, but the layers' `downloaded` (the older surveys of the tiles that came
    are deleted) runs first; the tiles not started are not downloaded; another error skips it as before."""
    class Pruning(FakeLayer):
        pruned = 0

        def downloaded(self, grid, cache_dir):
            Pruning.pruned += 1
    layer = Pruning(40, bad=[3])

    def stop(failed, tiles, error):
        raise ad.Stop("enough")
    with pytest.raises(ad.Stop, match="enough"):
        src.download_layers([(layer, "terrain")], _grid(), str(tmp_path / "a"), on_error=stop)
    assert Pruning.pruned == 1 and len(layer.fetched) < 40
    with pytest.raises(RuntimeError, match="cannot be read"):
        src.download_layers([(Pruning(5, bad=[2]), "terrain")], _grid(), str(tmp_path / "b"))
    assert Pruning.pruned == 1


def test_pass_to_its_end(setup):
    """Everything downloaded: the state says done, with the tiles and MB, and a second pass fetches nothing."""
    layer = FakeLayer(6)
    area = setup(layer)
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    state = ad.read_state(area.state_dir, "land")
    assert state["stage"] == "done"
    assert (state["tiles_done"], state["tiles_total"], state["failed"]) == (6, 6, 0)
    assert state["layers"] == [{"label": "terrain", "tiles": 6, "to_download": 6, "missing": 0}]
    assert state["tiles_missing"] == 0
    assert state["mb"] == pytest.approx(12)
    assert json.load(open(area.file(".failed.json"), encoding="utf-8")) == {}
    assert os.path.exists(os.path.join(area.state_dir, "status.html"))
    again = FakeLayer(6)
    assert ad.run_pass(setup(again), 2) == ad.EXIT_DONE
    assert again.fetched == []
    state = ad.read_state(area.state_dir, "land")
    assert (state["tiles_done"], state["mb"]) == (6, pytest.approx(12))  # the MB of the passes before stay


def test_pass_with_failed_tiles(setup):
    """The others are downloaded, the failed ones listed with their errors; the next pass asks only for those."""
    area = setup(FakeLayer(6, bad=[1, 4]))
    assert ad.run_pass(area, 1) == ad.EXIT_FAILED
    failed = json.load(open(area.file(".failed.json"), encoding="utf-8"))
    assert failed == {"fake/tiles/1.tif": "tile 1 cannot be read", "fake/tiles/4.tif": "tile 4 cannot be read"}
    state = ad.read_state(area.state_dir, "land")
    assert (state["stage"], state["tiles_done"], state["failed"]) == ("downloading", 4, 2)
    layer = FakeLayer(6)
    assert ad.run_pass(setup(layer), 2) == ad.EXIT_DONE
    assert sorted(layer.fetched) == [1, 4]


def test_done_says_what_has_no_data(setup):
    """The tiles the service has nothing for are counted per layer at the end (one query per cache folder), so a
    "done" area with half its tiles over the sea says so; a second pass counts the ones recorded before too."""
    layer, surface = EmptyLayer(6, empty=[1, 2]), EmptyLayer(4, empty=[3])
    surface.folder, surface.description = "fake/surface", "fake surface"
    area = setup(layer, surface)
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    state = ad.read_state(area.state_dir, "land")
    assert [row["missing"] for row in state["layers"]] == [2, 1] and state["tiles_missing"] == 3
    assert (state["tiles_done"], state["tiles_total"]) == (10, 10)
    row = ad.summary(state, [], time.time())
    assert row["missing"] == 3 and "3 tiles without data" in ad.table(area.state_dir)
    assert "Without data" in ad.page(area.state_dir)
    again = EmptyLayer(4)
    again.folder = "fake/surface"
    assert ad.run_pass(setup(EmptyLayer(6), again), 2) == ad.EXIT_DONE
    assert ad.read_state(area.state_dir, "land")["tiles_missing"] == 3


def test_an_area_without_data_needs_attention(setup, tmp_path):
    """No tile under the outline, or every tile without data: EXIT_NOTHING, never "done"."""
    area = setup(FakeLayer(0))
    assert ad.run_pass(area, 1) == ad.EXIT_NOTHING
    state = ad.read_state(area.state_dir, "land")
    assert state["message"].startswith("no tiles under the outline") and state["stage"] == "listing"
    area = setup(EmptyLayer(5, empty=range(5)))
    assert ad.run_pass(area, 2) == ad.EXIT_NOTHING
    state = ad.read_state(area.state_dir, "land")
    assert state["message"] == "all 5 tiles without data: the source has nothing under the outline"
    assert state["tiles_missing"] == 5 and state["stage"] == "downloading"
    (tmp_path / "run").mkdir()
    super_area = _area(tmp_path / "run")
    command = _pass(tmp_path, "json.dump({'name': 'land', 'stage': 'downloading', 'message': 'all 5 tiles without "
                              f"data'}}, open({super_area.file('.state.json')!r}, 'w'))\nsys.exit(6)\n")
    assert ad.supervise(super_area, command, retry_seconds=30) == 2
    state = ad.read_state(super_area.state_dir, "land")
    assert state["stage"] == "needs attention" and state["message"] == "all 5 tiles without data"


def test_the_index_counter_counts_this_areas_tiles_once(setup, monkeypatch, tmp_path):
    """The folder of index answers is shared by every area of a source: only the tiles of this area's grid count,
    and they are listed once per pass, not every ten seconds."""
    from sources.indexes.cached import CachedIndex
    grid = SimpleNamespace(crs="EPSG:4326", bounds=(10.0, 50.0, 10.6, 50.3), width=10, height=10, res=1.0,
                           area_shape=None)  # 3 x 2 tiles of 0.25°
    layer, other = FakeLayer(1), FakeLayer(1)
    layer.index = CachedIndex("fake index", None, None, "sheets", "fake")
    other.index = CachedIndex("other index", None, None, "other", "fake")
    area = setup(layer, other)
    cache_dir = os.path.join(area.data_dir, "cache")
    plan = SimpleNamespace(layers=[layer, other], grid=grid, paths=SimpleNamespace(cache=cache_dir))
    folder = os.path.dirname(layer.index.index_path(cache_dir, 50.0, 10.0))
    os.makedirs(folder)
    for name in ("N50.00_E010.00", "N50.25_E010.50", "N48.00_E012.00", "N47.75_E012.25", "N47.50_E012.50"):
        open(os.path.join(folder, name + ".json"), "w").close()   # two of this area's six, three of another's
    reporter = ad.Reporter(area, 1, [plan], ad.Failures(cache_dir))
    assert reporter._index_counts() == (2, 12)   # the other index has no folder yet: 0 of 6
    listed = []
    monkeypatch.setattr(ad.Reporter, "_index_folders", lambda self: listed.append(1) or [])
    assert reporter._index_counts() == (2, 12) and not listed
    reporter.write()
    state = ad.read_state(area.state_dir, "land")
    assert (state["index_done"], state["index_total"]) == (2, 12)


def test_index_out_of_reach_is_no_success(setup):
    """A layer whose index cannot be reached lists nothing to download: that must not look like a finished area."""
    area = setup(FakeLayer(2), NoIndex(0))
    assert ad.run_pass(area, 1) == ad.EXIT_STOPPED
    state = ad.read_state(area.state_dir, "land")
    assert "could not be reached" in state["message"] and state["stage"] != "done"


def test_many_failures_in_a_row_end_the_pass(setup, monkeypatch):
    """A share or a service that went away: no tile can be written, so the rest is not tried tile by tile."""
    monkeypatch.setattr(ad, "FAILURES_IN_A_ROW", 3)
    layer = FakeLayer(40, bad=range(40))
    area = setup(layer)
    assert ad.run_pass(area, 1) == ad.EXIT_STOPPED
    assert "failures in a row" in ad.read_state(area.state_dir, "land")["message"]


def _reporter(failures):
    """A Reporter without its thread and state file: what __call__ reads."""
    reporter = ad.Reporter.__new__(ad.Reporter)
    reporter.failures, reporter.free_gb, reporter.mb_pass, reporter.tiles_pass = failures, None, 0.0, 0
    reporter.tiles_offset, reporter.mb_offset, reporter.over_budget = 0, 0.0, False
    reporter.state, reporter.memory_gb = {"message": ""}, 0.0
    reporter.area = ad.Area("a", "b", "c", 1.0, "d", "e", min_free_gb=0, max_memory_gb=0)
    return reporter


def test_a_tile_between_failures_resets_the_count():
    failures = ad.Failures("cache")
    layer = FakeLayer(1)
    failures(layer, [0], RuntimeError("no"))
    reporter = _reporter(failures)
    reporter({"bar": "Download", "unit": "tile", "count": 1, "extra": {"MB": "5"}, "done": False})
    assert failures.in_a_row == 0 and reporter.mb_pass == 5
    reporter({"bar": "Compute", "unit": "tile", "count": 9, "extra": {}, "done": False})
    assert reporter.tiles_pass == 1


def test_the_tiles_of_the_plans_add_up():
    """A stand-in source's bar starts from 0: the tiles and MB of the plan before it stay counted."""
    reporter = _reporter(ad.Failures("cache"))
    reporter({"bar": "Download", "unit": "tile", "count": 4, "extra": {"MB": "10"}, "done": False})
    reporter.next_plan()
    reporter({"bar": "Download", "unit": "tile", "count": 2, "extra": {"MB": "3"}, "done": False})
    assert (reporter.tiles_pass, reporter.mb_pass) == (6, 13)


class SlowLayer(FakeLayer):
    def download_tile(self, tile, path):
        time.sleep(0.02)
        return super().download_tile(tile, path)


def test_a_pass_over_its_memory_budget_is_started_again(setup, monkeypatch):
    """The beat samples the memory; over the budget the next tile ends the pass with EXIT_RESTART and the message."""
    monkeypatch.setattr(ad, "memory_gb", lambda: 100.0)
    layer = SlowLayer(40)
    area = dataclasses.replace(setup(layer), max_memory_gb=6.5)
    assert ad.run_pass(area, 1) == ad.EXIT_RESTART
    state = ad.read_state(area.state_dir, "land")
    assert state["message"] == "memory 100.0 GB over the budget of 6.5 GB, the pass is started again"
    assert state["memory_gb"] == 100.0 and state["memory_peak_gb"] == 100.0 and state["stage"] == "downloading"
    assert len(layer.fetched) < 40
    assert ad.run_pass(dataclasses.replace(area, max_memory_gb=0), 2) == ad.EXIT_DONE  # 0: no budget


def test_memory_in_the_state_and_the_history(setup, monkeypatch):
    values = iter([1.5, 2.5, 2.0, 2.0, 2.0, 2.0])
    monkeypatch.setattr(ad, "memory_gb", lambda: next(values, 2.0))
    monkeypatch.setattr(ad, "STATE_SECONDS", 0.01)
    area = setup(SlowLayer(16))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    state = ad.read_state(area.state_dir, "land")
    assert state["memory_peak_gb"] == 2.5 and state["memory_gb"] == 2.0
    rows = open(area.file(".history.csv"), encoding="utf-8").read().splitlines()
    assert rows and all(len(row.split(",")) == 4 for row in rows)  # seconds, tiles, MB, memory GB
    assert ad.read_history(area.state_dir, "land")[0][1] == 0  # read as before, three values


def test_history_rows_without_the_memory_column_are_read(tmp_path):
    with open(ad.state_file(str(tmp_path), "land", ".history.csv"), "w", encoding="utf-8") as f:
        f.write("100,5,20.5\n160,8,30.0,1.25\n")
    assert ad.read_history(str(tmp_path), "land") == [(100.0, 5.0, 20.5), (160.0, 8.0, 30.0)]


def test_a_plan_that_fails_ends_the_pass_with_its_text(setup, monkeypatch, capsys):
    """Denmark without its key, an outline Nominatim does not know: a stopped pass with the reason, no traceback."""
    import search
    area = setup(FakeLayer(1))
    for error in (ValueError("no key for Datafordeler"), search.SearchError("no source covers the area"),
                  RuntimeError("Nominatim gave nothing")):
        def failing(_, error=error):
            raise error
        monkeypatch.setattr(ad, "plan_of", failing)
        assert ad.run_pass(area, 1) == ad.EXIT_STOPPED
        state = ad.read_state(area.state_dir, "land")
        assert state["message"] == f"the download could not be planned: {error}" and state["stage"] == "listing"
        assert f"Stopped: the download could not be planned: {error}" in capsys.readouterr().out


def test_a_stand_in_source_is_downloaded_too(setup, monkeypatch):
    """`alaska` names alaska_ifsar where it has no data (Source.instead_without_data): both are planned and
    downloaded, the stand-in's layers labelled with its id, the totals over both."""
    first, second = FakeLayer(3), FakeLayer(2)
    second.folder = "fake/ifsar"
    area = setup(first)

    def plan(layer, source, instead):
        cache_dir = os.path.join(area.data_dir, "cache")
        return SimpleNamespace(layers=[layer], grid=_grid(), paths=SimpleNamespace(cache=cache_dir),
                               source=SimpleNamespace(id=source, instead_without_data=instead))
    plans = {"fake": plan(first, "fake", "fake_ifsar"), "fake_ifsar": plan(second, "fake_ifsar", None)}
    monkeypatch.setattr(ad, "plan_of", lambda a: plans[a.source])
    assert [p.source.id for p in ad.plans_of(area)] == ["fake", "fake_ifsar"]
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    state = ad.read_state(area.state_dir, "land")
    assert [row["label"] for row in state["layers"]] == ["terrain", "terrain (fake_ifsar)"]
    assert (state["tiles_done"], state["tiles_total"]) == (5, 5) and sorted(second.fetched) == [0, 1]
    assert state["mb"] == pytest.approx(10)
    alone = ad.Area("land", "osm:Land", "fake_ifsar", 1.0, area.data_dir, area.state_dir)
    assert ad.plans_of(alone) == [plans["fake_ifsar"]]


def test_a_pass_without_a_contact_warns(setup, monkeypatch, capsys):
    """The warning is printed and stands in the state until the first tile; the pass never fails for it."""
    monkeypatch.delenv("FINDALINE_CONTACT", raising=False)
    area = setup(FakeLayer(2))
    seen = []

    class Reading(FakeLayer):
        def download_tile(self, tile, path):
            seen.append(ad.read_state(area.state_dir, "land")["message"])
            return super().download_tile(tile, path)
    area = setup(Reading(2))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert f"Warning: {ad.NO_CONTACT}" in capsys.readouterr().out
    assert seen[0] == ad.NO_CONTACT
    assert ad.read_state(area.state_dir, "land")["message"] == ""
    area = setup(NoIndex(0))
    assert ad.run_pass(area, 2) == ad.EXIT_STOPPED   # another message replaces it
    assert "could not be reached" in ad.read_state(area.state_dir, "land")["message"]
    assert "Warning" in capsys.readouterr().out
    monkeypatch.setenv("FINDALINE_CONTACT", "someone@example.org")
    assert ad.run_pass(setup(FakeLayer(1)), 3) == ad.EXIT_DONE
    assert "Warning" not in capsys.readouterr().out


def test_a_full_disk_ends_the_pass(setup, monkeypatch):
    area = setup(FakeLayer(4))
    area = ad.Area(area.name, area.area, area.source, area.resolution, area.data_dir, area.state_dir, (), 10.0)
    monkeypatch.setattr(ad.Reporter, "_free", lambda self: 1.0)
    assert ad.run_pass(area, 1) == ad.EXIT_STOPPED
    assert "1 GB free" in ad.read_state(area.state_dir, "land")["message"]


@pytest.mark.parametrize("native, expected", [(0.5, 5000), (1.0, 10000), (2.0, 20000)])
def test_groups_hold_the_same_pixels_whatever_the_files(setup, monkeypatch, native, expected):
    """The window layers' groups are PREFETCH_GROUP_M for 1 m files, half that for 0.5 m ones (Luxembourg's and
    Scotland's float64 at the app's 1 m minimum: 10 km took about 5 GB a thread and the passes were killed), by
    the finest grouped layer of the plan; the area's resolution only without a native one."""
    import country
    assert country.PREFETCH_GROUP_M == 10000
    dtm, dsm = FakeLayer(2), FakeLayer(2)
    dtm.groups = dsm.groups = True
    dtm.native_res, dsm.native_res = native, 2 * native
    area = dataclasses.replace(setup(dtm, dsm), resolution=1.0)
    asked = []
    monkeypatch.setattr(src, "download_layers", lambda *a, **k: asked.append(k))
    ad.run_pass(area, 1)
    assert asked[0]["group_m"] == expected
    plain = FakeLayer(2)
    plain.groups = True
    assert ad._group_m(dataclasses.replace(area, resolution=2.0), SimpleNamespace(layers=[plain])) == 20000
    assert ad._group_m(area, SimpleNamespace(layers=[FakeLayer(1)])) == 10000  # no grouped layer: unused anyway


def test_host_slots_only_in_this_process(monkeypatch):
    """A cap below the app's: that many connections, and no threads waiting beyond them."""
    monkeypatch.setattr(src.net, "HOST_SLOTS_OF", dict(src.net.HOST_SLOTS_OF))
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", src.layer.DOWNLOAD_THREADS)
    ad._set_host_slots(ad.Area("a", "b", "c", 1.0, "d", "e", (("opendata.example", 2),)))
    assert src.net.HOST_SLOTS_OF["opendata.example"] == 2
    assert src.layer.DOWNLOAD_THREADS == 2


def _pass(tmp_path, body):
    """A pass of the supervisor's: a script whose last argument is the pass's number."""
    path = tmp_path / "pass.py"
    path.write_text("import json, sys\nnumber = int(sys.argv[-1])\n" + body, encoding="utf-8")
    return [sys.executable, str(path)]


def _area(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    return ad.Area("land", "osm:Land", "fake", 1.0, str(tmp_path), str(state))


def test_supervisor_goes_on_until_done(tmp_path):
    """A pass that gave up is followed by another; what they print lands in the log."""
    area = _area(tmp_path)
    command = _pass(tmp_path, "print('pass', number, 'here')\nsys.exit(0 if number == 3 else 4)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 0
    log = open(area.file(".log"), encoding="utf-8").read()
    assert "pass 3 here" in log and "pass 3 ended with 0" in log


def test_a_pass_gets_gdals_block_cache(tmp_path, monkeypatch):
    """GDAL's default is 5 % of the memory for each of several passes at once; a setting of the environment stays."""
    area = _area(tmp_path)
    seen = tmp_path / "env.txt"
    command = _pass(tmp_path, f"import os\nopen({str(seen)!r}, 'w').write(os.environ.get('GDAL_CACHEMAX', ''))\n"
                              "sys.exit(0)\n")
    monkeypatch.delenv("GDAL_CACHEMAX", raising=False)
    assert ad.supervise(area, command) == 0
    assert seen.read_text() == str(ad.GDAL_CACHEMAX_MB)
    monkeypatch.setenv("GDAL_CACHEMAX", "64")
    assert ad.supervise(area, command) == 0
    assert seen.read_text() == "64"


def test_supervisor_needs_attention_for_the_same_tiles(tmp_path):
    """The same tiles failing pass after pass end the area; tiles that keep changing do not."""
    area = _area(tmp_path)
    failed = area.file(".failed.json")
    command = _pass(tmp_path, f"json.dump({{'a.tif': 'broken'}}, open({failed!r}, 'w'))\nsys.exit(3)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 2
    state = ad.read_state(area.state_dir, "land")
    assert state["stage"] == "needs attention" and "land.failed.json" in state["message"]
    assert "pass 3 ended with 3" in open(area.file(".log"), encoding="utf-8").read()
    command = _pass(tmp_path, f"json.dump({{str(number): 'broken'}}, open({failed!r}, 'w'))\n"
                              "sys.exit(0 if number == 5 else 3)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 0


def _restarting_pass(tmp_path, area, tiles, last):
    """A pass over its budget: the state as the Reporter leaves it (the restarts before carried over), its tiles
    done from `tiles` (a Python expression of `number`), exit 5 until pass `last` exits 0."""
    state = area.file(".state.json")
    return _pass(tmp_path, f"import os\nstate = {state!r}\n"
                           "before = json.load(open(state)) if os.path.exists(state) else {}\n"
                           "json.dump({'name': 'land', 'stage': 'downloading', 'message': 'memory 9.0 GB over "
                           f"the budget of 8 GB, the pass is started again', 'tiles_done': {tiles}, "
                           "'tiles_total': 100, 'mb': 5.0, 'restarts': before.get('restarts', 0)}, open(state, 'w'))\n"
                           f"sys.exit(0 if number == {last} else 5)\n")


def test_supervisor_starts_a_pass_over_its_budget_again_at_once(tmp_path):
    """EXIT_RESTART after progress: no retry wait, the restarts counted in the state, never attention."""
    area = _area(tmp_path)
    started = time.monotonic()
    assert ad.supervise(area, _restarting_pass(tmp_path, area, "10 * number", 5), retry_seconds=30) == 0
    assert time.monotonic() - started < 25
    assert ad.read_state(area.state_dir, "land")["restarts"] == 4
    log = open(area.file(".log"), encoding="utf-8").read()
    assert "started again at once (4 restarts)" in log and "without progress" not in log


def test_restarts_without_progress_wait_and_end_as_attention(tmp_path):
    """A budget too small for one group (or a pass over it before its first tile): the pass would list everything
    again in a hot loop. The first pass restarts at once; without progress the next waits, and three such restarts
    in a row end the area; progress between them resets the count."""
    area = dataclasses.replace(_area(tmp_path), max_memory_gb=8)
    assert ad.supervise(area, _restarting_pass(tmp_path, area, "10", 99), retry_seconds=0.01) == 2
    state = ad.read_state(area.state_dir, "land")
    assert state["stage"] == "needs attention" and state["restarts"] == 4
    assert state["message"] == "the memory budget of 8 GB is too small for this area: raise --max-memory-gb"
    log = open(area.file(".log"), encoding="utf-8").read()
    assert "pass 4 ended with 5" in log and "pass 5 starts" not in log
    assert "restart without progress (3 in a row, 4 restarts)" in log
    # progress on every other pass: never three in a row without it
    (tmp_path / "b").mkdir()
    area = dataclasses.replace(_area(tmp_path / "b"), max_memory_gb=8)
    command = _restarting_pass(tmp_path / "b", area, "10 * (number // 2)", 8)
    assert ad.supervise(area, command, retry_seconds=0.01) == 0
    state = ad.read_state(area.state_dir, "land")
    assert state["restarts"] == 7 and state["stage"] == "downloading"
    log = open(area.file(".log"), encoding="utf-8").read()
    assert "needs attention" not in log and "restart without progress (1 in a row" in log
    assert "restart without progress (2 in a row" not in log


def test_supervisor_needs_attention_for_the_same_stop(tmp_path):
    """A pass giving up with the same message ATTENTION_PASSES times (Slovenia: 37 passes of "50 failures in a
    row"; Denmark: 13 without its key); a restart between them does not break the row."""
    area = _area(tmp_path)
    state = area.file(".state.json")
    command = _pass(tmp_path, "json.dump({'name': 'land', 'stage': 'listing', 'message': 'the download could not be "
                              "planned: no key'}, open(" + repr(state) + ", 'w'))\n"
                              "sys.exit(5 if number == 2 else 4)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 2
    state_now = ad.read_state(area.state_dir, "land")
    assert state_now["stage"] == "needs attention"
    assert state_now["message"] == "the download could not be planned: no key (3 passes in a row)"
    assert "pass 4 ended with 4" in open(area.file(".log"), encoding="utf-8").read()
    # Failures' message names the last error, another tile's each pass: the same stop all the same
    command = _pass(tmp_path, "json.dump({'name': 'land', 'stage': 'downloading', 'message': '50 failures in a row, "
                              "the last: tile %d cannot be read' % number}, open(" + repr(state) + ", 'w'))\n"
                              "sys.exit(4)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 2
    assert ad.read_state(area.state_dir, "land")["message"].endswith("tile 3 cannot be read (3 passes in a row)")
    command = _pass(tmp_path, "json.dump({'name': 'land', 'stage': 'listing', 'message': 'reason %d' % number}, "
                              "open(" + repr(state) + ", 'w'))\nsys.exit(0 if number == 5 else 4)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 0


def test_supervisor_needs_attention_for_the_same_crash(tmp_path):
    """A code of its own (a traceback): the log's last line is the message, three alike end the area."""
    area = _area(tmp_path)
    command = _pass(tmp_path, "print('Traceback (most recent call last):')\nprint('  File x')\n"
                              "print('ModuleNotFoundError: No module named rasterio')\nsys.exit(1)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 2
    state = ad.read_state(area.state_dir, "land")
    assert state["stage"] == "needs attention"
    assert state["message"] == ("pass 3 ended with 1: ModuleNotFoundError: No module named rasterio "
                                "(3 crashes in a row)")
    command = _pass(tmp_path, "print('crash', number)\nsys.exit(0 if number == 5 else 1)\n")
    assert ad.supervise(area, command, retry_seconds=0.01) == 0
    assert "crash 4" in ad.read_state(area.state_dir, "land")["message"]  # the last waiting message


def test_the_last_line_of_the_log(tmp_path):
    path = tmp_path / "land.log"
    path.write_text("[2026-11-08T10:00:00Z] pass 1 starts\nsomething\n\n  Error: broken  \n"
                    "[2026-11-08T10:00:01Z] pass 1 ended with 1\n", encoding="utf-8")
    assert ad._last_line(str(path)) == "Error: broken"
    assert ad._last_line(str(tmp_path / "none.log")) == ""
    path.write_bytes(b"x" * (ad.LOG_TAIL_BYTES + 10) + b"\nlast\n")
    assert ad._last_line(str(path)) == "last"


def test_the_budget_on_the_command_line(monkeypatch):
    """`run` resolves the default once and hands every pass the same number; 0 is no budget."""
    seen = []
    monkeypatch.setattr(ad, "supervise", lambda area, command: seen.append((area, command)) or 0)
    monkeypatch.setattr(ad, "default_max_memory_gb", lambda: 15.5)
    base = ["run", "land", "--area", "osm:Land", "--source", "fake", "--resolution", "1", "--data-dir", "d",
            "--state-dir", "s"]
    ad.main(base)
    area, command = seen[-1]
    assert area.max_memory_gb == 15.5 and command[command.index("--max-memory-gb") + 1] == "15.5"
    ad.main(base + ["--max-memory-gb", "0", "--host-slots", "h=2"])
    area, command = seen[-1]
    assert area.max_memory_gb == 0 and command[command.index("--max-memory-gb") + 1] == "0.0"
    assert command[command.index("--host-slots") + 1] == "h=2" and command[-1] == "--number"
    assert ad.default_max_memory_gb() > 0


def test_supervisor_stops_by_hand(tmp_path):
    """The stop file ends the running pass and its process; `run` afterwards starts again."""
    area = _area(tmp_path)
    command = _pass(tmp_path, "import time\ntime.sleep(60)\n")
    threading.Timer(1.0, lambda: open(area.file(".stop"), "w").close()).start()
    started = time.monotonic()
    assert ad.supervise(area, command) == 0
    assert time.monotonic() - started < 30
    assert ad.read_state(area.state_dir, "land")["stage"] == "stopped"


def test_one_supervisor_per_area(tmp_path):
    from filelock import FileLock
    area = _area(tmp_path)
    with FileLock(area.file(".lock")):
        assert ad.supervise(area, [sys.executable, "-c", "pass"]) == 1


def test_summary():
    now = 100_000.0
    state = {"name": "land", "stage": "downloading", "tiles_done": 500, "tiles_total": 1000, "mb": 2000.0,
             "updated": ad._now(), "failed": 2, "source": "fake"}
    history = [(now - 600 + 60 * k, 400 + 10 * k, 1000 + 60 * k) for k in range(11)]
    row = ad.summary(state, history, ad._seconds(state["updated"]))
    assert row["share"] == 0.5 and row["gb"] == 2.0 and row["failed"] == 2
    assert row["mb_s"] == pytest.approx(1.0)
    assert row["eta"] == pytest.approx(500 * 6)  # 10 tiles a minute
    assert not row["stale"]
    late = ad.summary(state, history, ad._seconds(state["updated"]) + ad.STALE_SECONDS + 1)
    assert late["stale"]
    waiting = ad.summary({**state, "stage": "waiting"}, history, ad._seconds(state["updated"]) + ad.STALE_SECONDS + 1)
    assert not waiting["stale"] and waiting["mb_s"] is None and waiting["eta"] is None
    done = ad.summary({**state, "stage": "done"}, history, ad._seconds(state["updated"]) + 10 ** 6)
    assert not done["stale"]


def test_table_and_page(tmp_path):
    """Both show every area; what an area's message says cannot break the page."""
    state_dir = str(tmp_path)
    ad.write_state(state_dir, "poland", {"name": "poland", "source": "geoportal", "stage": "downloading",
                                         "tiles_done": 12_345, "tiles_total": 188_000, "mb": 51_000.0, "failed": 1,
                                         "free_gb": 5500.0, "message": ""})
    ad.write_state(state_dir, "utah", {"name": "utah", "source": "usa", "stage": "listing", "index_done": 12,
                                       "index_total": 400, "message": "<b>server & co</b>", "mb": 0.0})
    with open(ad.state_file(state_dir, "poland", ".history.csv"), "w", encoding="utf-8") as f:
        now = time.time()
        f.writelines(f"{now - 60 * (5 - k):.0f},{12_300 + 10 * k},{50_000 + 200 * k}\n" for k in range(6))
        f.write("123,4")  # a line cut short by a kill
    text = ad.table(state_dir)
    assert "12,345 / 188,000 (6.6 %)" in text and "index 12 / 400" in text and "3.3" in text
    html = ad.page(state_dir)
    assert "poland" in html and "utah" in html and "<svg" in html
    assert "&lt;b&gt;server &amp; co&lt;/b&gt;" in html and "<b>server" not in html
    ad.write_page(state_dir)
    assert os.path.exists(os.path.join(state_dir, "status.html"))
    assert ad.table(str(tmp_path / "none")).startswith("No areas")


def test_duration():
    assert [ad.duration(s) for s in (None, 600, 7200, 172800)] == ["-", "10 min", "2.0 h", "2.0 d"]


def test_no_folder_in_countries(setup):
    """The outline stays in the state folder: a folder in countries/ would be taken off the next country's outline."""
    area = setup(FakeLayer(1))
    ad.run_pass(area, 1)
    assert not os.path.exists(os.path.join(area.data_dir, "countries"))


def test_contact_goes_with_the_requests(monkeypatch):
    monkeypatch.setenv("FINDALINE_CONTACT", "someone@example.org")
    assert "contact: someone@example.org" in cache.http_headers()["User-Agent"]
    monkeypatch.delenv("FINDALINE_CONTACT")
    assert cache.http_headers()["User-Agent"].endswith("self-hosted)")


def test_clip_to_boxes():
    """area.clip_to_boxes: a WGS84 outline cut to the union of (south, north, west, east) boxes, with about the km²
    left out; no boxes: as it was; Source.coverage_boxes are the offline boxes and the bbox, never the border
    boxes (they may hold a neighbour's land); rough_boxes adds those."""
    import area as ar
    from shapely.geometry import box
    from shapely.ops import unary_union
    main, far = box(19.0, 50.0, 20.0, 51.0), box(-160.0, 19.0, -159.0, 20.0)  # about 7 900 and 11 700 km²
    outline = unary_union([main, far])
    kept, dropped = ar.clip_to_boxes(outline, [(49.0, 52.0, 18.0, 21.0)])
    assert kept.equals(main) and 11_000 < dropped < 12_500
    kept, dropped = ar.clip_to_boxes(outline, [(49.0, 52.0, 18.0, 21.0), (18.0, 21.0, -161.0, -158.0)])
    assert kept.equals(outline) and dropped == 0.0
    assert ar.clip_to_boxes(outline, []) == (outline, 0.0)
    kept, dropped = ar.clip_to_boxes(outline, [(50.5, 52.0, 18.0, 21.0)])  # half of the main part, all of far
    assert kept.equals(box(19.0, 50.5, 20.0, 51.0)) and 15_000 < dropped < 16_500
    assert ar.rough_km2(main) == pytest.approx(ar.size_km2(main), rel=0.02)
    us = src.SOURCES["usa"]
    assert us.coverage_boxes() == [b for _, b in us.offline] and us.rough_boxes()[:len(us.coverage_boxes())] == \
        us.coverage_boxes()
    cz = src.SOURCES["czechia"]
    assert cz.border_boxes and cz.coverage_boxes() == [b for _, b in cz.offline]
    assert cz.rough_boxes() == cz.coverage_boxes() + list(cz.border_boxes)


def test_plan_clips_the_outline_to_the_coverage_boxes(tmp_path, monkeypatch, capsys):
    """plan_of plans over the stored outline clipped to the source's coverage boxes (a Feature written into the
    pass's work folder; the stored <state>/<name>.geojson stays): of an outline of two parts, one in the source's
    box and one far away, the plan's area holds the first only, and a line names the km² left out; a source
    without boxes, or one whose boxes hold the outline, plans over the stored file itself."""
    import area as ar
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union
    data, state = tmp_path / "data", tmp_path / "state"
    (data / "cache").mkdir(parents=True)
    state.mkdir()
    near, far = box(19.0, 50.0, 19.2, 50.2), box(-160.0, 19.0, -159.8, 19.2)
    stored = state / "land.geojson"
    stored.write_text(json.dumps({"type": "Feature", "properties": {"name": "land"},
                                  "geometry": mapping(unary_union([near, far]))}), encoding="utf-8")
    before = stored.read_text(encoding="utf-8")
    planned = []

    def fake_plan(params, paths, say, tiled):
        geometry = ar.from_spec(params.area, params.buffer, None, paths.cache).geometry
        planned.append((params.area, geometry))
        return SimpleNamespace(grid=SimpleNamespace(area_shape=geometry), paths=paths)
    import search
    monkeypatch.setattr(search, "plan_search", fake_plan)
    # Real source ids (SearchParams checks them) with boxes of their own for the test
    monkeypatch.setattr(src.SOURCES["usa"], "coverage_boxes", lambda: [(49.0, 52.0, 18.0, 21.0)])
    monkeypatch.setattr(src.SOURCES["europe"], "coverage_boxes", lambda: [])
    area = ad.Area("land", "osm:Land", "usa", 1.0, str(data), str(state), min_free_gb=0)
    plan = ad.plan_of(area)
    path, geometry = planned[-1]
    assert path == os.path.join(str(data), "work", "area-download-land", "outline.geojson")
    assert geometry.geom_type == "Polygon" and geometry.equals(near) and plan.grid.area_shape.equals(near)
    assert stored.read_text(encoding="utf-8") == before
    with open(path, encoding="utf-8") as f:
        written = json.load(f)
    assert shape(written["geometry"]).equals(near) and written["properties"]["name"] == "land"
    out = capsys.readouterr().out
    assert "Outline clipped to the source's coverage boxes: about" in out and "km² outside them left out" in out
    # A source without boxes: the stored file as it is, nothing printed
    ad.plan_of(ad.Area("land", "osm:Land", "europe", 1.0, str(data), str(state), min_free_gb=0))
    assert planned[-1][0] == str(stored) and planned[-1][1].equals(unary_union([near, far]))
    assert capsys.readouterr().out == ""
    # Boxes holding the whole outline: the stored file too
    monkeypatch.setattr(src.SOURCES["usa"], "coverage_boxes",
                        lambda: [(49.0, 52.0, 18.0, 21.0), (18.0, 21.0, -161.0, -158.0)])
    ad.plan_of(area)
    assert planned[-1][0] == str(stored) and capsys.readouterr().out == ""
    # Nothing inside the boxes: refused
    monkeypatch.setattr(src.SOURCES["usa"], "coverage_boxes", lambda: [(0.0, 1.0, 0.0, 1.0)])
    with pytest.raises(ValueError, match="outside the source's coverage"):
        ad.plan_of(area)
