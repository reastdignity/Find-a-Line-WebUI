"""tools/mirror_tiles.py: own copies of elevation models published as one big file (Madeira's BigTIFF, Valle
d'Aosta's comma-decimal ASCII grid in a Deflate64 ZIP), downloaded, unpacked and cut into 2 km tiles of the local
mirror on the data's own pixel grid; sources.GridTiles reads them back with the same origin."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
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
    assert mt.extract("asc", str(work)) == str(work / "T.ASC")
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
    path = mt.extract("asc64", str(work))
    assert open(path, "rb").read() == data and not os.path.exists(path + ".part")
    # A flipped byte in the compressed data: 7-Zip's CRC check fails, nothing is put in place
    os.remove(path)
    raw = bytearray((work / "t64.zip").read_bytes())
    offset = info.header_offset + 30 + len(info.filename) + len(info.extra) + 20
    raw[offset] ^= 0xFF
    (work / "t64.zip").write_bytes(bytes(raw))
    with pytest.raises(RuntimeError, match="7-Zip"):
        mt.extract("asc64", str(work))
    assert not os.path.exists(path)


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
    path = mt.download("dl", str(work))
    assert open(path, "rb").read() == BODY and not os.path.exists(path + ".part")
    assert _ranges(server) == [None]
    assert server.requests("/files/")[0].user_agent.startswith("Find-a-Line")
    assert mt.download("dl", str(work)) == path and len(server.requests("/files/")) == 1  # complete: no request


def test_download_resumes_after_a_cut(served):
    """A part from before resumes by a Range from its end; an answer cut short is resumed again from where it
    stopped. Never a Range of 0-0, never one from 0."""
    server, spec, work = served
    work.mkdir()
    (work / "data.zip.part").write_bytes(BODY[:100_000])
    server.fault("/files/data.zip", "truncate", lambda n, rng: n == 1)
    path = mt.download("dl", str(work))
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
    path = mt.download("dl", str(work))
    assert open(path, "rb").read() == BODY and _ranges(server) == ["bytes=5000-"]


def test_download_without_a_range_beyond_resume_below(served, monkeypatch):
    """Valle d'Aosta's firewall refuses a Range beyond about 1e8 bytes: a part from before beyond resume_below
    starts again with a plain GET; below it the Range is sent."""
    server, spec, work = served
    monkeypatch.setitem(mt.DATASETS, "dl", {**spec, "resume_below": 50_000})
    work.mkdir()
    (work / "data.zip.part").write_bytes(BODY[:60_000])
    assert open(mt.download("dl", str(work)), "rb").read() == BODY
    assert _ranges(server) == [None]
    os.remove(work / "data.zip")
    (work / "data.zip.part").write_bytes(BODY[:40_000])
    assert open(mt.download("dl", str(work)), "rb").read() == BODY
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
    """The converter's datasets and the catalogue's layers name the same mirror folders, CRS, pixel size and
    origin (the tiles are read on the grid they were cut on)."""
    for name, sid in (("madeira", "madeira"), ("aosta", "aosta_valley")):
        spec, source = mt.DATASETS[name], src.SOURCES[sid]
        layer = source.nmt
        assert isinstance(layer, src.GridTiles) and layer.mirror == mt.tile_folder(spec)
        assert layer.crs == spec["crs"] == source.crs and layer.native_res == spec["res"] == source.default_resolution
        assert layer.origin == spec["origin"] == source.grid_origin and layer.tile_m == mt.TILE_M
        assert sk_tiles.TILE_M == 2000
