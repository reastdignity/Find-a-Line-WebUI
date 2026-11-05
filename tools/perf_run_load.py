"""
Where the time of opening a run's result and a line's 3D view goes in the browser (docs/performance.md,
"Loading a run in the browser"). The local app runs on a scratch data folder, where the given runs and the
cache are linked, never copied. Each run is opened in headless Chromium (Playwright, group `ui` of
pyproject.toml), with a fresh profile every round. The page's User Timing measures (viewer/src/perf.ts:
"fal:run:*", "fal:3d:*") give the loading phases. The main thread's long tasks and the JS heap come with them.

On the same origin, a run's data.js is then loaded as a script and compared with fetch + JSON.parse of the
same text. This shows whether parsing it as JSON is faster, and whether JSON.parse accepts the file at all
(it refuses the NaN and Infinity that runs.column_texts may write). The 3D view of each run's first line is
opened at the levels asked; the patch's request and body come from its resource timing.

    uv sync --group ui
    uv run playwright install chromium
    uv run tools/perf_run_load.py --runs <id> [<id> ...] --out <folder> [--rounds 3] [--levels full,phone]

The downloads here go over loopback. The table therefore adds each data.js gzipped as nginx sends it
(level 5) and the time that takes at a few line rates. Results go to <out>/perf_run_load.json and .md. The
scratch data folder is removed at the end, all but its jobs.sqlite, which the app's worker holds open until the
process ends (its links to the cache are gone by then).
Run it under `tools/test_lock.py run --exclusive`: it measures times.
"""

import argparse
import json
import os
import shutil
import socket
import statistics
import sys
import tempfile
import threading
import time
import zlib
from urllib.parse import quote

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

RATES_MBIT = (10, 50, 200)  # line rates of the gzipped download estimate
GZIP_LEVEL = 5  # deploy/nginx/findaline.conf gzip_comp_level
VIEWPORT = {"width": 1400, "height": 900}  # the desktop of tools/ui_shots.py: the result in columns
HEAD_MAX = 32 * 1024 * 1024  # bytes of data.js read to find its first line
RUN_COPY = ("data.js", "run.json", "ATTRIBUTION.txt")  # what the result and the 3D view read of a run
# data.js read as a script (before 2026-11-04, a map from disk, a file JSON.parse refuses) or fetched and parsed
PHASES = ("fal:run:script", "fal:run:download", "fal:run:parse", "fal:run:lines", "fal:run:filter", "fal:run:group", "fal:run:ranges", "fal:run:rows")
PHASES_3D = ("fal:3d:request", "fal:3d:body", "fal:3d:decode", "fal:3d:mesh", "fal:3d:first-frame",
             "fal:3d:profile", "fal:3d:imagery")

# Every long task of the main thread (over 50 ms) from the page's start, before its own scripts run
LONG_TASKS = """
window.__falLongTasks = [];
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__falLongTasks.push([e.startTime, e.duration]);
  }).observe({type: "longtask", buffered: true});
} catch (e) { /* no Long Tasks API */ }
"""

# What a page measured, two frames after it showed its result (the first drawing of the map is in them)
COLLECT = """
async (resource) => {
  await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done))));
  const ready = performance.now();
  const measures = performance.getEntriesByType("measure").filter((m) => m.name.startsWith("fal:"))
    .map((m) => ({name: m.name, start: m.startTime, ms: m.duration, detail: m.detail ?? null}));
  const files = performance.getEntriesByType("resource").filter((r) => new URL(r.name).pathname.endsWith(resource))
    .map((r) => ({start: r.startTime, request: r.requestStart, response: r.responseStart, end: r.responseEnd,
                  bytes: r.decodedBodySize, transferred: r.transferSize}));
  return {ready, measures, file: files[0] ?? null, longtasks: window.__falLongTasks || [],
          heap: performance.memory ? performance.memory.usedJSHeapSize : null};
}
"""

# data.js as a <script> (the loader of today) against fetch + JSON.parse of the same text, `rounds` times in
# turn, with a garbage collection before each (Chromium started with --expose-gc); both read it from the
# HTTP cache warmed by the result's page
COMPARE = """
async ({url, rounds}) => {
  const out = [];
  for (let r = 0; r < rounds; r++) {
    if (window.gc) gc();
    let t0 = performance.now();
    await new Promise((ok, bad) => {
      const s = document.createElement("script");
      s.src = url;
      s.onload = () => { s.remove(); ok(); };
      s.onerror = () => { s.remove(); bad(new Error("script failed")); };
      document.head.appendChild(s);
    });
    const script = performance.now() - t0;
    const lines = window.FINDALINE_RUN ? window.FINDALINE_RUN.lines.length : null;
    delete window.FINDALINE_RUN;
    if (window.gc) gc();
    t0 = performance.now();
    const text = await (await fetch(url)).text();
    const fetched = performance.now() - t0;
    t0 = performance.now();
    let error = null, parsed = null;
    try {
      parsed = JSON.parse(text.slice(text.indexOf(" = ") + 3, text.lastIndexOf(";"))).lines.length;
    } catch (e) {
      error = String(e).slice(0, 200);
    }
    const parse = performance.now() - t0;
    out.push({script, fetch: fetched, parse, error, lines, parsed});
  }
  return out;
}
"""

VIEW3D_DONE = ("() => { const v = document.getElementById('view3d'); return !!v && (v.dataset.ready === '1' || "
               "!!document.querySelector('.v3-error')); }")
IMAGERY_DONE = ("() => performance.getEntriesByType('measure').some((m) => m.name === 'fal:3d:imagery') || "
                "!document.querySelector('.v3-imagery-status') || document.querySelector('.v3-imagery-status').hidden")


def first_line(path: str) -> str:
    """The first line of a run's data.js as the links name it (keys.lineCoords: its row's first four values as
    written), read from its start only (a large run's file is 100 MB)."""
    with open(path, encoding="utf-8") as f:
        text = f.read(HEAD_MAX)
    at = text.find('"lines":[[')
    if at < 0:
        raise ValueError(f"no lines in the first {HEAD_MAX} bytes of {path}")
    values = text[at + len('"lines":[['):].split(",", 4)[:4]
    return ",".join(v.strip() for v in values)


def gzip_size(path: str, level: int = GZIP_LEVEL) -> int:
    """The bytes of a file gzipped at `level`, as nginx's gzip sends it."""
    gz = zlib.compressobj(level, zlib.DEFLATED, 31)
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            size += len(gz.compress(chunk))
    return size + len(gz.flush())


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def phase_ms(measures, name: str):
    """The first measure `name` of a page (the model's phases repeat with every change of the filters)."""
    return next((m["ms"] for m in measures if m["name"] == name), None)


def phase_detail(measures, name: str):
    return next((m["detail"] for m in measures if m["name"] == name), None)


def summarize_result(rounds: list) -> dict:
    """The medians of a run's rounds of the result's page: each phase, the time to the result shown, the
    longest task and the long tasks' sum, the heap; the line count from the phase "lines"."""
    detail = next((phase_detail(r["measures"], "fal:run:lines") for r in rounds if r.get("measures")), None) or {}
    out = {"count": detail.get("count"), "rounds": len(rounds),
           "errors": sorted({e for r in rounds for e in r.get("errors", [])})}
    for name in PHASES:
        out[name.split(":")[-1]] = median(phase_ms(r["measures"], name) for r in rounds)
    out["transfer"] = median(r["file"]["end"] - r["file"]["start"] if r.get("file") else None for r in rounds)
    out["ready"] = median(r.get("ready") for r in rounds)
    out["longest_task"] = median(max((d for _, d in r.get("longtasks", [])), default=0) for r in rounds)
    out["long_tasks"] = median(sum(d for _, d in r.get("longtasks", [])) for r in rounds)
    out["heap_mb"] = median(r["heap"] / 2 ** 20 if r.get("heap") else None for r in rounds)
    return out


def summarize_compare(trials: list) -> dict:
    """The medians of the script against fetch + JSON.parse; `json_ok`: JSON.parse read every line."""
    return {"script": median(t["script"] for t in trials), "fetch": median(t["fetch"] for t in trials),
            "parse": median(t["parse"] for t in trials),
            "json_ok": all(t["error"] is None and t["parsed"] == t["lines"] for t in trials),
            "error": next((t["error"] for t in trials if t["error"]), None)}


def summarize_3d(page: dict) -> dict:
    """A 3D view's phases: the server's part of the patch (its request until the answer's first byte), the
    body, each measure, the time to drawn and profiled (ready) and the imagery's tiles."""
    measures = page.get("measures", [])
    out = {name.split(":")[-1]: phase_ms(measures, name) for name in PHASES_3D}
    patch = page.get("file")
    out["server"] = patch["response"] - patch["request"] if patch and patch["request"] else None
    out["patch_mb"] = patch["bytes"] / 2 ** 20 if patch else None
    out["ready"] = page.get("ready_at")
    out["tiles"] = (phase_detail(measures, "fal:3d:imagery") or {}).get("tiles")
    out["error"] = page.get("error")
    return out


def _s(ms) -> str:
    return "" if ms is None else f"{ms / 1000:.2f}"


def markdown(results: dict) -> str:
    """The report's tables (seconds unless named)."""
    out = ["# Loading a run in the browser", "",
           f"Chromium {results['browser']}, {results['rounds']} rounds per run, medians; seconds unless named.", "",
           "## The result's page", "",
           "| run | lines | data.js MB | gzip MB | " + " | ".join(f"gzip at {r} Mbit/s" for r in RATES_MBIT) +
           " | transfer (loopback) | script | download | parse | lines | filter | group | ranges | rows | shown | longest task | "
           "long tasks | heap MB |",
           "|" + "---|" * (17 + len(RATES_MBIT))]
    for run in results["runs"]:
        r, size = run["result"], run["size"]
        rates = [_s(size["gzip"] * 8 / (rate * 1e6) * 1000) for rate in RATES_MBIT]
        out.append(f"| {run['id']} | {r['count']} | {size['bytes'] / 2 ** 20:.1f} | {size['gzip'] / 2 ** 20:.1f} | "
                   + " | ".join(rates) + " | " + " | ".join(_s(r[k]) for k in (
                       "transfer", "script", "download", "parse", "lines", "filter", "group", "ranges", "rows", "ready", "longest_task",
                       "long_tasks")) + f" | {'' if r['heap_mb'] is None else round(r['heap_mb'])} |")
    out += ["", "*transfer*: data.js's resource timing; *script*: from the request to its load event (download and parse); "
            "*download*, *parse*: fetched with its bytes counted, then JSON.parse (result/load.ts); *shown*: from the "
            "page's start to the result drawn.", "",
            "## data.js as a script against fetch + JSON.parse (from the HTTP cache)", "",
            "| run | script | fetch + text | JSON.parse | fetch + JSON.parse | JSON.parse reads it |", "|---|---|---|---|---|---|"]
    for run in results["runs"]:
        c = run["compare"]
        both = None if c["fetch"] is None or c["parse"] is None else c["fetch"] + c["parse"]
        ok = "yes" if c["json_ok"] else f"no: {c['error']}"
        out.append(f"| {run['id']} | {_s(c['script'])} | {_s(c['fetch'])} | {_s(c['parse'])} | {_s(both)} | {ok} |")
    if any(run.get("view3d") for run in results["runs"]):
        out += ["", "## The 3D view of the run's first line", "",
                "| run | level | server | patch MB | body | decode | mesh | first frame | profile | imagery | tiles | "
                "ready | error |", "|" + "---|" * 13]
        for run in results["runs"]:
            for level, v in (run.get("view3d") or {}).items():
                out.append(f"| {run['id']} | {level} | " + " | ".join(_s(v[k]) for k in (
                    "server",)) + f" | {'' if v['patch_mb'] is None else f'{v['patch_mb']:.2f}'} | " +
                    " | ".join(_s(v[k]) for k in ("body", "decode", "mesh", "first-frame", "profile", "imagery")) +
                    f" | {v['tiles'] or ''} | {_s(v['ready'])} | {v['error'] or ''} |")
        out += ["", "*server*: the patch's request until its first byte (the quick lane's queue and step 1); "
                "*ready*: from the page's start to the terrain drawn and the profile in."]
    return "\n".join(out) + "\n"


def _unlink(path: str):
    """A directory link removed without its target (a junction on Windows, a symlink elsewhere)."""
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isjunction(path):
        os.rmdir(path)


def scratch_data(folder: str, runs_dir: str, cache_dir: str, runs: list) -> list:
    """A data folder in `folder` with the cache linked and each run's files of RUN_COPY copied (the local app's
    /runs follows no link out of its folder); the links made (for _unlink)."""
    sys.path.insert(0, os.path.join(REPO, "tests"))
    from regression import link
    os.makedirs(os.path.join(folder, "runs"), exist_ok=True)
    links = [os.path.join(folder, "cache")]
    link(cache_dir, links[0])
    for run in runs:
        source, target = os.path.join(runs_dir, run), os.path.join(folder, "runs", run)
        if not os.path.isfile(os.path.join(source, "data.js")):
            raise SystemExit(f"no data.js in {source}")
        os.makedirs(target, exist_ok=True)
        for name in RUN_COPY:
            if os.path.isfile(os.path.join(source, name)):
                shutil.copy2(os.path.join(source, name), target)
    return links


def serve(data: str):
    """The local app with its worker (the quick lane answers the 3D view's patches) on a free port of
    127.0.0.1: (address, stop)."""
    import uvicorn

    import web
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = web.create_app(data, port=port)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)

    def stop():
        server.should_exit = True
        thread.join(timeout=30)
    return f"http://127.0.0.1:{port}", stop


def open_result(browser, site: str, run: str, timeout: float, out: str, keep_page: bool = False):
    """One round of a run's result in a fresh profile: its measures; with keep_page also (context, page).
    A result that does not show stops the tool, with a screenshot in `out`."""
    context = browser.new_context(viewport=VIEWPORT)
    context.add_init_script(LONG_TASKS)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.goto(f"{site}/#run={quote(run, safe='')}", wait_until="commit")
    try:
        page.wait_for_selector(".c-result, .c-result-wait .c-error", timeout=timeout * 1000)
        failed = page.evaluate("() => document.querySelector('.c-result-wait .c-error')?.textContent || null")
    except Exception as e:
        failed = str(e).splitlines()[0]
    if failed:
        shot = os.path.join(out, f"failed-{run}.png")
        page.screenshot(path=shot)
        context.close()
        raise SystemExit(f"{run}: the result did not show ({failed}; page errors {errors}; {shot})")
    found = page.evaluate(COLLECT, "/data.js")
    found["errors"] = errors
    if keep_page:
        return found, context, page
    context.close()
    return found


def open_view3d(browser, site: str, run: str, line: str, level: str, timeout: float) -> dict:
    """The 3D view of `line` at `level` in a fresh profile: its measures, the patch's resource timing, the time
    to drawn and profiled, an error shown."""
    context = browser.new_context(viewport=VIEWPORT)
    context.add_init_script(LONG_TASKS)
    page = context.new_page()
    try:
        page.goto(f"{site}/view3d?level={level}#run={quote(run, safe='')}&line={quote(line, safe='')}",
                  wait_until="commit")
        page.wait_for_function(VIEW3D_DONE, timeout=timeout * 1000, polling=100)
        ready_at = page.evaluate("() => performance.now()")
        error = page.evaluate("() => document.querySelector('.v3-error')?.textContent || null")
        if not error:
            try:
                page.wait_for_function(IMAGERY_DONE, timeout=180_000, polling=200)
            except Exception:  # the imagery still loading: its measure is left out
                pass
        found = page.evaluate(COLLECT, "/api/patch")
        found["ready_at"] = None if error else ready_at
        found["error"] = error
        return found
    except Exception as e:
        return {"measures": [], "file": None, "ready_at": None, "error": str(e).splitlines()[0][:200]}
    finally:
        context.close()


def measure(args) -> dict:
    from playwright.sync_api import sync_playwright

    data = args.data_dir or tempfile.mkdtemp(prefix="perf-run-load-", dir=args.out)
    links = scratch_data(data, args.runs_dir, args.cache, args.runs)
    site, stop = serve(data)
    results = {"rounds": args.rounds, "runs": []}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--js-flags=--expose-gc", "--enable-unsafe-swiftshader"])
            results["browser"] = browser.version
            for run in args.runs:
                path = os.path.join(args.runs_dir, run, "data.js")
                print(f"{run}: gzip size", flush=True)
                entry = {"id": run, "size": {"bytes": os.path.getsize(path), "gzip": gzip_size(path)}}
                rounds = []
                for k in range(args.rounds):
                    print(f"{run}: result, round {k + 1} of {args.rounds}", flush=True)
                    last = k == args.rounds - 1
                    found = open_result(browser, site, run, args.timeout, args.out, keep_page=last)
                    if last:
                        found, context, page = found
                        page.close()  # its model freed; the context keeps the HTTP cache
                        page = context.new_page()
                        page.goto(f"{site}/runs/{quote(run, safe='')}/run.json")
                        print(f"{run}: script against JSON.parse", flush=True)
                        trials = page.evaluate(COMPARE, {"url": f"/runs/{quote(run, safe='')}/data.js",
                                                         "rounds": args.compare_rounds})
                        context.close()
                        entry["compare_trials"] = trials
                        entry["compare"] = summarize_compare(trials)
                    rounds.append(found)
                entry["result_rounds"] = rounds
                entry["result"] = summarize_result(rounds)
                if args.levels:
                    line = first_line(path)
                    entry["line"] = line
                    entry["view3d"], entry["view3d_pages"] = {}, {}
                    for level in args.levels:
                        print(f"{run}: 3D view, {level}", flush=True)
                        page = open_view3d(browser, site, run, line, level, args.timeout)
                        entry["view3d_pages"][level] = page
                        entry["view3d"][level] = summarize_3d(page)
                results["runs"].append(entry)
            browser.close()
    finally:
        stop()
        for path in links:
            _unlink(path)
        if not args.data_dir:
            shutil.rmtree(data, ignore_errors=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--runs", nargs="+", required=True, help="the runs' folder names")
    parser.add_argument("--out", required=True, help="folder of the results (perf_run_load.json, .md)")
    parser.add_argument("--runs-dir", default=os.path.join(REPO, "runs"), help="where the runs are (default: runs/)")
    parser.add_argument("--cache", default=os.path.join(REPO, "cache"),
                        help="the cache the 3D view's patches read (default: cache/), linked")
    parser.add_argument("--data-dir", help="a scratch data folder to use (default: a new one in --out, removed)")
    parser.add_argument("--rounds", type=int, default=3, help="rounds of each run's result (default 3)")
    parser.add_argument("--compare-rounds", type=int, default=2, help="script/JSON trials (default 2)")
    parser.add_argument("--levels", default="full,phone",
                        help="the 3D view's levels, comma-separated; empty: no 3D view (default full,phone)")
    parser.add_argument("--timeout", type=float, default=600, help="seconds a page may take (default 600)")
    args = parser.parse_args()
    args.levels = [v for v in args.levels.split(",") if v]
    os.makedirs(args.out, exist_ok=True)
    results = measure(args)
    with open(os.path.join(args.out, "perf_run_load.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    report = markdown(results)
    with open(os.path.join(args.out, "perf_run_load.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
