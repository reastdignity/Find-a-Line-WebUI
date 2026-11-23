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

import psutil
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import area_download as ad  # noqa: E402
import cache  # noqa: E402
import sources as src  # noqa: E402
from sources.layer import Fetched, Layer  # noqa: E402

REAL_MACHINE_FREE_GB = ad.machine_free_gb  # before plenty_of_memory replaces it


@pytest.fixture(autouse=True)
def plenty_of_memory(monkeypatch):
    """The machine's memory as plenty (1000 GB available, 2 kept), so no pass here restarts for what the
    machine running the tests has free; a test of the machine's limit sets its own."""
    monkeypatch.setattr(ad, "machine_free_gb", lambda: (1000.0, 2.0))


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


def test_a_pass_asks_the_cache_once_and_by_folder(setup, monkeypatch):
    """The tiles of a whole area: each layer's to_download once a pass (run_pass for its counts; download_layers
    takes those answers), the files asked about by folder through sources.layer.EXISTING, which a search never
    sets and a pass leaves as it was. A tile another process downloads between the question and the download is
    not downloaded again."""
    from sources.indexes import versions

    class Counting(FakeLayer):
        asked = 0

        def to_download(self, grid, cache_dir, update):
            Counting.asked += 1
            Counting.how = src.layer.EXISTING
            todo, line = super().to_download(grid, cache_dir, update)
            if Counting.asked == 1:   # another download brings tile 0 right after the question
                path = self.tile_path(cache_dir, 0)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").close()
                cache.record(cache_dir, path)
            return todo, line
    assert src.layer.EXISTING is None
    layer = Counting(6)
    area = setup(layer)
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert Counting.asked == 1 and Counting.how is versions.existing
    assert src.layer.EXISTING is None
    assert sorted(layer.fetched) == [1, 2, 3, 4, 5]
    state = ad.read_state(area.state_dir, "land")
    assert state["layers"] == [{"label": "terrain", "tiles": 6, "to_download": 6, "missing": 0}]
    # a search, and any other caller of download_layers, asks itself, file by file
    Counting.asked = 0
    src.download_layers([(Counting(6), "terrain")], _grid(), os.path.join(area.data_dir, "cache"))
    assert Counting.asked == 1 and Counting.how is None
    # a pass that stops gives the setting back too
    monkeypatch.setattr(ad, "_one_pass", lambda area, number: (_ for _ in ()).throw(RuntimeError("broken")))
    with pytest.raises(RuntimeError, match="broken"):
        ad.run_pass(area, 2)
    assert src.layer.EXISTING is None


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


def test_a_row_without_tnm_data_is_not_renewed(setup, monkeypatch):
    """A source whose layers do not renew (sources/renewal.py: only the TNM datasets do): the first pass of a start
    asks nothing more than before (its three tiles; no HTTP request, the renewal never called) and notes no
    renewal."""
    import requests
    from sources import renewal
    sent = []
    real = requests.Session.request
    monkeypatch.setattr(requests.Session, "request", lambda self, method, url, *a, **k: (
        sent.append(url), real(self, method, url, *a, **k))[1])
    monkeypatch.setattr(renewal, "renew", lambda *a, **k: sent.append("renew"))
    layer = FakeLayer(3)
    area = setup(layer)
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert sorted(layer.fetched) == [0, 1, 2] and sent == []
    state = ad.read_state(area.state_dir, "land")
    assert "renewed" not in state and not state.get("renewal")


def test_the_row_shows_the_renewal_while_it_runs(setup, monkeypatch):
    """What the renewal says goes into the state while it runs (the window's row text: "renewal"), the beat writing
    it; afterwards "renewal" is empty and "renewed" says what it did."""
    from sources import renewal

    class Renewing(FakeLayer):
        renews = True
    seen = []

    def renew(layers, grid, cache_dir, say, asked, since=None):
        say("  the index of fake terrain: 1 of 2 answers, 0 changed, 0 failed")
        deadline = time.monotonic() + 60   # until the beat wrote it (a loaded machine: several beats), not a guess
        while not ad.read_state(area.state_dir, "land").get("renewal") and time.monotonic() < deadline:
            time.sleep(0.02)
        seen.append(ad.read_state(area.state_dir, "land").get("renewal"))
        return renewal.Renewal(asked=2)
    monkeypatch.setattr(ad, "STATE_SECONDS", 0.05)
    monkeypatch.setattr(renewal, "renew", renew)
    area = setup(Renewing(2))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert seen == ["the index of fake terrain: 1 of 2 answers, 0 changed, 0 failed"]
    state = ad.read_state(area.state_dir, "land")
    assert state["renewal"] == "" and state["renewed"]["text"].startswith(
        "this start: 2 index answers asked in 1 pass, the renewal went through; this pass: 2 index answers asked again")


def test_the_starts_time_is_on_disk_before_its_renewal(setup, monkeypatch):
    """The start's time (renewal_since) is in the state file before the renewal begins, so a pass killed during it
    (no final write of its state) leaves the time to the start's next pass, which then asks only what is open."""
    from sources import renewal

    class Renewing(FakeLayer):
        renews = True
    seen = []

    def renew(layers, grid, cache_dir, say, asked, since=None):
        seen.append((since, ad.read_state(area.state_dir, "land").get("renewal_since")))
        return renewal.Renewal(asked=2)
    monkeypatch.setattr(ad, "STATE_SECONDS", 3600)   # the beat writes nothing in between
    monkeypatch.setattr(renewal, "renew", renew)
    area = setup(Renewing(2))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert len(seen) == 1 and seen[0][0] and seen[0][0] == seen[0][1]


def test_a_restarted_row_asks_the_index_again(tmp_path, monkeypatch, http_server):
    """Every start of a row asks the USA's index again before the listing, and the list of the bucket's unlisted
    files (older than 28 days: none yet), on the stand-in TNM index and bucket: a finished row started again after
    the index gained a project fetches the new blocks and deletes the older ones; a later pass of the same start
    (after a failure, a memory restart) whose renewal went through in pass 1 asks nothing again, neither an answer
    nor the bucket (wave A of the USA, part A-2; fix round 2a)."""
    import requests
    from sources.layers import tnmbucket as tb
    from test_sources import _tile_1m
    from test_usa_renewal import FAR, Tnm, _bucket, _grid, _layer, _settle
    monkeypatch.setenv(tb.RENEW_ENV, "")
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    monkeypatch.setattr(tb, "MAX_UNLISTED_SHARE", 1.0)
    tb.forget_unlisted()
    tnm, files = Tnm(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    _bucket(http_server, tnm, [FAR])
    data, state_dir = tmp_path / "data", tmp_path / "state"
    (data / "cache").mkdir(parents=True)
    state_dir.mkdir()
    area = ad.Area("utah", "osm:Utah", "usa", 1.0, str(data), str(state_dir), min_free_gb=0)
    monkeypatch.setattr(ad, "plan_of", lambda _: SimpleNamespace(
        layers=[_layer(http_server.base)], grid=_grid(), paths=SimpleNamespace(cache=str(data / "cache"))))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    folder = data / "cache" / "usa" / "test1m" / "epsg26913" / "47_442"
    first = sorted(os.listdir(folder))
    state = ad.read_state(area.state_dir, "utah")
    assert len(first) == 4 and state["renewal"] == "" and "the list of unlisted files made" in state["renewed"]["text"]
    assert state["renewed"]["renewals"][0]["list"] == "made" and state["renewed"]["renewals"][0]["requests"]["answers"]

    _tile_1m(tnm, files, "CO_New_2025", 1025, published="2026-01-01")
    tnm.asked.clear()
    bucket = sum(1 for r in http_server.log if r.path == "/")
    assert ad.run_pass(area, 2) == ad.EXIT_DONE     # a later pass of the same start: its renewal went through
    assert tnm.tile_requests() == {} and sorted(os.listdir(folder)) == first
    assert sum(1 for r in http_server.log if r.path == "/") == bucket   # the list looked at once in the start
    renewed = ad.read_state(area.state_dir, "utah")["renewed"]
    assert (renewed["passes"], renewed["asked"], renewed["open"], renewed["through"]) == \
        (1, state["renewed"]["asked"], 0, True)   # pass 2 did not renew (E4)
    _settle(str(data / "cache"))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE     # the row started again
    after = sorted(os.listdir(folder))
    assert len(after) == 4 and all(n.startswith("2025_") for n in after) and not set(after) & set(first)
    assert "the list of unlisted files kept" in ad.read_state(area.state_dir, "utah")["renewed"]["text"]
    tb.forget_unlisted()


def test_the_passes_of_a_start_renew_until_it_went_through(tmp_path, monkeypatch):
    """The user's answer of 2026-11-23, "Until one renewal went through": a later pass of a start asks exactly the
    answers that start has not yet asked successfully (those that failed; those a killed pass never reached), none
    twice; once all are asked, later passes of the start ask nothing; a new start asks every answer again. The
    state's "renewed" says what the start asked in all and what is still open."""
    import requests
    from sources.indexes.cached import index_tiles
    from sources.layers import tnmbucket as tb
    from sources.layers.tnm import TNM_API
    from test_sources import _tile_1m
    from test_usa_renewal import Tnm, _grid, _layer, _settle

    class Flaky(Tnm):
        """The stand-in TNM index with tiles that do not answer (down) and a kill at the n-th tile request."""
        def __init__(self):
            super().__init__()
            self.down, self.kill_at, self.count = set(), None, 0

        def get(self, url, params=None, **kwargs):
            if str(url).startswith(TNM_API) and params:
                self.count += 1
                if self.kill_at == self.count:
                    raise KeyboardInterrupt()
                if params["bbox"] in self.down:
                    raise requests.ConnectionError("the service does not answer")
            return super().get(url, params=params, **kwargs)
    monkeypatch.setenv(tb.RENEW_ENV, "off")
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    tnm, files = Flaky(), tmp_path / "files"
    monkeypatch.setattr(requests, "get", tnm.get)
    _tile_1m(tnm, files, "CO_Full_2013", 1013)
    data, state_dir = tmp_path / "data", tmp_path / "state"
    (data / "cache").mkdir(parents=True)
    state_dir.mkdir()
    cache_dir, grid = str(data / "cache"), _grid(460000, 4410000, 30000)
    tiles = index_tiles(grid)
    box = {t: f"{t[1]},{t[0]},{t[1] + 0.25},{t[0] + 0.25}" for t in tiles}
    assert len(tiles) == 4
    for t in tiles:                                   # the answers cached before this start
        _layer().index.answers(cache_dir, *t)
    _settle(cache_dir)
    area = ad.Area("utah", "osm:Utah", "usa", 1.0, str(data), str(state_dir), min_free_gb=0)
    monkeypatch.setattr(ad, "plan_of", lambda _: SimpleNamespace(layers=[_layer()], grid=grid,
                                                                 paths=SimpleNamespace(cache=cache_dir)))

    def renewed():
        r = ad.read_state(area.state_dir, "utah")["renewed"]
        return r["passes"], r["asked"], r["open"], r["through"]

    tnm.down = {box[tiles[1]], box[tiles[2]]}         # pass 1: two tiles do not answer
    tnm.asked.clear()
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert sorted(tnm.tile_requests()) == sorted([box[tiles[0]], box[tiles[3]]]) and renewed() == (1, 2, 2, False)
    assert "2 still to ask by the next pass" in ad.read_state(area.state_dir, "utah")["renewed"]["text"]
    tnm.down, tnm.asked = set(), []
    assert ad.run_pass(area, 2) == ad.EXIT_DONE       # asks only those two
    assert tnm.tile_requests() == {box[tiles[1]]: 1, box[tiles[2]]: 1} and renewed() == (2, 4, 0, True)
    for number in (3, 4):                             # went through: nothing more in this start
        tnm.asked.clear()
        assert ad.run_pass(area, number) == ad.EXIT_DONE
        assert tnm.tile_requests() == {} and renewed() == (2, 4, 0, True)   # not called again (E4)

    _settle(cache_dir)                                # a new start, killed at its third answer
    tnm.asked, tnm.count, tnm.kill_at = [], 0, 3
    with pytest.raises(KeyboardInterrupt):
        ad.run_pass(area, 1)
    assert sorted(tnm.tile_requests()) == sorted([box[tiles[0]], box[tiles[1]]])
    tnm.asked, tnm.kill_at = [], None
    assert ad.run_pass(area, 2) == ad.EXIT_DONE       # the rest, not the two asked before the kill
    assert tnm.tile_requests() == {box[tiles[2]]: 1, box[tiles[3]]: 1}
    assert renewed() == (2, 4, 0, True)               # the killed pass's two asks counted (E6)
    from sources import renewal
    calls = []
    real = renewal.renew
    monkeypatch.setattr(renewal, "renew", lambda *a, **k: calls.append(1) or real(*a, **k))
    tnm.asked.clear()
    assert ad.run_pass(area, 3) == ad.EXIT_DONE       # went through: the renewal not called at all (E4)
    assert calls == [] and tnm.tile_requests() == {}
    monkeypatch.setattr(renewal, "renew", real)

    _settle(cache_dir)                                # E5: a new start whose pass 1 dies before it plans
    _tile_1m(tnm, files, "CO_New_2025", 1025, published="2026-01-01")
    with monkeypatch.context() as m:
        m.setattr(ad, "_planned", lambda area: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            ad.run_pass(area, 1)
    assert "renewal_since" not in ad.read_state(area.state_dir, "utah")   # the older start's time gone at once
    tnm.asked.clear()
    assert ad.run_pass(area, 2) == ad.EXIT_DONE       # starts the start's renewal: every answer, the new file seen
    assert tnm.tile_requests() == {box[t]: 1 for t in tiles} and renewed()[2:] == (0, True)

    _settle(cache_dir)                                # a new start: every answer again
    tnm.asked.clear()
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert tnm.tile_requests() == {box[t]: 1 for t in tiles} and renewed() == (1, 4, 0, True)


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
    reporter.tiles_offset, reporter.mb_offset, reporter.over_budget = 0, 0.0, None
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


def test_the_message_names_the_sample_over_the_budget(monkeypatch):
    """The reason keeps the sample that crossed the budget, not a later lower one (the server's log of 2026-11-14
    read "memory 15.4 GB over the budget of 16.7 GB")."""
    values = iter([17.2, 15.4])
    monkeypatch.setattr(ad, "memory_gb", lambda: next(values))
    reporter = _reporter(ad.Failures("cache"))
    reporter.area = dataclasses.replace(reporter.area, max_memory_gb=16.7)
    reporter.memory_peak_gb = 0.0
    reporter.sample_memory()
    reporter.sample_memory()
    assert reporter.memory_gb == 15.4 and reporter.memory_peak_gb == 17.2
    with pytest.raises(ad.Stop, match=r"^memory 17\.2 GB over the budget of 16\.7 GB, the pass is started again$"):
        reporter({"bar": "Download", "unit": "tile", "count": 1, "extra": {}, "done": False})


@pytest.mark.parametrize("held, restarts", [(3.0, True), (0.7, False)])
def test_a_big_pass_restarts_when_the_machine_runs_short(setup, monkeypatch, held, restarts):
    """Under its budget (none here), a pass of BIG_PASS_GB or more is started again while the machine has less
    memory available than it keeps; a small one goes on."""
    monkeypatch.setattr(ad, "memory_gb", lambda: held)
    monkeypatch.setattr(ad, "machine_free_gb", lambda: (1.5, 3.1))
    area = setup(SlowLayer(40))
    assert ad.run_pass(area, 1) == (ad.EXIT_RESTART if restarts else ad.EXIT_DONE)
    message = ad.read_state(area.state_dir, "land")["message"]
    if restarts:
        assert message == ("the machine has 1.5 GB of memory available, under the 3.1 GB kept, and this pass holds "
                           "3.0 GB, the pass is started again")


def _states(state_dir, now, **areas):
    """State files of areas: name -> (stage, memory_gb, seconds since written)."""
    os.makedirs(state_dir, exist_ok=True)
    for name, (stage, held, age) in areas.items():
        updated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - age))
        with open(ad.state_file(state_dir, name, ".state.json"), "w", encoding="utf-8") as f:
            json.dump({"name": name, "stage": stage, "memory_gb": held, "updated": updated}, f)


def test_only_the_largest_running_pass_restarts(tmp_path):
    """Short of memory, only the pass holding the most of the folder's running passes restarts; one waiting
    between passes, a stale state, a small pass and a finished area do not count; a tie goes to the name first."""
    state_dir, now = str(tmp_path), time.time()
    _states(state_dir, now, france=("downloading", 9.0, 2), canada=("listing", 6.0, 5), poland=("downloading", 4.0, 1),
            slovenia=("downloading", 0.7, 1), utah=("waiting", 20.0, 1), alaska=("downloading", 30.0, 600),
            spain=("done", 25.0, 1))
    assert ad.biggest_running(state_dir, "france", 9.0, now)
    assert not ad.biggest_running(state_dir, "canada", 6.0, now)
    assert not ad.biggest_running(state_dir, "poland", 4.0, now)
    assert ad.biggest_running(state_dir, "canada", 9.0, now)   # a tie: canada before france
    assert not ad.biggest_running(state_dir, "poland", 9.0, now)   # france before poland
    assert ad.biggest_running(str(tmp_path / "alone"), "france", 2.5, now)


def test_a_big_pass_waits_while_a_bigger_one_runs(setup, monkeypatch):
    """Short of memory with a bigger pass of another area running, a big pass goes on (that one restarts)."""
    monkeypatch.setattr(ad, "memory_gb", lambda: 3.0)
    monkeypatch.setattr(ad, "machine_free_gb", lambda: (1.5, 3.1))
    area = setup(SlowLayer(10))
    _states(area.state_dir, time.time(), france=("downloading", 9.0, 0))
    assert ad.run_pass(area, 1) == ad.EXIT_DONE


def test_memory_kept_free_on_the_machine(monkeypatch):
    """psutil's available memory, and a twentieth of the memory kept, at least 2 GB."""
    import psutil
    for total, kept in ((64e9, 3.2), (16e9, 2.0)):
        monkeypatch.setattr(psutil, "virtual_memory", lambda total=total: SimpleNamespace(total=total, available=5e9))
        assert REAL_MACHINE_FREE_GB() == pytest.approx((5.0, kept))


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


def test_a_stand_ins_layers_ask_again_before_their_download(setup, monkeypatch):
    """The answers a pass takes for its counts serve the first plan's download, a moment later; a stand-in's
    download comes after the first plan's whole download, so its layers ask again then, as before: a tile of
    theirs that another process cached meanwhile is not fetched."""
    class Counting(FakeLayer):
        def __init__(self, n):
            super().__init__(n)
            self.asked = 0

        def to_download(self, grid, cache_dir, update):
            self.asked += 1
            return super().to_download(grid, cache_dir, update)

    class First(Counting):
        def download_tile(self, tile, path):   # while the first plan downloads, the stand-in's tile 0 arrives
            other = second.tile_path(os.path.dirname(os.path.dirname(os.path.dirname(path))), 0)
            if not os.path.exists(other):
                os.makedirs(os.path.dirname(other), exist_ok=True)
                open(other, "wb").close()
            return super().download_tile(tile, path)
    first, second = First(3), Counting(2)
    second.folder = "fake/ifsar"
    area = setup(first)
    cache_dir = os.path.join(area.data_dir, "cache")
    plans = {"fake": SimpleNamespace(layers=[first], grid=_grid(), paths=SimpleNamespace(cache=cache_dir),
                                     source=SimpleNamespace(id="fake", instead_without_data="fake_ifsar")),
             "fake_ifsar": SimpleNamespace(layers=[second], grid=_grid(), paths=SimpleNamespace(cache=cache_dir),
                                           source=SimpleNamespace(id="fake_ifsar", instead_without_data=None))}
    monkeypatch.setattr(ad, "plan_of", lambda a: plans[a.source])
    assert ad.run_pass(area, 1) == ad.EXIT_DONE
    assert (first.asked, second.asked) == (1, 2)
    assert sorted(first.fetched) == [0, 1, 2] and second.fetched == [1]


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


def _queued(tmp_path, monkeypatch, names):
    """Areas of one state folder in the queue "usa", their tickets in the order of `names` whatever starts first;
    a pass writes "<name> <number> starts" and "... ends" to order.txt, 0.4 s apart."""
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ad, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(ad, "_ticket", lambda area: (float(names.index(area.name)), area.name))
    return [ad.Area(name, f"osm:{name}", "usa", 1.0, str(tmp_path), str(state), queue="usa") for name in names]


def _queue_pass(tmp_path, name, exit_code="0"):
    path = tmp_path / f"pass-{name}.py"
    order = str(tmp_path / "order.txt")
    path.write_text("import sys, time\nnumber = int(sys.argv[-1])\n"
                    f"open({order!r}, 'a').write('{name} %d starts\\n' % number)\ntime.sleep(0.4)\n"
                    f"open({order!r}, 'a').write('{name} %d ends\\n' % number)\nsys.exit({exit_code})\n",
                    encoding="utf-8")
    return [sys.executable, str(path)]


def _supervised(area, command, codes, **more):
    thread = threading.Thread(target=lambda: codes.__setitem__(area.name, ad.supervise(area, command, **more)),
                              daemon=True)
    thread.start()
    return thread


QUEUE_TEST_SECONDS = 60   # a supervisor stuck in its queue fails its test, never hangs it


def _until(condition, what, seconds=QUEUE_TEST_SECONDS):
    """Waits for condition() to hold; the test fails after `seconds` without it."""
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, f"not within {seconds} s: {what}"
        time.sleep(0.02)


def _ended(threads):
    _until(lambda: not any(thread.is_alive() for thread in threads), "the supervisors end")


def _order(tmp_path):
    return (tmp_path / "order.txt").read_text().split("\n")[:-1]


def test_a_queue_downloads_one_area_at_a_time_in_the_order_of_their_start(tmp_path, monkeypatch):
    """Three states started together, the last ticket's supervisor first: their passes never overlap and run in the
    tickets' order; the waiting ones say "queued", the one whose turn it is does not (its pass writes no state
    here: the supervisor's own "listing" stands, and the others wait for the lock, not for that state)."""
    areas = _queued(tmp_path, monkeypatch, ["texas", "ohio", "maine"])
    # a state that says "queued" counts for an hour: an area that kept saying so with its turn or after its pass
    # would hold the next one back for good, and the test would fail at its limit instead of passing 30 s late
    monkeypatch.setattr(ad, "RUNNING_STATE_S", 3600)
    ad.write_state(areas[0].state_dir, "texas", {"name": "texas", "stage": "stopped", "memory_gb": 6.5})
    codes, seen = {}, set()
    threads = [_supervised(area, _queue_pass(tmp_path, area.name), codes, settle_seconds=1.0)
               for area in reversed(areas)]

    def looked():
        stages = {area.name: ad.read_state(area.state_dir, area.name).get("stage") for area in areas}
        seen.update((name, stage) for name, stage in stages.items() if stage)
        return not any(thread.is_alive() for thread in threads)
    _until(looked, "the supervisors end")
    assert codes == {"texas": 0, "ohio": 0, "maine": 0}
    assert _order(tmp_path) == [
        "texas 1 starts", "texas 1 ends", "ohio 1 starts", "ohio 1 ends", "maine 1 starts", "maine 1 ends"]
    assert {("ohio", "queued"), ("maine", "queued"), ("texas", "listing"), ("maine", "listing")} <= seen
    texas = ad.read_state(areas[0].state_dir, "texas")
    assert "queued_at" not in texas and texas["memory_gb"] == 0.0   # the pass before's memory is not this one's
    assert "waiting for its turn among the downloads of the queue usa" in open(
        areas[2].file(".log"), encoding="utf-8").read()


def test_the_turn_is_given_up_while_an_area_waits_for_its_next_pass(tmp_path, monkeypatch):
    """A pass that gave up waits retry_seconds: the next area of the queue downloads meanwhile, and the first, its
    ticket kept, goes on after it."""
    texas, ohio = _queued(tmp_path, monkeypatch, ["texas", "ohio"])
    codes = {}
    _ended([_supervised(texas, _queue_pass(tmp_path, "texas", "0 if number == 2 else 4"), codes,
                        retry_seconds=1.5, settle_seconds=0.5),
            _supervised(ohio, _queue_pass(tmp_path, "ohio"), codes, settle_seconds=0.5)])
    assert codes == {"texas": 0, "ohio": 0}
    assert _order(tmp_path) == [
        "texas 1 starts", "texas 1 ends", "ohio 1 starts", "ohio 1 ends", "texas 2 starts", "texas 2 ends"]


def test_a_pass_started_again_at_once_keeps_the_turn(tmp_path, monkeypatch):
    """A pass over its memory budget (EXIT_RESTART, with progress: the first pass) is started again at once, the
    queue still this area's: the next area's pass comes after both."""
    texas, ohio = _queued(tmp_path, monkeypatch, ["texas", "ohio"])
    codes = {}
    _ended([_supervised(texas, _queue_pass(tmp_path, "texas", "0 if number == 2 else 5"), codes,
                        retry_seconds=30, settle_seconds=0.5),
            _supervised(ohio, _queue_pass(tmp_path, "ohio"), codes, settle_seconds=0.5)])
    assert codes == {"texas": 0, "ohio": 0}
    assert _order(tmp_path) == [
        "texas 1 starts", "texas 1 ends", "texas 2 starts", "texas 2 ends", "ohio 1 starts", "ohio 1 ends"]


def test_a_queued_area_stops_by_hand(tmp_path, monkeypatch):
    """The stop file ends an area that waits for its turn: no pass was started, `run` queues it again. While it
    waits its state is written again and again (the areas behind it read its age)."""
    from filelock import FileLock
    (texas,) = _queued(tmp_path, monkeypatch, ["texas"])
    monkeypatch.setattr(ad, "STATE_SECONDS", 0.1)
    codes = {}

    def state():
        return ad.read_state(texas.state_dir, "texas")
    with FileLock(ad.state_file(texas.state_dir, "usa", ".queue.lock")):   # another area's turn
        thread = _supervised(texas, _queue_pass(tmp_path, "texas"), codes, settle_seconds=0)
        _until(lambda: state().get("stage") == "queued", "texas is queued")
        first = state()
        assert (first["queue"], first["queued_at"]) == ("usa", 0.0) and "its turn" in first["message"]
        _until(lambda: state().get("updated", first["updated"]) != first["updated"], "the state is written again")
        assert state()["stage"] == "queued"
        open(texas.file(".stop"), "w").close()
        _ended([thread])
    assert codes == {"texas": 0} and state()["stage"] == "stopped"
    assert not (tmp_path / "order.txt").exists()
    assert "pass 1 starts" not in open(texas.file(".log"), encoding="utf-8").read()


def test_the_queues_lock_is_a_file_of_the_state_folder(tmp_path, monkeypatch):
    """<key>.queue.lock, a key's characters unfit for a file name replaced: an area waits while anything holds
    it (another supervisor, of this process or not) and goes on when it is free."""
    from filelock import FileLock
    (texas,) = _queued(tmp_path, monkeypatch, ["texas"])
    texas = dataclasses.replace(texas, queue="north america/usa 1m")
    codes = {}
    held = FileLock(ad.state_file(texas.state_dir, "north-america-usa-1m", ".queue.lock"))
    held.acquire()
    try:
        thread = _supervised(texas, _queue_pass(tmp_path, "texas"), codes, settle_seconds=0)
        _until(lambda: ad.read_state(texas.state_dir, "texas").get("stage") == "queued", "texas is queued")
        time.sleep(1.0)
        assert thread.is_alive() and not (tmp_path / "order.txt").exists()
    finally:
        held.release()
    _ended([thread])
    assert codes == {"texas": 0} and _order(tmp_path) == ["texas 1 starts", "texas 1 ends"]


def test_the_ticket_of_an_area(monkeypatch):
    """What started the supervisor says when (the window, for the rows' order); else the process's own start."""
    area = ad.Area("ohio", "osm:Ohio", "usa", 1.0, "d", "s", queue="usa")
    monkeypatch.setenv(ad.QUEUE_TICKET, "1794985693.25")
    assert ad._ticket(area) == (1794985693.25, "ohio")
    for value in (None, "soon"):
        monkeypatch.delenv(ad.QUEUE_TICKET, raising=False)
        if value:
            monkeypatch.setenv(ad.QUEUE_TICKET, value)
        assert ad._ticket(area) == (psutil.Process().create_time(), "ohio")


def test_who_is_ahead_in_a_queue(tmp_path):
    """Only an area that waits in the same queue with an earlier ticket, and whose supervisor still writes its
    state: one killed while it waited is passed over after RUNNING_STATE_S."""
    state_dir = str(tmp_path)
    area = ad.Area("ohio", "osm:Ohio", "usa", 1.0, "d", state_dir, queue="usa")
    waiting = {"stage": "queued", "queue": "usa"}
    ad.write_state(state_dir, "texas", {**waiting, "queued_at": 5.0})
    ad.write_state(state_dir, "maine", {**waiting, "queued_at": 3.0})
    ad.write_state(state_dir, "utah", {**waiting, "queued_at": 20.0})                 # after this one
    ad.write_state(state_dir, "alberta", {**waiting, "queue": "canada", "queued_at": 1.0})
    ad.write_state(state_dir, "idaho", {"stage": "downloading", "queue": "usa", "queued_at": 1.0})   # has its turn
    ad.write_state(state_dir, "iowa", {"stage": "queued", "queue": "usa"})            # a state cut short
    now = time.time()
    assert ad._ahead(area, (10.0, "ohio"), now) == "maine"
    assert ad._ahead(area, (4.0, "ohio"), now) == "maine" and ad._ahead(area, (2.0, "ohio"), now) is None
    assert ad._ahead(area, (3.0, "ohio"), now) == "maine"      # the same moment: by name
    assert ad._ahead(area, (10.0, "ohio"), now + ad.RUNNING_STATE_S + 5) is None


def test_no_queue_unless_asked(tmp_path, monkeypatch):
    """Without --queue a supervisor never waits, whoever holds a queue's lock."""
    seen = []
    monkeypatch.setattr(ad, "supervise", lambda area, command: seen.append(area) or 0)
    base = ["run", "land", "--area", "osm:Land", "--source", "fake", "--resolution", "1", "--data-dir", "d",
            "--state-dir", "s"]
    ad.main(base)
    ad.main(base + ["--queue", "usa"])
    assert [area.queue for area in seen] == ["", "usa"]
    monkeypatch.undo()
    monkeypatch.setattr(ad, "_take_turn", lambda *a: pytest.fail("no queue was asked for"))
    area = _area(tmp_path)
    assert ad.supervise(area, _pass(tmp_path, "sys.exit(0)\n")) == 0


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
    queued = ad.summary({**state, "stage": "queued"}, history, ad._seconds(state["updated"]))
    assert not queued["stale"] and queued["mb_s"] is None and queued["eta"] is None and queued["share"] == 0.5
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
    # a work folder of the caller's (tools/perf_cached_check.py): nothing written into the data folder's
    elsewhere = ad.plan_of(area, str(tmp_path / "elsewhere"))
    assert planned[-1][0] == str(tmp_path / "elsewhere" / "outline.geojson") and os.path.exists(planned[-1][0])
    assert elsewhere.paths.work == str(tmp_path / "elsewhere") and elsewhere.paths.data == str(data)
    capsys.readouterr()
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
