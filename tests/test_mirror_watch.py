"""tools/mirror_watch.py: the mirror's datasets checked against their providers, against the local server of
tests/http_server.py. No test reaches a provider: every test replaces WATCH with rows on the local server (the real
rows' patterns and feed reader are tried on cuts of the providers' answers, saved 2026-11-22, below)."""

import ast
import json
import os
import re
import shlex
import sys
import time

import pytest
import yaml

from http_server import Answer, HttpServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
import mirror_watch as mw  # noqa: E402

LM = "Wed, 26 Jun 2024 08:41:35 GMT"
LM2 = "Thu, 27 Jun 2024 08:41:35 GMT"

# A cut of SPW's ATOM feed of the MNT 2021-2022 (a004e570..., read 2026-11-22): its BOM, its namespaces, its three
# entries (the province entry in EPSG:3812 with its five ZIPs); the author blocks and the long texts left out
BOM = b"\xef\xbb\xbf"
SPW = "https://geoservices.wallonie.be/geotraitement/spwdatadownload/results/a004e570-99d6-4fe5-b83d-49b774409278/"
ID = "https://geodata.wallonie.be/a004e570-99d6-4fe5-b83d-49b774409278/RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_"
ZIP = SPW + "RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_{}.zip"
PROVINCES = {"BRABANT_WALLON": 13919501421, "HAINAUT": 47398087781, "LIEGE": 48579593210,
             "LUXEMBOURG": 55936435422, "NAMUR": 46315489746}
FEED_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:opensearchextensions="http://example.com/opensearchextensions/1.0/" \
xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:gml="http://www.opengis.net/gml" \
xmlns:inspire_dls="http://inspire.ec.europa.eu/schemas/inspire_dls/1.0" xmlns:georss="http://www.georss.org/georss" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.w3.org/2005/Atom" xml:lang="fr">
\t<!-- titre du flux (required)-->
\t<title>Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022</title>
\t<link type="application/atom+xml" rel="self" href="{spw}atom_dataset.xml" hreflang="fr"></link>
\t<id>https://geodata.wallonie.be/id/a004e570-99d6-4fe5-b83d-49b774409278/atom_dataset.xml</id>
\t<updated>2025-06-25T09:44:06.3512939+00:00</updated>
\t<entry>
\t\t<inspire_dls:spatial_dataset_identifier_code>a004e570-99d6-4fe5-b83d-49b774409278\
</inspire_dls:spatial_dataset_identifier_code>
\t\t<id>{id}31370_PROV</id>
\t<!-- Rque: ... --><link title="... PROVINCE HAINAUT -  EPSG:31370" rel="enclosure" \
href="{spw}RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_31370_PROV_HAINAUT.zip" hreflang="fr" length="42020040177" \
type="image/tiff"/>
\t\t<title>Relief de la Wallonie - MNT 2021-2022 - GEOTIFF - PROVINCE - Belge 1972 / Belgian Lambert 72</title>
\t\t<updated>2023-03-31T08:19:05Z</updated>
\t</entry>
\t<entry>
\t\t<id>{id}3812_REGION</id>
\t<!-- Rque: ... --><link title="... GEOTIFF -  EPSG:3812" rel="enclosure" \
href="{spw}RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_REGION.zip" hreflang="fr" length="211000000000" \
type="image/tiff"/>
\t\t<updated>2024-05-27T17:12:57Z</updated>
\t</entry>
"""
FEED_ENTRY = """\t<entry>
\t\t<!-- identifiant du jeu de données prédéfinis (required) -->
\t\t<id>{id}3812_PROV</id>
\t\t<!-- pre-defined dataset link to subfeed--><category term="http://www.opengis.net/def/crs/EPSG/0/3812" \
label="ETRS89 / Belgian Lambert 2008 (EPSG:3812)"/>
{links}\t\t<title>Relief de la Wallonie - MNT 2021-2022 - GEOTIFF - PROVINCE - ETRS89 / Belgian Lambert 2008</title>
\t\t<!-- date/time Date de mise à jour du jeu de données (required)-->
\t\t<updated>{updated}</updated>
\t\t<georss:polygon>2.75 49.45 6.5 49.45 6.5 50.85 2.75 50.85 2.75 49.45</georss:polygon>
\t</entry>
</feed>
"""
ENCLOSURE = ('<link title="Relief de la Wallonie - MNT 2021-2022 - GEOTIFF - PROVINCE {p} -  EPSG:3812" '
             'rel="enclosure" href="{href}" hreflang="fr" length="{n}" type="image/tiff"/>\n\n')


def atom(lengths=None, updated="2024-05-27T09:36:05Z") -> bytes:
    links = "".join(ENCLOSURE.format(p=p, href=ZIP.format(p), n=n) for p, n in (lengths or PROVINCES).items())
    text = FEED_HEAD.format(spw=SPW, id=ID) + FEED_ENTRY.format(id=ID, links=links, updated=updated)
    return BOM + text.encode("utf-8")


# A cut of ÚGKK's provision page (read 2026-11-22): lots of the second cycle, the national ZIPs, the INSPIRE copies
# and a footprint archive (the pattern takes LLS/ only), a relative link; the page's end as the real one's
SK_PAGE = """<!DOCTYPE html><html lang="sk"><body><table><tr>
<td class="text-center">LOT31</td>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/LLS/2_cyklus/LOT31/LOT31_DMR6_sjtsk03_bpv.zip" \
onclick="return openTargetBlank(this, event)" title="Odkaz sa otvorí v novom okne">ZIP (13,8 GB)</a></td>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/LLS/2_cyklus/LOT31/LOT31_DMP2_sjtsk03_bpv.zip" \
onclick="return openTargetBlank(this, event)" title="Odkaz sa otvorí v novom okne">ZIP (14,3 GB)</a></td>
</tr><tr>
<td class="text-center"><strong>celá SR</strong></td>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/LLS/DMR5/DMR5_0_sjtsk03_bpv.zip" \
title="Súbor ZIP">ZIP (183 GB) </a></td>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/INSPIRE/Elevation/DTM5_0_etrs89-tm34_h.zip" \
title="Odkaz sa otvorí v novom okne">ZIP (183 GB)</a></td>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/LLS/DMP1/DMP1_0_sjtsk03_bpv.zip" \
title="Súbor ZIP">ZIP (144 GB) </a></td>
</tr><tr>
<td class="text-center"><a href="https://opendata.skgeodesy.sk/static/LLS/Footprints/1_cyklus/\
las_footprints_s-jtsk03_1_cyklus_shp.zip" title="Odkaz sa otvorí v novom okne">ZIP (480 MB)</a></td>
<td><a href="/files/geoportal/zbgis/lls/prehlad_lokalit_lls_2_cyklus.zip">prehľad</a></td>
</tr></table></body>
</html>
"""
SK_LINKS = ["https://opendata.skgeodesy.sk/static/LLS/2_cyklus/LOT31/LOT31_DMP2_sjtsk03_bpv.zip",
            "https://opendata.skgeodesy.sk/static/LLS/2_cyklus/LOT31/LOT31_DMR6_sjtsk03_bpv.zip",
            "https://opendata.skgeodesy.sk/static/LLS/DMP1/DMP1_0_sjtsk03_bpv.zip",
            "https://opendata.skgeodesy.sk/static/LLS/DMR5/DMR5_0_sjtsk03_bpv.zip"]   # no footprint or INSPIRE archive

# A cut of the SNIG record abba9a83 (ISO 19139, read 2026-11-22): its date stamp, a citation date, a lineage date,
# a contact's link, and the distribution's links (a WMS with an entity in it, the two download ZIPs)
SNIG_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd" xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier><gco:CharacterString>abba9a83-cb1c-4d2c-ad1d-ccb592247754</gco:CharacterString>
  </gmd:fileIdentifier>
  <gmd:onlineResource><gmd:CI_OnlineResource>
              <gmd:linkage>
                <gmd:URL>https://www.madeira.gov.pt/drote/</gmd:URL>
              </gmd:linkage>
  </gmd:CI_OnlineResource></gmd:onlineResource>
  <gmd:dateStamp>
    <gco:Date>2026-06-12</gco:Date>
  </gmd:dateStamp>
  <gmd:date><gmd:CI_Date><gmd:date>
                <gco:Date>2019-10-15</gco:Date>
  </gmd:date></gmd:CI_Date></gmd:date>
  <gco:DateTime>2019-10-15T00:00:00</gco:DateTime>
          <gmd:onLine>
            <gmd:CI_OnlineResource>
              <gmd:linkage>
                <gmd:URL>https://irig-sig.madeira.gov.pt/ows/pg/qwc_config/DIR_modelo_digital_terreno?SERVICE=WMS&amp;\
VERSION=1.3.0&amp;REQUEST=GetCapabilities</gmd:URL>
              </gmd:linkage>
              <gmd:protocol>
                <gco:CharacterString>OGC:WMS-1.3.0-http-get-capabilities</gco:CharacterString>
              </gmd:protocol>
            </gmd:CI_OnlineResource>
          </gmd:onLine>
          <gmd:onLine>
            <gmd:CI_OnlineResource>
              <gmd:linkage>
                <gmd:URL>https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip</gmd:URL>
              </gmd:linkage>
              <gmd:protocol>
                <gco:CharacterString>WWW:DOWNLOAD-1.0-http--download</gco:CharacterString>
              </gmd:protocol>
            </gmd:CI_OnlineResource>
          </gmd:onLine>
          <gmd:onLine>
            <gmd:CI_OnlineResource>
              <gmd:linkage>
                <gmd:URL>https://irig-storage.madeira.gov.pt/irig-catalogo/MDT_2m.zip</gmd:URL>
              </gmd:linkage>
              <gmd:protocol>
                <gco:CharacterString>WWW:DOWNLOAD-1.0-http--download</gco:CharacterString>
              </gmd:protocol>
            </gmd:CI_OnlineResource>
          </gmd:onLine>
</gmd:MD_Metadata>
"""

# A cut of Valle d'Aosta's geoportal page of DTM products (read 2026-11-22): a product's download key and sheet, as
# the page writes them (in an attribute's escaped copy too)
VDA_PAGE = """<html><body><h3 class='av-icon-title'>DTM 2022 Dora Baltea &#8211; quota ortometrica</h3>
<a href='https://mappe.regione.vda.it/pub/geonavitg/geodownload.asp?carta=DTM2022_DORA' title='Download' \
target="_blank">Download</a>
<div aria-label="Icona: &lt;a href=&#039;https://metadati.partout.it/metadata_documents/DTM_2022_DORA_ORTOMETRICA.pdf\
&#039; title=&#039;Scheda informativa&#039; target=&quot;_blank&quot;"></div>
<a href='https://metadati.partout.it/metadata_documents/DTM_2022_DORA_ORTOMETRICA.pdf' title='Scheda informativa'>\
Scheda informativa</a>
<h3 class='av-icon-title'>DTM 2005/2008 aggregato &#8211; quota ortometrica</h3>
<a href='https://mappe.regione.vda.it/pub/geonavitg/geodownload.asp?carta=DTM0508' title='Download'>Download</a>
<a href='https://metadati.partout.it/metadata_documents/DTM_2005_2008_ORTOMETRICA.pdf' title='Scheda informativa'>\
Scheda informativa</a>
</body></HTML>
"""

# A cut of Metawal's CSW answer (read 2026-11-22): the count, two brief records
METAWAL_ANSWER = """<?xml version="1.0" encoding="UTF-8"?>
<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">
  <csw:SearchStatus timestamp="2026-11-22T22:56:13.980388Z" />
  <csw:SearchResults numberOfRecordsMatched="24" numberOfRecordsReturned="24" elementSet="brief" nextRecord="0">
    <csw:BriefRecord>
      <dc:identifier xmlns:dc="http://purl.org/dc/elements/1.1/">5a4c28fe-d30c-493e-861e-a80ebc703b64</dc:identifier>
      <dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Relief de la Wallonie - Modèle Numérique de Surface \
(MNS) 2021-2022</dc:title>
      <dc:type xmlns:dc="http://purl.org/dc/elements/1.1/">dataset</dc:type>
    </csw:BriefRecord>
    <csw:BriefRecord>
      <dc:identifier xmlns:dc="http://purl.org/dc/elements/1.1/">a004e570-99d6-4fe5-b83d-49b774409278</dc:identifier>
      <dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Relief de la Wallonie - Modèle Numérique de Terrain \
(MNT) 2021-2022</dc:title>
      <dc:type xmlns:dc="http://purl.org/dc/elements/1.1/">dataset</dc:type>
    </csw:BriefRecord>
  </csw:SearchResults>
</csw:GetRecordsResponse>
"""

LINKS = r'href="(https://example\.org/data/[^"]+\.zip)"'


def page(*names, end="</body></html>\n") -> bytes:
    links = "".join(f'<a href="https://example.org/data/{n}.zip">{n}</a>\n' for n in names)
    return f"<html><body>\n{links}{end}".encode()


class Bare(HttpServer):
    """The local server, but a path of `bare` answers 200 with the given headers only: no Content-Length (as a
    chunked answer or some servers' HEAD), the connection closed after it."""

    def __init__(self):
        self.bare = {}
        super().__init__()

    def _answer(self, handler, head, request):
        if request.path not in self.bare:
            return super()._answer(handler, head, request)
        with self._lock:
            self.log.append(request)
        handler.send_response(200)
        for name, value in self.bare[request.path].items():
            handler.send_header(name, value)
        handler.send_header("Connection", "close")
        request.ended = time.monotonic()
        handler.end_headers()
        handler.close_connection = True


class Tool:
    """The tool on the local server: rows of signals there, a baseline in tmp_path, main() run with its output."""

    def __init__(self, server, tmp_path, monkeypatch, capsys):
        self.server, self.tmp, self.monkeypatch, self.capsys = server, tmp_path, monkeypatch, capsys
        self.baseline = str(tmp_path / "baseline.json")

    def url(self, path):
        return self.server.url(path)

    def rows(self, **rows):
        self.monkeypatch.setattr(mw, "WATCH", {name.replace("_", "-"): tuple(sig) for name, sig in rows.items()})

    def file(self, path, size=1000, etag='"e1"', last_modified=LM, **kw):
        headers = {k: v for k, v in (("ETag", etag), ("Last-Modified", last_modified)) if v is not None}
        self.server.add(path, b"x" * size, headers=headers, **kw)

    def run(self, *argv, baseline=True):
        code = mw.main(list(argv) + (["--baseline", self.baseline] if baseline else []))
        out = self.capsys.readouterr()
        return code, out.out.splitlines(), out.err

    def check(self, *argv):
        return self.run("check", *argv)

    def adopt(self, *names):
        code, lines, _ = self.run("adopt", *names)
        assert code == 0, lines
        return lines

    def records(self):
        with open(self.baseline, encoding="utf-8") as f:
            return json.load(f)["signals"]


def _tool(server, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mw, "WATCH", {})   # the real rows are never asked: each test sets its own (Tool.rows)
    monkeypatch.setattr(mw, "SCHEMES", {"https", "http"})
    monkeypatch.setattr(mw, "REQUEST_PAUSE", 0)
    return Tool(server, tmp_path, monkeypatch, capsys)


@pytest.fixture
def tool(http_server, tmp_path, monkeypatch, capsys):
    return _tool(http_server, tmp_path, monkeypatch, capsys)


@pytest.fixture
def bare_tool(tmp_path, monkeypatch, capsys):
    server = Bare()
    yield _tool(server, tmp_path, monkeypatch, capsys)
    server.close()


def _line(lines, dataset):
    (line,) = [x for x in lines if x.startswith(dataset + ": ")]
    return line


# File

def _file_row(tool):
    tool.file("/f/a.zip")
    tool.rows(a=[mw.File(tool.url("/f/a.zip"))])
    tool.adopt("a")


def test_file_same(tool):
    _file_row(tool)
    code, lines, _ = tool.check()
    assert (code, lines) == (0, ["a: same | check 2: none"])
    assert {r.method for r in tool.server.requests("/f/")} == {"HEAD"}   # never a GET of a data file
    assert {r.user_agent for r in tool.server.requests()} == {mw.AGENT}


@pytest.mark.parametrize("change, said", [
    (dict(size=1001), "a.zip size: 1000 -> 1001"),
    (dict(etag='"e2"'), 'a.zip ETag: "e1" -> "e2"'),
    (dict(last_modified=LM2), f"a.zip Last-Modified: {LM} -> {LM2}"),   # alone: same size, same ETag
])
def test_file_changed(tool, change, said):
    _file_row(tool)
    tool.file("/f/a.zip", **change)
    code, lines, _ = tool.check()
    assert (code, lines) == (1, [f"a: changed: {said} | check 2: none"])


def test_a_file_changed_and_lacking_a_field_says_both(tool):
    _file_row(tool)
    tool.file("/f/a.zip", size=999, etag=None)
    code, lines, _ = tool.check()
    assert code == 1 and lines == ['a: changed: a.zip size: 1000 -> 999; a.zip ETag: "e1" -> none | check 2: none']


def test_a_field_absent_when_adopted_and_present_later_is_said_until_adopted(tool):
    tool.file("/f/a.zip", etag=None)
    tool.rows(a=[mw.File(tool.url("/f/a.zip"))])
    tool.adopt("a")
    assert tool.records()[f"file {tool.url('/f/a.zip')}"]["etag"] is None
    assert tool.check()[:2] == (0, ["a: same | check 2: none"])
    tool.file("/f/a.zip", etag='"new"')
    for _ in range(2):   # every check says it, never skipped, until the user adopts it
        assert tool.check()[:2] == (1, ['a: changed: a.zip ETag: none -> "new" (a new field) | check 2: none'])
    assert 'a.zip ETag: none -> "new" (a new field)' in tool.adopt("a")
    assert tool.check()[:2] == (0, ["a: same | check 2: none"])


def test_a_weak_and_a_strong_etag_of_one_tag_are_the_same(tool):
    _file_row(tool)
    tool.file("/f/a.zip", etag='W/"e1"')
    assert tool.check()[:2] == (0, ["a: same | check 2: none"])
    tool.file("/f/a.zip", etag='W/"e2"')
    assert tool.check()[:2] == (1, ['a: changed: a.zip ETag: "e1" -> W/"e2" | check 2: none'])


def test_a_head_without_content_length_is_not_checkable(bare_tool):
    tool = bare_tool
    _file_row(tool)
    tool.server.bare["/f/a.zip"] = {"ETag": '"e1"', "Last-Modified": LM}
    code, lines, _ = tool.check()
    assert (code, lines) == (3, ["a: not checkable: a.zip: the answer has no Content-Length | check 2: none"])
    code, lines, _ = tool.run("adopt", "a")
    assert code == 3 and lines[1] == "  a.zip: not checkable: no size: the answer has no Content-Length"


@pytest.mark.parametrize("previous", [False, True])
def test_a_head_without_content_length_but_another_etag_is_changed(bare_tool, previous):
    tool = bare_tool
    _file_row(tool)
    tool.server.bare["/f/a.zip"] = {"ETag": '"e2"', "Last-Modified": LM2}
    argv = ["--previous", _previous(tool, tool.tmp / "previous.json", a=[])] if previous else []
    code, lines, _ = tool.check(*argv)
    assert code == 1 and lines[-1] == (f'a: changed: a.zip ETag: "e1" -> "e2"; a.zip Last-Modified: {LM} -> {LM2}; '
                                       'a.zip size: 1000 -> none | check 2: none')


def test_an_html_page_for_a_file_is_not_checkable_never_changed(tool):
    _file_row(tool)
    tool.server.add("/f/a.zip", b"<html><body>Checking your browser...</body></html>", "text/html; charset=utf-8")
    assert tool.check()[:2] == (3, ["a: not checkable: a.zip: an HTML page instead of the file | check 2: none"])
    tool.server.add("/f/a.zip", b"<html/>", "application/xhtml+xml")
    assert tool.check()[0] == 3


def test_a_head_without_a_field_the_baseline_has_is_not_checkable(tool):
    _file_row(tool)
    tool.file("/f/a.zip", etag=None)
    assert tool.check()[:2] == (3, ["a: not checkable: a.zip: the answer has no ETag | check 2: none"])


@pytest.mark.parametrize("fault, why", [
    (403, "HTTP 403"), (404, "HTTP 404"), (500, "HTTP 500"), ("close", "no answer (RemoteDisconnected)")])
def test_a_refusal_or_no_answer_is_not_checkable_never_changed(tool, fault, why):
    _file_row(tool)
    if fault == "close":
        tool.server.fault("/f/a.zip", "close", lambda n, r: True, plain=True)
    elif fault == 404:
        tool.server.answers.clear()
    else:
        tool.server.add("/f/a.zip", b"refused", status=fault)
    code, lines, _ = tool.check()
    assert (code, lines) == (3, [f"a: not checkable: a.zip: {why} | check 2: none"])


def test_a_redirect_is_not_followed(tool):
    _file_row(tool)
    tool.server.add("/f/a.zip", b"", status=302, headers={"Location": "/elsewhere/a.zip?X-Amz-Signature=s3cr3t"})
    code, lines, _ = tool.check()
    assert code == 3 and lines == [f"a: not checkable: a.zip: HTTP 302 (a redirect to {tool.url('/elsewhere/a.zip')})"
                                   " | check 2: none"]
    assert not tool.server.requests("/elsewhere") and "s3cr3t" not in lines[0]


def test_only_https(tool):
    _file_row(tool)
    tool.monkeypatch.setattr(mw, "SCHEMES", {"https"})
    code, lines, _ = tool.check()
    assert code == 3 and "a.zip: an address on http: refused (only https)" in lines[0]
    assert len(tool.server.requests()) == 1   # the adopt's only


# Feed

def _feed_row(tool, body=None):
    tool.server.add("/spw/atom_dataset.xml", body or atom(), "application/atom+xml")
    tool.rows(w=[mw.Feed(tool.url("/spw/atom_dataset.xml"), r"_GEOTIFF_3812_PROV$", "MNT feed")])
    tool.adopt("w")


def test_feed_same(tool):
    _feed_row(tool)
    record = tool.records()[f"feed {tool.url('/spw/atom_dataset.xml')}"]
    assert record["lengths"] == {ZIP.format(p): n for p, n in PROVINCES.items()}
    assert record["updated"] == {ID + "3812_PROV": "2024-05-27T09:36:05Z"}   # that entry only, not the feed's own
    assert tool.check()[:2] == (0, ["w: same | check 2: none"])
    assert [r.method for r in tool.server.requests()] == ["GET", "GET"]   # the feed only, never an enclosure


def test_feed_length_changed(tool):
    _feed_row(tool)
    tool.server.add("/spw/atom_dataset.xml", atom({**PROVINCES, "NAMUR": 46315489747}))
    code, lines, _ = tool.check()
    assert (code, lines) == (1, ["w: changed: MNT feed RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_NAMUR.zip "
                                 "length: 46315489746 -> 46315489747 | check 2: none"])


def test_feed_updated_changed(tool):
    _feed_row(tool)
    tool.server.add("/spw/atom_dataset.xml", atom(updated="2026-01-23T10:00:00Z"))
    code, lines, _ = tool.check()
    assert (code, lines) == (1, ["w: changed: MNT feed entry RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV "
                                 "updated: 2024-05-27T09:36:05Z -> 2026-01-23T10:00:00Z | check 2: none"])


def test_feed_enclosure_gone_or_new(tool):
    _feed_row(tool)
    fewer = {p: n for p, n in PROVINCES.items() if p != "LIEGE"}
    tool.server.add("/spw/atom_dataset.xml", atom({**fewer, "LIEGE_2": 1}))
    code, lines, _ = tool.check()
    assert code == 1
    assert lines == ["w: changed: MNT feed RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_LIEGE.zip length: "
                     "48579593210 -> gone; MNT feed RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_LIEGE_2.zip "
                     "length: new -> 1 | check 2: none"]


@pytest.mark.parametrize("body, why", [
    (b"<html><body>Service unavailable</body></html", "an answer cut short or not XML (it does not parse)"),
    (atom()[:-200], "an answer cut short or not XML (it does not parse)"),
    (b"<html><body>maintenance</body></html>", "not an ATOM feed"),
    (atom().replace(b"3812_PROV</id>", b"3812_PROVINCES</id>"), "no entry matches"),
])
def test_feed_unreadable_is_not_checkable(tool, body, why):
    _feed_row(tool)
    tool.server.add("/spw/atom_dataset.xml", body)
    assert tool.check()[:2] == (3, [f"w: not checkable: MNT feed: {why} | check 2: none"])


LIEGE_LENGTH = b' length="48579593210"'
NAMUR = "RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_NAMUR.zip"
LIEGE = "RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV_LIEGE.zip"
ENTRY = "RELIEF_WALLONIE_MNT_50CM_2021_2022_GEOTIFF_3812_PROV"


@pytest.mark.parametrize("previous", [False, True])
def test_a_feed_piece_missing_never_hides_a_change(tool, previous):
    """NAMUR's length changed, LIEGE's length attribute gone: changed (exit 1, with or without a previous run that
    had the dataset checkable), the missing piece said beside the change."""
    _feed_row(tool)
    body = atom({**PROVINCES, "NAMUR": 46315489747}).replace(LIEGE_LENGTH, b"")
    assert body != atom({**PROVINCES, "NAMUR": 46315489747})
    tool.server.add("/spw/atom_dataset.xml", body)
    argv = ["--previous", _previous(tool, tool.tmp / "previous.json", w=[])] if previous else []
    code, lines, _ = tool.check(*argv)
    assert (code, lines[-1]) == (1, f"w: changed: MNT feed {NAMUR} length: 46315489746 -> 46315489747; "
                                    f"MNT feed {LIEGE} length: 48579593210 -> none | check 2: none")


def test_an_entry_without_updated_never_hides_a_change(tool):
    _feed_row(tool)
    body = atom({**PROVINCES, "NAMUR": 1}).replace(b"<updated>2024-05-27T09:36:05Z</updated>", b"")
    tool.server.add("/spw/atom_dataset.xml", body)
    code, lines, _ = tool.check()
    assert (code, lines) == (1, [f"w: changed: MNT feed {NAMUR} length: 46315489746 -> 1; MNT feed entry {ENTRY} "
                                 "updated: 2024-05-27T09:36:05Z -> none | check 2: none"])


@pytest.mark.parametrize("cut, why", [
    (lambda b: b.replace(LIEGE_LENGTH, b""), f"the answer has no length of {LIEGE}"),
    (lambda b: b.replace(LIEGE_LENGTH, ' length="²"'.encode()), f"the answer has no length of {LIEGE}"),
    (lambda b: b.replace(b"<updated>2024-05-27T09:36:05Z</updated>", b""),
     f"the answer has no updated of entry {ENTRY}"),
    # an enclosure that lost its address: LIEGE's length is gone with it, its shadow, never a change
    (lambda b: b.replace(f'href="{ZIP.format("LIEGE")}"'.encode(), b""), f"the answer has no address of {LIEGE}"),
])
def test_a_feed_piece_missing_alone_is_not_checkable_and_not_adopted(tool, cut, why):
    """A piece missing (or unreadable) where nothing readable differs: not checkable (the length "²" too:
    str.isdigit takes it, int() does not); first time with --previous; adopt refuses each and leaves the baseline."""
    _feed_row(tool)
    with open(tool.baseline, "rb") as f:
        before = f.read()
    tool.server.add("/spw/atom_dataset.xml", cut(atom()))
    assert tool.check()[:2] == (3, [f"w: not checkable: MNT feed: {why} | check 2: none"])
    previous = _previous(tool, tool.tmp / "previous.json", w=[])
    assert tool.check("--previous", previous)[:2] == (0, ["previous run: the run of 2026-10-01T03:17:00Z",
                                                          f"w: not checkable (first time): MNT feed: {why} | check 2: "
                                                          "none"])
    code, lines, _ = tool.run("adopt", "w")
    assert code == 3 and lines[0] == "not adopted, the baseline left as it was:"
    with open(tool.baseline, "rb") as f:
        assert f.read() == before


def test_an_enclosure_without_its_address_beside_a_real_change(tool):
    """LIEGE's address gone and NAMUR's length changed: changed by NAMUR, LIEGE said unreadable beside it."""
    _feed_row(tool)
    body = atom({**PROVINCES, "NAMUR": 1}).replace(f'href="{ZIP.format("LIEGE")}"'.encode(), b"")
    tool.server.add("/spw/atom_dataset.xml", body)
    assert tool.check()[:2] == (1, [f"w: changed: MNT feed {NAMUR} length: 46315489746 -> 1; MNT feed {LIEGE} "
                                    "length: 48579593210 -> unreadable | check 2: none"])


def test_an_entry_without_its_id_is_a_missing_piece_not_entries_gone(tool):
    """Two matching entries adopted; one loses its <id>: what was under it is gone only because it cannot be named,
    so not checkable, never changed; adopt refuses."""
    tool.server.add("/spw/atom_dataset.xml", atom(), "application/atom+xml")
    tool.rows(w=[mw.Feed(tool.url("/spw/atom_dataset.xml"), r"_GEOTIFF_3812_", "MNT feed")])
    tool.adopt("w")
    assert len(tool.records()[f"feed {tool.url('/spw/atom_dataset.xml')}"]["updated"]) == 2
    tool.server.add("/spw/atom_dataset.xml", atom().replace(f"<id>{ID}3812_PROV</id>".encode(), b"<id></id>"))
    assert tool.check()[:2] == (3, ["w: not checkable: MNT feed: the answer has no id of an entry | check 2: none"])
    code, lines, _ = tool.run("adopt", "w")
    assert code == 3 and "  MNT feed: not checkable: an entry has no id" in lines


def test_an_entry_with_no_enclosure_is_not_checkable(tool):
    _feed_row(tool)
    text = FEED_HEAD.format(spw=SPW, id=ID) + FEED_ENTRY.format(id=ID, links="", updated="2024-05-27T09:36:05Z")
    tool.server.add("/spw/atom_dataset.xml", BOM + text.encode("utf-8"))
    assert tool.check()[:2] == (3, ["w: not checkable: MNT feed: no enclosure in the matching entries | check 2: none"])


# Listing

def _listing_row(tool):
    tool.server.add("/page", page("a", "b"), "text/html")
    tool.rows(p=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("p")


def test_listing_same(tool):
    _listing_row(tool)
    assert tool.records()[f"listing {tool.url('/page')}"]["items"] == ["https://example.org/data/a.zip",
                                                                       "https://example.org/data/b.zip"]
    assert tool.check()[:2] == (0, ["p: same"])


def test_listing_link_added_and_removed(tool):
    _listing_row(tool)
    tool.server.add("/page", page("a", "b", "c"), "text/html")
    assert tool.check()[:2] == (1, ["p: changed: the page added: https://example.org/data/c.zip"])
    tool.server.add("/page", page("b"), "text/html")
    assert tool.check()[:2] == (1, ["p: changed: the page removed: https://example.org/data/a.zip"])


def test_listing_that_extracts_nothing_is_not_checkable(tool):
    _listing_row(tool)
    tool.server.add("/page", b"<html>We are moving: the new site soon</html>", "text/html")
    assert tool.check()[:2] == (3, ["p: not checkable: the page: the patterns found nothing"])


def test_a_page_without_its_end_is_cut_short(tool):
    """Where HTTP cannot tell a cut answer (here it carries its own length), an HTML page must end with </html> (any
    case, white space after it): one that stops early is not checkable, never "removed", and is not adopted."""
    _listing_row(tool)
    with open(tool.baseline, "rb") as f:
        before = f.read()
    tool.server.add("/page", page("a", end=""), "text/html")
    assert tool.check()[:2] == (3, ["p: not checkable: the page: an answer cut short (no closing </html>)"])
    assert tool.run("adopt", "p")[0] == 3
    with open(tool.baseline, "rb") as f:
        assert f.read() == before
    tool.server.add("/page", page("a", "b", end="</BODY></HTML> \r\n\t"), "text/html")
    assert tool.check()[:2] == (0, ["p: same"])


def test_an_xml_listing_that_does_not_parse_is_cut_short(tool):
    """A Listing of XML (a record, a catalogue's answer, a feed's entries) must parse whole."""
    tool.server.add("/record.xml", METAWAL_ANSWER.encode(), "application/xml")
    tool.rows(r=[mw.Listing(tool.url("/record.xml"), mw.METAWAL.patterns, "the record", form="xml")])
    tool.adopt("r")
    tool.server.add("/record.xml", METAWAL_ANSWER.encode()[:-60], "application/xml")
    assert tool.check()[:2] == (3, ["r: not checkable: the record: an answer cut short or not XML (it does not "
                                    "parse)"])
    assert tool.run("adopt", "r")[0] == 3


def test_an_answer_larger_than_the_cap_is_not_checkable(tool):
    _listing_row(tool)
    tool.monkeypatch.setattr(mw, "MAX_BODY", 50)
    assert tool.check()[:2] == (3, ["p: not checkable: the page: the answer is larger than 50 bytes"])


def test_the_reading_stops_at_the_cap(tool):
    """A body far over MAX_BODY is read only up to it (one chunk past), never whole: no data file is downloaded by a
    row that points at one."""
    tool.server.add("/huge", b"x" * 100_000, "text/html")
    tool.rows(p=[mw.Listing(tool.url("/huge"), (LINKS,), "the page")])
    tool.monkeypatch.setattr(mw, "MAX_BODY", 100)
    tool.monkeypatch.setattr(mw, "CHUNK", 10)
    reads = []
    real = mw.http.client.HTTPResponse.read1

    def counted(self, n=-1):
        reads.append(n)
        return real(self, n)
    tool.monkeypatch.setattr(mw.http.client.HTTPResponse, "read1", counted)
    assert tool.check()[:2] == (3, ["p: not checkable: the page: the answer is larger than 100 bytes"])
    assert len(reads) <= 100 // 10 + 2, len(reads)


def test_an_answer_cut_short_is_not_checkable_and_not_adopted(tool):
    """The page's whole Content-Length announced, half its bytes sent, the connection closed (http.client returns the
    short body without an error): not checkable, never "removed"; adopt refuses it and keeps the baseline."""
    names = [f"n{i:03d}" for i in range(60)]
    tool.server.add("/page", page(*names), "text/html")
    tool.rows(p=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("p")
    with open(tool.baseline, "rb") as f:
        before = f.read()
    tool.server.fault("/page", "truncate", lambda n, r: True, plain=True)
    size = len(page(*names))
    code, lines, _ = tool.check()
    assert (code, lines) == (3, [f"p: not checkable: the page: an answer cut short ({size // 2} of {size} bytes)"])
    code, lines, _ = tool.run("adopt", "p")
    assert code == 3 and lines[1] == f"  the page: not checkable: an answer cut short ({size // 2} of {size} bytes)"
    with open(tool.baseline, "rb") as f:
        assert f.read() == before


def test_a_readers_failure_is_that_signals_never_the_runs(tool):
    """A feed in an encoding XML does not know (ElementTree raises LookupError, not ParseError) beside a changed file:
    both datasets' lines, exit 1, the result file written."""
    tool.file("/f/a.zip")
    tool.server.add("/spw/atom_dataset.xml", atom(), "application/atom+xml")
    tool.rows(a=[mw.File(tool.url("/f/a.zip"))],
              w=[mw.Feed(tool.url("/spw/atom_dataset.xml"), r"_GEOTIFF_3812_PROV$", "MNT feed")])
    tool.adopt("a", "w")
    tool.file("/f/a.zip", size=2000)
    tool.server.add("/spw/atom_dataset.xml", b'<?xml version="1.0" encoding="x-nonsense"?><feed/>')
    result = tool.tmp / "result.json"
    code, lines, _ = tool.check("--json-out", str(result))
    assert (code, lines) == (1, ["a: changed: a.zip size: 1000 -> 2000 | check 2: none",
                                 "w: not checkable: MNT feed: a broken answer (LookupError: unknown encoding: "
                                 "x-nonsense) | check 2: none"])
    assert json.loads(result.read_text(encoding="utf-8"))["exit"] == 1


def test_a_content_length_of_other_digits_is_no_size(bare_tool):
    """A Content-Length "²" (the header byte 0xB2, read as Latin-1; str.isdigit takes it, int() does not): no size,
    never an error of the run."""
    tool = bare_tool
    _file_row(tool)
    tool.server.bare["/f/a.zip"] = {"Content-Length": "²", "ETag": '"e1"', "Last-Modified": LM}
    assert tool.check()[:2] == (3, ["a: not checkable: a.zip: the answer has no Content-Length | check 2: none"])
    assert mw._number(" 12 ") == 12 and mw._number(None) is None


def test_a_result_file_that_cannot_be_written_is_said_after_the_lines(tool):
    _listing_row(tool)
    missing = str(tool.tmp / "no-such-folder" / "result.json")
    code, lines, _ = tool.check("--json-out", missing)
    assert (code, lines) == (2, ["p: same", "the result file: not written (FileNotFoundError)"])   # nothing else: 2
    tool.server.add("/page", page("a", "b", "c"), "text/html")
    code, lines, _ = tool.check("--json-out", missing)
    assert code == 1 and lines[-1] == "the result file: not written (FileNotFoundError)"   # the change's code kept


def test_the_runs_time_is_bounded(tool):
    """After RUN_SECONDS no request starts: what was not reached is not checkable, the result file still written. The
    run's clock is the tool's swappable one: the first answer moves it past the bound (no real waiting)."""
    now, armed = [0.0], [False]

    def slow(request):   # answered by the server's thread: the run's time passes while it answers
        if armed[0]:
            now[0] = mw.RUN_SECONDS + 1
        return Answer(200, b"x" * 1000, {"ETag": '"e1"', "Last-Modified": LM})
    tool.server.route("/slow/", slow)
    tool.server.add("/page", page("a"), "text/html")
    tool.rows(a=[mw.File(tool.url("/slow/a.zip"))], p=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("a", "p")
    tool.monkeypatch.setattr(mw, "_clock", lambda: now[0])
    armed[0] = True
    result = tool.tmp / "result.json"
    code, lines, _ = tool.check("--json-out", str(result))
    assert (code, lines) == (3, ["a: same | check 2: none", "p: not checkable: the page: the run's time was up"])
    assert json.loads(result.read_text(encoding="utf-8"))["exit"] == 3
    assert len(tool.server.requests("/page")) == 1   # the adopt's only


def test_the_runs_time_is_checked_between_body_chunks(tool):
    """A clock that ticks once a reading of it: a body of many chunks outlasts the run's time while it is read."""
    tool.server.add("/page", page(*[f"n{i:03d}" for i in range(40)]), "text/html")
    tool.rows(p=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("p")
    ticks = iter(range(10 ** 6))
    tool.monkeypatch.setattr(mw, "_clock", lambda: next(ticks))
    tool.monkeypatch.setattr(mw, "RUN_SECONDS", 50)   # readings, not seconds: fewer than the body's 2000 / 10 chunks
    tool.monkeypatch.setattr(mw, "CHUNK", 10)
    assert tool.check()[:2] == (3, ["p: not checkable: the page: the run's time was up"])


def test_a_request_waits_no_longer_than_the_runs_time_left(tool):
    """Each socket wait is bounded by TIMEOUT or by the run's time left, whichever is shorter."""
    now = [0.0]
    tool.monkeypatch.setattr(mw, "_clock", lambda: now[0])
    http = mw.Http()
    asked = []

    def opener(request, timeout):
        asked.append(timeout)
        raise mw.urllib.error.URLError(TimeoutError())
    http.opener.open = opener
    for at, url in ((0.0, "http://127.0.0.1:9/a"), (mw.RUN_SECONDS - 5, "http://127.0.0.1:9/b"),
                    (mw.RUN_SECONDS - 0.01, "http://127.0.0.1:9/c")):
        now[0] = at
        with pytest.raises(mw.NotCheckable, match=r"no answer \(TimeoutError\)"):
            http.ask("HEAD", url)
    assert asked == [mw.TIMEOUT, 5, 0.1]


# Several signals, several datasets

def test_one_signal_changed_and_one_not_checkable_both_said(tool):
    tool.file("/f/a.zip")
    tool.server.add("/page", page("a"), "text/html")
    tool.rows(d=[mw.File(tool.url("/f/a.zip")), mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("d")
    tool.file("/f/a.zip", size=2000)
    tool.server.add("/page", b"busy", status=503)
    code, lines, _ = tool.check()
    assert (code, lines) == (1, ["d: changed: a.zip size: 1000 -> 2000 | not checkable: the page: HTTP 503"])


def _three_rows(tool):
    """Two datasets sharing a file and a listing, and a feed read for its enclosures and its entries."""
    tool.file("/f/shared.zip")
    tool.file("/f/own.zip")
    tool.server.add("/page", page("a"), "text/html")
    tool.server.add("/spw/atom_dataset.xml", atom(), "application/atom+xml")
    shared, listing = mw.File(tool.url("/f/shared.zip")), mw.Listing(tool.url("/page"), (LINKS,), "the page")
    feed = tool.url("/spw/atom_dataset.xml")
    tool.rows(one=[shared, listing], two=[mw.File(tool.url("/f/own.zip")), shared, listing],
              three=[mw.Feed(feed, r"_3812_PROV$", "feed"), mw.Listing(feed, mw._ENTRY_IDS, "entries", form="xml")])


def test_shared_signals_and_one_address_are_asked_once(tool):
    _three_rows(tool)
    lines = tool.adopt("one", "two", "three")
    assert "the page: new record" in lines
    tool.server.log.clear()
    code, lines, _ = tool.check()
    assert (code, lines) == (0, ["one: same", "two: same", "three: same"])
    asked = sorted((r.method, r.path) for r in tool.server.requests())
    assert asked == [("GET", "/page"), ("GET", "/spw/atom_dataset.xml"), ("HEAD", "/f/own.zip"),
                     ("HEAD", "/f/shared.zip")]


def test_the_wait_between_two_requests_to_one_host(tool):
    _three_rows(tool)
    tool.monkeypatch.setattr(mw, "REQUEST_PAUSE", 0.3)
    tool.check()
    started = sorted(r.started for r in tool.server.requests())
    assert len(started) == 4
    gaps = [b - a for a, b in zip(started, started[1:])]
    assert min(gaps) >= 0.3 - 0.02, gaps   # the clocks' resolution


def test_the_wait_after_a_failed_request(tool):
    """A refusal and a connection closed without an answer count as answers for the wait: the next request to the
    host comes REQUEST_PAUSE after them."""
    tool.server.add("/f/refused.zip", b"no", status=503)
    tool.server.add("/f/closed.zip", b"x" * 10)
    tool.server.fault("/f/closed.zip", "close", lambda n, r: True, plain=True)
    tool.file("/f/a.zip")
    tool.rows(d=[mw.File(tool.url(p)) for p in ("/f/refused.zip", "/f/closed.zip", "/f/a.zip")])
    tool.monkeypatch.setattr(mw, "REQUEST_PAUSE", 0.3)
    tool.check()
    started = [r.started for r in tool.server.requests()]
    assert [r.path for r in tool.server.requests()] == ["/f/refused.zip", "/f/closed.zip", "/f/a.zip"]
    gaps = [b - a for a, b in zip(started, started[1:])]
    assert min(gaps) >= 0.3 - 0.02, gaps


def test_check_two_none_is_said(tool):
    _three_rows(tool)
    tool.rows(one=[mw.File(tool.url("/f/own.zip"))], two=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("one", "two")
    assert tool.check()[:2] == (0, ["one: same | check 2: none", "two: same"])
    code, lines, _ = tool.run("list")
    assert code == 0 and "  check 2: none" in lines and lines.count("  check 2: none") == 1


def test_exit_codes_and_usage(tool):
    _listing_row(tool)
    assert tool.check()[0] == 0
    assert tool.check("p")[0] == 0
    code, lines, err = tool.check("nowhere")
    assert code == 2 and "unknown dataset: nowhere" in err and not lines
    assert tool.run(baseline=False)[0] == 2                  # no command
    assert tool.run("adopt")[0] == 2                         # adopt names its datasets
    with open(tool.baseline, "w", encoding="utf-8") as f:
        f.write("{not json")
    code, _, err = tool.check()
    assert code == 2 and "the baseline cannot be read as JSON" in err


def test_no_baseline_record_is_not_checkable(tool):
    tool.server.add("/page", page("a"), "text/html")
    tool.rows(p=[mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    assert tool.check()[:2] == (3, ["p: not checkable: the page: no baseline record (run adopt)"])
    tool.adopt("p")
    tool.rows(p=[mw.Listing(tool.url("/page"), (LINKS, r"(nothing)"), "the page")])
    assert tool.check()[:2] == (3, ["p: not checkable: the page: the baseline was read another way (run adopt)"])


# adopt

def test_adopt_writes_exactly_what_check_compares(tool):
    _three_rows(tool)
    tool.adopt("one", "two", "three")
    records = tool.records()
    signals = mw.signals_of(list(mw.WATCH))
    assert list(records) == [mw.key_of(s) for s in signals]
    for signal in signals:
        record = records[mw.key_of(signal)]
        assert set(record) == set(mw.META) | set(mw.HOW[signal.kind]) | set(mw.FIELDS[signal.kind])
        assert re.fullmatch(r"\d{4}-\d\d-\d\d", record["read"])
    with open(tool.baseline, "rb") as f:
        assert b"\r\n" not in f.read()
    assert tool.check()[:2] == (0, ["one: same", "two: same", "three: same"])


def test_adopt_says_what_changed_and_whose_baseline_moved(tool):
    _three_rows(tool)
    tool.adopt("one", "two", "three")
    tool.file("/f/shared.zip", size=1200)
    assert tool.check()[0] == 1
    lines = tool.adopt("one")
    assert "shared.zip size: 1000 -> 1200 (also the baseline of two)" in lines
    assert "the page: same (also the baseline of two)" in lines
    assert tool.check()[:2] == (0, ["one: same", "two: same", "three: same"])


def test_adopt_refuses_a_signal_not_checkable_and_keeps_the_file(tool):
    _three_rows(tool)
    tool.adopt("one", "two", "three")
    with open(tool.baseline, "rb") as f:
        before = f.read()
    tool.file("/f/shared.zip", size=1200)
    tool.server.add("/page", b"busy", status=503)
    code, lines, _ = tool.run("adopt", "one")
    assert code == 3 and lines == ["not adopted, the baseline left as it was:",
                                   "  the page: not checkable: HTTP 503"]
    with open(tool.baseline, "rb") as f:
        assert f.read() == before


def test_adopt_drops_records_no_longer_watched(tool):
    _three_rows(tool)
    tool.adopt("one", "two", "three")
    tool.rows(one=[mw.File(tool.url("/f/own.zip"))])
    lines = tool.adopt("one")
    assert f"dropped: file {tool.url('/f/shared.zip')} (no longer watched)" in lines
    assert list(tool.records()) == [f"file {tool.url('/f/own.zip')}"]


# --previous and --json-out

def _previous(tool, path, **states):
    """A previous run's result: each dataset's not checkable reasons ([] for checkable)."""
    datasets = {name: {"state": "not checkable" if why else "same", "changed": [], "not_checkable": why,
                       "first_time": False, "check_2": True, "line": ""} for name, why in states.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tool": "mirror_watch", "format": 1, "checked": "2026-10-01T03:17:00Z", "exit": 0,
                   "datasets": datasets, "signals": {}}, f)
    return str(path)


@pytest.mark.parametrize("before, now, code, said", [
    (False, False, 0, "p: same"),
    (True, False, 0, "p: same"),
    (False, True, 0, "p: not checkable (first time): the page: HTTP 503"),
    (True, True, 3, "p: not checkable: the page: HTTP 503"),
])
def test_previous_in_its_four_cases(tool, before, now, code, said):
    _listing_row(tool)
    previous = _previous(tool, tool.tmp / "previous.json", p=["the page: HTTP 500"] if before else [])
    if now:
        tool.server.add("/page", b"busy", status=503)
    assert tool.check("--previous", previous)[:2] == (code, ["previous run: the run of 2026-10-01T03:17:00Z", said])


def test_a_dataset_absent_before_is_a_first_time(tool):
    _listing_row(tool)
    tool.server.add("/page", b"busy", status=503)
    previous = _previous(tool, tool.tmp / "previous.json", other=["x: HTTP 500"])
    assert tool.check("--previous", previous)[:2] == (0, ["previous run: the run of 2026-10-01T03:17:00Z",
                                                          "p: not checkable (first time): the page: HTTP 503"])


def test_a_change_is_exit_1_whatever_the_previous_run_says(tool):
    tool.file("/f/a.zip")
    tool.server.add("/page", page("a"), "text/html")
    tool.rows(d=[mw.File(tool.url("/f/a.zip")), mw.Listing(tool.url("/page"), (LINKS,), "the page")])
    tool.adopt("d")
    tool.file("/f/a.zip", size=2000)
    tool.server.add("/page", b"busy", status=503)
    for before in ([], ["the page: HTTP 503"]):
        previous = _previous(tool, tool.tmp / "previous.json", d=before)
        code, lines, _ = tool.check("--previous", previous)
        first = "" if before else " (first time)"
        assert (code, lines[1]) == (1, f"d: changed: a.zip size: 1000 -> 2000 | not checkable{first}: the page: "
                                       "HTTP 503")


def test_json_out_is_the_next_runs_previous(tool):
    _listing_row(tool)
    tool.server.add("/page", b"busy", status=503)
    first, second = str(tool.tmp / "first.json"), str(tool.tmp / "second.json")
    code, lines, _ = tool.check("--previous", str(tool.tmp / "none.json"), "--json-out", first)
    assert (code, lines) == (0, ["previous run: none (no such file)",
                                 "p: not checkable (first time): the page: HTTP 503"])
    code, lines, _ = tool.check("--previous", first, "--json-out", second)
    assert code == 3 and lines[1] == "p: not checkable: the page: HTTP 503"
    with open(second, encoding="utf-8") as f:
        result = json.load(f)
    assert result["exit"] == 3 and result["datasets"]["p"]["not_checkable"] == ["the page: HTTP 503"]
    assert result["signals"][f"listing {tool.url('/page')}"]["why"] == "HTTP 503"
    code, lines, _ = tool.check("--json")
    assert code == 3 and json.loads("\n".join(lines))["datasets"]["p"]["state"] == "not checkable"


def test_the_previous_runs_time_is_printed_only_as_a_time(tool):
    _listing_row(tool)
    path = tool.tmp / "previous.json"
    for checked, said in (("2026-10-01T03:17:00Z", "the run of 2026-10-01T03:17:00Z"),
                          ("<script>alert(1)</script>", "a run of an unknown time"),
                          (None, "a run of an unknown time")):
        path.write_text(json.dumps({"tool": "mirror_watch", "checked": checked, "datasets": {}}), encoding="utf-8")
        assert tool.check("--previous", str(path))[1][0] == f"previous run: {said}"


@pytest.mark.parametrize("content, said", [
    ("{broken", "none (the file cannot be read as JSON)"),
    ('{"datasets": {}}', "none (not a result of this tool)"),
    ("[1, 2]", "none (not a result of this tool)"),
])
def test_a_broken_previous_file_is_no_previous_run(tool, content, said):
    _listing_row(tool)
    tool.server.add("/page", b"busy", status=503)
    path = tool.tmp / "previous.json"
    path.write_text(content, encoding="utf-8")
    assert tool.check("--previous", str(path))[:2] == (0, [f"previous run: {said}",
                                                           "p: not checkable (first time): the page: HTTP 503"])


def test_without_previous_every_not_checkable_counts(tool):
    _listing_row(tool)
    tool.server.add("/page", b"busy", status=503)
    assert tool.check()[:2] == (3, ["p: not checkable: the page: HTTP 503"])


# The real rows, on cuts of the providers' answers (no request)

class _Headers(dict):
    def get_content_charset(self):
        return "utf-8"


class _Saved:
    def __init__(self, bodies):
        self.bodies = bodies

    def ask(self, method, url):
        return mw.Answer(200, _Headers(), self.bodies[url])


def test_the_real_rows_read_cuts_of_the_providers_answers():
    saved = _Saved({mw.MNT_FEED.url: atom(), mw.SK_PAGE.url: SK_PAGE.encode(), mw.SNIG.url: SNIG_RECORD.encode(),
                    mw.VDA_PAGE.url: VDA_PAGE.encode(), mw.METAWAL.url: METAWAL_ANSWER.encode()})
    facts, why = mw.read(saved, mw.MNT_FEED)
    assert why is None and facts == {"updated": {ID + "3812_PROV": "2024-05-27T09:36:05Z"},
                                     "lengths": {ZIP.format(p): n for p, n in PROVINCES.items()}, "unaddressed": [],
                                     "unidentified": 0}
    assert mw.read(saved, mw.MNT_ENTRIES)[0]["items"] == [ID + "31370_PROV", ID + "3812_PROV", ID + "3812_REGION"]
    assert mw.read(saved, mw.SK_PAGE)[0]["items"] == SK_LINKS
    assert mw.read(saved, mw.SNIG)[0]["items"] == [   # dates and download links: no contact's, viewer's or WMS link
        "2019-10-15", "2019-10-15T00:00:00", "2026-06-12",
        "https://irig-storage.madeira.gov.pt/irig-catalogo/MDT_2m.zip",
        "https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip"]
    assert mw.read(saved, mw.VDA_PAGE)[0]["items"] == ["DTM0508", "DTM2022_DORA", "DTM_2005_2008_ORTOMETRICA.pdf",
                                                       "DTM_2022_DORA_ORTOMETRICA.pdf"]
    assert mw.read(saved, mw.METAWAL)[0]["items"] == [
        "5a4c28fe-d30c-493e-861e-a80ebc703b64 Relief de la Wallonie - Modèle Numérique de Surface (MNS) 2021-2022",
        "a004e570-99d6-4fe5-b83d-49b774409278 Relief de la Wallonie - Modèle Numérique de Terrain (MNT) 2021-2022",
        'numberOfRecordsMatched="24"']


def test_every_dataset_on_the_mirror_has_both_checks():
    """Each row has a check of its files (File or Feed) and a check for a successor (Listing): none says "check 2:
    none" today (the user's decision of 2026-11-22: "Implement if for every data set in the mirror."); one address is
    read one way only."""
    for name, row in mw.WATCH.items():
        kinds = {s.kind for s in row}
        assert kinds & {"file", "feed"} and "listing" in kinds, name
        assert all(s.url.startswith("https://") for s in row), name
    mw.signals_of(list(mw.WATCH))


def test_the_committed_baseline_has_a_record_for_every_signal():
    """tools/mirror_watch.json: one record per signal of WATCH and no other, each read the way WATCH reads it, with
    exactly the fields check compares."""
    records = mw.load_baseline(mw.BASELINE)
    signals = mw.signals_of(list(mw.WATCH))
    assert sorted(records) == sorted(mw.key_of(s) for s in signals)
    for signal in signals:
        record = records[mw.key_of(signal)]
        assert not mw.read_another_way(signal, record), mw.key_of(signal)
        assert set(record) == set(mw.META) | set(mw.HOW[signal.kind]) | set(mw.FIELDS[signal.kind])
        assert all(record[f] not in (None, [], {}) for f in mw.FIELDS[signal.kind] if f in ("size", "items",
                                                                                            "lengths", "updated"))


def test_the_monthly_workflow():
    """.github/workflows/mirror-watch.yml (the user's decision of 2026-11-22: "Yes, GitHub Actions monthly"): on the
    1st of each month (off the hour) and by hand, reading
    the repository and its own artifacts only, no secret; the runner's python3 without the project's dependencies; the
    tool's own command (its parser takes it), whose exit code is the run's; the result kept for the next run's
    --previous whatever the check said; every action pinned by its commit."""
    with open(os.path.join(REPO, ".github", "workflows", "mirror-watch.yml"), encoding="utf-8") as f:
        text = f.read()
    workflow = yaml.safe_load(text)
    on = workflow[True]   # PyYAML reads the key "on" as True
    assert set(on) == {"schedule", "workflow_dispatch"}
    (cron,) = [c["cron"] for c in on["schedule"]]
    minute, hour, day, month, weekday = cron.split()
    assert (day, month, weekday) == ("1", "*", "*") and minute.isdigit() and minute != "0" and hour.isdigit()
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    (job,) = workflow["jobs"].values()
    assert "permissions" not in job and "secrets." not in text
    steps = job["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses
    assert not any(re.search(r"setup-(python|uv)", u) for u in uses)
    runs = "\n".join(s.get("run", "") for s in steps)
    assert not re.search(r"\b(uv|pip)\b", runs)
    (command,) = re.findall(r"python3 -I tools/mirror_watch\.py ([^>|\n]+)", runs)
    args = mw._parser().parse_args(shlex.split(command))
    assert (args.command, args.datasets, args.previous, args.json_out) == ("check", [], "previous/result.json",
                                                                           "result.json")
    assert "|| status=$?" in runs and "exit $status" in runs   # the tool's exit code fails the run, not a pipe's
    (upload,) = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert upload["with"]["path"] == args.json_out and upload["if"].startswith("always()")
    assert upload["with"]["retention-days"] == 90 and upload["with"]["overwrite"] is True   # a re-run's attempt
    # The look-up of the previous result never ends the job (the user's decision of 2026-11-23, "Check anyway"): the
    # step goes on after an error, and its two commands that may fail are `if` conditions (bash -e, no pipefail,
    # does not stop on them), each else-branch a warning; only this repository's runs count (not a fork's)
    (look,) = [s for s in steps if f"-n {upload['with']['name']} -D previous" in s.get("run", "")]
    assert look["continue-on-error"] is True and steps.index(look) < steps.index(upload)
    assert look["timeout-minutes"] == 3   # a look-up that hangs ends there, and the job goes on to the check
    commands = [line.strip() for line in look["run"].splitlines() if line.strip()]
    assert commands[0].startswith("if ! run=$(gh api ") and "head_repository_id == .workflow_run.repository_id" in \
        look["run"]
    # One if/elif chain: after the API error's warning no other line (not "No previous result": not the reason)
    branches = [c for c in commands if c.startswith(("if ", "elif ", "else", "fi"))]
    assert [b.split()[0] for b in branches] == ["if", "elif", "elif", "else", "fi"]
    said = [next(c for c in commands[commands.index(b) + 1:] if c.startswith("echo")) for b in branches[:4]]
    assert said[0].startswith('echo "::warning title=Mirror watch::the previous result could not be looked up')
    assert branches[1] == 'elif [ -z "$run" ]; then' and said[1].startswith('echo "No previous result')
    assert branches[2].startswith("elif gh run download ") and branches[2].endswith("; then")
    assert said[3].startswith('echo "::warning title=Mirror watch::the result of run $run did not download')
    assert look["run"].count("::warning title=Mirror watch::") == 2 and look["run"].count("No previous result") == 1
    assert not [c for c in commands if c.startswith(("gh ", "run=$(", "run=", "exit"))]


def test_the_tool_imports_nothing_of_the_project():
    """Standard library only: it runs in a stock Python (the monthly workflow's) without the project."""
    with open(os.path.join(REPO, "tools", "mirror_watch.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names and names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)
