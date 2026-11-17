// The hint of the result view (docs/line-volume/spec-view.md B.2 item 12): how to open "Lines from here" at any
// point of the map. "Right click the map: the lines from that point" with a mouse, "Press and hold the map: the
// lines from that point" with a finger or a pen and always in the phone layout; before any press the word follows
// the device (pointer: coarse). Its × hides it and leaves a round "?" that shows it again; the choice is kept in the
// browser (viewstate.ts). In the columns both stand on the map beside the status line (the frame's `hint` slot:
// their boxes are obstacles of the map's numbers); on a phone the line is the sheet's first and the "?" stands
// beside the map's status line (the frame asks for each: PanelProps.place). A box of theirs over the map carries
// `data-map-control` (the viewer's rule: no number of the map under it).
// Two parts, so that each can stand where its layout wants it: HintLine and HintOpen.

import { useEffect } from "preact/hooks";
import { Icon } from "../../ui/icons";
import { t } from "../../i18n";
import type { SpotView } from "../spots";
import { useViewPanels } from "./SpotList";
import type { PanelProps } from "./SpotPanels";
import { byFinger, changePanels, panelState, showHint } from "./viewstate";

// where the focus goes once the hint was hidden ("?") or shown again (its ×)
let refocus: ".vl-hint-open" | ".vl-hint-x" | null = null;

/** Follow the pointer in use: the type of the last press anywhere on the page. */
function usePointer(view: SpotView) {
  useEffect(() => {
    const down = (e: PointerEvent) => {
      if (e.pointerType && e.pointerType !== panelState(view).pressedBy) changePanels(view, (s) => { s.pressedBy = e.pointerType; });
    };
    document.addEventListener("pointerdown", down, true);
    return () => document.removeEventListener("pointerdown", down, true);
  }, [view]);
}

function useRefocus() {
  useEffect(() => {
    if (!refocus) return;
    const to = document.querySelector<HTMLElement>(refocus);
    if (to) { to.focus(); refocus = null; }
  });
}

/** The hint's words now. */
export function hintText(view: SpotView, wide: boolean): string {
  const coarse = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  return t(byFinger(wide, panelState(view).pressedBy, coarse) ? "ui.view.hint.finger" : "ui.view.hint.mouse");
}

/** The hint with its ×; nothing while it is hidden. */
export function HintLine({view, wide}: {view: SpotView; wide: boolean}) {
  useViewPanels(view);
  usePointer(view);
  useRefocus();
  if (!panelState(view).hint) return null;
  return <div class={wide ? "vl-hint" : "vl-hint vl-hint-sheet"} data-map-control={wide ? true : undefined}>
    <span class="vl-hint-text">{hintText(view, wide)}</span>
    <button type="button" class="r-note-x vl-hint-x" aria-label={t("ui.view.hint.hide")}
            onClick={() => { refocus = ".vl-hint-open"; showHint(view, false); }}><Icon name="close" /></button>
  </div>;
}

/** The round "?" that shows the hint again; nothing while the hint is shown. */
export function HintOpen({view}: {view: SpotView}) {
  useViewPanels(view);
  useRefocus();
  if (panelState(view).hint) return null;
  return <button type="button" class="vl-hint-open" aria-label={t("ui.view.hint.show")} title={t("ui.view.hint.show")}
                 data-map-control onClick={() => { refocus = ".vl-hint-x"; showHint(view, true); }}>?</button>;
}

/** The frame's `hint` slot: in the columns the hint or its "?", beside the map's status line; on a phone the
 *  frame asks twice: for the sheet's first line (`place` "sheet": the hint) and for the map (`place` "map": the
 *  "?" beside the status line while the hint is hidden). */
export function Hint({view, wide, place}: PanelProps) {
  if (wide) return <><HintLine view={view} wide /><HintOpen view={view} /></>;
  return place === "sheet" ? <HintLine view={view} wide={false} /> : <HintOpen view={view} />;
}
