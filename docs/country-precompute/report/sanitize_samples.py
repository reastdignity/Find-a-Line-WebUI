"""samples.json as kept in docs/country-precompute: the measured samples without local paths (the data
folder, the run folders and an --area file become placeholders), for estimate (with relief.json).
Usage: python sanitize_samples.py <samples.json> <out.json>"""
import json
import os
import sys

for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
    stream.reconfigure(encoding="utf-8", errors="replace")

samples = json.load(open(sys.argv[1], encoding="utf-8"))
for s in samples.values():
    s["data_dir"] = "<data>"
    s["run"] = None if s.get("run") is None else f"<data>/runs/{os.path.basename(s['run'])}"
    args = list(s.get("args", []))
    for k, a in enumerate(args[:-1]):
        if a == "--data-dir":
            args[k + 1] = "<data>"
        elif a == "--area":
            args[k + 1] = "docs/country-precompute/" + ("lauterbrunnen.geojson" if args[k + 1].endswith("lauterbrunnen.geojson")
                                                       else os.path.basename(args[k + 1]))
    s["args"] = args
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(samples, f, indent=1, ensure_ascii=False)
print(len(samples), "samples")
