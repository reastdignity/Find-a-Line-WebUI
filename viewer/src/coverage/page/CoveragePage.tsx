// The coverage map's page (/coverage, web.py): where Find-a-Line has detailed elevation data. Three map
// views with a switch (flat by default, Leaflet, globe), the card of a clicked area (a bottom sheet on
// phones), the legend with its quality scale, the zoom presets, English or Polish, the app's theme, and
// every area as a table under the map. Preferences in localStorage (findaline.coverage.*, and the app's
// theme); nothing is sent to the server.
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { Segmented, useMedia, type Theme as UiTheme } from "../../ui/components";
import { Logo } from "../../ui/icons";
import { storedTheme, storeTheme } from "../../ui/choice";
import { COVERAGE, areaOf, loadShapes } from "../data";
import { LANGS, areaName, ct, pickLang, rememberLang, resText, type Lang } from "../i18n";
import { THEMES, applyPalette } from "../palette";
import { AreaList } from "./AreaList";
import { Card, Legend, SCALES, type Scale } from "./card";
import { mountFlat } from "./flat";
import { BOX_NAMES, makeGeo, parseKey, type Geo } from "./geo";
import { mountGlobe } from "./globe";
import { mountLeaflet } from "./leafletView";
import { VIEWS, type MapView, type ViewContext, type ViewName } from "./view";

const VIEW_KEY = "findaline.coverage.view";
const SCALE_KEY = "findaline.coverage.scale";
const MOUNT = {flat: mountFlat, leaflet: mountLeaflet, globe: mountGlobe};

function stored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    if (value && (allowed as readonly string[]).includes(value)) return value as T;
  } catch { /* storage blocked */ }
  return fallback;
}
function store(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* not remembered */ }
}

/** ?lang=en|pl chooses the language without remembering it; else the remembered one or the browser's. */
function firstLang(): Lang {
  const asked = new URLSearchParams(location.search).get("lang");
  return asked && (LANGS as readonly string[]).includes(asked) ? asked as Lang : pickLang();
}

export function CoveragePage({shapesUrl, site}: {shapesUrl: string; site: "public" | "local"}) {
  const [lang, setLang] = useState<Lang>(firstLang);
  const [theme, setTheme] = useState<UiTheme>(storedTheme);
  const systemDark = useMedia("(prefers-color-scheme: dark)");
  const reduced = useMedia("(prefers-reduced-motion: reduce)");
  const dark = theme === "dark" || (theme === "auto" && systemDark);
  const palette = THEMES[dark ? "dark" : "light"];
  const [view, setView] = useState<ViewName>(() => stored(VIEW_KEY, VIEWS, "flat"));
  const [scale, setScale] = useState<Scale>(() => stored(SCALE_KEY, SCALES, "words"));
  const [selected, setSelected] = useState<string | null>(null);
  const [geo, setGeo] = useState<Geo | null>(null);
  const [failed, setFailed] = useState(false);
  const [size, setSize] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const viewBox = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const card = useRef<HTMLElement>(null);
  const mounted = useRef<MapView | null>(null);
  const now = useRef({lang, palette, selected, reduced});
  now.current = {lang, palette, selected, reduced};

  useLayoutEffect(() => { if (root.current) applyPalette(root.current, palette); }, [palette]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = ct(lang, "page.doc_title");
  }, [lang]);
  useEffect(() => {
    loadShapes(shapesUrl).then(shapes => setGeo(makeGeo(shapes))).catch(() => setFailed(true));
  }, []);
  // the flat view and the globe are drawn for one size: a new size draws them again
  useEffect(() => {
    const box = viewBox.current;
    if (!box) return;
    let timer = 0;
    const observer = new ResizeObserver(() => {
      clearTimeout(timer);
      timer = window.setTimeout(() => setSize(`${box.clientWidth}x${box.clientHeight}`), 150);
    });
    observer.observe(box);
    return () => { observer.disconnect(); clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!geo || !viewBox.current) return;
    const ctx: ViewContext = {
      geo,
      theme: () => now.current.palette,
      selected: () => now.current.selected,
      select: key => setSelected(key),
      label: key => {
        const {id, rest} = parseKey(key), area = rest ? null : areaOf(id);
        return `${areaName(id, now.current.lang)} · ${resText(area ? area.res : COVERAGE.world.res, now.current.lang)}`;
      },
      credit: () => ct(now.current.lang, "map.credit"),
      reducedMotion: () => now.current.reduced,
    };
    const shown = MOUNT[view](viewBox.current, ctx);
    mounted.current = shown;
    return () => { shown.destroy(); mounted.current = null; };
  }, [geo, view, view === "leaflet" ? "" : size]);
  useEffect(() => { mounted.current?.update(); }, [lang, palette, selected]);
  useEffect(() => {
    if (!selected) return;
    const close = (e: KeyboardEvent) => { if (e.key === "Escape") setSelected(null); };
    addEventListener("keydown", close);
    return () => removeEventListener("keydown", close);
  }, [selected]);

  const changeLang = (value: Lang) => { setLang(value); rememberLang(value); };
  const changeTheme = (value: UiTheme) => { setTheme(value); storeTheme(value); };
  const changeView = (value: ViewName) => { setView(value); store(VIEW_KEY, value); };
  const changeScale = (value: Scale) => { setScale(value); store(SCALE_KEY, value); };
  /** From the list or a card's regions: the card opens and gets the focus (the keyboard's way). */
  const pick = (key: string) => {
    setSelected(key);
    requestAnimationFrame(() => {
      stage.current?.scrollIntoView({block: "nearest", behavior: reduced ? "auto" : "smooth"});
      card.current?.focus({preventScroll: true});
    });
  };

  const word = (key: string) => ct(lang, key);
  return <div ref={root} class="ui cov" data-theme={theme === "auto" ? undefined : theme}>
    <header class="cov-top"><div class="cov-inner cov-top-row">
      <a class="cov-brand" href="/" aria-label={word("page.open")}><Logo /></a>
      <span class="cov-name">{word("page.name")}</span>
      <span class="cov-spacer" />
      <div class="cov-toggles">
        <Segmented label={word("page.lang")} value={lang} onChange={changeLang}
                   options={LANGS.map(l => ({value: l, label: l.toUpperCase()}))} />
        <Segmented label={word("page.theme")} value={theme} onChange={changeTheme}
                   options={(["auto", "light", "dark"] as UiTheme[]).map(t2 => ({value: t2, label: word(`page.theme.${t2}`)}))} />
      </div>
    </div></header>
    <main class="cov-inner cov-main">
      <section class="cov-intro">
        <h1 class="cov-h1">{word("page.title")}</h1>
        <p class="cov-lead">{word("page.lead")}</p>
        <p class="cov-count">{ct(lang, "count.countries", {count: COVERAGE.countries})}</p>
      </section>
      <div class="cov-bar">
        <Segmented label={word("page.view")} value={view} onChange={changeView}
                   options={VIEWS.map(v => ({value: v, label: word(`page.view.${v}`)}))} />
        <span class="cov-small cov-muted">{word(`page.hint.${view}`)}</span>
      </div>
      <div class="cov-stage" ref={stage}>
        <div class={`cov-mapbox cov-in-${view}`}>
          <div class="cov-view" ref={viewBox} />
          <div class="cov-zoombar" role="group" aria-label={word("page.zoom")}>
            {BOX_NAMES.map(name => <button type="button" key={name} onClick={() => mounted.current?.zoomTo(name)}>
              {word(`zoom.${name}`)}</button>)}
          </div>
          {!geo && <p class="cov-status" role="status">{word(failed ? "page.failed" : "page.loading")}</p>}
          {selected && <aside ref={card} class="cov-card" tabIndex={-1} aria-label={selected === "world"
              ? word("world.name") : areaName(parseKey(selected).id, lang)}>
            <Card areaKey={selected} lang={lang} scale={scale} onClose={() => setSelected(null)} onPick={pick} />
          </aside>}
        </div>
        <div class="cov-legend"><Legend lang={lang} scale={scale} onScale={changeScale} /></div>
      </div>
      <p class="cov-small cov-muted cov-world">
        <button type="button" class="cov-link" onClick={() => pick("world")}>{word("world.name")}</button>
        {`: ${resText(COVERAGE.world.res, lang)}. ${word("note.world")}`}</p>
      <AreaList lang={lang} scale={scale} selected={selected} onPick={pick} />
      <p class="cov-cta"><a class="u-btn u-pri u-lg" href="/">{word("page.cta")}</a></p>
    </main>
    <footer class="cov-inner cov-footer">
      <a href="/">Find-a-Line</a>
      {site === "public" && <><a href="/about">{word("page.about")}</a><a href="/privacy">{word("page.privacy")}</a></>}
      <span>{word("map.credit")}</span>
    </footer>
  </div>;
}
