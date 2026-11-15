"""The 1:10 000 sheets of INEGI's 5 m lidar terrain and surface models (the source `mexico`): a static mask of the
cells of INEGI's lattice that hold a sheet, next to the catalogue (sources/catalogue/mexico_sheets.npz), read by
InegiIndex: a cell without a sheet is never asked of the per-sheet JSON, and `--source auto` takes `europe` where
no sheet lies within 2 km of the centre (about half of Mexico has no lidar: the Copper Canyon, Basaseachi, the
Sumidero Canyon).

The download viewer's lists (getFormato10k.do?res=5&mod=T and mod=S: every sheet of the model with its centroid in
Web Mercator, about 1.8 MB each) are read once; each centroid's cell must carry the sheet's name
(sources.layers.inegi.inegi_sheet), or the tool stops. The lidar models are frozen (surveys of 2006-2012): run this
again only when INEGI publishes more sheets, check the places of the test, and commit the new mask.

    uv run tools/mx_sheets.py [--out sources/catalogue/mexico_sheets.npz]
"""

import argparse
import json
import math
import os
import sys
from typing import Dict, Iterable, List, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

MERCATOR_R = 6378137.0


def cell_of(x: float, y: float) -> Tuple[int, int]:
    """The cell of INEGI's lattice holding a point in Web Mercator (a sheet's centroid)."""
    from sources.layers.inegi import INEGI_CELL, INEGI_ORIGIN
    lon = math.degrees(x / MERCATOR_R)
    lat = math.degrees(2 * math.atan(math.exp(y / MERCATOR_R)) - math.pi / 2)
    (w, h), (x0, y0) = INEGI_CELL, INEGI_ORIGIN
    return math.floor((lon - x0) / w), math.floor((lat - y0) / h)


def cells(listing: Iterable[Dict]) -> List[Tuple[int, int]]:
    """The cells of a list's sheets ({"cve", "x", "y"} each); ValueError when a centroid's cell is not its sheet's."""
    from sources.layers.inegi import inegi_sheet
    found = []
    for item in listing:
        cell = cell_of(float(item["x"]), float(item["y"]))
        if inegi_sheet(*cell) != item["cve"]:
            raise ValueError(f"{item['cve']}: its centroid lies in the cell of {inegi_sheet(*cell)}")
        found.append(cell)
    return found


def save(path: str, models: Dict[str, List[Tuple[int, int]]]):
    """The cells of each model (t, s) as bits of one box of the lattice (numpy's packbits, compressed): `<mod>_bits`,
    `shape` (rows, columns) and `origin` (i, j of the box's south-west cell; rows go north)."""
    every = [c for found in models.values() for c in found]
    i0, j0 = min(i for i, _ in every), min(j for _, j in every)
    shape = (max(j for _, j in every) - j0 + 1, max(i for i, _ in every) - i0 + 1)
    arrays = {}
    for mod, found in models.items():
        mask = np.zeros(shape, dtype=bool)
        for i, j in found:
            mask[j - j0, i - i0] = True
        arrays[f"{mod}_bits"] = np.packbits(mask, axis=None)
    np.savez_compressed(path, shape=np.array(shape), origin=np.array([i0, j0]), **arrays)


def main():
    from sources import net
    from sources.catalogue import mexico
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default=mexico.MX_SHEETS)
    args = parser.parse_args()
    models = {}
    for mod in ("T", "S"):
        response = net._get(f"{mexico.MX_VIEWER}/getFormato10k.do?res=5&mod={mod}", binary_types=("text", "json"))
        if response is None:
            raise RuntimeError(f"HTTP 404 for the list of mod={mod}")
        models[mod.lower()] = cells(json.loads(response.content))
        print(f"mod={mod}: {len(models[mod.lower()])} sheets", flush=True)
    save(args.out, models)
    print(f"{args.out}: {os.path.getsize(args.out)} bytes")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
