// What a run's result shows while it loads (result/load.ts loadRun, result/model.ts buildModel): the way back
// (the caller's), the phase in words and its bar (the share of the bytes while downloading, a moving bar while
// the amount is unknown), or the error. Styles in columns.css (.c-result-wait, .c-loading).

import type { ComponentChildren } from "preact";
import { t } from "../../i18n";
import { Progress } from "../../ui/components";
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

export function RunLoading({progress, error, children}: {progress: LoadProgress | null; error?: string;
                                                          children?: ComponentChildren}) {
  return <div class="c-result-wait">
    {children}
    {error ? <p class="c-error">{error}</p>
      : <div class="c-loading"><Progress value={progress?.fraction ?? null} label={loadingText(progress)} /></div>}
  </div>;
}
