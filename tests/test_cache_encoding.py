"""The encoding of the cache's float tiles: LERC_ZSTD within 5 mm (sources.layer._write_tile), the old tiles
(deflate, or a provider's file as it came) written again before a search reads them (sources.layer.reencode,
download_layers) or all at once (`cache migrate`, update.migrate)."""

import hashlib
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import rasterio as rio
from rasterio.crs import CRS
from rasterio.transform import from_origin

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import cache  # noqa: E402
import sources as src  # noqa: E402
import update  # noqa: E402
from grid import Grid  # noqa: E402
from sources import filling, layer as tiles  # noqa: E402
from sources.composed import ComposedLayer  # noqa: E402
from sources.readers.download import Download  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import sk_tiles  # noqa: E402

EPS = 0.0051  # m: the bound of the tiles (5 mm) and the float32 rounding of a height of some hundred metres
UTM = "EPSG:25832"


def _band(seed: int = 1, shape=(300, 280), centimetres: bool = False) -> np.ndarray:
    """Terrain-like heights with a hole of NaN (and a few below VALID_MIN)."""
    rng = np.random.default_rng(seed)
    z = np.cumsum(np.cumsum(rng.normal(0, 0.3, shape), axis=0), axis=1).astype(np.float32) + 500
    if centimetres:
        z = np.round(z, 2).astype(np.float32)
    z[10:30, 20:40] = np.nan
    return z


def _old(path, band, crs=UTM, transform=None, tags=None, nodata=np.nan, dtype="float32", **options):
    """A tile as the cache wrote it before LERC (deflate, predictor 3), or another file with options."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    options = options or dict(compress="deflate", predictor=3 if dtype.startswith("float") else 2, tiled=True)
    with rio.open(path, "w", driver="GTiff", height=band.shape[0], width=band.shape[1], count=1, dtype=dtype,
                  crs=crs, transform=transform or from_origin(500000, 5500000, 1, 1), nodata=nodata, **options) as dst:
        dst.write(band.astype(dtype), 1)
        if tags:
            dst.update_tags(**tags)
    return path


def _compression(path):
    with rio.open(path) as f:
        return f.tags(ns="IMAGE_STRUCTURE").get("COMPRESSION")


def _read(path):
    with rio.open(path) as f:
        return f.read(1, masked=True).astype(np.float32).filled(np.nan)


def _values(path):
    """What the mosaic reads of a file (sources.layer.float_band)."""
    with rio.open(path) as f:
        return tiles.float_band(f)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class FakeLayer(ComposedLayer):
    """A layer of numbered tiles in <cache>/fake/<name>, written by the test; rewrites as set."""

    def __init__(self, name, count, rewrites=True):
        self.description, self.folder, self.count = name, f"fake/{name}", count
        self._rewrites = rewrites

    @property
    def rewrites(self):
        return self._rewrites

    def tiles(self, grid):
        return list(range(self.count))

    def tile_path(self, cache_dir, tile):
        return os.path.join(cache_dir, "fake", self.description, f"{tile}.tif")

    def download_tile(self, tile, path):
        raise AssertionError("everything is cached")


GRID = Grid(500000, 5500000, 1.0, 100, 100, UTM)


# The writer

def test_tile_is_lerc_within_5_mm(tmp_path):
    band, path = _band(), str(tmp_path / "t.tif")
    tiles._write_tile(path, band, UTM, from_origin(500000, 5500000, 1, 1))
    assert _compression(path) == "LERC_ZSTD"
    with rio.open(path) as f:
        assert f.block_shapes == [(256, 256)] and np.isnan(f.nodata)
    back = _read(path)
    assert np.array_equal(np.isnan(back), np.isnan(band))
    assert np.nanmax(np.abs(back - band)) <= EPS
    assert os.path.getsize(path) < 0.7 * _size_deflate(tmp_path, band)


def _size_deflate(tmp_path, band):
    path = str(tmp_path / "d.tif")
    tiles._write_tile(path, band, UTM, from_origin(500000, 5500000, 1, 1), max_z_error=None)
    return os.path.getsize(path)


def test_lossless_profile_stays_available(tmp_path):
    """max_z_error None: deflate with predictor 3, the values exactly (the cache's tiles of before; the averaged
    Slovak tiles until 2026-11-08)."""
    band, path = _band(), str(tmp_path / "t.tif")
    tiles._write_tile(path, band, UTM, from_origin(500000, 5500000, 1, 1), max_z_error=None)
    assert _compression(path) == "DEFLATE" and np.array_equal(_read(path), band, equal_nan=True)
    assert tiles.old_encoding(path)


def test_old_encoding_tells_the_files_apart(tmp_path):
    band = _band()
    assert tiles.old_encoding(_old(str(tmp_path / "deflate.tif"), band))
    assert tiles.old_encoding(_old(str(tmp_path / "plain.tif"), band, compress="none"))
    assert tiles.old_encoding(_old(str(tmp_path / "f64.tif"), band, dtype="float64", compress="lzw"))
    lerc = str(tmp_path / "lerc.tif")
    tiles._write_tile(lerc, band, UTM, from_origin(0, 0, 1, 1))
    assert not tiles.old_encoding(lerc)
    assert not tiles.old_encoding(_old(str(tmp_path / "lerc_plain.tif"), band, compress="lerc", max_z_error=0))
    assert not tiles.old_encoding(_old(str(tmp_path / "int16.tif"), np.nan_to_num(band), dtype="int16", nodata=-32768))
    assert not tiles.old_encoding(_old(str(tmp_path / "uint8.tif"), np.zeros((20, 20)), dtype="uint8", nodata=255))
    (tmp_path / "text.json").write_text("{}")
    assert not tiles.old_encoding(str(tmp_path / "text.json"))
    assert not tiles.old_encoding(str(tmp_path / "missing.tif"))
    two = str(tmp_path / "two.tif")
    with rio.open(two, "w", driver="GTiff", height=10, width=10, count=2, dtype="float32", crs=UTM,
                  transform=from_origin(0, 0, 1, 1)) as dst:
        dst.write(np.ones((2, 10, 10), np.float32))
    assert not tiles.old_encoding(two)


# reencode

def test_reencode_keeps_values_georeference_and_tags(tmp_path):
    compound = CRS.from_wkt(CRS.from_user_input("EPSG:25832+7837").to_wkt())
    band = _band()
    band[40:60, 40:60] = -9999.0  # the provider's nodata, below VALID_MIN
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), band, crs=compound, nodata=-9999.0,
                transform=from_origin(412000.5, 5448000, 0.5, 0.5), tags={"SURVEY": "2020", "OTHER": "x"})
    with rio.open(path) as f:
        before = (f.crs.to_wkt(), f.transform, f.tags(), tiles.float_band(f))
    assert tiles.reencode(cache_dir, path)
    assert _compression(path) == "LERC_ZSTD" and not tiles.old_encoding(path)
    with rio.open(path) as f:
        assert f.crs.to_wkt() == before[0] and f.transform == before[1] and np.isnan(f.nodata)
        assert f.tags()["SURVEY"] == "2020" and f.tags()["OTHER"] == "x"
        after = f.read(1)
    expected = before[3]  # what the mosaic reads of the old file
    assert np.array_equal(np.isnan(after), np.isnan(expected)) and np.isnan(after[45, 45])
    assert np.nanmax(np.abs(after - expected)) <= EPS


def test_reencode_updates_only_the_sha256_of_the_row(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    cache.record(cache_dir, path, "ok", "https://example.org/0.tif", '"etag"', "Mon", "2020", 3)
    row = cache.info(cache_dir, path)
    assert row["sha256"] == _sha(path)
    assert tiles.reencode(cache_dir, path)
    after = cache.info(cache_dir, path)
    assert after["sha256"] == _sha(path) and after["sha256"] != row["sha256"]
    assert {k: v for k, v in after.items() if k != "sha256"} == {k: v for k, v in row.items() if k != "sha256"}
    with sqlite3.connect(os.path.join(cache_dir, "fake", "index.sqlite")) as db:
        assert len(db.execute("PRAGMA table_info(files)").fetchall()) == 11
        assert [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")] == ["files"]


def test_reencode_of_a_file_with_no_row_makes_none(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    assert tiles.reencode(cache_dir, path)
    assert cache.info(cache_dir, path) is None


def test_a_lerc_tile_is_never_encoded_again(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = os.path.join(cache_dir, "fake", "a", "0.tif")
    tiles._write_tile(path, _band(), UTM, from_origin(0, 0, 1, 1))
    first, stamp = _sha(path), os.stat(path).st_mtime_ns
    assert not tiles.reencode(cache_dir, path) and not tiles.reencode(cache_dir, path)
    assert _sha(path) == first and os.stat(path).st_mtime_ns == stamp
    old = _old(os.path.join(cache_dir, "fake", "a", "1.tif"), _band())
    assert tiles.reencode(cache_dir, old) and not tiles.reencode(cache_dir, old)


def test_an_integer_file_is_untouched(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), np.nan_to_num(_band()), dtype="int16", nodata=-32768)
    before = _sha(path)
    assert not tiles.reencode(cache_dir, path) and _sha(path) == before


def test_a_centimetre_tile_keeps_the_sea_fill_within_eps(tmp_path):
    """Schleswig-Holstein's sea is 1.30 m in whole centimetres: after the LERC rewrite the pixels at the fill are
    still within SEA_FILL_EPS of it, and those one centimetre away still are not."""
    rng = np.random.default_rng(5)
    z = np.round(rng.uniform(1.20, 1.40, (120, 120)), 2).astype(np.float32)
    z[:60] = np.float32(1.30)
    z[60:] = np.round(rng.uniform(2.0, 40.0, (60, 120)), 2)
    sea = np.zeros(z.shape, bool)
    sea[:90] = True
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), z)
    assert tiles.reencode(cache_dir, path)
    new = _read(path)
    assert np.abs(new - z).max() <= EPS
    # fill_water's own rule on both: the same water, the whole fill kept
    old_water = filling.water_with_data(z, None, sea, 1.30)
    assert np.array_equal(filling.water_with_data(new, None, sea, 1.30), old_water)
    assert np.abs(new[:60] - 1.30).max() <= filling.SEA_FILL_EPS and old_water[:60].all()
    assert not old_water[60:90].any()


# Concurrency

def test_two_threads_convert_a_tile_once(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    start = threading.Barrier(4)

    def go():
        start.wait()
        return tiles.reencode(cache_dir, path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [f.result() for f in [pool.submit(go) for _ in range(4)]]
    assert sorted(results) == [False, False, False, True] and not tiles.old_encoding(path)


def test_two_processes_convert_a_tile_once(tmp_path):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from sources import layer; "
            "print(layer.reencode(sys.argv[2], sys.argv[3]))")
    procs = [subprocess.Popen([sys.executable, "-c", code, ROOT, cache_dir, path], stdout=subprocess.PIPE, text=True,
                              cwd=str(tmp_path)) for _ in range(3)]
    answers = sorted(p.communicate(timeout=300)[0].strip() for p in procs)
    assert answers == ["False", "False", "True"] and not tiles.old_encoding(path)


def test_replace_refused_keeps_the_old_tile_and_the_next_call_converts(tmp_path, monkeypatch):
    """Windows refuses os.replace over a file another process has open: the old tile stays (exact values, no
    .part left) after REPLACE_SECONDS, and the next call converts it."""
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    cache.record(cache_dir, path)
    before = _sha(path)
    monkeypatch.setattr(tiles, "REPLACE_SECONDS", 0.5)
    real = os.replace

    def refuse(a, b):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(tiles.os, "replace", refuse)
    assert not tiles.reencode(cache_dir, path)
    monkeypatch.setattr(tiles.os, "replace", real)
    assert _sha(path) == before and tiles.old_encoding(path)
    assert cache.info(cache_dir, path)["sha256"] == before
    assert [f for f in os.listdir(os.path.dirname(path)) if f != "0.tif"] == []
    assert tiles.reencode(cache_dir, path) and not tiles.old_encoding(path)


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace a file that is open")
def test_a_tile_open_elsewhere_is_left_on_windows(tmp_path, monkeypatch):
    cache_dir = str(tmp_path / "cache")
    path = _old(os.path.join(cache_dir, "fake", "a", "0.tif"), _band())
    monkeypatch.setattr(tiles, "REPLACE_SECONDS", 0.5)
    before = _sha(path)
    with open(path, "rb"):
        assert not tiles.reencode(cache_dir, path)
        converted, left = tiles.reencode_paths(cache_dir, [path], quiet=True)
        assert (converted, left) == (0, 1)
    assert _sha(path) == before
    assert tiles.reencode(cache_dir, path)


# The lazy step of download_layers

def test_a_search_leaves_none_of_its_tiles_old(tmp_path, monkeypatch):
    cache_dir = str(tmp_path / "cache")
    ours, provider = FakeLayer("ours", 3), FakeLayer("theirs", 2, rewrites=False)
    paths = [_old(ours.tile_path(cache_dir, t), _band(t)) for t in ours.tiles(GRID)]
    kept = [_old(provider.tile_path(cache_dir, t), _band(10 + t)) for t in provider.tiles(GRID)]
    for p in paths + kept:
        cache.record(cache_dir, p)
    untouched = [_sha(p) for p in kept]
    expected = [_values(p) for p in paths]
    stale = {p: cache.info(cache_dir, p)["sha256"] for p in paths}
    src.download_layers([(ours, "terrain"), (provider, "surface")], GRID, cache_dir)
    assert not any(tiles.old_encoding(p) for p in paths)
    for p, was, z in zip(paths, stale.values(), expected):
        assert np.nanmax(np.abs(_read(p) - z)) <= EPS and cache.info(cache_dir, p)["sha256"] == _sha(p) != was
    assert [_sha(p) for p in kept] == untouched and all(tiles.old_encoding(p) for p in kept)
    # again: nothing to do, and the files are not looked at (a per-process memo)
    calls, real = [], tiles.old_encoding
    monkeypatch.setattr(tiles, "old_encoding", lambda p: calls.append(p) or real(p))
    src.download_layers([(ours, "terrain")], GRID, cache_dir)
    assert calls == []


def test_a_result_does_not_depend_on_the_threads(tmp_path, monkeypatch):
    cache_dir = str(tmp_path / "cache")
    paths = [_old(os.path.join(cache_dir, "fake", "a", f"{t}.tif"), _band(t)) for t in range(6)]
    copy = str(tmp_path / "copy")
    import shutil
    shutil.copytree(cache_dir, copy)
    tiles._NEW.clear()
    assert tiles.reencode_paths(cache_dir, paths, threads=1, quiet=True) == (6, 0)
    tiles._NEW.clear()
    assert tiles.reencode_paths(copy, [p.replace(cache_dir, copy) for p in paths], threads=8, quiet=True) == (6, 0)
    for p in paths:
        assert _sha(p) == _sha(p.replace(cache_dir, copy))


# A provider's file written by Download

class _Tile:
    url, label = "", "t"


def test_download_writes_a_float_raster_as_a_tile_and_keeps_the_rest(http_server, tmp_path):
    values = np.arange(60 * 50, dtype=np.float32).reshape(60, 50) / 10 + 100
    values[0:10, 0:10] = -9999.0
    transform = from_origin(412000, 5448000, 1.0, 1.0)
    float_file = str(tmp_path / "float.tif")
    _old(float_file, values, nodata=-9999.0, transform=transform, tags={"A": "b"}, tiled=False, compress="lzw")
    with rio.open(float_file, "r+") as f:  # a provider's overviews
        f.build_overviews([2, 4])
    int_file = str(tmp_path / "int.tif")
    _old(int_file, np.nan_to_num(values).astype(np.int16), dtype="int16", nodata=-32768, transform=transform)
    page = b"<html>no raster</html>"
    for name, body in (("float.tif", open(float_file, "rb").read()), ("int.tif", open(int_file, "rb").read()),
                       ("page.html", page)):
        http_server.add("/f/" + name, body, "image/tiff")
    reader = Download("test", lambda t: t.url, lambda t: t.label, binary_types=("tiff",))
    assert reader.rewrites
    tile = _Tile()
    tile.url = http_server.url("/f/float.tif")
    out = str(tmp_path / "out" / "float.tif")
    fetched = reader.fetch(tile, out)
    assert fetched.received == os.path.getsize(float_file)  # what was downloaded, not what is kept
    assert _compression(out) == "LERC_ZSTD" and not tiles.old_encoding(out)
    with rio.open(out) as f:
        assert f.overviews(1) == [] and np.isnan(f.nodata) and f.transform == transform and f.crs == CRS.from_epsg(25832)
        assert f.tags()["A"] == "b"
        band = f.read(1)
    assert np.isnan(band[:10, :10]).all() and np.nanmax(np.abs(band[10:] - values[10:])) <= EPS
    assert not [n for n in os.listdir(tmp_path / "out") if n != "float.tif"]
    for name, body in (("int.tif", open(int_file, "rb").read()), ("page.html", page)):  # saved as they came
        tile.url = http_server.url("/f/" + name)
        reader.fetch(tile, str(tmp_path / "out" / name))
        assert (tmp_path / "out" / name).read_bytes() == body


# cache migrate

def _mixed_cache(tmp_path):
    """A small cache: one tile of a rewriting layer in each of deflate / LERC, a Copernicus float tile as it came,
    NASADEM's int16, the water mask's uint8, a Slovak mirror tile (LERC), averaged ones (deflate, the mirror's
    tiles of before, and ZSTD, its tiles since 2026-11-08: tools/sk_tiles.py) and a non-tile file."""
    cache_dir = str(tmp_path / "data" / "cache")
    os.makedirs(cache_dir)
    cache.check_layout(cache_dir)
    files = {}
    files["sheet"] = _old(os.path.join(cache_dir, "poland", "nmt", "2020_N-34-1.tif"), _band(1))
    files["lerc"] = os.path.join(cache_dir, "poland", "nmt", "2021_N-34-2.tif")
    tiles._write_tile(files["lerc"], _band(2), UTM, from_origin(500000, 5500000, 1, 1))
    files["cop"] = _old(os.path.join(cache_dir, "copernicus30", "2021", "dem", "N50E019.tif"), _band(3), crs="EPSG:4326",
                        transform=from_origin(19, 51, 1 / 3600, 1 / 3600), nodata=None, tiled=False, compress="deflate")
    files["nasadem"] = _old(os.path.join(cache_dir, "nasadem", "v1", "N50E019.tif"), np.nan_to_num(_band(4)),
                            dtype="int16", nodata=-32768)
    files["wbm"] = _old(os.path.join(cache_dir, "copernicus30", "2021", "wbm", "N50E019.tif"), np.zeros((20, 20)),
                        dtype="uint8", nodata=255)
    files["slovak"] = os.path.join(cache_dir, "slovakia", "dmr5", "5.0", "epsg8353-1m-2km", "x", "t.tif")
    tiles._write_tile(files["slovak"], _band(5), "EPSG:8353", from_origin(0, 0, 1, 1))
    files["avg"] = _old(os.path.join(cache_dir, "slovakia", "dmr5", "5.0", "epsg8353-2m-2km", "x", "t.tif"), _band(6))
    files["avg_zstd"] = os.path.join(cache_dir, "slovakia", "dmp1", "1.0", "epsg8353-5m-2km", "x", "t.tif")
    sk_tiles._write_averaged(files["avg_zstd"], _band(7), "EPSG:8353", from_origin(0, 0, 5, 5))
    for key, p in files.items():
        cache.record(cache_dir, p)
    return cache_dir, files


def test_migrate_converts_what_is_ours_and_a_second_run_nothing(tmp_path, capsys):
    cache_dir, files = _mixed_cache(tmp_path)
    shas = {k: _sha(p) for k, p in files.items()}
    expected = {k: _values(files[k]) for k in ("sheet", "cop")}
    found = update.old_tiles(cache_dir)
    assert {os.path.basename(p) for paths in found.values() for p in paths} == {"2020_N-34-1.tif", "N50E019.tif"}
    assert update.migrate(cache_dir, dry_run=True) == 0 and _sha(files["sheet"]) == shas["sheet"]
    assert "to convert" in capsys.readouterr().out
    assert update.migrate(cache_dir, "poland") == 0  # one top-level folder
    assert not tiles.old_encoding(files["sheet"]) and tiles.old_encoding(files["cop"])
    assert update.migrate(cache_dir) == 0
    out = capsys.readouterr().out
    assert "copernicus30: 1 of 1 tiles converted" in out and "GB ->" in out
    for key in ("sheet", "cop"):
        assert not tiles.old_encoding(files[key]) and np.nanmax(np.abs(_read(files[key]) - expected[key])) <= EPS
    for key in ("lerc", "nasadem", "wbm", "slovak", "avg", "avg_zstd"):
        assert _sha(files[key]) == shas[key], key  # not ours, or ours already
    assert update.old_tiles(cache_dir) == {}
    assert update.migrate(cache_dir) == 0 and "Nothing to migrate" in capsys.readouterr().out
    after = {k: _sha(p) for k, p in files.items()}
    assert update.migrate(cache_dir) == 0 and {k: _sha(p) for k, p in files.items()} == after


def test_migrate_reports_tiles_open_elsewhere_with_exit_code_1(tmp_path, monkeypatch, capsys):
    cache_dir, files = _mixed_cache(tmp_path)
    monkeypatch.setattr(tiles, "REPLACE_SECONDS", 0.2)
    real = os.replace
    monkeypatch.setattr(tiles.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError(5, "open")))
    data = str(tmp_path / "data")
    assert update.main(["--data-dir", data, "cache", "migrate", "poland"]) == 1
    assert "1 left" in capsys.readouterr().out and tiles.old_encoding(files["sheet"])
    monkeypatch.setattr(tiles.os, "replace", real)
    assert update.main(["--data-dir", data, "cache", "migrate"]) == 0
    assert not tiles.old_encoding(files["sheet"]) and not tiles.old_encoding(files["cop"])


def test_status_counts_the_tiles_to_migrate(tmp_path, capsys):
    cache_dir, files = _mixed_cache(tmp_path)
    update.status(cache_dir, str(tmp_path / "runs"))
    assert "Tiles in the older encoding: 2" in capsys.readouterr().out
    update.migrate(cache_dir)
    capsys.readouterr()
    update.status(cache_dir, str(tmp_path / "runs"))
    assert "older encoding" not in capsys.readouterr().out


def test_an_averaged_zstd_tile_is_never_encoded_again(tmp_path, monkeypatch, capsys):
    """The Slovak mirror's averaged tiles in ZSTD (tools/sk_tiles.py since 2026-11-08) are one float band that is not
    LERC, which old_encoding calls old by its header alone: only the layer's rewrites (False: GridTiles copies the
    mirror's files) keeps them from being written again lossily. In a scratch data folder holding one, cached as
    a search caches it: `cache migrate --dry-run` and `cache status` find nothing, and a search's download_layers
    over it (the catalogue's DMR 5.0 at 2 m, read from the mirror's 2m folder) hands it to no re-encoding."""
    monkeypatch.setattr(src.net, "_get", lambda *a, **k: pytest.fail("no network with a mirror"))
    data = tmp_path / "data"
    cache_dir = str(data / "cache")
    cache.check_layout(cache_dir)
    mirror = tmp_path / "mirror"
    i, j = -241, -601
    band = _band(8, shape=(1000, 1000))
    name = src.grid_tile_name(i, j)
    tile = mirror / "slovakia" / "dmr5" / "2m" / name
    sk_tiles._write_averaged(str(tile), band, "EPSG:8353", from_origin(i * 2000, (j + 1) * 2000, 2, 2))
    (mirror / "slovakia" / "dmr5" / "2m" / "index.json").write_text(
        '{"tiles": {"%d_%d": "%s"}, "resolution": 2.0, "from_resolution": 1.0}' % (i, j, _sha(str(tile))),
        encoding="utf-8")
    monkeypatch.setenv(src.MIRROR_ENV, str(mirror))
    layer = src.SOURCES["slovakia"].nmt
    grid = Grid(i * 2000 + 200, (j + 1) * 2000 - 200, 2.0, 300, 400, "EPSG:8353")
    assert layer.resolution(2.0) == 2.0 and len(layer.tiles(grid)) == 1
    src.download_layers([(layer, "terrain")], grid, cache_dir)  # copied from the mirror as a search copies it
    path = layer.tile_path(cache_dir, layer.tiles(grid)[0])
    assert path.replace(os.sep, "/").endswith("slovakia/dmr5/5.0/epsg8353-2m-2km/" + name)
    sha = _sha(path)
    assert sha == _sha(str(tile)) and sk_tiles.is_zstd(path) and cache.info(cache_dir, path)["sha256"] == sha
    assert tiles.old_encoding(path) and not layer.rewrites and update.rewriting_layer(cache.relative(cache_dir, path)) is None

    assert update.old_tiles(cache_dir) == {}
    assert update.main(["--data-dir", str(data), "cache", "migrate", "--dry-run"]) == 0
    assert "Nothing to migrate" in capsys.readouterr().out
    update.status(cache_dir, str(data / "runs"))
    assert "older encoding" not in capsys.readouterr().out
    given, real = [], tiles.reencode_paths
    monkeypatch.setattr(tiles, "reencode_paths", lambda cache_dir, paths, *a, **k: given.append(list(paths)) or real(
        cache_dir, paths, *a, **k))
    tiles._NEW.clear()
    src.download_layers([(layer, "terrain")], grid, cache_dir)  # cached now: nothing copied, nothing re-encoded
    assert given == [[]] and _sha(path) == sha and sk_tiles.is_zstd(path)
    assert np.array_equal(_read(path), band, equal_nan=True)
    assert update.migrate(cache_dir) == 0 and _sha(path) == sha


def test_every_layer_that_rewrites_says_so_and_the_slovak_mirror_does_not():
    folders = {layer.folder: layer.rewrites for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt) if layer}
    assert folders["poland/nmt"] and folders["switzerland/swissalti3d"] and folders["copernicus30/2021/dem"]
    assert folders["fabdem/v1-2"] and folders["bavaria/dgm1"] and folders["hesse/dgm1/live"]
    assert not folders["slovakia/dmr5/5.0/epsg8353-1m-2km"] and src.WATER_MASK.rewrites
    assert update.rewriting_layer("slovakia/dmr5/5.0/epsg8353-1m-2km/x/t.tif") is None
    assert update.rewriting_layer("poland/nmt/2020_N-34-1.tif").folder == "poland/nmt"
    assert update.rewriting_layer("osm/themes/coastline/x.geojson") is None
