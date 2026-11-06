// C's result (c3) in the app: the shared result in columns (result/view/ResultColumns, also a run's
// map.html) with "‹ Home", Edit & run again, the app's orthophoto cache and the line's 3D view. The
// selected line is kept in the hash (#run=<id>&line=…, replaced, so Back leaves the result); a hash with
// another line (Back, Forward, a copied link) opens that line. A copied link has no ?ui=.

import { Button } from "../../ui/components";
import { Icon } from "../../ui/icons";
import { hrefWithoutUi } from "../../ui/choice";
import type { Line } from "../../types";
import type { ResultModel } from "../../result/model";
import { orthoForApp } from "../../result/load";
import { ResultColumns } from "../../result/view/ResultColumns";
import { OTHERS_MAX, alsoParam } from "../../view3d/page";
import { editHash, go, runHash } from "./route";

/** The link "Copy link" gives: this page with the line's hash, without ?ui=. */
const linkOf = (model: ResultModel, l: Line) => location.origin + hrefWithoutUi() + runHash(model.runOf(l), model.lineLink(l));
/** The line's 3D view (web.py /view3d), with the hash of the run's page and, for a spot of several lines, the
 *  others of the spot in the model's order (`&also=`, at most OTHERS_MAX: the 3D view draws them besides the line);
 *  a line alone in its spot gets the link it always had. */
export const view3dOf = (model: ResultModel, l: Line) =>
  "/view3d" + runHash(model.runOf(l), model.lineLink(l)) +
  alsoParam(model.alsoOf(l, OTHERS_MAX).map((m) => model.lineLink(m)));
const back = {label: "Home", onClick: () => go("#home")};

/** What the result page gets: the run, the route's line (`nav` changes with every navigation), the job to
 *  edit and run again (none for a run without one), the layout. */
export interface ResultPageProps { id: string; line: string | null; nav: number; editJob: string | null; wide: boolean }

export function ResultPage({id, line, nav = 0, editJob, wide}: Omit<ResultPageProps, "nav"> & {nav?: number}) {
  const actions = (compact: boolean) => editJob && (compact
    ? <a class="u-ib u-plain u-round" href={editHash(editJob)} aria-label="Edit & run again" title="Edit & run again">
        <Icon name="edit" /></a>
    : <Button icon="edit" href={editHash(editJob)}>Edit &amp; run again</Button>);
  return <ResultColumns runId={id} line={line} nav={nav} wide={wide} back={back} hashOf={runHash} linkOf={linkOf}
                        view3dOf={view3dOf} actions={actions} ortho={(data) => orthoForApp(data.ortho, data.run.id)} />;
}
