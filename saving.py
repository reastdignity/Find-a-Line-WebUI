"""
Step 5 in processes of its own: the line files of a run (lines.csv, lines.geojson, data.js and
lines.js) written by children of the search's process, each from the same functions as before
(runs.save_results, mapping.write_map_scripts), so the files are byte for byte what the search's
process writes with one process.

Building the texts of a million lines is Python string work on one core (docs/performance.md,
round 3: 112 s for 2.07 million lines on the VPS); the four files are independent, so with enough
cores each gets a process. The lines go to the children as files in the search's work folder
(`hand_over`: every column of the LineTable, the groups' arrays and the arrays of the profiles'
batches as .npy, memory-mapped by the children; the few profiles that are dicts, run.json's
values and the heads of the map's scripts as JSON): nothing is pickled through a pipe, and Windows
has no fork. The children are plain subprocesses (`python saving.py <folder> <run path> <files>`),
not multiprocessing's: the web worker's phase process is daemonic and may not start those. Each
child prints a line per chunk written ("<count>\t<file>"), which the parent turns into the Compute
bars "saving results" and "saving the map" (their totals the lines, as before); a child's error
fails the step: a non-zero exit raises RuntimeError in the parent with the end of the child's
stderr (on the public site the parent's Redact masks it, as every error). The hand-over folder is
removed afterwards, also on failure.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

import helpers as sh
import mapping as mp
import runs as rn
from progress import progress

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = "saving"  # the hand-over folder, in the search's work folder
RESULT_FILES = ("lines.csv", "lines.geojson")  # runs.save_results
MAP_FILES = ("data.js", "lines.js")  # mapping.write_map_scripts
# Below this many lines the search's process writes the files itself: a child takes about a second
# to start (the interpreter and the imports: numpy, rasterio through grid, pyproj), and the texts
# of each file's values are made again in every child, so a run gains only when its slowest file
# takes longer than that (measured on the dev PC with 7 cores, docs/performance.md round 3, wave
# 3: swiss-long's 1.7 M lines 20 → 13 s, R9's 85 671 lines with every profile 3.1 → 3.4 s; the
# VPS's core is about 4 times slower per line, so its break-even lies lower)
MIN_LINES = 100_000
STDERR_LINES = 30  # of a failed child's stderr kept in the error
PROFILE_ARRAYS = ("offsets", "d", "z", "s", "w", "g", "small", "flags", "zone")  # helpers.Profiles


def processes(threads: Optional[int]) -> int:
    """How many processes write a run's line files for a line search of `threads` threads
    (search.line_threads; None: the CPUs of this computer less one, find_valid_lines' default):
    1 (the search's own process, as before) below 2 threads, 2 below 4, else 4."""
    if threads is None:
        threads = max(1, (os.cpu_count() or 2) - 1)
    return 1 if threads < 2 else 2 if threads < 4 else 4


def plan(count: int, map_files: bool = True) -> List[Tuple[str, ...]]:
    """The files of each child for `count` processes (processes()): none for one process; with
    four a child per file, with two the results' files apart from the map's (or, without map
    files, lines.csv apart from lines.geojson)."""
    if count < 2:
        return []
    files = RESULT_FILES + (MAP_FILES if map_files else ())
    if count >= 4 or not map_files:
        return [(name,) for name in files]
    return [RESULT_FILES, MAP_FILES]


def hand_over(folder: str, lines: sh.LineTable, groups: mp.Groups, meta: Dict,
              heads: Optional[Tuple[str, str]]):
    """Write what the children read into `folder`: the lines' columns ("column-<name>.npy"),
    the groups ("groups-<name>.npy"), the arrays of every batch of profiles the lines' profiles
    come from ("profiles-<b>-<name>.npy") with which line has which profile of which batch, and
    saving.json: the names of the columns and the batches' arrays, the profiles that are dicts
    (profile_of_line's at the edges of tiles), run.json's values (`meta`) and the heads of the
    map's scripts (mapping.map_heads; None without a map)."""
    os.makedirs(folder, exist_ok=True)
    for name, column in lines.columns.items():
        np.save(os.path.join(folder, f"column-{name}.npy"), column)
    for name in ("rep", "members", "start"):
        np.save(os.path.join(folder, f"groups-{name}.npy"), getattr(groups, name))
    batches, present, lifts, dicts = {}, [], [], {}
    of_batch, index, rows = [], [], []
    for k, profile in lines.profiles.items():
        if isinstance(profile, sh.Profile):
            b = batches.setdefault(id(profile.batch), len(batches))
            if b == len(present):
                batch = profile.batch
                present.append([name for name in PROFILE_ARRAYS if getattr(batch, name) is not None])
                lifts.append(batch.lift)  # a float or None (the end zone and the A-frames: helpers.Profiles)
                for name in present[-1]:
                    np.save(os.path.join(folder, f"profiles-{b}-{name}.npy"), getattr(batch, name))
            rows.append(k)
            of_batch.append(b)
            index.append(profile.index)
        else:
            dicts[str(k)] = profile
    for name, values in (("rows", rows), ("batch", of_batch), ("index", index)):
        np.save(os.path.join(folder, f"profile-{name}.npy"), np.array(values, dtype=np.int64))
    with open(os.path.join(folder, "saving.json"), "w", encoding="utf-8") as f:
        json.dump({"columns": list(lines.columns), "batches": present, "lifts": lifts, "dicts": dicts, "meta": meta,
                   "heads": heads}, f, ensure_ascii=False)


def load(folder: str) -> Tuple[sh.LineTable, mp.Groups, Dict, Optional[Tuple[str, str]]]:
    """What hand_over wrote, the arrays memory-mapped: the lines (with their profiles), the
    groups, run.json's values and the heads of the map's scripts."""
    with open(os.path.join(folder, "saving.json"), encoding="utf-8") as f:
        info = json.load(f)

    def array(name: str) -> np.ndarray:
        path = os.path.join(folder, name + ".npy")
        try:
            return np.load(path, mmap_mode="r")
        except ValueError:  # an empty array cannot be mapped
            return np.load(path)

    columns = {name: array(f"column-{name}") for name in info["columns"]}
    groups = mp.Groups(*(array(f"groups-{name}") for name in ("rep", "members", "start")))
    batches = [sh.Profiles(**{name: array(f"profiles-{b}-{name}") if name in present else None
                              for name in PROFILE_ARRAYS}, lift=lift)
               for b, (present, lift) in enumerate(zip(info["batches"], info["lifts"]))]
    rows, of_batch, index = (array(f"profile-{name}").tolist() for name in ("rows", "batch", "index"))
    profiles = {k: sh.Profile(batches[b], i) for k, b, i in zip(rows, of_batch, index)}
    profiles.update({int(k): profile for k, profile in info["dicts"].items()})
    heads = info["heads"]
    return sh.LineTable(columns, profiles), groups, info["meta"], None if heads is None else tuple(heads)


def _read(stream, sink: Callable[[str], None]):
    """Hands every line of a child's stream (bytes) to sink, decoded; a thread, so neither pipe fills."""
    for line in stream:
        sink(line.decode("utf-8", "replace").rstrip("\r\n"))
    stream.close()


def write_files(folder: str, run_path: str, children: List[Tuple[str, ...]], n: int,
                between: Callable[[], None] = lambda: None):
    """Write the files of `children` (plan()) for the lines of `folder` (hand_over) into the run's
    folder in a child process each, all at once. The Compute bar shows "saving results" while the
    RESULT_FILES are written (its count the lines of the slower file) and "saving the map" while
    the MAP_FILES are; `between` runs after the first bar is finished (the parent's own small
    files). A child that fails ends the others and raises RuntimeError with its stderr."""
    counts = {name: 0 for files in children for name in files}
    messages = queue.Queue()
    errors: Dict[tuple, List[str]] = {}
    started = []
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    def progress_line(files: tuple, line: str):
        count, _, name = line.partition("\t")
        if name in files:
            try:
                messages.put((name, int(count)))
            except ValueError:  # something else printed by a library: not a count
                pass

    try:
        for files in children:
            process = subprocess.Popen([sys.executable, os.path.join(HERE, "saving.py"), folder, run_path, *files],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=env, cwd=HERE)
            started.append((files, process))
            errors[files] = []
            threading.Thread(target=_read, args=(process.stdout, lambda line, f=files: progress_line(f, line)),
                             daemon=True).start()
            threading.Thread(target=_read, args=(process.stderr, errors[files].append), daemon=True).start()
        _follow(started, counts, messages, errors, n, between)
    finally:
        for _, process in started:
            if process.poll() is None:
                process.kill()
                process.wait()


def _follow(started: list, counts: Dict[str, int], messages: "queue.Queue", errors: Dict[tuple, List[str]],
            n: int, between: Callable[[], None]):
    """The bars from the children's counts until every child has ended."""
    of = lambda wanted: [f for files, _ in started for f in files if f in wanted]  # noqa: E731
    phases = [("saving results", of(RESULT_FILES)), ("saving the map", of(MAP_FILES))]

    def ended(files: List[str]) -> bool:
        return all(process.poll() is not None for names, process in started if set(names) & set(files))

    def failed():
        for files, process in started:
            if process.poll() not in (None, 0):
                return files, process
        return None

    for k, (stage, files) in enumerate(phases):
        if not files:
            continue
        progress.compute.start(stage, n, unit="line")
        shown = 0
        label = ", ".join(files)
        while True:
            try:
                name, count = messages.get(timeout=0.1)
                counts[name] = max(counts[name], count)
            except queue.Empty:
                pass
            done = min(counts[name] for name in files)
            if done > shown:
                progress.compute.update(done - shown, file=label)
                shown = done
            bad = failed()
            if bad is not None:
                files_failed, process = bad
                for _ in range(50):  # the stderr thread may still be reading
                    if process.stderr.closed:
                        break
                    time.sleep(0.02)
                tail = "\n".join(errors[files_failed][-STDERR_LINES:])
                print(f"saving {', '.join(files_failed)} failed (exit code {process.returncode}):\n{tail}",
                      file=sys.stderr, flush=True)
                raise RuntimeError(f"saving {', '.join(files_failed)} failed (exit code {process.returncode}): "
                                   + (tail.strip().splitlines() or ["no message"])[-1])
            if ended(files):
                break
        progress.compute.finish()
        if k == 0:
            between()


def save(work: str, run_path: str, lines: sh.LineTable, groups: mp.Groups, meta: Dict,
         heads: Optional[Tuple[str, str]], children: List[Tuple[str, ...]], between: Callable[[], None]):
    """hand_over into `<work>/saving`, write_files, and the hand-over folder removed afterwards."""
    folder = os.path.join(work, FOLDER)
    try:
        hand_over(folder, lines, groups, meta, heads)
        write_files(folder, run_path, children, len(lines), between)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main(argv: List[str]):
    """A child: `saving.py <folder> <run path> <file> ...`, the files among RESULT_FILES and MAP_FILES."""
    folder, run_path, *files = argv
    lines, groups, meta, heads = load(folder)
    written: Dict[str, int] = {}

    def report(count: int, label: str):
        for name in label.split(", "):
            written[name] = written.get(name, 0) + count
            print(f"{written[name]}\t{name}", flush=True)

    results = [name for name in files if name in RESULT_FILES]
    maps = [name for name in files if name in MAP_FILES]
    unknown = [name for name in files if name not in RESULT_FILES + MAP_FILES]
    if unknown:
        raise SystemExit(f"not a file of a child: {', '.join(unknown)}")
    if results:
        rn.save_results(run_path, lines, groups, meta, report, files=tuple(results))
    if maps:
        if heads is None:
            raise SystemExit("the map's scripts need their heads (mapping.map_heads)")
        mp.write_map_scripts(lines, run_path, heads, report, files=tuple(maps))


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()  # redirected output in UTF-8, not the Windows code page (no "²" there)
    main(sys.argv[1:])
