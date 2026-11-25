"""The loading line of a tiny run (line volume's round 7, the user's answer 3 of 2026-11-25, "Two decimals": "For
example "0.02 of 0.04 MB", only for runs this small"). Where the download's total is known and under 0.05 MB (below
50 000 bytes, where one decimal would read "0.0 of 0.0 MB"), both numbers are written in MB with two decimals, each
rounded half up on the bytes (size.ts downloadSizes); from 50 000 bytes on the line is as before (the card's cut). The
text ui.result.loading_download does not change and keeps its no-break space between the total and its unit. A total
of 0 is no total for the line (result/view/RunLoading.tsx loadingText: as one not known) and a total not known reads
the bytes got with their own cut, as before; Home's card ("under 0.1 MB") is not touched. The page:
test_tiny_run_loading_page.py.

Units under Node (test_size_units' bundle). Needs Node and `npm install` in viewer/; skipped without them."""

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_size_units import NBSP, VIEWER, WORDS, bundle  # noqa: E402,F401

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

ABOVE = 20_000  # "done above the total": this many bytes more than the total (a size header that undercounts)

# (done, total) and the line's numbers (downloadSizes): the totals at the rule's edges, each with nothing got yet,
# everything got and more than the total got
DOWNLOADS = [
    ((0, 1), ("0.00", "0.00", "MB")), ((1, 1), ("0.00", "0.00", "MB")), ((1 + ABOVE, 1), ("0.02", "0.00", "MB")),
    ((0, 4_999), ("0.00", "0.00", "MB")), ((4_999, 4_999), ("0.00", "0.00", "MB")),
    ((4_999 + ABOVE, 4_999), ("0.02", "0.00", "MB")),
    ((0, 5_000), ("0.00", "0.01", "MB")), ((5_000, 5_000), ("0.01", "0.01", "MB")),
    ((5_000 + ABOVE, 5_000), ("0.03", "0.01", "MB")),
    ((0, 49_999), ("0.00", "0.05", "MB")), ((49_999, 49_999), ("0.05", "0.05", "MB")),
    ((49_999 + ABOVE, 49_999), ("0.07", "0.05", "MB")),
    # from 50 000 bytes on: as before (the card's cut, one decimal below 10 MB)
    ((0, 50_000), ("0.0", "0.1", "MB")), ((50_000, 50_000), ("0.1", "0.1", "MB")),
    ((50_000 + ABOVE, 50_000), ("0.1", "0.1", "MB")),
    # half a hundredth: up, whatever the double of bytes / 10^6 is (0.015 and 0.045 lie below their halves)
    ((15_000, 40_000), ("0.02", "0.04", "MB")), ((45_000, 45_000), ("0.05", "0.05", "MB")),
    ((25_000, 25_000), ("0.03", "0.03", "MB")), ((14_999, 40_000), ("0.01", "0.04", "MB")),
    # the user's example
    ((19_000, 38_000), ("0.02", "0.04", "MB")),
    # a total of 0 given to downloadSizes itself: under 50 000 bytes, so two decimals (the line never asks so)
    ((0, 0), ("0.00", "0.00", "MB")),
    # a total not known: the bytes got with their own cut, as before ("0.0" below 50 000 bytes)
    ((0, None), ("0.0", "", "MB")), ((30_000, None), ("0.0", "", "MB")), ((60_000, None), ("0.1", "", "MB")),
]


def line(done: str, total: str | None, unit: str = "MB") -> str:
    """The loading line as the catalogue words it."""
    if total is None:
        return WORDS["ui.result.loading_download_unknown"].replace("{{done}}", done).replace("{{unit}}", unit)
    return (WORDS["ui.result.loading_download"].replace("{{done}}", done).replace("{{total}}", total)
            .replace("{{unit}}", unit))


# A load's progress (result/load.ts LoadProgress) and its line (loadingText)
LOADING = [
    ({"done": 19_000, "total": 38_000}, line("0.02", "0.04")),
    ({"done": 0, "total": 1}, line("0.00", "0.00")),
    ({"done": 0, "total": 4_999}, line("0.00", "0.00")),
    ({"done": 0, "total": 5_000}, line("0.00", "0.01")),
    ({"done": 49_999, "total": 49_999}, line("0.05", "0.05")),
    ({"done": 69_999, "total": 49_999}, line("0.07", "0.05")),
    ({"done": 50_000, "total": 50_000}, line("0.1", "0.1")),
    ({"done": 30_000, "total": 0}, line("0.0", None)),  # a total of 0: as one not known
    ({"done": 30_000, "total": None}, line("0.0", None)),
]

UNITS = r"""
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf-8"));
console.log(JSON.stringify({
  downloads: cases.downloads.map(([done, total]) => m.downloadSizes(done, total)),
  loading: cases.loading.map((p) => m.loadingText({phase: "download", fraction: null, ...p})),
}));
"""


@pytest.fixture(scope="module")
def units(bundle, tmp_path_factory) -> dict:  # noqa: F811
    """UNITS over every case of this module (test_viewer's _run_node), once."""
    from test_viewer import _run_node
    folder = tmp_path_factory.mktemp("tiny-cases")
    cases = folder / "cases.json"
    cases.write_text(json.dumps({"downloads": [list(c) for c, _ in DOWNLOADS], "loading": [p for p, _ in LOADING]}),
                     encoding="ascii")
    return _run_node(folder, bundle, UNITS, cases)


def test_two_decimals_below_50_000_bytes(units):
    """downloadSizes: a known total under 50 000 bytes gives both numbers in MB with two decimals, rounded half up on
    the bytes (1 and 4 999 bytes "0.00", 5 000 "0.01", 49 999 "0.05"; done 0 "0.00", done above the total in the same
    two decimals); from 50 000 bytes as before ("0.1"); a total of 0 two decimals too; a total not known as before
    (the bytes got with their own cut: "0.0" below 50 000)."""
    got = [(d["done"], d["total"], d["unit"]) for d in units["downloads"]]
    assert got == [want for _, want in DOWNLOADS], [(c, w, g) for (c, w), g in zip(DOWNLOADS, got) if g != w]


def test_the_line_of_a_tiny_run(units):
    """loadingText: "Downloading the run… 0.02 of 0.04 MB" for 19 000 of 38 000 bytes; "0.00 of 0.00 MB" for a total
    under 5 000 bytes; "0.07 of 0.05 MB" for more than the total; "0.1 of 0.1 MB" from 50 000 bytes; a total of 0 or
    none: "Downloading the run… 0.0 MB" (as before). A no-break space between the last number and its unit."""
    assert units["loading"] == [want for _, want in LOADING], \
        [(p, w, g) for (p, w), g in zip(LOADING, units["loading"]) if g != w]
    assert line("0.02", "0.04") == f"Downloading the run… 0.02 of 0.04{NBSP}MB"
