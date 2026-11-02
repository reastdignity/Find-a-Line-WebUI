"""The highline layer's endpoints (web.py: /api/countries, its cells and the request of a cell) over a small
cube built by countcube from synthetic tile counts: the answers against Cube, the errors, who may ask, a cube
built again, no numba in the web process, and the page #layer in headless Edge on the real server."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest
import shapely
from pyproj import Transformer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import countcube as cc  # noqa: E402
import web  # noqa: E402

pytest.importorskip("httpx2")
from fastapi.testclient import TestClient  # noqa: E402

CRS = "EPSG:8353"  # S-JTSK [JTSK03] / Krovak East North: negative coordinates
# The sample's outline (lon, lat): a part of northern Slovakia around the Tatras
OUTLINE = [(19.55, 49.05), (20.05, 48.95), (20.6, 49.02), (20.62, 49.32), (20.1, 49.28), (19.6, 49.3)]
# Where the sample's lines are: (lon, lat, lines per km² at the centre, radius in km)
HOT = [(20.08, 49.18, 6e5, 4.0), (19.95, 49.23, 4e4, 3.0), (20.42, 49.12, 2e3, 5.0), (19.75, 49.15, 300, 6.0)]
BANDS = [("S", 30, 300, 1.0, "formula", 60, 5000, True), ("M", 300, 1000, 2.0, "sag", 60, 10000, True),
         ("L", 1000, 5000, 5.0, "sag", 45, 20000, True), ("M2", 1000, 2000, 2.0, "sag", 60, 10000, False)]


def sample_cube(data_dir, country: str = "slovakia", name: str = "Slovakia", seed: int = 1) -> str:
    """A small cube of made-up counts in <data_dir>/countries/<country>/cube (countcube.build of one tile
    of synthetic TileCounts) with its area.geojson; the cube folder. Also tools/ui_shots.py's sample."""
    rng = np.random.default_rng(seed)
    to_crs = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    to_wgs84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    outline = shapely.Polygon(OUTLINE)
    local = shapely.transform(shapely.segmentize(outline, 0.01),
                              lambda xy: np.column_stack(to_crs.transform(xy[:, 0], xy[:, 1])))
    origin = cc.origin_of(local.bounds)
    x0, y0 = origin
    left, bottom, right, top = local.bounds
    i0, i1 = int((left - x0) // cc.CELL_M), int((right - x0) // cc.CELL_M)
    j0, j1 = int((bottom - y0) // cc.CELL_M), int((top - y0) // cc.CELL_M)
    i, j = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    inside = shapely.contains_xy(local, x0 + (i + 0.5) * cc.CELL_M, y0 + (j + 0.5) * cc.CELL_M)
    i, j = i[inside], j[inside]
    lon, lat = to_wgs84.transform(x0 + (i + 0.5) * cc.CELL_M, y0 + (j + 0.5) * cc.CELL_M)
    density = rng.uniform(0, 3, len(i)) * (rng.random(len(i)) < 0.3)
    for hlon, hlat, peak, radius in HOT:
        d2 = ((lon - hlon) * 111.32 * np.cos(np.radians(49.1))) ** 2 + ((lat - hlat) * 111.32) ** 2
        density += peak * np.exp(-d2 / (2 * radius ** 2))
    lines = np.round(density * rng.uniform(0.5, 1.5, len(i))).astype(np.int64)
    i, j, lines = i[lines > 0], j[lines > 0], lines[lines > 0]

    # Each cell's lines in a few records of random values, the counts split among them
    per = rng.integers(1, 6, len(i))
    cell = np.repeat(np.arange(len(i)), per)
    n = len(cell)
    columns = {"length": rng.choice(np.array(cc.LENGTH_EDGES[:-1], dtype=float), n) + rng.uniform(0, 20, n),
               "clearance": rng.uniform(0, 30, n), "clearance_nmpt": np.full(n, np.nan),
               "height_max": rng.uniform(2, 150, n), "angle1": rng.uniform(20, 95, n), "angle2": rng.uniform(20, 95, n),
               "prom1": rng.uniform(0, 80, n), "prom2": rng.uniform(0, 80, n),
               "water_px": rng.integers(0, 3, n) * (rng.random(n) < 0.1)}
    records = cc.line_records(columns)
    share = rng.random(n)
    total = np.bincount(cell, share)[cell]
    counts = np.maximum(np.round(lines[cell] * share / total), 1).astype(np.int64)
    keys, counts = cc.sum_keys(cc.pack_keys(i[cell], j[cell], records), counts)

    # Spots: about one per 300 lines, each a pair of clusters in its cell with one of the cell's records
    spots = np.maximum(np.round(lines / 300 * rng.uniform(0.5, 1.5, len(i))), 1).astype(np.int64)
    owner = np.repeat(np.arange(len(i)), spots)
    m = len(owner)
    pcx = i[owner] * cc.CLUSTERS_PER_CELL + rng.integers(0, cc.CLUSTERS_PER_CELL, m)
    pcy = j[owner] * cc.CLUSTERS_PER_CELL + rng.integers(0, cc.CLUSTERS_PER_CELL, m)
    dx, dy = rng.integers(1, 30, m), rng.integers(-30, 31, m)
    ids = (pcx << cc.SPOT_CX_SHIFT) | (pcy << cc.SPOT_CY_SHIFT) | (dx << 8) | (dy + 128)
    first = np.searchsorted(cell, owner)  # the first record of the spot's cell
    ids, spot_records = cc.merge_spots(ids, records[first + rng.integers(0, per[owner])])

    folder = os.path.join(str(data_dir), "countries", country)
    os.makedirs(os.path.join(folder, "tiles", "S"), exist_ok=True)
    tile = os.path.join(folder, "tiles", "S", "sample.npz")
    cc.save_tile(tile, cc.TileCounts(keys, counts, ids, spot_records, int(counts.sum()), 0), {"sample": True})
    lon0, lat0, lon1, lat1 = outline.bounds
    bands = [{"name": b, "lengths": [lo, hi], "resolution": res, "model": model, "slope_threshold": slope,
              "core_m": core, "layer": layer, "tiles": 40, "done": 40, "seconds": 3600.0,
              "params": {"source": country, "min_length": lo, "max_length": hi, "resolution": res, "model": model,
                         "slope_threshold": slope, "nmpt": "off", "water": "fill", "coastline": "copernicus",
                         "fill_gaps": "on", "pretension": 2.5, "stretch": 2.1, "webbing_weight": 41.0}}
             for b, lo, hi, res, model, slope, core, layer in BANDS]
    info = {"id": country, "name": name, "crs": CRS, "origin": list(origin),
            "bounds_wgs84": [round(v, 6) for v in (lon0, lat0, lon1, lat1)], "bands": bands, "dsm": False,
            "water": True, "partial": False, "config": "0" * 64,
            "credits": [{"data": "DMR 5.0 (ÚGKK SR, Slovakia)", "attribution": "© ÚGKK SR", "licence": "CC BY 4.0",
                         "url": "https://creativecommons.org/licenses/by/4.0/", "notice": ""},
                        {"data": "OpenStreetMap", "attribution": "© OpenStreetMap contributors", "licence": "ODbL 1.0",
                         "url": "https://www.openstreetmap.org/copyright", "notice": ""}],
            "notes": ["A sample of made-up counts."]}
    out = os.path.join(folder, "cube")
    cc.build([tile], out, info)
    with open(os.path.join(out, "area.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "Feature", "properties": {}, "geometry": json.loads(shapely.to_geojson(outline))}, f)
    return out


TOKEN = "test-token"
LOCAL = "http://127.0.0.1:8765"
VIEW = "19.9,49.1,20.3,49.3"  # a part of the sample (west,south,east,north)


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """A data folder with the sample cube (made once)."""
    data = tmp_path_factory.mktemp("country")
    sample_cube(data)
    return data


@pytest.fixture
def client(sample):
    with TestClient(web.create_app(str(sample), token=TOKEN, start_scheduler=False), base_url=LOCAL) as c:
        yield c


def test_countries_listed(client, sample, tmp_path):
    """cube.json of each built country without "config" and "origin"; a country without a cube, or a cube
    that cannot be read, is left out; an empty data folder lists none."""
    found = client.get("/api/countries")
    assert found.status_code == 200, found.text
    countries = found.json()["countries"]
    assert [c["id"] for c in countries] == ["slovakia"]
    with open(os.path.join(sample, "countries", "slovakia", "cube", "cube.json"), encoding="utf-8") as f:
        info = json.load(f)
    assert countries[0] == {k: v for k, v in info.items() if k not in ("config", "origin")}
    assert "config" not in countries[0] and "origin" not in countries[0]
    assert {"bands", "edges", "levels", "cell_m", "totals", "built", "credits", "dsm"} <= set(countries[0])

    with TestClient(web.create_app(str(tmp_path), token=TOKEN, start_scheduler=False), base_url=LOCAL) as empty:
        assert empty.get("/api/countries").json() == {"countries": []}
        (tmp_path / "countries" / "unbuilt" / "tiles").mkdir(parents=True)
        broken = tmp_path / "countries" / "broken" / "cube"
        broken.mkdir(parents=True)
        (broken / "cube.json").write_text(json.dumps({"version": cc.VERSION + 1}))
        assert empty.get("/api/countries").json() == {"countries": []}
        assert empty.get("/api/countries/broken/cells").status_code == 404


def _cells(client, **query):
    answer = client.get("/api/countries/slovakia/cells", params=query)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_cells_as_the_cube_gives_them(client, sample):
    """The cells of a view: Cube.cells of the level asked (auto: Cube.auto_level), with their corners
    rounded to 6 decimals, the total and the largest count; the filters as Filters.parse reads them."""
    cube = cc.Cube(os.path.join(sample, "countries", "slovakia", "cube"))
    box = cube.box(*map(float, VIEW.split(",")))
    for query, level, filters in (
            ({"bbox": VIEW, "level": "auto"}, cube.auto_level(box), cc.Filters()),
            ({"bbox": VIEW, "level": "1", "mode": "spots"}, 1, cc.Filters()),
            ({"bbox": VIEW, "level": "2", "length": "60-1000", "prominence": "10", "clearance": "0", "height": "0",
              "trees": "all", "water": "land", "wall": "60"}, 2,
             cc.Filters(length=(60, 1000), prominence=10, wall=60, water="land")),
            ({"bbox": VIEW, "level": "8", "height": "50", "clearance": "5"}, 8, cc.Filters(height=50, clearance=5))):
        got = _cells(client, **query)
        i, j, n = cube.cells(query.get("mode", "lines"), level, box, filters)
        assert got["level"] == level and got["cell_m"] == level * 1000, query
        assert len(got["cells"]) == len(i) > 0, query
        assert got["total"] == int(n.sum()) and got["max"] == int(n.max()), query
        corners = cube.corners(level, i, j)
        for row, a, b, c, xy in zip(got["cells"], i, j, n, corners):
            assert row[:3] == [a, b, c] and len(row) == 11
            assert row[3:] == [round(float(v), 6) for v in xy.ravel()]
    assert _cells(client, bbox=VIEW)["level"] == cube.auto_level(box)  # level=auto by default
    # no bbox: the country's bounds
    whole = _cells(client, level="8")
    assert whole["total"] == int(cube.cells("lines", 8, None, cc.Filters())[2].sum())
    # far from the country: no cells
    assert _cells(client, bbox="100,10,101,11", level="1") == {"level": 1, "cell_m": 1000, "total": 0, "max": 0,
                                                               "cells": []}
    # filters that leave nothing
    assert _cells(client, bbox=VIEW, level="8", trees="only")["cells"] == []


def test_cells_refused(client):
    """400 with a plain message for a value the cube cannot take; 404 for an unknown country."""
    def refused(**query):
        answer = client.get("/api/countries/slovakia/cells", params={"bbox": VIEW, **query})
        assert answer.status_code == 400, (query, answer.text)
        return answer.json()["detail"]
    assert "too many cells" in refused(bbox="16,47,23,50", level="1")
    assert "zoom in" in refused(bbox="16,47,23,50", level="1")
    assert "level" in refused(level="3") and "level" in refused(level="x")
    assert "mode" in refused(mode="groups")
    assert "bbox" in refused(bbox="1,2,3") and "bbox" in refused(bbox="a,b,c,d")
    assert "box" in refused(bbox="20,49,19,50")  # west east of east
    assert "length" in refused(length="40-300") and "length" in refused(length="300-30")
    assert "prominence" in refused(prominence="7") and "wall" in refused(wall="50")
    assert "trees" in refused(trees="some") and "water" in refused(water="sea")
    for path in ("/api/countries/nowhere/cells", "/api/countries/nowhere/request?band=S&level=1&i=0&j=0",
                 "/api/countries/..%2Fruns/cells", "/api/countries/Slovakia/cells"):
        assert client.get(path).status_code == 404, path


def test_cell_request(client, sample):
    """The search of one cell: countcube.cell_request's params and geometry; 400 for a band not in the
    layer, a level not in the cube, a cell outside the country or a value that is no whole number."""
    cube = cc.Cube(os.path.join(sample, "countries", "slovakia", "cube"))
    row = _cells(client, bbox=VIEW, level="2")["cells"][0]
    answer = client.get("/api/countries/slovakia/request", params={"band": "M", "level": 2, "i": row[0], "j": row[1]})
    assert answer.status_code == 200, answer.text
    request = answer.json()
    assert request == json.loads(json.dumps(cc.cell_request(cube, "M", 2, row[0], row[1])))
    assert request["params"]["max_length"] == 1000 and request["geometry"]["type"] in ("Polygon", "MultiPolygon")
    for query, word in (({"band": "M2", "level": 2, "i": row[0], "j": row[1]}, "band"),
                        ({"band": "", "level": 2, "i": row[0], "j": row[1]}, "band"),
                        ({"band": "S", "level": 3, "i": row[0], "j": row[1]}, "level"),
                        ({"band": "S", "level": 1, "i": 0, "j": 0}, "outside"),
                        ({"band": "S", "level": 1, "i": -1, "j": 5}, "outside"),
                        ({"band": "S", "level": "two", "i": 1, "j": 1}, "whole"),
                        ({"band": "S", "i": 1, "j": 1}, "whole")):
        answer = client.get("/api/countries/slovakia/request", params=query)
        assert answer.status_code == 400 and word in answer.json()["detail"], (query, answer.text)


def test_cube_built_again_is_read_again(tmp_path):
    """One Cube per version of cube.json: a cube built again (another mtime) answers with its new counts,
    and a cube being built (no cube.json) is no layer."""
    sample_cube(tmp_path, seed=1)
    with TestClient(web.create_app(str(tmp_path), token=TOKEN, start_scheduler=False), base_url=LOCAL) as client:
        before = _cells(client, level="8")["total"]
        assert _cells(client, level="8")["total"] == before  # the cached cube
        path = tmp_path / "countries" / "slovakia" / "cube" / "cube.json"
        stamp = path.stat().st_mtime_ns
        sample_cube(tmp_path, seed=2)
        os.utime(path, ns=(stamp + 10 ** 9, stamp + 10 ** 9))  # a coarse clock may give the same mtime
        after = _cells(client, level="8")["total"]
        assert after != before and after == int(cc.Cube(str(path.parent)).cells("lines", 8, None, cc.Filters())[2].sum())
        path.unlink()
        assert client.get("/api/countries/slovakia/cells").status_code == 404
        assert client.get("/api/countries").json() == {"countries": []}


def test_administrators_only(tmp_path, monkeypatch):
    """On the public site the layer is for administrators: anonymous 401, an approved user 403, an
    administrator gets the answers; every route keeps its access rule."""
    from settings import AccountSettings, PublicSettings
    from test_public import ACCOUNTS, SETTINGS, URL, FakeProviders, _public_app, session_of
    import accounts as ac
    for key, value in {**SETTINGS, **ACCOUNTS}.items():
        monkeypatch.setenv(key, value)
    settings, accounts = PublicSettings.load(), AccountSettings.load()
    sample_cube(tmp_path)
    paths = ["/api/countries", f"/api/countries/slovakia/cells?bbox={VIEW}&level=2",
             "/api/countries/slovakia/request?band=S&level=8&i=0&j=0"]
    with TestClient(_public_app(tmp_path, settings, accounts, FakeProviders()), base_url=URL) as public:
        for path in paths:
            assert public.get(path).status_code == 401, path
        for who, status in (("a", 403), ("pending", 403), ("admin", 200)):
            client = TestClient(public.app, base_url=URL)
            _, cookie, csrf = session_of(tmp_path, accounts, who)
            client.cookies.set(ac.SESSION_COOKIE, cookie, domain="lines.example.org")
            client.headers["x-findaline-token"] = csrf
            for path in paths[:2]:
                assert client.get(path).status_code == status, (who, path)
            if who == "admin":
                assert client.get(paths[2]).status_code in (200, 400)  # cell (0, 0): may lie outside
                assert [c["id"] for c in client.get(paths[0]).json()["countries"]] == ["slovakia"]
            client.close()
        from fastapi.routing import APIRoute
        routes = {r.path: r for r in public.app.routes if isinstance(r, APIRoute)}
        for path in ("/api/countries", "/api/countries/{country}/cells", "/api/countries/{country}/request"):
            assert "require_admin" in {getattr(d.call, "__name__", "") for d in routes[path].dependant.dependencies}


def test_no_numba_in_the_web_process(sample):
    """The layer's endpoints import countcube only: never numba, search, linesearch or country."""
    code = (f"import json, sys; sys.path.insert(0, {REPO!r}); import web\n"
            "from fastapi.testclient import TestClient\n"
            f"c = TestClient(web.create_app({str(sample)!r}, token='t', start_scheduler=False), "
            "base_url='http://127.0.0.1:8765')\n"
            "assert c.get('/api/countries').status_code == 200\n"
            f"assert c.get('/api/countries/slovakia/cells?bbox={VIEW}&level=2').status_code == 200\n"
            "c.get('/api/countries/slovakia/request?band=S&level=8&i=1&j=1')\n"
            "assert 'countcube' in sys.modules\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('numba', 'linesearch', 'search', 'country'))))")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


# The page #layer: wait for the cells, count the painted pixels of the cells' canvas, click the cell under the
# centre of the first answer's largest cell, read the selected cell's panel
LAYER_SCRIPT = """
const answers = [];
const realFetch2 = window.fetch;
window.fetch = (url, init) => {
  const p = realFetch2(url, init);
  if (String(url).includes("/cells?")) p.then((r) => r.clone().json()).then((j) => answers.push(j), () => {});
  return p;
};
const painted = (canvas) => {  // the canvas's pixels that are not transparent
  if (!canvas.width || !canvas.height) return 0;
  const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
  let n = 0;
  for (let k = 3; k < data.length; k += 4) if (data[k]) n++;
  return n;
};
run({
  cells: (next) => wait(() => answers.length && /in view/.test(text(".c-layer-total"))  // drawn in an animation frame
                              && $$(".leaflet-container canvas").some((c) => painted(c) > 0), () => {
    const a = answers[answers.length - 1];
    result.level = a.level; result.cells = a.cells.length; result.total = text(".c-layer-total");
    result.painted = Math.max(0, ...$$(".leaflet-container canvas").map(painted));
    next();
  }),
  click: (next) => {
    const a = answers[answers.length - 1];
    const row = a.cells.reduce((best, r) => r[2] > best[2] ? r : best);
    const map = window.FINDALINE_PLACE.map;
    const lat = (row[3] + row[5] + row[7] + row[9]) / 4, lon = (row[4] + row[6] + row[8] + row[10]) / 4;
    const point = map.latLngToContainerPoint([lat, lon]);
    const box = map.getContainer().getBoundingClientRect();
    const canvas = $$(".leaflet-container canvas").reduce((best, c) => painted(c) > painted(best) ? c : best);
    const init = {bubbles: true, cancelable: true, clientX: box.left + point.x, clientY: box.top + point.y, button: 0};
    canvas.dispatchEvent(new MouseEvent("mousemove", init));
    canvas.dispatchEvent(new MouseEvent("click", init));
    result.wanted = row.slice(0, 3);
    wait(() => $(".c-layer-cell"), () => {
      result.selected = text(".c-layer-cell");
      result.search = $$(".c-layer-search a").map((b) => b.getAttribute("href"));
      next();
    });
  },
});
"""


@pytest.mark.skipif(not os.path.exists(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                    reason="needs Microsoft Edge")
@pytest.mark.parametrize("ui", ["c", "d"])
def test_layer_page_in_edge(sample, tmp_path, ui):
    """#layer on the real local server with the sample cube: the cells drawn on the map's canvas, a click
    selects the cell under it (its count, one "Search here" per layer band), no CSP violations."""
    from test_shell_c import _edge, stub_page
    from test_web import _server
    page = stub_page(sample, f"layer-{ui}", LAYER_SCRIPT)
    with _server(sample) as port:
        r = _edge(port, f"{page}?ui={ui}#layer", tmp_path / "edge")
    assert "timeout" not in r and "error" not in r, json.dumps(r)
    assert r["cells"] > 10 and r["painted"] > 1000 and "lines in view" in r["total"], r
    count = f"{r['wanted'][2]:,}"
    assert r["selected"].startswith("Selected cell") and count in r["selected"], r
    level = r["level"]
    assert r["search"] == [f"#new&cell=slovakia:{b}:{level}:{r['wanted'][0]}:{r['wanted'][1]}" for b in ("S", "M", "L")], r
    assert r["csp"] == [], r
