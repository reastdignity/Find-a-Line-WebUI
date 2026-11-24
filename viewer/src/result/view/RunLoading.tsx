// What a run's result shows while it loads (result/load.ts loadRun, result/model.ts buildModel): the way back
// (the caller's), the phase in words and its bar (the share of the bytes while downloading, a moving bar while
// the amount is unknown), or the error: its sentence, "Try again" where a new try can help (the caller's
// `onRetry`: a store that could not be loaded, never one too large or of a newer format) and a second sentence
// (the caller's `more`: a share link's visitor has no way back). Styles in columns.css (.c-result-wait, .c-loading).

import type { ComponentChildren } from "preact";
import { useEffect, useRef } from "preact/hooks";
import { t } from "../../i18n";
import { Button, Progress } from "../../ui/components";
import type { LoadProgress } from "../load";

const mb = (bytes: number) => (bytes / 2 ** 20).toFixed(1);

/** The words of a phase of loading a run (null: not started). */
export function loadingText(p: LoadProgress | null): string {
  if (!p) return t("ui.result.loading_start");
  if (p.phase === "parse") return t("ui.result.loading_parse");
  if (p.phase === "groups") return t("ui.result.loading_groups");
  if (p.done === undefined) return t("ui.result.loading_start");  // a script: no bytes known
  return p.total ? t("ui.result.loading_download", {done: mb(p.done), total: mb(p.total)})
    : t("ui.result.loading_download_unknown", {done: mb(p.done)});
}

export function RunLoading({progress, error, onRetry, more, children}:
                           {progress: LoadProgress | null; error?: string; onRetry?: () => void; more?: string;
                            children?: ComponentChildren}) {
  // A new try that failed too puts the focus back on its button (it went with the button while the run loaded)
  const retried = useRef(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!error || !retried.current) return;
    retried.current = false;
    box.current?.querySelector<HTMLElement>(".c-retry")?.focus();
  }, [error]);
  return <div class="c-result-wait" ref={box}>
    {children}
    {error ? <>
      <p class="c-error" role="alert">{error}</p>
      {onRetry && <Button class="c-retry" onClick={() => { retried.current = true; onRetry(); }}>{t("ui.actions.try_again")}</Button>}
      {more && <p class="u-small c-wait-more">{more}</p>}
    </> : <div class="c-loading"><Progress value={progress?.fraction ?? null} label={loadingText(progress)} /></div>}
  </div>;
}
