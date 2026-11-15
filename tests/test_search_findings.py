"""Phase 4's findings of the line-volume task (docs/line-volume/spec.md section 7), fixed: an unfinished tiled
sag job resumes after migration 17 of jobs.sqlite (search._search_keys), the funnel counts of a search the square
rule's early check stops, and the truth analysis' reason for a known line the square rule dropped."""

import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jobs as jb  # noqa: E402
import params as pm  # noqa: E402
import search  # noqa: E402

AREA = {"area": "coast", "within": "osm:Gozo"}  # no file path: the hashes hold in every checkout
CLI = ["--area", "coast", "--within", "osm:Gozo"]

# The hashes of main c8a079a (before the fix), web requests as the worker reads them (jobs.search_params of the
# stored JSON), command-line ones from params.parse_cli; source geoportal, resolution 2 m. The fix moves none.
WEB = {"sag, fall_zone 3": ({"model": "sag", "fall_zone": 3}, "829cd2e55c16a9e7", "ea8791ac80a2a352"),
       "sag, fall_zone 4.5": ({"model": "sag", "fall_zone": 4.5}, "55135368e473d7c0", "967a6a8e3d9b8d40"),
       "sag, default (6 m)": ({"model": "sag"}, None, None),
       "formula": ({}, "c2815824f4b9a796", "08f4bceb300b72ac"),
       "formula, fall_zone 3": ({"fall_zone": 3}, "6630d85d9cde2074", "ef1b56f1a7a21d06")}
COMMAND_LINE = {"sag --fall-zone 3": (["--model", "sag", "--fall-zone", "3"], "173c1c5395ba26b5", "a6dfefeb63327a5f"),
                "sag": (["--model", "sag"], "ed4f6442b52e1d6b", "355dd0484e2e5500"),
                "formula": ([], "31c28f8c91eecd44", "7e6ddbb80feb7f39")}
# A web sag request without a fall zone, hashed before migration 17 (8c6fccc~1, the default's int 3)
BEFORE = {None: "48404ab58fd24175", 7: "58018a4c32966889"}


def _plan(params, owner=None, runs=None):
    return SimpleNamespace(params=params, source=SimpleNamespace(id="geoportal"), resolution=2.0, owner=owner,
                           paths=SimpleNamespace(runs=runs), tile_core=400, tiles=[None] * 4,
                           emit=lambda kind, text: None)


def _web(values):
    return jb.search_params(json.loads(json.dumps({"params": {**AREA, **values}})))


def _migrated():
    """A stored web sag request of before 2026-11-14 without a fall zone, as migration 17 leaves it."""
    params = {**AREA, "model": "sag"}
    request = json.loads(json.dumps({"params": params}))
    if request["params"].get("model") == "sag" and "fall_zone" not in request["params"]:
        request["params"]["fall_zone"] = jb.FALL_ZONE_BEFORE
    return jb.search_params(json.loads(json.dumps(request)))


@pytest.mark.parametrize("owner", [None, 7])
def test_hashes_stay(owner):
    """_search_hash of every request is today's; the key of before is only a second key of a sag search at 3 m."""
    column = 1 if owner is None else 2
    for name, row in WEB.items():
        got = search._search_hash(_plan(_web(row[0]), owner))
        if row[column] is not None:
            assert got == row[column], name
    for name, row in COMMAND_LINE.items():
        [params], _ = pm.parse_cli(CLI + row[0])
        assert search._search_hash(_plan(params, owner)) == row[column], name
    migrated = _plan(_migrated(), owner)
    assert search._search_hash(migrated) == WEB["sag, fall_zone 3"][column]  # as today
    assert search._search_keys(migrated) == [WEB["sag, fall_zone 3"][column], BEFORE[owner]]
    [cli3], _ = pm.parse_cli(CLI + ["--model", "sag", "--fall-zone", "3"])
    assert search._search_keys(_plan(cli3, owner))[0] == COMMAND_LINE["sag --fall-zone 3"][column]
    for values in ({"model": "sag", "fall_zone": 4.5}, {"model": "sag"}, {}, {"fall_zone": 3}):
        assert search._search_keys(_plan(_web(values), owner)) == [search._search_hash(_plan(_web(values), owner))]


def _unfinished(runs, key, name="unfinished"):
    folder = os.path.join(runs, name)
    os.makedirs(os.path.join(folder, "tiles"))
    with open(os.path.join(folder, "progress.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "running", "search": key, "tile_core": 400, "name": "Gozo",
                   "created": "2026-11-13T10:00:00"}, f)
    return folder


def _state(folder):
    with open(os.path.join(folder, "progress.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("owner", [None, 7])
def test_migrated_job_resumes_the_run_of_before(tmp_path, owner):
    """A run written under the hash of before resumes for the migrated request, and its progress.json then holds
    today's key (so a later resume finds it under that one)."""
    runs = str(tmp_path)
    folder = _unfinished(runs, BEFORE[owner])
    plan = _plan(_migrated(), owner, runs)
    run = search._open_run(plan)
    assert run["path"] == folder and run["search"] == search._search_hash(plan)
    assert _state(folder)["search"] == search._search_hash(plan)
    assert {k: v for k, v in _state(folder).items() if k != "search"} == {
        "status": "running", "tile_core": 400, "name": "Gozo", "created": "2026-11-13T10:00:00"}
    assert search._open_run(_plan(_migrated(), owner, runs))["path"] == folder  # again, under today's key
    assert os.listdir(runs) == ["unfinished"]


def test_run_under_todays_key_is_not_rewritten(tmp_path):
    runs = str(tmp_path)
    plan = _plan(_migrated(), None, runs)
    folder = _unfinished(runs, search._search_hash(plan))
    before = os.path.getmtime(os.path.join(folder, "progress.json"))
    os.utime(os.path.join(folder, "progress.json"), (before - 100, before - 100))
    assert search._open_run(plan)["path"] == folder
    assert os.path.getmtime(os.path.join(folder, "progress.json")) == before - 100


@pytest.mark.parametrize("params, owner", [
    (lambda: _web({"model": "sag", "fall_zone": 4.5, "name": "other"}), None),  # another fall zone
    (lambda: _web({"model": "sag", "name": "other"}), None),  # today's default, 6 m
    (lambda: _web({"fall_zone": 3, "name": "other"}), None),  # the formula at 3 m
    (lambda: _web({"model": "sag", "fall_zone": 3, "name": "other"}), 8),  # another owner
])
def test_no_other_search_resumes_the_run_of_before(tmp_path, params, owner):
    """The run of before (owner 7 or none, sag at the default 3 m) is not resumed by another search or owner."""
    runs = str(tmp_path)
    _unfinished(runs, BEFORE[None], "local")
    _unfinished(runs, BEFORE[7], "owner7")
    run = search._open_run(_plan(params(), owner, runs))
    assert os.path.basename(run["path"]) not in ("local", "owner7")
    assert _state(os.path.join(runs, "local"))["search"] == BEFORE[None]
    assert _state(os.path.join(runs, "owner7"))["search"] == BEFORE[7]
