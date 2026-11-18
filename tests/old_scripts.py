"""A run's data.js and lines.js as Find-a-Line wrote them before store wave 4 (window.FINDALINE_RUN, the lines with
their profiles; window.FINDALINE_LINES[id], the lines without), for the tests only: the search writes neither since
wave 4, and the page has read neither since its item 5. A frozen copy of mapping.py's writers of a86b86e8
(`_script_head`, `map_rows`, `map_heads`' two heads, `write_map_scripts`), byte for byte their text, kept for:
- the tools' tests of the runs of before (tests/tool_runs.py `text_only`: tools/prune_study.py and tools/perf_reach.py
  read old runs' lines.js beyond item 5), and tests/test_prune_study.py's own lines.js;
- the Node units that take a run's rows as their input (the clip's rows read into columns by viewer/test/rows.ts, the
  reference the store's columns are compared with), never as a reader of the page.

`write_scripts(folder, files, out)` writes them from a run's store: data.js's head is the store's head less the result
view's keys (`linestore.VIEW_HEAD`: mapping.map_head's dict), lines.js's the crs, the area, the terrain and
`mapping._ends` of run.json; the lines and profiles from `linestore.read`. `data_js(folder)` gives data.js's value."""

import contextlib
import json
import os
from typing import Dict, List, Tuple

import linestore
import mapping
from helpers import END_VALUES, LineTable, profile_dict
from runs import ACCESS, STANDS_FOR, column_texts

LINES_CHUNK = 1_000  # lines written between two progress updates (their texts held meanwhile)
MAP_FILES = ("data.js", "lines.js")


def _script_head(target: str, value: Dict) -> str:
    """The start of a script that assigns value (pages opened from disk cannot fetch JSON) with
    its last key "lines" still open: the text of json.dump of the whole value up to its first line."""
    assert list(value)[-1] == "lines"
    head = json.JSONEncoder(separators=(",", ":")).encode({k: v for k, v in value.items() if k != "lines"})
    return f"{target} = {head[:-1]},\"lines\":["


def map_rows(lines: LineTable, start: int, stop: int) -> List[str]:
    """The JSON texts of the rows of lines.js of lines start..stop (viewer/test/rows.ts, toLine),
    without the profile that data.js adds as its last value (with the END_VALUES, the access mark's
    runs.ACCESS and then the count of the square rule, runs.STANDS_FOR, before it when the lines have
    them: the heads' "ends"). The same text as json.dumps of the row as a list of Python values
    (round() of each, rounded() for those that may be missing), built column by column. Values used
    for grouping are not rounded."""
    c = {name: column[start:stop] for name, column in lines.columns.items()}
    text = lambda values, digits=None, empty_nan=False: column_texts(values, digits, empty_nan)[1]  # noqa: E731
    columns = [text(c["anchor1"][:, 0], 7), text(c["anchor1"][:, 1], 7), text(c["anchor2"][:, 0], 7),
               text(c["anchor2"][:, 1], 7), text(c["a1_xy"][:, 0]), text(c["a1_xy"][:, 1]), text(c["a2_xy"][:, 0]),
               text(c["a2_xy"][:, 1]), text(c["length"]), text(c["clearance"]), text(c["clearance_nmpt"], 2, True),
               text(c["elev_a1"], 2), text(c["elev_a2"], 2), text(c["over_obstacles"]), text(c["water_m"], 1),
               text(c["filled_m"], 1), text(c["height_max"]), text(c["height_mean"], 2), text(c["high_pct"], 1),
               text(c["angle1"], 1), text(c["angle2"], 1), text(c["prom1"], 1, True), text(c["prom2"], 1, True),
               text(c["drop1"], 1, True), text(c["drop2"], 1, True)]
    if END_VALUES[0] in c:  # with an end zone or A-frames: the heads' "ends", before the profile
        columns += [text(c[name], 2) for name in END_VALUES]
    if ACCESS[0] in c:  # the access mark (--access): each anchor's answer, after the A-frame heights
        columns += [text(c[name]) for name in ACCESS]
    if STANDS_FOR in c:  # the square rule: the found lines each line stands for, the last value before the profile
        columns.append(text(c[STANDS_FOR]))
    return list(map(",".join, zip(*columns))) if stop > start else []


def heads_of(head: Dict, meta: Dict) -> Tuple[str, str]:
    """The heads of data.js and lines.js (mapping.map_heads of a86b86e8): data.js's is `head` (mapping.map_head's
    dict) with its lines; lines.js's the crs, the area, the terrain and the ends of run.json `meta`."""
    data = {**head, "lines": None}
    target = f"(window.FINDALINE_LINES = window.FINDALINE_LINES || {{}})[{json.dumps(meta['id'])}]"
    return (_script_head("window.FINDALINE_RUN", data),
            _script_head(target, {"crs": data["crs"], "area": data["area"], "terrain": data["terrain"],
                                  **mapping._ends(meta), "lines": None}))


def write_map_scripts(lines: LineTable, run_path: str, heads: Tuple[str, str], files: tuple = MAP_FILES):
    """data.js and lines.js (`files`: only one of them) of a run: their heads (heads_of), then
    the lines LINES_CHUNK at a time (map_rows; data.js with each line's profile, or null)."""
    encoder = json.JSONEncoder(separators=(",", ":"))
    want_full, want_short = "data.js" in files, "lines.js" in files
    with contextlib.ExitStack() as stack:
        full = short = None
        if want_full:
            full = stack.enter_context(open(os.path.join(run_path, "data.js"), "w", encoding="utf-8"))
            full.write(heads[0])
        if want_short:
            short = stack.enter_context(open(os.path.join(run_path, "lines.js"), "w", encoding="utf-8"))
            short.write(heads[1])
        for start in range(0, len(lines), LINES_CHUNK):
            stop = min(start + LINES_CHUNK, len(lines))
            separator = "," if start else ""
            rows = map_rows(lines, start, stop)
            profiles = lines.profiles
            if full is not None:
                full.write(separator + ",".join(
                    f"[{row},{encoder.encode(profile_dict(profiles[k])) if k in profiles else 'null'}]"
                    for k, row in enumerate(rows, start)))
            if short is not None:
                short.write(separator + ",".join(f"[{row}]" for row in rows))
        if full is not None:
            full.write("]};\n")
        if short is not None:
            short.write("]};\n")


def write_scripts(folder, files=MAP_FILES, out=None):
    """data.js and lines.js of a run with a store, as the search wrote them before store wave 4, into the run folder
    (or the folder `out`)."""
    folder = str(folder)
    lines, head = linestore.read(folder)
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    data = {k: v for k, v in head.items() if k not in linestore.VIEW_HEAD}
    write_map_scripts(lines, str(out or folder), heads_of(data, meta), files=tuple(files))


def data_js(folder) -> dict:
    """The value of the data.js a run with a store had before store wave 4 (its head and "lines": a row per line,
    the profile last or null), made in a temporary folder: the run folder is left as it is."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="data-js-") as out:
        write_scripts(folder, ("data.js",), out)
        with open(os.path.join(out, "data.js"), encoding="utf-8") as f:
            text = f.read()
    return json.loads(text.partition(" = ")[2].rstrip().rstrip(";"))
