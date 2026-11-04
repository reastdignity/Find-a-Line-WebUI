import json, sys, re, html

for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
    stream.reconfigure(encoding="utf-8", errors="replace")
for p in sys.argv[1:]:
    d = json.load(open(p, encoding="utf-8"))
    print("=====", p.rsplit("/",1)[-1])
    for k in ("title","type","url","access","accessInformation","licenseInfo","snippet","description","typeKeywords","modified","culture","properties"):
        v = d.get(k)
        if isinstance(v, str):
            v = html.unescape(re.sub(r"<[^>]+>", " ", v))
            v = re.sub(r"\s+", " ", v)
        print(f"--{k}: {v}")
