"""The samples of samples.json as a Markdown table for the report (section 7.1) and as JSON rows for
the artifact: place, band, grid, options that differ, area, lines, spots, per km², wall and CPU
seconds, peak memory."""
import json
import sys

samples = json.load(open(sys.argv[1], encoding="utf-8"))
out_json = sys.argv[2] if len(sys.argv) > 2 else None

PLACES = {
    "pl-tatry": "Tatras, Hala Gąsienicowa (49.235, 20.000)", "pl-jura": "Jura, Dolinki Krakowskie (50.190, 19.735)",
    "pl-niz": "Lowland near Gorzów (52.740, 15.355)", "ch-alps": "Lauterbrunnen (46.550, 7.882)",
    "ch-alps-area": "Lauterbrunnen valley (drawn area)", "ch-plateau": "Swiss Plateau (47.200, 7.700)",
    "ut-zion": "Zion Canyon (37.260, -112.950)", "ut-sevier": "Sevier Desert (39.350, -112.550)",
    "ut-wasatch": "Wasatch, Little Cottonwood (40.570, -111.680)", "ut-canyonlands": "Dead Horse Point (38.470, -109.740)",
}
VARIANT = {"45": "45° anchors", "50": "50° anchors", "nodsm": "no DSM", "axiom": "Axiom MK2",
           "tiger": "Tiger", "floors": "prominence ≥ 5 m, height ≥ 20 m"}


def option(args, name):
    for k, a in enumerate(args):
        if a == name and k + 1 < len(args):
            return args[k + 1]
    return None


rows = []
for name, s in samples.items():
    parts = name.split("-")
    variant = None
    if parts[-1] in VARIANT:
        variant, parts = parts[-1], parts[:-1]
    place, band, res = "-".join(parts[:-2]), parts[-2], parts[-1]
    args = s["args"]
    km2 = s["grid"].get("area_km2") or 0
    t = s["total"]
    shape = f"r = {float(option(args, '--radius')) / 1000:g} km" if option(args, "--radius") else "area"
    rows.append({
        "name": name, "place": PLACES.get(place, place), "band": band, "res": res, "variant": VARIANT.get(variant, ""),
        "shape": shape, "km2": round(km2, 1), "lines": s["summary"]["lines"], "spots": s["summary"]["spots"],
        "lines_km2": round(s["summary"]["lines"] / km2) if km2 else None,
        "wall_s": None if t["wall_s"] is None else round(t["wall_s"]),
        "cpu_s": None if t["cpu_s"] is None else round(t["cpu_s"]),
        "peak_gb": None if not t["peak_rss_mb"] else round(t["peak_rss_mb"] / 1024, 1),
        "rebuilt": bool(s.get("note")) and s["summary"]["lines"] > 0})
order = {"S": 0, "M": 1, "L": 2}
rows.sort(key=lambda r: (order.get(r["band"], 9), r["place"], float(r["res"][:-1]), r["variant"]))


def num(v):
    return "" if v is None else f"{v:,}".replace(",", " ")


print("| Sample | Place | Band | Grid | Variant | Area | Lines | Spots | Lines per km² | Wall | CPU | Peak |")
print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for r in rows:
    note = " (from its output)" if r["rebuilt"] else ""
    print(f"| `{r['name']}` | {r['place']} | {r['band']} | {r['res'][:-1]} m | {r['variant']} | {r['km2']} km² ({r['shape']}) | "
          f"{num(r['lines'])} | {num(r['spots'])} | {num(r['lines_km2'])} | {num(r['wall_s'])} s{note} | {num(r['cpu_s'])} s | "
          f"{'' if r['peak_gb'] is None else str(r['peak_gb']) + ' GB'} |")
if out_json:
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
