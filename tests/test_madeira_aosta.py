"""Madeira (portugal.py) and Valle d'Aosta (italy.py): our own 2 km tiles from the local mirror (tools/mirror_tiles.py).
--source auto takes them in their regions when the mirror holds them; without it says why and takes the next source
of the place (TINITALY in Valle d'Aosta, europe in Madeira, as Slovakia); the offline boxes keep Valle d'Aosta off
France."""

import json
import os
import sys

import pytest
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402

CABO_GIRAO = (32.655, -17.004)      # R80
ARNAD = (45.648, 7.720)             # R81
TIGNES = (45.47, 6.90)              # the Tarentaise, France: in the brief's box, not in the region's bands
PORTO_SANTO = (33.07, -16.34)       # Madeira's region (pt-30), no 2 m data there
PONT_SAINT_MARTIN = (45.597, 7.795)  # Valle d'Aosta's south-eastern tip
IVREA = (45.467, 7.876)             # the Canavese, Piedmont: not Valle d'Aosta's
VALCHIUSELLA = (45.50, 7.75)        # Piedmont
ANSWERS = {CABO_GIRAO: {"country_code": "pt", "ISO3166-2-lvl4": "PT-30"},
           PORTO_SANTO: {"country_code": "pt", "ISO3166-2-lvl4": "PT-30"},
           ARNAD: {"country_code": "it", "ISO3166-2-lvl4": "IT-23"}}


@pytest.fixture
def online(monkeypatch):
    """osm.reverse answering as Nominatim did on 2026-11-15 (reverse at zoom 10: PT-30, IT-23)."""
    monkeypatch.setattr(osm, "reverse", lambda lat, lon, cache_dir, **params: {"address": ANSWERS[(lat, lon)]})


@pytest.fixture
def offline(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", fail)


def _mirror(tmp_path, *folders):
    """A mirror holding the folders (an index without tiles: enough to be available)."""
    for folder in folders:
        path = tmp_path / "mirror" / folder
        path.mkdir(parents=True)
        (path / "index.json").write_text(json.dumps({"tiles": {}}), encoding="utf-8")
    return str(tmp_path / "mirror")


def test_without_the_mirror(tmp_path, monkeypatch, online):
    """Without FINDALINE_MIRROR (or without the dataset's folder in it) auto says why and takes the next source of
    the place: europe in Madeira (no other Portuguese source), TINITALY in Valle d'Aosta (not europe: TINITALY was
    Valle d'Aosta's source before)."""
    monkeypatch.delenv(src.MIRROR_ENV, raising=False)
    # the tool that makes each mirror is named (Slovakia's its own)
    for sid, tool in (("madeira", "tools/mirror_tiles.py"), ("aosta_valley", "tools/mirror_tiles.py"),
                      ("slovakia", "tools/sk_tiles.py")):
        assert f"(made by {tool})" in src.SOURCES[sid].nmt.unavailable(), sid
    source, why = src.choose_source("auto", *CABO_GIRAO, str(tmp_path))
    assert source.id == "europe" and why.startswith("the centre is in PT-30, but") and "FINDALINE_MIRROR" in why
    source, why = src.choose_source("auto", *ARNAD, str(tmp_path))
    assert source.id == "tinitaly" and why.startswith("the centre is in IT-23, but") and "aosta/dtm/2m" in why
    monkeypatch.setenv(src.MIRROR_ENV, _mirror(tmp_path, "slovakia/dmr5/1m"))
    assert src.choose_source("auto", *ARNAD, str(tmp_path))[0].id == "tinitaly"
    with pytest.raises(ValueError, match="does not exist"):
        src.choose_source("madeira", *CABO_GIRAO, str(tmp_path))


def test_with_the_mirror(tmp_path, monkeypatch, online):
    """With their folders in the mirror auto takes them in their regions, Porto Santo too (its gaps from europe)."""
    monkeypatch.setenv(src.MIRROR_ENV, _mirror(tmp_path, "madeira/dtm/2m", "aosta/dtm/2m"))
    assert src.choose_source("auto", *CABO_GIRAO, str(tmp_path)) == (src.SOURCES["madeira"], "the centre is in PT-30")
    assert src.choose_source("auto", *PORTO_SANTO, str(tmp_path))[0].id == "madeira"
    assert src.choose_source("auto", *ARNAD, str(tmp_path)) == (src.SOURCES["aosta_valley"], "the centre is in IT-23")


def test_offline_boxes(tmp_path, monkeypatch, offline):
    """Offline the region boxes decide: Madeira's and Valle d'Aosta's; the Tarentaise (France) inside the brief's
    box is not Valle d'Aosta's; north of 45.8 N Switzerland's box comes first (as before)."""
    monkeypatch.setenv(src.MIRROR_ENV, _mirror(tmp_path, "madeira/dtm/2m", "aosta/dtm/2m"))
    assert src.choose_source("auto", *CABO_GIRAO, str(tmp_path))[0].id == "madeira"
    assert src.choose_source("auto", *ARNAD, str(tmp_path))[0].id == "aosta_valley"
    assert src.choose_source("auto", *TIGNES, str(tmp_path))[0].id != "aosta_valley"
    assert src.choose_source("auto", *PONT_SAINT_MARTIN, str(tmp_path))[0].id == "aosta_valley"
    for point in (IVREA, VALCHIUSELLA):  # Piedmont: Italy's boxes, TINITALY
        assert src.choose_source("auto", *point, str(tmp_path))[0].id == "tinitaly", point
    assert src.choose_source("auto", 45.93, 7.63, str(tmp_path))[0].id == "swisstopo"  # Cervinia


def test_the_dsm_follows_by_hand():
    """Valle d'Aosta has no surface model yet: its module, README row and note say the DSM follows later (the user's
    words); Madeira has none at all. Both are 2 m on their own grids, our own tiles with no remote base yet."""
    import sources.catalogue.italy as italy
    aosta, madeira = src.SOURCES["aosta_valley"], src.SOURCES["madeira"]
    assert aosta.nmpt is None and "DSM follows by hand later" in aosta.listing.surface
    assert "DSM follows by hand later" in italy.__doc__ and "surface model follows later" in aosta.note
    assert madeira.nmpt is None and madeira.listing.surface == "–"
    for source in (aosta, madeira):
        assert source.nmt.urls == [] and source.default_resolution == 2.0 and source.neighbours == ()
    assert aosta.fallbacks == ["tinitaly", "europe"] and madeira.fallbacks == ["europe"]
