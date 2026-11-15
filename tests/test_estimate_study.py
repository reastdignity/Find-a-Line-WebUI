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


def _searched(tmp_path, monkeypatch, params, owner=None) -> tuple:
    """A search with limits (the web worker's estimate; owner: the job's user, as jobs.run_phase sets it): its
    estimate and its lines."""
    import search
    from settings import Limits
    seen, check = [], search._estimate_check
    monkeypatch.setattr(search, "_estimate_check", lambda plan, e, se, px: (seen.append((e, se)),
                                                                              check(plan, e, se, px))[1])
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(tmp_path / "work")), lambda kind, text: None,
                              limits=Limits())
    plan.owner = owner
    lines, _ = search.search_lines(plan)
    monkeypatch.setattr(search, "_estimate_check", check)
    return seen[0], len(lines.results), plan


def test_exact_counts_and_the_searchs_own_estimate(tmp_path, monkeypatch):
    """At a fraction of 1 the anchors design gives the lines found and the squares design the keys seen
    from their first square, at most the lines kept; the study rule's seeds give a row per seed, each with
    the numbers this clip gives (900 880 found, 18 593 kept, 18 577 from their first square; measured
    2026-11-15); the search rule gives the estimate a job of the web worker gets for the same request, in both
    designs, also of a job with an owner (the public site: the owner is in the seed)."""
    import estimate_study as es
    import search
    result = es.study(_params(**POINT, **SAG), str(tmp_path / "data"), fractions=(1.0, 0.25), seeds=2, exact=True,
                      limit=1_000_000)
    assert result["exact"] == {"found": 900_880, "kept": 18_593, "kept_tiles": 18_593, "from_ka": 18_577}
    rows = {(r["design"], r["fraction"], r["seed"]): r for r in result["rows"]}
    assert set(rows) == {(d, f, es.STUDY_SEEDS[d] + s) for d in es.DESIGNS for f in (1.0, 0.25) for s in (0, 1)}
    for s in (1000, 1001):
        assert rows[("anchors", 1.0, s)]["estimate"] == 900_880 and rows[("anchors", 1.0, s)]["se"] == 0
    for s in (2000, 2001):
        assert rows[("squares", 1.0, s)]["estimate"] == 18_577
    quarters = {key[2]: (r["estimate"], r["se"], r["lo"], r["hi"], r["k"], r["n"], r["verdict"])
                for key, r in rows.items() if key[1] == 0.25}
    assert quarters == {1000: (901_233, 28_373, 844_487, 957_980, 2_774, 11_097, "close"),  # 0.8 M <= est <= 1.25 M
                        1001: (898_749, 29_120, 840_508, 956_990, 2_774, 11_097, "close"),
                        2000: (19_013, 1_799, 15_415, 22_611, 281, 1_125, "on"),
                        2001: (18_524, 1_746, 15_033, 22_016, 281, 1_125, "on")}, quarters
    assert rows[("anchors", 0.25, 1000)]["ratio"] == round(901_233 / 900_880, 4)
    assert [es.verdict(e, 1_000_000) for e in (1_250_001, 1_250_000, 800_000, 799_999)] == [
        "refused", "close", "close", "on"]
    assert result["tiles"] == 0 and result["per_tile"][0]["anchors"] > 0
    assert not {"northing", "easting", "elevation_file"} & set(result["settings"])
    for square, design, owner in ((0, "anchors", None), (5, "squares", None), (0, "anchors", 7)):
        params = _params(same_line_square=square, **POINT, **SAG)
        (estimate, se), _, _ = _searched(tmp_path / f"{design}-{owner}", monkeypatch, params, owner)
        own = es.study(params, str(tmp_path / "data"), fractions=(search.SAMPLE_FRACTION,), seed_rule="search",
                       designs=(design,), owner=owner)
        assert [(r["estimate"], r["se"]) for r in own["rows"]] == [(int(round(estimate)), int(round(se)))]
        if owner:  # another seed than the local app's job of the same request
            assert own["rows"][0]["seed"] != es.study(params, str(tmp_path / "data"), fractions=(0.02,),
                                                      seed_rule="search", designs=(design,))["rows"][0]["seed"]
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
    assert saved["name"] == "clip" and len(saved["rows"]) == 1 and saved["exact"]["found"] == 1301
    assert (row["estimate"], row["se"], row["k"], row["n"], row["verdict"]) == (1288, 109, 310, 620, "refused")
    assert "| anchors | 0.5 | 1000 |" in printed and not os.path.exists(str(out) + ".partial")
    for text in (printed, out.read_text(encoding="utf-8")):
        assert "254608" not in text and "553966" not in text and "zabi_kon" not in text
    gc.collect()
