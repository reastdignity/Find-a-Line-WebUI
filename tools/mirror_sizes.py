"""
Sizes of the mirror's datasets and of the part of a search a mirror serves (M1 of the mirror-hosting plan), read-only
from a mirror folder (the folder above slovakia/: <mirror>/<dataset>/<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif with
one index.json per product folder, tools/sk_tiles.py and tools/mirror_tiles.py):

1. per product folder: the tiles with data (a sha256 in index.json) and null (no data), their bytes on disk, the size
   of a tile with data (minimum, median, mean, 90th and 99th percentile, maximum; nearest rank), and as a consistency
   note the files on disk the index does not list as data and the tiles it lists that are missing on disk;
2. per product folder: the tiles with data (the requests) and the bytes a square search of side 2, 5, 10 and 20 km
   asks the mirror for, over every placement of the square's lower-left corner on a lattice of --step metres (100 by
   default; it divides the 2 km tile) whose centre lies in a tile with data: median, 90th percentile and maximum
   (weighted nearest rank over the lattice's points). A square [x, x + side) x [y, y + side) covers every tile it
   touches, tile (i, j) covering [origin + 2000 i, origin + 2000 (i + 1)) on each axis (the origin from index.json,
   else (0, 0): the catalogue's GridTiles(origin=), which tools/mirror_tiles.py writes into its indexes). This is the
   mirror's part only: a real search also reads a margin around its area and may read a neighbour's data;
3. per dataset and resolution with two products or more (Slovakia's terrain and surface): the same squares with the
   products together (a placement counts when its centre lies in a tile with data of any of them);
4. the whole datasets (the cost of one full download): per dataset and resolution, per dataset, and all together, the
   tiles' bytes and those of the index.json and README.md files.

A product folder whose index says "partial" is reported in 1 and left out of 2-4; so is one without index.json,
with an index that cannot be read or without a "tiles" object, with a note saying so, and then the exit code is 1
(0 otherwise; 2 for a wrong argument: no mirror, or --json inside it by any spelling of its path). Products of one
dataset and resolution on different tile grids are left out of 3 with a line saying why. Nothing is opened but the
index.json files, for reading: sizes come from os.scandir (one listing per block folder; no tile is opened), tile
presence from the indexes. Standard library only, so it runs on the mirror's server with its python3 too.

    python tools/mirror_sizes.py [--mirror DIR] [--step 100] [--sides 2 5 10 20] [--json FILE]

--mirror defaults to the environment's FINDALINE_MIRROR. The output and the JSON never hold the mirror's path
("<mirror>"). MB and GB are 10^6 and 10^9 bytes.
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

MIRROR_ENV = "FINDALINE_MIRROR"  # sources.readers.tilebases.MIRROR_ENV (the tool imports nothing of the app)
TILE_M = 2000                    # tools/sk_tiles.py TILE_M, BLOCK: the defaults when an index does not name them
BLOCK = 10
STEP_M = 100
SIDES_KM = (2, 5, 10, 20)
RES_FOLDER = re.compile(r"^(\d+(?:\.\d+)?)m$")
BLOCK_FOLDER = re.compile(r"^-?\d+_-?\d+$")
TILE_FILE = re.compile(r"^(-?\d+)_(-?\d+)\.tif$")
NOTE = ("the mirror's part only: a real search also reads a margin around its area and may read a neighbour's "
        "data; a placement is the square's lower-left corner on the step's lattice, its centre in a tile with data")


def axis_range(x: float, side: float, origin: float, tile_m: float) -> Tuple[int, int]:
    """The first and last tile numbers that [x, x + side) touches on one axis, tile n covering
    [origin + tile_m n, origin + tile_m (n + 1))."""
    return math.floor((x - origin) / tile_m), math.ceil((x + side - origin) / tile_m) - 1


def tiles_of_square(x: float, y: float, side: float, origin: Tuple[float, float],
                    tile_m: float = TILE_M) -> Tuple[int, int, int, int]:
    """(i0, j0, i1, j1): the tiles a square search with its lower-left corner at (x, y) asks for."""
    i0, i1 = axis_range(x, side, origin[0], tile_m)
    j0, j1 = axis_range(y, side, origin[1], tile_m)
    return i0, j0, i1, j1


def axis_groups(side: float, step: float, tile_m: float = TILE_M) -> List[Tuple[int, int, int]]:
    """The placements of a square on one axis, grouped: (its first tile relative to the tile of its centre, the
    number of tiles, how many lattice points of one tile's span give that) for corners at origin + u, u = 0, step,
    ..., tile_m - step (the tile of the centre then runs over every tile, so this holds for all of them)."""
    if step <= 0 or (tile_m / step) != int(tile_m / step):
        raise ValueError(f"the step {step:g} m must divide the tile's {tile_m:g} m")
    groups: Dict[Tuple[int, int], int] = {}
    for k in range(int(tile_m / step)):
        u = k * step
        first, last = axis_range(u, side, 0.0, tile_m)
        centre = math.floor((u + side / 2) / tile_m)
        key = (first - centre, last - first + 1)
        groups[key] = groups.get(key, 0) + 1
    return [(offset, count, weight) for (offset, count), weight in sorted(groups.items())]


def nearest_rank(values: Sequence[float], share: float) -> Optional[float]:
    """The nearest-rank percentile of sorted values (share 0.5: the median, 1: the largest)."""
    if not values:
        return None
    return values[max(0, math.ceil(share * len(values)) - 1)]


def weighted_rank(pairs: Dict[float, int], share: float) -> Optional[float]:
    """The nearest-rank percentile of values each counted weight times ({value: weight})."""
    total = sum(pairs.values())
    if not total:
        return None
    goal, seen = max(1, math.ceil(share * total)), 0
    for value in sorted(pairs):
        seen += pairs[value]
        if seen >= goal:
            return value
    return max(pairs)


# Reading a mirror

def scan_folder(path: str) -> Dict[str, int]:
    """Every file in the block folders of a product folder: {"<block>/<name>": bytes} (one scandir per block)."""
    found: Dict[str, int] = {}
    with os.scandir(path) as entries:
        blocks = [e for e in entries if e.is_dir(follow_symlinks=False) and BLOCK_FOLDER.match(e.name)]
    for entry in blocks:
        with os.scandir(entry.path) as files:
            for f in files:
                if f.is_file(follow_symlinks=False):
                    found[f"{entry.name}/{f.name}"] = f.stat(follow_symlinks=False).st_size
    return found


NO_INDEX, UNREADABLE, NO_TILES = "no index.json", "index unreadable", "index without tiles"


def _noted(dataset: str, product: str, res_name: str, note: str, index_bytes: Optional[int] = None) -> Dict:
    """The part 1 row of a folder whose index cannot be used (note says why): no counts, left out of parts 2-4."""
    return {"folder": f"{dataset}/{product}/{res_name}", "dataset": dataset, "product": product,
            "resolution_m": float(RES_FOLDER.match(res_name)[1]), "partial": False, "origin": None, "tile_m": None,
            "block": None, "tiles_listed": None, "tiles_with_data": None, "tiles_null": None, "tile_bytes": None,
            "tile_gb": None, "index_bytes": index_bytes,
            "tile_mb": {k: None for k in ("min", "median", "mean", "p90", "p99", "max")},
            "unlisted_on_disk": None, "listed_missing_on_disk": None, "note": note, "_sizes": {}}


def read_folder(root: str, dataset: str, product: str, res_name: str) -> Dict:
    """One product folder: its index's tiles against the files on disk (part 1), with the tiles' sizes kept under
    "_sizes" ({(i, j): bytes} of the tiles with data, 0 for one missing on disk) for parts 2-4. A folder without
    an index.json, with one that cannot be read, or with one without a "tiles" object gets a row with only its
    "note" (NO_INDEX, UNREADABLE, NO_TILES)."""
    path = os.path.join(root, dataset, product, res_name)
    index_path = os.path.join(path, "index.json")
    if not os.path.isfile(index_path):
        return _noted(dataset, product, res_name, NO_INDEX)
    index_bytes = os.stat(index_path).st_size
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        if not isinstance(index, dict) or not isinstance(index.get("tiles"), dict):
            return _noted(dataset, product, res_name, NO_TILES, index_bytes)
        tiles = index["tiles"]
        origin = tuple(float(v) for v in index.get("origin", (0.0, 0.0)))
        tile_m, block = float(index.get("tile_m", TILE_M)), int(index.get("block", BLOCK))
        keys = {key: tuple(map(int, key.split("_"))) for key, digest in tiles.items() if digest is not None}
        if len(origin) != 2 or any(len(k) != 2 for k in keys.values()):
            raise ValueError("an origin or a tile key that is not a pair")
    except (OSError, ValueError, TypeError):  # JSONDecodeError is a ValueError
        return _noted(dataset, product, res_name, UNREADABLE, index_bytes)
    on_disk = scan_folder(path)
    sizes: Dict[Tuple[int, int], int] = {}
    expected = set()
    missing = 0
    for i, j in keys.values():
        name = f"{i // block}_{j // block}/{i}_{j}.tif"
        expected.add(name)
        if name in on_disk:
            sizes[(i, j)] = on_disk[name]
        else:
            sizes[(i, j)] = 0
            missing += 1
    present = sorted(on_disk[name] for name in expected if name in on_disk)
    folder = f"{dataset}/{product}/{res_name}"
    return {
        "folder": folder, "dataset": dataset, "product": product, "resolution_m": float(RES_FOLDER.match(res_name)[1]),
        "partial": bool(index.get("partial")), "origin": list(origin), "tile_m": tile_m, "block": block,
        "tiles_listed": len(tiles), "tiles_with_data": len(sizes), "tiles_null": len(tiles) - len(sizes),
        "tile_bytes": sum(present), "tile_gb": sum(present) / 1e9, "index_bytes": index_bytes,
        "tile_mb": {
            "min": present[0] / 1e6 if present else None,
            "median": nearest_rank(present, 0.5) / 1e6 if present else None,
            "mean": statistics.fmean(present) / 1e6 if present else None,
            "p90": nearest_rank(present, 0.9) / 1e6 if present else None,
            "p99": nearest_rank(present, 0.99) / 1e6 if present else None,
            "max": present[-1] / 1e6 if present else None,
        },
        "unlisted_on_disk": sum(1 for name in on_disk if name not in expected),
        "listed_missing_on_disk": missing,
        "note": None,
        "_sizes": sizes,
    }


def read_mirror(root: str) -> List[Dict]:
    """Every product folder <root>/<dataset>/<product>/<res>m, in name order (one without index.json too, with
    its note)."""
    found = []
    for dataset in sorted(os.listdir(root)):
        if dataset.startswith(".") or not os.path.isdir(os.path.join(root, dataset)):
            continue
        for product in sorted(os.listdir(os.path.join(root, dataset))):
            base = os.path.join(root, dataset, product)
            if product.startswith(".") or not os.path.isdir(base):
                continue
            for res_name in sorted(os.listdir(base), key=lambda n: float(RES_FOLDER.match(n)[1])
                                   if RES_FOLDER.match(n) else math.inf):
                if RES_FOLDER.match(res_name) and os.path.isdir(os.path.join(base, res_name)):
                    found.append(read_folder(root, dataset, product, res_name))
    return found


# Squares

class Table:
    """Summed-area tables of the tiles with data and their bytes over the extent of some product folders' tiles, so
    that a window of tiles is summed in four lookups."""

    def __init__(self, folders: Iterable[Dict]):
        cells: Dict[Tuple[int, int], List[int]] = {}
        for folder in folders:
            for key, size in folder["_sizes"].items():
                cell = cells.setdefault(key, [0, 0])
                cell[0] += 1
                cell[1] += size
        i = [k[0] for k in cells] or [0]
        j = [k[1] for k in cells] or [0]
        self.i0, self.j0 = min(i), min(j)
        self.w, self.h = max(i) - self.i0 + 1, max(j) - self.j0 + 1
        self.centres = sorted(cells)
        self.count = [[0] * (self.w + 1) for _ in range(self.h + 1)]
        self.bytes = [[0] * (self.w + 1) for _ in range(self.h + 1)]
        for b in range(self.h):
            row_c = row_b = 0
            for a in range(self.w):
                cell = cells.get((a + self.i0, b + self.j0))
                if cell:
                    row_c += cell[0]
                    row_b += cell[1]
                self.count[b + 1][a + 1] = self.count[b][a + 1] + row_c
                self.bytes[b + 1][a + 1] = self.bytes[b][a + 1] + row_b

    def window(self, i0: int, j0: int, i1: int, j1: int) -> Tuple[int, int]:
        """(tiles with data, bytes) of the tiles i0..i1 x j0..j1 (inclusive; beyond the extent nothing)."""
        a0, b0 = max(i0 - self.i0, 0), max(j0 - self.j0, 0)
        a1, b1 = min(i1 - self.i0, self.w - 1), min(j1 - self.j0, self.h - 1)
        if a0 > a1 or b0 > b1:
            return 0, 0
        out = []
        for t in (self.count, self.bytes):
            out.append(t[b1 + 1][a1 + 1] - t[b0][a1 + 1] - t[b1 + 1][a0] + t[b0][a0])
        return out[0], out[1]


def squares(table: Table, side_m: float, step: float, tile_m: float) -> Dict:
    """The distribution of (tiles, MB) of a square of side_m over every lattice placement whose centre lies in a
    tile of the table (see axis_groups)."""
    groups = axis_groups(side_m, step, tile_m)
    tiles: Dict[int, int] = {}
    sizes: Dict[int, int] = {}
    for ci, cj in table.centres:
        for ox, nx, wx in groups:
            for oy, ny, wy in groups:
                n, size = table.window(ci + ox, cj + oy, ci + ox + nx - 1, cj + oy + ny - 1)
                tiles[n] = tiles.get(n, 0) + wx * wy
                sizes[size] = sizes.get(size, 0) + wx * wy
    row = {"side_km": side_m / 1000, "placements": sum(tiles.values())}
    for name, share in (("median", 0.5), ("p90", 0.9), ("max", 1.0)):
        row[f"tiles_{name}"] = weighted_rank(tiles, share)
        mb = weighted_rank(sizes, share)
        row[f"mb_{name}"] = mb / 1e6 if mb is not None else None
    return row


def measure(folders: List[Dict], step: float = STEP_M, sides_km: Sequence[float] = SIDES_KM,
            cards: Optional[Dict[str, int]] = None) -> Dict:
    """Parts 1-4 of a mirror's folders (read_mirror; cards: README.md bytes per dataset), as the JSON's dict. A
    partial folder or one with a note is left out of 2-4; products of one dataset and resolution on different grids
    are left out of part 3, each such group named in "combined_left_out"."""
    complete = [f for f in folders if not f["partial"] and not f.get("note")]
    result: Dict = {"mirror": "<mirror>", "step_m": step, "sides_km": list(sides_km), "note": NOTE,
                    "folders": [{k: v for k, v in f.items() if not k.startswith("_")} for f in folders],
                    "squares": [], "combined": [], "combined_left_out": [], "totals": []}
    for f in complete:
        table = Table([f])
        for side in sides_km:
            result["squares"].append({"folder": f["folder"], **squares(table, side * 1000, step, f["tile_m"])})
    by_res: Dict[Tuple[str, float], List[Dict]] = {}
    for f in complete:
        by_res.setdefault((f["dataset"], f["resolution_m"]), []).append(f)
    for (dataset, res), group in by_res.items():
        if len(group) < 2:
            continue
        grids = sorted({(tuple(f["origin"]), f["tile_m"]) for f in group})
        if len(grids) != 1:  # products on different grids: not one square's tiles
            result["combined_left_out"].append({
                "dataset": dataset, "resolution_m": res, "products": "+".join(f["product"] for f in group),
                "reason": "the products lie on different tile grids: " + ", ".join(
                    f"{f['product']} origin ({f['origin'][0]:g}, {f['origin'][1]:g}) tile {f['tile_m']:g} m"
                    for f in group)})
            continue
        table = Table(group)
        for side in sides_km:
            result["combined"].append({"dataset": dataset, "resolution_m": res,
                                       "products": "+".join(f["product"] for f in group),
                                       **squares(table, side * 1000, step, group[0]["tile_m"])})
    datasets = sorted({f["dataset"] for f in complete})
    for dataset in datasets:
        mine = [f for f in complete if f["dataset"] == dataset]
        for res in sorted({f["resolution_m"] for f in mine}):
            at = [f for f in mine if f["resolution_m"] == res]
            result["totals"].append(_total(dataset, f"{res:g} m", at))
        result["totals"].append(_total(dataset, "all", mine, cards or {}))
    if complete:
        result["totals"].append(_total("all", "all", complete, cards or {}))
    return result


def _total(dataset: str, res: str, folders: List[Dict], cards: Optional[Dict[str, int]] = None) -> Dict:
    """One row of part 4: the folders' tiles, indexes and (cards given) their datasets' README.md."""
    tiles = sum(f["tile_bytes"] for f in folders)
    other = sum(f["index_bytes"] for f in folders)
    if cards is not None:
        other += sum(cards.get(d, 0) for d in {f["dataset"] for f in folders})
    return {"dataset": dataset, "resolution": res, "folders": len(folders),
            "tiles_with_data": sum(f["tiles_with_data"] for f in folders),
            "tile_bytes": tiles, "other_bytes": other,
            "tile_gb": tiles / 1e9, "index_and_card_mb": other / 1e6, "total_gb": (tiles + other) / 1e9}


# Output

def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else ""
    if isinstance(value, float):
        if value == int(value):
            return f"{value:.0f}"
        return f"{value:.3f}" if abs(value) < 10 else f"{value:.2f}" if abs(value) < 1000 else f"{value:.0f}"
    return str(value)


def markdown(rows: List[Dict], columns: List[Tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _ in columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        cells = []
        for _, key in columns:
            value = row
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            cells.append(_text(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


SQUARE_COLUMNS = [("side km", "side_km"), ("placements", "placements"), ("tiles median", "tiles_median"),
                  ("tiles p90", "tiles_p90"), ("tiles max", "tiles_max"), ("MB median", "mb_median"),
                  ("MB p90", "mb_p90"), ("MB max", "mb_max")]


def report(result: Dict) -> str:
    """The Markdown tables of a measure() result (from the dict alone, so the JSON holds the same numbers)."""
    parts = [f"# Mirror sizes ({result['mirror']})", "",
             "## 1. Product folders (tile sizes in MB, nearest rank; partial or with a note: left out of 2-4)",
             markdown(result["folders"], [
                 ("folder", "folder"), ("partial", "partial"), ("with data", "tiles_with_data"),
                 ("null", "tiles_null"), ("GB", "tile_gb"), ("min", "tile_mb.min"), ("median", "tile_mb.median"),
                 ("mean", "tile_mb.mean"), ("p90", "tile_mb.p90"), ("p99", "tile_mb.p99"), ("max", "tile_mb.max"),
                 ("on disk, not listed", "unlisted_on_disk"), ("listed, not on disk", "listed_missing_on_disk"),
                 ("note", "note")]),
             "", f"## 2. Square searches per product folder: tiles (requests) and MB asked of the mirror "
             f"(lattice step {result['step_m']:g} m; {result['note']})",
             markdown(result["squares"], [("folder", "folder")] + SQUARE_COLUMNS)]
    parts += ["", "## 3. Square searches, the products of a dataset together"]
    left_out = result.get("combined_left_out") or []
    if result["combined"]:
        parts.append(markdown(result["combined"], [("dataset", "dataset"), ("res m", "resolution_m"),
                                                   ("products", "products")] + SQUARE_COLUMNS))
    elif not left_out:
        parts.append("(no dataset with two complete products at one resolution)")
    parts += [f"Left out: {g['dataset']} {g['resolution_m']:g} m {g['products']}: {g['reason']}" for g in left_out]
    parts += ["", "## 4. Whole datasets (one full download)",
              markdown(result["totals"], [("dataset", "dataset"), ("resolution", "resolution"),
                                          ("folders", "folders"), ("tiles with data", "tiles_with_data"),
                                          ("tiles GB", "tile_gb"), ("index + card MB", "index_and_card_mb"),
                                          ("total GB", "total_gb")])]
    return "\n".join(parts) + "\n"


def run(root: str, step: float = STEP_M, sides_km: Sequence[float] = SIDES_KM) -> Dict:
    """Read and measure a mirror folder."""
    folders = read_mirror(root)
    cards = {}
    for dataset in {f["dataset"] for f in folders}:
        card = os.path.join(root, dataset, "README.md")
        if os.path.isfile(card):
            cards[dataset] = os.stat(card).st_size
    return measure(folders, step, sides_km, cards)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip(),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mirror", help=f"the mirror folder (default: the environment's {MIRROR_ENV}); read only")
    parser.add_argument("--step", type=float, default=STEP_M, help="lattice of the squares' corners in metres")
    parser.add_argument("--sides", type=float, nargs="+", default=list(SIDES_KM), help="square sides in km")
    parser.add_argument("--json", help="also write the numbers to this file (never inside the mirror)")
    args = parser.parse_args(argv)
    root = args.mirror or os.environ.get(MIRROR_ENV)
    if not root or not os.path.isdir(root):
        sys.stderr.write(f"no mirror folder: pass --mirror or set {MIRROR_ENV}\n")
        return 2
    if args.json and inside(args.json, root):
        sys.stderr.write("--json must not be inside the mirror\n")
        return 2
    result = run(root, args.step, args.sides)
    sys.stdout.write(report(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    return 1 if any(f.get("note") for f in result["folders"]) else 0


def inside(path: str, root: str) -> bool:
    """Whether path lies in root (or is it), whatever its spelling: case on Windows, a relative path, links and
    junctions resolved, a root at a drive's top; another drive is outside."""
    a, r = (os.path.normcase(os.path.realpath(p)) for p in (path, root))
    try:
        return os.path.commonpath([a, r]) == os.path.commonpath([r])
    except ValueError:  # different drives, or an absolute and a relative path
        return False


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
