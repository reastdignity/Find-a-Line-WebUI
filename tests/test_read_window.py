"""The read window of a run's record (D2): a layer's files are noted before the read (mosaic.noted_before) and after
it (cache.touch), and a file whose two notes are not the same known checksum is not known (mosaic.read_window).
Offline, on a canned cache with index rows: a file replaced at each moment of preparing a layer, every builder's
entries, the water mask, a local file, the index queries of preparing a layer."""

import hashlib
import os

import numpy as np
import pytest

import cache
import sources as src

OLD, NEW = b"the content read before", b"the content written meanwhile"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(cache_dir: str, path: str, content: bytes, row: bool = True):
    """A tile written as every writer of the cache writes one: the file moved into place, then its index row
    (cache.record hashes it) unless row is False."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with cache.replacing(path) as f:
        f.write(content)
    if row:
        cache.record(cache_dir, path)


class Tiles(src.layer.Layer):
    """Two cached tiles of a folder of their own; after_files: called once, when files() was first asked (by
    prepare_layer, before the note before the read); owners: used_entries gives one entry per tile (as
    cartoteca's and s3sheets' entries per owner)."""
    description, folder = "Window", "win/layer"

    def __init__(self, n: int = 2, after_files=None, owners: bool = False):
        self.n, self.after_files, self.owners = n, after_files, owners

    def tiles(self, grid):
        return list(range(self.n))

    def tile_path(self, cache_dir, tile):
        return os.path.join(cache_dir, "win", "layer", f"{tile}.bin")

    def files(self, grid, cache_dir):
        files = super().files(grid, cache_dir)
        if self.after_files is not None:
            call, self.after_files = self.after_files, None
            call()
        return files

    def used_entries(self, grid, cache_dir, wrote=None):
        if not self.owners:
            return super().used_entries(grid, cache_dir, wrote)
        entries = []
        for path in self.files(grid, cache_dir):
            checksums = {}
            entry = {"layer": f"Window, {os.path.basename(path)}", "folder": self.folder, "files": 1,
                     "fetched": cache.touch(cache_dir, [path], checksums), "paths": [cache.relative(cache_dir, path)]}
            entry["identity"] = cache.identity_of(entry["paths"], checksums)
            entries.append(entry)
        return entries


def _once(call):
    """call() the first time the returned function runs, never again."""
    left = [call]
    return lambda: left and left.pop()()


def _reading(monkeypatch, read: dict, before_file=None, after_all=None):
    """build_mosaic replaced by a read of each file's bytes into read (its sha256 by its path relative to the
    cache); before_file(k): before the k-th file is read; after_all(): after the last."""
    def build(files, grid, out_path, label, **kwargs):
        for k, path in enumerate(files):
            if before_file is not None:
                before_file(k)
            with open(path, "rb") as f:
                read[os.path.basename(path)] = _sha(f.read())
        if kwargs.get("wrote") is not None:
            kwargs["wrote"].extend([True] * len(files))
        if after_all is not None:
            after_all()
    monkeypatch.setattr(src.mosaic, "build_mosaic", build)


def _after(monkeypatch, name: str, call):
    """call() once, right after the first call of cache.<name> returns."""
    original, once = getattr(cache, name), _once(call)

    def wrapped(*args, **kwargs):
        answer = original(*args, **kwargs)
        once()
        return answer
    monkeypatch.setattr(cache, name, wrapped)


def _prepare(layer, cache_dir: str, out_dir: str, quiet: bool = True) -> list:
    src.used_data.clear()
    src.mosaic.prepare_layer(layer, None, cache_dir, os.path.join(out_dir, "out.npy"), "window", download=False,
                             quiet=quiet)
    entries = list(src.used_data)
    src.used_data.clear()
    return entries


def _later(cache_dir: str, path: str, recorded):
    """What a later comparison of the record with the cache's index says of one file (as `cache status` compares;
    the regression harness compares with its stored record instead)."""
    if recorded is None:
        return "not known"
    return "same" if cache.stored_checksums(cache_dir, [path])[0] == recorded else "differs"


# (moment, the tile replaced, the record's checksum of it, the content read, what a later comparison says)
CASES = [
    ("before the note before the read", 1, NEW, NEW, "same"),
    ("between the note before the read and the read", 1, None, NEW, "not known"),
    ("during the read, before its file is read", 1, None, NEW, "not known"),
    ("during the read, after its file was read", 0, None, OLD, "not known"),
    ("between the read and the note after it", 1, None, OLD, "not known"),
    ("after the note after the read", 1, OLD, OLD, "differs"),
]


@pytest.mark.parametrize("moment, tile, recorded, content, later", CASES, ids=[c[0] for c in CASES])
def test_a_file_replaced_at_each_moment(tmp_path, monkeypatch, moment, tile, recorded, content, later):
    """A file replaced while a layer is prepared (another search's --update, a cache update) is recorded with a
    checksum only when both notes saw the same one, and then it is the checksum of the bytes the read got: the
    record never names content that was not read. The other file keeps its checksum."""
    cache_dir = str(tmp_path / "cache")
    layer = Tiles()
    for t in range(2):
        _write(cache_dir, layer.tile_path(cache_dir, t), OLD + bytes([t]))
    path = layer.tile_path(cache_dir, tile)
    replace = lambda: _write(cache_dir, path, NEW + bytes([tile]))
    read = {}
    if moment.startswith("before the note"):
        layer.after_files = replace
    if moment.startswith("between the note before"):
        _after(monkeypatch, "stored_checksums", replace)
    if moment.startswith("during"):
        _reading(monkeypatch, read, before_file=lambda k: k == 1 and replace())
    elif moment.startswith("between the read"):
        _reading(monkeypatch, read, after_all=replace)
    else:
        _reading(monkeypatch, read)
    if moment.startswith("after the note"):
        _after(monkeypatch, "touch", replace)
    [entry] = _prepare(layer, cache_dir, str(tmp_path))
    relative = cache.relative(cache_dir, path)
    sums = dict(zip(entry["paths"], entry["identity"]["sha256"]))
    assert read[os.path.basename(path)] == _sha(content + bytes([tile]))
    assert sums[relative] == (None if recorded is None else _sha(recorded + bytes([tile])))
    for name, sha in sums.items():  # a known checksum is that of the bytes read
        assert sha is None or sha == read[name.rsplit("/", 1)[1]]
    other = cache.relative(cache_dir, layer.tile_path(cache_dir, 1 - tile))
    assert sums[other] == _sha(OLD + bytes([1 - tile]))
    assert _later(cache_dir, relative, sums[relative]) == later
    assert list(entry) == ["layer", "folder", "files", "fetched", "paths", "identity"] and entry["files"] == 2


def test_the_limit_left_a_row_written_after_both_notes(tmp_path, monkeypatch):
    """What the two notes cannot see (docs/known-bugs.md, "The data record"): a writer moves the new file in first
    and writes its row after (cache.record hashes the file, waits for the index's lock), so a read that falls
    between the two, with both notes before the row, is recorded with the old checksum although the new bytes were
    read. Compared with the index now (`cache status`) it reads "differs"; compared with a stored record made
    before the replacement (the regression harness's) it reads "same" although other bytes were read."""
    cache_dir = str(tmp_path / "cache")
    layer = Tiles()
    for t in range(2):
        _write(cache_dir, layer.tile_path(cache_dir, t), OLD + bytes([t]))
    path = layer.tile_path(cache_dir, 1)
    read = {}
    _reading(monkeypatch, read, before_file=lambda k: k == 1 and _write(cache_dir, path, NEW, row=False))
    _after(monkeypatch, "touch", lambda: cache.record(cache_dir, path))
    [entry] = _prepare(layer, cache_dir, str(tmp_path))
    recorded = entry["identity"]["sha256"][1]
    assert read["1.bin"] == _sha(NEW) and recorded == _sha(OLD + bytes([1]))
    assert _later(cache_dir, cache.relative(cache_dir, path), recorded) == "differs"


def test_a_quiet_cache_keeps_every_checksum(tmp_path, monkeypatch):
    """Nothing replaced: every checksum as the note after the read alone gave it (the record of before)."""
    cache_dir = str(tmp_path / "cache")
    layer = Tiles(3)
    for t in range(3):
        _write(cache_dir, layer.tile_path(cache_dir, t), OLD + bytes([t]))
    _reading(monkeypatch, {})
    [entry] = _prepare(layer, cache_dir, str(tmp_path))
    assert entry["identity"]["sha256"] == [_sha(OLD + bytes([t])) for t in range(3)]
    assert entry["identity"]["sha256"] == cache.stored_checksums(cache_dir, entry["paths"])


def test_every_entry_of_a_layer(tmp_path, monkeypatch):
    """The rule is applied where every builder's entries pass (prepare_layer, after used_entries): a layer with one
    entry per owner (cartoteca's, s3sheets') gets it in each entry; a file adopted by hand (no checksum in its row)
    stays not known."""
    cache_dir = str(tmp_path / "cache")
    layer = Tiles(3, owners=True)
    for t in range(3):
        _write(cache_dir, layer.tile_path(cache_dir, t), OLD + bytes([t]))
    db = cache._connect(cache_dir, "win")
    with db:
        db.execute("UPDATE files SET sha256 = NULL WHERE path = ?", ("layer/2.bin",))
    db.close()
    _reading(monkeypatch, {}, before_file=lambda k: k == 1 and _write(cache_dir, layer.tile_path(cache_dir, 0), NEW))
    entries = _prepare(layer, cache_dir, str(tmp_path))
    assert [e["identity"]["sha256"] for e in entries] == [[None], [_sha(OLD + bytes([1]))], [None]]
    assert [e["layer"] for e in entries] == ["Window, 0.bin", "Window, 1.bin", "Window, 2.bin"]


def test_read_window_leaves_the_rest():
    """read_window changes only the checksums of entries with paths: no key added, none moved, an entry of a local
    file (`file`, its own `identity`) and one without a record as they were."""
    entries = [{"layer": "a", "paths": ["x/1", "x/2", "x/3"], "identity": {"sha256": ["1" * 64, "2" * 64, None]},
                "credit": {}},
               {"layer": "file", "file": "/elsewhere/dem.tif", "identity": {"size": 1, "modified": "t"}},
               {"layer": "old", "paths": ["x/4"]}]
    out = src.mosaic.read_window(entries, {"x/1": "1" * 64, "x/2": "9" * 64, "x/3": None, "x/4": "4" * 64})
    assert out is entries
    assert entries == [{"layer": "a", "paths": ["x/1", "x/2", "x/3"], "identity": {"sha256": ["1" * 64, None, None]},
                        "credit": {}},
                       {"layer": "file", "file": "/elsewhere/dem.tif", "identity": {"size": 1, "modified": "t"}},
                       {"layer": "old", "paths": ["x/4"]}]
    assert list(entries[0]) == ["layer", "paths", "identity", "credit"]


def test_a_local_file_is_not_noted(tmp_path, monkeypatch):
    """A layer of a local file (FileLayer: --elevation-file) is outside the cache: no note before the read, no index
    made, its entry's size and time as before."""
    import rasterio as rio
    from rasterio.transform import from_origin
    path = str(tmp_path / "local" / "dem.tif")
    os.makedirs(os.path.dirname(path))
    with rio.open(path, "w", driver="GTiff", width=2, height=2, count=1, dtype="float32", crs="EPSG:2180",
                  transform=from_origin(0, 2, 1, 1)) as f:
        f.write(np.ones((1, 2, 2), np.float32))
    cache_dir = str(tmp_path / "cache")
    asked = []
    original = cache.stored_checksums
    monkeypatch.setattr(cache, "stored_checksums", lambda d, paths: asked.append(list(paths)) or original(d, paths))
    _reading(monkeypatch, {})
    [entry] = _prepare(src.layers.files.FileLayer("DEM", path), cache_dir, str(tmp_path))
    assert asked == [[]] and entry == {"layer": "DEM", "file": os.path.abspath(path),
                                       "identity": cache.file_identity(path)}
    assert not os.path.exists(cache_dir)


def test_the_water_mask_is_noted_before_it_is_read(tmp_path, monkeypatch):
    """The water body mask (filling.water_body_mask, outside prepare_layer) takes the same two notes, the first
    before constant_category, which opens its files too: on both of its ways."""
    cache_dir = str(tmp_path / "cache")
    mask = Tiles()
    for t in range(2):
        _write(cache_dir, mask.tile_path(cache_dir, t), OLD + bytes([t]))
    monkeypatch.setattr(src.filling, "WATER_MASK", mask)
    replace = lambda: _write(cache_dir, mask.tile_path(cache_dir, 1), NEW)
    monkeypatch.setattr(src.filling, "constant_category", lambda files, grid: replace())  # reads: the window
    monkeypatch.setattr(src.filling, "build_mosaic", lambda *a, **k: np.zeros((1, 1), np.uint8))
    src.used_data.clear()
    src.filling.water_body_mask(None, cache_dir, str(tmp_path / "wbm.npy"), download=False)
    [entry] = src.used_data
    assert entry["identity"]["sha256"] == [_sha(OLD + bytes([0])), None]
    # the way of a constant mosaic: replaced after constant_category gave its value (the mosaic not read again)
    _write(cache_dir, mask.tile_path(cache_dir, 1), OLD + bytes([1]))
    monkeypatch.setattr(src.filling, "constant_category", lambda files, grid: 1)
    monkeypatch.setattr(src.filling, "_constant_mosaic", lambda *a: replace() or np.zeros((1, 1), np.uint8))
    src.used_data.clear()
    src.filling.water_body_mask(None, cache_dir, str(tmp_path / "wbm.npy"), download=False)
    [entry] = src.used_data
    src.used_data.clear()
    assert entry["identity"]["sha256"] == [_sha(OLD + bytes([0])), None]


def _queries(monkeypatch):
    """The connections opened to the cache's indexes and the statements run on them from now on."""
    connections, statements, connect = [], [], cache._connect

    def traced(cache_dir, top):
        db = connect(cache_dir, top)
        connections.append(top)
        db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(cache, "_connect", traced)
    return connections, statements


def test_the_index_queries_of_preparing_a_layer(tmp_path, monkeypatch):
    """The cost of the note before the read, pinned: one connection to the index of the layer's folder and one
    SELECT of the stored checksum per file, beside the line about tiles without data (cache.states) and the note
    after the read (cache.touch), and nothing written by it."""
    cache_dir = str(tmp_path / "cache")
    layer = Tiles(5)
    for t in range(5):
        _write(cache_dir, layer.tile_path(cache_dir, t), OLD + bytes([t]))
    _reading(monkeypatch, {})
    connections, statements = _queries(monkeypatch)
    _prepare(layer, cache_dir, str(tmp_path), quiet=False)
    assert connections == ["win", "win", "win"]  # states, the note before the read, touch
    selects = [s for s in statements if s.startswith("SELECT sha256 FROM files")]
    assert len(selects) == 5
    connections.clear()
    statements.clear()
    src.mosaic.noted_before(cache_dir, [layer.tile_path(cache_dir, t) for t in range(5)])
    assert connections == ["win"]
    assert not [s for s in statements if s.split()[0].upper() in ("INSERT", "UPDATE", "DELETE", "REPLACE")]
    assert [s for s in statements if s.startswith("SELECT")] == selects
