"""The ArcGIS ImageServer reader (sources/readers/imageserver.py, Esri's "Export Image") and its layer, against
real answers of ČÚZK's DMR 5G and DMP 1G recorded in tests/data/recorded/imageserver/cuzk/ (README there),
served by the local server; and the source czechia built on them."""

import io
import json
import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from http_server import Answer  # noqa: E402
from sources import net  # noqa: E402
from sources.layers.imageserver import ImageServerTiles  # noqa: E402
from sources.readers.imageserver import ImageServerReader, number, service_error  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CASSETTE = os.path.join(HERE, "data", "recorded", "imageserver", "cuzk")
SERVICES = "/arcgis2/rest/services"
# The recorded boxes: 16 x 16 px of 2 m at Adršpach on the grid of each model (DMR 5G: pixel edges at 0.4 and
# 1.88 m modulo 2; DMP 1G at 1.69 and 1.98), the same moved one pixel east, a box in Poland and one beyond the
# service's extent (west of it, in Bavaria)
FULL = (-615777.6, -1000282.12)
SHIFT = (-615775.6, -1000282.12)
DMP = (-615776.31, -1000282.02)
POLAND = (-559081.6, -990980.12)
BEYOND = (-915689.6, -1026214.12)


def _body(name: str) -> bytes:
    with open(os.path.join(CASSETTE, name), "rb") as f:
        return f.read()


def _values(body: bytes) -> np.ndarray:
    with rio.MemoryFile(body) as memfile, memfile.open() as raster:
        return raster.read(1)


@pytest.fixture
def server(http_server, monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    http_server.add_cassette(CASSETTE)
    return http_server


def _reader(server, origin, service="dmr5g", px=16, **kwargs) -> ImageServerReader:
    """A reader whose tile (2.0, 0, 0) is the 16 px box at origin."""
    return ImageServerReader("test", server.url(f"{SERVICES}/{service}/ImageServer"), "EPSG:5514", 2.0, px,
                             origin, **kwargs)


def _fetch(reader, tmp_path, tile=(2.0, 0, 0)):
    path = str(tmp_path / f"{tile[1]}_{tile[2]}.tif")
    fetched = reader.fetch(tile, path)
    return fetched, path


def test_numbers_are_written_exactly():
    assert number(-616000 + 0.4) == "-615999.6" and number(-1002000 + 1.88) == "-1001998.12"
    assert number(-613999.6 + 0.0) == "-613999.6" and number(2000.0) == "2000" and number(-0.0) == "0"
    assert number(-9999) == "-9999" and number(0.25) == "0.25"
    # A tile of 2 km with negative indexes (EPSG:5514's coordinates are negative) on DMR 5G's grid
    reader = ImageServerReader("t", "https://example/ImageServer/", "EPSG:5514", 2.0, 1000, (0.4, 1.88))
    left, bottom, right, top = reader.edges((2.0, -308, -501))
    assert dict(reader.export_params(left, bottom, right, top, 2.0)) == {
        "bbox": "-615999.6,-1001998.12,-613999.6,-999998.12", "bboxSR": "5514", "imageSR": "5514",
        "size": "1000,1000", "format": "tiff", "pixelType": "F32", "noData": "-9999",
        "interpolation": "RSP_NearestNeighbor", "compression": "LZ77", "f": "image"}
    assert reader.export_url == "https://example/ImageServer/exportImage"
    assert reader.url((2.0, -308, -501)) == "https://example/ImageServer"


def test_mosaic_rule_and_more_parameters():
    reader = ImageServerReader("t", "https://example/ImageServer", "EPSG:3161", 1.0, 1000, sr="102100",
                               mosaic_rule={"ascending": True}, lock_raster_ids=(7, 3),
                               params=(("renderingRule", '{"rasterFunction":"None"}'),))
    params = dict(reader.export_params(0, 0, 1000, 1000, 1.0))
    assert params["bboxSR"] == params["imageSR"] == "102100"
    assert params["mosaicRule"] == '{"ascending":true,"lockRasterIds":[7,3],"mosaicMethod":"esriMosaicLockRaster"}'
    assert params["renderingRule"] == '{"rasterFunction":"None"}' and params["f"] == "image"
    assert "mosaicRule" not in dict(ImageServerReader("t", "u", "EPSG:5514", 2.0, 10).export_params(0, 0, 20, 20, 2))


def test_the_service_keeps_its_pixels():
    """What the reader relies on, as the service answered (2026-11-02): on its own grid a box equals its two
    halves, and a box one pixel further east the same values one pixel further."""
    answers = {e["case"]: _values(_body(e["body"]))
               for e in json.load(open(os.path.join(CASSETTE, "answers.json"), encoding="utf-8"))["answers"]
               if e["body"].endswith(".tif")}
    assert np.array_equal(answers["full"], np.hstack([answers["left"], answers["right"]]))
    assert np.array_equal(answers["full"][:, 1:], answers["shift"][:, :-1])
    assert (answers["full"] > 500).all() and (answers["poland"] == -9999).all() and (answers["beyond"] == -9999).all()


def test_tile_exact_in_its_crs(server, tmp_path):
    """The tile holds the service's values exactly, on the pixels asked for, in EPSG:5514 (the answer names
    a LOCAL_CS); halves and a shifted tile agree with it."""
    fetched, path = _fetch(_reader(server, FULL), tmp_path)
    assert fetched.received == len(_body("002-full.tif"))
    with rio.open(path) as tile:
        values = tile.read(1)
        assert tile.crs.to_epsg() == 5514 and tile.transform == from_origin(FULL[0], FULL[1] + 32, 2, 2)
    assert np.array_equal(values, _values(_body("002-full.tif")))
    assert np.isfinite(values).all()
    _, shifted = _fetch(_reader(server, SHIFT), tmp_path / "shift")
    with rio.open(shifted) as tile:
        assert np.array_equal(values[:, 1:], tile.read(1)[:, :-1])
    # The halves through the reader's request
    reader = _reader(server, FULL)
    halves = [reader.export(FULL[0] + k * 16, FULL[1], FULL[0] + (k + 1) * 16, FULL[1] + 32, 2.0) for k in (0, 1)]
    assert np.array_equal(values, np.hstack([_values(h.content) for h in halves]))
    assert not server.stray()


def test_surface_model_on_its_own_grid(server, tmp_path):
    _, path = _fetch(_reader(server, DMP, "dmp1g"), tmp_path)
    with rio.open(path) as tile:
        assert tile.transform.c == pytest.approx(DMP[0]) and tile.transform.f == pytest.approx(DMP[1] + 32)
        assert np.array_equal(tile.read(1), _values(_body("006-dmp.tif")))


@pytest.mark.parametrize("origin", [POLAND, BEYOND])
def test_no_data_is_missing(server, tmp_path, origin):
    """All pixels at noData (outside the country, or beyond the service's extent): no file, nothing received."""
    fetched, path = _fetch(_reader(server, origin), tmp_path)
    assert fetched.received == 0 and not os.path.exists(path)


def test_error_with_status_200_is_never_data(server, tmp_path):
    """ArcGIS answers an error with HTTP 200 and the image's content type: an error, not retried when the
    request is wrong (code 400)."""
    reader = _reader(server, FULL)
    with pytest.raises(RuntimeError, match="exceeds the size limit"):
        reader.export(FULL[0], FULL[1], FULL[0] + 32, FULL[1] + 4101 * 2, 2.0)
    assert len(server.requests(f"{SERVICES}/dmr5g/ImageServer/exportImage")) == 1
    assert service_error(_body("009-too-high.json")) == (
        400, "400 Invalid or missing input parameters. The requested image exceeds the size limit.")
    # The same answer to a tile: no file
    error = _body("009-too-high.json")
    server.route(f"{SERVICES}/broken/", lambda request: Answer(200, error, {"Content-Type": "image/tiff"}))
    with pytest.raises(RuntimeError, match="tile 0_0: the service answered an error"):
        _fetch(_reader(server, FULL, "broken"), tmp_path)
    assert not list(tmp_path.iterdir())


def test_other_errors_are_asked_again(server, tmp_path):
    answers = [b'{"error":{"code":500,"message":"Error exporting image.","details":[]}}', _body("002-full.tif")]
    asked = []

    def answer(request):
        asked.append(request)
        return Answer(200, answers[min(len(asked), len(answers)) - 1], {"Content-Type": "image/tiff"})
    server.route(f"{SERVICES}/flaky/", answer)
    fetched, path = _fetch(_reader(server, FULL, "flaky"), tmp_path)
    assert len(asked) == 2 and os.path.exists(path)
    answers[1] = b"<html>busy</html>"
    with pytest.raises(RuntimeError, match="busy"):
        _fetch(_reader(server, FULL, "flaky"), tmp_path / "again")
    assert len(asked) == 2 + net.RETRIES


def _tiff(values: np.ndarray, left: float, top: float, res: float = 2.0, nodata=-9999.0) -> bytes:
    out = io.BytesIO()
    with rio.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=values.shape[1], height=values.shape[0], count=1,
                          dtype="float32", transform=from_origin(left, top, res, res), nodata=nodata) as dst:
            dst.write(values.astype(np.float32), 1)
        out.write(memfile.read())
    return out.getvalue()


def test_partial_tile_and_wrong_pixels(server, tmp_path):
    """Pixels at noData become NaN, the others stay exactly; an answer on other pixels than the tile's
    (another origin or size) is an error, never resampled."""
    values = np.arange(256, dtype=np.float32).reshape(16, 16) / 7 + 300
    values[:, :5] = -9999
    good = _tiff(values, FULL[0], FULL[1] + 32)
    off = _tiff(values, FULL[0] + 1, FULL[1] + 32)
    small = _tiff(values[:8], FULL[0], FULL[1] + 32)
    for name, body in (("good", good), ("off", off), ("small", small)):
        server.route(f"{SERVICES}/{name}/", lambda request, body=body: Answer(200, body, {"Content-Type": "image/tiff"}))
    _, path = _fetch(_reader(server, FULL, "good"), tmp_path)
    with rio.open(path) as tile:
        kept = tile.read(1)
    assert np.isnan(kept[:, :5]).all() and np.array_equal(kept[:, 5:], values[:, 5:])
    for name in ("off", "small"):
        with pytest.raises(RuntimeError, match="not the tile's 16 x 16 px"):
            _fetch(_reader(server, FULL, name), tmp_path / name)


def test_not_found_is_missing(server, tmp_path):
    server.route(f"{SERVICES}/gone/", lambda request: Answer(404, b"", {"Content-Type": "text/html"}))
    fetched, path = _fetch(_reader(server, FULL, "gone"), tmp_path)
    assert fetched.received == 0 and not os.path.exists(path)


def test_layer_tiles_and_paths(tmp_path):
    layer = ImageServerTiles("DMR 5G", "https://example/ImageServer", "EPSG:5514", "czechia/dmr5g/live", 2.0,
                             origin=(0.4, 1.88))
    path = layer.tile_path(str(tmp_path), (2.0, -308, -501))
    rel = os.path.relpath(path, tmp_path).replace(os.sep, "/")
    assert rel == "czechia/dmr5g/live/epsg5514-2m-1000px-tif-o0.4_1.88/-308_-501.tif"
    assert layer.tile_of(rel) == (2.0, -308, -501)
    assert layer.tile_url((2.0, -308, -501)) == "https://example/ImageServer"
    assert layer.bytes_per_tile() == 3e6 and layer.native_res == 2.0
    # The tiles are fetched at the service's resolution whatever the working grid's
    from grid import make_grid
    for res in (1.0, 2.0, 5.0):
        grid = make_grid((-615999.6, -1001998.12, -615000, -1001000), res, "EPSG:5514", (0.4, 1.88))
        assert {t[0] for t in layer.tiles(grid)} == {2.0}
        assert (2.0, -308, -501) in layer.tiles(grid)
