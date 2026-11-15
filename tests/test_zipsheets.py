"""ZipSheetTiles (sheets of a fixed table made of "x y z" members of remote ZIP archives, read by Range from the
addresses their stable links redirect to) against a fake server and the recorded directories of OSNI's 10 m DTM
(tests/data/recorded/zipsheets/osni-dtm10/), and the catalogue's northern_ireland_10m."""

import gzip
import io
import json
import os
import sys
import zipfile

import numpy as np
import pytest
import rasterio as rio

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import cache  # noqa: E402
import sources as src  # noqa: E402
from grid import make_grid  # noqa: E402
from http_server import Answer  # noqa: E402
from sources.catalogue import uk  # noqa: E402
from sources.layers.zipsheets import ZipSheetIndex, ZipSheetTiles  # noqa: E402
from sources.readers import zipmember  # noqa: E402

RECORDED = os.path.join(HERE, "tests", "data", "recorded", "zipsheets", "osni-dtm10")
CRS = "EPSG:29903"
# A small fake sheet table: sheet 1 of 200 x 100 m, sheet 2 east of it, sheet 11 far away (the recorded member)
SHEETS = {1: (300000, 440000, 300200, 440100), 2: (300200, 440000, 300400, 440100),
          11: (264800, 431200, 274400, 437600)}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(src.net, "_sleep", lambda attempt: None)


def _height(x, y):
    """A plane within every kilometre square (sheet 1, 2 and the piece of sheet 11 lie within one each)."""
    return 100.0 + ((x - 300000) % 1000) * 0.5 + ((y - 440000) % 1000) * 0.25


def _xyz(box, step=10.0, holes=False) -> bytes:
    """Cell centres on x5 (as OSNI's), heights of _height; without the points of a corner (the sea)."""
    left, bottom, right, top = box
    lines = []
    for y in np.arange(top - step / 2, bottom, -step):
        for x in np.arange(left + step / 2, right, step):
            if holes and x < left + 50 and y < bottom + 30:
                continue
            lines.append(f"{x:.4f}     {y:.4f}     {_height(x, y):12.4f}")
    return ("\n".join(lines) + "\n \n").encode()


def _archive(members) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def _serve(server, archives):
    """Archives at /files/<name>, each behind a stable link /dl/<name> that redirects to it (as OpenDataNI's
    downloads redirect to signed addresses); returns the links."""
    links = []
    for name, body in archives.items():
        server.add(f"/files/{name}", body, "application/zip", headers={"ETag": f'"{len(body)}"'})
        server.add(f"/dl/{name}", b"", "text/html", status=302,
                   headers={"Location": server.url(f"/files/{name}")})
        links.append(server.url(f"/dl/{name}"))
    return links


def _layer(links, folder="fake/osni-dtm10"):
    return ZipSheetTiles("Fake 10 m DTM", links, uk.NI_10M_MEMBER, SHEETS, CRS, folder, "fake-dtm10", 10.0,
                         margin=1000.0)


def _grid(box, res=10.0):
    return make_grid(box, res, CRS)


def test_recorded_directories_name_the_sheets():
    """OSNI's six archives as their central directories listed them on 2026-11-15: 293 entries, one a folder, one
    name with a space before ".txt", sheets 51-100 under a folder, sheet 11 in two members (011 and 011a), no
    member for sheets 287 and 290, a sheet 293 of 49 points (a beach west of sheet 1) that the 10k grid lacks."""
    with open(os.path.join(RECORDED, "directories.json"), encoding="utf-8") as f:
        recorded = json.load(f)
    kept = {"archives": [{"link": name, "etag": None, "length": 0, "members": members}
                         for name, members in recorded.items()]}
    index = ZipSheetIndex(list(recorded), uk.NI_10M_MEMBER, uk.NI_10K_SHEETS, CRS, "x/y", "k")
    sheets = index._sheets(kept)
    assert len(sheets) == 291 and set(range(1, 294)) - set(sheets) == {287, 290}
    assert [m.member for m in sheets[11]] == ["Sheet011av2.txt", "Sheet011v4.txt"]
    assert [m.member for m in sheets[154]] == ["Sheet154v5 .txt"]
    assert sheets[51][0].member == "OSNI_10M_DTM_Sheets_51-100/Sheet051v4.txt"
    assert all(len(v) == 1 for k, v in sheets.items() if k != 11)
    assert set(sheets) <= set(uk.NI_10K_SHEETS) and len(uk.NI_10K_SHEETS) == 293
    assert uk.NI_10K_SHEETS[46] == (332000, 412000, 336800, 418400)   # OSNI's 10k grid, two quarters
    assert uk.NI_10K_SHEETS[230] == (226400, 335200, 236000, 341600)  # four quarters of 4.8 x 3.2 km


def test_recorded_member_is_a_grid_of_centres_on_x5():
    """The recorded member Sheet011av2.txt (a beach west of sheet 11, beyond its box: the reason for the margin):
    "x y z" lines of 10 m cell centres on x5, heights with four decimals, the sea without points."""
    from sources.readers.sheetfile import _xyz_grid
    with gzip.open(os.path.join(RECORDED, "Sheet011av2.txt.gz"), "rb") as f:
        data = f.read()
    band, transform = _xyz_grid(data, 10.0, CRS)
    assert (transform.a, transform.e) == (10.0, -10.0) and transform.c % 10 == 0 and transform.f % 10 == 0
    assert (transform.c, transform.f) == (263960.0, 432940.0) and band.shape == (153, 84)
    assert np.isfinite(band).sum() == 11026 and np.nanmin(band) == pytest.approx(-0.24)
    assert transform.c < SHEETS[11][0] < transform.c + 1000  # within the margin west of its sheet


def test_sheets_downloaded_and_stitched(http_server, tmp_path):
    """Two archives (one member under a folder), a grid over sheets 1 and 2: each sheet one raster on its centres'
    pixels (edges on multiples of 10 m: the grid copies it), the plane exact, the sea's corner NaN; sheet 11 (its
    two members, one the recorded beach) read when a grid reaches its margin; no HEAD to a file, only Ranges."""
    with gzip.open(os.path.join(RECORDED, "Sheet011av2.txt.gz"), "rb") as f:
        beach = f.read()
    links = _serve(http_server, {
        "a.zip": _archive([("Sheet001v4.txt", _xyz(SHEETS[1], holes=True)), ("Sheet011av2.txt", beach),
                           ("Sheet011v4.txt", _xyz((264800, 431200, 264900, 431300)))]),
        "b.zip": _archive([("Folder/", b""), ("Folder/Sheet002v5 .txt", _xyz(SHEETS[2]))])})
    layer = _layer(links)
    cache_dir = str(tmp_path / "cache")
    grid = _grid((300000, 440000, 300400, 440100))
    out = src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "w" / "dtm.npy"), "terrain")
    mosaic = np.load(out)
    rows, cols = np.mgrid[0:grid.height, 0:grid.width]
    x, y = grid.transform @ (cols + 0.5, rows + 0.5)
    want = _height(x, y)
    hole = (x < 300050) & (y < 440030)
    assert np.isnan(mosaic[hole]).all() and np.abs(mosaic[~hole] - want[~hole]).max() < 0.01
    assert [t.sheet for t in layer.tiles(grid)] == [1, 2]
    path = layer.tile_path(cache_dir, layer.tiles(grid)[0])
    assert os.path.basename(path).startswith("001_") and os.path.exists(path)
    with rio.open(path) as cached:
        assert cached.crs.to_string() == CRS and (cached.transform.c, cached.transform.f) == (300000.0, 440100.0)
    beach_grid = _grid((263000, 431000, 266000, 433000))
    assert [t.sheet for t in layer.tiles(beach_grid)] == [11]
    src.prepare_layer(layer, beach_grid, cache_dir, str(tmp_path / "w" / "b.npy"), "terrain")
    assert len(layer.tiles(beach_grid)[0].members) == 2
    beach = np.load(str(tmp_path / "w" / "b.npy"))
    rows, cols = np.mgrid[0:beach_grid.height, 0:beach_grid.width]
    bx, by = beach_grid.transform @ (cols + 0.5, rows + 0.5)
    second = (bx > 264800) & (bx < 264900) & (by > 431200) & (by < 431300)  # Sheet011v4.txt's points
    assert second.sum() == 100 and np.abs(beach[second] - _height(bx[second], by[second])).max() < 0.01
    first = (bx > 263970) & (bx < 264790) & (by > 431420) & (by < 432930)  # the recorded beach (011a)
    assert np.isfinite(beach[first]).mean() > 0.8
    asked = http_server.requests("/files/")
    assert asked and all(r.method == "GET" and r.headers.get("range", "").startswith("bytes=") for r in asked)
    assert "bytes=0-0" not in [r.headers.get("range") for r in asked]
    # The directories are kept: a second layer over the same data folder asks no directory again
    before = len(http_server.requests("/"))
    again = _layer(links)
    again.index.use(cache_dir)
    assert [t.sheet for t in again.tiles(grid)] == [1, 2] and len(http_server.requests("/")) == before


def test_faults(http_server, tmp_path):
    """A range answer cut short is asked again (and then read); a server answering a Range with the whole file is
    refused unread; a link that answers 404 makes the directories unreadable (no tile known: None)."""
    body = _archive([("Sheet001v4.txt", _xyz(SHEETS[1]))])
    links = _serve(http_server, {"a.zip": body})
    cut, seen = [], []

    def first_member_range(n, header):
        """The member's range, the first time only: in a small archive the directory's tail and the member's
        range are both bytes=0-<end> (the tail asked first)."""
        if header.startswith("bytes=0-") and header != "bytes=0-1":
            seen.append(header)
            if len(seen) == 2:
                cut.append(header)
                return True
        return False
    http_server.fault("/files/a.zip", "truncate", first_member_range)
    layer = _layer(links)
    cache_dir = str(tmp_path / "cache")
    grid = _grid(SHEETS[1])
    src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "w" / "a.npy"), "terrain")
    assert np.isfinite(np.load(str(tmp_path / "w" / "a.npy"))).all() and len(cut) == 1
    # The whole file for a Range (200): refused, nothing kept
    http_server.answers.clear()
    http_server.add("/dl/c.zip", b"", "text/html", status=302, headers={"Location": http_server.url("/files/c.zip")})
    http_server.answers[("GET", "/files/c.zip", ())] = Answer(200, body, {"Content-Type": "application/zip"},
                                                               ranges=False)
    refused = _layer([http_server.url("/dl/c.zip")], folder="fake/c")
    refused.index.use(str(tmp_path / "c"))
    assert refused.tiles(grid) is None
    gone = _layer([http_server.url("/dl/gone.zip")], folder="fake/gone")
    gone.index.use(str(tmp_path / "g"))
    assert gone.tiles(grid) is None


def test_a_replaced_archive_is_read_again(http_server, tmp_path):
    """The archive replaced after its directory was kept (another member first: the kept offset holds another
    member's header): the directories are read again and the sheet read from where they say now."""
    first = _archive([("Sheet001v4.txt", _xyz(SHEETS[1]))])
    links = _serve(http_server, {"a.zip": first})
    layer = _layer(links)
    cache_dir = str(tmp_path / "cache")
    grid = _grid(SHEETS[1])
    layer.index.use(cache_dir)
    tile = layer.tiles(grid)[0]
    second = _archive([("Sheet002v4.txt", _xyz(SHEETS[2])), ("Sheet001v4.txt", _xyz(SHEETS[1]))])
    http_server.add("/files/a.zip", second, "application/zip", headers={"ETag": '"other"'})
    fetched = layer.download_tile(tile, str(tmp_path / f"001_{tile.key}.tif"))
    written = [n for n in os.listdir(tmp_path) if n.startswith("001_")]
    assert fetched.received > 0 and written == [f"001_{tile.key}.tif"]  # the same CRC-32: the same key, another offset


def test_catalogue_chain():
    """northern_ireland's gaps come from the 10 m DTM, then europe; inland Northern Ireland takes the 10 m DTM."""
    ni, ten = src.SOURCES["northern_ireland"], src.SOURCES["northern_ireland_10m"]
    assert ni.fallbacks == ["northern_ireland_10m", "europe"] and ni.instead_without_data == "northern_ireland_10m"
    assert ten.fallbacks == ["europe"] and ten.default_resolution == 10.0 and ten.crs == CRS
    assert ten.regions == ("gb-nir",) and ten.coverage is None and isinstance(ten.nmt, ZipSheetTiles)
    assert len(ten.nmt.archives) == 6
    assert all(a.startswith("https://admin.opendatani.gov.uk/") for a in ten.nmt.archives)
    assert ten.nmt.has_data_near(54.1802, -5.9208, "unused") and not ten.nmt.has_data_near(53.35, -6.26, "unused")
    from sources import probe
    assert probe.strategy(ten.nmt) == "zipsheets"



SIGNED = "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=CRED123&X-Amz-Signature=SIG456&X-Amz-Security-Token=TOK789"


def test_signed_queries_are_masked():
    """cache.clean_url and clean_error mask a signed URL's X-Amz-* values (and Signature=), also URL-encoded."""
    url = "https://bucket.example.r2.cloudflarestorage.com/a.zip" + SIGNED
    for text in (cache.clean_url(url), cache.clean_error(f"HTTP 404 for {url}"),
                 cache.clean_error("redirected to X-Amz-Signature%3DSIG456&X-Amz-Credential=CRED123 then"),
                 cache.clean_url("https://h/a?Signature=SIG456&x=1")):
        assert "CRED123" not in text and "SIG456" not in text and "TOK789" not in text, text
    assert cache.clean_url(url).startswith("https://bucket.example.r2.cloudflarestorage.com/a.zip?X-Amz-Algorithm=...")


def _signed_serve(server, name, body, etag='"1"'):
    """An archive at a signed-looking address (its query X-Amz-*), its stable link redirecting there."""
    query = SIGNED.lstrip("?")
    server.add(f"/files/{name}?{query}", body, "application/zip", headers={"ETag": etag})
    server.add(f"/dl/{name}", b"", "text/html", status=302,
               headers={"Location": server.url(f"/files/{name}?{query}")})
    return server.url(f"/dl/{name}")


def test_no_signed_query_in_an_error(http_server, tmp_path):
    """The archive gone after its directory was kept (a 404 at the signed address; renew keeps the directory it
    had): the error names the sheet, never the signed address's query."""
    body = _archive([("Sheet001v4.txt", _xyz(SHEETS[1]))])
    link = _signed_serve(http_server, "a.zip", body)
    layer = _layer([link])
    layer.index.use(str(tmp_path / "cache"))
    tile = layer.tiles(_grid(SHEETS[1]))[0]
    http_server.answers = {k: v for k, v in http_server.answers.items() if k[1] != "/files/a.zip"}
    with pytest.raises(RuntimeError) as raised:
        layer.download_tile(tile, str(tmp_path / "t.tif"))
    text = str(raised.value)
    assert "sheet 1" in text and "SIG456" not in text and "CRED123" not in text and "TOK789" not in text


def test_a_member_replaced_in_place(http_server, tmp_path):
    """The archive's first member replaced in place (same name and offset, other heights): its CRC-32 differs after
    the retries, the directories are read again, the sheet written under its new key and the older version deleted
    and recorded in the cache's index as the new key."""
    link = _signed_serve(http_server, "a.zip", _archive([("Sheet001v4.txt", _xyz(SHEETS[1]))]))
    layer = _layer([link])
    cache_dir = str(tmp_path / "cache")
    grid = _grid(SHEETS[1])
    src.prepare_layer(layer, grid, cache_dir, str(tmp_path / "w" / "a.npy"), "terrain")
    old = layer.tiles(grid)[0]
    old_path = layer.tile_path(cache_dir, old)
    assert os.path.exists(old_path)
    other = _xyz(SHEETS[1]).replace(b"     1", b"     2")  # other heights, the same name and offset
    query = SIGNED.lstrip("?")
    http_server.add(f"/files/a.zip?{query}", _archive([("Sheet001v4.txt", other)]), "application/zip",
                    headers={"ETag": '"2"'})
    fetched = layer.download_tile(old, old_path)
    new = layer.tiles(grid)[0]
    new_path = layer.tile_path(cache_dir, new)
    assert fetched.received > 0 and new.key != old.key and os.path.exists(new_path) and not os.path.exists(old_path)
    assert cache.states(cache_dir, [new_path]) == ["ok"]


def test_a_length_not_stated_keeps_the_directories(http_server, tmp_path, capsys):
    """An archive answering the first two bytes with "Content-Range: bytes 0-1/*" (no length): the directories
    cannot be read again, the kept ones are used."""
    body = _archive([("Sheet001v4.txt", _xyz(SHEETS[1]))])
    links = _serve(http_server, {"a.zip": body})
    layer = _layer(links)
    layer.index.use(str(tmp_path / "cache"))
    grid = _grid(SHEETS[1])
    assert [t.sheet for t in layer.tiles(grid)] == [1]
    del http_server.answers[("GET", "/files/a.zip", ())]
    http_server.route("/files/a.zip", lambda request: Answer(206, body[:2], {
        "Content-Range": "bytes 0-1/*", "Content-Type": "application/zip"}, ranges=False))
    assert layer.index.table(force=True) is not None
    assert "length is not stated" in capsys.readouterr().out
    assert [t.sheet for t in layer.tiles(grid)] == [1]


def test_cached_sheets_without_directories_take_the_newest(tmp_path):
    """No kept directories and no answer (the links are gone): each sheet's newest cached file, never two."""
    import time
    from rasterio.transform import from_origin
    layer = _layer(["http://127.0.0.1:9/dl/none.zip"])
    cache_dir = str(tmp_path / "cache")
    folder = os.path.join(cache_dir, layer.folder)
    os.makedirs(folder)
    for key in ("ffffffff", "00000000"):  # the second written later, though its key sorts first
        with rio.open(os.path.join(folder, f"001_{key}.tif"), "w", driver="GTiff", width=2, height=2, count=1,
                      dtype="float32", crs=CRS, transform=from_origin(300000, 440100, 10, 10)) as dst:
            dst.write(np.ones((1, 2, 2), dtype=np.float32))
        time.sleep(0.05)
    os.utime(os.path.join(folder, "001_ffffffff.tif"), (1_000_000, 1_000_000))
    files = layer.files(_grid(SHEETS[1]), cache_dir)
    assert [os.path.basename(f) for f in files] == ["001_00000000.tif"]


def test_an_empty_member_is_missing(http_server, tmp_path):
    """A sheet whose member holds no point (blank lines only): missing, no file, no error."""
    links = _serve(http_server, {"a.zip": _archive([("Sheet001v4.txt", b" \n \n")])})
    layer = _layer(links)
    layer.index.use(str(tmp_path / "cache"))
    tile = layer.tiles(_grid(SHEETS[1]))[0]
    path = str(tmp_path / "t.tif")
    assert layer.download_tile(tile, path).received == 0 and not os.path.exists(path)
