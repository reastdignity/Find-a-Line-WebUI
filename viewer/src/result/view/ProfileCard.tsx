// The profile as a card floating over the bottom of the map (C's result on a desktop): ProfileDock in fill
// mode with its fold button, the card's top edge dragged for its height and both side edges for its width
// (the dragged edge moves, the other stays). Its place and size come from the Layout (layout.ts), clamped by
// the size of the card's positioned parent (the map's column, measured): at least its content's height with
// the chart at CHART_MIN (the bar, the profile's head, the controls and the readout: measured, at least
// LIMITS.cardMin; the top edge's least value and its Home key), at most LIMITS.cardShare of the map; in a
// narrow map the insets shrink (not kept). A map lower than LIMITS.low opens it folded; whatever is changed
// there (unfolded, its height or edges dragged) holds for the page and never reaches `onLayout`. Changes go
// to `onLayout` (commit: keep them now: a drag ended, a key, a click). `onSettle` is called once the card's
// size is known after it appeared and after each commit (the map keeps the selected line clear of it). The
// parent reads the card's height from the DOM (.r-card) for the map's padding and the corners (corners.ts
// useCornersAboveCard).

import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { Splitter } from "../../ui/components";
import type { Line } from "../../types";
import type { ResultModel } from "../model";
import type { ResultMap } from "../ResultMap";
import { cx, useModel } from "./common";
import { CHART_MIN, DEFAULT_LAYOUT, LIMITS, cardHeight, cardInsets, cardMaxHeight, cardWidthMin, isLowMap, moveCardEdge,
         type Layout } from "./layout";
import { ProfileDock, profileShown } from "./ProfileDock";

export interface ProfileCardProps {
  model: ResultModel;
  view?: ResultMap | null;
  /** Two points measured on the map, shown in the same card. */
  measured?: Line | null;
  onCloseMeasured?(): void;
  layout: Layout;
  /** A new layout: `commit` true when it should be kept now. */
  onLayout(next: Layout, commit: boolean): void;
  /** The card's size is known after it appeared, or after a change was committed (a drag ended, a key, the
   *  fold button). */
  onSettle?(): void;
}

/** What the user chose in a low map, for the page and never kept: folded (null: not chosen, so folded), the
 *  height and the insets (null: the layout's). */
type LowChoices = {folded: boolean | null; h: number | null; l: number | null; r: number | null};
const NO_CHOICES: LowChoices = {folded: null, h: null, l: null, r: null};
let lowChoices: LowChoices = NO_CHOICES;

/** The low-window choices back to none (tests and the kit page). */
export function resetLowChoice() { lowChoices = NO_CHOICES; }

/** About the height (px) a card will have in a map `mapHeight` px high when it appears, before it is drawn
 *  (a selection zooms to its line first): its bar when folded (also in a low map unless unfolded there), else
 *  the layout's height (its content may need more). */
export function cardHeightAhead(layout: Layout, mapHeight: number): number {
  const low = isLowMap(mapHeight);
  if (low ? lowChoices.folded ?? true : layout.profile.folded) return FOLDED_HEIGHT;
  return cardHeight(low && lowChoices.h !== null ? {...layout, profile: {...layout.profile, h: lowChoices.h}} : layout,
                    mapHeight);
}
const FOLDED_HEIGHT = 46;  // px: the folded card (its bar)

export function ProfileCard({model, view, measured, onCloseMeasured, layout, onLayout, onSettle}: ProfileCardProps) {
  useModel(model);
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{w: number; h: number} | null>(null);  // the positioned parent's size
  const [actual, setActual] = useState(0);  // the card's height as drawn
  const [least, setLeast] = useState(LIMITS.cardMin);  // its least height (its content's, measured)
  const [, redraw] = useState(0);
  const shown = profileShown(model, measured);
  const low = !!box && isLowMap(box.h);
  // The layout this card follows: in a low map with the page's choices over it
  const own: Layout = low ? {...layout, profile: {
    folded: lowChoices.folded ?? true, h: lowChoices.h ?? layout.profile.h,
    l: lowChoices.l ?? layout.profile.l, r: lowChoices.r ?? layout.profile.r}} : layout;
  // The layout of the last change: a key's onChange and onCommit come before the next render
  const latest = useRef(own);
  latest.current = own;
  const appeared = useRef(false), committed = useRef(false);

  useLayoutEffect(() => {
    const card = ref.current;
    // The positioned ancestor, not the parent (as Sheet)
    const parent = (card?.offsetParent ?? card?.parentElement) as HTMLElement | null | undefined;
    if (!card || !parent) return;
    const measure = () => {
      setBox((b) => b && b.w === parent.clientWidth && b.h === parent.clientHeight ? b
        : {w: parent.clientWidth, h: parent.clientHeight});
      setActual(card.offsetHeight);
    };
    measure();
    if (typeof ResizeObserver !== "function") return;
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    observer.observe(card);
    return () => observer.disconnect();
  }, [shown]);

  // After every render (also where no frame is drawn, so no ResizeObserver reports): the parent's size, the
  // height as drawn, the least one (the content less the chart's box, plus the chart's least height), and the
  // card settled
  useLayoutEffect(() => {
    const card = ref.current;
    if (!card) { appeared.current = false; return; }
    const parent = (card.offsetParent ?? card.parentElement) as HTMLElement | null;
    if (parent) {
      setBox((b) => b && b.w === parent.clientWidth && b.h === parent.clientHeight ? b
        : {w: parent.clientWidth, h: parent.clientHeight});
    }
    setActual(card.offsetHeight);
    const chart = card.querySelector<HTMLElement>(".fal-profile-chart");
    if (chart && !card.classList.contains("r-card-folded")) {
      setLeast(Math.max(LIMITS.cardMin, card.offsetHeight - chart.clientHeight + CHART_MIN));
    }
    if (!box || (appeared.current && !committed.current)) return;
    appeared.current = true;
    committed.current = false;
    onSettle?.();
  });

  if (!shown) return null;
  const folded = own.profile.folded;
  const emit = (next: Layout, commit: boolean) => {
    latest.current = next;
    if (commit) committed.current = true;
    if (low) {  // for the page: nothing of a low map is kept
      lowChoices = {folded: next.profile.folded, h: next.profile.h, l: next.profile.l, r: next.profile.r};
      redraw((n) => n + 1);
    } else onLayout(next, commit);
  };
  const commit = () => {
    committed.current = true;
    if (!low) onLayout(latest.current, true);
    redraw((n) => n + 1);  // settled once drawn, also when nothing changed
  };
  const profile = (part: Partial<Layout["profile"]>): Layout =>
    ({...latest.current, profile: {...latest.current.profile, ...part}});
  const setFolded = (f: boolean) => emit(profile({folded: f}), true);
  /** Unfolded by a drag or a key on the top edge. */
  const unfold = (part: Partial<Layout["profile"]>) => profile({...part, folded: false});

  const mapW = box?.w ?? 0, mapH = box?.h ?? 0;
  const [l, r] = box ? cardInsets(own, mapW) : [own.profile.l, own.profile.r];
  const height = box ? cardHeight(own, mapH) : own.profile.h;
  const width = mapW - l - r, widthMin = cardWidthMin(mapW), widthMax = mapW - 2 * LIMITS.inset;
  const side = (edge: "l" | "r") => box && <Splitter
    orientation="vertical" class={`r-card-side r-card-${edge}`} grow={edge === "l" ? -1 : 1}
    label={`Width of the profile, ${edge === "l" ? "left" : "right"} edge`}
    value={width} min={Math.min(widthMin, width)} max={Math.max(widthMax, width)}
    onChange={(w) => emit(moveCardEdge(latest.current, edge, edge === "l" ? mapW - r - w : mapW - l - w, [l, r], mapW),
                          false)}
    onCommit={commit} onReset={() => emit(profile({[edge]: LIMITS.inset}), true)} />;

  return <div ref={ref} class={cx("r-card", folded && "r-card-folded")}
              style={{left: `${l}px`, right: `${r}px`, height: folded ? undefined : `${height}px`}}>
    <Splitter orientation="horizontal" class="r-card-top" label="Height of the profile" grow={-1}
              value={actual || (folded ? 0 : height)} min={least} max={Math.max(least, cardMaxHeight(mapH))}
              onStart={() => { if (folded) emit(unfold({}), true); }}
              onChange={(h) => emit(unfold({h}), false)} onCommit={commit}
              onReset={() => emit(unfold({h: DEFAULT_LAYOUT.profile.h}), true)}
              onToggle={() => setFolded(!folded)} />
    {side("l")}
    {side("r")}
    <ProfileDock model={model} view={view} measured={measured} onCloseMeasured={onCloseMeasured} fill
                 folded={folded} onFold={setFolded} />
  </div>;
}
