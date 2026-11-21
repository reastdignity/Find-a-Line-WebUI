"""
A coastal run for tools/ui_shots.py's coast states of the result view (VIEW_STATES: c-view-boxes, -chips-held,
-box-coarser, -box-shore, -link-centre, which need a run with an uncertain shore and the view's columns): a copy of the
Żabi Koń clip's run of a ui_shots data folder (the run its marker names: made from tests/data, never a user's run)
under a run id of its own, given an uncertain shore (a segment of each kind) and coarser terrain (one region over the
south half) over its lines' box, in its store's head and in its run.json (as tests/test_shell_c_view_map.py's
_with_boxes does for the tests). The shore and the terrain are made up: the pictures show the boxes and chips, not a
real coast.

    uv run tools/ui_shots.py --list --data-dir <scratch>                  (once: the clip's run in the data folder)
    uv run tools/ui_coast_run.py --data-dir <scratch> --out <folder>       (prints the copy's folder)
    uv run tools/ui_shots.py --out <pictures> --data-dir <scratch> --run <the copy> --only c-view-boxes,c-view-chips-held,c-view-box-coarser,c-view-box-shore,c-view-link-centre
"""

import argparse
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

RUN = "2026-11-21_120000_Coast_00000000000000e3"  # the copy's run id
NAME = "Clip with the coast boxes"
CLIP = os.path.join("tests", "data", "zabi_kon_nmt.tif")  # the clip's elevation file: the only run copied


def _ring(a, b, c, d):
    return [[a, b], [c, b], [c, d], [a, d], [a, b]]


def coast_copy(clip_run: str, out: str) -> str:
    """The clip's run (its folder `clip_run`) copied into `out` as RUN, with an uncertain shore and coarser terrain over
    its lines' box in its store's head and run.json (the run's id replaced in the head too, run.json's block "store"
    written again); the copy's folder. A run that is not of the clip (its run.json names no CLIP): ValueError."""
    import pyarrow as pa
    import linestore
    import ui_shots
    with open(os.path.join(clip_run, "run.json"), encoding="utf-8") as f:
        meta = json.load(f)
    if not any(os.path.normcase(str(e.get("file", ""))).endswith(os.path.normcase(CLIP)) for e in meta.get("data", [])):
        raise ValueError(f"{clip_run} is not a run of the clip ({CLIP})")
    dst = os.path.join(out, RUN)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(clip_run, dst)
    path = os.path.join(dst, linestore.LINES_FILE)
    with pa.OSFile(path, "rb") as f:
        table = pa.ipc.open_file(f).read_all()
    head = table.schema.metadata[linestore.META_KEY].decode("utf-8").replace(os.path.basename(clip_run), RUN)
    linestore._write_file(path, table.replace_schema_metadata({linestore.META_KEY: head.encode("utf-8")}))
    lat, lon = ([v / 10 ** int(table.schema.field(name).metadata[b"decimals"]) for v in table.column(name).to_pylist()]
                for name in ("lat1", "lon1"))
    s, n, w, e = min(lat), max(lat), min(lon), max(lon)
    mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
    shore = {"rim_min": 5, "totals": {"surface_m": 420, "sea_m": 260, "surface_px": 60, "sea_px": 40},
             "segments": [{"kind": "surface", "px": 60, "m": 420, "ring": _ring(w, s, mid_lon, mid_lat)},
                          {"kind": "sea", "px": 40, "m": 260, "ring": _ring(mid_lon, mid_lat, e, n)}]}
    sources = {"land_km2": 0.3, "fallback_share": 0.3, "totals": {"fallback_km2": 0.09, "listed_km2": 0.09},
               "layers": [{"role": "source", "name": "Own", "resolution": 1.0, "share": 0.7},
                          {"role": "fallback", "name": "Coarse", "resolution": 10.0, "share": 0.3}],
               "regions": [{"layer": 1, "km2": 0.09, "rings": [_ring(w, s, e, mid_lat)]}]}
    store = ui_shots.with_store_head(dst, {"shore": shore, "terrain_sources": sources})
    meta.update(id=RUN, name=NAME, shore=shore, terrain_sources=sources, store=store)
    with open(os.path.join(dst, "run.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return dst


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True, help="a ui_shots data folder (its marker names the clip's run)")
    parser.add_argument("--out", required=True, help="the folder the copy goes into (outside the data folder's runs/)")
    args = parser.parse_args()
    import ui_shots
    clip = ui_shots.read_marker(args.data_dir).get("run")
    if not clip:
        sys.exit(f"{args.data_dir} has no clip run: run `ui_shots.py --list --data-dir {args.data_dir}` once first")
    os.makedirs(args.out, exist_ok=True)
    dst = coast_copy(os.path.join(args.data_dir, "runs", clip), args.out)
    print(dst, sorted(ui_shots.run_features(dst)))


if __name__ == "__main__":
    main()
