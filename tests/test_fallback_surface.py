"""The fallbacks fill the surface model only where they fill the terrain (Source.fallback_surface_with_terrain,
filling.fill_gaps' surface_with_terrain; the user's decision of 2026-11-27 for `spain`): around Ceuta and Melilla
MDS05 holds no data over land MDT05 covers, and one terrain gap anywhere in the grid gave the whole surface to the
30 m radar model (2 923 of 4 797 lines of a 5 km search at Ceuta "over trees"). With the switch a surface gap over the
source's own terrain stays empty; without it (every other source) nothing changes."""

import os

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

import grid as gd
import search
import sources as src

BOX = (49.0, 52.0, 18.0, 20.0)  # (south, north, west, east) around the test grid
SIZE = 60


def _tif(path, grid, band):
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=grid.crs, nodata=-9999.0, transform=from_origin(grid.left, grid.top, grid.res, grid.res)) as dst:
        dst.write(np.where(np.isnan(band), -9999.0, band).astype(np.float32), 1)
    return path


def _fallback(tmp, grid, sid, terrain, surface=None):
    """A fallback of local files: its terrain, and its surface model when given (else none: the terrain fills
    the surface, fill_gaps' surface_from_terrain)."""
    credit = src.Credit(f"{sid} data", f"© {sid}", "CC BY 4.0", "https://example.org")
    nmt = src.FileLayer(f"{sid} terrain", _tif(str(tmp / f"{sid}_nmt.tif"), grid, terrain))
    nmpt = None if surface is None else src.FileLayer(f"{sid} surface",
                                                      _tif(str(tmp / f"{sid}_nmpt.tif"), grid, surface))
    return src.Source(id=sid, name=f"{sid} name", description=sid, nmt=nmt, nmpt=nmpt, credits=(credit,),
                      offline=(("pl", BOX),))


def _full(value):
    return np.full((SIZE, SIZE), value, np.float32)


# The four cases of a pixel when a fallback starts (rows, columns of the grid)
BOTH_DATA = (slice(2, 6), slice(2, 6))         # terrain data, surface data: untouched
BOTH_GAP = (slice(10, 14), slice(10, 14))      # terrain gap, surface gap: both filled
TERRAIN_GAP = (slice(20, 24), slice(20, 24))   # terrain gap, surface data: terrain filled, surface kept
SURFACE_GAP = (slice(30, 58), slice(30, 58))   # terrain data, surface gap (the large one): filled only without the switch
SEA = (slice(50, 54), slice(2, 6))             # both gaps, in the sea zone: never filled


@pytest.fixture
def scene(tmp_path):
    """A grid of 60 x 60 px of 10 m: the source's terrain at 100 m and its surface at 105 m, with the four cases
    and gaps of both in the sea zone; a fallback 30 m higher with a surface 140 m."""
    grid = gd.make_grid((500000, 300000, 500600, 300600), 10, "EPSG:2180")
    terrain, surface = _full(100.0), _full(105.0)
    for at in (BOTH_GAP, TERRAIN_GAP, SEA):
        terrain[at] = np.nan
    for at in (BOTH_GAP, SURFACE_GAP, SEA):
        surface[at] = np.nan
    sea = np.zeros((SIZE, SIZE), bool)
    sea[SEA] = True
    np.save(tmp_path / "nmt.npy", terrain)
    np.save(tmp_path / "nmpt.npy", surface)
    src.mosaic.used_data.clear()
    yield grid, tmp_path, sea
    src.mosaic.used_data.clear()


def _run(grid, tmp, sea, fallbacks, switch, rows=None, name="filled"):
    """fill_gaps_chain over copies of the scene's grids; (terrain, surface, mask, counts, layers credited)."""
    nmt, nmpt = str(tmp / f"{name}_nmt.npy"), str(tmp / f"{name}_nmpt.npy")
    np.save(nmt, np.load(tmp / "nmt.npy"))
    np.save(nmpt, np.load(tmp / "nmpt.npy"))
    src.mosaic.used_data.clear()
    work = tmp / name
    os.makedirs(work)
    exclude = sea
    if rows is not None:  # step 1 in strips passes a memory-mapped zone
        np.save(work / "sea_zone.npy", sea)
        exclude = np.load(work / "sea_zone.npy", mmap_mode="r")
    _, counts = src.fill_gaps_chain(nmt, nmpt, grid, fallbacks, str(tmp / "cache"), str(work / "filled.npy"),
                                    exclude=exclude, rows=rows, surface_with_terrain=switch)
    credited = [entry["layer"] for entry in src.mosaic.used_data]
    return (np.load(nmt), np.load(nmpt), np.load(work / "filled.npy"), [(s.id, n) for s, n in counts], credited)


def test_round_one_defect(scene):
    """One small terrain gap and a large gap of the surface alone (Ceuta's MDS05 of zeros): without the switch
    the fallback's surface fills the whole surface gap; with it the surface gap over the source's own terrain stays
    empty, and only the terrain gap's surface is filled."""
    grid, tmp, sea = scene
    fallback = _fallback(tmp, grid, "fb", _full(130.0), _full(140.0))
    _, before, _, _, _ = _run(grid, tmp, sea, [fallback], False, name="off")
    assert np.isfinite(before[SURFACE_GAP]).all()  # today: every surface gap on land
    _, after, _, _, _ = _run(grid, tmp, sea, [fallback], True, name="on")
    assert np.isnan(after[SURFACE_GAP]).all()
    assert np.isfinite(after[BOTH_GAP]).all()


@pytest.mark.parametrize("switch", [False, True])
def test_the_four_cases(scene, switch):
    """Each case of the brief's table, with and without the switch, the sea zone never filled; the terrain and
    the terrain's mask the same either way."""
    grid, tmp, sea = scene
    fallback = _fallback(tmp, grid, "fb", _full(130.0), _full(140.0))
    terrain, surface, mask, counts, credited = _run(grid, tmp, sea, [fallback], switch)
    assert (terrain[BOTH_DATA] == 100).all() and (surface[BOTH_DATA] == 105).all()
    # gaps shifted by the median difference around them: the terrain 30 m lower, the surface 35 m
    assert np.allclose(terrain[BOTH_GAP], 100.0) and np.allclose(surface[BOTH_GAP], 105.0)
    assert np.allclose(terrain[TERRAIN_GAP], 100.0) and (surface[TERRAIN_GAP] == 105).all()
    assert (terrain[SURFACE_GAP] == 100).all()
    if switch:
        assert np.isnan(surface[SURFACE_GAP]).all()
    else:
        assert np.allclose(surface[SURFACE_GAP], 105.0)
    assert np.isnan(terrain[SEA]).all() and np.isnan(surface[SEA]).all()
    expected = np.zeros((SIZE, SIZE), bool)
    expected[BOTH_GAP] = expected[TERRAIN_GAP] = True
    assert (mask == expected).all() and counts == [("fb", 32)]
    assert credited == ["fb terrain", "fb surface"]


def test_no_surface_gap_on_the_terrains_gaps(scene):
    """With the switch and no surface gap on the terrain's gaps the fallback's surface is neither prepared nor
    credited (fill_gaps skips a pair without gaps)."""
    grid, tmp, sea = scene
    surface = np.load(tmp / "nmpt.npy")
    surface[BOTH_GAP] = 105.0
    np.save(tmp / "nmpt.npy", surface)
    fallback = _fallback(tmp, grid, "fb", _full(130.0), _full(140.0))
    _, after, _, _, credited = _run(grid, tmp, sea, [fallback], True)
    assert np.isnan(after[SURFACE_GAP]).all() and credited == ["fb terrain"]
    _, before, _, _, credited = _run(grid, tmp, sea, [fallback], False, name="off")
    assert np.isfinite(before[SURFACE_GAP]).all() and credited == ["fb terrain", "fb surface"]


@pytest.mark.parametrize("switch", [False, True])
def test_strips_as_whole(scene, switch):
    """fill_gaps in strips of rows (step 1 of a tiled search) gives the grids, the mask and the counts of the
    whole grid, with and without the switch."""
    grid, tmp, sea = scene
    fallback = _fallback(tmp, grid, "fb", _full(130.0), _full(140.0))
    whole = _run(grid, tmp, sea, [fallback], switch, name="whole")
    strips = _run(grid, tmp, sea, [fallback], switch, rows=7, name="strips")
    for a, b in zip(whole[:3], strips[:3]):
        assert np.array_equal(a, b, equal_nan=True)
    assert whole[3:] == strips[3:]


@pytest.mark.parametrize("rows", [None, 7])
def test_the_chain_of_two_fallbacks(scene, rows):
    """Two fallbacks: the first has terrain over the west half only and no surface over a part of it; with the
    switch a pixel whose terrain the first filled is terrain data for the second (its surface left empty), a pixel
    whose terrain the first could not fill is the second's in both grids."""
    grid, tmp, sea = scene
    terrain, surface = np.load(tmp / "nmt.npy"), np.load(tmp / "nmpt.npy")
    terrain[10:14, 40:44] = surface[10:14, 40:44] = np.nan  # a gap of both in the east: the second's
    np.save(tmp / "nmt.npy", terrain)
    np.save(tmp / "nmpt.npy", surface)
    first_terrain, first_surface = _full(130.0), _full(140.0)
    first_terrain[:, 30:] = first_surface[:, 30:] = np.nan
    first_surface[12:14, 10:14] = np.nan  # the first fills the terrain of these but not their surface
    first = _fallback(tmp, grid, "first", first_terrain, first_surface)
    second = _fallback(tmp, grid, "second", _full(150.0), _full(160.0))
    terrain, surface, mask, counts, credited = _run(grid, tmp, sea, [first, second], True, rows=rows)
    assert np.isfinite(terrain[10:14, 10:14]).all() and np.isfinite(surface[10:12, 10:14]).all()
    assert np.isnan(surface[12:14, 10:14]).all()  # the first filled their terrain: the second leaves the surface
    assert np.isfinite(terrain[10:14, 40:44]).all() and np.isfinite(surface[10:14, 40:44]).all()
    assert np.isnan(surface[SURFACE_GAP]).all()
    assert counts == [("first", 32), ("second", 16)]
    assert credited == ["first terrain", "first surface", "second terrain", "second surface"]
    off_terrain, off_surface, off_mask, off_counts, _ = _run(grid, tmp, sea, [first, second], False, rows=rows,
                                                             name="off")
    assert np.isfinite(off_surface[12:14, 10:14]).all() and np.isfinite(off_surface[SURFACE_GAP]).all()
    assert np.array_equal(off_terrain, terrain, equal_nan=True) and np.array_equal(off_mask, mask)
    assert off_counts == counts


def test_without_a_surface_model_of_its_own(scene):
    """A fallback without a surface model fills the surface from its terrain (surface_from_terrain), under the
    same rule."""
    grid, tmp, sea = scene
    fallback = _fallback(tmp, grid, "fb", _full(130.0))
    _, surface, _, _, credited = _run(grid, tmp, sea, [fallback], True)
    assert np.isfinite(surface[BOTH_GAP]).all() and np.isnan(surface[SURFACE_GAP]).all()
    assert credited == ["fb terrain", "fb terrain"]


def test_the_catalogue():
    """`spain` alone has the switch: not `spain_canarias` (MDS05 there has its own zeros as data), not the
    fallbacks or any other source."""
    on = [sid for sid, s in src.SOURCES.items() if s.fallback_surface_with_terrain]
    assert on == ["spain"]
    assert not src.SOURCES["spain_canarias"].fallback_surface_with_terrain
    assert not src.SOURCES["europe"].fallback_surface_with_terrain


@pytest.mark.parametrize("primary", [False, True])
def test_search_passes_its_sources_switch(tmp_path, monkeypatch, primary):
    """search.prepare_data passes the search's own source's switch to fill_gaps_chain, never a fallback's (the
    fallback here has the opposite)."""
    from params import SearchParams
    grid = gd.make_grid((500000, 300000, 500600, 300600), 10, "EPSG:2180")
    terrain = _full(100.0)
    terrain[10:14, 10:14] = np.nan
    _tif(str(tmp_path / "nmt.tif"), grid, terrain)
    _tif(str(tmp_path / "nmpt.tif"), grid, _full(105.0))
    fallback = _fallback(tmp_path, grid, "test_fallback", _full(130.0), _full(140.0))
    fallback.fallback_surface_with_terrain = not primary
    monkeypatch.setitem(src.SOURCES, "test_fallback", fallback)
    choose = src.choose_source

    def with_fallback(*args, **kwargs):
        source, reason = choose(*args, **kwargs)
        source.fallback = "test_fallback"
        source.fallback_surface_with_terrain = primary
        return source, reason
    monkeypatch.setattr(src, "choose_source", with_fallback)
    seen = []
    chain = src.fill_gaps_chain

    def recording(*args, **kwargs):
        seen.append(kwargs.get("surface_with_terrain"))
        return chain(*args, **kwargs)
    monkeypatch.setattr(src, "fill_gaps_chain", recording)
    params = SearchParams(elevation_file=str(tmp_path / "nmt.tif"), surface_file=str(tmp_path / "nmpt.tif"),
                          water="off", fill_gaps="on", ortho="never", northing=300300, easting=500300, radius=290,
                          resolution=10, min_length=20, max_length=100)
    work = tmp_path / "work"
    os.makedirs(work)
    plan = search.plan_search(params, search.Paths(str(tmp_path), str(work)), lambda kind, text: None)
    data = search.prepare_data(plan, statistics=False, shore="none")
    del data
    assert seen == [primary]
