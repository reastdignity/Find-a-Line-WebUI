"""
Where the time of opening a run's result and a line's 3D view goes in the browser (docs/performance.md,
"Loading a run in the browser"). The local app runs on a scratch data folder, where the given runs and the
cache are linked, never copied. Each run is opened in headless Chromium (Playwright, group `ui` of
pyproject.toml), with a fresh profile every round. The page's User Timing measures (viewer/src/perf.ts:
"fal:run:*", "fal:3d:*") give the loading phases. The main thread's long tasks and the JS heap come with them.
A run with a store (run.json's block "store") is read from it, as the page reads it (its runs.js in the scratch
folder lists the block); the report names the file read ("read": the store or data.js).

On the same origin, a run's data.js is then loaded as a script and compared with fetch + JSON.parse of the
same text. This shows whether parsing it as JSON is faster, and whether JSON.parse accepts the file at all
(it refuses the NaN and Infinity that runs.column_texts may write). A run saved since store wave 4 (2026-11-17)
has no data.js: its comparison is left out ("no data.js" in the report). The 3D view of each run's first line
(from its store, or the data.js of a run saved before the store) is opened at the levels asked; the patch's
request and body come from its resource timing.

    uv sync --group ui
    uv run playwright install chromium
    uv run tools/perf_run_load.py --runs <id> [<id> ...] --out <folder> [--rounds 3] [--levels full,phone]
                                  [--view] [--interact]

`--view` opens the result view of mock-up 2 (the page's flag `?view=b`; a run without the view's columns opens
today's page all the same, and the report says which page drew it); its phases are the measures "fal:view:*".
`--interact` then times changes on the open page, each from the call to two frames later (the map drawn again)
and its part in script: in the result view a filter on and off, "Top level only" off and on, Best 30 and 10, the
Lines level held and Auto again, "Lines from here" opened and closed; on today's page a filter and the grouping
distance (round 3's private t56.py, docs/line-volume/spec-store.md 1.8: T6).

The downloads here go over loopback. The table therefore adds the file read (the store, or data.js) gzipped as nginx
sends it
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
HEAD_MAX = 32 * 1024 * 1024  # bytes of data.js read to find its first line (a run without a store)
# what the result and the 3D view read of a run: its store when it has one (run.json's block "store", listed in the
# scratch folder's runs.js), else its data.js (a run saved before the store); a run of store wave 4 has no data.js
RUN_COPY = ("data.js", "lines.arrow", "profiles.arrow", "run.json", "ATTRIBUTION.txt")
STORE_FILES = ("lines.arrow", "profiles.arrow")  # linestore.FILES
# data.js read as a script (before 2026-11-04, a map from disk, a file JSON.parse refuses) or fetched and parsed
PHASES = ("fal:run:script", "fal:run:download", "fal:run:parse", "fal:run:lines", "fal:run:filter", "fal:run:group", "fal:run:ranges", "fal:run:rows")
# the result view's own phases (viewer/src/result/spots.ts, SpotMap.ts)
VIEW_PHASES = ("fal:view:first", "fal:view:pass", "fal:view:shown", "fal:view:order", "fal:view:picks", "fal:view:inview",
               "fal:view:squares", "fal:view:draw", "fal:view:fan", "fal:view:refan")
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

# Changes on the open page, each timed from its call to two frames later, with its part in script: the result
# view's (window.FINDALINE_VIEW) or today's page's (window.FINDALINE_RESULT)
INTERACT = """
async () => {
  const frames = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done))));
  const out = [];
  const timed = async (kind, change) => {
    await frames();
    const t0 = performance.now();
    change();
    const sync = performance.now() - t0;
    await frames();
    out.push({kind, sync, total: performance.now() - t0});
  };
  const shown = window.FINDALINE_VIEW, today = window.FINDALINE_RESULT;
  if (shown) {
    const {view} = shown, model = view.model, c = model.data.columns;
    await timed("filter on", () => model.setFilters({...model.filters, clrMin: 2}));
    await timed("filter off", () => model.setFilters({...model.filters, clrMin: null}));
    await timed("top level only off", () => view.setTopOnly(false));
    await timed("top level only on", () => view.setTopOnly(true));
    await timed("best 30", () => view.setBest(30));
    await timed("best 10", () => view.setBest(10));
    await timed("lines held", () => view.setLevel("lines"));
    await timed("auto again", () => view.setLevel("auto"));
    if (view.order.length) {
      const row = view.shownOf(view.order[0]);
      await timed("lines from here", () => view.openFan({lat: c.lat1.at(row), lng: c.lon1.at(row)}, {row, end: 1}));
      await timed("lines from here closed", () => view.closeFan());
    }
  } else if (today) {
    const {model} = today;
    await timed("filter on", () => model.setFilters({...model.filters, clrMin: 2}));
    await timed("filter off", () => model.setFilters({...model.filters, clrMin: null}));
    await timed("grouping wider", () => model.setState({...model.state, distance: model.data.distance * 1.5}));
    await timed("grouping back", () => model.setState({...model.state, distance: model.data.distance}));
  }
  return out;
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


def lines_read(folder: str) -> str:
    """Which file first_line reads of a run: "store" (lines.arrow) or "data.js" (a run saved before the store)."""
    return "store" if os.path.isfile(os.path.join(folder, "lines.arrow")) else "data.js"


def first_line(folder: str) -> str:
    """The first line of a run as the links name it (keys.lineCoords: its data.js row's first four values as written,
    round(value, 7)): from its store (lines.arrow, linestore.read: the same values in the same order), else from the
    start of its data.js only (a run saved before the store; a large run's file is 100 MB)."""
    if os.path.isfile(os.path.join(folder, "lines.arrow")):
        import linestore
        lines, _ = linestore.read(folder, profiles=False)
        if not len(lines):
            raise ValueError(f"no lines in the store of {folder}")
        return ",".join(str(v) for v in lines.columns["anchor1"][0].tolist() + lines.columns["anchor2"][0].tolist())
    path = os.path.join(folder, "data.js")
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


def source_of(asked: list) -> str:
    """The file a page read of its run, from the paths it asked for: "data.js" when it asked for that (a run without
    a store, or a store's file missing: the fallback), else "store" when it asked for lines.arrow."""
    if any(a.endswith("/data.js") for a in asked):
        return "data.js"
    return "store" if any(a.endswith("/lines.arrow") for a in asked) else "data.js"


def size_of(folder: str, source: str) -> dict:
    """The bytes of the file(s) a run's page read (`source`: "store", lines.arrow and profiles.arrow; else data.js)
    and gzipped as nginx sends them."""
    names = STORE_FILES if source == "store" else ("data.js",)
    paths = [os.path.join(folder, name) for name in names]
    return {"bytes": sum(os.path.getsize(p) for p in paths), "gzip": sum(gzip_size(p) for p in paths)}


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
           "errors": sorted({e for r in rounds for e in r.get("errors", [])}),
           "source": ", ".join(sorted({r["source"] for r in rounds if r.get("source")}))}
    for name in PHASES:
        out[name.split(":")[-1]] = median(phase_ms(r["measures"], name) for r in rounds)
    out["transfer"] = median(r["file"]["end"] - r["file"]["start"] if r.get("file") else None for r in rounds)
    out["ready"] = median(r.get("ready") for r in rounds)
    out["longest_task"] = median(max((d for _, d in r.get("longtasks", [])), default=0) for r in rounds)
    out["long_tasks"] = median(sum(d for _, d in r.get("longtasks", [])) for r in rounds)
    out["heap_mb"] = median(r["heap"] / 2 ** 20 if r.get("heap") else None for r in rounds)
    out["page"] = ", ".join(sorted({r["page"] for r in rounds if r.get("page")}))
    if any(m["name"].startswith("fal:view:") for r in rounds for m in r.get("measures", [])):
        out["view"] = {name.split(":")[-1]: median(phase_ms(r["measures"], name) for r in rounds) for name in VIEW_PHASES}
    return out


def summarize_interact(rounds: list) -> dict:
    """The medians of the changes timed on the open page (INTERACT), in their order: for each its part in script
    (`sync`) and the time to the second frame after it (`total`), ms."""
    kinds = []
    for r in rounds:
        kinds += [c["kind"] for c in r.get("interact") or [] if c["kind"] not in kinds]
    return {kind: {key: median(c[key] for r in rounds for c in r.get("interact") or [] if c["kind"] == kind)
                   for key in ("sync", "total")} for kind in kinds}


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


def _ms(ms) -> str:
    return "" if ms is None else f"{ms:.1f}"


def markdown(results: dict) -> str:
    """The report's tables (seconds unless named)."""
    out = ["# Loading a run in the browser", "",
           f"Chromium {results['browser']}, {results['rounds']} rounds per run, medians; seconds unless named.", "",
           "## The result's page", "",
           "| run | lines | read | file MB | gzip MB | " + " | ".join(f"gzip at {r} Mbit/s" for r in RATES_MBIT) +
           " | transfer (loopback) | script | download | parse | lines | filter | group | ranges | rows | shown | longest task | "
           "long tasks | heap MB |",
           "|" + "---|" * (18 + len(RATES_MBIT))]
    for run in results["runs"]:
        r, size = run["result"], run["size"]
        rates = [_s(size["gzip"] * 8 / (rate * 1e6) * 1000) for rate in RATES_MBIT]
        out.append(f"| {run['id']} | {r['count']} | {r.get('source') or ''} | {size['bytes'] / 2 ** 20:.1f} | "
                   f"{size['gzip'] / 2 ** 20:.1f} | "
                   + " | ".join(rates) + " | " + " | ".join(_s(r[k]) for k in (
                       "transfer", "script", "download", "parse", "lines", "filter", "group", "ranges", "rows", "ready", "longest_task",
                       "long_tasks")) + f" | {'' if r['heap_mb'] is None else round(r['heap_mb'])} |")
    out += ["", "*read*: the file the page read (the store, or data.js), whose bytes *file MB* and *gzip MB* give "
            "(the store: lines.arrow and profiles.arrow); *transfer*: that file's (lines.arrow's or "
            "data.js's) resource timing; *script*: from the request to its load event (download and parse); "
            "*download*, *parse*: fetched with its bytes counted, then JSON.parse (result/load.ts); *shown*: from the "
            "page's start to the result drawn.", "",
            "## data.js as a script against fetch + JSON.parse (from the HTTP cache)", "",
            "| run | script | fetch + text | JSON.parse | fetch + JSON.parse | JSON.parse reads it |", "|---|---|---|---|---|---|"]
    views = [run for run in results["runs"] if run["result"].get("view")]
    if views:
        names = [name.split(":")[-1] for name in VIEW_PHASES]
        out[-4:-4] = ["## The result view's phases at the first draw (ms)", "", "| run | " + " | ".join(names) + " |",
                      "|" + "---|" * (1 + len(names))] + [
            f"| {run['id']} | " + " | ".join(_ms(run["result"]["view"].get(name)) for name in names) + " |" for run in views] + [""]
    if any(run.get("interact") for run in results["runs"]):
        out[-4:-4] = ["## Changes on the open page (ms)", "", "| run | page | change | in script | to the second frame |",
                      "|---|---|---|---|---|"] + [
            f"| {run['id']} | {run['result'].get('page') or ''} | {kind} | {_ms(c['sync'])} | {_ms(c['total'])} |"
            for run in results["runs"] for kind, c in (run.get("interact") or {}).items()] + [""]
    for run in results["runs"]:
        c = run.get("compare")
        if c is None:  # a run of store wave 4: no data.js to load as a script
            out.append(f"| {run['id']} | | | | | no data.js (a run saved since store wave 4) |")
            continue
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
                "*ready*: from the page's start to the terrain drawn and the profile in. The first line read from: "
                + ", ".join(f"{run['id']} {run.get('line_read') or ''}".strip() for run in results["runs"]
                            if run.get("view3d")) + "."]
    return "\n".join(out) + "\n"


def _unlink(path: str):
    """A directory link removed without its target (a junction on Windows, a symlink elsewhere)."""
    if os.path.islink(path):
        os.unlink(path)
    elif os.path.isjunction(path):
        os.rmdir(path)


def scratch_data(folder: str, runs_dir: str, cache_dir: str, runs: list) -> list:
    """A data folder in `folder` with the cache linked, each run's files of RUN_COPY that it has copied (the local
    app's /runs follows no link out of its folder; a run needs run.json and its store or data.js) and its runs.js
    written (the page reads a run's store when its entry there has run.json's block "store"); the links made (for
    _unlink)."""
    sys.path.insert(0, os.path.join(REPO, "tests"))
    from regression import link
    os.makedirs(os.path.join(folder, "runs"), exist_ok=True)
    links = [os.path.join(folder, "cache")]
    link(cache_dir, links[0])
    for run in runs:
        source, target = os.path.join(runs_dir, run), os.path.join(folder, "runs", run)
        if not os.path.isfile(os.path.join(source, "run.json")) or not any(
                os.path.isfile(os.path.join(source, name)) for name in ("lines.arrow", "data.js")):
            raise SystemExit(f"no run.json with a store or data.js in {source}")
        os.makedirs(target, exist_ok=True)
        for name in RUN_COPY:
            if os.path.isfile(os.path.join(source, name)):
                shutil.copy2(os.path.join(source, name), target)
    import runs as rn  # runs.js as runs.write_index writes it (without its index.html)
    listed = [rn._listed(r) for r in rn.list_runs(os.path.join(folder, "runs"))]
    with open(os.path.join(folder, "runs", "runs.js"), "w", encoding="utf-8") as f:
        f.write("window.FINDALINE_RUNS = " + json.dumps(listed, ensure_ascii=False) + ";\n")
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


def open_result(browser, site: str, run: str, timeout: float, out: str, keep_page: bool = False, view: bool = False,
                interact: bool = False):
    """One round of a run's result in a fresh profile: its measures; with keep_page also (context, page).
    A result that does not show stops the tool, with a screenshot in `out`. `view`: the page is asked for the result
    view (`?view=b`; "page" says which page drew the run: "view" or "today"); `interact`: the changes of INTERACT
    are timed on the open page ("interact")."""
    context = browser.new_context(viewport=VIEWPORT)
    context.add_init_script(LONG_TASKS)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    import today_page  # without `view` today's page pinned, whatever SpotColumns.tsx VIEW_DEFAULT is
    address = f"{site}/#run={quote(run, safe='')}"
    page.goto(address.replace("/#", "/?view=b#", 1) if view else today_page.today(address), wait_until="commit")
    try:
        page.wait_for_selector(".c-result, .c-result-wait .c-error", timeout=timeout * 1000)
        failed = page.evaluate("() => document.querySelector('.c-result-wait .c-error')?.textContent || null")
        if not failed:  # the page's model and map are there (the result view: after its first draw)
            page.wait_for_function("() => !!(window.FINDALINE_VIEW || window.FINDALINE_RESULT)", timeout=timeout * 1000)
    except Exception as e:
        failed = str(e).splitlines()[0]
    if failed:
        shot = os.path.join(out, f"failed-{run}.png")
        page.screenshot(path=shot)
        context.close()
        raise SystemExit(f"{run}: the result did not show ({failed}; page errors {errors}; {shot})")
    # which file the page read: the store (lines.arrow, profiles.arrow) or data.js
    source = source_of(page.evaluate("() => performance.getEntriesByType('resource')"
                                     ".map((r) => new URL(r.name).pathname)"))
    found = page.evaluate(COLLECT, "/lines.arrow" if source == "store" else "/data.js")
    found["source"] = source
    found["page"] = page.evaluate("() => window.FINDALINE_VIEW ? 'view' : 'today'")
    print(f"{run}: read from {found['source']}, drawn by {found['page']}", flush=True)
    if interact:
        found["interact"] = page.evaluate(INTERACT)
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
                folder = os.path.join(args.runs_dir, run)
                has_script = os.path.isfile(os.path.join(folder, "data.js"))  # none since store wave 4
                entry = {"id": run, "compare": None}
                rounds = []
                for k in range(args.rounds):
                    print(f"{run}: result, round {k + 1} of {args.rounds}", flush=True)
                    last = k == args.rounds - 1 and has_script  # the comparison on the last round's page
                    found = open_result(browser, site, run, args.timeout, args.out, keep_page=last, view=args.view,
                                        interact=args.interact)
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
                if args.interact:
                    entry["interact"] = summarize_interact(rounds)
                print(f"{run}: gzip size", flush=True)
                entry["size"] = size_of(os.path.join(args.runs_dir, run), entry["result"]["source"])
                if args.levels:
                    line = first_line(folder)
                    entry["line"], entry["line_read"] = line, lines_read(folder)
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
    parser.add_argument("--view", action="store_true", help="open the result view (the page's flag ?view=b)")
    parser.add_argument("--interact", action="store_true", help="time changes on the open page (filters, levels, the fan)")
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
