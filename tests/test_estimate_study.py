"""tools/estimate_study.py: the estimate of a search's lines from a sample against the exact count, per case,
fraction and seed, in both designs, on the Żabi Koń clip of tests/data (offline): the exact counts of a
fraction of 1, the search's own estimate under its own seed, a tiled area, the command line's file."""

import gc
import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
DATA = os.path.join(REPO, "tests", "data")
CLIP = os.path.join(DATA, "zabi_kon_nmt.tif")
POINT = {"northing": 254608, "easting": 553966, "radius": 290}
SAG = {"model": "sag", "end_zone": 5, "anchor_lift": 2}
AREA = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                            [19.7522, 50.1580], [19.7522, 50.1546]]]}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key, value in {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""}.items():
        monkeypatch.setenv(key, value)


def _params(**values):
    from params import SearchParams
    return SearchParams(**{"elevation_file": CLIP, "water": "off", "fill_gaps": "off", "ortho": "never", **values})


def _searched(tmp_path, monkeypatch, params) -> tuple:
    """A search with limits (the web worker's estimate): its estimate and its lines."""
    import search
    from settings import Limits
    seen, check = [], search._estimate_check
    monkeypatch.setattr(search, "_estimate_check", lambda plan, e, se, px: (seen.append((e, se)),
                                                                              check(plan, e, se, px))[1])
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None,
                              limits=Limits())
    lines, _ = search.search_lines(plan)
    monkeypatch.setattr(search, "_estimate_check", check)
    return seen[0], len(lines.results), plan


def test_exact_counts_and_the_searchs_own_estimate(tmp_path, monkeypatch):
    """At a fraction of 1 the anchors design gives the lines found and the squares design the keys seen
    from their first square, at most the lines kept; the study rule's seeds give a row per seed; the search
    rule gives the estimate a job of the web worker gets for the same request, in both designs."""
    import estimate_study as es
    import search
    result = es.study(_params(**POINT, **SAG), str(tmp_path / "data"), fractions=(1.0, 0.25), seeds=2, exact=True,
                      limit=1_000_000)
    exact = result["exact"]
    assert exact["found"] > exact["kept"] == exact["kept_tiles"] >= exact["from_ka"] >= 0.999 * exact["kept"]
    rows = {(r["design"], r["fraction"], r["seed"]): r for r in result["rows"]}
    assert set(rows) == {(d, f, es.STUDY_SEEDS[d] + s) for d in es.DESIGNS for f in (1.0, 0.25) for s in (0, 1)}
    for s in (1000, 1001):
        assert rows[("anchors", 1.0, s)]["estimate"] == exact["found"] and rows[("anchors", 1.0, s)]["se"] == 0
    for s in (2000, 2001):
        assert rows[("squares", 1.0, s)]["estimate"] == exact["from_ka"]
    quarter = rows[("anchors", 0.25, 1000)]
    assert quarter["k"] == round(0.25 * quarter["n"]) and quarter["lo"] <= quarter["estimate"] <= quarter["hi"]
    assert quarter["verdict"] == es.verdict(quarter["estimate"], 1_000_000) and quarter["ratio"] > 0
    assert result["tiles"] == 0 and result["per_tile"][0]["anchors"] > 0
    assert not {"northing", "easting", "elevation_file"} & set(result["settings"])
    for square, design in ((0, "anchors"), (5, "squares")):
        (estimate, se), _, _ = _searched(tmp_path / design, monkeypatch, _params(same_line_square=square, **POINT,
                                                                                  **SAG))
        own = es.study(_params(same_line_square=square, **POINT, **SAG), str(tmp_path / "data"),
                       fractions=(search.SAMPLE_FRACTION,), seed_rule="search", designs=(design,))
        assert [(r["estimate"], r["se"]) for r in own["rows"]] == [(int(round(estimate)), int(round(se)))]
    gc.collect()


def test_a_tiled_area(tmp_path, monkeypatch):
    """A tiled area sums its tiles, each from its window and its anchors: at a fraction of 1 the lines a
    tiled search finds; the tiles' kept lines before the join are at least the kept lines after it and the
    keys seen from their first square in each tile (a key of two tiles counts in both, as the limit does)."""
    import estimate_study as es
    path = tmp_path / "area.geojson"
    path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": AREA}))
    params = _params(area=str(path), max_length=150, tile_size=150, **SAG)
    result = es.study(params, str(tmp_path / "data"), fractions=(1.0,), seeds=1, exact=True)
    (_, _), lines, plan = _searched(tmp_path / "search", monkeypatch, params)
    assert result["tiles"] == len(plan.tiles) == len(result["per_tile"]) > 4
    assert result["exact"]["found"] == lines == [r["estimate"] for r in result["rows"] if r["design"] == "anchors"][0]
    exact = result["exact"]
    assert exact["kept_tiles"] >= max(exact["kept"], exact["from_ka"]) and exact["from_ka"] > 0.99 * exact["kept_tiles"]
    gc.collect()


def test_the_command_line(tmp_path, capsys):
    """The tool's command line: the search's options after --, a table printed, the JSON written whole,
    no coordinates in either."""
    import estimate_study as es
    out = tmp_path / "out" / "clip.json"
    es.main(["--fractions", "0.5", "--seeds", "1", "--designs", "anchors", "--exact", "--limit", "500", "--name",
             "clip", "--out", str(out), "--", "--elevation-file", CLIP, "--northing", "254608", "--easting", "553966",
             "--radius", "290", "--water", "off", "--fill-gaps", "off", "--data-dir", str(tmp_path / "data")])
    printed = capsys.readouterr().out
    saved = json.loads(out.read_text(encoding="utf-8"))
    row = saved["rows"][0]
    assert saved["name"] == "clip" and len(saved["rows"]) == 1 and row["verdict"] == es.verdict(row["estimate"], 500)
    assert "| anchors | 0.5 | 1000 |" in printed and not os.path.exists(str(out) + ".partial")
    for text in (printed, out.read_text(encoding="utf-8")):
        assert "254608" not in text and "553966" not in text and "zabi_kon" not in text
    gc.collect()
