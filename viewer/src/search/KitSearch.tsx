// ?ui=kit-search: the search panel (search/) on its own, to develop and test its pieces without the
// interface: the form in a column left of the map and the estimate in a bottom bar (as NewSearch), the
// usage meters and the user's searches with their progress (useJobs, jobProgress) over the map; below
// 768 px the map on top, the form with the searches scrolling under it, the bar at the bottom.
// ?theme=light|dark picks the theme.

import { useEffect, useRef, useState } from "preact/hooks";
import { api, jobError, type Schema } from "../app/api";
import { PlaceMap } from "../app/PlaceMap";
import { jobProgress, useJobs, type JobsState, type JobView } from "../app/useJobs";
import { storedTheme } from "../ui/choice";
import { DESKTOP, Panel, Progress, Screen, StatusChip, useMedia, type Theme } from "../ui/components";
import { EstimateBar, SearchPanel, UsageMeters } from "./SearchPanel";
import { useSearch, useUsage, type UsageState } from "./useSearch";

function JobCard({job}: {job: JobView}) {
  const p = jobProgress(job);
  return <div class="s-job" data-job={job.id} data-status={job.status}>
    <div class="s-job-head"><StatusChip status={p.state}>{p.label}</StatusChip><b>{job.title}</b></div>
    {!p.finished && <Progress value={p.fraction} label={p.step || undefined} />}
    {job.error && <div class="s-job-error">{jobError(job)}</div>}
  </div>;
}

function Searches({jobs, usage}: {jobs: JobsState; usage: UsageState}) {
  return <div class="s-searches">
    <UsageMeters usage={usage.usage} />
    {!jobs.worker && <p class="s-hint">The worker is not running: searches wait until it starts.</p>}
    {jobs.error && <p class="s-problem">{jobs.error}</p>}
    <div class="s-jobs">
      {jobs.jobs.length ? jobs.jobs.slice(0, 8).map((j) => <JobCard key={j.id} job={j} />)
        : <p class="s-hint">No searches yet.</p>}
    </div>
  </div>;
}

/** Everything around the map, once the map and the schema are there. The grid of .s-kit places the
 *  form's column (s-c-form), the overlay of the map (s-kit-over, desktops) and the bar (s-c-bar). */
function Demo({place, schema}: {place: PlaceMap; schema: Schema}) {
  const wide = useMedia(DESKTOP);
  const jobs = useJobs();
  const usage = useUsage();
  const [started, setStarted] = useState("");
  const search = useSearch({place, schema, onStarted: (id) => {
    setStarted(id);
    jobs.refresh();
    usage.refresh();
  }});
  (window as any).FINDALINE_SEARCH = search;  // for tests and the browser console
  useEffect(() => { usage.refresh(); }, [jobs.active]);

  const startedNote = started && <p class="s-hint s-started" data-started={started}>Queued: {started}</p>;
  return <>
    <aside class="s-c-form" aria-label="New search">
      <SearchPanel search={search} usage={usage.usage} phone={!wide} />
      {startedNote}
      {!wide && <section class="s-form-jobs"><h2 class="u-h">Your searches</h2><Searches jobs={jobs} usage={usage} /></section>}
    </aside>
    {wide && <div class="s-kit-over">
      <aside class="s-kit-jobs"><Panel title="Your searches"><Searches jobs={jobs} usage={usage} /></Panel></aside>
    </div>}
    <footer class="s-c-bar"><EstimateBar search={search} usage={usage.usage} /></footer>
  </>;
}

export function KitSearch() {
  const params = new URLSearchParams(location.search);
  const asked = params.get("theme");
  const theme: Theme = asked === "light" || asked === "dark" ? asked : storedTheme();
  const wide = useMedia(DESKTOP);
  const mapRef = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<PlaceMap | null>(null);
  const [schema, setSchema] = useState<Schema | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const placeMap = new PlaceMap(mapRef.current!, {controls: "bottomright"});
    (window as any).FINDALINE_PLACE = placeMap;  // for tests and the browser console
    setPlace(placeMap);
    api.schema().then(setSchema, (e) => setError(e.message));
    const observer = new ResizeObserver(() => placeMap.map.invalidateSize());
    observer.observe(mapRef.current!);
    return () => { observer.disconnect(); placeMap.map.remove(); };
  }, []);

  return <Screen theme={theme} class={`s-kit${wide ? "" : " s-narrow"}`}>
    <div class="s-kit-map" ref={mapRef} />
    {error && <p class="s-problem s-kit-error">{error}</p>}
    {place && schema && <Demo place={place} schema={schema} />}
  </Screen>;
}
