// The keys of a radio group, as WAI-ARIA's radio group (step 3d, the planner's decision: the arrows move the focus
// and choose): one Tab stop a group (the checked radio, else the first that can be pressed), → and ↓ the next radio,
// ← and ↑ the one before (round the group), Home the first, End the last; a disabled radio is passed over. One way for
// every group: the kit's Segmented (ui/components.tsx), the coverage page's scale (coverage/page/card.tsx) and the 3D
// view's switches (view3d/views.ts, imagery.ts: plain DOM, which set the stop's tabIndex with the checked radio), so no
// Preact here. The search form's goal cards (search/BasicPane.tsx) take `radioFocusKeys`: the arrows move the focus
// only and Space or Enter chooses (the planner, 2026-11-21: a card applies up to 11 values, so reading the next card
// must not), as the search's tabs (search/SearchPanel.tsx, WAI-ARIA's tabs: going back to Basic may ask first).

const pressable = (radio: HTMLElement) => !(radio as HTMLButtonElement).disabled;

/** The index of a group's Tab stop among `count` radios: the checked one's (`checked`, -1 for none) unless it cannot
 *  be pressed, else the first that can; -1 when none can. */
export function radioStop(count: number, checked: number, enabled: (index: number) => boolean = () => true): number {
  if (checked >= 0 && checked < count && enabled(checked)) return checked;
  for (let i = 0; i < count; i++) if (enabled(i)) return i;
  return -1;
}

/** The radio `key` moves to from `from` among `radios` (those that can be pressed), or null for a key that is not
 *  the group's. */
export function radioTarget(radios: HTMLElement[], from: Element, key: string): HTMLElement | null {
  const n = radios.length, at = radios.indexOf(from as HTMLElement);
  if (!n) return null;
  if (key === "ArrowRight" || key === "ArrowDown") return radios[(at + 1) % n];
  if (key === "ArrowLeft" || key === "ArrowUp") return radios[at < 0 ? n - 1 : (at - 1 + n) % n];
  if (key === "Home") return radios[0];
  if (key === "End") return radios[n - 1];
  return null;
}

/** An arrow, Home or End on one of the group's radios (`e.currentTarget`): the radio it names gets the focus, and its
 *  click when `choose`; the key's default (a scroll) prevented. */
function step(e: KeyboardEvent, choose: boolean): void {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const group = e.currentTarget as HTMLElement, from = (e.target as Element | null)?.closest?.("[role=radio]");
  if (!from || !group.contains(from)) return;
  const to = radioTarget([...group.querySelectorAll<HTMLElement>("[role=radio]")].filter(pressable), from, e.key);
  if (!to) return;
  e.preventDefault();
  if (to === from) return;
  to.focus();
  if (choose) { to.click(); return; }
  // Focus only: the Tab stop follows the focus while it stays in the group (Tab then leaves the group from the
  // radio it is on), and goes back to the checked radio when the focus leaves it
  const radios = [...group.querySelectorAll<HTMLElement>("[role=radio]")];
  radios.forEach((r) => { r.tabIndex = r === to ? 0 : -1; });
  if (group.dataset.roving) return;
  group.dataset.roving = "1";
  const back = (out: FocusEvent) => {
    if (out.relatedTarget instanceof Node && group.contains(out.relatedTarget)) return;
    group.removeEventListener("focusout", back);
    delete group.dataset.roving;
    const all = [...group.querySelectorAll<HTMLElement>("[role=radio]")];
    const stop = radioStop(all.length, all.findIndex((r) => r.getAttribute("aria-checked") === "true"), (i) => pressable(all[i]));
    all.forEach((r, i) => { r.tabIndex = i === stop ? 0 : -1; });
  };
  group.addEventListener("focusout", back);
}

/** A group's keydown, set on the group's element: the arrows move the focus and choose (each group's own click). */
export function radioKeys(e: KeyboardEvent): void { step(e, true); }

/** A group's keydown where a choice costs more than a look (the goal cards): the arrows move the focus only; Space or
 *  Enter (the radio button's own click) chooses. One Tab stop: the checked radio's, moved with the focus while it is
 *  in the group. */
export function radioFocusKeys(e: KeyboardEvent): void { step(e, false); }
