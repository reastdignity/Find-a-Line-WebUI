"""Ontario: 1 km tiles that are members of the province's package ZIPs, listed through the GeoHub's package index
(an ArcGIS FeatureServer of the packages' footprints) and each package's central directory read by Range
(sources/indexes/packages.py), read one member at a time (sources/layers/packages.py), in UTM zones 15-18; the
catalogue's source. Offline: tests/http_server.py serves the FeatureServer and packages made here with zipfile (the
oracle); the catalogue's own layers are pointed at it.

Real answers recorded on 2026-11-16 in tests/data/ontario/: the projects of both index layers
(returnDistinctValues), and the head of a real member (1km174820498302023LHURONGEORGIANBAY_DTM.tif of
HuronGeorgianBay-DTM-40.zip: a "PixelIsPoint" GeoTIFF whose directory sits at the file's end, so the fixture is its
8-byte header and its directory with every value it points at moved behind it, the pixels left out)."""

import gzip
import io
import json
import os
import re
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.env import Env
from rasterio.transform import from_origin
from rasterio.warp import transform

import osm
import sources as src
from grid import make_grid
from http_server import Answer
from sources import net
from sources.catalogue import canada
from sources.indexes import packages as pk
from sources.indexes.cached import IndexUnavailable
from sources.layers.packages import PackageMember, PackageTiles
from sources.mosaic import build_mosaic
from tile_values import TILE_EPS

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "ontario")
FS = "/rest/services/Index/FeatureServer"
PACKAGES = "/Packages/"
ON = src.SOURCES["ontario"]
# Rattlesnake Point (zone 17): its tile and two of its neighbours; the 0.25° tile holding them
LAT, LON = 43.4690, -79.9198
EAST, NORTH = 587, 4813
TEN = 100.0  # the members made here: 10 x 10 px of 100 m, so a member is a whole 1 km tile


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)


def _raster(east: int, north: int, value: float, crs: str = "EPSG:6660", driver: str = "GTiff",
            nodata: float = -32767.0, shift: float = 0.0, point: bool = False, holes: bool = False) -> bytes:
    """A member of tile (east, north) km: 10 x 10 px of 100 m holding value (no data in its last row), in crs
    (the files' own names of their CRS: 6660 a compound one, 26917 NAD83 in the .img files); shift moves it east
    (metres); point writes it "PixelIsPoint" with the tie point at the first pixel's centre (as the province's);
    holes: no data in its east half too."""
    values = np.full((10, 10), value, np.float32)
    values[-1] = nodata
    if holes:
        values[:, 5:] = nodata
    ext = ".img" if driver == "HFA" else ".tif"
    with Env(GTIFF_POINT_GEO_IGNORE=False), rio.io.MemoryFile(ext=ext) as memfile:
        with memfile.open(driver=driver, width=10, height=10, count=1, dtype="float32", crs=crs, nodata=nodata,
                          transform=from_origin(east * 1000 + shift, (north + 1) * 1000, TEN, TEN)) as dst:
            dst.write(values, 1)
            if point:
                dst.update_tags(AREA_OR_POINT="Point")
        return memfile.read()


def _zip(members, zip64: bool = False) -> bytes:
    """A package of members (name, body), deflated; zip64: its directory and end record in ZIP64 form."""
    out = io.BytesIO()
    zf = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    for name, body in members:
        zf.writestr(zipfile.ZipInfo(name, (2026, 1, 16, 12, 0, 0)), body, zipfile.ZIP_DEFLATED)
    limit = zipfile.ZIP64_LIMIT
    if zip64:
        zipfile.ZIP64_LIMIT = 0
    try:
        zf.close()
    finally:
        zipfile.ZIP64_LIMIT = limit
    return out.getvalue()


def _name(zone: int, east: int, north: int, year, code: str = "GTA2023_DTM", ext: str = "tif") -> str:
    return f"1km{zone}{east * 10:04d}{north * 10:05d}{year or ''}L{code}.{ext}"


def _feature(server, package: str, project: str, res: float = 0.5) -> dict:
    url = server.url(f"{PACKAGES}{package}.zip")
    return {"attributes": {"Package": package, "Project": project, "Resolution": res,
                           "DownloadLink": f'<a href="{url}" target = "_blank">Lidar DTM {package}</a>'}}


def _featureserver(server, features, page=None):
    """The package index: every query answers features (in pages of page while exceededTransferLimit); it
    replaces the index served before."""
    server.routes[:] = [(prefix, handler) for prefix, handler in server.routes if prefix != FS]
    def query(request):
        q = dict(request.query)
        assert q["f"] == "json" and q["inSR"] == "4326" and q["returnGeometry"] == "false"
        assert set(q["outFields"].split(",")) == {"Package", "Project", "DownloadLink", "Resolution"}
        offset, count = int(q["resultOffset"]), page or int(q["resultRecordCount"])
        answer = {"features": features[offset:offset + count]}
        if offset + count < len(features):
            answer["exceededTransferLimit"] = True
        return Answer(200, json.dumps(answer).encode(), {"Content-Type": "application/json"})
    server.route(FS, query)


def _package(server, package: str, members, zip64: bool = False, etag: str = '"p1"') -> bytes:
    body = _zip(members, zip64)
    server.add(f"{PACKAGES}{package}.zip", body, "application/zip", headers={"ETag": etag})
    return body


@pytest.fixture
def layer(http_server, monkeypatch):
    """The catalogue's own DTM layer, its index and packages on the local server, nothing kept between tests."""
    layer = ON.nmt
    monkeypatch.setattr(layer.listing, "url", http_server.url(FS))
    monkeypatch.setattr(layer.listing, "packages", http_server.url(PACKAGES))
    monkeypatch.setattr(layer.listing, "_asked", set())
    monkeypatch.setattr(layer.index, "_listed", {})
    return layer


def _grid(lat: float = LAT, lon: float = LON, half: float = 400.0, crs: str = None):
    crs = crs or ON.working_crs(lat, lon)
    (x,), (y,) = transform("EPSG:4326", crs, [lon], [lat])
    return make_grid((x - half, y - half, x + half, y + half), 1.0, crs)


def _members_of(body: bytes):
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return {i.filename: i for i in zf.infolist()}


# Names, links, dates

def test_member_names():
    """Real members' names: the zone, the lower-left corner in 100 m, the year when the name has one (Ottawa River's
    have none), a folder before them; anything else is no tile. Muskoka's CGVD28 copies are left out."""
    assert pk.member_tile("1km175870481302023LGTA2023_DTM.tif") == (17, 587, 4813, 2023)
    assert pk.member_tile("1km175870481302018LHalton_DTM.img") == (17, 587, 4813, 2018)
    assert pk.member_tile("1km174820498302023LHURONGEORGIANBAY_DTM.tif") == (17, 482, 4983, 2023)
    assert pk.member_tile("1km18296050560LOTTAWARIVER.tif") == (18, 296, 5056, 0)
    assert pk.member_tile("1km183910491202008LEAP.img") == (18, 391, 4912, 2008)
    assert pk.member_tile("GTA2023-DTM-01/1km175870481302023LGTA2023_DSM.TIF") == (17, 587, 4813, 2023)
    for name in ("1km175870481302023LGTA2023_DTM.tif.aux.xml", "1km175875481302023LGTA2023_DTM.tif",
                 "1km175870481352023LGTA2023_DTM.tif", "readme.txt", "1km1758704813LGTA.tif"):
        assert pk.member_tile(name) is None, name
    exclude = re.compile(canada.ON_EXCLUDE)
    assert exclude.search("1km175930500502018LMuskoka_CGVD28_DTM.tif")
    assert not exclude.search("1km175930500502018LMuskoka_CGVD2013_DTM.tif")
    assert not exclude.search("1km175870481302023LGTA2023_DTM.tif")


def test_package_links():
    prefix = canada.ON_PACKAGES
    link = f'<a href="{prefix}GTA2023-DTM-01.zip" target = "_blank">Lidar DTM GTA 2023 Package 01</a>'
    assert pk.package_url(link, prefix) == f"{prefix}GTA2023-DTM-01.zip"
    assert pk.package_url(f"<a href='{prefix}A.zip'>A</a>", prefix) == f"{prefix}A.zip"
    assert pk.package_url(f"{prefix}A.zip", prefix) == f"{prefix}A.zip"
    for bad in (None, "", '<a href="https://example.com/Packages/A.zip">x</a>', f'<a href="{prefix}x/A.zip">x</a>',
                f'<a href="{prefix}A.pdf">x</a>', "<a>no link</a>"):
        assert pk.package_url(bad, prefix) is None, bad


def test_every_project_of_the_index_has_its_date():
    """The projects both index layers list (recorded 2026-11-16) are in the catalogue's table; two projects have
    the same date only where they share no tile (the tile index of 2026-10-28: 63 pairs of projects share tiles,
    none of them with equal dates); a project the table lacks gets its name's latest year."""
    for kind in ("dtm", "dsm"):
        with open(os.path.join(DATA, f"projects-{kind}.json"), encoding="utf-8") as f:
            projects = {feature["attributes"]["Project"] for feature in json.load(f)["features"]}
        assert len(projects) == 39 and projects <= set(canada.ON_PROJECT_DATES), projects - set(canada.ON_PROJECT_DATES)
    dates = canada.ON_PROJECT_DATES
    assert all(re.fullmatch(r"20[0-2]\d-[01]\d-[0-3]\d", d) for d in dates.values())
    same = {(a, b) for a in dates for b in dates if a < b and dates[a] == dates[b]}
    assert same == {("DEDSFM Atikokan 2024", "DEDSFM Ignace 2024"), ("DEDSFM Manitoulin 2024", "DEDSFM Sudbury 2023-24")}
    assert dates["GTA 2023"] > dates["GTA 2014-18"] and dates["Belleville 2022"] > dates["Eastern Ontario 2021-22"]
    assert dates["Ottawa River 2019-20"] > dates["Ottawa-Gatineau 2019-20"]
    assert pk.project_date("GTA 2023", dates) == "2023-05-11"
    assert pk.project_date("DEDSFM Somewhere 2026-27", dates) == "2027-12-31"
    assert pk.project_date("No year", dates) == "0000-00-00"


# The listing: the index, the packages' directories

def test_index_pages_and_zip64_directories(http_server, layer, tmp_path):
    """The index asked for the 0.25° tile grown by MARGIN_DEG, page by page; each package's link checked (another
    host's never asked); each directory read by a HEAD and one Range of the tail (a ZIP64 one too), kept per
    package with its ETag; the members over the 0.25° tile listed with what zipfile says of them; another 0.25°
    tile reuses the kept directories."""
    a = _package(http_server, "A", [(_name(17, EAST, NORTH, 2023), _raster(EAST, NORTH, 200.0)),
                                    (_name(17, EAST + 1, NORTH, 2023), _raster(EAST + 1, NORTH, 201.0)),
                                    (_name(17, EAST, NORTH, 2023, "Muskoka_CGVD28_DTM"), _raster(EAST, NORTH, 9.0)),
                                    ("A/readme.txt", b"text")], zip64=True)
    _package(http_server, "B", [(_name(17, 600, 4900, 2023), _raster(600, 4900, 300.0))])
    features = [_feature(http_server, "A", "GTA 2023"), _feature(http_server, "B", "GTA 2023"),
                {"attributes": {"Package": "C", "Project": "GTA 2023", "Resolution": 0.5,
                                "DownloadLink": '<a href="https://example.com/Packages/C.zip">C</a>'}}]
    _featureserver(http_server, features, page=2)
    cache_dir = str(tmp_path)
    lat, lon = osm.tiles(LON, LAT, LON, LAT)[0]
    items = layer.index.answers(cache_dir, lat, lon)
    asked = [dict(r.query) for r in http_server.requests(FS)]
    assert [q["resultOffset"] for q in asked] == ["0", "2"]
    m = pk.MARGIN_DEG
    assert asked[0]["geometry"] == f"{lon - m},{lat - m},{lon + 0.25 + m},{lat + 0.25 + m}"
    ranges = [r.headers.get("range") for r in http_server.requests(PACKAGES) if r.method == "GET"]
    assert len([r for r in http_server.requests(PACKAGES) if r.method == "HEAD"]) == 2 and len(ranges) == 2
    assert all(r and r.startswith("bytes=") and r != "bytes=0-0" for r in ranges)
    assert not http_server.stray()
    zipped = _members_of(a)
    assert sorted((i["east"], i["north"]) for i in items) == [(EAST, NORTH), (EAST + 1, NORTH)]  # B's: elsewhere
    for item in items:
        info = zipped[item["member"]]
        assert (item["offset"], item["size"], item["usize"], item["crc"]) == (
            info.header_offset, info.compress_size, info.file_size, info.CRC)
        assert item["crs"] == "EPSG:2958" and item["zone"] == 17 and item["year"] == 2023
        assert item["date"] == "2023-05-11" and item["project"] == "GTA 2023" and item["length"] == len(a)
        assert item["extent"] == [item["east"] * 1000, item["north"] * 1000, item["east"] * 1000 + 1000,
                                  item["north"] * 1000 + 1000]
    kept = os.path.join(cache_dir, "ontario", "zipdir", "ontario-dtm", "A.json.gz")
    with gzip.open(kept, "rt", encoding="utf-8") as f:
        assert json.load(f)["etag"] == '"p1"'
    before = len(http_server.requests(PACKAGES))
    layer.index.answers(cache_dir, lat + 0.25, lon)  # the next tile north: the same packages, kept
    assert len(http_server.requests(PACKAGES)) == before


def test_changed_package_read_again(http_server, layer, tmp_path):
    """Asked again (an update), a package whose ETag and length are unchanged keeps its directory (a HEAD only);
    a new ETag reads it again."""
    _package(http_server, "A", [(_name(17, EAST, NORTH, 2023), _raster(EAST, NORTH, 200.0))])
    _featureserver(http_server, [_feature(http_server, "A", "GTA 2023")])
    cache_dir = str(tmp_path)
    lat, lon = osm.tiles(LON, LAT, LON, LAT)[0]
    layer.index.answers(cache_dir, lat, lon)
    layer.listing._asked.clear()
    layer.index.answers(cache_dir, lat, lon, "all")
    gets = [r for r in http_server.requests(PACKAGES) if r.method == "GET"]
    assert len(gets) == 1
    _package(http_server, "A", [(_name(17, EAST, NORTH, 2024), _raster(EAST, NORTH, 210.0))], etag='"p2"')
    layer.listing._asked.clear()
    items = layer.index.answers(cache_dir, lat, lon, "all")
    assert len([r for r in http_server.requests(PACKAGES) if r.method == "GET"]) == 2
    assert [i["year"] for i in items] == [2024]


def test_package_unavailable(http_server, layer, tmp_path, capsys):
    """A package that answers 404: the index is unavailable (nothing kept), and the cached files are used."""
    _featureserver(http_server, [_feature(http_server, "Gone", "GTA 2023")])
    grid = _grid()
    layer.index.use(str(tmp_path))
    assert layer.tiles(grid) is None
    assert "index not available" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(str(tmp_path), "ontario", "sheet-index"))
    lat, lon = osm.tiles(LON, LAT, LON, LAT)[0]
    with pytest.raises(IndexUnavailable):
        layer.index.answers(str(tmp_path), lat, lon)


# Reading the members

def test_members_read_by_range(http_server, layer, tmp_path):
    """A GeoTIFF member (a compound CRS, nodata -32767) and an ERDAS Imagine one (EPSG:26917, nodata -3.4e38) read
    by one Range each, never the whole package; written as tiles in the zone's CRS with their values, no data as
    NaN, under ontario/dtm/epsg2958/; the estimate is the members' sizes."""
    body = _package(http_server, "A", [
        (_name(17, EAST, NORTH, 2023), _raster(EAST, NORTH, 200.25)),
        (_name(17, EAST - 1, NORTH, 2018, "Halton_DTM", "img"),
         _raster(EAST - 1, NORTH, 210.5, "EPSG:26917", "HFA", -3.4028230607370965e+38))])
    _featureserver(http_server, [_feature(http_server, "A", "GTA 2023")])
    cache_dir = str(tmp_path)
    grid = _grid()
    tiles, todo, mb = layer.estimate(grid, cache_dir, None)
    zipped = _members_of(body)
    assert (tiles, todo) == (2, 2) and mb == pytest.approx(sum(i.compress_size for i in zipped.values()) / 1e6)
    src.download_layers([(layer, "terrain")], grid, cache_dir, None)
    files = layer.files(grid, cache_dir)
    assert len(files) == 2
    assert all(os.path.normpath(f).split(os.sep)[-5:-2] == ["ontario", "dtm", "epsg2958"] for f in files)
    for path in files:
        with rio.open(path) as tile:
            assert tile.crs.to_epsg() == 2958 and tile.res == (TEN, TEN)
            values = tile.read(1)
        assert np.isnan(values[-1]).all()
        expected = 200.25 if os.path.basename(path).startswith(f"{EAST}_") else 210.5
        assert np.abs(values[:-1] - expected).max() <= TILE_EPS
    gets = [r for r in http_server.requests(PACKAGES) if r.method == "GET"]
    assert all(r.headers.get("range", "").startswith("bytes=") for r in gets)
    assert all(r.headers["range"] != "bytes=0-0" for r in gets)
    assert layer.used(grid, cache_dir)["survey_years"] == [2018, 2023]


def test_member_beyond_its_box_cut_to_it(http_server, layer, tmp_path):
    """A member reaching a pixel beyond its tile on every side (as LEAP 2009's DSM members reach 100 m) and one with
    float noise in its origin (as Muskoka's): both cached on the tile's box exactly, the first cut to it."""
    values = np.arange(144, dtype=np.float32).reshape(12, 12) + 100.0
    with rio.io.MemoryFile(ext=".img") as memfile:
        with memfile.open(driver="HFA", width=12, height=12, count=1, dtype="float32", crs="EPSG:26917",
                          transform=from_origin(EAST * 1000 - TEN, (NORTH + 1) * 1000 + TEN, TEN, TEN)) as dst:
            dst.write(values, 1)
        wide = memfile.read()
    with rio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=10, height=10, count=1, dtype="float32", crs="EPSG:2958",
                          transform=from_origin((EAST - 1) * 1000 - 2e-10, (NORTH + 1) * 1000, TEN, TEN)) as dst:
            dst.write(np.full((1, 10, 10), 300.0, np.float32))
        noisy = memfile.read()
    _package(http_server, "A", [(_name(17, EAST, NORTH, 2008, "LEAP_DSM", "img"), wide),
                                (_name(17, EAST - 1, NORTH, 2008, "LEAP_DSM", "img"), noisy)])
    _featureserver(http_server, [_feature(http_server, "A", "LEAP 2009")])
    grid = _grid()
    src.download_layers([(layer, "terrain")], grid, str(tmp_path), None)
    files = sorted(layer.files(grid, str(tmp_path)))
    assert len(files) == 2
    with rio.open(next(f for f in files if os.path.basename(f).startswith(f"{EAST}_"))) as tile:
        assert (tile.width, tile.height) == (10, 10)
        assert tuple(tile.transform)[:6] == (TEN, 0.0, EAST * 1000.0, 0.0, -TEN, (NORTH + 1) * 1000.0)
        assert np.abs(tile.read(1) - values[1:-1, 1:-1]).max() <= TILE_EPS
    with rio.open(next(f for f in files if os.path.basename(f).startswith(f"{EAST - 1}_"))) as tile:
        assert tile.transform.c == (EAST - 1) * 1000.0


def test_member_off_its_box_never_cached(http_server, layer, tmp_path):
    """A member half a pixel off its tile's box (a tie point read as the corner) is refused, nothing cached."""
    _package(http_server, "A", [(_name(17, EAST, NORTH, 2023), _raster(EAST, NORTH, 200.0, shift=TEN / 2))])
    _featureserver(http_server, [_feature(http_server, "A", "GTA 2023")])
    grid = _grid(half=100)
    with pytest.raises(RuntimeError, match="off its tile's box"):
        src.download_layers([(layer, "terrain")], grid, str(tmp_path), None)
    assert layer.files(grid, str(tmp_path)) == []


def test_pixel_is_point_header():
    """The head of a real member (HuronGeorgianBay-DTM-40, recorded 2026-11-16): "PixelIsPoint" with its tie point
    at the first pixel's centre, which GDAL places on the tile's 1 km box (482 000, 4 983 000 - 4 984 000); read as
    if the tie point were the corner (GTIFF_POINT_GEO_IGNORE) it would lie half a pixel off, which the reader
    refuses. A member written so here (rasterio's PixelIsPoint) lands on its box too."""
    with gzip.open(os.path.join(DATA, "1km174820498302023LHURONGEORGIANBAY_DTM.head.tif.gz")) as f:
        head = f.read()
    tile = pk.PackageTile("EPSG:2958", 482, 4983, 2023, "00000000")
    reader = PackageMember("test")
    with rio.io.MemoryFile(head) as memfile, memfile.open() as member:
        assert member.tags()["AREA_OR_POINT"] == "Point" and member.nodata == -32767
        assert member.crs.to_epsg() == 2958 and (member.width, member.height) == (2000, 2000)
        assert tuple(member.transform)[:6] == (0.5, 0.0, 482000.0, 0.0, -0.5, 4984000.0)
        reader.placed(member.transform, member.width, member.height, tile, "head")
    with Env(GTIFF_POINT_GEO_IGNORE=True), rio.io.MemoryFile(head) as memfile, memfile.open() as member:
        assert tuple(member.transform)[:6] == (0.5, 0.0, 482000.25, 0.0, -0.5, 4983999.75)
        with pytest.raises(RuntimeError, match="off its tile's box"):
            reader.placed(member.transform, member.width, member.height, tile, "head")
    with rio.io.MemoryFile(_raster(EAST, NORTH, 1.0, point=True)) as memfile, memfile.open() as member:
        assert member.tags()["AREA_OR_POINT"] == "Point"
        reader.placed(member.transform, member.width, member.height,
                      pk.PackageTile("EPSG:2958", EAST, NORTH, 2023, "00000000"), "made")


def test_moved_member_read_from_the_new_directory(http_server, layer, tmp_path):
    """The package was replaced (another order of its members, a new ETag) after its directory was kept: the
    member's offset holds another member's header, so its directory is read again and the member read from its new
    offset; a package gone (404) fails the tile, nothing cached."""
    first = (_name(17, EAST, NORTH, 2023), _raster(EAST, NORTH, 200.0))
    other = (_name(17, EAST + 5, NORTH, 2023), _raster(EAST + 5, NORTH, 1.0))
    _package(http_server, "A", [first, other])
    _featureserver(http_server, [_feature(http_server, "A", "GTA 2023")])
    cache_dir = str(tmp_path)
    grid = _grid(half=100)
    layer.index.use(cache_dir)
    assert len(layer.tiles(grid)) == 1
    _package(http_server, "A", [other, first], etag='"p2"')  # the same members, moved
    src.download_layers([(layer, "terrain")], grid, cache_dir, None)
    (path,) = layer.files(grid, cache_dir)
    with rio.open(path) as tile:
        assert np.nanmax(np.abs(tile.read(1) - 200.0)) <= TILE_EPS
    # Gone: the tile fails
    http_server.answers.pop(("GET", f"{PACKAGES}A.zip", ()))
    os.remove(path)
    layer.index._listed.clear()
    with pytest.raises(RuntimeError, match="Could not download"):
        src.download_layers([(layer, "terrain")], grid, cache_dir, "all")


# Several surveys of a place

def test_newest_project_wins_the_place(http_server, layer, tmp_path):
    """Projects over a tile: the newest survey's member is used whole (the others are never read): the later year
    in the members' names first (Huron-Georgian Bay 2022-23 ends later than GTA 2023, but its tile of 2022 is
    older than GTA 2023's), then the project's date; two members of one project at a place: the later year. A
    newer project published later replaces the cached older tile (pruned once the newer is cached)."""
    _package(http_server, "Old", [(_name(17, EAST, NORTH, 2018, "Halton_DTM"), _raster(EAST, NORTH, 100.0)),
                                  (_name(17, EAST - 1, NORTH, 2018, "Halton_DTM"), _raster(EAST - 1, NORTH, 101.0))])
    _featureserver(http_server, [_feature(http_server, "Old", "GTA 2014-18")])
    cache_dir = str(tmp_path)
    grid = _grid(half=600)
    src.download_layers([(layer, "terrain")], grid, cache_dir, None)
    old = layer.files(grid, cache_dir)
    assert len(old) == 2 and all("_2018_" in os.path.basename(p) for p in old)
    # GTA 2023 published: one tile in two members of the project (2022 and 2023)
    _package(http_server, "New", [(_name(17, EAST, NORTH, 2022, "GTA2023_DTM"), _raster(EAST, NORTH, 202.2)),
                                  (_name(17, EAST, NORTH, 2023, "GTA2023_DTM"), _raster(EAST, NORTH, 202.3))])
    _package(http_server, "HGB", [(_name(17, EAST, NORTH, 2022, "HURONGEORGIANBAY_DTM"), _raster(EAST, NORTH, 1.0))])
    _featureserver(http_server, [_feature(http_server, "Old", "GTA 2014-18"), _feature(http_server, "New", "GTA 2023"),
                                 _feature(http_server, "HGB", "DEDSFM Huron-Georgian Bay 2022-23")])
    layer.index._listed.clear()
    layer.listing._asked.clear()
    tiles = layer.index.versions.query(layer.index, grid, cache_dir, "all")
    assert [(t.east, t.year, t.project) for t in tiles] == [(EAST, 2023, "GTA 2023"), (EAST - 1, 2018, "GTA 2014-18")]
    src.download_layers([(layer, "terrain")], grid, cache_dir, "all")
    files = sorted(os.path.basename(p) for p in layer.files(grid, cache_dir))
    assert [f.split("_")[:3] for f in files] == [[str(EAST - 1), str(NORTH), "2018"], [str(EAST), str(NORTH), "2023"]]
    assert not os.path.exists(next(p for p in old if os.path.basename(p).startswith(f"{EAST}_")))  # pruned
    member = layer.index.versions.path(cache_dir, tiles[0])
    with rio.open(member) as tile:
        assert np.nanmax(np.abs(tile.read(1) - 202.3)) <= TILE_EPS
    read = [r.path for r in http_server.requests(PACKAGES) if r.method == "GET"]
    assert read.count(f"{PACKAGES}Old.zip") == 3  # its tail and its two members of the first download only
    assert read.count(f"{PACKAGES}HGB.zip") == 1  # its tail only


def test_tile_outside_every_package(http_server, layer, tmp_path):
    """No package's footprint over the place: no tile, nothing to download, no request to the package host; a
    package listed without a member there: its directory only."""
    _featureserver(http_server, [])
    cache_dir = str(tmp_path)
    grid = _grid()
    assert layer.estimate(grid, cache_dir, None) == (0, 0, 0.0)
    assert layer.missing(grid, cache_dir, None) == [] and not http_server.requests(PACKAGES)
    assert layer.has_data_near(LAT, LON, cache_dir) is False
    _package(http_server, "Far", [(_name(17, 600, 4900, 2023), _raster(600, 4900, 1.0))])
    _featureserver(http_server, [_feature(http_server, "Far", "GTA 2023")])
    for lat, lon in osm.tiles(LON, LAT, LON, LAT):
        os.remove(layer.index.index_path(cache_dir, lat, lon))
    layer.index._listed.clear()
    assert layer.tiles(grid) == []
    assert {r.method for r in http_server.requests(PACKAGES)} == {"HEAD", "GET"}
    assert len(http_server.requests(PACKAGES)) == 2


def test_zone_border(http_server, layer, tmp_path):
    """A grid across 78° W (zone 18, its working CRS) over tiles of zone 17 (Central East 2025) and zone 18
    (Belleville 2022): both listed, each cached in its zone's folder, the newer first though not in the working
    CRS; the mosaic takes the newer where it has data and the older beyond it. Of two tiles of one project in two
    zones (Sault Ste Marie's), the working CRS's comes first."""
    lat, lon = 44.30, -78.0
    (x17,), (y17,) = transform("EPSG:4326", "EPSG:2958", [lon], [lat])
    (x18,), (y18,) = transform("EPSG:4326", "EPSG:2959", [lon], [lat])
    e17, n17, e18, n18 = int(x17 // 1000), int(y17 // 1000), int(x18 // 1000), int(y18 // 1000)
    _package(http_server, "CE", [(_name(17, e17, n17, 2025, "CENTRALEAST_DTM"), _raster(e17, n17, 170.0, holes=True))])
    _package(http_server, "BV", [(_name(18, e18, n18, 2022, "BELLEVILLE_DTM"),
                                  _raster(e18, n18, 180.0, "EPSG:2959"))])
    _featureserver(http_server, [_feature(http_server, "BV", "Belleville 2022"),
                                 _feature(http_server, "CE", "DEDSFM Central East 2025")])
    cache_dir = str(tmp_path)
    grid = _grid(lat, lon + 0.005, half=700)
    assert grid.crs == "EPSG:2959"
    layer.index.use(cache_dir)
    tiles = layer.tiles(grid)
    assert [(t.crs, t.east, t.north) for t in tiles] == [("EPSG:2958", e17, n17), ("EPSG:2959", e18, n18)]
    src.download_layers([(layer, "terrain")], grid, cache_dir, None)
    files = layer.files(grid, cache_dir)
    assert [f.split(os.sep)[-3] for f in files] == ["epsg2958", "epsg2959"]
    mosaic = build_mosaic(files, grid, str(tmp_path / "m.npy"), "test")
    found = set(np.unique(np.round(mosaic[np.isfinite(mosaic)])).astype(int))
    assert found == {170, 180}
    same = pk.PackageVersions("x")._sorted([pk.PackageTile("EPSG:2958", 1, 1, 2023, "a", "2024-04-24"),
                                            pk.PackageTile("EPSG:3160", 1, 1, 2023, "b", "2024-04-24")], "EPSG:3160")
    assert [t.crs for t in same] == ["EPSG:3160", "EPSG:2958"]


# The source

def test_declaration():
    assert ON.regions == ("ca-on",) and ON.countries == ("ca",) and ON.crs is None
    assert ON.local_crs is canada.on_utm_crs and ON.grid_origin == (0.0, 0.0)
    assert ON.fallbacks == ["canada", "canada_2m", "mrdem30"]  # never FABDEM
    assert ON.instead_without_data == "canada" and ON.default_resolution == 1.0
    assert ON.neighbours == ("usa",) and src.SOURCES["usa"].neighbours[-1] == "ontario"
    assert src.SOURCES["usa"].neighbours.index("canada") < src.SOURCES["usa"].neighbours.index("ontario")
    assert "canada" not in ON.neighbours and "ontario" not in src.SOURCES["canada"].neighbours
    assert canada.ON_ZONES == {15: "EPSG:3159", 16: "EPSG:3160", 17: "EPSG:2958", 18: "EPSG:2959"}
    for zone, code in canada.ON_ZONES.items():
        assert rio.crs.CRS.from_user_input(code).to_wkt().startswith(f'PROJCS["NAD83(CSRS) / UTM zone {zone}N"')
    assert [canada.on_utm_crs(45.0, lon) for lon in (-94.5, -89.0, -79.9, -77.2, -74.5, -100.0, -70.0)] == [
        "EPSG:3159", "EPSG:3160", "EPSG:2958", "EPSG:2959", "EPSG:2959", "EPSG:3159", "EPSG:2959"]
    for layer, kind, index, size in ((ON.nmt, "dtm", "Ontario_Digital_Terrain_Model_Lidar_Derived_WFL1", 9e6),
                                     (ON.nmpt, "dsm", "Ontario_DSM_Lidar_Derived_Package_Map_WFL1", 6e6)):
        assert isinstance(layer, PackageTiles) and isinstance(layer, src.IndexedTiles)
        assert layer.folder == f"ontario/{kind}" and layer.prefix == f"ontario-{kind}" and layer.native_res == 0.5
        assert layer.featureserver == ("https://services1.arcgis.com/TJH5KDher0W13Kgo/arcgis/rest/services/"
                                       f"{index}/FeatureServer/0")
        assert layer.packages == "https://ws.gisetl.lrc.gov.on.ca/fmedatadownload/Packages/"
        assert layer.listing.zones == canada.ON_ZONES and layer.listing.dates == canada.ON_PROJECT_DATES
        assert layer.listing.exclude.pattern == canada.ON_EXCLUDE and layer.bytes_per_tile() == size
        assert layer.index.ttl_days == 60 and layer.listing.ttl_days == 60 and layer.ttl_days is None
        assert layer.rewrites and layer.credit is ON.credits[0]
    assert src.net.HOST_SLOTS_OF["ws.gisetl.lrc.gov.on.ca"] == 2
    credit = ON.credits[0]
    assert credit.attribution == "Contains information licensed under the Open Government Licence – Ontario."
    assert credit.licence == "OGL - Ontario 1.0" and credit.url == "https://www.ontario.ca/page/open-government-licence-ontario"
    assert ON.ortho is None and ON.sample == (44.9055, -77.1899)
    order = [s.id for s in canada.SOURCES]  # its offline boxes before canada's
    assert order.index("british_columbia") < order.index("ontario") < order.index("canada")
    assert src.AREA_NAMES["ca-on"] == "Ontario" and ON.map_areas() == ("ca-on",)


@pytest.fixture
def offline(monkeypatch):
    def lookup(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(osm, "reverse", lookup)


@pytest.mark.parametrize("lat, lon, region", [
    (43.469, -79.920, "ca-on"),  # Rattlesnake Point
    (44.906, -77.190, "ca-on"),  # Mazinaw Rock
    (45.004, -81.228, "ca-on"),  # Lion's Head
    (45.42, -75.70, "ca-on"),    # Ottawa
    (45.83, -77.12, "ca-on"),    # Pembroke
    (46.32, -78.70, "ca-on"),    # Mattawa
    (47.51, -79.68, "ca-on"),    # Haileybury, Lake Timiskaming
    (48.38, -89.25, "ca-on"),    # Thunder Bay
    (49.77, -94.49, "ca-on"),    # Kenora
    (51.27, -80.65, "ca-on"),    # Moosonee
    (55.99, -87.65, "ca-on"),    # Fort Severn
    (45.48, -75.70, "ca-on"),    # Gatineau (Quebec): the boxes hold the Ottawa River's Quebec shore
    (45.50, -73.57, None),       # Montreal (Quebec)
    (47.33, -79.43, None),       # Ville-Marie (Quebec), across Lake Timiskaming
    (48.24, -79.02, None),       # Rouyn-Noranda (Quebec)
    (49.90, -97.14, None),       # Winnipeg (Manitoba)
    (54.0, -94.0, None),         # Manitoba, west of the border's diagonal
])
def test_offline_region_boxes(tmp_path, offline, lat, lon, region):
    """Offline, the region boxes give Ontario inside Canada, hold every tile of the province's tile index (2026-10-28:
    8 of 200 296 centres outside, just across 79.517° W) and so the Ottawa River's Quebec shore, and keep off the
    rest of Quebec and Manitoba."""
    assert src.choose.region_codes(lat, lon, str(tmp_path), "ca") == ((region,) if region else ())


def test_choose_ontario_or_canada(tmp_path, monkeypatch):
    """--source auto in Ontario: ontario where the province has tiles within 2 km, canada itself elsewhere."""
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "ca")
    monkeypatch.setattr(src.choose, "region_codes", lambda lat, lon, cache_dir, code: ("ca-on",))
    monkeypatch.setattr(ON.nmt, "has_data_near", lambda lat, lon, cache_dir: True)
    assert src.choose_source("auto", LAT, LON, str(tmp_path))[0] is ON
    monkeypatch.setattr(ON.nmt, "has_data_near", lambda lat, lon, cache_dir: False)
    source, why = src.choose_source("auto", 48.39, -88.80, str(tmp_path))
    assert source is src.SOURCES["canada"] and "no terrain data near it" in why
