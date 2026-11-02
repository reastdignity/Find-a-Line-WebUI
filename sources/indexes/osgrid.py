"""The Ordnance Survey National Grid's tile names (British National Grid, EPSG:27700): NR9542 (1 km), HY21
(10 km), NO10NE (a 5 km quadrant), as the Scottish Remote Sensing Portal names its files."""

import math
import re
from typing import Dict, List, Optional, Tuple

# The letters of the grid's squares, I left out: the first letter names a 500 km square, the second a 100 km
# square in it, each in rows of five from the north-west (A B C D E / F G H J K / ...); SV's south-west corner is
# the grid's false origin (OS, "A guide to coordinate systems in Great Britain", appendix: the National Grid)
LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
NAME = re.compile(r"([A-HJ-Z]{2})(\d*)(NE|NW|SE|SW)?", re.I)


def _square_origin(letters: str) -> Tuple[int, int]:
    """(east, north) in metres of the south-west corner of a 100 km square (the usual formula: the 500 km
    square's letter counted from S, the 100 km square's from A)."""
    first, second = LETTERS.index(letters[0]), LETTERS.index(letters[1])
    east = ((first - 2) % 5) * 5 + second % 5
    north = (19 - (first // 5) * 5) - second // 5
    return east * 100_000, north * 100_000


# The 100 km squares of the grid (its east 0-700 km, north 0-1300 km) by their south-west corner in 100 km
SQUARES: Dict[Tuple[int, int], str] = {}
for _a in LETTERS:
    for _b in LETTERS:
        _e, _n = _square_origin(_a + _b)
        if 0 <= _e < 700_000 and 0 <= _n < 1_300_000:
            SQUARES[(_e // 100_000, _n // 100_000)] = _a + _b


def os_square(east: float, north: float) -> Optional[str]:
    """The letters of the 100 km square holding a point (None outside the grid)."""
    return SQUARES.get((math.floor(east / 100_000), math.floor(north / 100_000)))


def os_tile_extent(name: str) -> Optional[Tuple[int, int, int, int]]:
    """(left, bottom, right, top) in metres of a tile named by its square, an even number of digits (east,
    then north: 2 for 10 km, 4 for 1 km, ...) and maybe a quadrant (NE, NW, SE, SW: half the size); None if
    name is none."""
    match = NAME.fullmatch(name.upper())
    if not match:
        return None
    square, digits, quadrant = match.groups()
    if len(digits) % 2 or not 2 <= len(digits) <= 10:
        return None
    east, north = _square_origin(square)
    if (east // 100_000, north // 100_000) not in SQUARES:
        return None
    k = len(digits) // 2
    size = 10 ** (5 - k)
    east, north = east + int(digits[:k]) * size, north + int(digits[k:]) * size
    if quadrant:
        size //= 2
        east += size if quadrant[1] == "E" else 0
        north += size if quadrant[0] == "N" else 0
    return east, north, east + size, north + size


def os_prefixes(left: float, bottom: float, right: float, top: float) -> List[str]:
    """The beginnings of the 1 km names (square and tens of kilometres east, e.g. NR9) of every tile over a
    box, each 10 km column of each 100 km square once, west to east, then south to north within a column."""
    found: List[str] = []
    for column in range(math.floor(left / 10_000), math.ceil(right / 10_000)):
        for row in range(math.floor(bottom / 100_000), math.ceil(top / 100_000)):
            square = SQUARES.get((column // 10, row))
            if square and f"{square}{column % 10}" not in found:
                found.append(f"{square}{column % 10}")
    return found
