"""The reach of a fixed anchor in the 3D view (docs/3d-view-contract.md, "/api/reach"): search.reach_of_anchor on
the Żabi Koń clip against search.profile_of_line in both directions and every surface mode, the limits and the
lattice's switch, the meta and its framing, the errors, /api/reach of the local app with a real worker (offline:
local files), the quick lane's answer on the public site (Redact) and the warm-up (a reach compiles nothing)."""

import base64
import copy
import csv
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import zlib
from collections import Counter

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "tests", "data")
sys.path.insert(0, REPO)
import search  # noqa: E402

TIF = os.path.join(DATA, "zabi_kon_nmt.tif")
SURFACE_TIF = os.path.join(DATA, "zabi_kon_nmpt.tif")
TOKEN = "test-token"
LOCAL = "http://127.0.0.1:8765"
HEADER = {"x-findaline-reach": "1"}
META_KEYS = {"width", "height", "lattice", "res", "left", "top", "anchor", "as", "min_length", "max_length",
             "valid", "trees", "quantum", "sha256"}


def offline_env() -> dict:
    return {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}


@pytest.fixture(scope="module")
def clip_data(tmp_path_factory):
    """A data folder with a run of the clip (computed once, offline: the sag model, no surface model),
    its run.json and the busiest anchor of its lines with the other end of one of its lines: (data, meta,
    (lat, lon) of the anchor, (lat, lon) of the other end)."""
    import clip_runs  # the search once per session, this module's own copy
    data = clip_runs.data_copy(tmp_path_factory, "reach", [
        "--elevation-file", TIF, "--northing", "254608", "--easting", "553966",
        "--radius", "150", "--water", "off", "--fill-gaps", "off", "--no-plot", "--yes", "--ortho", "never",
        "--nmpt", "off", "--model", "sag"])
    run = next(d for d in os.listdir(data / "runs") if (data / "runs" / d / "run.json").is_file())
    meta = json.loads((data / "runs" / run / "run.json").read_text("utf-8"))
    with open(data / "runs" / run / "lines.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ends = Counter()
    for row in rows:
        ends[(row["anchor1_lat"], row["anchor1_lon"])] += 1
        ends[(row["anchor2_lat"], row["anchor2_lon"])] += 1
    (lat, lon), _ = ends.most_common(1)[0]
    row = next(r for r in rows if (lat, lon) in (
        (r["anchor1_lat"], r["anchor1_lon"]), (r["anchor2_lat"], r["anchor2_lon"])))
    end = ("anchor2_lat", "anchor2_lon") if (row["anchor1_lat"], row["anchor1_lon"]) == (lat, lon) else (
        "anchor1_lat", "anchor1_lon")
    return data, meta, (float(lat), float(lon)), (float(row[end[0]]), float(row[end[1]]))


def with_surface(meta: dict, mode: str) -> dict:
    """The run as if it had been searched with the clip's surface model (--nmpt mode) and the current obstacle rule."""
    import obstacles
    meta = copy.deepcopy(meta)
    meta["params"]["nmpt"] = mode
    meta["params"]["obstacles"] = dict(obstacles.RULE)
    meta["data"].append({"layer": "Surface file", "file": SURFACE_TIF})
    return meta


def paths_in(data, tmp_path, name="work"):
    paths = search.Paths(str(data), str(tmp_path / name))
    os.makedirs(paths.work, exist_ok=True)
    return paths


def mask_of(reach: dict, body: bytes) -> np.ndarray:
    return np.frombuffer(zlib.decompress(body), np.uint8).reshape(reach["height"], reach["width"])


def latlon_of(meta: dict, reach: dict, i: int, j: int):
    """The centre of the lattice sample (i, j) as (lat, lon)."""
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(meta["center"]["crs"], "EPSG:4326", always_xy=True).transform(
        reach["left"] + (j * reach["lattice"] + 0.5) * reach["res"],
        reach["top"] - (i * reach["lattice"] + 0.5) * reach["res"])
    return lat, lon


def grids(meta, data, tmp_path, a1, a2):
    """(terrain, the run's obstacle surface or None, the patch's plan) rebuilt as reach_of_anchor does."""
    paths = paths_in(data, tmp_path, "grids")
    plan, _, _ = search._patch_plan(meta, paths, a1, a2)
    plan.obstacles = meta["params"].get("obstacles")
    d = search.prepare_data(plan, statistics=False, shore="none")
    return np.array(d.elevation), None if d.surface is None else np.array(d.surface), plan


def pixel_of(plan, reach: dict):
    """The grid pixel (row, column) of the reach's fixed anchor."""
    return (round((plan.grid.top - reach["anchor"]["y"]) / reach["res"] - 0.5),
            round((reach["anchor"]["x"] - plan.grid.left) / reach["res"] - 0.5))


def candidate_mask(z: np.ndarray, fixed, p: dict) -> np.ndarray:
    """The pairs test of linesearch._pairs written out for every sample of the grid: the length within the run's
    limits and the heights differing by at most min(max_anchor_diff % of the length, max_anchor_diff_m)."""
    rr, cc = np.mgrid[0:z.shape[0], 0:z.shape[1]]
    length = np.hypot(rr - fixed[0], cc - fixed[1])
    with np.errstate(invalid="ignore"):
        return ((length <= p["max_length"]) & (length >= p["min_length"])
                & (np.abs(z - z[fixed]) <= np.minimum(p["max_anchor_diff"] / 100 * length, p["max_anchor_diff_m"])))


def with_ends(meta: dict) -> dict:
    """The run as if it had been searched with --end-zone 5 --anchor-lift 2."""
    meta = copy.deepcopy(meta)
    meta["params"].update(end_zone=5.0, anchor_lift=2.0)
    return meta


@pytest.mark.parametrize("mode", [None, "mark", "reject", "ends"])
@pytest.mark.parametrize("which", [1, 2])
def test_mask_equals_the_profiles(clip_data, tmp_path, mode, which):
    """For a sample of the lattice's targets the mask says what search.profile_of_line says of the line in the
    order the page asks it (which 1: the fixed point first, 2: the target first): valid exactly where the
    clearance over the terrain is above 0 (and, with --nmpt reject, the surface's too), the over-trees flag where
    the surface clearance is not, the clearance within the quantum; no target outside the limits is valid.
    "ends": a run with an end zone and A-frames, which both apply as the run's (more targets valid)."""
    data, meta, fixed, other = clip_data
    plain = meta
    meta = with_ends(meta) if mode == "ends" else with_surface(meta, mode) if mode else meta
    reach, body = search.reach_of_anchor(meta, paths_in(data, tmp_path), fixed, other, fixed, which)
    if mode == "ends":
        without, _ = search.reach_of_anchor(plain, paths_in(data, tmp_path, "plain"), fixed, other, fixed, which)
        assert reach["valid"] > without["valid"]
    mask = mask_of(reach, body)
    assert set(reach) == META_KEYS and reach["as"] == which and reach["lattice"] == 1
    assert mask.shape == (reach["height"], reach["width"]) == (1537, 1537)
    valid = np.argwhere(mask > 0)
    assert len(valid) == reach["valid"] and (mode == "reject" or len(valid) > 10)  # the clip's trees stand over nearly all
    assert int(((mask & 0x80) > 0).sum()) == reach["trees"]
    if mode == "mark":
        assert reach["trees"] > 0  # the sample must hold both kinds, or the flag is not tested
    if mode in (None, "ends"):
        assert reach["trees"] == 0 and not (mask & 0x80).any()

    z, _, plan = grids(meta, data, tmp_path, fixed, other)
    fi, fj = pixel_of(plan, reach)
    rng = np.random.default_rng(3)
    ours = [tuple(valid[k]) for k in rng.choice(len(valid), size=min(5, len(valid)), replace=False)]
    # targets within the run's limits that are no valid line (the profile says so too)
    blocked = np.argwhere(candidate_mask(z, (fi, fj), meta["params"]) & (mask == 0))
    zeros = [tuple(blocked[k]) for k in rng.choice(len(blocked), size=5, replace=False)]
    for i, j in ours + zeros:
        target = latlon_of(meta, reach, i, j)
        a, b = (fixed, target) if which == 1 else (target, fixed)
        profile = search.profile_of_line(meta, paths_in(data, tmp_path, f"p{i}-{j}"), a, b)
        clearance = profile["min"][1]
        surface = profile["min_nmpt"][1] if profile["min_nmpt"] else None
        expected = clearance > 0 and not (mode == "reject" and surface is not None and surface <= 0)
        value = int(mask[i, j])
        assert (value > 0) == expected, ((i, j), value, profile["min"], profile["min_nmpt"])
        if expected:
            assert bool(value & 0x80) == (mode == "mark" and surface is not None and surface <= 0)
            assert abs((value & 0x7F) * reach["quantum"] - clearance) <= reach["quantum"] + 0.01
            assert (value & 0x7F) * reach["quantum"] >= clearance - 0.01  # rounded up
    # No valid sample outside the run's limits of length
    lengths = np.hypot(valid[:, 0] - fi, valid[:, 1] - fj) * reach["res"]
    assert (lengths >= meta["params"]["min_length"]).all() and (lengths <= meta["params"]["max_length"]).all()


def test_limits_lattice_and_meta(clip_data, tmp_path, monkeypatch):
    """The targets are the pairs linesearch._pairs would test (length and height difference, never a sample
    without data); the lattice is 1 up to REACH_FULL_TARGETS targets and 2 above, its values the same samples'
    of the full one; the meta's fields and counts."""
    data, meta, fixed, other = clip_data
    meta = with_surface(meta, "mark")
    paths = paths_in(data, tmp_path)
    full, body = search.reach_of_anchor(meta, paths, fixed, other, fixed, 1)
    mask1 = mask_of(full, body)
    z, _, plan = grids(meta, data, tmp_path, fixed, other)
    p = meta["params"]
    row, col = pixel_of(plan, full)
    candidates = candidate_mask(z, (row, col), p)
    assert not (mask1 > 0)[~candidates].any()
    found = sum(len(r) for r, _ in search._reach_candidates(
        z, 1.0, (row, col), 1, p["min_length"], p["max_length"], p["max_anchor_diff"] / 100, p["max_anchor_diff_m"]))
    assert found == int(candidates.sum()) > 1000
    assert (full["anchor"]["x"], full["anchor"]["y"]) == (plan.grid.left + (col + 0.5), plan.grid.top - (row + 0.5))
    assert full["anchor"]["h"] == round(float(z[row, col]), 2)
    assert full["min_length"] == p["min_length"] and full["max_length"] == p["max_length"]
    assert full["quantum"] == 0.5 and full["res"] == 1.0 and (full["left"], full["top"]) == (plan.grid.left, plan.grid.top)

    # The boundary: exactly REACH_FULL_TARGETS candidates still make the full lattice, one fewer every second sample
    monkeypatch.setattr(search, "REACH_FULL_TARGETS", found)
    assert search.reach_of_anchor(meta, paths_in(data, tmp_path, "w2"), fixed, other, fixed, 1)[0]["lattice"] == 1
    monkeypatch.setattr(search, "REACH_FULL_TARGETS", found - 1)
    half, body2 = search.reach_of_anchor(meta, paths_in(data, tmp_path, "w3"), fixed, other, fixed, 1)
    mask2 = mask_of(half, body2)
    assert half["lattice"] == 2 and (half["width"], half["height"]) == (769, 769)
    assert (half["left"], half["top"], half["res"]) == (full["left"], full["top"], 1.0)
    assert np.array_equal(mask2, mask1[::2, ::2])  # value (i, j) is the patch's sample (2i, 2j)
    assert half["valid"] == int((mask2 > 0).sum()) < full["valid"]


def test_reach_errors(clip_data, tmp_path):
    """A point outside the patch or over no data is reach_anchor; as is 1 or 2."""
    data, meta, fixed, other = clip_data
    paths = paths_in(data, tmp_path)
    reach, _ = search.reach_of_anchor(meta, paths, fixed, other, fixed, 1)
    corner = latlon_of(meta, reach, 0, 0)  # inside the patch, outside the clip
    for point in (corner, (fixed[0] + 1, fixed[1]), (0.0, 0.0)):
        with pytest.raises(search.SearchError) as error:
            search.reach_of_anchor(meta, paths_in(data, tmp_path, "e"), fixed, other, point, 1)
        assert error.value.code == "reach_anchor"
    with pytest.raises(ValueError):
        search.reach_of_anchor(meta, paths, fixed, other, fixed, 3)
    with pytest.raises(search.SearchError) as error:
        search.reach_of_anchor(meta, paths, fixed, other, fixed, 1, side_m=search.MAX_MEASURED_PX * 1.0)
    assert error.value.code == "patch_too_large"


def test_reach_framing_and_redact(clip_data, tmp_path):
    """web.patch_body frames the reach as the patch (uint32 N, the meta, the deflated values) after checking the
    sha256; the public site's Redact leaves the mask alone."""
    import web
    from jobs import Jobs
    data, meta, fixed, other = clip_data
    reach, body = search.reach_of_anchor(meta, paths_in(data, tmp_path), fixed, other, fixed, 2)
    assert reach["sha256"] == hashlib.sha256(body).hexdigest()
    text = base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")
    framed = web.patch_body({"meta": reach, "mask": text}, "mask")
    n = struct.unpack("<I", framed[:4])[0]
    assert json.loads(framed[4:4 + n]) == reach and framed[4 + n:] == body
    bad = base64.urlsafe_b64encode(body[:-1] + bytes([body[-1] ^ 1])).rstrip(b"=").decode("ascii")
    with pytest.raises(Exception) as error:
        web.patch_body({"meta": reach, "mask": bad}, "mask")
    assert "patch_damaged" in str(error.value.detail)

    jobs = Jobs(str(tmp_path), public=True)
    secret = "AAAAC:/" + str(tmp_path).replace("\\", "/") + "BBBB_-"
    task = jobs.quick_add("reach", {"run": "x"}, 7)
    assert jobs.quick_claim("w")["id"] == task
    jobs.quick_answer(task, 200, {"meta": {"note": str(tmp_path), "sha256": "x"}, "mask": secret})
    answer = jobs.quick_take(task)
    assert answer["body"]["mask"] == secret and str(tmp_path) not in json.dumps(answer["body"]["meta"])


def test_api_reach_of_the_local_app(clip_data, tmp_path, monkeypatch):
    """/api/reach through the worker's quick lane: the header, the numbers, `as`, the anchor, another run; the
    binary answer equals reach_of_anchor's; /api/patch is as before and takes part=canopy only."""
    import web
    from fastapi.testclient import TestClient
    data, meta, fixed, other = clip_data
    for key, value in offline_env().items():
        monkeypatch.setenv(key, value)
    line = ",".join(f"{v:.7f}" for v in (*fixed, *other))
    anchor = f"{fixed[0]:.7f},{fixed[1]:.7f}"
    url = f"/api/reach?run={meta['id']}&line={line}&anchor={anchor}"
    app = web.create_app(str(data), token=TOKEN)
    with TestClient(app, base_url=LOCAL) as client:
        assert client.get(f"{url}&as=1").status_code == 403  # header needed
        assert client.get(f"{url}&as=1", headers={"x-findaline-patch": "1"}).status_code == 403
        wrong = client.get(f"/api/reach?run={meta['id']}&line=1,2,3&anchor={anchor}&as=1", headers=HEADER)
        assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "patch_line"
        assert client.get(f"{url}&as=3", headers=HEADER).status_code == 400
        assert client.get(url, headers=HEADER).status_code == 400  # no `as`
        assert client.get(f"{url}&as=1&step=3", headers=HEADER).status_code == 400
        for bad in ("1", "1,nan", "a,b", "1,2,3"):
            answer = client.get(f"/api/reach?run={meta['id']}&line={line}&anchor={bad}&as=1", headers=HEADER)
            assert answer.status_code == 400 and answer.json()["detail"]["code"] == "reach_anchor", bad
        assert client.get(f"/api/reach?run=..&line={line}&anchor={anchor}&as=1", headers=HEADER).status_code == 404
        far = client.get(f"/api/reach?run={meta['id']}&line={line}&anchor=0,0&as=1", headers=HEADER)  # the worker's check
        assert far.status_code == 400 and far.json()["detail"]["code"] == "reach_anchor"

        answer = client.get(f"{url}&as=2&step=2", headers=HEADER)
        assert answer.status_code == 200, answer.text
        assert answer.headers["content-type"] == "application/octet-stream" and answer.headers["cache-control"] == "no-store"
        n = struct.unpack("<I", answer.content[:4])[0]
        got = json.loads(answer.content[4:4 + n].decode("utf-8"))
        direct, body = search.reach_of_anchor(meta, paths_in(data, tmp_path), tuple(map(float, line.split(",")[:2])),
                                              tuple(map(float, line.split(",")[2:])), tuple(map(float, anchor.split(","))), 2)
        assert got == json.loads(json.dumps(direct)) and answer.content[4 + n:] == body

        # The plain patch is as before; only part=canopy is another part
        plain = client.get(f"/api/patch?run={meta['id']}&line={line}&step=2", headers={"x-findaline-patch": "1"})
        assert plain.status_code == 200
        n = struct.unpack("<I", plain.content[:4])[0]
        patch, heights = search.patch_of_line(meta, paths_in(data, tmp_path, "pw"), tuple(map(float, line.split(",")[:2])),
                                              tuple(map(float, line.split(",")[2:])), step=2)
        assert json.loads(plain.content[4:4 + n].decode("utf-8")) == json.loads(json.dumps(patch))
        assert plain.content[4 + n:] == heights
        other_part = client.get(f"/api/patch?run={meta['id']}&line={line}&part=roof", headers={"x-findaline-patch": "1"})
        assert other_part.status_code == 400


def test_a_reach_after_the_warm_up_compiles_nothing(clip_data, tmp_path):
    """warmup.warm_up compiles every kernel a reach uses (the public worker's numba cache is a tmpfs, rebuilt
    after every start of its container): afterwards a reach with and without a surface model compiles nothing
    (no new file in numba's cache, NUMBA_CACHE_DIR as on the public site), and the quick lane's process holds
    numba only after the first one."""
    import glob
    data, meta, fixed, other = clip_data
    numba_dir = tmp_path / "numba"
    env = {**offline_env(), "NUMBA_CACHE_DIR": str(numba_dir)}
    result = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {REPO!r}); import warmup; "
                                                   f"warmup.warm_up({str(tmp_path / 'warm')!r})"],
                            capture_output=True, text=True, encoding="utf-8", timeout=900, env=env)
    assert result.returncode == 0 and "warm-up failed" not in result.stderr, result.stdout + result.stderr
    compiled = lambda: {os.path.basename(p) for p in glob.glob(str(numba_dir / "**" / "*.nbc"), recursive=True)}  # noqa: E731
    before = compiled()
    meta_file = tmp_path / "meta.json"
    meta_file.write_text(json.dumps({"plain": meta, "surface": with_surface(meta, "mark")}), "utf-8")
    code = f"""
import json, os, sys
sys.path.insert(0, {REPO!r})
import search
metas = json.loads(open({str(meta_file)!r}, encoding="utf-8").read())
numba_before = 'numba' in sys.modules
for k, (name, meta) in enumerate(metas.items()):
    paths = search.Paths({str(data)!r}, {str(tmp_path / "work")!r} + str(k))
    os.makedirs(paths.work)
    search.reach_of_anchor(meta, paths, {fixed!r}, {other!r}, {fixed!r}, 1 + k)
print(json.dumps([numba_before, 'numba' in sys.modules]))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
                            timeout=900, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [False, True]
    assert compiled() == before, sorted(compiled() - before)
