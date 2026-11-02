"""The Markdown tables of docs/country-precompute.md from estimate.json (tools/perf_country.py estimate).
Usage: python report_tables.py <estimate.json> > tables.md"""
import json
import sys

est = json.load(open(sys.argv[1], encoding="utf-8"))
rows = est["rows"]
NAMES = {"SK": "Slovakia", "PL": "Poland", "CH": "Switzerland", "UT": "Utah"}
MACHINES = ["Ryzen 9 9900X", "Ryzen 5 5650G"]
SHORT = {"Ryzen 9 9900X": "9900X", "Ryzen 5 5650G": "5650G"}
VARIANTS = ["30-2000 m", "30-5000 m", "2000-5000 m"]
STRATEGIES = ["1 m", "2 m", "5 m", "split 1/2/5 m", "split 2/5/10 m"]


def find(**k):
    for r in rows:
        if all(r[a] == b for a, b in k.items()):
            return r
    return None


def dur(hours):
    """Hours as text: minutes below 1 h, hours below 48 h, else days."""
    if hours is None:
        return "-"
    if hours < 1:
        return f"{hours * 60:.0f} min"
    if hours < 48:
        return f"{hours:.1f} h" if hours < 10 else f"{hours:.0f} h"
    return f"{hours / 24:.1f} d" if hours < 240 else f"{hours / 24:.0f} d"


def big(n):
    if n is None:
        return "-"
    for unit, size in (("bn", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            v = n / size
            return f"{v:.1f} {unit}" if v < 10 else f"{v:.0f} {unit}"
    return f"{n:.0f}"


def compute_cell(country, variant, strategy, dsm, machine):
    lo, mid, hi = (find(country=country, variant=variant, strategy=strategy, dsm=dsm, machine=machine, scenario=s)
                   for s in ("low", "mid", "high"))
    if mid is None or mid["compute_hours"] is None:
        return "-"
    a, b, c = lo["compute_hours"], mid["compute_hours"], hi["compute_hours"]
    if abs(c - a) < 0.15 * max(b, 1e-9):
        return dur(b)
    return f"{dur(b)} ({dur(a)}-{dur(c)})"


out = []
NO_DSM = {c for c in NAMES if all(r["download_tb"] == find(country=c, variant=r["variant"], strategy=r["strategy"], dsm=False,
                                                          machine=r["machine"], scenario=r["scenario"])["download_tb"]
                                    for r in rows if r["country"] == c and r["dsm"])}


def days(r):
    """The download time; a local copy (Slovakia's mirror) in minutes."""
    if r["download_days"] < 0.05:
        return f"{max(1, round(r['download_days'] * 1440))} min (a local copy)"
    return f"{r['download_days']:.1f} days"


def dsms(c):
    return (True,) if c in NO_DSM else (True, False)


def dsm_text(c, dsm):
    return "none exists" if c in NO_DSM else "yes" if dsm else "no"


# Summary: the recommended strategy per variant, both machines
out.append("<!-- SUMMARY -->")
out.append("| Country | DSM | Download | Cache | Download time | 30-2000 m (S 1 m, M 2 m) | 30-5000 m (+ L 5 m) | 2000-5000 m (L 5 m) |")
out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
for c in NAMES:
    for dsm in dsms(c):
        r = find(country=c, variant="30-2000 m", strategy="split 1/2/5 m", dsm=dsm, machine=MACHINES[0], scenario="mid")
        cells = []
        for variant in VARIANTS:
            pair = [compute_cell(c, variant, "split 1/2/5 m", dsm, m) for m in MACHINES]
            cells.append("-" if pair[0] == "-" else f"{pair[0]} / {pair[1]}")
        out.append(f"| {NAMES[c]} | {dsm_text(c, dsm)} | {r['download_tb']:.2f} TB | {r['cache_tb']:.2f} TB | "
                   f"{days(r)} | " + " | ".join(cells) + " |")
out.append("")
out.append("Computing: 9900X / 5650G, mid (bootstrap range of the places). \"-\": not measured yet.")
out.append("")
# Data and download per country
out.append("<!-- DATATABLE -->")
out.append("| Country | Grids of | DSM | Download | Cache | Download time |")
out.append("| --- | --- | --- | --- | --- | --- |")
for c in NAMES:
    seen = set()
    for strategy in STRATEGIES:
        for dsm in dsms(c):
            r = find(country=c, variant="30-2000 m", strategy=strategy, dsm=dsm, machine=MACHINES[0], scenario="mid")
            key = (r["download_tb"], r["cache_tb"], dsm)
            if key in seen:
                continue
            seen.add(key)
            finest = "1 m and finer" if strategy in ("1 m", "split 1/2/5 m") else "2 m and coarser"
            out.append(f"| {NAMES[c]} | {finest} | {dsm_text(c, dsm)} | {r['download_tb']:.2f} TB | "
                       f"{r['cache_tb']:.2f} TB | {days(r)} |")
out.append("")
# Compute per country, variant and strategy, both machines, DSM on
for c in NAMES:
    out.append(f"<!-- COMPUTE {c} -->")
    out.append(f"| {NAMES[c]}: variant | Grids | 9900X | 5650G | Lines (mid) | Spots (mid) | Tiles (9900X) |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for variant in VARIANTS:
        for strategy in STRATEGIES:
            mid = find(country=c, variant=variant, strategy=strategy, dsm=True, machine=MACHINES[0], scenario="mid")
            cells = [compute_cell(c, variant, strategy, True, m) for m in MACHINES]
            tiles = ", ".join(f"{p['band']} {p['core_km']} km ×{p['tiles_at_once']}" for p in mid["bands"] if p) \
                if mid["compute_hours"] is not None else "not measured"
            out.append(f"| {variant} | {strategy} | {cells[0]} | {cells[1]} | {big(mid['lines'])} | {big(mid['spots'])} | {tiles} |")
    out.append("")
# Strata, all in one block
out.append("<!-- STRATA -->")
for key, s in est["strata"].items():
    if not s:
        continue
    c, band = key.split()
    out.append(f"| {NAMES[c]}, {band} at {s['res']:g} m: stratum | km² | Sample cells (km²) | Lines per km² | Spots per km² |")
    out.append("| --- | --- | --- | --- | --- |")
    for label, km2, cells, lines, spots in zip(s["strata"], s["km2"], s["cells_km2"], s["lines_per_km2"], s["spots_per_km2"]):
        out.append(f"| {label} | {km2:,.0f} | {cells:.1f} | {'-' if lines is None else f'{lines:,.0f}'} | "
                   f"{'-' if spots is None else f'{spots:,.1f}'} |")
    out.append("")
    out.append(f"Places: {', '.join(s['places'])}. Lines low / mid / high: {big(s['lines']['low'])} / {big(s['lines']['mid'])} / "
               f"{big(s['lines']['high'])}; spots {big(s['spots']['low'])} / {big(s['spots']['mid'])} / {big(s['spots']['high'])}.")
    out.append("")
# Time models
out.append("<!-- MODELS -->")
out.append("| Band, grid | Places | Steps 1-2: s per Mpx | Pair search: CPU s per km² | Over water: per line |")
out.append("| --- | --- | --- | --- | --- |")
for key, m in sorted(est["models"].items(), key=lambda kv: ("SML".index(kv[0][0]), float(kv[0].split()[1]))):
    if m:
        out.append(f"| {key} | {m['places']} | {m['grid_s_per_mpx']:.2f} | {m['cpu_a']:.3g} + {m['cpu_b'] * 1e6:.3g} µs × lines per km² | "
                   f"{m['count_s_per_line'] * 1e6:.2g} µs |")
out.append("")
print("\n".join(out))
