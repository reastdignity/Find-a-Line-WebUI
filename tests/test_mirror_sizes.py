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


def test_constants_match_the_app():
    """The tool imports nothing of the app (it runs on the mirror's server): its copies of the grid's constants."""
    import sk_tiles
    assert (ms.TILE_M, ms.BLOCK, ms.MIRROR_ENV) == (sk_tiles.TILE_M, sk_tiles.BLOCK, MIRROR_ENV)


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


def test_weighted_rank_by_hand():
    """The nearest rank over values counted weight times: the median and p90 columns of parts 2 and 3."""
    pairs = {1: 1, 2: 1, 3: 2}  # the list 1, 2, 3, 3
    assert [ms.weighted_rank(pairs, s) for s in (0.25, 0.5, 0.75, 0.9, 1.0)] == [1, 2, 3, 3, 3]
    assert [ms.weighted_rank({1: 5, 2: 4, 9: 1}, s) for s in (0.5, 0.9, 1.0)] == [1, 2, 9]
    assert [ms.weighted_rank({7: 3}, s) for s in (0.01, 0.5, 1.0)] == [7, 7, 7]
    assert ms.weighted_rank({}, 0.5) is None
    weights = {0: 3, 4: 7, 5: 1, 11: 6, 12: 2}
    expanded = sorted(v for v, w in weights.items() for _ in range(w))
    for share in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0):
        assert ms.weighted_rank(weights, share) == ms.nearest_rank(expanded, share), share
    assert [ms.nearest_rank([1, 2, 3, 3], s) for s in (0.25, 0.5, 0.9)] == [1, 2, 3]


def test_block_folders_and_stray_files(tmp_path):
    """Only block folders named <n>_<n> are listed: the files of another folder are in no count; a file in a block
    folder that is not a listed tile counts as "on disk, not listed" and never as a tile."""
    root = str(tmp_path / "mirror")
    folder = os.path.join(root, "alpha", "dtm", "2m")
    _tiles(folder, {(0, 0): 10, (1, 0): 20})
    for name, size in (("0_0/notes.txt", 3), ("tmp/2_0.tif", 50), ("old/0_0.tif", 60)):
        os.makedirs(os.path.dirname(os.path.join(folder, name)), exist_ok=True)
        with open(os.path.join(folder, name), "wb") as f:
            f.write(b"z" * size)
    row = _folder(ms.run(root), "alpha/dtm/2m")
    assert (row["tiles_with_data"], row["tile_bytes"], row["unlisted_on_disk"]) == (2, 30, 1)


def test_folders_without_a_usable_index_are_noted(mirror, tmp_path):
    """An index without "tiles", an empty or cut-short index.json and a resolution folder without one: listed with
    a note, left out of parts 2-4, the run goes on and its exit code is 1."""
    gamma = os.path.join(mirror, "gamma")
    for res, text in (("2m", "{}"), ("5m", ""), ("10m", '{"tiles": {"0_0": "ab')):
        os.makedirs(os.path.join(gamma, "dtm", res))
        with open(os.path.join(gamma, "dtm", res, "index.json"), "w", encoding="utf-8") as f:
            f.write(text)
    _tiles(os.path.join(gamma, "dsm", "2m"), {(0, 0): 10})
    os.remove(os.path.join(gamma, "dsm", "2m", "index.json"))
    result = ms.run(mirror)
    notes = {f["folder"]: f.get("note") for f in result["folders"]}
    assert notes["gamma/dtm/2m"] == ms.NO_TILES
    assert notes["gamma/dtm/5m"] == notes["gamma/dtm/10m"] == ms.UNREADABLE
    assert notes["gamma/dsm/2m"] == ms.NO_INDEX
    assert notes["alpha/dtm/2m"] is None and notes["beta/dmr5/1m"] is None
    assert _folder(result, "gamma/dsm/2m")["tiles_with_data"] is None
    assert all(not r["folder"].startswith("gamma/") for r in result["squares"])
    assert all(r["dataset"] != "gamma" for r in result["combined"] + result["totals"])
    assert any(r["folder"] == "alpha/dtm/2m" for r in result["squares"])
    text = ms.report(result)
    assert "| gamma/dsm/2m |" in text and "index without tiles |" in text and "no index.json |" in text
    with redirect_stdout(io.StringIO()):
        assert ms.main(["--mirror", mirror, "--json", str(tmp_path / "out.json")]) == 1
    with open(tmp_path / "out.json", encoding="utf-8") as f:
        assert ms.report(json.load(f)) == text


def test_products_on_different_grids_are_named_in_part_3(tmp_path):
    root = str(tmp_path / "mirror")
    _tiles(os.path.join(root, "delta", "dtm", "2m"), {(0, 0): 10}, index={"origin": [0.0, 0.0]})
    _tiles(os.path.join(root, "delta", "dsm", "2m"), {(0, 0): 20}, index={"origin": [1.0, 1.0]})
    result = ms.run(root)
    assert result["combined"] == []
    assert len(result["combined_left_out"]) == 1
    assert result["combined_left_out"][0]["products"] == "dsm+dtm"
    text = ms.report(result)
    assert "Left out: delta 2 m dsm+dtm: the products lie on different tile grids" in text
    assert "(no dataset with two complete products" not in text


def test_json_inside_the_mirror_by_any_spelling(mirror, tmp_path, monkeypatch):
    """--json is refused for any spelling of a path in the mirror: another case (Windows), a relative path, a
    junction to it; a root at a drive's top holds every path of that drive."""
    before = _snapshot(mirror)
    spellings = [os.path.relpath(os.path.join(mirror, "alpha", "rel.json"), os.getcwd())
                 if os.path.splitdrive(mirror)[0].lower() == os.path.splitdrive(os.getcwd())[0].lower() else None]
    monkeypatch.chdir(tmp_path)
    spellings.append(os.path.join("mirror", "alpha", "rel2.json"))
    if os.path.normcase("A") == "a":  # a file system without case (Windows)
        spellings.append(os.path.join(mirror.upper(), "ALPHA", "case.json"))
    link = str(tmp_path / "link")
    try:
        import _winapi
        _winapi.CreateJunction(mirror, link)
    except (ImportError, OSError):
        try:
            os.symlink(mirror, link, target_is_directory=True)
        except OSError:
            link = None
    if link:
        spellings.append(os.path.join(link, "alpha", "linked.json"))
    try:
        for path in [p for p in spellings if p]:
            with redirect_stdout(io.StringIO()):
                assert ms.main(["--mirror", mirror, "--json", path]) == 2, path
            assert _snapshot(mirror) == before, path
    finally:
        if link and os.path.lexists(link):
            os.rmdir(link) if os.name == "nt" else os.remove(link)
    top = os.path.abspath(os.sep)  # C:\ on Windows, / elsewhere
    assert ms.inside(os.path.join(top, "x.json"), top)
    assert ms.inside(mirror, mirror)
    assert not ms.inside(str(tmp_path / "out.json"), mirror)
    assert not ms.inside(mirror + "-other" + os.sep + "x.json", mirror)
