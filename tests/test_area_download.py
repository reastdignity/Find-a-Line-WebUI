"""The download of a whole area (tools/area_download.py), offline: sources.download_layers going on after a failed
tile only when asked, a pass over a made-up layer (the tiles failing, an index out of reach, too many failures in a
row, the disk), the supervisor's passes, and what is shown of them."""

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
    return SimpleNamespace(crs="EPSG:2180", bounds=(0, 0, 1000, 1000), width=1000, height=1000, res=1.0)


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


def test_pass_to_its_end(setup):
    """Everything downloaded: the state says done, with the tiles and MB, and a second pass fetches nothing."""
    layer = FakeLayer(6)
    area = setup(layer)
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    state = ad.read_state(area.state_dir, "land")
    assert state["stage"] == "done"
    assert (state["tiles_done"], state["tiles_total"], state["failed"]) == (6, 6, 0)
    assert state["layers"] == [{"label": "terrain", "tiles": 6, "to_download": 6}]
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


def test_a_tile_between_failures_resets_the_count():
    failures = ad.Failures("cache")
    layer = FakeLayer(1)
    failures(layer, [0], RuntimeError("no"))
    reporter = ad.Reporter.__new__(ad.Reporter)
    reporter.failures, reporter.free_gb, reporter.mb_pass = failures, None, 0
    reporter({"bar": "Download", "unit": "tile", "count": 1, "extra": {"MB": "5"}, "done": False})
    assert failures.in_a_row == 0 and reporter.mb_pass == 5
    reporter({"bar": "Compute", "unit": "tile", "count": 9, "extra": {}, "done": False})
    assert reporter.tiles_pass == 1


def test_a_full_disk_ends_the_pass(setup, monkeypatch):
    area = setup(FakeLayer(4))
    area = ad.Area(area.name, area.area, area.source, area.resolution, area.data_dir, area.state_dir, (), 10.0)
    monkeypatch.setattr(ad.Reporter, "_free", lambda self: 1.0)
    assert ad.run_pass(area, 1) == ad.EXIT_STOPPED
    assert "1 GB free" in ad.read_state(area.state_dir, "land")["message"]


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
