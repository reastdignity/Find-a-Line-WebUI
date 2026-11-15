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
            # 18 593 in one grid, 6 364 of 6 405 (0.64 % under) in the tiles of 150 m: 1 % there, not the 0.1 % of
            # one grid, because small tiles carry a larger share of squares cut by a core edge, whose keys a tile
            # sees only from their second square (part M2 measured 0.013 % on GZ1, up to 0.69 % on DOL and 1.14 % on
            # BEL with tiles of kilometres)
            kept = plan.funnel["lines"]
            assert share * kept <= estimate <= kept, (name, estimate, kept)
        del lines
        gc.collect()


@pytest.mark.parametrize("square", [0, 5])
def test_the_estimate_and_its_variance_against_every_unit(tmp_path, offline, square):
    """sample_estimate's estimate, variance, k and n equal an independent computation from one pair search
    from every useful anchor of the core (the code review's check): the lines (anchors) or the distinct keys
    seen from their first square (squares) of each unit, the units drawn by the same generator, and
    Horvitz-Thompson n² (1 - k/n) s² / k; one grid and a core that cuts squares and the circle."""
    import contextlib
    import io
    import samelines
    import search
    plan = _plan(tmp_path, **POINT, **SAG, same_line_square=square)
    data, found, table = _ready(plan)
    grid, anchors = plan.grid, found.anchors
    cx, cy = plan.center_xy
    for core in (None, (cx - 150.3, cy - 120.7, cx + 130.1, cy + 140.9)):
        useful = search._open_anchors(plan, data, found, table)
        if core is not None:
            x, y = grid.pixel_to_xy(anchors[useful, 0], anchors[useful, 1])
            useful = useful[(core[0] <= x) & (x < core[2]) & (core[1] <= y) & (y < core[3])]
        index = {(int(r), int(c)): i for i, (r, c) in enumerate(anchors)}
        firsts, keys = [], set()

        def sink(part):
            a1, a2 = np.asarray(part.columns["a1"]), np.asarray(part.columns["a2"])
            x1, y1 = grid.pixel_to_xy(a1[:, 0], a1[:, 1])
            x2, y2 = grid.pixel_to_xy(a2[:, 0], a2[:, 1])
            one = (x1 < x2) | ((x1 == x2) & (y1 <= y2))
            firsts.extend(index[(int(r), int(c))] for r, c in np.where(one[:, None], a1, a2))
            if square:
                xa, ya = np.where(one, x1, x2), np.where(one, y1, y2)
                ka, kb = samelines.square_keys(xa, ya, np.where(one, x2, x1), np.where(one, y2, y1), plan.square)
                own = (np.floor(xa / plan.square).astype(np.int64) << 32) + np.floor(ya / plan.square).astype(np.int64)
                keys.update((a, b) for a, b, m in zip(ka.tolist(), kb.tolist(), (ka == own).tolist()) if m)

        mask = np.zeros(len(anchors), dtype=bool)
        mask[useful] = True
        with contextlib.redirect_stdout(io.StringIO()):
            search._pair_search(dataclasses.replace(plan, funnel={}), data, found, core, table, sink=sink, first=mask)
        assert np.isin(firsts, useful).all() and len(firsts) > 1000
        if square:
            x, y = grid.pixel_to_xy(anchors[useful, 0], anchors[useful, 1])
            units = np.unique((np.floor(x / plan.square).astype(np.int64) << 32)
                              + np.floor(y / plan.square).astype(np.int64)).tolist()
            per = dict.fromkeys(units, 0)
            for a, _ in keys:
                per[a] += 1
            each = np.array([per[u] for u in units], dtype=np.float64)
        else:
            each = np.bincount(np.searchsorted(useful, firsts), minlength=len(useful)).astype(np.float64)
        n, seed = len(each), int(search._search_hash(plan)[:8], 16)
        for fraction in (0.02, 0.25):
            k = max(1, int(round(fraction * n)))
            drawn = each[np.random.default_rng([seed, 3]).permutation(n)[:k]]
            expect, variance = drawn.sum() * n / k, n ** 2 * (1 - k / n) * drawn.var(ddof=1) / k
            got = search.sample_estimate(plan, data, found, core, table, 3, fraction=fraction, seed=seed)
            assert got[2:] == (k, n) and variance > 0, (got, k, n)
            assert abs(got[0] - expect) <= 1e-6 * expect and abs(got[1] - variance) <= 1e-6 * variance, (got, expect, variance)
    del data
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
    # far below the limit: the note only. The limit is above the exact count too: the sample's seed comes from the
    # search's hash, which holds the clip's absolute path, so the estimate (and how far it lies from the exact count)
    # differs from one checkout to another
    assert len(search_with(Limits(lines_max=max(int(estimate / 0.7), exact) + 1)).results) == exact
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


def test_the_worker_tells_the_estimate(tmp_path, offline, monkeypatch):
    """The web worker (jobs.run_phase on the public site): a job far over the line limit fails with the
    estimate's refusal, its page's text and code; one under it gets the note of the estimate as an event in
    the page's words, and the estimate beside the lines in the funnel (job_funnel). The estimate's two
    disagreements can be counted: a job it refused keeps its estimate ("refused_estimate"), a job it let go on
    that the early check refused keeps its estimate and the lines it stopped at ("refused_after_estimate",
    "refused_lines"); neither writes the finished searches' FUNNEL_STEPS."""
    import sqlite3
    import jobs as jb
    import osm
    import progress
    import search
    from settings import Limits
    monkeypatch.setattr(sys, "stdout", sys.stdout)  # run_phase in this process: what it changes is put back
    monkeypatch.setattr(progress, "TEXT_INTERVAL", progress.TEXT_INTERVAL)
    monkeypatch.setattr(progress, "_listeners", list(progress._listeners))
    monkeypatch.setattr(osm, "BEFORE_REQUEST", osm.BEFORE_REQUEST)
    seen = _estimates(monkeypatch)
    jobs = jb.Jobs(str(tmp_path), public=True)
    request = {"params": {"elevation_file": CLIP, "water": "off", "fill_gaps": "off", "nmpt": "off", "ortho": "never",
                          **POINT}, "geometry": None}
    rows = {}
    for name, lines_max, factor in (("refused", 10, search.REFUSE_FACTOR), ("accepted", 1_000_000, search.REFUSE_FACTOR),
                                    ("stopped", 10, float("inf"))):  # the estimate lets it go on: the early check stops it
        monkeypatch.setattr(search, "REFUSE_FACTOR", factor)
        limits = Limits(lines_max=lines_max)
        job = jobs.add(request, name, user_id=7)
        jobs.claim("queued", "downloading", "w1")
        jb.run_phase(str(tmp_path), job, "download", limits, True)
        jobs.claim("ready", "computing", "w1")
        jb.run_phase(str(tmp_path), job, "compute", limits, True)
        db = sqlite3.connect(tmp_path / "jobs.sqlite")
        funnel = dict(db.execute("SELECT step, count FROM job_funnel WHERE job_id = ?", (job,)).fetchall())
        db.close()
        rows[name] = (jobs.get(job), [e["data"] for e in jobs.events(0, job) if e["kind"] in ("info", "warning")],
                      funnel, int(round(seen[-1][0])))
        gc.collect()
    row, said, funnel, estimate = rows["refused"]
    assert row["status"] == "failed" and json.loads(row["error_info"])["code"] == "too_many_lines_estimate", row
    assert row["error"].startswith("About ") and "at most 10 on this site. To find fewer lines" in row["error"], row
    assert funnel == {"refused_estimate": estimate} and estimate > 12, funnel
    row, said, funnel, estimate = rows["stopped"]
    info = json.loads(row["error_info"])
    assert row["status"] == "failed" and info["code"] == "too_many_lines_early", row
    assert funnel == {"refused_after_estimate": estimate, "refused_lines": info["params"]["n"]} and estimate > 12
    assert info["params"]["n"] > 10, funnel
    row, said, funnel, estimate = rows["accepted"]
    assert row["status"] == "done", row["error"]
    notes = [text for text in said if text.startswith("About ") and text.endswith(" with these settings.")]
    assert len(notes) == 1 and "--" not in notes[0] and "estimated" not in notes[0], said
    assert notes[0] == f"About {search._lines_text(estimate)} lines (" + notes[0].split(" lines (")[1], notes
    assert set(funnel) == set(jb.FUNNEL_STEPS) and funnel["estimate"] == estimate and funnel["lines"] > 0, funnel


def test_the_estimates_texts(monkeypatch):
    """The texts of the estimate (spec-search.md 2.2, "Seen"): two significant digits, in millions from a
    million, plain numbers below (never an exponent or a fraction of a million), the warning that it is close
    (none for an estimate of no line), both refusals with the advice."""
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
    assert events[1][0] == "warning" and events[1][1].params == {"max": 1_500_000, "limit": "1.5 million"}
    shown = []
    for estimate, se in ((42_312, 1_800), (870, 400), (987_000, 150_000), (0, 0)):
        events.clear()
        search._estimate_check(plan, estimate, se, 0)
        shown += [text.web_text() for _, text in events]
    assert shown == ["About 42 000 lines (39 000 to 46 000) with these settings.",
                     "About 870 lines (70 to 1 700) with these settings.",
                     "About 990 000 lines (690 000 to 1.3 million) with these settings.",
                     "About 0 lines (0 to 0) with these settings."]
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 24_300_000, 1_700_000, 0)
    advice = messages.line_advice(plan.params)
    assert error.value.code == "too_many_lines_estimate" and error.value.params == {
        "n": 24_300_000, "lo": 20_900_000, "hi": 27_700_000, "about": "24 million", "low": "21", "high": "28 million",
        "max": 1_500_000, "limit": "1.5 million", "advice": advice}
    assert error.value.web_text() == ("About 24 million lines (21 to 28 million) with these settings, at most "
                                      f"1.5 million on this site. {messages.advice_text(advice)}")
    assert "--same-line-square 5; --end-zone 0;" in str(error.value)
    plan.limits, plan.memory = None, int(search.memory_needed(1000, 2_000_000))
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 2_600_000, 100_000, 1000)
    assert error.value.code == "too_many_lines_memory_estimate" and error.value.params["max"] == 2_000_000
    assert error.value.web_text().startswith("About 2.6 million lines (2.4 to 2.8 million) with these settings, "
                                             "at most 2 million fit into the memory of this site. To find fewer")
    # a small memory (the grids and 40 lines; then the grids alone): whole numbers, no limit of 0
    texts = []
    for lines, estimate in ((40, 120), (40, 35), (0, 0)):
        events.clear()
        plan.memory = int(search.memory_needed(1000, lines))
        try:
            search._estimate_check(plan, estimate, estimate / 4, 1000)
        except search.SearchError as refused:
            events.append(("error", refused))
        texts += [text.web_text() for _, text in events]
    assert texts == ["About 120 lines (60 to 180) with these settings, at most 40 fit into the memory of this site. "
                     + messages.advice_text(advice),
                     "About 35 lines (18 to 52) with these settings.",
                     "That is close to this site's limit of 40: the search goes on and stops if it passes it.",
                     "About 0 lines (0 to 0) with these settings."]
    assert not [t for t in texts + shown if "e-" in t or "0 million" in t or "0." in t.split(" lines")[0]]


def _node_ready() -> bool:
    import shutil
    return shutil.which("node") is not None and os.path.isdir(os.path.join(REPO, "viewer", "node_modules", "esbuild"))


def test_the_estimates_texts_in_the_page(tmp_path):
    """The page renders the estimate's notes and refusals as the server writes them (viewer/src/i18n.ts
    errorText, detailMessage): the same words for the same values, in millions and below, with the advice."""
    from types import SimpleNamespace
    import messages
    import params as pm
    import search
    from settings import Limits
    if not _node_ready():
        pytest.skip("needs Node and `npm install` in viewer/")
    from test_viewer import run_ts
    infos = []
    plan = SimpleNamespace(limits=Limits(lines_max=1_500_000), memory=None, funnel={},
                           emit=lambda kind, text: infos.append(text.info()),
                           params=pm.SearchParams(lat=50, lon=19, model="sag", end_zone=5, anchor_lift=2))
    for estimate, se in ((1_300_000, 150_000), (42_312, 1_800), (870, 400)):
        search._estimate_check(plan, estimate, se, 0)
    with pytest.raises(search.SearchError) as error:
        search._estimate_check(plan, 24_300_000, 1_700_000, 0)
    plan.limits, plan.memory = None, int(search.memory_needed(1000, 40))
    with pytest.raises(search.SearchError) as memory:
        search._estimate_check(plan, 120, 30, 1000)
    cases = infos + [error.value.detail(), memory.value.detail()]
    found = run_ts(tmp_path, "i18n", f"""
console.log(JSON.stringify({json.dumps(cases)}.map((d) => m.detailMessage(d, "fallback"))));""")
    python = [messages.text(f"error.{c['code']}", **messages.web_params(c["params"])) for c in cases]
    assert found == python, (found, python)
    assert found[:4] == ["About 1.3 million lines (1 to 1.6 million) with these settings.",
                         "That is close to this site's limit of 1.5 million: the search goes on and stops if it passes it.",
                         "About 42 000 lines (39 000 to 46 000) with these settings.",
                         "About 870 lines (70 to 1 700) with these settings."]
    assert found[4] == error.value.web_text() and "1.5 million on this site. To find fewer lines" in found[4]
    assert found[5].startswith("About 120 lines (60 to 180) with these settings, at most 40 fit into the memory")


def test_the_page_shows_the_estimate_as_its_own_phase(tmp_path):
    """The job page's bar (viewer/src/app/useJobs.ts jobProgress) runs from 0 to 1 over the estimate of a tiled
    search ("Estimate, tile k/n · Step 2/5", "Step 3/5" of each tile) and of one grid ("Step 3/5: estimating"),
    never back within it, and the search's own tiles then start their own bar (a 9-tile search's first tile at
    its step 2 is near 0, as before)."""
    import subprocess
    if not _node_ready():
        pytest.skip("needs Node and `npm install` in viewer/")
    viewer = os.path.join(REPO, "viewer")
    bundle = tmp_path / "useJobs.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: ['src/app/useJobs.ts'], bundle: true, "
                                  f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=viewer, check=True)
    steps = [f"Estimate, tile {t}/9 · Step {s}/5: {what}" for t in range(1, 10)
             for s, what in ((2, "finding significant slopes"), (3, "estimating the lines"))]
    states = [(step, share) for step in steps for share in (0.0, 0.5, 1.0)]
    states += [("Step 3/5: estimating the lines", share) for share in (0.0, 0.5, 1.0)]
    states += [("Tile 1/9 · Step 2/5: finding significant slopes", 0.5), ("Step 1/5: preparing the data", 0.5)]
    script = tmp_path / "progress.cjs"
    script.write_text(f"""globalThis.document = {{querySelector: () => null}};  // api.ts reads the page's meta tags
const m = require({json.dumps(str(bundle))});
const job = (step, share) => ({{id: "j", created: "", status: "computing", title: "t", run_id: null, error: null,
  finished: null, log: [], step, bars: {{Compute: {{bar: "Compute", stage: "x", count: share * 10, total: 10, unit: "",
  extra: {{}}, done: false}}}}}});
console.log(JSON.stringify({json.dumps(states)}.map(([step, share]) => m.jobProgress(job(step, share)).fraction)));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True)
    fractions = json.loads(result.stdout)
    tiled, grid, after = fractions[:54], fractions[54:57], fractions[57:]
    assert tiled[0] == 0 and tiled[-1] == 1 and all(b >= a for a, b in zip(tiled, tiled[1:])), tiled
    assert abs(tiled[3 * 3 + 1] - (1 + 1.5 / 2) / 9) < 1e-9  # tile 2, step 3, half way: (1 + (1 + 0.5) / 2) / 9
    assert grid == [0, 0.5, 1]
    assert abs(after[0] - (1.5 / 5) / 9) < 1e-9 and abs(after[1] - 0.5 / 5) < 1e-9  # the search's own steps as before
