// The selected line's own controls in the result view (step 3c: the user's "11 a" and "4 d" at gate 1, 2026-11-20, in
// the places of the accepted mock-up): the star in the details' head (today's folder picker, FavouritePicker, as the
// kit's icon; a phone's sheet rises to full for its folders), the line's actions under "Stands for" ("3D view" with
// the spot's other passing lines as `&also=`, "Copy link" with today's field when the clipboard refuses, "Profile"
// once the line's profile was closed), "Report this line" below the facts (the frame's `lineActions` slot) and a
// phone's profile dock right under the four values (today's ProfileDock; a desktop's profile is the frame's card).
// Today's words and behaviour (LineDetails.tsx, whose words are not in the catalogue either); today's "Zoom" is left
// out (11 a). A page without favourites (a run's map.html, a share link: ResultModel.favouritesOn) has no star, one
// without a 3D view (`view3dOf`: map.html) no "3D view", one without the report form (the local app: canReport) no
// "Report this line". The line's profile is closed and shown again through the model (profileClosed, closeProfile,
// showProfile: SpotView.select and step open it again), which the frame's card shares.

import { useMemo, useState } from "preact/hooks";
import { Button } from "../../ui/components";
import { t } from "../../i18n";
import { lineCoords } from "../../keys";
import { canReport, openReport } from "../../report";
import { LineCursor, type Line } from "../../types";
import { alsoParam, OTHERS_MAX } from "../../view3d/page";
import type { SpotView } from "../spots";
import { FavouritePicker } from "./FavouritePicker";
import { appLink, copy, LinkField } from "./LineDetails";
import { ProfileDock } from "./ProfileDock";
import type { PanelProps } from "./SpotPanels";  // types only (SpotPanels.tsx imports the slots)

/** What the line's controls get: the panel's props, and the frame's measured line (`measured`: Measure's two points
 *  or a link's line measured outside the run, shown by the frame's own card or dock; PanelProps carries it on the
 *  stack, step 3c's frame). */
type Props = PanelProps & {measured?: Line | null};

/** The selected line, its row and its spot (null: nothing selected). */
const selected = (view: SpotView) => view.selected;

/** The star of the details' head: today's folder picker as the kit's star icon (filled for a favourite), only where the
 *  page keeps favourites. On a phone the sheet rises to full while its folders open (they open under the head). */
export function LineStar({view, sheet}: Props) {
  const sel = selected(view), model = view.model;
  if (!sel || !model.favouritesOn) return null;
  return <FavouritePicker model={model} line={sel.line} icon onOpen={(open) => { if (open) sheet?.setSnap("full"); }} />;
}

/** The keys of the 3D view's other lines: the spot's passing lines but the selected one, in the spot's order, at most
 *  OTHERS_MAX; each its link as ResultModel.lineLink writes it (keys.lineCoords, the 3D view's key of the same line),
 *  read through a cursor on the run's columns: no Line is made for them (a selection makes only its own line). */
export function alsoKeys(view: SpotView, spot: number, row: number): string[] {
  const cursor = new LineCursor(view.model.data.columns), keys: string[] = [];
  for (const r of view.passingOf(spot)) {
    if (keys.length >= OTHERS_MAX) break;
    if (r === row) continue;
    cursor.i = r;
    keys.push(lineCoords(cursor));
  }
  return keys;
}

/** "3D view", "Copy link" and, once the line's profile was closed, "Profile" in one row; the field to copy the link by
 *  hand when the browser refuses the clipboard (today's). The 3D view's address is the caller's (`view3dOf`: the run's
 *  page with the line, and none of `&also=`: the model built for the view has no groups, so ResultModel.alsoOf gives
 *  none) with the spot's other passing lines. */
export function LineActions(p: Props) {
  const {view, linkOf, view3dOf} = p, sel = selected(view), model = view.model;
  const [copied, setCopied] = useState<{line: Line; ok: boolean; text: string} | null>(null);
  const also = useMemo(() => sel ? alsoParam(alsoKeys(view, sel.spot, sel.row)) : "", [sel?.row, view.version]);
  if (!sel) return null;
  const l = sel.line;
  const link = () => {
    const text = linkOf ? linkOf(model, l) : appLink(model, l);
    copy(text).then((ok) => setCopied({line: l, ok, text}));
  };
  const shown = copied && copied.line === l ? copied : null;
  return <>
    <div class="vl-lacts">
      {view3dOf && <Button icon="cliff" class="r-view3d" href={view3dOf(model, l) + also}>{t("ui.view3d.open")}</Button>}
      <Button icon="link" class="r-copy" onClick={link}>{shown?.ok ? "Link copied" : "Copy link"}</Button>
      {model.profileClosed && <Button icon="bars" class="r-reprofile" onClick={() => model.showProfile()}>Profile</Button>}
    </div>
    {shown && !shown.ok && <LinkField text={shown.text} />}
    {shown?.ok && <input type="hidden" class="r-copied" value={shown.text} />}
  </>;
}

/** A phone's profile of the selected line, right under the four values (4 d): today's dock with the point under the
 *  finger on the map (SpotMap.hoverAt); none while it is closed, and none while the frame shows a measured profile
 *  (the frame's own dock: one profile at a time, as today's sheet). */
export function LineDock({view, map, measured}: Props) {
  const sel = selected(view), model = view.model;
  if (!sel || model.profileClosed || measured) return null;
  return <ProfileDock model={model} view={map} line={sel.line} onClose={() => model.closeProfile()} class="vl-dock" compact />;
}

/** "Report this line" (the frame's `lineActions` slot: below the facts), where the page has the report form; nothing
 *  while "Lines from here" stands in the details' place. */
export function ReportLine({view}: Props) {
  const sel = selected(view), model = view.model;
  if (!sel || view.fan || !canReport()) return null;
  const l = sel.line;
  return <Button icon="warn" kind="ghost" class="r-report vl-report"
                 onClick={() => openReport({category: "results", about: `a line of ${model.data.run.name}`,
                                            context: {run: model.runOf(l), line: model.lineLink(l)}})}>
    Report this line</Button>;
}
