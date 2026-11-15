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
    (with 0.024 mm of noise in the header), cut on its own grid; a stopped cut says "partial" and resumes."""
    spec = _spec(monkeypatch, "asc", url="https://example.org/dl/test.zip", member="T.ASC")
    values = _asc_values()
    work, out = tmp_path / "work", tmp_path / "mirror"
    _zip(work, "T.ASC", _asc_text(values), "test.zip")
    assert mt.extract("asc", str(work)) == [str(work / "T.ASC")]
    index = mt.cut("asc", str(work), str(out), rows_limit=1)
    assert index["partial"] is True
    mt.cut("asc", str(work), str(out))
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
    assert sorted(os.listdir(work)) == ["bad.zip"]


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
        mt.cut("prov", str(work), str(out), inputs=str(inputs))


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


def test_folder_of_1km_files_restarts_and_completes(tmp_path, monkeypatch):
    """Portugal's kind: a folder of 1 km files (here 200 px of 5 m) with done.jsonl, four per 2 km tile. While the
    folder holds fewer files than expected the index is partial and lists only tiles with data (never null); a tile
    cut from fewer files than cover it later is cut again; once complete the empty tiles are null and partial goes.
    A file whose sha256 is not done.jsonl's stops the cut."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    folder = inputs / "pt" / "MDT-50cm"
    sheets = {}
    for n, (x, y) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1), (4, 0), (5, 1)]):
        sheets[(x, y)] = _heights((200, 200), 10 + n)
    done = []

    def place(*cells):
        for x, y in cells:
            path = _tif(folder / f"{x}{y}" / f"sheet_{x}_{y}.tif", sheets[(x, y)], 2.5 + 1000 * x, 1002.5 + 1000 * y)
            done.append(json.dumps({"item": f"sheet_{x}_{y}", "size": path.stat().st_size,
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
        (inputs / "pt" / "done.jsonl").write_text("\n".join(done) + "\n", encoding="utf-8")

    ds = _dataset(monkeypatch, "pt-test", _product([mt.Folder("pt/MDT-50cm", expected=6, done="../done.jsonl")]))
    place((0, 0), (1, 0), (4, 0))
    mt.cut("pt-test", str(work), str(out), inputs=str(inputs))
    tiles, index = _tiles(out, ds)
    assert index["partial"] is True and set(tiles) == {"0_0", "2_0"}
    assert all(v is not None for v in tiles.values())
    assert np.isnan(tiles["0_0"][:200, :]).all()  # the north half's files are not there yet
    first = (out / "pt-test" / "dtm" / "5m" / "0_0" / "2_0.tif").read_bytes()
    place((0, 1), (1, 1), (5, 1))
    mt.cut("pt-test", str(work), str(out), inputs=str(inputs))
    tiles, index = _tiles(out, ds)
    assert "partial" not in index and tiles["1_0"] is None and set(tiles) == {"0_0", "1_0", "2_0"}
    want = _expected([(v, 2.5 + 1000 * x, 1002.5 + 1000 * y) for (x, y), v in sheets.items()])
    for key in ("0_0", "2_0"):
        _close(tiles[key], want[key])  # 0_0 cut again from its four files, 2_0 from its two
    assert (out / "pt-test" / "dtm" / "5m" / "0_0" / "2_0.tif").read_bytes() != first
    # Nothing changes on a third run
    snapshot = (out / "pt-test" / "dtm" / "5m" / "index.json").read_bytes()
    mt.cut("pt-test", str(work), str(out), inputs=str(inputs))
    assert (out / "pt-test" / "dtm" / "5m" / "index.json").read_bytes() == snapshot
    # A damaged file is refused by its sha256 (the state of the earlier runs is forgotten with the work)
    path = folder / "00" / "sheet_0_0.tif"
    path.write_bytes(path.read_bytes()[:-10] + b"0123456789")
    with pytest.raises(ValueError, match="done.jsonl"):
        mt.cut("pt-test", str(tmp_path / "work2"), str(tmp_path / "mirror2"), inputs=str(inputs))


def test_stopped_cut_resumes_to_the_same_tiles(tmp_path, monkeypatch):
    """A cut stopped after a row (and a tile's .new left by a kill) resumes to the same tiles as one run."""
    inputs = tmp_path / "in"
    values = _heights((900, 500), 7)
    _tif(inputs / "r.tif", values, 2.5, 4002.5)
    _dataset(monkeypatch, "rs", _product([mt.Placed("r.tif")]))
    one = tmp_path / "one"
    mt.cut("rs", str(tmp_path / "w1"), str(one), inputs=str(inputs))
    two = tmp_path / "two"
    index = mt.cut("rs", str(tmp_path / "w2"), str(two), rows_limit=1, inputs=str(inputs))
    assert index["partial"] is True and len(index["tiles"]) == 2
    stray = two / "rs" / "dtm" / "5m" / "0_0" / "0_0.tif.new"
    stray.write_bytes(b"half a tile")
    mt.cut("rs", str(tmp_path / "w2"), str(two), inputs=str(inputs))
    assert not stray.exists()
    files = lambda root: {p.relative_to(root): p.read_bytes() for p in root.rglob("*.tif")}  # noqa: E731
    assert files(one / "rs") == files(two / "rs") and len(files(one / "rs")) == 6
    a, b = (json.loads((r / "rs" / "dtm" / "5m" / "index.json").read_text()) for r in (one, two))
    assert a["tiles"] == b["tiles"] and "partial" not in b


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
    assert mt._workers(_product([], res=0.5), 6, 8.0)[0] == 6  # the server's bound: six tiles of 0.5 m at a time


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
    assert any("verify" in line and "ok" in line for line in mt.status(["ver"], str(work), str(out), str(inputs)))
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
    assert any("FAILED" in line for line in mt.status(["ver"], str(work), str(out), str(inputs)))


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


def _sheets(folder, nx, ny, seed=20):
    """nx x ny files of 1 km (200 px of 5 m) from (2.5, 2.5), with a done.jsonl beside the folder; their values."""
    done, values = [], {}
    for y in range(ny):
        for x in range(nx):
            values[(x, y)] = _heights((200, 200), seed + x + 100 * y)
            path = _tif(folder / f"{y:02d}" / f"s{x:02d}{y:02d}.tif", values[(x, y)], 2.5 + 1000 * x,
                        1002.5 + 1000 * y)
            done.append(json.dumps({"item": path.stem, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
    (folder.parent / "done.jsonl").write_text("\n".join(done) + "\n", encoding="utf-8")
    return values


def test_removed_inputs_leave_a_finished_product(tmp_path, monkeypatch):
    """The user deletes fetched files by hand once a product is cut: a cut run again cuts nothing, the index stays
    complete, every byte as it was; a file put back under its old name (other bytes, no sha256 line) is not cut again:
    its tiles were cut from it."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    folder = inputs / "pt" / "MDT"
    _sheets(folder, 4, 2)
    ds = _dataset(monkeypatch, "rm", _product([mt.Folder("pt/MDT", expected=8, done="../done.jsonl")]))
    mt.cut("rm", str(work), str(out), inputs=str(inputs))
    snapshot = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert "partial" not in json.loads((out / "rm" / "dtm" / "5m" / "index.json").read_text())
    os.remove(folder / "00" / "s0000.tif")
    os.remove(folder / "01" / "s0101.tif")
    mt.cut("rm", str(work), str(out), inputs=str(inputs))
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == snapshot
    assert any("waiting for" in line for line in mt.status(["rm"], str(work), str(out), str(inputs)))
    _tif(folder / "00" / "s0000.tif", _heights((200, 200), 99), 2.5, 1002.5)   # back, other heights: no sha256 line
    lines = (folder.parent / "done.jsonl").read_text().splitlines()
    (folder.parent / "done.jsonl").write_text("\n".join(line for line in lines if "s0000" not in line) + "\n")
    mt.cut("rm", str(work), str(out), inputs=str(inputs))
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == snapshot  # not added: nothing cut
    tiles, index = _tiles(out, ds)
    assert "partial" not in index and set(tiles) == {"0_0", "1_0"}


def test_files_closed_after_their_last_row(tmp_path, monkeypatch):
    """A folder of 200 files: each is closed once the last row of tiles it covers is cut, so the cut holds the files
    of about two rows of files open, never all of them (Portugal: 91 000 per product)."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _sheets(inputs / "pt" / "MDT", 20, 10)
    _dataset(monkeypatch, "many", _product([mt.Folder("pt/MDT", expected=200, done="../done.jsonl")]))
    most, real = [0], mt.assemble

    def counting(key, product, footprints, handles):
        most[0] = max(most[0], len(handles))
        return real(key, product, footprints, handles)
    monkeypatch.setattr(mt, "assemble", counting)
    mt.cut("many", str(work), str(out), inputs=str(inputs))
    assert 0 < most[0] <= 40, most[0]
    tiles, index = _tiles(out, mt.dataset("many"))
    assert len(tiles) == 50 and "partial" not in index


def test_done_jsonl_naming_none_of_the_files(tmp_path, monkeypatch):
    """A done.jsonl whose keys name none of the folder's files is an error (no file could be checked); without one
    the files are cut unchecked and the cut says so."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    _sheets(inputs / "pt" / "MDT", 2, 1)
    (inputs / "pt" / "done.jsonl").write_text(json.dumps({"key": "s0000", "hash": "x"}) + "\n" +
                                             json.dumps({"other": "s0100", "sha256": "0" * 64}) + "\n")
    _dataset(monkeypatch, "dj", _product([mt.Folder("pt/MDT", expected=2, done="../done.jsonl")]))
    with pytest.raises(ValueError, match="names none of the 2 files"):
        mt.cut("dj", str(work), str(out), inputs=str(inputs))
    os.remove(inputs / "pt" / "done.jsonl")
    mt.cut("dj", str(work), str(out), inputs=str(inputs))
    assert mt.resolve(mt.dataset("dj").products[0], str(work), str(inputs)).checks == [
        "pt/MDT: no ../done.jsonl, the files not checked"]
    assert mt.done_digests(str(tmp_path / "none.jsonl")) == {}


def test_clean_leaves_the_inputs(tmp_path, monkeypatch):
    """clean removes the product's unpacked ZIP members and tiled copies from --work, never an input or a downloaded
    file."""
    inputs, work, out = tmp_path / "in", tmp_path / "work", tmp_path / "mirror"
    src_dir = tmp_path / "src"
    _tif(src_dir / "a.tif", _heights((100, 100), 1), 2.5, 1002.5)
    (inputs / "z").mkdir(parents=True)
    with zipfile.ZipFile(inputs / "z" / "p.zip", "w") as z:
        z.write(src_dir / "a.tif", "a.tif")
    _tif(inputs / "b.tif", _heights((100, 100), 2), 1002.5, 1002.5)
    (inputs / "asc").mkdir()
    (inputs / "asc" / "g.asc").write_bytes(_asc_text(_heights((10, 10), 3), left=2002.5, bottom=502.5)
                                           .replace(b"cellsize 2", b"cellsize 5"))
    _dataset(monkeypatch, "cl", _product([mt.Placed("z/p.zip", members=("*.tif",)), mt.Placed("b.tif"),
                                         mt.Placed("asc/g.asc")]))
    before = {p: p.read_bytes() for p in inputs.rglob("*") if p.is_file()}
    mt.extract("cl", str(work), str(inputs))
    mt.cut("cl", str(work), str(out), inputs=str(inputs))
    assert (work / "p" / "a.tif").exists() and list((work / "tiled").glob("g-*.tif"))
    left = mt.clean("cl", str(work), str(inputs))
    assert not (work / "p" / "a.tif").exists() and not list((work / "tiled").glob("*.tif"))
    assert all(name.startswith("state") for name in left), left
    assert {p: p.read_bytes() for p in inputs.rglob("*") if p.is_file()} == before
