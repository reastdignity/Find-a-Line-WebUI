"""--source auto with sources of a region (Source.regions): the region looked up only for a country
with such sources, a region's source before its country's, the offline boxes of regions. Offline:
real reverse answers recorded on 2026-11-01 (tests/data/recorded/nominatim/reverse.json)."""

import dataclasses
import json
import os
import sys

import pytest
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import osm  # noqa: E402
import sources as src  # noqa: E402
from jobs import QuotaExceeded  # noqa: E402

RECORDED = os.path.join(REPO, "tests", "data", "recorded", "nominatim", "reverse.json")
SNOWDONIA = (53.1597, -3.9701)     # Carnedd Llewelyn: GB-WLS
SEA = (51.89, -5.34)               # off St David's Head, in the sea: GB-WLS
LAKES = (54.4542, -3.2116)         # Scafell Pike: GB-ENG
BROCKEN = (51.7995, 10.6156)       # the Harz: DE-ST
AURICH = (53.708, 7.15)            # the coast of East Frisia: DE-NI
ORTLER = (46.509, 10.545)          # IT-32 and IT-BZ
TRENTO = (46.07, 11.12)            # IT-32 and IT-TN
WALES_BOX = ("gb-wls", (51.3, 53.5, -5.4, -2.6))
GB_BOX = ("gb", (49.8, 60.9, -8.7, 1.8))


@pytest.fixture
def recorded(monkeypatch):
    """osm.reverse answering from the recorded answers; the zooms asked, in order."""
    with open(RECORDED, encoding="utf-8") as f:
        answers = {(r["query"]["lat"], r["query"]["lon"], r["query"]["zoom"]): r["answer"] for r in json.load(f)}
    asked = []

    def reverse(lat, lon, cache_dir, **params):
        asked.append(params["zoom"])
        return answers[(round(lat, 5), round(lon, 5), params["zoom"])]
    monkeypatch.setattr(osm, "reverse", reverse)
    return asked


def _like_europe(sid, **fields):
    return dataclasses.replace(src.SOURCES["europe"], id=sid, name=sid, **fields)


@pytest.fixture
def without_regional(monkeypatch):
    """The catalogue without its sources of regions (the tests below make their own)."""
    for sid, source in list(src.choose.SOURCES.items()):
        if source.regions:
            monkeypatch.delitem(src.choose.SOURCES, sid)
    monkeypatch.setattr(src.choose, "OFFLINE_BOXES", [b for b in src.choose.OFFLINE_BOXES if "-" not in b[0]])


@pytest.fixture
def regional(monkeypatch, without_regional):
    """A country-wide source of GB before Wales's, then Lower Saxony's and Bolzano's after europe,
    all at the end of SOURCES (the region decides, not the order)."""
    for source in (_like_europe("gb_all", countries=("gb",), offline=(GB_BOX,)),
                   _like_europe("wales", countries=("gb",), regions=("gb-wls",), offline=(WALES_BOX,)),
                   _like_europe("niedersachsen", countries=("de",), regions=("de-ni",)),
                   _like_europe("bolzano", countries=("it",), regions=("it-bz",))):
        monkeypatch.setitem(src.choose.SOURCES, source.id, source)
    monkeypatch.setattr(src.choose, "OFFLINE_BOXES", [WALES_BOX, GB_BOX])


def test_region_source_inside_its_region(tmp_path, recorded, regional):
    """A region's source inside its region (lvl4: GB-WLS, DE-NI; lvl6: IT-BZ), also for a centre in
    the sea, its country's source or europe elsewhere; the reason names the region that decided."""
    expected = {SNOWDONIA: ("wales", "the centre is in GB-WLS"), SEA: ("wales", "the centre is in GB-WLS"),
                LAKES: ("gb_all", "the centre is in GB"), AURICH: ("niedersachsen", "the centre is in DE-NI"),
                BROCKEN: ("europe", "no national source for DE"), ORTLER: ("bolzano", "the centre is in IT-BZ"),
                TRENTO: ("europe", "no national source for IT")}
    for (lat, lon), (sid, reason) in expected.items():
        recorded.clear()
        source, why = src.choose_source("auto", lat, lon, str(tmp_path))
        assert (source.id, why) == (sid, reason), (lat, lon)
        assert recorded == [3, src.choose.REGION_ZOOM]


def test_no_region_lookup_without_regional_sources(tmp_path, recorded, monkeypatch, without_regional):
    """A catalogue without sources of regions: one lookup at zoom 3, as before; with a
    regional source of GB only, a point in Germany is not asked again either."""
    assert not any(s.regions for s in src.choose.SOURCES.values())
    assert src.choose_source("auto", *SNOWDONIA, str(tmp_path)) == (src.SOURCES["europe"], "no national source for GB")
    assert recorded == [3]
    monkeypatch.setitem(src.choose.SOURCES, "wales", _like_europe("wales", countries=("gb",), regions=("gb-wls",)))
    recorded.clear()
    assert src.choose_source("auto", *AURICH, str(tmp_path))[0].id == "europe"
    assert recorded == [3]


def test_region_codes(tmp_path, recorded):
    """Every level Nominatim names, lower case, of the point's country only."""
    assert src.choose.region_codes(*ORTLER, str(tmp_path), "it") == ("it-32", "it-bz")
    assert src.choose.region_codes(*SNOWDONIA, str(tmp_path), "gb") == ("gb-wls", "gb-cwy")
    assert src.choose.region_codes(*SNOWDONIA, str(tmp_path), "ie") == ()


def test_region_from_offline_boxes_under_quota(tmp_path, monkeypatch, regional):
    """The country cached, the region's lookup refused by the user's quota (a ValueError): the
    region comes from the offline boxes, as the country does when its lookup fails."""
    cache_dir = str(tmp_path)
    for lat, lon in (SNOWDONIA, LAKES):
        key = json.dumps({"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 3}, sort_keys=True)
        osm._store(cache_dir, "reverse", key, {"address": {"country_code": "gb"}})

    def refuse():
        raise QuotaExceeded("quota")
    monkeypatch.setattr(osm, "BEFORE_REQUEST", refuse)
    assert src.choose_source("auto", *SNOWDONIA, cache_dir)[1] == "the centre is in GB-WLS"
    assert src.choose_source("auto", *LAKES, cache_dir)[1] == "the centre is in GB"


def test_region_offline(tmp_path, monkeypatch, regional):
    """Offline: a region's box gives its country (country_code: gb, also for the jobs' statistics)
    and its region; the first box holding a point wins, as for countries."""
    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(osm, "reverse", offline)
    cache_dir = str(tmp_path)
    assert src.choose.country_code(*SNOWDONIA, cache_dir) == "gb"
    assert src.choose.region_codes(*SNOWDONIA, cache_dir, "gb") == ("gb-wls",)
    assert src.choose.region_codes(*SNOWDONIA, cache_dir, "fr") == ()
    assert src.choose.region_codes(*LAKES, cache_dir, "gb") == ()
    assert src.choose_source("auto", *SNOWDONIA, cache_dir)[0].id == "wales"
    assert src.choose_source("auto", *LAKES, cache_dir)[0].id == "gb_all"
    assert src.choose_source("auto", 48.0, 2.0, cache_dir) == (src.SOURCES["europe"], "no national source for this place")


def test_catalogue_regions(tmp_path, recorded):
    """The catalogue's sources of regions: Lower Saxony's at the coast of East Frisia."""
    assert (src.choose_source("auto", *AURICH, str(tmp_path))
            == (src.SOURCES["lower_saxony"], "the centre is in DE-NI"))
