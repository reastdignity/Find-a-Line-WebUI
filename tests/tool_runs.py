"""The two kinds of run the tools of tools/ read (store wave 4, docs/line-volume/spec-store.md 2): copies of a run
made by findaline.py, for the tools' tests.

- `store_only(run, dest)`: a run as a search saves it since store wave 4: its store (lines.arrow, profiles.arrow),
  run.json, map.html, ATTRIBUTION.txt; data.js, lines.js, lines.csv and lines.geojson deleted.
- `text_only(run, dest)`: a run saved before the store (2026-11-15): data.js, lines.js, lines.csv, lines.geojson
  (the run's own when it has them, else written from its store by the writers of before: linestore.export's
  lines.csv and lines.geojson, the bytes the search wrote, and mapping.write_map_scripts' data.js and lines.js
  with the heads mapping.map_heads gives), the store and run.json's block "store" deleted.
- `snapshot(folder)`: every file of a folder with its size and time, to show a tool wrote nothing into a run.

Works on a run with or without its text files, so the tests hold before and after the search stops writing them.
"""

import json
import os
import shutil
from typing import Dict, Tuple

import linestore
import mapping as mp

TEXT_FILES = ("data.js", "lines.js", "lines.csv", "lines.geojson")


def store_only(run: str, dest: str) -> str:
    shutil.copytree(run, dest)
    for name in TEXT_FILES:
        if os.path.exists(os.path.join(dest, name)):
            os.remove(os.path.join(dest, name))
    assert os.path.isfile(os.path.join(dest, linestore.LINES_FILE))
    return dest


def map_scripts(folder: str):
    """data.js and lines.js of a run written from its store as mapping.save_map wrote them: the heads of
    mapping.map_heads (data.js's: the store's head without the result view's keys; lines.js's: the crs, the area,
    the terrain and the ends of run.json), the rows of mapping.map_rows with the store's profiles."""
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    lines, head = linestore.read(folder)
    data = {k: v for k, v in head.items() if k not in linestore.VIEW_HEAD}
    data["lines"] = None
    target = f"(window.FINDALINE_LINES = window.FINDALINE_LINES || {{}})[{json.dumps(meta['id'])}]"
    short = {"crs": data["crs"], "area": data["area"], "terrain": data["terrain"], **mp._ends(meta), "lines": None}
    heads = (mp._script_head("window.FINDALINE_RUN", data), mp._script_head(target, short))
    mp.write_map_scripts(lines, folder, heads)


def text_only(run: str, dest: str) -> str:
    shutil.copytree(run, dest)
    for fmt, name in linestore.EXPORTS.items():
        if not os.path.exists(os.path.join(dest, name)):
            linestore.export(dest, fmt, os.path.join(dest, name))
    if not all(os.path.exists(os.path.join(dest, name)) for name in mp.MAP_FILES):
        map_scripts(dest)
    for name in linestore.FILES:
        os.remove(os.path.join(dest, name))
    path = os.path.join(dest, "run.json")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta.pop("store", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return dest


def snapshot(folder: str) -> Dict[str, Tuple[int, int]]:
    out = {}
    for root, _, files in os.walk(folder):
        for name in files:
            path = os.path.join(root, name)
            s = os.stat(path)
            out[os.path.relpath(path, folder)] = (s.st_size, s.st_mtime_ns)
    return out
