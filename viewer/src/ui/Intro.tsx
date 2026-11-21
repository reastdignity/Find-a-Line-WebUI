// An introduction that opens once: a native <dialog> (showModal: Esc, the focus kept in it, the page
// behind inert) with a title, its text, "Do not show again" (checked at first) and "Got it". The
// browser remembers it in localStorage ("findaline.intro.<name>"); where the storage is blocked it
// opens once per page load. A link (IntroLink) opens it again. An intro that does not open by itself
// (`useIntro(name, false)`: the search's, the user's answer of 2026-11-21, so a first search reads fewer
// words) opens from its link only, without "Do not show again". Closed (Got it, Esc, Enter, a tap) it
// gives the focus back to what had it when it opened, or, where that is gone or was the page itself (a
// phone's tap focuses no button; an intro that opened by itself), to its own link (IntroLink). Styles in
// app/notices.css (n-intro*), the dialogs' look of the kit.

import type { ComponentChildren, RefObject } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { t } from "../i18n";
import { Button } from "./components";
import "../app/notices.css";

const shown = new Set<string>();  // opened in this page load (also when the storage is blocked)

export const introKey = (name: string) => `findaline.intro.${name}`;

/** Whether the intro `name` was put away ("Do not show again") in this browser or opened in this page load. */
export function introSeen(name: string): boolean {
  if (shown.has(name)) return true;
  try {
    return localStorage.getItem(introKey(name)) !== null;
  } catch {
    return false;
  }
}

function remember(name: string, again: boolean) {
  shown.add(name);
  try {
    if (again) localStorage.removeItem(introKey(name)); else localStorage.setItem(introKey(name), "seen");
  } catch { /* blocked storage: once per page load */ }
}

export interface IntroState {
  open: boolean;
  auto: boolean;  // opens by itself once (else from its link only)
  show(): void;
  close(dontShow: boolean): void;
  opener: RefObject<Element | null>;  // what had the focus when it opened
  link: RefObject<HTMLButtonElement | null>;  // its IntroLink: where the focus goes when the opener is gone
}

/** The state of the intro `name`: open at first when it was not seen (`auto`), else closed until its link. */
export function useIntro(name: string, auto = true): IntroState {
  const [open, setOpen] = useState(false);
  const opener = useRef<Element>(null), link = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!auto || introSeen(name)) return;
    shown.add(name);
    opener.current = document.activeElement;
    setOpen(true);
  }, []);
  return {open, auto, opener, link, show: () => { opener.current = document.activeElement; setOpen(true); },
          close: (dontShow) => { if (auto) remember(name, !dontShow); setOpen(false); }};
}

/** The focus back where it was when the intro opened, else on the intro's link (a page or an opener gone). */
function focusBack(state: IntroState) {
  const usable = (e: Element | null): e is HTMLElement =>
    e instanceof HTMLElement && e.isConnected && e !== document.body && !e.closest("dialog");
  const back = [state.opener.current, state.link.current].find(usable);
  back?.focus({preventScroll: true});
}

let ids = 0;

/** The dialog of an intro (`state` from useIntro). */
export function Intro({state, title, children, class: cls}:
                      {state: IntroState; title: string; children: ComponentChildren; class?: string}) {
  const ref = useRef<HTMLDialogElement>(null);
  const check = useRef<HTMLInputElement>(null);
  const [id] = useState(() => `n-intro-${++ids}`);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (state.open && !dialog.open) {
      // its own .ui root: the theme of the shell around it (data-theme), else the system's
      const theme = dialog.parentElement?.closest(".ui[data-theme]")?.getAttribute("data-theme");
      if (theme) dialog.setAttribute("data-theme", theme); else dialog.removeAttribute("data-theme");
      if (check.current) check.current.checked = true;
      dialog.showModal();
      dialog.scrollTop = 0;
    } else if (!state.open && dialog.open) dialog.close();
  }, [state.open]);
  if (!state.open) return null;
  // closed first (the page behind no longer inert), then the state and the focus back
  const done = () => {
    const dontShow = check.current?.checked ?? true;
    if (ref.current?.open) ref.current.close();
    state.close(dontShow);
    focusBack(state);
  };
  return <dialog ref={ref} class={"ui u-dialog n-intro" + (cls ? " " + cls : "")} aria-labelledby={id}
                 onCancel={(e) => { e.preventDefault(); done(); }}>
    <h2 class="u-h" id={id}>{title}</h2>
    <div class="n-intro-body">{children}</div>
    <div class="n-actions n-intro-foot">
      {state.auto && <label class="n-again"><input type="checkbox" ref={check} defaultChecked />{t("intro.dont_show")}</label>}
      <Button kind="primary" onClick={done}>{t("intro.got_it")}</Button>
    </div>
  </dialog>;
}

/** A text of the catalogue with <b>…</b> in bold and <i>…</i> in italics (the only markup it may hold;
 *  no innerHTML). */
export function Rich({text}: {text: string}) {
  const parts = text.split(/<(b|i)>(.*?)<\/\1>/);  // text, tag, inner, text, ...
  const out = [];
  for (let i = 0; i < parts.length; i += 3) {
    if (parts[i]) out.push(parts[i]);
    if (i + 2 < parts.length) out.push(parts[i + 1] === "b" ? <b key={i}>{parts[i + 2]}</b> : <i key={i}>{parts[i + 2]}</i>);
  }
  return <>{out}</>;
}

/** A link that opens the intro again. */
export function IntroLink({state, children, class: cls}:
                          {state: IntroState; children: ComponentChildren; class?: string}) {
  return <button type="button" ref={state.link} class={"n-intro-link" + (cls ? " " + cls : "")}
                 onClick={state.show}>{children}</button>;
}
