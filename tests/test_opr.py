"""USGS's OPR DEMs as the layer `OprBlocks` and the source `usa_opr` (sources/layers/tnm.py, oprsurveys.py): WESM as a
cached listing, the survey's record with its measured height unit, the items and the blocks' key, the blocks made
end to end, and the source's place in the catalogue. Everything on the local test server (tests/http_server.py):
the TNM index, WESM, the survey's files and the 1/3 arc-second DEM they are measured against."""

import json
import os
import re
import sqlite3
import sys

import numpy as np
import pytest
import rasterio as rio
from pyproj import Transformer
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer, only_local_hosts  # noqa: E402
from sources.indexes.cached import IndexUnavailable  # noqa: E402
from sources.indexes.versions import block_key  # noqa: E402
from sources.layers import oprsurveys as ops  # noqa: E402
from sources.layers import tnm  # noqa: E402

ZONE = "EPSG:26913"
X0, Y0 = 500000.0, 4400000.0
PROJECT = "StagedProducts/Elevation/OPR/Projects"
COLUMNS = ["workunit", "workunit_id", "project", "project_id", "collect_start", "collect_end", "ql", "spec",
           "p_method", "dem_gsd_meters", "horiz_crs", "vert_crs", "geoid", "lpc_pub_date", "lpc_update",
           "lpc_category", "lpc_reason", "sourcedem_pub_date", "sourcedem_update", "sourcedem_category",
           "sourcedem_reason", "onemeter_category", "onemeter_reason", "seamless_category", "seamless_reason",
           "lpc_link", "sourcedem_link", "metadata_link"]


COAST = X0 + 3000  # east of it a flat shore about 1 m above the sea


def terrain(x, y):
    """Ground at zone coordinates: hills around 900 m, east of COAST a flat shore about 1 m high."""
    hills = 900 + 60 * np.sin((x - X0) / 300.0) + 40 * np.cos((y - Y0) / 250.0)
    shore = 1.0 + 0.3 * np.sin((y - Y0) / 80.0)
    return np.where(x < COAST, hills, shore).astype(np.float32)


def sp(x, y):
    """Zone coordinates in NAD83 / Colorado Central (ftUS), EPSG:2232."""
    return Transformer.from_crs(ZONE, "EPSG:2232", always_xy=True).transform(x, y)


def write_tif(path, crs, transform, band, nodata=-999999.0, overviews=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    band = np.where(np.isnan(band), nodata, band).astype(np.float32)
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=nodata, transform=transform, tiled=True, blockxsize=64, blockysize=64) as dst:
        dst.write(band, 1)
        if overviews:
            dst.build_overviews([2, 4])


def opr_file(path, crs, left, top, res, size, unit=1.0, overviews=True):
    """A survey's file in crs: the terrain at its pixel centres, in its unit (0.3048: feet)."""
    t = from_origin(left, top, res, res)
    cols, rows = np.meshgrid(np.arange(size) + 0.5, np.arange(size) + 0.5)
    xs, ys = t @ (cols, rows)
    if crs != ZONE:
        xs, ys = Transformer.from_crs(crs, ZONE, always_xy=True).transform(xs, ys)
    write_tif(path, crs, t, terrain(xs, ys) / np.float32(unit), overviews=overviews)


def reference_file(path):
    """The 1/3 arc-second DEM over the test's place (NAD83 degrees, about 10 m), the same terrain in metres."""
    to_deg = Transformer.from_crs(ZONE, "EPSG:4269", always_xy=True)
    west, south = to_deg.transform(X0 - 3000, Y0 - 3000)
    east, north = to_deg.transform(X0 + 6000, Y0 + 6000)
    res = 1 / 10800
    t = from_origin(west, north, res, res)
    w, h = int((east - west) / res) + 1, int((north - south) / res) + 1
    cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    lons, lats = t @ (cols, rows)
    xs, ys = Transformer.from_crs("EPSG:4269", ZONE, always_xy=True).transform(lons, lats)
    write_tif(path, "EPSG:4269", t, terrain(xs, ys))


class Reference:
    """The 1/3 arc-second DEM's layer as OprIndex asks it (url of a 1° tile): every tile is the test's file."""

    def __init__(self, url):
        self.url = lambda name: url


def wesm_text(rows):
    lines = [",".join(COLUMNS)]
    for row in rows:
        lines.append(",".join(str(row.get(c, "")) for c in COLUMNS))
    return ("﻿" + "\n".join(lines) + "\n").encode()


def wesm_row(workunit, project="P_2019", end="2019/06/30", method="linear-mode lidar", **more):
    row = {"workunit": workunit, "project": project, "collect_end": end, "p_method": method,
           "sourcedem_link": f"https://prd-tnm.s3.amazonaws.com/index.html?prefix={PROJECT}/{project}/{workunit}",
           "sourcedem_category": "Meets", "onemeter_category": "Does not meet"}
    row.update(more)
    return row


class Place:
    """The test server holding the TNM index (its products), WESM and the files."""

    def __init__(self, server, tmp_path, monkeypatch):
        self.server, self.tmp = server, tmp_path
        self.products, self.wesm, self.etag = [], [], '"v1"'
        server.route("/api/v1/products", self._products)
        server.route("/wesm.csv", self._wesm)
        monkeypatch.setattr(ops, "WESM_URL", server.url("/wesm.csv"))
        reference_file(str(tmp_path / "ref" / "ref.tif"))
        server.add_folder("/ref", str(tmp_path / "ref"))
        monkeypatch.setattr(tnm.OprIndex, "reference", Reference(server.url("/ref/ref.tif")))

    def _products(self, request):
        q = dict(request.query)
        offset, size = int(q["offset"]), int(q["max"])
        return Answer(200, json.dumps({"total": len(self.products),
                                       "items": self.products[offset:offset + size]}).encode(),
                      {"Content-Type": "application/json"})

    def _wesm(self, request):
        if request.headers.get("if-none-match") == self.etag:
            return Answer(304, b"", {"ETag": self.etag})
        return Answer(200, wesm_text(self.wesm), {"Content-Type": "text/csv", "ETag": self.etag})

    def add_file(self, workunit, name, crs, left, top, res, size, project="P_2019", **kw):
        """A survey's file on the server and its product in the index (its box from its extent)."""
        path = self.file_path(workunit, name, project)
        opr_file(path, crs, left, top, res, size, **kw)
        return self.add_path(workunit, name, project)

    def file_path(self, workunit, name, project="P_2019"):
        return str(self.tmp / "files" / f"{PROJECT}/{project}/{workunit}/TIFF/{name}.tif")

    def add_path(self, workunit, name, project="P_2019"):
        """A file already written at file_path() served and listed."""
        rel = f"{PROJECT}/{project}/{workunit}/TIFF/{name}.tif"
        path = self.file_path(workunit, name, project)
        with open(path, "rb") as f:
            self.server.add("/" + rel, f.read(), "image/tiff")
        with rio.open(path) as dst:
            b = rio.warp.transform_bounds(dst.crs, "EPSG:4326", *dst.bounds)
        self.products.append({"downloadURL": self.server.url("/" + rel), "publicationDate": "1899-12-30",
                              "boundingBox": {"minX": b[0], "minY": b[1], "maxX": b[2], "maxY": b[3]}})
        return self.server.url("/" + rel)

    def layer(self):
        return tnm.OprBlocks("Test OPR", "OPR", "opr", "usa/3dep-opr", native_res=1.0, block_m=1000,
                             bytes_per_tile=2e6, api=self.server.url("/api/v1/products"))


def _age(cache_dir, path, days):
    """Set a file's index row's check time back by days."""
    top, inner = cache._split(cache_dir, path)
    db = sqlite3.connect(os.path.join(cache_dir, top, "index.sqlite"))
    db.execute("UPDATE files SET checked_at = ? WHERE path = ?", (cache.now_iso(days * 86400), inner))
    db.commit()
    db.close()


@pytest.fixture(autouse=True)
def _only_the_test_server():
    """Every test of this file asks the test server only (http_server.only_local_hosts: Python's sockets and GDAL
    through net.open_gdal); an outside host fails the test (fix round 3)."""
    with only_local_hosts() as asked:
        yield
    assert not asked, f"the test asked outside hosts: {sorted(set(asked))}"


def test_the_guard_stops_outside_hosts():
    """The guard itself: a request to an outside host and a GDAL open of one fail at once and are listed."""
    import requests
    with only_local_hosts() as asked:
        with pytest.raises(requests.RequestException):
            requests.get("https://tnmaccess.nationalmap.gov/api/v1/products", timeout=5)
        with pytest.raises(OSError, match="outside host"):
            src.net.open_gdal("/vsicurl/https://prd-tnm.s3.amazonaws.com/x.tif")
    assert asked == ["tnmaccess.nationalmap.gov", "prd-tnm.s3.amazonaws.com"]


@pytest.fixture
def place(http_server, tmp_path, monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    return Place(http_server, tmp_path, monkeypatch)


# WESM

def test_wesm_cached_listing(place, tmp_path, capsys):
    """WESM fetched through the app's path into usa/sheet-index/wesm/WESM.csv with its row; a search fetches it
    only when none is cached; a renewal makes it again after 28 days (a 304 for its ETag: nothing comes), a failed
    or refused fetch keeps the table there was and is not tried again within a day; a file's survey by
    sourcedem_link."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_A"), wesm_row("W_B", project="Q-2018")]
    ops.ensure_wesm(cache_dir)
    path = ops.wesm_path(cache_dir)
    assert path == os.path.join(cache_dir, "usa", "sheet-index", "wesm", "WESM.csv") and os.path.exists(path)
    row = cache.info(cache_dir, path)
    assert row["url"] == place.server.url("/wesm.csv") and row["etag"] == '"v1"'
    ops.ensure_wesm(cache_dir)
    assert ops.renew_wesm(cache_dir) == "kept"  # fresh: nothing asked
    assert len(place.server.requests("/wesm.csv")) == 1
    table = ops.table(cache_dir)
    assert table.survey_of(place.server.url(f"/{PROJECT}/Q-2018/W_B/TIFF/x.tif"))["workunit"] == "W_B"
    assert table.survey_of(place.server.url(f"/{PROJECT}/P_2019/W_A_more/TIFF/x.tif")) is None  # a folder, not a prefix
    _age(cache_dir, path, 29)
    assert ops.renew_wesm(cache_dir) == "same"  # 304: only the check time
    assert ops.wesm_age_days(cache_dir) < 0.01
    # a table that shrank by more than 2 %: refused, the table kept, no new try within a day
    place.etag, place.wesm = '"v2"', [wesm_row("W_A")]
    _age(cache_dir, path, 29)
    assert ops.renew_wesm(cache_dir) == "failed"
    assert "refused" in capsys.readouterr().out and len(ops.table(cache_dir).rows) == 2
    assert ops.renew_wesm(cache_dir) == "kept" and "not fetched again before a day" in capsys.readouterr().out
    assert ops.renew_wesm(cache_dir, force=True) == "kept"  # force still waits for a failure's day
    # not the table at all (columns missing): IndexUnavailable, the table kept
    place.server.add("/maintenance.csv", b"<html>maintenance</html>", "text/html")
    with pytest.raises(IndexUnavailable, match="not the table of surveys"):
        ops.fetch_wesm(cache_dir, url=place.server.url("/maintenance.csv"))
    assert len(ops.table(cache_dir).rows) == 2


def test_wesm_renewed_by_a_renewal_and_cache_update(place, tmp_path):
    """A renewal over a layer that reads WESM (sources/renewal.py renew) makes the table when it is missing or older
    than 28 days and leaves a fresh one, and asks again only the OPR answers already cached; `cache update usa`
    (update.checks) checks the table first when it is due, never when it is fresh."""
    import update
    from sources import renewal
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_A")]
    layer = place.layer()
    grid = make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE)
    done = renewal.renew([layer], grid, cache_dir, say=lambda text: None)
    assert done.wesm == "made" and os.path.exists(ops.wesm_path(cache_dir))
    # no OPR answer cached: the renewal asks none (only those a usa_opr search cached)
    assert done.asked == 0 and place.server.requests("/api/v1/products") == []
    layer._use(cache_dir)
    layer.tiles(grid)  # a search caches the answers of its tiles (and of those a block reaches: F1)
    from sources.indexes.cached import index_tiles
    searched = len(place.server.requests("/api/v1/products"))
    under = index_tiles(grid)  # the renewal's tiles: those under the grid, all cached now
    assert searched >= len(under) >= 1
    # (since: a minute ahead, so the answers cached within the same second count as not asked yet)
    again = renewal.renew([place.layer()], grid, cache_dir, say=lambda text: None, since=cache.now_iso(-60))
    assert again.wesm == "kept" and again.asked == len(under)
    assert len(place.server.requests("/api/v1/products")) == searched + len(under)
    assert len(place.server.requests("/wesm.csv")) == 1
    found = [c for c in update.checks(cache_dir, "usa") if c.path == "usa/sheet-index/wesm/WESM.csv"]
    assert found == []  # fresh
    _age(cache_dir, ops.wesm_path(cache_dir), 29)
    found = [c for c in update.checks(cache_dir, "usa") if c.path == "usa/sheet-index/wesm/WESM.csv"]
    assert len(found) == 1 and found[0].first
    assert found[0].action() is False  # the server's 304 for its ETag: checked, nothing new
    assert ops.wesm_age_days(cache_dir) < 0.01 and len(place.server.requests("/wesm.csv")) == 2


# The survey's record

def test_survey_records(place, tmp_path, capsys):
    """Decided metres, decided feet, undecided (flat, at sea level), headers that disagree, a geographic CRS, a
    survey that is not lidar: each record says why it is not read; made again when its WESM row changes."""
    cache_dir = str(tmp_path / "cache")
    ref = ops.reference_url(tnm.OprIndex.reference)
    metres = [place.add_file("W_M", f"m{k}", ZONE, X0 + k * 600, Y0 + 600, 0.5, 1200) for k in range(3)]
    left, top = sp(X0, Y0 + 600)
    feet = [place.add_file("W_F", "f0", "EPSG:2232", left, top, 2.5, 800, unit=1200 / 3937)]
    flat = [place.add_file("W_L", "l0", ZONE, COAST + 500, Y0 + 600, 1.0, 600)]
    mixed = [place.add_file("W_X", "x0", ZONE, X0, Y0 + 600, 0.5, 600),
             place.add_file("W_X", "x1", ZONE, X0 + 300, Y0 + 600, 2.0, 300)]
    geo = [place.add_file("W_G", "g0", "EPSG:4269", -105.0, 39.76, 1e-5, 300)]
    rows = {w: wesm_row(w) for w in ("W_M", "W_F", "W_L", "W_X", "W_G")}
    rows["W_I"] = wesm_row("W_I", method="IfSAR")

    record = ops.survey_record(cache_dir, rows["W_M"], metres, ref)
    assert record["read"] and record["unit"] == "metre" and record["factor"] == 1.0
    assert record["year"] == 2019 and record["collect_end"] == "2019-06-30" and record["pixel_m"] == 0.5
    assert record["files"] and record["windows"][-1]["verdict"] == "metre" and record["rule"] == ops.RULE
    assert os.path.exists(ops.record_path(cache_dir, "W_M"))
    record = ops.survey_record(cache_dir, rows["W_F"], feet, ref)
    assert record["read"] and record["unit"] == "US survey foot" and record["factor"] == pytest.approx(1200 / 3937)
    assert record["pixel_m"] == pytest.approx(0.762, abs=1e-3) and not record["on_metres"]
    record = ops.survey_record(cache_dir, rows["W_L"], flat, ref)
    assert not record["read"] and record["unit"] == "undecided"
    assert record["reason"] == "its height unit could not be told"
    record = ops.survey_record(cache_dir, rows["W_X"], mixed, ref)
    assert not record["read"] and record["pixel_m"] == 2.0
    assert sorted(h["pixel_m"] for h in record["headers"]) == [0.5, 2.0]  # the headers that disagree, each kept
    assert "coarser than 1.001 m" in record["reason"]
    record = ops.survey_record(cache_dir, rows["W_G"], geo, ref)
    assert not record["read"] and "no projected CRS" in record["reason"]
    record = ops.survey_record(cache_dir, rows["W_I"], [], ref)
    assert not record["read"] and record["reason"] == "not lidar (IfSAR)"

    # the cached record while the row is the same; made again (asked again) when collect_end changed
    asked = len(place.server.requests())
    assert ops.survey_record(cache_dir, rows["W_M"], metres, ref)["made_at"]
    assert len(place.server.requests()) == asked
    changed = dict(rows["W_M"], collect_end="2020/01/15")
    record = ops.survey_record(cache_dir, changed, metres, ref)
    assert record["year"] == 2020 and len(place.server.requests()) > asked


def test_a_file_cut_at_4gb(place, tmp_path, monkeypatch, capsys):
    """A mosaic cut at 4 GB (a classic TIFF at the format's limit whose last tiles have no offset: GDAL reads them as
    nodata without an error) is never read: its survey's record says so, the survey gives no item and is named once.
    Made up as a small sparse file with the limit set to its size."""
    cache_dir = str(tmp_path / "cache")
    rel = f"{PROJECT}/P_2019/W_CUT/TIFF/cut.tif"
    path = str(tmp_path / "files" / rel)
    os.makedirs(os.path.dirname(path))
    t = from_origin(X0, Y0 + 640, 1.0, 1.0)
    with rio.open(path, "w", driver="GTiff", width=640, height=640, count=1, dtype="float32", crs=ZONE,
                  nodata=-999999.0, transform=t, tiled=True, blockxsize=64, blockysize=64, sparse_ok=True) as dst:
        cols, rows = np.meshgrid(np.arange(640) + 0.5, np.arange(320) + 0.5)
        xs, ys = t @ (cols, rows)
        dst.write(terrain(xs, ys), 1, window=rio.windows.Window(0, 0, 640, 320))  # the south half never written
        dst.build_overviews([2, 4])
    with open(path, "rb") as f:
        body = f.read()
    place.server.add("/" + rel, body, "image/tiff")
    monkeypatch.setattr(ops, "CLASSIC_LIMIT", len(body))
    place.wesm = [wesm_row("W_CUT")]
    b = rio.warp.transform_bounds(ZONE, "EPSG:4326", X0, Y0, X0 + 640, Y0 + 640)
    place.products.append({"downloadURL": place.server.url("/" + rel), "publicationDate": "1899-12-30",
                           "boundingBox": {"minX": b[0], "minY": b[1], "maxX": b[2], "maxY": b[3]}})
    record = ops.survey_record(cache_dir, wesm_row("W_CUT"), [place.server.url("/" + rel)],
                               ops.reference_url(tnm.OprIndex.reference))
    assert not record["read"] and "cut.tif was cut at 4 GB" in record["reason"]
    layer = place.layer()
    grid = make_grid((X0 + 10, Y0 + 10, X0 + 600, Y0 + 600), 1.0, ZONE)
    layer._use(cache_dir)
    assert layer.tiles(grid) == [] and layer.index.answers(cache_dir, *_tile_of(grid)) == []
    assert capsys.readouterr().out.count("survey W_CUT left out: its file cut.tif was cut at 4 GB") == 1
    monkeypatch.setattr(ops, "CLASSIC_LIMIT", 2 ** 32)  # the same file far below 4 GB: not cut
    record = ops.make_record(cache_dir, wesm_row("W_CUT"), [place.server.url("/" + rel)],
                             ops.reference_url(tnm.OprIndex.reference))
    assert "cut" not in record["reason"]


def test_a_failed_measurement_waits_a_day(place, tmp_path, monkeypatch, capsys):
    """The code review's F5: a survey whose measurement failed (its host closing every connection) is measured once:
    two answers read in a row ask its files once, the failure remembered for a day (<work unit>.failed.json), and
    each such answer fails (tnm.SurveyNotRead, an IndexUnavailable: the second review's N4); a CRS that cannot be
    transformed gives a record "not read" with the reason, not a raise (it would be measured again at every
    answer)."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_DOWN")]
    url = place.add_file("W_DOWN", "d0", ZONE, X0, Y0 + 600, 1.0, 600)
    path = "/" + url.split("/", 3)[3]
    place.server.fault(path, "close", when=lambda n, r: True, plain=True)
    layer = place.layer()
    tile = _tile_of(make_grid((X0 + 10, Y0 + 10, X0 + 590, Y0 + 590), 1.0, ZONE))
    with pytest.raises(tnm.SurveyNotRead, match="survey W_DOWN: its record could not be made"):
        layer.index.answers(cache_dir, *tile)
    asked = len(place.server.requests(path))
    assert asked >= 1 and os.path.exists(ops.record_path(cache_dir, "W_DOWN")[:-5] + ".failed.json")
    with pytest.raises(tnm.SurveyNotRead, match="its measurement failed at"):
        layer.index.answers(cache_dir, *tile)
    assert len(place.server.requests(path)) == asked  # not measured again within the day
    # a CRS PROJ cannot transform (rasterio's CRSError, a ValueError) in every window: "not read", written
    place.wesm.append(wesm_row("W_CRS"))
    ok = place.add_file("W_CRS", "c0", ZONE, X0, Y0 + 600, 1.0, 600)

    def no_transform(*args, **kwargs):
        raise rio.errors.CRSError("simulated: no transformation between these CRSs")
    monkeypatch.setattr(ops.rio.warp, "transform", no_transform)
    record = ops.survey_record(cache_dir, wesm_row("W_CRS"), [ok], ops.reference_url(tnm.OprIndex.reference))
    assert not record["read"] and "its CRS cannot be used" in record["reason"]
    assert os.path.exists(ops.record_path(cache_dir, "W_CRS"))


def test_year_and_date_from_the_record(place, tmp_path):
    """The code review's F6 and F7: a WESM row without collect_end leaves the item its own year (its folders'),
    never 0; two surveys of one year in a block: a corrected collect_end of one changes the block's key."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_ND", project="ND_2017", end=""), wesm_row("W_S1", project="S_2019", end="2019/03/01"),
                  wesm_row("W_S2", project="T_2019", end="2019/09/01")]
    place.add_file("W_ND", "nd0", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020, project="ND_2017")
    place.add_file("W_S1", "s1", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020, project="S_2019")
    place.add_file("W_S2", "s2", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020, project="T_2019")
    layer = place.layer()
    grid = make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE)
    layer._use(cache_dir)
    items = {i["name"]: i for i in layer.index.answers(cache_dir, *_tile_of(grid))}
    assert items["nd0"]["year"] == 2017 and items["s1"]["year"] == items["s2"]["year"] == 2019
    block = next(b for b in layer.tiles(grid) if (b.i, b.j) == (500, 4400))
    assert [n for n, _, _ in block.files] == ["s2", "s1", "nd0"]
    place.wesm[1] = wesm_row("W_S1", project="S_2019", end="2019/12/01")  # WESM corrects S1's date: S1 first now
    os.remove(ops.wesm_path(cache_dir))
    cache.forget(cache_dir, [ops.wesm_path(cache_dir)])
    layer = place.layer()
    layer._use(cache_dir)
    again = next(b for b in layer.tiles(grid) if (b.i, b.j) == (500, 4400))
    assert [n for n, _, _ in again.files] == ["s1", "s2", "nd0"] and again.key != block.key


def test_items_rank_key_and_names(place, tmp_path, capsys):
    """An answer's items: in the NAD83 UTM zone under their box's centre, the box projected and rounded outward,
    IfSAR left out; readable surveys only, with WESM's year and collect_end (the rank: year, collect_end, name) and
    the key's token (factor, method and version); a survey left out named once; a changed factor or a changed
    method's version changes the key of the blocks holding such a file and no other block; the 1 m DEM's keys as
    before."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_NEW", end="2021/03/01"), wesm_row("W_OLD", project="O_2015", end="2015/09/09"),
                  wesm_row("W_FLAT", end="2022/01/01")]
    new = place.add_file("W_NEW", "n0", ZONE, X0 - 2, Y0 + 1002, 0.5, 2004)       # 0.5 m: average
    old = place.add_file("W_OLD", "o0", ZONE, X0 - 100, Y0 + 1100, 1.0, 1200, project="O_2015")  # on whole metres
    place.add_file("W_FLAT", "z0", ZONE, X0, Y0 + 1000, 1.0, 1000)                  # its record made below
    # W_FLAT's record: undecided (its files measured on the flat shore; the record is the survey's, not the file's)
    ops.survey_record(cache_dir, wesm_row("W_FLAT", end="2022/01/01"),
                      [place.add_file("W_FLAT", "z1", ZONE, COAST + 500, Y0 + 600, 1.0, 600)],
                      ops.reference_url(tnm.OprIndex.reference))
    place.products.pop()  # z1 is not in this answer
    place.products.append({"downloadURL": place.server.url(f"/{PROJECT}/P_2019/AK_IFSAR/x.tif"),
                           "publicationDate": "1899-12-30", "boundingBox": place.products[0]["boundingBox"]})
    layer = place.layer()
    grid = make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE)
    layer._use(cache_dir)
    blocks = layer.tiles(grid)
    assert [b.year for b in blocks] == [2021] and len(blocks) == 1
    block = blocks[0]
    assert [n for n, _, _ in block.files] == ["n0", "o0"]
    out = capsys.readouterr().out
    assert out.count("survey W_FLAT left out: its height unit could not be told") == 1
    lat, lon = 39.7, -105.0
    items = layer.index.answers(cache_dir, *_tile_of(grid))
    by = {i["name"]: i for i in items}
    assert by["n0"]["opr"] == "x1:average1:2021-03-01:u1" and by["o0"]["opr"] == "x1:copy1:2015-09-09:u1"
    assert "z0" not in by
    assert by["n0"]["crs"] == ZONE and by["n0"]["published"] == "2021-03-01" and by["n0"]["survey"] == "W_NEW"
    e = by["o0"]["extent"]
    assert all(float(v).is_integer() for v in e) and e[0] <= X0 - 100 and e[3] >= Y0 + 1100
    assert layer.index.rule_of(new) == (1.0, ("average",), "W_NEW", (1.0,))
    assert layer.index.rule_of(old)[1] == ("copy",)
    layer.index.answers(cache_dir, *_tile_of(grid))
    assert "W_FLAT" not in capsys.readouterr().out  # named once per run
    # the key: factor and method version in it, the 1 m DEM's keys unchanged
    files = [dict(by["n0"]), dict(by["o0"])]
    key = block_key(files)
    assert block_key([dict(files[0], opr="x0.3048:average1:2021-03-01"), files[1]]) != key
    assert block_key([files[0], dict(files[1], opr="x1:copy2:2015-09-09")]) != key
    # the code review's F7: a corrected collect_end gives another key
    assert block_key([files[0], dict(files[1], opr="x1:copy1:2015-10-01")]) != key
    import hashlib
    for plain in ([{k: v for k, v in f.items() if k != "opr"} for f in files],
                  [{"name": "USGS_1M_13_x50y441_P", "year": 2020, "published": "2021-01-01"}]):
        # a block without OPR files: the key of before, byte for byte (a sha1 of the sorted names)
        assert block_key(plain) == hashlib.sha1(",".join(sorted(f["name"] for f in plain)).encode()).hexdigest()[:8]


def _tile_of(grid):
    from rasterio.warp import transform_bounds
    west, south, east, north = transform_bounds(grid.crs, "EPSG:4326", *grid.bounds)
    return (np.floor(south / 0.25) * 0.25, np.floor(west / 0.25) * 0.25)


def test_reach_takes_a_file_ending_just_outside(place, tmp_path):
    """A block's files are those whose extent meets its square grown by OPR_REACH_M (5 m): a tile ending 3 m west
    of the block is one of its files, one ending 8 m west is not."""
    from sources.indexes.versions import ComposedBlocks
    versions = ComposedBlocks("x", 1000, 1.0)
    versions.reach = src.readers.windows.OPR_REACH_M
    items = [{"name": "near", "url": "u1", "crs": ZONE, "extent": [X0 - 600, Y0, X0 - 3, Y0 + 1000], "year": 2020},
             {"name": "far", "url": "u2", "crs": ZONE, "extent": [X0 - 600, Y0, X0 - 8, Y0 + 1000], "year": 2020}]
    blocks = versions._blocks(items, {ZONE: (X0, Y0, X0 + 1000, Y0 + 1000)})
    assert [(b.i, [n for n, _, _ in b.files]) for b in blocks] == [(500, ["near"])]
    versions.reach = 0.0
    assert versions._blocks(items, {ZONE: (X0, Y0, X0 + 1000, Y0 + 1000)}) == []


def _composed(layer, cache_dir, grid, ij):
    """The block (i, j) of a layer's tiles over grid composed in memory (compose_opr, the reader's own rule), its
    request's transform, and the block."""
    layer._use(cache_dir)
    block = next(b for b in layer.tiles(grid) if (b.i, b.j) == ij)
    request = layer.index.request(block)
    values, tags = src.readers.windows.compose_opr(request.files, request.crs, request.transform, request.shape,
                                                   layer.description, layer.index.rule_of)
    return values, tags, request, block


def _file_pixels(place, rel_name, transform, shape):
    """A local copy's pixels under a block whose pixels coincide with the file's (copy: bit for bit)."""
    path = next(str(p) for p in (place.tmp / "files").rglob(rel_name + ".tif"))
    with rio.open(path) as f:
        col, row = ~f.transform @ (transform.c, transform.f)
        return f.read(1, window=rio.windows.Window(round(col), round(row), shape[1], shape[0])).astype(np.float32)


def test_each_file_by_its_own_header(place, tmp_path, capsys):
    """The code review's F3 (the user's D4 and N4: each file by its own pixel): a survey of 1 m tiles on the lattice
    whose headers carry the CRS once plain and once compound is copied bit for bit, none left out (the CRSs compared
    by _same_crs, not as text); a survey with one sampled tile half a metre off copies the others and reads that one
    by cubic; a survey of 0.5 m and 0.762 m tiles reads both (average and cubic). The key's token holds the sorted
    methods of the sampled headers; nothing is named "left out"."""
    cache_dir = str(tmp_path / "cache")
    compound = rio.crs.CRS.from_user_input("EPSG:26913+5703").to_wkt()
    place.wesm = [wesm_row("W_PC"), wesm_row("W_HALF", project="H_2019"), wesm_row("W_MIX", project="M_2019")]
    place.add_file("W_PC", "pc0", ZONE, X0, Y0 + 1000, 1.0, 1000)
    place.add_file("W_PC", "pc1", compound, X0 + 1000, Y0 + 1000, 1.0, 1000)
    grid = make_grid((X0 + 20, Y0 + 20, X0 + 1980, Y0 + 980), 1.0, ZONE)
    layer = place.layer()
    for ij, name in (((500, 4400), "pc0"), ((501, 4400), "pc1")):
        values, tags, request, block = _composed(layer, cache_dir, grid, ij)
        assert tags["sources"] == name
        assert np.array_equal(values, _file_pixels(place, name, request.transform, request.shape))
    assert layer.index.rule_of(place.products[0]["downloadURL"])[1] == ("copy",)
    # one sampled tile half a metre off the lattice: the others copied, that one cubic
    cache2 = str(tmp_path / "cache2")
    place.products.clear()
    place.add_file("W_HALF", "h0", ZONE, X0, Y0 + 1000, 1.0, 1000, project="H_2019")
    place.add_file("W_HALF", "h1", ZONE, X0 + 1010.5, Y0 + 1000, 1.0, 1000, project="H_2019")  # beyond the reach
    layer = place.layer()
    values, tags, request, _ = _composed(layer, cache2, grid, (500, 4400))
    assert tags["sources"] == "h0"
    assert np.array_equal(values, _file_pixels(place, "h0", request.transform, request.shape))
    assert layer.index.rule_of(place.products[1]["downloadURL"])[1] == ("copy", "cubic")
    values, tags, request, _ = _composed(layer, cache2, grid, (501, 4400))
    assert tags["sources"] == "h1" and np.isfinite(values[:, 15:]).all()
    xs, ys = request.transform @ np.meshgrid(np.arange(1000) + 0.5, np.arange(1000) + 0.5)
    assert np.abs(values[:, 15:-5] - terrain(xs, ys)[:, 15:-5]).max() < 0.05  # cubic of a smooth ground
    # 0.5 m and 0.762 m tiles of one survey: both read
    cache3 = str(tmp_path / "cache3")
    place.products.clear()
    place.add_file("W_MIX", "m0", ZONE, X0, Y0 + 1000, 0.5, 2000, project="M_2019")
    place.add_file("W_MIX", "m1", ZONE, X0 + 999.7, Y0 + 1000.3, 0.762, 1313, project="M_2019")
    layer = place.layer()
    for ij, name in (((500, 4400), "m0"), ((501, 4400), "m1")):
        values, tags, request, block = _composed(layer, cache3, grid, ij)
        assert name in tags["sources"] and np.isfinite(values[:, 5:-5]).all()
    assert layer.index.rule_of(place.products[0]["downloadURL"])[1] == ("average", "cubic")
    assert "left out" not in capsys.readouterr().out


def test_files_not_read_end_to_end(place, tmp_path, capsys):
    """Every reason a file of a readable survey is left out, end to end (a download through the layer): its own
    pixel above 1.001 m, a geographic CRS, rotation terms in its geotransform, a horizontal unit (feet) none of the
    sampled files has (the scope review's S2: the survey's one factor was measured on files in metres). Each such file
    is unsampled (nine files, five sampled by name), alone in its block: no block from it, one named line in the run.
    The sampled files are read (copied)."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_NR")]
    to_deg = Transformer.from_crs(ZONE, "EPSG:4269", always_xy=True)
    for k in range(9):
        left, top = X0 + k * 1000 + 6, Y0 + 994
        name = f"b{k}"
        if k == 1:
            place.add_file("W_NR", name, ZONE, left, top, 1.2, 820)
        elif k == 3:
            lon, lat = to_deg.transform(left, top)
            place.add_file("W_NR", name, "EPSG:4269", lon, lat, 1e-5, 800)
        elif k == 5:
            path = place.file_path("W_NR", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_tif(path, ZONE, rio.Affine(0.987, 0.359, left, 0.359, -0.987, top),
                      np.full((600, 600), 900, np.float32))
            place.add_path("W_NR", name)
        elif k == 7:
            sx, sy = sp(left, top)
            place.add_file("W_NR", name, "EPSG:2232", sx, sy, 2.5, 1250, unit=1200 / 3937)
        else:
            place.add_file("W_NR", name, ZONE, left, top, 1.0, 988)
    layer = place.layer()
    grid = make_grid((X0 + 10, Y0 + 10, X0 + 8990, Y0 + 990), 1.0, ZONE)
    layer.download(grid, cache_dir, None, "test")
    names = sorted(os.path.basename(f).split("_")[1] for f in layer.files(grid, cache_dir))
    assert names == ["500", "502", "504", "506", "508"]  # the sampled files' blocks only
    record = ops.read_record(ops.record_path(cache_dir, "W_NR"))
    assert record["files"] == [f"b{k}.tif" for k in (0, 2, 4, 6, 8)] and ops.units_of(record) == (1.0,)
    out = capsys.readouterr().out
    for line in ("b1 left out: its pixel is 1.200 m (coarser than 1.001 m)", "b3 left out: it has no projected CRS",
                 "b5 left out: its geotransform is rotated",
                 "survey W_NR: file b7 left out: it is in another unit than the files its height unit was measured"):
        assert out.count(line) == 1, line


def test_answers_renewed_after_28_days(place, tmp_path):
    """The scope review's S5: `cache update usa` asks a cached OPR answer again after 28 days (the user's "every
    month"), as the 1 m DEM's, not after the sheet index's 180."""
    import update
    cache_dir = str(tmp_path / "cache")
    assert src.catalogue.usa.USGS_OPR.update_ttl_days == src.catalogue.usa.USGS_1M.update_ttl_days == 28
    for prefix in ("opr", "dem1m"):
        path = os.path.join(cache_dir, "usa", "sheet-index", prefix, "N44.75_W124.25.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"sheets": []}, f)
        cache.record(cache_dir, path, url="x")
    due = lambda: sorted(c.path for c in update.checks(cache_dir, "usa")  # noqa: E731
                         if c.path.endswith("N44.75_W124.25.json"))
    for prefix in ("opr", "dem1m"):
        _age(cache_dir, os.path.join(cache_dir, "usa", "sheet-index", prefix, "N44.75_W124.25.json"), 20)
    assert due() == []
    for prefix in ("opr", "dem1m"):
        _age(cache_dir, os.path.join(cache_dir, "usa", "sheet-index", prefix, "N44.75_W124.25.json"), 29)
    assert due() == ["usa/sheet-index/dem1m/N44.75_W124.25.json", "usa/sheet-index/opr/N44.75_W124.25.json"]


def test_block_files_do_not_depend_on_the_box(tmp_path):
    """The code review's F1: an OPR block's files, key and year are the same whatever box chose it. A survey over the
    whole block and a newer survey's tile in its east quarter: a search's grid holding the block, a grid ending inside
    the block (before the tile) and the block's inner half give the same block, and `cache update`'s update_tile
    finds nothing to read again. Without reach (the 1 m DEM, IfSAR) the blocks are those of before."""
    from sources.indexes.versions import ComposedBlocks
    import osm
    versions = ComposedBlocks("usa/3dep-opr", 1000, 1.0)
    versions.reach = src.readers.windows.OPR_REACH_M
    items = [{"name": "A", "url": "http://h/P/WA/A.tif", "crs": ZONE, "extent": [X0 - 2000, Y0 - 2000, X0 + 3000,
              Y0 + 3000], "year": 2018, "published": "2018-01-01", "opr": "x1:cubic1"},
             {"name": "B", "url": "http://h/P/WB/B.tif", "crs": ZONE, "extent": [X0 + 800, Y0 + 100, X0 + 1257,
              Y0 + 557], "year": 2021, "published": "2021-01-01", "opr": "x0.3048006096:cubic1"}]

    def block(bounds):
        return next(b for b in versions._blocks(items, {ZONE: bounds}) if (b.i, b.j) == (500, 4400))
    whole = block((X0 - 500, Y0 - 500, X0 + 1500, Y0 + 1500))
    inside = block((X0 - 500, Y0 - 500, X0 + 780, Y0 + 1500))
    inner = block((X0 + 250, Y0 + 250, X0 + 750, Y0 + 750))
    assert [n for n, _, _ in whole.files] == ["B", "A"] and whole.year == 2021
    assert (inside.key, inside.year, inside.files) == (inner.key, inner.year, inner.files) == \
        (whole.key, whole.year, whole.files)

    class FakeIndex:
        def store(self, cache_dir, lat, lon, answer):
            pass

        def fresh_answer(self, cache_dir, lat, lon):
            return {"sheets": items}

        def read_items(self, cache_dir, sheets):
            return sheets

        def answers(self, cache_dir, lat, lon, update=None):
            return items
    cache_dir = str(tmp_path / "cache")
    path = versions.path(cache_dir, whole)
    os.makedirs(os.path.dirname(path))
    open(path, "wb").close()
    west, south, east, north = rio.warp.transform_bounds(ZONE, "EPSG:4326", X0, Y0, X0 + 1000, Y0 + 1000)
    lat = (south + north) / 2 // osm.TILE_DEG * osm.TILE_DEG
    lon = (west + east) / 2 // osm.TILE_DEG * osm.TILE_DEG
    assert versions.update_tile(FakeIndex(), cache_dir, lat, lon) == ([], [])  # nothing to read again
    # without reach: the files inside the bounds, as before (the grid ending at 780 m does not hold B)
    versions.reach = 0.0
    plain = next(b for b in versions._blocks(items, {ZONE: (X0 - 500, Y0 - 500, X0 + 780, Y0 + 1500)})
                 if (b.i, b.j) == (500, 4400))
    assert [n for n, _, _ in plain.files] == ["A"]


# The one rule of a block's files (the second code review's N2 and N5): an index answering per 0.25° tile

T = 0.25


def _tnm_item(name, w, s, e, n, year):
    """An OPR item as OprBlocks caches it (the zone under its box's centre, the box projected and rounded out) with
    the fields opr_items adds, and its TNM box."""
    item = tnm.OprBlocks._item(None, {"downloadURL": f"http://h/P/{name}/{name}.tif", "publicationDate": "",
                                      "boundingBox": {"minX": w, "minY": s, "maxX": e, "maxY": n}})
    item.update(year=year, published=f"{year}-06-01", opr=f"x1:cubic2:{year}-06-01:u1")
    return item, (w, s, e, n)


class TileIndex:
    """An index answering per 0.25° tile the items whose TNM box meets the tile (TNM's bbox query), read as cached."""

    def __init__(self, products):
        self.products = list(products)

    def answers(self, cache_dir, lat, lon, update=None):
        return [dict(it) for it, (w, s, e, n) in self.products if w <= lon + T and e >= lon and s <= lat + T
                and n >= lat]

    def fresh_answer(self, cache_dir, lat, lon):
        return {"sheets": self.answers(cache_dir, lat, lon)}

    def read_items(self, cache_dir, items):
        return items

    def store(self, cache_dir, lat, lon, answer):
        pass


def _opr_versions():
    from sources.indexes.versions import ComposedBlocks
    versions = ComposedBlocks("usa/3dep-opr", 1000, 1.0)
    versions.reach = src.readers.windows.OPR_REACH_M
    return versions


def _block_wgs84(crs, i, j):
    return rio.warp.transform_bounds(crs, "EPSG:4326", i * 1000, j * 1000, (i + 1) * 1000, (j + 1) * 1000)


def _again(versions, index, block, cache_dir, tile=None):
    """What update_tile over tile (else the tile of the block's centre) reads again, the block cached."""
    import math
    path = versions.path(cache_dir, block)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    if tile is None:
        w, s, e, n = _block_wgs84(block.crs, block.i, block.j)
        tile = (math.floor((s + n) / 2 / T) * T, math.floor((w + e) / 2 / T) * T)
    try:
        return versions.update_tile(index, cache_dir, *tile)[0]
    finally:
        os.remove(path)


def _block_across(line, lat0):
    """A block of zone 13 whose west edge lies 0.0108-0.0125° west of an index tile line (its centre in the west
    tile, its east part in the east one), within one row of tiles."""
    import math
    for step in range(400):
        (x,), (y,) = rio.warp.transform("EPSG:4326", ZONE, [line], [lat0 + step * 0.001])
        i, j = math.floor(x / 1000), math.floor(y / 1000)
        w, s, e, n = _block_wgs84(ZONE, i, j)
        if line - 0.0125 < w < line - 0.0108 and e > line + 0.0006 and math.floor(s / T) == math.floor(n / T):
            return i, j, (w, s, e, n)
    raise AssertionError("no such block")


def test_one_rule_for_a_blocks_files(tmp_path):
    """The second code review's N2: an OPR block's files are those listed in its own index tiles (the tiles its
    square grown by the reach meets) whose extent meets the grown square, the same in a search (query) and in
    `cache update` (update_tile), for every kind of grid. B: a block across a tile line (-103°), a newer file listed
    only in the east tile, a circle grid whose own tiles are the west one: the block holds it and update_tile reads
    nothing again. C: a polygon whose east edge lies 0.0105° west of the line inside the block (index_tiles' margin
    of 0.01° misses the east tile): the same block. D: a newer file whose TNM box lies wholly east of the line but
    whose extent (the box projected into the zone, rounded out) reaches a block wholly west of it: left out in both
    (its box, and so its file, stays outside the block's square). E: a block of zone 14 at the corner of a grid of
    zone 13 (the zone line -102° is a tile line), a newer file listed only east of the line: the block holds it, as
    update_tile finds it."""
    import math
    from area import project
    from shapely.geometry import box as sbox
    from sources.indexes.cached import index_tiles
    versions = _opr_versions()
    cache_dir = str(tmp_path / "cache")
    line = -103.0
    i, j, (w, s, e, n) = _block_across(line, 45.1)
    a = _tnm_item("A", line - 0.1, s - 0.03, line - 0.002, n + 0.03, 2015)        # the older survey, west tile only
    a2 = _tnm_item("A2", line + 0.0001, s - 0.03, line + 0.1, n + 0.03, 2015)     # its east part, east tile only
    b = _tnm_item("B", line + 0.0002, s + 0.001, line + 0.0062, s + 0.005, 2021)  # newer, east tile only, in the block
    index = TileIndex([a, a2, b])

    def block_of(grid, ij, crs=ZONE):
        return next(blk for blk in versions.query(index, grid, cache_dir, None) if (blk.crs, blk.i, blk.j) == (crs, *ij))
    grid = make_grid((i * 1000 - 4000, j * 1000 - 2000, i * 1000 + 300, (j + 1) * 1000 + 2000), 1.0, ZONE)
    assert all(lon < line for _, lon in index_tiles(grid))
    q = block_of(grid, (i, j))
    assert [f for f, _, _ in q.files] == ["B", "A2", "A"] and q.year == 2021
    assert _again(versions, index, q, cache_dir) == []
    shape = project(sbox(w - 0.03, s - 0.01, line - 0.0105, n + 0.01), "EPSG:4326", ZONE)
    pw, ps, pe, pn = shape.bounds
    assert i * 1000 < pe < (i + 1) * 1000
    polygon = make_grid((pw - 300, ps - 300, pe + 300, pn + 300), 1.0, ZONE)
    polygon.area_shape = shape
    assert all(lon < line for _, lon in index_tiles(polygon))
    q2 = block_of(polygon, (i, j))
    assert (q2.key, q2.year, q2.files) == (q.key, q.year, q.files) and _again(versions, index, q2, cache_dir) == []

    # D: the easternmost block whose grown square stays west of the line, and a file east of it reaching it
    found = None
    for jj in range(j - 20, j + 20):
        west = [c for c in range(i - 3, i + 3) if rio.warp.transform_bounds(
            ZONE, "EPSG:4326", c * 1000 - 5, jj * 1000 - 5, (c + 1) * 1000 + 5, (jj + 1) * 1000 + 5)[2] < line]
        if not west:
            continue
        ii = max(west)
        bs = _block_wgs84(ZONE, ii, jj)[1]
        for k in range(200):
            lat_s = bs - 0.02 + k * 0.0002
            d = _tnm_item("D", line + 1e-6, lat_s, line + 0.006, lat_s + 0.0045, 2022)
            x0, y0, x1, y1 = d[0]["extent"]
            if x0 - 5 < (ii + 1) * 1000 and x1 + 5 > ii * 1000 and y0 - 5 < (jj + 1) * 1000 and y1 + 5 > jj * 1000:
                found = (ii, jj, d)
                break
        if found:
            break
    ii, jj, d = found
    index = TileIndex([_tnm_item("AD", line - 0.2, 44.8, line - 0.0001, 45.4, 2015), d])
    grid = make_grid((ii * 1000 - 3000, jj * 1000 - 3000, (ii + 1) * 1000 - 200, (jj + 1) * 1000 + 3000), 1.0, ZONE)
    q = block_of(grid, (ii, jj))
    assert [f for f, _, _ in q.files] == ["AD"] and _again(versions, index, q, cache_dir) == []

    # E: a block of zone 14 at a grid's corner
    zline, lat = -102.0, 45.1
    (x13,), (y13,) = rio.warp.transform("EPSG:4326", ZONE, [zline], [lat])
    # the line's westernmost x over the grid's height (a meridian bends toward the central one northwards)
    xs, _ = rio.warp.transform("EPSG:4326", ZONE, [zline] * 3, [lat - 0.1, lat, lat + 0.1])
    grid = make_grid((x13 - 6000, y13 - 10000, min(xs) - 300, y13 + 10000), 1.0, ZONE)
    assert all(lon < zline for _, lon in index_tiles(grid))
    z = _tnm_item("Z", zline - 0.06, lat - 0.15, zline + 0.08, lat + 0.15, 2015)  # zone 14, listed on both sides
    assert z[0]["crs"] == "EPSG:26914"
    left, bottom, right, top = rio.warp.transform_bounds(ZONE, "EPSG:26914", *grid.bounds)
    corner = next((c, r) for c in range(math.floor(left / 1000), math.ceil(right / 1000))
                  for r in range(math.floor(bottom / 1000), math.ceil(top / 1000))
                  if _block_wgs84("EPSG:26914", c, r)[2] > zline + 0.003
                  and c * 1000 < right and r * 1000 < top and (r + 1) * 1000 > bottom)
    cw, cs, ce, cn = _block_wgs84("EPSG:26914", *corner)
    f = _tnm_item("F", zline + 0.0005, (cs + cn) / 2, zline + 0.002, (cs + cn) / 2 + 0.001, 2022)
    index = TileIndex([z, f])
    q = block_of(grid, corner, "EPSG:26914")
    assert [n_ for n_, _, _ in q.files] == ["F", "Z"] and _again(versions, index, q, cache_dir) == []


def test_has_data_near_by_the_same_rule(tmp_path):
    """has_data_near of the OPR layer (a file within 2 km of a point) asks every index tile the point's box grown by
    2 km meets, the rule of a block's files: a file listed only in the east tile of a line, 400 m east of a point
    just west of it, is found; one 3.9 km away is not. Without reach (the 1 m DEM, IfSAR) only the point's own tile,
    as before."""
    versions = _opr_versions()
    cache_dir = str(tmp_path / "cache")
    line, lat = -103.0, 45.1
    index = TileIndex([_tnm_item("E", line + 0.0002, lat - 0.01, line + 0.01, lat + 0.01, 2021)])
    assert versions.has_data_near(index, lat, line - 0.005, cache_dir) is True
    assert versions.has_data_near(index, lat, line - 0.05, cache_dir) is False
    versions.reach = 0.0
    assert versions.has_data_near(index, lat, line - 0.005, cache_dir) is False


def test_update_tile_checks_every_block_its_tile_feeds(tmp_path):
    """`cache update` of one index tile checks every cached OPR block whose files may come from it, over the whole
    block: a block whose one file lies in its east quarter, a newer file added there (the second code review's N5:
    the inner half saw neither); a block centred in the west tile of a tile line whose newer file is listed only in
    the east tile, found by the east tile's update (before, only blocks centred in the tile were checked)."""
    versions = _opr_versions()
    cache_dir = str(tmp_path / "cache")
    # N5, on zone 13's central meridian (X0: one tile column)
    edge0 = {"name": "edge0", "url": "http://h/P/E0/edge0.tif", "crs": ZONE, "extent": [X0 + 800, Y0 + 100,
             X0 + 1300, Y0 + 900], "year": 2015, "published": "2015-01-01", "opr": "x1:cubic2:2015-01-01:u1"}
    edge1 = dict(edge0, name="edge1", url="http://h/P/E1/edge1.tif", extent=[X0 + 850, Y0 + 200, X0 + 1200, Y0 + 800],
                 year=2021, published="2021-01-01", opr="x1:cubic2:2021-01-01:u1")
    old = TileIndex([(edge0, (-105.0, 39.0, -104.9, 39.9))])
    cached = next(b for b in versions.query(old, make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE),
                                            cache_dir, None) if (b.i, b.j) == (500, 4400))
    assert [f for f, _, _ in cached.files] == ["edge0"]
    new = TileIndex([(edge0, (-105.0, 39.0, -104.9, 39.9)), (edge1, (-105.0, 39.0, -104.9, 39.9))])
    again = _again(versions, new, cached, cache_dir)
    assert [(b.i, b.j, [f for f, _, _ in b.files]) for b in again] == [(500, 4400, ["edge1", "edge0"])]
    # a new file listed only in the east tile of a block centred in the west one
    line = -103.0
    i, j, (w, s, e, n) = _block_across(line, 45.1)
    a = _tnm_item("A", line - 0.1, s - 0.03, line - 0.002, n + 0.03, 2015)
    b = _tnm_item("B", line + 0.0002, s + 0.001, line + 0.0062, s + 0.005, 2021)
    grid = make_grid((i * 1000 - 4000, j * 1000 - 2000, i * 1000 + 300, (j + 1) * 1000 + 2000), 1.0, ZONE)
    cached = next(blk for blk in versions.query(TileIndex([a]), grid, cache_dir, None) if (blk.i, blk.j) == (i, j))
    assert (w + e) / 2 < line and [f for f, _, _ in cached.files] == ["A"]
    east = (s // T * T, line)
    again = _again(versions, TileIndex([a, b]), cached, cache_dir, tile=east)
    assert [(blk.i, blk.j, [f for f, _, _ in blk.files]) for blk in again] == [(i, j, ["B", "A"])]


def _hand_record(cache_dir, row, headers, factor=1.0):
    """A readable survey's record written as survey_record keeps it (current for row)."""
    record = {"workunit": row["workunit"], "year": 2019, "collect_end": "2019-06-30", "wesm": ops.fingerprint(row),
              "rule": ops.RULE, "read": True, "unit": "metre", "factor": factor, "pixel_m": 0.762, "crs": None,
              "on_metres": False, "headers": headers}
    ops._write_json(ops.record_path(cache_dir, row["workunit"]), record)


class _Table:
    """WESM as opr_items asks it: every file's survey is row."""

    def __init__(self, row):
        self.row = row

    def survey_of(self, url):
        return self.row


def test_methods_once_per_survey_and_zone(tmp_path, monkeypatch):
    """The second code review's N3: methods_for once per survey, zone and record in a process, not per item (an
    answer of 2,000 items of one survey: one call; read again: none; items of another zone: one more; the survey's
    record made again with other headers: one more). The sampled units are in the key's token."""
    cache_dir = str(tmp_path / "cache")
    row = wesm_row("W_BIG")
    sp_wkt = rio.crs.CRS.from_epsg(2232).to_wkt()
    _hand_record(cache_dir, row, [{"file": "t0.tif", "pixel_m": 0.762, "crs": sp_wkt, "on_metres": False,
                                   "unit": 1200 / 3937}])
    index = tnm.OprBlocks("Test OPR", "OPR", "opr", "usa/3dep-opr", 1.0, 1000, 2e6, api="http://127.0.0.1:9/").index
    items = [{"name": f"t{k}", "url": f"http://h/{PROJECT}/P_2019/W_BIG/TIFF/t{k}.tif", "crs": ZONE,
              "extent": [X0, Y0, X0 + 500, Y0 + 500], "year": 0, "published": ""} for k in range(2000)]
    calls = []
    real = ops.methods_for
    monkeypatch.setattr(ops, "methods_for", lambda record, crs: calls.append(crs) or real(record, crs))
    monkeypatch.setattr(tnm, "_METHODS", {})
    out = tnm.opr_items(index, cache_dir, items, _Table(row))
    assert len(out) == 2000 and calls == [ZONE]
    assert {i["opr"] for i in out} == {"x1:cubic2:2019-06-30:u0.3048"}  # the feet's class (fix round 4)
    tnm.opr_items(index, cache_dir, items, _Table(row))
    assert calls == [ZONE]
    tnm.opr_items(index, cache_dir, [dict(items[0], crs="EPSG:26912")], _Table(row))
    assert calls == [ZONE, "EPSG:26912"]
    _hand_record(cache_dir, row, [{"file": "m0.tif", "pixel_m": 0.5, "crs": rio.crs.CRS.from_epsg(26913).to_wkt(),
                                   "on_metres": False, "unit": 1.0}])
    again = tnm.opr_items(index, cache_dir, items[:1], _Table(row))
    assert calls == [ZONE, "EPSG:26912", ZONE] and again[0]["opr"] == "x1:average1:2019-06-30:u1"


def test_a_survey_in_two_units_is_not_read(place, tmp_path):
    """A survey whose sampled files are in metres and in feet (a mosaic in metres beside State Plane tiles in US
    survey feet) is not read: one height factor cannot serve both; nothing of it is measured. The foot and the US
    survey foot count as one unit (relative UNIT_REL_TOL, 1e-5, as the reader's guard compares them: fix round 3)."""
    cache_dir = str(tmp_path / "cache")
    metres = place.add_file("W_TWO", "m0", ZONE, X0, Y0 + 600, 0.5, 1200)
    left, top = sp(X0 + 600, Y0 + 600)
    feet = place.add_file("W_TWO", "f0", "EPSG:2232", left, top, 2.5, 800, unit=1200 / 3937)
    record = ops.survey_record(cache_dir, wesm_row("W_TWO"), [metres, feet], ops.reference_url(tnm.OprIndex.reference))
    assert not record["read"] and not ops.readable(record) and record["windows"] == []
    assert record["reason"] == "its files are in metres and in US survey feet, one height factor cannot serve both"
    assert ops._distinct_units([ops.FOOT, ops.US_FOOT, 1.0]) == [1.0, ops.US_FOOT]


def test_the_foot_and_the_us_survey_foot_are_one_unit(place, tmp_path):
    """Fix round 3 (the third code review's finding 2): units compare at a relative 1e-5. A survey of State Plane
    files in US survey feet (Colorado Central) and in feet (Montana) is read, as before fix round 2 (its height
    factor measured, every file placed by its own CRS); the guard's units are one; metres and feet stay two."""
    cache_dir = str(tmp_path / "cache")
    left, top = sp(X0, Y0 + 600)
    ftus = place.add_file("W_FT", "a0", "EPSG:2232", left, top, 2.5, 800, unit=1200 / 3937)
    mx, my = Transformer.from_crs(ZONE, "EPSG:2256", always_xy=True).transform(X0 + 600, Y0 + 600)
    ft = place.add_file("W_FT", "b0", "EPSG:2256", mx, my, 2.5, 800, unit=0.3048)
    record = ops.survey_record(cache_dir, wesm_row("W_FT"), [ftus, ft], ops.reference_url(tnm.OprIndex.reference))
    assert record["read"] and record["unit"] in ("foot", "US survey foot"), record["reason"]
    assert sorted(h["unit"] for h in record["headers"]) == [0.3048, pytest.approx(1200 / 3937)]
    assert len(ops.units_of(record)) == 1 and ops._distinct_units([0.3048006, ops.US_FOOT]) == [ops.US_FOOT]
    assert ops._distinct_units([1.0, ops.FOOT]) == [1.0, ops.FOOT]


class _NoFiles:
    """make_record's opener when the headers' facts are made up (_file_facts patched)."""

    def __init__(self, cache_dir):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        return None


@pytest.mark.parametrize("case", ["two units", "cut", "rounded us foot"])
def test_verdicts_before_a_failed_request(monkeypatch, case):
    """The third code review's finding 1: a verdict no further header can change comes before the raise for a failed
    request: sampled headers in metres and US survey feet beside a third answering 503 give the "not read" record
    (another header could only add a unit), and so does a sampled file cut at 4 GB. A header storing a rounded
    0.3048006 beside an EPSG US survey foot is one unit (finding 2): with every header read the record is not left
    out for units. The headers' facts made up (the reviewer's check3_record.py)."""
    utm, sp_wkt = rio.crs.CRS.from_epsg(26913).to_wkt(), rio.crs.CRS.from_epsg(2232).to_wkt()
    metres = {"pixel_m": 0.5, "crs": utm, "on_metres": False, "foot": ops.US_FOOT, "unit": 1.0}
    feet = {"pixel_m": 0.762, "crs": sp_wkt, "on_metres": False, "foot": ops.US_FOOT, "unit": 1200 / 3937}
    facts = {"two units": {"a": metres, "b": feet, "c": "fail"},
             "cut": {"a": {"error": "cut", "cut": True}, "b": metres, "c": "fail"},
             "rounded us foot": {"a": feet, "b": dict(feet, unit=0.3048006), "c": feet}}[case]

    def file_facts(_, url):
        f = facts[url.rsplit("/", 1)[-1][0]]
        if f == "fail":
            raise RuntimeError("could not open c.tif: HTTP 503 (simulated)")
        return dict(f)
    monkeypatch.setattr(ops, "_Files", _NoFiles)
    monkeypatch.setattr(ops, "_file_facts", file_facts)
    monkeypatch.setattr(ops, "_windows_of", lambda *args, **kwargs: [])
    row = {"workunit": "W", "p_method": "lidar", "collect_end": "2019/05/01", "sourcedem_link": "x"}
    record = ops.make_record("unused", row, [f"http://h/{n}.tif" for n in "abc"], None)
    assert not record["read"]
    assert record["reason"] == {
        "two units": "its files are in metres and in US survey feet, one height factor cannot serve both",
        "cut": "its file a.tif was cut at 4 GB (a classic TIFF at the format's limit: its last tiles are missing)",
        "rounded us foot": "its height unit could not be told"}[case]


@pytest.mark.parametrize("outcome", ["not lidar", "cut", "no file"])
def test_a_record_left_out_early_is_kept(place, tmp_path, monkeypatch, outcome):
    """The second code review's N1: a survey left out before its headers are read (not lidar, a file cut at 4 GB,
    no file that could be read: here a geographic CRS) has a record with "headers" too, so the second answer read
    measures nothing."""
    cache_dir = str(tmp_path / "cache")
    if outcome == "not lidar":
        place.wesm = [wesm_row("W_E", method="IfSAR")]
        place.add_file("W_E", "e0", ZONE, X0, Y0 + 600, 1.0, 600)
    elif outcome == "cut":
        place.wesm = [wesm_row("W_E")]
        path = place.add_file("W_E", "e0", ZONE, X0, Y0 + 600, 1.0, 600)
        monkeypatch.setattr(ops, "cut_at_4gb", lambda *args, **kwargs: True)
    else:
        place.wesm = [wesm_row("W_E")]
        to_deg = Transformer.from_crs(ZONE, "EPSG:4269", always_xy=True)
        lon, lat = to_deg.transform(X0, Y0 + 600)
        place.add_file("W_E", "e0", "EPSG:4269", lon, lat, 1e-5, 600)
    made = []
    real = ops.make_record
    monkeypatch.setattr(ops, "make_record", lambda *args, **kwargs: made.append(1) or real(*args, **kwargs))
    layer = place.layer()
    tile = _tile_of(make_grid((X0 + 10, Y0 + 10, X0 + 590, Y0 + 590), 1.0, ZONE))
    assert layer.index.answers(cache_dir, *tile) == []
    asked = len(place.server.requests())
    record = ops.read_record(ops.record_path(cache_dir, "W_E"))
    assert made == [1] and record["headers"] == [] and not record["read"]
    assert {"not lidar": "not lidar", "cut": "cut at 4 GB", "no file": "no file could be read"}[outcome] in \
        record["reason"]
    assert layer.index.answers(cache_dir, *tile) == []
    assert made == [1] and len(place.server.requests()) == asked


def test_a_failed_survey_changes_no_block(place, tmp_path, monkeypatch):
    """The second code review's N4: while a survey has no record because its measurement failed (the day of its
    <work unit>.failed.json), the answer naming it counts as failed: `cache update` of its tile fails, the cached
    blocks and their names stay (not rewritten with the older survey's heights, not pruned) and the answer's check
    time is not written, so the next day, the host back, the tile is checked as usual and the block read again.
    `cache update`'s checks are built on the test's layer (update._sheet_layers), so its index is the test server's,
    never the real TNM API (the session's full run of round 2: a 504 there failed this test)."""
    import glob
    from datetime import datetime, timedelta, timezone
    import update
    monkeypatch.setattr(update, "_sheet_layers", lambda: [layer])
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_NEW", end="2019/06/30"), wesm_row("W_OLD", project="O_2015", end="2015/09/09")]
    url = place.add_file("W_NEW", "n0", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020)
    place.add_file("W_OLD", "o0", ZONE, X0 - 20, Y0 + 1020, 1.0, 1040, project="O_2015")
    layer = place.layer()
    grid = make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE)
    layer.download(grid, cache_dir, None, "test")
    folder = os.path.join(cache_dir, "usa", "3dep-opr", "epsg26913", "50_440")
    before = sorted(os.listdir(folder))
    assert len(before) == 1 and before[0].startswith("2019_500_4400_")
    # WESM corrects the newer survey's date (its record is made again at the next answer read) while its files' host
    # closes every connection
    place.wesm[0] = wesm_row("W_NEW", end="2019/12/01")
    place.etag = '"v2"'
    os.remove(ops.wesm_path(cache_dir))
    cache.forget(cache_dir, [ops.wesm_path(cache_dir)])
    broken = [True]
    place.server.fault("/" + url.split("/", 3)[3], "close", when=lambda n, r: broken[0], plain=True)
    answer = layer.index.index_path(cache_dir, *_tile_of(grid))
    _age(cache_dir, answer, 29)

    def check():
        return next(c for c in update.checks(cache_dir, "usa") if c.path.startswith("usa/sheet-index/opr/"))
    with pytest.raises(IndexUnavailable, match="survey W_NEW: its record could not be made"):
        check().action()
    assert sorted(os.listdir(folder)) == before
    with pytest.raises(IndexUnavailable, match="its measurement failed at"):
        check().action()  # still due, and failed again without a request (the failure's day)
    assert sorted(os.listdir(folder)) == before
    # the next day, the host back
    failed = ops.record_path(cache_dir, "W_NEW")[:-len(".json")] + ".failed.json"
    with open(failed, encoding="utf-8") as f:
        data = json.load(f)
    data["at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(timespec="seconds")
    with open(failed, "w", encoding="utf-8") as f:
        json.dump(data, f)
    broken[0] = False
    check().action()
    after = sorted(os.listdir(folder))
    assert len(after) == 1 and after[0].startswith("2019_500_4400_") and after != before
    assert not glob.glob(os.path.join(folder, before[0]))


# A survey that cannot be measured (the user's decision of 2026-11-27: "Wait 3 days, then skip it")

def _clock(monkeypatch):
    """oprsurveys' clock, moved by the test: [now]."""
    from datetime import datetime, timezone
    clock = [datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(ops, "_now_utc", lambda: clock[0])
    return clock


def test_a_survey_failing_three_days_is_skipped(place, tmp_path, monkeypatch, capsys):
    """Days 1 and 2: the answer fails (SurveyNotRead), one measurement a day, failed.json counts them. The third
    failed measurement (a day after the second) gives a "not read" record naming the last error and the date from
    which it is measured again (28 days on): the answer is read without the survey, the older survey's block made,
    the survey named once. Within the 28 days nothing of it is asked; after them one measurement: still failing, it
    is skipped another 28 days at once (no raise); the host back after those, the survey returns and its block gets a
    new key."""
    from datetime import timedelta
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_BAD", end="2021/06/30"), wesm_row("W_GOOD", project="O_2015", end="2015/09/09")]
    bad = place.add_file("W_BAD", "b0", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020)
    place.add_file("W_GOOD", "g0", ZONE, X0 - 20, Y0 + 1020, 1.0, 1040, project="O_2015")
    path = "/" + bad.split("/", 3)[3]
    broken = [True]
    place.server.fault(path, "close", when=lambda n, r: broken[0], plain=True)
    clock = _clock(monkeypatch)
    layer = place.layer()
    grid = make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE)
    tile = _tile_of(grid)
    failed = ops.record_path(cache_dir, "W_BAD")[:-len(".json")] + ".failed.json"
    names = lambda: {i["name"] for i in layer.index.answers(cache_dir, *tile)}  # noqa: E731
    for day in (1, 2):
        with pytest.raises(tnm.SurveyNotRead, match="survey W_BAD: its record could not be made"):
            names()
        with open(failed, encoding="utf-8") as f:
            assert json.load(f)["count"] == day
        asked = len(place.server.requests(path))
        with pytest.raises(tnm.SurveyNotRead, match="its measurement failed at"):  # the same day: not measured
            names()
        assert len(place.server.requests(path)) == asked
        clock[0] += timedelta(days=1, minutes=1)
    assert names() == {"g0"} and not os.path.exists(failed)  # day 3: skipped
    record = ops.read_record(ops.record_path(cache_dir, "W_BAD"))
    retry = (clock[0] + timedelta(days=28)).replace(microsecond=0)
    assert not record["read"] and record["retry_after"] == retry.isoformat()
    assert record["reason"].startswith("could not be measured on 3 days, last: ")
    assert record["reason"].endswith(f"; measured again from {retry:%Y-%m-%d}")
    assert capsys.readouterr().out.count("survey W_BAD left out: could not be measured on 3 days") == 1
    layer._use(cache_dir)
    block = next(b for b in layer.tiles(grid) if (b.i, b.j) == (500, 4400))
    assert [n for n, _, _ in block.files] == ["g0"]
    asked = len(place.server.requests(path))
    clock[0] += timedelta(days=27)
    assert names() == {"g0"} and len(place.server.requests(path)) == asked  # within the 28 days: nothing asked
    assert "W_BAD" not in capsys.readouterr().out  # named once per run
    clock[0] += timedelta(days=1, hours=1)
    assert names() == {"g0"} and len(place.server.requests(path)) > asked  # after them: measured once, no raise
    record = ops.read_record(ops.record_path(cache_dir, "W_BAD"))
    assert record["retry_after"] == (clock[0] + timedelta(days=28)).replace(microsecond=0).isoformat()
    assert record["reason"].startswith("could not be measured again after its skip, last: ")
    broken[0] = False
    clock[0] += timedelta(days=28, hours=1)
    layer = place.layer()
    layer._use(cache_dir)
    again = next(b for b in layer.tiles(grid) if (b.i, b.j) == (500, 4400))
    assert [n for n, _, _ in again.files] == ["b0", "g0"] and again.key != block.key
    assert ops.readable(ops.read_record(ops.record_path(cache_dir, "W_BAD")))


def test_a_success_clears_the_failed_count(place, tmp_path, monkeypatch):
    """A success between failures starts the count again: a failure on day 1, the host back on day 2 (the record
    written, failed.json removed); its record made again later (WESM corrects its date) with the host failing:
    count 1, the answer fails as on a first day."""
    from datetime import timedelta
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_ONE", end="2021/06/30")]
    url = place.add_file("W_ONE", "o0", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020)
    broken = [True]
    place.server.fault("/" + url.split("/", 3)[3], "close", when=lambda n, r: broken[0], plain=True)
    clock = _clock(monkeypatch)
    layer = place.layer()
    tile = _tile_of(make_grid((X0 + 100, Y0 + 100, X0 + 900, Y0 + 900), 1.0, ZONE))
    failed = ops.record_path(cache_dir, "W_ONE")[:-len(".json")] + ".failed.json"
    with pytest.raises(tnm.SurveyNotRead):
        layer.index.answers(cache_dir, *tile)
    broken[0] = False
    clock[0] += timedelta(days=1, minutes=1)
    assert [i["name"] for i in layer.index.answers(cache_dir, *tile)] == ["o0"] and not os.path.exists(failed)
    place.wesm[0] = wesm_row("W_ONE", end="2021/09/30")
    place.etag = '"v2"'
    os.remove(ops.wesm_path(cache_dir))
    cache.forget(cache_dir, [ops.wesm_path(cache_dir)])
    broken[0] = True
    with pytest.raises(tnm.SurveyNotRead):
        layer.index.answers(cache_dir, *tile)
    with open(failed, encoding="utf-8") as f:
        assert json.load(f)["count"] == 1


def test_a_measurement_without_a_connection_is_not_counted(tmp_path, monkeypatch):
    """A measurement whose every failed request found no connection (MeasurementNotReached: this machine's network)
    is remembered for the day but not counted towards the three."""
    from datetime import timedelta
    clock = _clock(monkeypatch)
    row = wesm_row("W_NET")
    calls = []

    def unreachable(*args, **kwargs):
        calls.append(1)
        raise ops.MeasurementNotReached("5 requests failed, no connection (simulated)")
    monkeypatch.setattr(ops, "make_record", unreachable)
    monkeypatch.setattr(ops, "WESM_URL", f"http://127.0.0.1:{_closed_port()}/wesm.csv")  # WESM's host unreachable too
    cache_dir = str(tmp_path / "cache")
    for _ in range(4):
        with pytest.raises(ops.MeasurementNotReached):
            ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
        clock[0] += timedelta(days=1, minutes=1)
    with open(ops.record_path(cache_dir, "W_NET")[:-len(".json")] + ".failed.json", encoding="utf-8") as f:
        assert json.load(f)["count"] == 0
    assert len(calls) == 4 and ops.read_record(ops.record_path(cache_dir, "W_NET")) is None


def _closed_port():
    """A port of the loopback nothing listens on (bound, then closed): a connection there is refused."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("case", ["one file refused", "every file refused, WESM's host up", "a dropped connection",
                                  "a TLS failure", "nothing reachable", "one file refused, WESM's host down"])
def test_which_failures_count(place, tmp_path, monkeypatch, case):
    """The fourth code review's finding 1: a failed measurement is not counted only when nothing of it answered and
    one probe of WESM's host finds no connection either; a survey's own unreachable file, every file unreachable
    while WESM's host answers, a dropped connection and a TLS failure after connecting all count. On the test server
    and a closed port of the loopback; the count after two failed days."""
    from datetime import timedelta
    cache_dir = str(tmp_path / "cache")
    clock = _clock(monkeypatch)
    closed = f"http://127.0.0.1:{_closed_port()}"
    rel = f"{PROJECT}/P_2019/W_C/TIFF"
    flat = place.add_file("W_C", "flat", ZONE, COAST + 500, Y0 + 600, 1.0, 600)  # answers, decides nothing
    hilly = place.add_file("W_C", "hilly", ZONE, X0, Y0 + 600, 1.0, 600)
    urls = {"one file refused": [flat, f"{closed}/{rel}/gone.tif"],
            "every file refused, WESM's host up": [f"{closed}/{rel}/a.tif", f"{closed}/{rel}/b.tif"],
            "a dropped connection": [hilly],
            "a TLS failure": [hilly.replace("http://", "https://")],
            "nothing reachable": [f"{closed}/{rel}/a.tif", f"{closed}/{rel}/b.tif"],
            # one file answered: counted although WESM's host is down too (the `answered` condition decides)
            "one file refused, WESM's host down": [flat, f"{closed}/{rel}/gone.tif"]}[case]
    if case == "a dropped connection":
        place.server.fault("/" + hilly.split("/", 3)[3], "close", when=lambda n, r: True, plain=True)
    if case in ("nothing reachable", "one file refused, WESM's host down"):
        monkeypatch.setattr(ops, "WESM_URL", f"{closed}/wesm.csv")
    reference = ops.reference_url(tnm.OprIndex.reference)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            ops.survey_record(cache_dir, wesm_row("W_C"), urls, reference)
        clock[0] += timedelta(days=1, minutes=1)
    with open(ops.record_path(cache_dir, "W_C")[:-len(".json")] + ".failed.json", encoding="utf-8") as f:
        assert json.load(f)["count"] == (0 if case == "nothing reachable" else 2)


def test_a_retry_without_a_network_keeps_the_skip_a_day(tmp_path, monkeypatch):
    """The fourth code review's finding 2: a retry after the skip that is not counted (nothing reachable, WESM's host
    neither) keeps the "not read" record and tries again a day later, not 28 days; one that counts skips 28 more."""
    from datetime import timedelta
    clock = _clock(monkeypatch)
    cache_dir = str(tmp_path / "cache")
    row = wesm_row("W_R")
    ops._write_json(ops.record_path(cache_dir, "W_R"), ops._skipped_record(row, "HTTP 503", 3))
    monkeypatch.setattr(ops, "WESM_URL", f"http://127.0.0.1:{_closed_port()}/wesm.csv")
    monkeypatch.setattr(ops, "make_record", lambda *a, **k: (_ for _ in ()).throw(
        ops.MeasurementNotReached("2 requests failed, no connection (simulated)")))
    clock[0] += timedelta(days=28, hours=1)
    record = ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
    retry = (clock[0] + timedelta(days=1)).replace(microsecond=0)
    assert record["retry_after"] == retry.isoformat() and record["reason"].endswith(f"from {retry:%Y-%m-%d}")
    assert record["reason"].startswith("could not be measured on 3 days")
    clock[0] += timedelta(days=1, minutes=1)
    monkeypatch.setattr(ops, "make_record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 503")))
    record = ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
    assert record["retry_after"] == (clock[0] + timedelta(days=28)).replace(microsecond=0).isoformat()


def test_failures_months_apart_do_not_add_up(tmp_path, monkeypatch):
    """The fourth code review's point 3: a failure more than RECORD_SKIP_DAYS after the one before starts the count
    again (two failures on 27 November and a third in June: count 1, the answer fails, no skip)."""
    from datetime import timedelta
    clock = _clock(monkeypatch)
    cache_dir = str(tmp_path / "cache")
    row = wesm_row("W_M")
    monkeypatch.setattr(ops, "make_record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 503")))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
        clock[0] += timedelta(days=1, minutes=1)
    clock[0] += timedelta(days=200)
    with pytest.raises(RuntimeError):
        ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
    with open(ops.record_path(cache_dir, "W_M")[:-len(".json")] + ".failed.json", encoding="utf-8") as f:
        assert json.load(f)["count"] == 1
    assert ops.read_record(ops.record_path(cache_dir, "W_M")) is None


def test_a_changed_row_offline_waits_a_day(tmp_path, monkeypatch):
    """Review 4b's finding 1: a skipped survey whose WESM row changed is measured again at once; offline (not
    counted) it keeps the skip a day under the new row's fingerprint, so the next read the same day measures nothing."""
    from datetime import timedelta
    clock = _clock(monkeypatch)
    cache_dir = str(tmp_path / "cache")
    ops._write_json(ops.record_path(cache_dir, "W_W"), ops._skipped_record(wesm_row("W_W"), "HTTP 503", 3))
    monkeypatch.setattr(ops, "WESM_URL", f"http://127.0.0.1:{_closed_port()}/wesm.csv")
    calls = []

    def offline(*args, **kwargs):
        calls.append(1)
        raise ops.MeasurementNotReached("1 requests failed, no connection (simulated)")
    monkeypatch.setattr(ops, "make_record", offline)
    changed = wesm_row("W_W", end="2019/12/01")
    clock[0] += timedelta(days=2)
    record = ops.survey_record(cache_dir, changed, ["http://h/x.tif"], None)
    assert record["wesm"] == ops.fingerprint(changed) and calls == [1]
    assert record["retry_after"] == (clock[0] + timedelta(days=1)).replace(microsecond=0).isoformat()
    ops.survey_record(cache_dir, changed, ["http://h/x.tif"], None)
    assert calls == [1]


def test_an_offline_try_does_not_move_the_gap(tmp_path, monkeypatch):
    """Review 4b's finding 2: the count's gap is measured from the last counted failure: two counted failures, offline
    tries every 20 days (not counted) until day 200, a counted failure on day 201.5: count 1, not a skip."""
    from datetime import timedelta
    clock = _clock(monkeypatch)
    cache_dir = str(tmp_path / "cache")
    row = wesm_row("W_G")
    monkeypatch.setattr(ops, "WESM_URL", f"http://127.0.0.1:{_closed_port()}/wesm.csv")
    start = clock[0]
    offline = [(day, ops.MeasurementNotReached("no connection")) for day in range(20, 201, 20)]
    for day, error in [(0, RuntimeError("HTTP 503")), (1.01, RuntimeError("HTTP 503"))] + offline + \
            [(201.5, RuntimeError("HTTP 503"))]:
        clock[0] = start + timedelta(days=day)
        monkeypatch.setattr(ops, "make_record", lambda *a, e=error, **k: (_ for _ in ()).throw(e))
        with pytest.raises(RuntimeError):
            ops.survey_record(cache_dir, row, ["http://h/x.tif"], None)
    with open(ops.record_path(cache_dir, "W_G")[:-len(".json")] + ".failed.json", encoding="utf-8") as f:
        assert json.load(f)["count"] == 1
    assert ops.read_record(ops.record_path(cache_dir, "W_G")) is None


def test_the_token_writes_the_units_by_class():
    """The fourth code review's finding 3: the units in the key's token by the guard's classes: ft, ftUS, both, a
    truncated header: one text; metres "1" (R110's), the foot "0.3048" (R111's: its 3 ft header gave the scale
    0.9144 exactly, the international foot), the texts the round-3 code wrote for them, so their block names stay."""
    assert ops.unit_class_texts([ops.FOOT]) == ops.unit_class_texts([ops.US_FOOT]) == \
        ops.unit_class_texts([ops.FOOT, ops.US_FOOT]) == ops.unit_class_texts([0.30480061]) == ["0.3048"]
    assert ops.unit_class_texts([1.0]) == ["1"] and ops.unit_class_texts([1.0, ops.FOOT]) == ["0.3048", "1"]
    for unit in (1.0, ops.FOOT):  # round 3's text (f"{u:.10g}") of R110's and R111's units, unchanged
        assert ops.unit_class_texts([unit]) == [f"{unit:.10g}"]


def test_two_processes_on_the_third_day(place, tmp_path, monkeypatch):
    """Two processes reading a survey's record on its third failing day at once: one measures (as many requests as
    one measurement), both get the "not read" record (the second waits for the record's lock and reads it)."""
    import subprocess
    from datetime import timedelta
    cache_dir = str(tmp_path / "cache")
    url = place.add_file("W_TWO_P", "t0", ZONE, X0 - 10, Y0 + 1010, 1.0, 1020)
    path = "/" + url.split("/", 3)[3]
    place.server.fault(path, "close", when=lambda n, r: True, plain=True)
    clock = _clock(monkeypatch)
    row = wesm_row("W_TWO_P")
    reference = ops.reference_url(tnm.OprIndex.reference)
    counts = []
    for _ in range(2):
        before = len(place.server.requests(path))
        with pytest.raises(RuntimeError):
            ops.survey_record(cache_dir, row, [url], reference)
        counts.append(len(place.server.requests(path)) - before)
        clock[0] += timedelta(days=1, minutes=1)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref = place.server.url("/ref/ref.tif")
    code = (f"import sys, json\nsys.path.insert(0, {repo!r})\nfrom datetime import datetime\n"
            "import sources as src\nfrom sources.layers import oprsurveys as ops\n"
            "src.net._sleep = lambda attempt: None\n"
            f"ops._now_utc = lambda: datetime.fromisoformat({clock[0].isoformat()!r})\n"
            f"class Ref:\n    url = staticmethod(lambda name: {ref!r})\n"
            f"r = ops.survey_record({cache_dir!r}, json.loads({json.dumps(row)!r}), [{url!r}], ops.reference_url(Ref()))\n"
            "print('RECORD', r['read'], r['reason'][:31])\n")
    env = {k: v for k, v in os.environ.items() if k not in ("ESRI_API_KEY", "DATAFORDELER_API_KEY")}
    env["PYTHONIOENCODING"] = "utf-8"
    before = len(place.server.requests(path))
    procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env=env) for _ in range(2)]
    outs = [p.communicate(timeout=180) for p in procs]
    for (out, err), p in zip(outs, procs):
        assert p.returncode == 0, err
        assert out.strip().splitlines()[-1] == "RECORD False could not be measured on 3 days", out
    assert counts[0] == counts[1] == len(place.server.requests(path)) - before


def _blocks_before(items, bounds, size):
    """ComposedBlocks._blocks as it was before wave B-1 (main 0d70d67c), without the outline: the 1 m DEM's and
    IfSAR's blocks must stay these, byte for byte."""
    import math
    over = {}
    for item in items:
        if item["crs"] not in bounds:
            continue
        left, bottom, right, top = bounds[item["crs"]]
        e = item["extent"]
        left, bottom, right, top = max(left, e[0]), max(bottom, e[1]), min(right, e[2]), min(top, e[3])
        if left >= right or bottom >= top:
            continue
        for i in range(math.floor(left / size), math.ceil(right / size)):
            for j in range(math.floor(bottom / size), math.ceil(top / size)):
                over.setdefault((item["crs"], i, j), []).append(item)
    out = {}
    for k, files in over.items():
        files = sorted(files, key=lambda f: (f["year"], f.get("published", ""), f["name"]), reverse=True)
        out[k] = (files[0]["year"], block_key(files), tuple((f["name"], f["url"], f["year"]) for f in files))
    return out


@pytest.mark.parametrize("case, layer_of", [("dem1m", "usa"), ("ifsar5m", "alaska_ifsar")])
def test_recorded_blocks_as_before(case, layer_of):
    """The recorded answers of the 1 m DEM and of IfSAR give the same blocks, years and keys as the code of before
    wave B-1, over several boxes of their tile (reach 0: F1's change is for OPR only)."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recorded", "tnm", case)
    items = json.load(open(os.path.join(folder, "expected.json"), encoding="utf-8"))["sheets"]
    layer = src.SOURCES[layer_of].nmt
    versions = layer.index.versions
    assert versions.reach == 0.0
    for crs in sorted({i["crs"] for i in items}):
        es = [i["extent"] for i in items if i["crs"] == crs]
        x0, y0 = min(e[0] for e in es), min(e[1] for e in es)
        x1, y1 = max(e[2] for e in es), max(e[3] for e in es)
        for frac in ((0, 0, 1, 1), (0.1, 0.2, 0.6, 0.7), (0.33, 0.1, 0.4, 0.9)):
            box = (x0 + frac[0] * (x1 - x0), y0 + frac[1] * (y1 - y0), x0 + frac[2] * (x1 - x0),
                   y0 + frac[3] * (y1 - y0))
            now = {(b.crs, b.i, b.j): (b.year, b.key, b.files) for b in versions._blocks(items, {crs: box})}
            assert now == _blocks_before(items, {crs: box}, versions.block_m)


def test_blocks_end_to_end(place, tmp_path, capsys):
    """A search's download of OPR blocks: a survey in feet (State Plane, 2.5 US survey feet: cubic) gives heights in
    metres near the ground's; a survey of 0.5 m UTM averaged; cached as <folder>/epsg26913/<i//10>_<j//10>/
    <year>_<i>_<j>_<key>.tif with the tags of their files; a block without data is missing."""
    cache_dir = str(tmp_path / "cache")
    place.wesm = [wesm_row("W_SP", end="2018/05/01"), wesm_row("W_UTM", project="U_2016", end="2016/04/01")]
    left, top = sp(X0 - 20, Y0 + 2020)
    for k in range(2):  # two tiles of 3,750 ft side by side: 2.3 km
        place.add_file("W_SP", f"sp{k}", "EPSG:2232", left + k * 3750, top, 2.5, 1500, unit=1200 / 3937)
    place.add_file("W_UTM", "u0", ZONE, X0 - 5, Y0 + 2005, 0.5, 4010, project="U_2016")
    layer = place.layer()
    grid = make_grid((X0 + 50, Y0 + 50, X0 + 1950, Y0 + 1950), 1.0, ZONE)
    layer.download(grid, cache_dir, None, "test")
    files = layer.files(grid, cache_dir)
    folder = os.path.join("usa", "3dep-opr", "epsg26913", "50_440")
    assert files and all(folder in os.path.normpath(f) for f in files)
    assert all(re.fullmatch(r"(2016|2018)_50[01]_440[01]_[0-9a-f]{8}\.tif", os.path.basename(f)) for f in files)
    mosaic = src.build_mosaic(files, grid, str(tmp_path / "m.npy"), "test")
    xs, ys = grid.transform @ np.meshgrid(np.arange(grid.width) + 0.5, np.arange(grid.height) + 0.5)
    truth = terrain(xs, ys)
    valid = np.isfinite(mosaic)
    assert valid.mean() > 0.9 and np.abs(mosaic[valid] - truth[valid]).max() < 0.5
    with rio.open(files[0]) as f:
        tags = f.tags()
    assert tags["sources"] and tags["years"]


def test_recorded_answer_with_wesm(http_server, tmp_path, monkeypatch):
    """The recorded OPR answer at the Oregon cove (tests/data/recorded/tnm/opr) with its WESM extract: every product
    is the 2016 survey's (by sourcedem_link), read with WESM's year and collect_end and the token of a 0.5 m survey in
    its own UTM zone (average), its record taken from the cache; nothing asked but the answer and the table."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recorded", "tnm", "opr")
    http_server.add_cassette(folder)
    with open(os.path.join(folder, "wesm.csv"), "rb") as f:
        http_server.add("/wesm.csv", f.read(), "text/csv")
    monkeypatch.setattr(ops, "WESM_URL", http_server.url("/wesm.csv"))
    with open(os.path.join(folder, "answers.json"), encoding="utf-8") as f:
        case = json.load(f)["case"]
    layer = tnm.OprBlocks("Test OPR", "Original Product Resolution (OPR) Digital Elevation Model (DEM)", "opr",
                          "usa/3dep-opr", 1.0, 1000, 2e6, api=http_server.url("/api/v1/products"))
    cache_dir = str(tmp_path / "cache")
    with open(os.path.join(folder, "wesm.csv"), encoding="utf-8") as f:
        row = ops.Wesm(ops.parse_wesm(f.read())).rows["CA_WestCoastElNinoUTM10_2016"]
    record = {"workunit": row["workunit"], "year": 2016, "collect_end": "2016-05-28", "wesm": ops.fingerprint(row),
              "rule": ops.RULE, "read": True, "unit": "metre", "factor": 1.0, "pixel_m": 0.5,
              "crs": rio.crs.CRS.from_epsg(26910).to_wkt(), "on_metres": False,
              "headers": [{"file": "x", "pixel_m": 0.5, "crs": rio.crs.CRS.from_epsg(26910).to_wkt(),
                           "on_metres": False, "unit": 1.0}]}
    ops._write_json(ops.record_path(cache_dir, row["workunit"]), record)
    items = layer.index.answers(cache_dir, case["lat"], case["lon"])
    assert len(items) == 35
    assert {(i["survey"], i["year"], i["published"], i["opr"], i["crs"]) for i in items} == {
        ("CA_WestCoastElNinoUTM10_2016", 2016, "2016-05-28", "x1:average1:2016-05-28:u1", "EPSG:26910")}
    assert not http_server.stray()
    assert [r.path for r in http_server.log] == ["/api/v1/products", "/wesm.csv"]


def test_usa_opr_in_the_catalogue(monkeypatch, tmp_path):
    """usa_opr: the OPR layer alone, fallback usgs10m, no countries (auto never picks it), no coverage (no download
    row), hidden on the public site (web.ADMIN_SOURCES), a listing, a sample and a credit of its own."""
    import web
    from sources import choose
    # auto at the cove (OPR only, no 1 m DEM within 2 km): usa's instead_without_data, never usa_opr
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "us")
    for answer, expected in ((False, "usgs10m"), (True, "usa")):
        monkeypatch.setattr(src.SOURCES["usa"].nmt, "has_data_near", lambda lat, lon, cache_dir, a=answer: a)
        assert choose.choose_source("auto", 44.767488, -124.070346, str(tmp_path))[0].id == expected
    assert choose.choose_source("usa_opr", 44.767488, -124.070346, str(tmp_path))[0].id == "usa_opr"
    s = src.SOURCES["usa_opr"]
    assert isinstance(s.nmt, tnm.OprBlocks) and s.nmt is src.catalogue.usa.USGS_OPR
    assert (s.nmt.prefix, s.nmt.folder, s.nmt.native_res) == ("opr", "usa/3dep-opr", 1.0)
    assert s.fallback == "usgs10m" and s.countries == () and s.coverage is None and s.nmpt is None
    assert s.listing is not None and s.sample and [c.data for c in s.credits] == ["USGS 3DEP source DEMs (OPR)"]
    assert "usa_opr" in web.ADMIN_SOURCES
    source_field = lambda fields: next(f for f in fields if f["name"] == "source")["choices"]  # noqa: E731
    assert "usa_opr" in source_field(web.schema())  # an administrator's form, and the local app's
    assert "usa_opr" not in source_field(web.schema(hidden_sources=web.ADMIN_SOURCES))  # the public form
    # no download row: the area download's rows come from the sources' coverage (tools/area_rows.py)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import area_rows
    assert all(row.source != "usa_opr" for row in area_rows.catalogue() + area_rows.parts())
    assert not s.offline  # no offline box: never chosen without the country lookup either
