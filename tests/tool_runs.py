"""The two kinds of run the tools of tools/ read (store wave 4, docs/line-volume/spec-store.md 2): copies of a run
made by findaline.py, for the tools' tests.

- `store_only(run, dest)`: a run as a search saves it since store wave 4: its store (lines.arrow, profiles.arrow),
  run.json, map.html, ATTRIBUTION.txt; data.js, lines.js, lines.csv and lines.geojson deleted.
- `text_only(run, dest)`: a run saved before the store (2026-11-15): data.js, lines.js, lines.csv, lines.geojson
  (the run's own when it has them, else written from its store by the writers of before: linestore.export's
  lines.csv and lines.geojson, the bytes the search wrote, and tests/old_scripts.py's data.js and lines.js, the
  frozen copy of mapping.py's writers of before store wave 4's item 5), the store and run.json's block "store"
  deleted.
- `snapshot(folder)`: every file of a folder with its size and time, to show a tool wrote nothing into a run.

Works on a run with or without its text files, so the tests hold before and after the search stops writing them.
"""

import json
import os
import shutil
from typing import Dict, Tuple

import linestore
import old_scripts

TEXT_FILES = ("data.js", "lines.js", "lines.csv", "lines.geojson")


def store_only(run: str, dest: str) -> str:
    shutil.copytree(run, dest)
    for name in TEXT_FILES:
        if os.path.exists(os.path.join(dest, name)):
            os.remove(os.path.join(dest, name))
    assert os.path.isfile(os.path.join(dest, linestore.LINES_FILE))
    return dest


def text_only(run: str, dest: str) -> str:
    shutil.copytree(run, dest)
    for fmt, name in linestore.EXPORTS.items():
        if not os.path.exists(os.path.join(dest, name)):
            linestore.export(dest, fmt, os.path.join(dest, name))
    if not all(os.path.exists(os.path.join(dest, name)) for name in old_scripts.MAP_FILES):
        old_scripts.write_scripts(dest)
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
