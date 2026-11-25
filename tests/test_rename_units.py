"""Units of the page's rename and of a failed load, run under Node (line volume's round 7): RunRename.tsx storedForm
(a typed name as the server stores it, runs.run_name) and nothingToSave (Save off), load.ts failureOf (what a page
whose run could not load shows, and whether "Try again" is offered).

Needs Node and `npm install` in viewer/; skipped without them."""

import json
import os
import shutil
import subprocess
import sys
import unicodedata

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
VIEWER = os.path.join(REPO, "viewer")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as _f:
    WORDS = json.load(_f)

# The cases go to Node as a JSON file (ASCII, every other character escaped) and come back as JSON
UNITS = r"""
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf-8"));
const failure = (e) => [m.failureOf(e), m.failureOf(e, true)];
console.log(JSON.stringify({
  stored: cases.stored.map((typed) => m.storedForm(typed)),
  nothing: cases.nothing.map(([typed, name]) => m.nothingToSave(typed, name)),
  failures: {tooLarge: failure(new m.TooLarge()), newer: failure(new m.NewerStore()),
             failed: failure(new m.StoreFailed("a run", "500")), plain: failure(new Error("x"))},
}));
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """storedForm, nothingToSave (result/view/RunRename.tsx) and failureOf with its errors (result/load.ts) bundled
    for Node: CSS, fonts and images of the components they import left out, the page's token read at import
    (app/api.ts) given a document without one."""
    folder = tmp_path_factory.mktemp("rename-units")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export {{ storedForm, nothingToSave }} from "{src}/result/view/RunRename";\n'
                     f'export {{ failureOf, NewerStore, StoreFailed, TooLarge }} from "{src}/result/load";\n',
                     encoding="utf-8")
    out = folder / "rename.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], bundle: true, "
                                  "format: 'cjs', platform: 'node', loader: {'.css': 'empty', '.png': 'dataurl', '.svg': 'text', "
                                  "'.woff2': 'empty', '.woff': 'empty'}, "
                                  "banner: {js: 'globalThis.document = globalThis.document || {querySelector: () => null};'}, "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


def run_units(bundle, tmp_path, stored=(), nothing=()) -> dict:
    """UNITS over the cases (test_viewer's _run_node): storedForm of each of `stored`, nothingToSave of each (typed,
    name) of `nothing`, and failureOf of the four kinds of error (without and with `worded`)."""
    from test_viewer import _run_node
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"stored": list(stored), "nothing": [list(c) for c in nothing]}), encoding="ascii")
    return _run_node(tmp_path, bundle, UNITS, cases)


# A typed name and its stored form: composed (NFC), each run of space separators one plain space, the ends trimmed;
# a tab, a line break and a zero-width space stay as typed (the server refuses them: such a name can be sent)
STORED = [
    ("été", "été"),          # "e" with a combining acute: U+00E9
    ("Café du Nord", "Café du Nord"),
    ("a  b", "a b"),
    ("a b", "a b"),                          # no-break space
    ("a  b", "a b"),                    # two em spaces
    ("a    b", "a b"),                  # a run of three kinds
    ("  A's   run ", "A's run"),
    (" A's run ", "A's run"),
    ("a\tb", "a\tb"),                             # a tab stays
    ("A's run\t", "A's run\t"),                   # also at the end: not trimmed
    ("a\nb", "a\nb"),                             # a line break stays
    ("a\r\nb", "a\r\nb"),
    ("a​b", "a​b"),                     # a zero-width space stays
    ("A's run​", "A's run​"),
]


def test_stored_form(bundle, tmp_path):
    """storedForm: Unicode's composed form; every run of space separators (a plain space, U+00A0, U+2003) one plain
    space; the ends trimmed; a tab, a line break and a zero-width space (U+200B) as typed."""
    out = run_units(bundle, tmp_path, stored=[typed for typed, _ in STORED])
    assert out["stored"] == [want for _, want in STORED], [(t, g) for (t, w), g in zip(STORED, out["stored"]) if g != w]


def test_nothing_to_save(bundle, tmp_path):
    """nothingToSave (Save off): true for an empty field, spaces only, the run's name as it is, with spaces added
    around it or doubled inside, or in the decomposed form; false for another name, the name with a tab in place of
    its space, and the name with a zero-width space added (the server refuses those two: Save stays on, so the
    refusal can be read)."""
    name = "Café du Nord"
    same = ["", "   ", "  ", name, "  " + name + " ", "Café  du   Nord", "Café du Nord",
            "Café du Nord", " Café  du Nord "]
    other = ["Café du Sud", "Café\tdu Nord", name + "​", "​" + name, "Cafe du Nord"]
    out = run_units(bundle, tmp_path, nothing=[(typed, name) for typed in same + other])
    assert out["nothing"] == [True] * len(same) + [False] * len(other), list(zip(same + other, out["nothing"]))


# Typed names for the agreement with the server: every space separator of Unicode (category Zs), the two joiners a
# name may hold, combining marks, Hangul jamo, emoji; a few the server refuses (skipped there)
SPACES = [chr(c) for c in range(0x3001) if unicodedata.category(chr(c)) == "Zs"]  # none above U+3000
AGREE = [
    "A's run", "  A's   run ", "Café du Nord", "Żabi Koń", "각 name",  # jamo: one syllable
    "a‌b", "\U0001F9D7‍♀️ climber",  # ZWNJ; ZWJ in an emoji
    "x́̂ marks", " lead", "trail ", "mid  dle", "\U0001F9D7" * 3,
] + [f"a{s}b{s}{s}c{s}" for s in SPACES] + [f"{s}x" for s in SPACES]
REFUSED = ["a\tb", "a\nb", "a​b", "", "   ", " x", "́"]


def test_stored_form_agrees_with_the_server(bundle, tmp_path):
    """For names without a character the server refuses, storedForm gives runs.run_name's name (the server's rule
    of what a rename stores): every space separator of Unicode, the joiners, combining marks and jamo alike; the
    names run_name refuses are left out (each of REFUSED is refused there)."""
    from messages import UserError
    import runs as rn
    stored, skipped = {}, []
    for typed in AGREE + REFUSED:
        try:
            stored[typed] = rn.run_name(typed)
        except UserError:
            skipped.append(typed)
    assert skipped == REFUSED, skipped
    assert len(stored) == len(AGREE) >= 40 and len(SPACES) == 17, (len(stored), len(SPACES))
    out = run_units(bundle, tmp_path, stored=list(stored))
    differ = [(typed, page, stored[typed]) for typed, page in zip(stored, out["stored"]) if page != stored[typed]]
    assert differ == [], differ


def test_failure_of(bundle, tmp_path):
    """failureOf: a store too large for the browser or made by a newer Find-a-Line offers no new try, with its own
    words; a store that could not be loaded offers one, with the catalogue's "This result could not be loaded."; any
    other error offers one with its own message, or with `worded` (a run's map.html) the catalogue's words."""
    out = run_units(bundle, tmp_path)["failures"]
    could_not = WORDS["ui.result.store_failed"]
    assert could_not == "This result could not be loaded."
    assert out["tooLarge"] == [{"text": WORDS["ui.result.too_large"], "again": False}] * 2, out["tooLarge"]
    assert out["newer"] == [{"text": WORDS["ui.result.newer_store"], "again": False}] * 2, out["newer"]
    assert out["failed"] == [{"text": could_not, "again": True}] * 2, out["failed"]
    assert out["plain"] == [{"text": "x", "again": True}, {"text": could_not, "again": True}], out["plain"]
