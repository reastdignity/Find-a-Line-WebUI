// The coverage map's page, /coverage (web.py: a shell with <div id="coverage">, coverage.css and
// coverage.js). The outlines are fetched from next to this bundle (/app/coverage-shapes.json), found
// through the script's own address; data-site="public" on the element shows the public site's links.
import { render } from "preact";
import { SHAPES_FILE } from "../data";
import { CoveragePage } from "./CoveragePage";
import "./page.css";

const script = document.currentScript as HTMLScriptElement | null;
const shapesUrl = script?.src ? new URL(SHAPES_FILE, script.src).href : SHAPES_FILE;
const root = document.getElementById("coverage");
if (root) render(<CoveragePage shapesUrl={shapesUrl} site={root.dataset.site === "public" ? "public" : "local"} />, root);
