// The keys of a radio group, as WAI-ARIA's radio group (step 3d, the planner's decision: the arrows move the focus
// and choose): one Tab stop a group (the checked radio, else the first that can be pressed), → and ↓ the next radio,
// ← and ↑ the one before (round the group), Home the first, End the last; a disabled radio is passed over. One way for
// every group: the kit's Segmented (ui/components.tsx), the goal cards (search/BasicPane.tsx), the coverage page's
// scale (coverage/page/card.tsx) and the 3D view's switches (view3d/views.ts, imagery.ts), which are plain DOM: no
// Preact here. The search's tabs (search/SearchPanel.tsx) are WAI-ARIA's tabs: there the arrows move the focus only
// and Enter or Space chooses (going back to Basic may ask first).

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

/** A group's keydown, set on the group's element: an arrow, Home or End on one of its radios moves the focus to the
 *  radio it names and chooses that radio by its click (each group's own handler), the key's default (a scroll)
 *  prevented. */
export function radioKeys(e: KeyboardEvent): void {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const group = e.currentTarget as HTMLElement, from = (e.target as Element | null)?.closest?.("[role=radio]");
  if (!from || !group.contains(from)) return;
  const to = radioTarget([...group.querySelectorAll<HTMLElement>("[role=radio]")].filter(pressable), from, e.key);
  if (!to) return;
  e.preventDefault();
  if (to === from) return;
  to.focus();
  to.click();
}

/** Plain DOM: the Tab stop of `group`'s radios set after its checked radio (aria-checked) changed. */
export function markRadioStop(group: Element): void {
  const radios = [...group.querySelectorAll<HTMLElement>("[role=radio]")];
  const stop = radioStop(radios.length, radios.findIndex((r) => r.getAttribute("aria-checked") === "true"),
                         (i) => pressable(radios[i]));
  radios.forEach((r, i) => { r.tabIndex = i === stop ? 0 : -1; });
}
