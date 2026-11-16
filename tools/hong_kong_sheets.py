"""The 0.5 m lidar sheets of CEDD's 2020 terrain and surface models of Hong Kong (the source `hong_kong`): a static
table of the sheets the CSDI Portal's index lists, next to the catalogue (sources/catalogue/hong_kong_sheets.npz), read
by the source's layers: a sheet outside the table is never asked, a 404 for one in it is an error of that tile.

The table comes from the index (the FeatureServer's layers 0 DTM_2020 and 1 DSM_2020: TILE_NAME, Filename, URL and the
footprint, paged by 3 000: two pages a layer, four requests). Every row is checked: its code a sheet of the scheme
(sources.catalogue.hong_kong.hk_cell) whose box is the footprint, its URL the layer's folder and its file name, the
name starting with the code; else the tool stops. The file names are kept as published (on map 17 their kilometre
pairs are not those of the sheet's box). Paced: one request at a time, at least PAUSE_S apart (start to start), each
under one of the host's slots of the data folder (net.host_slot, as the app's downloads); the answers kept in the
work folder (a second run asks nothing already there). `--count` says how many requests a run asks without asking any.
The survey is frozen (2020; the files' Last-Modified 2022-01-14): run this again only when CEDD publishes more sheets,
check the tests' places and commit the new table.

    uv run tools/hong_kong_sheets.py [--count] [--work <folder>] [--out sources/catalogue/hong_kong_sheets.npz]
                                     [--data-dir <folder>]
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

INDEX = "https://portal.csdi.gov.hk/server/rest/services/common/cedd_rcd_1629267205233_87895/FeatureServer"
LAYERS = {"dtm": 0, "dsm": 1}  # the index's layer of each of the source's layers
PAGE = 3000                     # the FeatureServer's maxRecordCount
PAUSE_S = 1.0
MAX_PAGE_BYTES = 20_000_000
EDGE_TOLERANCE_M = 0.01         # a footprint's corner off its code's box by more: the tool stops

Row = Tuple[str, str, str, List[List[float]]]  # code, file name, url, the footprint's ring


def page_url(layer: str, offset: int) -> Tuple[str, Dict[str, str]]:
    return f"{INDEX}/{LAYERS[layer]}/query", {
        "where": "1=1", "outFields": "TILE_NAME,Filename,URL", "returnGeometry": "true", "outSR": "2326",
        "orderByFields": "OBJECTID_1", "resultOffset": str(offset), "resultRecordCount": str(PAGE), "f": "json"}


class Pacer:
    """At least `pause` (PAUSE_S unless given) between the starts of two requests."""

    def __init__(self, pause: Optional[float] = None):
        self.pause, self.last = PAUSE_S if pause is None else pause, None

    def __call__(self):
        if self.last is not None:
            wait = self.pause - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
        self.last = time.monotonic()


def _get_json(url: str, params: Dict[str, str], cache_dir: str, pace: Pacer) -> dict:
    import cache
    from sources import net
    pace()
    with net.host_slot(cache_dir, url):  # held until the body is read
        with net.session().get(url, params=params, headers=cache.http_headers(), timeout=120, stream=True) as r:
            if r.status_code != 200:
                raise RuntimeError(f"{url}: HTTP {r.status_code}")
            data = r.raw.read(MAX_PAGE_BYTES + 1, decode_content=True)
    if len(data) > MAX_PAGE_BYTES:
        raise RuntimeError(f"{url}: more than {MAX_PAGE_BYTES} bytes")
    answer = json.loads(data)
    if "error" in answer:
        raise RuntimeError(f"{url}: {answer['error']}")
    return answer


def index_rows(layer: str, cache_dir: str, pace: Pacer) -> List[Row]:
    """Every row of a layer's index, page by page until a page says no more."""
    rows: List[Row] = []
    while True:
        url, params = page_url(layer, len(rows))
        page = _get_json(url, params, cache_dir, pace)
        for feature in page.get("features", []):
            a = feature["attributes"]
            rows.append((a["TILE_NAME"], a["Filename"], a["URL"], feature["geometry"]["rings"][0]))
        if not page.get("exceededTransferLimit") or not page.get("features"):
            return rows


def check(layer: str, rows: Iterable[Row]) -> Dict[str, str]:
    """{code: file name} of a layer's rows; ValueError when a code is no sheet of the scheme or twice, its footprint
    is not its box, or its URL or file name is not the layer's address of it."""
    from sources.catalogue.hong_kong import HK_BULK, HK_FOLDERS, HK_LEFT, HK_BOTTOM, HK_SHEET, hk_cell
    found: Dict[str, str] = {}
    w, h = HK_SHEET
    for code, name, url, ring in rows:
        cell = hk_cell(code)
        if cell is None:
            raise ValueError(f"{code}: not a 1:1000 sheet of the scheme")
        box = (HK_LEFT + cell[0] * w, HK_BOTTOM + cell[1] * h, HK_LEFT + (cell[0] + 1) * w, HK_BOTTOM + (cell[1] + 1) * h)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        if max(abs(a - b) for a, b in zip((min(xs), min(ys), max(xs), max(ys)), box)) > EDGE_TOLERANCE_M:
            raise ValueError(f"{code}: footprint {min(xs):.2f}, {min(ys):.2f}, {max(xs):.2f}, {max(ys):.2f}, "
                             f"its box {box} expected")
        if not (name.startswith(f"{code}(") and name.endswith(".zip")) or "/" in name:
            raise ValueError(f"{code}: file name {name}")
        if url != f"{HK_BULK}/{HK_FOLDERS[layer]}/{name}":
            raise ValueError(f"{code}: URL {url}, {HK_BULK}/{HK_FOLDERS[layer]}/{name} expected")
        if code in found:
            raise ValueError(f"{code}: twice in the {layer} index")
        found[code] = name
    return found


def save(path: str, table: Dict[str, Dict[str, str]]):
    """The table: per layer the codes and the file names of its sheets, sorted by code."""
    arrays = {}
    for layer, rows in table.items():
        codes = sorted(rows)
        arrays[f"{layer}_codes"] = np.array([c.encode() for c in codes], dtype="S8")
        arrays[f"{layer}_files"] = np.array([rows[c].encode() for c in codes], dtype="S40")
    np.savez_compressed(path, **arrays)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", action="store_true", help="say how many requests a run asks, ask none")
    parser.add_argument("--work", default=os.path.join(HERE, "work", "hong-kong-sheets"),
                        help="folder of the index's answers (kept: a second run asks nothing already there)")
    parser.add_argument("--out", default=os.path.join(HERE, "sources", "catalogue", "hong_kong_sheets.npz"))
    parser.add_argument("--data-dir", help="the data folder whose host slots the requests take (default: the app's)")
    args = parser.parse_args(argv)
    os.makedirs(args.work, exist_ok=True)
    todo = [layer for layer in LAYERS if not os.path.exists(os.path.join(args.work, f"{layer}.json"))]
    if args.count:
        print(f"{len(todo)} layers to ask, 2 pages each (3 253 and 3 310 rows on 2026-11-16): {2 * len(todo)} "
              f"requests, {PAUSE_S:g} s apart")
        return
    import cache
    cache_dir = os.path.join(cache.data_dir(args.data_dir), "cache")
    cache.check_layout(cache_dir)  # a new cache is marked first: the host slots' lock files would make it unusable
    pace = Pacer()
    table: Dict[str, Dict[str, str]] = {}
    for layer in LAYERS:
        saved = os.path.join(args.work, f"{layer}.json")
        if layer in todo:
            rows = index_rows(layer, cache_dir, pace)
            with open(saved, "w", encoding="utf-8") as f:
                json.dump(rows, f)
        with open(saved, encoding="utf-8") as f:
            table[layer] = check(layer, (tuple(r) for r in json.load(f)))
        print(f"{layer}: {len(table[layer])} sheets", flush=True)
    only = sorted(set(table["dsm"]) - set(table["dtm"]))
    print(f"surface sheets without terrain: {len(only)} {only[:20]}")
    save(args.out, table)
    print(f"written {args.out}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
