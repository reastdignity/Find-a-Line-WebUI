"""
Counts and measurements of the app's UI for the UX and UI design task (its targets: the user's thresholds are picked
from these numbers, so the tool has no pass or fail: it reports counts and distributions, and the bounds it cuts at
are parameters). Two commands, each writing JSON and a Markdown summary into --out:

    python tools/ui_metrics.py static --out <folder>
    uv sync --group ui; uv run playwright install chromium webkit; cd viewer; npm ci   (once, for "pages")
    uv run tools/ui_metrics.py pages --out <folder> [--only c-home,c-result] [--devices desktop,iphone,pixel] [--dark]

"static" reads the source only (static.json, static.md): in the CSS of viewer/src every distinct font size (also of
the `font:` shorthand), border radius and z-index, the colour literals (hex, rgb(), hsl()) outside ui/tokens.css (and,
apart, in the .ts/.tsx code), the uses of the monospace font with their uppercase ones; "the same grey box" (selectors
with a surface background, a 1 px border in var(--line), a radius of 8 px or more and var(--shadow), their rules
merged per selector: a count of rules, not of the places the look appears; "pages" counts those); the characters
used as icons or joints (ICON_CHARS) in the code (comments and regular expressions left out; inside an aria-label or
a title listed apart as not shown; the demo pages DEMO_FILES left out unless --with-demos), in CSS `content:` and in
locales/en.json, and the "dense strings" (two of them or more, or a "·" joint); the texts of locales/en.json by group
(words per text) and the .tsx files that hold English text in code without calling t(. CSS is read by a small scanner
of this file (no CSS parser is installed and none may be added for this tool): nested CSS rules are not parsed (the
viewer has none), a `font:` whose size is var() or calc() is counted as "unresolved", colours are normalised (#FFF =
#ffffff, the spaces of rgb()).

"pages" renders every state of tools/ui_shots.py's PAGES the way that tool does (its serve, select_pages,
left_out_by_run and shoot_all with `act`: the same site, users, waits and steps; a data folder of its own, one run at
a time per folder) and measures each one just where the screenshot would be taken (pages-states.jsonl, one line a
state as it ends; then pages.json, pages.md). A state whose wait timed out or whose load, steps or measuring failed
is recorded as not measured, with its reason, and counts in no total:
- the visible, enabled controls (only an open modal dialog's when one is open) and the size of each one's target:
  its own box joined with the boxes of its absolutely positioned ::before and ::after (computed from their insets,
  sizes and the control's padding box; one positioned against another element, a transform or a clip is not seen),
  and for a checkbox or radio the largest of that and its labels' boxes; under 44 px and 24 px in width or height
  (WCAG 2.5.8's size; its spacing exception is not modelled). A target's size is the part of it no ancestor clips
  (per axis; an absolutely positioned control only from its containing block up). A control that cannot be reached
  (wholly before the scroll origin of a scroller or of the document, or clipped to nothing) is listed apart, not
  counted; one below the fold of a scrolling page or panel counts. A control in the viewport whose centre another
  element covers (one hit test: elementFromPoint at the centre of its own box, or its label's) is listed apart as
  covered and not counted; one out of the viewport is not tested, and a cover of only a part is not seen. Signatures are tag, role, input type and class names without the state
  classes (STATE_CLASS: on, open, selected, ...; the viewer's BASE_CLASSES that end so are kept), so one control in
  two states is one signature;
- the visible text and its rendered font size (under 12, 11, 10 px, as shares of the visible characters; SVG text
  scaled to the screen), also without what lies in a map's credits or scale (a text's or control's zone, "credits" or
  "scale", is kept with its size and makes a signature of its own; its nearest named ancestor is kept too);
- the document wider than its viewport (the defect), and apart the elements that scroll sideways by themselves
  (overflow-x auto or scroll, content wider than their box);
- "the same grey box" as rendered: the visible containers (not controls) of at least BOX_MIN px each way with an
  opaque background, a border of 1 px or more, a radius of 8 px or more and a box shadow, beside all visible
  containers of that size with a background or a border of their own;
- axe-core's violations and "incomplete" results by impact (a failure of axe on a state is recorded for the state,
  its own measurements are kept), and the seconds of loading, steps and measuring (indicative only: the test lock's
  shared lane, other sessions; the set-up's and each pass's seconds in pages-run.json).

axe-core comes from viewer/node_modules/axe-core/axe.min.js (a development dependency of viewer/package.json; `npm
ci` in viewer); without it the axe part is left out with a note. The app's pages forbid inline script and eval
(CSP `script-src 'self'`), so axe-core cannot be put into them as they are served: this tool's browser contexts are
opened with Playwright's bypass_csp, which tools/ui_shots.py's never are. With the CSP bypassed a page could apply
what the CSP would block (inline styles): the viewer has none (.claude/rules/viewer.md), so the pages look the same.

The keys of the user's services (ESRI_API_KEY, DATAFORDELER_API_KEY) are best removed from the environment of
"pages": the clip's run shows no Esri imagery without them.
"""

import argparse
import fnmatch
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

ICON_CHARS = "▾▴▸›‹↑↓→×•★⋯·Δ✓✗"  # characters used as icons or joints in what the user reads
JOINT = "·"  # a "dense string" also when it joins parts with this
TOKENS = "viewer/src/ui/tokens.css"
CATALOGUE = "locales/en.json"
CONTROL_BOUNDS = (44, 24)  # px: a touch target (Apple, Material), WCAG 2.5.8's minimum
TEXT_BOUNDS = (12, 11, 10)  # px
AXE = os.path.join(REPO, "viewer", "node_modules", "axe-core", "axe.min.js")
AXE_TIMEOUT_MS = 60000  # one axe.run on a page; a page whose run takes longer gets an error, not a hang
TOP = 25  # rows of a list in the Markdown summaries
BOX_MIN = 40  # px each way: a container counted by "pages"' rendered grey box
# The demo pages of the developers (?ui=kit), left out of the characters' count unless --with-demos
DEMO_FILES = ("viewer/src/ui/Gallery.tsx", "Kit*.tsx")
# State classes, left out of the signatures: a class that is one of these words, or ends in "-<word>"
STATE_WORDS = ("on", "off", "open", "closed", "selected", "active", "disabled", "checked", "current", "pressed",
               "expanded", "collapsed", "folded", "unfolded", "changed", "busy", "loading", "picking", "dragging",
               "failed", "hidden", "shown", "focus", "focused", "hover")
STATE_CLASS = r"(^|-)(" + "|".join(STATE_WORDS) + r")$"
# The viewer's classes that end in such a word but name what an element is, not a state it is in (Home's run cards,
# the favourites' open buttons, the pages' "open" links, the result's loading box): kept in the signatures
BASE_CLASSES = ("c-card-open", "c-fav-open", "c-folder-open", "p-open", "c-loading")
TEMP_PREFIX = "ui-shots-metrics-"  # tools/clean_temp.py removes the ui-shots-* folders of runs that did not end


# ---------------------------------------------------------------------------------------------------------- static

def _blank(text: str) -> str:
    """The text with every character but newlines made a space (a comment taken out, the lines kept)."""
    return re.sub(r"[^\n]", " ", text)


def css_rules(text: str) -> list:
    """The declaration blocks of a style sheet: dicts of `selectors` (the prelude split at its top-level commas),
    `prelude`, `line` (1-based), `at` (the enclosing at-rules' preludes) and `decls` ([(property, value)]; property in
    lower case, `!important` dropped). Comments are left out; at-rules without a block (`@import`) are skipped."""
    text = re.sub(r"/\*.*?\*/", lambda m: _blank(m.group()), text, flags=re.S)
    rules, stack = [], []  # stack: [prelude, body start, line, has a block inside]
    start, quote, i = 0, None, 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "{":
            prelude = text[start:i]
            line = text.count("\n", 0, start + len(prelude) - len(prelude.lstrip())) + 1
            if stack:
                stack[-1][3] = True
            stack.append([" ".join(prelude.split()), i + 1, line, False])
            start = i + 1
        elif c == "}":
            if stack:
                prelude, body, line, nested = stack.pop()
                if not nested:
                    rules.append({"prelude": prelude, "selectors": _split_top(prelude, ","), "line": line,
                                  "at": [s[0] for s in stack], "decls": _declarations(text[body:i])})
            start = i + 1
        elif c == ";" and not stack or c == ";" and stack and stack[-1][3]:
            start = i + 1  # a statement (@import) or, inside an at-rule's block, nothing to keep
        i += 1
    return rules


def _split_top(text: str, sep: str) -> list:
    """`text` split at `sep` outside parentheses and quotes, each part stripped (empty parts dropped)."""
    parts, depth, quote, cur = [], 0, None, []
    for c in text:
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(c)
    parts.append("".join(cur).strip())
    return [" ".join(p.split()) for p in parts if p.strip()]


def _declarations(body: str) -> list:
    out = []
    for part in _split_top(body, ";"):
        prop, colon, value = part.partition(":")
        if not colon:
            continue
        value = re.sub(r"\s*!important\s*$", "", value.strip(), flags=re.I)
        out.append((prop.strip().lower(), value))
    return out


SIZE = re.compile(r"^(\d*\.?\d+(?:px|em|rem|%|pt|vw|vh|vmin|vmax|ch|ex)|xx-small|x-small|small|medium|large|x-large|"
                  r"xx-large|smaller|larger)(?:/.*)?$")


def font_size_of(prop: str, value: str):
    """The font size a declaration sets ("13px", "inherit", "var(--x)", ...), None if it sets none. Custom
    properties (--font: ...) set none."""
    if prop == "font-size":
        return value
    if prop != "font":
        return None
    unresolved = False
    for token in _split_top(value.replace(",", " , "), " "):
        if token == ",":
            break  # the family list begins
        m = SIZE.match(token)
        if m:
            return m.group(1)
        unresolved = unresolved or token.startswith(("var(", "calc("))
    return "unresolved" if unresolved else None  # a size of var() or calc(): set, but not known here


def _px(value: str):
    m = re.match(r"^(-?\d*\.?\d+)px$", value)
    return float(m.group(1)) if m else None


COLOUR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?)\([^()]*\)")


def _colour(value: str) -> str:
    """A colour literal normalised: lower case, #abc as #aabbcc, the spaces of rgb() and hsl() as rgb(1 2 3 / .5)."""
    value = " ".join(value.lower().split())
    if value.startswith("#") and len(value) in (4, 5):
        value = "#" + "".join(c * 2 for c in value[1:])
    return re.sub(r"\s*([,/()])\s*", lambda m: {",": ", ", "/": " / "}.get(m.group(1), m.group(1)), value)


def _is_mono(prop: str, value: str) -> bool:
    return prop in ("font", "font-family") and ("var(--mono)" in value or "monospace" in value.lower())


def _decode_css(value: str) -> str:
    """CSS escapes (\\25be) decoded."""
    return re.sub(r"\\([0-9a-fA-F]{1,6})\s?", lambda m: chr(int(m.group(1), 16)), value)


def strip_comments(text: str, blank_regex: bool = False) -> str:
    """JavaScript or TypeScript with its comments made spaces (lines kept): strings (', " and ` with ${} inside),
    regular expressions (after an operator or a keyword; made spaces too with `blank_regex`) and JSX text are left as
    they are. A quote in JSX text ("don't") is taken as a string to the end of its line, never further; "//" right
    after a word and a colon (https://) in JSX text is no comment."""
    out, i, n = list(text), 0, len(text)
    stack = []  # "`" in a template, "{" in a ${...} of one (its depth of braces)
    prev = ""  # the last character of code that is not a space
    while i < n:
        c = text[i]
        if stack and stack[-1] == "`":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                stack.pop()
                prev = "`"
            elif c == "$" and text.startswith("${", i):
                stack.append(0)
                i += 2
                continue
            i += 1
            continue
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            i, prev = j + 1, c
            continue
        if c == "`":
            stack.append("`")
            i += 1
            continue
        url = (i >= 2 and text[i - 1] == ":" and text[i - 2].isalpha() and i + 2 < n and not text[i + 2].isspace())
        if c == "/" and text.startswith("//", i) and not url:  # "https://x" in JSX text; "default:// a note" is one
            j = text.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
            continue
        if c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out[i:j] = _blank(text[i:j])
            i = j
            continue
        # a regular expression after an operator, an arrow or a keyword; not after "<" (a closing tag), nor after "}"
        # or ">" (JSX text: "{a} / {b}", "<p>/ day")
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{;+-*%~^" or text[max(0, i - 200):i].rstrip().endswith("=>")
                         or re.search(r"\b(return|typeof|case)\s*$", text[max(0, i - 8):i])):
            j, cls = i + 1, False  # a regular expression
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    cls = True
                elif text[j] == "]":
                    cls = False
                elif text[j] == "/" and not cls:
                    break
                j += 1
            if j >= n or text[j] != "/":  # not closed on its line: no regular expression, a "/" of the code
                i, prev = i + 1, "/"
                continue
            if blank_regex:
                out[i:j + 1] = " " * (j + 1 - i)
            i, prev = j + 1, "/"
            continue
        if stack and stack[-1] != "`":
            if c == "{":
                stack[-1] += 1
            elif c == "}":
                if stack[-1] == 0:
                    stack.pop()  # back in the template
                    i += 1
                    continue
                stack[-1] -= 1
        if not c.isspace():
            prev = c
        i += 1
    return "".join(out)


def _rel(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _files(root: str, folder: str, ext: tuple) -> list:
    found = []
    for base, dirs, names in os.walk(os.path.join(root, folder)):
        dirs[:] = sorted(d for d in dirs if d != "node_modules")
        found += [os.path.join(base, f) for f in sorted(names) if f.endswith(ext)]
    return sorted(found, key=lambda p: _rel(p, root))


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _p90(values: list):
    s = sorted(values)
    return s[max(0, math.ceil(0.9 * len(s)) - 1)] if s else None


def _words(text: str) -> int:
    return len(text.split())


def text_group(key: str) -> str:
    """The group of a catalogue key, the first that fits in this order: intro.*, hint.*, *.help, error.*, ui.*, the
    rest ("ui.x.help" is a help text)."""
    if key.startswith("intro."):
        return "intro"
    if key.startswith("hint."):
        return "hint"
    if key.endswith(".help"):
        return "help"
    if key.startswith("error."):
        return "error"
    if key.startswith("ui."):
        return "ui"
    return "rest"


JSX_TEXT = re.compile(r">([^<>{}\n=;&|()]*[A-Za-z]{3,}[^<>{}\n=;&|()]*)<")
JSX_TEXT_END = re.compile(r">\s*([A-Z][a-z]+(?:[ ,.'’-]+[A-Za-z]+)*[.!?:…]?)\s*$", re.M)  # text that goes on below
ATTR_TEXT = re.compile(r"\b(?:title|aria-label|placeholder|alt|label)=\"([^\"]*[A-Za-z]{2,}[^\"]*)\"")
SENTENCE = re.compile(r"[\"'`]([A-Z][a-z]+(?: [^\"'`\n${}]+)+)[\"'`]")  # "Two words or more", a capital first
T_CALL = re.compile(r"(?<![\w.$])t\(")
OTHER_CALLS = re.compile(r"(?<![\w.$])(?:label|errorText|quantity|detailMessage)\(")


def english_in_code(code: str) -> list:
    """English texts a .tsx file holds in its code (comments taken out): JSX text, the attributes title, aria-label,
    placeholder, alt and label, and quoted texts of two words or more that start with a capital."""
    found = [m.group(1).strip() for m in JSX_TEXT.finditer(code)]
    found += [m.group(1).strip() for m in JSX_TEXT_END.finditer(code)]
    found += [m.group(1) for m in ATTR_TEXT.finditer(code)]
    found += [m.group(1) for m in SENTENCE.finditer(code)]
    return [f for f in found if re.search(r"[A-Za-z]{2,}", f)]


NOT_SHOWN = re.compile(r"""(?:\baria-label|\btitle)\s*[=:]\s*(?:"[^"\n]*"|'[^'\n]*'|`[^`\n]*`|\{(?:[^{}\n]|\{[^{}\n]*\})*\})"""
                       r"""|setAttribute\(\s*["'](?:aria-label|title)["']\s*,[^)\n]*\)""")


def _is_demo(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(os.path.basename(name), pattern)
               for pattern in DEMO_FILES)


def static(root: str = REPO, chars: str = ICON_CHARS, radius_min: float = 8, with_demos: bool = False) -> dict:
    """The counts of "static" for the tree at `root` (viewer/src, locales/en.json); the demo pages (DEMO_FILES) are
    left out of the characters and dense strings unless `with_demos`."""
    css_files = _files(root, "viewer/src", (".css",))
    code_files = _files(root, "viewer/src", (".ts", ".tsx"))
    sizes, radii, radius_lengths, zs = defaultdict(Counter), defaultdict(Counter), Counter(), defaultdict(Counter)
    colours, mono, content_chars = defaultdict(Counter), [], []
    merged = defaultdict(list)  # selector -> [(prop, value)] of all its rules
    where = defaultdict(set)  # selector -> files
    for path in css_files:
        name = _rel(path, root)
        for rule in css_rules(_read(path)):
            for prop, value in rule["decls"]:
                if prop.startswith("--"):
                    if name != TOKENS:  # a custom property's value outside the tokens: its colours count
                        for m in COLOUR.finditer(value):
                            colours[name][_colour(m.group())] += 1
                    continue
                size = font_size_of(prop, value)
                if size is not None:
                    sizes[size][name] += 1
                if prop == "border-radius" or re.fullmatch(r"border-(top|bottom)-(left|right)-radius", prop):
                    radii[value][name] += 1
                    for token in value.replace("/", " ").split():
                        radius_lengths[token] += 1
                if prop == "z-index":
                    zs[value][name] += 1
                if name != TOKENS:
                    for m in COLOUR.finditer(value):
                        colours[name][_colour(m.group())] += 1
                if prop == "content":
                    for c in _decode_css(value):
                        if c in chars:
                            content_chars.append({"file": name, "line": rule["line"], "char": c,
                                                  "selector": rule["prelude"]})
            if any(_is_mono(p, v) for p, v in rule["decls"]):
                mono.append({"file": name, "line": rule["line"], "selector": rule["prelude"]})
            for selector in rule["selectors"]:
                merged[selector] += rule["decls"]
                where[selector].add(name)

    def upper(selectors: str) -> bool:
        return any(("text-transform", "uppercase") in [(p, v.lower()) for p, v in merged[s]]
                   for s in _split_top(selectors, ","))
    for place in mono:
        place["uppercase"] = upper(place["selector"])

    boxes = []
    for selector, decls in merged.items():
        has = {"surface": any(p in ("background", "background-color") and "var(--surface" in v for p, v in decls),
               "border": any(p == "border" and re.search(r"(^|\s)1px(\s|$)", v) and "var(--line)" in v
                             for p, v in decls),
               "radius": any(p == "border-radius" and (_px(v.split()[0]) or 0) >= radius_min for p, v in decls),
               "shadow": any(p == "box-shadow" and "var(--shadow)" in v for p, v in decls)}
        if sum(has.values()) >= 2:
            boxes.append({"selector": selector, "files": sorted(where[selector]), **has, "of_four": sum(has.values())})
    boxes.sort(key=lambda b: (-b["of_four"], b["files"], b["selector"]))

    # characters in the code, in CSS content and in the catalogue; dense strings
    in_code, not_shown, dense, demos = [], [], [], []
    for path in code_files:
        name = _rel(path, root)
        if not with_demos and _is_demo(name):
            demos.append(name)
            continue
        for number, line in enumerate(strip_comments(_read(path), blank_regex=True).split("\n"), 1):
            if not any(c in chars for c in line):
                continue
            hidden = set()  # the positions inside an aria-label or a title: never shown
            for m in NOT_SHOWN.finditer(line):
                hidden.update(range(m.start(), m.end()))
            found = []
            for at, c in enumerate(line):
                if c in chars:
                    (not_shown if at in hidden else in_code).append({"file": name, "line": number, "char": c})
                    if at not in hidden:
                        found.append(c)
            if len(found) >= 2 or JOINT in found:
                dense.append({"where": f"{name}:{number}", "text": line.strip()[:160]})
    catalogue = json.loads(_read(os.path.join(root, CATALOGUE)))
    in_catalogue = []
    for key, value in catalogue.items():
        found = [c for c in value if c in chars]
        for c in found:
            in_catalogue.append({"key": key, "char": c})
        if len(found) >= 2 or JOINT in found:
            dense.append({"where": f"{CATALOGUE}:{key}", "text": value[:160]})

    # the catalogue's texts
    groups = defaultdict(list)
    empty = 0
    for key, value in catalogue.items():
        if not value.strip():
            empty += 1
            continue
        groups[text_group(key)].append((key, _words(value)))
    texts = {}
    for group in ("intro", "hint", "help", "error", "ui", "rest"):
        words = [w for _, w in groups.get(group, [])]
        texts[group] = {"texts": len(words), "words": sum(words),
                        "median": statistics.median(words) if words else None, "p90": _p90(words),
                        "longest": max(words) if words else None}
    longest = sorted(((w, k) for g in groups.values() for k, w in g), key=lambda x: (-x[0], x[1]))[:25]

    # .tsx files with English text in code
    tsx = []
    for path in code_files:
        if not path.endswith(".tsx"):
            continue
        code = strip_comments(_read(path))
        english = english_in_code(code)
        tsx.append({"file": _rel(path, root), "calls_t": bool(T_CALL.search(code)),
                    "calls_other": bool(OTHER_CALLS.search(code)), "english": len(english),
                    "examples": sorted(set(english))[:4]})

    def table(counter: dict) -> list:
        return sorted(({"value": v, "count": sum(c.values()), "files": dict(sorted(c.items()))}
                       for v, c in counter.items()), key=lambda r: (-r["count"], r["value"]))
    numeric_sizes = sorted({_px(v) for v in sizes if _px(v) is not None})
    return {
        "chars": chars,
        "css_files": len(css_files), "code_files": len(code_files),
        "font_sizes": table(sizes), "font_sizes_px": numeric_sizes,
        "radii": table(radii), "radius_lengths": dict(sorted(radius_lengths.items(), key=lambda x: (-x[1], x[0]))),
        "z_index": table(zs),
        "colours_outside_tokens": {f: dict(sorted(c.items())) for f, c in sorted(colours.items())},
        "colours_outside_tokens_distinct": sorted({c for f in colours.values() for c in f}),
        "colours_in_code": _code_colours(root, code_files),
        "mono": mono, "mono_uppercase": sum(p["uppercase"] for p in mono),
        "boxes": boxes,
        "boxes_totals": {"all four": sum(b["of_four"] == 4 for b in boxes), "three": sum(b["of_four"] == 3 for b in boxes),
                         "two": sum(b["of_four"] == 2 for b in boxes),
                         "border and radius only": sum(b["border"] and b["radius"] and not b["surface"] and not b["shadow"]
                                                       for b in boxes)},
        "chars_in_code": in_code, "chars_not_shown": not_shown, "demos_left_out": demos,
        "chars_in_css_content": content_chars, "chars_in_catalogue": in_catalogue,
        "chars_count": {c: {"code": sum(x["char"] == c for x in in_code),
                            "not_shown": sum(x["char"] == c for x in not_shown),
                            "css": sum(x["char"] == c for x in content_chars),
                            "catalogue": sum(x["char"] == c for x in in_catalogue)} for c in chars},
        "dense_strings": dense,
        "texts": texts, "texts_empty": empty, "texts_total": len(catalogue), "longest_texts": [
            {"key": k, "words": w, "text": catalogue[k]} for w, k in longest],
        "tsx": tsx,
        "tsx_without_t": {
            "english, no t(": sorted(f["file"] for f in tsx if f["english"] and not f["calls_t"]),
            "english, no t( nor label(, errorText(, quantity(, detailMessage(": sorted(
                f["file"] for f in tsx if f["english"] and not f["calls_t"] and not f["calls_other"]),
            "two English texts or more, no t(": sorted(f["file"] for f in tsx if f["english"] >= 2 and not f["calls_t"]),
            "no t( at all": sorted(f["file"] for f in tsx if not f["calls_t"])},
    }


def _code_colours(root: str, code_files: list) -> dict:
    found = defaultdict(Counter)
    for path in code_files:
        for m in COLOUR.finditer(strip_comments(_read(path))):
            found[_rel(path, root)][_colour(m.group())] += 1
    return {f: dict(sorted(c.items())) for f, c in sorted(found.items())}


def static_markdown(r: dict) -> str:
    def files(d: dict) -> str:
        return ", ".join(f"{os.path.basename(f)} {n}" for f, n in d.items())
    out = ["# UI metrics: static", "",
           f"{r['css_files']} CSS files and {r['code_files']} .ts/.tsx files of viewer/src; {CATALOGUE}. "
           f"Characters: `{r['chars']}`.", "",
           f"## Font sizes ({len(r['font_sizes'])} distinct values; {len(r['font_sizes_px'])} distinct px values)", "",
           "px values: " + ", ".join(f"{v:g}" for v in r["font_sizes_px"]), "",
           "| Value | Declarations | Files |", "| --- | --- | --- |"]
    out += [f"| `{x['value']}` | {x['count']} | {files(x['files'])} |" for x in r["font_sizes"]]
    out += ["", f"## Border radii ({len(r['radii'])} distinct values; {len(r['radius_lengths'])} distinct lengths)", "",
            "Lengths: " + ", ".join(f"`{k}` {v}" for k, v in r["radius_lengths"].items()), "",
            "| Value | Declarations | Files |", "| --- | --- | --- |"]
    out += [f"| `{x['value']}` | {x['count']} | {files(x['files'])} |" for x in r["radii"]]
    out += ["", f"## z-index ({len(r['z_index'])} distinct values)", "", "| Value | Declarations | Files |",
            "| --- | --- | --- |"]
    out += [f"| `{x['value']}` | {x['count']} | {files(x['files'])} |" for x in r["z_index"]]
    distinct = r["colours_outside_tokens_distinct"]
    out += ["", f"## Colour literals outside {TOKENS} ({len(distinct)} distinct, "
            f"{sum(sum(c.values()) for c in r['colours_outside_tokens'].values())} uses)", "",
            "| File | Colours (uses) |", "| --- | --- |"]
    out += [f"| {f} | " + ", ".join(f"`{k}` {v}" for k, v in c.items()) + " |"
            for f, c in r["colours_outside_tokens"].items()]
    code = r["colours_in_code"]
    out += ["", f"In the .ts/.tsx code (apart): {len({c for f in code.values() for c in f})} distinct, "
            f"{sum(sum(c.values()) for c in code.values())} uses in {len(code)} files: "
            + "; ".join(f"{f} {sum(c.values())}" for f, c in code.items())]
    out += ["", f"## Monospace ({len(r['mono'])} rules, {r['mono_uppercase']} of them also uppercase)", "",
            "| File:line | Selector | Uppercase |", "| --- | --- | --- |"]
    out += [f"| {m['file']}:{m['line']} | `{m['selector'][:90]}` | {'yes' if m['uppercase'] else ''} |" for m in r["mono"]]
    t = r["boxes_totals"]
    out += ["", f"## The same grey box (selectors with 2 of the 4 or more: all four {t['all four']}, three {t['three']}, "
            f"two {t['two']}; border and radius only {t['border and radius only']})", "",
            "A count of selectors (their rules merged), not of the places the look appears: `pages` counts those.", "",
            "| Selector | Files | Surface | Border | Radius | Shadow |", "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| `{b['selector'][:80]}` | {', '.join(os.path.basename(f) for f in b['files'])} | "
            + " | ".join("x" if b[k] else "" for k in ("surface", "border", "radius", "shadow")) + " |" for b in r["boxes"]]
    out += ["", "## Characters as icons or joints", "",
            "Regular expressions and comments left out; the demo pages left out: "
            + (", ".join(r["demos_left_out"]) or "none") + ".", "",
            "| Char | Code (shown) | Code (aria-label, title: not shown) | CSS content | Catalogue |",
            "| --- | --- | --- | --- | --- |"]
    out += [f"| {c} | {n['code']} | {n['not_shown']} | {n['css']} | {n['catalogue']} |"
            for c, n in r["chars_count"].items()]
    out += ["", "Places in the code: " + "; ".join(f"{x['file']}:{x['line']} {x['char']}" for x in r["chars_in_code"]),
            "", "Not shown: " + "; ".join(f"{x['file']}:{x['line']} {x['char']}" for x in r["chars_not_shown"]),
            "", "In CSS content: " + "; ".join(f"{x['file']}:{x['line']} {x['char']}" for x in r["chars_in_css_content"]),
            "", "In the catalogue: " + "; ".join(f"{x['key']} {x['char']}" for x in r["chars_in_catalogue"])]
    out += ["", f"## Dense strings ({len(r['dense_strings'])}: two of the characters or more, or a `{JOINT}` joint; "
            "code by line)", "", "| Where | Text |", "| --- | --- |"]
    out += [f"| {d['where']} | `{d['text'].replace('|', '¦')}` |" for d in r["dense_strings"]]
    out += ["", f"## Texts of {CATALOGUE} ({r['texts_total']} keys, {r['texts_empty']} empty)", "",
            "| Group | Texts | Words | Median | 90th percentile | Longest |", "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| {g} | {x['texts']} | {x['words']} | {x['median']} | {x['p90']} | {x['longest']} |"
            for g, x in r["texts"].items()]
    out += ["", "The 25 longest:", "", "| Key | Words |", "| --- | --- |"]
    out += [f"| {x['key']} | {x['words']} |" for x in r["longest_texts"]]
    out += ["", "## .tsx files with English text in code", ""]
    for name, found in r["tsx_without_t"].items():
        out += [f"- {name}: {len(found)}: " + ", ".join(found)]
    out += ["", "| File | t( | label( etc. | English texts | Examples |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {f['file']} | {'yes' if f['calls_t'] else ''} | {'yes' if f['calls_other'] else ''} | {f['english']} | "
            + "; ".join(e[:40].replace("|", "¦") for e in f["examples"]) + " |" for f in r["tsx"] if not f["calls_t"]]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------------------------------------- pages

# One evaluation per state: the controls, the text, sideways scroll, the containers (opts: the state classes, BOX_MIN)
MEASURE_JS = r"""(opts) => {
  const CONTROLS = "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], " +
    "[role=menuitem], [role=option], [role=radio], [role=switch], [role=slider], [role=checkbox], [role=link]";
  const STATE = new RegExp(opts.state), BASE = new Set(opts.base);
  const shown = (e) => e.checkVisibility({visibilityProperty: true, opacityProperty: true});
  const classes = (e) => [...e.classList].filter((c) => !/\d{3,}/.test(c) && (BASE.has(c) || !STATE.test(c))).sort()
    .map((c) => "." + c).join("");
  const sig = (e) => e.tagName.toLowerCase() + (e.getAttribute("role") ? `[role=${e.getAttribute("role")}]` : "") +
    (e.tagName === "INPUT" ? `[type=${e.type}]` : "") + classes(e);
  const short = (s) => s.replace(/\s+/g, " ").trim().slice(0, 50);
  const r1 = (v) => Math.round(v * 10) / 10;
  const box = (r) => ({left: r.left, top: r.top, right: r.right, bottom: r.bottom});
  const size = (b) => Math.min(b.right - b.left, b.bottom - b.top);
  const px = (v) => (v === "auto" || v === "" || v === undefined) ? null : parseFloat(v);
  // The box of a control's ::before or ::after when it is absolutely positioned against the control (its insets or
  // sizes against the control's padding box); null when there is none, it takes no clicks (hidden, pointer-events
  // none), the control clips it (its own overflow hidden) or it is not seen this way (a transform moves it)
  const pseudoBox = (e, which, rect) => {
    const s = getComputedStyle(e, which), own = getComputedStyle(e);
    if (!s || s.content === "none" || s.content === "normal" || s.display === "none" || s.pointerEvents === "none" ||
        s.visibility === "hidden" || s.transform !== "none" || s.position !== "absolute" || own.position === "static" ||
        /hidden|clip/.test(own.overflowX) || /hidden|clip/.test(own.overflowY)) return null;
    const lo = {x: rect.left + parseFloat(own.borderLeftWidth), y: rect.top + parseFloat(own.borderTopWidth)};
    const hi = {x: rect.right - parseFloat(own.borderRightWidth), y: rect.bottom - parseFloat(own.borderBottomWidth)};
    const extra = (a, b) => s.boxSizing === "border-box" ? 0 : parseFloat(s["padding" + a]) + parseFloat(s["padding" + b]) +
      parseFloat(s["border" + a + "Width"]) + parseFloat(s["border" + b + "Width"]);
    const axis = (start, end, length, l, h, more) => {
      const a = px(start), b = px(end), w = px(length);
      if (a !== null && b !== null) return [l + a, h - b];
      if (a !== null && w !== null) return [l + a, l + a + w + more];
      if (b !== null && w !== null) return [h - b - w - more, h - b];
      return null;
    };
    const x = axis(s.left, s.right, s.width, lo.x, hi.x, extra("Left", "Right"));
    const y = axis(s.top, s.bottom, s.height, lo.y, hi.y, extra("Top", "Bottom"));
    return x && y && x[1] > x[0] && y[1] > y[0] ? {left: x[0], right: x[1], top: y[0], bottom: y[1]} : null;
  };
  const join = (a, b) => ({left: Math.min(a.left, b.left), top: Math.min(a.top, b.top),
                           right: Math.max(a.right, b.right), bottom: Math.max(a.bottom, b.bottom)});
  // Reachable: the part of a target box no ancestor's overflow clips away, null when nothing is left (or the box is
  // wholly before the scroll origin of a scrolling ancestor or of the document). Per axis: an ancestor that hides its
  // overflow on an axis clips that axis; one that scrolls on it brings what lies past its fold into reach (the box's
  // own part is then the scroller's on that axis, for the ancestors above). An absolutely positioned box is clipped
  // only from its containing block up (a positioned ancestor or one with a transform); a fixed one or one in the top
  // layer by no ancestor (only by the viewport).
  const escapes = (x) => {
    if (getComputedStyle(x).position === "fixed") return true;
    try { return x.matches(":popover-open, dialog:modal"); } catch (err) { return false; }
  };
  const viewportCut = (r) => r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight;
  const contains = (s) => s.position !== "static" || s.transform !== "none" || s.filter !== "none" ||
    /paint|layout|strict|content/.test(s.contain || "");
  const reachable = (e, b) => {
    let r = {...b}, own = {...b}, mine = {x: true, y: true};  // `own`: the box's part not clipped (on axes still its)
    if (escapes(e)) return viewportCut(r) ? own : null;
    let absolute = getComputedStyle(e).position === "absolute";
    for (let a = e.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (absolute && !contains(s)) continue;  // between an absolute box and its containing block: no clip
      absolute = s.position === "absolute";
      const ab = a.getBoundingClientRect();
      for (const [axis, lo, hi, scroll, over] of [["x", "left", "right", a.scrollLeft, s.overflowX],
                                                   ["y", "top", "bottom", a.scrollTop, s.overflowY]]) {
        if (/auto|scroll/.test(over)) {
          if (r[hi] <= ab[lo] - scroll) return null;  // before the scroll origin: no scrolling reaches it
          r[lo] = ab[lo]; r[hi] = ab[hi]; mine[axis] = false;
        } else if (/hidden|clip/.test(over)) {
          r[lo] = Math.max(r[lo], ab[lo]); r[hi] = Math.min(r[hi], ab[hi]);
          if (r[hi] <= r[lo]) return null;
          if (mine[axis]) { own[lo] = Math.max(own[lo], ab[lo]); own[hi] = Math.min(own[hi], ab[hi]); }
        }
      }
      if (escapes(a)) return viewportCut(r) ? own : null;
    }
    return r.right + scrollX > 0 && r.bottom + scrollY > 0 ? own : null;
  };
  // Covered: the centre of the control's own box (its label's, for one measured by its label), when it lies in the
  // viewport, hits another element than the control, what it holds, its labels or an ancestor of it: a tap there
  // goes elsewhere. One hit test a control in view; a control out of the viewport is not tested (null)
  const covered = (e, owner) => {
    const r = owner.getBoundingClientRect(), x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
    const hit = document.elementFromPoint(x, y);
    if (!hit || hit === e || e.contains(hit) || owner.contains(hit) || hit.contains(e)) return false;
    return !(e.labels && [...e.labels].some((l) => l.contains(hit)));
  };
  // Where an element lies: "credits" inside a map's credits (Leaflet's attribution control, the 3D view's credits, the
  // home cards' mini-map credits), "scale" inside Leaflet's scale control, else null; and its nearest named ancestor
  // (one with an id, a landmark, a dialog or a section: its tag and id, or its first two classes)
  const ZONES = [["credits", ".leaflet-control-attribution, .v3-credits, .c-thumb-credit"],
                 ["scale", ".leaflet-control-scale"]];
  const zone = (e) => { for (const [name, sel] of ZONES) if (e.closest(sel)) return name; return null; };
  const NAMED = "[id], dialog, main, nav, header, footer, aside, section, [role=dialog], [role=region]";
  const within = (e) => {
    const a = e.parentElement && e.parentElement.closest(NAMED);
    if (!a) return null;
    return a.tagName.toLowerCase() + (a.id ? "#" + a.id : classes(a).split(".").slice(0, 3).join("."));
  };
  const controls = [], unreachable = [], hidden = [];
  let modal = null;  // an open modal dialog makes the rest of the page inert: only its controls count
  try { modal = document.querySelector("dialog:modal"); } catch (e) { modal = null; }
  for (const e of document.querySelectorAll(CONTROLS)) {
    if (e.disabled || e.closest("[inert], [aria-disabled=true], fieldset:disabled")) continue;
    if (modal && !modal.contains(e)) continue;
    const rect = e.getBoundingClientRect();
    const visible = shown(e) && rect.width > 2 && rect.height > 2;
    let target = null, owner = e, how = "own";
    if (visible) {
      target = box(rect);
      for (const which of ["::before", "::after"]) {
        const p = pseudoBox(e, which, rect);
        if (!p) continue;
        const joined = join(target, p);  // "with" only when it grows the target (not a decoration inside it)
        if (joined.right - joined.left > target.right - target.left + 0.05 ||
            joined.bottom - joined.top > target.bottom - target.top + 0.05) { target = joined; how = "with " + which; }
      }
    }
    if (/^(checkbox|radio)$/.test(e.type || "") && e.labels) {  // its labels are its target too: the largest
      for (const l of e.labels) {
        if (!shown(l)) continue;
        const lb = box(l.getBoundingClientRect());
        if (size(lb) > 0 && (!target || size(lb) > size(target))) { target = lb; owner = l; how = "by its label"; }
      }
    }
    if (!target || target.right - target.left === 0 || target.bottom - target.top === 0) continue;
    const inline = e.tagName === "A" && getComputedStyle(e).display === "inline" &&
      /\S/.test([...e.parentElement.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(""));
    const part = reachable(owner, target);  // the target as far as no ancestor clips it; null: none of it
    const cut = part || target;
    const item = {sig: sig(e) + (how === "by its label" ? " (by its label)" : ""), how, inline, zone: zone(e),
                  within: within(e),
                  w: r1(cut.right - cut.left), h: r1(cut.bottom - cut.top),
                  text: short(e.getAttribute("aria-label") || e.textContent || e.getAttribute("title") || e.value || "")};
    (!part ? unreachable : covered(e, owner) ? hidden : controls).push(item);
  }
  const texts = [];
  const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "OPTION", "TITLE", "TEMPLATE", "desc", "title"]);
  const all = document.body ? document.body.querySelectorAll("*") : [];
  for (const e of all) {
    if (skip.has(e.tagName)) continue;
    let own = "";
    for (const n of e.childNodes) if (n.nodeType === 3) own += n.textContent;
    own = own.replace(/\s+/g, " ").trim();
    if (!own || !shown(e)) continue;
    const b = e.getBoundingClientRect();
    if (b.width <= 1 || b.height <= 1) continue;  // screen-reader-only text
    let fs = parseFloat(getComputedStyle(e).fontSize);
    const svg = e instanceof SVGElement;
    if (svg && e.getScreenCTM) {  // the size on the screen of SVG text in a scaled drawing
      const m = e.getScreenCTM();
      if (m) fs *= Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
    }
    texts.push({sig: sig(e) + (svg ? " (svg)" : ""), size: r1(fs), chars: own.length, text: short(own),
                zone: zone(e), within: within(e)});
  }
  // Sideways: the document wider than its viewport; apart, the elements that scroll sideways by themselves
  const doc = document.scrollingElement || document.documentElement;
  const docOver = doc.scrollWidth - doc.clientWidth;
  const scrollers = [];
  // The containers: an opaque background, a border all round, a radius of 8 px or more, a shadow ("the grey box"),
  // among the containers with a background or a border of their own; at least opts.boxMin px each way, not controls
  const alpha = (c) => {
    if (!c || c === "transparent") return 0;
    const slash = c.match(/\/\s*([\d.]+)(%?)\s*\)\s*$/);
    if (slash) return parseFloat(slash[1]) / (slash[2] ? 100 : 1);
    const parts = (c.match(/\(([^)]*)\)/) || [, ""])[1].split(",");
    return parts.length === 4 ? parseFloat(parts[3]) : 1;
  };
  const containers = {}, grey = {};
  for (const e of all) {
    const s = getComputedStyle(e);
    if (/auto|scroll/.test(s.overflowX) && e.scrollWidth - e.clientWidth > 1 && e.clientWidth > 0 && shown(e))
      scrollers.push({sig: sig(e), over: e.scrollWidth - e.clientWidth});
    if (e instanceof SVGElement || e.matches(CONTROLS)) continue;
    const b = e.getBoundingClientRect();
    if (b.width < opts.boxMin || b.height < opts.boxMin || !shown(e)) continue;
    const a = alpha(s.backgroundColor);
    const sides = ["Top", "Right", "Bottom", "Left"];
    const framed = sides.every((x) => parseFloat(s["border" + x + "Width"]) >= 1 && s["border" + x + "Style"] !== "none");
    const anyBorder = sides.some((x) => parseFloat(s["border" + x + "Width"]) >= 1 && s["border" + x + "Style"] !== "none");
    if (a === 0 && !anyBorder) continue;
    const k = sig(e);
    containers[k] = (containers[k] || 0) + 1;
    const rad = s.borderTopLeftRadius.endsWith("%") ? parseFloat(s.borderTopLeftRadius) * Math.min(b.width, b.height) / 100
      : parseFloat(s.borderTopLeftRadius);
    if (a >= 0.9 && framed && rad >= 8 && s.boxShadow !== "none") grey[k] = (grey[k] || 0) + 1;
  }
  return {controls, unreachable, covered: hidden, texts, document_over: docOver > 1 ? docOver : 0, scrollers, containers, grey,
          viewport: [innerWidth, innerHeight]};
}"""

AXE_RUN_JS = """(ms) => Promise.race([
  axe.run(document, {resultTypes: ["violations", "incomplete"]}).then((r) => {
    const pick = (list) => list.map((x) => ({id: x.id, impact: x.impact, tags: x.tags, nodes: x.nodes.length,
      example: x.nodes.length ? String(x.nodes[0].target[x.nodes[0].target.length - 1]) : ""}));
    return {violations: pick(r.violations), incomplete: pick(r.incomplete)};
  }),
  new Promise((done) => setTimeout(() => done({error: `axe.run took over ${ms} ms`}), ms))])"""

IMPACTS = ("critical", "serious", "moderate", "minor")


def recut(record: dict, controls=CONTROL_BOUNDS, text=TEXT_BOUNDS) -> dict:
    """The counts under the bounds `controls` and `text` from a state's kept sizes ("control_sizes": [signature,
    width, height, how, inline, example, zone, within]; "text_sizes": [signature, size, characters, example, zone,
    within]; zone: "credits" or "scale" of a map, else None; within: the nearest named ancestor): the controls under
    each bound by signature (links inside a sentence apart: WCAG 2.5.8 exempts them) and an example of each (the
    smallest), the text characters under each bound in all, outside a map's credits and scale, and by signature, an
    example of each. Any bounds can be asked of a kept log (`pages --summarise --controls ...`)."""
    under = {str(b): Counter() for b in controls}
    inline_under = {str(b): Counter() for b in controls}
    examples = {}
    for sig, w, h, how, inline, example, *where in record["control_sizes"]:
        sig = sig + (f" [{where[0]}]" if where and where[0] else "")  # a map's credits or scale: a signature apart
        key = sig + (" (inline link)" if inline else "")
        for b in controls:
            if min(w, h) < b:
                (inline_under if inline else under)[str(b)][sig] += 1
                if key not in examples or min(w, h) < min(examples[key]["w"], examples[key]["h"]):
                    examples[key] = {"w": w, "h": h, "text": example, "how": how,
                                     **dict(zip(("zone", "within"), where))}
    small = {str(b): Counter() for b in text}
    chars = {str(b): 0 for b in text}
    outside = {str(b): 0 for b in text}
    text_examples = {}
    for sig, size, n, example, *where in record["text_sizes"]:
        zone = where[0] if where else None
        sig = sig + (f" [{zone}]" if zone else "")
        for b in text:
            if size < b:
                small[str(b)][sig] += n
                chars[str(b)] += n
                outside[str(b)] += 0 if zone else n
                if sig not in text_examples or size < text_examples[sig]["size"]:
                    text_examples[sig] = {"size": size, "text": example, **dict(zip(("zone", "within"), where))}
    return {"controls_under": {b: dict(sorted(c.items())) for b, c in under.items()},
            "inline_links_under": {b: dict(sorted(c.items())) for b, c in inline_under.items()},
            "control_examples": dict(sorted(examples.items())),
            "text_chars_under": chars, "text_chars_under_outside_credits": outside,
            "text_under": {b: dict(sorted(c.items())) for b, c in small.items()},
            "text_examples": dict(sorted(text_examples.items()))}


def measure(page, axe_source: str | None, controls=CONTROL_BOUNDS, text=TEXT_BOUNDS) -> dict:
    """The measurements of a prepared page: its own first, axe-core's last (its run may touch the page's state). A
    failure of axe-core is recorded as the "axe" part's error; the page's own measurements stay. Every control's
    and every text's size is kept (control_sizes, text_sizes), the counts under `controls` and `text` cut from them
    (recut)."""
    raw = page.evaluate(MEASURE_JS, {"state": STATE_CLASS, "base": list(BASE_CLASSES), "boxMin": BOX_MIN})
    result = {
        "viewport": raw["viewport"],
        "controls": len(raw["controls"]),
        "control_sizes": [[c["sig"], c["w"], c["h"], c["how"], c["inline"], c["text"], c["zone"], c["within"]]
                          for c in raw["controls"]],
        "controls_grown": sum(c["how"].startswith("with ::") for c in raw["controls"]),
        "unreachable": dict(sorted(Counter(c["sig"] for c in raw["unreachable"]).items())),
        "covered": dict(sorted(Counter(c["sig"] for c in raw["covered"]).items())),
        "text_elements": len(raw["texts"]), "text_chars": sum(t["chars"] for t in raw["texts"]),
        "text_sizes": [[t["sig"], t["size"], t["chars"], t["text"], t["zone"], t["within"]] for t in raw["texts"]],
        "document_over": raw["document_over"], "scrollers": raw["scrollers"],
        "containers": dict(sorted(raw["containers"].items())), "grey_boxes": dict(sorted(raw["grey"].items())),
    }
    result.update(recut(result, controls, text))
    if axe_source is not None:
        try:
            if not page.evaluate("() => typeof axe !== 'undefined'"):
                page.add_script_tag(content=axe_source)
            result["axe"] = page.evaluate(AXE_RUN_JS, AXE_TIMEOUT_MS)
        except Exception as e:  # the state keeps its own measurements
            result["axe"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    return result


def _axe_source():
    if not os.path.exists(AXE):
        print(f"axe-core not found ({os.path.relpath(AXE, REPO)}; `npm ci` in viewer): the axe part is left out")
        return None
    return _read(AXE)


def record_of(row: dict) -> dict | None:
    """A state's record from a row of ui_shots.shoot_page: its measurements when the outcome is "done"; a row that
    "timed out" or "failed" is recorded as not measured ("error": the outcome and its reason) and counts in no total;
    a page left out on a device (a click finds nothing, a "need:" is false) as "left_out" with its reason."""
    seconds = {"load": round(sum(row[k] or 0 for k in ("load", "settle", "tiles")), 2),
               "steps": round(sum(s["seconds"] for s in row["steps"]), 2), "measure": round(row["shot"] or 0, 2)}
    record = {"page": row["page"], "device": row["device"], "theme": row["theme"]}
    if row["outcome"] == "done":
        return {**record, **row["result"], "seconds": seconds}
    if row["outcome"] == "left out":
        return {**record, "left_out": row["reason"] or "left out"}
    why = row["error"] if row["outcome"] == "failed" else "; ".join(row["timeouts"])
    return {**record, "error": f"{row['outcome']}: {why}", "seconds": seconds}


class _Logged(list):
    """shoot_all's rows: each one, as it is made, also a record (record_of) kept and written to `log` (a line of JSON)
    and printed."""

    def __init__(self, records: list, log):
        super().__init__()
        self.records, self.log = records, log

    def append(self, row):
        super().append(row)
        self.keep(record_of(row))

    def keep(self, record: dict):
        self.records.append(record)
        self.log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.log.flush()
        what = record.get("error") or ("left out, " + record["left_out"] if "left_out" in record else "measured")
        print(f"{record['page']}-{record['device']}-{record['theme']}: {what}", flush=True)


def measure_all(pw, site: dict, shown: list, devices: list, themes: list, axe_source: str | None, log,
                times: dict | None = None, passes: list | None = None, dropped: dict | None = None) -> list:
    """Every page of `shown` measured through ui_shots.shoot_all (its passes, pages, waits and steps; `act` in place
    of the screenshot) in contexts that bypass the CSP; each record also written to `log` as it ends. A page whose
    loading, steps or measuring raise, or whose wait timed out, is recorded as not measured and the pass goes on.
    `site`: ui_shots' dict (url, cookies, run, share, line, also, border). `dropped`: the pages the run lacks the
    feature of (ui_shots.left_out_by_run: page -> reason), recorded as left out on every device and theme first."""
    import ui_shots
    records = []
    rows = _Logged(records, log)
    for device in devices:
        for theme in themes:
            for name, reason in (dropped or {}).items():
                rows.keep({"page": name, "device": device, "theme": theme, "left_out": reason})
    ui_shots.shoot_all(pw, site, shown, devices, themes, None, False, {} if times is None else times, rows,
                       [] if passes is None else passes,
                       act=lambda page, name, device, theme: measure(page, axe_source), bypass_csp=True)
    return records


def run_pages(out: str, only: str, devices: list, dark: bool, data_dir: str | None) -> list:
    """The site of tools/ui_shots.py set up (serve; its data folder a temporary one named for tools/clean_temp.py
    unless `data_dir`, one run at a time per data folder), the pages chosen as ui_shots.main chooses them (those the
    run lacks the feature of left out first), every state measured (pages-states.jsonl; the set-up's and passes'
    seconds in pages-run.json), the site stopped and the temporary folder removed."""
    import ui_shots
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    axe_source = _axe_source()
    data = data_dir or tempfile.mkdtemp(prefix=TEMP_PREFIX)
    stop = None
    times, passes, dropped = {}, [], {}
    try:
        url, cookies, run, share, stop = ui_shots.serve(data, times=times)
        site = {"url": url, "cookies": cookies, "run": run, "share": share, "line": ui_shots.first_line(data, run),
                "also": ";".join(ui_shots.first_line(data, run, k) for k in (40, 200)),
                "border": ui_shots.border_view(data)}
        pages = ui_shots.select_pages(only)
        dropped = ui_shots.left_out_by_run(pages, ui_shots.run_features(os.path.join(data, "runs", run)))
        for name, reason in dropped.items():
            print(f"{name}: left out, {reason}")
        shown = [name for name in pages if name not in dropped]
        themes = ["light", "dark"] if dark else ["light"]
        with sync_playwright() as pw, open(os.path.join(out, "pages-states.jsonl"), "w", encoding="utf-8") as log:
            return measure_all(pw, site, shown, devices, themes, axe_source, log, times, passes, dropped)
    finally:
        if stop:
            stop()
        if not data_dir:
            import gc
            gc.collect()  # SQLite connections left in reference cycles keep their files open on Windows
            shutil.rmtree(data, ignore_errors=True)
        with open(os.path.join(out, "pages-run.json"), "w", encoding="utf-8") as f:
            json.dump({"setup": times, "passes": passes, "left_out_by_run": dropped}, f, indent=1)


# The pages' families in the summary, by the prefix of their names (a page in the first that fits; the app's other
# pages in "the app"): never by a word inside a name ("c-new-coverage" is the app's, "map-layers" a run's map)
FAMILIES = (("coverage page", ("page-coverage",)), ("layer explorer", ("c-layer",)), ("3D view", ("view3d",)),
            ("run's map", ("map",)), ("other pages", ("page-",)), ("the app", ("",)))


def family_of(page: str) -> str:
    return next(name for name, prefixes in FAMILIES if page.startswith(prefixes))


def _families(ok: list, controls, text) -> dict:
    """Per family (FAMILIES) of the measured states: states, controls, those under each bound, text characters and
    those under each bound."""
    out = {}
    for name, _ in FAMILIES:
        rs = [r for r in ok if family_of(r["page"]) == name]
        if not rs:
            continue
        out[name] = {"states": len(rs), "controls": sum(r["controls"] for r in rs),
                     **{f"controls_under_{b}": sum(sum(r["controls_under"][str(b)].values()) for r in rs)
                        for b in controls},
                     "text_chars": sum(r["text_chars"] for r in rs),
                     **{f"text_chars_under_{b}": sum(r["text_chars_under"][str(b)] for r in rs) for b in text}}
    return out


def _left_out(records: list) -> dict:
    """The states left out: "page | reason" -> the devices and themes, in the records' order."""
    out = {}
    for r in records:
        if "left_out" in r:
            out.setdefault(f"{r['page']} | {r['left_out']}", []).append(f"{r['device']} {r['theme']}")
    return out


def _axe_ok(r: dict) -> bool:
    return "axe" in r and "error" not in r["axe"]


def summarise(records: list, controls=CONTROL_BOUNDS, text=TEXT_BOUNDS) -> dict:
    """Per device and theme the totals; the lists de-duplicated by signature over all states, most frequent first.
    The counts under `controls` and `text` are cut anew from the records' kept sizes (recut); records of earlier
    versions, without sizes, are read as they are (their "sideways": the scrolling elements) and only with the
    bounds they were cut at."""
    if any("control_sizes" not in r for r in records if "controls" in r) and \
            (tuple(controls), tuple(text)) != (CONTROL_BOUNDS, TEXT_BOUNDS):
        raise SystemExit("the log keeps no sizes (a pass before they were kept): only the default bounds")
    records = [{**r, **recut(r, controls, text)} if "control_sizes" in r else r for r in records]
    groups = defaultdict(list)
    for r in records:
        groups[f"{r['device']} {r['theme']}"].append(r)
    scrollers = lambda r: r.get("scrollers", r.get("sideways", []))  # noqa: E731
    per = {}
    for key, rs in groups.items():
        ok = [r for r in rs if r.get("page") and "error" not in r and "left_out" not in r]
        row = {"states": len(ok), "errors": [f"{r.get('page')}: {r['error']}" for r in rs if "error" in r],
               "left_out": sorted(f"{r['page']}: {r['left_out']}" for r in rs if "left_out" in r),
               "controls": sum(r["controls"] for r in ok),
               "controls_unreachable": sum(sum(r.get("unreachable", {}).values()) for r in ok),
               "controls_covered": sum(sum(r.get("covered", {}).values()) for r in ok),
               "controls_grown": sum(r.get("controls_grown", 0) for r in ok)}
        for b in controls:
            row[f"controls_under_{b}"] = sum(sum(r["controls_under"][str(b)].values()) for r in ok)
            row[f"control_signatures_under_{b}"] = len({s for r in ok for s in r["controls_under"][str(b)]})
            # links inside a sentence apart (WCAG 2.5.8 exempts them); "with" them: the count of before
            row[f"inline_links_under_{b}"] = sum(sum(r.get("inline_links_under", {}).get(str(b), {}).values())
                                                 for r in ok)
            row[f"controls_under_{b}_with_inline"] = row[f"controls_under_{b}"] + row[f"inline_links_under_{b}"]
        chars = sum(r["text_chars"] for r in ok)
        row["text_chars"] = chars
        for b in text:
            n = sum(r["text_chars_under"][str(b)] for r in ok)
            row[f"text_chars_under_{b}"] = n
            row[f"text_share_under_{b}"] = round(n / chars, 4) if chars else None
            m = sum(r.get("text_chars_under_outside_credits", {}).get(str(b), 0) for r in ok)  # a map's credits, scale
            row[f"text_chars_under_{b}_outside_credits"] = m
            row[f"text_share_under_{b}_outside_credits"] = round(m / chars, 4) if chars else None
        row["states_document_sideways"] = sorted(r["page"] for r in ok if r["document_over"])
        row["states_with_scrollers"] = sorted(r["page"] for r in ok if scrollers(r))
        row["containers"] = sum(sum(r.get("containers", {}).values()) for r in ok)
        row["grey_boxes"] = sum(sum(r.get("grey_boxes", {}).values()) for r in ok)
        with_axe = [r for r in ok if _axe_ok(r)]
        row["axe_states"] = len(with_axe)
        row["axe_missing"] = len(ok) - len(with_axe)
        row["axe_errors"] = sorted(f"{r['page']}: {r['axe']['error']}" for r in ok if "axe" in r and not _axe_ok(r))
        for kind in ("violations", "incomplete"):
            row[f"axe_{kind}_nodes"] = {i: sum(x["nodes"] for r in with_axe for x in r["axe"][kind] if x["impact"] == i)
                                        for i in IMPACTS}
            row[f"axe_{kind}_rules"] = {i: len({x["id"] for r in with_axe for x in r["axe"][kind] if x["impact"] == i})
                                        for i in IMPACTS}
        row["families"] = _families(ok, controls, text)
        per[key] = row

    ok = [r for r in records if r.get("page") and "error" not in r and "left_out" not in r]

    def dedup(get) -> list:
        rows = {}
        for r in ok:
            for sig, n, example in get(r):
                row = rows.setdefault(sig, {"signature": sig, "states": 0, "count": 0, "devices": set(),
                                            "pages": set(), "example": example})
                row["states"] += 1
                row["count"] += n
                row["devices"].add(r["device"])
                row["pages"].add(r["page"])
        out = sorted(rows.values(), key=lambda x: (-x["states"], -x["count"], x["signature"]))
        for row in out:
            row["devices"], row["pages"] = sorted(row["devices"]), len(row["pages"])
        return out

    phones = lambda r: r["device"] != "desktop"  # noqa: E731
    desktop = lambda r: r["device"] == "desktop"  # noqa: E731
    lists = {}
    for b in controls:
        for scope, keep in (("phones", phones), ("desktop", desktop)):
            lists[f"controls_under_{b}_{scope}"] = dedup(lambda r, b=b, keep=keep: [
                (s, n, r["control_examples"].get(s)) for s, n in r["controls_under"][str(b)].items()] if keep(r) else [])
            lists[f"inline_links_under_{b}_{scope}"] = dedup(lambda r, b=b, keep=keep: [
                (s, n, r["control_examples"].get(s + " (inline link)"))
                for s, n in r.get("inline_links_under", {}).get(str(b), {}).items()] if keep(r) else [])
    for b in text:
        lists[f"text_under_{b}"] = dedup(lambda r, b=b: [(s, n, r["text_examples"].get(s))
                                                          for s, n in r["text_under"][str(b)].items()])
    lists["document_sideways"] = dedup(lambda r: [("(the document)", r["document_over"], None)] if r["document_over"]
                                       else [])
    lists["scrollers"] = dedup(lambda r: [(s["sig"], s["over"], None) for s in scrollers(r)])
    lists["unreachable"] = dedup(lambda r: [(s, n, None) for s, n in r.get("unreachable", {}).items()])
    lists["covered"] = dedup(lambda r: [(s, n, None) for s, n in r.get("covered", {}).items()])
    lists["grey_boxes"] = dedup(lambda r: [(s, n, None) for s, n in r.get("grey_boxes", {}).items()])
    lists["containers"] = dedup(lambda r: [(s, n, None) for s, n in r.get("containers", {}).items()])
    axe_rows = {}
    for r in ok:
        if not _axe_ok(r):
            continue
        for kind in ("violations", "incomplete"):
            for x in r["axe"][kind]:
                row = axe_rows.setdefault((kind, x["id"]), {"kind": kind, "rule": x["id"], "impact": x["impact"],
                                                           "wcag": any(t.startswith("wcag") for t in x["tags"]),
                                                           "states": 0, "nodes": 0, "example": x["example"]})
                row["states"] += 1
                row["nodes"] += x["nodes"]
    lists["axe"] = sorted(axe_rows.values(), key=lambda x: (x["kind"] != "violations", IMPACTS.index(x["impact"])
                                                             if x["impact"] in IMPACTS else 9, -x["states"], x["rule"]))
    seconds = [{"state": f"{r['page']}-{r['device']}-{r['theme']}", **r["seconds"],
                "total": round(sum(r["seconds"].values()), 2)} for r in records if r.get("page") and "seconds" in r]
    seconds.sort(key=lambda x: (-x["total"], x["state"]))
    return {"per_device_theme": dict(sorted(per.items())), "lists": lists, "seconds_slowest": seconds[:10],
            "seconds_total": round(sum(s["total"] for s in seconds), 1),
            "states": len(ok),  # measured: neither failed nor left out (a failed state also has its seconds)
            "states_failed": sum(1 for r in records if "error" in r),
            "states_left_out": sum(1 for r in records if "left_out" in r),
            "left_out": _left_out(records),
            "bounds": {"controls": list(controls), "text": list(text), "box_min": BOX_MIN}}


def pages_markdown(s: dict) -> str:
    cs, ts = s["bounds"]["controls"], s["bounds"]["text"]
    columns = (["Device, theme", "States", "Controls (unreachable / covered apart)"]
               + [x for b in cs for x in (f"Under {b} px (signatures)", f"Links in a sentence under {b} px")]
               + ["Text chars"] + [f"Text under {b} px (outside a map's credits and scale)" for b in ts]
               + ["Document sideways / states with elements scrolling sideways", "Grey boxes / containers",
                  "axe violations: nodes (rules) crit / serious / moderate / minor", "axe incomplete: nodes",
                  "No axe result", "Errors"])
    out = ["# UI metrics: pages", "", f"{s['states']} states measured, {s.get('states_failed', 0)} failed, "
           f"{s.get('states_left_out', 0)} left out; seconds in "
           f"all {s['seconds_total']} (indicative: the shared lock, other sessions).", "",
           "| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    for key, r in s["per_device_theme"].items():
        v = " / ".join(f"{r['axe_violations_nodes'][i]} ({r['axe_violations_rules'][i]})" for i in IMPACTS)
        inc = " / ".join(str(r["axe_incomplete_nodes"][i]) for i in IMPACTS)
        pct = lambda b: f"{r[f'text_chars_under_{b}']} ({(r[f'text_share_under_{b}'] or 0) * 100:.1f} %)"  # noqa: E731
        cells = ([key, r["states"], f"{r['controls']} ({r['controls_unreachable']} / {r.get('controls_covered', 0)})"]
                 + [x for b in cs for x in (f"{r[f'controls_under_{b}']} ({r[f'control_signatures_under_{b}']})",
                                            r.get(f"inline_links_under_{b}", 0))]
                 + [r["text_chars"]] + [f"{pct(b)} ({r.get(f'text_chars_under_{b}_outside_credits', '–')})"
                                        for b in ts]
                 + [f"{len(r['states_document_sideways'])} / {len(r['states_with_scrollers'])}",
                    f"{r['grey_boxes']} / {r['containers']}", v, inc, r["axe_missing"], len(r["errors"])])
        out.append("| " + " | ".join(str(c) for c in cells) + " |")

    def rows(name: str, title: str, example) -> None:
        items = s["lists"].get(name, [])
        out.extend(["", f"## {title} ({len(items)} signatures; top {TOP})", "",
                    "| Signature | States | Count | Devices | Example |", "| --- | --- | --- | --- | --- |"])
        for x in items[:TOP]:
            out.append(f"| `{x['signature'][:90]}` | {x['states']} | {x['count']} | {', '.join(x['devices'])} | "
                       f"{example(x['example'])} |")
    ctl = lambda e: (f"{e['w']}×{e['h']} “{e['text'].replace('|', '¦')}”"  # noqa: E731
                     + (f" ({e['how']})" if e.get("how", "own") != "own" else "")) if e else ""
    txt = lambda e: f"{e['size']} px “{e['text'].replace('|', '¦')}”" if e else ""  # noqa: E731

    for b in cs:
        rows(f"controls_under_{b}_phones", f"Controls under {b} px on the phones", ctl)
        rows(f"controls_under_{b}_desktop", f"Controls under {b} px on the desktop", ctl)
        rows(f"inline_links_under_{b}_phones", f"Links in a sentence under {b} px on the phones (apart)", ctl)
        rows(f"inline_links_under_{b}_desktop", f"Links in a sentence under {b} px on the desktop (apart)", ctl)
    rows("unreachable", "Controls that cannot be reached (not counted above)", lambda e: "")
    rows("covered", "Controls covered by another element at their centre (not counted above)", lambda e: "")
    for b in ts:
        rows(f"text_under_{b}", f"Text under {b} px (count: characters)", txt)
    rows("document_sideways", "The document wider than its viewport (count: px over, summed)", lambda e: "")
    rows("scrollers", "Elements that scroll sideways by themselves (count: px over, summed)", lambda e: "")
    rows("grey_boxes", f"Grey boxes as rendered (opaque background, border, radius ≥ 8 px, shadow; ≥ {BOX_MIN} px)",
         lambda e: "")
    rows("containers", f"Containers with a background or border of their own (≥ {BOX_MIN} px)", lambda e: "")
    out += ["", "## axe-core rules", "", "| Kind | Rule | Impact | WCAG | States | Nodes | Example |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    out += [f"| {x['kind']} | {x['rule']} | {x['impact']} | {'yes' if x['wcag'] else ''} | {x['states']} | {x['nodes']} | "
            f"`{x['example'][:70]}` |" for x in s["lists"]["axe"]]
    out += ["", "## Slowest states (seconds)", "", "| State | Load | Steps | Measure | Total |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {x['state']} | {x['load']} | {x['steps']} | {x['measure']} | {x['total']} |" for x in s["seconds_slowest"]]
    if any(r.get("families") for r in s["per_device_theme"].values()):
        heads = (["Device, theme", "Family", "States", "Controls"] + [f"Under {b} px" for b in cs] + ["Text chars"]
                 + [f"Text under {b} px" for b in ts])
        out += ["", "## Page families (by the prefix of a page's name: page-coverage, c-layer, view3d, map, page-, "
                "the rest the app)", "", "| " + " | ".join(heads) + " |", "|" + " --- |" * len(heads)]
        for key, r in s["per_device_theme"].items():
            for name, f in r.get("families", {}).items():
                cells = ([key, name, f["states"], f["controls"]] + [f[f"controls_under_{b}"] for b in cs]
                         + [f["text_chars"]] + [f[f"text_chars_under_{b}"] for b in ts])
                out.append("| " + " | ".join(str(c) for c in cells) + " |")
    if s.get("left_out"):
        out += ["", f"## Left out ({s['states_left_out']} states: the run or the device does not show them)", ""]
        out += [f"- {page}: {reason} ({', '.join(where)})" for (page, reason), where in
                ((tuple(k.split(" | ", 1)), v) for k, v in s["left_out"].items())]
    errors = [e for r in s["per_device_theme"].values() for e in r["errors"] + [f"axe: {p}" for p in r["axe_errors"]]]
    if errors:
        out += ["", "## Errors", ""] + [f"- {e}" for e in errors]
    return "\n".join(out) + "\n"


def _write(out: str, name: str, data, markdown: str):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    with open(os.path.join(out, name + ".md"), "w", encoding="utf-8") as f:
        f.write(markdown)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("static", help="counts from the source")
    s.add_argument("--out", required=True)
    s.add_argument("--chars", default=ICON_CHARS, help="the characters used as icons or joints")
    s.add_argument("--radius", type=float, default=8, help="the radius (px) of 'the same grey box' at least")
    s.add_argument("--with-demos", action="store_true", help="count the characters of the demo pages too")
    p = sub.add_parser("pages", help="measurements of the rendered states of tools/ui_shots.py")
    p.add_argument("--out", required=True)
    p.add_argument("--only", default="", help="pages whose name contains this (comma-separated)")
    p.add_argument("--devices", default="desktop,iphone,pixel", help="of: desktop, iphone, pixel")
    p.add_argument("--dark", action="store_true", help="the dark theme too")
    p.add_argument("--data-dir", help="a scratch data folder (default: a new temporary one, removed at the end)")
    p.add_argument("--summarise", action="store_true", help="only the summary again, from --out's pages-states.jsonl")
    p.add_argument("--controls", default=",".join(map(str, CONTROL_BOUNDS)),
                   help="the bounds of the controls, px (comma-separated)")
    p.add_argument("--text", default=",".join(map(str, TEXT_BOUNDS)), help="the bounds of the text, px (comma-separated)")
    args = parser.parse_args(argv)
    if args.command == "static":
        result = static(REPO, args.chars, args.radius, args.with_demos)
        _write(args.out, "static", result, static_markdown(result))
        print(os.path.join(args.out, "static.md"))
        return
    if args.summarise:
        with open(os.path.join(args.out, "pages-states.jsonl"), encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    else:
        records = run_pages(args.out, args.only, args.devices.split(","), args.dark, args.data_dir)
    number = lambda v: int(v) if float(v).is_integer() else float(v)  # noqa: E731
    controls = tuple(number(v) for v in args.controls.split(",") if v)
    text = tuple(number(v) for v in args.text.split(",") if v)
    summary = summarise(records, controls, text)
    # other bounds than the defaults: a summary of their own beside pages.json/.md
    name = "pages" if (controls, text) == (CONTROL_BOUNDS, TEXT_BOUNDS) else \
        "pages-c" + "-".join(map(str, controls)) + "-t" + "-".join(map(str, text))
    _write(args.out, name, summary, pages_markdown(summary))
    print(os.path.join(args.out, name + ".md"))


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    main()
