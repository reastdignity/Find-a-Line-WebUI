"""The 0.5 m grid sheets of the Tokyo Digital Twin's point clouds (the source `tokyo`): a static table of every sheet
with the folder it lies in, next to the catalogue (sources/catalogue/tokyo_sheets.npz), read by the source's layer:
a sheet outside the table is never asked (the bucket answers 403 for a key it does not have, never 404).

The table comes from the publisher's index vector tiles of the grids (one set per survey: Tama and the islands in
the folder 2023, the 23 wards in 2024), Mapbox vector tiles at zoom 12 with the fields MESH_NO (the sheet's code)
and URL (its ZIP), read with GDAL's MVT driver through pyogrio (no other dependency). Every code must be a 1/500
sheet of zone IX (sources.catalogue.japan.jp_cell) and its URL the folder's address of that code, or the tool stops.
Paced: one request at a time, at least PAUSE_S apart; `--count` says how many tiles a run asks without asking any.
A sheet may be in both folders (85 along the line between Tama and the wards, 2026-11-15: each file partial).
The surveys are frozen (2022-2023): run this again only when Tokyo publishes more sheets, check the tests' places and
commit the new table.

    uv run tools/tokyo_sheets.py [--count] [--work <folder for the tiles>] [--out sources/catalogue/tokyo_sheets.npz]
"""

import argparse
import math
import os
import re
import sys
import time
from typing import Dict, Iterable, List, Set, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

BUCKET = "https://gic-tokyo.s3.ap-northeast-1.amazonaws.com"
ZOOM = 12  # the finest zoom of the index tiles: lower ones drop features
PAUSE_S = 1.0
MAX_TILE_BYTES = 5_000_000
# (folder, set, boxes as (south, north, west, east)): Tama and the 23 wards on the mainland, the Izu islands
# (Ogasawara was not surveyed)
SETS: Tuple[Tuple[int, str, Tuple[Tuple[float, float, float, float], ...]], ...] = (
    (2023, "tama", ((35.50, 35.90, 138.94, 139.93),)),
    (2023, "toushobu", ((32.40, 34.82, 139.20, 140.00),)),
    (2024, "23ku", ((35.50, 35.90, 139.50, 139.93),)),
)


def tile_url(folder: int, name: str, z: int, x: int, y: int) -> str:
    return f"{BUCKET}/{folder}/dig/Vectortile/{name}/grd50/{z}/{x}/{y}.pbf"


def sheet_url(folder: int, code: str) -> str:
    """The ZIP of a sheet (the layer's address: sources.catalogue.japan)."""
    return f"{BUCKET}/{folder}/dig/grd50/{code}.zip"


def tiles_of(box: Tuple[float, float, float, float], z: int = ZOOM) -> List[Tuple[int, int]]:
    """The (x, y) of the Web Mercator tiles at zoom z over a box (south, north, west, east)."""
    south, north, west, east = box
    n = 2 ** z

    def xy(lat: float, lon: float) -> Tuple[int, int]:
        return (int((lon + 180) / 360 * n),
                int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))

    (x0, y0), (x1, y1) = xy(north, west), xy(south, east)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def asked() -> List[Tuple[int, str, int, int]]:
    """Every (folder, set, x, y) a run asks, each once."""
    found = {}
    for folder, name, boxes in SETS:
        for box in boxes:
            for x, y in tiles_of(box):
                found[(folder, name, x, y)] = None
    return list(found)


def read_tile(path: str) -> List[Tuple[str, str]]:
    """(MESH_NO, URL) of every feature of a saved tile (its path ends in <z>/<x>/<y>.pbf: GDAL's MVT driver takes
    the tile's place from it)."""
    import pyogrio
    found = []
    for layer, _ in pyogrio.list_layers(path):
        meta, _, _, fields = pyogrio.raw.read(path, layer=layer, read_geometry=False)
        names = list(meta["fields"])
        if "MESH_NO" not in names or "URL" not in names:
            raise ValueError(f"{path}: layer {layer} has no MESH_NO and URL ({names})")
        found += zip((str(v) for v in fields[names.index("MESH_NO")]), (str(v) for v in fields[names.index("URL")]))
    return found


def sheets(features: Iterable[Tuple[int, str, str]]) -> Dict[str, Set[int]]:
    """The folders of each code from (folder, MESH_NO, URL); ValueError when a code is not a sheet of zone IX or
    its URL is not the folder's address of it."""
    from sources.catalogue.japan import jp_cell
    found: Dict[str, Set[int]] = {}
    for folder, code, url in features:
        if jp_cell(9, code) is None:
            raise ValueError(f"{code}: not a 1/500 sheet of zone IX")
        if url != sheet_url(folder, code):
            raise ValueError(f"{code}: URL {url}, {sheet_url(folder, code)} expected")
        found.setdefault(code, set()).add(folder)
    return found


def save(path: str, found: Dict[str, Set[int]]):
    """The table: one row per sheet and folder, `codes` (bytes of 8) and `folders`, sorted by code and newest
    folder first. A sheet on the line between Tama's survey (2023) and the wards' (2024) is in both, each file
    partial: the layer composes them."""
    rows = sorted(((c, f) for c, folders in found.items() for f in folders), key=lambda r: (r[0], -r[1]))
    np.savez_compressed(path, codes=np.array([c.encode() for c, _ in rows], dtype="S8"),
                        folders=np.array([f for _, f in rows], dtype=np.int16))


def fetch(url: str) -> bytes:
    """A tile's bytes; b"" when the bucket has none (403 or 404: S3 answers 403 for a missing key when listing
    is denied); RuntimeError for anything else."""
    import cache
    from sources import net
    response = net.session().get(url, headers=cache.http_headers(), timeout=60, stream=True)
    with response:
        if response.status_code in (403, 404):
            return b""
        if response.status_code != 200:
            raise RuntimeError(f"{url}: HTTP {response.status_code}")
        data = response.raw.read(MAX_TILE_BYTES + 1, decode_content=True)
    if len(data) > MAX_TILE_BYTES:
        raise RuntimeError(f"{url}: more than {MAX_TILE_BYTES} bytes")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", action="store_true", help="say how many tiles a run asks, ask none")
    parser.add_argument("--work", default=os.path.join(HERE, "work", "tokyo-sheets"),
                        help="folder of the tiles (kept: a second run asks only those not there)")
    parser.add_argument("--out", default=os.path.join(HERE, "sources", "catalogue", "tokyo_sheets.npz"))
    args = parser.parse_args(argv)
    todo = asked()
    if args.count:
        for folder, name, _ in SETS:
            print(f"{folder}/{name}: {sum(1 for t in todo if t[:2] == (folder, name))} tiles at zoom {ZOOM}")
        print(f"{len(todo)} requests at most, {len(todo) * PAUSE_S / 60:.1f} min at {PAUSE_S:g} s apart")
        return
    features, tiles, empty = [], 0, 0
    for folder, name, x, y in todo:
        path = os.path.join(args.work, f"{folder}-{name}", str(ZOOM), str(x), f"{y}.pbf")
        if not os.path.exists(path):
            data = fetch(tile_url(folder, name, ZOOM, x, y))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as out:
                out.write(data)
            time.sleep(PAUSE_S)
        if os.path.getsize(path) == 0:
            empty += 1
            continue
        tiles += 1
        features += [(folder, code, url) for code, url in read_tile(path)]
    found = sheets(features)
    both = sorted(c for c, f in found.items() if len(f) > 1)
    for folder in sorted({f for fs in found.values() for f in fs}):
        print(f"folder {folder}: {sum(1 for f in found.values() if folder in f)} sheets")
    print(f"{len(found)} sheets from {tiles} tiles ({empty} without a tile); in two folders: {len(both)} {both[:10]}")
    save(args.out, found)
    print(f"written {args.out}")


if __name__ == "__main__":
    main()
