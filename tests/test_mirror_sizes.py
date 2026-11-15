"""tools/mirror_sizes.py on a tiny mirror built in tmp_path: the counts and bytes of the product folders, the tiles
of a square at an origin other than (0, 0), across a block boundary and at negative tile numbers, the square
distributions against a brute-force walk over the lattice, a "partial" index reported and left out, a listed tile
missing on disk counted, the JSON and the table holding the same numbers, and nothing under the mirror written."""

import builtins
import io
import json
import math
import os
import sys
from contextlib import redirect_stdout

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import mirror_sizes as ms  # noqa: E402
from sources.readers.tilebases import MIRROR_ENV, grid_tile_name  # noqa: E402

# alpha/dtm/2m: origin (1, 1) as Madeira's; tiles at negative numbers and on both sides of the block boundary
# 9 | 10; (0, 0) listed with data but missing on disk; (-1, 0) null; two files the index does not list
ALPHA = {(-1, -1): 100, (0, -1): 200, (9, 0): 300, (10, 0): 400}
ALPHA_MISSING = (0, 0)
ALPHA_NULL = (-1, 0)
# beta: terrain and surface at 1 m (no origin in the index: (0, 0), as Slovakia's), and a partial 2 m folder
BETA_DMR = {(-3, 2): 1000, (-2, 2): 1100, (-3, 3): 1200}
BETA_DMP = {(-3, 2): 2000, (-2, 2): 2100, (-2, 3): 2200}


def _tiles(folder, sizes, nulls=(), missing=(), index=None):
    tiles = {}
    for (i, j), size in sizes.items():
        path = os.path.join(folder, *grid_tile_name(i, j).split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x" * size)
        tiles[f"{i}_{j}"] = f"{i}{j}".ljust(64, "0")
    for i, j in nulls:
        tiles[f"{i}_{j}"] = None
    for i, j in missing:
        tiles[f"{i}_{j}"] = "f" * 64
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as f:
        json.dump({**(index or {}), "tiles": tiles}, f)


@pytest.fixture
def mirror(tmp_path):
    root = str(tmp_path / "mirror")
    alpha = os.path.join(root, "alpha", "dtm", "2m")
    _tiles(alpha, ALPHA, nulls=[ALPHA_NULL], missing=[ALPHA_MISSING],
           index={"origin": [1.0, 1.0], "tile_m": 2000, "block": 10, "resolution": 2.0})
    with open(os.path.join(alpha, "0_0", "5_5.tif"), "wb") as f:  # on disk, not in the index
        f.write(b"y" * 7)
    with open(os.path.join(alpha, "0_0", "9_0.tif.part"), "wb") as f:
        f.write(b"y" * 7)
    with open(os.path.join(root, "alpha", "README.md"), "w", encoding="utf-8") as f:
        f.write("card")
    _tiles(os.path.join(root, "beta", "dmr5", "1m"), BETA_DMR)
    _tiles(os.path.join(root, "beta", "dmp1", "1m"), BETA_DMP, nulls=[(-3, 3)])
    _tiles(os.path.join(root, "beta", "dmr5", "2m"), {(-3, 2): 50}, index={"partial": True})
    return root


def _snapshot(root):
    found = {}
    for folder, _, files in os.walk(root):
        for name in files:
            st = os.stat(os.path.join(folder, name))
            found[os.path.relpath(os.path.join(folder, name), root)] = (st.st_size, st.st_mtime_ns)
    return found


def _folder(result, name):
    return next(f for f in result["folders"] if f["folder"] == name)


def test_counts_and_bytes_of_a_folder(mirror):
    """Part 1: tiles with data and null, bytes, size statistics, the consistency counts (a missing tile is
    counted, not a crash)."""
    alpha = _folder(ms.run(mirror), "alpha/dtm/2m")
    assert (alpha["tiles_listed"], alpha["tiles_with_data"], alpha["tiles_null"]) == (6, 5, 1)
    assert alpha["tile_bytes"] == 1000 and alpha["tile_gb"] == 1000 / 1e9
    assert alpha["listed_missing_on_disk"] == 1
    assert alpha["unlisted_on_disk"] == 2  # 5_5.tif and the .part
    sizes = alpha["tile_mb"]
    assert (sizes["min"], sizes["median"], sizes["mean"], sizes["max"]) == (100e-6, 200e-6, 250e-6, 400e-6)
    assert sizes["p90"] == sizes["p99"] == 400e-6
    assert alpha["origin"] == [1.0, 1.0] and not alpha["partial"]
    assert _folder(ms.run(mirror), "beta/dmr5/1m")["origin"] == [0.0, 0.0]


def test_square_tiles_at_an_origin_negative_and_across_a_block():
    """A square covers every 2 km tile it touches, tile n covering [origin + 2000 n, origin + 2000 (n + 1))."""
    o = (1.0, 1.0)
    assert ms.tiles_of_square(1, 1, 2000, o) == (0, 0, 0, 0)  # exactly one tile
    assert ms.tiles_of_square(0.5, 1, 2000, o) == (-1, 0, 0, 0)  # half a metre left of the origin
    assert ms.tiles_of_square(-3999, -3999, 2000, o) == (-2, -2, -2, -2)  # negative: [-3999, -1999)
    assert ms.tiles_of_square(-4000, -1, 5000, o) == (-3, -1, 0, 2)  # x [-4000, 1000), y [-1, 4999)
    i0, _, i1, _ = ms.tiles_of_square(1 + 2000 * 9 + 500, 1, 5000, o)  # tiles 9..11: blocks 0 and 1
    assert (i0, i1) == (9, 11) and grid_tile_name(i0, 0).split("/")[0] != grid_tile_name(i1, 0).split("/")[0]
    assert grid_tile_name(-1, -11) == "-1_-2/-1_-11.tif"
    assert ms.tiles_of_square(0, 0, 2000, (0.0, 0.0)) == (0, 0, 0, 0)
    assert ms.axis_groups(2000, 100) == [(-1, 2, 10), (0, 1, 1), (0, 2, 9)]
    with pytest.raises(ValueError):
        ms.axis_groups(2000, 300)


def _brute(sizes_list, origin, side, step, tile_m=2000):
    """(tiles, bytes) per lattice placement whose centre lies in a tile with data of any of the products, walking
    the corners in metres with tiles_of_square (independent of axis_groups and the summed-area tables)."""
    data = {}
    for sizes in sizes_list:
        for key, size in sizes.items():
            data.setdefault(key, []).append(size)
    tiles, nbytes = {}, {}
    i_lo = min(k[0] for k in data) - math.ceil(side / tile_m) - 1
    i_hi = max(k[0] for k in data) + 2
    j_lo = min(k[1] for k in data) - math.ceil(side / tile_m) - 1
    j_hi = max(k[1] for k in data) + 2
    per = int(tile_m / step)
    for kx in range(i_lo * per, i_hi * per):
        x = origin[0] + kx * step
        for ky in range(j_lo * per, j_hi * per):
            y = origin[1] + ky * step
            centre = (math.floor((x + side / 2 - origin[0]) / tile_m), math.floor((y + side / 2 - origin[1]) / tile_m))
            if centre not in data:
                continue
            i0, j0, i1, j1 = ms.tiles_of_square(x, y, side, origin, tile_m)
            hit = [s for i in range(i0, i1 + 1) for j in range(j0, j1 + 1) for s in data.get((i, j), [])]
            tiles[len(hit)] = tiles.get(len(hit), 0) + 1
            nbytes[sum(hit)] = nbytes.get(sum(hit), 0) + 1
    return tiles, nbytes


def _expected(tiles, nbytes, side_km):
    row = {"side_km": side_km, "placements": sum(tiles.values())}
    for name, share in (("median", 0.5), ("p90", 0.9), ("max", 1.0)):
        row[f"tiles_{name}"] = ms.weighted_rank(tiles, share)
        row[f"mb_{name}"] = ms.weighted_rank(nbytes, share) / 1e6
    return row


def test_squares_against_a_brute_force_walk(mirror):
    """Parts 2 and 3 equal a walk over every corner of the lattice; figures by hand: at 2 km the most tiles a
    square asks of alpha is 3 ((-1, -1), (0, -1) and (0, 0), whose file is missing), the most bytes 700 ((9, 0) and
    (10, 0) across the block boundary)."""
    result = ms.run(mirror, step=250, sides_km=(2, 5))
    alpha_sizes = {**ALPHA, ALPHA_MISSING: 0}
    for side in (2, 5):
        row = next(r for r in result["squares"] if r["folder"] == "alpha/dtm/2m" and r["side_km"] == side)
        assert row == {"folder": "alpha/dtm/2m", **_expected(*_brute([alpha_sizes], (1.0, 1.0), side * 1000, 250),
                                                              side)}
        both = next(r for r in result["combined"] if r["dataset"] == "beta" and r["side_km"] == side)
        assert both["products"] == "dmp1+dmr5" and both["resolution_m"] == 1.0
        assert {k: v for k, v in both.items() if k not in ("dataset", "resolution_m", "products")} == \
            _expected(*_brute([BETA_DMR, BETA_DMP], (0.0, 0.0), side * 1000, 250), side)
    two = next(r for r in result["squares"] if r["folder"] == "alpha/dtm/2m" and r["side_km"] == 2)
    assert (two["tiles_max"], two["mb_max"]) == (3, 700e-6)
    assert two["placements"] == 5 * (2000 // 250) ** 2  # five tiles with data as centres


def test_a_partial_index_is_reported_and_left_out(mirror):
    result = ms.run(mirror)
    partial = _folder(result, "beta/dmr5/2m")
    assert partial["partial"] and partial["tiles_with_data"] == 1
    assert all(r["folder"] != "beta/dmr5/2m" for r in result["squares"])
    assert all(r["resolution_m"] == 1.0 for r in result["combined"] if r["dataset"] == "beta")
    totals = {(r["dataset"], r["resolution"]): r for r in result["totals"]}
    assert ("beta", "2 m") not in totals
    assert totals[("beta", "all")]["tile_bytes"] == sum(BETA_DMR.values()) + sum(BETA_DMP.values())
    assert totals[("alpha", "all")]["other_bytes"] == _folder(result, "alpha/dtm/2m")["index_bytes"] + len("card")
    assert totals[("all", "all")]["tile_bytes"] == 1000 + sum(BETA_DMR.values()) + sum(BETA_DMP.values())
    assert totals[("all", "all")]["tiles_with_data"] == 5 + 3 + 3


def test_the_json_and_the_table_hold_the_same_numbers_and_no_path(mirror, tmp_path, monkeypatch):
    """main() writes the table from the same dict it saves: the saved JSON makes the same table; neither names
    the mirror's folder. Nothing under the mirror is opened for writing or changed."""
    monkeypatch.setenv(MIRROR_ENV, mirror)
    before = _snapshot(mirror)
    real_open = builtins.open
    root = os.path.abspath(mirror)

    def guarded(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and os.path.abspath(file).startswith(root) and \
                any(c in mode for c in "wax+"):
            raise AssertionError(f"opened for writing under the mirror: {file}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    out_json = str(tmp_path / "sizes.json")
    printed = io.StringIO()
    with redirect_stdout(printed):
        assert ms.main(["--json", out_json, "--step", "500"]) == 0
    with real_open(out_json, encoding="utf-8") as f:
        saved = json.load(f)
    assert ms.report(saved) == printed.getvalue()
    assert saved["mirror"] == "<mirror>" and saved["step_m"] == 500
    text = printed.getvalue() + json.dumps(saved)
    assert mirror not in text and mirror.replace("\\", "\\\\") not in text and "mirror" + os.sep not in text
    assert "| alpha/dtm/2m |  | 5 | 1 |" in printed.getvalue()
    assert _snapshot(mirror) == before
    with redirect_stdout(io.StringIO()):
        assert ms.main(["--json", os.path.join(mirror, "x.json")]) == 2  # never into the mirror
    assert _snapshot(mirror) == before
