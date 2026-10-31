"""
README's lists of the data sources, generated from the catalogue (sources/catalogue/).

Rewrites the "Data sources" table of README.md (between `<!-- sources-table:start -->` and
`<!-- sources-table:end -->`, from each source's `listing`) and the ids in the `--source` row
of the options table (between `<!-- source-ids:start -->` and `<!-- source-ids:end -->`,
inside the cell: markers on lines of their own would break the table).
tests/test_catalogue.py::test_docs_list_every_source fails while README is out of date.

    uv run tools/source_docs.py           # rewrite README.md
    uv run tools/source_docs.py --check   # exit 1 if README.md is out of date
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import sources as src  # noqa: E402

README = os.path.join(HERE, "README.md")
TABLE = ("<!-- sources-table:start -->", "<!-- sources-table:end -->")
IDS = ("<!-- source-ids:start -->", "<!-- source-ids:end -->")
# The rows of README before they were generated (2026-10-31), in its order
TABLE_ORDER = ["geoportal", "malta", "malta2012", "spain", "spain_canarias", "swisstopo", "slovakia", "usa",
               "alaska", "alaska_ifsar", "usgs10m", "europe", "nasadem"]
IDS_ORDER = ["geoportal", "swisstopo", "slovakia", "malta", "malta2012", "spain", "spain_canarias", "usa",
             "alaska", "alaska_ifsar", "usgs10m", "europe", "nasadem"]


def table() -> str:
    """The "Data sources" table, a row per source and one for --elevation-file."""
    rows = ["| `--source` | Where | Terrain (DTM) | Surface (DSM, trees/buildings) | Orthophoto (cached) |",
            "| --- | --- | --- | --- | --- |"]
    for sid in TABLE_ORDER:
        where, terrain, surface, ortho = src.SOURCES[sid].listing
        rows.append(f"| `{sid}` | {where} | {terrain} | {surface} | {ortho} |")
    rows.append("| `files` | your files | `--elevation-file` | `--surface-file` (optional) | – |")
    return "\n".join(rows)


def ids() -> str:
    """The values of --source."""
    return ", ".join(f"`{sid}`" for sid in ["auto", *IDS_ORDER, "files"])


def _between(text: str, markers, content: str, block: bool) -> str:
    start, end = markers
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if len(pattern.findall(text)) != 1:
        raise SystemExit(f"README.md must hold {start} ... {end} once")
    inner = f"\n{content}\n" if block else content
    return pattern.sub(lambda _: start + inner + end, text)


def render(text: str) -> str:
    """README's text with the generated parts rewritten."""
    text = _between(text, TABLE, table(), block=True)
    return _between(text, IDS, ids(), block=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="only check; exit 1 if README.md is out of date")
    args = parser.parse_args(argv)
    with open(README, encoding="utf-8") as f:
        text = f.read()
    new = render(text)
    if args.check:
        if new != text:
            print("README.md is out of date: run `uv run tools/source_docs.py`")
            return 1
        return 0
    if new != text:
        with open(README, "w", encoding="utf-8") as f:
            f.write(new)
        print("README.md rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
