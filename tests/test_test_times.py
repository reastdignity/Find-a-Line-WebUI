"""tools/test_times.py: seconds per file and per test of a pytest run from its JUnit files, the counts by
threshold, the comparison of two runs id by id (a serial run and one of pytest-xdist write the same ids),
and setup / call / teardown from pytest's --durations lines."""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import test_times as tt  # noqa: E402

# Two files of synthetic tests (a parametrized test, a failure, a skip, a method of a class, an error in a
# fixture's setup, an error in a teardown after a pass) run by pytest 9.1.1 on 2026-11-13: serially, and
# with pytest-xdist 3.8.0 (-n 2 --dist loadfile). The JUnit files as pytest wrote them, one case a line,
# the tracebacks and the host shortened: the same ids and outcomes, xdist's cases in the order the
# workers reported them (test_beta.py's between test_alpha.py's).
SERIAL = """<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="2" failures="1" skipped="1" tests="8" time="0.072" timestamp="2026-11-13T09:37:19.069036+01:00" hostname="pc">
<testcase classname="tests.test_alpha" name="test_param[1]" time="0.000" />
<testcase classname="tests.test_alpha" name="test_param[2]" time="0.000" />
<testcase classname="tests.test_alpha" name="test_fails" time="0.000"><failure message="assert 1 == 2">def test_fails():
&gt;       assert 1 == 2
E       assert 1 == 2

tests\\test_alpha.py:10: AssertionError</failure></testcase>
<testcase classname="tests.test_alpha" name="test_skipped" time="0.000"><skipped type="pytest.skip" message="skipped here">tests\\test_alpha.py:13: skipped here</skipped></testcase>
<testcase classname="tests.test_alpha.TestGroup" name="test_in_class" time="0.000" />
<testcase classname="tests.test_beta" name="test_setup_error" time="0.000"><error message="failed on setup with &quot;RuntimeError: setup&quot;">E       RuntimeError: setup</error></testcase>
<testcase classname="tests.test_beta" name="test_teardown_error" time="0.000"><error message="failed on teardown with &quot;RuntimeError: teardown&quot;">E       RuntimeError: teardown</error></testcase>
<testcase classname="tests.test_beta" name="test_passes" time="0.000" />
</testsuite></testsuites>"""

XDIST = """<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests"><testsuite name="pytest" errors="2" failures="1" skipped="1" tests="8" time="0.837" timestamp="2026-11-13T09:37:19.931621+01:00" hostname="pc">
<testcase classname="tests.test_alpha" name="test_param[1]" time="0.000" />
<testcase classname="tests.test_alpha" name="test_param[2]" time="0.000" />
<testcase classname="tests.test_alpha" name="test_fails" time="0.001"><failure message="assert 1 == 2">def test_fails():
&gt;       assert 1 == 2
E       assert 1 == 2

tests\\test_alpha.py:10: AssertionError</failure></testcase>
<testcase classname="tests.test_beta" name="test_setup_error" time="0.000"><error message="failed on setup with &quot;RuntimeError: setup&quot;">E       RuntimeError: setup</error></testcase>
<testcase classname="tests.test_beta" name="test_teardown_error" time="0.000"><error message="failed on teardown with &quot;RuntimeError: teardown&quot;">E       RuntimeError: teardown</error></testcase>
<testcase classname="tests.test_alpha" name="test_skipped" time="0.000"><skipped type="pytest.skip" message="skipped here">tests\\test_alpha.py:13: skipped here</skipped></testcase>
<testcase classname="tests.test_alpha.TestGroup" name="test_in_class" time="0.000" />
<testcase classname="tests.test_beta" name="test_passes" time="0.000" />
</testsuite></testsuites>"""

OUTCOMES = {"tests.test_alpha::test_param[1]": "passed", "tests.test_alpha::test_param[2]": "passed",
            "tests.test_alpha::test_fails": "failed", "tests.test_alpha::test_skipped": "skipped",
            "tests.test_alpha.TestGroup::test_in_class": "passed", "tests.test_beta::test_setup_error": "error",
            "tests.test_beta::test_teardown_error": "error", "tests.test_beta::test_passes": "passed"}


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_ids_and_outcomes_of_a_serial_and_an_xdist_run(tmp_path):
    serial = tt.read([_write(tmp_path, "serial.xml", SERIAL)])
    xdist = tt.read([_write(tmp_path, "xdist.xml", XDIST)])
    assert {i: c.outcome for i, c in serial.items()} == OUTCOMES
    assert {i: c.outcome for i, c in xdist.items()} == OUTCOMES
    assert serial["tests.test_alpha.TestGroup::test_in_class"].file == "tests/test_alpha.py"
    lines, differs = tt.compare(serial, xdist, top=10)
    assert not differs
    assert lines[1] == "ids only in A: 0, only in B: 0, outcome differs: 0"


def test_a_case_written_twice_counts_once(tmp_path):
    """A pass and then its teardown's error as two cases of one id: one test, an error, the seconds summed."""
    twice = SERIAL.replace('<testcase classname="tests.test_beta" name="test_passes" time="0.000" />',
                           '<testcase classname="tests.test_beta" name="test_passes" time="0.250" />'
                           '<testcase classname="tests.test_beta" name="test_passes" time="0.500">'
                           '<error message="failed on teardown">E       OSError</error></testcase>')
    found = tt.read([_write(tmp_path, "twice.xml", twice)])
    assert len(found) == len(OUTCOMES)
    assert found["tests.test_beta::test_passes"].outcome == "error"
    assert found["tests.test_beta::test_passes"].seconds == 0.75


def test_compare_names_what_differs(tmp_path):
    a = tt.read([_write(tmp_path, "a.xml", SERIAL)])
    b_text = (SERIAL.replace('name="test_passes" time="0.000" />',
                             'name="test_passes" time="0.000"><failure message="x">x</failure></testcase>')
                    .replace('<testcase classname="tests.test_alpha" name="test_param[2]" time="0.000" />\n', "")
                    .replace("</testsuite>", '<testcase classname="tests.test_gamma" name="test_new" time="2.5" />'
                                             "</testsuite>"))
    b = tt.read([_write(tmp_path, "b.xml", b_text)])
    lines, differs = tt.compare(a, b, top=10)
    assert differs
    assert "  only in A: tests.test_alpha::test_param[2]" in lines
    assert "  only in B: tests.test_gamma::test_new" in lines
    assert "  passed -> failed: tests.test_beta::test_passes" in lines
    assert any(line.endswith("tests/test_gamma.py") and "2.50 s" in line for line in lines)
    assert tt.main(["compare", _write(tmp_path, "a2.xml", SERIAL), _write(tmp_path, "x.xml", XDIST)]) == 0
    assert tt.main(["compare", str(tmp_path / "a.xml"), str(tmp_path / "b.xml")]) == 1


def test_show_files_shares_and_thresholds(tmp_path):
    cases = [("tests.test_slow", "test_a", 40.0), ("tests.test_slow", "test_b", 6.0),
             ("tests.test_fast", "test_c", 1.0), ("tests.test_fast", "test_d", 0.5),
             ("tests.test_fast", "test_e", 12.5)]
    text = ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">' +
            "".join(f'<testcase classname="{c}" name="{n}" time="{t}" />' for c, n, t in cases) +
            "</testsuite></testsuites>")
    # a run split over two JUnit files reads as one
    half = len(text) // 2
    split = text.index("<testcase", half)
    first = text[:split] + "</testsuite></testsuites>"
    second = '<testsuites><testsuite name="pytest">' + text[split:]
    found = tt.read([_write(tmp_path, "1.xml", first), _write(tmp_path, "2.xml", second)])
    assert len(found) == 5
    lines = tt.show(found, top=2)
    assert lines[0] == "5 tests (5 passed, 0 skipped, 0 failed, 0 error), 60.00 s in all"
    assert "  >=    1 s:     4 tests,     59.50 s ( 99.2 %)" in lines
    assert "  >=    5 s:     3 tests,     58.50 s ( 97.5 %)" in lines
    assert "  >=   10 s:     2 tests,     52.50 s ( 87.5 %)" in lines
    assert "  >=   30 s:     1 tests,     40.00 s ( 66.7 %)" in lines
    files = lines.index("Seconds per file (2 files; the top 2):")
    assert lines[files + 1] == "      46.00 s   76.7 %     2 tests  tests/test_slow.py"
    assert lines[files + 2] == "      14.00 s   23.3 %     3 tests  tests/test_fast.py"
    slow = lines.index("Slowest tests (the top 2):")
    assert lines[slow + 1:] == ["      40.00 s   66.7 %  tests.test_slow::test_a",
                                "      12.50 s   20.8 %  tests.test_fast::test_e"]


def test_durations_split_setup_call_teardown(tmp_path, capsys):
    log = _write(tmp_path, "pytest.log", """........
============================= slowest durations ==============================
18.81s setup    tests/test_patch.py::test_patch_of_a_line
4.20s call     tests/test_patch.py::test_patch_of_a_line
0.50s teardown tests/test_web.py::test_page[phone]
1.25s call     tests/test_web.py::test_page[phone]
0.51s teardown tests/test_web.py::test_other
(12 durations < 0.05s hidden.  Use -vv to show these durations.)
1742 passed, 4 skipped in 2193.70s (0:36:33)
""")
    found = tt.read_durations(log)
    assert found["tests/test_web.py::test_page[phone]"] == {"teardown": 0.5, "call": 1.25}
    lines = tt.durations(found, top=5)
    assert lines[0] == "3 tests with a duration line, 25.27 s in all"
    assert lines[1].split() == ["setup", "18.81", "s", "(", "74.4", "%)"]
    assert lines[3].split() == ["teardown", "1.01", "s", "(", "4.0", "%)"]
    per_file = lines.index("Per file: setup, call, teardown (2 files; the top 2):")
    assert lines[per_file + 1].split() == ["18.81", "4.20", "0.00", "tests/test_patch.py"]
    assert lines[per_file + 2].split() == ["0.00", "1.25", "1.01", "tests/test_web.py"]
    assert tt.main(["durations", log, "--top", "1"]) == 0
    assert "Slowest teardown (the top 1):" in capsys.readouterr().out
