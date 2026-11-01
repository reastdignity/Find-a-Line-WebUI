"""tools/job_stats.py: the statistics of the computing phases of a jobs.sqlite by class, from the
tables of migration 16 and, for jobs of before, from their events; its embedded defaults and presets
against params, its keys against jobs, and no ids, titles or places in its output."""

import csv
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import jobs as jb  # noqa: E402
import job_stats as js  # noqa: E402
import params as pm  # noqa: E402

# The info lines of a computing phase of two tiles (from a real search, shortened)
OLD_OUTPUT = """Area: coast ±100 m within osm:Gozo, 9.65 km², resolution: 1m (14547 x 8665 px, 6 tiles)
\n--- Tile 1 of 2 (7602 x 7602 px) ---
\nStep 2: Finding significant slopes...
[Compute] finding anchors: 7602/7602 (100%) - done in 0s
Found 200756 potential anchors to evaluate
[Compute] anchor prominence and drop: 2/2 (100%) - done in 1m08s
Anchors left after the prominence and drop limits: 150000
\nStep 3: Evaluating anchor pairs...
[Compute] free directions: 1/1 (100%) - done in 3s
Anchors with an open direction: 75317 of 150000
[Compute] anchor pairs: 50196/50196 (100%), pairs 8,466,854, lines 342592 - done in 1h02m
[Compute] checking lines: 342592/342592 (100%), valid 171872 - done in 1s, 171872 valid
Completed in 4.30 seconds
Candidate pairs between anchors with an open direction: 118952627
Checked pixel by pixel: 8466854
Left out by the line limits (mean ≥ 40): 170718
Found 171872 valid lines
\n--- Tile 2 of 2 (8604 x 7602 px) ---
[Compute] finding anchors: 7602/7602 (100%) - done in 2s
Found 73500 potential anchors to evaluate
[Compute] anchor prominence and drop: 2/2 (100%) - done in 8s
[Compute] free directions: 1/1 (100%) - done in 0s
Anchors with an open direction: 15835 of 73500
[Compute] anchor pairs: 891/891 (100%), pairs 493, lines 21 - done in 0s
[Compute] checking lines: 21/21 (100%), valid 0 - done in 0s, 0 valid
Candidate pairs between anchors with an open direction: 74261
Checked pixel by pixel: 493
Left out by the line limits (mean ≥ 40): 21
Found 0 valid lines"""
SECRET = {"title": "Secret Valley", "place": "Secretplace"}


def test_tables_match_the_app():
    """The defaults, presets and keys the tool carries are those of params and jobs."""
    for name, default in js.DEFAULTS.items():
        assert pm.SearchParams.model_fields[name].default == default, name
    assert js.PRESET_FIELDS == pm.PRESET_FIELDS
    assert js.PRESETS == {k: v for k, v in pm.PRESETS.items() if v is not None}
    assert set(pm.PRESETS) == set(js.PRESETS) | {"custom"}
    assert (js.STEP_KEYS, js.STAGE_KEYS, js.FUNNEL_STEPS) == (jb.STEP_KEYS, jb.STAGE_KEYS, jb.FUNNEL_STEPS)
    for name in pm.PRESETS:
        values = pm.preset_values(name)
        if values is not None:
            assert js.preset_of(values) == name


def test_events_of_a_search_from_before():
    """The funnel and the stages' seconds of the printed lines, each tile added up."""
    funnel, stages, resolution = js.from_events(OLD_OUTPUT.split("\n"))
    assert resolution == 1.0
    assert funnel == {"anchors": 274256, "grids": 2, "anchors_kept": 150000 + 73500, "open": 91152,
                      "todo": 51087, "found": 342613, "candidates": 119026888, "checked": 8467347,
                      "left_out": 170739, "valid": 171872}  # tiled: the lines of the cores unknown
    assert stages == {"finding anchors": 2, "anchor prominence and drop": 76, "free directions": 3,
                      "anchor pairs": 3720, "checking lines": 1}
    one, _, _ = js.from_events(["Found 10 potential anchors", "Anchors with an open direction: 4 of 10",
                                "Found 3 valid lines"])
    assert one["lines"] == 3 and one["anchors_kept"] == 10


def test_classes():
    assert [js.resolution_class(r) for r in (0.5, 1, 1.5, 5, 8, 25, None)] == ["1", "1", "2", "5", "10", "30", "?"]
    assert [js.length_class(v) for v in (60, 150, 400, 1000, 2000)] == ["<=150", "<=150", "<=400", "<=1000", ">1000"]
    assert js.preset_of({}) == "custom" and js.preset_of({"min_length": 100, "max_length": 400}) == "long"
    assert js.preset_of({"min_length": 30, "max_length": 150, "max_anchor_diff_m": 10.0}) == "typical"


def _search(jobs, params, title, geometry=None):
    job = jobs.add({"params": params, "geometry": geometry}, title, None)
    assert jobs.claim("queued", "downloading", "w")["id"] == job
    jobs.set(job, "ready")
    assert jobs.claim("ready", "computing", "w")["id"] == job
    return job


def test_report_of_a_database(tmp_path, capsys):
    """A database with a search of migration 16's tables, one from before (its events only) and an
    OSM extract: the classes, the sums and ratios, read-only, nothing that names a job."""
    jobs = jb.Jobs(str(tmp_path))
    new = _search(jobs, {"min_length": 30, "max_length": 150, "max_anchor_diff_m": 10, "resolution": 2}, SECRET["title"])
    jobs.event(new, "info", f"Run saved: {SECRET['place']}")
    jobs.set_steps(new, {"2": 2.0, "3": 10.0}, {"2": 3.0, "3": 70.0})
    jobs.set_stages(new, {"anchor pairs": (6.0, 50.0), "checking lines": (3.0, 18.0)})
    jobs.set_funnel(new, {"grids": 1, "anchors": 100, "anchors_kept": 80, "open": 40, "todo": 40,
                          "candidates": 1000, "checked": 100, "found": 20, "valid": 10, "lines": 10})
    jobs.set(new, "done")
    square = {"type": "Polygon", "coordinates": [[[19.75, 50.15], [19.76, 50.15], [19.76, 50.16], [19.75, 50.15]]]}
    old = _search(jobs, {"area": "coast", "model": "sag"}, "an old search", geometry=square)
    for line in OLD_OUTPUT.split("\n"):
        jobs.event(old, "info", line)
    jobs.set(old, "done")
    osm = jobs.add({"osm": {"action": "download", "region": "malta"}}, "OSM", None)
    jobs.set(osm, "done")
    path = str(tmp_path / "jobs.sqlite")
    db = js.connect(path, immutable=False)
    rows = {(r["model"], r["shape"]): r for r in js.summarise(js.load(db))}
    db.close()
    assert set(rows) == {("formula", "circle"), ("sag", "area")}
    first, second = rows["formula", "circle"], rows["sag", "area"]
    assert (first["resolution"], first["length"], first["preset"], first["jobs"]) == ("2", "<=150", "typical", 1)
    assert first["step 3 s"] == 10.0 and first["step 3 cpu"] == 70.0 and first["step 1 s"] is None
    assert first["stage anchor pairs cpu"] == 50.0 and first["open/anchors_kept"] == 0.5
    assert first["found/checked"] == 0.2 and first["valid/found"] == 0.5 and first["compute_s"] >= 0
    assert (second["resolution"], second["length"], second["preset"]) == ("1", "<=1000", "custom")
    assert second["stage anchor pairs s"] == 3720 and second["stage anchor pairs cpu"] is None
    assert second["funnel checked"] == 8467347
    checkpoint = sqlite3.connect(path)  # an immutable read skips the WAL, as of a copy of the file
    checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    checkpoint.close()
    out_csv = tmp_path / "stats.csv"
    assert js.main(["--db", path, "--immutable", "--csv", str(out_csv)]) == 0
    with open(out_csv, encoding="utf-8") as f:
        table = list(csv.DictReader(f))
    assert len(table) == 2 and "step 3 cpu" in table[0]
    assert js.main(["--db", path, "--days", "1"]) == 0
    text = open(out_csv, encoding="utf-8").read() + capsys.readouterr().out
    assert "| sag | 1 | <=1000 | area | custom | 1 |" in text
    for secret in (new, old, osm, SECRET["title"], SECRET["place"], "an old search", "Gozo", "19.75"):
        assert secret not in text, secret


def test_output_names_no_job(tmp_path, capsys):
    jobs = jb.Jobs(str(tmp_path))
    job = _search(jobs, {}, SECRET["title"])
    jobs.event(job, "info", "Found 5 potential anchors to evaluate")
    jobs.set(job, "done")
    js.main(["--db", str(tmp_path / "jobs.sqlite")])
    out = capsys.readouterr().out
    assert "## Searches by class" in out and "| formula |" in out
    assert job not in out and SECRET["title"] not in out
    empty = tmp_path / "empty"
    empty.mkdir()
    jb.Jobs(str(empty))
    js.main(["--db", str(empty / "jobs.sqlite"), "--immutable"])
    assert capsys.readouterr().out == "No finished searches.\n"
