// The app (python findaline.py web): one of the interfaces of ui/choice.ts (?ui=b|c|d, D the default, or a
// demo of the kit), with the beta notice and Report a problem around it; the browser's time zone sent once
// per browser session on the public site (timeZone.ts).

import "../leaflet";
import { render } from "preact";
import "./base.css";
import "../ui/pages.css";
import { AppB } from "./b/AppB";
import { BetaNotice, ReportDialog } from "./ReportDialog";
import { AppC } from "./c/AppC";
import { AppD } from "./d/AppD";
import { Gallery, KitLayer } from "../ui/Gallery";
import { KitResult } from "../result/view/KitResult";
import { KitSearch } from "../search/KitSearch";
import { chooseUi } from "../ui/choice";
import { sendTimeZone } from "./timeZone";

const SHELLS = {b: AppB, c: AppC, d: AppD, kit: Gallery, "kit-result": KitResult, "kit-search": KitSearch, "kit-layer": KitLayer};
const choice = chooseUi(), Shell = SHELLS[choice];
// The beta notice after a sign-in and Report a problem (the public site), whichever interface is shown
const dialogs = ["b", "c", "d"].includes(choice) && <><BetaNotice /><ReportDialog /></>;
render(<><Shell />{dialogs}</>, document.getElementById("app")!);
if (dialogs) sendTimeZone();
