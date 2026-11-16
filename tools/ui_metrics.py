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
merged per selector); the characters used as icons or joints (ICON_CHARS) in the code (comments left out), in CSS
`content:` and in locales/en.json, and the "dense strings" (two of them or more, or a "·" joint); the texts of
locales/en.json by group (words per text) and the .tsx files that hold English text in code without calling t(. CSS
is read by a small scanner of this file (no CSS parser is installed and none may be added for this tool).

"pages" renders every state of tools/ui_shots.py's PAGES the way that tool does (its prepared_pages: the same site,
users, waits and steps) and measures each one just where the screenshot would be taken (pages-states.jsonl, one line
a state as it ends; then pages.json, pages.md): the visible, enabled controls and their boxes (under 44 px and 24 px,
WCAG 2.5.8's size; a visually hidden checkbox or radio is measured by its label's box), the visible text and its
rendered font size (under 12, 11, 10 px, as shares of the visible characters; SVG text scaled to the screen), sideways
scroll of the document or a scrolling panel, axe-core's violations and "incomplete" results by impact, and the
seconds of loading, steps and measuring (indicative only: the test lock's shared lane, other sessions).

axe-core comes from viewer/node_modules/axe-core/axe.min.js (a development dependency of viewer/package.json; `npm
ci` in viewer); without it the axe part is left out with a note. The app's pages forbid inline script and eval
(CSP `script-src 'self'`), so axe-core cannot be put into them as they are served: this tool's browser contexts are
opened with Playwright's bypass_csp, which tools/ui_shots.py's never are. With the CSP bypassed a page could apply
what the CSP would block (inline styles): the viewer has none (.claude/rules/viewer.md), so the pages look the same.

The keys of the user's services (ESRI_API_KEY, DATAFORDELER_API_KEY) are best removed from the environment of
"pages": the clip's run shows no Esri imagery without them.
"""

import argparse
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
    for token in _split_top(value.replace(",", " , "), " "):
        if token == ",":
            break  # the family list begins
        m = SIZE.match(token)
        if m:
            return m.group(1)
    return None


def _px(value: str):
    m = re.match(r"^(-?\d*\.?\d+)px$", value)
    return float(m.group(1)) if m else None


COLOUR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?)\([^()]*\)")


def _colour(value: str) -> str:
    return " ".join(value.lower().split())


def _is_mono(prop: str, value: str) -> bool:
    return prop in ("font", "font-family") and ("var(--mono)" in value or "monospace" in value.lower())


def _decode_css(value: str) -> str:
    """CSS escapes (\\25be) decoded."""
    return re.sub(r"\\([0-9a-fA-F]{1,6})\s?", lambda m: chr(int(m.group(1), 16)), value)


def strip_comments(text: str) -> str:
    """JavaScript or TypeScript with its comments made spaces (lines kept): strings (', " and ` with ${} inside),
    regular expressions (after an operator or a keyword) and JSX text are left as they are. A quote in JSX text
    ("don't") is taken as a string to the end of its line, never further."""
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
        if c == "/" and text.startswith("//", i):
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
        # a regular expression after an operator or a keyword (not after "<": a closing tag)
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%>~^"
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


def static(root: str = REPO, chars: str = ICON_CHARS, radius_min: float = 8) -> dict:
    """The counts of "static" for the tree at `root` (viewer/src, locales/en.json)."""
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
    in_code, dense = [], []
    for path in code_files:
        name = _rel(path, root)
        for number, line in enumerate(strip_comments(_read(path)).split("\n"), 1):
            found = [c for c in line if c in chars]
            if not found:
                continue
            for c in found:
                in_code.append({"file": name, "line": number, "char": c})
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
        "chars_in_code": in_code, "chars_in_css_content": content_chars, "chars_in_catalogue": in_catalogue,
        "chars_count": {c: {"code": sum(x["char"] == c for x in in_code),
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
            "| Selector | Files | Surface | Border | Radius | Shadow |", "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| `{b['selector'][:80]}` | {', '.join(os.path.basename(f) for f in b['files'])} | "
            + " | ".join("x" if b[k] else "" for k in ("surface", "border", "radius", "shadow")) + " |" for b in r["boxes"]]
    out += ["", "## Characters as icons or joints", "", "| Char | Code | CSS content | Catalogue |",
            "| --- | --- | --- | --- |"]
    out += [f"| {c} | {n['code']} | {n['css']} | {n['catalogue']} |" for c, n in r["chars_count"].items()]
    out += ["", "Places in the code: " + "; ".join(f"{x['file']}:{x['line']} {x['char']}" for x in r["chars_in_code"]),
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

# One evaluation per state: the controls, the text, sideways scroll (opts: the bounds)
MEASURE_JS = r"""(opts) => {
  const CONTROLS = "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], " +
    "[role=menuitem], [role=option], [role=radio], [role=switch], [role=slider], [role=checkbox], [role=link]";
  const shown = (e) => e.checkVisibility({visibilityProperty: true, opacityProperty: true});
  const classes = (e) => [...e.classList].filter((c) => !/\d{3,}/.test(c)).sort().map((c) => "." + c).join("");
  const sig = (e) => e.tagName.toLowerCase() + (e.getAttribute("role") ? `[role=${e.getAttribute("role")}]` : "") +
    (e.tagName === "INPUT" ? `[type=${e.type}]` : "") + classes(e);
  const short = (s) => s.replace(/\s+/g, " ").trim().slice(0, 50);
  const r1 = (v) => Math.round(v * 10) / 10;
  const controls = [];
  let modal = null;  // an open modal dialog makes the rest of the page inert: only its controls count
  try { modal = document.querySelector("dialog:modal"); } catch (e) { modal = null; }
  for (const e of document.querySelectorAll(CONTROLS)) {
    if (e.disabled || e.closest("[inert], [aria-disabled=true], fieldset:disabled")) continue;
    if (modal && !modal.contains(e)) continue;
    let box = e.getBoundingClientRect(), hidden = false;
    const tiny = box.width <= 2 || box.height <= 2;
    if (!shown(e) || tiny) {
      // a visually hidden checkbox or radio (u-sr, opacity 0) is taken by its label: the label's box
      const label = e.labels && [...e.labels].find((l) => shown(l) && l.getBoundingClientRect().width > 2);
      if (!label || !/^(checkbox|radio)$/.test(e.type || "")) continue;
      box = label.getBoundingClientRect();
      hidden = true;
    }
    if (box.width === 0 || box.height === 0) continue;
    const inline = e.tagName === "A" && getComputedStyle(e).display === "inline" &&
      /\S/.test([...e.parentElement.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(""));
    controls.push({sig: sig(e) + (hidden ? " (by its label)" : ""), w: r1(box.width), h: r1(box.height), inline,
                   text: short(e.getAttribute("aria-label") || e.textContent || e.getAttribute("title") || e.value || "")});
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
    const box = e.getBoundingClientRect();
    if (box.width <= 1 || box.height <= 1) continue;  // screen-reader-only text
    let size = parseFloat(getComputedStyle(e).fontSize);
    const svg = e instanceof SVGElement;
    if (svg && e.getScreenCTM) {  // the size on the screen of SVG text in a scaled drawing
      const m = e.getScreenCTM();
      if (m) size *= Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
    }
    texts.push({sig: sig(e) + (svg ? " (svg)" : ""), size: r1(size), chars: own.length, text: short(own)});
  }
  const sideways = [];
  const doc = document.scrollingElement || document.documentElement;
  const docOver = doc.scrollWidth - doc.clientWidth;
  for (const e of all) {
    const s = getComputedStyle(e);
    if (!/auto|scroll/.test(s.overflowY) || !/auto|scroll/.test(s.overflowX) || !shown(e)) continue;
    const over = e.scrollWidth - e.clientWidth;
    if (over > 1 && e.clientWidth > 0) sideways.push({sig: sig(e), over: over});
  }
  return {controls, texts, document_over: docOver > 1 ? docOver : 0, sideways,
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


def measure(page, axe_source: str | None, controls=CONTROL_BOUNDS, text=TEXT_BOUNDS) -> dict:
    """The measurements of a prepared page: its own first, axe-core's last (its run may touch the page's state)."""
    raw = page.evaluate(MEASURE_JS)
    under = {b: Counter() for b in controls}
    examples = {}
    for c in raw["controls"]:
        for b in controls:
            if min(c["w"], c["h"]) < b:
                key = c["sig"] + (" (inline link)" if c["inline"] else "")
                under[b][key] += 1
                if key not in examples or min(c["w"], c["h"]) < min(examples[key]["w"], examples[key]["h"]):
                    examples[key] = {"w": c["w"], "h": c["h"], "text": c["text"]}
    total_chars = sum(t["chars"] for t in raw["texts"])
    small = {b: Counter() for b in text}
    small_chars = {b: 0 for b in text}
    text_examples = {}
    for t in raw["texts"]:
        for b in text:
            if t["size"] < b:
                small[b][t["sig"]] += t["chars"]
                small_chars[b] += t["chars"]
                if t["sig"] not in text_examples or t["size"] < text_examples[t["sig"]]["size"]:
                    text_examples[t["sig"]] = {"size": t["size"], "text": t["text"]}
    result = {
        "viewport": raw["viewport"],
        "controls": len(raw["controls"]),
        "controls_under": {str(b): dict(sorted(under[b].items())) for b in controls},
        "control_examples": dict(sorted(examples.items())),
        "text_elements": len(raw["texts"]), "text_chars": total_chars,
        "text_chars_under": {str(b): small_chars[b] for b in text},
        "text_under": {str(b): dict(sorted(small[b].items())) for b in text},
        "text_examples": dict(sorted(text_examples.items())),
        "document_over": raw["document_over"], "sideways": raw["sideways"],
    }
    if axe_source is not None:
        if not page.evaluate("() => typeof axe !== 'undefined'"):
            page.add_script_tag(content=axe_source)
        result["axe"] = page.evaluate(AXE_RUN_JS, AXE_TIMEOUT_MS)
    return result


def _axe_source():
    if not os.path.exists(AXE):
        print(f"axe-core not found ({os.path.relpath(AXE, REPO)}; `npm ci` in viewer): the axe part is left out")
        return None
    return _read(AXE)


def run_pages(out: str, only: str, devices: list, dark: bool, data_dir: str | None) -> list:
    """Every state measured; each written to pages-states.jsonl as it ends. The states' records."""
    import ui_shots
    from playwright.sync_api import sync_playwright

    os.makedirs(out, exist_ok=True)
    axe_source = _axe_source()
    data = data_dir or tempfile.mkdtemp(prefix="ui-metrics-")
    site, cookies, run, share, stop = ui_shots.serve(data)
    line = ui_shots.first_line(data, run)
    also = ";".join(ui_shots.first_line(data, run, k) for k in (40, 200))
    border = ui_shots.border_view(data)
    wanted = [w for w in only.split(",") if w]
    pages = {n: p for n, p in ui_shots.PAGES.items() if not wanted or any(w in n for w in wanted)}
    themes = ["light", "dark"] if dark else ["light"]
    records = []
    path = os.path.join(out, "pages-states.jsonl")
    try:
        with sync_playwright() as pw, open(path, "w", encoding="utf-8") as log:
            for device in devices:
                for theme in themes:  # one slice each: a failure in the loop costs this slice only
                    try:
                        for shown in ui_shots.prepared_pages(pw, site, cookies, run, share, line, also, border, pages,
                                                             [device], [theme], {"bypass_csp": True}):
                            began = time.monotonic()
                            record = {"page": shown.name, "device": device, "theme": theme}
                            try:
                                record.update(measure(shown.page, axe_source))
                            except Exception as e:  # recorded, the pass goes on
                                record["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                            record["seconds"] = {**{k: round(v, 2) for k, v in shown.seconds.items()},
                                                 "measure": round(time.monotonic() - began, 2)}
                            records.append(record)
                            log.write(json.dumps(record, ensure_ascii=False) + "\n")
                            log.flush()
                            print(f"{shown.name}-{device}-{theme}: " + (record.get("error") or "measured"), flush=True)
                    except Exception as e:
                        note = {"page": None, "device": device, "theme": theme,
                                "error": f"the slice stopped: {type(e).__name__}: {str(e)[:300]}"}
                        records.append(note)
                        log.write(json.dumps(note, ensure_ascii=False) + "\n")
                        log.flush()
                        print(note["error"], flush=True)
    finally:
        stop()
        if not data_dir:
            import gc
            gc.collect()
            shutil.rmtree(data, ignore_errors=True)
    return records


def summarise(records: list, controls=CONTROL_BOUNDS, text=TEXT_BOUNDS) -> dict:
    """Per device and theme the totals; the lists de-duplicated by signature over all states, most frequent first."""
    groups = defaultdict(list)
    for r in records:
        groups[f"{r['device']} {r['theme']}"].append(r)
    per = {}
    for key, rs in groups.items():
        ok = [r for r in rs if r.get("page") and "error" not in r]
        row = {"states": len(ok), "errors": [f"{r.get('page')}: {r['error']}" for r in rs if "error" in r],
               "controls": sum(r["controls"] for r in ok)}
        for b in controls:
            row[f"controls_under_{b}"] = sum(sum(r["controls_under"][str(b)].values()) for r in ok)
            row[f"control_signatures_under_{b}"] = len({s for r in ok for s in r["controls_under"][str(b)]})
        chars = sum(r["text_chars"] for r in ok)
        row["text_chars"] = chars
        for b in text:
            n = sum(r["text_chars_under"][str(b)] for r in ok)
            row[f"text_chars_under_{b}"] = n
            row[f"text_share_under_{b}"] = round(n / chars, 4) if chars else None
        row["states_document_sideways"] = sorted(r["page"] for r in ok if r["document_over"])
        row["states_panel_sideways"] = sorted(r["page"] for r in ok if r["sideways"])
        with_axe = [r for r in ok if "axe" in r and "error" not in r["axe"]]
        row["axe_states"] = len(with_axe)
        row["axe_errors"] = sorted(r["page"] for r in ok if "axe" in r and "error" in r["axe"])
        for kind in ("violations", "incomplete"):
            row[f"axe_{kind}_nodes"] = {i: sum(x["nodes"] for r in with_axe for x in r["axe"][kind] if x["impact"] == i)
                                        for i in IMPACTS}
            row[f"axe_{kind}_rules"] = {i: len({x["id"] for r in with_axe for x in r["axe"][kind] if x["impact"] == i})
                                        for i in IMPACTS}
        per[key] = row

    ok = [r for r in records if r.get("page") and "error" not in r]

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

    lists = {}
    for b in controls:
        for scope, keep in (("phones", lambda r: r["device"] != "desktop"), ("desktop", lambda r: r["device"] == "desktop")):
            lists[f"controls_under_{b}_{scope}"] = dedup(lambda r, b=b, keep=keep: [
                (s, n, r["control_examples"].get(s)) for s, n in r["controls_under"][str(b)].items()] if keep(r) else [])
            lists[f"controls_under_{b}_{scope}"] = [x for x in lists[f"controls_under_{b}_{scope}"] if x["states"]]
    for b in text:
        lists[f"text_under_{b}"] = dedup(lambda r, b=b: [(s, n, r["text_examples"].get(s))
                                                          for s, n in r["text_under"][str(b)].items()])
    lists["sideways"] = dedup(lambda r: [(s["sig"], s["over"], None) for s in r["sideways"]]
                              + ([("(the document)", r["document_over"], None)] if r["document_over"] else []))
    axe_rows = {}
    for r in ok:
        if "axe" not in r or "error" in r["axe"]:
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
            "seconds_total": round(sum(s["total"] for s in seconds), 1), "states": len(seconds),
            "bounds": {"controls": list(controls), "text": list(text)}}


def pages_markdown(s: dict) -> str:
    c1, c2 = s["bounds"]["controls"]
    t1, t2, t3 = s["bounds"]["text"]
    out = ["# UI metrics: pages", "", f"{s['states']} states measured; seconds in all {s['seconds_total']} "
           "(indicative: the shared lock, other sessions).", "",
           f"| Device, theme | States | Controls | Under {c1} px (signatures) | Under {c2} px (signatures) | "
           f"Text chars | Under {t1} px | Under {t2} | Under {t3} | Sideways (document / panel) | axe violations: "
           "nodes (rules) crit / serious / moderate / minor | axe incomplete: nodes | Errors |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for key, r in s["per_device_theme"].items():
        v = " / ".join(f"{r['axe_violations_nodes'][i]} ({r['axe_violations_rules'][i]})" for i in IMPACTS)
        inc = " / ".join(str(r["axe_incomplete_nodes"][i]) for i in IMPACTS)
        pct = lambda b: f"{r[f'text_chars_under_{b}']} ({(r[f'text_share_under_{b}'] or 0) * 100:.1f} %)"  # noqa: E731
        out.append(f"| {key} | {r['states']} | {r['controls']} | {r[f'controls_under_{c1}']} "
                   f"({r[f'control_signatures_under_{c1}']}) | {r[f'controls_under_{c2}']} "
                   f"({r[f'control_signatures_under_{c2}']}) | {r['text_chars']} | {pct(t1)} | {pct(t2)} | {pct(t3)} | "
                   f"{len(r['states_document_sideways'])} / {len(r['states_panel_sideways'])} | {v} | {inc} | "
                   f"{len(r['errors']) + len(r['axe_errors'])} |")

    def rows(name: str, title: str, example) -> None:
        items = s["lists"].get(name, [])
        out.extend(["", f"## {title} ({len(items)} signatures; top {TOP})", "",
                    "| Signature | States | Count | Devices | Example |", "| --- | --- | --- | --- | --- |"])
        for x in items[:TOP]:
            out.append(f"| `{x['signature'][:90]}` | {x['states']} | {x['count']} | {', '.join(x['devices'])} | "
                       f"{example(x['example'])} |")
    ctl = lambda e: f"{e['w']}×{e['h']} “{e['text'].replace('|', '¦')}”" if e else ""  # noqa: E731
    txt = lambda e: f"{e['size']} px “{e['text'].replace('|', '¦')}”" if e else ""  # noqa: E731
    for b in (c1, c2):
        rows(f"controls_under_{b}_phones", f"Controls under {b} px on the phones", ctl)
        rows(f"controls_under_{b}_desktop", f"Controls under {b} px on the desktop", ctl)
    for b in (t1, t2, t3):
        rows(f"text_under_{b}", f"Text under {b} px (count: characters)", txt)
    rows("sideways", "Sideways scroll (count: px over, summed)", lambda e: "")
    out += ["", "## axe-core rules", "", "| Kind | Rule | Impact | WCAG | States | Nodes | Example |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    out += [f"| {x['kind']} | {x['rule']} | {x['impact']} | {'yes' if x['wcag'] else ''} | {x['states']} | {x['nodes']} | "
            f"`{x['example'][:70]}` |" for x in s["lists"]["axe"]]
    out += ["", "## Slowest states (seconds)", "", "| State | Load | Steps | Measure | Total |", "| --- | --- | --- | --- | --- |"]
    out += [f"| {x['state']} | {x['load']} | {x['steps']} | {x['measure']} | {x['total']} |" for x in s["seconds_slowest"]]
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


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("static", help="counts from the source")
    s.add_argument("--out", required=True)
    s.add_argument("--chars", default=ICON_CHARS, help="the characters used as icons or joints")
    s.add_argument("--radius", type=float, default=8, help="the radius (px) of 'the same grey box' at least")
    p = sub.add_parser("pages", help="measurements of the rendered states of tools/ui_shots.py")
    p.add_argument("--out", required=True)
    p.add_argument("--only", default="", help="pages whose name contains this (comma-separated)")
    p.add_argument("--devices", default="desktop,iphone,pixel", help="of: desktop, iphone, pixel")
    p.add_argument("--dark", action="store_true", help="the dark theme too")
    p.add_argument("--data-dir", help="a scratch data folder (default: a new temporary one, removed at the end)")
    p.add_argument("--summarise", action="store_true", help="only the summary again, from --out's pages-states.jsonl")
    args = parser.parse_args()
    if args.command == "static":
        result = static(REPO, args.chars, args.radius)
        _write(args.out, "static", result, static_markdown(result))
        print(os.path.join(args.out, "static.md"))
        return
    if args.summarise:
        with open(os.path.join(args.out, "pages-states.jsonl"), encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    else:
        records = run_pages(args.out, args.only, args.devices.split(","), args.dark, args.data_dir)
    summary = summarise(records)
    _write(args.out, "pages", summary, pages_markdown(summary))
    print(os.path.join(args.out, "pages.md"))


if __name__ == "__main__":
    from progress import utf8_output
    utf8_output()
    main()
