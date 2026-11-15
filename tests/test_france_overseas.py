"""France's overseas territories (sources/catalogue/france.py OVERSEAS: RGE ALTI 1 m of Guadeloupe with
Saint-Barthélemy and Saint-Martin, Martinique, French Guiana and Saint-Pierre-et-Miquelon from IGN's WMS-R): their
layers, the half-metre pixel edges of the Antilles' layers on recorded answers (tests/data/recorded/wmsr/overseas/,
served by tests/http_server.py), and which source --source auto takes there."""

import json
import os
import sys
from urllib.parse import urlsplit

import numpy as np
import pytest
import rasterio as rio

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402
from sources import net  # noqa: E402
from sources.layers.wmsr import WmsrTiles  # noqa: E402
from tile_values import same_tile  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "wmsr", "overseas")
GLP = "RGEALTI-MNT_PYR-ZIP_GLP_WGS84UTM20_WMS"
# The recorded boxes (EPSG:32620, 32 m on the layer's pixel edges): the Soufrière and Sint Maarten
SOUFRIERE = (642912.5, 1774240.5)
SINT_MAARTEN = (493632.5, 1993504.5)
OVERSEAS = {"france_guadeloupe": ("RGEALTI-MNT_PYR-ZIP_GLP_WGS84UTM20_WMS", "EPSG:32620", (0.5, 0.5)),
            "france_martinique": ("RGEALTI-MNT_PYR-ZIP_MTQ_WGS84UTM20_WMS", "EPSG:32620", (0.5, 0.5)),
            "france_guiana": ("RGEALTI-MNT_PYR-ZIP_GUF_UTM22RGFG95_WMS", "EPSG:2972", (0.0, 0.0)),
            "france_spm": ("RGEALTI-MNT_PYR-ZIP_SPM_RGSPM06U21_WMS", "EPSG:4467", (0.5, 0.5))}


@pytest.fixture
def service(http_server, monkeypatch):
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        for answer in json.load(f)["answers"]:
            with open(os.path.join(RECORDED, answer["body"]), "rb") as body:
                parts = urlsplit(answer["url"])
                http_server.add(f"{parts.path}?{parts.query}", body.read(), answer["content_type"],
                                answer["status"])
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    return http_server


def _answer(n):
    with rio.open(os.path.join(RECORDED, f"{n:03d}.tif")) as raster:
        return raster.read(1, masked=True).astype(np.float32).filled(np.nan), raster.transform


def _layer(server) -> WmsrTiles:
    # Guadeloupe's layer as declared, on 32 m tiles so a recorded box is one tile
    return WmsrTiles("RGE ALTI test", server.url("/wms-r/wms"), GLP, "EPSG:32620", "france/test-glp/live",
                     native_res=1.0, fetch_res=(1.0,), tile_m=32, origin=(0.5, 0.5))


def test_the_overseas_layers():
    for sid, (layer, crs, origin) in OVERSEAS.items():
        s = src.SOURCES[sid]
        assert isinstance(s.nmt, WmsrTiles) and s.nmt.reader.layer == layer and s.nmpt is None, sid
        assert s.crs == s.nmt.crs == crs and s.nmt.origin == origin, sid
        assert s.grid_origin == origin, sid  # the working grid's edges on the stored pixels' edges
        assert s.default_resolution == 1.0 and s.fallbacks == ["europe"] and s.neighbours == (), sid
        assert s.nmt.folder.startswith("france/rgealti-1m-") and s.nmt.folder.endswith("/live"), sid
        assert s.ortho is src.SOURCES["france"].ortho and s.credits == src.SOURCES["france_rgealti"].credits, sid
        assert s.countries == ("fr",) and not s.regions, sid
        for area in s.map_areas():
            assert area in src.AREA_NAMES, (sid, area)
    assert src.SOURCES["france_guadeloupe"].map_areas() == ("fr-gp", "bl", "mf")


# Per layer the recorded 32 m box on its declared pixel edges: (source, the answer at 1 m, at 0.5 m, its corner)
ALIGNMENT = [("france_guadeloupe", 1, 2, SOUFRIERE), ("france_martinique", 4, 5, (704544.5, 1626528.5)),
             ("france_guiana", 6, 7, (359168.0, 539520.0)), ("france_spm", 8, 9, (562592.5, 5181024.5))]


def test_the_alignment_recordings_are_the_layers_requests():
    """Each recording is the GetMap its layer writes for that box (the BBOX on the declared origin)."""
    with open(os.path.join(RECORDED, "requests.json"), encoding="utf-8") as f:
        urls = {a["body"]: a["url"] for a in json.load(f)["answers"]}
    from sources.readers.wmsr import MapRequest
    from urllib.parse import parse_qsl
    for sid, one, half, (x, y) in ALIGNMENT:
        layer = src.SOURCES[sid].nmt
        assert ((x - layer.origin[0]) % 32, (y - layer.origin[1]) % 32) == (0, 0), sid
        for n, px in ((one, 32), (half, 64)):
            asked = dict(parse_qsl(urlsplit(urls[f"{n:03d}.tif"]).query, keep_blank_values=True))
            assert asked == dict(layer.reader.getmap_params(MapRequest(x, y, x + 32, y + 32, px, px))), (sid, n)


@pytest.mark.parametrize("sid, one, half, corner", ALIGNMENT)
def test_the_declared_pixel_edges(sid, one, half, corner):
    """The 1 m answer on the layer's declared edges (half metres in the Antilles and Saint-Pierre-et-Miquelon,
    whole metres in French Guiana) is the stored pixels: at 0.5 m on the same box the server repeats each of them in
    a 2 x 2 block (nearest), which starts on those edges. Declared half a metre off, the blocks would straddle the
    0.5 m pixel pairs and differ from the 1 m answer."""
    a, transform = _answer(one)
    b, _ = _answer(half)
    assert (transform.c, transform.f) == (corner[0], corner[1] + 32)
    assert np.isfinite(a).all() and np.isfinite(b).all()
    assert np.ptp(a) > 1  # relief: equal blocks are not flat ground
    for dy in (0, 1):
        for dx in (0, 1):
            assert np.array_equal(b[dy::2, dx::2], a), (sid, dy, dx)


def test_a_tile_on_the_half_metre_edges(service, tmp_path):
    layer = _layer(service)
    i, j = round((SOUFRIERE[0] - 0.5) / 32), round((SOUFRIERE[1] - 0.5) / 32)
    assert layer.index.request((1.0, i, j))[:4] == (SOUFRIERE[0], SOUFRIERE[1], SOUFRIERE[0] + 32,
                                                    SOUFRIERE[1] + 32)
    path = layer.tile_path(str(tmp_path), (1.0, i, j))
    assert path.replace(os.sep, "/").endswith(f"france/test-glp/live/epsg32620-1m-32px-tif-o0.5_0.5/{i}_{j}.tif")
    assert layer.download_tile((1.0, i, j), path).received > 0
    with rio.open(path) as raster:
        assert raster.transform.c == SOUFRIERE[0] and raster.transform.f == SOUFRIERE[1] + 32
        assert raster.crs.to_epsg() == 32620
        cached = raster.read(1, masked=True).astype(np.float32).filled(np.nan)
    assert same_tile(cached, _answer(1)[0])


def test_sint_maarten_is_missing(service, tmp_path):
    """The Dutch side of the island: every pixel nodata (-99999, HTTP 200), so no tile and the fallback fills it."""
    layer = _layer(service)
    i, j = round((SINT_MAARTEN[0] - 0.5) / 32), round((SINT_MAARTEN[1] - 0.5) / 32)
    path = layer.tile_path(str(tmp_path), (1.0, i, j))
    assert layer.download_tile((1.0, i, j), path).received == 0
    assert not os.path.exists(path)


# (lat, lon, the country Nominatim names at zoom 3 (asked 2026-11-15), the source --source auto takes)
PLACES = [(16.044, -61.664, "fr", "france_guadeloupe"), (17.90, -62.83, "fr", "france_guadeloupe"),
          (18.08, -63.05, "fr", "france_guadeloupe"), (18.03, -63.06, "nl", "europe"),
          (14.705, -61.100, "fr", "france_martinique"), (4.93, -52.33, "fr", "france_guiana"),
          (46.78, -56.18, "fr", "france_spm"), (47.05, -56.38, "fr", "france_spm"),
          (-21.11, 55.53, "fr", "europe"), (-12.78, 45.23, "fr", "europe"),  # Réunion, Mayotte: not declared
          (43.7655, 6.3580, "fr", "france")]


@pytest.mark.parametrize("lat, lon, code, expected", PLACES)
def test_the_source_of_a_place(monkeypatch, tmp_path, lat, lon, code, expected):
    monkeypatch.setattr(osm, "reverse", lambda *args, **kwargs: {"address": {"country_code": code}})
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == expected


@pytest.mark.parametrize("lat, lon, code, expected", [p for p in PLACES if p[0] > 0 and p[2] == "fr"])
def test_the_source_of_a_place_offline(monkeypatch, tmp_path, lat, lon, code, expected):
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    assert src.choose.choose_source("auto", lat, lon, str(tmp_path))[0].id == expected
