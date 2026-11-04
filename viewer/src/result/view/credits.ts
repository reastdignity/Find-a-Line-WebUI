// The licences of a run's data in the map's attribution, as long as the run is shown (ResultColumns, in the
// app and a run's map.html): the credits with the link to the run's ATTRIBUTION.txt
// (layers.ts creditsHtml), on a phone folded behind a "Data credits" button (ui.css .u-credits), the
// state not kept. Leaflet draws the attribution again from its HTML: the button's state is in that HTML,
// and a click (caught on the control, which keeps it from the map) adds the other one.

import type L from "leaflet";
import { useEffect, useRef, useState } from "preact/hooks";
import { creditsHtml } from "../../layers";
import { t } from "../../i18n";
import type { RunData } from "../../types";
import { runFolder } from "./RunActions";

/** Puts the credits of `data` into the attribution of `map` (none yet: nothing) while it is shown; `base` and
 *  `folder` locate the run's files as RunActions' do. */
export function useRunCredits(map: L.Map | null | undefined, data: RunData, base?: string, folder?: string) {
  const [open, setOpen] = useState(false);
  const toggled = useRef(false);
  useEffect(() => {
    const credits = data.attribution || [], control = map?.attributionControl;
    if (!credits.length || !control) return;
    const html = creditsHtml(credits, runFolder(data.run.id, base, folder) + "ATTRIBUTION.txt",
                             {label: t("ui.credits.toggle"), open});
    control.addAttribution(html);
    const box = control.getContainer();
    if (toggled.current) box?.querySelector<HTMLElement>(".u-credits-toggle")?.focus();  // the new button
    toggled.current = false;
    const click = (e: Event) => {
      if (!(e.target as HTMLElement).closest?.(".u-credits-toggle")) return;
      toggled.current = true;
      setOpen(!open);
    };
    box?.addEventListener("click", click);
    return () => { box?.removeEventListener("click", click); control.removeAttribution(html); };
  }, [map, data, open]);
}
