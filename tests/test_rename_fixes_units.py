"""Units of the rename's fix round (line volume's round 7, the code review's F2 to F4), run under Node:
RunRename.tsx answeredName (the name a rename's answer gives, or none for an answer that is no rename) and
renameFailure (a failed rename's line, and whether the name itself was refused: only then is the field marked
invalid), with FAILED_TEXT (the key of the line of a failure that came with no words of its own).

Needs Node and `npm install` in viewer/; skipped without them."""

import json
import os
import re
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
# The key FAILED_TEXT names, as RunRename.tsx writes it (a stand-in today: the words are read through the key, never
# pinned, so the test follows the key the constant will name)
with open(os.path.join(VIEWER, "src", "result", "view", "RunRename.tsx"), encoding="utf-8") as _f:
    _failed = re.search(r'^export const FAILED_TEXT = "([^"]+)";', _f.read(), re.M)
FAILED_KEY = _failed.group(1) if _failed else None  # None: a checkout without the constant

# The cases are made in Node (undefined and the errors do not travel as JSON); the results come back as JSON, an
# answer of none as null
UNITS = r"""
const named = (v) => { const got = m.answeredName(v); return got === undefined ? "undefined" : got; };
console.log(JSON.stringify({
  constant: m.FAILED_TEXT,
  named: {name: named({name: "x"}), empty: named({}), nothing: named(null), undefined: named(undefined),
          emptyName: named({name: ""}), number: named({name: 5}), nullName: named({name: null}), text: named("text"),
          ok: named({ok: true}), stored: named({ok: true, name: "Stored by the server"})},
  failures: {
    inUse: m.renameFailure(new m.ApiError("the run is in use: try again in a moment", 409)),
    refused: m.renameFailure(new m.ApiError("The server's words for the name", 400, {code: "run_name", params: {max: 100}})),
    otherCode: m.renameFailure(new m.ApiError("Another refusal", 400, {code: "bad_request", params: {}})),
    noCode: m.renameFailure(new m.ApiError("A 400 without a code", 400)),
    noWords: m.renameFailure(new m.ApiError("", 502)),
    serverError: m.renameFailure(new m.ApiError("made-up failure", 500)),
    network: m.renameFailure(new TypeError("Failed to fetch")),
    none: m.renameFailure(null),
  },
}));
"""


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """answeredName, renameFailure and FAILED_TEXT (result/view/RunRename.tsx) with ApiError (app/api.ts) bundled
    for Node as test_rename_units.py bundles RunRename.tsx: CSS, fonts and images of the components it imports left
    out, the page's token read at import given a document without one. ApiError comes from the same bundle, so an
    error made in Node is the form's ApiError."""
    folder = tmp_path_factory.mktemp("rename-fixes-units")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export {{ answeredName, renameFailure, FAILED_TEXT }} from "{src}/result/view/RunRename";\n'
                     f'export {{ ApiError }} from "{src}/app/api";\n', encoding="utf-8")
    out = folder / "rename-fixes.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], bundle: true, "
                                  "format: 'cjs', platform: 'node', loader: {'.css': 'empty', '.png': 'dataurl', '.svg': 'text', "
                                  "'.woff2': 'empty', '.woff': 'empty'}, "
                                  "banner: {js: 'globalThis.document = globalThis.document || {querySelector: () => null};'}, "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


def run_units(bundle, tmp_path) -> dict:
    from test_viewer import _run_node
    return _run_node(tmp_path, bundle, UNITS)


def test_failed_text_names_a_text_of_the_catalogue(bundle, tmp_path):
    """FAILED_TEXT, as the bundle exports it, is the key RunRename.tsx writes, and that key has a text in the
    catalogue: the words a failure without words of its own shows."""
    out = run_units(bundle, tmp_path)
    assert FAILED_KEY is not None, "RunRename.tsx exports no FAILED_TEXT"
    assert out["constant"] == FAILED_KEY, (out["constant"], FAILED_KEY)
    assert isinstance(WORDS.get(FAILED_KEY), str) and WORDS[FAILED_KEY].strip(), FAILED_KEY


def test_answered_name(bundle, tmp_path):
    """answeredName: the answer's name where it is a text with a character in it ({"name": "x"}: "x"; the server's
    {"ok": true, "name": <as stored>}: that name); none (null) for an answer without a name, an empty name, a name
    that is not a text (5, null), an answer that is no object (null, undefined, a text) and {"ok": true} alone."""
    out = run_units(bundle, tmp_path)["named"]
    assert out == {"name": "x", "empty": None, "nothing": None, "undefined": None, "emptyName": None, "number": None,
                   "nullName": None, "text": None, "ok": None, "stored": "Stored by the server"}, out


def test_rename_failure(bundle, tmp_path):
    """renameFailure: a 409 shows the catalogue's "in use", the name not refused; a 400 coded run_name shows its own
    words and is the one refusal of the name; a 400 with another code or none shows its words, the name not
    refused; a 500 with words shows them; an error answer with no words (a 502 page that is no JSON and has no
    reason phrase) and no error at all (an answer that is no rename) show FAILED_TEXT's words; a network failure
    (a TypeError) shows its own message. Only the 400 coded run_name says refused."""
    out = run_units(bundle, tmp_path)["failures"]
    assert FAILED_KEY is not None, "RunRename.tsx exports no FAILED_TEXT"
    in_use, failed = WORDS["ui.rename.in_use"], WORDS[FAILED_KEY]
    assert in_use == "The run is in use. Try again in a moment."
    assert out["inUse"] == {"line": in_use, "refused": False}, out["inUse"]
    assert out["refused"] == {"line": "The server's words for the name", "refused": True}, out["refused"]
    assert out["otherCode"] == {"line": "Another refusal", "refused": False}, out["otherCode"]
    assert out["noCode"] == {"line": "A 400 without a code", "refused": False}, out["noCode"]
    assert out["serverError"] == {"line": "made-up failure", "refused": False}, out["serverError"]
    assert out["noWords"] == {"line": failed, "refused": False}, out["noWords"]
    assert out["none"] == {"line": failed, "refused": False}, out["none"]
    assert out["network"] == {"line": "Failed to fetch", "refused": False}, out["network"]
