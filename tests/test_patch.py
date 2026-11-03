"""The terrain of the 3D view (docs/3d-view-contract.md): search.patch_of_line on the Żabi Koń clip,
the encoder against the recorded patch, the quick lane's answer on the public site (Redact) and
/api/patch and /view3d of the local app with a real worker (offline: local files)."""

import importlib.util
import json
import math
import os
import struct
import sys
import zlib

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "tests", "data")
sys.path.insert(0, REPO)
import search  # noqa: E402

TIF = os.path.join(DATA, "zabi_kon_nmt.tif")
# The clip (EPSG:2180, 1 m): pixel (0, 0) has its top left corner here
CLIP_LEFT, CLIP_TOP, CLIP_SIZE = 553665.5, 254908.5, 600
TOKEN = "test-token"
LOCAL = "http://127.0.0.1:8765"


def _fixture():
    spec = importlib.util.spec_from_file_location("make_patch_fixture", os.path.join(DATA, "make_patch_fixture.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REFERENCE = _fixture()


def _clip() -> np.ndarray:
    import rasterio as rio
    with rio.open(TIF) as src:
        return src.read(1).astype(np.float64)


def _offline_env() -> dict:
    return {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "",
            "PYTHONIOENCODING": "utf-8"}


@pytest.fixture(scope="module")
def clip_data(tmp_path_factory):
    """A data folder with a run of the clip (computed once, offline) and its run.json."""
    import subprocess
    data = tmp_path_factory.mktemp("patch")
    result = subprocess.run(
        [sys.executable, "findaline.py", "--elevation-file", TIF, "--northing", "254608", "--easting", "553966",
         "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
         "--nmpt", "off", "--model", "sag", "--data-dir", str(data)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=600, env=_offline_env())
    assert result.returncode == 0, result.stdout + result.stderr
    run = next(d for d in os.listdir(data / "runs") if (data / "runs" / d / "run.json").is_file())
    meta = json.loads((data / "runs" / run / "run.json").read_text("utf-8"))
    return data, meta


def _latlon(x: float, y: float):
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform(x, y)
    return lat, lon


def _patch(clip_data, tmp_path, xy1, xy2, **kwargs):
    data, meta = clip_data
    paths = search.Paths(str(data), str(tmp_path / "work"))
    os.makedirs(paths.work)
    return search.patch_of_line(meta, paths, _latlon(*xy1), _latlon(*xy2), **kwargs)


# The clip's pixel (256, 256) has its centre here: a line of 100 m centred on it, a patch of 513 x 513
# samples (side 500 m) is the clip's first 513 rows and columns, the window of the recorded patch
MIDDLE = (CLIP_LEFT + 256.5, CLIP_TOP - 256.5)
LINE = ((MIDDLE[0] - 50, MIDDLE[1]), (MIDDLE[0] + 50, MIDDLE[1]))


def test_encoder_matches_the_reference():
    """The production encoder gives the recorded patch's values (its deflated bytes may differ)."""
    with open(os.path.join(DATA, "patch_zabi_kon.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    heights = _clip()[:513, :513]
    heights[-16:, -16:] = np.nan
    body, base_dm = search.encode_heights(heights.astype(np.float32))
    assert base_dm == recorded["base_dm"]
    values = REFERENCE.decode_values(body, 513, 513)
    assert REFERENCE.values_sha256(values) == recorded["values_sha256"]
    with open(os.path.join(DATA, "patch_zabi_kon.bin"), "rb") as f:
        assert np.array_equal(REFERENCE.decode_values(f.read(), 513, 513), values)
    with pytest.raises(search.SearchError) as error:
        search.encode_heights(np.array([[0.0, 3276.8]]))
    assert error.value.code == "patch_relief"
    search.encode_heights(np.array([[0.0, 3276.7]]))  # just within
    with pytest.raises(search.SearchError) as error:
        search.encode_heights(np.full((3, 3), np.nan))
    assert error.value.code == "patch_no_data"


def test_patch_heights_are_the_clips(clip_data, tmp_path):
    """The patch's heights are the clip's DEM within 0.05 m, on its pixels; the meta as the contract has it."""
    from pyproj import Transformer
    data, meta = clip_data
    patch, body = _patch(clip_data, tmp_path, *LINE, side_m=500)
    clip = _clip()
    assert (patch["width"], patch["height"], patch["step"], patch["res"]) == (513, 513, 1, 1.0)
    assert (patch["left"], patch["top"]) == (CLIP_LEFT, CLIP_TOP) and patch["crs"] == meta["center"]["crs"]
    heights = REFERENCE.decode(body, 513, 513, patch["base_dm"])
    window = clip[:513, :513]
    assert np.isfinite(window).all() and np.isfinite(heights).all()
    assert np.abs(heights - window).max() <= 0.05 + 1e-9
    import hashlib
    assert patch["sha256"] == hashlib.sha256(body).hexdigest()
    assert patch["base_dm"] == math.floor(window.min() * 10)
    (a1, a2) = patch["anchors"]
    assert (a1["x"], a1["y"], a2["x"], a2["y"]) == (*LINE[0], *LINE[1])
    assert a1["h"] == round(float(clip[256, 206]), 2) and a2["h"] == round(float(clip[256, 306]), 2)
    # The affine of the grid metres to lon/lat: pyproj's within 5e-7° (5 cm) over this patch of 513 m (a
    # plane cannot follow the projection's curvature: about 2 cm at its corners, growing with the side squared)
    a0, a_x, a_y, b0, b_x, b_y = patch["affine"]
    to_lonlat = Transformer.from_crs(patch["crs"], "EPSG:4326", always_xy=True).transform
    for x, y in ((CLIP_LEFT, CLIP_TOP), (*MIDDLE,), (CLIP_LEFT + 513, CLIP_TOP - 513)):
        lon, lat = to_lonlat(x, y)
        assert abs(a0 + a_x * x + a_y * y - lon) < 5e-7 and abs(b0 + b_x * x + b_y * y - lat) < 5e-7
    assert patch["rigging"] == meta["params"]["rigging"] and patch["model"] == "sag"
    assert patch["ortho"] is None and patch["attribution"] == meta["attribution"]  # local files: no orthophoto
    json.dumps(patch, allow_nan=False)  # plain JSON

    # Every second sample from the first: the outer edges half a pixel out
    half, small = _patch(clip_data, tmp_path / "2", *LINE, side_m=500, step=2)
    assert (half["width"], half["height"], half["res"]) == (257, 257, 2.0)
    assert (half["left"], half["top"]) == (CLIP_LEFT - 0.5, CLIP_TOP + 0.5)
    assert np.abs(REFERENCE.decode(small, 257, 257, half["base_dm"]) - window[::2, ::2]).max() <= 0.05 + 1e-9
    assert half["anchors"] == patch["anchors"]


def test_patch_without_data_outside_the_clip(clip_data, tmp_path):
    """Samples outside the clip have no data; inside they are the clip's. The default side and its refusals."""
    near = (CLIP_LEFT + 100.5, CLIP_TOP - 100.5)
    patch, body = _patch(clip_data, tmp_path, near, (near[0] + 20, near[1]), side_m=1000)  # 1025 samples
    assert patch["width"] == patch["height"] == 1025
    heights = REFERENCE.decode(body, 1025, 1025, patch["base_dm"])
    col = int(round(CLIP_LEFT - patch["left"]))
    row = int(round(patch["top"] - CLIP_TOP))
    inside = np.zeros(heights.shape, bool)
    inside[row:row + CLIP_SIZE, col:col + CLIP_SIZE] = True
    assert np.isnan(heights[~inside]).all() and np.isfinite(heights[inside]).all()
    assert np.abs(heights[inside].reshape(CLIP_SIZE, CLIP_SIZE) - _clip()).max() <= 0.05 + 1e-9

    data, meta = clip_data
    paths = search.Paths(str(data), str(tmp_path / "w"))
    os.makedirs(paths.work)
    a1, a2 = _latlon(*LINE[0]), _latlon(*LINE[1])
    with pytest.raises(search.SearchError) as error:
        search.patch_of_line(meta, paths, a1, a2, side_m=search.MAX_MEASURED_PX * 1.0)  # 6145 samples
    assert error.value.code == "patch_too_large" and error.value.params == {"km": 6.0, "max": 6.0}
    far = _latlon(LINE[0][0] + 5000, LINE[0][1])
    with pytest.raises(search.SearchError) as error:
        search.patch_of_line(meta, paths, far, _latlon(LINE[0][0] + 5100, LINE[0][1]), side_m=500)
    assert error.value.code == "patch_no_data"
    with pytest.raises(search.SearchError) as error:  # the run's CRS is not the one a search there takes
        search.patch_of_line({**meta, "center": {**meta["center"], "crs": "EPSG:32634"}}, paths, a1, a2, side_m=500)
    assert error.value.code == "patch_crs"
    with pytest.raises(ValueError):
        search.patch_of_line(meta, paths, a1, a2, step=3)


def test_patch_loads_no_numba(clip_data, tmp_path):
    """The quick lane never loads numba (tests/test_units.py::test_search_imports_numba_only_to_compute):
    the patch of a line neither."""
    import subprocess
    data, meta = clip_data
    (tmp_path / "meta.json").write_text(json.dumps(meta), "utf-8")
    code = f"""
import json, os, sys
sys.path.insert(0, {REPO!r})
import search
paths = search.Paths({str(data)!r}, {str(tmp_path / "work")!r})
os.makedirs(paths.work)
meta = json.loads(open({str(tmp_path / "meta.json")!r}, encoding="utf-8").read())
search.patch_of_line(meta, paths, {_latlon(*LINE[0])!r}, {_latlon(*LINE[1])!r}, side_m=500)
print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in
                        ('numba', 'llvmlite', 'linesearch', 'lineprofiles', 'terrain', 'grouping'))))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
                            timeout=600, env=_offline_env())
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_redact_leaves_the_heights_alone(tmp_path, monkeypatch):
    """On the public site the quick lane's answers are redacted, but not the heights: a substring that
    looks like a service key or a path survives there (the web checks their sha256), not in the meta."""
    from jobs import Jobs
    monkeypatch.setenv("OPENTOPOGRAPHY_API_KEY", "Secret4Key")
    heights = "AAAASecret4KeyBBBB_-C:" + str(tmp_path).replace("\\", "/")
    jobs = Jobs(str(tmp_path), public=True)
    task = jobs.quick_add("patch", {"run": "x"}, 7)
    assert jobs.quick_claim("w")["id"] == task
    jobs.quick_answer(task, 200, {"meta": {"note": "key Secret4Key", "sha256": "x"}, "heights": heights})
    answer = jobs.quick_take(task)
    assert answer["body"]["heights"] == heights
    assert "Secret4Key" not in json.dumps(answer["body"]["meta"])


def test_patch_and_view3d_of_the_local_app(clip_data, tmp_path, monkeypatch):
    """/api/patch through the worker's quick lane: the header, the line, the step, another run; the
    binary answer (N, the meta, the heights that its sha256 names) equals patch_of_line's. /view3d."""
    import web
    from fastapi.testclient import TestClient
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    line = ",".join(f"{v:.7f}" for v in (*_latlon(*LINE[0]), *_latlon(*LINE[1])))
    app = web.create_app(str(data), token=TOKEN)
    header = {"x-findaline-patch": "1"}
    with TestClient(app, base_url=LOCAL) as client:
        assert client.get(f"/api/patch?run={meta['id']}&line={line}").status_code == 403  # header needed
        wrong = client.get(f"/api/patch?run={meta['id']}&line=1,2,3", headers=header)
        assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "patch_line"
        assert client.get(f"/api/patch?run={meta['id']}&line=1,2,3,nan", headers=header).status_code == 400
        assert client.get(f"/api/patch?run={meta['id']}&line={line}&step=3", headers=header).status_code == 400
        assert client.get(f"/api/patch?run=..&line={line}", headers=header).status_code == 404
        answer = client.get(f"/api/patch?run={meta['id']}&line={line}&step=2", headers=header)
        assert answer.status_code == 200, answer.text
        assert answer.headers["content-type"] == "application/octet-stream"
        assert answer.headers["cache-control"] == "no-store"
        n = struct.unpack("<I", answer.content[:4])[0]
        patch = json.loads(answer.content[4:4 + n].decode("utf-8"))
        body = answer.content[4 + n:]
        import hashlib
        assert hashlib.sha256(body).hexdigest() == patch["sha256"]
        assert patch["step"] == 2 and patch["width"] == patch["height"] == 769  # 1537 samples of 1 m, halved
        heights = REFERENCE.decode(body, 769, 769, patch["base_dm"])
        # The patch reaches 768 pixels on each side of the clip's pixel 256: 512 pixels before the clip
        assert (CLIP_LEFT - (patch["left"] + 0.5), patch["top"] - 0.5 - CLIP_TOP) == (512, 512)
        assert np.abs(heights[256:556, 256:556] - _clip()[::2, ::2]).max() <= 0.05 + 1e-9
        assert np.isnan(heights[:256]).all() and np.isnan(heights[556:]).all()
        assert zlib.decompress(body) and np.isnan(heights[0, 0])

        page = client.get("/view3d")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        assert page.headers["content-security-policy"] == web.PAGE_CSP["/view3d"]
        assert '<meta name="findaline-3d-ring" content="off">' in page.text and TOKEN not in page.text
        assert '<div id="view3d" class="ui"></div>' in page.text and "/app/view3d.js" in page.text
        assert client.get("/").headers["content-security-policy"] == web.SECURITY_HEADERS["Content-Security-Policy"]
