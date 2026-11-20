"""The interface's texts live in the message catalogue (locales/en.json), not in the code (step 3d, group G4).

- The server-rendered pages whose texts moved into the catalogue (the sign-in page with its examples and the area
  total, the about page, the pages' footer) render byte for byte as before the move: main's rendering at db84edbc is
  kept here as the reference (`old_*`), over every variant (signed in or not, the account's state, providers, notes,
  examples or none, totals, the satellite map and the 3D view's ring or not). The privacy page is not moved (its
  words are the user's to approve): its footer, the one part it shares, keeps its bytes.
- The files whose texts moved hold no user-visible English literal but a named list of exceptions (brands, format
  names, a provider's required wording, values), so a later change does not put a sentence back into the code: the
  viewer's files (MOVED; JSX text, and literals that read as words: a phrase, a capitalised word, the words of
  markup) and web.py's moved pages (the words of their markup). A single lower-case word is not looked at (too many
  are identifiers); the hand list of 2026-11-20 found those.
- Keys the page builds (a server's status word, the kit's status chips, the usage meters, the report's kinds) and the
  keys of i18n.parts exist in the catalogue; parts keeps a text's values as parts of their own.

A change of these pages' words is a change of the catalogue and of this reference together.
"""

import html
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import accounts as ac  # noqa: E402
import web  # noqa: E402

# ---- main's rendering at db84edbc (web.py), the reference -------------------------------------------------------

OLD_FOOTER = ('<footer class="p-footer"><a href="/">Find-a-Line</a><a href="/coverage">Data coverage</a>'
              '<a href="/privacy">Privacy</a><a href="/about">About / data licences</a></footer>')
OLD_SIGNIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Find-a-Line</title>
<link rel="icon" href="/app/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/app/app.css">
</head><body class="ui p-body"><main class="p-page p-signin">
<header class="p-brand"><h1 class="u-logo">{logo}<span class="u-sr">Find-a-Line</span></h1>
<p class="p-lead">Finds possible highlines in elevation data.</p>{total}
<p class="u-small"><a href="/coverage">Where the data is detailed: the coverage map</a></p></header>
{body}
{footer}
</main></body></html>
"""


def old_esri_terms() -> str:
    e = html.escape
    return ('<p>Satellite imagery: provided by Esri through ArcGIS Location Platform ("Powered by Esri"). By using '
            "the satellite imagery (in the map or in the 3D view of a line) you agree to comply with Esri's terms of "
            f"use for it (<a href='{e(web.ESRI_TERMS_URL)}'>{e(web.ESRI_TERMS_URL)}</a>). In particular, it may only be "
            "viewed in this map and in the 3D view of a line: it may not be downloaded, stored, copied or passed "
            "on.</p>")


def old_about_page(contact: str, esri: bool = False, ring: bool = False) -> str:
    import sources as src
    e = html.escape

    def link(text: str, url: str) -> str:
        return f"<a href='{e(url)}'>{e(text)}</a>" if url.startswith("https://") else e(text)
    credits = {}
    for source in src.SOURCES.values():
        for credit in source.credits + tuple(layer.credit for layer in (source.nmt, source.nmpt)
                                             if layer is not None and layer.credit is not None):
            credits.setdefault(credit.data, credit)
    credits.setdefault(src.WATER_MASK_CREDIT.data, src.WATER_MASK_CREDIT)
    rows = [f"<li><b>{e(c.data)}</b>: {e(src.dated(c.attribution, src.YEAR_TEXT))}. Licence: {link(c.licence, c.url)}."
            + (f" <span class='u-small'>{e(src.dated(c.notice, src.YEAR_TEXT))}</span>" if c.notice else "") + "</li>"
            for c in credits.values()]
    orthos = {s.ortho.name: link(src.dated(s.ortho.attribution, src.YEAR_TEXT), s.ortho.attribution_url or "")
              for s in src.SOURCES.values() if s.ortho is not None}
    body = [
        "<p>Find-a-Line finds possible highlines in elevation data: anchors on steep ground, every pair checked for "
        "clearance under the webbing. Its results are suggestions to check on the spot, not safety advice.</p>",
        "<h2>Elevation data</h2><p>Where each source's data is detailed: <a href='/coverage'>the coverage map</a>."
        "</p><ul>" + "".join(rows) + "</ul>",
        f"<p>{e(src.credit.PROCESSED_NOTE)}</p>",
        (f"<p>Terrain around the 3D view: © Mapterhorn (<a href='{e(web.MAPTERHORN_ATTRIBUTION)}'>"
         "mapterhorn.com/attribution</a>), from open elevation data under the licences of its sources.</p>"
         if ring else ""),
        "<h2>OpenStreetMap</h2><p>Coastlines, cliffs, named areas and place names: © "
        "<a href='https://www.openstreetmap.org/copyright'>OpenStreetMap contributors</a>, under the Open Database "
        "Licence (ODbL 1.0); searched with Nominatim and the Overpass API, extracts from Geofabrik. Errors in the "
        f"map data can be reported at <a href='{e(src.credit.OSM_FIXTHEMAP)}'>openstreetmap.org/fixthemap</a>.</p>",
        "<h2>Orthophotos and background maps</h2><ul>"
        + "".join(f"<li>{e(name)}: {attribution}</li>" for name, attribution in orthos.items())
        + "<li>OpenStreetMap tiles: © OpenStreetMap contributors</li><li>OpenTopoMap: © OpenTopoMap (CC-BY-SA)"
          "</li>"
        + (f"<li>Esri World Imagery: <a href='https://www.esri.com'>Powered by Esri</a>. {e(web.ESRI_SOURCE)}</li>"
           if esri else "") + "</ul>",
        old_esri_terms() if esri else "",
        "<p>Each run names the data it used in its map and in its ATTRIBUTION.txt; results made from FABDEM may be "
        "shared only for non-commercial use, under the same licence.</p>",
        "<h2>Software</h2><p>The maps, the app and the 3D view include open-source libraries (Leaflet, Preact, "
        "i18next, three.js and others); their licences and copyright notices: "
        f"<a href='/app/{web.THIRD_PARTY_LICENCES}'>{web.THIRD_PARTY_LICENCES}</a>.</p>",
        f"<p>Contact: {e(contact)}.</p>",
    ]
    return web.PAGE_HTML.format(title="About / data licences", body="\n".join(body), logo=web.LOGO_SVG,
                                footer=OLD_FOOTER)


def old_demo_list(demos) -> str:
    import runs as rn
    from urllib.parse import quote
    e = html.escape
    if not demos:
        return ""
    items = []
    for run in demos:
        summary = run.get("summary") or {}
        inner = (f"<b>{e(run.get('name') or run['id'])}</b><span class='u-small'>{summary.get('spots', 0)} spots · "
                 f"{summary.get('lines', 0)} lines</span><span class='u-small'>{e(rn.params_summary(run))}</span>")
        items.append(f"<li><a class='p-ex' href='/runs/{e(quote(run['id'], safe=''))}/map.html'>{inner}"
                     f"<span class='p-open'>Open map{web.NEXT_ICON}</span></a></li>" if run.get("has_map")
                     else f"<li><div class='p-ex'>{inner}</div></li>")
    return ("<section class='p-examples'><h2 class='u-h'>Examples</h2><ul class='p-cards'>" + "".join(items)
            + "</ul></section>")


def old_area_total(total) -> str:
    km2, searches = total or (0.0, 0)
    if not searches:
        return ""
    return (f"<p class='u-small'>{web.thousands(km2)} km² searched in {web.thousands(searches)} "
            f"search{'' if searches == 1 else 'es'}</p>")


def old_signin_page(providers, user=None, csrf=None, note: str = "", demos=None, total=None) -> str:
    e = html.escape
    card = [f"<p class='p-error' role='alert'>{e(note)}</p>"] if note else []
    if user is None:
        card.append("<h2 class='u-h'>Sign in to search</h2><div class='p-providers'>" + "".join(
            f"<a class='p-provider p-{p}' href='/login/{p}'>{web.PROVIDER_SVG.get(p, '')}Sign in with {ac.NAMES[p]}</a>"
            for p in providers) + "</div>")
        card.append("<p class='u-small'>A new account waits for an administrator's approval. The site keeps your "
                    "provider's user id and display name, no e-mail address.</p>")
    else:
        state = ("is waiting for an administrator's approval" if user.status == "pending"
                 else "is blocked")
        card.append(f"<p>Your account <b>{e(user.name)}</b> ({e(ac.NAMES.get(user.provider, user.provider))}) "
                    f"{state}.</p>")
        card.append(f"<form method='post' action='/logout'><input type='hidden' name='csrf' value='{e(csrf or '')}'>"
                    "<button class='u-btn' type='submit'>Sign out</button></form>")
    parts = ["<section class='p-card'>" + "\n".join(card) + "</section>", old_demo_list(demos or [])]
    return OLD_SIGNIN_HTML.format(body="\n".join(parts), logo=web.LOGO_SVG, footer=OLD_FOOTER,
                                  total=old_area_total(total))


# ---- the variants ------------------------------------------------------------------------------------------------

PARAMS = {"nmpt": None, "radius": 300, "resolution": 1, "slope_threshold": 60, "min_length": 20, "max_length": 200}
DEMOS = [
    None, [],
    [{"id": "r1", "name": "A run", "summary": {"spots": 1, "lines": 2}, "has_map": True, "params": PARAMS}],
    [{"id": "r 2/x", "name": "", "summary": {"spots": 12, "lines": 1}, "has_map": True, "params": PARAMS},
     {"id": "r3", "name": "<Gozo & Comino>", "has_map": False, "params": {**PARAMS, "nmpt": "mark"}}],
]
TOTALS = [None, (0.0, 0), (0.4, 1), (48300.2, 1234), (1.0, 2)]
NOTES = ["", "New accounts are not accepted.", "Signing in failed (OAuthError).", "<b>&</b>"]
PROVIDERS = [[], ["github"], ["github", "google", "microsoft"]]


def user(status: str, name: str = "Ann", provider: str = "github"):
    return ac.User(id=7, provider=provider, subject="1", name=name, status=status, admin=False)


def test_footer_unchanged():
    """The pages' footer keeps its bytes: the privacy page, whose code and words do not change, shows it too."""
    assert web.PAGE_FOOTER == OLD_FOOTER


@pytest.mark.parametrize("contact", ["admin@example.org", "<Ann & Bob>"])
@pytest.mark.parametrize("esri", [False, True])
@pytest.mark.parametrize("ring", [False, True])
def test_about_page_as_before(contact, esri, ring):
    assert web.about_page(contact, esri=esri, ring=ring) == old_about_page(contact, esri=esri, ring=ring)


def test_signin_page_as_before():
    """Every variant of the sign-in page: a visitor (providers, a note, examples, the total) and an account that is
    not approved (pending or blocked, a name to escape, a provider without a name)."""
    pages = 0
    for providers in PROVIDERS:
        for note in NOTES:
            for demos in DEMOS:
                for total in TOTALS:
                    assert (web.signin_page(providers, note=note, demos=demos, total=total)
                            == old_signin_page(providers, note=note, demos=demos, total=total))
                    pages += 1
    for status in ("pending", "blocked"):
        for who in (user(status), user(status, "<Ann & Bob>", "google"), user(status, "X", "elsewhere")):
            for csrf in (None, "t0k'en"):
                for demos in DEMOS[:3]:
                    assert (web.signin_page(["github"], who, csrf, demos=demos, total=(5.0, 1))
                            == old_signin_page(["github"], who, csrf, demos=demos, total=(5.0, 1)))
                    pages += 1
    assert pages == 3 * 4 * 4 * 5 + 2 * 3 * 2 * 3


def test_examples_and_total_as_before():
    for demos in DEMOS:
        assert web.demo_list(demos or []) == old_demo_list(demos or [])
    for total in TOTALS:
        assert web.area_total(total) == old_area_total(total)


def test_sign_in_notes_as_before():
    """The two notes the sign-in routes give the page (signup closed, a failed sign-in) are the words of before."""
    import messages
    assert messages.text("page.signin.closed") == "New accounts are not accepted."
    assert messages.text("page.signin.failed", error="OAuthError") == "Signing in failed (OAuthError)."


# ---- no English left in the moved files ---------------------------------------------------------------------------

SRC = os.path.join(REPO, "viewer", "src")
# The viewer's files whose texts moved into the catalogue: {file: {text the check finds: why it stays}}
MOVED = {
    "app/c/FavouritesPage.tsx": {"JSX GeoJSON": "a format's name", "JSX CSV": "a format's name"},
    "app/c/Trip.tsx": {"JSX GeoJSON": "a format's name", "JSX CSV": "a format's name"},
    "app/c/Home.tsx": {}, "app/c/AdminC.tsx": {}, "app/c/Account.tsx": {}, "app/c/AppC.tsx": {},
    "app/c/NewSearch.tsx": {}, "app/c/OsmC.tsx": {}, "app/c/ResultPage.tsx": {},
    "app/c/Thumb.tsx": {"xMidYMid slice": "an SVG attribute's value"},
    "app/ReportDialog.tsx": {},
    "app/BetaNotice.tsx": {"${WELCOME}=; Max-Age=0; Path=/; Secure; SameSite=Lax": "a cookie's attributes"},
    "app/useJobs.ts": {}, "app/files.ts": {},
    "search/SearchPanel.tsx": {}, "search/useSearch.ts": {}, "search/PlaceBox.tsx": {},
    "ui/components.tsx": {},
    "ui/SidePanel.tsx": {"${rail.text}${column.forced ? ": "a template inside a template, no words"},
    "baselayers.ts": {"MARKUP OpenStreetMap": "a name", "MARKUP SRTM": "a name", "MARKUP OpenTopoMap": "a name",
                      "MARKUP CC-BY-SA": "a licence's name"},
    "layers.ts": {
        "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community": "Esri's required attribution",
        "Esri World Imagery": "a name", "Powered by Esri": "Esri's required wording",
        " + c.charCodeAt(0) + ": "a regular expression's quote read as a string (no words shown)",
        "Find-a-Line's lines, heights, profiles and maps are computed from these data, ":
            "PROCESSED_NOTE: a data credit word for word with sources.credit (tests/test_catalogue.py)",
        "which were resampled and combined onto a working grid (changed).": "PROCESSED_NOTE (as above)"},
    "download.ts": {}, "result/measured.ts": {}, "view3d/decode.ts": {}, "view3d/canopymesh.ts": {},
}
LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')
NAMES = {"Escape", "Enter", "Home", "End", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",  # keys
         "Feature", "FeatureCollection", "Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point",
         "MultiPoint", "GeometryCollection"}  # GeoJSON's types
UNITS = re.compile(r"\b(?:MB|GB|km²|m|%|°)(?![\w])")
CODE_WORDS = re.compile(r"\b(?:return|export|interface|function|const|let|else|catch|finally|class|extends|as|import|"
                        r"type|async|await|new|throw|Promise|Record|Omit)\b")
ELEMENTS = re.compile(r"[a-z][\w.\-:]*(\s*>\s*[\w.\-:]+)*")


def code_of(text: str) -> str:
    """TypeScript without its comments (literals kept as they are)."""
    out, i = [], 0
    while i < len(text):
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            out.append(re.sub(r"[^\n]", " ", text[i:j + 2]))
            i = j + 2
        elif text[i] in "\"'`" and LITERAL.match(text, i):
            m = LITERAL.match(text, i)
            out.append(m.group())
            i = m.end()
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def has_words(text: str) -> bool:
    """A word of two letters or more, but entities, ${…} and units."""
    return bool(re.search(r"[A-Za-z]{2,}", UNITS.sub("", re.sub(r"&\w+;|\$\{[^}]*\}", "", text))))


def english_in(code: str) -> list:
    """What may be words the page shows in TypeScript `code` (code_of's): JSX text between tags or expressions, and
    literals that read as words (a phrase, a capitalised word, the words between the tags of markup); not the keys
    of t(), parts() or word(), imports, identifiers, classes, selectors, media queries, CSS values, key names."""
    found = []
    blank = LITERAL.sub(lambda m: m.group()[0] + " " * (len(m.group()) - 2) + m.group()[-1], code)
    for m in re.finditer(r"(?:(?<=[^=\-]>)|(?<=\}))([^<>{}]+)(?=[<{])", blank):
        run = m.group(1)
        if not has_words(run) or CODE_WORDS.search(run) or run.lstrip().startswith(":"):
            continue
        if re.search(r"(?:^|,)\s*[A-Za-z_]\w*:\s*$", run):  # an object's key
            continue
        if re.search(r"[(){};=|&+`'\"\[\]?]|\.\w|\w\.|\w:\w", run.strip().rstrip(".:!?…")):
            continue
        found.append("JSX " + " ".join(run.split()))
    for m in LITERAL.finditer(code):
        s = m.group()[1:-1]
        if re.search(r"\b(?:t|parts|textParts|word)\(\s*$|\bimport\b[^;]*$|from\s*$", code[max(0, m.start() - 60):m.start()]):
            continue
        body = re.sub(r"\$\{[^}]*\}", "", s)
        if "<" in body:  # markup: the words between its tags
            found += ["MARKUP " + p.strip() for p in re.split(r"<[^<>]*>", body)
                      if has_words(p) and not re.search(r"[=\"]", p)]
            continue
        if body.lstrip().startswith((".", "[", "(", "#", ":")) or re.match(r"(?:calc|var|rgba?|translate|rotate)\(", body):
            continue  # selectors, media queries, CSS values
        if not has_words(re.sub(r'[\w-]+="[^"]*"|["<>]', "", body)):
            continue  # the attributes of a tag split over literals
        if not has_words(body) or body in NAMES or "://" in body:
            continue
        if re.fullmatch(r"[\w.\-/:#@?=&%]*", body) and not re.fullmatch(r"[A-Z][a-z]+", body):
            continue  # an identifier, a key, a class, a path
        if re.fullmatch(r"[a-z0-9\- ]+", body) and "-" in body:  # a list of classes
            continue
        if "," in body and all(ELEMENTS.fullmatch(p.strip()) for p in body.split(",")):
            continue  # a list of elements
        if " " not in body.strip() and not re.match(r"[A-Z][a-z]", body):
            continue
        found.append(s)
    return found


def test_check_finds_main_texts():
    """The check finds the kinds of text that moved: JSX text, an attribute's phrase, a capitalised label, a sentence
    built in code, the words of markup."""
    sample = code_of('''
const MODES = [{value: "area", label: "Area"}];  // a comment "Not this"
const nav = <nav aria-label="Main"><a href="#x" class="c-a b-c">Home page</a>{n} favourite {k}</nav>;
const text = `Over your daily limit: ${used} of ${limit}`;
const credit = 'Map data: <a href="https://x.org">OpenStreetMap</a> contributors';
const fine = [t("ui.app.home"), ".c-a > .b", "(pointer: coarse)", "Escape", "c-a c-b", "input, button"];''')
    assert english_in(sample) == ["JSX Home page", "JSX favourite", "Area", "Main",
                                  "Over your daily limit: ${used} of ${limit}",
                                  "MARKUP Map data:", "MARKUP OpenStreetMap", "MARKUP contributors"]


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_files_hold_no_english(name):
    """No user-visible English literal is back in a moved file but its named exceptions (each still there)."""
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        found = english_in(code_of(f.read()))
    left = sorted(set(found) - set(MOVED[name]))
    assert not left, f"{name}: texts to put into locales/en.json (or name as an exception with its reason): {left}"
    assert set(MOVED[name]) <= set(found), f"{name}: exceptions no longer found: {set(MOVED[name]) - set(found)}"


# web.py's moved pages: the words of their markup ({name: {text: why it stays}})
SERVER_PAGES = {
    "PAGE_FOOTER": {"Find-a-Line": "the brand"},
    "SIGNIN_HTML": {"Find-a-Line": "the brand"},
    "signin_page": {}, "demo_list": {}, "area_total": {}, "esri_terms": {},
    "about_page": {"OpenStreetMap": "a name (the heading)",
                   "OpenTopoMap: © OpenTopoMap (CC-BY-SA)": "names and a licence",
                   "Esri World Imagery:": "a name", "Powered by Esri": "Esri's required wording"},
}


def test_server_pages_hold_no_english():
    """web.py's moved pages hold no words in their markup but the named exceptions (their texts: page.*)."""
    import ast
    with open(os.path.join(REPO, "web.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    nodes.update({t.id: n for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)})
    for name, allowed in SERVER_PAGES.items():
        node = nodes[name]
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node):
            node.body = node.body[1:]  # the docstring is no page text
        found = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and ("<" in sub.value or ">" in sub.value):
                for piece in re.split(r"<[^<>]*>", re.sub(r"\{[^{}]*\}", "", sub.value)):
                    piece = piece.strip()
                    if has_words(piece) and not re.search(r"[=\"']", piece):
                        found.add(piece)
        assert found == set(allowed), (name, sorted(found - set(allowed)), sorted(set(allowed) - found))


# ---- keys the page builds, and i18n.parts -------------------------------------------------------------------------

def test_built_keys_in_catalogue():
    """Every key the page builds from a value has its text: the server's status words (jobs, users, reports), the
    report's kinds, the kit's status chips, the usage meters; and the literal keys of i18n.parts."""
    import accounts
    import jobs
    import messages
    texts = messages.catalogue()
    with open(os.path.join(SRC, "ui", "components.tsx"), encoding="utf-8") as f:
        kit = re.search(r'export type Status = ([^;]+);', f.read()).group(1)
    with open(os.path.join(SRC, "search", "SearchPanel.tsx"), encoding="utf-8") as f:
        meters = re.search(r"const METERS.*?> = \{(.*?)\};", f.read(), re.S).group(1)
    statuses = jobs.WAITING + jobs.ACTIVE + jobs.FINISHED
    built = ([f"ui.admin.job.{s}" for s in statuses] + [f"ui.jobs.{s}" for s in statuses]
             + [f"ui.admin.user.{s}" for s in accounts.STATUSES] + [f"ui.admin.report.{s}" for s in jobs.REPORT_STATUSES]
             + [f"ui.{k}.{c}" for c in jobs.REPORT_CATEGORIES for k in ("admin.kind", "report.category", "report.hint")]
             + [f"ui.kit.status.{s}" for s in re.findall(r'"(\w+)"', kit)]
             + [f"ui.usage.{k}" for k in re.findall(r"(\w+): \[", meters)])
    assert len(built) == 7 * 2 + 3 + 2 + 4 * 3 + 6 + 7
    used = set()
    for folder, _, files in os.walk(SRC):
        for file in files:
            if file.endswith((".ts", ".tsx")):
                with open(os.path.join(folder, file), encoding="utf-8") as f:
                    used |= set(re.findall(r"""\b(?:parts|textParts)\(\s*["']([^"'`]+)["']""", f.read()))
    assert "ui.thumb.credit" in used
    missing = [k for k in built + sorted(used) if not {k, f"{k}_one", f"{k}_other"} & set(texts)]
    assert not missing, missing


@pytest.mark.skipif(not os.path.isdir(os.path.join(REPO, "viewer", "node_modules", "esbuild")),
                    reason="needs Node and `npm install` in viewer/")
def test_parts_keeps_values_apart(tmp_path):
    """i18n.parts: the words between the values as strings, each value as given (a number stays a number, an object
    an object), empty pieces left out; `count` picks the plural form."""
    import subprocess
    bundle = tmp_path / "i18n.cjs"
    subprocess.run(["node", "-e", "require('esbuild').buildSync({entryPoints: ['src/i18n.ts'], bundle: true, "
                    f"format: 'cjs', platform: 'node', outfile: {json.dumps(str(bundle))}}})"],
                   cwd=os.path.join(REPO, "viewer"), check=True)
    script = tmp_path / "parts.cjs"
    script.write_text(f"const m = require({json.dumps(str(bundle))});\n" + """
console.log(JSON.stringify([
  m.parts("ui.search.centre", {lat: "50.15595", lon: "19.75627"}),
  m.parts("ui.search.stat_grid", {res: 5}),
  m.parts("ui.favourites.empty", {icon: {icon: "star"}}),
  m.parts("ui.admin.sessions", {n: 1}, 1), m.parts("ui.admin.sessions", {n: 3}, 3),
  m.parts("ui.osm.meta", {mb: 9, data: "2026-11-01", checked: "2026-11-19"})]));""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == [
        ["Centre ", "50.15595", ", ", "19.75627"], [5, " m grid"],
        ["No favourite lines yet: mark them with ", {"icon": "star"}, " in a result."],
        [1, " session"], [3, " sessions"], [9, " MB, data of ", "2026-11-01", ", checked ", "2026-11-19"]]
