// The app (python findaline.py web): the interface (AppC) or a demo of the kit (ui/choice.ts), with the
// beta notice and Report a problem around the interface; the browser's time zone sent once per browser
// session on the public site (timeZone.ts).

import "../leaflet";
import { render } from "preact";
import "./base.css";
import "../ui/pages.css";
import { BetaNotice, ReportDialog } from "./ReportDialog";
import { AppC } from "./c/AppC";
import { Gallery, KitLayer } from "../ui/Gallery";
import { KitResult } from "../result/view/KitResult";
import { KitSearch } from "../search/KitSearch";
import { chooseUi } from "../ui/choice";
import { sendTimeZone } from "./timeZone";

const SHELLS = {c: AppC, kit: Gallery, "kit-result": KitResult, "kit-search": KitSearch, "kit-layer": KitLayer};
const choice = chooseUi(), Shell = SHELLS[choice];
// The beta notice after a sign-in and Report a problem (the public site), with the interface, not the kit's demos
const dialogs = choice === "c" && <><BetaNotice /><ReportDialog /></>;
render(<><Shell />{dialogs}</>, document.getElementById("app")!);
if (dialogs) sendTimeZone();
