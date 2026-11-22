"""tools/perf_cached_check.py, offline: the two ways it asks about the files and the rows of a layer's tiles give the
same answers, and its steps over a made-up layer."""

import json
import os
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import area_download as ad  # noqa: E402
import cache  # noqa: E402
import perf_cached_check as pc  # noqa: E402

FOLDER = "land/blocks"


def _cache(tmp_path):
    """A layer's folder with tiles in two folders: recorded and there, recorded as missing, there without a row,
    neither; and another layer's rows beside it in the same index."""
    cache_dir = str(tmp_path / "cache")
    paths = []
    for sub in ("a", "b"):
        for name in ("ok", "missing", "adopted", "new"):
            path = os.path.join(cache_dir, "land", "blocks", sub, f"{name}.tif")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if name in ("ok", "adopted"):
                open(path, "wb").close()
            if name in ("ok", "missing"):
                cache.record(cache_dir, path, "missing" if name == "missing" else "ok", processing=3)
            paths.append(path)
    other = os.path.join(cache_dir, "land", "blocks-of-another-layer", "ok.tif")
    os.makedirs(os.path.dirname(other))
    open(other, "wb").close()
    cache.record(cache_dir, other)
    return cache_dir, paths[::-1]


def test_files_by_folder_as_each(tmp_path):
    _, paths = _cache(tmp_path)
    paths.append(str(tmp_path / "cache" / "land" / "blocks" / "no-such-folder" / "x.tif"))
    each = pc.files_each(paths)
    assert pc.files_by_folder(paths) == each
    assert each == [False, True, False, True, False, True, False, True, False]
    assert pc.files_by_folder([]) == []


def test_rows_at_once_as_each(tmp_path):
    cache_dir, paths = _cache(tmp_path)
    each = pc.rows_each(cache_dir, paths)
    assert pc.rows_at_once(cache_dir, paths, FOLDER) == each
    assert each == [None, None, ("missing", 3), ("ok", 3)] * 2
    assert pc.rows_each(cache_dir, []) == [] and pc.rows_at_once(cache_dir, [], FOLDER) == []


def test_the_steps_of_a_layer(tmp_path, monkeypatch, capsys):
    """Every step once for the plan's layer, `check` adopting the file without a row (and left out when asked)."""
    cache_dir, paths = _cache(tmp_path)

    class Layer:
        description, folder = "Made-up blocks (terrain)", FOLDER

        def tiles(self, grid):
            return paths

        def tile_path(self, cache_dir, tile):
            return tile

        def to_download(self, grid, cache_dir, update):
            due = cache.due_many(cache_dir, paths, 3)
            return [p for p, d in zip(paths, due) if d], "line"

    plan = SimpleNamespace(grid=SimpleNamespace(width=10, height=20), layers=[Layer()],
                           paths=SimpleNamespace(cache=cache_dir))
    monkeypatch.setattr(ad, "plan_of", lambda area, work: plan)
    monkeypatch.setattr(pc, "index_missing", lambda plan, cache_dir: 0)   # the made-up layer has no index
    area = ad.Area("land", "osm:Land", "fake", 1.0, str(tmp_path), str(tmp_path / "state"))
    rows = pc.measure(area, str(tmp_path / "work"), check=False)
    assert [row["step"] for row in rows] == ["plan", "tiles", "tiles", "paths", "files", "folders", "rows", "rows-all"]
    assert [row["note"] for row in rows[3:]] == ["2 folders", "4 there", "the same answers", "4 rows",
                                                 "the same answers"]
    assert pc.rows_each(cache_dir, paths).count(None) == 4      # nothing adopted
    rows = pc.measure(area, str(tmp_path / "work"))
    assert [row["step"] for row in rows[-2:]] == ["check", "prune"]
    assert [row["note"] for row in rows[-2:]] == ["2 to download, asked file by file", "no prune"]
    assert pc.rows_each(cache_dir, paths).count(None) == 2      # the two files without a row, adopted by the check
    assert "ANSWERS DIFFER" not in capsys.readouterr().out
    only = pc.measure(area, str(tmp_path / "work"), only=["folders", "check"], by_folder=True)
    assert [row["step"] for row in only] == ["plan", "tiles", "tiles", "paths", "folders", "check"]
    assert [row["note"] for row in only[-2:]] == ["4 there", "2 to download, asked by folder"]


def test_the_check_as_a_pass_asks(tmp_path, monkeypatch):
    """--by-folder sets what a pass of area_download sets, for the step only; a real Layer asks through it."""
    import sources as src
    from sources.indexes import versions
    from sources.layer import Layer
    cache_dir, paths = _cache(tmp_path)
    seen = []

    class Blocks(Layer):
        description, folder, processing = "Made-up blocks (terrain)", FOLDER, 3

        def tiles(self, grid):
            return paths

        def tile_path(self, cache_dir, tile):
            return tile

    real = versions.existing

    def existing(asked):
        seen.append(len(asked))
        return real(asked, 1)
    monkeypatch.setattr(versions, "existing", existing)
    plan = SimpleNamespace(grid=SimpleNamespace(width=10, height=20), layers=[Blocks()],
                           paths=SimpleNamespace(cache=cache_dir))
    monkeypatch.setattr(ad, "plan_of", lambda area, work: plan)
    monkeypatch.setattr(pc, "index_missing", lambda plan, cache_dir: 0)
    area = ad.Area("land", "osm:Land", "fake", 1.0, str(tmp_path), str(tmp_path / "state"))
    rows = pc.measure(area, str(tmp_path / "work"), only=["check"], by_folder=True)
    assert rows[-1]["note"] == "2 to download, asked by folder" and seen == [8]   # the two without a file or a row
    assert src.layer.EXISTING is None
    assert pc.rows_each(cache_dir, paths).count(None) == 2    # the files without a row adopted, as file by file
    rows = pc.measure(area, str(tmp_path / "work"), only=["check"])
    assert rows[-1]["note"] == "2 to download, asked file by file" and seen == [8]


def test_a_dry_prune_deletes_nothing(tmp_path):
    cache_dir, paths = _cache(tmp_path)
    kept = cache.forget

    class Index:
        def prune(self, cache_dir, tiles):
            cache.forget(cache_dir, tiles[:3])
            return 3
    assert pc.dry_prune(SimpleNamespace(index=Index()), cache_dir, paths) == 3
    assert cache.forget is kept and pc.files_each(paths).count(True) == 4
    assert pc.dry_prune(SimpleNamespace(), cache_dir, paths) == -1


def test_an_index_answer_not_cached_stops_the_tool(tmp_path, monkeypatch):
    """`tiles` would ask the service for it: the tool stops before, unless told that it may."""
    cache_dir, paths = _cache(tmp_path)
    plan = SimpleNamespace(grid=SimpleNamespace(width=10, height=20), layers=[], paths=SimpleNamespace(cache=cache_dir))
    monkeypatch.setattr(ad, "plan_of", lambda area, work: plan)
    monkeypatch.setattr(ad.Reporter, "_index_counts", lambda self: (3, 5))
    assert pc.index_missing(plan, cache_dir) == 2
    area = ad.Area("land", "osm:Land", "fake", 1.0, str(tmp_path), str(tmp_path / "state"))
    with pytest.raises(SystemExit, match="2 index answers of land are not cached"):
        pc.measure(area, str(tmp_path / "work"))
    assert [row["step"] for row in pc.measure(area, str(tmp_path / "work"), allow_index=True)] == ["plan"]


def test_the_command_reads_the_areas_state(tmp_path, monkeypatch):
    """The area, the source and the resolution from <name>.state.json; the rows also as JSON."""
    state = tmp_path / "state"
    state.mkdir()
    with pytest.raises(SystemExit, match="no state of land"):
        pc.main(["land", "--state-dir", str(state), "--data-dir", str(tmp_path), "--work", str(tmp_path / "w")])
    ad.write_state(str(state), "land", {"name": "land", "area": "osm:Land", "source": "fake", "resolution": 2.0})
    seen = []
    monkeypatch.setattr(pc, "measure", lambda *a: seen.append(a) or [{"step": "plan"}])
    out = tmp_path / "rows.json"
    assert pc.main(["land", "--state-dir", str(state), "--data-dir", str(tmp_path), "--work", str(tmp_path / "w"),
                    "--by-folder", "--only", "check", "--no-check", "--json", str(out)]) == 0
    area, work, check, allow_index, by_folder, only = seen[0]
    assert (area.name, area.area, area.source, area.resolution) == ("land", "osm:Land", "fake", 2.0)
    assert area.data_dir == str(tmp_path) and area.state_dir == str(state) and work == str(tmp_path / "w")
    assert (check, allow_index, by_folder, only) == (False, False, True, ["check"])
    assert json.loads(out.read_text(encoding="utf-8")) == {"area": "land", "source": "fake", "rows": [{"step": "plan"}]}
