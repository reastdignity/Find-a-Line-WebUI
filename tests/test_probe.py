"""The source probe (sources/probe.py, `findaline.py sources check`) with fake layers and requests."""

import os
import sys
import time

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sources as src  # noqa: E402
import update  # noqa: E402
from sources import probe  # noqa: E402
from sources.indexes.cached import CachedIndex, Listing  # noqa: E402
from sources.indexes.versions import NewestPerSheet  # noqa: E402
from sources.readers.download import Download  # noqa: E402

SAMPLE = (50.5, 19.5)
ORTHO = src.OrthoService("Fake orthophoto", None, "", "fake/ortho", "fake",
                         base_url="https://ortho.example/{z}/{x}/{y}.jpg")


class Tiles(src.DegreeTiles):
    def __init__(self, host: str = "files.example", slow: float = 0):
        super().__init__(f"Tiles of {host}", "fake/tiles", lambda lat, lon: f"https://{host}/{lat}_{lon}.tif")
        self.slow = slow

    def tiles(self, grid):
        time.sleep(self.slow)
        return super().tiles(grid)


class FakeListing(Listing):
    """A listing that cannot be reached (error), or lists nothing there."""
    url = "https://index.example/wfs"

    def __init__(self, error: bool):
        self.error = error

    def fetch(self, lat, lon):
        if self.error:
            raise requests.ConnectionError("refused")
        return {"sheets": []}


class Index(src.IndexedTiles):
    """An index that cannot be reached (error), or lists nothing there (an empty list)."""
    index_crs = "EPSG:2180"

    def __init__(self, error: bool):
        super().__init__("Fake index", FakeListing.url, "fake", "fake/index", 1.0, 1e6)
        self.index = CachedIndex(self.description, FakeListing(error),
                                 NewestPerSheet(self.folder, self.index_crs, self.native_res), self.prefix, "fake")
        self.reader = Download(self.description, lambda tile: tile.url, lambda tile: tile.godlo)


def _source(sid: str, nmt, nmpt=None, sample=SAMPLE, ortho=None) -> src.Source:
    return src.Source(id=sid, name=sid, description=sid, nmt=nmt, nmpt=nmpt, sample=sample, ortho=ortho)


@pytest.fixture
def asked(monkeypatch):
    """The requests of the probe: a 404 from gone.example, an exception report from a WCS asked for
    its coverage at bad.example, a byte or an image elsewhere."""
    calls = []

    def fake(url, params=None, headers=None):
        calls.append((url, params, headers))
        if "gone.example" in url:
            return 404, "text/html", b"not found"
        if "wcs" in url:
            request = dict(params).get("REQUEST")
            if request == "GetCoverage" and "bad.example" in url:
                return 200, "application/xml", b"<ows:ExceptionReport>no such subset"
            return 200, "image/tiff" if request == "GetCoverage" else "text/xml", b"<wcs:CoverageDescriptions>"
        return (206, "image/tiff", b"x") if headers and "Range" in headers else (200, "image/jpeg", b"x")
    monkeypatch.setattr(probe, "_http", fake)
    return calls


def _run(tmp_path, sources, ids=(), **kwargs):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    code = probe.run(str(cache_dir), ids, sources=sources, **kwargs)
    assert set(os.listdir(cache_dir)) <= {"locks"}  # only the hosts' lock files
    return code


def test_failures_are_reported_and_the_rest_checked(tmp_path, capsys, asked):
    shared = Tiles()
    sources = {"broken": _source("broken", Index(error=True)), "empty": _source("empty", Index(error=False)),
               "gone": _source("gone", Tiles("gone.example")),
               "good": _source("good", shared, Tiles("surface.example"), ortho=ORTHO),
               "again": _source("again", shared, ortho=ORTHO)}
    assert _run(tmp_path, sources) == 1
    out = capsys.readouterr().out
    rows = {tuple(line.split()[:2]): line for line in out.splitlines()[1:] if line.strip()}
    broken = rows[("broken", "terrain")]
    assert "FAIL" in broken and "index not available (ConnectionError)" in broken
    assert "no tile at the sample point" in rows[("empty", "terrain")]
    assert "HTTP 404" in rows[("gone", "terrain")]
    for what in ("terrain", "surface", "orthophoto"):  # 1° tiles and base tiles: no index, read
        assert rows[("good", what)].split()[2:4] == ["-", "ok"]
    assert "as good" in rows[("again", "terrain")] and "as good" in rows[("again", "orthophoto")]
    assert "5 checked, 3 failed, 0 skipped" in out
    # One byte of each file; the orthophoto's tile at zoom 15 around the sample
    ranged = [url for url, _, headers in asked if headers]
    assert ranged == ["https://gone.example/50_19.tif", "https://files.example/50_19.tif",
                      "https://surface.example/50_19.tif"]
    assert [url for url, _, _ in asked if "ortho" in url] == ["https://ortho.example/15/18158/11041.jpg"]


def test_skipped_sources(tmp_path, capsys, asked, monkeypatch):
    monkeypatch.delenv(src.MIRROR_ENV, raising=False)
    api = src.OpenTopographyTiles("Fake API", "fake/api", "FAKE")
    sources = {"mirror": _source("mirror", src.GridTiles("Fake grid", [], "EPSG:2180", "fake/grid", 2000, 1.0, 1e6,
                                                         mirror="fake/1m")),
               "nowhere": _source("nowhere", Tiles(), sample=None), "api": _source("api", api)}
    assert _run(tmp_path, sources) == 0
    out = capsys.readouterr().out
    assert "no copy of the tiles is set up" in out and "no sample point" in out and "50 calls a day" in out
    assert "0 checked, 0 failed, 3 skipped" in out
    assert not asked
    # Named and with a key: its index is computed, its read left to --deep
    assert _run(tmp_path, sources, ["api"], key="secret") == 0
    out = capsys.readouterr().out
    assert "read only with --deep" in out and "1 checked, 0 failed, 0 skipped" in out


def test_wcs(tmp_path, capsys, asked):
    def wcs(host):
        return src.WcsTiles(f"WCS of {host}", f"https://{host}/wcs", "dtm", "EPSG:32633", "fake/wcs", native_res=1.0,
                            fetch_res=1.0, axes=("E", "N"))
    sources = {"ok": _source("ok", wcs("ok.example")), "bad": _source("bad", wcs("bad.example"))}
    assert _run(tmp_path, sources) == 1
    out = capsys.readouterr().out
    assert "1 checked" not in out and "2 checked, 1 failed" in out
    assert "GetCoverage: HTTP 200 <ows:ExceptionReport>" in out
    coverage = [dict(p) for url, p, _ in asked if "ok.example" in url][1]
    assert coverage["COVERAGEID"] == "dtm" and coverage["SUBSET"].startswith("N(")  # the last SUBSET: northing


def test_timeout(tmp_path, capsys, asked):
    sources = {"slow": _source("slow", Tiles(slow=3)), "fast": _source("fast", Tiles("fast.example"))}
    assert _run(tmp_path, sources, timeout=0.5) == 1
    out = capsys.readouterr().out
    assert "no answer within 0.5 s" in out and "2 checked, 1 failed" in out


def test_every_layer_has_a_probe():
    for s in src.SOURCES.values():
        for layer in (s.nmt, s.nmpt):
            if layer is not None:
                assert probe.strategy(layer) is not None, (s.id, layer.description)
    assert probe.strategy(src.FileLayer.__new__(src.FileLayer)) == "file"
    assert probe.strategy(src.Layer()) is None


def test_command(tmp_path, monkeypatch, asked, capsys):
    monkeypatch.setattr(probe, "SOURCES", {"good": _source("good", Tiles()),
                                           "gone": _source("gone", Tiles("gone.example"))})
    data = str(tmp_path)
    assert update.main(["--data-dir", data, "sources", "check", "good"]) == 0
    assert update.main(["sources", "check", "--data-dir", data]) == 1
    with pytest.raises(SystemExit, match="unknown source: nowhere"):
        update.main(["--data-dir", data, "sources", "check", "nowhere"])
    assert sorted(os.listdir(tmp_path / "cache")) == ["LAYOUT", "locks"]


def test_wcs_multipart_answer(tmp_path, capsys, monkeypatch):
    """A multipart GetCoverage answer whose parameters name an XML part (Saxony-Anhalt:
    multipart/related; ... type="text/xml") is a coverage; an XML answer itself is a failure."""
    multipart = 'multipart/related; boundary="wcs"; start="GML-Part"; type="text/xml"'

    def fake(url, params=None, headers=None):
        if dict(params).get("REQUEST") == "GetCoverage":
            return 200, (multipart if "ok.example" in url else "text/xml; charset=UTF-8"), b"--wcs"
        return 200, "text/xml", b"<wcs:CoverageDescriptions>"
    monkeypatch.setattr(probe, "_http", fake)
    layer = lambda host: src.WcsTiles(f"WCS of {host}", f"https://{host}/wcs", "dtm", "EPSG:32633",  # noqa: E731
                                      "fake/wcs", native_res=1.0, fetch_res=1.0, axes=("E", "N"))
    assert _run(tmp_path, {"ok": _source("ok", layer("ok.example"))}, ["ok"]) == 0
    assert _run(tmp_path, {"bad": _source("bad", layer("bad.example"))}, ["bad"]) == 1
    assert "GetCoverage: HTTP 200" in capsys.readouterr().out
