"""tools/mirror_tiles.py: own copies of elevation models published as one big file (Madeira's BigTIFF, Valle
d'Aosta's comma-decimal ASCII grid in a Deflate64 ZIP), downloaded, unpacked and cut into 2 km tiles of the local
mirror on the data's own pixel grid; sources.GridTiles reads them back with the same origin."""

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import tracemalloc
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import mirror_tiles as mt  # noqa: E402
import sk_tiles  # noqa: E402
import grid as gd  # noqa: E402
import sources as src  # noqa: E402
from sources import net  # noqa: E402
from http_server import Answer, key_of  # noqa: E402

# Valle d'Aosta's header: x edges on even, y edges on odd metres, the corner with an ASCII writer's noise
ASC_LEFT, ASC_BOTTOM = 329116.000024, 5036774.999974
ASC_W, ASC_H = 1300, 700  # 2 m pixels: 2.6 x 1.4 km, so tiles of 2 km cut it on every side


def _heights(shape, seed):
    rng = np.random.default_rng(seed)
    return (500 + rng.random(shape) * 2000).round(3)  # millimetre values, as both datasets


def _asc_text(values: np.ndarray, left=ASC_LEFT, bottom=ASC_BOTTOM, nodata=-9999) -> bytes:
    """An ESRI ASCII grid as the region writes it: decimal commas, CRLF."""
    def number(v):
        return f"{v:.6f}".replace(".", ",")
    header = (f"ncols {values.shape[1]}\r\nnrows {values.shape[0]}\r\nxllcorner {number(left)}\r\n"
              f"yllcorner {number(bottom)}\r\ncellsize 2\r\nNODATA_value {nodata}\r\n")
    rows = ["  ".join("-9999" if v == nodata else f"{v:.3f}".replace(".", ",") for v in row) for row in values]
    return (header + "\r\n".join(rows) + "\r\n").encode("ascii")


def _asc_values():
    values = _heights((ASC_H, ASC_W), 1)
    values[:200, :300] = -9999          # a hole in the north-west
    values[650:, 1250:] = -9999         # and in the south-east corner
    return values


def _spec(monkeypatch, name, **kwargs):
    spec = {**mt.DATASETS["aosta" if name.startswith("asc") else "madeira"], **kwargs}
    monkeypatch.setitem(mt.DATASETS, name, spec)
    return spec


def _zip(work, member, data: bytes, url_name):
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(work / url_name, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, data)


def _mosaic_of_tiles(folder, index, origin, res=2.0):
    """The tiles of an index as one array with its (left, top), NaN for no data."""
    keys = [tuple(map(int, k.split("_"))) for k, v in index["tiles"].items() if v]
    i0, i1 = min(i for i, _ in keys), max(i for i, _ in keys)
    j0, j1 = min(j for _, j in keys), max(j for _, j in keys)
    px = round(2000 / res)
    out = np.full(((j1 - j0 + 1) * px, (i1 - i0 + 1) * px), np.nan, dtype=np.float32)
    for i, j in keys:
        with rio.open(folder / src.grid_tile_name(i, j)) as t:
            out[(j1 - j) * px:(j1 - j + 1) * px, (i - i0) * px:(i - i0 + 1) * px] = t.read(1)
    return out, origin[0] + i0 * 2000, origin[1] + (j1 + 1) * 2000


def _check_tiles(root, spec, values, left, top, nodata):
    """The tiles under root: every tile of the extent in the index with its sha256, on the dataset's grid, in the
    mirror's profile, the values within LERC's 5 mm and every no-data value NaN."""
    folder = root / spec["folder"] / spec["product"] / "2m"
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    assert "partial" not in index and index["origin"] == list(spec["origin"]) and index["crs"] == spec["crs"]
    ox, oy = spec["origin"]
    keys = [tuple(map(int, k.split("_"))) for k in index["tiles"]]
    cols = range(int(np.floor((left - ox) / 2000)), int(np.ceil((left + values.shape[1] * 2 - ox) / 2000)))
    rows = range(int(np.floor((top - values.shape[0] * 2 - oy) / 2000)), int(np.ceil((top - oy) / 2000)))
    assert sorted(keys) == sorted((i, j) for i in cols for j in rows)  # every tile of the extent
    for key, sha in index["tiles"].items():
        path = folder / src.grid_tile_name(*map(int, key.split("_")))
        assert (sha is None) == (not path.exists())
        if sha is None:
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        i, j = map(int, key.split("_"))
        with rio.open(path) as t:
            # the mirror's profile: Slovakia's (sk_tiles._write), on the dataset's own pixel grid
            assert t.transform == from_origin(ox + i * 2000, oy + (j + 1) * 2000, 2, 2) and t.shape == (1000, 1000)
            assert t.crs == rio.crs.CRS.from_user_input(spec["crs"]) and np.isnan(t.nodata)
            assert t.tags(ns="IMAGE_STRUCTURE")["COMPRESSION"] == "LERC_ZSTD" and t.dtypes[0] == "float32"
            assert t.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG" and t.block_shapes == [(512, 512)]
    mosaic, m_left, m_top = _mosaic_of_tiles(folder, index, spec["origin"])
    r0, c0 = round((m_top - top) / 2), round((left - m_left) / 2)
    assert r0 >= 0 and c0 >= 0
    part = mosaic[r0:r0 + values.shape[0], c0:c0 + values.shape[1]]
    expected = values.astype(np.float32).copy()
    for value in nodata:
        expected[expected == value] = np.nan
    assert np.array_equal(np.isnan(part), np.isnan(expected))
    assert np.nanmax(np.abs(part - expected)) <= 0.005 + 1e-4  # LERC's bound, float32 rounding at 2500 m
    outside = np.ones(mosaic.shape, bool)
    outside[r0:r0 + values.shape[0], c0:c0 + values.shape[1]] = False
    assert np.isnan(mosaic[outside]).all()  # beyond the raster: no data
    assert (root / spec["folder"] / "README.md").read_text(encoding="utf-8") == spec["card"]
    return index


def test_comma_decimal_ascii_grid_cut(tmp_path, monkeypatch):
    """Valle d'Aosta's kind: an ASCII grid with decimal commas and CRLF, x edges on even and y edges on odd metres
    (with 0.024 mm of noise in the header), cut on its own grid; a stopped cut leaves nothing in the mirror (its
    tiles wait in the staging folder) and resumes."""
    spec = _spec(monkeypatch, "asc", url="https://example.org/dl/test.zip", member="T.ASC")
    values = _asc_values()
    work, out = tmp_path / "work", tmp_path / "mirror"
    _zip(work, "T.ASC", _asc_text(values), "test.zip")
    assert mt.extract("asc", str(work)) == [str(work / "T.ASC")]
    assert mt.cut("asc", str(work), str(out), rows_limit=1) == {"dtm": "stopped"}
    assert not (out / "aosta").exists()
    assert mt.cut("asc", str(work), str(out)) == {"dtm": "cut"}
    left, top = 329116.0, 5036775.0 + ASC_H * 2
    index = _check_tiles(out, spec, values, left, top, (-9999,))
    # the origin (0, 1): rows of tiles from y = 2000 j + 1 (the bottom edge 5 036 775 in row 2518)
    assert {int(k.split("_")[1]) for k in index["tiles"]} == {2518, 2519}
    assert index["licence"] == "CC-BY-4.0" and index["attribution"].startswith("Dati estratti dal Modello")
    # Again: nothing to cut, the index as it was
    before = (out / "aosta" / "dtm" / "2m" / "index.json").read_bytes()
    mt.cut("asc", str(work), str(out))
    assert (out / "aosta" / "dtm" / "2m" / "index.json").read_bytes() == before


@pytest.mark.skipif(not (os.path.exists(mt.SEVEN_ZIP) or shutil.which(mt.SEVEN_ZIP)), reason="7-Zip not installed")
def test_deflate64_member_unpacked_by_seven_zip(tmp_path, monkeypatch):
    """Valle d'Aosta's ZIP packs its grid with Deflate64 (method 9), which zipfile cannot read: 7-Zip unpacks it,
    the same bytes; a damaged archive is an error, not a short file."""
    _spec(monkeypatch, "asc64", url="https://example.org/dl/t64.zip", member="T.ASC")
    work = tmp_path / "work"
    work.mkdir()
    data = _asc_text(_heights((50, 60), 2))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "T.ASC").write_bytes(data)
    subprocess.run([mt.SEVEN_ZIP, "a", "-tzip", "-mm=Deflate64", "-bd", str(work / "t64.zip"),
                    str(tmp_path / "src" / "T.ASC")], check=True, capture_output=True)
    with zipfile.ZipFile(work / "t64.zip") as z:
        info = z.getinfo("T.ASC")
        assert info.compress_type == 9
        with pytest.raises(NotImplementedError):
            z.read("T.ASC")
    assert (work / "T.ASC").exists() is False
    [path] = mt.extract("asc64", str(work))
    assert open(path, "rb").read() == data and not os.path.exists(path + ".part")
    # A flipped byte in the compressed data: 7-Zip's CRC check fails, nothing is put in place
    os.remove(path)
    raw = bytearray((work / "t64.zip").read_bytes())
    offset = info.header_offset + 30 + len(info.filename) + len(info.extra) + 20
    raw[offset] ^= 0xFF
    (work / "t64.zip").write_bytes(bytes(raw))
    with pytest.raises(RuntimeError, match="7-Zip"):
        mt.extract("asc64", str(work))
    assert not os.path.exists(path) and not os.path.exists(path + ".part")  # no partial file left behind


def test_failed_unpacking_leaves_no_part(tmp_path, monkeypatch):
    """A Deflate member that fails its CRC (zipfile) leaves neither the raster nor its .part behind."""
    _spec(monkeypatch, "asc", url="https://example.org/dl/bad.zip", member="T.ASC")
    work = tmp_path / "work"
    _zip(work, "T.ASC", _asc_text(_heights((40, 50), 6)), "bad.zip")
    with zipfile.ZipFile(work / "bad.zip") as z:
        info = z.getinfo("T.ASC")
    raw = bytearray((work / "bad.zip").read_bytes())
    raw[info.header_offset + 30 + len(info.filename) + len(info.extra) + 40] ^= 0xFF
    (work / "bad.zip").write_bytes(bytes(raw))
    with pytest.raises(Exception):
        mt.extract("asc", str(work))
    assert [n for n in os.listdir(work) if n not in ("state", "mirror_tiles.lock")] == ["bad.zip"]


def test_replace_tried_again(tmp_path, monkeypatch):
    """Replacing a file the share refuses for a moment (PermissionError) is tried again until REPLACE_SECONDS, then
    the error is raised."""
    real, calls = os.replace, []

    def flaky(a, b):
        calls.append(a)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real(a, b)
    monkeypatch.setattr(mt.os, "replace", flaky)
    monkeypatch.setattr(mt.time, "sleep", lambda s: None)
    (tmp_path / "a.part").write_text("new")
    (tmp_path / "a").write_text("old")
    mt._replace(str(tmp_path / "a.part"), str(tmp_path / "a"))
    assert len(calls) == 3 and (tmp_path / "a").read_text() == "new" and not (tmp_path / "a.part").exists()

    def refused(a, b):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(mt.os, "replace", refused)
    monkeypatch.setattr(mt, "REPLACE_SECONDS", 0)
    (tmp_path / "b.part").write_text("x")
    with pytest.raises(PermissionError):
        mt._replace(str(tmp_path / "b.part"), str(tmp_path / "b"))


def test_ascii_grid_errors(tmp_path):
    """A row of the wrong length, a value that is not a number and a corner off the dataset's grid are errors; a row
    over two lines is read whole."""
    good = _heights((3, 4), 3)
    text = _asc_text(good).decode()
    lines = text.split("\r\n")
    path = tmp_path / "g.asc"
    # A row over two lines (some writers wrap): the same values
    wrapped = lines[:6] + [" ".join(lines[6].split()[:2]), " ".join(lines[6].split()[2:])] + lines[7:]
    path.write_text("\r\n".join(wrapped), encoding="ascii", newline="")
    bands = mt.AscBands(str(path), ())
    assert np.allclose(bands.rows(0, 3), good, atol=1e-3)
    bands.close()
    for bad in (lines[:6] + [lines[6] + " 1,5"] + lines[7:],            # five values in a row of four
                lines[:7] + [lines[7].replace(lines[7].split()[1], "x")] + lines[8:]):
        path.write_text("\r\n".join(bad), encoding="ascii", newline="")
        bands = mt.AscBands(str(path), ())
        with pytest.raises(ValueError):
            bands.rows(0, 3)
        bands.close()
    # Rows only forwards
    path.write_text(text, encoding="ascii", newline="")
    bands = mt.AscBands(str(path), ())
    bands.rows(1, 2)
    with pytest.raises(ValueError, match="from the top"):
        bands.rows(0, 1)
    bands.close()
    with pytest.raises(ValueError, match="origin is wrong"):
        mt._on_grid(329117.0, 0.0, 2.0, "left edge")
    assert mt._on_grid(329116.000024, 0.0, 2.0, "left edge") == 329116.0


def _strip_bigtiff(path, values, left, top):
    """Madeira's kind: a BigTIFF of float32, one row per strip, DEFLATE with the horizontal predictor, nodata
    -32768 in its tag and -999 in its values."""
    with rio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                  dtype="float32", crs="EPSG:5016", transform=from_origin(left, top, 2, 2), nodata=-32768.0,
                  compress="deflate", predictor=2, blockysize=1, BIGTIFF="YES") as dst:
        dst.write(values.astype(np.float32), 1)
    with rio.open(path) as check:
        assert check.block_shapes == [(1, values.shape[1])]
        assert check.tags(ns="IMAGE_STRUCTURE").get("PREDICTOR") == "2"


def test_strip_bigtiff_with_two_nodata_values(tmp_path, monkeypatch):
    """Madeira's kind: pixel edges on odd metres (origin (1, 1)), both no-data values made NaN, tiles on the data's
    own grid."""
    spec = _spec(monkeypatch, "tif", url="https://example.org/dl/m.zip", member="M.tif")
    left, top = 287861.0, 3666229.0
    values = _heights((900, 1200), 4)
    values[:100, :] = -32768.0           # the tag's no data (the sea)
    values[400:500, 600:700] = -999.0    # the other one
    work, out = tmp_path / "work", tmp_path / "mirror"
    work.mkdir()
    _strip_bigtiff(work / "M.tif.src", values, left, top)
    _zip(work, "M.tif", (work / "M.tif.src").read_bytes(), "m.zip")
    mt.extract("tif", str(work))
    mt.cut("tif", str(work), str(out))
    _check_tiles(out, spec, values, left, top, (-32768.0, -999.0))
    # The origin must be the data's: (0, 0) would cut pixels in two
    monkeypatch.setitem(mt.DATASETS, "tif", {**spec, "origin": (0.0, 0.0)})
    with pytest.raises(ValueError, match="origin is wrong"):
        mt.cut("tif", str(work), str(tmp_path / "other"))


def test_grid_tiles_with_an_origin_read_the_mirror(tmp_path, monkeypatch):
    """GridTiles with the dataset's origin brings the mirror's tiles back onto a grid on the data's own pixels (a
    grid of grid_origin (1, 1)): the source's values within 5 mm, its no data NaN; without the origin the tiles
    named are the wrong ones."""
    import cache
    spec = _spec(monkeypatch, "tif", url="https://example.org/dl/m.zip", member="M.tif")
    left, top = 287861.0, 3666229.0
    values = _heights((900, 1200), 5)
    values[:, :150] = -999.0
    work, out = tmp_path / "work", tmp_path / "mirror"
    work.mkdir()
    _strip_bigtiff(work / "M.tif.src", values, left, top)
    _zip(work, "M.tif", (work / "M.tif.src").read_bytes(), "m.zip")
    mt.extract("tif", str(work))
    mt.cut("tif", str(work), str(out))
    monkeypatch.setattr(net, "_get", lambda *a, **k: pytest.fail("no network with a mirror"))
    monkeypatch.setenv(src.MIRROR_ENV, str(out))
    layer = src.GridTiles("Test DTM", [], "EPSG:5016", "test/madeira/epsg5016-2m-2km", 2000, 2.0, 1.5e6,
                          mirror="madeira/dtm/2m", origin=spec["origin"])
    grid = gd.make_grid((left + 200, top - 1700, left + 2200, top - 100), 2.0, "EPSG:5016", spec["origin"])
    assert grid.left % 2 == 1 and grid.top % 2 == 1
    cache_dir = str(tmp_path / "cache")
    layer.download(grid, cache_dir, None, "test")
    assert {cache.state(cache_dir, layer.tile_path(cache_dir, t)) for t in layer.tiles(grid)} == {"ok"}
    mosaic = src.build_mosaic(layer.files(grid, cache_dir), grid, str(tmp_path / "m.npy"), "test")
    r0, c0 = round((top - grid.top) / 2), round((grid.left - left) / 2)
    expected = values[r0:r0 + grid.height, c0:c0 + grid.width].astype(np.float32)
    expected[expected == -999.0] = np.nan
    assert np.array_equal(np.isnan(mosaic), np.isnan(expected)) and np.isnan(expected).any()
    assert np.nanmax(np.abs(mosaic - expected)) <= 0.0051
    # The tiling's edges come from the origin
    edges = layer.index.tilings[2.0].edges(layer.tiles(grid)[0][1:])
    assert edges[0] % 2000 == 1 and edges[1] % 2000 == 1
    plain = src.GridTiles("Test DTM", [], "EPSG:5016", "test/plain", 2000, 2.0, 1.5e6, mirror="madeira/dtm/2m")
    assert plain.index.tilings[2.0].edges(plain.tiles(grid)[0][1:])[0] % 2000 == 0

    # A grid off the data's pixels (1 m from origin (0, 0), as a neighbour's or another resolution's) whose left edge
    # is a multiple of 2 km: its first metre lies in the tile cut from 288 001 to 290 001, which only the origin
    # names; without it the tile is not listed and the first column has no data
    k = 145  # x = 290 000, inside the data (287 861 - 290 261)
    fine = gd.make_grid((k * 2000, top - 1700, k * 2000 + 200, top - 100), 1.0, "EPSG:5016")
    assert fine.left == k * 2000
    assert {t[1] for t in layer.tiles(fine)} == {k - 1, k}
    assert {t[1] for t in plain.tiles(fine)} == {k}  # what ignoring the origin would read
    layer.download(fine, cache_dir, None, "test")
    fine_mosaic = src.build_mosaic(layer.files(fine, cache_dir), fine, str(tmp_path / "f.npy"), "test")
    assert np.isfinite(fine_mosaic[:, 0]).all() and np.isfinite(fine_mosaic).all()
    plain_dir = str(tmp_path / "plain")
    plain.download(fine, plain_dir, None, "test")
    plain_mosaic = src.build_mosaic(plain.files(fine, plain_dir), fine, str(tmp_path / "p.npy"), "test")
    assert not np.isfinite(plain_mosaic[:, 0]).any()  # the test would fail if GridTiles ignored its origin


# Downloads

BODY = bytes(range(256)) * 1200  # 307 200 bytes


@pytest.fixture
def served(http_server, monkeypatch, tmp_path):
    """A dataset whose ZIP the local server holds; no waiting between attempts."""
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    monkeypatch.setattr(mt, "CHUNK", 4096)  # what a cut answer brought is kept
    spec = _spec(monkeypatch, "dl", url=http_server.url("/files/data.zip"), bytes=len(BODY), resume_below=None)
    http_server.add("/files/data.zip", BODY, "application/zip")
    return http_server, spec, tmp_path / "work"


def _ranges(server):
    return [r.headers.get("range") for r in server.requests("/files/")]


def test_download_whole_file(served):
    server, spec, work = served
    [path] = mt.download("dl", str(work))
    assert open(path, "rb").read() == BODY and not os.path.exists(path + ".part")
    assert _ranges(server) == [None]
    assert server.requests("/files/")[0].user_agent.startswith("Find-a-Line")
    assert mt.download("dl", str(work)) == [path] and len(server.requests("/files/")) == 1  # complete: no request


def test_download_resumes_after_a_cut(served):
    """A part from before resumes by a Range from its end; an answer cut short is resumed again from where it
    stopped. Never a Range of 0-0, never one from 0."""
    server, spec, work = served
    work.mkdir()
    (work / "data.zip.part").write_bytes(BODY[:100_000])
    server.fault("/files/data.zip", "truncate", lambda n, rng: n == 1)
    [path] = mt.download("dl", str(work))
    assert open(path, "rb").read() == BODY
    ranges = _ranges(server)
    assert ranges[0] == "bytes=100000-" and len(ranges) == 2
    assert int(ranges[1].split("=")[1].rstrip("-")) > 100_000  # half of the cut answer was kept
    assert all(r is None or not r.startswith("bytes=0-") for r in ranges)


def test_download_server_ignoring_the_range(served):
    """A server that answers 200 to a Range sends the whole file: written from the start, not appended."""
    server, spec, work = served
    server.answers[key_of("GET", "/files/data.zip")] = Answer(200, BODY, {"Content-Type": "application/zip"},
                                                               ranges=False)
    work.mkdir()
    (work / "data.zip.part").write_bytes(b"x" * 5000)
    [path] = mt.download("dl", str(work))
    assert open(path, "rb").read() == BODY and _ranges(server) == ["bytes=5000-"]


def test_download_without_a_range_beyond_resume_below(served, monkeypatch):
    """Valle d'Aosta's firewall refuses a Range beyond about 1e8 bytes: a part from before beyond resume_below
    starts again with a plain GET; below it the Range is sent."""
    server, spec, work = served
    monkeypatch.setitem(mt.DATASETS, "dl", {**spec, "resume_below": 50_000})
    work.mkdir()
    (work / "data.zip.part").write_bytes(BODY[:60_000])
    assert open(mt.download("dl", str(work))[0], "rb").read() == BODY
    assert _ranges(server) == [None]
    os.remove(work / "data.zip")
    (work / "data.zip.part").write_bytes(BODY[:40_000])
    assert open(mt.download("dl", str(work))[0], "rb").read() == BODY
    assert _ranges(server) == [None, "bytes=40000-"]


def test_download_of_another_size_stops(served, monkeypatch):
    """A file of another size than the dataset's (it has changed) is never read beyond the expected bytes: the
    download stops at once, its part removed; a server error is tried ATTEMPTS times."""
    server, spec, work = served
    monkeypatch.setitem(mt.DATASETS, "dl", {**spec, "bytes": len(BODY) - 10})
    with pytest.raises(mt.SizeChanged):
        mt.download("dl", str(work))
    assert not (work / "data.zip.part").exists() and len(server.requests("/files/")) == 1
    monkeypatch.setitem(mt.DATASETS, "dl", {**spec, "url": server.url("/files/broken.zip")})
    server.add("/files/broken.zip", b"blocked", "text/html", status=500)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        mt.download("dl", str(work))
    assert len(server.requests("/files/broken.zip")) == mt.ATTEMPTS


def test_datasets_match_the_catalogue():
    """Every product of the tool's datasets is read by one catalogue layer, and every layer of the catalogue made by
    the tool is a product: the same mirror folder, CRS, pixel size and origin (the tiles are read on the grid they
    were cut on). The search's own grid (the source's default resolution) is never finer than the data or than 1 m
    (a search never runs finer: 0.5 m data is searched at 1 m), a whole multiple of the data's pixel, its edges on
    the data's (grid_origin == origin), and the source works in the product's CRS."""
    layers = {layer.mirror: (s, layer) for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
              if isinstance(layer, src.GridTiles) and layer.index.tilings and getattr(layer, "readers", None)
              and layer.readers[layer.native_res].tool == "tools/mirror_tiles.py"}
    products = {}
    for name in mt.DATASETS:
        ds = mt.dataset(name)
        mt.check_names(ds)
        for product in ds.products:
            products[mt.tile_folder(ds, product)] = product
    assert set(products) == set(layers)
    assert {"madeira/dtm/2m", "aosta/dtm/2m", "porto-santo/dtm/5m", "selvagens/dtm/5m"} <= set(products)
    for folder, product in products.items():
        source, layer = layers[folder]
        assert layer.crs == product.crs == source.crs and layer.native_res == product.res, folder
        assert layer.origin == product.origin == source.grid_origin and layer.tile_m == mt.TILE_M, folder
        res = source.default_resolution
        assert res >= max(product.res, src.MIN_RESOLUTION) and math.isclose(round(res / product.res) * product.res,
                                                                            res), folder
    assert sk_tiles.TILE_M == 2000


# Datasets of many inputs (2026-11-15): products, placed files, folders, ZIPs of several rasters, mosaics, masks

def _tif(path, values, left, top, res=5.0, crs="EPSG:5016", nodata=None, dtype="float32", strips=False):
    """A GeoTIFF of values (north up) at (left, top)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = dict(blockysize=1) if strips else dict(tiled=True, blockxsize=256, blockysize=256)
    with rio.open(path, "w", driver="GTiff", width=values.shape[1], height=values.shape[0], count=1, dtype=dtype,
                  crs=crs, transform=from_origin(left, top, res, res), nodata=nodata, compress="deflate",
                  **extra) as dst:
        dst.write(values.astype(dtype), 1)
    return path


def _product(inputs, name="dtm", res=5.0, crs="EPSG:5016", origin=(2.5, 2.5), **kwargs):
    return mt.Product(name, res, crs, origin, tuple(inputs), f"Test {name}", "as published", **kwargs)


def _dataset(monkeypatch, name, *products, **kwargs):
    ds = mt.Dataset(name, f"Test {name}", "Test Provider", "No conditions apply", "Test Provider, 2026",
                    tuple(products), record="https://example.org/record", not_endorsed="TP", **kwargs)
    monkeypatch.setitem(mt.DATASETS, name, ds)
    return ds


def _tiles(out, ds, product=None):
    """{key: values or None} of a product's folder, and its index."""
    folder = out / mt.tile_folder(ds, product)
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    found = {}
    for key, sha in index["tiles"].items():
        if sha is None:
            found[key] = None
            continue
        with rio.open(folder / src.grid_tile_name(*map(int, key.split("_")))) as t:
            found[key] = t.read(1)
    return found, index


def _expected(rasters, origin=(2.5, 2.5), res=5.0):
    """The tiles a mosaic of [(values with NaN, left, top)] makes, the first raster winning: {key: values}."""
    px = round(2000 / res)
    out = {}
    for values, left, top in rasters:
        rows, cols = values.shape
        i0, i1 = int(np.floor((left - origin[0]) / 2000)), int(np.ceil((left + cols * res - origin[0]) / 2000))
        j0, j1 = int(np.floor((top - rows * res - origin[1]) / 2000)), int(np.ceil((top - origin[1]) / 2000))
        for j in range(j0, j1):
            for i in range(i0, i1):
                tile = out.setdefault(f"{i}_{j}", np.full((px, px), np.nan, np.float32))
                c0, r0 = round((origin[0] + i * 2000 - left) / res), round((top - origin[1] - (j + 1) * 2000) / res)
                rs, cs = slice(max(r0, 0), min(r0 + px, rows)), slice(max(c0, 0), min(c0 + px, cols))
                if rs.start >= rs.stop or cs.start >= cs.stop:
                    continue
                part = values[rs, cs].astype(np.float32)
                target = tile[rs.start - r0:rs.stop - r0, cs.start - c0:cs.stop - c0]
                fill = np.isnan(target) & np.isfinite(part)
                target[fill] = part[fill]
    return out


def _close(got, want):
    assert np.array_equal(np.isnan(got), np.isnan(want))
    assert np.nanmax(np.abs(got - want)) <= 0.0051 if np.isfinite(want).any() else True


def test_datasets_of_before_byte_for_byte(tmp_path, monkeypatch):
    """Madeira's and Valle d'Aosta's kind (a dict of before: one URL, one member) cut by the tool of many inputs:
    every tile is sk_tiles._write of the expected pixels byte for byte, the index has exactly the keys of before in
    their order, the card is the published text; cutting again, verifying and writing the card change none of the
    index's, the tiles' or the card's bytes; one thread or six give the same bytes."""
    left, top = 287861.0, 3666229.0
    values = _heights((900, 1200), 4)
    values[:100, :] = -32768.0
    values[400:500, 600:700] = -999.0
    digests = []
    for threads in (1, 6):
        spec = _spec(monkeypatch, "tif", url="https://example.org/dl/m.zip", member="M.tif")
        work, out = tmp_path / f"w{threads}", tmp_path / f"m{threads}"
        work.mkdir()
        _strip_bigtiff(work / "M.tif.src", values, left, top)
        _zip(work, "M.tif", (work / "M.tif.src").read_bytes(), "m.zip")
        mt.extract("tif", str(work))
        mt.cut("tif", str(work), str(out), threads=threads)
        folder = out / "madeira" / "dtm" / "2m"
        index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
        assert list(index) == ["tiles", "dataset", "product", "title", "source", "crs", "heights", "tile_m",
                               "resolution", "origin", "block", "encoding", "licence", "attribution", "created"]
        assert index["dataset"] == "tif" and index["source"] == "https://example.org/dl/m.zip"
        masked = values.astype(np.float32)
        masked[(masked == -32768) | (masked == -999)] = np.nan
        expected = _expected([(masked, left, top)], origin=(1.0, 1.0), res=2.0)
        assert list(index["tiles"]) == sorted(expected, key=lambda k: (-int(k.split("_")[1]), int(k.split("_")[0])))
        for key, want in expected.items():
            i, j = map(int, key.split("_"))
            ref = tmp_path / f"ref-{threads}-{key}.tif"
            sk_tiles._write(str(ref), want, "EPSG:5016", from_origin(1 + 2000 * i, 1 + 2000 * (j + 1), 2, 2))
            assert (folder / src.grid_tile_name(i, j)).read_bytes() == ref.read_bytes(), key
        snapshot = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
        assert (out / "madeira" / "README.md").read_text(encoding="utf-8") == mt.MADEIRA_CARD
        mt.cut("tif", str(work), str(out), threads=threads)
        assert mt.verify("tif", str(work), str(out))["dtm"]["ok"]
        mt.write_card(mt.dataset("tif"), str(out))
        assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file() and p.name != "verify.json"} == snapshot
        digests.append(sorted(hashlib.sha256(b).hexdigest() for b in snapshot.values()))
    assert digests[0] == digests[1]


def test_products_share_one_card(tmp_path, monkeypatch):
    """A terrain and a surface product under one dataset: two folders, one card naming both with the changes of
    each, written whole by either cut (before 2026-11-15 the second product's card replaced the first's); a fixed
    card of before covers one product only; names outside [a-z0-9_-] are refused."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _tif(inputs / "t.tif", _heights((300, 300), 1), 402.5, 1902.5)
    _tif(inputs / "s.tif", _heights((300, 300), 2) + 10, 402.5, 1902.5)
    ds = _dataset(monkeypatch, "isle", _product([mt.Placed("t.tif")], "dtm"),
                  _product([mt.Placed("s.tif")], "dsm", sea=0.0))
    mt.cut("isle", str(work), str(out), inputs=str(inputs), product="dtm")
    card = (out / "isle" / "README.md").read_text(encoding="utf-8")
    assert "## `dtm/5m`" in card and "## `dsm/5m`" in card and "the sea's value 0 made no data" in card
    assert "Licence: No conditions apply" in card and "not endorsed by TP" in card
    mt.cut("isle", str(work), str(out), inputs=str(inputs), product="dsm")
    assert (out / "isle" / "README.md").read_text(encoding="utf-8") == card
    assert all((out / "isle" / name / "5m" / "index.json").exists() for name in ("dtm", "dsm"))
    with pytest.raises(ValueError, match="fixed card"):
        mt.card_text(mt.replace(ds, card="# old"))
    _dataset(monkeypatch, "Bad Name", _product([mt.Placed("t.tif")]))
    with pytest.raises(ValueError, match="must match"):
        mt.cut("Bad Name", str(work), str(out), inputs=str(inputs))
    assert mt.tile_folder(ds, ds.products[1]) == "isle/dsm/5m"
    assert mt.tile_folder(mt.replace(ds, products=(mt.replace(ds.products[0], res=0.5),))) == "isle/dtm/0.5m"


def test_zip_of_several_rasters_seams_and_placed_files(tmp_path, monkeypatch):
    """A placed ZIP (any name; a .crdownload beside it is not an input) of two rasters chosen by a pattern, each with
    its own no-data pattern, side by side: unpacked into a folder of the ZIP's name, a tile across their seam holds
    both, each one's no data NaN; two files matching a placed input are an error."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    a, b = _heights((400, 300), 3), _heights((400, 300), 4)
    a[:50, :] = -9999.0          # its tag's no data
    b[100:120, :] = -999.0       # a declared value
    b[200:210, :] = -32768.0     # its tag's
    src_dir = tmp_path / "src"
    _tif(src_dir / "west.tif", a, 1002.5, 3002.5, nodata=-9999.0)
    _tif(src_dir / "east.tif", b, 1002.5 + 1500, 3002.5, nodata=-32768.0)
    (inputs / "prov").mkdir(parents=True)
    with zipfile.ZipFile(inputs / "prov" / "Namur MNT 2022.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src_dir / "west.tif", "rasters/west.tif")
        z.write(src_dir / "east.tif", "rasters/east.tif")
        z.writestr("rasters/readme.txt", "not a raster")
    (inputs / "prov" / "Liege MNT 2022.zip.crdownload").write_bytes(b"half")
    _dataset(monkeypatch, "prov", _product([mt.Placed("prov/*.zip*", members=("*.tif",))], nodata=(-999.0,)))
    paths = mt.extract("prov", str(work), str(inputs))
    assert sorted(os.path.relpath(p, work).replace(os.sep, "/") for p in paths) == [
        "Namur MNT 2022/rasters/east.tif", "Namur MNT 2022/rasters/west.tif"]
    mt.cut("prov", str(work), str(out), inputs=str(inputs))
    tiles, index = _tiles(out, mt.dataset("prov"))
    am, bm = a.astype(np.float32), b.astype(np.float32)
    am[am == -9999] = np.nan
    bm[(bm == -999) | (bm == -32768)] = np.nan
    # the members in name order: east before west (no overlap, so the order does not matter here)
    want = _expected([(bm, 2502.5, 3002.5), (am, 1002.5, 3002.5)])
    assert set(tiles) == set(want) and "partial" not in index and index["inputs"] == 2
    for key in want:
        _close(tiles[key], want[key])
    seam = tiles["1_0"]  # x from 2002.5 to 4002.5, y down to 2.5: west's last 100 columns and east's 300, rows 0-200
    assert np.isfinite(seam[150:200, 50:100]).all() and np.isfinite(seam[150:200, 100:150]).all()
    assert np.isnan(seam[200:]).all()
    (inputs / "prov" / "Liege MNT 2022.zip").write_bytes(b"PK")
    with pytest.raises(ValueError, match="2 files match"):
        mt.resolve(mt.dataset("prov").products[0], str(work), str(inputs))


def test_overlap_rules_and_disjoint_rasters(tmp_path, monkeypatch):
    """Where two inputs overlap: "first" takes the first listed; "agree" accepts differences within 5 mm and stops
    with the tile's name beyond; tiles between disjoint rasters inside the extent are null."""
    inputs, work = tmp_path / "in", tmp_path / "work"
    field_ = _heights((200, 300), 5)
    base = field_[:, :200]
    _tif(inputs / "a.tif", base, 2.5, 1002.5)
    _tif(inputs / "b.tif", field_[:, 100:] + 0.004, 502.5, 1002.5)  # overlaps a by 100 columns, 4 mm higher
    _tif(inputs / "c.tif", field_[:, 100:] + 0.2, 502.5, 1002.5)    # 20 cm higher
    _tif(inputs / "far.tif", base, 6002.5, 1002.5)             # 6 km east: tiles 1 and 2 between are empty
    for rule, second, ok in (("first", "c.tif", True), ("agree", "b.tif", True), ("agree", "c.tif", False)):
        out = tmp_path / f"m-{rule}-{second}"
        _dataset(monkeypatch, "ov", _product([mt.Placed("a.tif"), mt.Placed(second), mt.Placed("far.tif")],
                                             overlap=rule))
        if not ok:
            with pytest.raises(mt.Overlap, match="tile 0_0: c.tif differs by 0.200"):
                mt.cut("ov", str(work / rule), str(out), inputs=str(inputs))
            continue
        mt.cut("ov", str(work / f"{rule}{second}"), str(out), inputs=str(inputs))
        tiles, index = _tiles(out, mt.dataset("ov"))
        assert tiles["1_0"] is None and tiles["2_0"] is None and tiles["3_0"] is not None
        assert "partial" not in index
        _close(tiles["0_0"][200:, :200], base.astype(np.float32))  # a wins where both are


def test_memory_bound(tmp_path, monkeypatch):
    """A raster of full-width strips too wide for the bound (60 000 px: one row of tiles across it is 96 MB) is
    copied into a tiled GeoTIFF in row chunks, then cut tile by tile: numpy's peak stays far below one row of tiles,
    the tiles are right; a bound below one tile is refused."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    rows, cols = 400, 60_000
    values = (np.add.outer(np.arange(rows), np.arange(cols) % 977) * 0.25).astype(np.float32)
    _tif(inputs / "wide.tif", values, 2.5, 2002.5, strips=True)
    _dataset(monkeypatch, "wide", _product([mt.Placed("wide.tif")]))
    band = rows * cols * 4
    bound = 0.4  # GB: GDAL's cache 64 MB, about 36 MB for the rest
    assert mt._budget(bound)[0] < band
    tracemalloc.start()
    try:
        mt.cut("wide", str(work), str(out), inputs=str(inputs), threads=6, max_memory_gb=bound)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < band / 2, peak
    assert list((work / "tiled").glob("wide-*.tif"))  # the tiled copy
    tiles, index = _tiles(out, mt.dataset("wide"))
    assert len(tiles) == 150 and "partial" not in index
    want = _expected([(values, 2.5, 2002.5)])
    for key in ("0_0", "77_0", "149_0"):
        _close(tiles[key], want[key])
    with pytest.raises(ValueError, match="too little for one tile"):
        mt._workers(_product([], res=0.5), 6, 0.5)
    assert mt._workers(_product([], res=0.5), 6, 8.0)[0] == 6  # the default bound: six tiles of 0.5 m at a time


def test_masks_and_the_datasets_crs(tmp_path, monkeypatch):
    """Masks per product: the file's nodata, declared values, the sea's value and a floor; the CRS is the
    product's, the file's other label recorded in the index."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    values = _heights((300, 300), 8)
    values[:20] = 0.0          # the sea
    values[20:25] = -0.5       # a real height below 0: kept
    values[25:30] = -50.0      # coast pixels averaged with -999
    values[30:35] = -999.0
    values[35:40] = -32768.0   # the file's own
    _tif(inputs / "d.tif", values, 2.5, 1502.5, crs="EPSG:3061", nodata=-32768.0)
    ds = _dataset(monkeypatch, "isl", _product([mt.Placed("d.tif")], nodata=(-999.0,), sea=0.0, floor=-1.0))
    mt.cut("isl", str(work), str(out), inputs=str(inputs))
    tiles, index = _tiles(out, ds)
    tile = tiles["0_0"]
    r0 = 100  # the tile's top is 2002.5, the raster's 1502.5
    assert np.isnan(tile[r0:r0 + 20]).all() and np.allclose(tile[r0 + 20:r0 + 25, :300], -0.5, atol=0.006)
    assert np.isnan(tile[r0 + 25:r0 + 40]).all() and np.isfinite(tile[r0 + 40:r0 + 300, :300]).all()
    with rio.open(out / "isl" / "dtm" / "5m" / "0_0" / "0_0.tif") as t:
        assert t.crs == rio.crs.CRS.from_epsg(5016)
    assert index["crs"] == "EPSG:5016" and index["input_crs"] == {"EPSG:3061": ["d.tif"]}
    assert index["masks"] == {"nodata": [-999.0, "the files' own"], "sea": 0.0, "below": -1.0}


def test_verify(tmp_path, monkeypatch):
    """verify: a good cut passes (verify.json beside the index); a tile rewritten with other heights, a tile whose
    bytes no longer match its sha256 and a file the index does not list are each found."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _tif(inputs / "v.tif", _heights((800, 800), 9), 2.5, 4002.5)
    ds = _dataset(monkeypatch, "ver", _product([mt.Placed("v.tif")]))
    mt.cut("ver", str(work), str(out), inputs=str(inputs))
    result = mt.verify("ver", str(work), str(out), inputs=str(inputs), samples=4)["dtm"]
    assert result["ok"] and len([s for s in result["samples"] if s["data"]]) == 4
    folder = out / "ver" / "dtm" / "5m"
    assert json.loads((folder / "verify.json").read_text())["ok"] is True
    assert any("final" in line and "verified 20" in line
               for line in mt.status(["ver"], str(work), str(out), str(inputs)))
    index = json.loads((folder / "index.json").read_text())
    # Another tile's heights 1 m higher, its sha256 updated: only the comparison with the inputs finds it
    with rio.open(folder / "0_0" / "0_1.tif") as t:
        raised, transform = t.read(1) + 1.0, t.transform
    sk_tiles._write(str(folder / "0_0" / "0_1.tif"), raised, "EPSG:5016", transform)
    index["tiles"]["0_1"] = hashlib.sha256((folder / "0_0" / "0_1.tif").read_bytes()).hexdigest()
    (folder / "index.json").write_text(json.dumps(index))
    data = bytearray((folder / "0_0" / "1_0.tif").read_bytes())
    data[-1] ^= 0xFF
    (folder / "0_0" / "1_0.tif").write_bytes(bytes(data))
    (folder / "0_0" / "9_9.tif").write_bytes(b"stray")
    result = mt.verify("ver", str(work), str(out), inputs=str(inputs), samples=4)["dtm"]
    problems = "\n".join(result["problems"])
    assert not result["ok"] and "0_1: differs from the inputs by 1.0" in problems
    assert "1_0: the file does not match its sha256" in problems and "0_0/9_9.tif" in problems
    assert any("verify FAILED" in line for line in mt.status(["ver"], str(work), str(out), str(inputs)))


def test_ascii_dataset_of_before_byte_for_byte(tmp_path, monkeypatch):
    """Valle d'Aosta's kind (an ASCII grid, now copied into a tiled GeoTIFF before the cut): every tile is
    sk_tiles._write of the expected pixels byte for byte, the index keys of before, the published card; cutting again
    and verifying change nothing."""
    spec = _spec(monkeypatch, "asc", url="https://example.org/dl/test.zip", member="T.ASC")
    values = _asc_values()
    work, out = tmp_path / "work", tmp_path / "mirror"
    _zip(work, "T.ASC", _asc_text(values), "test.zip")
    mt.extract("asc", str(work))
    mt.cut("asc", str(work), str(out))
    folder = out / "aosta" / "dtm" / "2m"
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    assert list(index) == ["tiles", "dataset", "product", "title", "source", "crs", "heights", "tile_m",
                           "resolution", "origin", "block", "encoding", "licence", "attribution", "created"]
    masked = values.astype(np.float32)
    masked[masked == -9999] = np.nan
    expected = _expected([(masked, 329116.0, 5036775.0 + ASC_H * 2)], origin=(0.0, 1.0), res=2.0)
    assert set(index["tiles"]) == set(expected)
    for key, want in expected.items():
        i, j = map(int, key.split("_"))
        ref = tmp_path / f"ref-{key}.tif"
        sk_tiles._write(str(ref), want, spec["crs"], from_origin(2000 * i, 1 + 2000 * (j + 1), 2, 2))
        assert (folder / src.grid_tile_name(i, j)).read_bytes() == ref.read_bytes(), key
    assert (out / "aosta" / "README.md").read_text(encoding="utf-8") == mt.AOSTA_CARD
    snapshot = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    mt.cut("asc", str(work), str(out))
    assert mt.verify("asc", str(work), str(out))["dtm"]["ok"]
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file() and p.name != "verify.json"} == snapshot


_HOLD = """
import sys, time, os
sys.path.insert(0, sys.argv[1])
import mirror_tiles as mt
with mt._locked(sys.argv[2], "a test's"):
    print("held", flush=True)
    while not os.path.exists(sys.argv[3]):
        time.sleep(0.05)
"""


def _holder(tmp_path, lock_path, release):
    """Another process holding the tool's lock at lock_path until release exists."""
    script = tmp_path / "hold.py"
    script.write_text(_HOLD)
    proc = subprocess.Popen([sys.executable, str(script), os.path.dirname(mt.__file__), lock_path, release],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def test_one_run_at_a_time(tmp_path, monkeypatch):
    """Another process holding the work folder (or the product's mirror folder): cut, verify, clean and extract stop
    at once with Busy, touching nothing; the command line exits non-zero with the message."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _tif(inputs / "r.tif", _heights((100, 100), 1), 2.5, 1002.5)
    _dataset(monkeypatch, "busy", _product([mt.Placed("r.tif")]))
    release = tmp_path / "release"
    proc = _holder(tmp_path, str(work / "mirror_tiles.lock"), str(release))
    try:
        for call in (lambda: mt.cut("busy", str(work), str(out), inputs=str(inputs)),
                     lambda: mt.verify("busy", str(work), str(out), inputs=str(inputs)),
                     lambda: mt.clean("busy", str(work), str(inputs)),
                     lambda: mt.extract("busy", str(work), str(inputs))):
            with pytest.raises(mt.Busy, match="in use by another run"):
                call()
        assert not out.exists()
        monkeypatch.setattr(sys, "argv", ["mirror_tiles.py", "cut", "busy", "--work", str(work), "--inputs",
                                          str(inputs), "--out", str(out)])
        with pytest.raises(SystemExit) as stopped:
            mt.main()
        assert "Busy" in str(stopped.value.code)
    finally:
        release.write_text("")
        proc.wait(30)
    release.unlink()
    proc = _holder(tmp_path, str(out / ".locks" / "busy.dtm.5m.lock"), str(release))
    try:
        with pytest.raises(mt.Busy, match="busy/dtm/5m"):
            mt.cut("busy", str(tmp_path / "other-work"), str(out), inputs=str(inputs))
    finally:
        release.write_text("")
        proc.wait(30)
    mt.cut("busy", str(work), str(out), inputs=str(inputs))  # free again
    assert (out / "busy" / "dtm" / "5m" / "index.json").exists()


def _buggy(kind):
    """An assemble with a bug, used by both the cut and verify's own re-assembly (so only the independent check can
    see it)."""
    real = mt.assemble

    def assemble(key, product, footprints, handles):
        if kind == "origin":
            return real(key, mt.replace(product, origin=(product.origin[0] + product.res, product.origin[1])),
                        footprints, handles)
        tile = real(key, product, footprints, handles)
        return tile[::-1].copy() if kind == "rows" else np.roll(tile, 3, axis=1)
    return assemble


@pytest.mark.parametrize("kind", ["origin", "rows", "shift"])
def test_verify_reads_the_inputs_apart_from_the_cut(tmp_path, monkeypatch, kind):
    """verify's second comparison reads pixels straight from the input rasters through their own transforms, with
    the masks applied apart: a wrong origin, a swapped row order or a shifted tile, made in assemble and so equal in
    the cut and in verify's own re-assembly, is found."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    values = _heights((400, 400), 4)
    values[50:60] = -999.0
    _tif(inputs / "r.tif", values, 2.5, 2002.5)
    _dataset(monkeypatch, "pts", _product([mt.Placed("r.tif")], nodata=(-999.0,)))
    mt.cut("pts", str(work), str(out), inputs=str(inputs))
    good = mt.verify("pts", str(work), str(out), inputs=str(inputs))["dtm"]
    assert good["ok"] and good["points_compared"] == mt.POINTS and good["seed"] == 0
    monkeypatch.setattr(mt, "assemble", _buggy(kind))
    bad = tmp_path / "bad"
    mt.cut("pts", str(tmp_path / "w2"), str(bad), inputs=str(inputs))
    result = mt.verify("pts", str(tmp_path / "w2"), str(bad), inputs=str(inputs))["dtm"]
    assert not result["ok"] and any("read straight from the inputs" in x for x in result["problems"])
    assert not any("differs from the inputs by" in x or "no data differs" in x for x in result["problems"])


def test_verify_sample_size():
    """1 % of the tiles with data, at least 8, at most 500 (a defect in 1 % of 50 000 tiles found 99.3 % of the
    time instead of 7.7 % with 8)."""
    assert [mt.default_samples(n) for n in (0, 799, 5_000, 50_000, 10 ** 6)] == [8, 8, 50, 500, 500]


def test_card_follows_the_overlap_rule_and_the_floor(monkeypatch):
    """The card says the overlap rule the product has, and the islands' masks: the Desertas' and the Selvagens'
    floor of -1 m (the user's decision of 2026-11-15), none for Porto Santo."""
    agree = mt.Dataset("o", "O", "P", "L", "A", (_product([mt.Placed("a.tif"), mt.Placed("b.tif")], overlap="agree"),))
    first = mt.replace(agree, products=(mt.replace(agree.products[0], overlap="first"),))
    assert "where they overlap they agree within 5 mm" in mt.card_text(agree)
    assert "first listed wins" not in mt.card_text(agree) and "first listed wins" in mt.card_text(first)
    for name in ("desertas", "selvagens"):
        assert mt.dataset(name).products[0].floor == -1.0
        assert "every value below -1 m made no data" in mt.card_text(mt.dataset(name))
    assert mt.dataset("porto-santo").products[0].floor is None


# Round 3 (2026-11-16): a product is cut once, when it is complete, in a staging folder, and is final after that

def _fetch_area(inputs, cells, area="portugal", collection="MDT", done=None, seed=20):
    """A folder as tools/cdd_fetch.py leaves it: for every cell (x, y) a 1 km file (200 px of 5 m from (2.5, 2.5)) in
    manifest.jsonl; the cells of `done` (default: all) fetched, recorded in done.jsonl (id, group, path, size,
    sha256) and on disk. Rows are appended, so two collections may share an area. Their values by cell."""
    root = inputs / area
    root.mkdir(parents=True, exist_ok=True)
    values = {}
    with open(root / "manifest.jsonl", "a", encoding="utf-8") as m, open(root / "done.jsonl", "a",
                                                                         encoding="utf-8") as d:
        for x, y in cells:
            rid, folder = f"{collection}-{x:02d}{y:02d}", f"{y:03d}"
            rel = f"{collection}/{folder}/{rid}.tif"
            values[(x, y)] = _heights((200, 200), seed + x + 100 * y)
            m.write(json.dumps({"collection": collection, "id": rid, "folder": folder, "size": None}) + "\n")
            if done is None or (x, y) in done:
                path = _tif(root / rel, values[(x, y)], 2.5 + 1000 * x, 1002.5 + 1000 * y)
                d.write(json.dumps({"id": rid, "group": collection, "path": rel, "size": path.stat().st_size,
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}) + "\n")
    return values


def _snapshot(root):
    """Every file below root: its relative path, size, modification time and sha256."""
    found = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            found[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns,
                                                     hashlib.sha256(p.read_bytes()).hexdigest())
    return found


def _contents(root):
    """Every file below root by its bytes, index.json's "created" date left out, verify.json (its time) only as
    there and passing."""
    found = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name == "verify.json":
            found[p.relative_to(root).as_posix()] = json.loads(p.read_bytes())["ok"]
        elif p.is_file() and p.name == "inputs.jsonl":  # a placed file's stamp is its own copy's time
            rows = [json.loads(line) for line in p.read_text().splitlines()]
            found[p.relative_to(root).as_posix()] = [
                (r["id"], r["stamp"] if r["stamp"].startswith(("sha256:", "crc:")) else r["stamp"].split(":")[0])
                for r in rows]
        elif p.is_file():
            data = p.read_bytes()
            if p.name == "index.json":
                index = json.loads(data)
                index.pop("created", None)
                data = json.dumps(index).encode()
            found[p.relative_to(root).as_posix()] = data
    return found


def _main(monkeypatch, *argv):
    """The command line: its exit code (0 when it returns)."""
    monkeypatch.setattr(sys, "argv", ["mirror_tiles.py", *argv])
    try:
        mt.main()
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    return 0


def _stops_dataset(inputs):
    """A product of several inputs and several tiles reaching every write site: a fetched area of 4 x 2 files, a
    placed ZIP whose member is unpacked, a placed ASCII grid that is copied."""
    products = (mt.Product("dtm", 5.0, "EPSG:5016", (2.5, 2.5),
                           (mt.Fetched("portugal", collection="MDT"), mt.Placed("z/m.zip", members=("m.tif",)),
                            mt.Placed("asc/g.asc")), "Test dtm", "as published"),)
    return mt.Dataset("stops", "Test stops", "Test Provider", "No conditions apply", "Test Provider, 2026",
                      products, record="https://example.org/record", not_endorsed="TP")


def _stops_inputs(inputs):
    _fetch_area(inputs, [(x, y) for x in range(4) for y in range(2)])
    src_dir = inputs.parent / "src"
    _tif(src_dir / "m.tif", _heights((200, 300), 7), 6002.5, 1002.5)
    (inputs / "z").mkdir(parents=True)
    with zipfile.ZipFile(inputs / "z" / "m.zip", "w") as z:
        z.write(src_dir / "m.tif", "m.tif")
    (inputs / "asc").mkdir()
    (inputs / "asc" / "g.asc").write_bytes(_asc_text(_heights((40, 40), 8), left=2002.5, bottom=2502.5)
                                           .replace(b"cellsize 2", b"cellsize 5"))


class _Stop(Exception):
    pass


def _visits(tmp_path, monkeypatch):
    """The write sites an uninterrupted cut passes, with their counts, and the reference folder it makes."""
    inputs = tmp_path / "ref-in"
    _stops_inputs(inputs)
    monkeypatch.setitem(mt.DATASETS, "stops", _stops_dataset(inputs))
    seen = {}
    lock = __import__("threading").Lock()

    def count(name):
        with lock:
            seen[name] = seen.get(name, 0) + 1
    monkeypatch.setattr(mt, "HOOK", count)
    assert mt.cut("stops", str(tmp_path / "ref-work"), str(tmp_path / "ref-out"), inputs=str(inputs)) == \
        {"dtm": "cut"}
    assert mt.verify("stops", str(tmp_path / "ref-work"), str(tmp_path / "ref-out"), inputs=str(inputs))["dtm"]["ok"]
    monkeypatch.setattr(mt, "HOOK", None)
    return seen, tmp_path / "ref-out"


def _cut_and_verify(work, out, inputs):
    """A cut, then its verify (both write into the mirror)."""
    state = mt.cut("stops", str(work), str(out), inputs=str(inputs))["dtm"]
    return state, mt.verify("stops", str(work), str(out), inputs=str(inputs))["dtm"]


def test_write_sites_are_the_codes(tmp_path, monkeypatch):
    """Every name in WRITE_SITES is passed by a cut of the test product and appears in the code, and every _site call
    in the code is named there: a new write site without its stop test fails here."""
    import re
    seen, _ = _visits(tmp_path, monkeypatch)
    assert set(seen) == set(mt.WRITE_SITES)
    code = open(mt.__file__, encoding="utf-8").read()
    assert set(re.findall(r'_site\("([a-z_.]+)"\)', code)) == set(mt.WRITE_SITES)


def _reader_sees(out, folder_rel, monkeypatch):
    """What a GridTiles reader over out finds: None (no such dataset) or the set of tiles, each one whole."""
    layer = src.GridTiles("Test", [], "EPSG:5016", "test/stops", 2000, 5.0, 1e5, mirror=folder_rel,
                          origin=(2.5, 2.5))
    monkeypatch.setenv(src.MIRROR_ENV, str(out))
    if layer.unavailable():
        return None
    base = layer.bases()[0]
    index = json.loads(open(os.path.join(base, "index.json"), encoding="utf-8").read())
    assert "partial" not in index
    for key, sha in index["tiles"].items():
        if sha:
            path = os.path.join(base, src.grid_tile_name(*map(int, key.split("_"))))
            assert hashlib.sha256(open(path, "rb").read()).hexdigest() == sha
    return set(index["tiles"])


_CHILD = """
import os, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])
import mirror_tiles as mt
import test_mirror_tiles as T
from pathlib import Path
inputs, work, out, site, nth = Path(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6], int(sys.argv[7])
mt.DATASETS["stops"] = T._stops_dataset(inputs)
seen = [0]
def hook(name):
    if name == site:
        seen[0] += 1
        if seen[0] == nth:
            os._exit(17)
mt.HOOK = hook
mt.cut("stops", work, out, inputs=str(inputs))
mt.verify("stops", work, out, inputs=str(inputs))
sys.exit(3)
"""


@pytest.mark.parametrize("mode", ["raise", "exit"])
@pytest.mark.parametrize("site", mt.WRITE_SITES)
def test_a_stop_at_every_write_site(tmp_path, monkeypatch, site, mode):
    """Acceptance A and B: a stop at each write site (an exception, and a process ended by os._exit) at its second
    passing where it has one, else its first. At the stop the product's mirror folder is absent or whole (a reader
    finds no dataset or every tile); a run to completion then makes the folder and the card byte for byte as an
    uninterrupted run (index.json's date aside)."""
    seen, ref = _visits(tmp_path, monkeypatch)
    nth = 2 if seen[site] >= 2 else 1
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _stops_inputs(inputs)
    monkeypatch.setitem(mt.DATASETS, "stops", _stops_dataset(inputs))
    if mode == "raise":
        passed = [0]

        def hook(name):
            if name == site:
                passed[0] += 1
                if passed[0] == nth:
                    raise _Stop(site)
        monkeypatch.setattr(mt, "HOOK", hook)
        with pytest.raises(_Stop):
            _cut_and_verify(work, out, inputs)
        monkeypatch.setattr(mt, "HOOK", None)
    else:
        script = tmp_path / "child.py"
        script.write_text(_CHILD)
        done = subprocess.run([sys.executable, str(script), os.path.dirname(mt.__file__), os.path.dirname(__file__),
                               str(inputs), str(work), str(out), site, str(nth)], capture_output=True, text=True)
        assert done.returncode == 17, done.stderr[-2000:]
    seen_now = _reader_sees(out, "stops/dtm/5m", monkeypatch)
    if seen_now is not None:  # the rename happened: the whole product
        got = _contents(out / "stops" / "dtm" / "5m")
        got.pop("verify.json.part", None)  # a verify stopped while writing its result: the next one removes it
        want = _contents(ref / "stops" / "dtm" / "5m")
        assert {k: v for k, v in got.items() if k != "verify.json"} == {k: v for k, v in want.items()
                                                                        if k != "verify.json"}
    assert not (out / "stops" / "dtm" / "5m").exists() or seen_now is not None
    state, result = _cut_and_verify(work, out, inputs)
    assert state in ("cut", "final") and result["ok"] is True
    assert _contents(out / "stops") == _contents(ref / "stops")
    assert not (out / "stops" / "dtm" / "5m" / "verify.json.part").exists()
    assert not (out / ".staging").exists() or not list((out / ".staging").rglob("*.tif"))


def test_final_is_final(tmp_path, monkeypatch):
    """Acceptance C: after the rename, an input deleted, replaced by other values, touched, a new input added,
    done.jsonl removed, the work folder deleted: cut and all write nothing in the product's folder or the card (the
    listing, sizes, times and sha256 the same) and exit 0."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _fetch_area(inputs, [(x, y) for x in range(4) for y in range(2)])
    _dataset(monkeypatch, "fin", _product([mt.Fetched("portugal", collection="MDT")]))
    assert _main(monkeypatch, "all", "fin", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    assert mt.verified(mt.dataset("fin"), mt.dataset("fin").products[0], str(out))
    before = _snapshot(out)
    area = inputs / "portugal"
    first = area / "MDT" / "000" / "MDT-0000.tif"
    steps = [lambda: os.remove(area / "MDT" / "001" / "MDT-0101.tif"),
             lambda: _tif(first, _heights((200, 200), 99), 2.5, 1002.5),
             lambda: os.utime(area / "MDT" / "000" / "MDT-0100.tif", ns=(10 ** 9, 10 ** 9)),
             lambda: _fetch_area(inputs, [(5, 0)], seed=50),
             lambda: os.remove(area / "done.jsonl"),
             lambda: shutil.rmtree(work)]
    for step in steps:
        step()
        assert mt.cut("fin", str(work), str(out), inputs=str(inputs)) == {"dtm": "final"}
        assert _main(monkeypatch, "all", "fin", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
        assert _main(monkeypatch, "cut", "fin", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
        assert _snapshot(out) == before


def test_complete_only_when_every_input_is_there(tmp_path, monkeypatch, capsys):
    """Acceptance D: a product with one fetched file missing is not cut (nothing under --out) while its sibling,
    complete, is cut by `all` (exit 0, a line "waiting: ..."); --without of exactly that id cuts it and the index
    and the card name it; --without of a present id, or of an id that is no item, is an error."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    cells = [(x, y) for x in range(2) for y in range(2)]
    _fetch_area(inputs, cells, collection="MDT", done=cells[:3])
    _fetch_area(inputs, cells, collection="MDS", seed=40)
    _dataset(monkeypatch, "two", _product([mt.Fetched("portugal", collection="MDT")], "dtm"),
             _product([mt.Fetched("portugal", collection="MDS")], "dsm"))
    capsys.readouterr()
    assert _main(monkeypatch, "all", "two", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    printed = capsys.readouterr().out
    assert "waiting: two/dtm/5m: portugal/MDT: 3 of 4" in printed and "MDT-0101" in printed
    assert not (out / "two" / "dtm").exists() and (out / "two" / "dsm" / "5m" / "index.json").exists()
    assert not list(work.glob("staging/two/dtm*")) and not (out / ".staging" / "two" / "dtm").exists()
    with pytest.raises(ValueError, match="MDT-0000: it is present"):
        mt.cut("two", str(work), str(out), inputs=str(inputs), product="dtm", without=["MDT-0101", "MDT-0000"])
    with pytest.raises(ValueError, match="not an item"):
        mt.cut("two", str(work), str(out), inputs=str(inputs), product="dtm", without=["MDT-0101", "MDT-9999"])
    assert not (out / "two" / "dtm").exists()
    assert mt.cut("two", str(work), str(out), inputs=str(inputs), product="dtm", without=["MDT-0101"]) == \
        {"dtm": "cut"}
    index = json.loads((out / "two" / "dtm" / "5m" / "index.json").read_text())
    assert index["missing_inputs"] == ["MDT-0101"] and index["inputs"] == 3
    card = (out / "two" / "README.md").read_text(encoding="utf-8")
    assert "Cut without 1 sheets the provider did not deliver: MDT-0101." in card
    assert _main(monkeypatch, "cut", "two", "--work", str(work), "--out", str(out), "--inputs", str(inputs),
                 "--without", "MDT-0101") == 1  # several products: --product is needed


def test_inputs_never_written_or_removed(tmp_path, monkeypatch):
    """Acceptance E: an input named like an unpacked member beside --work; "tile!1.tif"; a fetch area "a!b"; a
    symbolic link in the work folder to an input; --work or --out inside the inputs (refused): the inputs folder's
    listing and sha256 the same after all and clean."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _tif(inputs / "m.tif", _heights((100, 100), 1), 9002.5, 1002.5)      # the name the ZIP's member unpacks to
    src_dir = tmp_path / "src"
    _tif(src_dir / "m.tif", _heights((100, 100), 2), 2.5, 1002.5)
    (inputs / "z").mkdir()
    with zipfile.ZipFile(inputs / "z" / "p.zip", "w") as z:
        z.write(src_dir / "m.tif", "m.tif")
    _tif(inputs / "tile!1.tif", _heights((100, 100), 3), 502.5, 1002.5)
    _fetch_area(inputs, [(1, 0)], area="a!b")
    work.mkdir()
    _dataset(monkeypatch, "safe", _product([mt.Placed("z/p.zip", members=("m.tif",)), mt.Placed("tile!1.tif"),
                                            mt.Fetched("a!b", collection="MDT")]))
    before = _snapshot(inputs)
    assert _main(monkeypatch, "all", "safe", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    assert _main(monkeypatch, "clean", "safe", "--work", str(work), "--inputs", str(inputs)) == 0
    assert _snapshot(inputs) == before
    assert (out / "safe" / "dtm" / "5m" / "index.json").exists()
    for argv in (("--work", str(inputs)), ("--work", str(inputs / "w")), ("--work", str(work), "--out",
                                                                           str(inputs / "mirror"))):
        args = ["all", "safe", "--inputs", str(inputs)] + list(argv)
        if "--out" not in argv:
            args += ["--out", str(out)]
        assert _main(monkeypatch, *args) == 1  # one sentence on stderr, exit 1
        with pytest.raises(ValueError, match="keep the inputs, the work folder and the mirror"):
            mt.check_folders(*(args[args.index(f) + 1] for f in ("--work", "--inputs", "--out")))
    assert _snapshot(inputs) == before
    with pytest.raises(ValueError, match="removes only files it made"):
        mt._remove(str(inputs / "tile!1.tif"), str(work))


def test_restart_keeps_the_tiles_of_its_journal(tmp_path, monkeypatch, capsys):
    """A cut stopped after some rows continues: the tiles whose files match their journal lines are kept, a tile
    file without its line (or changed since) is cut again, the result as one run's."""
    inputs = tmp_path / "in"
    _fetch_area(inputs, [(x, y) for x in range(6) for y in range(4)])
    _dataset(monkeypatch, "rs", _product([mt.Fetched("portugal", collection="MDT")]))
    mt.cut("rs", str(tmp_path / "w1"), str(tmp_path / "one"), inputs=str(inputs))
    two, w2 = tmp_path / "two", tmp_path / "w2"
    assert mt.cut("rs", str(w2), str(two), rows_limit=1, inputs=str(inputs)) == {"dtm": "stopped"}
    assert not (two / "rs").exists()
    staging = next(p for p in (w2 / "staging" / "rs" / "dtm" / "5m", two / ".staging" / "rs" / "dtm" / "5m")
                   if p.exists())
    tiles = sorted(staging.rglob("*.tif"))
    assert len(tiles) == 3
    tiles[0].write_bytes(tiles[0].read_bytes()[:-5] + b"xxxxx")  # damaged after its line: cut again
    (staging / "stray.tif").write_bytes(b"a file of nobody")
    capsys.readouterr()
    assert mt.cut("rs", str(w2), str(two), inputs=str(inputs)) == {"dtm": "cut"}
    assert "2 kept from before, 4 to cut" in capsys.readouterr().out
    assert _contents(tmp_path / "one" / "rs") == _contents(two / "rs")


def test_changed_sources_before_final(tmp_path, monkeypatch):
    """Before a product is final every doubt is cut again: a placed ASCII grid replaced by one 100 m higher makes
    its tiled copy in --work again and its tile is cut again (no stop); a placed ZIP replaced by a new version whose
    member has the same size is unpacked again (its CRC differs)."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    grid = _heights((10, 10), 3)
    (inputs / "asc").mkdir(parents=True)
    text = lambda v: _asc_text(v, left=2002.5, bottom=502.5).replace(b"cellsize 2", b"cellsize 5")  # noqa: E731
    (inputs / "asc" / "g.asc").write_bytes(text(grid))
    _dataset(monkeypatch, "ch", _product([mt.Placed("asc/g.asc")]))
    mt.cut("ch", str(work), str(out), rows_limit=0, inputs=str(inputs))  # scanned, the copy made, nothing cut
    (inputs / "asc" / "g.asc").write_bytes(text(grid + 100))
    os.utime(inputs / "asc" / "g.asc", ns=(1, 1))
    assert mt.cut("ch", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    tiles, _ = _tiles(out, mt.dataset("ch"))
    assert np.nanmin(tiles["1_0"]) > 590

    def member_zip(values):
        with rio.open(tmp_path / "src" / "m.tif", "w", driver="GTiff", width=100, height=100, count=1,
                      dtype="float32", crs="EPSG:5016", transform=from_origin(2.5, 1002.5, 5, 5)) as dst:
            dst.write(values.astype(np.float32), 1)
        with zipfile.ZipFile(inputs / "z" / "p.zip", "w") as z:
            z.write(tmp_path / "src" / "m.tif", "m.tif")
    (tmp_path / "src").mkdir()
    (inputs / "z").mkdir()
    member_zip(_heights((100, 100), 1))
    _dataset(monkeypatch, "zz", _product([mt.Placed("z/p.zip", members=("m.tif",))]))
    [path] = mt.extract("zz", str(work), str(inputs))
    size = os.path.getsize(path)
    member_zip(_heights((100, 100), 2))
    [again] = mt.extract("zz", str(work), str(inputs))
    assert again == path and os.path.getsize(path) == size
    with rio.open(path) as m:
        assert np.allclose(m.read(1), _heights((100, 100), 2).astype(np.float32))


def test_torn_done_line_and_files_not_recorded_yet(tmp_path, monkeypatch, capsys):
    """A done.jsonl whose last line was torn by a stopped fetch: skipped with one log line (its number, never its
    text), so that file is not an input yet and the product waits; a file on disk that done.jsonl does not record is
    no input; a file whose sha256 is not done.jsonl's stops the cut naming it."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _fetch_area(inputs, [(0, 0), (1, 0)])
    done = inputs / "portugal" / "done.jsonl"
    lines = done.read_text().splitlines()
    done.write_text(lines[0] + "\n" + lines[1][:30])
    _dataset(monkeypatch, "torn", _product([mt.Fetched("portugal", collection="MDT")]))
    capsys.readouterr()
    r = mt.resolve(mt.dataset("torn").products[0], str(work), str(inputs))
    printed = capsys.readouterr().out
    assert "line 2 is not UTF-8 or JSON" in printed and lines[1][:30] not in printed
    assert [x.id for x in r.rasters] == ["portugal/MDT/000/MDT-0000.tif"] and r.missing == ["MDT-0100"]
    assert mt.cut("torn", str(work), str(out), inputs=str(inputs)) == {"dtm": "waiting"}
    done.write_text("\n".join(lines) + "\n")
    path = inputs / "portugal" / "MDT" / "000" / "MDT-0000.tif"
    path.write_bytes(path.read_bytes()[:-10] + b"0123456789")
    with pytest.raises(ValueError, match="MDT-0000.tif: its sha256 is not the one done.jsonl records"):
        mt.cut("torn", str(work), str(out), inputs=str(inputs))
    assert not (out / "torn").exists()


def test_fetch_list_by_status(tmp_path, monkeypatch):
    """A fetch-list area (Wallonia's ZIPs: no manifest): complete when done.jsonl holds as many files of the group
    as status.json counts, each a ZIP whose members are the rasters."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    area = inputs / "wallonia"
    src_dir = tmp_path / "src"
    rows = []
    for n, name in enumerate(("A_NAMUR.zip", "A_LIEGE.zip")):
        _tif(src_dir / f"r{n}.tif", _heights((200, 200), n), 2.5 + 1000 * n, 1002.5)
        area.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(area / name, "w") as z:
            z.write(src_dir / f"r{n}.tif", f"inner/r{n}.tif")
        rows.append({"id": name, "group": "MNT", "path": name, "size": (area / name).stat().st_size,
                     "sha256": hashlib.sha256((area / name).read_bytes()).hexdigest()})
    (area / "status.json").write_text(json.dumps({"groups": {"MNT": {"files": 3}}}))
    (area / "done.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    _dataset(monkeypatch, "wal", _product([mt.Fetched("wallonia", group="MNT", members=("*.tif",))]))
    assert mt.cut("wal", str(work), str(out), inputs=str(inputs)) == {"dtm": "waiting"}
    (area / "status.json").write_text(json.dumps({"groups": {"MNT": {"files": 2}}}))
    assert mt.cut("wal", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    tiles, index = _tiles(out, mt.dataset("wal"))
    assert index["inputs"] == 2 and np.isfinite(tiles["0_0"][200:, :400]).all()


def test_upper_case_extensions(tmp_path, monkeypatch):
    """".tif" finds ".TIF" on every system (Linux's globs are case-sensitive), a ZIP member's pattern too."""
    inputs, work = tmp_path / "in", tmp_path / "work"
    _tif(inputs / "P.TIF", _heights((100, 100), 3), 1002.5, 1002.5)
    product = _product([mt.Placed("p.tif")])
    assert [r.id for r in mt.resolve(product, str(work), str(inputs)).rasters] == ["P.TIF"]
    assert mt._any_case("**/*.tif") == "**/*.[tT][iI][fF]" and mt._any_case("[ab]x") == "[ab][xX]"


def test_files_closed_after_their_last_row(tmp_path, monkeypatch):
    """A fetched area of 200 files: each is closed once the last row of tiles it covers is cut (at most two rows of
    files open, never all), and verify opens one sampled tile's files at a time."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _fetch_area(inputs, [(x, y) for x in range(20) for y in range(10)])
    _dataset(monkeypatch, "many", _product([mt.Fetched("portugal", collection="MDT")]))
    most, real = [0], mt.assemble

    def counting(key, product, footprints, handles):
        most[0] = max(most[0], len(handles))
        return real(key, product, footprints, handles)
    monkeypatch.setattr(mt, "assemble", counting)
    mt.cut("many", str(work), str(out), inputs=str(inputs))
    assert 0 < most[0] <= 40, most[0]
    most[0], real_points = 0, mt._point_problems

    def points(key, got, product, readers, rng, n, handles):
        found = real_points(key, got, product, readers, rng, n, handles)
        most[0] = max(most[0], len(handles))
        return found
    monkeypatch.setattr(mt, "_point_problems", points)
    result = mt.verify("many", str(work), str(out), inputs=str(inputs), samples=50)["dtm"]
    assert result["ok"] and len(result["samples"]) == 50 and 4 <= most[0] <= 16, most[0]


def test_verify_checks_the_extent_and_the_feeders(tmp_path, monkeypatch):
    """verify's checks apart from the cut's plan: a tile dropped from the index that an input's own bounds touch, and
    an input the journal never names as a feeder, are found; a product that is not final is not verified."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _fetch_area(inputs, [(x, 0) for x in range(4)])
    _dataset(monkeypatch, "ext", _product([mt.Fetched("portugal", collection="MDT")]))
    assert mt.verify("ext", str(work), str(out), inputs=str(inputs))["dtm"]["ok"] is None  # not final
    mt.cut("ext", str(work), str(out), inputs=str(inputs))
    assert mt.verify("ext", str(work), str(out), inputs=str(inputs))["dtm"]["ok"]
    folder = out / "ext" / "dtm" / "5m"
    journal = next((work / "journals").glob("ext.dtm.5m-*.jsonl"))
    kept = journal.read_text()
    journal.write_text("\n".join(line for line in kept.splitlines() if "MDT-0300" not in line))
    problems = "\n".join(mt.verify("ext", str(work), str(out), inputs=str(inputs))["dtm"]["problems"])
    assert "MDT-0300.tif: an input under listed tiles that fed none" in problems
    journal.write_text(kept)
    index = json.loads((folder / "index.json").read_text())
    del index["tiles"]["1_0"]
    os.remove(folder / "0_0" / "1_0.tif")
    (folder / "index.json").write_text(json.dumps(index))
    problems = "\n".join(mt.verify("ext", str(work), str(out), inputs=str(inputs))["dtm"]["problems"])
    assert "tile(s) under an input are not in the index: ['1_0']" in problems


def test_download_waits_for_another(served, tmp_path, monkeypatch):
    """Never two downloads at once: a download that finds another process holding the lock waits (it says so) and
    asks the server only after that process let go (no clock: the order of events)."""
    import threading
    server, spec, work = served
    work.mkdir()
    release = tmp_path / "release"
    script = tmp_path / "hold_download.py"
    script.write_text("import sys, os, time\nfrom filelock import FileLock\nwith FileLock(sys.argv[1]):\n"
                      "    print('held', flush=True)\n    while not os.path.exists(sys.argv[2]):\n"
                      "        time.sleep(0.02)\n")
    proc = subprocess.Popen([sys.executable, str(script), str(work / "download.lock"), str(release)],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    waiting, order = threading.Event(), []
    monkeypatch.setattr(mt, "_on_wait", lambda path: waiting.set())
    real_fetch = mt._fetch

    def fetch(*args):
        order.append(("fetch", release.exists()))
        return real_fetch(*args)
    monkeypatch.setattr(mt, "_fetch", fetch)
    paths = []
    thread = threading.Thread(target=lambda: paths.extend(mt.download("dl", str(work))))
    thread.start()
    assert waiting.wait(60)
    assert not server.requests("/files/")
    release.write_text("")
    thread.join(60)
    proc.wait(30)
    assert order == [("fetch", True)] and open(paths[0], "rb").read() == BODY


@pytest.mark.parametrize("site", mt.WRITE_SITES)
def test_a_stop_with_the_staging_folder_in_the_mirror(tmp_path, monkeypatch, site):
    """Acceptance A and B with the staging folder in <out>/.staging (--work on another filesystem or mount, as in a
    container with separate mounts): a stop at each write site leaves nothing a reader takes for the dataset, and the
    run to completion makes what an uninterrupted run makes."""
    real = mt.staging_folder

    def in_out(work, out, ds, product):
        return os.path.join(out, ".staging", ds.name, product.name, f"{product.res:g}m"), "in <out>/.staging (test)"
    monkeypatch.setattr(mt, "staging_folder", in_out)
    seen, ref = _visits(tmp_path, monkeypatch)
    nth = 2 if seen[site] >= 2 else 1
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _stops_inputs(inputs)
    monkeypatch.setitem(mt.DATASETS, "stops", _stops_dataset(inputs))
    passed = [0]

    def hook(name):
        if name == site:
            passed[0] += 1
            if passed[0] == nth:
                raise _Stop(site)
    monkeypatch.setattr(mt, "HOOK", hook)
    with pytest.raises(_Stop):
        _cut_and_verify(work, out, inputs)
    monkeypatch.setattr(mt, "HOOK", None)
    seen_now = _reader_sees(out, "stops/dtm/5m", monkeypatch)
    assert not (out / "stops" / "dtm" / "5m").exists() or seen_now is not None
    if seen_now is not None:
        got, want = _contents(out / "stops" / "dtm" / "5m"), _contents(ref / "stops" / "dtm" / "5m")
        assert {k: v for k, v in got.items() if not k.startswith("verify.json")} == \
            {k: v for k, v in want.items() if k != "verify.json"}
    assert _cut_and_verify(work, out, inputs)[1]["ok"] is True
    assert _contents(out / "stops") == _contents(ref / "stops")
    assert not list((out / ".staging").rglob("*.tif"))
    assert real is not mt.staging_folder


def test_a_waiting_product_writes_nothing_under_out(tmp_path, monkeypatch):
    """A product with a fetched file missing: cut, all and verify leave --out as it was (here: not even made)."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    cells = [(0, 0), (1, 0)]
    _fetch_area(inputs, cells, done=cells[:1])
    _dataset(monkeypatch, "wait", _product([mt.Fetched("portugal", collection="MDT")]))
    assert mt.cut("wait", str(work), str(out), inputs=str(inputs)) == {"dtm": "waiting"}
    assert _main(monkeypatch, "all", "wait", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    assert mt.verify("wait", str(work), str(out), inputs=str(inputs))["dtm"]["ok"] is None
    assert not out.exists()


def _stop_after(rows, monkeypatch):
    """A HOOK that stops a cut after its journal's rows-th line."""
    lines = [0]

    def hook(name):
        if name == "journal.after_line":
            lines[0] += 1
            if lines[0] == rows:
                raise _Stop()
    monkeypatch.setattr(mt, "HOOK", hook)


@pytest.mark.parametrize("doubt", ["torn", "deleted", "garbage", "input changed", "floor changed", "order changed"])
def test_every_doubt_is_cut_again(tmp_path, monkeypatch, doubt):
    """Before a product is final every doubt is resolved by cutting again: after a stop, a torn last journal line, a
    deleted journal, a journal of garbage, an input re-fetched with other values after its tile was journaled, the
    product's floor or its inputs' order changed in DATASETS: the run goes on and ends as an uninterrupted run with
    what is there now."""
    inputs, work, out, ref_in = tmp_path / "in", tmp_path / "work", tmp_path / "out", tmp_path / "ref-in"
    cells = [(x, y) for x in range(4) for y in range(2)]
    for folder in (inputs, ref_in):
        _fetch_area(folder, cells)
        _fetch_area(folder, [(0, 0)], area="extra", collection="X", seed=70)  # overlaps cell (0, 0)
    first = (mt.Fetched("portugal", collection="MDT"), mt.Fetched("extra", collection="X"))
    _dataset(monkeypatch, "dbt", _product(list(first)))
    _stop_after(1, monkeypatch)
    with pytest.raises(_Stop):
        mt.cut("dbt", str(work), str(out), inputs=str(inputs))
    monkeypatch.setattr(mt, "HOOK", None)
    journal = next((work / "journals").glob("dbt.dtm.5m-*.jsonl"))
    if doubt == "torn":
        journal.write_bytes(journal.read_bytes()[:-20])
    elif doubt == "deleted":
        journal.unlink()
    elif doubt == "garbage":
        journal.write_bytes(b"\x00\xffnot json\n{\"key\": 3}\n")
    elif doubt == "input changed":  # the fetch got the file again with other values (and recorded its sha256)
        for folder in (inputs, ref_in):
            root = folder / "portugal"
            path = _tif(root / "MDT" / "000" / "MDT-0000.tif", _heights((200, 200), 77), 2.5, 1002.5)
            rows = [json.loads(line) for line in (root / "done.jsonl").read_text().splitlines()]
            for row in rows:
                if row["id"] == "MDT-0000":
                    row.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            (root / "done.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    elif doubt == "floor changed":
        _dataset(monkeypatch, "dbt", _product(list(first), floor=1200.0))
    elif doubt == "order changed":
        _dataset(monkeypatch, "dbt", _product(list(reversed(first))))
    assert mt.cut("dbt", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    ref = tmp_path / "ref-out"
    mt.cut("dbt", str(tmp_path / "ref-work"), str(ref), inputs=str(ref_in))
    assert _contents(out / "dbt") == _contents(ref / "dbt")


@pytest.mark.skipif(os.name != "nt", reason="drives are Windows'")
def test_folders_on_other_drives():
    """Folders on two drives are apart, not an error (the mirror on another drive than --work)."""
    assert mt._below(r"C:\a", r"D:\b") is False
    mt.check_folders(r"C:\work", r"C:\in", r"D:\mirror")


# The last round (2026-11-16): ids by path, verify against the cut's inputs, the fetch tool's pair, staging

def test_placed_inputs_of_one_name(tmp_path, monkeypatch):
    """Two placed inputs of one file name in two folders have two ids (their paths below --inputs). The reviewer's
    sequence: cut one row, a/d.tif rewritten 100 m higher, cut to the end: the result is a fresh cut of what is there
    now, and verify passes on a fresh cut. The same path listed twice is an error naming both."""
    inputs = tmp_path / "in"
    _tif(inputs / "a" / "d.tif", _heights((400, 400), 1), 2.5, 4002.5)
    _tif(inputs / "b" / "d.tif", _heights((400, 400), 2), 2.5, 2002.5)
    ds = _dataset(monkeypatch, "names", _product([mt.Placed("a/d.tif"), mt.Placed("b/d.tif")]))
    assert [r.id for r in mt.resolve(ds.products[0], str(tmp_path / "w"), str(inputs)).rasters] == ["a/d.tif",
                                                                                                    "b/d.tif"]
    work, out = tmp_path / "work", tmp_path / "out"
    assert mt.cut("names", str(work), str(out), rows_limit=1, inputs=str(inputs)) == {"dtm": "stopped"}
    _tif(inputs / "a" / "d.tif", _heights((400, 400), 1) + 100, 2.5, 4002.5)
    os.utime(inputs / "a" / "d.tif", ns=(1, 1))
    assert mt.cut("names", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    fresh = tmp_path / "fresh"
    mt.cut("names", str(tmp_path / "w2"), str(fresh), inputs=str(inputs))
    assert _contents(out / "names") == _contents(fresh / "names")
    assert mt.verify("names", str(tmp_path / "w2"), str(fresh), inputs=str(inputs))["dtm"]["ok"] is True
    _dataset(monkeypatch, "twice", _product([mt.Placed("a/d.tif"), mt.Placed("a/d.tif")]))
    with pytest.raises(ValueError, match="two rasters of one id 'a/d.tif'"):
        mt.resolve(mt.dataset("twice").products[0], str(work), str(inputs))


def test_inputs_that_came_after_the_cut(tmp_path, monkeypatch, capsys):
    """A final product judges against the inputs it was cut from (inputs.jsonl): a sheet cut --without that arrives
    later, and a new input added inside the extent before the first verify, are no part of the edition (one line),
    never an error; `all` exits 0 and verify passes."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    cells = [(0, 0), (1, 0), (2, 0), (3, 0)]
    _fetch_area(inputs, cells, done=cells[:3])
    _dataset(monkeypatch, "late", _product([mt.Fetched("portugal", collection="MDT")]))
    assert mt.cut("late", str(work), str(out), inputs=str(inputs), without=["MDT-0300"]) == {"dtm": "cut"}
    recorded = (out / "late" / "dtm" / "5m" / "inputs.jsonl").read_text().splitlines()
    assert [json.loads(line)["id"] for line in recorded] == [f"portugal/MDT/000/MDT-0{x}00.tif" for x in range(3)]
    shutil.rmtree(inputs / "portugal")
    _fetch_area(inputs, cells)                       # the missing sheet arrived
    _fetch_area(inputs, [(1, 1)], collection="MDT", seed=90)  # and one more inside the extent
    capsys.readouterr()
    assert _main(monkeypatch, "all", "late", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    printed = capsys.readouterr().out
    assert "2 inputs arrived after this product was cut (not part of this edition)" in printed
    result = json.loads((out / "late" / "dtm" / "5m" / "verify.json").read_text())
    assert result["ok"] is True and not result["problems"]


def test_verify_after_the_inputs_were_deleted(tmp_path, monkeypatch, capsys):
    """A first verify after a final product's inputs were deleted compares no tile: not checkable (ok null), status
    says "final, not verified (inputs removed)", `all` exits 0 with that line and does not skip it next time."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _tif(inputs / "v.tif", _heights((400, 400), 9), 2.5, 2002.5)
    _dataset(monkeypatch, "gone", _product([mt.Placed("v.tif")]))
    mt.cut("gone", str(work), str(out), inputs=str(inputs))
    os.remove(inputs / "v.tif")
    result = mt.verify("gone", str(work), str(out), inputs=str(inputs))["dtm"]
    assert result["ok"] is None and json.loads((out / "gone" / "dtm" / "5m" / "verify.json").read_text())["ok"] is None
    assert any("final" in line and "not verified (inputs removed)" in line
               for line in mt.status(["gone"], str(work), str(out), str(inputs)))
    capsys.readouterr()
    assert _main(monkeypatch, "all", "gone", "--work", str(work), "--inputs", str(inputs), "--out", str(out)) == 0
    assert "final, not verified (inputs removed)" in capsys.readouterr().out
    assert mt.verified(mt.dataset("gone"), mt.dataset("gone").products[0], str(out)) is None


def test_the_fetch_tools_reasons(tmp_path, monkeypatch, capsys):
    """A manifest row planned again with a newer version than done.jsonl's, and a file of another size than the
    manifest's: waiting, each with its reason; a fetched ZIP whose bytes are not done.jsonl's is refused before its
    members are read, saying what to do with the fetch tool."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _fetch_area(inputs, [(0, 0), (1, 0)])
    area = inputs / "portugal"
    rows = [json.loads(line) for line in (area / "manifest.jsonl").read_text().splitlines()]
    done = [json.loads(line) for line in (area / "done.jsonl").read_text().splitlines()]
    rows[0]["version"], done[0]["version"] = "02", "01"
    rows[1]["size"] = done[1]["size"] + 1
    (area / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (area / "done.jsonl").write_text("\n".join(json.dumps(r) for r in done) + "\n")
    _dataset(monkeypatch, "why", _product([mt.Fetched("portugal", collection="MDT")]))
    r = mt.resolve(mt.dataset("why").products[0], str(work), str(inputs))
    assert r.missing == ["MDT-0000 (a newer version in the manifest)", "MDT-0100 (size differs)"]
    assert mt.cut("why", str(work), str(out), inputs=str(inputs)) == {"dtm": "waiting"}
    wal = inputs / "wallonia"
    wal.mkdir()
    _tif(tmp_path / "src" / "r.tif", _heights((100, 100), 1), 2.5, 502.5)
    with zipfile.ZipFile(wal / "A.zip", "w") as z:
        z.write(tmp_path / "src" / "r.tif", "r.tif")
    (wal / "status.json").write_text(json.dumps({"groups": {"MNT": {"files": 1}}}))
    (wal / "done.jsonl").write_text(json.dumps({"id": "A.zip", "group": "MNT", "path": "A.zip",
                                                "size": (wal / "A.zip").stat().st_size, "sha256": "0" * 64}) + "\n")
    _dataset(monkeypatch, "wz", _product([mt.Fetched("wallonia", group="MNT", members=("*.tif",))]))
    with pytest.raises(ValueError, match="remove the file and its line from done.jsonl, then run the fetch tool"):
        mt.cut("wz", str(work), str(out), inputs=str(inputs))
    assert not (work / "A").exists()


def test_the_probes_rename_fails_for_real(tmp_path, monkeypatch, capsys):
    """When a folder does not rename from --work into --out (the probe's os.replace fails, as across mounts), the
    staging folder is <out>/.staging and the product ends final; a stop left no probe behind. When the final rename
    itself crosses filesystems the cut stops in one sentence and keeps the staging folder."""
    import errno
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _tif(inputs / "r.tif", _heights((400, 400), 3), 2.5, 2002.5)
    _dataset(monkeypatch, "prb", _product([mt.Placed("r.tif")]))
    (out / ".probe-prb.dtm.5m").mkdir(parents=True)  # left by a stop
    real = os.replace

    def replace(a, b):
        if os.path.basename(str(a)).startswith(".probe-"):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real(a, b)
    monkeypatch.setattr(mt.os, "replace", replace)
    capsys.readouterr()
    assert mt.cut("prb", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    assert "staging in <out>/.staging" in capsys.readouterr().out
    assert not list(out.glob(".probe-*")) and not list((work / "staging").glob(".probe-*"))

    _dataset(monkeypatch, "far", _product([mt.Placed("r.tif")]))

    def replace_far(a, b):
        if str(b).endswith(os.path.join("far", "dtm", "5m")):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real(a, b)
    monkeypatch.setattr(mt.os, "replace", replace_far)
    with pytest.raises(ValueError, match="does not rename into .* the staging folder is kept"):
        mt.cut("far", str(work), str(out), inputs=str(inputs))
    assert not (out / "far" / "dtm" / "5m").exists()
    kept = [s for s in mt.staging_folders(str(work), str(out)) if s[0] == "far"]
    assert kept and (pathlib_of(kept[0][3]) / "index.json").exists()


def pathlib_of(path):
    from pathlib import Path
    return Path(path)


def test_abandoned_staging_listed_and_cleaned(tmp_path, monkeypatch):
    """status lists every staging folder with its tiles and size; clean removes one only with --staging (a product
    not final), or by itself when the product is final (a leftover), never while a run holds the product's lock."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _tif(inputs / "r.tif", _heights((800, 400), 3), 2.5, 4002.5)
    _dataset(monkeypatch, "ab", _product([mt.Placed("r.tif")]))
    assert mt.cut("ab", str(work), str(out), rows_limit=1, inputs=str(inputs)) == {"dtm": "stopped"}
    assert any(line.startswith("staging: ab/dtm/5m: 1 tiles") for line in mt.status(["ab"], str(work), str(out),
                                                                                     str(inputs)))
    mt.clean("ab", str(work), str(inputs), out=str(out))
    assert mt.staging_folders(str(work), str(out))
    release = tmp_path / "release"
    proc = _holder(tmp_path, str(out / ".locks" / "ab.dtm.5m.lock"), str(release))
    try:
        mt.clean("ab", str(work), str(inputs), out=str(out), staging=True)  # a run holds it: kept
        assert mt.staging_folders(str(work), str(out))
    finally:
        release.write_text("")
        proc.wait(30)
    mt.clean("ab", str(work), str(inputs), out=str(out), staging=True)
    assert not mt.staging_folders(str(work), str(out))
    # a leftover beside a final product
    mt.cut("ab", str(work), str(out), inputs=str(inputs))
    leftover = work / "staging" / "ab" / "dtm" / "5m" / "0_0"
    leftover.mkdir(parents=True)
    (leftover / "0_1.tif").write_bytes(b"old")
    assert any("a leftover" in line for line in mt.status(["ab"], str(work), str(out), str(inputs)))
    mt.clean("ab", str(work), str(inputs), out=str(out))
    assert not mt.staging_folders(str(work), str(out))


def test_links_in_the_work_folder(tmp_path, monkeypatch):
    """A symbolic link in --work where the tool writes a member (and its .part) is replaced by the tool's file; the
    input it pointed to keeps its bytes. Skipped where links cannot be made (Windows without the right)."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "out"
    _tif(inputs / "x.tif", _heights((100, 100), 1), 9002.5, 1002.5)
    _tif(tmp_path / "src" / "m.tif", _heights((100, 100), 2), 2.5, 1002.5)
    (inputs / "z").mkdir()
    with zipfile.ZipFile(inputs / "z" / "p.zip", "w") as z:
        z.write(tmp_path / "src" / "m.tif", "m.tif")
    work.mkdir()
    try:
        os.symlink(inputs / "x.tif", work / "m.tif")
        os.symlink(inputs / "x.tif", work / "m.tif.part")
    except OSError:
        pytest.skip("symbolic links cannot be made here")
    _dataset(monkeypatch, "lnk", _product([mt.Placed("z/p.zip", members=("m.tif",))]))
    before = _snapshot(inputs)
    assert mt.cut("lnk", str(work), str(out), inputs=str(inputs)) == {"dtm": "cut"}
    assert _snapshot(inputs) == before and not (work / "m.tif").is_symlink()


def test_the_card_of_a_finished_product_rewritten(tmp_path, monkeypatch, capsys):
    """`cut` of a final product through the tool's command line rewrites a README.md that differs from card_text
    (or is missing) and touches nothing else: no README.md.part left, every other file of the dataset the same bytes
    and modification time; a second run changes nothing. Until 2026-11-17 the old card was still open when
    write_card replaced it: Windows refused (WinError 5) and README.md.part stayed beside it."""
    monkeypatch.setattr(mt, "REPLACE_SECONDS", 2)  # a refused replace fails fast, not after a minute
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _tif(inputs / "t.tif", _heights((300, 300), 1), 402.5, 1902.5)
    ds = _dataset(monkeypatch, "isle", _product([mt.Placed("t.tif")], "dtm"))
    mt.cut("isle", str(work), str(out), inputs=str(inputs))
    readme = out / "isle" / "README.md"
    card = mt.card_text(ds, str(out))

    def others():
        return {p.relative_to(out).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in out.rglob("*") if p.is_file() and p.name != "README.md"}

    def cut_command():
        monkeypatch.setattr(sys, "argv", ["mirror_tiles.py", "cut", "isle", "--work", str(work), "--out", str(out)])
        mt.main()  # returns on success: exit 0
        assert "isle/dtm/5m: final; nothing is cut again" in capsys.readouterr().out

    before = others()
    for case in ("differs", "missing"):
        if case == "differs":
            readme.write_text("# an older card\n", encoding="utf-8")
        else:
            readme.unlink()
        cut_command()
        assert readme.read_text(encoding="utf-8") == card, case
        assert not (out / "isle" / "README.md.part").exists() and others() == before, case
        stamp = readme.stat().st_mtime_ns
        cut_command()  # again: nothing changes
        assert readme.stat().st_mtime_ns == stamp and others() == before, case
