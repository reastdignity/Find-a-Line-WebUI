"""The Forestry Agency's tiled DEM files (sources/catalogue/japan_forest.py, tools/forest_files.py): the quarters of
the 1/50000 sheets, the shipped table and its data masks, the tool that makes it, the files of a block, has_data_near,
a recorded window read through the catalogue's own layer from a host that answers only the asked ranges, and the
source `mie`.

Recorded (tests/data/recorded/forest/, 2026-11-27): dem_06ne4_2025_pieces.zip, pieces of Kitaise's dem_06ne4_2025.tif
(380 489 100 bytes) byte for byte: its first 64 KB (the header with every tile's offset and byte count) and the nine
tiles under the 500 m block x 33 500-34 000, y -118 000..-117 500 (two hold data, 13 569 and 4 588 bytes, their valid
pixels outside the block; the others are empty); kitaise_081_rows.json, five resources of the record's package_show
answer as served."""

import json
import math
import os
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio
from affine import Affine
from rasterio.transform import from_origin
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.catalogue import japan_forest as jf  # noqa: E402
from sources.readers.windows import BlockRequest, _coincide  # noqa: E402

RECORDED = os.path.join(HERE, "data", "recorded", "forest")
NE4_KEY = "ckan/resources/0ef7dcca-5f70-4090-a037-be6974385c14/dem_06ne4_2025.tif"
BLOCK = (67, -236)  # x 33 500-34 000, y -118 000..-117 500 (the recorded tiles)
LM = "Fri, 02 Oct 2026 07:41:47 GMT"  # a Last-Modified date of a written file's row


def _pieces():
    """The recorded pieces of 06NE4: {first byte: bytes}, and the file's size."""
    with zipfile.ZipFile(os.path.join(RECORDED, "dem_06ne4_2025_pieces.zip")) as z:
        pieces = {int(n): z.read(n) for n in z.namelist() if n != "size"}
        return pieces, int(z.read("size"))


def _head():
    pieces, size = _pieces()
    return pieces[0], size


def _decode_window(pieces, left, top, shape=(1000, 1000)):
    """A window of the recorded file decoded by hand from its pieces (forest_files.decode_tile), NaN for no data: what
    the layer must give."""
    import forest_files
    with rio.io.MemoryFile(pieces[0]) as mem, mem.open() as f:
        t = f.transform
        th, tw = f.block_shapes[0]
        c1, r1 = round((left - t.c) / t.a), round((top - t.f) / t.e)
        h, w = shape
        out = np.full(shape, np.nan, dtype=np.float32)
        for y in range(r1 // th, (r1 + h - 1) // th + 1):
            for x in range(c1 // tw, (c1 + w - 1) // tw + 1):
                offset = int(f.get_tag_item(f"BLOCK_OFFSET_{x}_{y}", "TIFF", bidx=1))
                tile = forest_files.decode_tile(pieces[offset], (th, tw), (th, tw), 2, True).astype(np.float32)
                tile[tile == -9999] = np.nan
                ra, rb = max(y * th, r1), min((y + 1) * th, r1 + h)
                ca, cb = max(x * tw, c1), min((x + 1) * tw, c1 + w)
                out[ra - r1:rb - r1, ca - c1:cb - c1] = tile[ra - y * th:rb - y * th, ca - x * tw:cb - x * tw]
    return out


class _Size(bytes):
    """A body of no bytes whose length is the file's: a HEAD's Content-Length (the server never writes it)."""

    def __new__(cls, n):
        obj = super().__new__(cls, b"")
        obj.n = n
        return obj

    def __len__(self):
        return self.n


def _serve_pieces(http_server, path, pieces, size):
    """The file at path answered range by range from the recorded pieces (zeros between them), never whole: a GET
    without a Range is refused (400). Returns the list of asked ranges."""
    asked = []

    def answer(request):
        if request.method == "HEAD":
            return Answer(200, _Size(size), {"Accept-Ranges": "bytes"})
        spec = request.headers.get("range", "")
        if not spec.startswith("bytes=") or "," in spec:
            return Answer(400, b"one range only", {"Content-Type": "text/plain"})
        first, last = spec[6:].split("-")
        first, last = int(first), min(int(last), size - 1)
        asked.append((first, last))
        body = bytearray(last - first + 1)
        for start, data in pieces.items():
            a, b = max(first, start), min(last + 1, start + len(data))
            if a < b:
                body[a - first:b - first] = data[a - start:b - start]
        return Answer(206, bytes(body), {"Content-Range": f"bytes {first}-{last}/{size}"})
    http_server.route(path, answer)
    return asked


# --- the quarters ----------------------------------------------------------------------------------------------------
def test_quarter_code_and_box_against_the_files_tie_point():
    """A point's quarter and a quarter's box both ways: 06NE4 (zone VI) is x 20 000-40 000, y -120 000..-105 000, the
    recorded file's own tie point its north-west corner (with the file's float noise); Gozaisho (R100) lies in it; the
    four quarters of sheet NE in their order (1 north-west .. 4 south-east)."""
    assert jf.rf_box("06NE4") == (6, 20_000, -120_000, 40_000, -105_000)
    head, _ = _head()
    with rio.io.MemoryFile(head) as mem, mem.open() as f:
        t = f.transform
        assert f.crs.to_epsg() == 6674
    assert abs(t.c - 20_000) < 1e-6 and abs(t.f - -105_000) < 1e-6
    assert jf.rf_quarter(6, t.c + 1, t.f - 1) == "06NE4"
    assert jf.rf_quarter(6, 39_066.4, -108_447.7) == "06NE4"  # Gozaisho's Fujiuchi wall
    for code, (x, y) in (("06NE1", (1, -90_001)), ("06NE2", (20_001, -90_001)), ("06NE3", (1, -105_001)),
                         ("06NE4", (39_999, -119_999))):
        assert jf.rf_quarter(6, x, y) == code
        zone, left, bottom, right, top = jf.rf_box(code)
        assert left <= x < right and bottom < y <= top
    assert jf.rf_quarter(6, -170_000, 0) is None
    for bad in ("06NE5", "6NE4", "06NI4"):
        with pytest.raises(ValueError):
            jf.rf_box(bad)


# --- the shipped table -----------------------------------------------------------------------------------------------
def test_shipped_table():
    """Kitaise's 13 files (tools/forest_files.py, 2026-11-27): EPSG:6674 by their tags (the record says 6675), 0.5 m,
    tiled 512 x 512, each on its quarter, masks of one cell per tile; 06NE4 with 817 tiles of data of 4 661; nothing of
    another record."""
    rows = [r for r in jf.rf_table() if r.record == "kitaise"]
    assert sorted(r.code for r in rows) == ["06ME4", "06MF3", "06NE2", "06NE4", "06NF1", "06NF3", "06OE2", "06OE4",
                                            "06OF1", "06PE1", "06PE2", "06PE3", "06PE4"]
    assert {r.epsg for r in rows} == {6674}
    assert sum(r.size for r in rows) == 4_949_405_915
    for r in rows:
        zone, left, bottom, right, top = jf.rf_box(r.code)
        assert abs(r.a - 0.5) < 1e-9 and abs(r.e + 0.5) < 1e-9 and (r.tile_w, r.tile_h) == (512, 512)
        assert left - 1e-6 <= r.c and r.c + r.width * r.a <= right + 0.5 + 1e-6
        assert bottom - 0.5 - 1e-6 <= r.f + r.height * r.e and r.f <= top + 1e-6
        assert r.mask.shape == (-(-r.height // 512), -(-r.width // 512))
        assert r.key.endswith(f"dem_{r.code.lower()}_2025.tif") and r.edition == 2025
        assert r.on_pixels  # every block of every file of a built source reads the file's own pixels
        for x, y in ((r.c, r.f), (r.c + r.width * r.a - 1e-3, r.f + r.height * r.e + 1e-3)):  # first, far corner
            block = Affine(0.5, 0, math.floor(x / 500) * 500, 0, -0.5, math.ceil(y / 500) * 500)
            assert _coincide(SimpleNamespace(transform=Affine(r.a, 0, r.c, 0, r.e, r.f)), block) is not None
    ne4 = next(r for r in rows if r.code == "06NE4")
    assert ne4.key == NE4_KEY and int(ne4.mask.sum()) == 817 and ne4.etag == "adc10fbd648aefa05e690b293d7e71be-46"
    assert ne4.mask[22, 71] and not ne4.mask[23, 71]  # 45 valid pixels (1 877 bytes) beside an empty tile (1 626)


STRIPS = {"10NB1": 5, "10NC4": 20, "10PB3": 15, "03QE1": 28, "03QE3": 13, "03QG2": 30, "05MB4": 1}  # cells with data


def test_shipped_table_of_stage_two():
    """The records of stage 2 in the table (tools/forest_files.py, 2026-11-28, the mask read from the files): Shonai
    17 files in zone X, Inadani 23 in zone VIII (40 000 x 30 000 px), Noto's r6 21 in zone VII and 11 in zone VIII;
    each CRS from the tags, every file on the blocks' pixels, nothing of Aichi, Oita or Tokushima; the sources take
    their zone's files only. h30 (the July 2018 rains): 24 files in zone III and 41 in zone V, no file in both zones.
    The seven strip files (Shonai's 10NB1, 10NC4, 10PB3; h30's 03QE1, 03QE3, 03QG2, one-row Deflate, and 05MB4,
    uncompressed) read whole (--strips, 36.6 MB) and masked on cells of 512 px: 112 cells with data where the strip
    rule had marked 15 292 strips, 62 blocks of 500 m meeting data where it had marked 435."""
    rows = jf.rf_table()
    by = {rec: [r for r in rows if r.record == rec] for rec in ("syounai", "inatani", "r6", "h30")}
    assert {r.record for r in rows} == {"kitaise", "syounai", "inatani", "r6", "h30"}
    h3, h5 = jf.rf_rows(("h30",), 3), jf.rf_rows(("h30",), 5)
    assert len(h3) == 24 and len(h5) == 41 and len(by["h30"]) == 65 and not {r.code for r in h3} & {r.code for r in h5}
    strips = {r.code: r for r in rows if r.code in STRIPS}
    assert {code: int(r.mask.sum()) for code, r in strips.items()} == STRIPS
    assert all((r.tile_w, r.tile_h) == (512, 512) and r.mask.shape == (-(-r.height // 512), -(-r.width // 512))
               for r in strips.values())
    assert strips["05MB4"].mask.tolist() == [[True]] and (strips["05MB4"].width, strips["05MB4"].height) == (432, 150)
    assert sum(int(r.mask.sum()) for r in h3 if r.code not in STRIPS) == 47_988
    assert sum(int(r.mask.sum()) for r in h5 if r.code not in STRIPS) == 112_122
    assert len(by["syounai"]) == 17 and {r.epsg for r in by["syounai"]} == {6678}
    assert len(by["inatani"]) == 23 and {r.epsg for r in by["inatani"]} == {6676}
    assert {(r.width, r.height) for r in by["inatani"]} >= {(40_000, 30_000)}
    assert sorted(r.epsg for r in by["r6"]).count(6675) == 21 and len(by["r6"]) == 32
    assert all(r.on_pixels for r in rows) and all(r.mask is not None for r in rows)
    assert all(r.tile_w == r.tile_h == 512 for r in rows)  # no strip file left masked strip by strip
    assert [r.code for r in jf.rf_rows(("r6",), 8)] == sorted(r.code for r in by["r6"] if r.epsg == 6676)
    assert sum(int(r.mask.sum()) for r in by["syounai"] if r.code not in STRIPS) == 18_401


def _row(record, code, mask, size=1000, etag="e"):
    zone, left, bottom, right, top = jf.rf_box(code)
    return {"record": record, "code": code, "key": f"k/{record}/dem_{code.lower()}_2025.tif", "edition": 2025,
            "size": size, "etag": etag, "modified": "m", "epsg": 6668 + zone, "transform": (0.5, -0.5, left, top),
            "width": 40001, "height": 30001, "tile_w": 512, "tile_h": 512, "mask": mask, "on_pixels": True}


def test_a_code_in_two_records_newest_first(tmp_path, monkeypatch):
    """Two records with the same quarter (as h28 and r2 share 02JD4): a block gets both files, the newer record first
    (the records' order), each only where its mask has data; a strip file (no mask) is never used."""
    import forest_files
    full, part = np.ones((59, 79), dtype=bool), np.zeros((59, 79), dtype=bool)
    part[:4, :4] = True  # the north-west 1 x 1 km
    path = str(tmp_path / "t.npz")
    strip = {**_row("c", "06NE4", None), "tile_w": 0, "tile_h": 0}
    forest_files.save(path, [_row("a", "06NE4", part), _row("b", "06NE4", full), strip])
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(path))
    files = jf.rf_files(("b", "a", "c"), 6, {"a": 2016, "b": 2020, "c": 2024})
    corner = (40, -211)  # x 20 000-20 500, y -105 500..-105 000: both masks
    assert [(n, y) for n, _, y in files(*corner)] == [("b_06NE4", 2020), ("a_06NE4", 2016)]
    assert files(*corner)[0][1] == f"{jf.RF_BUCKET}/k/b/dem_06ne4_2025.tif"
    assert [n for n, _, _ in files(60, -230)] == ["b_06NE4"]  # beyond a's data
    files = jf.rf_files(("a", "b"), 6, {"a": 2016, "b": 2020})
    assert [n for n, _, _ in files(*corner)] == ["a_06NE4", "b_06NE4"]


def test_folder_stamp_follows_the_table(tmp_path, monkeypatch):
    """A record's cache folder is stamped with the newest Last-Modified date of its files in the table: a file the
    Agency uploads again in place (a newer date in a table made again) gives the record a new stamp, so its blocks go
    to a new folder; a record without files is an error."""
    import forest_files
    full = np.ones((59, 79), dtype=bool)
    path = str(tmp_path / "t.npz")
    rows = [{**_row("a", "06NE4", full), "modified": "Fri, 02 Oct 2026 07:41:47 GMT"},
            {**_row("a", "06NE2", full), "modified": "Thu, 01 Oct 2026 23:59:59 GMT"}]
    forest_files.save(path, rows)
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(path))
    assert jf.rf_stamp("a") == "20261002"
    rows[1]["modified"] = "Tue, 24 Nov 2026 10:00:00 GMT"  # 06NE2 uploaded again
    forest_files.save(path, rows)
    assert jf.rf_stamp("a") == "20261124"
    with pytest.raises(ValueError, match="b: no file"):
        jf.rf_stamp("b")


def test_rows_of_one_zone_and_off_pixels_refused(tmp_path, monkeypatch):
    """rf_rows takes the files of the source's zone only (a record's file in another zone, numerically on the same
    box, as h30's zones III and V, is never served in this zone's CRS); a file whose blocks would not read its own
    pixels (on_pixels False, Tokushima's) is refused, not resampled in silence."""
    import forest_files
    full = np.ones((59, 79), dtype=bool)
    path = str(tmp_path / "t.npz")
    forest_files.save(path, [_row("a", "06NE4", full), _row("a", "07NE4", full)])
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(path))
    assert [n for n, _, _ in jf.rf_files(("a",), 6, {"a": 2020})(40, -211)] == ["a_06NE4"]
    assert [n for n, _, _ in jf.rf_files(("a",), 7, {"a": 2020})(40, -211)] == ["a_07NE4"]
    forest_files.save(path, [_row("a", "06NE4", full), {**_row("a", "06NE2", full), "on_pixels": False}])
    with pytest.raises(ValueError, match="a 06NE2 would not read the files' own pixels"):
        jf.rf_files(("a",), 6, {"a": 2020})(40, -211)


def test_files_of_a_block():
    """The catalogue's files(i, j): a block inside 06NE4 reads it alone; a block on 06NF3's western edge reads 06NF3
    first and 06NE4 after it (its 40 001st column lies in the block: only for what 06NF3 leaves without data); the
    corner of four quarters lists the four, its own first; outside every file and where the masks are empty, none."""
    files = jf.KS_DTM.index.files
    assert files(78, -217) == [("kitaise_06NE4", f"{jf.RF_BUCKET}/{NE4_KEY}", 2023)]
    assert [n for n, _, _ in files(80, -217)] == ["kitaise_06NF3", "kitaise_06NE4"]
    corner = [n for n, _, _ in files(80, -211)]
    assert corner[0] == "kitaise_06NF3" and sorted(corner) == ["kitaise_06NE2", "kitaise_06NE4", "kitaise_06NF1",
                                                               "kitaise_06NF3"]
    assert files(0, 0) == [] and files(40, -180) == []
    ne4 = next(r for r in jf.rf_table() if r.code == "06NE4")
    assert not ne4.mask[:4, :4].any() and files(40, -211) == []  # 06NE4's empty north-west corner: no request
    request = jf.KS_DTM.index.request((78, -217))
    assert request.crs == "EPSG:6674" and request.shape == (1000, 1000)
    assert (request.transform.c, request.transform.f, request.transform.a) == (39_000, -108_000, 0.5)


def test_tiles_are_the_blocks_with_data():
    """The tiles over a grid are the blocks with a file holding data there: every block of a grid over R100's place,
    none in Tsu's centre (in the quarter 06OF3, which has no file)."""
    tiling = jf.KS_DTM.index
    assert tiling.tiles(make_grid((39_001, -108_999, 39_999, -108_001), 1.0, jf.KS_CRS)) == [
        (78, -218), (79, -218), (78, -217), (79, -217)]
    assert tiling.tiles(make_grid((46_001, -140_999, 46_999, -140_001), 1.0, jf.KS_CRS)) == []


def test_has_data_near_from_the_masks(monkeypatch, tmp_path):
    """Within 2 km of a tile with data (the masks; no request): inside the data (R100), on its edge and 1 km outside it
    (east of the Suzuka range at 35.03 N, where the data end at 136.560 E), not 5 km outside (Yokkaichi's plain) nor in
    Tsu's centre; --source auto in jp-24 takes mie, else europe."""
    def no_request(*args, **kwargs):
        raise AssertionError("a request")
    monkeypatch.setattr(src.net, "_get", no_request)
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "jp")
    monkeypatch.setattr(src.choose, "region_codes", lambda lat, lon, cache_dir, code: ("jp-24",))
    layer = jf.KS_DTM
    inside, edge, near, far = (35.0217, 136.4281), (35.0300, 136.5600), (35.0300, 136.5710), (35.0300, 136.6149)
    assert layer.has_data_near(*inside, str(tmp_path)) is True
    assert layer.has_data_near(*edge, str(tmp_path)) is True
    assert layer.has_data_near(*near, str(tmp_path)) is True
    assert layer.has_data_near(*far, str(tmp_path)) is False
    assert layer.has_data_near(34.7339, 136.5103, str(tmp_path)) is False
    assert layer.index.has_data_near(*far, str(tmp_path), metres=8000) is True
    assert src.choose_source("auto", *inside, str(tmp_path))[0].id == "mie"
    assert src.choose_source("auto", *far, str(tmp_path)) == (
        src.SOURCES["europe"], "the centre is in JP-24, but mie has no terrain data near it")


# --- the tool --------------------------------------------------------------------------------------------------------
def _package():
    with open(os.path.join(RECORDED, "kitaise_081_rows.json"), encoding="utf-8") as f:
        return json.load(f)["result"]


def test_tool_rows_of_a_listing():
    """dem_resources: the DEM GeoTIFFs of a record's resources (not the DCHM, not the PDF), their keys in the bucket
    (CKAN's download link becomes ckan/resources/<id>/<file>), codes upper case, the edition from the name; a DEM
    file behind CKAN's own download name (www.geospatial.jpdem_...) is left out and named (skipped_dems)."""
    import forest_files
    assert forest_files.dem_resources(_package()) == [
        ("06NE2", "ckan/resources/f32fcb50-0c82-4c9a-ae21-a2011b96e198/dem_06ne2_2025.tif", 2025),
        ("06NE4", NE4_KEY, 2025)]
    other = {"resources": [{"id": "x", "url": "https://example.org/files/dem_06NE4_2025.tif"}]}
    with pytest.raises(ValueError, match="neither the bucket nor CKAN"):
        forest_files.dem_resources(other)
    national = {"resources": [{"id": "x", "url": f"{forest_files.BUCKET}/national-gov/a/b/dem_06OE2_2025.tif"}]}
    assert forest_files.dem_resources(national) == [("06OE2", "national-gov/a/b/dem_06OE2_2025.tif", 2025)]
    assert forest_files.skipped_dems(_package()) == []
    behind = {"resources": [{"id": "y", "name": "dem_04FE4_2025", "url": "https://www.geospatial.jp/ckan/dataset/d/"
                             "resource/y/download/www.geospatial.jpdem_04fe4_2025.tif"}]}  # Yoshinokawa's 14
    assert forest_files.dem_resources(behind) == [] and forest_files.skipped_dems(behind) == ["dem_04FE4_2025"]


def _empty_tiles():
    """The two recorded empty tiles of 06NE4 that the tool decodes for its classes (the first of the smallest size in
    row order: full tile 0, 0 and the last row's first 1 390-byte tile): {first byte: bytes}."""
    with zipfile.ZipFile(os.path.join(RECORDED, "dem_06ne4_2025_empty_tiles.zip")) as z:
        return {int(n): z.read(n) for n in z.namelist()}


def test_tool_row_from_a_recorded_header():
    """file_row on 06NE4's recorded header: the shipped table's facts (CRS from the tags, size, ETag, the tile entries
    without reading a tile, on the blocks' pixels); the empty tiles of the full and last-row classes are the recorded
    file's own (1 626 and 1 390 bytes, decoded to nodata), asked by their own ranges; refused under another code (not
    on its quarter) and another zone (other CRS)."""
    import forest_files
    pieces, size = _pieces()
    head = (pieces[0], size, "adc10fbd648aefa05e690b293d7e71be-46", "Fri, 02 Oct 2026 07:41:47 GMT")
    row = forest_files.file_row("kitaise", "06NE4", NE4_KEY, 2025, head)
    shipped = next(r for r in jf.rf_table() if r.code == "06NE4")
    assert row["epsg"] == 6674 and (row["width"], row["height"]) == (40001, 30001) and row["size"] == shipped.size
    assert row["on_pixels"] and row["sizes"].shape == shipped.mask.shape == (59, 79)
    assert row["sizes"][23, 71] == 1626 and row["sizes"][22, 71] == 1877 and row["sizes"][58, 0] == 1390
    assert row["class_ids"].keys() == {(512, 512), (305, 512), (512, 65), (305, 65)}
    recorded, asked = _empty_tiles(), []

    def read(offset, n):
        asked.append(offset)
        return recorded[offset]
    assert forest_files.class_empty(row, (512, 512), read) == recorded[56509] and len(recorded[56509]) == 1626
    assert len(forest_files.class_empty(row, (305, 512), read)) == 1390
    assert sorted(asked) == sorted(recorded)
    with pytest.raises(ValueError, match="does not lie on its quarter"):
        forest_files.file_row("kitaise", "06NE2", NE4_KEY, 2025, head)
    with pytest.raises(ValueError, match="not EPSG:6675 of zone 7"):
        forest_files.file_row("kitaise", "07NE4", NE4_KEY, 2025, head)


def _written(path, band, origin=(20_000, -105_000), block=512, **options):
    """A file as the Agency's (float32, Deflate, predictor 2, block px tiles, nodata -9999) at origin, its bytes."""
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs="EPSG:6674", transform=from_origin(*origin, 0.5, 0.5), tiled=True, blockxsize=block,
                  blockysize=block, compress="deflate", predictor=2, nodata=-9999, **options) as dst:
        dst.write(band, 1)
    with open(path, "rb") as f:
        return f.read()


def _masked(files, reads=None, kept=()):
    """Rows of written files ({code: bytes}), their masks made together by the tool (masks, with the kept rows of
    other records as seeds); reads collects the asked ranges (code, first, last)."""
    import forest_files
    rows = [forest_files.file_row("t", code, code, 2025, (data, len(data), "e", LM)) for code, data in files.items()]

    def read(row, first, last):
        if reads is not None:
            reads.append((row["code"], first, last))
        return files[row["code"]][first:last + 1]
    counts = forest_files.masks(rows, read, report=lambda line: None, kept=kept)
    return {r["code"]: r for r in rows}, counts


def _constant_height(path, tries=400):
    """A height whose constant full tile compresses (zlib level 9, as the Agency's files) to exactly the empty full
    tile's size, and that size (the code review's finding: 1 757 of 6 000 heights do with the Agency's encoder)."""
    rng = np.random.default_rng(3)
    for h in rng.uniform(0, 1500, tries).astype(np.float32):
        band = np.full((512, 1024), -9999.0, dtype=np.float32)
        band[:, 512:] = h
        _written(path, band, zlevel=9)
        with rio.open(path) as f:
            sizes = [int(f.get_tag_item(f"BLOCK_SIZE_{x}_0", "TIFF", bidx=1)) for x in (0, 1)]
        if sizes[0] == sizes[1]:
            return float(h), sizes[0]
    raise AssertionError("no height compressed to the empty size")


def test_data_mask_rule_on_a_written_file(tmp_path):
    """The mask on a file GDAL writes as the Agency's are: each class's empty tile (full, last row, last column) found
    by decoding its smallest tile; a tile with 3 valid pixels, a full slope and the corner's one tile (data, so its
    class has no empty tile) are data; tiles without bytes (sparse_ok) are empty when the file was read whole."""
    band = np.full((1100, 1300), -9999.0, dtype=np.float32)
    band[600:603, 10] = 412.5          # three pixels in tile (0, 1)
    band[0:512, 512:1024] = 300.0 + np.arange(512, dtype=np.float32) * 0.01  # tile (1, 0): a slope
    band[1050:1100, 1200:1300] = 50.0  # the corner tile (2, 2)
    expected = np.array([[(band[y * 512:(y + 1) * 512, x * 512:(x + 1) * 512] != -9999).any() for x in range(3)]
                         for y in range(3)])
    row = _masked({"06NE4": _written(str(tmp_path / "f.tif"), band)})[0]["06NE4"]
    assert np.array_equal(row["mask"], expected), (row["mask"], expected)
    assert row["empties"][(512, 512)] and row["empties"][(512, 276)] and row["empties"][(76, 276)] is None
    data = _written(str(tmp_path / "s.tif"), band, sparse_ok=True)  # the empty tiles not written
    with rio.open(str(tmp_path / "s.tif")) as f:
        assert f.get_tag_item("BLOCK_OFFSET_2_0", "TIFF", bidx=1) in (None, "0")
    assert np.array_equal(_masked({"06NE4": data})[0]["06NE4"]["mask"], expected)


def test_constant_tile_beside_data_is_data(tmp_path):
    """A tile of one constant height whose byte count is exactly the empty tile's (zlib level 9, the Agency's): beside
    a data tile it is read and compared byte for byte with the empty tile, so it is data, and so is a constant tile
    beside it (read in turn); one wholly enclosed by empty tiles is called empty (the rule's residual, said in the
    module and the tool). Adjacent empty-sized tiles are read in one range."""
    h, size = _constant_height(str(tmp_path / "h.tif"))
    band = np.full((1536, 2048), -9999.0, dtype=np.float32)  # 3 rows x 4 columns of tiles
    band[1024:, 1536:] = 200.0 + np.arange(512, dtype=np.float32)  # tile (3, 2): a slope
    band[1024:, 1024:1536] = h       # tile (2, 2), beside the slope
    band[1024:, 512:1024] = h        # tile (1, 2), beside tile (2, 2) only
    band[:512, :512] = h             # tile (0, 0): enclosed by empty tiles
    reads = []
    rows, counts = _masked({"06NE4": _written(str(tmp_path / "f.tif"), band, zlevel=9)}, reads)
    row = rows["06NE4"]
    assert row["sizes"][2, 2] == row["sizes"][2, 1] == row["sizes"][0, 0] == row["sizes"][1, 1] == size
    expected = np.zeros((3, 4), dtype=bool)
    expected[2, 1:] = True
    assert np.array_equal(row["mask"], expected), row["mask"]
    assert counts["data"] == 2 and counts["read"] > counts["ranges"]  # (2, 1) and (3, 1): one range
    assert any(last - first + 1 == 2 * size for _, first, last in reads)


def test_constant_tile_beside_data_in_the_next_file(tmp_path):
    """Across a file's edge: data in the last tile column of 06NE3 make the first tile column of 06NE4 (the
    neighbouring quarter's file of the same run) be read, and a constant tile of the empty size there is data; one two
    tiles away from any data stays empty."""
    h, size = _constant_height(str(tmp_path / "h.tif"))
    west = np.full((512, 2048), -9999.0, dtype=np.float32)
    west[:, 1536:] = 100.0 + np.arange(512, dtype=np.float32)  # 06NE3's last tile, x 19 744-20 000
    east = np.full((512, 2048), -9999.0, dtype=np.float32)
    east[:, :512] = h               # 06NE4's first tile, x 20 000-20 256
    east[:, 1024:1536] = h          # its third tile: no data beside it
    rows, _ = _masked({"06NE3": _written(str(tmp_path / "w.tif"), west, origin=(18_976, -105_000), zlevel=9),
                       "06NE4": _written(str(tmp_path / "e.tif"), east, zlevel=9)})
    assert rows["06NE4"]["sizes"][0, 0] == size
    assert rows["06NE3"]["mask"].tolist() == [[False, False, False, True]]
    assert rows["06NE4"]["mask"].tolist() == [[True, False, False, False]]


def test_a_sea_at_zero_smaller_than_the_empty_tile(tmp_path):
    """A tile of a sea flattened at 0.0 m compresses smaller than the empty tile (1 039 against 1 626 bytes at zlib 9):
    the class's empty tile is still found (the next size up is tried), so the empty tiles stay empty and the sea tile
    is data; without it every tile of the file would count as data."""
    band = np.full((1024, 1536), -9999.0, dtype=np.float32)  # 2 x 3 full tiles
    band[:512, :512] = 0.0                                    # tile (0, 0): a sea at 0.0 m
    band[512:, 1024:] = 200.0 + np.arange(512, dtype=np.float32)  # tile (2, 1): a slope
    rows, _ = _masked({"06NE4": _written(str(tmp_path / "f.tif"), band, zlevel=9)})
    row = rows["06NE4"]
    assert row["sizes"][0, 0] < row["sizes"][0, 1]  # the sea's tile smaller than the empty ones
    assert row["mask"].tolist() == [[True, False, False], [False, False, True]]
    assert row["empties"][(512, 512)] == row["sizes"][0, 1]


def test_constant_tile_beside_data_of_a_kept_record(tmp_path):
    """The search from data tiles starts from the rows kept from the table too (another record, made by an earlier
    run): a constant tile of the empty size in the file read now, beside a kept record's data tile, is read and is
    data (Tokushima beside Yoshinokawa, two --record runs)."""
    import forest_files
    h, size = _constant_height(str(tmp_path / "h.tif"))
    west = np.full((512, 2048), -9999.0, dtype=np.float32)
    west[:, 1536:] = 100.0 + np.arange(512, dtype=np.float32)
    east = np.full((512, 2048), -9999.0, dtype=np.float32)
    east[:, :512] = h
    first, _ = _masked({"06NE3": _written(str(tmp_path / "w.tif"), west, origin=(18_976, -105_000), zlevel=9)})
    table = str(tmp_path / "t.npz")
    forest_files.save(table, [{**first["06NE3"], "record": "y"}])
    kept = list(forest_files.load(table).values())
    rows, counts = _masked({"06NE4": _written(str(tmp_path / "e.tif"), east, zlevel=9)}, kept=kept)
    assert rows["06NE4"]["sizes"][0, 0] == size and counts["data"] == 1
    assert rows["06NE4"]["mask"].tolist() == [[True, False, False, False]]


def test_no_row_without_a_last_modified(tmp_path):
    """A file whose answer gave no Last-Modified date (or one that is no date) gets no row: the catalogue reads every
    date of the table when it is imported (the cache folder's stamp), so a table the tool makes never breaks it."""
    import forest_files
    data = _written(str(tmp_path / "f.tif"), np.full((512, 512), 100.0, dtype=np.float32))
    for modified in ("", "yesterday"):
        with pytest.raises(ValueError, match="no Last-Modified date"):
            forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", modified))
    assert forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", LM))["modified"] == LM


def test_an_old_table_without_the_on_pixels_column(tmp_path, monkeypatch):
    """A table written before the on_pixels column reads every file as off the blocks' pixels, so rf_rows refuses
    them all (safe: nothing read through a resampling unseen)."""
    import forest_files
    path = str(tmp_path / "t.npz")
    forest_files.save(path, [_row("a", "06NE4", np.ones((59, 79), dtype=bool))])
    with np.load(path) as t:
        arrays = {k: t[k] for k in t.files if k != "on_pixels"}
    np.savez_compressed(path, **arrays)
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(path))
    assert jf.load_table(path)[0].on_pixels is False
    with pytest.raises(ValueError, match="a 06NE4 would not read the files' own pixels"):
        jf.rf_files(("a",), 6, {"a": 2020})(40, -211)


def _strips(path, band, rows=1, compress="deflate", origin=(20_000, -105_000)):
    """A strip file as Shonai's and h30's small ones: one-row strips, Deflate with predictor 2 (or rows-row strips
    without compression, as h30's 05MB4), float32, nodata -9999; its bytes."""
    options = {"compress": compress, "predictor": 2} if compress else {}
    with rio.open(path, "w", driver="GTiff", width=band.shape[1], height=band.shape[0], count=1, dtype="float32",
                  crs="EPSG:6674", transform=from_origin(*origin, 0.5, 0.5), tiled=False, blockysize=rows,
                  nodata=-9999, **options) as dst:
        dst.write(band, 1)
    with open(path, "rb") as f:
        return f.read()


def test_strip_files_read_whole_and_masked_by_cells(tmp_path):
    """A strip file of at most STRIP_WHOLE_BYTES is read whole (one range) and masked from its decoded pixels on cells
    of 512 x 512 px, as a tiled file: its data in columns 100-299 make only the first cell column data, Deflate or
    uncompressed (h30's 05MB4) alike; its data cells seed the search of the files beside it."""
    import forest_files
    band = np.full((40, 1200), -9999.0, dtype=np.float32)
    band[10:14, 100:300] = 250.0 + np.arange(200, dtype=np.float32)
    for name, data in (("deflate", _strips(str(tmp_path / "s.tif"), band)),
                       ("plain", _strips(str(tmp_path / "u.tif"), band, rows=4, compress=None))):
        reads = []
        rows, counts = _masked({"06NE4": data}, reads)
        row = rows["06NE4"]
        assert not row["tiled"] and (row["tile_w"], row["tile_h"]) == (512, 512) and row["whole"] == len(data), name
        assert row["mask"].tolist() == [[True, False, False]], name
        assert counts["whole"] == 1 and reads == [("06NE4", 0, len(data) - 1)], name
        assert "cells 512 x 512, 1 of 3 with data" in forest_files.describe(row) and "read whole" in \
            forest_files.describe(row)


def test_a_strip_file_read_whole_seeds_the_file_beside_it(tmp_path):
    """The data cells of a strip file read whole seed the search of the tiled file beside it: a constant tile of the
    empty size in 06NE4's first column, beside data in 06NE3's (a strip file's) last cell column, is read and is
    data."""
    h, size = _constant_height(str(tmp_path / "h.tif"))
    west = np.full((40, 2048), -9999.0, dtype=np.float32)
    west[:, 1900:] = 100.0 + np.arange(148, dtype=np.float32)
    east = np.full((512, 2048), -9999.0, dtype=np.float32)
    east[:, :512] = h
    rows, counts = _masked({"06NE3": _strips(str(tmp_path / "w.tif"), west, origin=(18_976, -105_000)),
                            "06NE4": _written(str(tmp_path / "e.tif"), east, zlevel=9)})
    assert rows["06NE3"]["mask"].tolist() == [[False, False, False, True]] and rows["06NE3"]["whole"]
    assert rows["06NE4"]["sizes"][0, 0] == size and counts["data"] == 1
    assert rows["06NE4"]["mask"].tolist() == [[True, False, False, False]]


def test_a_strip_file_too_large_to_read_whole_keeps_the_strip_rule(tmp_path, monkeypatch):
    """Over STRIP_WHOLE_BYTES a strip file is masked strip by strip, and the tool says so: the strips with data are
    data, the empty-sized strips beside them read and found empty; an uncompressed one is data in every strip; a short
    last strip (42 rows of 4-row strips: the last holds 2) is decoded, not an error (code review F3)."""
    import forest_files
    monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", 0)
    band = np.full((40, 600), -9999.0, dtype=np.float32)
    band[10:14, 100:300] = 250.0 + np.arange(200, dtype=np.float32)  # rows 10-13
    said, data = [], _strips(str(tmp_path / "s.tif"), band)
    rows = [forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", LM))]
    counts = forest_files.masks(rows, lambda row, a, b: data[a:b + 1], report=said.append)
    row = rows[0]
    assert (row["tile_w"], row["tile_h"]) == (600, 1) and row["mask"].shape == (40, 1) and "whole" not in row
    assert np.flatnonzero(row["mask"][:, 0]).tolist() == [10, 11, 12, 13]
    assert counts["read"] >= 2 and counts["data"] == 0 and counts["whole"] == 0
    assert any("masked strip by strip" in line for line in said)
    row = _masked({"06NE4": _strips(str(tmp_path / "u.tif"), band, rows=4, compress=None)})[0]["06NE4"]
    assert row["compression"] in (None, "NONE") and row["mask"].shape == (10, 1) and row["mask"].all()
    short = np.full((42, 600), -9999.0, dtype=np.float32)
    short[9:11, 50:60] = 100.0  # strip 2 (rows 8-11)
    row = _masked({"06NE4": _strips(str(tmp_path / "w.tif"), short, rows=4)})[0]["06NE4"]
    assert row["mask"].shape == (11, 1) and np.flatnonzero(row["mask"][:, 0]).tolist() == [2]


def test_a_strip_files_data_reach_no_farther_than_their_cells(tmp_path, monkeypatch):
    """Code review F2: a 6 km wide one-row strip file with data in its first 200 columns. Read whole, its mask's
    cells are 256 m, so a box 5 km east of the data holds none and the block there is no tile; masked strip
    by strip (the cell as wide as the file) it said yes there."""
    import forest_files
    band = np.full((60, 12_000), -9999.0, dtype=np.float32)
    band[:, :200] = 300.0 + np.arange(200, dtype=np.float32)
    data = _strips(str(tmp_path / "s.tif"), band)
    for cap, far in ((forest_files.STRIP_WHOLE_BYTES, False), (0, True)):
        monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", cap)
        rows, _ = _masked({"06NE4": data})
        table = str(tmp_path / f"t{cap}.npz")
        forest_files.save(table, [{**rows["06NE4"], "record": "kitaise", "key": "k/s.tif"}])
        monkeypatch.setattr(jf, "rf_table", lambda table=table: jf.load_table(table))
        file = jf.rf_table()[0]
        assert file.has_data((20_000, -105_030, 20_100, -105_000))
        assert file.has_data((25_100, -105_030, 25_200, -105_000)) is far
        assert bool(jf.KS_DTM.index.files(50, -211)) is far  # the block x 25 000-25 500: a tile, read, or none


def test_block_of_a_strip_file_through_the_catalogue_layer(http_server, monkeypatch, tmp_path):
    """A block of a strip file (one-row Deflate strips, and an uncompressed one of 4-row strips) read through the
    catalogue's own layer from the local host on the file's own pixels: the file's values within LERC's 5 mm."""
    import forest_files
    band = np.full((1200, 1100), -9999.0, dtype=np.float32)
    band[100:900, 50:1000] = 300.0 + np.add.outer(np.arange(800), np.arange(950)).astype(np.float32) * 0.05
    monkeypatch.setattr(jf, "RF_BUCKET", http_server.base)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    for name, data in (("deflate", _strips(str(tmp_path / "d.tif"), band)),
                       ("plain", _strips(str(tmp_path / "p.tif"), band, rows=4, compress=None))):
        rows, _ = _masked({"06NE4": data})
        table = str(tmp_path / f"{name}.npz")
        forest_files.save(table, [{**rows["06NE4"], "record": "kitaise", "key": f"k/{name}.tif"}])
        monkeypatch.setattr(jf, "rf_table", lambda table=table: jf.load_table(table))
        http_server.add(f"/k/{name}.tif", data, "image/tiff")
        cache_dir = str(tmp_path / f"cache-{name}")
        grid = make_grid((20_001, -105_499, 20_499, -105_001), 0.5, jf.KS_CRS)
        assert jf.KS_DTM.tiles(grid) == [(40, -211)]
        jf.KS_DTM.download(grid, cache_dir, None, "terrain")
        with rio.open(jf.KS_DTM.tile_path(cache_dir, (40, -211))) as block:
            values = block.read(1)
        expected = band[:1000, :1000].copy()
        expected[expected == -9999] = np.nan
        assert np.array_equal(np.isnan(values), np.isnan(expected)), name
        assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.0051), name


def test_unnamed_tile_entries_are_an_error(tmp_path, monkeypatch):
    """Tile entries GDAL cannot name in the bytes read (a COG's arrays cut by the re-read's cap) are an error naming
    the file, never sparse tiles; read whole, unnamed entries are sparse."""
    import forest_files
    from rasterio.shutil import copy as rio_copy
    band = np.full((320, 3776), -9999.0, dtype=np.float32)
    band[:, ::7] = 300.0
    plain = str(tmp_path / "p.tif")
    _written(plain, band, block=64)
    cog = str(tmp_path / "c.tif")
    rio_copy(plain, cog, driver="COG", BLOCKSIZE=64, COMPRESS="DEFLATE", PREDICTOR="2", OVERVIEWS="NONE")
    data = open(cog, "rb").read()
    with rio.io.MemoryFile(data[:2500]) as mem, mem.open() as src:
        assert forest_files._unnamed(src) > 0  # the open names its tags, not all its tiles
    monkeypatch.setattr(forest_files, "MAX_HEAD_BYTES", 2500)
    with pytest.raises(ValueError, match="06NE4: .* tile entries not named in the first 2500 bytes"):
        forest_files.file_row("t", "06NE4", "k", 2025, (data[:2000], len(data), "e", LM),
                              lambda n: (data[:n], len(data), "e", LM))
    row = forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", LM))
    assert (row["sizes"] > 0).all()


def test_quarter_slack_is_a_pixel_and_a_metre(tmp_path):
    """A file may reach one pixel and 1 m beyond its quarter (40 001 px files, float noise), not 2 m."""
    import forest_files
    band = np.full((512, 512), 100.0, dtype=np.float32)
    ok = _written(str(tmp_path / "a.tif"), band, origin=(39_745.0, -105_000))     # far edge 40 001.0
    far = _written(str(tmp_path / "b.tif"), band, origin=(39_746.0, -105_000))    # far edge 40 002.0
    assert forest_files.file_row("t", "06NE4", "k", 2025, (ok, len(ok), "e", LM))["epsg"] == 6674
    with pytest.raises(ValueError, match="does not lie on its quarter"):
        forest_files.file_row("t", "06NE4", "k", 2025, (far, len(far), "e", LM))


def _wide(path, pixel, origin):
    """A sparse file of 40 001 x 512 px (only its first tile written) of a pixel size and corner: Tokushima's case."""
    with rio.open(path, "w", driver="GTiff", width=40_001, height=512, count=1, dtype="float32", crs="EPSG:6674",
                  transform=from_origin(*origin, pixel, pixel), tiled=True, blockxsize=512, blockysize=512,
                  compress="deflate", predictor=2, nodata=-9999, sparse_ok=True) as dst:
        dst.write(np.full((512, 512), 100.0, dtype=np.float32), 1, window=rio.windows.Window(0, 0, 512, 512))
    with open(path, "rb") as f:
        return f.read()


def test_on_pixels_by_the_readers_test(tmp_path):
    """on_pixels asks windows._coincide at the file's first block and at its far edge: Kitaise's float noise passes;
    a corner 1.3 cm off the grid fails at once; Tokushima's 0.49999987 m pixel with an exact corner fails only at the
    far edge (0.0104 px over 40 001 px), so the far edge must be asked."""
    import forest_files
    for name, pixel, origin, expected in (("kitaise", 0.4999999999999944, (19_999.9999999998, -105_000), True),
                                          ("corner", 0.5, (20_000.013, -105_000), False),
                                          ("pixel", 0.49999987, (20_000.0, -105_000), False)):
        data = _wide(str(tmp_path / f"{name}.tif"), pixel, origin)
        row = forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", LM))
        assert row["on_pixels"] is expected, name


def test_tool_reads_more_when_the_header_is_cut(tmp_path):
    """A header cut before its directory (GDAL writes a file's directory at its end): file_row asks the file's first
    MAX_HEAD_BYTES (here the whole small file) once and makes the row from them; without a way to read more it
    refuses."""
    import forest_files
    band = np.full((1100, 1300), -9999.0, dtype=np.float32)
    band[600:700, 10:400] = 412.5 + np.arange(390, dtype=np.float32) * 0.01
    data = _written(str(tmp_path / "f.tif"), band)
    asked = []

    def more(n):
        asked.append(n)
        return data[:n], len(data), "e", "m"
    row = forest_files.file_row("kitaise", "06NE4", "k", 2025, (data[:200], len(data), "e", LM), more)
    assert asked == [len(data)] and row["epsg"] == 6674 and row["sizes"][1, 0] > row["sizes"][0, 0]
    with pytest.raises(ValueError, match="does not fit"):
        forest_files.file_row("kitaise", "06NE4", "k", 2025, (data[:200], len(data), "e", LM))


def test_tool_save_load_and_changes(tmp_path):
    """save and load keep every row and mask; changes names a file added, removed, re-published in place (another
    ETag or size) and a changed mask."""
    import forest_files
    m = np.zeros((59, 79), dtype=bool)
    m[3, 4] = True
    rows = [_row("kitaise", "06NE4", m), _row("kitaise", "06NE2", m.copy())]
    path = str(tmp_path / "t.npz")
    forest_files.save(path, rows)
    old = forest_files.load(path)
    back = jf.load_table(path)
    assert [r.code for r in back] == ["06NE2", "06NE4"] and np.array_equal(back[1].mask, m)
    assert back[1].epsg == 6674 and (back[1].a, back[1].e, back[1].c, back[1].f) == (0.5, -0.5, 20_000, -105_000)
    m2 = m.copy()
    m2[5, 5] = True
    new_rows = [_row("kitaise", "06NE4", m, etag="other"), _row("kitaise", "06NF3", m), _row("kitaise", "06NE2", m2)]
    forest_files.save(path, new_rows)
    lines = forest_files.changes(old, forest_files.load(path))
    assert lines[0] == "files added: 1 ['kitaise 06NF3']" and lines[1] == "files removed: 0 []"
    assert lines[2] == "files replaced (size, ETag or address): 1 ['kitaise 06NE4']"
    assert lines[3] == "masks changed: 1 [('kitaise 06NE2', 1, 2)]"


def _serve_written(http_server, monkeypatch, files, records):
    """The tool's hosts on the local server: CKAN's package_show for each record (records: our name -> {code: bytes})
    and each file at its key in the bucket (Range answered by the server), the ETag and Last-Modified of a file."""
    import forest_files
    monkeypatch.setattr(forest_files, "CKAN", http_server.url("/ckan/api/3/action/package_show"))
    monkeypatch.setattr(forest_files, "BUCKET", http_server.base)
    monkeypatch.setattr(forest_files, "RECORDS", {name: f"p_{name}" for name in records})
    monkeypatch.setattr(forest_files, "SHIPPED", (sorted(records)[0],))
    for name, codes in records.items():
        resources = [{"id": f"{name}{code}", "name": f"dem_{code}_2025",
                      "url": f"{http_server.base}/{name}/dem_{code.lower()}_2025.tif"} for code in codes]
        http_server.add(f"/ckan/api/3/action/package_show?id=p_{name}",
                        json.dumps({"result": {"resources": resources}}).encode(), "application/json")
        for code in codes:
            http_server.add(f"/{name}/dem_{code.lower()}_2025.tif", files[code], "image/tiff",
                            headers={"ETag": f'"{name}{code}"', "Last-Modified": "Fri, 02 Oct 2026 07:41:47 GMT"})


def test_tool_main_keeps_the_other_records(http_server, monkeypatch, tmp_path, capsys):
    """tools/forest_files.py main() against the local hosts (Fetcher, record_rows, masks, save): --record b keeps
    record a's rows of the table it replaces and says nothing was removed; a's record no longer listing its file is
    then reported removed, against the whole old table, and b's rows are kept."""
    import forest_files
    band = np.full((512, 1024), -9999.0, dtype=np.float32)
    band[:, :512] = 300.0 + np.arange(512, dtype=np.float32)
    files = {"06NE4": _written(str(tmp_path / "a.tif"), band), "06NE2": _written(
        str(tmp_path / "b.tif"), band, origin=(20_000, -90_000))}
    _serve_written(http_server, monkeypatch, files, {"a": ["06NE4"], "b": ["06NE2"]})
    out, data = str(tmp_path / "t.npz"), str(tmp_path / "data")
    forest_files.main(["--out", out, "--data-dir", data])
    assert [(r.record, r.code) for r in jf.load_table(out)] == [("a", "06NE4")]
    forest_files.main(["--record", "b", "--out", out, "--data-dir", data])
    table = jf.load_table(out)
    assert [(r.record, r.code) for r in table] == [("a", "06NE4"), ("b", "06NE2")]
    assert table[1].etag == "b06NE2" and table[1].mask.tolist() == [[True, False]] and table[1].on_pixels
    printed = capsys.readouterr().out
    assert "kept from the table: 1 rows" in printed and "files removed: 0 []" in printed
    http_server.add("/ckan/api/3/action/package_show?id=p_a", json.dumps({"result": {"resources": []}}).encode(),
                    "application/json")
    before = open(out, "rb").read()
    with pytest.raises(ValueError, match="a: its listing names no DEM file: nothing saved"):
        forest_files.main(["--record", "a", "--out", out, "--data-dir", data])
    assert open(out, "rb").read() == before  # code review F4 b: never a table without a record's rows


def test_tool_main_dates_of_any_http_form(http_server, monkeypatch, tmp_path):
    """Code review F4 a: the table stores a Last-Modified date the tool parsed itself, written again in GMT: RFC 1123
    with -0000, RFC 850 and asctime (no zone: GMT, as HTTP's dates are) give the same stored date, so rf_stamp can
    compare them; a date it cannot parse stops the run and nothing is saved."""
    import forest_files
    band = np.full((512, 1024), -9999.0, dtype=np.float32)
    band[:, :512] = 300.0 + np.arange(512, dtype=np.float32)
    files = {"06NE4": _written(str(tmp_path / "a.tif"), band)}
    _serve_written(http_server, monkeypatch, files, {"a": ["06NE4"]})
    out, data = str(tmp_path / "t.npz"), str(tmp_path / "data")
    for text in ("Fri, 02 Oct 2026 07:41:47 -0000", "Friday, 02-Oct-26 07:41:47 GMT", "Fri Oct  2 07:41:47 2026"):
        http_server.add("/a/dem_06ne4_2025.tif", files["06NE4"], "image/tiff",
                        headers={"ETag": '"x"', "Last-Modified": text})
        forest_files.main(["--out", out, "--data-dir", data])
        assert jf.load_table(out)[0].modified == LM, text
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(out))
    assert jf.rf_stamp("a") == "20261002"
    http_server.add("/a/dem_06ne4_2025.tif", files["06NE4"], "image/tiff",
                    headers={"ETag": '"x"', "Last-Modified": "about noon"})
    os.remove(out)
    with pytest.raises(ValueError, match="no Last-Modified date"):
        forest_files.main(["--out", out, "--data-dir", data])
    assert not os.path.exists(out)


def test_tool_main_makes_every_shipped_record_in_one_run(http_server, monkeypatch, tmp_path, capsys):
    """Code review F5 and M14: SHIPPED names every record of the shipped table; a run without --record makes them all
    in one run, so a constant tile of the empty size in record b's file beside record a's data tile is read and is
    data; a --record b run seeds its search from a's kept rows the same way (main passes them to masks); each row
    described (describe)."""
    import forest_files
    assert set(forest_files.SHIPPED) == {r.record for r in jf.rf_table()}
    h, size = _constant_height(str(tmp_path / "h.tif"))
    west = np.full((512, 2048), -9999.0, dtype=np.float32)
    west[:, 1536:] = 100.0 + np.arange(512, dtype=np.float32)
    east = np.full((512, 2048), -9999.0, dtype=np.float32)
    east[:, :512] = h
    files = {"06NE3": _written(str(tmp_path / "w.tif"), west, origin=(18_976, -105_000), zlevel=9),
             "06NE4": _written(str(tmp_path / "e.tif"), east, zlevel=9)}
    _serve_written(http_server, monkeypatch, files, {"a": ["06NE3"], "b": ["06NE4"]})
    monkeypatch.setattr(forest_files, "SHIPPED", ("a", "b"))
    out, data = str(tmp_path / "t.npz"), str(tmp_path / "data")
    forest_files.main(["--out", out, "--data-dir", data])
    table = {r.code: r for r in jf.load_table(out)}
    assert table["06NE4"].mask.tolist() == [[True, False, False, False]] and table["06NE3"].record == "a"
    printed = capsys.readouterr().out
    assert "b 06NE4: EPSG:6674 2048 x 512 px" in printed and "on the blocks' pixels, tiles 512 x 512, 1 of 4" in printed
    forest_files.save(out, [forest_files.load(out)[("a", "06NE3")]])  # a alone in the table
    forest_files.main(["--record", "b", "--out", out, "--data-dir", data])
    assert {r.code: r for r in jf.load_table(out)}["06NE4"].mask.tolist() == [[True, False, False, False]]


def test_tool_main_max_requests_saves_nothing(http_server, monkeypatch, tmp_path):
    """Code review M15: main gives --max-requests to its Fetcher; the run stops before the request past it and
    nothing is saved."""
    import forest_files
    band = np.full((512, 1024), -9999.0, dtype=np.float32)
    band[:, :512] = 300.0 + np.arange(512, dtype=np.float32)
    _serve_written(http_server, monkeypatch, {"06NE4": _written(str(tmp_path / "a.tif"), band)}, {"a": ["06NE4"]})
    out = str(tmp_path / "t.npz")
    with pytest.raises(RuntimeError, match="stopped before request 3"):
        forest_files.main(["--out", out, "--data-dir", str(tmp_path / "data"), "--max-requests", "2"])
    assert not os.path.exists(out) and len(http_server.requests("/a/dem_06ne4_2025.tif")) == 1


def test_tool_strips_reads_only_the_strip_files_whole(http_server, monkeypatch, tmp_path, capsys):
    """--strips: the table's strip files still masked strip by strip are read whole (one range each) and masked on
    cells; a tiled file and the other rows stay as they were, and no other request is made; a file the bucket answers
    with another ETag stops it, nothing saved."""
    import forest_files
    band = np.full((40, 1200), -9999.0, dtype=np.float32)
    band[10:14, 100:300] = 250.0
    strip = _strips(str(tmp_path / "s.tif"), band)
    tiled = np.full((512, 1024), -9999.0, dtype=np.float32)
    tiled[:, :512] = 300.0 + np.arange(512, dtype=np.float32)
    files = {"06NE4": strip, "06NE2": _written(str(tmp_path / "t.tif"), tiled, origin=(20_000, -90_000))}
    _serve_written(http_server, monkeypatch, files, {"a": ["06NE4", "06NE2"]})
    out, data = str(tmp_path / "t.npz"), str(tmp_path / "data")
    monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", 0)  # the table made with the strip rule
    forest_files.main(["--out", out, "--data-dir", data])
    assert {r.code: r.mask.shape for r in jf.load_table(out)} == {"06NE4": (40, 1), "06NE2": (1, 2)}
    monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", 32 * 2 ** 20)
    asked = len(http_server.requests("/a/dem_06ne2_2025.tif"))
    forest_files.main(["--strips", "--out", out, "--data-dir", data])
    table = {r.code: r for r in jf.load_table(out)}
    assert table["06NE4"].mask.tolist() == [[True, False, False]] and table["06NE4"].tile_w == 512
    assert table["06NE2"].mask.tolist() == [[True, False]]
    assert len(http_server.requests("/a/dem_06ne2_2025.tif")) == asked
    assert "a 06NE4: read whole" in capsys.readouterr().out
    monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", 0)
    forest_files.main(["--out", out, "--data-dir", data])
    monkeypatch.setattr(forest_files, "STRIP_WHOLE_BYTES", 32 * 2 ** 20)
    http_server.add("/a/dem_06ne4_2025.tif", strip, "image/tiff",
                    headers={"ETag": '"other"', "Last-Modified": "Fri, 02 Oct 2026 07:41:47 GMT"})
    before = open(out, "rb").read()
    with pytest.raises(RuntimeError, match="not the table's"):
        forest_files.main(["--strips", "--out", out, "--data-dir", data])
    assert open(out, "rb").read() == before


def test_empty_sizes_bound(tmp_path, monkeypatch):
    """Code review M16: the class's EMPTY_SIZES (4) smallest distinct sizes are tried: a sea at 0.0 m and two nearly
    flat tiles compress smaller than the empty tile (1 039, 1 046, 1 054 against 1 626 bytes), so the empty tile is the
    fourth size and still found; with 3 it is not, and every tile of the class is data (safe)."""
    import forest_files
    band = np.full((512, 2560), -9999.0, dtype=np.float32)
    band[:, :1536] = 0.0
    band[0, 512] = 1.0
    band[0, 1024], band[100, 1100] = 1.0, 2.0
    band[:, 2048:] = 300.0 + np.arange(512, dtype=np.float32)
    data = _written(str(tmp_path / "f.tif"), band, zlevel=9)
    row = _masked({"06NE4": data})[0]["06NE4"]
    assert len(set(row["sizes"][0, :4].tolist())) == 4 and row["sizes"][0, 3] == max(row["sizes"][0, :4])
    assert row["mask"].tolist() == [[True, True, True, False, True]]
    monkeypatch.setattr(forest_files, "EMPTY_SIZES", 3)
    assert _masked({"06NE4": data})[0]["06NE4"]["mask"].tolist() == [[True] * 5]


def test_other_compressions_refused(tmp_path):
    """Code review M17: a file in LZW (or any codec but Deflate and none) has no mask rule: an error naming it."""
    import forest_files
    path = str(tmp_path / "l.tif")
    with rio.open(path, "w", driver="GTiff", width=512, height=512, count=1, dtype="float32", crs="EPSG:6674",
                  transform=from_origin(20_000, -105_000, 0.5, 0.5), tiled=True, blockxsize=512, blockysize=512,
                  compress="lzw", nodata=-9999) as dst:
        dst.write(np.full((512, 512), 100.0, dtype=np.float32), 1)
    data = open(path, "rb").read()
    with pytest.raises(ValueError, match="06NE4: no mask rule for LZW"):
        forest_files.file_row("t", "06NE4", "k", 2025, (data, len(data), "e", LM))


def test_seeds_meet_files_of_their_own_crs_only(tmp_path):
    """Code review M18: a kept row of another EPSG whose data tile lies at the same numbers as an empty tile of the
    file read now seeds nothing there: no tile more is read than without it."""
    import forest_files
    band = np.full((512, 2048), -9999.0, dtype=np.float32)
    band[:, :512] = 300.0 + np.arange(512, dtype=np.float32)
    data = _written(str(tmp_path / "f.tif"), band)
    _, alone = _masked({"06NE4": data})
    mask = np.array([[False, False, False, True]])
    other = {**_row("y", "06NE4", mask), "epsg": 6675, "width": 2048, "height": 512}
    rows, counts = _masked({"06NE4": data}, kept=[other])
    assert counts["read"] == alone["read"] and rows["06NE4"]["mask"].tolist() == [[True, False, False, False]]
    rows, counts = _masked({"06NE4": data}, kept=[{**other, "epsg": 6674}])  # the same CRS: tiles 2 and 3 read
    assert counts["read"] == alone["read"] + 2


def test_fetcher_checks_lengths_and_stops(http_server, tmp_path):
    """Fetcher.range: an answer shorter than the range asked is an error, never a short tile; a 429 or a 503 stops the
    run; json reads an answer whole; each request counted."""
    import cache
    import forest_files
    from http_server import Answer as A
    cache_dir = str(tmp_path / "cache")
    cache.check_layout(cache_dir)
    fetch = forest_files.Fetcher(cache_dir)
    http_server.route("/short", lambda r: A(206, b"x" * 10, {"Content-Range": "bytes 0-99/1000"}))
    with pytest.raises(RuntimeError, match="10 bytes for the range 0-99"):
        fetch.range(http_server.url("/short"), 0, 99)
    http_server.route("/busy", lambda r: A(429, b"slow down", {"Content-Type": "text/plain"}))
    with pytest.raises(RuntimeError, match="HTTP 429: stopped"):
        fetch.range(http_server.url("/busy"), 0, 99)
    http_server.add("/ok", b"0123456789" * 10)
    assert fetch.range(http_server.url("/ok"), 10, 19)[:2] == (b"0123456789", 100)
    http_server.add("/j", b'{"result": 1}', "application/json")
    assert fetch.json(http_server.url("/j")) == {"result": 1} and fetch.requests == 4
    capped = forest_files.Fetcher(cache_dir, max_requests=1)  # --max-requests: stopped before the request past it
    capped.range(http_server.url("/ok"), 0, 9)
    with pytest.raises(RuntimeError, match="stopped before request 2"):
        capped.range(http_server.url("/ok"), 0, 9)
    assert len(http_server.requests("/ok")) == 2


def test_block_with_data_through_the_catalogue_layer(http_server, monkeypatch, tmp_path):
    """The catalogue's own layer (KS_DTM) downloads a block holding data from the local host by ranges: a table made by
    the tool for a written file of 06NE4's quarter, the block's values the file's own pixels (within LERC's 5 mm),
    cached in the layer's folder; a second download asks nothing."""
    import forest_files
    band = np.full((1024, 1024), -9999.0, dtype=np.float32)
    band[:, :700] = 300.0 + np.add.outer(np.arange(1024), np.arange(700)).astype(np.float32) * 0.07
    data = _written(str(tmp_path / "f.tif"), band)
    rows, _ = _masked({"06NE4": data})
    row = {**rows["06NE4"], "record": "kitaise", "key": "k/dem_06ne4_2025.tif"}
    table = str(tmp_path / "t.npz")
    forest_files.save(table, [row])
    monkeypatch.setattr(jf, "rf_table", lambda: jf.load_table(table))
    monkeypatch.setattr(jf, "RF_BUCKET", http_server.base)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    http_server.add("/k/dem_06ne4_2025.tif", data, "image/tiff")
    cache_dir = str(tmp_path / "cache")
    grid = make_grid((20_001, -105_499, 20_499, -105_001), 0.5, jf.KS_CRS)
    assert jf.KS_DTM.tiles(grid) == [(40, -211)]
    jf.KS_DTM.download(grid, cache_dir, None, "terrain")
    path = jf.KS_DTM.tile_path(cache_dir, (40, -211))
    assert path.replace(os.sep, "/").endswith(f"{jf.KS_DTM.folder}/0_-5/40_-211.tif")
    with rio.open(path) as block:
        values = block.read(1)
        assert block.tags()["sources"] == "kitaise_06NE4"
    expected = band[:1000, :1000].copy()
    expected[expected == -9999] = np.nan
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.0051)
    n = len(http_server.requests("/k/"))
    jf.KS_DTM.download(grid, cache_dir, None, "terrain")
    assert len(http_server.requests("/k/")) == n


# --- the layer -------------------------------------------------------------------------------------------------------
@pytest.fixture
def ne4_served(http_server, monkeypatch):
    """06NE4 at the local server where the catalogue's layer looks for it (RF_BUCKET), answered from the recorded
    pieces range by range."""
    monkeypatch.setattr(jf, "RF_BUCKET", http_server.base)
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)
    pieces, size = _pieces()
    return pieces, _serve_pieces(http_server, "/" + NE4_KEY, pieces, size)


def test_recorded_window_through_the_layer(ne4_served, http_server, tmp_path, monkeypatch):
    """The catalogue's reader (Windows, range by range) reads a window of the recorded file from the host by ranges
    (the header, then the one tile under the window: tile 54, 48 of 06NE4, 4 832 valid pixels near its north-east
    corner), on the file's own 0.5 m pixels without resampling: equal to the tile decoded by hand within LERC's
    5 mm, tagged with the file, and never through the bilinear branch (windows.reproject): on Kitaise's grid a bilinear
    read gives the same values within 1e-9 m (its tags' float noise), so the values alone cannot tell it, the branch
    taken can. The block's files are the layer's own (files(i, j))."""
    from sources.readers import windows
    resampled = []
    real_reproject = windows.reproject
    monkeypatch.setattr(windows, "reproject", lambda *a, **k: resampled.append(1) or real_reproject(*a, **k))
    pieces, asked = ne4_served
    layer = jf.KS_DTM
    # file columns 28 040-28 155, rows 24 578-24 687: a bilinear read's margin (2 px and the tags' float noise) stays
    # in the recorded tile
    left, top, shape = 34_020.0, -117_289.0, (110, 116)
    files = layer.index.request((68, -235)).files
    assert [n for n, _, _ in files] == ["kitaise_06NE4"] and files[0][1] == f"{http_server.base}/{NE4_KEY}"
    request = BlockRequest(files, jf.KS_CRS, from_origin(left, top, 0.5, 0.5), shape)
    path = str(tmp_path / "window.tif")
    assert layer.reader.fetch(request, path).received > 0
    expected = _decode_window(pieces, left, top, shape)
    with rio.open(path) as window:
        values = window.read(1)
        assert window.crs.to_epsg() == 6674 and window.transform == from_origin(left, top, 0.5, 0.5)
        assert window.tags()["sources"] == "kitaise_06NE4" and window.tags()["years"] == "2023"
    assert 0 < np.isfinite(expected).sum() < expected.size
    assert np.array_equal(np.isnan(values), np.isnan(expected))
    assert np.allclose(values[np.isfinite(values)], expected[np.isfinite(expected)], atol=0.0051)
    assert not resampled  # read on the file's own pixels (windows._coincide), not resampled
    tile = min(o for o in pieces if len(pieces[o]) == 13569)
    assert any(a <= tile and tile + 13569 - 1 <= b for a, b in asked)  # the tile, by a range
    assert sum(b - a + 1 for a, b in asked) < 200_000  # the header and a tile, not the file's 380 MB


def test_recorded_block_without_data_inside_is_missing(ne4_served, http_server, tmp_path):
    """The recorded block x 33 500-34 000, y -118 000..-117 500: its masks say data (two of its nine tiles hold some),
    but none of their valid pixels lies in the block: the layer reads it once (its tiles, by ranges) and records it as
    missing, no file; a second search asks nothing."""
    pieces, asked = ne4_served
    layer = jf.KS_DTM
    cache_dir = str(tmp_path)
    left, bottom = BLOCK[0] * 500, BLOCK[1] * 500
    assert np.isnan(_decode_window(pieces, left, bottom + 500)).all()
    grid = make_grid((left + 1, bottom + 1, left + 499, bottom + 499), 0.5, jf.KS_CRS)
    assert layer.tiles(grid) == [BLOCK]
    layer.download(grid, cache_dir, None, "terrain")
    path = layer.tile_path(cache_dir, BLOCK)
    assert not os.path.exists(path) and not cache.due(cache_dir, path)
    assert sum(b - a + 1 for a, b in asked) < 200_000
    n = len(http_server.requests("/" + NE4_KEY))
    layer.download(grid, cache_dir, None, "terrain")
    assert len(http_server.requests("/" + NE4_KEY)) == n


# --- the source ------------------------------------------------------------------------------------------------------
def test_mie_catalogue_entry():
    """The catalogue's own settings: region jp-24, zone VI, the Kitaise record's files read in blocks of 500 m range by
    range (two connections at once to the bucket), the credit in the Agency's form for local bodies' surveys (PDL1.0)
    with the edited work's sentence, no surface model, no neighbours, europe where no data lie near."""
    source = src.SOURCES["mie"]
    assert source.regions == ("jp-24",) and source.countries == ("jp",) and source.crs == "EPSG:6674"
    assert source.nmt is jf.KS_DTM and source.nmpt is None and source.credits == (jf.KS_CREDIT,)
    assert source.neighbours == () and source.border_boxes == () and source.instead_without_data == "europe"
    layer = jf.KS_DTM
    assert isinstance(layer.index, jf.RfBlockTiling) and layer.reader.serial and not layer.reader.ranged
    assert layer.native_res == 0.5 and layer.block_m == 500 and layer.folder == "mie/kitaise-dem/2025-20261002"
    assert jf.rf_stamp("kitaise") == "20261002"  # the newest Last-Modified of Kitaise's files in the table
    assert layer.reader.warp is None and layer.reader.geoid is None and layer.bytes_per_tile() == 2.3e6
    assert jf.RF_BUCKET == "https://gsic-opendata.s3.ap-northeast-1.amazonaws.com"
    credit = jf.KS_CREDIT
    assert credit.licence == "PDL 1.0" and credit.url == jf.PDL[1]
    for text in ("出典：国土交通省土地・建設産業局地籍整備課、東海農政局木曽川水系土地改良調査管理事務所、三重県森林・林業経営課、"
                 "津市農林水産部林業振興室、菰野町産業観光課・三重県（北伊勢森林計画区）DEM（林野庁加工）", jf.KS_RECORD, "PDL1.0（"):
        assert text in credit.attribution, text
    assert "をもとにFind-a-Lineが作成" in credit.notice and "not made by" in credit.notice
    assert src.net.HOST_SLOTS_OF["gsic-opendata.s3.ap-northeast-1.amazonaws.com"] == 2
    assert src.net.HOST_SLOTS_OF["www.geospatial.jp"] == 2
    assert source.sample == (35.0217, 136.4281) and layer.has_data_near(*source.sample, "") is True
    assert "2013-2023" in source.note and source.coverage.partial and source.coverage.survey == "2013–2023"


@pytest.mark.parametrize("sid, inside, outside, neighbour", [
    ("yamagata", (38.6013, 139.7778), (38.2554, 140.3397), (38.5212, 139.5984)),   # Niigata's part of 10PB1
    ("nagano", (35.7448, 137.8643), (36.6486, 138.1948), (35.7802, 138.2034)),     # Yamanashi's part of 08KD3
    ("hiroshima", (34.6332, 133.1886), (34.8580, 133.0170), None),                 # zone III's data all Hiroshima's
    ("okayama", (34.7827, 133.4858), (34.3963, 132.4596), (35.3453, 133.5954)),    # Tottori's part of 05MC1
    ("ishikawa", (37.1185, 137.0093), (36.5613, 136.6562), (36.8050, 136.8633))])  # Toyama's part of 07HD1
def test_stage_two_sources(sid, inside, outside, neighbour, monkeypatch, tmp_path):
    """yamagata (Shonai, zone X), nagano (Inadani, zone VIII), hiroshima and okayama (h30's zones III and V) and
    ishikawa (r6's zone VII): their entries, credits in the local bodies' variant with the notes' names (Inadani's
    with the forestry department's approval; h30's 林野庁、岡山県) or the Agency's own (r6), folders named by the record
    and its state, has_data_near inside the data, far from it (Yamagata city, Nagano city, Shobara, Hiroshima city for
    okayama, Kanazawa: europe without a request) and inside a neighbouring prefecture's part of the files (true: the
    files' data are not cut at the border)."""
    def no_request(*args, **kwargs):
        raise AssertionError("a request")
    monkeypatch.setattr(src.net, "_get", no_request)
    source = src.SOURCES[sid]
    layer = source.nmt
    record, zone, crs, region = {"yamagata": ("syounai", 10, "EPSG:6678", "jp-06"),
                                 "nagano": ("inatani", 8, "EPSG:6676", "jp-20"),
                                 "hiroshima": ("h30", 3, "EPSG:6671", "jp-34"),
                                 "okayama": ("h30", 5, "EPSG:6673", "jp-33"),
                                 "ishikawa": ("r6", 7, "EPSG:6675", "jp-17")}[sid]
    assert source.regions == (region,) and source.crs == crs and source.instead_without_data == "europe"
    assert isinstance(layer, jf.RfBlocks) and layer.reader.serial and layer.index.records == (record,)
    assert layer.bytes_per_tile() == {"yamagata": 0.63e6, "nagano": 0.68e6, "hiroshima": 1.67e6, "okayama": 0.55e6,
                                      "ishikawa": 1.35e6}[sid]  # GDAL's downloads in the entries' cold searches
    assert layer.folder == f"{sid}/{record}-dem/2025-{jf.rf_stamp(record)}"
    assert all(r.epsg == 6668 + zone for r in jf.rf_rows((record,), zone))
    assert layer.has_data_near(*inside, str(tmp_path)) is True
    assert layer.has_data_near(*outside, str(tmp_path)) is False
    assert neighbour is None or layer.has_data_near(*neighbour, str(tmp_path)) is True
    credit = source.credits[0]
    assert credit.licence == "PDL 1.0" and "をもとにFind-a-Lineが作成" in credit.notice
    if sid == "yamagata":
        assert credit.attribution.startswith("出典：山形県森林ノミクス課及び庄内町農林課・山形県（庄内森林計画区）DEM（林野庁加工）")
        assert source.neighbours == () and source.border_boxes == ()
    elif sid in ("hiroshima", "okayama"):  # one record, two zones: 11.3 km apart, no neighbour pair (gate 5)
        assert credit.attribution.startswith(f"出典：林野庁、岡山県・平成30年7月豪雨 DEM（林野庁加工）（{jf.H30_RECORD}）、PDL1.0（")
        assert source.neighbours == () and source.border_boxes == () and source.credits == (jf.H30_CREDIT,)
        assert source.coverage.survey == "2018" and jf.H30_YEARS == {"h30": 2018}
    elif sid == "ishikawa":
        assert credit.attribution == f"出典：林野庁（{jf.R6_RECORD}）、PDL1.0（{jf.PDL[1]}）"
        assert source.neighbours == () and source.coverage.survey == "2024" and jf.R6_YEARS == {"r6": 2024}
    else:
        assert credit.attribution.startswith("出典：長野県森林政策課及び同県森林づくり推進課・長野県（伊那谷森林計画区）DEM（林野庁加工）"
                                             "（長野県林務部長承認（承認番号７森政第51-2号）に基づき林野庁作成）")
        assert source.neighbours == ("yamanashi", "shizuoka")
        assert "nagano" in src.SOURCES["yamanashi"].neighbours and "nagano" in src.SOURCES["shizuoka"].neighbours
    monkeypatch.setattr(src.choose, "country_code", lambda lat, lon, cache_dir: "jp")
    monkeypatch.setattr(src.choose, "region_codes", lambda lat, lon, cache_dir, code: (region,))
    assert src.choose_source("auto", *inside, str(tmp_path))[0].id == sid
    assert src.choose_source("auto", *outside, str(tmp_path))[0].id == "europe"


def test_agency_credit_variant():
    """The Agency's own variant (h28, r2, r6's important notes): 出典：林野庁（<record>）、PDL1.0（<terms>）, the edited work's
    sentence in the notice."""
    credit = jf.rf_agency_credit("r6", "https://www.geospatial.jp/ckan/dataset/r6_noto-peninsula-earthquake")
    assert credit.attribution == ("出典：林野庁（https://www.geospatial.jp/ckan/dataset/r6_noto-peninsula-earthquake）、PDL1.0（"
                                  f"{jf.PDL[1]}）")
    assert credit.notice.startswith("出典：林野庁（") and "をもとにFind-a-Lineが作成" in credit.notice


def test_mie_offline_boxes():
    """Mie's offline boxes (region jp-24) hold the data's places, not the plain without data: Gozaisho, the Nunobiki
    hills, Kameyama's forests; not Yokkaichi's port, Tsu's station or Ise."""
    from sources import choose
    source = src.SOURCES["mie"]
    assert all(region == "jp-24" for region, _ in source.offline) and source.offline == jf.KS_BOXES

    def offline(lat, lon):
        return next((region for region, (s, n, w, e) in choose.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e),
                    None)
    for lat, lon in ((35.0217, 136.4281), (34.6000, 136.3000), (34.9000, 136.4000)):
        assert offline(lat, lon) == "jp-24", (lat, lon)
    for lat, lon in ((34.9650, 136.6400), (34.7339, 136.5103), (34.4870, 136.7090)):
        assert offline(lat, lon) is None, (lat, lon)


def test_the_agencys_family_before_japans_offline():
    """The Agency's sources come before japan's in SOURCES, so offline their boxes, cut to their data, win over
    Shizuoka's rough ones on Nagano's land (the first box holding a point wins): a place of Nagano inside both goes
    to nagano; one of Nagano that only Yamanashi's box holds stays Yamanashi's, in either order (Inadani has no data
    there). With japan first 478 lattice points of Nagano's land went to shizuoka, this way round 195, and 35 of
    Shizuoka's go to nagano (0.005 degrees, at least 300 m inside the prefecture, 2026-11-28)."""
    from sources import choose
    order = list(src.SOURCES)
    assert max(order.index(s.id) for s in jf.SOURCES) < min(order.index(s) for s in ("kanagawa", "yamanashi"))

    def offline(lat, lon):
        return next((region for region, (s, n, w, e) in choose.OFFLINE_BOXES if s <= lat <= n and w <= lon <= e),
                    None)
    assert offline(35.2075, 137.8225) == "jp-20"   # Nagano's Tenryu, also inside a box of Shizuoka's
    assert any(region == "jp-22" and s <= 35.2075 <= n and w <= 137.8225 <= e
               for region, (s, n, w, e) in choose.OFFLINE_BOXES)
    assert offline(35.7525, 138.1825) == "jp-19"   # Nagano's land in Yamanashi's box only
