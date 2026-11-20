"""The 3D view's controls and marks on a touch screen (docs/DESIGN.md, "The pilot's look", rows 43 and 45; R2), in
Playwright with a phone's profile (Pixel 7: touch, a coarse pointer) and on a desktop: the tools, the views' switch,
the speed, the data credits' button, the list's heads and rows 44 px on touch; the marks over the stage (the fan's
dots, the other lines' labels, the anchors' handles) keep their drawn size while their invisible targets are 44 px on
touch and 24 px with a mouse; a finger's tap inside a target but outside the drawn box reaches the control. Headless
Edge through Playwright: run from PowerShell (headless Edge prints nothing from Git Bash)."""

import json
import os
import sys
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_patch import _offline_env, clip_data  # noqa: E402,F401 (the fixture of the 3D page's tests)
from test_shell_c_view_map import _tap  # noqa: E402
from test_view3d import _script_page  # noqa: E402
from test_view3d_others import _key_of  # noqa: E402
from test_web import EDGE, WAIT, _lines_of, _playwright, _server  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(), reason="needs Microsoft Edge and Playwright")

READY = "() => document.getElementById('view3d')?.dataset.ready === '1'"
# Each shown element of `sel`: its own box and its target (the box joined with an absolutely positioned ::after,
# whose insets count from inside the element's border), [left, top, right, bottom]
BOXES = r"""(sel) => [...document.querySelectorAll(sel)].filter((e) => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('.v3-hidden'); }).map((e) => {
  const r = e.getBoundingClientRect(), own = [r.left, r.top, r.right, r.bottom], a = getComputedStyle(e, '::after');
  if (a.content === 'none' || a.position !== 'absolute') return {own, target: own};
  const cs = getComputedStyle(e), l = r.left + parseFloat(cs.borderLeftWidth) + parseFloat(a.left),
        t = r.top + parseFloat(cs.borderTopWidth) + parseFloat(a.top);
  return {own, target: [Math.min(own[0], l), Math.min(own[1], t), Math.max(own[2], l + parseFloat(a.width)),
                        Math.max(own[3], t + parseFloat(a.height))]}; })"""
# The control a click reaches, recorded and not acted on (a capture listener on the document) while CATCHING
CATCH = """() => { window.CLICKS = []; window.CATCHING = true; document.addEventListener('click', (e) => {
  if (!window.CATCHING) return;
  const c = e.target.closest('button, .v3-handle'); window.CLICKS.push(c ? c.className : e.target.tagName);
  e.preventDefault(); e.stopPropagation(); }, true); }"""
# The second shown label set 30 px under the first (its place, through the CSSOM as screen.ts place: no frame is drawn
# meanwhile, so it stays); the keys and boxes of both
PAIR = r"""() => { const ats = [...document.querySelectorAll('.v3-other-at')].filter((a) => !a.classList.contains('v3-hidden'));
  const [a, b] = ats, m = /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(a.style.transform);
  b.style.transform = `translate(${m[1]}px, ${+m[2] + 30}px)`;
  const box = (e) => { const r = e.firstElementChild.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  return {first: a.firstElementChild.dataset.other, second: b.firstElementChild.dataset.other, a: box(a), b: box(b)}; }"""
POINT_CLICK = """() => { const r = document.querySelector('.v3-handle').getBoundingClientRect(),
  c = document.querySelector('.v3-canvas'), at = {clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
  pointerId: 7, button: 0, bubbles: true, isPrimary: true};
  c.dispatchEvent(new PointerEvent('pointerdown', at)); c.dispatchEvent(new PointerEvent('pointerup', at)); }"""


def _size(box):
    return box[2] - box[0], box[3] - box[1]


def _open(browser, url, context):
    ctx = browser.new_context(**context)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)[:300]))
    page.goto(url)
    page.wait_for_function(READY, timeout=WAIT * 4)
    return page


def _tapped(page, x, y):
    """The classes of the control a finger's tap at (x, y) reaches (CATCH installed)."""
    page.evaluate("() => { window.CLICKS = []; }")
    _tap(page, x, y)
    page.wait_for_function("() => window.CLICKS.length > 0", timeout=WAIT)
    return page.evaluate("() => window.CLICKS[0]")


def test_view3d_touch_targets(clip_data, tmp_path, monkeypatch):
    from playwright.sync_api import sync_playwright
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    page_path = _script_page(data, "view3dtouch", "")
    run_json = data / "runs" / meta["id"] / "run.json"  # data credits for the run (as test_view3d_credits_and_pill)
    saved = run_json.read_text("utf-8")
    run_json.write_text(json.dumps({**json.loads(saved), "attribution": [
        {"data": "Test model", "attribution": "Test survey", "licence": "CC BY 4.0", "url": "https://example.org/"}]}),
        encoding="utf-8")
    try:
        _touch_targets(data, meta, keys, page_path)
    finally:
        run_json.write_text(saved, encoding="utf-8")


def _touch_targets(data, meta, keys, page_path):
    from playwright.sync_api import sync_playwright
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            phone = {k: v for k, v in p.devices["Pixel 7"].items() if k != "default_browser_type"}
            base = f"http://127.0.0.1:{port}/{page_path}"
            # the phone level: the tools, the views' buttons and the speed 44 px each way; the data credits' button
            # keeps its drawn height and takes a tap 8 px above its box
            page = _open(browser, f"{base}#run={meta['id']}&line={quote(keys[0], safe='')}", phone)
            assert page.evaluate("() => document.getElementById('view3d').classList.contains('v3-phone')")
            for sel in (".v3-tool", ".v3-views button", ".v3-speed"):
                boxes = page.evaluate(BOXES, sel)
                assert boxes and all(min(_size(b["own"])) >= 43.5 for b in boxes), (sel, boxes)
            toggle = page.evaluate(BOXES, ".v3-credits .u-credits-toggle")[0]
            assert _size(toggle["own"])[1] < 40 and _size(toggle["target"])[1] >= 43.5, toggle
            page.evaluate(CATCH)
            own = toggle["own"]
            assert "u-credits-toggle" in _tapped(page, (own[0] + own[2]) / 2, own[1] - 8)
            assert page.errors == [], page.errors
            page.context.close()
            # the full level with two lines of the address: the handles (22 px drawn) and the labels (28 px high)
            # with 44 px targets; a tap 8 px below a label reaches it; the lines from a point: the dots (18 px drawn)
            # with 44 px targets, a tap 16 px beside a dot's centre reaches a dot; the list's heads and rows 44 px
            url = (f"{base}?level=full#run={meta['id']}&line={quote(keys[0], safe='')}"
                   f"&also={quote(';'.join(keys[1:3]), safe='')}")
            page = _open(browser, url, phone)
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
            handles, labels = page.evaluate(BOXES, ".v3-handle"), page.evaluate(BOXES, ".v3-other")
            assert len(handles) == 2 and all(_size(h["own"]) == (22, 22) for h in handles), handles
            assert all(min(_size(h["target"])) >= 43.5 for h in handles), handles
            assert labels and all(_size(b["own"])[1] < 40 and min(_size(b["target"])) >= 43.5 for b in labels), labels
            page.evaluate(CATCH)
            own = labels[0]["own"]
            assert "v3-other" in _tapped(page, (own[0] + own[2]) / 2, own[3] + 8)
            assert page.errors == [], page.errors
            page.context.close()
            # the lines from a point, on a page of its own (test_view3d_layout._fan: the press at anchor 1 finds lines
            # or none by the stage's height, so a height that gives dots is taken)
            from test_view3d_layout import _fan
            page = _fan(browser, p, f"{base}?level=full#run={meta['id']}&line={quote(keys[0], safe='')}")
            dots = page.evaluate(BOXES, ".v3-opt-dot")
            assert dots and all(_size(d["own"]) == (18, 18) and min(_size(d["target"])) >= 43.5 for d in dots), dots
            for sel in (".v3-opt-sort", ".v3-opt-row td"):
                boxes = page.evaluate(BOXES, sel)
                assert boxes and all(_size(b["own"])[1] >= 43.5 for b in boxes), (sel, boxes)
            own = dots[0]["own"]
            page.evaluate(CATCH)
            assert "v3-opt-dot" in _tapped(page, (own[0] + own[2]) / 2 + 16, (own[1] + own[3]) / 2)
            # the synthetic press on the terrain (POINT_CLICK) has no pointer for the page's capture: its error only
            assert [e for e in page.errors if "setPointerCapture" not in e] == [], page.errors
            page.context.close()
            # a fresh page (the line made active changes what the lines from a point ask for):
            page = _open(browser, url, phone)
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 1", timeout=WAIT)
            # two labels 30 px apart, the later one's target over the earlier one's drawn box: a finger's tap inside
            # the earlier box, nearer to its centre (12 px) than to the later one's (18 px), reaches the later label's
            # element but makes the earlier label's line the active one (screen.ts pressedMark)
            pair = page.evaluate(PAIR)
            x, y = (pair["a"][0] + pair["a"][2]) / 2, pair["a"][3] - 2
            hit = page.evaluate("([x, y]) => document.elementFromPoint(x, y).closest('.v3-other')?.dataset.other", [x, y])
            assert hit == pair["second"], (pair, hit)  # the case: the later target lies over the earlier box
            _tap(page, x, y)
            page.wait_for_function("(key) => !document.querySelector(`[data-other=\"${key}\"]`)", arg=pair["first"],
                                   timeout=WAIT)
            assert page.evaluate("(key) => !!document.querySelector(`[data-other=\"${key}\"]`)", pair["second"])
            assert page.errors == [], page.errors
            page.context.close()
            # a desktop: the marks' targets 24 px, the labels as drawn (28 px)
            page = _open(browser, url, {"viewport": {"width": 1200, "height": 800}})
            page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 0", timeout=WAIT)
            handles, labels = page.evaluate(BOXES, ".v3-handle"), page.evaluate(BOXES, ".v3-other")
            assert all(_size(h["target"]) == (24, 24) for h in handles), handles
            assert labels and all(b["target"] == b["own"] and _size(b["own"])[1] >= 28 for b in labels), labels
            page.context.close()
        finally:
            browser.close()


# Two shown labels side by side (the code review's case): the first as wide as a favourite's with a longer text, the
# second 4 px right of it on the same row; the press 2 px inside the first's right end, which is nearer to the
# second's centre (through the CSSOM as screen.ts place: no frame is drawn meanwhile, so it stays)
SIDE = r"""() => { const ats = [...document.querySelectorAll('.v3-other-at')].filter((a) => !a.classList.contains('v3-hidden'));
  const [a, b] = ats, A = a.firstElementChild, B = b.firstElementChild;
  A.querySelector('.v3-other-text').textContent = '312 m (saved)';
  const m = /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(a.style.transform);
  const ra = A.getBoundingClientRect(), rb0 = B.getBoundingClientRect();
  b.style.transform = `translate(${+m[1] + ra.width / 2 + 4 + rb0.width / 2}px, ${m[2]}px)`;
  const rb = B.getBoundingClientRect(), x = ra.right - 2, y = ra.top + ra.height / 2;
  return {first: A.dataset.other, second: B.dataset.other, x, y,
          hit: document.elementFromPoint(x, y).closest('.v3-other')?.dataset.other,
          dA: Math.hypot(ra.left + ra.width / 2 - x, ra.top + ra.height / 2 - y),
          dB: Math.hypot(rb.left + rb.width / 2 - x, rb.top + rb.height / 2 - y)}; }"""
# Two fan dots, the second set 30 px under the first (their 44 px targets overlap, their 18 px boxes do not), for a
# first dot whose place is free: the press 12 px under the first's centre lies on no drawn box, in both targets, on
# the second dot's element (drawn later) and nearer to the first's centre (12 px against 18 px)
DOTS = r"""() => { const dots = [...document.querySelectorAll('.v3-opt-dot')].filter((d) => !d.classList.contains('v3-hidden'));
  const length = (d) => d.getAttribute('aria-label').replace(/^\D+/, '');
  for (const a of dots) { const b = dots.find((d) => d !== a && dots.indexOf(d) > dots.indexOf(a)); if (!b) continue;
    const kept = b.style.transform, m = /translate\(([-\d.]+)px, ([-\d.]+)px\)/.exec(a.style.transform);
    b.style.transform = `translate(${m[1]}px, ${+m[2] + 30}px)`;
    for (const d of [a, b]) { d.style.setProperty('--v3-tx', '0px'); d.style.setProperty('--v3-ty', '0px'); }
    const r = a.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2 + 12;
    if (document.elementFromPoint(x, y) === b) return {x, y, first: length(a), second: length(b)};
    b.style.transform = kept; }
  return null; }"""


def test_view3d_press_on_a_drawn_mark(clip_data, tmp_path, monkeypatch):
    """A press on a mark's own drawn box goes to that mark, whatever centre is nearer (screen.ts pressedMark; the
    code review's F1): of two labels side by side, the first much wider, a press 2 px inside the first's right end
    is nearer to the second's centre and makes the first label's line the active one, with a mouse (no enlarged
    targets: the click is on the first label's element) and with a finger (the second's 44 px target lies over the
    first's end and takes the tap). Before, the nearer centre alone decided and the second label's line came up."""
    from playwright.sync_api import sync_playwright
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    page_path = _script_page(data, "view3dpress", "")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            phone = {k: v for k, v in p.devices["Pixel 7"].items() if k != "default_browser_type"}
            url = (f"http://127.0.0.1:{port}/{page_path}?level=full#run={meta['id']}&line={quote(keys[0], safe='')}"
                   f"&also={quote(';'.join(keys[1:3]), safe='')}")
            for name, context in (("mouse", {"viewport": {"width": 1200, "height": 800}}), ("finger", phone)):
                page = _open(browser, url, context)
                page.wait_for_function("() => Number(document.getElementById('view3d').dataset.others) > 1", timeout=WAIT)
                side = page.evaluate(SIDE)
                assert side["dB"] < side["dA"], (name, side)  # the case: the other label's centre is nearer
                assert side["hit"] == (side["first"] if name == "mouse" else side["second"]), (name, side)
                if name == "mouse":
                    page.mouse.click(side["x"], side["y"])
                else:
                    _tap(page, side["x"], side["y"])
                page.wait_for_function("([a, b]) => !document.querySelector(`[data-other=\"${a}\"]`) || "
                                       "!document.querySelector(`[data-other=\"${b}\"]`)",
                                       arg=[side["first"], side["second"]], timeout=WAIT)
                left = page.evaluate("([a, b]) => [!!document.querySelector(`[data-other=\"${a}\"]`), "
                                     "!!document.querySelector(`[data-other=\"${b}\"]`)]", [side["first"], side["second"]])
                assert left == [False, True], (name, side, left)  # the first label's line is the active one
                assert page.errors == [], page.errors
                page.context.close()
        finally:
            browser.close()


def test_view3d_dots_nearer_centre(clip_data, tmp_path, monkeypatch):
    """Where only the fan dots' invisible targets overlap (a press on no dot's drawn box), the dot whose centre is
    nearer takes the press, not the one drawn later (fan.ts through screen.ts pressedMark; the code review's F4: no
    test held it for the dots): a finger's tap 12 px under one dot and 18 px above the next reaches the later
    dot's element and chooses the earlier dot's line (the readout shows its length)."""
    from playwright.sync_api import sync_playwright
    from test_view3d_layout import _fan
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    page_path = _script_page(data, "view3ddotpair", "")
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            page = _fan(browser, p, f"http://127.0.0.1:{port}/{page_path}?level=full#run={meta['id']}"
                                    f"&line={quote(keys[0], safe='')}")
            pair = page.evaluate(DOTS)
            assert pair and pair["first"] != pair["second"], pair
            _tap(page, pair["x"], pair["y"])
            page.wait_for_function("() => document.getElementById('view3d').dataset.point === ''", timeout=WAIT)
            readout = page.evaluate("() => document.querySelector('.v3-readout').innerText")
            assert pair["first"].replace(" m", "") in readout and pair["second"].replace(" m", "") not in readout, (pair, readout)
            page.context.close()
        finally:
            browser.close()


def test_view3d_handle_drag_keeps_its_offset(clip_data, tmp_path, monkeypatch):
    """An anchor's handle pressed on the rim of its 44 px target (18 px beside or above its centre) and moved by
    1 px goes where the same move from a press at its centre takes it: the press's offset is kept (screen.ts
    draggable `fromCentre`; the code review's F2: before, the anchor went to the terrain under the pointer and the
    rim press put the handle 16.7 px further, the offset on top). What a 1 px move from the centre itself does to
    the handle is not this test's (docs/known-bugs.md: the anchor goes to the terrain under the pointer)."""
    from playwright.sync_api import sync_playwright
    data, meta = clip_data
    for key, value in _offline_env().items():
        monkeypatch.setenv(key, value)
    keys = [_key_of(r) for r in _lines_of(data, meta["id"])]
    page_path = _script_page(data, "view3ddrag", "")
    centre = r"""(k) => { const r = document.querySelectorAll('.v3-handle')[k].getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2]; }"""
    frames = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"
    with _server(data, start_scheduler=True) as port, sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            phone = {k: v for k, v in p.devices["Pixel 7"].items() if k != "default_browser_type"}
            url = f"http://127.0.0.1:{port}/{page_path}?level=full#run={meta['id']}&line={quote(keys[0], safe='')}"
            for anchor in (0, 1):
                ends = {}
                for name, dx, dy in (("centre", 0, 0), ("right rim", 18, 0), ("upper rim", 0, -18)):
                    page = _open(browser, url, phone)
                    start = page.evaluate(centre, anchor)
                    x, y = start[0] + dx, start[1] + dy
                    hit = page.evaluate("([x, y]) => document.elementFromPoint(x, y).className", [x, y])
                    assert "v3-handle" in hit, (name, hit)  # the press is on the handle's target
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.move(x + 1, y, steps=1)
                    page.evaluate(frames)
                    ends[name] = page.evaluate(centre, anchor)
                    page.mouse.up()
                    assert page.errors == [], page.errors
                    page.context.close()
                for name in ("right rim", "upper rim"):
                    apart = ((ends[name][0] - ends["centre"][0]) ** 2 + (ends[name][1] - ends["centre"][1]) ** 2) ** 0.5
                    assert apart <= 1.5, (anchor, name, ends)
        finally:
            browser.close()
