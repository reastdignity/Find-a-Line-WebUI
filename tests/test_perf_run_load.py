"""tools/perf_run_load.py: its pure parts (the first line of a data.js, the gzipped size, the summaries and the
report). The browser's part runs by hand (docs/performance.md, "Loading a run in the browser")."""

import gzip
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import perf_run_load as prl  # noqa: E402


def _data_js(path, rows):
    head = '{"run":{"id":"r"},"area":{"type":"Polygon"},"lines":['
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.FINDALINE_RUN = " + head + ",".join(rows) + "]};\n")


def test_first_line_is_the_rows_anchors_as_written(tmp_path):
    path = tmp_path / "data.js"
    _data_js(path, ["[49.1234567,19.7654321,49.1240001,19.7660002,1.5,2,NaN,null]", "[1,2,3,4]"])
    assert prl.first_line(str(path)) == "49.1234567,19.7654321,49.1240001,19.7660002"


def test_gzip_size_as_gzip(tmp_path):
    path = tmp_path / "data.js"
    _data_js(path, [f"[{k},{k + 0.5},{k * 3},{k},1,2]" for k in range(20000)])
    size = prl.gzip_size(str(path), level=5)
    expected = len(gzip.compress(path.read_bytes(), compresslevel=5))
    assert abs(size - expected) < 64  # the same deflate stream, a header of its own


def _measures(lines_ms, group_ms, count=1000):
    return [{"name": "fal:run:script", "ms": 900.0, "detail": None},
            {"name": "fal:run:lines", "ms": lines_ms, "detail": {"count": count}},
            {"name": "fal:run:group", "ms": group_ms, "detail": {"count": count}},
            {"name": "fal:run:group", "ms": 1.0, "detail": {"count": 10}}]  # a later change of the filters


def test_summarize_result_takes_the_first_measure_and_medians():
    rounds = [{"measures": _measures(100.0, 50.0), "file": {"start": 10, "end": 410}, "ready": 2000,
               "longtasks": [[0, 300], [500, 900]], "heap": 2 ** 30, "errors": []},
              {"measures": _measures(300.0, 70.0), "file": {"start": 10, "end": 210}, "ready": 3000,
               "longtasks": [[0, 100]], "heap": 2 ** 29, "errors": ["boom"]},
              {"measures": _measures(200.0, 60.0), "file": None, "ready": 2500, "longtasks": [], "heap": None,
               "errors": []}]
    out = prl.summarize_result(rounds)
    assert out["count"] == 1000
    assert out["lines"] == 200.0 and out["group"] == 60.0 and out["script"] == 900.0
    assert out["transfer"] == 300.0  # the rounds with a resource timing only
    assert out["download"] is None and out["parse"] is None  # a script's load: no such phases
    assert out["ready"] == 2500 and out["longest_task"] == 100 and out["long_tasks"] == 100
    assert out["heap_mb"] == 768 and out["errors"] == ["boom"]


def test_summarize_compare_and_3d():
    trials = [{"script": 10, "fetch": 2, "parse": 5, "error": None, "lines": 7, "parsed": 7},
              {"script": 12, "fetch": 4, "parse": 7, "error": None, "lines": 7, "parsed": 7}]
    assert prl.summarize_compare(trials) == {"script": 11, "fetch": 3, "parse": 6, "json_ok": True, "error": None}
    trials[1].update(error="SyntaxError: Unexpected token 'N'", parsed=None)
    assert prl.summarize_compare(trials)["json_ok"] is False
    page = {"measures": [{"name": "fal:3d:mesh", "ms": 300.0, "detail": None},
                         {"name": "fal:3d:imagery", "ms": 1500.0, "detail": {"kind": "ortho", "tiles": 90}}],
            "file": {"request": 100.0, "response": 2600.0, "bytes": 3 * 2 ** 20}, "ready_at": 4000.0, "error": None}
    out = prl.summarize_3d(page)
    assert out["server"] == 2500.0 and out["patch_mb"] == 3 and out["mesh"] == 300.0
    assert out["imagery"] == 1500.0 and out["tiles"] == 90 and out["ready"] == 4000.0 and out["body"] is None


def test_markdown_has_every_table():
    result = prl.summarize_result([{"measures": _measures(100.0, 50.0), "file": None, "ready": 1000,
                                    "longtasks": [], "heap": None, "errors": []}])
    compare = prl.summarize_compare([{"script": 10, "fetch": 2, "parse": 5, "error": "SyntaxError", "lines": 7,
                                      "parsed": None}])
    view = prl.summarize_3d({"measures": [], "file": None, "ready_at": None, "error": "no patch"})
    text = prl.markdown({"browser": "1.0", "rounds": 1, "runs": [
        {"id": "run-a", "size": {"bytes": 2 ** 20, "gzip": 2 ** 18}, "result": result, "compare": compare,
         "view3d": {"full": view}}]})
    assert "| run-a | 1000 | 1.0 | 0.2 |" in text
    assert "no: SyntaxError" in text and "| run-a | full |" in text and "no patch" in text


def test_markdown_tables_have_as_many_delimiters_as_headers():
    result = prl.summarize_result([{"measures": _measures(100.0, 50.0), "file": None, "ready": 1000,
                                    "longtasks": [], "heap": None, "errors": []}])
    compare = prl.summarize_compare([{"script": 10, "fetch": 2, "parse": 5, "error": None, "lines": 7, "parsed": 7}])
    view = prl.summarize_3d({"measures": [], "file": None, "ready_at": None, "error": None})
    lines = prl.markdown({"browser": "1.0", "rounds": 1, "runs": [
        {"id": "r", "size": {"bytes": 1, "gzip": 1}, "result": result, "compare": compare,
         "view3d": {"full": view}}]}).splitlines()
    for k, line in enumerate(lines):
        if line.startswith("|---"):  # a table's delimiter row: its header above, its rows below
            columns = lines[k - 1].count("|")
            assert line.count("|") == columns and lines[k + 1].count("|") == columns, lines[k - 1]
