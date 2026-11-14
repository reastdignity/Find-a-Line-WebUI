# Webbings and areas: research for the Find-a-Line feasibility report

Read-only web research, 2026-11-02. Quotes are verbatim from the pages named (some long sentences
only in part, marked "..."). "My arithmetic" marks every number computed here rather than read from a
source. Pages that could not be opened are named, together with how their text was seen instead
(search-engine snippets).

Find-a-Line's sag model, for reference (`sag.py`, `params.py`): an elastic catenary with
`EA = 10 kN / (stretch / 100)` (linear, from the stretch at 10 kN), `w = webbing_weight` in g/m per
unstretched metre, pretension 2.5 kN, athlete 80 kg. Defaults: `webbing_weight` 70 g/m, `stretch` 5 %.

---

## Part A. Webbings

### A1. Silk 99 (Balance Community)

Page: https://balancecommunity.com/products/silk-99 (title "Silk 99", subtitle "Extreme Tech Highline Webbing")

| Item | Value (quoted) |
| --- | --- |
| Material | "Flat, 100% UHMWPE (Dyneema SK99 + black HMPE)"; "Single-Layer Weave" |
| Weight | "20 g/m (1.34 lbs / 100 ft)" |
| Width / thickness | "18.9 mm (0.74 in)" / "1.6 mm (0.06 in)" |
| Stretch, quick specs | "ISA Stretch" "1.3% @ 5kN · 2.1% @ 10kN" |
| Stretch, test data (ISA) | ISA Stretch @ 5 kN "1.25%", @ 10 kN "2.12%"; "Standardized ISA stretch method, 200 mm gauge." |
| Stretch curve (BC method) | 1 kN 0.23 %, 2 kN 0.69 %, 3 kN 1.04 %, 4 kN 1.29 %, 5 kN 1.57 %, 6 kN 1.73 %, 7 kN 1.86 %, 8 kN 2.07 %, 9 kN 2.17 %, 10 kN 2.24 %, 11 kN 2.39 %, 12 kN 2.53 %; "Stretch-curve method — read off each webbing's load–elongation curve, not the standardized ISA gauge test." |
| MBS | "35 kN (7,868 lbf)"; batch W25YZ (Jan 2026) measured "35.39 kN (7,956 lbf)" |
| Sewn loop MBS | "35 kN (7,868 lbf)"; measured "35.89 kN (8,068 lbf)" |
| WLL | "12 kN (2,698 lbf)" |
| Optimum tension | "1.0 - 4.5 kN (225 - 1,000 lbf)" |
| Preferred lengths | "200+ m (660+ feet)"; "it is recommended to only use it for highlines longer than 200m"; for shorter lines "a nylon segment of 15m or longer at either end of the line" |
| Lengths, price | 50 m, 60 m, 100 m or custom; "$210.00 USD"; loops naked or sleeved |

Main and backup: **the same product in both roles**, no separate backup product.
- "we want to use Silk 99 for the mainline and backup line for most of the gap" (part of a sentence)
- "Now, for the bulk of the line, we have a very lightweight main/backup combo that is excellent for walking."
- Backup lengths: 50 m main, 52.5 m backup; 60 m, 63 m; 100 m, 105 m; 120 m, 126 m. "For any other length, make the backup 5% longer than the main." "In our testing on a 100m segment, we found 5% extra backup length to be a good sweet spot for most rigs."

Not for a whole bigline: "Silk 99 should not be used for the entire length of a big line." "Silk 99 is not meant to be used as a longline webbing without another piece of webbing to be used as the tensioning segment." It recommends "at least 2 segments of Spider Silk MK5 to use on each end", example: "50m Spider Silk MK5/Silk 99 Backup -> 900m Silk 99/Silk 99 Backup (100m segments) -> 100m Spider Silk MK5/Silk 99 Backup". Full HMPE "has trouble being paired with hardware" (weblocks, line-locker rings, LineGrip, Wafer).

Connections: "Skipping the bulky protective sleeve brings the weight of your connection down by a staggering 50+ grams (assuming naked loops on main and backup), ..." (a difference, not the weight of a connection).

No ISA certification is named; only the ISA stretch method.

### A2. Axiom (Balance Community): two products

The name now covers two webbings. Balance Community's stretch table (https://balancecommunity.com/collections/stretch) lists "Axiom (discontinued)" and "Axiom MK2". The old product page is still online (sold out).

**Axiom MK2 (current, "In stock")**: https://www.balancecommunity.com/products/axiom-mk2

| Item | Value |
| --- | --- |
| Material | 100% UHMWPE (HMPE), the yarn "generic HMPE"; flat, single-layer, single zone |
| Weight | 32 g/m |
| Width / thickness | 19.4 mm / 2.5 mm |
| Stretch (ISA) | quick specs 1.1 % @ 5 kN, 1.8 % @ 10 kN; test data 1.75 % @ 10 kN; the curve has values at 5 and 10 kN only (stretch table: 1.10 % @ 5 kN, 1.75 % @ 10 kN) |
| MBS | 42 kN; batch W26DZ-2 measured 42.96 kN (the earlier batch W26DZ, 39.93 kN, superseded) |
| Sewn loop MBS | 42 kN; measured 42.82 kN |
| WLL | 13 kN |
| Optimum tension | 1.0–4.5 kN (225–1,000 lbf) |
| Preferred lengths | 200+ m; shorter lines: at least 15 m of nylon at each end; it creeps over its lifetime |
| Lengths, price | 50 m, 60 m, 100 m, custom; $145.00 USD (50 m) |

**Axiom (original, discontinued)**: https://www.balancecommunity.com/products/axiom (title "Axiom (50m+)", sold out)

| Item | Value (quoted) |
| --- | --- |
| Material | "100% UHMWPE (HMPE)"; "Axiom is made with generic HMPE yarn"; flat, single-layer, single-zone |
| Weight | "33 g/m (2.22 lbs / 100 ft)" |
| Width / thickness | "20.0 mm (0.79 in)" / "2.9 mm (0.11 in)" |
| Stretch | quick spec "3.4% @ 5kN · 4.4% @ 10kN"; curve (BC method, not ISA): 1 kN 1.58 %, 2 kN 2.26 %, 3 kN 2.73 %, 4 kN 3.10 %, 5 kN 3.40 %, 6 kN 3.63 %, 7 kN 3.85 %, 8 kN 4.02 %, 9 kN 4.20 %, 10 kN 4.35 %, 11 kN 4.49 %, 12 kN 4.62 % |
| MBS / sewn loop / WLL | "40 kN (8,992 lbf)" / "40 kN (8,992 lbf)" / "13 kN (2,990 lbf)" |
| Optimum tension, lengths | 1.0–4.5 kN; preferred "200+ m (660+ feet)"; $145.00 USD |

Main and backup (both versions): **the same product in both roles**, no separate backup product. Old page: "Axiom is meant for the body of a bigline project, or as the backup for the entire bigline." MK2's example: "100m Spider Silk MK5/Axiom backup, then 900m Axiom in 100m segments, then 100m Spider Silk MK5/Axiom backup" (as summarised by the fetch). Backup lengths (both): 50 m, 53.5 m; 60 m, 64.2 m; 100 m, 107 m; 120 m, 128.4 m; "For any other length, make the backup 7% longer than the main." Not compatible with Alpine WebLock 6.x or Wafer grips; MightyLock only double-wrapped with a Van Beest 1/2" shackle; ends of a bigline in Spider Silk MK5 (MK2: at least two 100 m segments at each end).

Stretch methods (they differ, so the numbers are not comparable one to one):
- ISA: "Standardized ISA stretch method, 200 mm gauge." (product pages). The ISA standard's own text was not found online.
- Balance Community's curve method (blog "Webbing Stretch Testing Methods and Data Update", 11 July 2025, https://www.balancecommunity.com/blogs/slack-science/webbing-stretch-testing-methods-and-data-update): "Length of each webbing sample: 1.5 meters (5 feet)", "our standard loop pattern, which is 95 mm (3.75 inches) long", "Our minimum force threshold is set at 0.20 kN" (the zero point), "Number of samples: 5", data "all the way up to 12 kN".
- For Silk 99 both exist: 2.12 % (ISA) vs 2.24 % (curve) at 10 kN.

### A3. Tiger (Slackhouse, sold by Slackhouse Shop)

Pages: https://slackhouseshop.pl/en/produkt/tiger/ and the Polish https://slackhouseshop.pl/produkt/tiger/ (shop category: https://slackhouseshop.pl/en/kategoria-produktu/webbings/, "Slackhouse Tiger", "300,00 € – 3.375,00 €", all webbings shown "Sold out" on 2026-11-02).

| Item | Value (quoted) |
| --- | --- |
| Producer, origin | "Slackhouse"; made in "China" ("Kraj produkcji: Chiny") |
| Material | "Made entirely of UHMWPE fibers"; table "UHMWPE"; weave "Flat" ("Płaski") |
| Weight | table "29,8 g/m"; text "it wights just around 30 g/m" (PL "ważąca jedynie niecałe 30 g/m"); a second table row "Weight" reads "N/A" ("Waga: Brak danych") |
| Width / thickness | "21,5 mm" ("The width reduced to 21,5 mm decreases wind catching") / "2,5 mm" |
| Stretch | table "1,9 % (5 kN), 2,8 % (10 kN)"; text "Its low stretch of 2.9% (at 10 kN) ensures effective tensioning of the longest projects" and "the 2,4% stretch at 5 kN"; no curve, no test method stated |
| MBS | "⇕ 30 kN"; sewn loop "30 kN" |
| WLL | "8 kN" (PL "Dopuszczalne obciążenie") |
| Backup length | "+ 7%"; "The backup length is 53.5 m for 50 m segments and 107 m for 100 m segments" |
| Lengths | 100 to 1500 m; "Tiger webbing is available in 50 m or 100 m splits"; for 100 m segments with backup both webbings are stitched together in the middle (M2B) by default |
| Use | "we recommend it for projects of at least 150 m in length"; "We do not recommend using Tiger as the mainline for permanent rigs." |
| Hardware | "UHMWPE webbing cannot be tensioned using typical webbing grips (e.g. Petram Cito) because it is too slippery."; "not compatible with a standard weblocks and can only be attached using the original sewn loops"; soft-thimble loops (ST) by default, flat loops (FL) on request |
| Lifespan | "The maximum lifespan of the Tiger is 5 years regardless of how it was used."; melting point "140-150 °C" |

Main and backup: **one product in both roles** ("Apart from large projects, Tiger is a great choice as the backup for your freestyle set!"; Tiger backups of +7 % on Tiger mains). No ISA certification mentioned. The page contradicts itself on the stretch (2.8 vs 2.9 % at 10 kN, 1.9 vs 2.4 % at 5 kN) and gives the weight twice (29.8 g/m and "N/A"). No other source (datasheet, ISA list) was found.

### A4. Tape, rings and connections

- The backup's weight hangs on the main: "The tapes hold the backup line up to the mainline, thus they are supporting the weight of the backup line." (Balance Community, "All About Highline Tape Spacing", 3 Feb 2018, https://www.balancecommunity.com/blogs/slack-science/all-about-highline-tape-spacing). Spacing there: 5–20 m lines 1–2 m, 20–50 m 1.5–3 m, 50–100 m 2–5 m, 100–200 m 3–6 m, 200 m+ 3–7 m, ends and trick zones about 1–1.5 m.
- Tape per wrap: 19–25 cm (standard method) to 27–33 cm (slider methods) ("The Different Taping Methods for Highlines", 28 Jan 2018, https://www.balancecommunity.com/blogs/slack-science/the-different-taping-methods-for-highlines). **No source states the weight of tape**, so no per-metre figure is given here.
- Leash rings (a point load that moves with the athlete): Balance Community BigLoop "90 g (3 oz)", 80 mm inside, 7075 aluminium, MBS 24 kN, "only to be used as a leash ring" (https://www.balancecommunity.com/products/bigloop); Spider Slacklines 80 mm HighRing "TOTAL WEIGHT 99 gr", forged aluminium, 35 kN (https://spider-slacklines.com/shop/en/leashes/468-80mm-highring-flat-aluminum-highline-ring-7616999009.html).
- Segment connections (point loads every 50–100 m): only the Silk 99 page's "50+ grams" saved without sleeves; no absolute weight found.
- Find-a-Line has no input for point loads besides `athlete_mass`; a leash ring (about 0.1 kg) could be added there.

### A5. Proposed sag-model inputs (same webbing as main and backup)

| Setup | Main g/m | Backup g/m | Backup longer by | `webbing_weight` = main + backup | Length-corrected (my arithmetic) | `stretch` = main % at 10 kN | Method |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Silk 99 / Silk 99 | 20 | 20 | 5 % | **40** | 41.0 | **2.1** (ISA 2.12; curve 2.24) | ISA |
| Axiom MK2 / Axiom MK2 | 32 | 32 | 7 % | **64** | 66.2 | **1.8** (1.75) | ISA |
| Axiom (original) / Axiom | 33 | 33 | 7 % | **66** | 68.3 | **4.4** (curve 4.35) | BC curve |
| Tiger / Tiger | 29.8 | 29.8 | 7 % | **59.6** (≈60) | 61.7 | **2.8** (text: 2.9) | not stated |

Flags (every value that needed an assumption):
1. **Hardware left out.** The weights are webbing only: no tape, sewn loops, sleeves, M2B stitching or leash ring, because no source gives a per-metre figure for them.
2. **Length correction** (my arithmetic): the backup is cut 5–7 % longer, so it weighs backup g/m × 1.05 or 1.07 per metre of main; the model's `w` is per unstretched metre. The plain sum is what was asked; the corrected value is 1–2.3 g/m higher.
3. **Methods differ**: ISA 200 mm gauge (Silk 99, Axiom MK2), BC curve from 0.20 kN (original Axiom), unstated (Tiger). Silk 99 shows the gap: 2.12 % vs 2.24 %.
4. **Linear vs real curves** (my arithmetic from the published points). `sag.py` takes the secant stiffness at 10 kN; under an athlete the tension moves within about 2–6 kN (BC's optimum tension 1.0–4.5 kN, the model's pretension 2.5 kN). Silk 99: secant EA 446–472 kN, tangent between 2 and 5 kN 341 kN (3 kN / 0.88 %), so the model is stiffer there and underestimates the extra sag (not conservative). Original Axiom: secant 227–230 kN, tangent 2–5 kN 263 kN, so the model is a little softer (conservative). Axiom MK2: secant 556–571 kN, tangent 5–10 kN 769 kN; below 5 kN unknown. Tiger: secant 345–357 kN, tangent 5–10 kN 556 kN (table) or 1000 kN (text); below 5 kN unknown.
5. **Real biglines are composite.** Balance Community puts Spider Silk MK5 at the ends (MK5 curve 3.79 % at 10 kN, stretch table; weight not listed there) and asks for at least 15 m of nylon at each end of lines under 200 m. Slackhouse recommends Tiger for 150 m or more. One weight and stretch for the whole line fits only the body of a long line.
6. **Tiger's own figures disagree** (point A3): 2.8 or 2.9 % at 10 kN.
7. **Creep**: both Axioms grow over their lifetime (pretension and backup length change, the inputs do not).
8. Against the defaults (70 g/m, 5 %): all four setups are lighter (40–66 g/m) and stiffer (1.8–4.4 %).

---

## Part B. Areas

### B1. Poland

Total area (GUS, the official figure of the territorial division):
- 1 Jan 2025: **31,393,293 ha = 313,932.9 km²**, "68 hektarów mniej" than 1 Jan 2024 (31,393,361 ha). Polsat News, 22 Jul 2025, citing GUS: https://www.polsatnews.pl/wiadomosc/2025-07-22/terytorium-polski-zmniejszylo-sie-nowy-raport-gus/ (GUS's publication: https://stat.gov.pl/obszary-tematyczne/ludnosc/ludnosc/powierzchnia-i-ludnosc-w-przekroju-terytorialnym-w-2025-r-,7,22.html; the figure itself is in its PDF/XLSX, not opened).
- 2026 edition (published 21 Jul 2026, https://stat.gov.pl/obszary-tematyczne/ludnosc/ludnosc/powierzchnia-i-ludnosc-w-przekroju-terytorialnym-w-2026-r-,7,23.html): the area "wzrosła dokładnie o 433 hektary" in 2025 (money.pl, 21 Jul 2026, https://www.money.pl/gospodarka/polska-urosla-o-433-hektary-wiadomo-jaki-region-skorzystal-7309809028634720a.html; eska.pl, 22 Jul 2026). Absolute figure not quoted by them; ≈ 31,393,726 ha ≈ 313,937 km² (my arithmetic).
- Why about 313.9 thousand km² and not the older 312.7 thousand: in the 2023 edition "powierzchnia Polski zwiększyła się o 121 106 ha (z 31 272 030 ha do 31 393 136 ha)" when part of the internal sea waters of the Gulf of Gdańsk joined gminas (Gdańsk's "sea" part 41,713 ha; Gdynia +25,631 ha, Sopot +1,040 ha, powiat pucki +28,732 ha, nowodworski +24,003 ha). Bankier.pl, 27 Jul 2023: https://www.bankier.pl/wiadomosc/Warszawa-nie-jest-juz-najwiekszym-miastem-w-Polsce-8585487.html. **So the GUS area includes inland waters and part of the internal sea waters: it is not land.**

Land area:
- World Bank / FAO "Land area (sq. km)" 2024: **306,070 km²** (2023: 306,270; 2022: 306,090); "Surface area" 2024: 313,940 km² (2022: 312,720). Definition: "Land area is a country's total area, excluding area under inland water bodies, national claims to continental shelf" (and EEZs; inland water "in most cases" major rivers and lakes); source "FAOSTAT". https://api.worldbank.org/v2/country/POL;CHE;LIE/indicator/AG.LND.TOTL.K2?format=json&mrv=3 (data last updated 2026-10-08), definitions https://api.worldbank.org/v2/indicator/AG.LND.TOTL.K2?format=json.
- GDOŚ "Polska w liczbach" (undated, no source given): "Obszar lądowy (łącznie z wodami śródlądowymi) wynosi **311 888 km²**", "morskich wód wewnętrznych 2005 km²", "morza terytorialnego 8682 km²", "powierzchni całkowitej 322 575 km²". https://www.gov.pl/web/gdos/polska-w-liczbach
- (The CIA World Factbook, often quoted for land/water, was retired on 4 Feb 2026; its country pages now show that notice.)

Terrain classes (the Polish school classification, by absolute height):
- Thresholds: lowlands (niziny) up to 300 m a.s.l., uplands (wyżyny) 300–500 m, mountains (góry) above 500 m. "stanowiącą 91,4% powierzchni, zajmują obszary nizinne o wysokości bezwzględnej do 300 m n.p.m."; "pas wyżyn z wysokościami bezwzględnymi 300‑500 m n.p.m."; mountains "niskich (500–600 m n.p.m.), średnich (600‑1 000 m n.p.m.) i wysokich gór (powyżej 1 000 m n.p.m.)"; "średnia wysokość wynosi 173 m n.p.m." Lesson "Główne cechy środowiska przyrodniczego Polski", zpe.gov.pl (the Ministry of Education's platform): https://zpe.gov.pl/a/glowne-cechy-srodowiska-przyrodniczego-polski/DtmFB7sta. Another lesson ("Krajobrazy Polski", https://zpe.gov.pl/a/krajobrazy-polski/DSROSFgbT) adds for mountains relative heights above 300 m ("o dużych różnicach wysokości względnych (przekraczających 300 m)").
- Table "Pionowe zróżnicowanie powierzchni Polski" (zpe.gov.pl, https://zpe.gov.pl/watek/LPV6e89ez3/63/b/PkoZvTaGW, no source named): below 0 m 0.5 %; 0–100 m 24.1 %; 100–200 m 50.3 %; 200–300 m 16.5 %; 300–500 m 5.4 %; 500–1000 m 3.0 %; above 1000 m 0.2 %. Hence **lowlands 91.4 % (with depressions), uplands 5.4 %, mountains 3.2 %**.
- GDOŚ (link above): "Niziny zajmują 91,3% powierzchni, wyżyny 5,6%, góry 3,3%, z czego 0,2% przypada na góry wysokie." These add up to 100.2 % (an inconsistency; the triple usually quoted is 91.3 / 5.6 / 3.1).
- No GUS table of the area by height was found online.
- In km² (my arithmetic, × 311,888 km²): mountains ≈ 10,000 km², uplands ≈ 16,800 km², lowlands ≈ 285,000 km².

### B2. Switzerland and Liechtenstein

Switzerland:
- FDFA "Geography" (aboutswitzerland, 17 Jul 2023, https://www.aboutswitzerland.eda.admin.ch/en/geography): "Half of its **41,285km2** surface area lies at more than 1,080m above sea level and is sparsely populated." Water: "Switzerland has around 1,500 lakes which, together with other bodies of water like streams and lakes, account for 4% ..." (the rest of the sentence cut off). Glaciers "approximately 1,000 km2".
- BFS land use statistics 2013/18 (Statistical Atlas of Switzerland, seen only as a search snippet of its PDF): 41,291 km²; "Wasser- und Feuchtflächen" 2,913 km² (water and wetlands together).
- World Bank / FAO: surface 41,290.7 km², **land 39,509.63 km²** (2022–2024); so inland water ≈ 1,781 km² = 4.3 % (my arithmetic, matching the FDFA's 4 %).

Liechtenstein:
- World Bank / FAO: surface **160 km²**, land 160 km². Amt für Statistik, "Liechtenstein in Zahlen" (PDFs, seen as search snippets): "Landesfläche 160 km2 100%"; Statistikportal: Oberland 125.5 km² + Unterland 35.0 km² = 160.5 km².

Together (my arithmetic): total 41,445 km² (41,285 + 160) or 41,451 km² (41,290.7 + 160.5); land 39,670 km² (World Bank 39,509.6 + 160).

Terrain classes:
- FDFA (same page): "**The Alps cover roughly 58% of the country, the Central Plateau around 31% and the Jura 11%.**" The same page also says "the Alps cover 60% of Switzerland's surface area" and "The Alps cover two thirds of the country" (it disagrees with itself; 58 / 31 / 11 is the triple that adds up to 100).
- In km² (my arithmetic, × 41,285): Alps ≈ 23,945, Plateau ≈ 12,798, Jura ≈ 4,541.
- With Liechtenstein, assuming all of it counts as Alps (the Alpine Rhine valley and the Rätikon; no source with a number found): Alps ≈ 24,105 km² of 41,445 = 58.2 %, Plateau 30.9 %, Jura 11.0 % (my arithmetic).
- Other official divisions exist but their areas were not found as pages: BAFU's six biogeographic regions (Jura, Mittelland, Alpennordflanke, westliche and östliche Zentralalpen, Alpensüdflanke) and the forest inventory's five production regions (Jura, Mittelland, Voralpen, Alpen, Alpensüdseite).

### B3. Utah

Area (US Census Bureau, "State Area Measurements and Internal Point Coordinates", 2010, boundaries "as of January 1, 2010": https://www.census.gov/geographies/reference-files/2010/geo/state-area.html):
- Total **84,897 sq mi = 219,882 km²**; land **82,170 sq mi = 212,818 km²**; water 2,727 sq mi = 7,064 km², all inland (no coastal, Great Lakes or territorial water).
- "Water area calculations in this table include only perennial water." "All other water (intermittent, glacier, and marsh/swamp) is included in this table as part of land area calculations."

Physiographic provinces:
- Utah Geological Survey, "Glad You Asked: How was Utah's topography formed?" (Survey Notes, 2000, https://geology.utah.gov/map-pub/survey-notes/glad-you-asked/how-was-utahs-topography-formed/). The UGS servers refused connections from here, so its text was seen only through search snippets: "Utah contains parts of three major physiographic provinces: the Colorado Plateau, Basin and Range, and Middle Rocky Mountains"; the Basin and Range in western Utah, the Colorado Plateau in the southeast, the Middle Rocky Mountains in the northeast; "The three provinces meet near the center of the state"; "some geologists would make this area a distinct, fourth physiographic province called the Basin and Range – Colorado Plateau Transition". A UGS geothermal page describes "a 100-km- (62 mi) wide zone of transitional tectonics, structure, and physiography".
- **No UGS or USGS percentage of the state's area per province was found.** What exists:
  - USGS Fact Sheet FS-044-96 (1996, "U.S. Geological Survey programs in Utah", https://pubs.usgs.gov/fs/FS-044-96/fs-044-96.pdf): "The Great Basin Province, which occupies the western one-third of Utah, contains the majority of commercial mineral deposits of the State ..." (text from the search index; the PDF has no text layer that could be read here).
  - R. D. Feltis (USGS) 1966, "Water from bedrock in the Colorado Plateau of Utah", Utah State Engineer Technical Publication 15 (https://pubs.usgs.gov/publication/70178827): a search summary says the Colorado Plateau "comprises about half the area of the State". Not verified (its PDF host refused connections, the USGS abstract does not say it).
  - Rangelands (1992, Utah State University authors): "almost half of the state falls within the Colorado Plateau" (search snippet only).
  - Utah Division of State History, "Physical Geography of Utah" (https://historytogo.utah.gov/physical-geography-utah, 403 here, snippets): "The largest of the provinces in Utah is the Colorado Plateau."; the Rocky Mountains are "the physiographic province that covers the smallest area in Utah".
- Rough split from these fractions (my arithmetic, flagged): Colorado Plateau ≈ 1/2 (≈ 106,000 km² of land), Basin and Range ≈ 1/3 (≈ 71,000 km²), Middle Rocky Mountains plus the transition ≈ 1/6 (≈ 35,000 km²). An exact split would need the USGS physiographic divisions (Fenneman and Johnson 1946) as polygons, a download not made here.

---

## Sources

- Balance Community, Silk 99: https://balancecommunity.com/products/silk-99
- Balance Community, Axiom MK2: https://www.balancecommunity.com/products/axiom-mk2
- Balance Community, Axiom (original): https://www.balancecommunity.com/products/axiom
- Balance Community, stretch table: https://balancecommunity.com/collections/stretch
- Balance Community, stretch test method (11 Jul 2025): https://www.balancecommunity.com/blogs/slack-science/webbing-stretch-testing-methods-and-data-update
- Balance Community, tape spacing (3 Feb 2018): https://www.balancecommunity.com/blogs/slack-science/all-about-highline-tape-spacing
- Balance Community, taping methods (28 Jan 2018): https://www.balancecommunity.com/blogs/slack-science/the-different-taping-methods-for-highlines
- Balance Community, BigLoop: https://www.balancecommunity.com/products/bigloop
- Spider Slacklines, 80 mm HighRing: https://spider-slacklines.com/shop/en/leashes/468-80mm-highring-flat-aluminum-highline-ring-7616999009.html
- Slackhouse Shop, Tiger: https://slackhouseshop.pl/en/produkt/tiger/ (PL https://slackhouseshop.pl/produkt/tiger/), webbings: https://slackhouseshop.pl/en/kategoria-produktu/webbings/
- GUS publications 2025 / 2026: https://stat.gov.pl/obszary-tematyczne/ludnosc/ludnosc/powierzchnia-i-ludnosc-w-przekroju-terytorialnym-w-2025-r-,7,22.html, https://stat.gov.pl/obszary-tematyczne/ludnosc/ludnosc/powierzchnia-i-ludnosc-w-przekroju-terytorialnym-w-2026-r-,7,23.html
- Polsat News (22 Jul 2025): https://www.polsatnews.pl/wiadomosc/2025-07-22/terytorium-polski-zmniejszylo-sie-nowy-raport-gus/
- Bankier.pl (27 Jul 2023): https://www.bankier.pl/wiadomosc/Warszawa-nie-jest-juz-najwiekszym-miastem-w-Polsce-8585487.html
- money.pl (21 Jul 2026): https://www.money.pl/gospodarka/polska-urosla-o-433-hektary-wiadomo-jaki-region-skorzystal-7309809028634720a.html
- GDOŚ, Polska w liczbach: https://www.gov.pl/web/gdos/polska-w-liczbach
- zpe.gov.pl: https://zpe.gov.pl/a/glowne-cechy-srodowiska-przyrodniczego-polski/DtmFB7sta, https://zpe.gov.pl/watek/LPV6e89ez3/63/b/PkoZvTaGW, https://zpe.gov.pl/a/krajobrazy-polski/DSROSFgbT
- World Bank API (FAO data): https://api.worldbank.org/v2/country/POL;CHE;LIE/indicator/AG.LND.TOTL.K2?format=json&mrv=3, https://api.worldbank.org/v2/country/POL;CHE;LIE/indicator/AG.SRF.TOTL.K2?format=json&mrv=3
- FDFA, Geography: https://www.aboutswitzerland.eda.admin.ch/en/geography
- US Census Bureau, state areas 2010: https://www.census.gov/geographies/reference-files/2010/geo/state-area.html
- Utah Geological Survey: https://geology.utah.gov/map-pub/survey-notes/glad-you-asked/how-was-utahs-topography-formed/ (snippets only)
- USGS FS-044-96: https://pubs.usgs.gov/fs/FS-044-96/fs-044-96.pdf; Feltis 1966: https://pubs.usgs.gov/publication/70178827
- Utah Division of State History: https://historytogo.utah.gov/physical-geography-utah (snippets only)
