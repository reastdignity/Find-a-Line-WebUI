"""The interface's texts live in the message catalogue (locales/en.json), not in the code (step 3d, group G4).

- The server-rendered pages whose texts moved into the catalogue (the sign-in page with its examples and the area
  total, the about page, the pages' footer) render byte for byte as before the move: main's rendering at db84edbc is
  kept here as the reference (`old_*`), over every variant (signed in or not, the account's state, providers, notes,
  examples or none, totals, the satellite map and the 3D view's ring or not). The privacy page is not moved (its
  words are the user's to approve): its footer, the one part it shares, keeps its bytes.

A change of these pages' words is a change of the catalogue and of this reference together.
"""

import html
import os
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
