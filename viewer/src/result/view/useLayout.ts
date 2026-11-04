// The state of a result's layout (layout.ts) for one result on a desktop: the panels and the profile card
// share it. Read from localStorage once, kept there on a commit (a drag ended, a key, a click). A change and
// its commit can come before the next render (a Splitter's key calls onChange, then onCommit), so the layout
// of the last change is in a "latest" ref, which the callbacks build on instead of the rendered value.

import { useRef, useState } from "preact/hooks";
import { loadLayout, saveLayout, type Layout } from "./layout";

export interface LayoutState {
  /** The layout as drawn. */
  layout: Layout;
  /** The layout of the last change (drawn or not yet): what the next change builds on. */
  latest: {current: Layout};
  /** A new layout; `commit`: keep it now. */
  change(next: Layout, commit: boolean): void;
  /** Keep the layout of the last change (a drag ended). */
  commit(): void;
}

export function useLayout(): LayoutState {
  const [layout, setLayout] = useState(loadLayout);
  const latest = useRef(layout);
  latest.current = layout;
  const state = useRef<LayoutState | null>(null);
  if (!state.current) {
    state.current = {
      layout, latest,
      change(next, commit) {
        latest.current = next;
        setLayout(next);
        if (commit) saveLayout(next);
      },
      commit() { saveLayout(latest.current); },
    };
  }
  state.current.layout = layout;
  return state.current;
}
