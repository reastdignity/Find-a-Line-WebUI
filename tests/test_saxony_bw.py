"""Saxony (GeoSN) and Baden-Württemberg (LGL): zipped 2 km tiles on a fixed grid (ZippedTiles), read by
SheetFile with members (GeoTIFF, XYZ with spaces, several per ZIP), and MetricTiling's origin."""

import io
import os
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
from tile_values import TILE_EPS, same_tile  # noqa: E402
from grid import Grid  # noqa: E402
from sources import net  # noqa: E402
from sources.indexes.tilings import MetricTiling  # noqa: E402
from sources.layers.zipped import ZippedTiles  # noqa: E402
from sources.readers.sheetfile import SheetFile  # noqa: E402

DGM_MEMBERS = r"^dgm1_32_\d+_\d+_1_bw_\d{4}\.xyz$"


# The tiling

def test_metric_tiling_origin():
    """Tiles from an origin: LGL's 2 km tiles start at odd kilometres east; (0, 0) gives the tiles of before
    (Slovakia's), and a grid on a tile's edge takes the tile on each side only where it reaches into it."""
    plain, odd = MetricTiling("EPSG:25832", "f", 2000), MetricTiling("EPSG:25832", "f", 2000, origin=(1000.0, 0.0))
    grid = Grid(left=497100.0, top=5323900.0, res=1.0, height=1000, width=2400, crs="EPSG:25832")
    assert plain.tiles(grid) == [(248, 2661), (249, 2661)]  # 496-498, 498-500 km
    assert odd.tiles(grid) == [(248, 2661), (249, 2661)]    # 497-499, 499-501 km
    assert odd.edges((248, 2661)) == (497000.0, 5322000.0, 499000.0, 5324000.0)
    assert plain.edges((248, 2661)) == (496000.0, 5322000.0, 498000.0, 5324000.0)
    inside = Grid(left=497100.0, top=5323900.0, res=1.0, height=100, width=100, crs="EPSG:25832")
    assert odd.tiles(inside) == [(248, 2661)] and plain.tiles(inside) == [(248, 2661)]
    west, south, east, north = odd.bounds_wgs84((248, 2661))
    assert 8.95 < west < east < 9.0 and 48.03 < south < north < 48.07


@pytest.mark.parametrize("sid, lat, lon, tile, names", [
    ("saxony", 50.920, 14.210, (222, 2820), ("dgm1_33444_5640_2_sn_tiff.zip", "dom1_33444_5640_2_sn_tiff.zip")),
    ("baden_wurttemberg", 48.053, 8.971, (248, 2661), ("dgm1_32_497_5322_2_bw.zip", "dom1_32_497_5322_2_bw.zip")),
])
def test_tile_names(sid, lat, lon, tile, names):
    """The ZIP of the tile holding a point: its name from the south-west corner in km (Saxony's E with the
    zone's 33, LGL's E odd), the GeoSN shares and LGL's folders; cached as grid_tile_name, read back."""
    from rasterio.warp import transform
    source = src.SOURCES[sid]
    xs, ys = transform("EPSG:4326", source.crs, [lon], [lat])
    grid = Grid(left=xs[0] - 50, top=ys[0] + 50, res=1.0, height=100, width=100, crs=source.crs)
    for layer, name in zip((source.nmt, source.nmpt), names):
        assert layer.tiles(grid) == [tile]
        url = layer.tile_url(tile)
        assert url.rsplit("/", 1)[-1] == name
        path = f"{layer.folder}/{tile[0] // 10}_{tile[1] // 10}/{tile[0]}_{tile[1]}.tif"
        assert layer.tile_of(path) == tile
        assert layer.tile_of(f"{layer.folder}/0_0/{tile[0]}_{tile[1]}.tif") is None
        assert layer.tile_of("elsewhere/" + path) is None
    assert source.nmt.tile_url(tile).startswith(("https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/"
                                                 "JCcXyifaNdLDnxZ/", "https://opengeodata.lgl-bw.de/data/dgm/"))
    assert source.nmpt.tile_url(tile).startswith(("https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/"
                                                  "S6wwnFwX7882sZm/", "https://opengeodata.lgl-bw.de/data/dom1/"))


# The reader: ZIPs made here in the shape of the real ones (2026-11-02), small

def _heights(left: int, top: int, size: int, seed: int) -> np.ndarray:
    """Centimetre heights of a size x size block (float32, as the files store them)."""
    rng = np.random.default_rng(seed)
    return (np.round(rng.uniform(300, 900, (size, size)), 2)).astype(np.float32)


def _xyz(left: int, top: int, z: np.ndarray, newline: str = "\r\n") -> bytes:
    """LGL's XYZ: "x y z" with one space, two decimals, centres on x.5, rows from the north, x ascending."""
    lines = [f"{left + c + 0.5:.2f} {top - r - 0.5:.2f} {z[r, c]:.2f}"
             for r in range(z.shape[0]) for c in range(z.shape[1])]
    return (newline.join(lines) + newline).encode()


def _geotiff(left: float, top: float, z: np.ndarray, crs=None, nodata=-9999.0) -> bytes:
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=z.shape[1], height=z.shape[0], count=1, dtype="float32",
                          crs=crs, transform=from_origin(left, top, 1.0, 1.0), nodata=nodata, compress="lzw") as dst:
            dst.write(z, 1)
        return memfile.read()


def _zip(members) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def _layer(http_server, folder: str, members: str, origin=(1000.0, 0.0), tile_m: float = 20) -> ZippedTiles:
    def url(left: float, bottom: float) -> str:
        return http_server.url(f"/data/t_{left:.0f}_{bottom:.0f}.zip")
    return ZippedTiles("test model", folder, "EPSG:25832", tile_m, 1.0, url, members, origin=origin)


def _read(path):
    with rio.open(path) as ds:
        return ds.read(1), ds.transform, ds.crs


def test_xyz_members_merged(http_server, tmp_path):
    """LGL's DGM1: four XYZ members of a quarter each (names with a year, one year differing), the CSVs,
    licence and metadata text left out, merged into the tile on its pixels."""
    size = 10  # members of 10 m, a tile of 20 m
    quarters = {(0, 0): 2022, (1, 0): 2022, (0, 1): 2019, (1, 1): 2022}
    whole = np.full((20, 20), np.nan, dtype=np.float32)
    members = [("dgm1_32_1_0_2_bw/GOVDATA-Datenlizenz_Deutschland.pdf", b"%PDF-1.4"),
               ("dgm1_32_1_0_2_bw/Meta-ATKIS_DGM1_ALS2.txt", b"Hoehenbezug: DHHN2016\n")]
    for (qx, qy), year in quarters.items():
        left, top = 1000 + qx * size, 20 - qy * size
        z = _heights(left, top, size, qx * 2 + qy)
        whole[qy * size:(qy + 1) * size, qx * size:(qx + 1) * size] = z
        name = f"dgm1_32_1_0_2_bw/dgm1_32_{left}_{top}_1_bw_{year}"
        members += [(name + ".xyz", _xyz(left, top, z)), (name + ".csv", b"Kachelname;Aktualitaet\nx;2016-04-06\n")]
    http_server.add("/data/t_1000_0.zip", _zip(members), "application/zip")
    layer = _layer(http_server, "bw/dgm1/live", DGM_MEMBERS)
    path = layer.tile_path(str(tmp_path), (0, 0))
    fetched = layer.download_tile((0, 0), path)
    assert fetched.received > 0
    band, transform, crs = _read(path)
    assert transform == from_origin(1000, 20, 1.0, 1.0) and crs.to_epsg() == 25832
    assert same_tile(band, whole)


def test_halves_give_the_same_pixels(http_server, tmp_path):
    """One XYZ member of a block and two members of its halves (one shifted by a pixel inside, a GeoTIFF
    for the other half) give the same tile: the raw pixels are kept wherever they come from."""
    z = _heights(1000, 20, 20, 7)
    http_server.add("/data/t_1000_0.zip", _zip([("a_1_bw_2020.xyz", _xyz(1000, 20, z))]), "application/zip")
    http_server.add("/data/t_1020_0.zip", _zip([("b_1_bw_2020.xyz", _xyz(1020, 20, z[:, :11], "\n")),
                                                ("c_1_bw_2020.tif", _geotiff(1031, 20, z[:, 11:]))]),
                    "application/zip")
    one = _layer(http_server, "one", r"_1_bw_\d{4}\.(xyz|tif)$")
    two = _layer(http_server, "two", r"_1_bw_\d{4}\.(xyz|tif)$")
    for layer, tile in ((one, (0, 0)), (two, (1, 0))):
        layer.download_tile(tile, layer.tile_path(str(tmp_path), tile))
    a, ta, _ = _read(one.tile_path(str(tmp_path), (0, 0)))
    b, tb, _ = _read(two.tile_path(str(tmp_path), (1, 0)))
    assert same_tile(a, z) and same_tile(b, z)
    assert (ta.c, tb.c) == (1000, 1020) and ta.f == tb.f == 20


def test_geotiff_member_crs_forced_and_nodata(http_server, tmp_path):
    """A GeoTIFF member (GeoSN: one per ZIP with its .tfw, .aux.xml and a date CSV) with -9999 outside the
    Land: NaN in the tile, the tile in the layer's CRS whatever the member names (LGL's DOM1: a compound
    CRS with DHHN2016; none at all here)."""
    z = _heights(0, 20, 20, 3)
    z[:, :5] = -9999.0
    members = [("dgm1_33444_5640_2_sn.tif", _geotiff(20, 20, z, crs=None)),
               ("dgm1_33444_5640_2_sn.tfw", b"1\n0\n0\n-1\n20.5\n19.5\n"),
               ("dgm1_33444_5640_2_sn.tif.aux.xml", b"<PAMDataset/>"),
               ("dgm1_33444_5640_2_sn_akt.csv", b"Kachelname;Ausdehnung;Aktualitaet\n")]
    http_server.add("/data/t_20_0.zip", _zip(members), "application/zip")
    layer = _layer(http_server, "sn", r"^dgm1_33\d+_\d+_2_sn\.tif$", origin=(0.0, 0.0))
    path = layer.tile_path(str(tmp_path), (1, 0))
    layer.download_tile((1, 0), path)
    band, transform, crs = _read(path)
    assert crs.to_epsg() == 25832 and transform == from_origin(20, 20, 1.0, 1.0)
    assert np.isnan(band[:, :5]).all() and same_tile(band[:, 5:], z[:, 5:])


def test_missing_and_errors(http_server, tmp_path, monkeypatch):
    """A tile the server does not have (404) is missing, no file; what is not a ZIP of the expected members
    (an HTML page with status 200, a ZIP without them, one over the byte caps) is an error, never data."""
    monkeypatch.setattr(net, "_sleep", lambda attempt: None)
    layer = _layer(http_server, "e", r"\.xyz$")
    path = layer.tile_path(str(tmp_path), (0, 0))
    fetched = layer.download_tile((0, 0), path)
    assert fetched.received == 0 and not os.path.exists(path)
    http_server.add("/data/t_1000_0.zip", b"<html>Wartungsarbeiten</html>", "text/html")
    with pytest.raises(RuntimeError, match="not a ZIP"):
        layer.download_tile((0, 0), path)
    http_server.add("/data/t_1000_0.zip", _zip([("readme.txt", b"x")]), "application/zip")
    with pytest.raises(RuntimeError, match="no member"):
        layer.download_tile((0, 0), path)
    big = _zip([("a.xyz", b"0" * 5000)])
    http_server.add("/data/t_1000_0.zip", big, "application/zip")
    layer.reader.member_bytes = 4000
    with pytest.raises(RuntimeError, match="unpacked"):
        layer.download_tile((0, 0), path)
    layer.reader.max_bytes = len(big) - 1
    with pytest.raises(RuntimeError, match="more than"):
        layer.download_tile((0, 0), path)
    assert not os.path.exists(path)


def test_members_on_other_pixels_refused(http_server, tmp_path):
    """Members that do not share the tile's pixels (half a metre apart, or of another size) are refused,
    never resampled."""
    z = _heights(0, 0, 4, 1)
    http_server.add("/data/t_1000_0.zip", _zip([("a.tif", _geotiff(1000, 20, z)), ("b.tif", _geotiff(1004.5, 20, z))]),
                    "application/zip")
    layer = _layer(http_server, "p", r"\.tif$")
    with pytest.raises(RuntimeError, match="same pixels"):
        layer.download_tile((0, 0), layer.tile_path(str(tmp_path), (0, 0)))


def test_without_members_as_before(tmp_path, monkeypatch):
    """Without members SheetFile reads as for Poland's sheets: the first .asc/.xyz/.txt (or nested .zip)
    member, whatever else the ZIP holds."""
    z = _heights(0, 0, 3, 5)

    class Response:
        def __init__(self, content):
            self.content, self.url, self.headers = content, "https://example/s.zip", {}
    inner = _zip([("s.txt", _xyz(100, 30, z, "\n"))])
    monkeypatch.setattr(net, "_get", lambda url, **kw: Response(_zip([("s.zip", inner)])))
    sheet = src.Sheet(year=2020, name="s", godlo="s", url="https://example/s.zip", crs="EPSG:2180", res=1.0)
    path = str(tmp_path / "s.tif")
    SheetFile("test").fetch(sheet, path)
    band, transform, crs = _read(path)
    assert np.array_equal(band, z) and transform == from_origin(100, 30, 1.0, 1.0) and crs.to_epsg() == 2180


def test_check_source_reads_the_members(http_server, tmp_path):
    """tools/check_source.py compares a ZippedTiles tile with its ZIP's members read by GDAL (the XYZ
    and GeoTIFF drivers, not SheetFile's parser), merged on the tile's pixels: equal to the last bit."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import check_source as cs
    z = _heights(1000, 20, 20, 11)
    http_server.add("/data/t_1000_0.zip", _zip([("a_1_bw_2020.xyz", _xyz(1000, 20, z[:, :10])),
                                                ("b_1_bw_2021.tif", _geotiff(1010, 20, z[:, 10:])),
                                                ("Meta.txt", b"x")]), "application/zip")
    layer = _layer(http_server, "c", r"_1_bw_\d{4}\.(xyz|tif)$")
    path = layer.tile_path(str(tmp_path), (0, 0))
    layer.download_tile((0, 0), path)
    with rio.open(path) as ds:
        profile = {"crs": ds.crs, "transform": ds.transform, "width": ds.width, "height": ds.height}
    assert cs._sources_of(layer, (0, 0)) == [layer.tile_url((0, 0))]
    assert np.array_equal(cs._read_zip(layer, layer.tile_url((0, 0)), profile), z)
