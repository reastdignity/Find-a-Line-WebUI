// C's focused new search (c2): the form (SearchPanel) in a column, the map on the right and the size word,
// the receipt and "Start search" in a bar at the bottom. Every new search opens Basic with "The best lines
// here" and the rig in use; "Edit & run again" (#new&edit=<job>) starts with the job's request, "Search a cell"
// (#new&cell=<id>:<band>:<level>:<i>:<j>, from the highline layer) with the cell's (api.countryRequest; the form
// adds its access mark, on: basic.ts cellValues): Basic when the request fits a goal and the rig in use, else
// Advanced (useSearch openingTab), so the form waits for the saved rigs. On phones the map is on top, the form scrolls under it and the compact bar stays at the bottom.

import { useEffect, useRef, useState } from "preact/hooks";
import { Button } from "../../ui/components";
import { EstimateBar, SearchPanel, useRigs, useSearch, type RigsState, type UsageState } from "../../search";
import { api, type Schema, type SearchRequest } from "../api";
import { PlaceMap } from "../PlaceMap";
import { layerHash, parseCell } from "./route";

/** The form and the bar, once the map, the schema, the saved rigs and the request to edit are there. */
function Form({place, schema, rigs, initial, cell, usage, wide, onStarted}:
              {place: PlaceMap; schema: Schema; rigs: RigsState; initial: SearchRequest | null; cell: boolean;
               usage: UsageState; wide: boolean; onStarted(id: string): void}) {
  const search = useSearch({place, schema, rigs, onStarted, initial, cell});
  (window as any).FINDALINE_SEARCH = search;  // for tests and the browser console
  return <>
    <aside class="c-form" aria-label="New search">
      <SearchPanel search={search} usage={usage.usage} phone={!wide} />
    </aside>
    <footer class="c-bar"><EstimateBar search={search} usage={usage.usage} phone={!wide} /></footer>
  </>;
}

export function NewSearch({edit, cell = null, schema, usage, wide, onStarted}:
                          {edit: string | null; cell?: string | null; schema: Schema | null; usage: UsageState; wide: boolean;
                           onStarted(id: string): void}) {
  const mapRef = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<PlaceMap | null>(null);
  const [initial, setInitial] = useState<SearchRequest | null | undefined>(edit || cell ? undefined : null);
  const rigs = useRigs();
  const ofCell = cell ? parseCell(cell) : null;
  const [error, setError] = useState("");

  useEffect(() => {
    const placeMap = new PlaceMap(mapRef.current!, {controls: "bottomright"});
    (window as any).FINDALINE_PLACE = placeMap;  // for tests and the browser console
    setPlace(placeMap);
    const observer = new ResizeObserver(() => placeMap.map.invalidateSize());
    observer.observe(mapRef.current!);
    return () => { observer.disconnect(); placeMap.map.remove(); };
  }, []);
  useEffect(() => {
    if (edit) api.job(edit).then((job) => setInitial(job.request), (e) => setError(e.message));
    else if (cell && !ofCell) setError("This is not a cell of the highline layer.");
    else if (ofCell) {
      api.countryRequest(ofCell.country, ofCell.band, ofCell.level, ofCell.i, ofCell.j)
        .then(setInitial, (e) => setError(e.message));
    }
  }, [edit, cell]);

  return <div class="c-newsearch">
    <div class="c-subtop">
      {ofCell ? <Button kind="ghost" icon="back" href={layerHash(ofCell.country)}>Layer</Button>
        : <Button kind="ghost" icon="back" href="#home">Home</Button>}
      <h1 class="c-subtitle">{edit ? "Edit & run again" : cell ? "Search a cell" : "New search"}</h1>
    </div>
    <div class="c-newmap" ref={mapRef} />
    {error && <p class="c-error c-form">{error}</p>}
    {!error && place && schema && initial !== undefined && rigs.loaded &&
      <Form key={edit || cell || "new"} place={place} schema={schema} rigs={rigs} initial={initial} cell={!!ofCell} usage={usage}
            wide={wide} onStarted={onStarted} />}
  </div>;
}
