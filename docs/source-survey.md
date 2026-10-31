# Elevation data around the world: a survey of sources (2026-10-31)

What each country or region publishes, how Find-a-Line could get it, under which terms, and how much work each
source would be. It covers Europe, North and Central America with the Caribbean, Oceania (Australia and New
Zealand), South America and Asia; Poland, Slovakia, Switzerland, Spain, Malta and the USA are sources already,
Greece was looked at before (roadmap, "New data sources") and again here. How a source is researched:
[data-sources.md](data-sources.md); how many sources could be built and maintained:
[sources-architecture.md](sources-architecture.md).

- **The notes** per country, in the style of the roadmap's "New data sources" (data, access, versions, licence,
  orthophoto, quick tests, fit, open questions, links): [Europe](source-survey/europe.md),
  [North America](source-survey/north-america.md), [Oceania](source-survey/oceania.md),
  [South America](source-survey/south-america.md), [Asia](source-survey/asia.md).
- **The rows** as data, one source per line: [source-survey/sources.json](source-survey/sources.json) (the fields
  are described at the end).

## How it was done
- Seventeen groups of countries were researched on 2026-10-31, each by an agent following one brief: the questions
  of [data-sources.md](data-sources.md) §1, the national agencies' own pages and terms, catalogues (INSPIRE,
  data.europa.eu, national CKAN portals, OpenTopography, the AWS Registry of Open Data), and quick read-only tests of
  every source with an automatic access method (§3: capabilities, one request of at most 500 × 500 m, one STAC or
  index page, the header of one file, a window of a COG, an orthophoto tile), with a cap of 50 MB per download.
- A region has a row of its own where it publishes its own data and the national data is weaker or missing
  (Germany's Länder, Italy's regions, Canada's provinces, the UK's nations, Australia's states...). Countries with
  nothing usable have short rows.
- **Priority**: *high* = notable highline terrain, a terrain model of 2 m or finer, terms that allow a public
  non-commercial site, and an automatic way to get it; *medium* = one of these weaker (5 m, partial coverage,
  unclear terms, an account, little terrain); *low* = poor data or little terrain; *none* = nothing better than
  FABDEM. **Effort**: S = an existing class configured, M = a new subclass or index in a known pattern, L = a new
  mechanism (own hosting, archives, composing versions).
- Checked afterwards: every row's fields; 12 endpoints of the top candidates requested again independently
  (Austria, England, Norway, France, Canada, Bavaria, New Zealand, Japan, Shizuoka, Tasmania: all as reported);
  every link (see the end).
- **Limits**: the quick tests are not the data checks of a new source ([regression-tests.md](regression-tests.md),
  "Data checks for a new source": shift against Copernicus, coverage at 5 m, tiles against files), which come with
  the implementation. Terms were read on the agencies' pages, but a person should read them again before a source
  goes public. Several services were down or refused scripts on the day; their rows say so.

## Summary

| Continent | high | medium | low | none | rows |
| --- | --- | --- | --- | --- | --- |
| Europe | 14 | 25 | 30 | 25 | 94 |
| North America | 1 | 9 | 16 | 27 | 53 |
| Oceania | 2 | 3 | 3 | 2 | 10 |
| South America | 0 | 2 | 8 | 13 | 23 |
| Asia | 2 | 2 | 6 | 41 | 51 |
| All | 19 | 41 | 63 | 108 | 231 |

- **Europe** has most of the open data, thanks to the High Value Datasets regulation (2023/138): all 16 German
  Länder publish 1 m terrain models, so do Austria, France (0.5 m), the UK's nations, Norway, the Benelux, Czechia
  (2 m), Portugal and many Italian regions. Southeast Europe (Croatia, Romania, Bulgaria, Greece and the Balkans)
  has surveys but little open access yet; Hungary sells its data.
- **North America**: Canada's federal catalogue (HRDEM, OGL-Canada) carries the open lidar of every province as
  1 m terrain and surface models. Mexico has a 5 m lidar terrain model of about half the country behind
  undocumented endpoints. Central America and the Caribbean have almost nothing (the Caribbean Netherlands are the
  exception), Greenland only ArcticDEM.
- **Oceania**: New Zealand publishes a national 1 m composite (DTM and DSM, CC BY 4.0) as COGs; Australia's lidar
  is mostly behind ELVIS's ordering, with Tasmania's 2 m DEM and Queensland's ImageServer as the open ways.
- **South America and Asia**: fine elevation data is mostly restricted (defence or survey laws) or sold. The
  exceptions are Japan (1 m lidar as open tiles, Shizuoka and Tokyo at 0.5 m), Hong Kong (on order), Colombia (1–2 m
  in some municipalities), Espírito Santo in Brazil (2 m) and Uruguay (2.5 m). In the high mountains of Asia NASA's
  High Mountain Asia 8 m surface model is the only thing better than FABDEM.

## Suggested order
By value for highlining and cost, following [sources-architecture.md](sources-architecture.md), "Recommendation and
steps":
1. **With existing classes**: England (`gb-eng`, WCS, 1 m DTM and DSM), Lower Saxony (`de-ni`, STAC), Austria
   (`at`, windows of 50 km COGs on a fixed grid), Wales (`gb-wls`, one national COG), Saxony-Anhalt (`de-st`, WCS,
   no DSM), Bolzano (`it-bz`, WCS, 2.5 m in the Dolomites, CC0); then Hesse, Mecklenburg-Vorpommern, Luxembourg and
   Denmark (a token).
2. **New parts, each with the sources it unlocks**: France (`fr`, WFS index + WMS-R GeoTIFF, 0.5 m: the largest
   single gain), Norway (`no`, ATOM + windows), Canada (`ca`, STAC + windows: all provinces), the ImageServer reader
   (Czechia, Sicily, Ontario, Queensland, Colombia), New Zealand (`nz`, sheet grid + windows), Metalink (Bavaria,
   Rhineland-Palatinate), zipped grid files (Saxony, Baden-Württemberg), listings (Trento, North Rhine-Westphalia,
   Scotland, British Columbia), Japan's XYZ tiles (`jp`) and Shizuoka's files (`jp-22`), Portugal (`pt`, an account),
   Tasmania (`au-tas`, one COG), ArcticDEM (a gap filler for the Arctic).
3. **Own hosting, only where nothing else works** (as Slovakia): Wallonia (ZIPs of 46–56 GB), Croatia (on request),
   Hong Kong (on order), New South Wales' lidar.

## Sources by continent
"Files found by → read as": how the files of an area are found and how the heights are read (see
[sources-architecture.md](sources-architecture.md), "What the survey changes"); an existing class of `sources.py`
in brackets when the combination is one. "Public site": whether the terms allow a public non-commercial site to
download, cache and show lines derived from the data.

### Europe

| Source | DTM / DSM | Files found by → read as | Licence | Public site | Effort | Priority | Where it matters |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Austria (`at`) | 1 m / 1 m | grid → COG windows (`DegreeBlocks`) | CC BY 4.0 | yes | S | high | Alps (Tirol, Salzburg, Kärnten, Steiermark), Wachau and Danube valley… |
| Germany, Niedersachsen (`de-ni`) | 1 m / 1 m | STAC → file (`StacTiles`) | CC BY 4.0 | yes | S | high | Harz (Okertal granite), Ith and Hohenstein (Weserbergland limestone)… |
| Germany, Sachsen-Anhalt (`de-st`) | 1 m / – | grid → WCS (`WcsTiles`) | dl-de/by-2.0 | yes | S | high | Harz: Bodetal (Rosstrappe, Hexentanzplatz), Saale valley limestone… |
| United Kingdom, England (`gb-eng`) | 1 m / 1 m | grid → WCS (`WcsTiles`) | OGL v3 | yes | S | high | Peak District gritstone edges (Stanage, Froggatt, Curbar), Cornwall… |
| United Kingdom, Wales (`gb-wls`) | 1 m / 1 m | one file → COG windows | OGL v3 | yes | S | high | Snowdonia (Llanberis Pass, Ogwen, Cloggy), Pembroke sea cliffs (St… |
| Czechia (`cz`) | 2 m / 2 m | grid → ImageServer | CC BY 4.0 | yes | M | high | sandstone towers of Adršpach-Teplice, Bohemian Paradise (Prachovské… |
| Germany, Baden-Württemberg (`de-bw`) | 1 m / 1 m | grid → file (`DegreeTiles / GridTiles`) | dl-de/by-2.0 | yes | M | high | Swabian Jura (Danube valley at Beuron, Blautal, Lenninger Alb), Black… |
| Germany, Bayern (`de-by`) | 1 m / 0.2 m | Metalink → file | CC BY 4.0 | yes | M | high | Franconian Jura (Pottenstein, Wiesent valley), Danube gorge… |
| Germany, Rheinland-Pfalz (`de-rp`) | 1 m / 1 m | Metalink → file | dl-de/by-2.0 | yes | M | high | Pfälzerwald sandstone towers (Dahner Felsenland, Annweiler)… |
| Germany, Sachsen (`de-sn`) | 1 m / 1 m | grid → file (`DegreeTiles / GridTiles`) | dl-de/by-2.0 | yes | M | high | Elbsandstein (Saxon Switzerland: Bastei, Schrammsteine, Affensteine)… |
| France (`fr`) | 0.5 m / 0.5 m | WFS → WMS-R | Licence Ouverte 2.0 | yes | M | high | Verdon, Calanques, Vercors, Chartreuse, Corsica (Bavella)… |
| Italy, Autonomous Province of Trento (`it-tn`) | 0.5 m / 0.5 m | listing → file | CC BY 4.0 | yes | M | high | Arco and the Sarca valley, Brenta Dolomites, Pale di San Martino, Val… |
| Norway (`no`) | 1 m / 1 m | ATOM → COG windows | CC BY 4.0 | yes | M | high | Kjerag, Preikestolen, Lysefjord, Romsdal, Lofoten, Senja, fjords… |
| Portugal, mainland (Continente) (`pt`) | 0.5 m / 0.5 m | API → file | CC BY 4.0 (account) | yes | M | high | Sintra, Arrabida, Cabo da Roca and Algarve sea cliffs, Serra da… |
| Bulgaria (`bg`) | 1 m / 4 m | grid → WCS (`WcsTiles`) | unclear | unclear | S | medium | Vratsa (Vratsata), Rhodopes gorges (Trigrad), Belogradchik, Kaliakra… |
| Germany, Hessen (`de-he`) | 1 m / 1 m | grid → WCS (`WcsTiles`) | dl-de/zero-2.0 | yes | S | medium | Rhön basalt, Edersee/Kellerwald, Lahn valley, quarries: low-medium |
| Germany, Mecklenburg-Vorpommern (`de-mv`) | 1 m / 1 m | grid → WCS (`WcsTiles`) | CC BY 4.0 | yes | S | medium | Rügen chalk cliffs (Jasmund, ~120 m, crumbling chalk), Baltic cliffs… |
| Denmark (`dk`) | 0.4 m / 0.4 m | grid → WCS (`WcsTiles`) | free terms (token) | yes | S | medium | Mons Klint chalk cliffs, Bornholm granite (Jons Kapel, Hammeren)… |
| Faroe Islands (`fo`) | 10 m / 2 m | one file → COG windows | free terms | yes | S | medium | huge sea cliffs (Vestmanna, Enniberg, Mykines): high terrain |
| Italy, Liguria (`it-42`) | 5 m / 1 m | grid → WCS (`WcsTiles`) | unclear | unclear | S | medium | Finale Ligure (sea and inland crags), Muzzerone, Cinque Terre cliffs… |
| Italy, Autonomous Province of Bolzano / South Tyrol (`it-bz`) | 2.5 m / 2.5 m | grid → WCS (`WcsTiles`) | CC0 | yes | S | medium | Dolomites (Sassolungo, Sella, Tre Cime north side, Odle): very high… |
| Luxembourg (`lu`) | 0.5 m / 0.5 m | one file → COG windows | CC0 | yes | S | medium | Mullerthal sandstone (Berdorf climbing), Sûre/Our valleys: medium |
| Portugal, Azores (Acores) (`pt-20`) | 1 m / 1 m | API → file (as `pt`) | CC BY 4.0 (account) | yes | S | medium | sea cliffs, calderas (Sete Cidades, Faja do Sao Jorge, Flores): medium |
| Sweden (`se`) | 1 m / – | STAC → file (`StacTiles`) | CC BY 4.0 (account) | yes | S | medium | Bohuslan granite, Kullaberg, High Coast (Hoga Kusten), Lapland… |
| Germany, Nordrhein-Westfalen (`de-nw`) | 1 m / 1 m | listing → file | dl-de/zero-2.0 | yes | M | medium | Sauerland (Bruchhauser Steine), Eifel sandstone (Rurtal)… |
| Germany, Thüringen (`de-th`) | 1 m / 1 m | ATOM → file | dl-de/by-2.0 (unconfirmed) | yes | M | medium | Saale valley limestone (Jena Kernberge), Thuringian Forest… |
| Finland (`fi`) | 2 m / – | grid → COG windows (`DegreeBlocks`) | CC BY 4.0 | yes | M | medium | Olhava, Korouoma, Julma-Olkky, Lapland fells; few big cliffs… |
| United Kingdom, Scotland (`gb-sct`) | 0.5 m / 0.5 m | listing → COG windows | OGL v3 | yes | M | medium | Highlands, Glen Coe, Skye (Cuillin), Arran, sea stacks and sea cliffs… |
| Ireland (`ie`) | 2 m / 2 m | FeatureServer → file | CC BY 4.0 | yes | M | medium | Cliffs of Moher, Burren, Ailladie, Kerry and Donegal sea cliffs… |
| Iceland (`is`) | 2 m / – | one file → COG windows | open (text unconfirmed) | unclear | M | medium | basalt canyons and sea cliffs (Asbyrgi, Hljodaklettar, Vestrahorn… |
| Italy, Toscana (`it-52`) | 1 m / 1 m | WFS → file (`SheetTiles`) | CC BY 4.0 / CC BY-SA 3.0 | yes | M | medium | Apuan Alps (marble cliffs), Elba and Argentario sea cliffs: high |
| Italy, Sicilia (`it-82`) | 2 m / – | grid → ImageServer | unclear | unclear | M | medium | San Vito lo Capo, Monte Pellegrino (Palermo), Cava d'Ispica, Etna… |
| Slovenia (`si`) | 1 m / – | listing → file | attribution (unconfirmed) | unclear | M | medium | Julian Alps, Osp / Mišja peč, Kamnik-Savinja Alps, Soča gorges: very… |
| Belgium, Wallonia (`be-wal`) | 0.5 m / 0.5 m | own copy → own copy | CC BY 4.0 | yes | L | medium | Meuse valley (Freyr, Dinant, Marche-les-Dames), Ourthe and Amblève… |
| Croatia (`hr`) | 1 m / 1 m | own copy → own copy | DGU licence (a clause) | unclear | L | medium | Paklenica, Omiš/Cetina, Dalmatian sea cliffs, Velebit, Biokovo: very… |
| Italy (`it`) | 1 m / 1 m | WFS → manual | CC BY 4.0 | unclear | L | medium | Coasts (Liguria, Sardinia, Sicily, Campania) and river gorges; little… |
| Italy, Valle d'Aosta (`it-23`) | 2 m / – | - → manual | CC BY 4.0 | unclear | L | medium | Aosta valley crags, Gran Paradiso, Monte Bianco side valleys: high |
| Italy, Friuli-Venezia Giulia (`it-36`) | 0.5 m / 0.5 m | - → manual | unclear | unclear | L | medium | Julian and Carnic Alps, Dolomiti Friulane, Val Rosandra (Trieste… |
| Romania (`ro`) | 0.5 m / – | - → manual | OGL-ROU | yes | L | medium | Bicaz gorge, Cheile Turzii, Carpathian limestone (Piatra Craiului… |

<details><summary>55 sources of low priority or without open data</summary>

| Source | DTM / DSM | Access | Licence | Priority |
| --- | --- | --- | --- | --- |
| Finland, Aland (`ax`) | 2 m / – | vsicurl-COG, WCS, API-key | CC BY 4.0 | low |
| Cyprus (`cy`) | 5 m / – | portal-manual | not stated (DLS disclaimer); the Zenodo mirror… | low |
| Germany, Brandenburg (`de-bb`) | 1 m / – | index+files, WCS | Datenlizenz Deutschland Namensnennung 2.0… | low |
| Germany, Berlin (`de-be`) | 1 m / – | ATOM | Datenlizenz Deutschland – Zero – Version 2.0… | low |
| Germany, Bremen (`de-hb`) | 1 m / – | archives, ATOM | CC BY 4.0, credit 'Landesamt GeoInformation… | low |
| Germany, Hamburg (`de-hh`) | 1 m / – | archives | Datenlizenz Deutschland – Namensnennung – Version… | low |
| Germany, Schleswig-Holstein (`de-sh`) | 1 m / 0.2 m | index+files | CC BY 4.0: 'Jede Nutzung ist unter den… | low |
| Germany, Saarland (`de-sl`) | 1 m / – | WMS-only | dl-de/by-2.0 per DGM1 metadata (©LVGL 2022)… | low |
| Estonia (`ee`) | 1 m / 1 m | index+files, vsicurl-COG | Maa- ja Ruumiamet open data licence (2025): free… | low |
| United Kingdom, Northern Ireland (`gb-nir`) | 10 m / 1 m | archives | Open Government Licence (OpenDataNI license_title… | low |
| Italy, Piemonte (`it-21`) | 5 m / – | portal-manual | unclear | low |
| Italy, Lombardia (`it-25`) | 5 m / – | portal-manual | unclear | low |
| Italy, Veneto (`it-34`) | 5 m / – | portal-manual, WMS-only | IODL 2.0 | low |
| Italy, Emilia-Romagna (`it-45`) | 5 m / – | WCS | CC BY 4.0 for the 2023 flood DTM; 5x5 DTM unclear | low |
| Italy, Umbria (`it-55`) | – / – | none | unclear | low |
| Italy, Marche (`it-57`) | – / – | none | unclear | low |
| Italy, Lazio (`it-62`) | – / – | portal-manual | unclear | low |
| Italy, Abruzzo (`it-65`) | – / – | none | unclear | low |
| Italy, Molise (`it-67`) | – / – | none | unclear | low |
| Italy, Campania (`it-72`) | – / – | none | unclear | low |
| Italy, Puglia (`it-75`) | – / – | portal-manual | unclear | low |
| Italy, Basilicata (`it-77`) | – / – | portal-manual | unclear | low |
| Italy, Calabria (`it-78`) | – / – | none | unclear | low |
| Italy, Sardegna (`it-88`) | 1 m / 1 m | WCS, portal-manual | unclear (metadata 'Other restrictions', keyword… | low |
| Italy, TINITALY 10 m (national fallback) (`it-tinitaly`) | 10 m / – | archives | CC BY 4.0 | low |
| Latvia (`lv`) | 20 m / – | portal-manual | CC BY 4.0 (LGIA open data page) | low |
| Monaco (`mc`) | 0.5 m / 0.5 m | WMS-only, index+files | Licence Ouverte 2.0 (IGN's data) | low |
| Netherlands (`nl`) | 0.5 m / 0.5 m | WCS, ATOM, vsicurl-COG | CC0 1.0 (AHN open data) | low |
| Portugal, Madeira (`pt-30`) | 5 m / – | on-request | not specified (dados.gov.pt: 'License Not… | low |
| Svalbard and Jan Mayen (`sj`) | 5 m / – | ATOM, archives | CC BY 4.0 | low |
| Andorra (`ad`) | – / – | portal-manual | Avis legal: private and personal use only… | none |
| Albania (`al`) | – / – | WMS-only | unclear; files on request | none |
| Armenia (`am`) | – / – | none | – | none |
| Azerbaijan (`az`) | – / – | none | – | none |
| Bosnia and Herzegovina (`ba`) | – / – | none | not published | none |
| Belgium, Brussels-Capital (`be-bru`) | – / – | archives | UrbIS open data licence | none |
| Belgium, Flanders (`be-vlg`) | 1 m / 1 m | WCS, archives | Modellicentie Gratis Hergebruik (Flemish open… | none |
| Belarus (`by`) | – / – | none | none open | none |
| Germany (`de`) | 1 m / 1 m | on-request | fee licence through ZSGT (AdV fee rules); free… | none |
| Georgia (`ge`) | – / – | none | – | none |
| Guernsey (`gg`) | – / – | none | Digimap Guernsey data are licensed commercially | none |
| Gibraltar (`gi`) | – / – | none | – | none |
| Greece (`gr`) | 1 m / 1 m | none | not published | none |
| Hungary (`hu`) | – / – | on-request | paid (Lechner geoshop, Envimap shop); no open… | none |
| Isle of Man (`im`) | – / – | on-request | commercial (Bluesky Mapshop since 2016) | none |
| Jersey (`je`) | – / – | none | – | none |
| Lithuania (`lt`) | 5 m / – | on-request | per-package licence; release restricted 'due to… | none |
| Moldova (`md`) | 5 m / – | WMS-only | unclear | none |
| Montenegro (`me`) | – / – | none | not published | none |
| North Macedonia (`mk`) | – / – | on-request | paid product | none |
| Serbia (`rs`) | 5 m / – | on-request | not open (OSM community: laws and project… | none |
| San Marino (`sm`) | – / – | none | unclear | none |
| Ukraine (`ua`) | – / – | none | no open elevation data; geodata restricted under… | none |
| Vatican City (`va`) | – / – | none | – | none |
| Kosovo (`xk`) | – / – | none | not published | none |

</details>

### North America

| Source | DTM / DSM | Files found by → read as | Licence | Public site | Effort | Priority | Where it matters |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Canada (`ca`) | 1 m / 1 m | STAC → COG windows | OGL-Canada | yes | M | high | Squamish / Sea-to-Sky, Bow Valley (Canmore), Niagara Escarpment, Bon… |
| Canada, Alberta (`ca-ab`) | 1 m / 1 m | STAC → COG windows (as `ca`) | OGL-Canada | yes | S | medium | Bow Valley / Canmore, Kananaskis, Rockies: very high |
| Canada, Newfoundland and Labrador (`ca-nl`) | 1 m / 1 m | STAC → COG windows (as `ca`) | OGL-Canada | yes | S | medium | Newfoundland sea cliffs, Gros Morne fjords: high (coverage partial) |
| Canada, Quebec (`ca-qc`) | 1 m / 1 m | STAC → COG windows (as `ca`) | OGL-Canada / CC BY 4.0 | yes | S | medium | Val-David, Saguenay fjord, Gaspesie (Perce), Charlevoix: very high |
| Arctic (multi-country), all land north of ~60 N + Alaska (Greenland, Iceland, Norway N of ~60, Sweden, Finland, Svalbard, Canada N of 60, Russia) (`arcticdem`) | – / 2 m | STAC → COG windows | CC BY 4.0 | yes | M | medium | Greenland fjords, Lofoten/Senja (N Norway), Iceland, Svalbard, Baffin… |
| Caribbean Netherlands, Bonaire, Sint Eustatius, Saba (`bq`) | 0.5 m / 0.5 m | grid → WCS (`WcsTiles`) | CC BY 4.0 | yes | M | medium | Saba (sea cliffs, steep volcano), Statia (The Quill crater): medium… |
| Canada, British Columbia (`ca-bc`) | 1 m / 1 m | listing → COG windows | OGL-BC | yes | M | medium | Squamish Chief, Sea-to-Sky, Skaha, Gwaii Haanas coast: very high |
| Canada, Ontario (`ca-on`) | 0.5 m / 0.5 m | grid → ImageServer | OGL-Ontario | yes | M | medium | Niagara Escarpment (Lion's Head, Bruce Peninsula), Bon Echo, Lake… |
| Greenland (`gl`) | – / 2 m | STAC → COG windows (as `arcticdem`) | CC BY 4.0 | yes | M | medium | Tasermiut fjord (Ketil, Ulamertorsuaq), Uummannaq, Sermersooq/East… |
| Mexico (`mx`) | 5 m / 5 m | API → file | INEGI free use | yes | M | medium | El Potrero Chico, Huasteca and El Salto (Nuevo Leon), El Chico… |

<details><summary>43 sources of low priority or without open data</summary>

| Source | DTM / DSM | Access | Licence | Priority |
| --- | --- | --- | --- | --- |
| Saint-Barthelemy (France) (`bl`) | – / – | unclear | Licence Ouverte Etalab 2.0 (if IGN covers it) | low |
| Canada, Manitoba (`ca-mb`) | 1 m / 1 m | STAC, vsicurl-COG | OGL - Canada | low |
| Canada, New Brunswick (`ca-nb`) | 1 m / 1 m | ImageServer, index+files | Open Government Licence (GeoNB) | low |
| Canada, Nova Scotia (`ca-ns`) | 1 m / 1 m | portal-manual | unclear (NS open / unrestricted licence PDFs) | low |
| Canada, Northwest Territories (`ca-nt`) | 1 m / 1 m | STAC, vsicurl-COG | OGL - Canada | low |
| Canada, Nunavut (`ca-nu`) | 1 m / 2 m | STAC, vsicurl-COG | OGL - Canada (ArcticDEM part: PGC terms… | low |
| Canada, Prince Edward Island (`ca-pe`) | 1 m / 1 m | STAC, vsicurl-COG | OGL - Canada | low |
| Canada, Saskatchewan (`ca-sk`) | 1 m / 1 m | STAC, vsicurl-COG | OGL - Canada | low |
| Canada, Yukon (`ca-yt`) | 1 m / 1 m | STAC, vsicurl-COG | OGL - Canada | low |
| Global, FathomDEM and GEDTM30 (newer global DTMs) (`fathomdem`) | 30 m / – | on-request, vsicurl-COG | FathomDEM CC BY-NC-SA 4.0 (as FABDEM); GEDTM30 CC… | low |
| Guadeloupe (France) (`gp`) | – / – | unclear | Licence Ouverte Etalab 2.0 (if IGN covers it) | low |
| Haiti (`ht`) | 1.5 m / – | vsicurl-COG, portal-manual | not provided (OpenTopography: 'Not Provided'… | low |
| Saint-Martin (France) (`mf`) | – / – | unclear | Licence Ouverte Etalab 2.0 (if IGN covers it) | low |
| Martinique (France) (`mq`) | – / – | unclear | Licence Ouverte Etalab 2.0 (if IGN covers it) | low |
| Saint-Pierre-et-Miquelon (France) (`pm`) | – / – | unclear | Licence Ouverte Etalab 2.0 (if IGN covers it) | low |
| Saint Vincent and the Grenadines (`vc`) | 0.6 m / – | portal-manual | CC0 1.0 | low |
| Antigua and Barbuda (`ag`) | – / – | none | – | none |
| Anguilla (`ai`) | – / – | none | – | none |
| Aruba (`aw`) | – / – | none | – | none |
| Barbados (`bb`) | – / – | none | – | none |
| Bermuda (`bm`) | – / – | none | – | none |
| Bahamas (`bs`) | – / – | none | – | none |
| Belize (`bz`) | – / – | none | – | none |
| Costa Rica (`cr`) | – / – | none | – | none |
| Cuba (`cu`) | – / – | none | – | none |
| Curacao (`cw`) | – / – | none | – | none |
| Dominica (`dm`) | – / – | none | – | none |
| Dominican Republic (`do`) | – / – | none | – | none |
| Grenada (`gd`) | – / – | none | – | none |
| Guatemala (`gt`) | – / – | none | – | none |
| Honduras (`hn`) | – / – | none | – | none |
| Jamaica (`jm`) | – / – | none | – | none |
| Saint Kitts and Nevis (`kn`) | – / – | none | – | none |
| Cayman Islands (`ky`) | – / – | none | – | none |
| Saint Lucia (`lc`) | – / – | none | – | none |
| Montserrat (`ms`) | – / – | none | – | none |
| Nicaragua (`ni`) | – / – | none | – | none |
| Panama (`pa`) | – / – | none | – | none |
| El Salvador (`sv`) | – / – | none | – | none |
| Sint Maarten (`sx`) | – / – | none | – | none |
| Turks and Caicos (`tc`) | – / – | none | – | none |
| Trinidad and Tobago (`tt`) | – / – | none | – | none |
| British Virgin Islands (`vg`) | – / – | none | – | none |

</details>

### Oceania

| Source | DTM / DSM | Files found by → read as | Licence | Public site | Effort | Priority | Where it matters |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Australia, Tasmania (`au-tas`) | 2 m / – | one file → COG windows | CC BY 3.0 AU | yes | S | high | Tasman Peninsula sea cliffs (Cape Hauy, Totem Pole, Cape Pillar, Cape… |
| New Zealand (`nz`) | 1 m / 1 m | grid → COG windows (`DegreeBlocks`) | CC BY 4.0 | yes | M | high | very high: Castle Hill / Kura Tawhiti, Paynes Ford, Whanganui Bay and… |
| Australia (`au`) | 5 m / – | one file → COG windows | CC BY 4.0 | yes | M | medium | Blue Mountains, Grampians, Arapiles, Tasman Peninsula, Frog Buttress… |
| Australia, Queensland (`au-qld`) | 0.5 m / – | grid → ImageServer | CC BY-SA | yes | M | medium | Frog Buttress (Mt French), Glass House Mountains, Kangaroo Point… |
| Australia, New South Wales (`au-nsw`) | 1 m / – | own copy → own copy | CC BY 4.0 | yes | L | medium | Blue Mountains (Katoomba, Blackheath, Mount Victoria, Grose Valley)… |

<details><summary>5 sources of low priority or without open data</summary>

| Source | DTM / DSM | Access | Licence | Priority |
| --- | --- | --- | --- | --- |
| Australia, Australian Capital Territory (`au-act`) | 1 m / – | portal-manual | CC BY 4.0, '(c) Australian Capital Territory and… | low |
| Australia, South Australia (`au-sa`) | 1 m / 1 m | portal-manual | CC BY 4.0 ('LiDAR classified point clouds and… | low |
| Australia, Victoria (`au-vic`) | 1 m / – | API-key, on-request | 1 m: licensed, fees (Data Access Licence… | low |
| Australia, Northern Territory (`au-nt`) | 5 m / – | archives | CC BY 4.0 | none |
| Australia, Western Australia (`au-wa`) | 5 m / – | on-request | Landgate Personal Use Licence / fees | none |

</details>

### South America

| Source | DTM / DSM | Files found by → read as | Licence | Public site | Effort | Priority | Where it matters |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Brazil, Espirito Santo (`br-es`) | 2 m / 2 m | grid → COG windows (`DegreeBlocks`) | unclear | unclear | M | medium | Pedra Azul, Forno Grande, Pancas and the granite domes of the… |
| Colombia (`co`) | 1 m / 12.2 m | FeatureServer → ImageServer | unclear (CC BY 4.0?) | unclear | L | medium | Suesca (only the town end at 1 m, rest 10 m), Jerico/Jardin 2 m… |

<details><summary>21 sources of low priority or without open data</summary>

| Source | DTM / DSM | Access | Licence | Priority |
| --- | --- | --- | --- | --- |
| Argentina (`ar`) | 5 m / – | portal-manual | unclear: IGN download terms… | low |
| Argentina, Cordoba (`ar-x`) | 5 m / – | WCS | unclear (provincial portal; IGN data) | low |
| Brazil, Rio de Janeiro (city) (`br-rj`) | 5 m / – | WMS-only, on-request | IPP items: 'uso publico, citadas as fontes e sem… | low |
| Brazil, Santa Catarina (`br-sc`) | 1 m / 1 m | portal-manual | unclear | low |
| Brazil, Sao Paulo (state and city) (`br-sp`) | – / – | archives, portal-manual | city: open (licence text not found) | low |
| Ecuador (`ec`) | 3 m / – | portal-manual, on-request | contradictory: CKAN 'CC BY-SA'; the dataset's own… | low |
| France, French Guiana (`gf`) | 1 m / – | WMS-only, archives | Licence Ouverte / Etalab 2.0 | low |
| Uruguay (`uy`) | 2.5 m / 0.1 m | index+files, vsicurl-COG | Licencia de Datos Abiertos - Uruguay (v0.1)… | low |
| Bolivia (`bo`) | – / – | none | – | none |
| Brazil (`br`) | 20 m / 20 m | index+files, archives | unclear: no licence file in the folder (IBGE… | none |
| Brazil, Distrito Federal (`br-df`) | – / – | none | – | none |
| Brazil, Minas Gerais (`br-mg`) | 30 m / – | WCS | – | none |
| Brazil, Parana (`br-pr`) | – / – | none | – | none |
| Brazil, Rio Grande do Sul (`br-rs`) | – / – | none | unclear (publication not announced) | none |
| Chile (`cl`) | 12.5 m / – | portal-manual | datos.gob.cl lists the IDE categories as Creative… | none |
| Falkland Islands (`fk`) | – / – | none | – | none |
| Guyana (`gy`) | – / – | none | – | none |
| Peru (`pe`) | – / – | none | – | none |
| Paraguay (`py`) | – / – | none | – | none |
| Suriname (`sr`) | – / – | none | – | none |
| Venezuela (`ve`) | – / – | none | – | none |

</details>

### Asia

| Source | DTM / DSM | Files found by → read as | Licence | Public site | Effort | Priority | Where it matters |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Japan (`jp`) | 1 m / – | grid → XYZ tiles | GSI terms (attribution) | unclear | M | high | Ogawayama / Mizugaki (granite domes), Jogasaki sea cliffs (Izu)… |
| Japan, Shizuoka (VIRTUAL SHIZUOKA) (`jp-22`) | 0.5 m / – | grid → file (`DegreeTiles / GridTiles`) | CC BY 4.0 / ODbL | yes | M | high | Jogasaki sea cliffs (Izu, a known highline spot), Izu coast, Fuji… |
| Japan, Tokyo (Tokyo Digital Twin point clouds) (`jp-13`) | 0.5 m / – | listing → file | CC BY | yes | M | medium | Okutama gorges and crags (Hatonosu, Mitake), Izu Islands sea cliffs… |
| Hong Kong (`hk`) | 0.5 m / 0.5 m | own copy → own copy | open data T&C | unclear | L | medium | Lion Rock, Kowloon Peak, Shek O and Tung Lung Chau sea cliffs… |

<details><summary>47 sources of low priority or without open data</summary>

| Source | DTM / DSM | Access | Licence | Priority |
| --- | --- | --- | --- | --- |
| High Mountain Asia (multi-country: kg, kz, tj, uz, af, pk, in, np, bt, cn), lat 26-46 N, lon 67-103 E, mountain areas (`hma`) | – / 8 m | API-key, index+files | NASA data, no licence stated; 'As a condition of… | low |
| Indonesia (`id`) | 8 m / – | portal-manual, API-key | unclear: data.go.id marks the DEMNAS index… | low |
| Sri Lanka (`lk`) | 20 m / 0.5 m | archives | Creative Commons Attribution 4.0 (CKAN… | low |
| Malaysia (`my`) | – / – | on-request | unclear (archive listing; JUPEM terms: restricted… | low |
| Philippines (`ph`) | 1 m / 1 m | index+files, on-request | Taal: 'We don't have a final license yet but for… | low |
| Taiwan (`tw`) | 20 m / 20 m | archives | 政府資料開放授權條款-第1版 (Open Government Data License v1… | low |
| United Arab Emirates (`ae`) | – / – | none | – | none |
| Afghanistan (`af`) | – / – | none | no open national DEM (USGS's 2013 Afghanistan… | none |
| Bangladesh (`bd`) | – / – | none | no open DEM found | none |
| Bahrain (`bh`) | – / – | none | – | none |
| Brunei (`bn`) | – / – | none | – | none |
| Bhutan (`bt`) | – / – | on-request | unclear (third-party metadata says free for… | none |
| China (`cn`) | – / – | none | classified under 测绘地理信息管理工作国家秘密范围的规定 (2020)… | none |
| Israel (`il`) | 25 m / 1 m | on-request | MAPI: copyright, uses by request to the Survey's… | none |
| India (`in`) | 10 m / 30 m | portal-manual, on-request | SoI: single-user licence, Rs 3300 per sheet… | none |
| Iraq (`iq`) | – / – | none | – | none |
| Iran (`ir`) | – / – | WMS-only | unclear | none |
| Jordan (`jo`) | 900 m / – | on-request | sale | none |
| Kyrgyzstan (`kg`) | – / – | none | no open national DEM; CAIAG's ASTER-based layers… | none |
| Cambodia (`kh`) | – / – | none | – | none |
| North Korea (`kp`) | – / – | none | – | none |
| South Korea (`kr`) | 90 m / – | portal-manual, on-request | data.go.kr: free, '이용허락범위 제한 없음' for the public… | none |
| Kuwait (`kw`) | – / – | none | – | none |
| Kazakhstan (`kz`) | – / – | none | no open DEM found; topographic data of the… | none |
| Laos (`la`) | – / – | none | – | none |
| Lebanon (`lb`) | – / – | none | – | none |
| Myanmar (`mm`) | – / – | none | – | none |
| Mongolia (`mn`) | – / – | none | – | none |
| Macau (`mo`) | – / – | none | – | none |
| Maldives (`mv`) | – / – | none | no open DEM found | none |
| Nepal (`np`) | 1 m / – | on-request | unclear; Survey Department sells maps and data… | none |
| Oman (`om`) | – / – | on-request | defence agency; terms of a request unclear | none |
| Pakistan (`pk`) | – / – | none | no open DEM; only the 30 arc-second Global Map… | none |
| Palestine (`ps`) | – / – | none | – | none |
| Qatar (`qa`) | – / – | none | – | none |
| Russia (`ru`) | – / – | none | large-scale relief is restricted: Federal Law… | none |
| Saudi Arabia (`sa`) | – / – | on-request | GEOSA open data: 'without technical, financial… | none |
| Singapore (`sg`) | – / – | on-request | SLA licensing (government and research projects) | none |
| Syria (`sy`) | – / – | none | – | none |
| Thailand (`th`) | – / – | none | – | none |
| Tajikistan (`tj`) | – / – | none | no open DEM found | none |
| Timor-Leste (`tl`) | – / – | none | – | none |
| Turkmenistan (`tm`) | – / – | none | no open DEM found | none |
| Turkey (`tr`) | 30 m / – | on-request | sale (HGM, İBB); CBSGM/ULASAV open data licence… | none |
| Uzbekistan (`uz`) | – / – | none | no open DEM found | none |
| Vietnam (`vn`) | – / – | none | – | none |
| Yemen (`ye`) | – / – | none | – | none |

</details>

## What to watch for when implementing
- **Half-pixel origins**: France's LiDAR HD (pixel centres on whole and half metres), Tasmania's 2 m DEM (origin off
  whole metres), Bolzano's 0.5 m coverages: `grid_origin`, as for Poland.
- **Heights**: ArcticDEM and Greenland are above the WGS84 ellipsoid (a geoid correction before gap filling);
  Espírito Santo and Liguria's 5 m DTM are whole metres; Mecklenburg-Vorpommern stores the sea as 0, not nodata;
  Corsica uses IGN78, not NGF-IGN69; Italy's regions name their vertical datum rarely.
- **Services**: Norway's WCS 2.0.1 fails where 1.0.0 works; the Caribbean Netherlands serve WCS 1.1.1; Saxony-Anhalt
  answers multipart; Wallonia's server and one English survey tile ignore HTTP Range (a test streamed 477 MB before
  it was stopped): read with a byte cap; Flanders' firewall refuses subsetting parameters; Czechia's ImageServer
  interpolates from a TIN of thinned points (compare with Copernicus first); Colombia's ImageServers serve the
  coarse raster unless the fine one is asked for.
- **Access**: Portugal and Sweden need a free account, Denmark and Finland a token, New Zealand's and Norway's
  orthophotos a key; Australia's ELVIS refuses our User-Agent (403) and its buckets are requester-pays (not worked
  around); Berlin, data.gov.il, data.go.th and gov.im refuse scripts.
- **Versions**: Austria publishes yearly editions of the whole country; Scotland, British Columbia, New Zealand's
  surveys and Canada's projects overlap and need composing per block (as `TnmBlocks`); Thuringia has two survey
  periods.
- **No surface model** in 15 of the 60 high and medium sources (Saxony-Anhalt, Sweden, Finland, Japan, Tasmania,
  Queensland...): lines over trees are not marked there, as in the USA.
- **No open orthophoto** for the UK, Canada, Australia (national) and parts of Italy: the map falls back to Esri or
  OpenStreetMap.

## Open questions and requests
- **Terms to confirm**: Bulgaria (WCS with no fees stated, the orthophoto sold), Espírito Santo (no licence
  stated), Colombia (Resolución 616/2020, a scanned PDF), Sicily (none stated), Slovenia's newer survey, Iceland's
  2 m, Japan (does a site caching GSI tiles need an approval under Art. 30 of the Survey Act?), Queensland's
  share-alike (does it reach derived lines?), Croatia (a clause against publishing readable coordinates and heights).
- **Requests to agencies**: Geoscience Australia (automated access to ELVIS for a non-commercial site), LINZ (a
  developer key for the orthophoto), Croatia's DGU (the clause), Rio de Janeiro (the 2019 lidar as data), Bulgaria's
  ministry (terms and vertical datum).
- **Look again later**: Italy's national PST portal (in maintenance until 2026-11-06), Romania's geoportal (offline
  after a ransomware attack), Thuringia's download server, Quebec's server, Argentina's IGN (DNS), Greece's new
  lidar, Israel's GovMap 3D release, Scotland's national programme (to 2027), Otago in New Zealand (2026–28).

## The data file
`source-survey/sources.json` is a JSON array, one object per source and line, as the agents wrote them plus:
`continent`, `group` (the research group), `public` (yes/no/unclear, from `public_site_ok`), and for high and medium
rows `index`, `read`, `licence_short` and `existing_class`. The agents' fields: `id` (ISO 3166-1, or 3166-2 for a
region), `country`, `region`, `agency`, `dtm` and `dsm` (`product`, `res_m`, `coverage`, `years`...), `access`,
`endpoint`, `format`, `crs`, `vertical`, `precision`, `alignment`, `versions`, `licence`, `licence_url`,
`attribution`, `auto_download`, `redistribution`, `commercial`, `public_site_ok`, `limits`, `ortho`, `tested`, `fit`,
`effort`, `highline`, `priority`, `risks`, `links`.

## Links
All 662 links of the rows were requested on 2026-10-31 (HEAD, else GET): 558 answered, 29 certificate error, 25 no connection or timeout, 25 refused (401/403), 22 not found (404/410), 1 other (503), 1 other (400), 1 other (406). Government servers often refuse scripts or foreign networks, and the INSPIRE geoportal's certificate had expired, so only a 404 says much: these pages have moved or the address is wrong, and should be found again before they are used:

- <https://ancpi.ro/laki3/en>
- <https://basisdata.nl/hwh-ortho/Caribisch_NL/AUX/potree/index.html>
- <https://data.gov.il/api/3/action/package_search?fq=organization:israel_mapping_center&rows=100>
- <https://datacatalog.worldbank.org/search/dataset/0039936/caribbean-islands-digital-elevation-model>
- <https://datamap.gov.wales/layers/geonode:wg_lidar_2020_2022_delivery_index/metadata_detail>
- <https://dst.gov.in/sites/default/files/Final%20Approved%20Guidelines%20on%20Geospatial%20Data.pdf>
- <https://eurogeographics.org/?p=10319>
- <https://eurogeographics.org/?p=8777>
- <https://eurogeographics.org/app/uploads/2025/06/04.-Lolonis-P-et-al.-2025-Quality-control-procedures-for-high-definition-aerial-LIDAR-data-in-Greece-SDQ-2025-5th-Int-Work-on-SDQ-EuroSDR-Eurogeographics-Athens-Nov-20-21.pdf>
- <https://events.development.asia/system/files/materials/2024/11/202411-kazakhstan-national-center-geodesy-and-spatial-information_0.pdf>
- <https://github.com/resuly/property-scores/blob/main/docs/national-lidar-bake-handoff.md>
- <https://gsi.ie/en-ie/events-and-news/news/Pages/Open-Topographic-Data-Viewer.aspx>
- <https://lantmateriet.se/en/geodata/geodata-products/product-list/elevation-model-download>
- <https://mundialis.github.io/r.dem.import/r.dtm.import.hh.html>
- <https://owsproxy.lgl-bw.de/owsproxy/wcs/WCS_INSP_BW_Hoehe_Coverage_DGM1?REQUEST=GetCapabilities&SERVICE=WCS&version=2.0.1>
- <https://projects.europa.ba/Project/Details/C_2000026>
- <https://snig.dgterritorio.gov.pt/rndg/srv/api/records/0bcce93f-12e4-44ec-90b8-4fb42fe49b15>
- <https://snig.dgterritorio.gov.pt/rndg/srv/api/records/cb85978f-afa9-4b9a-b5ed-ae7628372e11>
- <https://www.gov.si/novice/2025-03-27-na-voljo-podatki-ciklicnega-laserskega-skeniranja-za-leti-2023-in-2024/>
- <https://www.gov.si/novice/2026-06-03-lidarski-podatki-za-celotno-slovenijo-dostopni-v-pregledovalniku-3d-podatkov/>
- <https://www.nrsc.gov.in/sites/default/files/pdf/ebooks/UIM-2024/12_UIM_2024.pdf>
- <https://www.sla.gov.sg/geospatial/2020/press-release-by-singapore-land-authority-launch-of-onemap3d-beta-at-singapore-geospatial-week-2020>
