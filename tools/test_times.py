"""Run by hand: where the time of a pytest run goes, from its JUnit files (`pytest --junitxml=FILE`), and
what differs between two runs.

    python tools/test_times.py show RUN.xml [MORE.xml ...] [--top 25]   # seconds per file and per test
    python tools/test_times.py compare A.xml B.xml [--top 25]           # two runs: ids, outcomes, seconds
    python tools/test_times.py durations LOG [--top 25]                 # setup / call / teardown

`show` reads one or more JUnit files of one run (a run split over several commands) and prints the totals,
the counts of tests by threshold (at least 1, 5, 10, 30 s), the seconds per file and the slowest tests,
each with its share of the run. `compare` prints the test ids in one run and not in the other, the ids
whose outcome differs (passed / failed / error / skipped) and the seconds per file side by side, so a
serial run and a parallel one (pytest-xdist writes the same ids: `classname` and `name` of each test
case) can be checked id by id; exit code 1 when an id or an outcome differs. JUnit lumps a test's setup,
call and teardown into one time; `durations` splits them from the lines of
`pytest --durations=0 --durations-min=0` in a saved log ("12.34s setup tests/test_x.py::test_y").

A test id is `<classname>::<name>` as JUnit writes it (tests.test_web::test_page[phone]); its file is
the classname up to its module (tests/test_web.py). A test case written twice (a teardown error after a
result) counts once, with the worse outcome and the seconds summed. Standard library only.
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

OUTCOMES = ("passed", "skipped", "failed", "error")   # from the best to the worst
THRESHOLDS = (1.0, 5.0, 10.0, 30.0)
PHASES = ("setup", "call", "teardown")
DURATION = re.compile(r"^\s*([0-9.]+)s\s+(setup|call|teardown)\s+(\S.*?)\s*$")


class Case:
    """One test of a run: its id, file, outcome and seconds (JUnit's time)."""

    def __init__(self, test_id: str, file: str, outcome: str, seconds: float):
        self.id, self.file, self.outcome, self.seconds = test_id, file, outcome, seconds


def file_of(classname: str) -> str:
    """The test file of a JUnit classname: tests.test_web -> tests/test_web.py, tests.test_x.TestY ->
    tests/test_x.py (the parts up to the first module named test_* or *_test)."""
    parts = classname.split(".")
    for i, part in enumerate(parts):
        if part.startswith("test_") or part.endswith("_test"):
            return "/".join(parts[:i + 1]) + ".py"
    return "/".join(parts) + ".py"


def _outcome(case: ET.Element) -> str:
    tags = {child.tag for child in case}
    if "error" in tags:
        return "error"
    if "failure" in tags:
        return "failed"
    if "skipped" in tags:
        return "skipped"
    return "passed"


def read(paths: Iterable[str]) -> Dict[str, Case]:
    """{test id: Case} of the JUnit files of one run."""
    cases: Dict[str, Case] = {}
    for path in paths:
        for element in ET.parse(path).getroot().iter("testcase"):
            classname, name = element.get("classname", ""), element.get("name", "")
            test_id = f"{classname}::{name}"
            outcome, seconds = _outcome(element), float(element.get("time") or 0.0)
            if test_id in cases:  # written twice: the worse outcome, the seconds summed
                old = cases[test_id]
                if OUTCOMES.index(outcome) > OUTCOMES.index(old.outcome):
                    old.outcome = outcome
                old.seconds += seconds
            else:
                cases[test_id] = Case(test_id, file_of(classname), outcome, seconds)
    return cases


def per_file(cases: Dict[str, Case]) -> Dict[str, Tuple[float, int]]:
    """{file: (seconds, tests)}."""
    out: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0])
    for case in cases.values():
        out[case.file][0] += case.seconds
        out[case.file][1] += 1
    return {file: (seconds, int(count)) for file, (seconds, count) in out.items()}


def counts(cases: Dict[str, Case]) -> Dict[str, int]:
    out = {outcome: 0 for outcome in OUTCOMES}
    for case in cases.values():
        out[case.outcome] += 1
    return out


def _share(part: float, whole: float) -> str:
    return f"{100.0 * part / whole:5.1f} %" if whole > 0 else "    - %"


def show(cases: Dict[str, Case], top: int) -> List[str]:
    total = sum(case.seconds for case in cases.values())
    numbers = counts(cases)
    lines = [f"{len(cases)} tests ({', '.join(f'{numbers[o]} {o}' for o in OUTCOMES)}), {total:.2f} s in all",
             "", "Tests by threshold:"]
    for threshold in THRESHOLDS:
        over = [case.seconds for case in cases.values() if case.seconds >= threshold]
        lines.append(f"  >= {threshold:4g} s: {len(over):5d} tests, {sum(over):9.2f} s ({_share(sum(over), total)})")
    files = sorted(per_file(cases).items(), key=lambda item: (-item[1][0], item[0]))
    lines += ["", f"Seconds per file ({len(files)} files; the top {min(top, len(files))}):"]
    for file, (seconds, count) in files[:top]:
        lines.append(f"  {seconds:9.2f} s  {_share(seconds, total)}  {count:4d} tests  {file}")
    slow = sorted(cases.values(), key=lambda case: (-case.seconds, case.id))
    lines += ["", f"Slowest tests (the top {min(top, len(slow))}):"]
    for case in slow[:top]:
        mark = "" if case.outcome == "passed" else f"  [{case.outcome}]"
        lines.append(f"  {case.seconds:9.2f} s  {_share(case.seconds, total)}  {case.id}{mark}")
    return lines


def compare(a: Dict[str, Case], b: Dict[str, Case], top: int) -> Tuple[List[str], bool]:
    """The lines comparing run A with run B, and whether an id or an outcome differs."""
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    changed = sorted(i for i in set(a) & set(b) if a[i].outcome != b[i].outcome)
    total_a, total_b = sum(c.seconds for c in a.values()), sum(c.seconds for c in b.values())
    lines = [f"A: {len(a)} tests, {total_a:.2f} s; B: {len(b)} tests, {total_b:.2f} s",
             f"ids only in A: {len(only_a)}, only in B: {len(only_b)}, outcome differs: {len(changed)}"]
    lines += [f"  only in A: {i}" for i in only_a]
    lines += [f"  only in B: {i}" for i in only_b]
    lines += [f"  {a[i].outcome} -> {b[i].outcome}: {i}" for i in changed]
    files_a, files_b = per_file(a), per_file(b)
    files = sorted(set(files_a) | set(files_b),
                   key=lambda f: (-max(files_a.get(f, (0.0, 0))[0], files_b.get(f, (0.0, 0))[0]), f))
    lines += ["", f"Seconds per file, A and B ({len(files)} files; the top {min(top, len(files))}):"]
    for file in files[:top]:
        sa, sb = files_a.get(file, (0.0, 0))[0], files_b.get(file, (0.0, 0))[0]
        ratio = f"{sb / sa:6.2f}x" if sa > 0 else "      -"
        lines.append(f"  {sa:9.2f} s  {sb:9.2f} s  {ratio}  {file}")
    return lines, bool(only_a or only_b or changed)


def read_durations(path: str) -> Dict[str, Dict[str, float]]:
    """{pytest node id: {phase: seconds}} from the --durations lines of a saved pytest log."""
    out: Dict[str, Dict[str, float]] = defaultdict(dict)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            match = DURATION.match(line)
            if match:
                seconds, phase, node = float(match.group(1)), match.group(2), match.group(3)
                out[node][phase] = out[node].get(phase, 0.0) + seconds
    return dict(out)


def durations(found: Dict[str, Dict[str, float]], top: int) -> List[str]:
    totals = {phase: sum(t.get(phase, 0.0) for t in found.values()) for phase in PHASES}
    whole = sum(totals.values())
    lines = [f"{len(found)} tests with a duration line, {whole:.2f} s in all"]
    lines += [f"  {phase:8s} {totals[phase]:9.2f} s ({_share(totals[phase], whole)})" for phase in PHASES]
    files: Dict[str, Dict[str, float]] = defaultdict(lambda: dict.fromkeys(PHASES, 0.0))
    for node, phases in found.items():
        for phase, seconds in phases.items():
            files[node.split("::", 1)[0]][phase] += seconds
    order = sorted(files.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    lines += ["", f"Per file: setup, call, teardown ({len(order)} files; the top {min(top, len(order))}):"]
    for file, phases in order[:top]:
        lines.append("  " + "  ".join(f"{phases[p]:8.2f}" for p in PHASES) + f"  {file}")
    for phase in PHASES:
        slow = sorted(((t.get(phase, 0.0), node) for node, t in found.items()), key=lambda x: (-x[0], x[1]))
        lines += ["", f"Slowest {phase} (the top {min(top, len(slow))}):"]
        lines += [f"  {seconds:9.2f} s  {node}" for seconds, node in slow[:top] if seconds > 0]
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("show", help="seconds per file and per test of one run")
    one.add_argument("junit", nargs="+", help="JUnit files of one run")
    two = commands.add_parser("compare", help="two runs: ids, outcomes, seconds per file")
    two.add_argument("a")
    two.add_argument("b")
    log = commands.add_parser("durations", help="setup / call / teardown from pytest's --durations lines")
    log.add_argument("log")
    for sub in (one, two, log):
        sub.add_argument("--top", type=int, default=25, help="rows of each list (default 25)")
    args = parser.parse_args(argv)
    code = 0
    if args.command == "show":
        lines = show(read(args.junit), args.top)
    elif args.command == "compare":
        lines, differs = compare(read([args.a]), read([args.b]), args.top)
        code = 1 if differs else 0
    else:
        lines = durations(read_durations(args.log), args.top)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
