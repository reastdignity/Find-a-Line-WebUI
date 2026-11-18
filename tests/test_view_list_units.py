"""Units of the result view's panels, run under Node (docs/line-volume/spec-view.md B.2 items 9-14, B.4): what the
panels keep (result/view/viewstate.ts: the sort and the hint in the browser's storage, nothing else; the sectors'
pages; how the list follows a selection; the hint's word by pointer), and the panels' pure rules and texts (the
table of spots' order, the sentence, a height difference and a direction of "Lines from here", the sentence of
"Top level only", metres).

The run is the made-up one of tests/test_view_units.py; every expected value is counted here in Python or written
out from the specification's words, with the catalogue's texts."""
import json
import os
import subprocess

import pytest

from test_view_units import PRELUDE, REPO, VIEWER, Run

pytestmark = pytest.mark.skipif(
    __import__("shutil").which("node") is None or not os.path.isdir(os.path.join(VIEWER, "node_modules", "esbuild")),
    reason="needs Node and `npm install` in viewer/")

NB = " "
PAGE, MORE = 20, 40


@pytest.fixture(scope="module")
def words():
    with open(os.path.join(REPO, "locales", "en.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def run():
    return Run()


@pytest.fixture(scope="module")
def made_path(run, tmp_path_factory):
    path = tmp_path_factory.mktemp("list-run") / "made.json"
    path.write_text(json.dumps(run.made()), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """The panels' modules bundled for Node (their styles left out; the slots' file SpotDetails.tsx is not among them:
    it needs Leaflet and today's details, which need a window)."""
    folder = tmp_path_factory.mktemp("list-bundle")
    src = os.path.join(VIEWER, "src").replace("\\", "/")
    entry = folder / "entry.ts"
    entry.write_text(f'export * from "{src}/../test/model_rows";\n'
                     f'export * from "{src}/result/spots";\nexport {{ NO_FILTERS }} from "{src}/filters";\n'
                     f'export * from "{src}/result/view/viewstate";\n'
                     f'export {{ chooserRows, CHOICES, place }} from "{src}/result/view/SpotChooser";\n'
                     f'export {{ fanText, signedMetres, directionText }} from "{src}/result/view/FanPanel";\n'
                     f'export {{ topSentence, lengthLabel }} from "{src}/result/view/ViewFilters";\n'
                     f'export {{ metres, hoverOf }} from "{src}/result/view/SpotList";\n', encoding="utf-8")
    out = folder / "list.cjs"
    subprocess.run(["node", "-e", f"require('esbuild').buildSync({{entryPoints: [{json.dumps(str(entry))}], "
                                  "bundle: true, format: 'cjs', platform: 'node', "
                                  "loader: {'.css': 'empty', '.png': 'empty', '.svg': 'text'}, "
                                  f"outfile: {json.dumps(str(out))}}})"], cwd=VIEWER, check=True)
    return out


# the browser's storage, before the bundle is loaded: a plain map, or one that refuses (storage blocked)
STORAGE = r"""
const stored = new Map(Object.entries(JSON.parse(process.argv[4] || "{}")));
let blocked = false, writes = 0;
globalThis.localStorage = {
  getItem: (k) => { if (blocked) throw new Error("blocked"); return stored.has(k) ? stored.get(k) : null; },
  setItem: (k, v) => { if (blocked) throw new Error("blocked"); writes++; stored.set(k, String(v)); },
  removeItem: (k) => { if (blocked) throw new Error("blocked"); stored.delete(k); },
};
"""


def node(tmp_path, bundle, made_path, script: str, storage: dict | None = None):
    path = tmp_path / "script.cjs"
    path.write_text(STORAGE + PRELUDE + script, encoding="utf-8")
    result = subprocess.run(["node", str(path), str(bundle), str(made_path), json.dumps(storage or {})],
                            capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert result.returncode == 0, result.stderr[-4000:]
    return json.loads(result.stdout)


def count(n: int) -> str:
    """A count as the page writes it: thousands with a no-break space."""
    return f"{n:,}".replace(",", NB)


def test_kept_pages_and_the_hints_word(tmp_path, bundle, made_path):
    """What a stored text keeps (the sort among the five keys, the hint; anything else: the defaults); the rows a
    sector shows after a selection (its page of 20 is in, never fewer than it showed); the hint speaks of a finger
    always in the phone layout, else by the pointer last pressed, before any press by the device."""
    found = node(tmp_path, bundle, made_path, r"""
out.parse = [null, "", "not json", "[]", '{"sort":"len"}', '{"sort":"n","hint":false}', '{"sort":"best","hint":"no"}',
             '{"sort":"hmax","hint":true,"size":"p390","topOnly":false}'].map((t) => m.parseKept(t));
out.sorts = m.SORTS;
out.pages = [[0, 20], [19, 20], [20, 20], [39, 20], [40, 20], [45, 20], [30, 60], [59, 60], [60, 60], [3, 100]].map(([r, l]) => m.pageFor(r, l));
out.consts = [m.PAGE, m.MORE, m.VIEW_KEY, m.CHOICES];
out.finger = [[true, "", false], [true, "", true], [true, "mouse", true], [true, "touch", false], [true, "pen", false],
              [false, "mouse", false], [false, "", false]].map(([w, p, c]) => m.byFinger(w, p, c));
done();
""")
    default = {"sort": "hmean", "hint": True}
    assert found["parse"] == [default, default, default, default, {"sort": "len", "hint": True},
                              {"sort": "n", "hint": False}, default, {"sort": "hmax", "hint": True}]
    assert found["sorts"] == ["hmean", "clr", "len", "hmax", "n"]  # B.2 item 13's order: mean height first
    assert found["pages"] == [20, 20, 40, 40, 60, 60, 60, 60, 80, 100]
    assert found["consts"] == [PAGE, MORE, "findaline.view.v1", 6]
    assert found["finger"] == [False, True, False, True, True, True, True]


def test_the_view_remembers_only_the_sort_and_the_hint(tmp_path, bundle, made_path, run):
    """A view gets the kept sort once, at the first use of its panels' state (the B numbers follow the order), and
    the kept hint; a sort or the hint's × is kept under findaline.view.v1 and nothing else is ("Top level only" is
    on at every start); with the storage blocked the page works and keeps nothing."""
    ok, _ = run.passing()
    found = node(tmp_path, bundle, made_path, r"""
const a = build().view;
out.before = [a.sort, a.topOnly];
const state = m.panelState(a);
out.first = [a.sort, state.hint, list(a.order).slice(0, 5), writes];
a.setSort("hmean");                 // the user's choice of this visit is not undone by a later use of the state
m.panelState(a);
out.once = a.sort;
m.sortBy(a, "n");
out.sorted = [a.sort, stored.get("findaline.view.v1")];
const once = writes;
m.sortBy(a, "n"); m.showHint(a, m.panelState(a).hint); m.panelState(a);  // nothing changed: nothing is written
out.writes = [once, writes];
m.showHint(a, true);
a.setTopOnly(false);
out.shown = [m.panelState(a).hint, stored.get("findaline.view.v1"), [...stored.keys()].sort()];
let drawn = 0;
const stop = m.watchPanels(a, () => drawn++);
m.changePanels(a, (s) => { s.why = true; });
m.showHint(a, false);
stop();
m.changePanels(a, (s) => { s.why = false; });
out.drawn = drawn;
// another run opened later: the kept choices, "Top level only" on again
const b = build().view;
out.second = [m.panelState(b).hint, b.sort, b.topOnly, m.panelState(b).why];
// storage blocked: the defaults, and nothing throws
blocked = true;
const c = build({}, made).view;
m.sortBy(c, "clr");
m.showHint(c, false);
out.blocked = [m.kept(), c.sort, m.panelState(c).hint];
done();
""", {"findaline.view.v1": json.dumps({"sort": "len", "hint": False}), "findaline.filters": "{}"})
    assert found["before"] == ["hmean", True]
    assert found["first"] == ["len", False, run.order(ok, "len")[:5], 0]  # reading the kept choices writes nothing
    assert found["once"] == "hmean"
    assert found["sorted"][0] == "n" and json.loads(found["sorted"][1]) == {"sort": "n", "hint": False}
    assert found["writes"] == [1, 1]  # a choice is written when it changes, once
    assert found["shown"][0] is True and json.loads(found["shown"][1]) == {"sort": "n", "hint": True}
    assert "findaline.view.v1" in found["shown"][2] and not [k for k in found["shown"][2] if "top" in k.lower()]
    assert found["drawn"] == 2
    assert found["second"] == [False, "n", True, False]
    assert found["blocked"] == [{"sort": "hmean", "hint": True}, "clr", False]


def test_the_list_follows_a_selection(tmp_path, bundle, made_path, run):
    """A selected spot's sector opens and shows pages until its row, in steps of 20, and the list has to scroll, once
    per selected spot (the user may close the sector again; stepping through the spot's lines changes nothing); the
    pages a selection needed go back when it leaves the sector or ends, the user's own ("Show more") stay, and a
    "Show more" pressed while a selection has paged the sector grows the user's own pages, not the selection's; after a
    change of the sort the selection is followed again (paged to its new place, scrolled once, a phone's sheet not
    sent to its top); the first sector shown is open until the user says otherwise."""
    ok, _ = run.passing()
    order = run.order(ok)
    by_sector = {}
    for spot in order:
        by_sector.setdefault(int(run.sector_of_spot[spot]), []).append(spot)
    first = int(run.sector_of_spot[order[0]])
    big = max((s for s in by_sector if s != first), key=lambda s: len(by_sector[s]))
    assert len(by_sector[big]) > 2 * PAGE
    last, early = by_sector[big][-1], by_sector[big][3]
    rank = len(by_sector[big]) - 1
    # under the sort by lines: a spot of the big sector on its first page by mean height and beyond it by lines
    by_lines = [s for s in run.order(ok, "n") if int(run.sector_of_spot[s]) == big]
    moved = next(s for s in by_sector[big][:PAGE] if by_lines.index(s) >= PAGE)
    found = node(tmp_path, bundle, made_path, r"""
const {view} = build();
const [big, last, early, first, moved, other] = %s;
const s = m.panelState(view);
const k = (n) => view.sectors.findIndex((x) => x.n === n);
const state = () => ({open: m.isOpen(s, big, k(big)), limit: m.limitOf(s, big), own: s.limit.get(big) ?? null, followed: s.followed, scroll: s.scroll});
out.start = [m.follow(s, view), state(), m.isOpen(s, first, k(first)), view.sectors.map((x) => m.isOpen(s, x.n, k(x.n)))];
view.select(last);
out.selected = [m.follow(s, view), state(), s.scrollNew];
s.scroll = false;                                // the list scrolled
out.again = [m.follow(s, view), state()];
view.step(1);
out.stepped = [m.follow(s, view), state().followed];
s.open.set(big, false);                          // the user closes the sector: it stays closed
out.closed = [m.follow(s, view), state().open];
view.select(early);                              // another spot of it, on its first page: opens again, the pages go back
out.early = [m.follow(s, view), state()];
view.select(last);
m.follow(s, view);
view.select(other);                              // the selection leaves the sector: its pages go back
m.follow(s, view);
out.left = state().limit;
view.select(last);
m.follow(s, view);
view.select(null);                               // the selection ends: its pages go back
out.none = [m.follow(s, view), state()];
// "Show more" while a selection has paged the sector: 40 more rows now; at the selection's end the user's own pages
// stay (PAGE + MORE), the selection's go back
view.select(last);
m.follow(s, view);
const pagedBy = state().limit;
m.showMore(s, big);
out.pagedMore = [pagedBy, state().limit, state().own];
view.select(null);
m.follow(s, view);
out.pagedEnd = [state().limit, state().own];
s.limit.delete(big);
m.showMore(s, big);                              // "Show more" once (the button's own call), then a selection and its end
view.select(early);
m.follow(s, view);
out.more = [state().limit, state().own];
view.select(null);
m.follow(s, view);
out.kept = [state().limit, state().own];
s.limit.delete(big);
// the reviewer's example: a sector of 1 211 spots, the spot at rank 1 000 selected (paged to 1 020), "Show more",
// the selection ends: 60 rows, not 1 060
const sector = {n: 0, spots: Array.from({length: 1211}, (_, k) => k)};
const fake = {selected: null, sort: "hmean", version: 1, sectors: [sector], sectorOf: () => 0};
const f = {open: new Map(), limit: new Map(), paged: new Map(), followed: null, followedOrder: "", scroll: false, scrollNew: false};
fake.selected = {spot: 1000};
m.follow(f, fake);
const at1000 = m.limitOf(f, 0);
m.showMore(f, 0);
const more1000 = m.limitOf(f, 0);
fake.selected = null;
m.follow(f, fake);
out.example = [at1000, more1000, m.limitOf(f, 0), f.limit.get(0)];
// another sort under a selection: followed again, paged to the row's new place, scrolled once
view.select(moved);
m.follow(s, view);
s.scroll = false;
out.before = [state().limit, view.sectors.find((x) => x.n === big).spots.indexOf(moved)];
m.sortBy(view, "n");
out.sorted = [m.follow(s, view), state(), s.scrollNew, view.sectors.find((x) => x.n === big).spots.indexOf(moved)];
s.scroll = false;
out.sortedAgain = m.follow(s, view);
// other lines pass (a filter): followed again too
const version = view.version;
view.setTopOnly(false);
out.filtered = [view.version !== version, m.follow(s, view)];
s.open.set(first, false);
out.firstClosed = m.isOpen(s, first, k(first));
done();
""" % json.dumps([big, last, early, first, moved, by_sector[first][0]]))
    paged = -(-(rank + 1) // PAGE) * PAGE
    assert found["start"][0] is False and found["start"][1] == {"open": False, "limit": PAGE, "own": None, "followed": None, "scroll": False}
    assert found["start"][2] is True and found["start"][3] == [True] + [False] * (len(by_sector) - 1)
    assert found["selected"] == [True, {"open": True, "limit": paged, "own": None, "followed": last, "scroll": True}, True]
    assert found["again"] == [False, {"open": True, "limit": paged, "own": None, "followed": last, "scroll": False}]
    assert found["stepped"] == [False, last]
    assert found["closed"] == [False, False]
    assert found["early"] == [True, {"open": True, "limit": PAGE, "own": None, "followed": early, "scroll": True}]
    assert found["left"] == PAGE
    assert found["none"] == [False, {"open": True, "limit": PAGE, "own": None, "followed": None, "scroll": False}]
    assert found["more"] == [PAGE + MORE, PAGE + MORE] and found["kept"] == [PAGE + MORE, PAGE + MORE]
    assert paged > PAGE and found["pagedMore"] == [paged, paged + MORE, PAGE + MORE]
    assert found["pagedEnd"] == [PAGE + MORE, PAGE + MORE]
    assert found["example"] == [1020, 1060, PAGE + MORE, PAGE + MORE]
    place = by_lines.index(moved)
    assert found["before"] == [PAGE, by_sector[big].index(moved)] and place >= PAGE
    assert found["sorted"] == [True, {"open": True, "limit": -(-(place + 1) // PAGE) * PAGE, "own": None, "followed": moved, "scroll": True},
                               False, place]
    assert found["sortedAgain"] is False and found["filtered"] == [True, True] and found["firstClosed"] is False


def test_hover_length_chip_and_the_tables_place(tmp_path, bundle, made_path, words):
    """The mouse over a row thickens its line on the map and a row that goes ends only its own highlight (a finger
    never highlights); the Length chip's words; the table of spots stands beside the press (right and below, else
    left or above) inside the map's free part."""
    found = node(tmp_path, bundle, made_path, r"""
const calls = [], map = {highlight: (row) => calls.push(row)};
const a = m.hoverOf(map, 5), b = m.hoverOf(map, 9), none = m.hoverOf(null, 5);
a.enter("touch"); a.enter("pen"); none.enter("mouse"); a.gone(); a.leave("mouse");
out.quiet = calls.slice();
a.enter("mouse"); a.leave("touch"); a.leave("mouse"); a.leave("mouse");
out.overAndAway = calls.splice(0);
a.enter("mouse"); b.enter("mouse"); a.gone(); a.leave("mouse");   // the mouse is over another row by now
out.other = calls.splice(0);
b.gone(); b.gone();
out.gone = calls.splice(0);
out.length = [{lenMin: null, lenMax: null}, {lenMin: 40, lenMax: null}, {lenMin: null, lenMax: 120}, {lenMin: 40.4, lenMax: 120.6}].map(m.lengthLabel);
globalThis.innerWidth = 1400; globalThis.innerHeight = 900;
const area = {left: 372, top: 58, right: 1020, bottom: 866};
out.place = [[500, 300], [900, 300], [500, 800], [380, 60], [1010, 860]].map(([x, y]) => m.place({x, y}, 300, 200, area));
out.small = m.place({x: 400, y: 100}, 300, 200, {left: 372, top: 58, right: 600, bottom: 200});
globalThis.innerWidth = 700;                                       // a window narrower than the area says
out.narrow = m.place({x: 500, y: 300}, 300, 200, area);
done();
""")
    assert found["quiet"] == [] and found["overAndAway"] == [5, None] and found["other"] == [5, 9] and found["gone"] == [None]
    assert found["length"] == [words["ui.view.chip.length"], words["ui.view.chip.length_min"].replace("{{a}}", "40"),
                               words["ui.view.chip.length_max"].replace("{{b}}", "120"),
                               words["ui.view.chip.length_range"].replace("{{a}}", "40").replace("{{b}}", "121")]
    at = lambda left, top: {"left": left, "top": top}  # noqa: E731
    assert found["place"] == [at(512, 312), at(588, 312), at(512, 588), at(392, 72), at(698, 648)]
    assert found["small"] == at(376, 62) and found["narrow"] == at(376, 312)


def test_table_of_spots_order(tmp_path, bundle, made_path):
    """The table's rows: a spot once, the numbered ones first by their number (B2 before B10), the others by their
    distance from the press; at most six."""
    found = node(tmp_path, bundle, made_path, r"""
const c = (spot, label, px) => ({spot, row: spot * 10, label, px});
const rows = (cs) => m.chooserRows(cs).map((x) => x.spot);
out.order = rows([c(1, null, 5), c(2, "B10", 9), c(3, null, 2), c(4, "B2", 7), c(5, "P1", 1)]);
out.once = rows([c(7, null, 3), c(7, null, 1), c(8, "B1", 6), c(8, "B1", 2)]);
out.most = rows([1, 2, 3, 4, 5, 6, 7, 8].map((k) => c(k, null, 20 - k)));
const given = [c(1, null, 5), c(2, "B1", 9)];
m.chooserRows(given);
out.kept = given.map((x) => x.spot);
done();
""")
    assert found["order"] == [5, 4, 2, 3, 1]
    assert found["once"] == [8, 7]
    assert found["most"] == [8, 7, 6, 5, 4, 3]
    assert found["kept"] == [1, 2]


def test_texts_of_the_fan_the_chip_and_metres(tmp_path, bundle, made_path, run, words):
    """The sentence of "Lines from here" (its two plurals, "The best 40 are shown." when the far ends are more
    than the rows), a height difference with its sign at 0.1 m, a direction as "SE 141°", the sentence of "Top
    level only" on and off (N of M of the lines that pass the other filters), and metres with a no-break space."""
    ok, top_hidden = run.passing()
    # filters under which exactly two, and exactly one, of the lines that hang lower pass: the two with the most
    # clearance among them, then only the longer of the two
    lower = sorted((i for i in range(run.n) if run.top[i] == 0), key=lambda i: -run.clr[i])
    a, b, c = lower[:3]
    two = {"clrMin": float(run.clr[b] + run.clr[c]) / 2}
    one = {**two, "lenMin": float(run.len[a] + run.len[b]) / 2}
    assert run.clr[b] > run.clr[c] and run.len[a] != run.len[b]
    assert run.passing(clr_min=two["clrMin"])[1] == 2 and run.passing(clr_min=one["clrMin"], len_min=one["lenMin"])[1] == 1
    star = int(run.spot[0])  # the star's spot: its lines start at one point, their far ends 22 m apart
    found = node(tmp_path, bundle, made_path, r"""
const {model, view} = build();
const star = %d;
view.openFan({lat: 0, lng: 0}, {row: view.shownOf(star), end: 1});
out.fan = [view.fan.lines, view.fan.farEnds, view.fan.rows.length, view.fan.capped, m.fanText(view.fan)];
out.one = m.fanText({lines: 1, farEnds: 1, rows: [{}], capped: false});
out.few = m.fanText({lines: 1234, farEnds: 2, rows: [{}, {}], capped: false});
out.signed = [3.24, -0.44, 0.04, -0.04, 0, 144.26, -0.06, NaN].map(m.signedMetres);
out.direction = [141, 0, 22.4, 22.6, 359.6, 180, 270, 337.4, NaN].map(m.directionText);
out.metres = [m.metres(120), m.metres(59.94, 1), m.metres(NaN), m.metres(null), m.metres(1234.4)];
out.on = [m.topSentence(view), view.counts.lines, view.counts.topHidden];
view.setTopOnly(false);
out.off = [m.topSentence(view), view.counts.lines];
model.setFilters({...m.NO_FILTERS, clrMin: 10});
out.offFiltered = [m.topSentence(view), view.counts.topHidden];
view.setTopOnly(true);
out.onFiltered = [m.topSentence(view), view.counts.lines, view.counts.topHidden];
// exactly one line hangs lower, then two: the singular's own words
for (const few of %s) {
  model.setFilters({...m.NO_FILTERS, ...few});
  const on = [m.topSentence(view), view.counts.lines + view.counts.topHidden, view.counts.topHidden];
  view.setTopOnly(false);
  (out.ones ||= []).push([...on, m.topSentence(view)]);
  view.setTopOnly(true);
}
// the singular with M of a thousand or more (the made run is smaller): its counts with the no-break space
out.big = [true, false].map((topOnly) => m.topSentence({topOnly, counts: {topHidden: 1, lines: 1233}}));
done();
""" % (star, json.dumps([one, two])))
    lines, ends, rows, capped, text = found["fan"]
    assert capped is True and rows == 40 and ends > rows
    assert text == f"{count(lines)} lines start within 10 m of this point, to {count(ends)} far ends. The best 40 are shown."
    assert found["one"] == "1 line starts within 10 m of this point, to 1 far end."
    assert found["few"] == f"1{NB}234 lines start within 10 m of this point, to 2 far ends."
    minus = "−"
    assert found["signed"] == [f"+3.2{NB}m", f"{minus}0.4{NB}m", f"0.0{NB}m", f"0.0{NB}m", f"0.0{NB}m", f"+144.3{NB}m",
                               f"{minus}0.1{NB}m", "–"]
    assert found["direction"] == ["SE 141°", "N 0°", "N 22°", "NE 23°", "N 0°", "S 180°", "W 270°", "NW 337°", "–"]
    assert found["metres"] == [f"120{NB}m", f"59.9{NB}m", "–", "–", f"1234{NB}m"]
    passing = int(ok.sum())
    on = words["ui.view.top_on"].replace("{{n}}", count(top_hidden)).replace("{{m}}", count(passing + top_hidden))
    assert found["on"] == [on, passing, top_hidden]
    assert on.startswith("Top level only is on: ") and on.endswith(" lines hang lower on the same face and are hidden. Press the chip to see them.")
    off = words["ui.view.top_off"].replace("{{n}}", count(top_hidden))
    assert found["off"] == [off, passing + top_hidden]
    assert off == f"Top level only is off: the {count(top_hidden)} lines that hang lower on the same face are shown too."
    ok10, hidden10 = run.passing(clr_min=10)
    assert found["offFiltered"] == [words["ui.view.top_off"].replace("{{n}}", count(hidden10)), hidden10]
    (on1, m1, n1, off1), (on2, m2, n2, off2) = found["ones"]
    assert (n1, n2) == (1, 2) and m1 == int(run.passing(clr_min=one["clrMin"], len_min=one["lenMin"])[0].sum()) + 1
    assert on1 == f"Top level only is on: 1 of {count(m1)} lines hangs lower on the same face and is hidden. Press the chip to see it."
    assert off1 == "Top level only is off: the 1 line that hangs lower on the same face is shown too."
    assert on2 == words["ui.view.top_on"].replace("{{n}}", "2").replace("{{m}}", count(m2))
    assert off2 == "Top level only is off: the 2 lines that hang lower on the same face are shown too."
    assert found["big"] == [f"Top level only is on: 1 of 1{NB}234 lines hangs lower on the same face and is hidden. Press the chip to see it.",
                            off1]
    assert found["onFiltered"] == [words["ui.view.top_on"].replace("{{n}}", count(hidden10))
                                   .replace("{{m}}", count(int(ok10.sum()) + hidden10)), int(ok10.sum()), hidden10]
