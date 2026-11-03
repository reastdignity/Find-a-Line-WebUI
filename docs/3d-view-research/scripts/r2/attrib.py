import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.load(open(sys.argv[1], encoding="utf-8-sig"))
pts = {"PL_ZabiKon": (50.1559508, 19.7562722), "PL_Tatras": (49.232, 20.088), "CH_Lauterbrunnen": (46.596, 7.907),
       "SK_Sulov": (49.17, 18.575), "ES_Montserrat": (41.593, 1.81), "MT_Dingli": (35.8565, 14.383),
       "AT_Dachstein": (47.47, 13.6), "US_Moab": (38.561, -109.568), "IT_Sella": (46.5208, 11.7325)}
for name, (lat, lon) in pts.items():
    hits = []
    for c in d["contributors"]:
        for a in c["coverageAreas"]:
            s, w, n, e = a["bbox"]
            if s <= lat <= n and w <= lon <= e:
                hits.append((a["zoomMax"], a["zoomMin"], a["score"], c["attribution"]))
    hits.sort(reverse=True)
    print(name, "max zoom", max(h[0] for h in hits) if hits else None)
    for h in hits[:8]:
        print("   zoom %d-%d score %d %s" % (h[1], h[0], h[2], h[3]))
