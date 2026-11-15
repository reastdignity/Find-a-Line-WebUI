"""The Netherlands (PDOK's AHN4 WCS, 0.5 m), Caribbean Netherlands (whole-island AHN files of 2023 whose LOCAL_CS
is forced to the island's CRS: Windows(force_crs=True)) and the Faroe Islands (one DSM GeoTIFF whose pixel edges lie
off whole metres)."""

import os
import sys

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin
from rasterio.warp import transform

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cache  # noqa: E402
import grid as gd  # noqa: E402
import sources as src  # noqa: E402
from sources import choose  # noqa: E402
from sources.catalogue import faroe, netherlands  # noqa: E402
from sources.layers.fileblocks import FileBlocks  # noqa: E402
from sources.readers import windows  # noqa: E402
from tile_values import same_tile  # noqa: E402

NODATA = 3.4028234663852886e+38  # the AHN files'
LOCAL_CS = ('LOCAL_CS["unnamed",UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],'
            'AXIS["Northing",NORTH]]')  # as the AHN files of Caribbean Netherlands name it
ISLANDS = ("saba", "sint_eustatius", "bonaire")


def test_declarations():
    """The European Netherlands within its box on the WCS's 0.5 m pixels in RD New; each island of Caribbean
    Netherlands its own source in its own CRS (one CRS per FileBlocks layer), chosen by its box (Nominatim names
    the islands country nl); the Faroe Islands on the DSM as terrain, its gaps from Copernicus."""
    nl = src.SOURCES["netherlands"]
    assert nl.countries == ("nl",) and nl.bbox == netherlands.NL_BOX and nl.crs == "EPSG:28992"
    assert nl.default_resolution == 1.0 and nl.fallbacks == ["europe"]
    assert set(nl.neighbours) == {"north_rhine_westphalia", "lower_saxony"}
    for layer, coverage in ((nl.nmt, "dtm_05m"), (nl.nmpt, "dsm_05m")):
        assert (layer.coverage, layer.fetch_res, layer.tile_px, layer.crs) == (coverage, 0.5, 2000, "EPSG:28992")
        assert layer.url == netherlands.NL_WCS and layer.ttl_days is None
    assert nl.nmt.folder == "netherlands/ahn4-dtm" and nl.nmpt.folder == "netherlands/ahn4-dsm"
    crss = {"saba": "EPSG:10641", "sint_eustatius": "EPSG:10745", "bonaire": "EPSG:10759"}
    areas = {"saba": "nl-bq2", "sint_eustatius": "nl-bq3", "bonaire": "nl-bq1"}
    for sid in ISLANDS:
        s = src.SOURCES[sid]
        assert s.countries == ("nl",) and s.regions == () and s.crs == crss[sid] and s.map_areas() == (areas[sid],)
        assert s.offline == (("nl", s.bbox),) and s.default_resolution == netherlands.BQ_RESOLUTION
        lat, lon = s.sample
        south, north, west, east = s.bbox
        assert south <= lat <= north and west <= lon <= east
        for layer in (s.nmt, s.nmpt):
            assert isinstance(layer, FileBlocks) and layer.reader.force_crs and layer.native_res == 0.5
            assert layer.crs == crss[sid] and layer.folder.startswith("caribbean_nl/ahn-")
    # The islands' blocks share no folder (their block numbers are in different CRSs)
    folders = [src.SOURCES[sid].nmt.folder for sid in ISLANDS] + [src.SOURCES[sid].nmpt.folder for sid in ISLANDS]
    assert len(set(folders)) == 6
    fo = src.SOURCES["faroe_islands"]
    assert fo.countries == ("fo",) and fo.crs == "EPSG:5316" and fo.nmpt is None and fo.fallbacks == ["copernicus"]
    assert fo.grid_origin == faroe.FO_ORIGIN and fo.default_resolution == 2.0 and fo.neighbours == ()
    assert fo.nmt.folder == "faroe/dsm-2015-2m/20241112" and not fo.nmt.reader.force_crs
    for host, slots in (("service.pdok.nl", 4), ("basisdata.nl", 4), ("cdn.foroyakort.fo", 2)):
        assert src.net.HOST_SLOTS_OF[host] == slots


def test_printed_texts_in_cp1250():
    """Names, descriptions and notes are printed to a Windows console (cp1250): no "ø" in them; the credits and
    the orthophoto's attribution keep Umhvørvisstovan's name (files and the map only)."""
    for sid in ("netherlands", "faroe_islands") + ISLANDS:
        s = src.SOURCES[sid]
        for text in (s.name, s.description, s.note, s.nmt.description, s.ortho.name,
                     s.nmpt.description if s.nmpt else ""):
            text.encode("cp1250")
    assert src.SOURCES["faroe_islands"].credits[0].attribution == (
        "Data from the Faroese Environment Agency, Umhvørvisstovan: DSM 2015 (2 m), {year}")


@pytest.mark.parametrize("lat, lon, expected", [
    (17.4783, -62.9600, "sint_eustatius"),   # The Quill
    (17.6350, -63.2370, "saba"),             # Mount Scenery
    (12.2830, -68.3900, "bonaire"),          # Brandaris
    (50.8335, 5.6830, "netherlands"),        # the ENCI quarry
    (12.10, -68.90, "europe"),               # nl outside every box
    (18.04, -63.06, "europe"),               # Sint Maarten: nl at Nominatim's zoom 3 (NL-SX), in no box
])
def test_chosen_by_box(monkeypatch, tmp_path, lat, lon, expected):
    """Caribbean Netherlands is country nl to Nominatim: each island's source by its box, the European part by its
    own, anything else of nl the global source."""
    monkeypatch.setattr(choose, "country_code", lambda *_: "nl")
    source, _ = choose.choose_source("auto", lat, lon, str(tmp_path))
    assert source.id == expected


def test_offline_boxes():
    """Without a lookup, the islands' boxes and the European box give nl; the Faroes fo."""
    for code, (s, n, w, e) in [("nl", netherlands.NL_BOX), ("fo", faroe.FO_BOX)] + [
            ("nl", src.SOURCES[sid].bbox) for sid in ISLANDS]:
        lat, lon = (s + n) / 2, (w + e) / 2
        assert any(c == code and bs <= lat <= bn and bw <= lon <= be
                   for c, (bs, bn, bw, be) in choose.OFFLINE_BOXES)


def _write(path, crs, left, top, band, res=0.5):
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs=crs, nodata=NODATA, transform=from_origin(left, top, res, res), tiled=True, blockxsize=256,
                  blockysize=256, compress="deflate") as dst:
        dst.write(np.where(np.isnan(band), NODATA, band).astype(np.float32), 1)


@pytest.fixture
def island_files(http_server, tmp_path):
    """Three files like Sint Eustatius' (0.5 m, 256 px tiles, DEFLATE, nodata 3.4e38): one naming only a LOCAL_CS,
    one in the island's CRS, one in another real CRS, served by the local server."""
    left, top = 499000.0, 1938000.0
    band = (np.add.outer(np.arange(2400) * 0.01, np.arange(2400) * 0.02) + 100.0).astype(np.float32)
    band[:100, :300] = np.nan  # "the sea"
    os.makedirs(tmp_path / "files")
    _write(tmp_path / "files" / "local.tif", rio.crs.CRS.from_wkt(LOCAL_CS), left, top, band)
    _write(tmp_path / "files" / "island.tif", "EPSG:10745", left, top, band)
    _write(tmp_path / "files" / "other.tif", "EPSG:32620", left, top, band)
    with rio.open(tmp_path / "files" / "local.tif") as check:
        assert windows._local(check.crs) and check.crs.to_epsg() is None
    http_server.add_folder("/files", str(tmp_path / "files"))
    return band, left, top, (lambda name: http_server.url(f"/files/{name}"))


def _layer(url, force_crs):
    return FileBlocks("AHN test", "test/bq", "EPSG:10745", 0.5, 1000, url,
                      extent=(499000.0, 1936800.0, 500200.0, 1938000.0), year=2023, force_crs=force_crs)


@pytest.mark.parametrize("name, force_crs, read", [
    ("local.tif", True, True),      # the LOCAL_CS taken as the island's CRS
    ("local.tif", False, False),    # without the option: another CRS, never used
    ("island.tif", True, True),     # a file in the island's own CRS: as ever
    ("island.tif", False, True),
    ("other.tif", True, False),     # a real CRS other than the block's: never used, the option or not
    ("other.tif", False, False),
])
def test_forced_crs_block(island_files, tmp_path, name, force_crs, read):
    """A block of a file naming only a LOCAL_CS is read on its own pixels in the layer's CRS when the layer forces
    it (Windows.fetch, one block); without the option, and for a file with another real CRS whatever the option,
    the block fails as a file in another CRS (WrongCrs: never "missing")."""
    band, left, top, url = island_files
    layer = _layer(url(name), force_crs)
    tile = (499, 1937)  # 499 000-500 000 E, 1 937 000-1 938 000 N
    request = layer.index.request(tile)
    path = str(tmp_path / "block.tif")
    if not read:
        with pytest.raises(RuntimeError, match="no file of this block could be read in its CRS"):
            layer.reader.fetch(request, path)
        assert not os.path.exists(path)
        return
    layer.reader.fetch(request, path)
    with rio.open(path) as block:
        values = block.read(1)
        assert block.crs.to_epsg() == 10745 and block.transform.c == left and block.transform.f == top
        assert same_tile(values, band[:2000, :2000])  # the sea's pixels without data


@pytest.mark.parametrize("name, force_crs, read", [
    ("local.tif", True, True), ("local.tif", False, False), ("island.tif", False, True), ("other.tif", True, False)])
def test_forced_crs_group(island_files, name, force_crs, read):
    """The same through read_group (several blocks of one file in one window: Windows.fetch_group)."""
    band, left, top, url = island_files
    layer = _layer(url(name), force_crs)
    requests = [layer.index.request(t) for t in ((499, 1937), (500, 1937))]  # the second over the file's edge
    if not read:
        with pytest.raises(RuntimeError, match="could be read in its CRS"):
            layer.reader.fetch_group(requests)
        return
    (first, tags), (second, _) = layer.reader.fetch_group(requests)
    assert tags["sources"] == name and tags["years"] == "2023"
    assert (first[100:] == band[100:2000, :2000]).all() and np.isnan(first[:100, :300]).all()
    assert (second[:, :400] == band[:2000, 2000:2400]).all() and np.isnan(second[:, 400:]).all()


def test_forced_crs_download(island_files, tmp_path, monkeypatch):
    """A layer forcing its CRS downloads its blocks through Layer.download like any FileBlocks layer."""
    monkeypatch.setattr(src.layer, "DOWNLOAD_THREADS", 1)  # one block at a time (the test server)
    band, left, top, url = island_files
    layer = _layer(url("local.tif"), True)
    grid = gd.make_grid((left + 100, top - 900, left + 1100, top - 100), 1.0, "EPSG:10745")
    cache_dir = str(tmp_path / "cache")
    assert layer.tiles(grid) == [(499, 1937), (500, 1937)]
    layer.download(grid, cache_dir, None, "test")
    assert all(cache.state(cache_dir, layer.tile_path(cache_dir, t)) == "ok" for t in layer.tiles(grid))
    with rio.open(layer.tile_path(cache_dir, (500, 1937))) as block:
        assert block.crs.to_epsg() == 10745 and same_tile(block.read(1)[:, :400], band[:2000, 2000:2400])


def test_island_blocks():
    """Blocks of 1 km of each island's files, named after them; outside a file's extent no request."""
    for sid, name in (("saba", "SABA"), ("sint_eustatius", "STATIA"), ("bonaire", "BONAIRE")):
        s = src.SOURCES[sid]
        lat, lon = s.sample
        (x,), (y,) = transform("EPSG:4326", s.crs, [lon], [lat])
        tile = (int(x // 1000), int(y // 1000))
        for layer, part in ((s.nmt, "02a_DTM_50cm/M_"), (s.nmpt, "03a_DSM_50cm/R_")):
            request = layer.index.request(tile)
            assert len(request.files) == 1 and request.files[0][1].endswith(f"{part}{name}2023.TIF")
            assert request.shape == (2000, 2000) and request.crs == s.crs
            assert layer.index.request((tile[0] + 40, tile[1])).files == []


def test_faroe_blocks():
    """Blocks of 2 km from the file's own corner (its pixel edges off whole metres): Enniberg's block starts on a
    pixel edge of the file and lies inside it; the working grid's edges are the file's too."""
    s = src.SOURCES["faroe_islands"]
    lat, lon = s.sample
    (x,), (y,) = transform("EPSG:4326", s.crs, [lon], [lat])
    ox, oy = faroe.FO_ORIGIN
    tile = (int((x - ox) // 2000), int((y - oy) // 2000))
    request = s.nmt.index.request(tile)
    assert request.files == [("FO_DSM_2015_FOTM_2M.tif", faroe.FO_DSM_URL, 2015)]
    col = (request.transform.c - faroe.FO_LEFT) / 2.0
    row = (faroe.FO_TOP - request.transform.f) / 2.0
    assert abs(col - round(col)) < 1e-6 and abs(row - round(row)) < 1e-6 and request.shape == (1000, 1000)
    grid = gd.make_grid((x - 300, y - 300, x + 300, y + 300), 2.0, s.crs, s.grid_origin)
    assert abs((grid.left - faroe.FO_LEFT) / 2 - round((grid.left - faroe.FO_LEFT) / 2)) < 1e-6
    assert s.nmt.index.request((tile[0] + 100, tile[1])).files == []  # east of the file


def test_wcs_requests():
    """GetCoverage of a 1 km tile on the WCS's own 0.5 m pixels (no SCALESIZE), x/y axes, a TIFF."""
    reader = src.SOURCES["netherlands"].nmt.reader
    params = dict((k, v) for k, v in reader.coverage_params(175000, 315000, 176000, 316000, 0.5) if k != "SUBSET")
    subsets = [v for k, v in reader.coverage_params(175000, 315000, 176000, 316000, 0.5) if k == "SUBSET"]
    assert params["COVERAGEID"] == "dtm_05m" and params["FORMAT"] == "image/tiff" and "SCALESIZE" not in params
    assert subsets == ["x(175000.000,176000.000)", "y(315000.000,316000.000)"]
