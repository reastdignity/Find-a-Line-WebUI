// The profile card of the 3D view (docs/3d-view-contract.md, "Round 2", decision 4): the 2D result's chart
// (Profile.tsx ProfilePanel, compact) in the card slot over the stage's bottom, behind the tool `profile`. A second
// small Preact tree rendered with `render` of preact into the slot (never preact/compat) inside a plain-DOM page;
// folded by default, the choice kept in localStorage (findaline.view3d.profile). The chart's cursor moves the walker
// and the walker's moves are the chart's cursor (the distance along the profile and the fraction of the span are
// the same thing). Between an anchor's move and its new profile the card says so.

import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { t } from "../i18n";
import { ProfilePanel } from "../Profile";
import type { Line } from "../types";
import type { Current } from "./save";
import type { LineView } from "./line";
import type { PatchMeta } from "./decode";
import type { SceneCore } from "./scene";
import "../profile.css";
import "./profilecard.css";

const KEY = "findaline.view3d.profile";
const ICON = "M1.5 14.5h13M2 11l3-4 3 2.5 3-5 3 3";

function remembered(): boolean {
  try { return localStorage.getItem(KEY) === "open"; } catch { return false; }
}

function remember(open: boolean) {
  try { localStorage.setItem(KEY, open ? "open" : "folded"); } catch { /* the page is right without it */ }
}

/** What the card shows: the current line (null until its profile is in), and the walker's distance along it. */
interface Shown {
  line: Line | null;
  cursor: number | null;
}

interface CardProps {
  shown: { get(): Shown; subscribe(fn: (s: Shown) => void): () => void };
  meta: PatchMeta;
  onCursor(distance: number | null, length: number): void;
  onHide(): void;
}

function Card({shown, meta, onCursor, onHide}: CardProps) {
  const [s, setShown] = useState<Shown>(shown.get());
  const [rigging, setRigging] = useState(false);
  const [title, setTitle] = useState({title: "", facts: ""});
  useEffect(() => { setShown(shown.get()); return shown.subscribe(setShown); }, [shown]);
  const line = s.line;
  return <section class={"v3-pcard" + (rigging ? " r-rigging" : "")} aria-label={t("ui.view3d.profile")}
                  data-waiting={line ? "" : "1"}>
    <div class="v3-pcard-head">
      <b>{t("ui.view3d.profile")}</b>
      {line && title.facts && <span class="u-small v3-pcard-facts" title={title.title} aria-hidden="true">{title.facts}</span>}
      {line && title.title && <span class="u-sr fal-profile-title">{title.title}</span>}
      <span class="u-grow" />
      {line && <button type="button" class={"u-chip" + (rigging ? " u-on" : "")} aria-expanded={rigging}
                       onClick={() => setRigging(!rigging)}>{t("ui.view3d.profile_rigging")}</button>}
      <button type="button" class="u-btn v3-pcard-hide" onClick={onHide}>{t("ui.view3d.profile_hide")}</button>
    </div>
    {line ? <div class="r-profile">
      <ProfilePanel line={line} model={meta.model === "sag" ? "sag" : "formula"} slope={meta.slope}
                    leashFall={meta.leash_fall} rigging={meta.rigging} fill compact cursorAt={s.cursor}
                    onHover={() => {}} onCursor={onCursor} onClose={onHide}
                    onTitle={(title, facts) => setTitle((o) => o.title === title && o.facts === facts ? o : {title, facts})} />
    </div> : <p class="v3-pcard-wait" role="status">{t("ui.view3d.profile_waiting")}</p>}
  </section>;
}

/** The tool `profile` (order 5) and its card; the choice (open or folded) is kept in the browser. */
export function createProfileCard(scene: SceneCore, view: LineView, current: Current, meta: PatchMeta) {
  let open = remembered(), cursor: number | null = null;
  const listeners = new Set<(s: Shown) => void>();
  const store = {
    get(): Shown { return {line: current.line(), cursor}; },
    subscribe(fn: (s: Shown) => void) { listeners.add(fn); return () => { listeners.delete(fn); }; },
  };
  const push = () => { if (open) { const s = store.get(); for (const fn of listeners) fn(s); } };
  // The cursor in the profile's metres: the walker's fraction of the span times the line's length
  const length = () => current.line()?.len ?? 0;
  const cursorOf = () => view.span > 0 ? view.s / view.span * length() : null;
  const button = scene.tools.add({id: "profile", label: t("ui.view3d.profile"), icon: ICON, order: 5, toggle: true,
                                  onClick: () => set(!open)});
  function set(next: boolean) {
    open = next;
    remember(open);
    button.setPressed(open);
    scene.card.dataset.open = open ? "1" : "";
    if (open) {
      cursor = cursorOf();
      render(<Card shown={store} meta={meta} onHide={() => set(false)}
                   onCursor={(d, len) => { if (d !== null && len > 0) view.setWalker(d / len * view.span); }} />, scene.card);
    } else render(null, scene.card);
  }
  view.onWalker(() => { cursor = cursorOf(); push(); });
  view.onProfile(() => { cursor = cursorOf(); push(); });
  view.onAnchors(push);
  scene.onDispose(() => render(null, scene.card));
  set(open);
  return {set, isOpen: () => open};
}
