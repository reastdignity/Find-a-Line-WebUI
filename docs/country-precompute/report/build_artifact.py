"""docs/country-precompute/report.html: the designed page of docs/country-precompute.md. The overview
(verdict, country cards, the numbers by country, variant and DSM) is drawn by app.js from the estimate;
the sections after it are the report's own text, converted from its Markdown (a small converter for
the subset the report uses: headings, paragraphs, lists, tables, bold, code, links).
Usage: python build_artifact.py <report.md> <estimate.json> <shell.html> <app.js> <out.html> [samples.json]"""
import html
import json
import re
import sys

for stream in (sys.stdout, sys.stderr):  # UTF-8 when redirected (progress.utf8_output, inline)
    stream.reconfigure(encoding="utf-8", errors="replace")

md_path, est_path, shell_path, app_path, out_path = sys.argv[1:6]
md = open(md_path, encoding="utf-8").read()
est = json.load(open(est_path, encoding="utf-8"))
n_samples = len(sys.argv) > 6 and len(json.load(open(sys.argv[6], encoding="utf-8"))) or "Thirty-odd"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


SECTION_IDS = {}


def inline(text):
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)", text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        code, bold, label, href = m.groups()
        if code is not None:
            out.append(f"<code>{html.escape(code, quote=False)}</code>")
        elif bold is not None:
            out.append(f"<strong>{inline(bold)}</strong>")
        elif href.startswith("#"):
            out.append(f'<a href="#{html.escape(SECTION_IDS.get(href[1:], href[1:]))}">{inline(label)}</a>')
        elif href.startswith("http"):
            out.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inline(label)}</a>')
        else:  # a file of the repository: no link from the page
            out.append(f'<span class="path" title="{html.escape(href)} in the repository">{inline(label)}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def table(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    head, body = rows[0], rows[2:]
    numeric = [all(re.fullmatch(r"[-–]|[\d.,  %×µs()/a-zA-Z²-]*\d[\d.,  %×µs()/a-zA-Z²-]*", r[k] or "-") and
                   re.match(r"^[\d–-]", r[k] or "-") for r in body if k < len(r)) for k in range(len(head))]
    out = ['<div class="tablebox"><table><thead><tr>']
    out += [f'<th{" class=\"n\"" if numeric[k] and k else ""}>{inline(h)}</th>' for k, h in enumerate(head)]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f'<td{" class=\"n\"" if numeric[k] and k else ""}>{inline(c)}</td>'
                                    for k, c in enumerate(r)) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def blocks(text):
    """Markdown of a section to HTML."""
    lines = [l for l in text.split("\n")]
    out, k = [], 0
    while k < len(lines):
        line = lines[k]
        if not line.strip() or line.strip().startswith("<!--"):
            k += 1
            continue
        if line.startswith("### "):
            title = line[4:].strip()
            out.append(f'<h3 id="{slug(title)}">{inline(title)}</h3>')
            k += 1
        elif line.startswith("|"):
            j = k
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out.append(table(lines[k:j]))
            k = j
        elif re.match(r"^(- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            items, j = [], k
            while j < len(lines) and (re.match(r"^(- |\d+\. )", lines[j]) or (lines[j].startswith("  ") and lines[j].strip())):
                if re.match(r"^(- |\d+\. )", lines[j]):
                    items.append([re.sub(r"^(- |\d+\. )", "", lines[j])])
                else:
                    items[-1].append(lines[j][2:])
                j += 1
            html_items = []
            for item in items:
                head = []
                sub = []
                for l in item:
                    if re.match(r"^(\d+\. |- )", l) or sub:
                        sub.append(l)
                    else:
                        head.append(l)
                inner = inline(" ".join(s.strip() for s in head))
                if sub:
                    inner += blocks("\n".join(s[1:] if s.startswith(" ") else s for s in sub))
                html_items.append(f"<li>{inner}</li>")
            tag = "ol" if ordered else "ul"
            out.append(f'<{tag} class="tight">{"".join(html_items)}</{tag}>')
            k = j
        else:
            j = k
            while j < len(lines) and lines[j].strip() and not re.match(r"^(\||- |\d+\. |#)", lines[j]):
                j += 1
            out.append(f"<p>{inline(' '.join(l.strip() for l in lines[k:j]))}</p>")
            k = max(j, k + 1)
    return "\n".join(out)


# Sections of the report after the summary
parts = re.split(r"^## ", md, flags=re.M)
sections = {}
for part in parts[1:]:
    title, _, body = part.partition("\n")
    sections[title.strip()] = body
for title in sections:
    SECTION_IDS[slug(title)] = slug(title)
summary = sections.pop("Summary")
summary = re.sub(r"^\|.*\n", "", summary, flags=re.M)  # the table: drawn as cards
summary = re.sub(r"^Computing: 9900X.*\n", "", summary, flags=re.M)

body = []
for title, text in sections.items():
    if title.startswith("4."):
        # 4.3: the per-country tables become the interactive numbers; 4.5: the strata of the chosen country
        text = re.sub(r"(### 4\.3 Per country\n).*?(?=\n- \*\*Poland)",
                      r"\1\nThe numbers of each country, variant and grid strategy are in the overview at the top "
                      r"(choose the country, the variant and the DSM there); the tables of all of them are in the "
                      r"report's Markdown.\n", text, flags=re.S)
        text = re.sub(r"(### 4\.5 The strata of each country\n).*$", r"\1\n<!-- STRATA -->\n", text, flags=re.S)
    num = re.match(r"^(\d+)\.", title)
    content = blocks(text)
    content = content.replace("<p>&lt;!-- STRATA --&gt;</p>", "")
    if title.startswith("4."):
        content += ('\n<p class="note" id="strata-title"></p><p class="note">The country\'s km² per stratum (the share '
                    'of 30 m pixels of 45° or more around each 1 km block; where that is below 0.5 %, the relief), the '
                    'samples\' cells in it and their lines and spots per km², for the country chosen at the top.</p>'
                    '<div id="strata" class="stack"></div>')
    body.append(f'<section id="{slug(title)}"><h2>{inline(title)}</h2>{content}</section>')

data = {"rows": [{k: r[k] for k in ("country", "variant", "strategy", "dsm", "machine", "scenario", "download_tb",
                                    "cache_tb", "download_days", "compute_hours", "lines", "spots")} |
                 {"bands": [p and {k: p[k] for k in ("band", "res", "core_km", "tiles_at_once", "tile_gb", "lines_gb_today")}
                            for p in r["bands"]]} for r in est["rows"]],
        "strata": est["strata"], "models": est["models"],
        "no_dsm": [c for c in ("SK", "PL", "CH", "UT") if all(
            r["download_tb"] == next(o for o in est["rows"] if o["country"] == c and not o["dsm"] and o["variant"] == r["variant"]
                                     and o["strategy"] == r["strategy"] and o["machine"] == r["machine"]
                                     and o["scenario"] == r["scenario"])["download_tb"]
            for r in est["rows"] if r["country"] == c and r["dsm"])]}

summary_html = blocks(summary)
shell = open(shell_path, encoding="utf-8").read()
app = open(app_path, encoding="utf-8").read()
page = f"""{shell}
<div class="page">
<header class="hero">
  <div class="eyebrow">Find-a-Line · feasibility report · 2 November 2026</div>
  <h1>Highline counts for whole countries</h1>
  <p class="lede">Can Poland, Switzerland and Utah be searched offline in fixed tiles, keeping only how many
  lines and spots each square kilometre holds? {n_samples} measured searches, the relief of the three
  countries and both machines' benchmarks say: yes, after four pieces of work, in days of computing and
  up to two weeks of downloading.</p>
  <p class="meta">Branch country-precompute · main 221dd10 · rough figures (about ±50 %; ranges from a bootstrap
  over the sampled places) · the same report as docs/country-precompute.md</p>
</header>
<section id="answer"><h2>The answer</h2>
<div class="cards" id="cards"></div>
{summary_html}
</section>
<div class="controls" role="toolbar" aria-label="What the numbers show">
  <div class="ctl"><span>Country</span><div class="seg" id="ctl-country"></div></div>
  <div class="ctl"><span>Lines</span><div class="seg" id="ctl-variant"></div></div>
  <div class="ctl"><span>Data</span><div class="seg" id="ctl-dsm"></div></div>
</div>
<section id="numbers">
  <h2 id="tiles-title"></h2>
  <div class="tiles" id="tiles"></div>
  <figure class="chart">
    <figcaption><b id="chart-title"></b><span>Dots: the plain estimate; lines: the range of a bootstrap over the
    sampled places; the vertical line: the download. A logarithmic time axis.</span></figcaption>
    <div class="legend"><span><i class="dot m1"></i>Ryzen 9 9900X (12 cores)</span><span><i class="dot m2"></i>Ryzen 5 5650G (6 cores)</span></div>
    <div class="svgbox" id="chart"></div>
  </figure>
  <div class="tablebox"><table>
    <thead><tr><th>Grids</th><th class="n">Download</th><th class="n">Download time</th><th class="n">9900X</th>
    <th class="n">5650G</th><th class="n">Lines</th><th class="n">Spots</th><th>Tiles (9900X)</th></tr></thead>
    <tbody id="strategy-rows"></tbody>
    <caption>Grid strategies: one grid for all bands, or S / M / L on their own grids. "–": a band at a grid not
    measured (M at 1 m, L at 2 m: out of reach today).</caption>
  </table></div>
</section>
{''.join(body)}
<footer class="meta">Find-a-Line · docs/country-precompute.md · tools/perf_country.py · the inputs, relief, estimate
and research notes in docs/country-precompute/</footer>
</div>
<script id="estimate-data" type="application/json">{json.dumps(data, separators=(",", ":"))}</script>
<script>
{app}
</script>
"""
open(out_path, "w", encoding="utf-8", newline="\n").write(page)
print(len(page) // 1024, "KB")
