"""The size of a search before its pairs (search.sample_estimate, _estimate_check: docs/line-volume/spec-search.md
section 2) and count_tile's sag table built once per process (spec-search.md 5.2). Offline, on the Żabi Koń
clip of tests/data."""

import dataclasses
import gc
import json
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


# --- the sample (spec-search.md 2) ---

SQUARE_AREA = {"type": "Polygon", "coordinates": [[[19.7522, 50.1546], [19.7590, 50.1546], [19.7590, 50.1580],
                                                   [19.7522, 50.1580], [19.7522, 50.1546]]]}
TILES = {"geometry": {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                                                 "geometry": SQUARE_AREA}]},
         "max_length": 150, "tile_size": 150}  # an area of the clip in many tiles (test_public's)


def _estimates(monkeypatch) -> list:
    """The arguments of every _estimate_check call from now on: [(estimate, se, pixels)]."""
    import search
    seen, check = [], search._estimate_check
    monkeypatch.setattr(search, "_estimate_check",
                        lambda plan, estimate, se, pixels: (seen.append((estimate, se, pixels)),
                                                            check(plan, estimate, se, pixels))[1])
    return seen


def _ready(plan):
    """Step 1, step 2's anchors and the sag table of a plan of one grid."""
    import search
    data = search.prepare_data(plan)
    p = plan.params
    table = search._sag_table(dataclasses.astuple(plan.rigging), p.min_length, p.max_length) \
        if p.model == "sag" else None
    return data, search._anchors(plan, data), table


@pytest.mark.parametrize("values", [{}, SAG, {"model": "sag", "max_anchor_diff_m": 3}])
def test_open_anchors_are_the_line_searchs(tmp_path, offline, values):
    """The anchors the sample draws from (search._open_anchors, find_valid_lines' set-up of
    free_directions repeated) are exactly the line search's useful anchors: as many, and every one of
    them starts pairs when they are the first-anchor mask."""
    import search
    plan = _plan(tmp_path, **POINT, **values)
    data, found, table = _ready(plan)
    useful = search._open_anchors(plan, data, found, table)
    assert len(useful) and np.all(np.diff(useful) > 0)
    mask = np.zeros(len(found.anchors), dtype=bool)
    mask[useful] = True
    plan.funnel = {}
    search._pair_search(plan, data, found, None, table, sink=lambda part: None, first=mask)
    assert plan.funnel["open"] == plan.funnel["todo"] == len(useful), (plan.funnel, len(useful))
    del data
    gc.collect()


def test_a_fraction_of_one_counts_every_line(tmp_path, offline, monkeypatch):
    """With a sample of every unit the estimate is the exact count: the lines of one grid and of an
    area in tiles (every tile sampled before the first tile's pairs, from its window and its own
    anchors), and with the square rule the keys seen from their first square, at most the lines the
    grid or the tiles kept and hardly fewer (a key whose lines all start in its second square)."""
    import search
    from settings import Limits
    monkeypatch.setattr(search, "SAMPLE_FRACTION", 1.0)
    seen = _estimates(monkeypatch)
    calls = []
    sample, lines_of = search.sample_estimate, search._lines
    monkeypatch.setattr(search, "sample_estimate", lambda *a, **k: (calls.append(("sample", a[5])), sample(*a, **k))[1])
    monkeypatch.setattr(search, "_lines", lambda *a, **k: (calls.append(("tile", len(a) > 2 and a[2] is not None)),
                                                           lines_of(*a, **k))[1])
    for name, values, square, share in (("grid", POINT, 0, 1), ("tiles", TILES, 0, 1),
                                        ("grid-sq", {**POINT, **SAG}, 5, 0.999), ("tiles-sq", {**TILES, **SAG}, 5, 0.99)):
        seen.clear()
        calls.clear()
        plan = _plan(tmp_path / name, Limits(), same_line_square=square, **values)
        lines, _ = search.search_lines(plan)
        assert len(seen) == 1, seen
        estimate, se, _ = seen[0]
        assert se == 0 and plan.funnel["estimate"] == estimate  # every unit: no variance
        if plan.tiles:  # each tile with anchors sampled once, all of them before the first tile's own steps
            tiles = [c for c in calls if c[0] == "tile"]
            samples = [k for kind, k in calls if kind == "sample"]
            assert len(tiles) == len(plan.tiles) > 4 and all(core for _, core in tiles)
            assert samples == sorted(set(samples)) and len(samples) > 4 and calls.index(tiles[0]) == len(samples)
        if not square:
            assert estimate == len(lines.results) == plan.funnel["lines"], (name, estimate, len(lines.results))
        else:  # the kept lines (a tiled search's before their join: the funnel's "lines"); measured 18 577 of
            # 18 593 in one grid, 6 364 of 6 405 in the tiles of 150 m, which cut many pairs of squares
            kept = plan.funnel["lines"]
            assert share * kept <= estimate <= kept, (name, estimate, kept)
        del lines
        gc.collect()


@pytest.mark.parametrize("square", [0, 5])
def test_the_same_estimate_for_any_number_of_threads(tmp_path, offline, square):
    """The estimate (both designs) does not depend on the number of threads, and the search's seed is
    the first 8 hex digits of its hash: another seed draws another sample."""
    import search
    plan = _plan(tmp_path, **POINT, **SAG, same_line_square=square)
    data, found, table = _ready(plan)
    results = []
    for threads in (1, 3):
        threaded = dataclasses.replace(plan, params=plan.params.model_copy(update={"threads": threads}))
        results.append(search.sample_estimate(threaded, data, found, None, table, 0))
    assert results[0] == results[1] and results[0][0] > 0 and results[0][2] > 1, results
    seed = int(search._search_hash(plan)[:8], 16)
    assert search.sample_estimate(plan, data, found, None, table, 0, seed=seed) == results[0]
    assert search.sample_estimate(plan, data, found, None, table, 0, seed=seed + 1) != results[0]
    del data
    gc.collect()


def test_the_band_and_its_codes(tmp_path, offline, monkeypatch):
    """Over 1.25 times the line limit the search is refused at once, before its own pairs
    (too_many_lines_estimate, with the advice); from 0.8 times it goes on with the warning that it is
    close and the full search's checks decide; below, only the note of the estimate. The memory the
    same way (too_many_lines_memory_estimate). The estimate goes to the funnel."""
    import messages
    import search
    from settings import Limits
    plan = _plan(tmp_path, Limits(), **POINT)
    data = search.prepare_data(plan)
    pixels = plan.grid.width * plan.grid.height
    seen = _estimates(monkeypatch)
    events = []
    plan.emit = lambda kind, text: events.append((kind, getattr(text, "code", None), getattr(text, "params", None)))
    exact = len(search.find_lines(plan, data).results)
    estimate, se, at = seen[-1]
    n = int(round(estimate))
    assert at == pixels and estimate > 0 and plan.funnel["estimate"] == n and plan.funnel["lines"] == exact
    coded = [e for e in events if e[1]]
    assert [e[:2] for e in coded] == [("info", "estimate_lines")], events
    assert coded[0][2]["n"] == n and coded[0][2]["lo"] <= n <= coded[0][2]["hi"]
    pairs, real = [], search._pair_search
    monkeypatch.setattr(search, "_pair_search", lambda *a, **k: (pairs.append(k.get("first")), real(*a, **k))[1])

    def search_with(limits, memory=None):
        events.clear()
        pairs.clear()
        plan.limits, plan.memory, plan.funnel = limits, memory, {}
        return search.find_lines(plan, data)

    for limits, memory, code, limit in ((Limits(lines_max=int(estimate / 1.3)), None, "too_many_lines_estimate",
                                         int(estimate / 1.3)),
                                        (Limits(), int(search.memory_needed(pixels, int(estimate / 1.3))),
                                         "too_many_lines_memory_estimate", int(estimate / 1.3))):
        with pytest.raises(search.SearchError) as error:
            search_with(limits, memory)
        assert error.value.code == code and error.value.params["max"] == limit, error.value.params
        assert error.value.params["n"] == n and error.value.params["advice"] == messages.line_advice(plan.params)
        assert len(pairs) == 1 and pairs[0] is not None  # the sample's pairs only, never the search's
        assert "estimated from a sample" in str(error.value) and "--same-line-square 5" in str(error.value)
        assert plan.funnel["estimate"] == n
    # close (between 0.8 and 1.25 times the limit): it goes on, the full search's checks decide at its end
    close = int(round(estimate))
    try:
        assert len(search_with(Limits(lines_max=close)).results) == exact <= close
    except search.SearchError as error:
        assert exact > close and error.code in ("too_many_lines_early", "too_many_lines"), error
    coded = [e for e in events if e[1]]
    assert [e[:2] for e in coded] == [("info", "estimate_lines"), ("warning", "estimate_close")], events
    assert coded[-1][2]["max"] == close and len(pairs) == 2 and pairs[1] is None
    # far below the limit: the note only
    assert len(search_with(Limits(lines_max=int(estimate / 0.7) + 1)).results) == exact
    assert [e[:2] for e in events if e[1]] == [("info", "estimate_lines")], events
    del data
    gc.collect()


def test_no_sample_without_limits_or_the_early_stop(tmp_path, offline, monkeypatch):
    """The command line and the regression set (no limits, no memory) never sample, nor a search with
    Limits.lines_early_stop false (no funnel "estimate"); a search with the switch on does."""
    import search
    from settings import Limits
    calls = []
    sample = search.sample_estimate
    monkeypatch.setattr(search, "sample_estimate", lambda *a, **k: (calls.append(1), sample(*a, **k))[1])
    for name, limits, sampled in (("cli", None, False), ("off", Limits(lines_early_stop=False), False),
                                  ("on", Limits(), True)):
        calls.clear()
        plan = _plan(tmp_path / name, limits, **POINT)
        assert (plan.memory is None) == (limits is None)
        search.search_lines(plan)
        assert bool(calls) == sampled and ("estimate" in plan.funnel) == sampled, name
        gc.collect()


def test_the_estimates_texts(monkeypatch):
    """The texts of the estimate (spec-search.md 2.2, "Seen"): the page's in millions of two digits, the
    note of a search under 0.1 million, the warning that it is close, both refusals with the advice."""
    from types import SimpleNamespace
    import messages
    import params as pm
    import search
    from settings import Limits
    events = []
    plan = SimpleNamespace(limits=Limits(lines_max=5_000_000), memory=None, funnel={},
                           params=pm.SearchParams(lat=50, lon=19, model="sag", end_zone=5),
                           emit=lambda kind, text: events.append((kind, text)))
    search._estimate_check(plan, 3_215_000, 320_000, 0)
    assert [(kind, text.web_text()) for kind, text in events] == [
        ("info", "About 3.2 million lines (2.6 to 3.9 million) with these settings.")]
    assert str(events[0][1]).startswith("About 3215000 lines (2575000 to 3855000)") and plan.funnel["estimate"] == 3215000
    events.clear()
    plan.limits = Limits(lines_max=1_500_000)
    search._estimate_check(plan, 1_500_000, 100_000, 0)
    assert [text.web_text() for _, text in events] == [
        "About 1.5 million lines (1.3 to 1.7 million) with these settings.",
        "That is close to this site's limit of 1.5 million: the search goes on and stops if it passes it."]
    assert events[1][0] == "warning" and events[1][1].params == {"max": 1_500_000, "limit": 1.5}
    events.clear()
    search._estimate_check(plan, 42_000, 9_000, 0)
    assert [text.web_text() for _, text in events] == ["Fewer than 0.1 million lines with these settings."]
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 24_300_000, 1_700_000, 0)
    advice = messages.line_advice(plan.params)
    assert error.value.code == "too_many_lines_estimate" and error.value.params == {
        "n": 24_300_000, "lo": 20_900_000, "hi": 27_700_000, "count": 24, "low": 21, "high": 28, "max": 1_500_000,
        "limit": 1.5, "advice": advice}
    assert error.value.web_text() == ("About 24 million lines (21 to 28 million) with these settings, at most "
                                      f"1.5 million on this site. {messages.advice_text(advice)}")
    assert "--same-line-square 5; --end-zone 0;" in str(error.value)
    plan.limits, plan.memory = None, int(search.memory_needed(1000, 2_000_000))
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 2_600_000, 100_000, 1000)
    assert error.value.code == "too_many_lines_memory_estimate" and error.value.params["max"] == 2_000_000
    assert error.value.web_text().startswith("About 2.6 million lines (2.4 to 2.8 million) with these settings, "
                                             "at most 2 million fit into the memory of this site. To find fewer")


def test_the_estimates_texts_in_the_page(tmp_path):
    """The page renders the estimate's notes and refusals as the server writes them (viewer/src/i18n.ts
    errorText, detailMessage): the millions, the plural form of fewer than 0.1 million, the advice."""
    import shutil
    from types import SimpleNamespace
    import messages
    import params as pm
    import search
    from settings import Limits
    viewer = os.path.join(REPO, "viewer")
    if shutil.which("node") is None or not os.path.isdir(os.path.join(viewer, "node_modules", "esbuild")):
        pytest.skip("needs Node and `npm install` in viewer/")
    from test_viewer import run_ts
    plan = SimpleNamespace(limits=Limits(lines_max=1_500_000), memory=None, funnel={}, emit=lambda kind, text: None,
                           params=pm.SearchParams(lat=50, lon=19, model="sag", end_zone=5, anchor_lift=2))
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 24_300_000, 1_700_000, 0)
    cases = [messages.Note("x", "estimate_lines", n=3_215_000, lo=2_575_000, hi=3_855_000, count=3.2, low=2.6,
                           high=3.9).info(),
             messages.Note("x", "estimate_lines", n=42_000, lo=24_000, hi=60_000, count=0, low=0.024,
                           high=0.06).info(),
             messages.Note("x", "estimate_close", max=1_500_000, limit=1.5).info(), error.value.detail()]
    found = run_ts(tmp_path, "i18n", f"""
console.log(JSON.stringify({json.dumps(cases)}.map((d) => m.detailMessage(d, "fallback"))));""")
    python = [messages.text(f"error.{c['code']}", **messages.web_params(c["params"])) for c in cases]
    assert found == python and found[1] == "Fewer than 0.1 million lines with these settings.", found
    assert found[3] == error.value.web_text() and "1.5 million on this site. To find fewer lines" in found[3]
