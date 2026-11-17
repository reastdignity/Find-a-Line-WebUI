"""
Find-a-Line - Highline Location Finder
========================================

This application finds locations with significant highline potential by analyzing
elevation data: terrain (NMT/DTM) and surface (NMPT/DSM) models from national
LiDAR services (geoportal.gov.pl, Malta), Europe-wide models (FABDEM, Copernicus),
NASADEM or local files. See sources/.

This file is the command line: the options come from params.py, the search itself
is search.py.

Example:
    python findaline.py --lat 50.1559508 --lon 19.7562722

Run `python findaline.py --help` for all options. The cache commands
(`python findaline.py cache status|update|migrate`, `osm download|update`) and the source probe
(`python findaline.py sources check`) are update.py,
the web application (`python findaline.py web`) is web.py, its worker as a process of
its own (`python findaline.py worker`, with `web --no-worker`) jobs.py, the country layer
(`python findaline.py country run|status|build|compare <id>`) country.py. `python findaline.py
export RUN --format csv|geojson` (export_main) writes a run's lines as text from its store, `python
findaline.py view [RUN]` (view_main) opens a run in the local app, and `python findaline.py runs
remove-old --dry-run|--yes` (runs_main) lists or deletes the runs saved before the store of today
(docs/line-volume/spec-store.md 1.2 and section 2). A search ends with the `view` command of its run.
"""

import gc
import json
import os
import sys
from typing import Dict, List, Optional
from urllib.parse import quote

import cache
import mapping as mp
import params as pm
import runs as rn
import search
from progress import progress, utf8_output

DESCRIPTION = ("Find highline spots using elevation data (geoportal.gov.pl, Malta, FABDEM/"
               "Copernicus, NASADEM or your own files).")


def print_event(kind: str, text: str):
    if kind == "warning":
        print("\n" + "!" * 60 + "\nWARNING: " + text + "\n" + "!" * 60 + "\n")
    else:
        print(text)


def ask(question):
    """Ask a yes/no question; anything but yes (or no terminal) means no."""
    try:
        answer = progress.ask(question)
    except EOFError:
        answer = ""
    return answer.strip().lower() in ("y", "yes", "t", "tak")


def confirmer(assume_yes: bool):
    """search.Confirm for the terminal."""
    def confirm(kind: str, text: str) -> bool:
        if kind == "expensive":
            print("\nThis run looks expensive:")
            for reason in text.splitlines():
                print(f"  - {reason}")
            print("Consider a smaller --radius or area, or a coarser --resolution.")
            if assume_yes:
                return True
            if not ask("Continue? [y/N] "):
                sys.exit("Stopped. Use --yes to skip this question.")
            return True
        return assume_yes or ask(text)
    return confirm


def print_lines(lines: search.Lines, group_distance: float, group_by: str, all_lines: bool) -> List[Dict]:
    """Print the spots (or every line); returns the lines shown, as dicts (helpers.LineTable.row)."""
    results = lines.results
    # With the square rule (--same-line-square) the lines are the kept ones, each standing for the lines found
    # between its two anchor squares
    found = (f"Kept {len(results)} of {int(results.columns[rn.STANDS_FOR].sum())} valid lines (one per pair of "
             f"anchor squares)" if rn.STANDS_FOR in results.columns else f"Found {len(results)} valid lines")
    if all_lines:
        groups = mp.Groups.each_alone(len(results))
        print(f"\n{found}")
    else:
        groups = lines.spot_groups
        shown = {"clearance": "largest clearance", "longest": "longest", "height": "highest"}[group_by]
        print(f"\n{found} in {len(groups)} spots "
              f"(lines with both anchors within {group_distance:g}m are grouped, "
              f"showing the one with the {shown}; use --all-lines to list every line)")
    print("GPS Coordinates (lat, lon):")
    rows = []
    for n, (rep, members) in enumerate(zip(groups.rep.tolist(), map(groups.of, range(len(groups)))), 1):
        r = results.row(rep)
        rows.append(r)
        flag = "  [over trees/buildings]" if r["over_obstacles"] else ""
        label = "Line" if all_lines else "Spot"
        if r["water_m"]:
            flag += f"  [{r['water_m']:.0f}m over water]"
        if r["filled_m"]:
            flag += f"  [{r['filled_m']:.0f}m over filled gaps]"
        print(f"  {label} {n}: {r['length']:.0f}m, min. clearance {r['clearance']:.1f}m{flag}")
        if len(members) > 1:
            lengths = results.columns["length"][members].tolist()
            print(f"    {len(members)} similar lines, {min(lengths):.0f}-{max(lengths):.0f}m")
        print(f"    Anchor 1: {r['anchor1'][0]:.6f}, {r['anchor1'][1]:.6f}")
        print(f"    Anchor 2: {r['anchor2'][0]:.6f}, {r['anchor2'][1]:.6f}")
    return rows


def main(params: pm.SearchParams, options: pm.CliOptions, paths: search.Paths):
    """One search; a search.SearchError ends it with its message."""
    confirm = confirmer(options.yes)
    try:
        plan = search.plan_search(params, paths, print_event)
        estimate = search.estimate_search(plan)
        if estimate.reasons:
            confirm("expensive", "\n".join(estimate.reasons))
        lines, run = search.search_lines(plan)
        shown = print_lines(lines, plan.group_distance, params.group_by, options.all_lines)
        result = search.save_run(plan, lines, run)
        search.download_orthophoto(plan, search.orthophoto_lines(plan, lines), confirm)
    except search.SearchError as e:
        sys.exit(str(e))

    # A run opens through the app (docs/line-volume/spec-store.md 1.2: no page of the latest run, no index.html
    # since store wave 4); --html is accepted for one release (store U10) and only says so
    # (a data folder given by --data-dir is named too: `view` would look in the default one)
    view = f"findaline.py view {result.meta['id']}" + (f' --data-dir "{paths.data}"' if options.data_dir else "")
    if options.html:  # the command once, on the line below
        print("--html is no longer used: maps open through the app.")
    print(f"View it: {view}")
    if not options.no_plot:
        mp.mapify(shown, plan.area)

    print("\n" + "=" * 60)
    print("Analysis complete!")
    print("=" * 60)


EXPORT_FORMATS = {"csv": "csv", "geojson": "geojson"}  # --format: the file's extension (linestore.EXPORTS)


def export_main(argv: List[str]) -> int:
    """`findaline.py export RUN --format csv|geojson [--out PATH]`: a run's lines.csv or lines.geojson
    made from its store (linestore.export: the bytes the search's own text file holds), written where
    --out says (default <run id>.<format> in the current folder), never into the run folder: no run
    keeps an export (docs/line-volume/spec-store.md 1.2, store U4). RUN is a run folder or a run id of
    the data folder. A run without a store, an output in the run folder, a folder as --out or a folder
    that does not exist end with a message and exit status 1, before any work; an existing file is
    overwritten."""
    import argparse

    import linestore
    parser = argparse.ArgumentParser(prog="findaline.py export",
                                     description="Write a run's lines as CSV or GeoJSON, made from its store.")
    parser.add_argument("run", metavar="RUN", help="a run folder, or the id of a run in the data folder")
    parser.add_argument("--format", required=True, choices=sorted(EXPORT_FORMATS), help="the file's format")
    parser.add_argument("--out", help="the file to write, never in the run folder; an existing file is overwritten "
                                      "(default: <run id>.csv or <run id>.geojson in the current folder)")
    parser.add_argument("--data-dir", help="the data folder of a run id (default: FINDALINE_DATA, else the folder "
                                           "of the script)")
    args = parser.parse_args(argv)
    folder = args.run
    if not os.path.isfile(os.path.join(folder, "run.json")):
        folder = os.path.join(cache.data_dir(args.data_dir), "runs", args.run)
        if os.path.basename(args.run) != args.run or not os.path.isfile(os.path.join(folder, "run.json")):
            sys.exit(f"No run {args.run}: give a run folder or the id of a run in {os.path.dirname(folder)}")
    run_id = os.path.basename(os.path.normpath(os.path.abspath(folder)))
    if not os.path.isfile(os.path.join(folder, linestore.LINES_FILE)):
        sys.exit(f"The run {run_id} has no store ({linestore.LINES_FILE}): it was saved before exports were made "
                 f"from it; its own {linestore.EXPORTS[args.format]} is in its folder")
    out = args.out or f"{run_id}.{EXPORT_FORMATS[args.format]}"
    target = os.path.dirname(os.path.abspath(out))
    if os.path.isdir(out):
        sys.exit(f"--out names a folder ({os.path.abspath(out)}): give the file to write")
    if not os.path.isdir(target):
        sys.exit(f"No folder {target} to write {os.path.basename(out)} into")
    run_folder = os.path.realpath(folder)
    try:
        inside = os.path.commonpath([os.path.realpath(target), run_folder]) == run_folder
    except ValueError:  # another drive (Windows)
        inside = False
    if inside:
        sys.exit(f"{os.path.abspath(out)} is in the run folder, which keeps no export: give another --out "
                 f"(or run the command from another folder)")
    with progress.bars():  # the grouping's progress
        linestore.export(folder, args.format, out)
    print(f"Saved {os.path.abspath(out)}")
    return 0


def _run_folder(run: str, data_dir: str) -> str:
    """The folder of a run of `findaline.py view`: a run folder (its data folder must hold it in runs/), a run id
    of the data folder, or "" for the newest run there; ends with a message when there is none."""
    runs_dir = os.path.join(data_dir, "runs")
    if not run:
        listed = rn.list_runs(runs_dir)
        if not listed:
            sys.exit(f"No run in {runs_dir}")
        return os.path.join(runs_dir, listed[0]["id"])
    if os.path.isfile(os.path.join(run, "run.json")):
        folder = os.path.abspath(run)
        if os.path.basename(os.path.dirname(folder)) != "runs":
            sys.exit(f"view opens the runs of a data folder (<data>/runs/<id>); {folder} is not in one")
        return folder
    folder = os.path.join(runs_dir, run)
    if os.path.basename(run) != run or not os.path.isfile(os.path.join(folder, "run.json")):
        sys.exit(f"No run {run}: give a run folder or the id of a run in {runs_dir}")
    return folder


def app_holds(port: int, folder: str) -> Optional[bool]:
    """Whether the app on `port` of this computer holds the run `folder`: None when nothing listens there, True
    when the app's runs folder serves this run's run.json (the local app serves its runs folder as files: the same
    id and time say the same data folder), False for any other answer (another data folder, the public site,
    another program)."""
    import socket

    import requests
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(2)
        if probe.connect_ex(("127.0.0.1", port)) != 0:
            return None
    with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
        mine = json.load(f)
    session = requests.Session()
    session.trust_env = False  # no proxy for this computer's own port
    try:
        answer = session.get(f"http://127.0.0.1:{port}/runs/{quote(mine['id'])}/run.json", timeout=2)
        theirs = answer.json() if answer.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        return False
    return isinstance(theirs, dict) and theirs.get("id") == mine["id"] and theirs.get("created") == mine["created"]


def view_main(argv: List[str]) -> int:
    """`findaline.py view [RUN] [--port N] [--data-dir DIR] [--no-browser]`: open a run in the app
    (docs/line-volume/spec-store.md 1.2): the app on the port when it holds the run, else the app started here as
    `findaline.py web` runs it (it keeps running; Ctrl+C stops it), the browser at /#run=<id>. An app on the port
    that does not hold the run (another data folder, another program) ends with a message: never a second app."""
    import argparse
    import webbrowser

    import web
    parser = argparse.ArgumentParser(prog="findaline.py view", description="Open a run in Find-a-Line.")
    parser.add_argument("run", metavar="RUN", nargs="?", default="",
                        help="a run folder, or the id of a run in the data folder (default: the newest run)")
    parser.add_argument("--port", type=int, default=web.PORT, help=f"the app's port (default {web.PORT})")
    parser.add_argument("--data-dir", help="the data folder (default: FINDALINE_DATA, else the folder of the script)")
    parser.add_argument("--no-browser", action="store_true", help="print the address, do not open the browser")
    args = parser.parse_args(argv)
    data = cache.data_dir(args.data_dir)
    folder = _run_folder(args.run, data)
    data = os.path.dirname(os.path.dirname(folder))
    run_id = os.path.basename(folder)
    path = f"/#run={quote(run_id)}"
    held = app_holds(args.port, folder)
    if held is False:
        sys.exit(f"Port {args.port} answers, but not with this run: another Find-a-Line (another data folder) or "
                 f"another program. Stop it, or use --port.")
    if held is None:  # nothing there: the app, here, as findaline.py web runs it
        return web.main(["--port", str(args.port), "--data-dir", data] + (["--no-browser"] if args.no_browser else []),
                        open_path=path)
    url = f"http://127.0.0.1:{args.port}{path}"
    print(f"The run in Find-a-Line: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    return 0


def _size(n: int) -> str:
    """A size on disk in plain words: 45 MB, 1.2 GB."""
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def _number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _print_runs(old: List[Dict], facts: Optional[Dict], with_db: bool):
    """The table of old runs of `runs remove-old` and its total (the dry run's list, --yes's list of what went): id,
    created, lines, size; with a jobs.sqlite whose facts were read the owner's user id (never a name or an e-mail),
    shared, demo, favourite lines, and in the total the searches that leave the list on Home."""
    columns = with_db and facts is not None
    width = max(len(r["id"]) + (19 if r["unreadable"] else 0) for r in old)
    head = f"{'Run id':<{width}}  {'Created':<16}  {'Lines':>11}  {'Size':>8}"
    if columns:
        head += f"  {'Owner':>6}  Shared  Demo  Favourites"
    print(head)
    for r in old:
        name = r["id"] + (" (store unreadable)" if r["unreadable"] else "")
        row = f"{name:<{width}}  {rn._local_time(r['created']):<16}  {_number(r['lines']):>11}  {_size(r['bytes']):>8}"
        if columns:
            f = facts.get(r["id"], {})
            owner = "–" if f.get("user_id") is None else str(f["user_id"])
            row += (f"  {owner:>6}  {'yes' if f.get('shared') else 'no':<6}  {'yes' if f.get('demo') else 'no':<4}"
                    f"  {f.get('favourites', 0):>10}")
        print(row)
    total = (f"Total: {len(old)} run{'s' if len(old) != 1 else ''}, "
             f"{_number(sum(r['lines'] for r in old))} lines, {_size(sum(r['bytes'] for r in old))}")
    if columns:
        favourites = sum(facts.get(r["id"], {}).get("favourites", 0) for r in old)
        searches = sum(facts.get(r["id"], {}).get("searches", 0) for r in old)
        total += (f", {favourites} favourite line{'s' if favourites != 1 else ''}, {searches} "
                  f"{'search leaves' if searches == 1 else 'searches leave'} the list on Home")
    print(total + ".")


def _skipped_and_kept(skipped: List, current: List) -> str:
    """'Skipped: 3 (2 being saved: no run.json; 1 cannot read now).  Kept: 5 runs with the current store.' (the
    accepted draft's words; the reasons counted, the count left out when there is one reason)."""
    kept = f"Kept: {len(current)} run{'s' if len(current) != 1 else ''} with the current store."
    if not skipped:
        return kept
    reasons: Dict[str, int] = {}
    for _, reason in skipped:
        reasons[reason] = reasons.get(reason, 0) + 1
    said = (next(iter(reasons)) if len(reasons) == 1
            else "; ".join(f"{count} {reason}" for reason, count in reasons.items()))
    return f"Skipped: {len(skipped)} ({said}).  {kept}"


FACTS_NOTE = ("The database's facts (owner, shared, demo, favourites) could not be read: the runs are listed "
              "without them.")


def runs_main(argv: List[str]) -> int:
    """`findaline.py runs remove-old (--dry-run | --yes) [--data-dir DIR]` (docs/line-volume/spec-store.md section 2):
    the old runs of the data folder (runs.old_runs: no store of today) listed (--dry-run: nothing written in the data
    folder, the database's facts read from a copy, jobs.run_facts) or deleted (--yes), with the leftovers
    runs/index.html and findaline_map.html (they list or open old runs only) and the folders a removal left behind
    (runs/_removing-<id>). --yes takes each run in turn: under cache.runs_lock its state checked again
    (runs.run_state: a run that is not old any more is kept), its folder renamed (runs.park_run) and its rows deleted
    (Jobs.forget_run, with a jobs.sqlite; if that fails the folder is renamed back); then, outside the lock, the
    renamed folder deleted. A failure of one run is reported and the others go on; the leftovers and the rewrite of
    runs.js (where one exists: never on the public site) come last whatever happened; exit status 1 if anything was
    not done. It prints the table of what it deleted. The listing names runs by id and owners by user id only (never
    a name or an e-mail). Old runs are removed, never converted, and only on the user's word after the list
    (store U5)."""
    import argparse

    import jobs as jb
    parser = argparse.ArgumentParser(prog="findaline.py runs", description="Commands on the saved runs.")
    verbs = parser.add_subparsers(dest="verb", required=True)
    remove = verbs.add_parser("remove-old", description="List (--dry-run) or delete (--yes) the runs saved before the "
                                                        "current store: they no longer open.")
    how = remove.add_mutually_exclusive_group(required=True)
    how.add_argument("--dry-run", action="store_true", help="list the old runs, delete nothing")
    how.add_argument("--yes", action="store_true", help="delete the old runs listed by --dry-run")
    remove.add_argument("--data-dir", help="the data folder (default: FINDALINE_DATA, else the folder of the script)")
    args = parser.parse_args(argv)
    data = cache.data_dir(args.data_dir)
    runs_dir = os.path.join(data, "runs")
    database = os.path.join(data, "jobs.sqlite")
    if not os.path.isdir(runs_dir):  # nothing to list; no runs folder made by the lock
        print(f"Old runs in {runs_dir}: 0")
        return 0
    with cache.runs_lock(runs_dir):
        found = rn.old_runs(runs_dir)
    with_db = os.path.isfile(database)
    facts = jb.run_facts(database) if with_db else {}
    old = found["old"]
    leftovers = [(name, path) for name, path in (("runs/index.html", os.path.join(runs_dir, "index.html")),
                                                 ("findaline_map.html", os.path.join(data, "findaline_map.html")))
                 if os.path.isfile(path)]
    unfinished = [(f"runs/{name}", os.path.join(runs_dir, name)) for name in found["removing"]]
    if args.dry_run:
        print(f"Old runs in {runs_dir}: {len(old)}"
              + (" (saved before the current store; they will no longer open)" if old else ""))
        if old:
            _print_runs(old, facts, with_db)
        if leftovers:
            print(f"Also deleted: {', '.join(name for name, _ in leftovers)} (they list or open old runs only).")
        if unfinished:
            print(f"Also deleted: {', '.join(name for name, _ in unfinished)} (left by a removal that did not "
                  f"finish).")
        print(_skipped_and_kept(found["skipped"], found["current"]))
        if old and with_db and facts is None:
            print(FACTS_NOTE)
        if old and with_db:
            print('Favourite lines in these runs are deleted with them. To keep them, export them first: Favourites '
                  'in the app, "Export for the trip" (CSV or GeoJSON).')
        if old or leftovers or unfinished:
            print("Nothing was deleted (--dry-run). To delete these runs: findaline.py runs remove-old --yes"
                  + (f' --data-dir "{data}"' if args.data_dir else ""))
        return 0
    deleted, failed, left, kept_now = [], [], [], []
    try:
        jobs = jb.Jobs(data) if with_db else None
        for r in old:
            parked = None
            try:
                with cache.runs_lock(runs_dir):
                    state, _ = rn.run_state(os.path.join(runs_dir, r["id"]))
                    if state not in ("old", "unreadable"):  # changed since the scan: not deleted
                        kept_now.append((r["id"], state))
                        continue
                    parked = rn.park_run(runs_dir, r["id"])
                    if jobs is not None:
                        try:
                            jobs.forget_run(r["id"])
                        except BaseException:  # the run back as it was: never a row of a missing run
                            if parked:
                                os.rename(parked, os.path.join(runs_dir, r["id"]))
                            raise
                deleted.append(r)
            except Exception as error:  # noqa: BLE001 - reported, the other runs go on
                failed.append(f"{r['id']}: {type(error).__name__}: {error}")
                continue
            try:
                rn.finish_removal(parked)
            except OSError as error:
                left.append(f"runs/{rn.REMOVING}{r['id']}: {error}")
    except Exception as error:  # noqa: BLE001 - e.g. the database could not be opened: nothing more deleted
        failed.append(f"{type(error).__name__}: {error}")
    finally:
        for name, path in unfinished:
            try:
                rn.finish_removal(path)
            except OSError as error:
                left.append(f"{name}: {error}")
        for name, path in leftovers:
            try:
                os.remove(path)
            except OSError as error:
                failed.append(f"{name}: {error}")
        if os.path.isfile(os.path.join(runs_dir, "runs.js")):
            try:
                rn.write_index(runs_dir)
            except Exception as error:  # noqa: BLE001
                failed.append(f"runs/runs.js: {type(error).__name__}: {error}")
    print(f"Deleted from {runs_dir}: {len(deleted)} run{'s' if len(deleted) != 1 else ''}"
          + (" (saved before the current store)" if deleted else ""))
    if deleted:
        _print_runs(deleted, facts, with_db)
    done = [name for name, path in leftovers + unfinished if not os.path.lexists(path)]
    if done:
        print(f"Also deleted: {', '.join(done)}.")
    if kept_now:
        print(f"Kept, changed since the list: {len(kept_now)} ("
              + "; ".join(f"{run_id}: {state}" for run_id, state in kept_now) + ").")
    if failed:
        print(f"Not deleted: {len(failed)}")
        for text in failed:
            print(f"  {text}")
    if left:
        print(f"Left on disk (a file held open): {len(left)}. Run the command again to delete them.")
        for text in left:
            print(f"  {text}")
    print(_skipped_and_kept(found["skipped"], found["current"]))
    if deleted and with_db and facts is None:
        print(FACTS_NOTE)
    return 1 if failed or left else 0


if __name__ == "__main__":
    utf8_output()  # output redirected to a file gets the Windows code page, which has no "²" and the like
    if len(sys.argv) > 1 and sys.argv[1] in ("cache", "osm", "sources"):
        import update
        sys.exit(update.main(sys.argv[1:]))
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        import web
        sys.exit(web.main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        import jobs
        sys.exit(jobs.main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "country":
        import country
        sys.exit(country.main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        sys.exit(export_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "view":
        sys.exit(view_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "runs":
        sys.exit(runs_main(sys.argv[2:]))
    searches, options = pm.parse_cli(description=DESCRIPTION)
    data_dir = cache.data_dir(options.data_dir)
    stopped = []
    for n, params in enumerate(searches, 1):
        if len(searches) > 1:
            print(f"\n{'#' * 60}\nPoint {n} of {len(searches)}: {params.lat}, {params.lon}"
                  + (f" ({params.name})" if params.name else "") + f"\n{'#' * 60}")
        paths = search.Paths(data_dir, cache.new_work(data_dir))
        failed = True
        try:
            with progress.bars():
                main(params, options, paths)
            failed = False
        except SystemExit as e:  # a stop with a message (no lines found, bad input...) is not a failure
            failed = e.code not in (None, 0) and not isinstance(e.code, str)
            if failed or len(searches) == 1:
                raise
            print(e.code)
            stopped.append(n)
        finally:
            if failed:
                print(f"The working grids are kept in {paths.work} (delete the folder when done)")
            else:
                gc.collect()  # close the memory-mapped grids before deleting them (Windows)
                cache.remove_work(paths.work)
    if stopped:
        sys.exit(f"Stopped without a run: point{'s' if len(stopped) > 1 else ''} "
                 f"{', '.join(map(str, stopped))} of {len(searches)}")
