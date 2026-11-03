// Builds dist/viewer.js and .css (the map of every run, map.html) and dist/app.js and .css
// (the web app of `findaline.py web`), dist/coverage.js and .css (the coverage map's page, /coverage) and
// dist/index.css (runs/index.html); dist is committed: users need no Node.
// The logo's files go to dist/ as they are: logo.svg for web.py's server-rendered pages (the app bundles
// the same file as text), favicon.svg for every page of the app; the coverage map's outlines
// (src/coverage/shapes.json, tools/coverage_shapes.py) as coverage-shapes.json, fetched when a map needs them.
// Fonts go next to the bundles under their hashed names: dist stays one flat folder (runs/_viewer copies it).
// The licences of the bundled libraries go to dist/THIRD-PARTY-LICENSES.txt (MIT, BSD and Apache-2.0 ask for their
// notices with every copy), and every bundle starts with a comment pointing to it.
// `node build.mjs --out <dir>` builds elsewhere (tests compare it with dist/).
// `node build.mjs --media --out <dir>` builds only the page of the coverage animations and images
// (coverage-media.js and .css, for tools/coverage_media.py; never in dist: users do not need it).
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import * as esbuild from "esbuild";
import { getLicenseFileText } from "generate-license-file";

const at = process.argv.indexOf("--out");
const outdir = at > 0 ? process.argv[at + 1] : "dist";
const media = process.argv.includes("--media");
const LICENCES = "THIRD-PARTY-LICENSES.txt";
const notice = `/*! Licences of the bundled libraries: ${LICENCES} */`;

const entryPoints = media
  ? { "coverage-media": "src/coverage/media/main.ts" }
  : { viewer: "src/map/main.tsx", app: "src/app/app.tsx", coverage: "src/coverage/page/main.tsx", index: "src/index.css" };
await esbuild.build({
  entryPoints,
  bundle: true,
  minify: true,
  legalComments: "none",
  banner: { js: notice, css: notice },
  format: "iife",
  target: "es2020",
  outdir,
  assetNames: "[name]-[hash]",
  loader: { ".png": "dataurl", ".svg": "text", ".woff2": "file" },
  logLevel: "warning",
});
mkdirSync(outdir, { recursive: true });
copyFileSync("src/coverage/shapes.json", `${outdir}/coverage-shapes.json`);
if (!media) {
  for (const name of ["logo.svg", "favicon.svg"]) copyFileSync(`src/ui/logo/${name}`, `${outdir}/${name}`);
}
// The runtime dependencies' licences; TypeScript (an optional peer of i18next) and the type-only packages are
// never bundled, and TypeScript's native package differs per platform, while dist must be the same on every OS.
writeFileSync(`${outdir}/${LICENCES}`, await getLicenseFileText("./package.json", {
  lineEnding: "lf", exclude: ["/^typescript@/", "/^@typescript\\//", "/^@types\\//"],
}));
