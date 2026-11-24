// Renaming a run (line volume's round 7, step 2g; the public site, the run's owner: web.py POST /api/runs/<id>):
// the form (RenameForm: the field with the whole name selected, Save and Cancel, the line of a refusal), which
// Home's card shows in its panel and the result view in a box under its title (RunRename: an icon button after the
// name, on a desktop's header). The name shown afterwards is the server's answer (the name as stored), never what
// was typed; load.ts renamedRun gives it to the loaded run and has the list of runs read again.
// Styles in columns.css (.c-rename, .c-run-nameline).

import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError } from "../../app/api";
import { t } from "../../i18n";
import { Button, IconButton } from "../../ui/components";
import { renamedRun } from "../load";
import { Popover } from "./common";
import { useOwnRun } from "./RunActions";

/** A typed name as the server stores it where it takes it (runs.run_name: Unicode's composed form, each run of
 *  spaces one space, the ends trimmed). A character the server refuses (a tab, a line break, an invisible one)
 *  stays as typed: such a name differs from the stored one, so it can be sent and the server's refusal read. */
export function storedForm(typed: string): string {
  return typed.normalize("NFC").replace(/\p{Zs}+/gu, " ").replace(/^ | $/g, "");
}

/** Save is off for a name that would change nothing: empty, or the run's name as it is. */
export function nothingToSave(typed: string, name: string): boolean {
  const stored = storedForm(typed);
  return stored === "" || stored === name;
}

let forms = 0;  // ids of the forms' fields (the refusal's line describes its field)

export interface RenameFormProps {
  /** The run and its name now. */
  id: string;
  name: string;
  /** Saved: the name as the server stored it (the loaded run and the list of runs already follow: renamedRun).
   *  Called also for a form no longer drawn (its holder showed something else while the request waited). */
  onRenamed(name: string): void;
  /** Cancel. */
  onClose(): void;
  /** While the request waits (true) nothing closes the form: its holder keeps it open. */
  onWaiting?(waiting: boolean): void;
  /** A line of a failure was drawn: the holder brings it into view. */
  onLine?(): void;
}

/** The form of a rename: no visible label (the field is named for a screen reader), the whole name selected when
 *  it opens, Enter saves; Save is off while the field is empty or unchanged. While the request waits the field
 *  cannot be changed and both buttons are off (a sent rename cannot be taken back), and Esc does nothing. A
 *  refusal's line stands under the buttons, the typed name stays and the focus is back in the field: the server's
 *  words for a refused name (400, error.run_name), "in use" for 409, and for any other failure the request's
 *  error text, as the card's other panels show one. */
export function RenameForm({id, name, onRenamed, onClose, onWaiting, onLine}: RenameFormProps) {
  const [value, setValue] = useState(name);
  const [wait, setWait] = useState(false);
  const [error, setError] = useState("");
  const field = useRef<HTMLInputElement>(null);
  const fieldId = useRef("c-rename-" + (++forms)).current;
  const live = useRef(true);
  useEffect(() => {
    field.current?.focus({preventScroll: true});
    field.current?.select();
    return () => { live.current = false; };
  }, []);
  // a refusal: the focus back in the field, the caret after what was typed; the line brought into view
  useEffect(() => {
    if (!error) return;
    const input = field.current;
    if (input) {
      input.focus({preventScroll: true});
      input.setSelectionRange(input.value.length, input.value.length);
    }
    onLine?.();
  }, [error]);
  const waiting = (now: boolean) => { setWait(now); onWaiting?.(now); };
  const off = wait || nothingToSave(value, name);
  const save = (e: Event) => {
    e.preventDefault();
    if (off) return;
    waiting(true);
    setError("");
    field.current?.focus({preventScroll: true});  // the pressed button goes off: the focus stays in the form
    api.renameRun(id, value).then((answer) => {
      renamedRun(id, answer.name);
      if (live.current) waiting(false);
      onRenamed(answer.name);  // also when the form is no longer drawn: the run has its new name
    }, (e) => {
      if (!live.current) return;
      waiting(false);
      setError(e instanceof ApiError && e.status === 409 ? t("ui.rename.in_use") : e.message);
    });
  };
  const keys = (e: KeyboardEvent) => {
    if (e.key === "Escape" && wait) { e.preventDefault(); e.stopPropagation(); }
  };
  return <form class="c-rename" noValidate onSubmit={save} onKeyDown={keys}>
    <input class="u-input c-panel-first" ref={field} id={fieldId} aria-label={t("ui.rename.name")} value={value}
           readOnly={wait} aria-invalid={error ? true : undefined} aria-describedby={error ? fieldId + "-error" : undefined}
           autocomplete="off" spellcheck={false}
           onInput={(e) => { setValue(e.currentTarget.value); setError(""); }} />
    <div class="u-row">
      <Button kind="primary" type="submit" disabled={off} aria-busy={wait ? true : undefined}>
        {wait && <span class="r-spin r-spin-ic" />}{t("ui.common.save")}</Button>
      <Button kind="ghost" disabled={wait} onClick={onClose}>{t("ui.common.cancel")}</Button>
    </div>
    {error && <p class="c-error u-small" role="alert" id={fieldId + "-error"}>{error}</p>}
  </form>;
}

/** The result view's Rename (a desktop's header, after the run's name): an icon button that opens the form in a
 *  box under the title, for a run the user may rename: their own on the public site, learned as Share learns it
 *  (useOwnRun: nothing in the local app, on a run's map.html, or for another user's run an administrator opens).
 *  `onRenamed`: the head draws the name again. A press outside or Esc closes the box, but not while the request
 *  waits. */
export function RunRename({id, name, onRenamed}: {id: string; name: string; onRenamed(name: string): void}) {
  const [own] = useOwnRun(id);
  const [open, setOpen] = useState(false);
  const waiting = useRef(false);
  if (!own) return null;
  return <Popover label={t("ui.rename.title")} open={open} onOpen={(now) => { if (now || !waiting.current) setOpen(now); }}
                  button={(on, toggle) => <IconButton icon="edit" label={t("ui.rename.title")} plain expanded={on}
                                                      class="c-rename-btn" onClick={toggle} />}>
    <RenameForm id={id} name={name} onWaiting={(now) => { waiting.current = now; }}
                onRenamed={(stored) => { setOpen(false); onRenamed(stored); }} onClose={() => setOpen(false)} />
  </Popover>;
}
