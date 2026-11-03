(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("estimate-data").textContent);
  const NAMES = { SK: "Slovakia", PL: "Poland", CH: "Switzerland", UT: "Utah" };
  const MACHINES = ["Ryzen 9 9900X", "Ryzen 5 5650G"];
  const SHORT = { "Ryzen 9 9900X": "9900X", "Ryzen 5 5650G": "5650G" };
  const STRATEGIES = ["1 m", "2 m", "5 m", "split 1/2/5 m", "split 2/5/10 m"];
  const VARIANTS = ["30-2000 m", "30-5000 m", "2000-5000 m"];
  const NO_DSM = new Set(DATA.no_dsm);
  const state = { country: "SK", variant: "30-2000 m", dsm: true };
  try {
    const saved = JSON.parse(localStorage.getItem("cp-state") || "null");
    if (saved && NAMES[saved.country] && VARIANTS.includes(saved.variant)) Object.assign(state, saved);
  } catch (e) { /* storage unavailable: defaults */ }

  const index = new Map();
  for (const r of DATA.rows) index.set([r.country, r.variant, r.strategy, r.dsm, r.machine, r.scenario].join("|"), r);
  const row = (c, v, s, d, m, sc) => index.get([c, v, s, d, m, sc].join("|"));

  function dur(h) {
    if (h == null) return "–";
    if (h < 1) return `${Math.round(h * 60)} min`;
    if (h < 48) return h < 10 ? `${h.toFixed(1)} h` : `${Math.round(h)} h`;
    const d = h / 24;
    return d < 10 ? `${d.toFixed(1)} days` : `${Math.round(d)} days`;
  }
  function big(n) {
    if (n == null) return "–";
    const units = [["bn", 1e9], ["M", 1e6], ["k", 1e3]];
    for (const [u, s] of units) if (n >= s) { const v = n / s; return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${u}`; }
    return String(Math.round(n));
  }
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };

  // ---- controls
  function seg(id, options, current, onPick) {
    const box = document.getElementById(id);
    box.replaceChildren();
    for (const [value, label, disabled] of options) {
      const b = el("button", { type: "button", "aria-pressed": String(value === current), text: label });
      if (disabled) { b.disabled = true; b.title = "Utah has no surface model"; }
      b.addEventListener("click", () => onPick(value));
      box.append(b);
    }
  }
  function renderControls() {
    seg("ctl-country", Object.entries(NAMES).map(([k, v]) => [k, v]), state.country, v => set({ country: v }));
    seg("ctl-variant", VARIANTS.map(v => [v, v.replace("-", "–")]), state.variant, v => set({ variant: v }));
    const noDsm = NO_DSM.has(state.country);
    seg("ctl-dsm", [[true, "with DSM", noDsm], [false, "terrain only", false]], noDsm ? false : state.dsm,
        v => set({ dsm: v }));
  }
  function set(patch) {
    Object.assign(state, patch);
    try { localStorage.setItem("cp-state", JSON.stringify(state)); } catch (e) { /* ignore */ }
    render();
  }
  const dsmOf = () => NO_DSM.has(state.country) ? true : state.dsm;

  // ---- tiles
  function renderTiles() {
    const c = state.country, d = dsmOf();
    const rec = row(c, state.variant, "split 1/2/5 m", d, MACHINES[0], "mid");
    const recSlow = row(c, state.variant, "split 1/2/5 m", d, MACHINES[1], "mid");
    const lo = row(c, state.variant, "split 1/2/5 m", d, MACHINES[0], "low");
    const hi = row(c, state.variant, "split 1/2/5 m", d, MACHINES[0], "high");
    const tiles = document.getElementById("tiles");
    tiles.replaceChildren(
      tile("Download", `${rec.download_tb.toFixed(2)} TB`, `${rec.cache_tb.toFixed(2)} TB kept in the cache`),
      tile("Download time", dur(rec.download_days * 24), c === "PL" ? "at the 5.9 MB/s the server gave" :
           c === "CH" ? "36 requests a minute" : c === "SK" ? "a copy of the local mirror" : "8 connections, 138 blocks a minute"),
      tile("Computing, 9900X", dur(rec.compute_hours), rec.compute_hours == null ? "a band not measured yet" :
           (hi.compute_hours - lo.compute_hours > 0.3 * rec.compute_hours ? `range ${dur(lo.compute_hours)} – ${dur(hi.compute_hours)}` : "split 1/2/5 m")),
      tile("Computing, 5650G", dur(recSlow.compute_hours), "the same tiles, 6 cores"),
      tile("Lines / spots", rec.lines == null ? "–" : `${big(rec.lines)} / ${big(rec.spots)}`, "mid estimate, today's spots"),
    );
    document.getElementById("tiles-title").textContent =
      `${NAMES[c]}, ${state.variant.replace("-", "–")}, ${NO_DSM.has(c) ? "no DSM exists" : d ? "with the DSM" : "terrain only"}: S at 1 m, M at 2 m, L at 5 m`;
  }
  function tile(label, value, sub) {
    return el("div", { class: "tile" }, el("div", { class: "label", text: label }), el("div", { class: "value", text: value }),
              el("div", { class: "sub", text: sub }));
  }

  // ---- chart: compute time per strategy, both machines, log axis
  const tip = el("div", { class: "tip", role: "status" }); tip.hidden = true; document.body.append(tip);
  function showTip(evt, lines) {
    tip.replaceChildren(...lines);
    tip.hidden = false;
    const r = (evt.target.getBoundingClientRect && evt.type === "focus") ? evt.target.getBoundingClientRect() : null;
    const x = r ? r.right : evt.clientX, y = r ? r.top : evt.clientY;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.min(window.innerWidth - w - 8, x + 14)}px`;
    tip.style.top = `${Math.max(8, Math.min(window.innerHeight - h - 8, y - h - 10))}px`;
  }
  const hideTip = () => { tip.hidden = true; };

  function renderChart() {
    const box = document.getElementById("chart");
    const c = state.country, d = dsmOf(), v = state.variant;
    const width = Math.max(560, box.clientWidth || 720), rowH = 46, top = 28, left = 132, right = 28;
    const plotW = width - left - right;
    const ticks = [[1 / 6, "10 min"], [1, "1 h"], [6, "6 h"], [24, "1 day"], [168, "1 week"], [720, "1 month"]];
    const minH = 1 / 12, maxH = 1500;
    const x = h => left + (Math.log(Math.max(minH, Math.min(maxH, h))) - Math.log(minH)) / (Math.log(maxH) - Math.log(minH)) * plotW;
    const height = top + STRATEGIES.length * rowH + 34;
    const NS = "http://www.w3.org/2000/svg";
    const s = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, val] of Object.entries(attrs)) e.setAttribute(k, val); return e; };
    const svg = s("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img",
                           "aria-label": `Computing time of ${NAMES[c]} by grid strategy on both machines` });
    for (const [h, label] of ticks) {
      const gx = x(h);
      svg.append(s("line", { x1: gx, x2: gx, y1: top - 6, y2: height - 30, stroke: "var(--grid)", "stroke-width": 1 }));
      const t = s("text", { x: gx, y: height - 12, "text-anchor": "middle", "font-size": 11, fill: "var(--muted)" });
      t.textContent = label; svg.append(t);
    }
    const dl = row(c, v, "split 1/2/5 m", d, MACHINES[0], "mid").download_days * 24;
    const dx = x(dl);
    svg.append(s("line", { x1: dx, x2: dx, y1: top - 14, y2: height - 30, stroke: "var(--fg-2)", "stroke-width": 1 }));
    const dt = s("text", { x: Math.min(dx + 4, width - 4), y: top - 16, "font-size": 11, fill: "var(--fg-2)",
                           "text-anchor": dx > width - 150 ? "end" : "start" });
    dt.textContent = `download ${dur(dl)}`; svg.append(dt);
    STRATEGIES.forEach((strategy, i) => {
      const y0 = top + i * rowH + rowH / 2;
      const lab = s("text", { x: left - 12, y: y0 + 4, "text-anchor": "end", "font-size": 12, fill: "var(--fg)" });
      lab.textContent = strategy; svg.append(lab);
      MACHINES.forEach((m, k) => {
        const mid = row(c, v, strategy, d, m, "mid"), lo = row(c, v, strategy, d, m, "low"), hi = row(c, v, strategy, d, m, "high");
        const y = y0 + (k ? 7 : -7), color = k ? "var(--m2)" : "var(--m1)";
        if (mid.compute_hours == null) {
          if (k === 0) {
            const t = s("text", { x: left + 4, y: y0 + 4, "font-size": 11.5, fill: "var(--muted)" });
            t.textContent = "not measured: a band at this grid is out of reach today"; svg.append(t);
          }
          return;
        }
        svg.append(s("line", { x1: x(lo.compute_hours), x2: x(hi.compute_hours), y1: y, y2: y, stroke: color, "stroke-width": 2, "stroke-linecap": "round" }));
        svg.append(s("circle", { cx: x(mid.compute_hours), cy: y, r: 5, fill: color, stroke: "var(--surface)", "stroke-width": 2 }));
        const hit = s("rect", { x: Math.min(x(lo.compute_hours), x(mid.compute_hours) - 12) , y: y - 9,
                                width: Math.max(24, x(hi.compute_hours) - x(lo.compute_hours) + 24), height: 18,
                                fill: "transparent", tabindex: 0, role: "img",
                                "aria-label": `${strategy}, ${SHORT[m]}: ${dur(mid.compute_hours)}` });
        const lines = () => {
          const key = el("i");
          key.style.background = color;
          return [
            el("b", { text: dur(mid.compute_hours) }),
            el("div", { class: "row" }, key, document.createTextNode(`${strategy} on the ${SHORT[m]}`)),
            el("div", { class: "k", text: `range of the places ${dur(lo.compute_hours)} – ${dur(hi.compute_hours)}` }),
            el("div", { class: "k", text: `tiles: ${mid.bands.filter(Boolean).map(p => `${p.band} ${p.res} m, ${p.core_km} km ×${p.tiles_at_once}`).join("; ")}` }),
          ];
        };
        hit.addEventListener("pointermove", e => showTip(e, lines()));
        hit.addEventListener("pointerleave", hideTip);
        hit.addEventListener("focus", e => showTip(e, lines()));
        hit.addEventListener("blur", hideTip);
        svg.append(hit);
      });
    });
    box.replaceChildren(svg);
    document.getElementById("chart-title").textContent =
      `${NAMES[c]}: computing time by grid strategy, ${v.replace("-", "–")}`;
  }

  // ---- table under the chart
  function renderTable() {
    const c = state.country, d = dsmOf(), v = state.variant;
    const body = document.getElementById("strategy-rows");
    body.replaceChildren();
    for (const strategy of STRATEGIES) {
      const cells = MACHINES.map(m => {
        const mid = row(c, v, strategy, d, m, "mid"), lo = row(c, v, strategy, d, m, "low"), hi = row(c, v, strategy, d, m, "high");
        if (mid.compute_hours == null) return el("td", { class: "n", text: "–" });
        const td = el("td", { class: "n" }, document.createTextNode(dur(mid.compute_hours)));
        if (hi.compute_hours - lo.compute_hours > 0.15 * mid.compute_hours)
          td.append(el("div", { class: "range", text: `${dur(lo.compute_hours)} – ${dur(hi.compute_hours)}` }));
        return td;
      });
      const mid = row(c, v, strategy, d, MACHINES[0], "mid");
      body.append(el("tr", {}, el("td", { text: strategy }), el("td", { class: "n", text: `${mid.download_tb.toFixed(2)} TB` }),
                     el("td", { class: "n", text: dur(mid.download_days * 24) }), ...cells,
                     el("td", { class: "n", text: big(mid.lines) }), el("td", { class: "n", text: big(mid.spots) }),
                     el("td", { text: mid.compute_hours == null ? "–" :
                                mid.bands.filter(Boolean).map(p => `${p.band} ${p.core_km} km ×${p.tiles_at_once}`).join(", ") })));
    }
  }

  // ---- strata of the selected country
  function renderStrata() {
    const box = document.getElementById("strata");
    box.replaceChildren();
    for (const band of ["S", "M", "L"]) {
      const s = DATA.strata[`${state.country} ${band}`];
      if (!s) continue;
      const table = el("table", {},
        el("caption", { text: `Places: ${s.places.join(", ")}. Lines low / mid / high: ${big(s.lines.low)} / ${big(s.lines.mid)} / ${big(s.lines.high)}.` }),
        el("thead", {}, el("tr", {}, el("th", { text: `${band} at ${s.res} m: stratum` }), el("th", { class: "n", text: "km²" }),
                                     el("th", { class: "n", text: "sample cells km²" }), el("th", { class: "n", text: "lines per km²" }),
                                     el("th", { class: "n", text: "spots per km²" }))));
      const tb = el("tbody");
      s.strata.forEach((label, i) => tb.append(el("tr", {}, el("td", { text: label }),
        el("td", { class: "n", text: Math.round(s.km2[i]).toLocaleString("en-GB") }),
        el("td", { class: "n", text: s.cells_km2[i].toFixed(1) }),
        el("td", { class: "n", text: s.lines_per_km2[i] == null ? "–" : Math.round(s.lines_per_km2[i]).toLocaleString("en-GB") }),
        el("td", { class: "n", text: s.spots_per_km2[i] == null ? "–" : s.spots_per_km2[i].toLocaleString("en-GB", { maximumFractionDigits: 1 }) }))));
      table.append(tb);
      box.append(el("div", { class: "tablebox" }, table));
    }
    document.getElementById("strata-title").textContent = `The strata of ${NAMES[state.country]}`;
  }

  // ---- the country cards of the answer
  const NECK = {
    SK: "The first step: our own tiles are on this PC, so nothing is downloaded; the Tatras decide the computing.",
    PL: "Decides: the download. Nine tenths of Poland are flat, so the grids, not the lines, take the computing time.",
    CH: "Decides: the M band in the Alps, billions of lines at 2 m, and the memory to count them.",
    UT: "Decides: the M band in the canyon country, as dense as the Alps' walls.",
  };
  function renderCards() {
    const box = document.getElementById("cards");
    box.replaceChildren();
    for (const c of Object.keys(NAMES)) {
      const dl = [];
      const withDsm = row(c, "30-2000 m", "split 1/2/5 m", true, MACHINES[0], "mid");
      const terrain = row(c, "30-2000 m", "split 1/2/5 m", false, MACHINES[0], "mid");
      if (NO_DSM.has(c)) dl.push(["Download", `${withDsm.download_tb.toFixed(2)} TB, ${dur(withDsm.download_days * 24)} (no DSM exists)`]);
      else {
        dl.push(["Download", `${withDsm.download_tb.toFixed(2)} TB, ${dur(withDsm.download_days * 24)} with the DSM`]);
        dl.push(["", `${terrain.download_tb.toFixed(2)} TB, ${dur(terrain.download_days * 24)} terrain only`]);
      }
      for (const v of VARIANTS) {
        const a = row(c, v, "split 1/2/5 m", true, MACHINES[0], "mid"), b = row(c, v, "split 1/2/5 m", true, MACHINES[1], "mid");
        dl.push([v.replace("-", "–"), a.compute_hours == null ? "not measured yet" : `${dur(a.compute_hours)} / ${dur(b.compute_hours)}`]);
      }
      const list = el("dl");
      for (const [k, v] of dl) list.append(el("dt", { text: k }), el("dd", { text: v }));
      const card = el("article", { class: "card", tabindex: "0", role: "button", "aria-label": `${NAMES[c]}: show its numbers` },
                      el("h3", { text: NAMES[c] }), list, el("p", { class: "neck", text: NECK[c] }));
      const open = () => {
        set({ country: c });
        const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        document.getElementById("numbers").scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
      };
      card.addEventListener("click", open);
      card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
      box.append(card);
    }
    box.append(el("p", { class: "note", text: "Computing: Ryzen 9 9900X / Ryzen 5 5650G, S at 1 m, M at 2 m, L at 5 m, lines counted in the search (section 6.5). Click a country for its numbers." }));
  }

  function render() {
    renderControls(); renderTiles(); renderChart(); renderTable(); renderStrata();
  }
  renderCards();
  let resizeTimer = 0;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderChart, 120); });
  render();
})();
