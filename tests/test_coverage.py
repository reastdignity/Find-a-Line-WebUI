"""The coverage map's data: coverage.json from the catalogue, its outlines and texts, and the pure parts of
tools/coverage_contrast.py (no network)."""

import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import sources as src  # noqa: E402
import coverage_contrast  # noqa: E402
import coverage_data  # noqa: E402

COVERAGE = os.path.join(REPO, "viewer", "src", "coverage", "coverage.json")
SHAPES = os.path.join(REPO, "viewer", "src", "coverage", "shapes.json")
# Sources only used to fill the gaps of others: not on the map
GAP_FILLERS = {"usgs10m", "canada_2m", "mrdem30", "nz8m", "france_rgealti", "malta2012", "alaska_ifsar", "nasadem",
               "europe"}


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _base(key):
    """A key without its plural form."""
    stem, _, form = key.rpartition("_")
    return stem if stem and form in ("zero", "one", "two", "few", "many", "other") else key


def _catalogues():
    return {lang: _json(os.path.join(REPO, "locales", "coverage", f"{lang}.json")) for lang in ("en", "pl")}


def test_coverage_json_up_to_date():
    """viewer/src/coverage/coverage.json is generated from the catalogue: run `uv run tools/coverage_data.py`
    after changing a source's coverage (and rebuild viewer/dist)."""
    with open(COVERAGE, encoding="utf-8") as f:
        assert f.read() == coverage_data.render(), "coverage.json is out of date: run `uv run tools/coverage_data.py`"
    assert coverage_data.main(["--check"]) == 0


def test_every_map_source_has_a_coverage():
    """Every source but the gap fillers colours the map; the gap fillers do not."""
    for sid, source in src.SOURCES.items():
        assert (source.coverage is None) == (sid in GAP_FILLERS), sid
        if source.coverage:
            assert source.coverage.provider and len(source.coverage.added) == 10, sid


def test_one_source_per_area():
    seen = {}
    for source in src.SOURCES.values():
        if source.coverage:
            for area in coverage_data.areas_of(source):
                assert area not in seen, (area, seen.get(area), source.id)
                assert area == area.lower()
                seen[area] = source.id
    assert set(seen) == set(_json(COVERAGE)["areas"])


def test_areas_as_decided():
    """The special cases of the plan: Alaska's IfSAR at 5 m, Canada's mix, the six of wave 3."""
    areas = _json(COVERAGE)["areas"]
    ak = areas["us-ak"]
    assert (ak["level"], ak["partial"], ak["res"], ak["notes"][0]["code"]) == (2, False, [1, 5], "mixed")
    ca = areas["ca"]
    assert (ca["level"], ca["partial"], ca["res"]) == (1, True, [1, 2, 30])
    for area in ("de-by", "de-rp", "de-nw", "it-tn", "gb-sct", "au-tas"):
        assert area in areas
    assert areas["us"]["notes"] == [{"code": "no_trees"}, {"code": "gaps", "params": {"res": 10}}]
    assert {"code": "gaps", "params": {"res": 8}} in areas["nz"]["notes"]


def test_every_area_has_a_shape():
    """Every area of coverage.json has a feature in shapes.json (tools/coverage_shapes.py), regions as
    regions, and dist holds the same outlines."""
    shapes = _json(SHAPES)
    kinds = {}
    for feature in shapes["features"]:
        p = feature["properties"]
        assert set(p) <= {"id", "kind", "continent", "small", "rest"}
        if not p.get("rest"):
            assert p["id"] not in kinds, p["id"]
            kinds[p["id"]] = p["kind"]
    for area in _json(COVERAGE)["areas"]:
        assert kinds.get(area) == ("region" if "-" in area else "country"), area
    with open(SHAPES, "rb") as a, open(os.path.join(REPO, "viewer", "dist", "coverage-shapes.json"), "rb") as b:
        assert a.read() == b.read(), "rebuild viewer/dist"


def test_texts_of_codes_in_both_catalogues():
    """Every note and survey code and every region has its text in English and Polish; both catalogues
    have the same keys (a plural's forms are the language's own: Polish has _few and _many too)."""
    catalogues = _catalogues()
    assert set(map(_base, catalogues["en"])) == set(map(_base, catalogues["pl"]))
    for key in catalogues["pl"]:
        if _base(key) != key:
            assert all(f"{_base(key)}_{form}" in catalogues["pl"] for form in ("one", "few", "many", "other")), key
    data = _json(COVERAGE)
    keys = set()
    for area, entry in data["areas"].items():
        keys |= {f"note.{note['code']}" for note in entry["notes"]}
        if entry["survey"] and not entry["survey"][0].isdigit():
            keys.add(f"survey.{entry['survey']}")
        if "-" in area:
            keys.add(f"region.{area}")
    for lang, texts in catalogues.items():
        assert not keys - set(texts), (lang, sorted(keys - set(texts)))


def test_survey_years_with_an_en_dash():
    for entry in _json(COVERAGE)["areas"].values():
        survey = entry["survey"]
        if survey and survey[0].isdigit():
            assert len(survey) in (4, 9) and (len(survey) == 4 or survey[4] == "–"), survey


def test_contrast_matching():
    """A line is matched when another has both anchors within the radius, either way round."""
    a1 = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 500.0]])
    a2 = np.array([[50.0, 0.0], [150.0, 0.0], [50.0, 500.0]])
    b1 = np.array([[155.0, 30.0], [10.0, 0.0]])
    b2 = np.array([[100.0, 30.0], [500.0, 0.0]])
    # the first: b's second has one anchor near only; the second: b's first reversed within 45 m
    assert coverage_contrast.matched(a1, a2, b1, b2, 45).tolist() == [False, True, False]
    assert coverage_contrast.matched(a1, a2, b1, b2, 30).tolist() == [False, False, False]
    assert coverage_contrast.matched(a1, a2, b1[:0], b2[:0], 45).tolist() == [False] * 3


def test_contrast_verify():
    """1 m spots found at 30 m (by their representatives), 30 m spots with a real line (any member)."""
    fine = {"a1": np.array([[0.0, 0.0], [1000.0, 0.0], [5.0, 0.0]]),
            "a2": np.array([[60.0, 0.0], [1060.0, 0.0], [65.0, 0.0]]), "rep": np.array([0, 1])}
    coarse = {"a1": np.array([[3000.0, 0.0], [20.0, 0.0]]), "a2": np.array([[3060.0, 0.0], [70.0, 0.0]]),
              "rep": np.array([0]), "members": np.array([0, 1]), "start": np.array([0, 2])}
    assert coverage_contrast.verify(fine, coarse) == {"fine_spots": 2, "fine_found": 1, "coarse_spots": 1,
                                                       "coarse_real": 1}


def test_contrast_segments():
    """The representatives' lines in the square's 0..1 coordinates (y down), those far outside left out."""
    a1 = np.array([[100.0, 900.0], [0.0, 1000.0], [-200.0, 500.0]])
    a2 = np.array([[300.0, 700.0], [1000.0, 0.0], [100.0, 500.0]])
    over = np.array([False, True, False])
    square = (0.0, 1000.0, 1000.0)
    assert coverage_contrast.segments(a1, a2, np.array([1, 0, 2]), over, square) == [
        [0.0, 0.0, 1.0, 1.0, 1], [0.1, 0.1, 0.3, 0.3, 0]]
    assert coverage_contrast.segments(a1, a2, np.array([1, 0, 2]), over, square, limit=1) == [[0.0, 0.0, 1.0, 1.0, 1]]


def test_contrast_crop():
    """The square around the centre, NaN beyond the grid."""
    info = {"grid": {"left": 0.0, "top": 10.0, "res": 1.0}, "center_xy": [2.0, 8.0]}
    values = np.arange(100, dtype=float).reshape(10, 10)
    cut, square = coverage_contrast.crop(info, values, 3.0)
    assert square == (-1.0, 11.0, 6.0) and cut.shape == (6, 6)
    assert np.isnan(cut[0]).all() and np.isnan(cut[:, 0]).all() and cut[1, 1] == values[0, 0]


@pytest.mark.parametrize("res,level", [(0.5, 1), (1, 1), (2, 2), (5, 2), (10, 3), (30, 3)])
def test_level_of(res, level):
    assert coverage_data.level_of(res) == level
