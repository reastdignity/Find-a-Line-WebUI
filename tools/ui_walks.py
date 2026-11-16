"""
Task walks through the app, counted (the UX target "ease of use", docs/roadmap.md): each walk is a defined task a
person does in the real app (the public site of tools/ui_shots.py's serve(), its scratch data folder, its users and
device profiles), driven with Playwright, and counted step by step: what the task asks of a person.

Before each action (a tap or click, typed text, a key) the runner measures the surface the person is looking at (the
viewport; with a modal dialog or a popover open only what is in it):
- the visible, enabled controls (links, buttons, fields, options, ...): their number, and whether it is more than 4
  (a "decision point"); a Leaflet map counts as one control (its panes' markers and lines are part of it, its zoom
  and layer buttons and attribution links count each);
- the words visible (text nodes and fields' values or placeholders; a word holds a letter or a digit, so "·" or "⋯"
  is none; the map's panes hold none);
then it does the action and times the seconds until the step's expected state (indicative only), and whether the
page showed anything within 300 ms (a busy mark, a progress bar or changed visible text) when it took longer. A
step whose element or expected state never comes ends the walk as a dead end, named, never worked around. "Visible"
means inside the viewport and every clipping ancestor, and hit by elementFromPoint (not covered by a sheet, a modal or
a panel); MEASURE holds the rules.

Per walk: screens (the walk's marks "a new screen"), pointer actions, keystrokes, changes between pointer and
keyboard (desktop), decision points and the largest number of controls seen, the words before the first action and
summed over the screens, the waits, dead ends. A screenshot per step into --out/<walk>/, walks.json and walks.md.

No walk starts a search: the site has a worker and a started job would download elevation data. A walk ends at the
enabled "Start" (step kind "unmade": counted, never tapped), the page's job requests are refused (and fail the walk),
and the data folder must have no job at the end.

    uv sync --group ui
    uv run playwright install chromium webkit
    uv run tools/ui_walks.py --out <folder> [--only R1,F2]
    uv run tools/ui_walks.py compare <folder1>/walks.json <folder2>/walks.json
    uv run tools/ui_walks.py probe --out <folder> --user admin --device desktop --start "/?ui=c#run={run} | <selector>"

"compare": what differs in the counts of two runs (each run of the tool makes its own data folder). "probe": the
surface's controls and words at an address (after clicks on the selectors given after " | "), for writing walks.

The walks (WALKS) are proposals of the UX plan, not confirmed tasks: data, easy to change. Each has its user (a key of
serve()'s cookies or "visitor"), its device (a key of ui_shots.DEVICES), what the browser remembers (MEMORIES), its
start address ("{run}", "{line}" filled), its steps (the functions tap, type_, key, unmade, swipe, sign_in, wait,
screen, note), and optionally "needs" (what the fixtures lack for the whole walk, shown with a dead end) or "skip"
(not walked, and why). A swipe is one pointer action (made as scrolling the element into view); a tap on an element
outside the viewport is flagged in walks.md (the walk then lacks a swipe). Seconds are indicative: the machine's load
and Playwright's polling are in them.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

import ui_shots  # noqa: E402

TIMEOUT_MS = 20000  # how long an element or an expected state may take before the step is a dead end
SETTLE_MS = 5000  # how long a measurement waits for the surface to stop changing
FEEDBACK_MS = 300  # a wait longer than this needs something on the screen within it
DECISION = 4  # a decision point: more visible enabled controls than this (the plan's "more than 4 visible options")
KINDS = ("tap", "type", "key", "unmade", "swipe", "sign_in", "wait", "screen", "note")
ACTIONS = ("tap", "type", "key", "unmade", "swipe")  # measured before, counted
POINTER = ("tap", "unmade", "swipe")
# What the browser remembers at the start: "first": just signed in (the beta notice and the intros not yet seen);
# "new": the intros not yet seen (the notice was seen at the sign-in); "returning": all put away, as ui_shots does
MEMORIES = ("first", "new", "returning")
VISITOR = "visitor"
# The page's requests that would start work in the worker: refused, and the walk fails
FORBIDDEN = [("POST", re.compile(r"/api/jobs(/[^/]+/again)?/?$")), ("POST", re.compile(r"/api/osm/?$"))]
WELCOME = "__Host-findaline-welcome"  # web.WELCOME_COOKIE: the beta notice after a sign-in
SESSION = "__Host-findaline"  # accounts.SESSION_COOKIE


# The steps: dicts made by these functions. `target` is a Playwright selector (role=button[name='Start'], text=...,
# CSS, chained with >>); the first visible match is used. `expect` is a JavaScript expression that becomes true when
# the action has done what the person waits for; `see` says what the person sees next (for the report).
def tap(target, expect=None, see=""):
    """A tap (phones) or a click (desktop) on the element."""
    return {"kind": "tap", "target": target, "expect": expect, "see": see}


def type_(target, text, expect=None, see=""):
    """Characters typed into the element (it has the focus from a tap before; the text is added where the caret is)."""
    return {"kind": "type", "target": target, "text": text, "expect": expect, "see": see}


def key(name, expect=None, see=""):
    """One key (Playwright's names: Enter, Escape, Tab, ArrowDown, Control+A: a chord is one keystroke)."""
    return {"kind": "key", "key": name, "expect": expect, "see": see}


def unmade(target, see=""):
    """A tap counted and never made (the search's Start: no search is started; a provider's sign-in button): the
    element must be visible and enabled."""
    return {"kind": "unmade", "target": target, "see": see}


def swipe(target, expect=None, see=""):
    """A swipe that brings the element into view (one pointer action, made as scrolling it into view)."""
    return {"kind": "swipe", "target": target, "expect": expect, "see": see}


def sign_in(user, address, see=""):
    """The session of another user from here on, at an address (signing in through a provider cannot be walked: the
    providers are dummies); counts nothing. With the walk's memory "first" the beta notice's cookie comes too."""
    return {"kind": "sign_in", "user": user, "address": address, "see": see}


def wait(expect, see=""):
    """A wait for a state (counts nothing; a dead end when it never comes)."""
    return {"kind": "wait", "expect": expect, "see": see}


def screen(name):
    """A mark: a new screen (a route, a dialog, a sheet state, a popover) the person must take in; measured."""
    return {"kind": "screen", "name": name}


def note(text):
    """A remark for the report (counts nothing)."""
    return {"kind": "note", "text": text}


def at_map(lat, lon, expect=None, see=""):
    """A tap on the place map at a place: counted as one tap, made as Leaflet's click there (finding the place by
    panning and zooming is not counted: say so in a note)."""
    return {"kind": "tap", "target": ".leaflet-container", "map": [lat, lon], "expect": expect, "see": see}


READY = "document.querySelector('.s-bar')?.dataset.estimate === 'ready'"  # the search's bar: source and grid known
RESULT = "!!document.querySelector('.r-rows [role=option]')"  # a result's list of lines shown
LINE = "/[#&]line=/.test(location.hash)"  # a line selected
PROFILE = "!!document.querySelector('.r-dock .fal-profile-chart')"  # the selected line's profile drawn
HOME = "!!document.querySelector('.c-cards .c-card')"
POPOVER = "!!document.querySelector('.r-pop')"
NO_POPOVER = "!document.querySelector('.r-pop')"
DIALOG = "!!document.querySelector('dialog[open]')"
NO_DIALOG = "!document.querySelector('dialog[open]')"
FORM = "!!document.querySelector('.s-panel .s-tabs')"  # the search form


def chip(text: str) -> str:
    """A filter chip of the result's bar shows this text."""
    return f"[...document.querySelectorAll('.r-filters button')].some((b) => b.textContent.includes({text!r}))"


CARD = ".c-card[data-run='{run}']"  # the run's card on Home
OPEN_RUN = [tap(CARD + " .c-card-open", RESULT, "the result: the lines' list, the map, the details' column"),
            screen("the result")]
THE_PLACE = (50.1559508, 19.7562722)  # the clip's place (ui_shots.POINT)

# The walks (proposals of the UX plan, "to confirm"): R* the experienced rigger at a desk, F* a first-timer on a phone.
# The order is the order of the runs: R4 last, since it saves a favourite and makes a new share link (Home's
# "Favourite lines" would change the words of the walks after it).
WALKS = {
    "R1": {
        "title": "Edit a search and run it again", "user": "admin", "device": "desktop", "memory": "returning",
        "start": "/?ui=c",
        "needs": "a finished job of the run: Edit & run again needs the job's request (ui_shots.serve() adds the "
                 "clip's run without a job, so neither the card's menu nor the result's header offers it)",
        "steps": [
            wait(HOME), screen("Home"),
            tap(CARD + " .c-card-menu", POPOVER, "the card's menu"),
            screen("the card's menu"),
            tap("role=menuitem[name='Edit & run again']", FORM, "the search form with the run's settings"),
            screen("Edit & run again"),
            tap("role=spinbutton[name='Search radius']", None, "the radius field has the focus"),
            key("Control+A"),
            type_("role=spinbutton[name='Search radius']", "300"),
            key("Tab", READY, "the bar's estimate for the new radius"),
            unmade("role=button[name='Start search']", "the search would start"),
        ]},
    "R2": {
        "title": "From a finished search to the best lines of a wanted length and height", "user": "admin",
        "device": "desktop", "memory": "returning", "start": "/?ui=c",
        "steps": [
            wait(HOME), screen("Home"),
            *OPEN_RUN,
            tap(".r-filters >> role=button[name='Length']", "!!document.querySelector('.r-editor')",
                "the length filter's editor under the chips"),
            screen("the length filter"),
            tap("role=spinbutton[name='Length from']", None, "the field has the focus (empty, 30 as its placeholder)"),
            type_("role=spinbutton[name='Length from']", "100"),
            key("Enter", chip("Length ≥ 100"), "the chip reads Length ≥ 100 m, the list shorter"),
            tap(".r-filters >> role=button[name='Height']", "!!document.querySelector('.r-editor')",
                "the height filter's editor"),
            screen("the height filter"),
            tap("role=spinbutton[name='Height above the ground at least']", None, "the field has the focus"),
            type_("role=spinbutton[name='Height above the ground at least']", "20"),
            key("Enter", chip("Height ≥ 20"), "the chip reads Height ≥ 20 m"),
            tap(".r-rows [role=option]", f"{LINE} && {PROFILE}", "the line's details and its profile over the map"),
            screen("the line: details and profile"),
        ]},
    "R3": {
        "title": "Compare: another run on the same map, and two lines", "user": "admin", "device": "desktop",
        "memory": "returning", "start": "/?ui=c",
        "needs": "a second run of the user with lines in the same area (ui_shots.serve() has one run): Compare's "
                 "list is empty",
        "steps": [
            wait(HOME), screen("Home"),
            *OPEN_RUN,
            tap("role=button[name='Compare']", POPOVER, "Compare's popover: the other runs to show on the map"),
            screen("Compare"),
            note("with one run Compare says 'No other runs with lines.': adding a run is not walked (fixture)"),
            key("Escape", NO_POPOVER, "the popover closed"),
            note("two lines: the UI has no side-by-side comparison; the nearest is one line's details, then "
                 "another's"),
            tap(".r-rows [role=option] >> nth=0", LINE, "the first line's details and profile"),
            screen("line 1"),
            tap(".r-rows [role=option] >> nth=1", "!location.hash.endsWith('{line}')",
                "the second line's details replace the first's"),
            screen("line 2"),
        ]},
    "F1": {
        "title": "First search: from the sign-in page to Start", "user": VISITOR, "device": "iphone",
        "memory": "first", "start": "/",
        "steps": [
            wait("document.readyState === 'complete'"),
            screen("the sign-in page"),
            unmade("role=link[name='Sign in with GitHub']", "the provider's pages (not walked: dummies)"),
            note("signing in at the provider is not walked; a new account waits for an administrator's approval"),
            sign_in("walker", "/", "the app as a newly approved user (no saved rig), just signed in"),
            wait(DIALOG), screen("the beta notice"),
            tap("dialog[open] >> role=button[name='Understood']", NO_DIALOG, "Home"),
            screen("Home"),
            tap("role=link[name='New search']", DIALOG, "the search, and over it its intro"),
            screen("How a search works"),
            tap("dialog[open] >> role=button[name='Got it']", f"{NO_DIALOG} && {FORM}",
                "the search: the map, the form under it"),
            screen("New search"),
            note("the place: a tap on the map where the clip lies (the map opens near it); finding one's own place "
                 "(panning, zooming or Go to a place) is not counted"),
            at_map(*THE_PLACE, READY, "the centre set, the bar's estimate"),
            screen("the place set"),
            unmade("role=button[name='Start search']", "the search would start"),
        ]},
    "F2": {
        "title": "Understanding the first result", "user": "admin", "device": "iphone", "memory": "new",
        "start": "/?ui=c",
        "steps": [
            note("as the administrator: the only user with a finished run in ui_shots.serve()"),
            wait(HOME), screen("Home"),
            tap(CARD + " .c-card-open", None, "the result loads"),
            wait(f"{RESULT} || {DIALOG}"),
            screen("the result's first view"),
            tap("dialog[open] >> role=button[name='Got it']", NO_DIALOG, "the result: the map and the list"),
            screen("the result"),
            tap(".r-rows [role=option]", LINE, "the line's details in the sheet"),
            screen("the line's details"),
            swipe(".r-dock .fal-profile-chart", None, "the profile further down the sheet"),
            screen("the line's profile"),
        ]},
    "F3": {
        "title": "Recovering from \"nothing found\"", "user": "walker", "device": "iphone", "memory": "new",
        "start": "/?ui=c",
        "skip": "not measurable with today's fixtures: ui_shots.serve() has no failed job. It would need a job of "
                "the user with the status failed and the error of a search that found nothing (code no_lines or "
                "no_steep_terrain, no run), so Home shows its card",
        "steps": [
            wait(HOME), screen("Home with the failed search"),
            tap(".c-card[data-status=failed] .c-card-menu", POPOVER, "the card's menu"),
        ]},
    "R4": {
        "title": "Save, sort and share", "user": "admin", "device": "desktop", "memory": "returning",
        "start": "/?ui=c",
        "steps": [
            wait(HOME), screen("Home"),
            *OPEN_RUN,
            note("the list's star saves to the top level at once; a folder is chosen in the line's details"),
            tap(".r-rows [role=option]", LINE, "the line's details"),
            screen("the line's details"),
            tap(".r-details >> role=button[name='Add to favourites']", POPOVER, "Save to a folder"),
            screen("Save to a folder"),
            tap(".r-pop >> role=button[name='New folder']", "!!document.querySelector('.r-newfolder input')",
                "the folder's name field, with the focus"),
            type_(".r-newfolder input", "Tatras"),
            key("Enter", "!!document.querySelector('.r-details .r-fav.r-on')", "the line is a favourite, in Tatras"),
            tap(".r-head >> role=button[name='Length']",
                "/^Length/.test(document.querySelector('.r-head button[aria-sort]')?.textContent || '')",
                "the list sorted by length"),
            tap("role=button[name='Share']", POPOVER, "Share's popover"),
            screen("Share"),
            tap(".r-pop >> role=button[name=/^(Make a link|New link)$/]",
                "!!document.querySelector('.r-pop input')?.value", "the link, shown once"),
            screen("the link"),
        ]},
}


def walk_errors(walks: dict, users, devices) -> list:
    """What is wrong with the walks' data (empty: nothing): known users, devices, memories, step kinds and fields."""
    errors = []
    need = {"tap": ("target",), "type": ("target", "text"), "key": ("key",), "unmade": ("target",),
            "swipe": ("target",), "sign_in": ("user", "address"), "wait": ("expect",), "screen": ("name",),
            "note": ("text",)}
    known = set(users) | {VISITOR}
    for wid, w in walks.items():
        for field in ("title", "user", "device", "memory", "start", "steps"):
            if field not in w:
                errors.append(f"{wid}: no {field}")
        if w.get("user") not in known:
            errors.append(f"{wid}: unknown user {w.get('user')!r}")
        if w.get("device") not in devices:
            errors.append(f"{wid}: unknown device {w.get('device')!r}")
        if w.get("memory") not in MEMORIES:
            errors.append(f"{wid}: unknown memory {w.get('memory')!r}")
        if not str(w.get("start", "")).startswith("/"):
            errors.append(f"{wid}: the start is not a path")
        for i, s in enumerate(w.get("steps", [])):
            if not isinstance(s, dict) or s.get("kind") not in KINDS:
                errors.append(f"{wid} step {i + 1}: unknown kind {s.get('kind') if isinstance(s, dict) else s!r}")
                continue
            errors += [f"{wid} step {i + 1}: {s['kind']} without {f}" for f in need[s["kind"]] if not s.get(f)]
            if s["kind"] == "sign_in" and s.get("user") not in known - {VISITOR}:
                errors.append(f"{wid} step {i + 1}: unknown user {s.get('user')!r}")
        if not w.get("skip") and not any(s.get("kind") in ACTIONS for s in w.get("steps", []) if isinstance(s, dict)):
            errors.append(f"{wid}: no action")
    return errors


# The measurement of the surface (a function of the page; no eval: the app's CSP forbids it). Returns the controls
# (each: its kind and name, enabled or not) and the words visible, and which surface it measured.
MEASURE = r"""() => {
  const SCOPES = ['dialog:modal', '[aria-modal=true]', '.r-pop', ':popover-open'];
  const CONTROLS = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], ' +
    '[role=menuitem], [role=menuitemradio], [role=menuitemcheckbox], [role=tab], [role=radio], [role=checkbox], ' +
    '[role=switch], [role=option], [role=slider], [role=combobox], [contenteditable=true], ' +
    '[tabindex]:not([tabindex^="-"])';
  const MAP = '.leaflet-container', PANES = '.leaflet-map-pane';
  const W = innerWidth, H = innerHeight;
  const matches = (e, sel) => { try { return e.matches(sel); } catch (x) { return false; } };
  const shown = (e) => e.checkVisibility ? e.checkVisibility({visibilityProperty: true, opacityProperty: true})
    : (() => { const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0'; })();
  // A rectangle clipped by the viewport and by every ancestor that clips its overflow; null when nothing is left
  const clip = (r, from) => {
    let x0 = Math.max(r.left, 0), y0 = Math.max(r.top, 0), x1 = Math.min(r.right, W), y1 = Math.min(r.bottom, H);
    for (let a = from; a && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const b = a.getBoundingClientRect();
        x0 = Math.max(x0, b.left); y0 = Math.max(y0, b.top); x1 = Math.min(x1, b.right); y1 = Math.min(y1, b.bottom);
      }
      if (s.position === 'fixed') break;
    }
    return x1 - x0 >= 1 && y1 - y0 >= 1 ? [x0, y0, x1, y1] : null;
  };
  const hits = (e, r) => {
    for (const [fx, fy] of [[.5, .5], [.2, .5], [.8, .5], [.5, .2], [.5, .8]]) {
      const h = document.elementFromPoint(r[0] + (r[2] - r[0]) * fx, r[1] + (r[3] - r[1]) * fy);
      if (h && (h === e || e.contains(h) || h.contains(e))) return true;
    }
    return false;
  };
  const seen = (e) => {
    if (!shown(e)) return false;
    const r = clip(e.getBoundingClientRect(), e.parentElement);
    return !!r && hits(e, r);
  };
  let scope = null, scopeName = 'viewport';
  for (const sel of SCOPES) {
    const open = [...document.querySelectorAll(sel)].filter((e) => { try { return seen(e) || shown(e); } catch (x) { return false; } });
    if (open.length) { scope = open[open.length - 1]; scopeName = sel; break; }
  }
  const root = scope || document.body;
  const inPanes = (e) => !!e.closest(PANES);
  const nameOf = (e) => (e.getAttribute('aria-label') || e.textContent || e.value || e.placeholder || e.title || '')
    .replace(/\s+/g, ' ').trim().slice(0, 60);
  const controls = [], counted = new Set();
  const add = (e, kind) => {
    if (counted.has(e)) return;
    counted.add(e);
    const disabled = e.disabled || e.getAttribute('aria-disabled') === 'true' || !!e.closest('[inert], fieldset:disabled');
    controls.push({kind, name: kind === 'map' ? 'the map' : nameOf(e), enabled: !disabled});
  };
  for (const m of root.querySelectorAll(MAP)) {
    if (!m.closest(CONTROLS) && seen(m)) add(m, 'map');
  }
  for (const e of root.querySelectorAll(CONTROLS)) {
    if (e === scope || inPanes(e)) continue;
    if (seen(e)) { add(e, e.getAttribute('role') || e.tagName.toLowerCase()); continue; }
    // a field hidden for its label's look (a styled radio or checkbox): the label is what the person sees
    const label = e.labels && e.labels[0];
    if (label && !counted.has(label) && seen(label)) add(label, (e.getAttribute('type') || 'input') + ' label');
  }
  // The words: each word of a text node whose box is visible and hit; fields' values and placeholders
  const WORD = /[\p{L}\p{N}]/u;
  const words = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: (n) => {
    const p = n.parentElement;
    if (!p || !/\S/.test(n.data) || p.closest('script, style, noscript, template, option, ' + PANES)) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  const range = document.createRange();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const p = n.parentElement;
    if (!shown(p)) continue;
    const re = /\S+/g;
    let m;
    while ((m = re.exec(n.data))) {
      if (!WORD.test(m[0])) continue;
      range.setStart(n, m.index); range.setEnd(n, m.index + m[0].length);
      let b = range.getBoundingClientRect();
      if (b.width < 1 && b.height < 1) b = p.getBoundingClientRect();
      const r = clip(b, p);
      if (r && hits(p, r)) words.push(m[0]);
    }
  }
  for (const e of root.querySelectorAll('input, textarea, select')) {
    if (inPanes(e) || !seen(e)) continue;
    const t = e.tagName === 'SELECT' ? (e.selectedOptions[0]?.textContent || '')
      : ['checkbox', 'radio', 'range', 'color', 'file'].includes(e.type) ? '' : (e.value || e.placeholder || '');
    for (const w of t.split(/\s+/)) if (WORD.test(w)) words.push(w);
  }
  // In a dialog or popover also every word of it, those scrolled out of its view too (what it gives to read)
  let inScope = null;
  if (scope) {
    inScope = 0;
    const all = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    for (let n = all.nextNode(); n; n = all.nextNode()) {
      const p = n.parentElement;
      if (!p || !shown(p) || p.closest('script, style, option')) continue;
      inScope += n.data.split(/\s+/).filter((w) => WORD.test(w)).length;
    }
  }
  const enabled = controls.filter((c) => c.enabled);
  return {scope: scopeName, controls: enabled.length, disabled: controls.length - enabled.length,
          words: words.length, words_in_scope: inScope,
          list: controls.map((c) => `${c.enabled ? '' : '(disabled) '}${c.kind}: ${c.name}`), text: words.join(' ')};
}"""

# A watcher installed just before an action: did a new busy mark or progress bar come, or the visible text change,
# within FEEDBACK_MS? (the text compared by its length and a cheap hash of document.body.innerText)
FEEDBACK = r"""(ms) => {
  const sig = () => { const t = document.body ? document.body.innerText : ''; let h = 0;
                      for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0; return t.length + ':' + h; };
  const marks = () => [...document.querySelectorAll('[aria-busy=true], progress, [role=progressbar], .u-spin, .u-spinner')];
  const before = sig(), had = new Set(marks());  // a busy mark shown before the action is no feedback of it
  window.__walkFeedback = null;
  setTimeout(() => { window.__walkFeedback = marks().some((e) => !had.has(e)) ? 'busy'
                                             : sig() !== before ? 'text' : 'none'; }, ms);
}"""

# The measurement repeated until the surface stops changing (three equal readings 100 ms apart), at most `ms`
SETTLED = r"""async (ms) => {
  const measure = """ + MEASURE + r""";
  const key = (m) => m.scope + '|' + m.controls + '|' + m.disabled + '|' + m.words + '|' + m.list.join(';');
  const end = performance.now() + ms;
  let m = measure(), same = 0;
  while (same < 2 && performance.now() < end) {
    await new Promise((done) => setTimeout(done, 100));
    const next = measure();
    same = key(next) === key(m) ? same + 1 : 0;
    m = next;
  }
  m.settled = same >= 2;
  return m;
}"""

IN_VIEW = """(e) => { const r = e.getBoundingClientRect();
  return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth; }"""

MAP_CLICK = """([lat, lng]) => { const p = window.FINDALINE_PLACE; if (!p) return false;
  p.map.fire('click', {latlng: {lat, lng}}); return true; }"""


TOKEN = re.compile(r"/s/[A-Za-z0-9_-]{8,}")  # a share link's token: never in an output
LINK_FIELDS = ".r-pop input, .c-card-panel input"  # where a share link is shown: covered in the screenshots


def measure(page) -> dict:
    """The surface the person looks at, once it stopped changing (share links' tokens masked)."""
    m = page.evaluate(SETTLED, SETTLE_MS)
    m["text"] = TOKEN.sub("/s/<token>", m["text"])
    m["list"] = [TOKEN.sub("/s/<token>", c) for c in m["list"]]
    return m


def _fill(text: str, values: dict) -> str:
    return text.replace("{run}", values.get("run", "")).replace("{line}", values.get("line", ""))


def _state(page, expect: str, values: dict, timeout: int) -> bool:
    try:
        page.wait_for_function(f"() => ({_fill(expect, values)})", timeout=timeout)
        return True
    except Exception:
        return False


def _locate(page, target: str, timeout: int):
    """The first visible element of the selector, or None after `timeout`."""
    loc = page.locator(target).filter(visible=True).first
    try:
        loc.wait_for(state="visible", timeout=timeout)
        return loc
    except Exception:
        return None


def run_walk(page, walk: dict, out: str | None = None, values: dict | None = None, touch: bool = False,
             timeout: int = TIMEOUT_MS, session=None) -> dict:
    """Drive one walk on an open page (already at its start address) and count it. `touch`: taps, not clicks;
    `session(page, user, address)`: a sign_in step's change of user (the caller's: cookies and the address).
    Returns the walk's record: each step with what was measured before it, and the totals (totals())."""
    values = values or {}
    steps, dead = [], None
    if out:
        os.makedirs(out, exist_ok=True)

    def shot(n: int, kind: str) -> str | None:
        if not out:
            return None
        path = os.path.join(out, f"{n:02d}-{kind}.png")
        try:
            page.screenshot(path=path, mask=[page.locator(LINK_FIELDS)])
        except Exception:
            return None
        return path

    for i, s in enumerate(walk["steps"]):
        n, kind = i + 1, s["kind"]
        rec = {"n": n, "kind": kind}
        steps.append(rec)
        if kind == "note":
            rec["text"] = s["text"]
            continue
        if kind == "wait":
            rec["expect"] = s["expect"]
            if not _state(page, s["expect"], values, timeout):
                dead = {"step": n, "why": f"the state never came: {s['expect']}"}
                rec["shot"] = shot(n, "dead")
                break
            continue
        if kind == "screen":
            rec.update(name=s["name"], measured=measure(page), shot=shot(n, "screen"))
            continue
        if kind == "sign_in":
            rec.update(user=s["user"], address=s["address"], see=s.get("see", ""))
            if session is None:
                dead = {"step": n, "why": "no way to change the user here"}
                break
            session(page, s["user"], _fill(s["address"], values))
            continue
        # an action: its element, the surface before it, then the action and the time to its expected state
        target = _fill(s["target"], values) if s.get("target") else None
        rec.update(target=s.get("target"), see=s.get("see", ""))  # as written: the same in every run
        if kind == "type":
            rec["text"] = s["text"]
        if kind == "key":
            rec["key"] = s["key"]
        loc = _locate(page, target, timeout) if target else None
        if target and loc is None:
            dead = {"step": n, "why": f"no visible element {s['target']}"}
            rec.update(measured=measure(page), shot=shot(n, "dead"))
            break
        rec.update(measured=measure(page), shot=shot(n, kind))
        if kind in ("tap", "unmade") and not s.get("map"):
            rec["in_view"] = loc.evaluate(IN_VIEW)  # False: the walk needs a swipe before it
        if kind == "unmade":
            if not _enabled(loc, timeout):
                dead = {"step": n, "why": f"{s['target']} is not enabled"}
                break
            rec["made"] = False  # counted, never tapped (no search is started)
            continue
        try:
            page.evaluate(FEEDBACK, FEEDBACK_MS)
        except Exception:
            pass
        t0 = time.perf_counter()
        try:
            if kind == "tap" and s.get("map"):
                if not page.evaluate(MAP_CLICK, s["map"]):
                    raise RuntimeError("no place map")
            elif kind == "tap":
                loc.tap() if touch else loc.click()
            elif kind == "swipe":
                loc.scroll_into_view_if_needed()
            elif kind == "type":
                loc.press_sequentially(s["text"])
            else:
                page.keyboard.press(s["key"])
        except Exception as e:
            dead = {"step": n, "why": f"the action failed: {type(e).__name__}: {str(e).splitlines()[0][:160]}"}
            break
        if s.get("expect") and not _state(page, s["expect"], values, timeout):
            dead = {"step": n, "why": f"the expected state never came: {s['expect']}"}
            rec["shot_after"] = shot(n, "dead")
            break
        rec["seconds"] = round(time.perf_counter() - t0, 3)
        if rec["seconds"] * 1000 > FEEDBACK_MS:
            try:
                page.wait_for_function("() => typeof window.__walkFeedback === 'string'", timeout=2000)
                rec["feedback"] = page.evaluate("() => window.__walkFeedback")
            except Exception:
                rec["feedback"] = "unknown"  # a new document: the watcher went with the old one
    end = len(steps)
    if dead is None and steps:
        rec = {"n": end + 1, "kind": "end", "measured": measure(page), "shot": shot(end + 1, "end")}
        steps.append(rec)
    record = {"id": walk.get("id", ""), "title": walk.get("title", ""), "user": walk.get("user"),
              "device": walk.get("device"), "memory": walk.get("memory"), "needs": walk.get("needs"),
              "steps": steps, "dead_end": dead}
    record["totals"] = totals(record, desktop=not touch)
    return record


def _enabled(loc, timeout: int) -> bool:
    """Wait until the element is enabled (no `disabled`, no aria-disabled), at most `timeout`."""
    try:
        loc.page.wait_for_function("(e) => !e.disabled && e.getAttribute('aria-disabled') !== 'true'",
                                   arg=loc.element_handle(timeout=timeout), timeout=timeout)
        return True
    except Exception:
        return False


def _done(s: dict) -> bool:
    """An action that was made (it has its seconds) or counted as not made."""
    return s["kind"] in ACTIONS and (s.get("seconds") is not None or s.get("made") is False)


def totals(record: dict, desktop: bool = True) -> dict:
    """A walk's numbers from its steps (see the module's docstring); a dead end's step and those after it count
    nothing."""
    steps = record["steps"]
    acts = [s for s in steps if _done(s)]
    pointer = sum(1 for s in acts if s["kind"] in POINTER)
    keys = sum(len(s["text"]) if s["kind"] == "type" else 1 for s in acts if s["kind"] in ("type", "key"))
    hand = ["pointer" if s["kind"] in POINTER else "keyboard" for s in acts]
    switches = sum(1 for a, b in zip(hand, hand[1:]) if a != b) if desktop else None
    seen = [s["measured"]["controls"] for s in acts]
    screens = [s for s in steps if s["kind"] == "screen"]
    waits = [s for s in acts if (s.get("seconds") or 0) * 1000 > FEEDBACK_MS]
    return {
        "screens": len(screens), "pointer": pointer, "keystrokes": keys, "switches": switches,
        "decisions": sum(1 for c in seen if c > DECISION), "max_controls": max(seen, default=0),
        "words_first": acts[0]["measured"]["words"] if acts else 0,
        "words_screens": sum(s["measured"]["words"] for s in screens),
        "wait_seconds": round(sum(s.get("seconds") or 0 for s in acts), 2),
        "waits": [{"step": s["n"], "seconds": s["seconds"], "feedback": s.get("feedback")} for s in waits],
        "no_feedback": sum(1 for s in waits if s.get("feedback") == "none"),
        "not_made": sum(1 for s in acts if s.get("made") is False),
        "dead_end": record["dead_end"]["step"] if record["dead_end"] else None,
    }


COLUMNS = [("screens", "Screens"), ("pointer", "Taps/clicks"), ("keystrokes", "Keystrokes"),
           ("switches", "Pointer↔keyboard"), ("decisions", "Decision points (>4)"), ("max_controls", "Most controls"),
           ("words_first", "Words before 1st action"), ("words_screens", "Words over screens"),
           ("wait_seconds", "Seconds waited (indicative)"), ("no_feedback", "Waits >300 ms without feedback"),
           ("dead_end", "Dead end at step")]


def _step_line(s: dict) -> str:
    """One step for the Markdown path: what was done, what the person saw before it."""
    m = s.get("measured")
    seen = (f" [{m['controls']} controls, {m['words']} words"
            + (f"; {m['words_in_scope']} in the {m['scope']}, scrolled out too" if m.get("words_in_scope") is not None
               and m["words_in_scope"] > m["words"] else "") + "]") if m else ""
    if s["kind"] == "note":
        return f"{s['n']}. note: {s['text']}"
    if s["kind"] == "wait":
        return f"{s['n']}. (wait for `{s['expect']}`)"
    if s["kind"] == "screen":
        return f"{s['n']}. **screen: {s['name']}**{seen}"
    if s["kind"] == "sign_in":
        return f"{s['n']}. (signed in as {s['user']} at {s['address']}: not walked)"
    if s["kind"] == "end":
        return f"{s['n']}. end{seen}"
    what = {"tap": "tap", "unmade": "tap (not made)", "swipe": "swipe to", "type": f"type {s.get('text')!r} into",
            "key": f"key {s.get('key')}"}
    timing = f", {s['seconds']} s" + (f" (feedback: {s['feedback']})" if s.get("feedback") else "") \
        if s.get("seconds") is not None else ""
    where = f" `{s['target']}`" if s.get("target") else ""
    return f"{s['n']}. {what[s['kind']]}{where}{seen}{timing}" + (f" → {s['see']}" if s.get("see") else "")


def markdown(records: list) -> str:
    """The table of all walks, then each walk's path step by step."""
    lines = ["| Walk | " + " | ".join(c for _, c in COLUMNS) + " |", "| --- " * (len(COLUMNS) + 1) + "|"]
    for r in records:
        t = r["totals"]
        if t is None:  # not walked
            cells = ["–" for _ in COLUMNS]
        else:
            cells = ["n/a" if t[k] is None and k == "switches" else ("–" if t[k] is None else str(t[k]))
                     for k, _ in COLUMNS]
        lines.append(f"| {r['id']} {r['title']} | " + " | ".join(cells) + " |")
    for r in records:
        lines += ["", f"## {r['id']} {r['title']} ({r['user']}, {r['device']}, {r['memory']} visit)", ""]
        if r.get("skipped"):
            lines.append(f"Not walked: {r['skipped']}")
            continue
        lines += [_step_line(s) for s in r["steps"]]
        out_of_view = [s["n"] for s in r["steps"] if s.get("in_view") is False]
        if out_of_view:
            lines.append(f"\nTapped out of view (the page scrolled to it; the walk needs a swipe): steps {out_of_view}")
        if r["dead_end"]:
            lines.append(f"\nDead end at step {r['dead_end']['step']}: {r['dead_end']['why']}")
            if r.get("needs"):
                lines.append(f"\nWhat the walk needs that the fixtures lack: {r['needs']}")
        if r.get("refused"):
            lines.append(f"\nRefused requests (a start of work): {r['refused']}")
    return "\n".join(lines) + "\n"


def compare(a: list, b: list) -> list:
    """What differs between two runs of the walks in the counts (not in the seconds): a list of texts."""
    diffs = []
    keys = ("screens", "pointer", "keystrokes", "switches", "decisions", "max_controls", "words_first",
            "words_screens", "dead_end")
    other = {r["id"]: r for r in b}
    for r in a:
        o = other.get(r["id"])
        if o is None:
            diffs.append(f"{r['id']}: only in the first")
            continue
        if r["totals"] is None or o["totals"] is None:
            if (r["totals"] is None) != (o["totals"] is None):
                diffs.append(f"{r['id']}: walked in one run only")
            continue
        diffs += [f"{r['id']} {k}: {r['totals'][k]} / {o['totals'][k]}" for k in keys if r["totals"][k] != o["totals"][k]]
        for s, t in zip(r["steps"], o["steps"]):
            if s.get("measured") and t.get("measured"):
                for k in ("controls", "words"):
                    if s["measured"][k] != t["measured"][k]:
                        diffs.append(f"{r['id']} step {s['n']} {k}: {s['measured'][k]} / {t['measured'][k]}")
    return diffs


def _cookies(cookie: str | None, memory: str) -> list:
    """The session's cookie, and with the memory "first" the beta notice's (web.WELCOME_COOKIE)."""
    if not cookie:
        return []
    found = [{"name": SESSION, "value": cookie, "domain": "localhost", "path": "/", "secure": True,
              "httpOnly": True, "sameSite": "Lax"}]
    if memory == "first":
        found.append({"name": WELCOME, "value": "1", "domain": "localhost", "path": "/", "secure": True,
                      "httpOnly": False, "sameSite": "Lax"})
    return found


def _context(pw, browsers: dict, device: str, memory: str, cookie: str | None, site: str):
    """A fresh browser context of the device in the light theme, with what the browser remembers (MEMORIES) and a
    guard that refuses the requests of FORBIDDEN (listed in the second value)."""
    engine, profile = ui_shots.DEVICES[device]
    if engine not in browsers:
        browsers[engine] = getattr(pw, engine).launch()
    options = dict(pw.devices[profile]) if profile else dict(ui_shots.DESKTOP)
    options.pop("default_browser_type", None)
    context = browsers[engine].new_context(**options, color_scheme="light", ignore_https_errors=True)
    if memory == "returning":  # the intros put away, as ui_shots does
        context.add_init_script("try { localStorage.setItem('findaline-theme', 'light'); "
                                + "".join(f"localStorage.setItem('findaline.intro.{intro}', 'seen'); "
                                          for intro in ui_shots.INTROS) + "} catch (e) {}")
    if cookie:
        context.add_cookies(_cookies(cookie, memory))
    refused = []

    def guard(route):
        request = route.request
        if any(request.method == m and p.search(request.url.split("?")[0]) for m, p in FORBIDDEN):
            refused.append(f"{request.method} {request.url}")
            route.abort()
        else:
            route.continue_()
    context.route(f"{site}/api/**", guard)
    return context, refused


def _jobs(data: str) -> int:
    from jobs import Jobs
    return len(Jobs(data, public=True).all())


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command")
    cmp = sub.add_parser("compare", help="what differs in the counts of two runs (walks.json)")
    cmp.add_argument("first")
    cmp.add_argument("second")
    probe = sub.add_parser("probe", help="the surface of one address: its controls and words")
    for p in (parser, probe):
        p.add_argument("--out", required=p is probe, help="folder of the output")
        p.add_argument("--data-dir", help="a scratch data folder (default: a new temporary one, removed at the end)")
    parser.add_argument("--only", default="", help="walks by id (comma-separated)")
    probe.add_argument("--user", default="admin")
    probe.add_argument("--device", default="desktop", choices=list(ui_shots.DEVICES))
    probe.add_argument("--memory", default="returning", choices=MEMORIES)
    probe.add_argument("--start", action="append", required=True,
                       help="an address ({run}, {line}), then ' | ' and selectors to click first, in order; repeatable")
    args = parser.parse_args()

    if args.command == "compare":
        with open(args.first, encoding="utf-8") as f, open(args.second, encoding="utf-8") as g:
            diffs = compare(json.load(f), json.load(g))
        print("\n".join(diffs) if diffs else "the same counts")
        return
    if not args.out:
        parser.error("--out is needed")
    errors = walk_errors(WALKS, list(ui_shots.RIGGERS) + ["admin", "walker"], ui_shots.DEVICES)
    if errors:
        sys.exit("\n".join(errors))
    for name in ("ESRI_API_KEY", "DATAFORDELER_API_KEY"):  # no key in the app this tool starts
        os.environ.pop(name, None)
    import logging  # the server's closed TLS connections on Windows (asyncio's ConnectionResetError): no finding
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    from playwright.sync_api import sync_playwright

    os.makedirs(args.out, exist_ok=True)
    data = args.data_dir or tempfile.mkdtemp(prefix="ui-walks-")
    site, cookies, run, share, stop = ui_shots.serve(data)
    values = {"run": run, "line": ui_shots.first_line(data, run)}
    if _jobs(data):
        sys.exit("the data folder has jobs before the walks: a fresh --data-dir is needed")
    records, refused_all = [], []
    try:
        with sync_playwright() as pw:
            browsers = {}
            if args.command == "probe":
                context, refused = _context(pw, browsers, args.device, args.memory,
                                            cookies.get(args.user), site)
                found = []
                touch = args.device != "desktop"
                for k, given in enumerate(args.start):
                    address, *clicks = given.split(" | ")
                    page = context.new_page()
                    page.goto(site + _fill(address, values))
                    page.wait_for_load_state()
                    for sel in clicks:
                        loc = _locate(page, _fill(sel, values), TIMEOUT_MS)
                        if loc is None:
                            print(f"{given}: no {sel}")
                            break
                        loc.tap() if touch else loc.click()
                    m = measure(page)
                    page.screenshot(path=os.path.join(args.out, f"probe-{k + 1}.png"),
                                    mask=[page.locator(LINK_FIELDS)])
                    found.append({"address": address, **m})
                    print(f"{address}: {m['scope']}, {m['controls']} controls (+{m['disabled']} disabled), "
                          f"{m['words']} words")
                    for c in m["list"]:
                        print("   ", c)
                    print("    words:", m["text"])
                    page.close()
                with open(os.path.join(args.out, "probe.json"), "w", encoding="utf-8") as f:
                    json.dump(found, f, ensure_ascii=False, indent=1)
                context.close()
                refused_all += refused
            else:
                wanted = [w for w in args.only.split(",") if w]
                for wid, walk in WALKS.items():
                    if wanted and wid not in wanted:
                        continue
                    if walk.get("skip"):
                        records.append({"id": wid, "title": walk["title"], "user": walk["user"],
                                        "device": walk["device"], "memory": walk["memory"], "steps": [],
                                        "dead_end": None, "skipped": walk["skip"], "totals": None})
                        print(wid, "not walked:", walk["skip"])
                        continue
                    context, refused = _context(pw, browsers, walk["device"], walk["memory"],
                                                cookies.get(walk["user"]), site)

                    def session(page, user, address, memory=walk["memory"]):
                        page.context.clear_cookies()
                        page.context.add_cookies(_cookies(cookies[user], memory))
                        page.goto(site + address)
                    page = context.new_page()
                    page.goto(site + _fill(walk["start"], values))
                    touch = walk["device"] != "desktop"
                    record = run_walk(page, {**walk, "id": wid}, os.path.join(args.out, wid), values, touch=touch,
                                      session=session)
                    record["refused"] = refused
                    records.append(record)
                    refused_all += refused
                    print(wid, json.dumps(record["totals"]))
                    context.close()
            for b in browsers.values():
                b.close()
    finally:
        stop()
        jobs = _jobs(data)
        if not args.data_dir:
            import gc
            gc.collect()  # SQLite connections left in reference cycles keep their files open on Windows
            shutil.rmtree(data, ignore_errors=True)
    if records:
        with open(os.path.join(args.out, "walks.json"), "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=1)
        with open(os.path.join(args.out, "walks.md"), "w", encoding="utf-8") as f:
            f.write(markdown(records))
        print(os.path.join(args.out, "walks.md"))
    if refused_all or jobs:
        sys.exit(f"a walk asked to start work: {refused_all}; jobs in the data folder: {jobs}")


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    main()
