"""
Where the computing time of the web app's searches goes (F19 of docs/monitoring.md), from a
jobs.sqlite: the finished searches by class (model, resolution, longest line, circle or area,
preset), their computing seconds (sum, median, p90), the seconds and CPU seconds of every step
(job_steps) and of the stages of the line search (job_stages), and the ratios of its funnel
(job_funnel). Jobs from before migration 16 have no stages or funnel: those are read from their
"info" events (the lines the search prints, whole seconds; no CPU).

    python3 tools/job_stats.py --db <jobs.sqlite> [--days N] [--immutable] [--csv <file>] [--phases]

--phases adds what a job waited for and took outside its steps: the seconds from queued to
downloading (a download slot), of the download phase, from ready to computing (a compute slot) and
of the computing phase (the columns of migrations 13 and 15, whole seconds), the computing seconds
outside its steps (the process's start, imports and planning; the step "orthophoto" is not
subtracted: since 2026-11-02 the worker downloads it after "done", outside the phase's timestamps,
and for jobs from before that it lies inside these seconds), the steps "orthophoto" and "other",
and the tiles of an area (their number and the largest one's Mpx, from the "--- Tile k of N" lines).

Standard library only (it runs on the VPS host with the system python3, no venv); read-only
(mode=ro; --immutable for a copy that nothing writes, which also skips the WAL). The output holds
no job id, user id, title, place or outline: counts and times per class only.
"""

import argparse
import csv
import json
import re
import sqlite3
import statistics
import sys
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

# What the tool needs of params.SearchParams and params.PRESETS (tests/test_job_stats.py checks it):
# the defaults of the fields a class depends on, and the values of the presets of the kind of lines
DEFAULTS = {"model": "formula", "min_length": 30, "max_length": 1000, "max_anchor_diff_m": 50, "resolution": None}
PRESETS = {
    "typical": {"min_length": 30, "max_length": 150, "max_anchor_diff_m": 10},
    "long": {"min_length": 100, "max_length": 400},
    "short": {"min_length": 15, "max_length": 60},
}
PRESET_FIELDS = ("min_length", "max_length", "max_anchor_diff_m")
# jobs.STEP_KEYS, jobs.STAGE_KEYS, jobs.FUNNEL_STEPS (the tool imports nothing of the app)
STEP_KEYS = ("1", "2", "3", "4", "5", "orthophoto", "other")
STAGE_KEYS = ("finding anchors", "anchor prominence and drop", "sag estimator table", "free directions",
              "anchor pairs", "checking lines")
FUNNEL_STEPS = ("grids", "anchors", "anchors_kept", "open", "todo", "candidates", "checked", "found", "valid",
                "left_out", "lines")
RATIOS = (("open", "anchors_kept"), ("checked", "candidates"), ("found", "checked"), ("valid", "found"))
CLASSES = ("model", "resolution", "length", "shape", "preset")
# --phases: the seconds between the timestamps of a job (jobs.created, downloading_at, ready_at,
# computing_at, finished) and of its computing phase outside the steps
PHASE_KEYS = ("wait_download", "download", "wait_compute", "compute", "outside_steps", "orthophoto", "other")

# The lines of a search's output (tests/regression.py PATTERNS, linesearch.find_valid_lines, search._lines)
# and of the Compute bars (progress._Bar._print_text: "[Compute] <stage>: <count>/<total> ... - done in 5s")
ANCHORS = re.compile(r"Found (\d+) potential anchors")
KEPT = re.compile(r"Anchors left after the prominence and drop limits: (\d+)")
OPEN = re.compile(r"Anchors with an open direction: (\d+)")
CANDIDATES = re.compile(r"Candidate pairs between anchors with an open direction: (\d+)")
CHECKED = re.compile(r"Checked pixel by pixel: (\d+)")
LEFT_OUT = re.compile(r"Left out by the line limits \(.*\): (\d+)")
VALID = re.compile(r"Found (\d+) valid lines")
RESOLUTION = re.compile(r"resolution: ([\d.]+)m \(")
TILE = re.compile(r"--- Tile \d+ of (\d+)(?: \((\d+) x (\d+) px\))?")
PAIRS_FOUND = re.compile(r", lines (\d+) - done in")  # the extra of the bar "anchor pairs": the pairs found
BAR = re.compile(r"^\[Compute\] (.+?): ([\d.e+]+)/([\d.e+]+) .* - done in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def duration(text_h: Optional[str], text_m: Optional[str], text_s: Optional[str]) -> int:
    """The seconds of progress._duration's text ("5s", "1m05s", "2h03m")."""
    return int(text_h or 0) * 3600 + int(text_m or 0) * 60 + int(text_s or 0)


def from_events(texts: Iterable[str]) -> Tuple[Dict[str, int], Dict[str, float], Optional[float]]:
    """The funnel, the seconds of the stages and the resolution of a computing phase from its info
    lines (each tile's lines added up)."""
    funnel: Dict[str, int] = {}
    stages: Dict[str, float] = {}
    resolution, tiles, pending = None, None, None

    def add(key, n):
        funnel[key] = funnel.get(key, 0) + int(n)

    for text in texts:
        for line in text.splitlines():
            if (m := ANCHORS.search(line)):
                pending = int(m.group(1))  # kept as they are unless their limits leave some out
                add("anchors", pending)
            elif (m := KEPT.search(line)):
                pending = int(m.group(1))
            elif (m := OPEN.search(line)):
                add("grids", 1)
                add("anchors_kept", pending or 0)
                add("open", m.group(1))
            elif (m := CANDIDATES.search(line)):
                add("candidates", m.group(1))
            elif (m := CHECKED.search(line)):
                add("checked", m.group(1))
            elif (m := LEFT_OUT.search(line)):
                add("left_out", m.group(1))
            elif (m := VALID.search(line)):
                add("valid", m.group(1))
            elif (m := TILE.search(line)):
                tiles = int(m.group(1))
            elif (m := RESOLUTION.search(line)) and resolution is None:
                resolution = float(m.group(1))
            elif (m := BAR.match(line)) and m.group(1) in STAGE_KEYS:
                stages[m.group(1)] = stages.get(m.group(1), 0.0) + duration(*m.group(4, 5, 6))
                if m.group(1) == "anchor pairs":  # its total: the anchors pairs start from (":g", 6 digits)
                    add("todo", float(m.group(3)))
                    if (lines := PAIRS_FOUND.search(line)):
                        add("found", lines.group(1))
    if funnel.get("grids") and tiles is None:
        funnel["lines"] = funnel.get("valid", 0)  # one grid: every valid line is the search's
    return funnel, stages, resolution


def tiles_of(texts: Iterable[str]) -> Tuple[Optional[int], Optional[float]]:
    """(tiles, Mpx of the largest tile) of a computing phase from its "--- Tile k of N (W x H px)"
    lines; (None, None) for one grid."""
    tiles, largest = None, None
    for text in texts:
        for line in text.splitlines():
            if (m := TILE.search(line)):
                tiles = int(m.group(1))
                if m.group(2):
                    largest = max(largest or 0.0, int(m.group(2)) * int(m.group(3)) / 1e6)
    return tiles, largest


def _seconds(later: Optional[str], earlier: Optional[str]) -> Optional[float]:
    """Seconds between two ISO timestamps of jobs.sqlite (cache.now: UTC, whole seconds)."""
    if not later or not earlier:
        return None
    try:
        return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()
    except ValueError:
        return None


def phases_of(job: Dict, steps: Dict[str, Tuple[float, Optional[float]]]) -> Dict[str, Optional[float]]:
    """The seconds of PHASE_KEYS of a job: between its timestamps, and of its computing phase
    outside the steps (None where a timestamp or the steps are missing)."""
    compute = _seconds(job.get("finished"), job.get("computing_at"))
    # The orthophoto's seconds (jobs.run_phase: after "done" since 2026-11-02, so after `finished`)
    # are not subtracted: for jobs from before, the phase holds them (the column shows them)
    total = sum(s for key, (s, _) in steps.items() if key != "orthophoto") if steps else None
    return {
        "wait_download": _seconds(job.get("downloading_at"), job.get("created")),
        "download": _seconds(job.get("ready_at"), job.get("downloading_at")),
        "wait_compute": _seconds(job.get("computing_at"), job.get("ready_at")),
        "compute": compute,
        "outside_steps": compute - total if compute is not None and total is not None else None,
        "orthophoto": steps["orthophoto"][0] if "orthophoto" in steps else None,
        "other": steps["other"][0] if "other" in steps else None,
    }


def resolution_class(resolution: Optional[float]) -> str:
    """The class of a resolution as F19's metrics (metrics.RESOLUTION_SQL)."""
    if resolution is None or resolution <= 0:
        return "?"
    return next((c for c, top in (("1", 1), ("2", 2), ("5", 5), ("10", 10)) if resolution <= top), "30")


def length_class(max_length: float) -> str:
    return next((f"<={top}" for top in (150, 400, 1000) if max_length <= top), ">1000")


def preset_of(params: Dict) -> str:
    """The preset whose values a search has (the defaults for those it leaves out), else custom."""
    values = {k: float(params.get(k, DEFAULTS[k])) for k in PRESET_FIELDS}
    for name, preset in PRESETS.items():
        if values == {k: float(preset.get(k, DEFAULTS[k])) for k in PRESET_FIELDS}:
            return name
    return "custom"


def connect(path: str, immutable: bool) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro{'&immutable=1' if immutable else ''}", uri=True)


def _columns(db: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _rows(db: sqlite3.Connection, sql: str, *args) -> list:
    try:
        return db.execute(sql, args).fetchall()
    except sqlite3.OperationalError:  # a database from before the migration of that table
        return []


def load(db: sqlite3.Connection, days: Optional[float] = None) -> List[Dict]:
    """The finished searches (status done) with their classes and statistics, without ids."""
    have = _columns(db, "jobs")
    picked = ["id", "request"] + [c for c in ("resolution", "source", "created", "downloading_at", "ready_at",
                                              "computing_at", "finished") if c in have]
    where = "status = 'done'" + (" AND julianday(created) >= julianday('now') - ?" if days else "")
    jobs = [dict(zip(picked, row)) for row in db.execute(f"SELECT {', '.join(picked)} FROM jobs WHERE {where}",
                                                          (days,) if days else ())]
    steps: Dict[str, Dict[str, Tuple[float, Optional[float]]]] = {}
    cpu_column = "cpu_seconds" if "cpu_seconds" in _columns(db, "job_steps") else "NULL"
    for job_id, step, s, c in _rows(db, f"SELECT job_id, step, seconds, {cpu_column} FROM job_steps"):
        steps.setdefault(job_id, {})[step] = (s, c)
    stages: Dict[str, Dict[str, Tuple[float, Optional[float]]]] = {}
    for job_id, stage, s, c in _rows(db, "SELECT job_id, stage, seconds, cpu_seconds FROM job_stages"):
        stages.setdefault(job_id, {})[stage] = (s, c)
    funnels: Dict[str, Dict[str, int]] = {}
    for job_id, step, n in _rows(db, "SELECT job_id, step, count FROM job_funnel"):
        funnels.setdefault(job_id, {})[step] = n
    found = []
    for job in jobs:
        try:
            request = json.loads(job["request"] or "{}")
        except ValueError:
            continue
        params = request.get("params")
        if not isinstance(params, dict):  # an OSM extract, not a search
            continue
        job_id = job["id"]
        stage_times, funnel = stages.get(job_id), funnels.get(job_id)
        resolution = job.get("resolution") or params.get("resolution")
        texts = _compute_events(db, job_id)
        if stage_times is None or funnel is None or resolution is None:
            parsed, parsed_stages, parsed_resolution = from_events(texts)
            funnel = funnel if funnel is not None else parsed
            stage_times = stage_times if stage_times is not None else {k: (s, None) for k, s in parsed_stages.items()}
            resolution = resolution or parsed_resolution
        seconds = None
        if job.get("computing_at") and job.get("finished"):
            seconds = db.execute("SELECT (julianday(?) - julianday(?)) * 86400.0", (job["finished"],
                                                                                    job["computing_at"])).fetchone()[0]
        found.append({
            "model": params.get("model", DEFAULTS["model"]),
            "resolution": resolution_class(resolution),
            "length": length_class(float(params.get("max_length", DEFAULTS["max_length"]))),
            "shape": "area" if params.get("area") or request.get("geometry") or params.get("geometry") else "circle",
            "preset": preset_of(params),
            "seconds": seconds, "steps": steps.get(job_id, {}), "stages": stage_times, "funnel": funnel,
            "phases": phases_of(job, steps.get(job_id, {})), "tiles": tiles_of(texts),
        })
    return found


def _compute_events(db: sqlite3.Connection, job_id: str) -> List[str]:
    """The info lines of a job's (last) computing phase."""
    texts, computing = [], False
    for kind, data in db.execute("SELECT kind, data FROM events WHERE job = ? ORDER BY seq", (job_id,)):
        try:
            value = json.loads(data)
        except (TypeError, ValueError):
            continue
        if kind == "status" and isinstance(value, dict):
            if value.get("status") == "computing":
                texts, computing = [], True
        elif kind == "info" and computing and isinstance(value, str):
            texts.append(value)
    return texts


def _percentile(values: List[float], share: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(share * (len(values) - 1))))]


def summarise(jobs: List[Dict]) -> List[Dict]:
    """One row per class (model, resolution, length, shape, preset) of the searches."""
    groups: Dict[tuple, List[Dict]] = {}
    for job in jobs:
        groups.setdefault(tuple(job[c] for c in CLASSES), []).append(job)
    rows = []
    for key, members in sorted(groups.items()):
        row = dict(zip(CLASSES, key))
        times = [j["seconds"] for j in members if j["seconds"] is not None]
        row.update(jobs=len(members), compute_s=sum(times) if times else None,
                   compute_median_s=statistics.median(times) if times else None,
                   compute_p90_s=_percentile(times, 0.9))
        for kind, keys in (("step", STEP_KEYS), ("stage", STAGE_KEYS)):
            for k in keys:
                pairs = [j[kind + "s"][k] for j in members if k in j[kind + "s"]]
                row[f"{kind} {k} s"] = sum(s for s, _ in pairs) if pairs else None
                cpus = [c for _, c in pairs if c is not None]
                row[f"{kind} {k} cpu"] = sum(cpus) if cpus else None
        # A count only where every search of the class has it (the events of a tiled search from before
        # migration 16 do not tell its lines); a ratio over the searches that have both of its counts
        row.update({f"funnel {k}": sum(j["funnel"][k] for j in members)
                    if all(k in j["funnel"] for j in members) else None for k in FUNNEL_STEPS})
        for top, bottom in RATIOS:
            both = [j["funnel"] for j in members if top in j["funnel"] and bottom in j["funnel"]]
            under = sum(f[bottom] for f in both)
            row[f"{top}/{bottom}"] = sum(f[top] for f in both) / under if under else None
        rows.append(row)
    return rows


def phases_summary(jobs: List[Dict]) -> List[Dict]:
    """One row per class and one for all the searches: how many, and the median and the largest
    of each of PHASE_KEYS' seconds (over the searches that have it), the tiles (median and most)
    and the largest tile's Mpx."""
    groups: Dict[tuple, List[Dict]] = {}
    for job in jobs:
        groups.setdefault(tuple(job[c] for c in CLASSES), []).append(job)
    rows = []
    for key, members in sorted(groups.items()) + [(("all",) + ("",) * (len(CLASSES) - 1), jobs)]:
        row = dict(zip(CLASSES, key))
        row["jobs"] = len(members)
        for k in PHASE_KEYS:
            values = [j["phases"][k] for j in members if j["phases"].get(k) is not None]
            row[f"{k} median"] = statistics.median(values) if values else None
            row[f"{k} max"] = max(values) if values else None
        tiles = [j["tiles"][0] for j in members if j["tiles"][0]]
        sizes = [j["tiles"][1] for j in members if j["tiles"][1]]
        row["tiles median"] = statistics.median(tiles) if tiles else None
        row["tiles max"] = max(tiles) if tiles else None
        row["tile Mpx max"] = max(sizes) if sizes else None
        rows.append(row)
    return rows


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3g}" if abs(value) < 1 else f"{value:.1f}" if abs(value) < 100 else f"{value:.0f}"
    return str(value)


def markdown(rows: List[Dict], columns: List[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_text(row.get(c)) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def report(rows: List[Dict]) -> str:
    """The Markdown tables: the classes with their times and funnel ratios, then the steps and the
    stages (seconds and CPU seconds, summed over the class's searches)."""
    overview = list(CLASSES) + ["jobs", "compute_s", "compute_median_s", "compute_p90_s", "funnel anchors_kept",
                                "funnel candidates", "funnel lines"] + [f"{a}/{b}" for a, b in RATIOS]
    parts = ["## Searches by class", markdown(rows, overview)]
    for kind, keys, title in (("step", STEP_KEYS, "Steps of computing"),
                              ("stage", STAGE_KEYS, "Stages of the line search")):
        columns = list(CLASSES) + [f"{kind} {k} {what}" for k in keys for what in ("s", "cpu")]
        parts += ["", f"## {title}: seconds and CPU seconds", markdown(rows, columns)]
    return "\n".join(parts) + "\n"


def phases_report(rows: List[Dict]) -> str:
    """The Markdown table of phases_summary: the classes (and all) with the median and the largest
    seconds of each phase, the tiles and the largest tile."""
    columns = list(CLASSES) + ["jobs"] + [f"{k} {what}" for k in PHASE_KEYS for what in ("median", "max")]
    columns += ["tiles median", "tiles max", "tile Mpx max"]
    return "\n".join(["## Phases of the jobs: seconds (median and max per class)", markdown(rows, columns)]) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, help="the jobs.sqlite to read (never written)")
    parser.add_argument("--days", type=float, help="only the searches queued in the last N days")
    parser.add_argument("--immutable", action="store_true", help="the file is a copy nothing writes")
    parser.add_argument("--csv", help="also write the table of the classes (every column) to this file")
    parser.add_argument("--phases", action="store_true",
                        help="also the seconds of the phases and the waits between them, and the tiles")
    args = parser.parse_args(argv)
    db = connect(args.db, args.immutable)
    try:
        found = load(db, args.days)
        rows = summarise(found)
    finally:
        db.close()
    sys.stdout.write(report(rows) if rows else "No finished searches.\n")
    if args.phases and rows:
        sys.stdout.write("\n" + phases_report(phases_summary(found)))
    if args.csv:
        columns = list(rows[0]) if rows else list(CLASSES)
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, columns)
            writer.writeheader()
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
