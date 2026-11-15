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
    assert out["heap_mb"] == 768 and out["errors"] == ["boom"] and out["source"] == ""
    assert prl.summarize_result([{**r, "source": "data.js"} for r in rounds])["source"] == "data.js"


def test_the_file_read_and_its_size(tmp_path):
    """A row names the file its page read, with that file's bytes: the store (lines.arrow + profiles.arrow) when the
    page asked for lines.arrow and not data.js; data.js when it asked for that, also after a store's 404 (the
    fallback)."""
    assert prl.source_of(["/app/app.js", "/runs/r/lines.arrow", "/runs/r/profiles.arrow"]) == "store"
    assert prl.source_of(["/runs/r/lines.arrow", "/runs/r/profiles.arrow", "/runs/r/data.js"]) == "data.js"
    assert prl.source_of(["/runs/r/data.js"]) == "data.js"
    for name, size in (("data.js", 5000), ("lines.arrow", 3000), ("profiles.arrow", 700)):
        (tmp_path / name).write_bytes(bytes(range(256)) * (size // 256) + b"x" * (size % 256))
    store = prl.size_of(str(tmp_path), "store")
    assert store["bytes"] == 3700 and store["gzip"] == prl.gzip_size(str(tmp_path / "lines.arrow")) + \
        prl.gzip_size(str(tmp_path / "profiles.arrow"))
    assert prl.size_of(str(tmp_path), "data.js") == {"bytes": 5000, "gzip": prl.gzip_size(str(tmp_path / "data.js"))}


def test_scratch_data_lists_a_runs_store(tmp_path):
    """The scratch data folder holds each run's store beside its data.js and a runs.js that lists run.json's block
    "store", so the page reads the store there, as in the app; a run without a store is listed without one."""
    import json
    runs, cache = tmp_path / "runs", tmp_path / "cache"
    cache.mkdir()
    for run_id, store in (("with", {"format": 1, "lines": 1, "bytes": 2, "sha256": "0" * 16}), ("without", None)):
        (runs / run_id).mkdir(parents=True)
        _data_js(runs / run_id / "data.js", ["[1,2,3,4]"])
        meta = {"id": run_id, "name": run_id, "created": "2026-11-15T10:00:00+00:00", "params": {}}
        if store:
            meta["store"] = store
            for name in ("lines.arrow", "profiles.arrow"):
                (runs / run_id / name).write_bytes(b"x")
        (runs / run_id / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    scratch = tmp_path / "scratch"
    links = prl.scratch_data(str(scratch), str(runs), str(cache), ["with", "without"])
    try:
        assert sorted(os.listdir(scratch / "runs" / "with")) == ["data.js", "lines.arrow", "profiles.arrow", "run.json"]
        listed = (scratch / "runs" / "runs.js").read_text(encoding="utf-8")
        entries = {r["id"]: r.get("store") for r in json.loads(listed.split(" = ", 1)[1].split(";\n")[0])}
        assert entries == {"with": {"format": 1, "lines": 1, "bytes": 2, "sha256": "0" * 16}, "without": None}
    finally:
        for path in links:
            prl._unlink(path)


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
                                    "longtasks": [], "heap": None, "errors": [], "source": "store"}])
    compare = prl.summarize_compare([{"script": 10, "fetch": 2, "parse": 5, "error": "SyntaxError", "lines": 7,
                                      "parsed": None}])
    view = prl.summarize_3d({"measures": [], "file": None, "ready_at": None, "error": "no patch"})
    text = prl.markdown({"browser": "1.0", "rounds": 1, "runs": [
        {"id": "run-a", "size": {"bytes": 2 ** 20, "gzip": 2 ** 18}, "result": result, "compare": compare,
         "view3d": {"full": view}}]})
    assert "| run-a | 1000 | store | 1.0 | 0.2 |" in text  # the file the page read
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
