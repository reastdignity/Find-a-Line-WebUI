"""tests/regression.py skips an entry whose needs cannot be met here: its variable not set (needs_env), or a folder
it names below that variable's folder missing (needs_path: a mirror holding Slovakia's tiles only, as on the VPS, or a
process's stale value), instead of failing it; with --mirror-url (the project's data server) the entries that read our
own tiles run without the folder. Without --mirror-url the data server is never asked."""

import importlib.util
import json
import os


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("regression_tool", os.path.join(REPO, "tests", "regression.py"))
regression = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(regression)


def test_unmet_needs(tmp_path, monkeypatch):
    test = {"needs_env": "FINDALINE_MIRROR", "needs_path": ["madeira/dtm/2m"]}
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    assert regression.unmet_needs(test) == "FINDALINE_MIRROR not set"
    monkeypatch.setenv("FINDALINE_MIRROR", str(tmp_path / "gone"))  # a stale value
    assert regression.unmet_needs(test) == "FINDALINE_MIRROR has no madeira/dtm/2m"
    (tmp_path / "slovakia" / "dmr5" / "1m").mkdir(parents=True)  # Slovakia's tiles only
    monkeypatch.setenv("FINDALINE_MIRROR", str(tmp_path))
    assert regression.unmet_needs(test) == "FINDALINE_MIRROR has no madeira/dtm/2m"
    assert regression.unmet_needs({"needs_env": "FINDALINE_MIRROR", "needs_path": ["slovakia/dmr5/1m"]}) is None
    (tmp_path / "madeira" / "dtm" / "2m").mkdir(parents=True)
    assert regression.unmet_needs(test) is None
    assert regression.unmet_needs({}) is None and regression.unmet_needs({"needs_env": "FINDALINE_MIRROR"}) is None
    # Madeira's island groups, each a folder of its own: one present does not stand for another
    islands = {"needs_env": "FINDALINE_MIRROR", "needs_path": ["selvagens/dtm/5m"]}
    (tmp_path / "porto-santo" / "dtm" / "5m").mkdir(parents=True)
    assert regression.unmet_needs(islands) == "FINDALINE_MIRROR has no selvagens/dtm/5m"
    (tmp_path / "selvagens" / "dtm" / "5m").mkdir(parents=True)
    assert regression.unmet_needs(islands) is None
    # With --mirror-url the entries that name their mirror folders run without the folder (the data server has them);
    # an empty value is none, and other needs stay
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    assert regression.unmet_needs(test, "http://127.0.0.1:8080") is None
    assert regression.unmet_needs(test, "") == regression.unmet_needs(test, None) == "FINDALINE_MIRROR not set"
    monkeypatch.delenv("OPENTOPOGRAPHY_API_KEY", raising=False)
    assert regression.unmet_needs({"needs_env": "OPENTOPOGRAPHY_API_KEY"}, "http://127.0.0.1:8080") is not None


def test_the_data_server_only_when_named(tmp_path, monkeypatch):
    """regression.py asks the project's data server only with --mirror-url: FINDALINE_MIRROR_URL off otherwise, for
    its searches and for itself. The child process at the end guards this test's own putting back of "off" (as
    tests/conftest.py sets it), not conftest's line: tests/test_mirror_client.py::
    test_the_processes_of_the_tests_ask_no_data_server guards that."""
    import subprocess
    import sys
    monkeypatch.setattr(regression, "write_doc", lambda tests: None)
    try:
        os.environ["FINDALINE_MIRROR_URL"] = "https://elsewhere.example"
        for argv, expected in ((["--mirror-url", "http://127.0.0.1:9"], "http://127.0.0.1:9"), ([], "off")):
            monkeypatch.setattr(sys, "argv", ["regression.py", "--write-doc", *argv])
            try:
                regression.main()
            except SystemExit:
                pass
            assert os.environ["FINDALINE_MIRROR_URL"] == expected
    finally:
        os.environ["FINDALINE_MIRROR_URL"] = "off"
    code = "import os; print(repr(os.environ.get('FINDALINE_MIRROR_URL', 'unset')))"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip() == "'off'"


def test_mirror_entries_name_their_folders():
    """Every entry that reads the mirror names the folders it reads, and they are the catalogue's mirror folders."""
    import sources as src
    folders = {layer.mirror for s in src.SOURCES.values() for layer in (s.nmt, s.nmpt)
               if isinstance(layer, src.GridTiles)}
    with open(regression.TESTS, encoding="utf-8") as f:
        tests = json.load(f)
    mirrored = {k: t for k, t in tests.items() if t.get("needs_env") == "FINDALINE_MIRROR"}
    assert {"R21", "R80", "R81"} <= set(mirrored)
    for test_id, test in mirrored.items():
        assert test.get("needs_path") and set(test["needs_path"]) <= folders, test_id
    assert tests["R80"]["needs_path"] == ["madeira/dtm/2m"] and tests["R81"]["needs_path"] == ["aosta/dtm/2m"]
    assert tests["R86"]["needs_path"] == ["porto-santo/dtm/5m"] and tests["R87"]["needs_path"] == ["desertas/dtm/5m"]
    assert tests["R88"]["needs_path"] == ["selvagens/dtm/5m"]
