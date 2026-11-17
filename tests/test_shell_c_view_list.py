"""The result view's panels (viewer/src/result/view/SpotList.tsx, SpotDetails.tsx, FanPanel.tsx, SpotChooser.tsx,
Hint.tsx, SpotSummary.tsx, ViewFilters.tsx; step 3b of docs/line-volume/spec-view.md part B) in Playwright's Edge
over the app's server, offline, under the app's CSP, on the clip's run for the view (clip_runs.view_clip). The
mock-up's own checks, ported (B.7): ranking (the best first, line 1 and the steps down, the sorts, mean height and
clearance in every row, the tight mark, the order of "Lines from here"), the table of spots and its rows, the fan
(the hint, the panel, a row), the list's states (Start here, Best in view, All, a sector open, All levels, Why so
many), on a desktop and two phones. What a panel shows is compared with the page's model (the model's own rules
are tests/test_view_units.py's). Every wait is an event with a deadline. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_shell_c import BIG  # noqa: E402
from test_shell_c_view_map import DESKTOP, HELPERS, PHONE, WAIT, WORDS, _open, _state, _tap, site, view_clip  # noqa: E402, F401
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
PIXEL = {"viewport": {"width": 412, "height": 915}, "device_scale_factor": 2.625, "is_mobile": True, "has_touch": True}
NB = " "
PAGE, MORE, BEST_ROWS, CHOICES = 20, 40, 100, 6
# 16 of the browser's frames: longer than keepFocus's tries (6) and the frames a lost focus may be repaired in (12)
FRAMES = "() => new Promise((ok) => { let n = 16; const f = () => (--n > 0 ? requestAnimationFrame(f) : ok()); requestAnimationFrame(f); })"

# What the panels show, read from the DOM, and what the model says they must (window.P)
PANELS = r"""
window.P = {
  view() { return window.FINDALINE_VIEW.view; },
  n(v) { return Math.round(v).toLocaleString("en").replace(/,/g, " "); },
  rows(sel) { return [...document.querySelectorAll(sel + " .vl-main")].map((b) => ({
    spot: b.dataset.spot === undefined ? null : +b.dataset.spot, row: +b.dataset.row,
    mark: b.querySelector(".v-sh")?.getAttribute("aria-label") ?? null, label: b.querySelector(".vl-num")?.textContent ?? null,
    pick: b.querySelector(".vl-lab")?.textContent ?? null, pressed: b.getAttribute("aria-pressed"), tab: b.tabIndex,
    tight: !!b.querySelector(".r-tight"), dots: b.querySelectorAll(".ac").length, text: b.textContent,
    item: b.parentElement.tagName + ">" + b.tagName, inner: b.querySelectorAll("button, a, [tabindex]").length})); },
  // a row's values as the page must write them: length, the height (mean, or the highest point), clearance (a tight
  // line's rounded down), each after its column's name
  want(row, height) { const v = this.view().values, clr = v.clr[row], m = (x, d) => Number.isFinite(x) ? x.toFixed(d) + " m" : "–";
    return ["Length " + m(v.len[row], 0), height === "hmax" ? "Highest point " + m(v.hmax[row], 0) : "Mean height " + m(v.hmean[row], 1),
            "Clear. " + (clr < 1 ? (Math.floor(clr * 10 + 1e-4) / 10).toFixed(1) : clr.toFixed(1)) + " m"]; },
  holds(rows, height) { const view = this.view(); return rows.filter((r) => {
    const want = this.want(r.row, height).concat(r.spot === null ? [] : ["Lines " + this.n(view.passingCount(r.spot))]);
    const over = view.model.data.columns.over[r.row] === 1;
    return !(want.every((w) => r.text.includes(w)) && r.tight === (view.values.clr[r.row] < 1) && r.item === "LI>BUTTON" && r.inner === 0
             && r.text.includes("Over trees or buildings") === over); })
    .map((r) => r.text); },
  heads(sel) { return [...document.querySelectorAll(sel + " .vl-cols span")].map((s) => s.textContent).filter(Boolean); },
  text(sel) { return document.querySelector(sel)?.textContent ?? null; },
  list() { const view = this.view(), c = view.counts;
    return {title: this.text("#vl-top-title"), top: this.rows(".vl-topblock"), note: this.text(".vl-topblock .vl-note"),
            more: this.text(".vl-more-best"), count: this.text(".vl-count"), sentence: this.text(".vl-top-text"),
            chip: document.querySelector(".vl-top")?.getAttribute("aria-pressed"), clear: !!document.querySelector(".vl-clear"),
            sectors: [...document.querySelectorAll(".vl-sec")].map((s) => ({n: +s.dataset.sector, open: s.querySelector(".vl-toggle").getAttribute("aria-expanded"),
              name: s.querySelector(".vl-sec-name").textContent, meta: s.querySelector(".vl-meta").textContent, meta2: s.querySelector(".vl-meta2").textContent,
              rows: [...s.querySelectorAll(".vl-main")].map((b) => +b.dataset.spot), more: s.querySelector(".vl-more")?.textContent ?? null})),
            sort: document.querySelector(".vl-tree select")?.value, counts: c, level: view.level, best: view.best,
            inView: {best: Array.from(view.inView.best), m: view.inView.m, numbered: view.inView.numbered},
            order: Array.from(view.order), model: view.sectors.map((s) => ({n: s.n, word: s.word, spots: s.spots, lines: s.lines, hmeanMax: s.hmeanMax, len: s.len})),
            picks: view.picks().map((k) => [k.kind, k.row, k.spot, k.n]), kept: (() => { try { return localStorage.getItem("findaline.view.v1"); } catch (e) { return "blocked"; } })(),
            tabstops: [...document.querySelectorAll(".vl-rows")].map((u) => u.querySelectorAll('.vl-main[tabindex="0"]').length),
            keyLast: !!document.querySelector(".vl-tree")?.lastElementChild?.classList.contains("r-tight-key"),
            keys: document.querySelectorAll(".vl-tree .r-tight-key").length, tightRows: this.rows(".vl-tree").filter((r) => r.tight).length,
            csp: window.CSP_VIOLATIONS}; },
  details() { const view = this.view(), sel = view.selected, d = document.querySelector(".vl-details");
    return {selected: sel && [sel.spot, sel.row], index: view.selectedIndex, passing: sel ? Array.from(view.passingOf(sel.spot)) : [],
            label: sel ? view.label(sel.spot) : null, shown: !!d, data: d && [+d.dataset.spot, +d.dataset.row],
            title: this.text(".vl-spot-title"), step: this.text(".vl-step-text"), stats: [...document.querySelectorAll(".vl-details .u-stat")].map((s) => s.textContent),
            tight: this.text(".vl-details .r-tight-line"), stands: this.text(".vl-stands:not(.vl-fan-text)"), access: document.querySelectorAll(".vl-details .r-acc-row").length,
            prev: document.querySelector(".vl-prev")?.disabled ?? null, next: document.querySelector(".vl-next")?.disabled ?? null,
            pressed: [...document.querySelectorAll('.vl-main[aria-pressed="true"]')].map((b) => +b.dataset.spot), empty: this.text(".vl-empty"),
            hmean: sel ? view.values.hmean[sel.row] : null, clr: sel ? view.values.clr[sel.row] : null, standsFor: sel ? sel.line.stands_for ?? null : null}; },
  fan() { const view = this.view(), fan = view.fan, v = view.values;
    return {open: !!fan, panel: !!document.querySelector(".vl-fan"), text: this.text(".vl-fan-text"), heads: this.heads(".vl-fan"),
            rows: this.rows(".vl-fan").map((r) => ({row: r.row, mark: r.mark, text: r.text, dots: r.dots})),
            model: fan ? fan.rows.map((r) => ({row: r.row, label: r.label, numbered: r.numbered, dh: r.dh, bearing: r.bearing, hmean: v.hmean[r.row], clr: v.clr[r.row], len: v.len[r.row]})) : [],
            lines: fan?.lines, farEnds: fan?.farEnds, capped: fan?.capped, sort: fan?.sort,
            pressed: [...document.querySelectorAll(".vl-fan [data-sort]")].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.dataset.sort),
            onMap: window.FINDALINE_VIEW.map.drawn().numbers.map((n) => n.label).filter((l) => l[0] === "L")}; },
  // what has the focus: its class and id, "" for the page's body
  focus() { const a = document.activeElement; return !a || a === document.body ? "" : (a.closest("li")?.id ? "#" + a.closest("li").id + " " : "") + a.className; },
  inBox(el, box) { const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(); return r.top >= b.top - 1 && r.bottom <= b.bottom + 1; },
  size(sel) { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; },
};
"""


def _count(n: int) -> str:
    return f"{n:,}".replace(",", NB)


def _list(page) -> dict:
    page.evaluate("() => T.frames()")
    return page.evaluate("() => P.list()")


def _headline(s: dict) -> str:
    c = s["counts"]
    spots = WORDS["ui.result.spots_one" if c["spots"] == 1 else "ui.result.spots_other"].replace("{{n}}", _count(c["spots"]))
    lines = WORDS["ui.result.lines_one" if c["lines"] == 1 else "ui.result.lines_other"].replace("{{n}}", _count(c["lines"]))
    hidden = WORDS["ui.result.hidden"].replace("{{n}}", _count(c["hidden"])) if c["hidden"] else ""
    return f"{spots} · {lines}{hidden}"


def _sentence(s: dict) -> str:
    c = s["counts"]
    if s["chip"] == "true":
        return WORDS["ui.view.top_on"].replace("{{n}}", _count(c["topHidden"])).replace("{{m}}", _count(c["lines"] + c["topHidden"]))
    return WORDS["ui.view.top_off"].replace("{{n}}", _count(c["topHidden"]))


def _tree_holds(s: dict, limits: dict | None = None):
    """The tree shows the model's sectors in their order, each with its head; an open one its first rows by pages."""
    assert [x["n"] for x in s["sectors"]] == [m["n"] for m in s["model"]]
    for shown, model in zip(s["sectors"], s["model"]):
        assert shown["name"] == WORDS["ui.view.sector"].replace("{{n}}", str(model["n"] + 1)).replace("{{word}}", model["word"])
        k = len(model["spots"])
        assert shown["meta"] == WORDS["ui.view.sector_spots_one" if k == 1 else "ui.view.sector_spots_other"] \
            .replace("{{n}}", _count(k)).replace("{{m}}", f"{model['hmeanMax']:.0f}")
        assert shown["meta2"].startswith(_count(model["lines"]) + " line") and shown["meta2"].endswith(
            f" · {round(model['len'][0])}–{round(model['len'][1])} m")
        if shown["open"] == "true":
            limit = (limits or {}).get(model["n"], PAGE)
            assert shown["rows"] == model["spots"][:limit], model["n"]
            rest = k - limit
            assert shown["more"] == (WORDS["ui.view.show_more"].replace("{{n}}", _count(rest)) if rest > 0 else None)
        else:
            assert shown["rows"] == [] and shown["more"] is None


def test_list_ranking_sorts_sectors_and_chips(site):
    """A desktop. The headline and the chip's sentence from the counts; "Start here" at the Area level (the picks
    with P numbers, a pick's name, the fifth "From a top edge"); "Best in view" with B rows equal to the map's best
    spots, best first, and the button that raises Best; with All "In view: N spots", no numbers, at most 100 rows;
    every row a list item with one button and its values (mean height and clearance in every row, the tight mark
    exactly under 1 m); the five sorts, kept; the sectors with their heads, the first open, 20 rows and 40 more;
    "Top level only" off and on; "Clear all" leaves it; "Why so many?"; More filters without the grouping."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=PANELS)
            page.wait_for_selector(".vl-tree .vl-main", timeout=WAIT)
            first = _list(page)
            # the headline, the chip pressed at the start with its sentence (N of M of the passing lines)
            assert first["count"] == _headline(first) and first["counts"]["hidden"] == first["counts"]["topHidden"] > 0
            assert first["chip"] == "true" and first["sentence"] == _sentence(first) and first["clear"] is False
            assert first["sort"] == "hmean" and first["kept"] is None
            # the first view of this small run is at the Lines level: "Best in view: 10 of M", rows B1 … B10
            assert first["level"] == "lines" and first["inView"]["numbered"]
            assert first["title"] == WORDS["ui.view.best"].replace("{{n}}", "10").replace("{{m}}", _count(first["inView"]["m"]))
            assert [r["spot"] for r in first["top"]] == first["inView"]["best"] and [r["mark"] for r in first["top"]] == [f"B{k}" for k in range(1, 11)]
            assert first["more"] == WORDS["ui.view.show_30"] and first["note"] is None
            assert page.evaluate("() => P.holds(P.rows('.vl-topblock'), 'hmean').concat(P.holds(P.rows('.vl-tree'), 'hmean'))") == []
            # best first: the rows' mean heights never rise; every row carries the two access marks of this run
            means = page.evaluate("() => P.rows('.vl-topblock').map((r) => P.view().values.hmean[r.row])")
            assert means == sorted(means, reverse=True) and all(r["dots"] == 2 for r in first["top"])
            assert page.evaluate("() => P.heads('.vl-topblock')") == ["Length", "Mean height ▾", "Clear.", "Anchors", "Lines"]
            assert first["tabstops"] and set(first["tabstops"]) == {1}  # one tab stop per list
            _tree_holds(first)
            assert first["sectors"][0]["open"] == "true" and all(x["open"] == "false" for x in first["sectors"][1:])
            # the tree's labels are the spots' fixed labels
            labels = page.evaluate("() => P.rows('.vl-tree').map((r) => [r.label, P.view().label(r.spot)])")
            assert labels and all(a == b for a, b in labels)
            # "Show 30", "Show 100", "Show all" (by the keyboard): Best rises, the rows follow; with All no numbers, at
            # most 100 rows. The focus stays on the button while it stays, and goes to the block's tab stop when "Show
            # all" goes (a later selection: test_selection_details_fan_and_table)
            page.focus(".vl-more-best")
            page.keyboard.press("Enter")
            page.wait_for_function("() => P.view().best === 30 && P.rows('.vl-topblock').length === P.view().inView.best.length", timeout=WAIT)
            thirty = _list(page)
            assert [r["mark"] for r in thirty["top"]] == [f"B{k}" for k in range(1, len(thirty["top"]) + 1)] and len(thirty["top"]) == 30
            assert thirty["more"] == WORDS["ui.view.show_100"]
            assert page.evaluate("() => document.activeElement === document.querySelector('.vl-more-best')")
            page.keyboard.press("Enter")
            page.wait_for_function("() => P.view().best === 100", timeout=WAIT)
            page.keyboard.press("Enter")
            page.wait_for_function("() => P.view().best === 'all' && !document.querySelector('.vl-more-best')", timeout=WAIT)
            stop = ".vl-topblock .vl-main[tabindex=\"0\"]"
            page.wait_for_function(f"() => document.activeElement === document.querySelector('{stop}')", timeout=WAIT)
            every = _list(page)
            m = every["inView"]["m"]
            assert m > BEST_ROWS and every["title"] == WORDS["ui.view.in_view_other"].replace("{{n}}", _count(m))
            assert len(every["top"]) == BEST_ROWS and all(r["mark"] is None and r["label"] for r in every["top"])
            assert every["note"] == WORDS["ui.view.first_rows"].replace("{{shown}}", str(BEST_ROWS)).replace("{{n}}", _count(m))
            # the Area level: "Start here", the picks in the model's order under P1 …, a pick's name on its row
            page.evaluate("() => { P.view().setBest(10); P.view().setLevel('area'); }")
            page.wait_for_function(f"() => P.text('#vl-top-title') === {WORDS['ui.view.start']!r}", timeout=WAIT)
            start = _list(page)
            assert [[r["pick"], r["row"], r["spot"], r["mark"]] for r in start["top"]] == \
                [[WORDS[f"ui.view.pick.{kind}"], row, spot, f"P{n}"] for kind, row, spot, n in start["picks"]]
            assert 1 <= len(start["picks"]) <= 5 and start["picks"][0][0] == "mean" and start["more"] is None
            assert page.evaluate("() => P.holds(P.rows('.vl-topblock'), 'hmean')") == []
            assert "▾" not in "".join(page.evaluate("() => P.heads('.vl-topblock')"))  # the picks are not ranked
            # the fifth pick, "From a top edge", is the highest line on average whose two anchors read easy access, left
            # out when it is an earlier pick's line: on the clip that line is the first pick's own, so no fifth row
            # (the pick's rule: tests/test_view_units.py)
            edge = page.evaluate("() => { const v = P.view(), c = v.model.data.columns, h = v.values.hmean; let best = -1; "
                                 "for (let r = 0; r < v.count; r++) if (v.passes(r) && c.access1.at(r) === 2 && c.access2.at(r) === 2 && "
                                 "(best < 0 || h[r] > h[best])) best = r; return best; }")
            assert edge == start["picks"][0][1] and "edge" not in [k[0] for k in start["picks"]]
            page.evaluate("() => P.view().setLevel('auto')")
            # the five sorts: the tree follows the model's order, the ranking column is marked, the choice is kept
            for sort, head in (("clr", "Clear."), ("len", "Length"), ("hmax", "Highest point"), ("n", "Lines"), ("hmean", "Mean height")):
                page.select_option(".vl-tree select", sort)
                page.wait_for_function(f"() => P.view().sort === '{sort}' && P.rows('.vl-tree')[0]?.spot === P.view().sectors[0].spots[0]", timeout=WAIT)
                s = _list(page)
                _tree_holds(s)
                assert s["sectors"][0]["rows"][0] == s["order"][0] and f'"sort":"{sort}"' in s["kept"]
                heads = page.evaluate("() => P.heads('.vl-tree')")
                assert [h for h in heads if "▾" in h] == [head + " ▾"], heads
                height = "hmax" if sort == "hmax" else "hmean"
                assert page.evaluate(f"() => P.holds(P.rows('.vl-tree'), '{height}').concat(P.holds(P.rows('.vl-topblock'), '{height}'))") == []
            # a sector opened: 20 rows; "Show more" adds 40; closed again
            big = max(s["model"], key=lambda x: len(x["spots"]))
            assert len(big["spots"]) > PAGE
            toggle = f'.vl-sec[data-sector="{big["n"]}"] .vl-toggle'
            if next(x for x in s["sectors"] if x["n"] == big["n"])["open"] == "false":
                page.click(toggle)
            page.wait_for_function(f"() => document.querySelector('{toggle}').getAttribute('aria-expanded') === 'true'", timeout=WAIT)
            _tree_holds(_list(page))
            # "Show more" by the keyboard; on the clip it is the sector's last (34 spots): the button goes and the focus
            # goes to the first row it showed
            sec = f'.vl-sec[data-sector="{big["n"]}"]'
            assert PAGE < len(big["spots"]) <= PAGE + MORE, len(big["spots"])
            page.focus(f"{sec} .vl-more")
            page.keyboard.press("Enter")
            page.wait_for_function(f"() => document.querySelectorAll('{sec} .vl-main').length === {len(big['spots'])}", timeout=WAIT)
            page.wait_for_function(f"() => document.activeElement === document.querySelector('{sec} .vl-rows > li:nth-child({PAGE + 1}) > .vl-main')",
                                   timeout=WAIT)
            _tree_holds(_list(page), {big["n"]: PAGE + MORE})
            # a focused row that a filter removes: the focus goes to the row that took its place in the same list
            gone = page.evaluate(f"""() => {{ const v = P.view(), c = v.values.clr, rows = [...document.querySelectorAll('{sec} .vl-main')];
                const most = (b) => Math.max(...Array.from(v.passingOf(+b.dataset.spot)).map((r) => c[r]));
                const b = rows.slice(0, 30).reduce((a, x) => most(x) < most(a) ? x : a);
                return {{spot: +b.dataset.spot, index: rows.indexOf(b), clr: most(b)}}; }}""")
            page.focus(f"#vl-row-{gone['spot']} .vl-main")
            page.evaluate(f"() => {{ const m = P.view().model; m.setFilters({{...m.filters, clrMin: {gone['clr']} + 0.001}}); }}")
            page.wait_for_function(f"() => !document.querySelector('#vl-row-{gone['spot']}')", timeout=WAIT)
            page.wait_for_function(f"() => document.activeElement === (document.querySelector('{sec} .vl-rows > li:nth-child({gone['index'] + 1}) > .vl-main') "
                                   f"|| document.querySelector('{sec} .vl-rows > li:last-child > .vl-main'))", timeout=WAIT)
            page.evaluate("() => P.view().model.clearFilters()")
            page.wait_for_function("() => !document.querySelector('.vl-clear')", timeout=WAIT)
            # the tight mark's key line stands under the list, and only while a row shown is tight
            tight = page.evaluate("() => { const v = P.view(); return Array.from(v.order).find((s) => v.values.clr[v.shownOf(s)] < 1); }")
            assert tight is not None, "the clip has no spot whose shown line is tight"
            page.evaluate(f"() => P.view().select({tight})")
            page.wait_for_selector(f"#vl-row-{tight} .r-tight", timeout=WAIT)
            keyed = _list(page)
            assert keyed["tightRows"] >= 1 and keyed["keys"] == 1 and keyed["keyLast"] is True
            page.evaluate("() => { P.view().select(null); const m = P.view().model; m.setFilters({...m.filters, clrMin: 1}); }")
            page.wait_for_function("() => document.querySelectorAll('.vl-tree .r-tight').length === 0", timeout=WAIT)
            assert _list(page)["keys"] == 0
            page.evaluate("() => P.view().model.clearFilters()")
            page.wait_for_function("() => !document.querySelector('.vl-clear')", timeout=WAIT)
            # a redraw that changes nothing in the tree (the map moved) draws the top block's rows only
            before = page.evaluate("() => [window.FINDALINE_ROWS.rows, document.querySelectorAll('.vl-tree .vl-main').length, document.querySelectorAll('.vl-topblock .vl-main').length]")
            assert before[1] > PAGE
            page.evaluate("() => window.FINDALINE_MAP.panBy([40, 0], {animate: false})")
            page.evaluate("() => T.frames()")
            page.evaluate("() => T.frames()")
            after = page.evaluate("() => [window.FINDALINE_ROWS.rows, document.querySelectorAll('.vl-topblock .vl-main').length]")
            assert 0 < after[0] - before[0] <= 3 * max(before[2], after[1]), (before, after)
            # "Top level only" off: the lines that hang lower are shown too; on again
            page.click(".vl-top")
            page.wait_for_function("() => P.view().topOnly === false && P.list().chip === 'false'", timeout=WAIT)
            off = _list(page)
            assert off["counts"]["lines"] == first["counts"]["lines"] + first["counts"]["topHidden"] == off["counts"]["total"]
            assert off["sentence"] == _sentence(off) and off["count"] == _headline(off) and "hidden" not in off["count"]
            page.click(".vl-top")
            page.wait_for_function("() => P.view().topOnly === true", timeout=WAIT)
            # a filter through its chip's editor; "Clear all" ends it and leaves "Top level only"
            page.evaluate("() => { const m = P.view().model; m.setFilters({...m.filters, clrMin: 5}); }")
            page.wait_for_selector(".vl-clear", timeout=WAIT)
            filtered = _list(page)
            assert filtered["counts"]["lines"] < first["counts"]["lines"] and filtered["sentence"] == _sentence(filtered)
            assert filtered["count"] == _headline(filtered)
            assert page.evaluate("() => P.rows('.vl-tree').every((r) => P.view().values.clr[r.row] >= 5)")
            # the chip's × by the keyboard: the filter ends, the focus goes to the chip itself (a button now)
            x = f'.vl-filters .u-chip-x[aria-label="{WORDS["ui.view.chip.clearance_remove"]}"]'
            at = page.evaluate(f"() => {{ const c = document.querySelector('{x}').parentElement; return [...c.parentElement.children].indexOf(c); }}")
            page.focus(x)
            page.keyboard.press("Enter")
            page.wait_for_function("() => !document.querySelector('.vl-clear')", timeout=WAIT)
            chip = f".vl-filters .u-chips > :nth-child({at + 1})"
            page.wait_for_function(f"() => document.activeElement === document.querySelector('{chip}')", timeout=WAIT)
            assert page.evaluate(f"() => [document.activeElement.tagName, document.activeElement.className]") == ["BUTTON", "u-chip"]
            # "Clear all" by the keyboard: one change of the model for filters alone, the focus to "More filters"
            page.evaluate("""() => { const m = P.view().model; window.CHANGES = [];
                for (const k of ['setState', 'clearFilters']) { const f = m[k].bind(m); m[k] = (...a) => { window.CHANGES.push(k); return f(...a); }; }
                m.setFilters({...m.filters, clrMin: 5}); }""")
            page.wait_for_selector(".vl-clear", timeout=WAIT)
            page.evaluate("() => { window.CHANGES = []; }")
            page.focus(".vl-clear")
            page.keyboard.press("Enter")
            page.wait_for_function("() => !document.querySelector('.vl-clear')", timeout=WAIT)
            page.wait_for_function("() => document.activeElement === document.querySelector('.vl-filters .u-chip.u-add')", timeout=WAIT)
            assert page.evaluate("() => window.CHANGES") == ["clearFilters"]
            cleared = _list(page)
            assert cleared["chip"] == "true" and cleared["counts"] == first["counts"]
            # the "show" boxes alone: one change too
            page.evaluate("() => { const m = P.view().model; m.setState({...m.state, showOver: false}); }")
            page.wait_for_selector(".vl-clear", timeout=WAIT)
            page.evaluate("() => { window.CHANGES = []; }")
            page.click(".vl-clear")
            page.wait_for_function("() => !document.querySelector('.vl-clear')", timeout=WAIT)
            assert page.evaluate("() => [window.CHANGES, P.view().model.state.showOver]") == [["setState"], True]
            assert _list(page)["counts"] == first["counts"]
            # "Why so many?" opens today's box; More filters has no grouping part; the intro's link is not in the view
            page.click(".r-why-link")
            page.wait_for_selector("#r-why", timeout=WAIT)
            found = page.evaluate("() => P.view().model.data.found")
            assert _count(found) in page.evaluate("() => P.text('.r-found')") and _count(found) in page.evaluate("() => P.text('.r-why-text')")
            page.click(".vl-filters .u-add")
            page.wait_for_selector(".r-more", timeout=WAIT)
            heads = page.evaluate("() => [...document.querySelectorAll('.r-more h3')].map((h) => h.textContent)")
            assert heads and "Grouping" not in heads and not page.evaluate("() => !!document.querySelector('.r-group, .r-intro-link, .n-intro-link')")
            assert page.evaluate("() => document.querySelector('.vl-body').scrollTop") == 0
            # no line passes: both blocks say so
            page.evaluate("() => { const m = P.view().model; m.setFilters({...m.filters, lenMin: 1e6}); }")
            page.wait_for_function("() => document.querySelectorAll('.vl-main').length === 0", timeout=WAIT)
            assert page.evaluate("() => [...document.querySelectorAll('.vl-note')].map((n) => n.textContent)")[-1] == WORDS["ui.view.none_pass"]
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


def test_selection_details_fan_and_table(site):
    """A desktop. A press on a number selects: the details ("Spot 7.1 · N lines", the four values, the stepper by
    mean height, "Stands for"), the rows pressed, the sector opened and paged with the row in the list's box; the
    row pressed again, × and Esc end it (a top-block row too); the keys; "Lines from anchor A1" opens the panel
    whose rows carry the map's labels, its sentence, its sorts, the far end's mark; a row selects its line and
    closes the fan; a press on several spots opens the table (numbered first), a row selects and the map stays."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, script=PANELS)
            page.wait_for_selector(".vl-tree .vl-main", timeout=WAIT)
            empty = page.evaluate("() => P.details()")
            assert empty["selected"] is None and empty["empty"] == WORDS["ui.view.empty"] and empty["shown"] is False
            # a focused element that went while nothing repaired the focus (the code review's finding 1): a selection
            # the page makes later (a link) does not take the focus to a row
            page.evaluate("() => { const b = document.createElement('button'); document.body.appendChild(b); b.focus(); b.remove(); }")
            page.evaluate(FRAMES)
            page.evaluate("() => P.view().select(P.view().order[0])")
            page.wait_for_selector(".vl-details", timeout=WAIT)
            page.evaluate(FRAMES)
            assert page.evaluate("() => P.focus()") == ""
            page.evaluate("() => P.view().select(null)")
            page.wait_for_function("() => !document.querySelector('.vl-details')", timeout=WAIT)
            # the code review's sequence: "Show 30", "Show 100", "Show all" by the keyboard; the button goes and the
            # focus is on the top block's tab stop; a selection the page makes later does not move it
            page.focus(".vl-more-best")
            for best in ("30", "100", "'all'"):
                page.keyboard.press("Enter")
                page.wait_for_function(f"() => P.view().best === {best}", timeout=WAIT)
            stop = ".vl-topblock .vl-main[tabindex=\"0\"]"
            page.wait_for_function(f"() => document.activeElement === document.querySelector('{stop}')", timeout=WAIT)
            held = page.evaluate("() => P.focus()")
            page.evaluate("() => P.view().select(P.view().order[0])")
            page.wait_for_selector(".vl-details", timeout=WAIT)
            page.evaluate(FRAMES)
            assert held.endswith("vl-main") and page.evaluate("() => P.focus()") == held
            page.evaluate("() => { P.view().select(null); P.view().setBest(10); }")
            page.wait_for_function("() => !document.querySelector('.vl-details') && P.view().best === 10", timeout=WAIT)
            page.evaluate("() => document.activeElement.blur()")
            # a spot far down its sector, selected from the map's side (the model): its sector opens and pages to it
            target = page.evaluate("""() => { const v = P.view(), s = v.sectors.find((x, k) => k > 0 && x.spots.length > 25);
                return {spot: s.spots[s.spots.length - 1], n: s.n, rank: s.spots.length - 1, size: s.spots.length}; }""")
            page.evaluate(f"() => P.view().select({target['spot']})")
            page.wait_for_selector(f"#vl-row-{target['spot']}", timeout=WAIT)
            page.wait_for_function(f"() => P.inBox(document.querySelector('#vl-row-{target['spot']}'), document.querySelector('.vl-body'))", timeout=WAIT)
            shown = page.evaluate(f"() => document.querySelectorAll('.vl-sec[data-sector=\"{target['n']}\"] .vl-main').length")
            assert shown == min(target["size"], -(-(target["rank"] + 1) // PAGE) * PAGE) > PAGE
            d = page.evaluate("() => P.details()")
            n = len(d["passing"])
            assert d["selected"] == d["data"] == [target["spot"], d["passing"][0]] and d["index"] == 0
            assert d["title"].startswith(WORDS["ui.view.spot_one" if n == 1 else "ui.view.spot_other"].replace("{{label}}", d["label"]).replace("{{n}}", _count(n)))
            assert d["step"] == WORDS["ui.view.line_of"].replace("{{k}}", "1").replace("{{n}}", _count(n)) and d["prev"] is True
            assert len(d["stats"]) == 4 and d["stats"][1].startswith(f"{d['hmean']:.1f}") and d["access"] == 2
            assert (d["tight"] is not None) == (d["clr"] < 1) and target["spot"] in d["pressed"]
            # another sort: the selection is followed again (its row paged in and in the list's box)
            for sort in ("n", "len", "hmean"):
                page.select_option(".vl-tree select", sort)
                page.wait_for_function(f"() => P.view().sort === '{sort}' && !!document.querySelector('#vl-row-{target['spot']}') && "
                                       f"P.inBox(document.querySelector('#vl-row-{target['spot']}'), document.querySelector('.vl-body'))", timeout=WAIT)
            # the row pressed again ends the selection; the pages the selection opened go back
            page.click(f"#vl-row-{target['spot']} .vl-main")
            page.wait_for_function("() => P.view().selected === null && !document.querySelector('.vl-details')", timeout=WAIT)
            page.wait_for_function(f"() => document.querySelectorAll('.vl-sec[data-sector=\"{target['n']}\"] .vl-main').length === {PAGE}", timeout=WAIT)
            # "Stands for" in its two forms: a line that stands for several found lines, and one for itself alone
            both = page.evaluate("""() => { const v = P.view(), c = v.model.data.columns, out = {};
                for (let row = 0; row < v.count && !(out.one && out.many); row++) { if (!v.passes(row)) continue; const n = c.stands_for.at(row);
                  if (n === 1 && !out.one) out.one = [v.spotOf(row), row, n]; if (n > 1 && !out.many) out.many = [v.spotOf(row), row, n]; }
                return out; }""")
            assert both.get("one") and both.get("many"), both
            for key, (spot_, row_, n_) in both.items():
                page.evaluate(f"() => P.view().select({spot_}, {row_})")
                page.wait_for_function(f"() => P.details().data && P.details().data[1] === {row_}", timeout=WAIT)
                want = WORDS["ui.details.stands_for_n_one"] if key == "one" else \
                    "Stands for: " + WORDS["ui.details.stands_for_n_other"].replace("{{n}}", _count(n_))
                assert page.evaluate("() => P.details().stands") == want
            assert WORDS["ui.details.stands_for_n_one"] == "this line only: no other was found between its two anchor squares"
            # the × of the details ends the selection: the focus goes to the spot's row, not to the page's body
            page.focus(".vl-dclose")
            page.click(".vl-dclose")
            page.wait_for_function("() => P.view().selected === null && P.focus() !== ''", timeout=WAIT)
            assert page.evaluate("() => P.focus()").endswith("vl-main")
            # a press on a number of the map: its spot, the top block's row and the tree's are pressed
            s = _state(page, "view.setLevel('spots');")
            box = page.evaluate("() => { const b = T.box(); return [b.left, b.top]; }")
            number = s["numbers"][0]
            page.mouse.click(box[0] + number["x"], box[1] + number["y"])
            page.wait_for_selector(".vl-details", timeout=WAIT)
            d = page.evaluate("() => P.details()")
            best = int(number["label"][1:]) - 1
            assert d["selected"][0] == s["bestSpots"][best] and d["pressed"].count(d["selected"][0]) == 2
            # a selection by a press on the map moves no focus: it stays on the map
            page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
            assert "leaflet-container" in page.evaluate("() => P.focus()")
            top = page.evaluate("() => P.rows('.vl-topblock').filter((r) => r.pressed === 'true').map((r) => r.mark)")
            assert top == [number["label"]]
            # the steps down a spot: by mean height, clearance, length; the ends of the stepper are off
            spot = page.evaluate("() => { const v = P.view(); return Array.from(v.order).find((s) => v.passingCount(s) >= 4); }")
            page.evaluate(f"() => P.view().select({spot})")
            page.wait_for_function(f"() => P.details().data && P.details().data[0] === {spot}", timeout=WAIT)
            seen = [page.evaluate("() => P.details()")]
            for k in range(1, 4):
                page.click(".vl-next")
                page.wait_for_function(f"() => P.details().index === {k} && P.details().data[1] === P.details().selected[1]", timeout=WAIT)
                seen.append(page.evaluate("() => P.details()"))
            assert [x["selected"][1] for x in seen] == seen[0]["passing"][:4]
            means = [x["hmean"] for x in seen if x["hmean"] is not None]
            assert means == sorted(means, reverse=True)
            assert seen[3]["step"] == WORDS["ui.view.line_of"].replace("{{k}}", "4").replace("{{n}}", _count(len(seen[0]["passing"])))
            assert seen[1]["prev"] is False and all(x["pressed"] and set(x["pressed"]) == {spot} for x in seen)
            # the top block's row of the selected spot pressed again ends the selection (a row of either block)
            page.evaluate("() => { const v = P.view(); v.select(v.inView.best[0]); }")
            page.wait_for_selector(".vl-topblock .vl-sel", timeout=WAIT)
            page.click(".vl-topblock .vl-sel .vl-main")
            page.wait_for_function("() => P.view().selected === null", timeout=WAIT)
            # the keys: arrows move inside a list, Enter selects, Esc ends, the × ends
            page.focus(".vl-tree .vl-main")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowUp")
            assert page.evaluate("() => document.activeElement === document.querySelectorAll('.vl-tree .vl-main')[1]")
            page.keyboard.press("Enter")
            page.wait_for_function("() => P.view().selected && P.view().selected.spot === +document.querySelectorAll('.vl-tree .vl-main')[1].dataset.spot", timeout=WAIT)
            page.keyboard.press("Escape")
            page.wait_for_function("() => P.view().selected === null", timeout=WAIT)
            page.keyboard.press("Space")
            page.wait_for_selector(".vl-dclose", timeout=WAIT)
            page.click(".vl-dclose")
            page.wait_for_function("() => P.view().selected === null", timeout=WAIT)
            # "Lines from anchor A1": the panel in the details' place, its rows the model's with the map's labels
            page.evaluate(f"() => P.view().select({spot})")
            page.wait_for_selector(".vl-from-1", timeout=WAIT)
            page.click(".vl-from-1")
            page.wait_for_selector(".vl-fan", timeout=WAIT)
            page.evaluate("() => T.frames()")
            f = page.evaluate("() => P.fan()")
            assert f["open"] and not page.evaluate("() => !!document.querySelector('.vl-details')")
            # one tab stop for the fan's rows; the focus went from the button that is gone to the first row; arrows move
            page.wait_for_function("() => document.activeElement === document.querySelector('.vl-fan .vl-main')", timeout=WAIT)
            assert page.evaluate("() => document.querySelectorAll('.vl-fan .vl-main[tabindex=\"0\"]').length") == 1
            assert len(f["rows"]) > 2, f["rows"]
            fan_at = "() => [...document.querySelectorAll('.vl-fan .vl-main')].indexOf(document.activeElement)"
            for key, want in (("ArrowDown", 1), ("ArrowDown", 2), ("ArrowUp", 1), ("End", len(f["rows"]) - 1), ("Home", 0)):
                page.keyboard.press(key)
                assert page.evaluate(fan_at) == want, key
            lines = WORDS["ui.view.fan.lines_one" if f["lines"] == 1 else "ui.view.fan.lines_other"].replace("{{n}}", _count(f["lines"]))
            ends = WORDS["ui.view.fan.ends_one" if f["farEnds"] == 1 else "ui.view.fan.ends_other"].replace("{{n}}", _count(f["farEnds"]))
            text = WORDS["ui.view.fan.text"].replace("{{lines}}", lines).replace("{{m}}", "10").replace("{{ends}}", ends)
            assert f["text"] == text + (" " + WORDS["ui.view.fan.capped"].replace("{{n}}", str(len(f["model"]))) if f["capped"] else "")
            assert [[r["row"], r["mark"]] for r in f["rows"]] == [[r["row"], r["label"]] for r in f["model"]] and len(f["rows"]) <= 40
            assert set(f["onMap"]) <= {r["label"] for r in f["model"]} and all(r["dots"] == 1 for r in f["rows"])
            assert f["heads"] == ["Length", "Mean height ▾", "Clear.", "Height diff.", "Direction", "Far end"] and f["pressed"] == ["hmean"]
            assert page.evaluate("() => P.holds(P.rows('.vl-fan'), 'hmean')") == []
            free = [r["hmean"] for r in f["model"] if not r["numbered"] and r["hmean"] is not None]
            assert free == sorted(free, reverse=True)
            assert all(r["numbered"] for r in f["model"][:sum(1 for r in f["model"] if r["numbered"])])  # numbered rows first
            for sort, key, down in (("clr", "clr", True), ("len", "len", True), ("dh", "dh", False), ("dir", "bearing", False)):
                page.click(f'.vl-fan [data-sort="{sort}"]')
                page.wait_for_function(f"() => P.fan().sort === '{sort}' && P.fan().pressed[0] === '{sort}'", timeout=WAIT)
                g = page.evaluate("() => P.fan()")
                values = [abs(r[key]) if sort == "dh" else r[key] for r in g["model"] if not r["numbered"]]
                assert values == sorted(values, reverse=down), sort
                assert [[r["row"], r["mark"]] for r in g["rows"]] == [[r["row"], r["label"]] for r in g["model"]]
                assert len([h for h in g["heads"] if "▾" in h]) == 1
            # the panel's rows stay while the map's numbers do not change: a small move of the map ("Favourites only"
            # with the same lines passing is the model's unit: this page has no favourite, so it would pass no line)
            same = [[r["row"], r["mark"]] for r in g["rows"]]
            page.evaluate("() => window.FINDALINE_MAP.panBy([3, 0], {animate: false})")
            page.evaluate("() => T.frames().then(() => T.frames())")
            moved = page.evaluate("() => P.fan()")
            assert moved["open"] and [[r["row"], r["mark"]] for r in moved["rows"]] == same
            # a row's height difference and direction as the page writes them
            row = g["model"][0]
            sign = "" if abs(row["dh"]) < 0.05 else "+" if row["dh"] > 0 else "−"
            words = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            assert f"Height diff. {sign}{abs(row['dh']):.1f}{NB}m" in g["rows"][0]["text"]
            assert f"Direction {words[round(row['bearing'] / 45) % 8]} {round(row['bearing']) % 360}°" in g["rows"][0]["text"]
            # a fan row selects its line and closes the fan
            last = g["model"][-1]["row"]
            page.click(".vl-fan .vl-row:last-child .vl-main")
            page.wait_for_function(f"() => P.view().fan === null && P.view().selected && P.view().selected.row === {last}", timeout=WAIT)
            assert page.evaluate("() => P.details().data[1]") == last
            page.wait_for_function("() => P.focus().includes('vl-from-1')", timeout=WAIT)  # the button that opened the fan
            # "Close" keeps the selection; the focus goes back to the button that opened the fan
            page.click(".vl-from-2")
            page.wait_for_selector(".vl-fan-close", timeout=WAIT)
            page.click(".vl-fan-close")
            page.wait_for_function("() => P.view().fan === null && !!document.querySelector('.vl-details')", timeout=WAIT)
            page.wait_for_function("() => P.focus().includes('vl-from-2')", timeout=WAIT)
            # Esc ends the selection: the focus goes to the spot's row or the list, never to the body
            page.keyboard.press("Escape")
            page.wait_for_function("() => P.view().selected === null && P.focus().endsWith('vl-main')", timeout=WAIT)
            # several spots under a mouse press: the table of spots, numbered first by number, the rest by distance
            _state(page, "view.setLevel('lines');")
            at = page.evaluate("() => T.crowded(false)")
            assert at, "no point with several spots under the mouse"
            centre = page.evaluate("() => { const m = window.FINDALINE_MAP; return [m.getCenter().lat, m.getCenter().lng, m.getZoom()]; }")
            page.mouse.click(at["x"], at["y"])
            page.wait_for_selector(".vl-choose:not(.vl-choose-new)", timeout=WAIT)
            page.wait_for_function("() => !!document.activeElement.closest('.vl-choose')", timeout=WAIT)
            rows = page.evaluate("() => P.rows('.vl-choose')")
            assert 2 <= len(rows) <= CHOICES and set(at["spots"]) <= {r["spot"] for r in rows}
            assert page.evaluate("() => P.text('.vl-choose-title')") == WORDS["ui.view.chooser.title"].replace("{{n}}", str(len(rows)))
            marks = [r["mark"] for r in rows]
            numbered = [int(m[1:]) for m in marks if m]
            assert marks[:len(numbered)] == [f"B{k}" for k in sorted(numbered)] and all(m is None for m in marks[len(numbered):])
            assert all(r["label"] for r in rows if not r["mark"]) and page.evaluate("() => P.holds(P.rows('.vl-choose').map((r) => ({...r, spot: null})), 'hmean')") == []
            assert page.evaluate("() => P.view().selected") is None
            # Esc closes the table first; a row selects its spot, closes the table and never moves the map
            page.keyboard.press("Escape")
            page.wait_for_function("() => !document.querySelector('.vl-choose') && P.focus().includes('leaflet-container')", timeout=WAIT)
            # its ×: the same
            page.mouse.click(at["x"], at["y"])
            page.wait_for_selector(".vl-choose:not(.vl-choose-new)", timeout=WAIT)
            page.click(".vl-choose-x")
            page.wait_for_function("() => !document.querySelector('.vl-choose') && P.focus().includes('leaflet-container')", timeout=WAIT)
            page.mouse.click(at["x"], at["y"])
            page.wait_for_selector(".vl-choose:not(.vl-choose-new)", timeout=WAIT)
            page.click(".vl-choose .vl-row:last-child .vl-main")
            page.wait_for_function("() => !document.querySelector('.vl-choose') && P.view().selected !== null", timeout=WAIT)
            assert page.evaluate("() => P.view().selected.spot") == rows[-1]["spot"]
            # the focus to the selected spot's row in the tree (its sector opened and paged to it)
            page.wait_for_function(f"() => document.activeElement === document.querySelector('#vl-row-{rows[-1]['spot']} .vl-main')", timeout=WAIT)
            assert page.evaluate("() => { const m = window.FINDALINE_MAP; return [m.getCenter().lat, m.getCenter().lng, m.getZoom()]; }") == centre
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


def _sheet(page, key: str, stop: str):
    """One stop of a phone's sheet by its handle's arrow key, awaited (peek, half, full)."""
    page.focus(".u-sheet-handle")
    page.keyboard.press(key)
    page.wait_for_function(f"() => document.querySelector('.u-sheet').classList.contains('u-{stop}')", timeout=WAIT)


@pytest.mark.parametrize("device", [PHONE, PIXEL], ids=["390", "412"])
def test_phone_sheet_hint_and_fan(site, device):
    """A phone (390 and 412 px wide), whose sheet opens low. The sheet's order: the handle, the hint ("Press and
    hold"), the head's row, the body; at the low start the handle, the hint and the head's row are whole in the
    sheet, also with the longest heads. The hint's × hides it and leaves the "?" on the map beside the status line;
    kept. The head's row holds the headline, then the selected spot's title with its ×, then "Lines from here" with
    "Close", each pressed with the sheet low; a selection sends the sheet's body to its top; a fan row selects; the
    list's rows hold as on a desktop; one tab stop in the fan, the focus never on the page's body."""
    from playwright.sync_api import sync_playwright
    # is the sheet's head (hint and head's row) whole inside the sheet, and what its parts measure
    fits = """() => { const sheet = document.querySelector('.u-sheet').getBoundingClientRect(), head = document.querySelector('.u-sheet-head'),
        h = head.getBoundingClientRect(), row = document.querySelector('.vl-sheet-row').getBoundingClientRect(), hint = document.querySelector('.u-sheet-head .vl-hint');
        return {sheet: Math.round(sheet.height), handle: Math.round(h.top - sheet.top), hint: hint ? Math.round(hint.getBoundingClientRect().height) : 0,
                row: Math.round(row.height), whole: row.bottom <= sheet.bottom + 0.5 && h.top >= sheet.top,
                order: [...head.children].map((e) => e.className.split(' ')[0])}; }"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _open(browser, f"{site}#run={BIG}", device, script=PANELS)
            page.wait_for_selector(".u-sheet.u-peek .vl-count", timeout=WAIT)  # the view opens with the sheet low
            page.wait_for_function("() => document.querySelector('.u-sheet').getBoundingClientRect().height > 0", timeout=WAIT)
            # the sheet's order: handle, hint, head's row (the headline), body; all of the head inside the low sheet
            low = page.evaluate(fits)
            assert low["order"] == ["vl-hint", "vl-sheet-row"] and low["whole"] and low["sheet"] == 132, low
            assert page.evaluate("() => [P.text('.vl-hint-text'), !!document.querySelector('.vl-hint-open'), !!document.querySelector('.u-sheet-body .vl-hint')]") == \
                [WORDS["ui.view.hint.finger"], False, False]
            s = _list(page)
            assert page.evaluate("() => P.text('.u-sheet-head .vl-count')") == _headline(s)
            assert page.evaluate("() => document.querySelectorAll('.vl-count').length") == 1
            assert s["sentence"] == _sentence(s) and s["chip"] == "true"
            # a spot selected while nothing has the focus (a link, the page's own doing): the focus stays nowhere
            page.evaluate("() => P.view().select(P.view().order[0])")
            page.wait_for_selector(".u-sheet-head .vl-dclose", timeout=WAIT)
            page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
            assert page.evaluate("() => P.focus()") == ""
            page.evaluate("() => P.view().select(null)")
            page.wait_for_selector(".u-sheet-head .vl-count", timeout=WAIT)
            # the map's legend opened on the phone does not lie on the sheet's head, and the keyboard's way from its
            # button leads on into the sheet (nothing holds the focus)
            page.wait_for_selector(".v-fold", timeout=WAIT)
            if page.evaluate("() => document.querySelector('.v-fold').getAttribute('aria-expanded')") != "true":
                page.tap(".v-fold")
            page.wait_for_function("() => document.querySelector('.v-fold').getAttribute('aria-expanded') === 'true' && !!document.querySelector('.v-legend')", timeout=WAIT)
            apart = page.evaluate("""() => { const l = document.querySelector('.v-legend').getBoundingClientRect(), s = document.querySelector('.u-sheet').getBoundingClientRect();
                return l.bottom <= s.top + 1 || l.top >= s.bottom; }""")
            assert apart
            page.focus(".v-fold")
            for _ in range(40):
                page.keyboard.press("Tab")
                if page.evaluate("() => !!document.activeElement.closest('.u-sheet')"):
                    break
            assert page.evaluate("() => !!document.activeElement.closest('.u-sheet')")
            page.evaluate("() => { document.activeElement.blur(); window.TOUCHED = performance.now(); }")  # the next tap is its own
            # a number of the map tapped at the low start: the spot's head in the low sheet, whole; the body at its top
            first = _state(page, "view.setLevel('spots');")
            assert first["numbers"], first["free"]
            box = page.evaluate("() => { const b = T.box(); return [b.left, b.top]; }")
            number = first["numbers"][0]
            before = page.evaluate("() => P.focus()")
            scrolled = page.evaluate("() => { const b = document.querySelector('.u-sheet-body'); b.scrollTop = 300; return b.scrollTop; }")
            assert scrolled > 0  # the body was not at its top before the selection
            _tap(page, box[0] + number["x"], box[1] + number["y"])
            page.wait_for_selector(".u-sheet-head .vl-spot-title", timeout=WAIT)
            assert page.evaluate("() => P.view().selected.spot") == first["bestSpots"][int(number["label"][1:]) - 1]
            # a selection by a tap on the map moves no focus: it is where the tap put it (the map), on no control of
            # the sheet's head
            page.evaluate("() => T.frames().then(() => T.frames()).then(() => T.frames())")
            after = page.evaluate("() => P.focus()")
            assert before == "" and "leaflet-container" in after and "vl-" not in after
            spot_head = page.evaluate(fits)
            assert spot_head["whole"] and spot_head["order"] == ["vl-hint", "vl-sheet-row"], spot_head
            page.wait_for_function("() => document.querySelector('.u-sheet-body').scrollTop === 0", timeout=WAIT)
            # the longest heads still fit: a long spot's title with its two marks and ×, and "Lines from here" with "Close"
            page.evaluate("() => { const t = document.querySelector('.vl-spot-title'); t.firstChild.textContent = 'Spot 12.34 · 1 234 lines'; }")
            long_head = page.evaluate(fits)
            assert long_head["whole"], long_head
            print("peek", device["viewport"]["width"], low, spot_head, long_head)
            # the × of the head works with the sheet low
            page.tap(".u-sheet-head .vl-dclose")
            page.wait_for_function("() => P.view().selected === null && !!document.querySelector('.u-sheet-head .vl-count')", timeout=WAIT)
            # the hint's ×: the "?" on the map beside the status line takes the focus; kept; and back
            page.tap(".vl-hint-x")
            page.wait_for_selector(".v-map .vl-hint-open", timeout=WAIT)
            page.wait_for_function("() => document.activeElement.className === 'vl-hint-open'", timeout=WAIT)
            assert page.evaluate("() => [!!document.querySelector('.vl-hint'), localStorage.getItem('findaline.view.v1')]") == \
                [False, '{"sort":"hmean","hint":false}']
            page.tap(".vl-hint-open")
            page.wait_for_selector(".u-sheet-head > .vl-hint", timeout=WAIT)
            page.wait_for_function("() => document.activeElement.classList.contains('vl-hint-x')", timeout=WAIT)  # the focus on its ×
            # the sheet at full height: the list's rows hold; a row far down selects, the sheet's body goes to its top
            _sheet(page, "ArrowUp", "half")
            _sheet(page, "ArrowUp", "full")
            assert page.evaluate("() => P.holds(P.rows('.vl-topblock'), 'hmean').concat(P.holds(P.rows('.vl-tree'), 'hmean'))") == []
            row = page.locator(".vl-tree .vl-main").nth(6)
            row.scroll_into_view_if_needed()
            assert page.evaluate("() => document.querySelector('.u-sheet-body').scrollTop") > 0
            spot = int(row.get_attribute("data-spot"))
            row.tap()
            page.wait_for_function(f"() => P.view().selected && P.view().selected.spot === {spot} && document.querySelector('.u-sheet-body').scrollTop === 0",
                                   timeout=WAIT)
            d = page.evaluate("() => P.details()")
            assert d["shown"] and d["title"] is not None and d["step"].startswith("Line 1 of")
            assert page.evaluate("() => [!!document.querySelector('.u-sheet-head .vl-spot-title'), !!document.querySelector('.u-sheet-body .vl-spot-title'), "
                                 "document.querySelectorAll('.u-sheet-body .vl-count').length, document.querySelector('.u-sheet-body').firstElementChild.className.split(' ')[0]]") == \
                [True, False, 1, "vl-details"]
            # another sort under the selection (the list's own select): the list follows it again, but the sheet's
            # body is not sent to its top (that is for another spot only)
            down = page.evaluate("() => { const b = document.querySelector('.u-sheet-body'); b.scrollTop = 400; return b.scrollTop; }")
            assert down > 0
            sort = "() => { const s = document.querySelector('.vl-tree select'); s.value = '%s'; s.dispatchEvent(new Event('change', {bubbles: true})); }"
            page.evaluate(sort % "len")
            page.wait_for_function("() => P.view().sort === 'len'", timeout=WAIT)
            page.evaluate(FRAMES)
            assert page.evaluate("() => [P.view().selected.spot, document.querySelector('.u-sheet-body').scrollTop > 0]") == [spot, True]
            page.evaluate(sort % "hmean")
            page.wait_for_function("() => P.view().sort === 'hmean'", timeout=WAIT)
            # the head's row adds no edge of its own above the scrolled body (the sheet's own look is the kit's)
            edge = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.vl-sheet-row')); return [s.borderBottomWidth, s.boxShadow]; }")
            assert edge == ["0px", "none"]
            # "Lines from anchor A2": the panel in the sheet, its head with "Close"; one tab stop, the focus in the fan
            page.tap(".vl-from-2")
            page.wait_for_selector(".u-sheet-head .vl-fan-close", timeout=WAIT)
            page.evaluate("() => T.frames()")
            f = page.evaluate("() => P.fan()")
            assert f["panel"] and [[r["row"], r["mark"]] for r in f["rows"]] == [[r["row"], r["label"]] for r in f["model"]]
            assert page.evaluate("() => document.querySelector('.u-sheet-body').scrollTop") == 0
            page.wait_for_function("() => document.activeElement === document.querySelector('.vl-fan .vl-main')", timeout=WAIT)
            assert page.evaluate("() => document.querySelectorAll('.vl-fan .vl-main[tabindex=\"0\"]').length") == 1
            # with the sheet low the head's buttons still work and are whole: "Close", then the spot's ×
            _sheet(page, "ArrowDown", "half")
            _sheet(page, "ArrowDown", "peek")
            page.wait_for_function("() => Math.round(document.querySelector('.u-sheet').getBoundingClientRect().height) === 132", timeout=WAIT)
            fan_head = page.evaluate(fits)
            assert fan_head["whole"], fan_head
            page.tap(".vl-fan-close")
            page.wait_for_function("() => P.view().fan === null && !!document.querySelector('.u-sheet-head .vl-dclose')", timeout=WAIT)
            assert page.evaluate(fits)["whole"]
            page.tap(".vl-dclose")
            page.wait_for_function("() => P.view().selected === null && !!document.querySelector('.u-sheet-head .vl-count')", timeout=WAIT)
            # never the page's body: the rows of the low sheet's body cannot take it, so the map does
            page.wait_for_function("() => P.focus().includes('leaflet-container')", timeout=WAIT)
            # a fan row selects its line (the sheet at full height again)
            page.evaluate("() => P.view().select(P.view().order[0])")
            page.wait_for_selector(".u-sheet-head .vl-spot-title", timeout=WAIT)
            _sheet(page, "ArrowUp", "half")
            _sheet(page, "ArrowUp", "full")
            page.tap(".vl-from-1")
            page.wait_for_selector(".vl-fan .vl-main", timeout=WAIT)
            want = page.evaluate("() => P.view().fan.rows[0].row")
            page.tap(".vl-fan .vl-row:first-child .vl-main")
            page.wait_for_function(f"() => P.view().fan === null && P.view().selected && P.view().selected.row === {want}", timeout=WAIT)
            page.wait_for_function("() => P.focus().includes('vl-from-1')", timeout=WAIT)
            # the sizes of the panels' controls on this phone (CSS px), for the report
            sizes = page.evaluate("""() => Object.fromEntries([".vl-main", ".vl-toggle", ".vl-sec-map", ".vl-top", ".vl-dclose", ".vl-prev", ".vl-from-1",
                ".vl-hint-x", ".r-sort", ".u-chip", ".vl-more"].map((s) => [s, P.size(s)]))""")
            print("sizes", device["viewport"]["width"], sizes)
            assert sizes[".vl-main"][1] >= 40 and sizes[".vl-dclose"][1] >= 40
            assert page.evaluate("() => window.CSP_VIOLATIONS") == [] and page.errors == []
        finally:
            browser.close()


def test_storage_blocked_and_today_untouched(site):
    """With the browser's storage blocked the view's panels work (the sort, the hint's ×) and keep nothing; without
    the flag today's page shows none of the view's panels."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            blocked = "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"
            page = browser.new_context(**DESKTOP).new_page()
            page.add_init_script(blocked + HELPERS + PANELS)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)[:300]))
            page.goto(f"{site}&view=b#run={BIG}")
            page.wait_for_function("() => !!window.FINDALINE_VIEW", timeout=WAIT)
            page.wait_for_selector(".vl-tree .vl-main", timeout=WAIT)
            page.select_option(".vl-tree select", "len")
            page.wait_for_function("() => P.view().sort === 'len' && P.rows('.vl-tree')[0].spot === P.view().order[0]", timeout=WAIT)
            assert page.evaluate("() => P.text('.vl-hint-text')") == WORDS["ui.view.hint.mouse"]
            page.click(".vl-hint-x")
            page.wait_for_selector(".vl-hint-open", timeout=WAIT)
            # the keyboard's focus shows on the "?": the kit's ring (--focus) beside its own shadow (the design review's
            # finding 16)
            shadow = "() => getComputedStyle(document.querySelector('.vl-hint-open')).boxShadow"
            page.wait_for_function("() => document.activeElement === document.querySelector('.vl-hint-open')", timeout=WAIT)  # the hint's ×
            page.keyboard.press("Tab")  # the keyboard is in use: a focused control shows its ring
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            assert page.evaluate("() => document.activeElement === document.body")
            own = page.evaluate(shadow)
            focused = page.evaluate("() => { const e = document.querySelector('.vl-hint-open'); e.focus(); "
                                    "return [document.activeElement === e, e.matches(':focus-visible')]; }")
            ring = page.evaluate(shadow)
            assert focused == [True, True]
            assert own != "none" and "0px 0px 0px 3px" not in own and "0px 0px 0px 3px" in ring, (own, ring)
            assert ring.startswith(own) and len(ring) > len(own), (own, ring)
            page.click(".vl-tree .vl-main")
            page.wait_for_selector(".vl-details", timeout=WAIT)
            assert page.evaluate("() => P.list().kept") == "blocked" and errors == []
            page.close()
            page = _open(browser, f"{site}#run={BIG}", DESKTOP, flag=False, script=PANELS)
            page.wait_for_function("() => !!window.FINDALINE_RESULT", timeout=WAIT)
            assert page.evaluate("() => document.querySelectorAll('[class*=\"vl-\"]').length") == 0 and page.errors == []
        finally:
            browser.close()
