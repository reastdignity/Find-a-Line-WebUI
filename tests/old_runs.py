"""Runs as Find-a-Line saved them before store wave 4 (docs/line-volume/spec-store.md 2.2), made from a new run for
the tests: since wave 4 a search writes only its store (lines.arrow, profiles.arrow), map.html, ATTRIBUTION.txt and
run.json, while the page still opens the old runs on disk until wave 4's item 5 (the reader of data.js) and
`findaline.py runs remove-old` lists and removes them. This module goes with item 5, all but what remove-old's
tests still need then (a folder with run.json and no current store).

`make_old(folder, kind)` turns a run folder (a copy: `clip_runs.data_copy`) into one of the kinds of before, in
place, with today's writers: data.js and lines.js by `mapping.write_map_scripts` (kept in mapping.py until item 5),
their heads from the store's head (data.js's head is `mapping.map_head`'s dict, the store's head less
`linestore.VIEW_HEAD`; lines.js's that of `mapping.map_heads`), the lines and profiles from `linestore.read`;
lines.csv and lines.geojson by `linestore.export` (the bytes the search wrote: export = lines.csv was checked on
every regression entry until wave 4); map.html of an old kind is the page of before (BASE_MAP_HTML: without the
disk notice). The kinds:
- "data_js": saved before store wave 2: data.js, lines.js, lines.csv, lines.geojson, no store;
- "no_html": saved with --no-html before wave 2: lines.csv and lines.geojson only (no map.html, no store);
- "tiled": "data_js" with a tiled search's work state (tiles/, progress.json "done", shore.json);
- "no_view": saved between wave 2 and view B1: the text files and a store without the view's columns;
- "with_text": saved between view B1 and wave 4: the current store and the text files (not old by 2.2).
`make_running`, `make_unsaved`, `newer_store` and `make_leftovers` make the other folders remove-old meets.
"""

import json
import os
import shutil
from pathlib import Path

KINDS = ("data_js", "no_html", "tiled", "no_view", "with_text")
TEXT_FILES = ("data.js", "lines.js", "lines.csv", "lines.geojson")

# mapping.MAP_HTML at e88d69f3 (before store wave 4): the map.html of every run saved before, which loads data.js
BASE_MAP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Find-a-Line</title>
<link rel="stylesheet" href="../{viewer}/viewer.css">
</head><body><div id="map"></div>
<script src="../runs.js"></script>
<script src="../{viewer}/viewer.js"></script>
</body></html>
"""


def _meta(folder) -> dict:
    return json.loads((Path(folder) / "run.json").read_text("utf-8"))


def _write_meta(folder, meta: dict):
    with open(Path(folder) / "run.json", "w", encoding="utf-8") as f:  # as runs.save_results writes it
        json.dump(meta, f, ensure_ascii=False, indent=2)


def write_scripts(folder, files=("data.js", "lines.js")):
    """data.js and lines.js of a run with a store, as mapping.save_map wrote them before store wave 4."""
    import linestore
    import mapping
    folder = str(folder)
    lines, head = linestore.read(folder)
    meta = _meta(folder)
    data = {k: v for k, v in head.items() if k not in linestore.VIEW_HEAD}
    target = f"(window.FINDALINE_LINES = window.FINDALINE_LINES || {{}})[{json.dumps(meta['id'])}]"
    heads = (mapping._script_head("window.FINDALINE_RUN", {**data, "lines": None}),
             mapping._script_head(target, {"crs": data["crs"], "area": data["area"], "terrain": data["terrain"],
                                           **mapping._ends(meta), "lines": None}))
    mapping.write_map_scripts(lines, folder, heads, files=tuple(files))


def write_text(folder, files=("lines.csv", "lines.geojson")):
    """lines.csv and lines.geojson of a run with a store, the bytes the search wrote before store wave 4."""
    import linestore
    for name in files:
        fmt = {"lines.csv": "csv", "lines.geojson": "geojson"}[name]
        out = Path(folder).parent / f".{Path(folder).name}.{fmt}"  # never written in the run folder by export
        linestore.export(str(folder), fmt, str(out))
        os.replace(out, Path(folder) / name)


def drop_store(folder):
    """The run as one saved before the store: no lines.arrow, profiles.arrow, no block "store" in run.json."""
    import linestore
    for name in linestore.FILES:
        (Path(folder) / name).unlink(missing_ok=True)
    meta = _meta(folder)
    meta.pop("store", None)
    _write_meta(folder, meta)


def drop_view(folder):
    """The store as one saved before view B1: without the columns spot, top, by_spot and the head's sectors, box,
    lengths (the rest of the file as it was)."""
    import pyarrow as pa
    import linestore
    path = str(Path(folder) / linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    for key in linestore.VIEW_HEAD:
        meta["head"].pop(key, None)
    table = table.drop_columns([name for name, _ in linestore.VIEW if name in table.schema.names])
    table = table.replace_schema_metadata({linestore.META_KEY: json.dumps(meta).encode("utf-8")})
    linestore._write_file(path, table)


def old_map(folder):
    """map.html as runs saved before wave 4 hold it (BASE_MAP_HTML), when the run has one."""
    import html
    import mapping
    page = Path(folder) / "map.html"
    if page.is_file():
        page.write_text(BASE_MAP_HTML.format(title=html.escape(_meta(folder)["name"]), viewer=mapping.VIEWER_FOLDER),
                        "utf-8")


def make_old(folder, kind: str):
    """Turn the run folder `folder` (a new run, with its store) into a run of `kind` (KINDS), in place."""
    if kind not in KINDS:
        raise ValueError(kind)
    folder = Path(folder)
    if kind != "no_html":
        write_scripts(folder)
    write_text(folder)
    old_map(folder)
    if kind in ("data_js", "tiled", "no_html"):
        drop_store(folder)
    if kind == "no_html":
        (folder / "map.html").unlink(missing_ok=True)
    if kind == "no_view":
        drop_view(folder)
    if kind == "tiled":
        (folder / "tiles").mkdir(exist_ok=True)
        (folder / "tiles" / "tile_0.npz").write_bytes(b"tile")
        (folder / "shore.json").write_text("[]", "utf-8")
        _progress(folder, "done")
    return folder


def _progress(folder, status: str):
    meta = _meta(folder) if (Path(folder) / "run.json").is_file() else {"name": "x", "created": "2026-11-01T00:00:00"}
    (Path(folder) / "progress.json").write_text(json.dumps({
        "status": status, "search": "0" * 16, "tile_core": 1000, "name": meta["name"], "created": meta["created"]}),
        "utf-8")


def make_running(folder):
    """A tiled search still running (progress.json "running")."""
    _progress(folder, "running")
    return Path(folder)


def make_unsaved(folder):
    """A run folder being saved: no run.json yet."""
    (Path(folder) / "run.json").unlink()
    return Path(folder)


def newer_store(folder):
    """A store made by a newer Find-a-Line (its format one higher)."""
    import pyarrow as pa
    import linestore
    path = str(Path(folder) / linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    meta = json.loads(table.schema.metadata[linestore.META_KEY])
    meta["format"] = linestore.FORMAT + 1
    linestore._write_file(path, table.replace_schema_metadata({linestore.META_KEY: json.dumps(meta).encode("utf-8")}))
    return Path(folder)


def make_leftovers(data_dir):
    """runs/index.html and the data folder's findaline_map.html, as searches before wave 4 left them."""
    data_dir = Path(data_dir)
    (data_dir / "runs").mkdir(parents=True, exist_ok=True)
    (data_dir / "runs" / "index.html").write_text("<!doctype html><title>Find-a-Line runs</title>", "utf-8")
    (data_dir / "findaline_map.html").write_text("<!doctype html><title>Find-a-Line - latest run</title>", "utf-8")


def copy_run(run_folder, runs_dir, run_id: str) -> Path:
    """A copy of a run folder under another id (run.json's id; the store's head names the run too)."""
    import pyarrow as pa
    import linestore
    target = Path(runs_dir) / run_id
    shutil.copytree(run_folder, target)
    meta = _meta(target)
    old = meta["id"]
    meta["id"] = run_id
    _write_meta(target, meta)
    path = target / linestore.LINES_FILE
    if path.is_file():
        with pa.OSFile(str(path), "rb") as f:
            table = pa.ipc.open_file(f).read_all()
        head = table.schema.metadata[linestore.META_KEY].decode("utf-8").replace(old, run_id)
        linestore._write_file(str(path), table.replace_schema_metadata({linestore.META_KEY: head.encode("utf-8")}))
    return target
