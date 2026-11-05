"""The trees and buildings of the 3D view (docs/3d-view-contract.md, "The block of trees and buildings"):
search.canopy_of_line on the Żabi Koń clip with its surface model against obstacles.obstacle_surface, at step 1
and 2, the run without a rule, a run without a surface model, and GET /api/patch?part=canopy of the local app."""

import base64
import hashlib
import json
import os
import shutil
import struct
import sys
import zlib

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import search  # noqa: E402
from test_reach import TOKEN, LOCAL, clip_data, offline_env, paths_in, with_surface  # noqa: E402,F401

HEADER = {"x-findaline-patch": "1"}
META_KEYS = {"part", "width", "height", "step", "res", "left", "top", "quantum", "min_height", "rule", "cells",
             "sha256"}


def values_of(meta: dict, body: bytes) -> np.ndarray:
    return np.frombuffer(zlib.decompress(body), np.uint8).reshape(meta["height"], meta["width"])


def expected(meta, data, tmp_path, a1, a2, rule):
    """The obstacle surface less the terrain from obstacles.obstacle_surface on the raw surface of the patch's grid."""
    import obstacles
    paths = paths_in(data, tmp_path, "expected")
    plan, _, _ = search._patch_plan(meta, paths, a1, a2)
    plan.obstacles = None  # the raw surface model
    d = search.prepare_data(plan, statistics=False, shore="none")
    z, s = np.array(d.elevation, dtype=np.float32), np.array(d.surface, dtype=np.float32)
    surface = obstacles.obstacle_surface(z, s, plan.resolution, **rule) if rule else s
    with np.errstate(invalid="ignore"):
        height = surface.astype(np.float64) - z.astype(np.float64)
        height = np.where(height >= 1.0, np.minimum(np.rint(height / 0.5), 255), 0)
    return np.nan_to_num(height).astype(np.uint8), z, s


@pytest.mark.parametrize("step", [1, 2])
def test_canopy_is_the_obstacle_surface_less_the_terrain(clip_data, tmp_path, step):
    """The values are the run's obstacle surface less the terrain in steps of 0.5 m (0 below 1 m and over no
    data), on the patch's grid of that step; the meta as the contract has it, the patch's own extent."""
    import obstacles
    data, meta, a1, a2 = clip_data
    meta = with_surface(meta, "mark")
    canopy, body = search.canopy_of_line(meta, paths_in(data, tmp_path), a1, a2, step)
    assert set(canopy) == META_KEYS and canopy["part"] == "canopy" and canopy["step"] == step
    values = values_of(canopy, body)
    want, z, s = expected(meta, data, tmp_path, a1, a2, dict(obstacles.RULE))
    assert np.array_equal(values, want[::step, ::step])
    assert canopy["rule"] == obstacles.RULE and canopy["quantum"] == 0.5 and canopy["min_height"] == 1
    assert canopy["cells"] == int((values > 0).sum()) > 1000 and canopy["sha256"] == hashlib.sha256(body).hexdigest()
    assert values.max() > 2 and (values[values > 0] >= 2).all()  # at least 1 m: 2 steps
    # Trees: where the canopy is, the surface stands above the terrain; no data (outside the clip) gives 0
    outside = np.isnan(z[::step, ::step])
    assert outside.any() and not values[outside].any()
    assert (s[::step, ::step][values > 0] > z[::step, ::step][values > 0]).all()
    # The patch of the same request has the same grid
    patch, _ = search.patch_of_line(meta, paths_in(data, tmp_path, "patch"), a1, a2, step=step)
    for key in ("width", "height", "step", "res", "left", "top"):
        assert canopy[key] == patch[key], key
    json.dumps(canopy, allow_nan=False)


def test_canopy_without_a_rule_is_the_surface_model(clip_data, tmp_path):
    """A run from before the obstacle rule (params.obstacles null): the surface model as it is, less the terrain."""
    data, clip, a1, a2 = clip_data
    meta = with_surface(clip, "mark")
    meta["params"]["obstacles"] = None
    canopy, body = search.canopy_of_line(meta, paths_in(data, tmp_path), a1, a2)
    want, _, _ = expected(meta, data, tmp_path, a1, a2, None)
    assert canopy["rule"] is None and np.array_equal(values_of(canopy, body), want)
    with_rule, _ = search.canopy_of_line(with_surface(clip, "mark"), paths_in(data, tmp_path, "rule"), a1, a2)
    assert 0 < with_rule["cells"] < canopy["cells"]  # the rule takes the terrain's own rock out


def test_canopy_needs_a_surface_model(clip_data, tmp_path):
    """A run without a surface model (--nmpt off): patch_no_surface, before any grid is built."""
    data, meta, a1, a2 = clip_data
    with pytest.raises(search.SearchError) as error:
        search.canopy_of_line(meta, paths_in(data, tmp_path), a1, a2)
    assert error.value.code == "patch_no_surface"
    with pytest.raises(ValueError):
        search.canopy_of_line(with_surface(meta, "mark"), paths_in(data, tmp_path, "w"), a1, a2, step=3)


def test_api_patch_canopy_of_the_local_app(clip_data, tmp_path, monkeypatch):
    """/api/patch?part=canopy through the worker's quick lane: the patch's header and numbers, the framing with
    the sha256 checked, the answer equal to canopy_of_line's; a run without a surface model 400 patch_no_surface;
    the plain patch unchanged."""
    import web
    from fastapi.testclient import TestClient
    data, meta, a1, a2 = clip_data
    for key, value in offline_env().items():
        monkeypatch.setenv(key, value)
    with_trees = with_surface(meta, "mark")
    with_trees["id"] = "with-trees"
    folder = data / "runs" / "with-trees"
    os.makedirs(folder)
    (folder / "run.json").write_text(json.dumps(with_trees), "utf-8")
    line = ",".join(f"{v:.7f}" for v in (*a1, *a2))
    app = web.create_app(str(data), token=TOKEN)
    with TestClient(app, base_url=LOCAL) as client:
        url = f"/api/patch?run=with-trees&line={line}&part=canopy"
        assert client.get(url).status_code == 403  # the patch's header
        assert client.get(url + "&step=3", headers=HEADER).status_code == 400
        answer = client.get(url + "&step=2", headers=HEADER)
        assert answer.status_code == 200, answer.text
        assert answer.headers["content-type"] == "application/octet-stream"
        n = struct.unpack("<I", answer.content[:4])[0]
        got = json.loads(answer.content[4:4 + n].decode("utf-8"))
        direct, body = search.canopy_of_line(with_trees, paths_in(data, tmp_path), a1, a2, 2)
        assert got == json.loads(json.dumps(direct)) and answer.content[4 + n:] == body
        assert hashlib.sha256(answer.content[4 + n:]).hexdigest() == got["sha256"] and got["part"] == "canopy"
        none = client.get(f"/api/patch?run={meta['id']}&line={line}&part=canopy", headers=HEADER)
        assert none.status_code == 400 and none.json()["detail"]["code"] == "patch_no_surface"
        plain = client.get(f"/api/patch?run=with-trees&line={line}&step=2", headers=HEADER)
        assert plain.status_code == 200
        n = struct.unpack("<I", plain.content[:4])[0]
        patch = json.loads(plain.content[4:4 + n].decode("utf-8"))
        assert "part" not in patch and patch["sha256"] == hashlib.sha256(plain.content[4 + n:]).hexdigest()
    shutil.rmtree(folder)
    framed = web.patch_body({"meta": direct, "heights": base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")})
    assert framed[4 + struct.unpack("<I", framed[:4])[0]:] == body
