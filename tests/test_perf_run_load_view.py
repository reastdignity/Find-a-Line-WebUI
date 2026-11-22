"""tools/perf_run_load.py's pass over the result view (`--view`, `--interact`): the summaries of the view's phases
and of the changes timed on the open page, and their tables in the report (the pure parts; the browser's part is
run by hand: docs/performance.md)."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import perf_run_load as prl  # noqa: E402


def _round(page: str, first: float, changes: list) -> dict:
    measures = [{"name": "fal:run:lines", "ms": 5.0, "detail": {"count": 1234}}]
    if page == "view":
        measures += [{"name": "fal:view:pass", "ms": first, "detail": None}, {"name": "fal:view:first", "ms": 10 * first, "detail": None},
                     {"name": "fal:view:pass", "ms": 99.0, "detail": None}]  # a later change: the first one counts
    return {"measures": measures, "source": "store", "page": page, "ready": 800.0, "heap": 50 * 2 ** 20, "longtasks": [],
            "file": {"start": 0, "end": 40}, "errors": [],
            "interact": [{"kind": kind, "sync": sync, "total": total} for kind, sync, total in changes]}


def test_view_phases_and_changes_are_medians():
    rounds = [_round("view", 2.0, [("filter on", 3.0, 30.0), ("best 30", 1.0, 20.0)]),
              _round("view", 4.0, [("filter on", 5.0, 50.0), ("best 30", 2.0, 21.0), ("lines from here", 7.0, 40.0)]),
              _round("view", 9.0, [("filter on", 4.0, 31.0), ("best 30", 9.0, 90.0)])]
    result = prl.summarize_result(rounds)
    assert result["page"] == "view" and result["count"] == 1234
    assert result["view"]["pass"] == 4.0 and result["view"]["first"] == 40.0  # each round's first measure, the median
    assert result["view"]["fan"] is None and list(result["view"]) == [name.split(":")[-1] for name in prl.VIEW_PHASES]
    changes = prl.summarize_interact(rounds)
    assert list(changes) == ["filter on", "best 30", "lines from here"]  # in the order they were made
    assert changes["filter on"] == {"sync": 4.0, "total": 31.0} and changes["best 30"] == {"sync": 2.0, "total": 21.0}
    assert changes["lines from here"] == {"sync": 7.0, "total": 40.0}
    # today's page: no phases of the view, its own changes
    today = [_round("today", 0, [("filter on", 900.0, 1200.0), ("grouping wider", 1300.0, 1500.0)])]
    assert "view" not in prl.summarize_result(today) and prl.summarize_result(today)["page"] == "today"
    assert prl.summarize_interact(today) == {"filter on": {"sync": 900.0, "total": 1200.0},
                                             "grouping wider": {"sync": 1300.0, "total": 1500.0}}
    assert prl.summarize_interact([{"measures": []}]) == {}


def test_report_has_the_views_tables():
    rounds = [_round("view", 2.0, [("filter on", 3.0, 30.0), ("lines from here", 7.5, 40.25)])]
    size = {"bytes": 2 ** 20, "gzip": 2 ** 19}
    compare = {"script": 100.0, "fetch": 50.0, "parse": 60.0, "json_ok": True, "error": None}
    run = {"id": "r1", "result": prl.summarize_result(rounds), "interact": prl.summarize_interact(rounds), "size": size,
           "compare": compare}
    plain = {"id": "r0", "result": prl.summarize_result([_round("today", 0, [])]), "size": size, "compare": compare}
    text = prl.markdown({"browser": "x", "rounds": 1, "runs": [run, plain]})
    lines = text.splitlines()
    at = lines.index("## The result view's phases at the first draw (ms)")
    assert lines[at + 2].count("|") == lines[at + 3].count("|") == lines[at + 4].count("|") == len(prl.VIEW_PHASES) + 2
    assert lines[at + 4].startswith("| r1 | 20.0 | 2.0 |") and lines[at + 5] == ""  # only the run the view drew
    at = lines.index("## Changes on the open page (ms)")
    assert lines[at + 2] == "| run | page | change | in script | to the second frame |"
    assert lines[at + 4:at + 7] == ["| r1 | view | filter on | 3.0 | 30.0 |", "| r1 | view | lines from here | 7.5 | 40.2 |", ""]
    assert lines.index("## Changes on the open page (ms)") < lines.index("## data.js as a script against fetch + JSON.parse (from the HTTP cache)")
    # without the view and the changes the report is as before
    before = prl.markdown({"browser": "x", "rounds": 1, "runs": [plain]})
    assert "result view" not in before and "Changes on the open page" not in before


def test_the_changes_script_times_both_pages():
    """The page's script of the changes asks the result view's model first, then today's (each by its own global)."""
    script = prl.INTERACT
    assert script.index("window.FINDALINE_VIEW") < script.index("if (shown)") < script.index("else if (today)")
    for change in ("setTopOnly(false)", "setBest(30)", 'setLevel("lines")', "openFan(", "closeFan()", "setFilters(", "setState("):
        assert change in script, change
