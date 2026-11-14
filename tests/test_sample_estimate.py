"""The size of a search before its pairs (search.sample_estimate, _estimate_check: docs/line-volume/spec-search.md
section 2) and count_tile's sag table built once per process (spec-search.md 5.2). Offline, on the Żabi Koń
clip of tests/data."""

import dataclasses
import gc
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")
OFFLINE_ENV = {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}
POINT = {"northing": 254608, "easting": 553966, "radius": 290}
SAG = {"model": "sag", "end_zone": 5, "anchor_lift": 2}  # many more lines than the formula's, both rigging classes


@pytest.fixture
def offline(monkeypatch):
    for key, value in OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)


def _plan(tmp_path, limits=None, **values):
    import search
    from params import SearchParams
    params = SearchParams(**{"elevation_file": CLIP, "water": "off", "fill_gaps": "off", "ortho": "never",
                             **values})
    paths = search.Paths(str(tmp_path), str(tmp_path / "work"))
    os.makedirs(paths.work, exist_ok=True)
    return search.plan_search(params, paths, lambda kind, text: None, limits=limits)


def _counts(parts) -> tuple:
    """The lines of a count's parts and the sums of their clearances and lengths (order free)."""
    return (sum(len(p) for p in parts), round(sum(float(p.columns["clearance"].sum()) for p in parts), 6),
            round(sum(float(p.columns["length"].sum()) for p in parts), 6))


def test_count_tile_takes_the_sag_table_of_the_process(tmp_path, offline, monkeypatch):
    """count_tile without a sag table counts the lines of one with the table given, and builds the
    table of a rigging and the lengths once per process (search._sag_table, as _lines): not again for
    the next tile."""
    import sag as sg
    import search
    plan = _plan(tmp_path, **POINT, **SAG)
    data = search.prepare_data(plan)
    given = []
    search.count_tile(plan, data, None, given.append,
                      sg.EnvelopeTable(plan.rigging, plan.params.min_length, plan.params.max_length))
    built = []
    table = sg.EnvelopeTable
    monkeypatch.setattr(search, "_SAG_TABLES", {})
    monkeypatch.setattr(sg, "EnvelopeTable", lambda *a, **k: (built.append(a), table(*a, **k))[1])
    counted = [[], []]
    for parts in counted:
        search.count_tile(plan, data, None, parts.append)
    assert len(built) == 1, built
    assert _counts(counted[0]) == _counts(counted[1]) == _counts(given) and _counts(given)[0] > 0
    del data
    gc.collect()
