// The panels of the result view's frame (SpotColumns.tsx): the slots' types, the hook that follows a SpotView, and
// what stands in the slots (PANELS). Until the list, the details, the hint and the table of spots are built (view
// B3: SpotList, SpotDetails, Hint, SpotChooser), each slot shows a placeholder; B3 puts its components into PANELS
// here and nowhere in the frame. PANELS' entries are functions called when the frame draws, so the components may
// import this file's types and hook.

import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import type { Snap } from "../../ui/components";
import type { Padding } from "../ResultMap";
import type { SpotMap } from "../SpotMap";
import type { SpotChoice, SpotView } from "../spots";
import { t } from "../../i18n";
import type { Area } from "./LineChooser";
import { SLOTS } from "./SpotDetails";

/** What every panel gets: the view's model, the canvas (null until the map is made), the layout (wide: the three
 *  columns; else a phone's map with the sheet), the map's free part for moves (SpotMap.reveal, zoomTo) and, on a
 *  phone, the sheet's state (peek, half, full) and how to change it. */
export interface PanelProps { view: SpotView; map: SpotMap | null; wide: boolean; padding(): Padding;
                              sheet?: {snap: Snap; setSnap(snap: Snap): void};
                              /** Where the frame draws this call of `hint`: beside the map's status line ("map": in
                               *  the columns the hint and its "?", on a phone only the "?") or as the sheet's first
                               *  line ("sheet": a phone's hint). */
                              place?: "map" | "sheet" }

/** The table of spots' own: the spots a press reached, its point in the viewport, the part of the viewport the map
 *  shows free (LineChooser's placing), and how it closes (the frame also closes it when the map moves, the view
 *  changes, or Esc is pressed). */
export interface ChooserProps extends PanelProps { choices: SpotChoice[]; at: {x: number; y: number}; area: Area;
                                                   onClose(): void }

/** The frame's slots. `list`: the left column (a phone: the sheet's body, under the details); `details`: the right
 *  column (a phone: the sheet's body, first); `sheetHead`: a phone's sheet head; `hint`: on a desktop beside the
 *  map's status line; on a phone it is called twice: as the sheet's first line (`place` "sheet") and beside the
 *  map's status line (`place` "map": the round "?" that shows a hidden hint again); `chooser`: the table of spots
 *  under a press. */
export interface SpotPanels {
  list(p: PanelProps): ComponentChildren;
  details(p: PanelProps): ComponentChildren;
  sheetHead(p: PanelProps): ComponentChildren;
  hint(p: PanelProps): ComponentChildren;
  chooser?(p: ChooserProps): ComponentChildren;
}

/** Draw the component again after every change of the view (its own and its model's: SpotView.subscribe). */
export function useSpotView(view: SpotView) {
  const [, setTick] = useState(0);
  useEffect(() => view.subscribe(() => setTick((n) => n + 1)), [view]);
}

export const PANELS: SpotPanels = {
  list: (p) => SLOTS.list(p),
  details: (p) => SLOTS.details(p),
  sheetHead: (p) => SLOTS.sheetHead(p),
  hint: (p) => SLOTS.hint(p),
  chooser: (p) => SLOTS.chooser(p),
};
