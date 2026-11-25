"""Units of the sizes the page shows (line volume's round 7, step 2d as reduced), run under Node: size.ts sizeText (a
run's size as stored, on Home's card) and downloadSizes (the two numbers of the line shown while a run downloads),
and result/view/RunLoading.tsx loadingText (that line's words). A MB is 10^6 bytes and a GB 10^9; one decimal below
10 MB, whole MB up to 999, then GB with one decimal, each rounded; "under 0.1 MB" where one decimal would read "0.0".
The line counts in the total's unit and cut, so it ends at the card's number; a total under 50 000 bytes, where one
decimal would read "0.0", in MB with two decimals (the user's answer 3 of 2026-11-25: test_tiny_run_loading.py). A size never breaks inside: its number
and its unit (and "under") are joined by no-break spaces (U+00A0, written NBSP below), in the card and in the line.

Needs Node and `npm install` in viewer/; skipped without them."""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(REPO, "viewer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    WORDS = json.load(_f)
NBSP = "\u00a0"  # (since the fix round: a size never breaks inside, the design review's finding 3)
UNDER = f"under{NBSP}0.1{NBSP}MB"

# A size in bytes and its words (sizeText): the cut's edges on both sides, as the user's answer 2 a draws them
SIZES = [
    (0, UNDER), (1, UNDER), (49_999, UNDER),
    (50_000, f"0.1{NBSP}MB"), (99_999, f"0.1{NBSP}MB"), (100_000, f"0.1{NBSP}MB"), (612_000, f"0.6{NBSP}MB"),
    (9_940_000, f"9.9{NBSP}MB"), (9_949_999, f"9.9{NBSP}MB"), (9_950_000, f"10{NBSP}MB"), (46_800_000, f"47{NBSP}MB"),
    (247_300_000, f"247{NBSP}MB"), (999_400_000, f"999{NBSP}MB"), (999_499_999, f"999{NBSP}MB"), (999_500_000, f"1.0{NBSP}GB"),
    (1_000_000_000, f"1.0{NBSP}GB"), (1_840_000_000, f"1.8{NBSP}GB"),
]
# A download's bytes got and its total (None: not known) and its numbers (downloadSizes)
DOWNLOADS = [
    ((41e6, 247.3e6), {"done": "41", "total": "247", "unit": "MB"}),
    ((412e6, 1.84e9), {"done": "0.4", "total": "1.8", "unit": "GB"}),
    ((0.3e6, 0.612e6), {"done": "0.3", "total": "0.6", "unit": "MB"}),
    ((19_000, 38_000), {"done": "0.02", "total": "0.04", "unit": "MB"}),  # never "under" in the line: two decimals
    ((247.3e6, 247.3e6), {"done": "247", "total": "247", "unit": "MB"}),
    ((41e6, None), {"done": "41", "total": "", "unit": "MB"}),
    ((3e6, None), {"done": "3.0", "total": "", "unit": "MB"}),
    ((1.2e9, None), {"done": "1.2", "total": "", "unit": "GB"}),
]
# Sizes whose card number and loading line's total must agree
AGREE = [38_000, 612_000, 9.95e6, 46.8e6, 247.3e6, 999.5e6, 1.84e9]
# A load's progress (result/load.ts LoadProgress; None: not started) and its line
LOADING = [
    (None, WORDS["ui.result.loading_start"]),
    ({"phase": "parse", "fraction": None}, WORDS["ui.result.loading_parse"]),
    ({"phase": "groups", "fraction": None}, WORDS["ui.result.loading_groups"]),
    ({"phase": "download", "fraction": None}, WORDS["ui.result.loading_start"]),  # no bytes known yet
    ({"phase": "download", "fraction": 41 / 247.3, "done": 41e6, "total": 247.3e6}, f"Downloading the run… 41 of 247{NBSP}MB"),
    ({"phase": "download", "fraction": 412 / 1840, "done": 412e6, "total": 1.84e9}, f"Downloading the run… 0.4 of 1.8{NBSP}GB"),
    ({"phase": "download", "fraction": None, "done": 41e6, "total": None}, f"Downloading the run… 41{NBSP}MB"),
    ({"phase": "download", "fraction": None, "done": 41e6, "total": 0}, f"Downloading the run… 41{NBSP}MB"),
]

# The cases go to Node as a JSON file; the numbers JSON cannot carry (undefined, NaN, the infinities) are made there
UNITS = r"""
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf-8"));
const none = [null, undefined, -1, -0.5, -1e9, NaN, Infinity, -Infinity];
console.log(JSON.stringify({
  sizes: cases.sizes.map((b) => m.sizeText(b)),
  none: none.map((b) => m.sizeText(b)),
  downloads: cases.downloads.map(([done, total]) => m.downloadSizes(done, total)),
  agree: cases.agree.map((b) => [m.sizeText(b), m.downloadSizes(b, b)]),
  loading: cases.loading.map((p) => m.loadingText(p)),
}));
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """sizeText, downloadSizes (size.ts) and loadingText (result/view/RunLoading.tsx) bundled for Node as
    test_rename_units bundles its units: CSS, fonts and images of the components they import left out, a document
    without anything for code that reads the page at import."""
    folder = tmp_path_factory.mktemp("size-units")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export {{ sizeText, downloadSizes }} from "{src}/size";\n'
                     f'export {{ loadingText }} from "{src}/result/view/RunLoading";\n', encoding="utf-8")
    out = folder / "size.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], bundle: true, "
                                  "format: 'cjs', platform: 'node', loader: {'.css': 'empty', '.png': 'dataurl', '.svg': 'text', "
                                  "'.woff2': 'empty', '.woff': 'empty'}, "
                                  "banner: {js: 'globalThis.document = globalThis.document || {querySelector: () => null};'}, "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


@pytest.fixture(scope="module")
def units(bundle, tmp_path_factory) -> dict:
    """UNITS over every case of this module (test_viewer's _run_node), once."""
    from test_viewer import _run_node
    folder = tmp_path_factory.mktemp("size-cases")
    cases = folder / "cases.json"
    cases.write_text(json.dumps({"sizes": [b for b, _ in SIZES], "downloads": [list(c) for c, _ in DOWNLOADS],
                                 "agree": AGREE, "loading": [p for p, _ in LOADING]}), encoding="ascii")
    return _run_node(folder, bundle, UNITS, cases)


def test_size_text(units):
    """sizeText cuts a size by the rule: "under 0.1 MB" below 50 000 bytes (0 and 1 byte too), one decimal of a MB
    of 10^6 bytes from there to 9 949 999 bytes, whole MB from 9 950 000 to 999 499 999, then GB of 10^9 bytes with
    one decimal; the number and the unit (and "under") joined by no-break spaces, no plain space in a size."""
    assert units["sizes"] == [want for _, want in SIZES], [(b, w, g) for (b, w), g in zip(SIZES, units["sizes"]) if g != w]
    # (since the fix round: a size never breaks inside, the design review's finding 3; before it a plain space, never
    # U+00A0)
    assert all(NBSP in s and " " not in s for s in units["sizes"]), units["sizes"]


def test_no_size_has_no_words(units):
    """sizeText of no size (null, undefined) and of a number that is none (negative, NaN, either infinity) is empty."""
    assert units["none"] == [""] * 8, units["none"]


def test_download_sizes(units):
    """downloadSizes gives the bytes got and the total in the total's unit and with its cut ("41" of "247" MB, "0.4"
    of "1.8" GB, "0.3" of "0.6" MB; under 50 000 bytes two decimals, "0.02" of "0.04" MB: never "under"); a total not
    known: the bytes got with their own cut and unit, the total empty."""
    got = units["downloads"]
    assert got == [want for _, want in DOWNLOADS], [(c, w, g) for (c, w), g in zip(DOWNLOADS, got) if g != w]


def test_the_card_and_the_line_agree(units):
    """For a spread of sizes over every part of the cut, the loading line's total with its unit is the card's size
    (sizeText), but where the card says "under 0.1 MB" (the line then reads two decimals: "0.04"); both join the
    number and the unit
    by a no-break space (since the fix round: the design review's finding 3)."""
    differ, under = [], []
    for size, (card, line) in zip(AGREE, units["agree"]):
        if card == UNDER:
            under.append((size, line))
        elif f"{line['total']}{NBSP}{line['unit']}" != card:
            differ.append((size, card, line))
    assert differ == [], differ
    assert under == [(38_000, {"done": "0.04", "total": "0.04", "unit": "MB"})], under
    assert [card for card, _ in units["agree"]] == [UNDER] + [f"{n}{NBSP}{u}" for n, u in (("0.6", "MB"), ("10", "MB"), ("47", "MB"),
                                                                                         ("247", "MB"), ("1.0", "GB"), ("1.8", "GB"))]


def test_loading_text(units):
    """loadingText: not started and a download with no bytes known yet say the catalogue's ui.result.loading_start;
    reading and grouping say their texts; a download with its total "Downloading the run… 41 of 247 MB" or "… 0.4 of
    1.8 GB" (the total's unit); a total not known (none or 0) "Downloading the run… 41 MB"; a no-break space between
    the last number and its unit, plain spaces elsewhere."""
    assert units["loading"] == [want for _, want in LOADING], [(p, w, g) for (p, w), g in zip(LOADING, units["loading"]) if g != w]


def test_the_catalogue_texts():
    """The six texts of the sizes and the loading line, word for word (a no-break space inside a size: between its
    number and its unit, and in "under 0.1 MB" both), and the start's three."""
    # (since the fix round: a size never breaks inside, the design review's finding 3; the words are as before)
    assert WORDS["ui.size.value"] == "{{n}}" + NBSP + "{{unit}}"
    assert WORDS["ui.size.mb"] == "MB" and WORDS["ui.size.gb"] == "GB"
    assert WORDS["ui.size.under"] == "under" + NBSP + "0.1" + NBSP + "MB"
    assert WORDS["ui.result.loading_download"] == "Downloading the run… {{done}} of {{total}}" + NBSP + "{{unit}}"
    assert WORDS["ui.result.loading_download_unknown"] == "Downloading the run… {{done}}" + NBSP + "{{unit}}"
    assert [WORDS[f"ui.result.loading_{k}"] for k in ("start", "parse", "groups")] == \
        ["Loading the run…", "Reading the lines…", "Grouping the lines…"]
