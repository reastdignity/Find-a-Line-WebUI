"""docs/country-precompute/samples.sh: the commands that measured every sample of samples.json (its
recorded options), to run them again on another machine or after a change of the search.
Usage: python samples_sh.py <samples.json> <out.sh>"""
import json
import shlex
import sys

samples = json.load(open(sys.argv[1], encoding="utf-8"))
order = {"S": 0, "M": 1, "L": 2}


def key(name):
    parts = name.split("-")
    variant = parts[-1] if parts[-1] in ("45", "50", "nodsm", "axiom", "tiger", "floors") else ""
    band = next((p for p in parts if p in order), "Z")
    return (variant != "", order.get(band, 9), name)


lines = ['#!/usr/bin/env bash',
         '# The samples of docs/country-precompute.md (2026-11-02): one search each, measured by',
         '# tools/perf_country.py profile into $OUT/samples.json, one at a time under the exclusive test lock',
         '# (their times are measured). A sample already in samples.json is skipped, so the script can be',
         '# started again. The options are the recorded ones; an --area file must exist at its path',
         '# (the Lauterbrunnen polygon: docs/country-precompute/lauterbrunnen.geojson).',
         '# Usage: OUT=<scratch>/samples DATA=<scratch>/data bash docs/country-precompute/samples.sh',
         'set -u',
         'MAIN="${MAIN:-$(git rev-parse --show-toplevel)}"',
         'PY="${PY:-python}"',
         'OUT="${OUT:?the folder of samples.json}"',
         'DATA="${DATA:?a data folder (its cache may be a link to the real one)}"',
         'mkdir -p "$OUT/logs"',
         'done_already() { "$PY" -c "import json,os,sys; p=sys.argv[1]; d=json.load(open(p)) if os.path.exists(p) else {}; '
         'sys.exit(0 if sys.argv[2] in d else 1)" "$OUT/samples.json" "$1"; }',
         '# prof NAME TENSION(-|m:kN,...) [findaline options...]',
         'prof() {',
         '  local name=$1 tension=$2; shift 2',
         '  if done_already "$name"; then echo "--- $name: in samples.json already"; return; fi',
         '  local extra=(); [ "$tension" != "-" ] && extra=(--tension-by-length "$tension")',
         '  echo "=== $name $(date \'+%H:%M:%S\')"',
         '  "$PY" "$MAIN/tools/test_lock.py" run --exclusive --owner cp-sample -- \\',
         '    "$PY" -X utf8 "$MAIN/tools/perf_country.py" profile --lean --out "$OUT" --name "$name" "${extra[@]}" -- \\',
         '    "$@" --no-html --data-dir "$DATA" > "$OUT/logs/$name.log" 2>&1',
         '  tail -n 1 "$OUT/logs/$name.log"',
         '}',
         '']
for name in sorted(samples, key=key):
    s = samples[name]
    args = [a for a in s["args"]]
    # drop the data folder (the script's own) and --no-html (added by prof)
    clean, skip = [], False
    for k, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == "--data-dir":
            skip = True
            continue
        if a == "--no-html":
            continue
        if a == "--area" and k + 1 < len(args) and args[k + 1].endswith("ch-lauterbrunnen.geojson"):
            clean += ["--area", "$MAIN/docs/country-precompute/lauterbrunnen.geojson"]
            skip = True
            continue
        clean.append(a)
    tension = s.get("tension_by_length") or "-"
    text = " ".join(shlex.quote(a) if not a.startswith("$MAIN") else f'"{a}"' for a in clean)
    note = "  # rebuilt from its output: its run was lost while saving" if s.get("note") and s["summary"]["lines"] else ""
    lines.append(f"prof {name} {tension} {text}{note}")
lines.append('echo "=== done $(date \'+%H:%M:%S\')"')
open(sys.argv[2], "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print(len(samples), "samples")
