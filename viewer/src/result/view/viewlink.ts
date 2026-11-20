// A line's link in the result view (docs/line-volume/spec-view.md B.2, "What the app needs that the mock-up does not
// have": `#line=` links select the line and open its spot), as today's page has it (ResultColumns.tsx
// useLinkedLine) on the view's selection (SpotView.selected: the model built without the grouping selects nothing of
// its own, so model.openLinked cannot select a line of the run here). The frame (SpotColumns.tsx) gets the route's
// line (`line`: #run=<id>&line=… in the app, #line=… on a run's map.html and on a share link's page) and `nav`,
// which Back, Forward and a hashchange move on, and its caller's `hashOf`:
// - a line of the run that passes is selected in its spot and put in view (the frame's zoomTo with its padding);
// - a line that "Top level only" alone hides: the chip is turned off and the line selected (the user's "6. a",
//   spec-view.md B.2 item 14; the chip is on at every start and kept nowhere);
// - a line other filters hide: today's note with its action "clear filters" (the filters and both kinds of lines
//   back to all, then the link opened again), the link kept in the address while nothing is selected;
// - a line not among the run's: model.openLinked as on today's page (measured where the page may ask profiles: the
//   line handed to the frame, the link's key in model.measuredLink and in the address; else today's note).
// The notes show where the view shows model.note (SpotSummary's ResultNote); a link that ends in one tells the frame
// (`onNote`: a phone raises its sheet to half, where the note shows). The selection goes into the hash
// (history.replaceState: never a new entry; only while the hash is this run's page); no selection writes the run's
// hash without a line (on a map's page: the address without a hash), but for the link of a line the filters hide or
// of a measured line, which stays. A new selection ends a measured line (today's useMeasureEnds). The route is opened
// once per (line, nav) and view: Desktop and Phone are made again for the same view when the window crosses the
// phone's width, and that opens nothing.

import { useEffect, useRef } from "preact/hooks";
import { NO_FILTERS, saveFilters } from "../../filters";
import type { Line } from "../../types";
import type { Padding, SpotMap } from "../SpotMap";
import type { SpotView } from "../spots";
import { linkOf, type ResultColumnsProps } from "./ResultColumns";

/** Today's note of a link whose line the filters hide and its action: the words of model.ts openLinked (they are
 *  not in the catalogue there either). */
export const HIDDEN_NOTE = "The line of the link is hidden by the filters.";
export const CLEAR_FILTERS = "clear filters";

/** Open the line of `route` (a hash, or a line's value) in the view: its row once it is selected, else -1 (a note, or
 *  a measurement under way). `show(row)` puts a selected line in view; `onMeasured` gets a line outside the run once
 *  it is measured. */
export function openLink(view: SpotView, route: string, show: (row: number) => void,
                         onMeasured: (l: Line) => void): number {
  const model = view.model, wanted = linkOf(route);
  if (!wanted) return -1;
  const line = model.linkedLine(wanted);
  if (!line) {  // not among the run's lines: model.openLinked touches no group on this way
    model.openLinked(route, onMeasured);
    return -1;
  }
  const row = model.indexOf(line);
  model.measuredLink = null;
  model.note = null;  // the selection below, or the note, tells the view's listeners
  if (view.topOnlyHides(row)) view.setTopOnly(false);
  if (view.passes(row)) {
    view.select(view.spotOf(row), row);
    show(row);
    return row;
  }
  model.setNote({text: HIDDEN_NOTE, action: CLEAR_FILTERS, onAction: () => {
    // as model.openLinked's action: no filter, both kinds of lines; one change the view follows (setState)
    model.filters = {...NO_FILTERS};
    saveFilters(model.filters);
    model.setState({...model.state, showClean: true, showOver: true});
    openLink(view, route, show, onMeasured);
  }});
  return -1;
}

/** The (line, nav) of the route each view has opened. */
const opened = new WeakMap<SpotView, string>();

interface Frame {
  map: SpotMap | null;
  padding(): Padding;
  onMeasured(l: Line | null): void;
  hashOf: ResultColumnsProps["hashOf"];
  onNote?(): void;
}

/** The frame that draws each view now: a link opened later (a note's action, a measurement that ends) reaches the
 *  map and the frame of now, also after the window crossed the phone's width. */
const frames = new WeakMap<SpotView, {current: Frame}>();

/** Put a line of the view in view (the frame's zoomTo with its padding). */
function showRow(view: SpotView, row: number) {
  const frame = frames.get(view)?.current;
  frame?.map?.zoomTo(row, frame.padding());
}

/** The route's line opened in the view once the canvas is there (`map`), the selection written into the hash from
 *  then on. `padding()`: the frame's padding of a move; `onMeasured`: the frame keeps a measured line (null: a new
 *  selection ended it); `onNote`: the link ended in a note (hidden by the filters, not in the run, or its
 *  measurement failed; a phone raises its sheet to show it). */
export function useViewLink(view: SpotView, map: SpotMap | null, line: string | null, nav: number,
                            hashOf: ResultColumnsProps["hashOf"], padding: () => Padding,
                            onMeasured: (l: Line | null) => void, onNote?: () => void) {
  const latest = useRef<Frame>({map, padding, onMeasured, hashOf, onNote});
  latest.current = {map, padding, onMeasured, hashOf, onNote};
  useEffect(() => {
    frames.set(view, latest);
    return () => { if (frames.get(view) === latest) frames.delete(view); };
  }, [view]);
  // the route's line: before the hash is written (the effect below), so no drawing before it can drop the link
  useEffect(() => {
    if (!map || !line) return;
    const key = `${nav} ${line}`;
    if (opened.get(view) === key) return;
    opened.set(view, key);
    const sel = view.selected;
    if (sel && view.model.lineLink(sel.line) === linkOf(line)) return;  // selected already
    let waiting: (() => void) | null = null;  // the wait for a measurement's outcome
    const end = () => { waiting?.(); waiting = null; };
    const measured = (l: Line) => { end(); frames.get(view)?.current.onMeasured(l); };
    const row = openLink(view, line, (r) => showRow(view, r), measured);
    const model = view.model, noted = () => frames.get(view)?.current.onNote?.();
    if (row >= 0) return;
    if (model.note) { noted(); return; }  // hidden by the filters, or not in the run
    const measuring = model.measuredLink;
    if (!measuring) return;
    // a measurement under way: a failure is a note too (a success, or a selection, ends the wait)
    waiting = view.subscribe(() => {
      if (model.measuredLink === measuring) return;
      end();
      if (model.note) noted();
    });
    return end;
  }, [view, map, line, nav]);  // nav: Back or Forward to the same link opens it again
  useEffect(() => {
    if (!map) return;
    const model = view.model;
    // the hash's link and what it names (linkedLine reads every line; the view tells its listeners at every move)
    let known: {link: string; row: number; measurable: boolean | null} | null = null;
    const facts = (link: string) => {
      if (!known || known.link !== link) {
        const l = model.linkedLine(link);
        known = {link, row: l ? model.indexOf(l) : -1, measurable: null};
      }
      return known;
    };
    let last = view.selected?.row ?? -1;
    const write = () => {
      const sel = view.selected, row = sel ? sel.row : -1;
      if (row !== last) {
        last = row;
        if (sel) {  // a new selection ends a measured line
          model.measuredLink = null;
          latest.current.onMeasured(null);
        }
      }
      const want = sel ? model.lineLink(sel.line) : null, hashOf = latest.current.hashOf;
      const base = hashOf(model.runId, null), now = location.hash;
      // the hash is still this run's page (the app: #run=<id>…; a map has no other page)
      if (base && now !== base && !now.startsWith(base + "&")) return;
      const hash = hashOf(model.runId, want);
      if (now === hash) return;
      if (!want) {  // nothing selected: the link stays for a line hidden by the filters, and for a measured one
        const link = linkOf(now), f = link ? facts(link) : null;
        if (f && f.row >= 0 && !view.passes(f.row)) return;
        if (link && link === model.measuredLink) return;
        if (f && f.row < 0) {
          if (f.measurable === null) f.measurable = model.measurableLink(f.link);
          if (f.measurable) return;
        }
      }
      // no hash (a map's page without a line): the address without one; replaceState leaves the address as it is
      // for "" (today's map page keeps the line's hash so)
      history.replaceState(history.state, "", hash || location.pathname + location.search);
    };
    write();
    return view.subscribe(write);
  }, [view, map]);
}
