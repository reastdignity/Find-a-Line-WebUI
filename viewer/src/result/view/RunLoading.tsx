// What a run's result shows while it loads (result/load.ts loadRun, result/model.ts buildModel): the way back
// (the caller's), the phase in words and its bar (the share of the bytes while downloading, a moving bar while
// the amount is unknown), or the error: its sentence, "Try again" where a new try can help (the caller's
// `onRetry`: a store that could not be loaded, never one too large or of a newer format) and a second sentence
// (the caller's `more`: a share link's visitor has no way back). Styles in columns.css (.c-result-wait, .c-loading).

import type { ComponentChildren } from "preact";
import { useEffect, useRef } from "preact/hooks";
import { t } from "../../i18n";
import { Button, Progress } from "../../ui/components";
import { downloadSizes } from "../../size";
import type { LoadProgress } from "../load";

/** The words of a phase of loading a run (null: not started). While downloading: the bytes got and the total in the
 *  total's unit and cut as Home's card cuts the run's size (size.ts: a MB is 10^6 bytes), so the line ends at the
 *  card's number, but for a total under 0.05 MB (the card's "under 0.1 MB"): both in MB with two decimals; a total
 *  not known (or 0): the bytes got with their own unit. */
export function loadingText(p: LoadProgress | null): string {
  if (!p) return t("ui.result.loading_start");
  if (p.phase === "parse") return t("ui.result.loading_parse");
  if (p.phase === "groups") return t("ui.result.loading_groups");
  if (p.done === undefined) return t("ui.result.loading_start");  // a script: no bytes known
  const sizes = downloadSizes(p.done, p.total || null);
  return p.total ? t("ui.result.loading_download", {done: sizes.done, total: sizes.total, unit: sizes.unit})
    : t("ui.result.loading_download_unknown", {done: sizes.done, unit: sizes.unit});
}

/** `main`: the box is the page's main part (a run's map.html, which has no other landmark: its text would stand
 *  outside every region; the app's page has its own `main` around it). */
export function RunLoading({progress, error, onRetry, more, main, children}:
                           {progress: LoadProgress | null; error?: string; onRetry?: () => void; more?: string;
                            main?: boolean; children?: ComponentChildren}) {
  // A new try that failed too puts the focus back on its button (it went with the button while the run loaded)
  const retried = useRef(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!error || !retried.current) return;
    retried.current = false;
    box.current?.querySelector<HTMLElement>(".c-retry")?.focus();
  }, [error]);
  return <div class="c-result-wait" ref={box} role={main ? "main" : undefined}>
    {children}
    {error ? <>
      <p class="c-error" role="alert">{error}</p>
      {onRetry && <Button class="c-retry" onClick={() => { retried.current = true; onRetry(); }}>{t("ui.actions.try_again")}</Button>}
      {more && <p class="u-small c-wait-more">{more}</p>}
    </> : <div class="c-loading"><Progress value={progress?.fraction ?? null} label={loadingText(progress)} /></div>}
  </div>;
}
