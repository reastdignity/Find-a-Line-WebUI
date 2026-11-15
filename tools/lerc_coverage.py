"""The cells an Esri elevation tile cache holds data in (a source whose terrain layer is `LercTiles`): a static mask
next to the catalogue (its `cells`, e.g. sources/catalogue/northern_ireland_dtm_cells.npz), read by
`LercTiles.has_data_near`, so `--source auto` takes the source's `instead_without_data` where the cache has no data
near the centre (Northern Ireland's coastal DTM covers the coast only: Belfast's centre and the Mournes take
`europe`), and by `MercatorTiling`, so a search asks no tile far from any data.

The cache is walked down from START_LEVEL to LEVEL over the source's boxes (its `offline` boxes and `bbox`): a tile
with a valid sample (the LERC mask's, at or above the reader's `floor`) has its four children asked at the next
level, one without stops there. At LEVEL each tile's 256 x 256 cells are split into PER_TILE x PER_TILE cells of the
mask (level 13 and 8: cells of 611 m of Web Mercator, about 350 m on the ground at 55° N, 560 m at 23° S), a cell
holding data when one of its samples is valid. This relies on a coarser level having a valid sample wherever a finer
one has: checked when the masks were made (2026-11-15) against every tile of LEVEL in a box on each coast, see
tests/test_lerc_tiles.py and the module of each source.

One request at a time, at least MIN_INTERVAL_S apart (and the host's rate, net.rate_turn); tiles of a few kB. Run it
again when the provider adds data (the layer's folder is live), check the places of the tests, commit the mask:

    uv run tools/lerc_coverage.py northern_ireland [--out PATH] [--check-box south,north,west,east]
"""

import argparse
import math
import os
import sys
import time
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

START_LEVEL = 10
LEVEL = 13
PER_TILE = 8
MIN_INTERVAL_S = 1.1

Tile = Tuple[int, int, int]  # level, row, col


def tile_range(box: Tuple[float, float, float, float], level: int) -> Tuple[int, int, int, int]:
    """(col0, row0, col1, row1), both ends inclusive, of the tiles of a level over a (south, north, west, east) box."""
    south, north, west, east = box
    n = 2 ** level

    def col(lon):
        return min(n - 1, max(0, int((lon + 180) / 360 * n)))

    def row(lat):
        return min(n - 1, max(0, int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)))

    return col(west), row(north), col(east), row(south)


def children(tile: Tile) -> List[Tile]:
    level, row, col = tile
    return [(level + 1, 2 * row + dr, 2 * col + dc) for dr in (0, 1) for dc in (0, 1)]


def cells_of(valid: np.ndarray, per_tile: int) -> np.ndarray:
    """A tile's per_tile x per_tile cells (of its 256 x 256 cells' samples, the shared last row and column dropped)
    holding a valid sample."""
    from sources.readers.lerc import CELLS
    v = valid[:CELLS, :CELLS]
    k = CELLS // per_tile
    return v.reshape(per_tile, k, per_tile, k).any(axis=(1, 3))


def survey(fetch: Callable[[Tile], Optional[np.ndarray]], boxes: Iterable[Tuple[float, float, float, float]],
           start: int = START_LEVEL, level: int = LEVEL, per_tile: int = PER_TILE,
           say: Callable[[str], None] = print) -> Tuple[np.ndarray, Tuple[int, int], int]:
    """The mask over the boxes: (mask, (col0, row0) of its first tile at `level`, requests made). fetch(tile) gives
    a tile's validity (257 x 257 bools; None: no tile, a 404)."""
    boxes = list(boxes)
    ranges = [tile_range(b, level) for b in boxes]
    col0, row0 = min(r[0] for r in ranges), min(r[1] for r in ranges)
    col1, row1 = max(r[2] for r in ranges), max(r[3] for r in ranges)
    mask = np.zeros(((row1 - row0 + 1) * per_tile, (col1 - col0 + 1) * per_tile), dtype=bool)
    todo: List[Tile] = sorted({(start, r, c) for b in boxes for c0, r0, c1, r1 in [tile_range(b, start)]
                               for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)})
    asked = 0
    while todo:
        tile = todo.pop(0)
        valid = fetch(tile)
        asked += 1
        if asked % 50 == 0:
            say(f"{asked} tiles asked, {len(todo)} to go, {int(mask.sum())} cells with data")
        if valid is None or not valid.any():
            continue
        lv, row, col = tile
        if lv < level:
            shift = level - lv  # keep only children whose tiles at `level` meet the mask's rectangle
            rows_meet = (row + 1) << shift > row0 and row << shift <= row1
            if rows_meet and (col + 1) << shift > col0 and col << shift <= col1:
                todo.extend(children(tile))
            continue
        if row0 <= row <= row1 and col0 <= col <= col1:
            r, c = (row - row0) * per_tile, (col - col0) * per_tile
            mask[r:r + per_tile, c:c + per_tile] |= cells_of(valid, per_tile)
    return mask, (col0, row0), asked


def save(path: str, mask: np.ndarray, level: int, per_tile: int, origin: Tuple[int, int]):
    """The mask as bits (numpy's packbits, compressed) with its shape, level, cells per tile and first tile."""
    np.savez_compressed(path, bits=np.packbits(mask, axis=None), shape=np.array(mask.shape), level=np.array(level),
                        per_tile=np.array(per_tile), origin=np.array(origin))


class Fetcher:
    """Tiles through the layer's reader (its capped GET, LERC decoding and floor), one at a time, paced."""

    def __init__(self, layer):
        self.layer, self.last, self.memo = layer, 0.0, {}  # type: ignore[var-annotated]

    def __call__(self, tile: Tile) -> Optional[np.ndarray]:
        from sources import net
        from sources.layer import VALID_MIN
        from sources.readers.lerc import decode
        if tile in self.memo:
            return self.memo[tile]
        reader = self.layer.reader
        wait = MIN_INTERVAL_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        url = reader.url(tile)
        for attempt in range(net.RETRIES):
            try:
                body, _ = reader._get(url)
                samples = None if body is None else decode(body)
                break
            except Exception as e:  # noqa: BLE001 (asked again, then raised)
                if attempt == net.RETRIES - 1:
                    raise
                print(f"{url}: {e}; again", flush=True)
                net._sleep(attempt)
        self.last = time.monotonic()
        if samples is None:
            found = None
        else:
            found = np.isfinite(samples) & (samples >= VALID_MIN)
            if reader.floor is not None:
                found &= samples >= reader.floor
        self.memo[tile] = found
        return found


def check(fetch, box, mask, origin, level: int = LEVEL, per_tile: int = PER_TILE) -> Dict[str, int]:
    """Every tile of `level` in a (south, north, west, east) box asked and compared with the mask: cells with data
    the mask lacks (`missed`, must be 0) and the tiles asked."""
    col0, row0 = origin
    c0, r0, c1, r1 = tile_range(box, level)
    missed = asked = 0
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            valid = fetch((level, row, col))
            asked += 1
            if valid is None:
                continue
            found = cells_of(valid, per_tile)
            r, c = (row - row0) * per_tile, (col - col0) * per_tile
            if 0 <= r < mask.shape[0] and 0 <= c < mask.shape[1]:
                held = mask[r:r + per_tile, c:c + per_tile]
                missed += int((found & ~held).sum())
            else:
                missed += int(found.sum())
    return {"asked": asked, "missed": missed}


def main():
    from sources import SOURCES
    from sources.layers.lerc import LercTiles
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source")
    parser.add_argument("--out", help="the mask (default: the layer's cells)")
    parser.add_argument("--check-box", action="append", default=[],
                        help="south,north,west,east: every tile of the level there compared with the mask")
    args = parser.parse_args()
    source = SOURCES[args.source]
    layer = source.nmt
    if not isinstance(layer, LercTiles):
        raise SystemExit(f"{args.source}'s terrain layer is not LercTiles")
    out = args.out or layer.cells
    if not out:
        raise SystemExit("the layer has no cells file: give --out")
    boxes = source.coverage_boxes()
    fetch = Fetcher(layer)
    started = time.monotonic()
    mask, origin, asked = survey(fetch, boxes)
    save(out, mask, LEVEL, PER_TILE, origin)
    print(f"{out}: {mask.shape[1]} x {mask.shape[0]} cells, {int(mask.sum())} with data ({mask.mean():.2%}), "
          f"{asked} tiles asked in {time.monotonic() - started:.0f} s, {os.path.getsize(out)} bytes")
    for text in args.check_box:
        box = tuple(float(v) for v in text.split(","))
        print(f"check {box}: {check(fetch, box, mask, origin)}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
