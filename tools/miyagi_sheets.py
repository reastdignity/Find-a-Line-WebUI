"""The 1 m grid sheets of Miyagi Prefecture's point cloud data (the source `miyagi`): a static table of every sheet with
the folder it lies in, next to the catalogue (sources/catalogue/miyagi_sheets.npz), read by the source's layer: a
sheet outside the table is never asked (the bucket gic-miyagi denies listing and answers 403 for a key it does not
have), and the folder (01-07, a region of the survey) cannot be derived from a sheet's code.

The table comes from the list the prefecture publishes on its open data portal (resource 1523 of the dataset 915,
「【宮城県】3次元点群データ_データ一覧_グリッドデータ_CSV_2023」, 040002_point_cloud_url_1mcsv.csv: UTF-8 with a BOM, the
columns データセット_タイトル, リソース_タイトル, リソース_URL, リソース_ファイルサイズ; 9 571 rows on 2026-11-27): one request
(the portal redirects it to its own bucket), at most MAX_CSV_BYTES. Every URL must be the bucket's address of a
quadrant sheet of zone X (sources.catalogue.japan.jp_quad_cell) in a folder 01-07, or the tool stops; a sheet listed
in two folders keeps both (10PE0822 in 02 and 03 on 2026-11-27: the layer composes the two files); the same row
twice is taken once. It prints what changed against the table it replaces (sheets added, removed, moved to another
folder). The survey is frozen (labelled 2023): run this again only when the prefecture publishes more sheets, check
the tests' places and commit the new table. A sheet cached before keeps its file (its name is the code, not the
publisher's version): a re-published file of a sheet is not read again unless its cached tile is deleted.

    uv run tools/miyagi_sheets.py [--csv <a saved copy of the list>] [--out sources/catalogue/miyagi_sheets.npz]
"""

import argparse
import csv
import io
import os
import re
import sys
from typing import Dict, Iterable, List, Set, Tuple

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

INDEX_URL = "https://miyagi.dataeye.jp/resource_download/1523"
BUCKET = "https://gic-miyagi.s3.ap-northeast-1.amazonaws.com"
MAX_CSV_BYTES = 20_000_000
HEADER = ["データセット_タイトル", "リソース_タイトル", "リソース_URL", "リソース_ファイルサイズ"]
_URL = re.compile(re.escape(BUCKET) + r"/2024/1mcsv/(0[1-7])/(10[A-Z]{2}\d{4})\.zip")


def sheet_url(folder: int, code: str) -> str:
    """The ZIP of a sheet (the layer's address: sources.catalogue.japan)."""
    return f"{BUCKET}/2024/1mcsv/{folder:02d}/{code}.zip"


def rows(text: str) -> List[Tuple[int, str]]:
    """(folder, code) of each row of the list; ValueError when the header is not the list's, a URL is not the
    bucket's address of a quadrant sheet of zone X in a folder 01-07, or the list is empty."""
    from sources.catalogue.japan import jp_quad_cell
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, None)
    if header != HEADER:
        raise ValueError(f"not the grid list: header {header}")
    found = []
    for number, row in enumerate(reader, start=2):
        if not row:
            continue
        match = _URL.fullmatch(row[2].strip()) if len(row) >= 3 else None
        if not match:
            raise ValueError(f"row {number}: {row[2] if len(row) >= 3 else row} is no sheet's address")
        if jp_quad_cell(10, match.group(2)) is None:
            raise ValueError(f"row {number}: {match.group(2)} is not a quadrant sheet of zone X")
        found.append((int(match.group(1)), match.group(2)))
    if not found:
        raise ValueError("the list names no sheet")
    return found


def sheets(listed: Iterable[Tuple[int, str]]) -> Dict[str, Set[int]]:
    """The folders of each code."""
    found: Dict[str, Set[int]] = {}
    for folder, code in listed:
        found.setdefault(code, set()).add(folder)
    return found


def save(path: str, found: Dict[str, Set[int]]):
    """The table: one row per sheet and folder, `codes` (bytes of 8) and `folders`, sorted by code and folder."""
    table = sorted((c, f) for c, folders in found.items() for f in folders)
    np.savez_compressed(path, codes=np.array([c.encode() for c, _ in table], dtype="S8"),
                        folders=np.array([f for _, f in table], dtype=np.int16))


def load(path: str) -> Dict[str, Set[int]]:
    """A saved table (empty when there is none)."""
    if not os.path.exists(path):
        return {}
    with np.load(path) as table:
        return sheets((int(f), c.decode()) for c, f in zip(table["codes"], table["folders"]))


def changes(old: Dict[str, Set[int]], new: Dict[str, Set[int]]) -> List[str]:
    """What a new table changes against the old one, as lines."""
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    moved = sorted(c for c in set(old) & set(new) if old[c] != new[c])
    return [f"sheets added: {len(added)} {added[:10]}", f"sheets removed: {len(removed)} {removed[:10]}",
            f"sheets in other folders: {len(moved)} {[(c, sorted(old[c]), sorted(new[c])) for c in moved[:10]]}"]


def fetch(url: str, cache_dir: str) -> bytes:
    """The list's bytes (one request under a slot of the portal's host in the data folder); RuntimeError for any
    answer but 200 or one over MAX_CSV_BYTES."""
    import cache
    from sources import net
    with net.host_slot(cache_dir, url):
        with net.session().get(url, headers=cache.http_headers(), timeout=120, stream=True) as response:
            if response.status_code != 200:
                raise RuntimeError(f"{url}: HTTP {response.status_code}")
            data = response.raw.read(MAX_CSV_BYTES + 1, decode_content=True)
    if len(data) > MAX_CSV_BYTES:
        raise RuntimeError(f"{url}: more than {MAX_CSV_BYTES} bytes")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", help="a saved copy of the list (no request)")
    parser.add_argument("--out", default=os.path.join(HERE, "sources", "catalogue", "miyagi_sheets.npz"))
    parser.add_argument("--data-dir", help="the data folder whose host slots the request takes (default: the app's)")
    args = parser.parse_args(argv)
    if args.csv:
        with open(args.csv, "rb") as f:
            data = f.read()
    else:
        import cache
        cache_dir = os.path.join(cache.data_dir(args.data_dir), "cache")
        cache.check_layout(cache_dir)  # a new cache is marked first: the host slots' lock files would make it unusable
        data = fetch(INDEX_URL, cache_dir)
    listed = rows(data.decode("utf-8"))
    found = sheets(listed)
    both = sorted(c for c, f in found.items() if len(f) > 1)
    for folder in sorted({f for fs in found.values() for f in fs}):
        print(f"folder {folder:02d}: {sum(1 for f in found.values() if folder in f)} sheets")
    print(f"{len(listed)} rows, {len(found)} sheets; in two folders: {len(both)} {both[:10]}")
    for line in changes(load(args.out), found):
        print(line)
    save(args.out, found)
    print(f"written {args.out}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page
    main()
