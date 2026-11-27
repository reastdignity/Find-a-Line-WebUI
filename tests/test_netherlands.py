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
    # Lower Saxony has six already (countcube.PARTNERS); Wallonia (2026-11-23) last
    assert nl.neighbours == ("north_rhine_westphalia", "wallonia")
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
    for host, slots in (("service.pdok.nl", 4), ("basisdata.nl", 1), ("cdn.foroyakort.fo", 2)):
        assert src.net.HOST_SLOTS_OF[host] == slots
    # basisdata.nl (blocked a development network's address on 2026-11-15): one connection, 54 requests a minute,
    # every one in its turn: the islands' layers read through our own ranges (the user's decision of 2026-11-24)
    assert _declared_rates()["basisdata.nl"] == 54
    for sid in ISLANDS:
        for layer in (src.SOURCES[sid].nmt, src.SOURCES[sid].nmpt):
            assert layer.reader.ranged and layer.reader.force_crs and src.net.single_connection(layer.tile_url(
                layer.tiles(gd.Grid(left=layer.index.extent[0], top=layer.index.extent[3], res=2.0, height=10,
                                    width=10, crs=layer.crs))[0]))


def _declared_rates():
    """net.HOST_RATES_OF as sources/net.py declares it (conftest.py empties it for this module)."""
    import ast
    with open(src.net.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.AnnAssign)
                and getattr(node.target, "id", None) == "HOST_RATES_OF")


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
    """Without a lookup, the islands' boxes give nl; the Faroes fo."""
    for code, (s, n, w, e) in [("fo", faroe.FO_BOX)] + [("nl", src.SOURCES[sid].bbox) for sid in ISLANDS]:
        lat, lon = (s + n) / 2, (w + e) / 2
        assert any(c == code and bs <= lat <= bn and bw <= lon <= be
                   for c, (bs, bn, bw, be) in choose.OFFLINE_BOXES)


@pytest.mark.parametrize("lat, lon, expected", [
    (51.44, 3.57, "nl"),    # Vlissingen
    (51.31, 3.39, "nl"),    # Sluis (Zeeuws-Vlaanderen)
    (51.28, 4.05, "nl"),    # Hulst
    (51.44, 5.48, "nl"),    # Eindhoven
    (51.25, 5.71, "nl"),    # Weert
    (50.85, 5.69, "nl"),    # Maastricht
    (53.22, 6.57, "nl"),    # Groningen
    (50.85, 4.35, None),    # Brussels
    (51.22, 4.40, None),    # Antwerp
    (51.05, 3.72, None),    # Ghent
    (50.63, 5.57, "be"),    # Liège: Wallonia's box (2026-11-23)
    (51.21, 3.22, None),    # Bruges
    (51.32, 4.95, None),    # Turnhout
    (51.10, 5.79, None),    # Maaseik
    (51.84, 5.86, "nl"),    # Nijmegen
    (51.98, 5.91, "nl"),    # Arnhem
    (52.22, 6.89, "nl"),    # Enschede
    (51.37, 6.17, "nl"),    # Venlo
    (51.19, 5.99, "nl"),    # Roermond
    (51.00, 5.87, "nl"),    # Sittard
    (50.89, 5.98, "nl"),    # Heerlen
    (50.771, 6.015, "nl"),  # Vaals (its west; the border runs through the town's east)
    (53.17, 7.03, "nl"),    # Winschoten
    (50.776, 6.083, "de"),  # Aachen
    (51.79, 6.14, "de"),    # Kleve
    (51.83, 6.25, "de"),    # Emmerich
    (52.21, 7.02, "de"),    # Gronau
    (52.43, 7.07, "de"),    # Nordhorn
    (53.37, 7.21, "de"),    # Emden
    (51.19, 6.44, "de"),    # Mönchengladbach
    (51.03, 5.90, "de"),    # Selfkant (Germany's westernmost bulge, between Sittard and Belgium)
])
def test_offline_boxes_along_the_borders(monkeypatch, tmp_path, lat, lon, expected):
    """Offline (or with a user's Nominatim quota used up) a centre in Belgium, which has no source, never gets the
    Netherlands' boxes, nor one in Germany (its Land's boxes come after the Netherlands'); the Dutch land does,
    Zeeuws-Vlaanderen, the east and South Limburg included."""
    def offline(*args, **kwargs):
        raise ValueError("offline")
    monkeypatch.setattr(choose.osm, "reverse", offline)
    assert choose.country_code(lat, lon, str(tmp_path)) == expected


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


@pytest.mark.parametrize("force_crs, ok", [(True, True), (False, False)])
def test_probe_window_forced_crs(tmp_path, force_crs, ok):
    """The probe's window read (sources/probe.py _window) takes a LOCAL_CS file in the layer's CRS when the layer
    forces it, and calls it a file in another CRS when it does not (a local file: no request)."""
    from sources import probe
    band = np.full((2400, 2400), 250.0, np.float32)
    band[:8, :] = np.nan  # the window's first rows without data: a share, not all
    path = tmp_path / "local.tif"
    _write(path, rio.crs.CRS.from_wkt(LOCAL_CS), 499000.0, 1938000.0, band)
    layer = _layer(str(path), force_crs)
    if ok:
        text = probe._window(str(tmp_path / "cache"), layer, (499, 1937))
        assert text.startswith("window ") and text.endswith("% with data") and not text.startswith("window 100%")
    else:
        with pytest.raises(RuntimeError, match="is in .*not EPSG:10745"):
            probe._window(str(tmp_path / "cache"), layer, (499, 1937))


def test_check_source_reads_a_local_cs_file(tmp_path):
    """tools/check_source.py compares cached blocks with their files through a WarpedVRT in the block's CRS: a file
    naming only a LOCAL_CS is read as if in that CRS (src_crs), its pixels as they are."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    band = (np.add.outer(np.arange(400) * 0.5, np.arange(400) * 0.25) + 10.0).astype(np.float32)
    band[:20, :30] = np.nan
    path = tmp_path / "local.tif"
    _write(path, rio.crs.CRS.from_wkt(LOCAL_CS), 499000.0, 1938000.0, band)
    profile = {"crs": rio.crs.CRS.from_epsg(10745), "transform": from_origin(499050.0, 1937990.0, 0.5, 0.5),
               "width": 200, "height": 300}
    values = cs._read_source(str(path), profile)
    expected = band[20:320, 100:300]
    assert values.shape == (300, 200)
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[~np.isnan(values)], expected[~np.isnan(expected)])


@pytest.fixture
def islands_like(http_server, tmp_path):
    """A file made like the islands' (float32, 0.5 m, 256 px tiles, DEFLATE, overviews, nodata 3.4e38, only a
    LOCAL_CS, forced to Sint Eustatius' CRS), its tiles about as big as lidar's (centimetres of noise), on the
    server; its layer through our ranges or GDAL's (layer(where, ranged))."""
    left, top = 499000.0, 1938000.0
    band = (np.add.outer(np.arange(2600) * 0.013, np.arange(2700) * 0.021) + 100.0).astype(np.float32)
    band += np.sin(np.arange(2700) / 9.0).astype(np.float32)
    band += np.random.default_rng(1).normal(0, 0.03, band.shape).astype(np.float32)
    band[:150, :400] = np.nan  # "the sea"
    path = tmp_path / "M_STATIA2023.TIF"
    _write(path, rio.crs.CRS.from_wkt(LOCAL_CS), left, top, band)
    with rio.open(path, "r+") as dst:
        dst.build_overviews([2, 4, 8])
    http_server.add("/bq/M_STATIA2023.TIF", path.read_bytes(), "image/tiff")

    def layer(where, ranged):
        return FileBlocks("AHN test", "test/bq", "EPSG:10745", 0.5, 1000, where,
                          extent=(left, top - 1300.0, left + 1350.0, top), year=2023, force_crs=True, ranged=ranged)
    return http_server.url("/bq/M_STATIA2023.TIF"), path, layer


BQ_BLOCKS = ((499, 1937), (500, 1937), (499, 1936), (500, 1936))


def test_ranged_blocks_as_gdal_reads_them(islands_like, http_server, tmp_path, monkeypatch):
    """The islands-like file gives the same blocks through our own ranges in strips (windows._ranged_values, since
    2026-11-24), through our own ranges as GDAL reads a window (the reader before it), through GDAL's /vsicurl/ and
    as a local read: a block on the file's tiles over its sea (no data), one off them (2000 px is not a multiple of
    256) at the file's east edge, one at its south edge, one at its corner. The strips ask a request per run of
    tiles: at most the open, 2 runs per strip of 512 rows and one plain read a block, never more than before, and
    for the whole block under half of what GDAL's plain reads of 64 KB asked (10 against 44)."""
    from sources.readers import windows
    url, path, layer = islands_like
    strips = windows._ranged_values
    blocks, asked = {}, {}
    for name, where, ranged in (("ranged", url, True), ("before", url, True), ("gdal", url, False),
                                ("local", str(path), False)):
        monkeypatch.setattr(windows, "_ranged_values", strips if name != "before" else (
            lambda src, file, crs, transform, shape, warp=None: windows._values_on(src, crs, transform, shape, warp)))
        found = layer(where, ranged)
        for tile in BQ_BLOCKS:
            out = str(tmp_path / f"{name}-{tile[0]}-{tile[1]}.tif")
            before = len(http_server.requests("/bq/"))
            found.reader.fetch(found.index.request(tile), out)
            asked[name, tile] = len(http_server.requests("/bq/")) - before
            with rio.open(out) as block:
                blocks[name, tile] = block.read(1), block.tags(), block.transform, block.crs
    for (name, tile), (values, tags, transform, crs) in blocks.items():
        values0, tags0, transform0, crs0 = blocks["local", tile]
        assert np.array_equal(values, values0, equal_nan=True), (name, tile)
        assert (transform, crs) == (transform0, crs0) and (name == "local" or tags == blocks["gdal", tile][1])
    assert np.isnan(blocks["ranged", (499, 1937)][0][:150, :400]).all()
    counts = {k: v for k, v in asked.items() if k[0] in ("ranged", "before")}
    for tile in BQ_BLOCKS:  # the smaller windows at the edges GDAL asks in one multi-range call either way
        assert asked["ranged", tile] <= min(1 + 2 * 4 + 1, asked["before", tile]), counts
    assert 2 * asked["ranged", BQ_BLOCKS[0]] < asked["before", BQ_BLOCKS[0]], counts  # the whole 2000 x 2000 px


def test_ranged_block_failures(islands_like, http_server, tmp_path, monkeypatch):
    """Through the strips: every request takes its turn and is counted (servicecounts), a range that never comes
    whole fails the block (never a block of what came, nothing written), and a connection lost in the middle comes
    out as net.Unreachable with its own message."""
    from sources import net
    from sources.readers import ranges
    url, path, layer = islands_like
    turns, counted = [], []
    monkeypatch.setattr(net, "rate_turn", lambda u, share=1.0: turns.append(u))
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    count = ranges.servicecounts.request
    monkeypatch.setattr(ranges.servicecounts, "request", lambda u: (counted.append(u), count(u))[1])
    found = layer(url, True)
    request = found.index.request((499, 1937))
    before = len(http_server.requests("/bq/"))
    found.reader.fetch(request, str(tmp_path / "block.tif"))
    sent = len(http_server.requests("/bq/")) - before
    assert turns == counted == [url] * sent and sent > 1
    http_server.add("/cut/M_STATIA2023.TIF", path.read_bytes(), "image/tiff")
    http_server.fault("/cut/M_STATIA2023.TIF", "truncate", lambda n, r: int(r.split("=")[1].split("-")[0]) > 0)
    cut = layer(http_server.url("/cut/M_STATIA2023.TIF"), True)
    with pytest.raises(RuntimeError, match="completely"):
        cut.reader.fetch(cut.index.request((499, 1937)), str(tmp_path / "cut.tif"))
    assert not os.path.exists(tmp_path / "cut.tif")
    get_range, calls = ranges.get_range, []

    def lost(u, first, last, *args):
        calls.append(first)
        if len(calls) > 1:  # the open's range came, then the host went away
            raise net.unreachable(u, ConnectionRefusedError(10061, "refused"))
        return get_range(u, first, last, *args)
    monkeypatch.setattr(ranges, "get_range", lost)
    with pytest.raises(net.Unreachable, match=r"^127\.0\.0\.1 could not be connected to \(refused or no route\)$"):
        found.reader.fetch(request, str(tmp_path / "lost.tif"))
    assert not os.path.exists(tmp_path / "lost.tif")


def test_one_connection_hosts_are_read_by_our_own_ranges():
    """No layer of the catalogue reads a host of one connection (net.single_connection) through GDAL's /vsicurl/
    windows: GDAL keeps an idle connection per download thread (the code review of 2026-11-23), so such a host must
    be read through our own ranges (Windows(ranged=True)), one session of one connection. The layers' file
    addresses are taken at their source's sample point, offline (a FileBlocks' fixed files), and from every
    address in the layer's attributes."""
    import re
    from sources.readers.windows import Windows

    def addresses(obj, depth=0):
        found = []
        for value in (vars(obj).values() if hasattr(obj, "__dict__") and depth < 3 else ()):
            if isinstance(value, str) and re.match(r"https?://", value):
                found.append(value)
            elif hasattr(value, "__dict__") and not callable(value):
                found += addresses(value, depth + 1)
        return found
    checked = 0
    for source in src.SOURCES.values():
        for layer in (source.nmt, source.nmpt):
            reader = getattr(layer, "reader", None)
            if not isinstance(reader, Windows) or reader.ranged:
                continue
            urls = addresses(layer)
            if isinstance(layer, FileBlocks) and source.sample:
                (x,), (y,) = transform("EPSG:4326", layer.crs, [source.sample[1]], [source.sample[0]])
                res = layer.native_res
                tiles = layer.tiles(gd.Grid(left=x, top=y, res=res, height=4, width=4, crs=layer.crs))
                urls += [url for tile in tiles[:1] for _, url, _ in layer.index.request(tile).files]
            assert not any(src.net.single_connection(url) for url in urls), (source.id, layer.description)
            checked += 1
    assert checked > 10
