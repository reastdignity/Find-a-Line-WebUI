"""Compare two cache folders: the same files with the same bytes, and the same rows in their
index.sqlite but for the times (fetched_at, checked_at, last_used_at).

    uv run tools/cache_diff.py A B                    # every top-level folder
    uv run tools/cache_diff.py A B --only poland usa  # these top-level folders
    uv run tools/cache_diff.py A B --ignore osm/      # without paths starting so

Made to check that a refactoring of the download code leaves the cache as it was: the
same search on an empty cache with the old code (A) and the new one (B). Lock files,
temporary .part files and other SQLite databases (Nominatim's, with times in them) are not
compared. Exit code 1 when anything
differs; the differences are listed.
"""

import argparse
import hashlib
import os
import sqlite3
import sys
from typing import Dict, List, Optional, Sequence, Tuple

TIMES = ("fetched_at", "checked_at", "last_used_at")
SKIP_TOPS = ("locks",)
# index.sqlite is compared by its rows; other databases (Nominatim's answers and its rate) hold times
SKIP_ENDINGS = (".part", ".sqlite", ".sqlite-wal", ".sqlite-shm", ".sqlite-journal")


def _files(root: str, only: Optional[Sequence[str]], ignore: Sequence[str]) -> Dict[str, str]:
    """{relative path with /: sha256} of the compared files under root."""
    found = {}
    for folder, dirs, files in os.walk(root):
        rel_folder = os.path.relpath(folder, root).replace(os.sep, "/")
        top = rel_folder.split("/")[0]
        if top in SKIP_TOPS or (only and rel_folder != "." and top not in only):
            dirs[:] = []
            continue
        for name in files:
            rel = name if rel_folder == "." else f"{rel_folder}/{name}"
            if name.endswith(SKIP_ENDINGS) or ".part" in name or any(rel.startswith(p) for p in ignore):
                continue
            if only and rel_folder == ".":
                continue  # files at the top (LAYOUT) only when comparing everything
            with open(os.path.join(folder, name), "rb") as f:
                found[rel] = hashlib.sha256(f.read()).hexdigest()
    return found


def _rows(root: str, top: str, ignore: Sequence[str]) -> Dict[str, Tuple]:
    """The rows of a top-level folder's index.sqlite without the times, by path."""
    path = os.path.join(root, top, "index.sqlite")
    if not os.path.exists(path):
        return {}
    db = sqlite3.connect(path)
    try:
        cursor = db.execute("SELECT * FROM files")
        columns = [c[0] for c in cursor.description]
        keep = [i for i, c in enumerate(columns) if c not in TIMES]
        rows = {}
        for row in cursor:
            if any(f"{top}/{row[0]}".startswith(p) for p in ignore):
                continue
            rows[row[0]] = tuple((columns[i], row[i]) for i in keep)
        return rows
    finally:
        db.close()


def compare(a: str, b: str, only: Optional[Sequence[str]] = None, ignore: Sequence[str] = ()) -> List[str]:
    """The differences between two cache folders, as lines (none: the same)."""
    out = []
    files_a, files_b = _files(a, only, ignore), _files(b, only, ignore)
    for rel in sorted(set(files_a) | set(files_b)):
        if rel not in files_b:
            out.append(f"only in A: {rel}")
        elif rel not in files_a:
            out.append(f"only in B: {rel}")
        elif files_a[rel] != files_b[rel]:
            out.append(f"different bytes: {rel}")
    tops = sorted({d for root in (a, b) if os.path.isdir(root) for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d)) and d not in SKIP_TOPS and (not only or d in only)})
    for top in tops:
        rows_a, rows_b = _rows(a, top, ignore), _rows(b, top, ignore)
        for path in sorted(set(rows_a) | set(rows_b)):
            if path not in rows_b:
                out.append(f"index row only in A: {top}/{path}")
            elif path not in rows_a:
                out.append(f"index row only in B: {top}/{path}")
            elif rows_a[path] != rows_b[path]:
                changed = [f"{name}: {va!r} -> {vb!r}" for (name, va), (_, vb) in zip(rows_a[path], rows_b[path])
                           if va != vb]
                out.append(f"index row differs: {top}/{path} ({'; '.join(changed)})")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--only", nargs="+", help="top-level folders to compare (default: all)")
    parser.add_argument("--ignore", nargs="+", default=[], help="path prefixes (relative, with /) left out")
    args = parser.parse_args()
    differences = compare(args.a, args.b, args.only, args.ignore)
    for line in differences:
        print(line)
    files = len(_files(args.a, args.only, args.ignore))
    print(f"{len(differences)} differences ({files} files in A)" if differences else f"the same ({files} files)")
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()
