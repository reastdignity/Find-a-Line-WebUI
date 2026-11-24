// Builds dist/viewer.js and .css (the map of every run, map.html) and dist/app.js and .css
// (the web app of `findaline.py web`), dist/view3d.js and .css (the app's 3D view of a line, /view3d),
// dist/coverage.js and .css (the coverage map's page, /coverage);
// dist is committed: users need no Node.
// The logo's files go to dist/ as they are: logo.svg for web.py's server-rendered pages (the app bundles
// the same file as text), favicon.svg for every page of the app; the coverage map's outlines
// (src/coverage/shapes.json, tools/coverage_shapes.py) as coverage-shapes.json, fetched when a map needs them.
// Fonts go next to the bundles under their hashed names: dist stays one flat folder (runs/_viewer copies it).
// The licences of the bundled libraries go to dist/THIRD-PARTY-LICENSES.txt (MIT, BSD and Apache-2.0 ask for their
// notices with every copy), and every bundle starts with a comment pointing to it.
// `node build.mjs --out <dir>` builds elsewhere (tests compare it with dist/).
// `node build.mjs --media --out <dir>` builds only the page of the coverage animations and images
// (coverage-media.js and .css, for tools/coverage_media.py; never in dist: users do not need it).
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import * as esbuild from "esbuild";
import { getLicenseFileText } from "generate-license-file";

const at = process.argv.indexOf("--out");
const outdir = at > 0 ? process.argv[at + 1] : "dist";
const media = process.argv.includes("--media");
const LICENCES = "THIRD-PARTY-LICENSES.txt";
const notice = `/*! Licences of the bundled libraries: ${LICENCES} */`;
// The site on a phone's home screen ("Add to home screen"): the icons (src/ui/logo/*.png, the logo's mark drawn by
// tools/home_screen_icons.py), the iPhone's (every page's head links it: runs.HOME_SCREEN_HEAD) and the manifest,
// written here as JSON (one line ending on every system) with the page's light ground, --bg of src/ui/tokens.css, as
// its one colour (an Android phone's splash and task switcher).
const HOME_SCREEN_ICONS = [
  { src: "icon-192.png", sizes: "192x192", type: "image/png" },
  { src: "icon-512.png", sizes: "512x512", type: "image/png" },
  { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
];
const APPLE_TOUCH_ICON = "apple-touch-icon.png";

function homeScreenManifest() {
  const light = /^\.ui \{([\s\S]*?)^\}/m.exec(readFileSync("src/ui/tokens.css", "utf8"));
  const ground = light && /--bg:\s*(#[0-9a-f]{6});/.exec(light[1]);
  if (!ground) throw new Error("src/ui/tokens.css: no --bg in its first .ui block");
  return JSON.stringify({
    name: "Find-a-Line", short_name: "Find-a-Line", start_url: "/", display: "standalone", orientation: "portrait",
    background_color: ground[1], theme_color: ground[1], icons: HOME_SCREEN_ICONS,
  }, null, 2) + "\n";
}

const entryPoints = media
  ? { "coverage-media": "src/coverage/media/main.ts" }
  : { viewer: "src/map/main.tsx", app: "src/app/app.tsx", view3d: "src/view3d/main.ts",
      coverage: "src/coverage/page/main.tsx" };
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
  for (const name of ["logo.svg", "favicon.svg", ...HOME_SCREEN_ICONS.map((icon) => icon.src), APPLE_TOUCH_ICON]) {
    copyFileSync(`src/ui/logo/${name}`, `${outdir}/${name}`);
  }
  writeFileSync(`${outdir}/manifest.webmanifest`, homeScreenManifest());
}
// The runtime dependencies' licences; TypeScript (an optional peer of i18next) and the type-only packages are
// never bundled, and TypeScript's native package differs per platform, while dist must be the same on every OS.
// Code copied into src (no package of its own: @mapbox/martini in src/view3d) adds its notice from licences/.
writeFileSync(`${outdir}/${LICENCES}`, await getLicenseFileText("./package.json", {
  lineEnding: "lf", exclude: ["/^typescript@/", "/^@typescript\\//", "/^@types\\//"],
  append: ["licences/martini.txt"],
}));
