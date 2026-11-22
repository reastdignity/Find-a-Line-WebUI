"""The interface's texts live in the message catalogue (locales/en.json), not in the code (step 3d, group G4).

- The server-rendered pages whose texts moved into the catalogue (the sign-in page with its examples and the area
  total, the about page, the pages' footer) render byte for byte as before the move: main's rendering at db84edbc is
  kept here as the reference (`old_*`), with the words the user changed since (step 3d G5, the answers of 2026-11-21:
  "About and data licences" for "About / data licences", the examples' "1 spot" and "1 line"), over every variant
  (signed in or not, the account's state, providers, notes, examples or none, totals, the satellite map and the 3D
  view's ring or not). The privacy page is not moved (its words are the user's to approve): its footer, the one part
  it shares, keeps its bytes but for G5's link.
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
import shutil
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import accounts as ac  # noqa: E402
import web  # noqa: E402

# ---- main's rendering at db84edbc (web.py), the reference -------------------------------------------------------

OLD_FOOTER = ('<footer class="p-footer"><a href="/">Find-a-Line</a><a href="/coverage">Data coverage</a>'
              '<a href="/privacy">Privacy</a><a href="/about">About and data licences</a></footer>')  # G5: one wording
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
    return web.PAGE_HTML.format(title="About and data licences", body="\n".join(body), logo=web.LOGO_SVG,
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
        spots, lines = summary.get("spots", 0), summary.get("lines", 0)  # G5: a plural by the count
        counts = f"{spots} spot{'' if spots == 1 else 's'} · {lines} line{'' if lines == 1 else 's'}"
        inner = (f"<b>{e(run.get('name') or run['id'])}</b><span class='u-small'>{counts}</span>"
                 f"<span class='u-small'>{e(rn.params_summary(run))}</span>")
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


# The privacy page's rendering on main at db84edbc (sha256 of web.privacy_page(contact, keep_events_days, ring=ring)),
# its footer's link "About and data licences" since G5 (the user's answer of 2026-11-21; the page's own words unchanged:
# each page with that link put back as "About / data licences" gave the digest of before), and the row "Elevation data
# from the project's data server" of the mirror's task (its words approved by the user on 2026-11-15, U13:
# docs/mirror-hosting/spec.md, section 7; web.py differs from main's only by that row)
PRIVACY = {
    ("admin@example.org", None, False): "d31eaa982420ed046353498f66874e7f738bf9be0292a03d173c0490f424a337",
    ("admin@example.org", None, True): "e79035d8bf88cfd6470e046bc485d2d7a8dd779bff035c7c40cae84e2c1b41e1",
    ("admin@example.org", 30, False): "97a4152d3b99e99d3613a818cc13d957e018ef041873df0a77617076b69d7225",
    ("admin@example.org", 30, True): "e32c7424fa2b3e3213408a3cd1f6e19a625635feb914ae8277d71e8397318704",
    ("admin@example.org", 7.5, False): "73a03466b3f9cfd8be13b590642c2f403f47701bf9616d30318246972ea0c12a",
    ("admin@example.org", 7.5, True): "c88f0690b835e685bfdfa85d3ddae4c21d568e31819255eb61fbb59b4db6b42c",
    ("<Ann & Bob>", None, False): "b261559665c3fdb441a9ae15f1da0e43b1712d8878a297fa5cdf127ad9924c0d",
    ("<Ann & Bob>", None, True): "4caaed9f7319720e1b3df54cd7fb5c6499a8582925aeea46741a397504ffb464",
    ("<Ann & Bob>", 30, False): "0a818af58eb593c75a179056ab983bf659555d0b8e3eb102af469747c74cafcd",
    ("<Ann & Bob>", 30, True): "ecf206892b4eac12d2054fb4aef3e4e6f0ad624a3da5413f81386fcbe3e07bb5",
    ("<Ann & Bob>", 7.5, False): "1c280a7f8417bc5cfb266014cf4cdc282ceace9c36f35ab04eb9ff6e311fa741",
    ("<Ann & Bob>", 7.5, True): "bbb438fe35f5d928b467a50cec466ea398de678583b9872cc912dd1d720dc80e",
}


@pytest.mark.parametrize("variant", sorted(PRIVACY, key=repr))
def test_privacy_page_byte_for_byte(variant):
    """The privacy page renders byte for byte as pinned above (main at db84edbc, G5's link, the data server's row), in every variant (contact, how long events are
    kept, the 3D view's ring). Its words are the user's: a change of them, or of a fact it states (a retention, a
    cookie, a stored field), needs the user's yes on the exact sentences first; then the digests here change with it."""
    import hashlib
    contact, days, ring = variant
    page = web.privacy_page(contact, days, ring=ring)
    assert hashlib.sha256(page.encode("utf-8")).hexdigest() == PRIVACY[variant], (
        "the privacy page changed: its words are the user's to approve; change it only with the user's yes on the "
        "exact sentences, then update PRIVACY")


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
    "app/c/Thumb.tsx": {"ATTR preserveAspectRatio=xMidYMid slice": "an SVG attribute's value"},
    "app/ReportDialog.tsx": {},
    "app/BetaNotice.tsx": {"${}=; Max-Age=0; Path=/; Secure; SameSite=Lax": "a cookie's attributes"},
    "app/useJobs.ts": {}, "app/files.ts": {},
    "search/SearchPanel.tsx": {}, "search/useSearch.ts": {}, "search/PlaceBox.tsx": {},
    "ui/components.tsx": {}, "ui/SidePanel.tsx": {},
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
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')
NAMES = {"Escape", "Enter", "Home", "End", "Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",  # keys
         "Feature", "FeatureCollection", "Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point",
         "MultiPoint", "GeometryCollection"}  # GeoJSON's types
UNITS = re.compile(r"(?<![\w])(?:MB|GB|km²|km|m|%|°)(?![\w])")
ELEMENTS = re.compile(r"[a-z][\w.\-:]*(\s*>\s*[\w.\-:]+)*")
# JSX attributes whose value a person reads or hears: any word in them counts (others: as a code literal)
TEXT_ATTRS = {"title", "aria-label", "placeholder", "alt", "label", "act", "aria-valuetext", "aria-roledescription",
              "removeLabel", "hintLabel", "help", "hint"}
# Calls whose first argument is a key, a selector, an event or a storage name, never words shown
KEY_CALLS = {"t", "parts", "textParts", "word", "label", "querySelector", "querySelectorAll", "closest", "matches",
             "getElementById", "addEventListener", "removeEventListener", "matchMedia", "setAttribute", "getAttribute",
             "removeAttribute", "createElement", "add", "remove", "toggle", "contains", "startsWith", "endsWith",
             "split", "includes", "useId", "useIntro", "go", "getItem", "setItem", "removeItem", "padStart", "join",
             "replace", "useMedia"}


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


class TsxReader:
    """What a TypeScript file may show as words, read without a TypeScript parser (the project's TypeScript 7 has no
    JavaScript API): JSX text, JSX attributes' literal values, and the code's string and template literals, each with
    the call whose first argument holds it and the attribute it stands in. JSX begins at a `<` followed by a letter or
    `>` after an operator, a bracket or `return` (so a type's `<T>` stays code); a compared literal (===, a case) is a
    value and is left out."""

    def __init__(self, code: str, jsx: bool):
        self.s, self.jsx, self.items = code, jsx, []
        self.parens = []  # per open bracket: [the call's name or None, a comma seen at its level]

    def read(self) -> list:
        self.code(0, None)
        return self.items

    def callee(self):
        return self.parens[-1][0] if self.parens and not self.parens[-1][1] else None

    def compared(self, start, end):
        before, after = self.s[max(0, start - 8):start].rstrip(), self.s[end:end + 4].lstrip()
        return bool(re.search(r"[=!]==?$|\bcase$|\bin$", before) or re.match(r"[=!]==?|in\b", after))

    def jsx_start(self, i):
        s = self.s
        if not self.jsx or i + 1 >= len(s) or not (s[i + 1].isalpha() or s[i + 1] == ">"):
            return False
        j = i - 1
        while j >= 0 and s[j] in " \t\r\n":
            j -= 1
        return j < 0 or s[j] in "(=,?:&|{}[;" or s[j - 1:j + 1] == "=>" or bool(re.search(r"\breturn$", s[:j + 1]))

    def code(self, i, stop, attr=None):
        """The code from i to `stop` at its own depth (or the end): the index after it."""
        s, depth = self.s, 0
        while i < len(s):
            c = s[i]
            if c in "\"'":
                m = STRING.match(s, i)
                if m:
                    if not self.compared(i, m.end()):
                        self.items.append({"kind": "lit", "text": m.group()[1:-1], "call": self.callee(), "attr": attr})
                    i = m.end()
                    continue
            if c == "`":
                i = self.template(i, attr)
                continue
            if c == "<" and self.jsx_start(i):
                end = self.element(i)
                if end is not None:
                    i = end
                    continue
            if c in "([{":
                name = re.search(r"([A-Za-z_$][\w$]*)\s*$", s[max(0, i - 60):i]) if c == "(" else None
                self.parens.append([name.group(1) if name else None, c != "("])
                depth += 1
            elif c in ")]}":
                if depth == 0 and c == stop:
                    return i + 1
                depth -= 1
                if self.parens:
                    self.parens.pop()
            elif c == "," and self.parens:
                self.parens[-1][1] = True
            i += 1
        return i

    def template(self, i, attr):
        """A template literal at i, its `${…}` read as code: the index after it."""
        s, j, text = self.s, i + 1, ""
        while j < len(s) and s[j] != "`":
            if s[j] == "\\":
                text, j = text + s[j:j + 2], j + 2
            elif s.startswith("${", j):
                text += "${}"
                self.parens.append([None, True])
                j = self.code(j + 2, "}")
                self.parens.pop()
            else:
                text, j = text + s[j], j + 1
        self.items.append({"kind": "lit", "text": text, "call": self.callee(), "attr": attr})
        return j + 1

    def inner(self, i, attr=None):
        saved, self.parens = self.parens, []
        end = self.code(i, "}", attr)
        self.parens = saved
        return end

    def element(self, i):
        """A JSX element at i: the index after it, None when it is none (the reader goes on as code)."""
        s = self.s
        m = re.compile(r"<([A-Za-z][\w.:-]*)?").match(s, i)
        tag, j = m.group(1) or "", m.end()
        while True:
            while j < len(s) and s[j] in " \t\r\n":
                j += 1
            if j >= len(s):
                return None
            if s.startswith("/>", j):
                return j + 2
            if s[j] == ">":
                j += 1
                break
            if s[j] == "{":  # {...spread}
                j = self.inner(j + 1)
                continue
            a = re.compile(r"[\w:-]+").match(s, j)
            if not a:
                return None
            name, j = a.group(), a.end()
            if s.startswith("=", j):
                j += 1
                if j < len(s) and s[j] in "\"'":
                    lit = STRING.match(s, j)
                    if not lit:
                        return None
                    self.items.append({"kind": "attr", "name": name, "tag": tag, "text": lit.group()[1:-1]})
                    j = lit.end()
                elif j < len(s) and s[j] == "{":
                    j = self.inner(j + 1, attr=name)
                else:
                    return None
        while j < len(s):  # the children
            k = j
            while k < len(s) and s[k] not in "<{":
                k += 1
            if s[j:k].strip():
                self.items.append({"kind": "jsx", "text": s[j:k]})
            if k >= len(s):
                return None
            if s[k] == "{":
                j = self.inner(k + 1)
            elif s.startswith("</", k):
                end = s.find(">", k)
                return None if end < 0 else end + 1
            else:
                end = self.element(k)
                if end is None:
                    return None
                j = end
        return None


def has_words(text: str) -> bool:
    """A word of two letters or more, but entities, ${…} and units."""
    return bool(re.search(r"[A-Za-z]{2,}", UNITS.sub("", re.sub(r"&\w+;|\$\{[^}]*\}", "", text))))


def jsx_text(raw: str) -> str:
    """JSX text as the page gets it: its lines trimmed (the first's start and the last's end kept), joined by a space,
    entities read."""
    lines = raw.split("\n")
    if len(lines) > 1:
        lines = [ln.rstrip() if k == 0 else ln.lstrip() if k == len(lines) - 1 else ln.strip()
                 for k, ln in enumerate(lines)]
        raw = " ".join(ln for ln in lines if ln.strip())
    return html.unescape(raw)


def phrase(text: str) -> list:
    """The words a code literal shows: a phrase (two words or more), a capitalised word, or the words between the tags
    of markup; none for a key, a path, a class, a selector, a media query, a CSS value, a key's or a type's name."""
    body, filled = text.replace("${}", " "), text.replace("${}", "x")
    if re.fullmatch(r"[\w.\-/:#@?=&%]*", filled) and not re.fullmatch(r"[A-Z][a-z]+[:.…!?]?", body):
        return []  # a key or a path, perhaps built from values
    if "<" in body:  # markup: the words between its tags
        return ["MARKUP " + p.strip() for p in re.split(r"<[^<>]*>", body)
                if has_words(p) and not re.search(r"[=\"]", p)]
    if not has_words(body) or body.strip() in NAMES or "://" in body:
        return []
    if body.lstrip().startswith((".", "[", "#", ":", "/")) or re.match(r"(?:calc|var|rgba?|translate|rotate)\(", body):
        return []  # selectors, paths, CSS values
    if re.match(r"\((?:min-|max-|prefers-|pointer|hover|orientation|any-)", body):
        return []  # a media query
    if "-" in body and all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+|[a-z]{1,3}", w) for w in filled.split()):
        return []  # a list of classes (each hyphened, or a short one such as "ui")
    if not has_words(re.sub(r'[\w-]+="[^"]*"|["<>]', "", body)):  # a tag's attributes split over literals
        return []
    if "," in body and all(ELEMENTS.fullmatch(p.strip()) for p in body.split(",")):  # a list of elements
        return []
    return [text] if " " in body.strip() or re.match(r"[A-Z][a-z]", body) else []


def english_in(code: str, jsx: bool = True) -> list:
    """What may be words the page shows in TypeScript `code` (code_of's): every JSX text with a word, every word of a
    text attribute (TEXT_ATTRS), and the code's literals and other attributes' values that read as words (`phrase`);
    not the keys of t(), parts() and the like (KEY_CALLS), imports, compared values."""
    found = []
    for item in TsxReader(code, jsx).read():
        if item["kind"] == "jsx":
            text = " ".join(jsx_text(item["text"]).split())
            if has_words(text):
                found.append("JSX " + text)
        elif item["kind"] == "attr":
            if item["name"] in TEXT_ATTRS:
                found += [f"ATTR {item['name']}={item['text']}"] if has_words(item["text"]) else []
            else:
                found += [f"ATTR {item['name']}={p}" for p in phrase(item["text"])]
        elif item["call"] not in KEY_CALLS:
            if item["attr"] in TEXT_ATTRS:
                found += [f"ATTR {item['attr']}={item['text']}"] if has_words(item["text"]) else []
            else:
                found += phrase(item["text"])
    return found


def test_check_finds_main_texts():
    """The check finds the kinds of text that moved: JSX text (one word too, with punctuation, over several lines), a
    text attribute's word, a capitalised label, a sentence built in code, the words of markup."""
    sample = code_of('''
const MODES = [{value: "area", label: "Area"}];  // a comment "Not this"
const nav = <nav aria-label="Main"><a href="#x" class="c-a b-c">Home page</a>{n} favourite {k}
  <span title="nobody">(default)</span><p>Draw them; drag their
  corners. Both anchors lie inside.</p><i>Edit &amp; run again</i></nav>;
const text = `Over your daily limit: ${used} of ${limit}`;
const credit = 'Map data: <a href="https://x.org">OpenStreetMap</a> contributors';
const ok = s.status === "Done" ? <b>{t("ui.app.home")}</b> : null;
function f(): Promise<Record<string, number>> { return new Map<string, Promise<number>>(); }
const fine = [t("ui.app.home"), ".c-a > .b", "(pointer: coarse)", "Escape", "c-a c-b", "input, button"];''')
    assert english_in(sample) == [
        "Area", "ATTR aria-label=Main", "JSX Home page", "JSX favourite", "ATTR title=nobody", "JSX (default)",
        "JSX Draw them; drag their corners. Both anchors lie inside.", "JSX Edit & run again",
        "Over your daily limit: ${} of ${}", "MARKUP Map data:", "MARKUP OpenStreetMap", "MARKUP contributors"]


def moved_items(name: str) -> list:
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return english_in(code_of(f.read()), name.endswith(".tsx"))


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_files_hold_no_english(name):
    """No user-visible English is back in a moved file but its named exceptions (each still there). Any word in JSX
    text or a text attribute counts. What the check cannot tell from code, and so lets pass: in a code literal outside
    JSX and text attributes, a single lower-case word (statuses, modes, icon names and other identifiers are such words;
    the hand list of 2026-11-20 checked them: "done", "auto", "(default)") and a name of NAMES ("Home", "Point" are
    labels too); anywhere, a text with no word of its own ("{{title}}: {{used}}{{unit}}"). The fix round's mutation
    script (local notes, 3d/g4/fix/mutate.py) puts every text G4 moved back once each way: the rest is caught."""
    found = moved_items(name)
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
# web.py's own English beside the server pages' catalogue texts: {function or constant: why}
SERVER_OWN = {"privacy_page": "the privacy page: its words are the user's to approve (pinned byte for byte below)",
              "COVERAGE_HTML": "the coverage page's shell: its title, description and noscript line in English "
                               "(the page's words are its own catalogue's, locales/coverage; docs/known-bugs.md)"}


def server_texts() -> list:
    """The fixed pieces of the catalogue's texts web.py writes (page.*, and the ui.* keys it reads through page_text or
    messages.text), split at their placeholders: each a phrase of two words or more."""
    import messages
    with open(os.path.join(REPO, "web.py"), encoding="utf-8") as f:
        source = f.read()
    keys = set(re.findall(r"""(?:page_text|messages\.text)\(\s*f?["']((?:page|ui)\.[\w.]+)""", source))
    keys |= set(re.findall(r"""\bt\(\s*["']((?:page|ui)\.[\w.]+)""", source))  # `t = page_text` inside a page
    texts = messages.catalogue()
    pieces = set()
    for key, text in texts.items():
        if key.startswith("page.") or key in keys or re.sub(r"_(one|other|zero)$", "", key) in keys:
            pieces |= {p.strip() for p in re.split(r"\{\{[^{}]*\}\}", text) if len(p.split()) >= 2}
    return sorted(pieces)


def server_constants(tree) -> list:
    """(where, text) of web.py's string constants outside SERVER_OWN, docstrings left out."""
    import ast
    found = []

    def walk(node, where):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in SERVER_OWN:
                return
            where = node.name
            body = node.body[1:] if ast.get_docstring(node) else node.body
            for child in body:
                walk(child, where)
            for child in node.decorator_list:
                walk(child, where)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((where, node.value))
        for child in ast.iter_child_nodes(node):
            walk(child, where)
    module_body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    for node in module_body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) in SERVER_OWN for t in node.targets):
            continue
        walk(node, "web.py")
    return found


def server_english(source: str) -> list:
    """What web.py shows that should come from the catalogue: a catalogue text's piece written as a string anywhere but
    the privacy page (a route's note, a page's sentence put back), and the words of the moved pages' markup."""
    import ast
    tree = ast.parse(source)
    pieces = server_texts()
    found = [f"{where}: {piece}" for where, value in server_constants(tree) for piece in pieces if piece in value]
    nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    nodes.update({t.id: n for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)})
    for name in SERVER_PAGES:
        node = nodes[name]
        body = node.body[1:] if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) else [node]
        for sub in (s for part in body for s in ast.walk(part)):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and ("<" in sub.value or ">" in sub.value):
                for piece in re.split(r"<[^<>]*>", re.sub(r"\{[^{}]*\}", "", sub.value)):
                    piece = piece.strip()
                    if has_words(piece) and not re.search(r"[=\"']", piece) and piece not in SERVER_PAGES[name]:
                        found.append(f"{name}: MARKUP {piece}")
    return found


def test_server_pages_hold_no_english():
    """web.py writes none of the server pages' catalogue texts as its own string (a route's note included) but on the
    privacy page, and the moved pages' markup holds no words but the named exceptions (each still there)."""
    with open(os.path.join(REPO, "web.py"), encoding="utf-8") as f:
        source = f.read()
    assert len(server_texts()) > 25
    assert not server_english(source), server_english(source)
    import ast
    tree = ast.parse(source)
    markup = set()
    for name in SERVER_PAGES:
        node = next(n for n in tree.body if getattr(n, "name", None) == name
                    or isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets))
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and ("<" in sub.value or ">" in sub.value):
                markup |= {(name, p.strip()) for p in re.split(r"<[^<>]*>", re.sub(r"\{[^{}]*\}", "", sub.value))}
    assert {(n, t) for n, ts in SERVER_PAGES.items() for t in ts} <= markup


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


def calls_of(code: str):
    """The t(), parts() and textParts() calls of `code` with a literal key: (their keys, the text of the arguments after
    the first), the arguments found by their brackets (literals skipped)."""
    for m in re.finditer(r"(?<![\w.$])(?:t|parts|textParts)\(", code):
        depth, i, comma = 1, m.end(), None
        while depth and i < len(code):
            lit = LITERAL.match(code, i) if code[i] in "\"'`" else None
            if lit:
                i = lit.end()
                continue
            depth += code[i] in "([{"
            depth -= code[i] in ")]}"
            if code[i] == "," and depth == 1 and comma is None:
                comma = i
            i += 1
        first = code[m.end():comma if comma is not None else i - 1]
        keys = re.findall(r"""["']((?:ui|page|basic|intro|topic|hint|field)\.[\w.]+)["']""", first)
        if keys:
            yield keys, code[comma:i - 1] if comma is not None else ""


def test_moved_calls_give_every_value():
    """Every t()/parts() call of a moved file gives each value its text names ({{name}}, in every plural form): a text
    edited later (G5) keeps its placeholders, or the call changes with it."""
    import messages
    texts = messages.catalogue()
    calls = 0
    for name in MOVED:
        with open(os.path.join(SRC, name), encoding="utf-8") as f:
            code = code_of(f.read())
        for keys, rest in calls_of(code):
            for key in keys:
                forms = [texts[k] for k in (key, f"{key}_one", f"{key}_other", f"{key}_zero") if k in texts]
                assert forms, (name, key)
                calls += 1
                for value in {v for form in forms for v in re.findall(r"\{\{-?\s*([^{}]+?)\s*\}\}", form)}:
                    given = re.search(r"[{,]\s*" + re.escape(value) + r"\s*[:,}]", rest)
                    if value == "count" and not given:  # parts(key, values, count)
                        given = re.search(r"\}\s*,\s*[^,]+$", rest)
                    assert given, f"{name}: {key} names {{{{{value}}}}}, the call does not give it: {rest[:120]}"
    assert calls > 250, calls


@pytest.mark.skipif(shutil.which("node") is None
                    or not os.path.isdir(os.path.join(REPO, "viewer", "node_modules", "esbuild")),
                    reason="needs Node and `npm install` in viewer/")
def test_parts_keeps_values_apart(tmp_path):
    """i18n.parts: the words between the values as strings, each value as given (a number stays a number, an object
    an object), empty pieces left out; `count` picks the plural form, and so does a number value named `count`; a value
    named like an i18next option (`count` as a string, `context`, `lng`, `defaultValue`) does not steer the lookup."""
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
  m.parts("ui.result.lines", {n: 1}, 1), m.parts("ui.result.lines", {n: "1,234"}, 1234),
  m.parts("ui.osm.meta", {mb: 9, data: "2026-11-01", checked: "2026-11-19"}),
  m.parts("basic.rigs", {count: 1}), m.parts("basic.rigs", {count: 3}), m.parts("basic.rigs", {}, 2),
  m.parts("ui.favourites.delete_folders", {count: 1}), m.parts("ui.favourites.delete_folders", {count: 4}),
  m.parts("ui.search.centre", {lat: "1", lon: "2", context: "male", lng: "pl", defaultValue: "x"}),
  m.parts("ui.favourites.export", {what: "this folder"})]));""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == [
        ["Centre ", "50.15595", ", ", "19.75627"], [5, " m grid"],
        ["No favourite lines yet: mark them with ", {"icon": "star"}, " in a result."],
        [1, " line"], ["1,234", " lines"], [9, " MB, data of ", "2026-11-01", ", checked ", "2026-11-19"],
        [1, " rig"], [3, " rigs"], ["2 rigs"], [", ", 1, " folder in it"], [", ", 4, " folders in it"],  # G5: by the count
        ["Centre ", "1", ", ", "2"],
        ["Export ", "this folder"]]
