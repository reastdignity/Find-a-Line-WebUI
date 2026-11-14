// C's account: the user (the public site: name, privacy and about, sign out; Admin for administrators),
// the OSM extracts and the highline layer (LayerPage) locally and for administrators, the area searched
// (Searched.tsx) and the theme. A menu under the header's account button on desktops, a page (#account) on
// phones. The Admin page (AdminC) is a
// page of panels; the OSM page (OsmC) a panel next to the map it needs (the regions around its centre).

import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { ComponentChildren, RefObject } from "preact";
import { Button, DESKTOP, Segmented, useMedia, type Theme } from "../../ui/components";
import { SidePanel, useWidthOf } from "../../ui/SidePanel";
import { DEFAULT_LAYER_LAYOUT, LAYER_LIMITS, fitPanels, loadLayerLayout, maxPanelWidth, saveLayerLayout, type Column,
         type LayerLayout, type PanelSide } from "../../result/view/layout";
import { Icon } from "../../ui/icons";
import { storeTheme } from "../../ui/choice";
import { Popover } from "../../result/view";
import { api, user } from "../api";
import { canReport, openReport } from "../../report";
import { PlaceMap } from "../PlaceMap";
import type { Job, Usage } from "../api";
import { SearchedLine } from "./Searched";
import { AdminC } from "./AdminC";
import { OsmC } from "./OsmC";
import { go } from "./route";

const THEMES = [{value: "auto" as const, label: "Auto"}, {value: "light" as const, label: "Light"},
                {value: "dark" as const, label: "Dark"}];

export function AccountBody({theme, setTheme, onPick, usage}:
                            {theme: Theme; setTheme(t: Theme): void; onPick?(): void; usage?: Usage | null}) {
  const pick = () => onPick?.();
  return <div class="c-account">
    <div class="c-account-who">
      <span class="c-avatar"><Icon name="user" /></span>
      <span><b>{user.local ? "This computer" : user.name}</b>
        <span class="u-small">{user.local ? "the local app: no account" : user.admin ? "administrator" : "signed in"}</span></span>
    </div>
    <SearchedLine usage={usage} />
    <nav class="c-account-links">
      {!user.local && user.admin && <a class="c-menu-item" href="#admin" onClick={pick}><Icon name="user" />Admin</a>}
      {(user.local || user.admin) && <a class="c-menu-item" href="#osm" onClick={pick}><Icon name="layers" />OpenStreetMap extracts</a>}
      {(user.local || user.admin) && <a class="c-menu-item" href="#layer" onClick={pick}><Icon name="poly" />Highline layer</a>}
      {canReport() && <button type="button" class="c-menu-item" onClick={() => { pick(); openReport(); }}>
        <Icon name="warn" />Report a problem</button>}
      {!user.local && <a class="c-menu-item" href="/privacy" target="_blank"><Icon name="info" />Privacy</a>}
      {!user.local && <a class="c-menu-item" href="/about" target="_blank"><Icon name="info" />About and data licences</a>}
    </nav>
    <div class="c-account-theme"><span class="u-small">Theme</span>
      <Segmented label="Theme" options={THEMES} value={theme} onChange={(t) => { storeTheme(t); setTheme(t); }} /></div>
    {!user.local && <Button kind="danger" class="c-signout"
                            onClick={() => api.logout().finally(() => { location.href = "/"; })}>Sign out</Button>}
  </div>;
}

/** The header's account button with its menu. */
export function AccountMenu({theme, setTheme, usage}:
                            {theme: Theme; setTheme(t: Theme): void; usage?: Usage | null}) {
  const [open, setOpen] = useState(false);
  return <Popover label="Account" align="right" open={open} onOpen={setOpen}
                  button={(on, toggle) => <button type="button" class={`c-account-btn${on ? " u-on" : ""}`}
                                                  aria-expanded={on} onClick={toggle}>
                    <span class="c-avatar"><Icon name="user" /></span>
                    <span class="c-account-name">{user.local ? "Local" : user.name}</span>
                    <Icon name="down" /></button>}>
    <AccountBody theme={theme} setTheme={setTheme} onPick={() => setOpen(false)} usage={usage} />
  </Popover>;
}

/** What MapPage gives the children of a page with `aside`: `panels` changes whenever a side panel's width or open
 *  state changes the map's width (LayerPage restarts its automatic level then), `setRails` the collapsed panels'
 *  labels (left, right). */
export interface MapPageExtras { panels: string; setRails(left: string, right: string): void }

/** The highline layer's side panels: their kept layout (layout.ts loadLayerLayout, LAYER_LIMITS) fitted to the
 *  window, the edges, the rails and the focus moved on a collapse (to the rail) and an expand (to the edge), as the
 *  result's (ResultColumns.tsx); on phones open and without edges (one scrolling column, c.css). */
function useLayerPanels(wide: boolean, cols: RefObject<HTMLDivElement | null>) {
  const [layout, setLayout] = useState<LayerLayout>(loadLayerLayout);
  const latest = useRef(layout);
  latest.current = layout;
  const [prefer, setPrefer] = useState<PanelSide | null>(null);
  const width = useWidthOf(cols);
  const change = (next: LayerLayout, commit: boolean) => {
    latest.current = next;
    setLayout(next);
    if (commit) saveLayerLayout(next);
  };
  const open = (side: PanelSide): Column => ({open: true, width: layout[side].w, forced: false});
  const fit = !wide ? {left: open("left"), right: open("right")}
    : width ? fitPanels(layout.left, layout.right, LAYER_LIMITS, width, prefer)
    : {left: {...open("left"), open: layout.left.open}, right: {...open("right"), open: layout.right.open}};
  const focus = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (!focus.current) return;
    cols.current?.querySelector<HTMLElement>(focus.current)?.focus();
    focus.current = null;
  });
  const props = (side: PanelSide) => ({
    side, column: fit[side], min: LAYER_LIMITS[side][0], max: maxPanelWidth(side, width, fit, LAYER_LIMITS),
    railWidth: LAYER_LIMITS.rail,
    onWidth: (w: number) => change({...latest.current, [side]: {...latest.current[side], w}}, false),
    onCommit: () => saveLayerLayout(latest.current),
    onReset: () => change({...latest.current, [side]: {...latest.current[side], w: DEFAULT_LAYER_LAYOUT[side].w}}, true),
    onOpen: (now: boolean) => {
      change({...latest.current, [side]: {...latest.current[side], open: now}}, true);
      if (now) setPrefer(side);  // in a narrow window the other panel collapses
      focus.current = `.c-col-${side} > ${now ? ".c-split" : ".c-rail"}`;
    },
  });
  const panels = `${fit.left.open ? fit.left.width : 0},${fit.right.open ? fit.right.width : 0}`;
  return {fit, props, panels};
}

/** A page with a panel on the left and the map it uses on the right (on phones the map on top, the panel scrolling
 *  under it); `aside` (its label) adds a panel on the right, an element the children fill (LayerPage renders a
 *  second tree into it), under the panel on phones. With `aside` both panels are side panels as the result's
 *  (ui/SidePanel.tsx: dragged edges, collapsed to rails, the layout kept), their content in a scroll box each. */
export function MapPage({title, aside, children}:
                        {title: string; aside?: string;
                         children: (place: PlaceMap, aside: HTMLElement | null, extras: MapPageExtras) => ComponentChildren}) {
  const ref = useRef<HTMLDivElement>(null);
  const cols = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<PlaceMap | null>(null);
  const [right, setRight] = useState<HTMLElement | null>(null);
  const [rails, setRailsState] = useState<[string, string]>(["", ""]);
  const wide = useMedia(DESKTOP);
  const {fit, props, panels} = useLayerPanels(wide, cols);
  const extras = useRef<MapPageExtras>({panels, setRails: () => {}});
  extras.current = {panels, setRails: (l, r) => setRailsState((now) => now[0] === l && now[1] === r ? now : [l, r])};
  useEffect(() => {
    const placeMap = new PlaceMap(ref.current!, {controls: "bottomright"});
    placeMap.setSearchVisible(false);
    (window as any).FINDALINE_PLACE = placeMap;
    setPlace(placeMap);
    const observer = new ResizeObserver(() => placeMap.map.invalidateSize());
    observer.observe(ref.current!);
    return () => { observer.disconnect(); placeMap.map.remove(); };
  }, []);
  // The map's size follows the panels at once (also where no frame is drawn, so no ResizeObserver reports)
  useLayoutEffect(() => { place?.map.invalidateSize(); }, [place, panels]);
  if (!aside) {
    return <div class="c-mappage">
      <aside class="c-sidepanel" aria-label={title}>
        <h1 class="u-h">{title}</h1>
        {place && children(place, null, extras.current)}
      </aside>
      <div class="c-newmap" ref={ref} />
    </div>;
  }
  return <div class="c-mappage c-mappage-3" ref={cols}>
    <SidePanel {...props("left")} name="filters" label={title} rail={{icon: "filter", text: rails[0] || title}}>
      <div class="c-col-scroll" data-scroll="left">
        <h1 class="u-h">{title}</h1>
        {place && right && children(place, right, extras.current)}
      </div>
    </SidePanel>
    <div class="c-newmap" ref={ref} />
    <SidePanel {...props("right")} name="histograms" label={aside} rail={{icon: "bars", text: rails[1] || aside}}>
      <div class="c-col-scroll" data-scroll="right" ref={setRight} />
    </SidePanel>
  </div>;
}

export function AdminPage({jobs}: {jobs: Job[]}) {
  if (user.local || !user.admin) return <div class="c-page"><p>Administrators of the public site only.</p></div>;
  return <AdminC jobs={jobs} />;
}

export function OsmPage() {
  if (!user.local && !user.admin) return <div class="c-page"><p>The local app and administrators only.</p></div>;
  return <MapPage title="OpenStreetMap extracts">{(place) => <OsmC place={place} onStarted={() => go("#home")} />}</MapPage>;
}

