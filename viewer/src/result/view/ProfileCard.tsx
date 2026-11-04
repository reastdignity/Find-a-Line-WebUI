// The profile as a card floating over the bottom of the map (C's result on a desktop): ProfileDock in fill
// mode with its fold button, the card's top edge dragged for its height and both side edges for its width
// (the dragged edge moves, the other stays). Its place and size come from the Layout (layout.ts), clamped by
// the size of the card's positioned parent (the map's column, measured): at least LIMITS.cardMin high (the
// chart keeps 120 px: the card grows over that when the bar, the controls and the readout need it), at
// most LIMITS.cardShare of the map; in a narrow map the insets shrink (not kept). A map lower than
// LIMITS.low opens it folded; unfolding or dragging it there holds for the page (not kept). Changes go
// to `onLayout` (commit: keep them now: a drag ended, a key, a click). The parent reads the card's height
// from the DOM (.r-card) for the map's padding and the corners (corners.ts useCornersAboveCard).

import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { Splitter } from "../../ui/components";
import type { Line } from "../../types";
import type { ResultModel } from "../model";
import type { ResultMap } from "../ResultMap";
import { cx, useModel } from "./common";
import { DEFAULT_LAYOUT, LIMITS, cardHeight, cardInsets, cardMaxHeight, cardWidthMin, isLowMap, moveCardEdge,
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
}

/** Whether the card is folded in a low map, as the user chose it there (null: not chosen, so folded); for
 *  the page, never kept. */
let lowChoice: boolean | null = null;

/** The low-window choice back to none (tests and the kit page). */
export function resetLowChoice() { lowChoice = null; }

export function ProfileCard({model, view, measured, onCloseMeasured, layout, onLayout}: ProfileCardProps) {
  useModel(model);
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{w: number; h: number} | null>(null);  // the positioned parent's size
  const [actual, setActual] = useState(0);  // the card's height as drawn
  const [, setChosen] = useState(0);  // drawn again after a low-window choice
  // The layout of the last change: a key's onChange and onCommit come before the next render
  const latest = useRef(layout);
  latest.current = layout;
  const shown = profileShown(model, measured);

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

  if (!shown) return null;
  const low = !!box && isLowMap(box.h);
  const folded = low ? lowChoice ?? true : layout.profile.folded;
  const emit = (next: Layout, commit: boolean) => { latest.current = next; onLayout(next, commit); };
  const commit = () => onLayout(latest.current, true);
  const profile = (part: Partial<Layout["profile"]>): Layout =>
    ({...latest.current, profile: {...latest.current.profile, ...part}});
  const choose = (f: boolean) => { lowChoice = f; setChosen((n) => n + 1); };
  const setFolded = (f: boolean) => { if (low) choose(f); else emit(profile({folded: f}), true); };
  /** Unfolded by a drag or a key on the top edge (in a low map for the page only). */
  const unfold = (part: Partial<Layout["profile"]>) => {
    if (low && lowChoice !== false) choose(false);
    return profile(low ? part : {...part, folded: false});
  };

  const mapW = box?.w ?? 0, mapH = box?.h ?? 0;
  const [l, r] = box ? cardInsets(layout, mapW) : [layout.profile.l, layout.profile.r];
  const height = box ? cardHeight(layout, mapH) : layout.profile.h;
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
              value={actual || (folded ? 0 : height)} min={LIMITS.cardMin} max={cardMaxHeight(mapH)}
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
