import re, sys
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t = sys.stdin.read()
before, after, limit = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
for kw in sys.argv[4:]:
    ms = list(re.finditer(kw, t))
    print("##", kw, len(ms))
    for m in ms[:limit]:
        s = max(0, m.start() - before)
        print("   ", t[s:m.end() + after])
        print()
