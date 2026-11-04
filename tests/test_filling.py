"""The shore faces the terrain model lacks, filled from the surface model before the sea
(sources.filling.fill_shore_from_surface): what is reached from the terrain's data edge, what
stays for fill_water, and the masks the two steps leave."""

import numpy as np
import pytest

from grid import Grid
from sources import filling


def _grid(shape):
    return Grid(left=0.0, top=float(shape[0]), res=1.0, height=shape[0], width=shape[1], crs="EPSG:32633")


def _scene():
    """A plateau of 140 m whose cliff face has no terrain data on its lower part, the sea below:
    rows 0-5 terrain data (140 m, then the upper face 136 → 55 m), rows 6-13 no terrain data, where
    the surface model holds the face (48 → 5 m) and then the sea surface at 1.0 m with holes (NaN).
    The sea zone (the mapped coastline grown by the buffer) covers rows 4 and below."""
    h, w = 20, 12
    terrain = np.full((h, w), np.nan, np.float32)
    terrain[:3] = 140.0
    terrain[3] = 136.0
    terrain[4] = 92.0
    terrain[5] = 55.0
    surface = np.full((h, w), 1.0, np.float32)
    surface[:6] = terrain[:6] + 0.5
    face = [48.0, 45.0, 41.0, 33.0, 13.0, 11.0, 6.0, 5.0]
    for k, v in enumerate(face):
        surface[6 + k] = v
    surface[16, ::3] = np.nan  # holes in the surface model's sea
    surface[17, 1::4] = np.nan
    zone = np.zeros((h, w), bool)
    zone[4:] = True
    return terrain, surface, zone


def _run(tmp_path, terrain, surface, zone, sea_value=None):
    t = tmp_path / "nmt.npy"
    s = tmp_path / "nmpt.npy"
    np.save(t, terrain)
    np.save(s, surface)
    out, n = filling.fill_shore_from_surface(str(t), str(s), _grid(terrain.shape), zone, str(tmp_path / "face.npy"),
                                             sea_value=sea_value)
    face = np.load(out)
    water = np.load(filling.fill_water(str(t), str(s), _grid(terrain.shape), np.zeros(terrain.shape, np.uint8), zone,
                                       str(tmp_path / "water.npy"), sea_value=sea_value))
    return np.load(t), np.load(s), face, water, n


def test_face_from_the_surface_model_then_the_sea(tmp_path):
    terrain, surface, zone = _scene()
    before = surface.copy()
    z, s, face, water, n = _run(tmp_path, terrain, surface, zone)
    # The face: the surface model's heights, filled data, not water
    assert n == 8 * 12
    assert face[6:14].all() and not face[:6].any() and not face[14:].any()
    assert np.array_equal(z[6:14], surface[6:14])
    assert not water[6:14].any()
    # The sea below: 0 m and water, its holes in the surface model too; the surface model unchanged but for them
    assert (z[14:] == 0).all() and water[14:].all()
    assert np.array_equal(np.isnan(before), np.isnan(np.where(s == 0, np.nan, s)) & np.isnan(before))
    assert (s[14:][np.isfinite(before[14:])] == 1.0).all() and (s[np.isnan(before)] == 0).all()
    # The terrain's own data untouched
    assert np.array_equal(z[:6], terrain[:6])


def test_only_what_descends_from_the_data_edge(tmp_path):
    """A boulder standing above the face next to it, a ship at a quay and a platform with no terrain
    data in reach stay for the sea: not reached downwards from the terrain's data edge."""
    terrain, surface, zone = _scene()
    surface[9, 4] = 53.0  # a boulder above the 33 m of its row, between 41 m above and 13 m below
    surface[9, 5] = 36.0  # just above the 33 m next to it: within FACE_TOLERANCE of the 41 m above
    # A quay of 3 m with terrain data in the sea zone and a ship of 25 m next to it
    terrain[15, 9:12] = 3.0
    surface[15, 9:12] = 3.0
    surface[16:19, 9:12] = 25.0
    # A platform of 8 m out in the sea, no terrain data anywhere near
    surface[18:20, 0:3] = 8.0
    z, s, face, water, n = _run(tmp_path, terrain, surface, zone)
    assert not face[9, 4] and z[9, 4] == 0 and water[9, 4]
    assert face[9, 5] and z[9, 5] == 36.0
    assert not face[16:19, 9:12].any() and (z[16:19, 9:12] == 0).all() and water[16:19, 9:12].all()
    assert not face[18:20, 0:3].any() and (z[18:20, 0:3] == 0).all()
    assert z[15, 9] == 3.0 and not face[15, 9]  # the quay's own data
    assert n == 8 * 12 - 1


def test_face_only_in_the_sea_zone(tmp_path):
    """Outside the zone the gaps are the fallback's (fill_gaps, which runs before): nothing here."""
    terrain, surface, zone = _scene()
    zone[:8] = False  # the zone starts lower: rows 6 and 7 of the face are outside it
    z, s, face, water, n = _run(tmp_path, terrain, surface, zone)
    assert np.isnan(z[6:8]).all() and not face[6:8].any()
    # Rows 8 and below are reached from nothing: no terrain data next to them
    assert not face.any() and n == 0
    assert (z[8:] == 0).all()


def test_sea_surface_by_the_sources_constant(tmp_path):
    """A source whose models hold the sea at a constant (Source.sea_fill): that is the sea surface."""
    terrain, surface, zone = _scene()
    surface[14:] = np.where(np.isnan(surface[14:]), np.nan, 1.3)
    z, s, face, water, n = _run(tmp_path, terrain, surface, zone, sea_value=1.3)
    assert n == 8 * 12 and (z[14:] == 0).all()
    terrain, surface, zone = _scene_with(surface_sea=1.3)
    sea_px = int(np.isfinite(surface[14:]).sum())
    z2, s2, face2, water2, n2 = _run(tmp_path, terrain, surface, zone)
    # Without the constant, 1.3 m is a face of its own: reached from the 5 m above it
    assert n2 == 8 * 12 + sea_px and (z2[14:][face2[14:]] == np.float32(1.3)).all()


def _scene_with(surface_sea):
    terrain, surface, zone = _scene()
    surface[14:] = np.where(np.isnan(surface[14:]), np.nan, surface_sea)
    return terrain, surface, zone


def test_independent_of_the_shore_buffer_and_the_surface(tmp_path):
    """No zone: nothing is a candidate; a surface model without data on the face: nothing filled."""
    terrain, surface, zone = _scene()
    z, s, face, water, n = _run(tmp_path, terrain.copy(), surface.copy(), np.zeros_like(zone))
    assert n == 0 and not face.any() and np.isnan(z[6:]).all()
    surface[6:14] = np.nan
    z, s, face, water, n = _run(tmp_path, terrain.copy(), surface, zone)
    assert n == 0 and (z[6:] == 0).all() and water[6:].all()


def test_tolerance_bounds_each_step(tmp_path):
    """Each pixel at most FACE_TOLERANCE above the neighbour it is reached from: a face that rises
    more than that from the data edge is not a face."""
    terrain, surface, zone = _scene()
    surface[6] = 55.0 + filling.FACE_TOLERANCE + 0.1
    z, s, face, water, n = _run(tmp_path, terrain, surface, zone)
    assert n == 0
    surface[6] = 55.0 + filling.FACE_TOLERANCE
    z, s, face, water, n = _run(tmp_path, *_scene()[:1], surface, zone)
    assert n == 8 * 12


@pytest.mark.parametrize("shape, rows", [((50, 70), None), ((7, 300), None), ((50, 70), 16), ((50, 70), 7)])
def test_on_a_band_of_any_shape(tmp_path, shape, rows):
    """The candidates' indices and their neighbours across rows, found at once or in strips of rows
    (step 1 in strips: the mask memory-mapped): the same as a dense pass."""
    rng = np.random.default_rng(shape[0])
    terrain = np.full(shape, np.nan, np.float32)
    terrain[: shape[0] // 3] = 30.0
    surface = rng.uniform(0.0, 40.0, shape).astype(np.float32)
    surface[: shape[0] // 3] = 30.5
    zone = np.ones(shape, bool)
    t = tmp_path / "t.npy"
    s = tmp_path / "s.npy"
    np.save(t, terrain)
    np.save(s, surface)
    out, n = filling.fill_shore_from_surface(str(t), str(s), _grid(shape), zone, str(tmp_path / "f.npy"), rows=rows)
    face = np.load(out)
    filled = np.load(t)
    assert np.array_equal(np.isfinite(filled), np.isfinite(terrain) | face)
    assert np.array_equal(filled[face], surface[face])
    # The dense reference: grow the accepted set with a 3 x 3 maximum of the accepted heights
    from scipy import ndimage
    cand = np.isnan(terrain) & (surface > filling.SEA_LEVEL_TOLERANCE)
    heights = np.where(np.isfinite(terrain), terrain, -np.inf)
    accepted = np.zeros(shape, bool)
    while True:
        best = ndimage.maximum_filter(np.where(accepted | np.isfinite(terrain), heights, -np.inf), 3, mode="constant",
                                      cval=-np.inf)
        new = cand & ~accepted & (surface <= best + filling.FACE_TOLERANCE)
        if not new.any():
            break
        accepted |= new
        heights = np.where(new, surface, heights)
    assert np.array_equal(face, accepted)
    assert n == int(accepted.sum())


def _shore_scene():
    """_scene after the face fill and fill_water, plus a cliff of a source without a surface model: rows
    0-5 terrain data, the face of rows 6-13 from the surface model (columns 0-5 only: columns 6-11 of
    those rows have no surface data, so the sea fill stands in for the face there), the sea below."""
    terrain, surface, zone = _scene()
    surface[6:14, 6:] = np.nan  # no surface data on the right half of the face
    return terrain, surface, zone


def _after_filling(tmp_path, terrain, surface, zone):
    t, s = tmp_path / "nmt.npy", tmp_path / "nmpt.npy"
    np.save(t, terrain)
    np.save(s, surface)
    face, n = filling.fill_shore_from_surface(str(t), str(s), _grid(terrain.shape), zone, str(tmp_path / "face.npy"))
    water = filling.fill_water(str(t), str(s), _grid(terrain.shape), np.zeros(terrain.shape, np.uint8), zone,
                               str(tmp_path / "water.npy"))
    return t, water, face


def test_shore_kinds(tmp_path):
    """SHORE_SURFACE on the face from the surface model, SHORE_SEA on the sea fill next to terrain standing
    SHORE_RIM_MIN or more above it (the fill stands in for the cliff's foot), nothing on a low shore."""
    terrain, surface, zone = _shore_scene()
    t, water, face = _after_filling(tmp_path, terrain, surface, zone)
    z, wet, f = np.load(t), np.load(water), np.load(face)
    kinds = filling.shore_rows(z, wet, f, 0, z.shape[0])
    assert kinds.dtype == np.uint8 and kinds.shape == z.shape
    assert (kinds[6:14, :6] == filling.SHORE_SURFACE).all()  # the face from the surface model
    # The sea fill below the terrain's last row (55 m) where the face is missing: the row right under it;
    # the column along the face's side is none (a face's foot is as good as the data get)
    assert (kinds[6, 6:] == filling.SHORE_SEA).all() and (kinds[7:14, 6:] == 0).all()
    # Below the face: the face ends at 5 m, not more than SHORE_RIM_MIN: no rim there
    assert (kinds[14:] == 0).all()
    assert (kinds[:6] == 0).all()  # terrain with data is never the shore
    # A lake with data stands at its level: the rim is the difference, not the height
    z2 = z.copy()
    z2[6, 6:] = 300.0  # a lake's level (water with data)
    z2[5, 6:] = 305.0  # its shore 5 m up: not more than the rim: no rim; 306 m: a rim
    kinds2 = filling.shore_rows(z2, wet, f, 0, z.shape[0])
    assert (kinds2[6, 6:] == 0).all()
    z2[5, 6:] = 306.0
    assert (filling.shore_rows(z2, wet, f, 0, z.shape[0])[6, 6:] == filling.SHORE_SEA).all()
    # Strips of rows read their neighbours: the same as the whole grid
    strips = np.concatenate([filling.shore_rows(z, wet, f, r0, r1) for r0, r1, _, _ in filling.strips(z.shape[0], 3)])
    assert np.array_equal(strips, kinds)
    # Without the face mask the face's pixels are the terrain's own: its side stands next to the fill
    bare = filling.shore_rows(z, wet, None, 0, z.shape[0])
    assert not (bare == filling.SHORE_SURFACE).any() and (bare[7:13, 6] == filling.SHORE_SEA).all()


def test_shore_segments(tmp_path, monkeypatch):
    """The segments of a run: the bands of each kind, their outlines in WGS84, pixels and metres, the
    totals; the same found at once or in strips; short bands left out of the list at the default."""
    terrain, surface, zone = _shore_scene()
    t, water, face = _after_filling(tmp_path, terrain, surface, zone)
    grid = _grid(terrain.shape)
    short = filling.shore_segments(str(t), str(water), str(face), grid)
    assert short["segments"] == []  # the bands of 8 and 6 m are under SHORE_MIN_M: listed nowhere, counted in the totals
    assert short["totals"] == {"surface_m": 0, "sea_m": 0, "surface_px": 48, "sea_px": 6}
    monkeypatch.setattr(filling, "SHORE_MIN_M", 0)
    shore = filling.shore_segments(str(t), str(water), str(face), grid)
    assert shore["rim_min"] == filling.SHORE_RIM_MIN
    kinds = sorted(s["kind"] for s in shore["segments"])
    assert kinds == ["sea", "surface"]
    surface_seg = next(s for s in shore["segments"] if s["kind"] == "surface")
    sea_seg = next(s for s in shore["segments"] if s["kind"] == "sea")
    # The bands: the 8 x 6 block of the face grown 2 px each way (12 x 10 pixels, the longer side 12 less the
    # growth 4 = 8 m); the L of the sea (a bar of 6 and one of 8 pixels) grown the same way
    assert surface_seg["px"] == 12 * 8 and surface_seg["m"] == 8  # the band clipped at the grid's left edge
    assert sea_seg["px"] == 5 * 8 and sea_seg["m"] == 4  # the bar of 6 grown to 5 x 8 (clipped at the right): 8 - 4
    assert shore["totals"] == {"surface_m": 8, "sea_m": 4, "surface_px": 48, "sea_px": 6}
    # The rings are closed, in lon/lat (EPSG:32633 near 0, 0: the false easting's lon/lat)
    ring = surface_seg["ring"]
    assert ring[0] == ring[-1] and len(ring) >= 5
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True).transform(0.0, 16.0)  # the band's corner
    assert any(abs(p[0] - round(lon, 6)) < 1e-5 and abs(p[1] - round(lat, 6)) < 1e-5 for p in ring)
    assert shore["segments"][0]["m"] >= shore["segments"][1]["m"]  # the longest first
    in_strips = filling.shore_segments(str(t), str(water), str(face), grid, rows=3)
    assert in_strips == shore
    # No shore at all: empty segments and zero totals
    flat = np.full(terrain.shape, 10.0, np.float32)
    np.save(tmp_path / "flat.npy", flat)
    np.save(tmp_path / "dry.npy", np.zeros(terrain.shape, bool))
    none = filling.shore_segments(str(tmp_path / "flat.npy"), str(tmp_path / "dry.npy"), None, grid)
    assert none["segments"] == [] and none["totals"] == {"surface_m": 0, "sea_m": 0, "surface_px": 0, "sea_px": 0}
