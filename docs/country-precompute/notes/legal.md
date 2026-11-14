# Whole-country downloads and published counts: licences, channels, etiquette

Research of 2026-11-02, read-only. Pages were read with curl (raw HTML, embedded Nuxt/JS payloads
where a page is rendered in the browser) or WebFetch; no dataset was downloaded (only licence PDFs,
legal texts, catalogue metadata and one 12 KB tile metadata XML). WebFetch limits quotes to 125
characters, so some usgs.gov quotes are fragments. Failed pages are listed at the end. This is a
reading of the texts for a feasibility report, not legal advice.

## Summary

| Question | Short answer |
| --- | --- |
| swisstopo: licence | OGD terms ("Opendata BY: Open use. Must provide the source."); use, distribution, making accessible, processing and commercial use allowed; source reference mandatory |
| swisstopo: derived statistics | Allowed; source in the documentation accompanying the publication, optionally "derived from ..."; published under our own name |
| swisstopo: keeping / mirroring raw tiles | Allowed ("may be used, distributed and made accessible") with the source reference; offline delivery on a data carrier can be requested (geodata@swisstopo.ch, paid offer for preparation) |
| GUGiK: legal basis | Art. 40a ust. 2 pkt 1 lit. d PGiK (current text Dz.U. 2026 poz. 1389): no fee for the NMT data sets; NMPT belongs to the NMT database (§ 3 of Dz.U. 2023 poz. 89); no licence issued (art. 40c ust. 5); source must be stated in published works (art. 40c ust. 3) |
| GUGiK: official bulk channel | For NMT/NMPT gov.pl says "nie składaj wniosku. Pobierz dane"; no whole-country NMT package found. The formal request (form C + C5, Dz.U. 2026 poz. 1068) offers FTP/SFTP/cloud or a carrier supplied by the applicant; above 20 GB only on the applicant's carrier (annex ust. 13); postage is charged (annex ust. 14) |
| GUGiK: automated downloading | No rule, limit or robots.txt found; GUGiK: "The user can download any required data, without any limitations"; its own QGIS plugin downloads NMT/NMPT sheets in bulk. Asking first is still the polite route (e-mail draft in section 5) |
| USGS 3DEP | Public domain, "There are no restrictions"; prd-tnm is offered for "Direct access ... via standard HTTP clients"; no published limits; uGet (3 downloads at a time) for batch; ask tnm_help@usgs.gov. Credit: "Map services and data available from U.S. Geological Survey, National Geospatial Program." Modifications must be described (tile metadata) |
| Copernicus GLO-30 | Adaptation and combination allowed; for adapted data the notice "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved", plus the liability sentence and no implied endorsement |
| FABDEM V1-2 | CC BY-NC-SA 4.0. Our own use (downloading = extraction) must be NonCommercial. A count grid holds none of FABDEM's contents, so it is most likely not Adapted Material and ShareAlike does not attach; attribute anyway. Publishing elevations, profiles or the filled terrain from FABDEM areas would be different |
| OSM coastline (ODbL) | A count map made with an OSM sea mask is a Produced Work (ODbL 4.5 b): attribution "© OpenStreetMap contributors" with a link to openstreetmap.org/copyright. If the mask counts as a Derivative Database, 4.6 also asks for the mask or "the method ... (such as an algorithm)": the open-source code covers that |

## 1. swisstopo: swissALTI3D and swissSURFACE3D Raster

### geocat.ch "Legal restrictions" / "Rechtliche Einschränkungen"

The geocat.ch UI is rendered in the browser, so the records were read through the GeoNetwork API.

- swissALTI3D: uuid `691cb471-c3b5-48ec-a107-d0ad612fa70b`, revision 2026-10-26.
  UI: https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/691cb471-c3b5-48ec-a107-d0ad612fa70b
  XML: https://www.geocat.ch/geonetwork/srv/api/records/691cb471-c3b5-48ec-a107-d0ad612fa70b/formatters/xml
- swissSURFACE3D Raster ("swissSURFACE3D Raster, das digitale Oberflächenmodell der Schweiz"):
  uuid `bd4f6bf2-6622-4a16-a6c8-37326ebc9012`, revision 2026-06-15.
  UI: https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/bd4f6bf2-6622-4a16-a6c8-37326ebc9012
  XML: https://www.geocat.ch/geonetwork/srv/api/records/bd4f6bf2-6622-4a16-a6c8-37326ebc9012/formatters/xml

Both records hold the same `CHE_MD_LegalConstraints` / `otherConstraints` (swissSURFACE3D also has
`useConstraints = otherRestrictions`), anchored to https://www.swisstopo.admin.ch/ogd-conditions:

> DE: "Opendata BY: Freie Nutzung. Quellenangabe ist Pflicht."
> FR: "Opendata BY: Utilisation libre. Obligation d'indiquer la source."
> IT: "Opendata BY: Libero utilizzo. Indicazione della fonte obbligatoria."
> EN: "Opendata BY: Open use. Must provide the source."

The FSDI terms (below) point to exactly this field: "Informationen zu den Nutzungsbedingungen eines
Datensatzes können via Metadatenprotal geocat.ch unter «Rechtliche Einschränkungen» gefunden werden."

opendata.swiss explains "Open use. Must provide the source." (https://opendata.swiss/en/terms-of-use):
"You may use this dataset for non-commercial purposes. You may use this dataset for commercial
purposes. You must provide the source (author, title and link to the dataset)."

### The OGD terms (Version 1.3.2021, published 26 August 2022)

EN: https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices (the geocat link
https://www.swisstopo.admin.ch/ogd-conditions redirects there)
DE: https://www.swisstopo.admin.ch/de/nutzungsbedingungen-kostenlose-geodaten-und-geodienste

> "2. Terms of use: The free geodata and geoservices of swisstopo may be used, distributed and made
> accessible. Furthermore, they may be enriched and processed and also used commercially.
> A reference to the source is mandatory. In the case of digital or analogue representations and
> publications, as well as in the case of dissemination, one of the following source references must
> be attached in any case: Bundesamt für Landestopografie swisstopo / Office fédéral de topographie
> swisstopo / Ufficio federale di topografia swisstopo / Uffizi federal da topografia swisstopo /
> Federal Office of Topography swisstopo / ©swisstopo"

DE: "Die kostenlosen Geodaten und Geodienste von swisstopo dürfen genutzt, verbreitet und zugänglich
gemacht werden. Weiter dürfen sie angereichert, bearbeitet sowie auch kommerziell genutzt werden.
Eine Quellenangabe ist Pflicht. Bei digitalen oder analogen Darstellungen und Publikationen sowie bei
der Weitergabe ist in jedem Fall eine der folgenden Quellenangaben anzubringen: ..."

Exceptions with another source reference: only swissALTIRegio and swissEO (not our datasets).

> "3. Excessive use: In the event of excessive use of the geoservices infrastructure, access may be
> restricted or refused. In such cases, swisstopo may conclude a contract with the data user."
> (DE: "3. Übermässige Nutzung ...")

Legal bases named: GeoIA (SR 510.62) Art. 10 ff, GeoIO (SR 510.620) Art. 20 ff, GebV-swisstopo
(SR 510.620.2). The swisstopo FAQ (https://www.swisstopo.admin.ch/en/faq-free-geodata, 5 Sept 2025):
"Is authorisation necessary to use swisstopo geodata? No, no authorisation is required. However, the
source must be indicated upon use as «Source: Federal Office of Topography swisstopo» or «© swisstopo»."
and "The use of Creative Commons licences ... is not compatible with the legal basis (GeoIG, GeoIV)."
"May the free basic geodata obtained be published and used commercially? Yes."

Binding language: the OGD terms have no language clause (published in DE/FR/IT/EN; DE quoted above).
The FSDI terms, which the OGD terms incorporate ("4. Framework conditions"), say "Bei Widersprüchen
zwischen den verschiedenen Sprachversionen gilt die deutsche Version als die verbindliche."

### Attribution guidance (14 September 2021)

https://www.swisstopo.admin.ch/en/source-reference-ogd-swisstopo (DE: .../de/quellenangabe-ogd-swisstopo)

> "Publication of geodata without direct visual representation (e.g. in an elevation service, as a
> table based on geodata analysis). The source is indicated in the documentation accompanying the
> publication. In the case of online publication, the documentation is available online."
>
> "Publication of derived data based on swisstopo geodata (e.g. digitised elements from a swisstopo
> aerial photograph). The requirements are the same as for direct use of swisstopo geodata. ... The
> indication of the source may be preceded by the additional statement "derived from ..."."
>
> "Representation of data in a dynamic map application or service. Ideal: Each time swisstopo data is
> featured, the source is indicated next to the swisstopo data. Acceptable: The source is mentioned in
> a central location on a web page listing all sources used in the map application or service. A link
> ... to the web page of the sources can be found in the map application ..."

### FSDI general terms (BGDI, swisstopo KOGIS / 01.01.2025, German binding)

https://www.geo.admin.ch/de/allgemeine-nutzungsbedingungen-bgdi/ (from http://www.geo.admin.ch/terms-of-use)

- Definitions: "Analyse : Statistiken und Auswertung, die auf Rohdaten und/oder aufbereiteten
  BGDI-Daten basieren." "Publikation: Bereitstellung von BGDI-Daten in jeglicher Form, z.B. als
  Applikation, als Service oder Datei, basierend auf Rohdaten oder aufbereiteten Daten."
- 2.1: "Die bezogenen Daten dürfen gemäss ihren Nutzungsbedingungen aufbereitet, analysiert und
  publiziert werden inkl. Einbezug weiterer Daten."
- 2.3: "Hinweis zum Web-Scraping: Das automatisches Parsing der Geodienste via Bots mit hohen
  Abfrageintensitäten ist zu unterlassen. Für den Bezug der Datensätze ausserhalb des Kontextes der
  Webdienste (Nutzung in offline Systemen, Datenbanken usw.) ist der Downloadservice zu nutzen."
  "Falls Limitenüberschreitungen durch Ihre Anwendungen absehbar werden, bitten wir Sie vor der
  Inbetriebnahme Kontakt mit uns via info@geo.admin.ch aufzunehmen." The fair-use table (in the
  page's payload) lists api3/*.geo.admin.ch, WMTS, WMS and geodesy only; no row for the download
  service data.geo.admin.ch (STAC).
- 3.1 Quellenangabe: "In Publikationen und Analysen, die auf der BGDI basieren, ist gemäss den
  Nutzungsbedingungen des entsprechenden Datensatzes eine Quellangabe anzugeben ... © Data: swisstopo"
- 3.2: "Daten müssen gemäss den Nutzungsbedingungen des entsprechenden Datensatzes allenfalls
  regelmässig aktualisiert werden, entsprechend dem zugrundeliegenden Aktualisierungstakt ..."
- 3.3 Urheberschaft: "Die Publikation der aufbereiteten Daten und allfällig darauf basierenden
  Analysen oder Veredelungen hat gemäss den Nutzungsbedingungen des entsprechenden Datensatzes unter
  dem Namen der Datennutzerin / des Datennutzers zu erfolgen."

### Answers

- Derived statistics (counts per km² cell): allowed (OGD "enriched and processed", FSDI 2.1
  "aufbereitet, analysiert und publiziert"). Duties: source reference in the documentation that
  accompanies the published statistics (online), e.g. "derived from swissALTI3D and swissSURFACE3D
  Raster, © swisstopo"; publish under our own name, not as swisstopo's (FSDI 3.3).
- Keeping copies: allowed. Mirroring (publishing the raw tiles to others): allowed, "distributed and
  made accessible", with one of the source references attached. A public mirror should follow
  swisstopo's update cycle (FSDI 3.2 "allenfalls"); the OGD terms themselves state no such duty.
- Whole-country download: FSDI 2.3 sends offline/database use to the download service (STAC,
  data.geo.admin.ch), and an offline delivery exists:
  "Delivery request: For all geodata from swisstopo, an "offline" delivery request on a suitable
  digital data carrier can be submitted to geodata@swisstopo. swisstopo will prepare an offer for
  the delivery costs. Standard delivery takes place by post on a USB stick. For data volumes of more
  than 30 GB the data carrier will be agreed with the customer. Delivery time: 1 to 2 weeks depending
  on the data volume." "Payment abroad: Exclusively by credit card (MasterCard or VISA) or payment in
  advance." "Unless otherwise specified on delivery of the data, the Terms of use for free geodata and
  geoservices (OGD) from swisstopo apply." (https://www.swisstopo.admin.ch/en/conditions-geodata,
  DE https://www.swisstopo.admin.ch/de/konditionen-geodaten, 8 January 2024). The FAQ adds: "if the
  data must be prepared and sent by a swisstopo employee, a fee is charged for the preparation of the
  data." No price is published.
- Volume check from the product pages: swissALTI3D "0.5 m COG: ~ 26 MB / tile, 770 GB / full
  coverage", "2 m COG: ~ 1 MB / tile, 44 GB / full coverage", "~ 43500 tiles"
  (https://www.swisstopo.admin.ch/en/height-model-swissalti3d); swissSURFACE3D Raster "~ 16 MB /
  Kachel, 335 GB / halbe Schweiz" (https://www.swisstopo.admin.ch/de/hoehenmodell-swisssurface3d-raster),
  so about 1.5 TB at full coverage, in line with the plan.

## 2. GUGiK (Poland): NMT and NMPT

### Legal basis: free of charge, no licence, source stated

Current consolidated text: Dz.U. 2026 poz. 1389 (obwieszczenie of 18 Sept 2026, state of
17 Sept 2026), https://api.sejm.gov.pl/eli/acts/DU/2026/1389/text.pdf (also checked against
Dz.U. 2024 poz. 1151, https://api.sejm.gov.pl/eli/acts/DU/2024/1151/text.html).

> Art. 40a. 1. "Organy prowadzące państwowy zasób geodezyjny i kartograficzny udostępniają materiały
> zasobu odpłatnie. 2. Nie pobiera się opłaty za: 1) udostępnianie zbiorów danych: ... d) numerycznego
> modelu terenu, e) ortofotomapy, ..."
>
> Art. 40c. 3. "Podmioty, które wykorzystują materiały zasobu, zamieszczają w publikowanych
> opracowaniach informacje o źródle pochodzenia użytego materiału."
> Art. 40c. 5. "Licencji nie wydaje się ... w przypadku udostępnienia materiałów zasobu, o których
> mowa w art. 40a ust. 2 pkt 1 i 3."

NMPT is not named in art. 40a, but it is part of the NMT database. Rozporządzenie MRiT z 16 grudnia
2022 (Dz.U. 2023 poz. 89, in force since 26 Jan 2023), https://api.sejm.gov.pl/eli/acts/DU/2023/89/text.html:
"§ 3. W bazie danych dotyczącej numerycznego modelu terenu gromadzi się: 1) chmurę punktów ...;
2) numeryczne modele terenu ...; 3) numeryczne modele pokrycia terenu ...; 4) modele siatkowe 3D ...".
GUGiK treats NMPT as free: "I. Materiały centralnego zasobu geodezyjnego i kartograficznego
udostępniane nieodpłatnie bez konieczności składania wniosku - zgodnie z art. 40a ust. 2 ustawy Prawo
geodezyjne i kartograficzne. ... Numeryczny Model Terenu (NMT), Numeryczny Model Pokrycia Terenu
(NMPT), Dane pomiarowe LIDAR ..." (https://www.gov.pl/web/gugik/dane-udostepniane-bez-platnie-do-pobrania-z-serwisu-wwwgeoportalgovpl).

Other statements:
- "Dane NMT są dostępne bezpłatnie i możliwe do dowolnego wykorzystania."
  (https://www.geoportal.gov.pl/pl/dane/numeryczny-model-terenu-nmt/); the same sentence for NMPT
  (https://www.geoportal.gov.pl/pl/dane/numeryczny-model-pokrycia-terenu-nmpt/).
- Regulamin serwisu geoportal.gov.pl (in force 8 July 2024), § 3: "Publikacja materiałów z Serwisu jest
  dozwolona pod warunkiem umieszczenia informacji o źródle pochodzenia."
  (https://www.geoportal.gov.pl/pl/o-geoportalu/regulamin/). Nothing on automated downloading.
- Dataset metadata "Numeryczny model terenu" in GUGiK's CSW (id f72871bc-bbec-11e4-8dfd-aa08a5b093db,
  dateStamp 2015-02-23): "Brak warunków dostępu i użytkowania" and "Brak ograniczeń w publicznym
  dostępie" (GetRecordById on https://mapy.geoportal.gov.pl/wss/service/CSWINSP/guest/CSWStartup).

Attribution wording: no prescribed text found. Art. 40c ust. 3 asks only for "informacje o źródle
pochodzenia". A suggestion: "Źródło danych: Główny Urząd Geodezji i Kartografii, NMT i NMPT
(PL-EVRF2007-NH), www.geoportal.gov.pl" (EN: "Source: Head Office of Geodesy and Cartography (GUGiK),
Poland"). The e-mail below asks whether they prefer a wording.

### Official channels for the whole country

1. Download (the channel GUGiK points to). gov.pl service card (last updated 13.03.2023, so it still
   cites the 2020 forms regulation; https://www.gov.pl/web/gov/uzyskaj-materialy-geodezyjne-i-kartograficzne): for PRG, PRNG, PRPOG,
   BDOO, ORTO, "Numerycznego Modelu Terenu (NMT), Numerycznego Modelu Pokrycia Terenu (NMPT)",
   BDOT10k: "nie składaj wniosku. Pobierz dane ze strony GUGiK lub geoportal.gov.pl."
   GUGiK EN page (https://www.gov.pl/web/gugik-en/data): "Data of the Central Geodetic and
   Cartographic Resource is now freely available for download from www.geoportal.gov.pl. ... The user
   can download any required data, without any limitations." (English page; the Polish pages say the
   same in substance but not this sentence.)
   - The NMT page names the sheet index WFS (EVRF2007 "od 2018":
     https://mapy.geoportal.gov.pl/wss/service/PZGIK/NumerycznyModelTerenuEVRF2007/WFS/Skorowidze) and
     says: "Usługa jest ułatwieniem do pobierania NMT dla większych obszarów." The WCS tool is limited
     ("maksymalnie 7 km2" in the web tool).
   - GUGiK offers sheet grids for NMT as shapefiles ("Siatki podziału na arkusze dla NMT i
     ortofotomapy w układzie PL-1992 i PL-2000", same gov.pl page as above).
   - GUGiK's own QGIS plugin (news 2026-04-03,
     https://www.geoportal.gov.pl/aktualnosci/gugik-udostepnia-aktualizacje-wtyczki-do-pobierania-danych-bezposrednio-do-oprogramowania-qgis-2/)
     downloads "Dane z usług skorowidzowych: ortofotomapa, prawdziwa ortofotomapa, LIDAR, NMT, NMPT":
     sheet-by-sheet bulk downloading is something GUGiK itself provides.
   - Packages for large areas: "W przypadku chęci pobrania danych dla dużych obszarów (np. kraj,
     województwo, powiat) sugerowane jest pobieranie paczek danych z modułu
     https://mapy.geoportal.gov.pl/imapnext/imap/index.html?moduleId=modulPD" (news 2026-02-13, about
     the parcel plugin). Country packages exist for BDOT10k; I found none for NMT/NMPT (the NMT page
     describes download by sheets only).
2. Formal request with delivery on a carrier or by FTP. Rozporządzenie Ministra Finansów i Gospodarki
   z 28 lipca 2026 r. (Dz.U. 2026 poz. 1068, in force 14 Aug 2026, replacing Dz.U. 2020 poz. 1322),
   https://api.sejm.gov.pl/eli/acts/DU/2026/1068/text.pdf: Załącznik nr 1 "Wniosek o udostępnienie
   materiałów centralnego zasobu geodezyjnego i kartograficznego" (formularz C; "Inne materiały" are
   specified in formularz C5). Field "10. Sposób udostępnienia materiałów" offers "udostępnienie inną
   usługą sieciową GUGiK" (footnote: "Np. FTP, FTPS, SFTP, chmura i inne."), "odbiór osobisty",
   "wysyłka pod wskazany adres", e-mail ("Dotyczy danych o rozmiarze do 25 MB.") and "udostępnienie
   materiałów na nośniku danych elektronicznych dostarczonym przez wnioskodawcę"; explanation: "Dane
   powyżej 20 GB mogą być udostępniane po dostarczeniu przez wnioskodawcę odpowiedniego nośnika danych
   elektronicznych."
   - The law's annex (Dz.U. 2026 poz. 1389, załącznik): "12. Opłaty, o której mowa w ust. 11, nie
     pobiera się, jeżeli odpowiednie nośniki danych elektronicznych dostarczy wnioskodawca.
     13. Materiały zasobu, których łączna wielkość przekracza 20 GB, mogą być udostępniane po
     dostarczeniu przez wnioskodawcę odpowiedniego nośnika danych elektronicznych. 14. Opłata za
     wysłanie materiałów zasobu pod wskazany adres jest równa opłacie za przesyłkę poleconą zgodnie z
     obowiązującym w dniu wystawienia Dokumentu Obliczenia Opłaty cennikiem usług powszechnych ..."
     Art. 40b ust. 1 pkt 4 keeps a fee for "wysłanie materiałów zasobu pod wskazany adres".
   - Where to file (https://www.gov.pl/web/gugik/dane-udostepniane-na-wniosek): ePUAP, "drogą
     elektroniczną na adres e-mail: gugik@gugik.gov.pl" (with an electronic signature), or by post to
     ul. Jana Olbrachta 94B, 01-102 Warszawa or ul. Żurawia 6/12, 00-926 Warszawa; personal pick-up at
     Olbrachta 94B (https://www.geoportal.gov.pl/en/contact/). The portal PZGiK
     (https://pzgik.geoportal.gov.pl/imap/) handles paid central data online.
   - Cost for NMT/NMPT: no fee for the data (art. 40a), no media fee if we supply the disk (annex
     ust. 12), postage at the registered-letter rate if shipped (annex ust. 14); pick-up is free.
   - Open point: gov.pl tells people not to file a request for NMT/NMPT. Whether GUGiK would copy
     4-5 TB onto a supplied disk or open an SFTP/cloud share is not stated anywhere: ask (e-mail below).
   - CODGiK: no current separate CODGiK channel found; all current pages direct central-resource
     requests to GUGiK itself.
   - "Nieodpłatne udostępnianie danych na wniosek" (art. 40a ust. 2 pkt 2) covers schools,
     universities, research bodies and public-benefit organisations; it does not apply to an
     individual's project and is not needed for NMT/NMPT, which are free for everyone.

### Automated downloading from opendata.geoportal.gov.pl

No rule, limit or etiquette statement found: opendata.geoportal.gov.pl has no robots.txt (404 "plik
nie istnieje: /robots.txt"), its landing page is empty, the Regulamin is silent, no request limits
are published (as noted in `.claude/rules/providers.md`). GUGiK's statements point the other way ("without any
limitations", "dowolnego wykorzystania", its own bulk plugin). A Uniwersytet Zielonogórski document
reportedly describes a scripted download of about 7 TB of LIDAR data for one voivodeship (seen only
in a search summary, not opened; not an official source). Courtesy measures: a User-Agent with a
contact address, modest parallelism,
off-peak hours, a notice to GUGiK beforehand.

### Contacts (current pages disagree)

- gugik@gugik.gov.pl: general, also for requests by e-mail (gov.pl pages, geoportal contact).
- sigservicedesk@geoportal.gov.pl: "Problemy techniczne związane z Geoportalem i systemami
  dziedzinowymi", tel. +48 58 773 79 91, 24 h (https://www.geoportal.gov.pl/pl/kontakt/ and footers).
- service.desk@gugik.gov.pl: the same role on https://www.geoportal.gov.pl/en/contact/ and
  https://www.gov.pl/web/gugik-en/contact2.
- "Nieodpłatne udostępnianie danych na wniosek": +48 22 532 25 98 (PL contact page) or
  +48 22 532 25 19 (EN contact page).
- Geoportal information: +48 22 563 14 14 (working days 8:15-16:15).

A lead not verified: the EU high-value datasets regulation (Implementing Regulation (EU) 2023/138,
https://eur-lex.europa.eu/eli/reg_impl/2023/138/oj) asks public bodies to provide designated
geospatial HVDs "free of charge ... through APIs and bulk downloads where relevant" (data.europa.eu
news). EUR-Lex refused automated reading, so whether Poland's NMT is designated with a bulk-download
duty was not checked.

## 3. USGS 3DEP (Utah, prd-tnm)

### Terms and citation

- FAQ "What are the terms of use/licensing for map services and data from The National Map?"
  (https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map):
  "Map services and data downloaded from The National Map are free and in the public domain."
  "There are no restrictions;" "we request that the following acknowledgment statement of the
  originating agency be included" "in products and data derived from our map services when citing,
  copying, or reprinting:" "Map services and data available from U.S. Geological Survey, National
  Geospatial Program."
- FAQ "How should I cite datasets and services from The National Map?"
  (https://www.usgs.gov/faqs/how-should-i-cite-datasets-and-services-national-map): "The USGS does
  not require a specific format when citing data obtained through The National Map." Pattern: author
  U.S. Geological Survey, year (first four digits of `<pubdate>`), title, version (metadata `<title>`),
  access date and URL. Its 1 m example: "U.S. Geological Survey, 2019, 3D Elevation Program 1-Meter
  Resolution Digital Elevation Model (published 20200606), accessed October 23, 2019 at URL
  https://www.usgs.gov/the-national-map-data-delivery" (read in two fragments).
- Tile metadata (FGDC XML of USGS_1M_12_x44y449_UT_StatewideNCentral_2020_A20,
  https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/UT_StatewideNCentral_2020_A20/metadata/USGS_1M_12_x44y449_UT_StatewideNCentral_2020_A20.xml),
  `useconst`: "Acknowledgement of the originating agencies would be appreciated in products derived
  from these data. Any user who modifies the data is obligated to describe the types of
  modifications they perform. User specifically agrees not to misrepresent the data, nor to imply
  that changes made were approved or endorsed by the USGS." Citation: origin "U.S. Geological
  Survey", pubdate 20211121, title "USGS 1 Meter 12 x44y449 UT_StatewideNCentral_2020_A20".
  So the counts page should describe the processing (a methods page is enough).
- Collection citation: the ScienceBase item of the project 1 m collection
  (https://www.sciencebase.gov/catalog/item/543e6b86e4b0fd76af69cf4c) is behind a Cloudflare
  challenge (403). A search engine's copy of it reads "U.S. Geological Survey, 2024, 1 meter Digital
  Elevation Models (DEMs) - USGS National Map 3DEP Downloadable Data Collection: U.S. Geological
  Survey." (not verified on the page). The newer seamless product (not the one we use) has a DOI:
  "National Geospatial Technical Operations Center, Earth Resources Observation and Science Center,
  and National Geospatial Program, 2025, Seamless 1 meter Digital Elevation Models (DEMs) - USGS
  National Map 3DEP Downloadable Data Collection: U.S. Geological Survey data release,
  https://doi.org/10.5066/P13LJKFS." with "All 3DEP products are public domain."
  (https://data.usgs.gov/datacatalog/data/USGS:4f34caac-f28f-4ea0-8d82-eafb2b8f9a5d).
- Copyrights and credits (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits):
  "USGS-authored or produced data and information are considered to be in the U.S. Public Domain."
  Suggested credit form "Credit: U.S. Geological Survey"; the USGS identifier (logo) is trademarked.

### Large downloads: what USGS says

- GIS data download page (https://www.usgs.gov/the-national-map-data-delivery/gis-data-download):
  "TNM Cloud Downloads (Staged Products)": "Direct access to datasets and maps via standard HTTP
  clients." (link https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/); uGet:
  "utilizing the URL lists available through TNM Downloader for bulk data access"; lidar: "For faster,
  very large volume access to 3DEP lidar data" (AWS requester-pays instructions).
- uGet instructions (https://apps.nationalmap.gov/uget-instructions/, text from its JS bundle):
  URL lists from TNM Download ("Save as Text", "Export URLs to TXT"), then "Batch Downloads";
  "Three items are downloaded at a time."
- TNM Access API docs (https://tnmaccess.nationalmap.gov/api/v1/docs, OpenAPI 3.0.1 in the page):
  no rate limits or etiquette; "With no additional parameters, this query will return 10,000 of the
  almost 4 million pre-staged products"; `max`: "If the offset is > 100 the max must be a multiple
  of 5."
- FAQ "Is there an API for accessing The National Map data?"
  (https://www.usgs.gov/faqs/there-api-accessing-national-map-data) and "Does the USGS have APIs?"
  (https://www.usgs.gov/faqs/does-usgs-have-apis): no usage limits stated; "Direct access to The
  National Map data is provided via browsable links through: Amazon's Cloud USGS Server."
- Bulk by request exists only for vectors: "The USGS only offers vector downloads from The National
  Map in bulk by special request" (a related FAQ shown on the API FAQ page above; per search results
  its own page is https://www.usgs.gov/faqs/how-can-i-download-vector-data-national-map-bulk; help:
  tnm_help@usgs.gov, The National Map Help Desk).
- No AWS Registry of Open Data entry for prd-tnm was found (the elevation tag lists only "USGS 3DEP
  LiDAR Point Clouds", https://registry.opendata.aws/usgs-lidar/); the bucket's index page
  (https://prd-tnm.s3.amazonaws.com/index.html) carries no terms. Egress is paid
  by USGS, so modest parallelism (uGet's 3), windowed reads (as the code already does), a User-Agent
  with contact and an optional heads-up to tnm_help@usgs.gov are the courteous choice.

## 4. Derived statistics and the gap fillers

### Copernicus DEM GLO-30

Licence "Licence for the use of the Copernicus WorldDEM-30" (instance "COP-DEM-GLO-30-F Global 30m
Full, Free & Open"), https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf;
the same notices on the CDSE collection page
(https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM),
to which the AWS registry entry points ("GLO-30 Public and GLO-90 are available on a free basis for
the general public", https://registry.opendata.aws/copernicus-dem/).

> Article 4. Right of Use: "(a) reproduction; (b) distribution; (c) communication to the General
> Public; (d) adaptation, modification and combination with other data and information."
> Article 6 (a) "When communicating to the General Public or distributing the Copernicus WorldDEM-30,
> the User shall inform the General Public of the source by using the following notice: © DLR e.V.
> 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European
> Union and ESA; all rights reserved."
> (b) "Where the Copernicus WorldDEM-30 data have been adapted or modified, the User shall provide the
> following notice: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence
> and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights
> reserved"."
> (c) "... The following sentence or its translation in any language shall be added by such Users in a
> licence or any legal warning or notice covering their distribution or communication to the General
> Public of the Copernicus WorldDEM-30: "The organisations in charge of the Copernicus programme by law
> or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30"."
> (d) "User shall make sure not to convey the impression to the General Public that the user's
> activities are officially endorsed by the Provider, the Licensor or any other legal entities ..."
> Article 9: "Neither the Licensor nor the Provider will claim any IPRs ... as obtained by the User
> through his own work while exercising the use rights granted in this licence."

Assessment: counts computed from a terrain partly filled with GLO-30 are adapted data: give the 6(b)
notice and the 6(c) sentence on the about/methods page and do not suggest endorsement. The rights to
our own results stay ours (Art. 9). The Copernicus water body mask is an auxiliary layer of the same
product; I found no separate licence for it. AWS's suggested citation: "Copernicus Digital Elevation
Model (DEM) was accessed on DATE from https://registry.opendata.aws/copernicus-dem."

### FABDEM V1-2 (CC BY-NC-SA 4.0)

The dataset page https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn reset every
connection (curl and WebFetch); the Wayback copy answered 429. Its DOI record at DataCite
(https://api.datacite.org/dois/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn, publisher University of
Bristol, 2023, creators Neal, Jeffrey; Hawker, Laurence) carries the abstract: "FABDEM V1-2, an
update on FABDEM V1-0. ... The FABDEM dataset is licensed under a Creative Commons "CC BY-NC-SA 4.0"
license. For commercial use queries, please contact fabdem@fathom.global This dataset is published
in support of the paper "A 30 m global map of elevation with forests and buildings removed" ...
https://dx.doi.org/10.1088/1748-9326/ac4d4f."

Citations: Neal, J., Hawker, L. (2023): FABDEM V1-2. University of Bristol.
https://doi.org/10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn; Hawker, L., Uhe, P., Paulo, L., Sosa, J.,
Savage, J., Sampson, C., Neal, J. (2022): A 30 m global map of elevation with forests and buildings
removed. Environ. Res. Lett. 17, 024016. Required statements as the GEE community catalog repeats them
(secondary source, https://gee-community-catalog.org/projects/fabdem/): "FABDEM is produced using
Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided
under COPERNICUS by the European Union and ESA; all rights reserved. The organizations in charge of
the Copernicus program by law or by delegation do not incur any liability for any use of the
Copernicus WorldDEM-30".

CC BY-NC-SA 4.0 legal code (https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en):

> "Adapted Material means material subject to Copyright and Similar Rights that is derived from or
> based upon the Licensed Material and in which the Licensed Material is translated, altered,
> arranged, transformed, or otherwise modified in a manner requiring permission under the Copyright
> and Similar Rights held by the Licensor."
> "NonCommercial means not primarily intended for or directed towards commercial advantage or
> monetary compensation."
> Section 4: "Section 2(a)(1) grants You the right to extract, reuse, reproduce, and Share all or a
> substantial portion of the contents of the database for NonCommercial purposes only; if You include
> all or a substantial portion of the database contents in a database in which You have Sui Generis
> Database Rights, then the database in which You have Sui Generis Database Rights (but not its
> individual contents) is Adapted Material, including for purposes of Section 3(b); and You must
> comply with the conditions in Section 3(a) if You Share all or a substantial portion of the contents
> of the database."
> Section 3(b) ShareAlike applies "if You Share Adapted Material You produce".

CC FAQ, data section (https://creativecommons.org/faq/#data):

> "even where database contents are subject to copyright and published under a CC license, use of the
> facts and ideas embedded within the contents will not require attribution (or compliance with other
> applicable license conditions), unless doing so implicates copyright in the database structure"
> (#how-do-i-know-whether-a-particular-use-of-a-database-is-restricted-by-copyright)
> "Under version 4.0, if an NC license has been applied then any use of the licensed database or its
> contents that is restricted by copyright law or sui generis database rights requires compliance with
> the NC term, even if the database is not publicly shared." (#how-do-the-different-cc-license-elements-operate-for-a-cc-licensed-database)
> "the SA licenses require you to apply the same or a compatible license to any database you share
> publicly and in which you include a substantial portion of the licensed database contents."
> (#if-my-use-of-a-database-is-restricted-by-sui-generis-database-rights-how-do-i-comply-with-the-license)
> Text/data mining: "Outputs: If you publicly share the results of your mining activity or the data
> you mined, you should attribute the rights holder. ... If you share an adaptation of material under
> an SA license, you must apply the same license to the adaptation that results."
> (#can-i-conduct-textdata-mining-on-a-cc-licensed-database)

Assessment (counts per km² cell, no elevations, no geometry):
- NonCommercial binds our own use: downloading the tiles of a country is extraction of a substantial
  part, so the project and the public site must stay non-commercial (no ads, paid tiers or
  commercial clients of the counts); otherwise a Fathom licence is needed (fabdem@fathom.global).
- ShareAlike: the count grid contains no FABDEM contents (no elevations) and reproduces no
  copyrightable expression, so it is most likely not Adapted Material; ShareAlike would not attach and
  the counts may carry our own terms. Attribution is still advisable (CC's guidance on mining outputs)
  and costs nothing: FABDEM credit, licence link, the Copernicus statements above.
- Where it would change: publishing the filled terrain, heights, profiles or contours from areas
  filled with FABDEM is sharing FABDEM contents (Adapted Material if modified): BY-NC-SA terms with
  attribution and licence link would then apply to that material. The internal mosaic is not shared,
  so SA does not attach to it.
- The question is less clear-cut outside the EU/UK sui generis right (EU Directive 96/9/EC; FABDEM is
  made in the UK); in the EU, extraction rights are exactly what the licence grants for NC use.

### OpenStreetMap coastline (ODbL 1.0)

ODbL 1.0 (https://opendatacommons.org/licenses/odbl/1-0/):

> "Produced Work" – "a work (such as an image, audiovisual material, text, or sounds) resulting from
> using the whole or a Substantial part of the Contents (via a search or other query) from this
> Database, a Derivative Database, or this Database as part of a Collective Database."
> "Derivative Database" – "Means a database based upon the Database, and includes any translation,
> adaptation, arrangement, modification, or any other alteration of the Database or of a Substantial
> part of the Contents."
> 4.3 "Creating and Using a Produced Work does not require the notice in Section 4.2. However, if you
> Publicly Use a Produced Work, You must include a notice associated with the Produced Work reasonably
> calculated to make any Person ... aware that Content was obtained from the Database ... and that it
> is available under this License." Example: "Contains information from DATABASE NAME, which is made
> available here under the Open Database License (ODbL)."
> 4.5 b "Using this Database, a Derivative Database, or this Database as part of a Collective Database
> to create a Produced Work does not create a Derivative Database for purposes of Section 4.4"
> 4.5 c "Use of a Derivative Database internally within an organisation is not to the public and
> therefore does not fall under the requirements of Section 4.4."
> 4.6 "If You Publicly Use a Derivative Database or a Produced Work from a Derivative Database, You must
> also offer ... a. The entire Derivative Database; or b. A file containing all of the alterations made
> to the Database or the method of making the alterations to the Database (such as an algorithm) ..."

OSMF guidelines:
- Produced Work guideline (endorsed 2014-06-06,
  https://osmfoundation.org/wiki/Licence/Community_Guidelines/Produced_Work_-_Guideline): "If the
  published result of your project is intended for the extraction of the original data, then it is a
  database and not a Produced Work. Otherwise it is a Produced Work. However, if you publish a produced
  work, the underlying database has to be published as well (or alternations to the original database
  as is the case of derived databases), according to section 4.6 of ODbL."
- Guidelines index (https://osmfoundation.org/wiki/Licence/Community_Guidelines): a Produced Work
  "often means a map, but could be something else (a mug, a data visualisation...)".
- Substantial guideline (endorsed, https://osmfoundation.org/wiki/Licence/Community_Guidelines/Substantial_-_Guideline):
  "Less than 100 Features" is insubstantial; "A section of coastline is considered to be a feature -
  the whole coastline of a large landmass is made up of many linked features." A country's coast is
  substantial.
- Trivial Transformations (still "at the proposal stage",
  https://osmfoundation.org/wiki/Licence/Community_Guidelines/Trivial_Transformations_-_Guideline):
  "Purely algorithmic augmentation of data and re-casting of data ... is a "trivial transformation""
  and lists "Other applications of geometric and graph algorithms on OSM data ... if they are driven
  by OSM data only."
- Attribution guidelines (adopted 2021-06-25, https://osmfoundation.org/wiki/Licence/Attribution_Guidelines):
  "Attribution must be to "OpenStreetMap"." "... making the text "OpenStreetMap" a link to
  openstreetmap.org/copyright"; "The historical forms of attribution "© OpenStreetMap contributors" or
  "© OpenStreetMap" are acceptable."; "Attribution must be placed in the vicinity of the produced work
  or in a location where customarily attribution would be expected"; for databases: notices "such as a
  readme file, or within the data or metadata".

Assessment: a count map (or a count grid offered as data) made with an OSM sea mask is a Produced Work:
it is not meant for extracting coastline data (4.5 b, guideline). Duty: an ODbL notice where the
counts are shown and in any downloadable file's metadata. If the rasterised sea mask counts as a
Derivative Database, 4.6 applies to the Produced Work; the public source code that builds the mask
from OSM data alone is "the method of making the alterations (such as an algorithm)", and the
Trivial Transformations proposal would not ask even for that. Switzerland and Utah are inland and
use no coastline; Nominatim place names shown with the counts are OSM data too (Geocoding guideline:
credit OpenStreetMap).

### A combined credit block for the counts page (draft)

> Counts derived from: swissALTI3D and swissSURFACE3D Raster © swisstopo (Federal Office of
> Topography swisstopo); NMT and NMPT, source: Główny Urząd Geodezji i Kartografii (GUGiK),
> www.geoportal.gov.pl; USGS 3DEP 1 m DEM, map services and data available from U.S. Geological
> Survey, National Geospatial Program. Gaps filled with FABDEM V1-2 (Neal & Hawker 2023,
> doi:10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn, CC BY-NC-SA 4.0) and Copernicus DEM GLO-30: produced
> using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018
> provided under COPERNICUS by the European Union and ESA; all rights reserved. The organisations in
> charge of the Copernicus programme by law or by delegation do not incur any liability for any use
> of the Copernicus WorldDEM-30. Coastline: © OpenStreetMap contributors (ODbL,
> openstreetmap.org/copyright). The data providers do not endorse this work; how the counts are
> computed is described on the methods page.

### Keeping or mirroring raw data (for completeness)

| Data | Keep a copy | Mirror publicly |
| --- | --- | --- |
| swisstopo | yes | yes, with a source reference |
| GUGiK NMT/NMPT | yes | yes ("dowolnego wykorzystania", no licence), with source info |
| USGS 3DEP | yes | yes (public domain); acknowledgment appreciated, describe modifications |
| Copernicus GLO-30 | yes | yes, notices 6(a), 6(c), passed on to subsequent users (6(e)) |
| FABDEM | yes (NC use) | NC only, with attribution and the BY-NC-SA licence |
| OSM | yes | as a database under ODbL with the notice (4.2) |

## 5. E-mail draft to GUGiK (Polish, not sent)

To: gugik@gugik.gov.pl; Cc: sigservicedesk@geoportal.gov.pl (the English contact page names
service.desk@gugik.gov.pl for the same role)

Temat: Pobranie całego NMT (1 m, PL-EVRF2007-NH) i NMPT – preferowany sposób i tempo (projekt niekomercyjny)

> Szanowni Państwo,
>
> rozwijam Find-a-Line – bezpłatne, niekomercyjne narzędzie open source ([adres repozytorium]),
> które na podstawie danych wysokościowych wskazuje miejsca, w których można by rozpiąć highline,
> czyli taśmę zawieszoną wysoko nad terenem między dwoma punktami zaczepienia.
>
> Chciałbym jednorazowo pobrać dla całej Polski numeryczny model terenu w siatce 1 m
> (PL-EVRF2007-NH) oraz numeryczny model pokrycia terenu, a później pobierać już tylko arkusze
> zaktualizowane. Według moich szacunków to około 117 000 arkuszy, łącznie około 4–5 TB.
> Publikowane byłyby wyłącznie dane pochodne – liczba możliwych linii i miejsc w komórkach
> o powierzchni 1 km², bez wysokości i bez przebiegu linii – zawsze z informacją o źródle danych
> (art. 40c ust. 3 ustawy Prawo geodezyjne i kartograficzne).
>
> Nie chciałbym nadmiernie obciążać Państwa serwerów, dlatego mam kilka pytań:
> 1. Który sposób pobrania całego zbioru jest dla Państwa najwygodniejszy: pobieranie arkuszy
>    z opendata.geoportal.gov.pl według skorowidzów WFS, czy inny kanał, np. udostępnienie przez
>    serwer FTP/SFTP albo zapis na dysku dostarczonym przeze mnie (ust. 13 załącznika do ustawy)?
> 2. Jeśli mogę pobierać dane z opendata.geoportal.gov.pl, jakie tempo będzie akceptowalne (liczba
>    równoległych połączeń, przepustowość, preferowane godziny)? Proponuję [np. najwyżej dwa
>    połączenia naraz, głównie nocą i w weekendy]; każde zapytanie będzie miało w nagłówku
>    User-Agent nazwę projektu i mój adres e-mail.
> 3. Jeśli możliwe jest przekazanie danych na dysku: jak złożyć wniosek, jaki dysk przygotować
>    (pojemność, system plików) i jakie byłyby koszty?
> 4. Czy mają Państwo preferowane brzmienie informacji o źródle, np. „Źródło danych: Główny Urząd
>    Geodezji i Kartografii (NMT, NMPT)”?
>
> Z góry dziękuję za odpowiedź.
>
> Z poważaniem
> [Imię i nazwisko]
> [e-mail, telefon]
> [adres strony projektu]

## Pages that failed or needed workarounds

- https://www.swisstopo.admin.ch/en/conditions-geodata: HTTP 500 at first (WebFetch, curl), 200 later
  with curl; read in EN and DE (https://www.swisstopo.admin.ch/de/konditionen-geodaten).
- https://www.swisstopo.admin.ch/en/height-model-swisssurface3d-raster: HTTP 500; the DE page was used.
- geocat.ch: rendered in the browser; read through the GeoNetwork search API and record XML.
- https://www.geo.admin.ch/de/allgemeine-nutzungsbedingungen-bgdi/: the fair-use table is client-side;
  decoded from the page's `__NUXT_DATA__` payload.
- https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn: connection reset (curl, WebFetch);
  Wayback Machine 429; WebFetch cannot read web.archive.org. Used the DataCite record instead.
- https://www.fathom.global/product/global-terrain-data-fabdem/: no licence terms on the page.
- https://www.sciencebase.gov/catalog/item/543e6b86e4b0fd76af69cf4c: 403 Cloudflare challenge (curl,
  WebFetch); the collection citation above comes from a search snippet.
- usgs.gov FAQ and policy pages: 403 to curl; read with WebFetch (quotes split into fragments).
- https://tnmaccess.nationalmap.gov/api/v1/docs and https://apps.nationalmap.gov/uget-instructions/:
  client-rendered; read from the raw HTML (OpenAPI literal) and the JS bundle.
- EUR-Lex (Regulation (EU) 2023/138): 202 with an empty body (bot protection); not verified.
- INSPIRE geoportal search API: the POST failed (no response); GUGiK's own CSW was used.
- https://www.geoportal.gov.pl/pl/pomoc/pytania-i-odpowiedzi-faq/: no questions, only a pointer to
  the "Edukacja" module.
- catalog.data.gov CKAN API: 404.
