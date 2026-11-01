// Bundle each entry as the viewer does (esbuild, IIFE, minify, es2020, no legal comments) against the
// packages installed (with --ignore-scripts) under downloads/r3/<lib>/node_modules; report min, gzip -5
// (nginx's gzip_comp_level of deploy/nginx/findaline.conf), gzip -9 and brotli, plus the biggest inputs.
// Usage: node bundle.mjs <esbuild main.js> <downloads/r3 dir> <entries dir> <out dir>
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { gzipSync, brotliCompressSync, constants } from "node:zlib";

const [esbuildMain, downloads, entries, out] = process.argv.slice(2);
const esbuild = await import(pathToFileURL(esbuildMain).href);
const JOBS = [
  ["cesium-widget", "cesium"], ["cesium-viewer", "cesium"], ["three-own", "three"],
  ["three-tiles", "three"], ["giro3d", "giro3d"], ["itowns", "itowns"],
];
const kb = (n) => (n / 1024).toFixed(0) + " KB";
for (const [name, lib] of JOBS) {
  for (const target of ["es2020", "es2022"]) {
    const outfile = join(out, `${name}.${target}.js`);
    try {
      const result = await esbuild.build({
        entryPoints: [join(entries, `${name}.js`)], bundle: true, minify: true, legalComments: "none",
        format: "iife", target, outfile, metafile: true, logLevel: "silent",
        nodePaths: [join(downloads, lib, "node_modules")],
        loader: { ".png": "file", ".svg": "file", ".gif": "file", ".jpg": "file", ".wasm": "file", ".glsl": "text" },
        define: { "process.env.NODE_ENV": '"production"' },
      });
      const code = readFileSync(outfile);
      const gz5 = gzipSync(code, { level: 5 }).length, gz9 = gzipSync(code, { level: 9 }).length;
      const br = brotliCompressSync(code, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }).length;
      const inputs = {};
      for (const [path, o] of Object.entries(result.metafile.outputs)) {
        if (!path.endsWith(".js")) continue;
        for (const [inp, v] of Object.entries(o.inputs)) {
          const m = inp.match(/node_modules[\\/]((@[^\\/]+[\\/])?[^\\/]+)/);
          const key = m ? m[1].replace("\\", "/") : inp;
          inputs[key] = (inputs[key] || 0) + v.bytesInOutput;
        }
      }
      const top = Object.entries(inputs).sort((a, b) => b[1] - a[1]).slice(0, 8)
        .map(([k, v]) => `${k} ${kb(v)}`).join(", ");
      const warnings = result.warnings.map((w) => w.text.slice(0, 90)).slice(0, 4).join(" | ");
      console.log(`${name} [${target}]: min ${kb(code.length)} gzip-5 ${kb(gz5)} gzip-9 ${kb(gz9)} brotli ${kb(br)}`);
      console.log(`   top: ${top}`);
      if (warnings) console.log(`   warnings: ${warnings}`);
      writeFileSync(join(out, `${name}.${target}.meta.json`), JSON.stringify(result.metafile));
      break;  // es2020 worked: no need for es2022
    } catch (e) {
      const errs = (e.errors || []).map((x) => `${x.text} (${x.location?.file}:${x.location?.line})`).slice(0, 3);
      console.log(`${name} [${target}]: FAILED ${errs.join(" | ") || e.message}`);
    }
  }
}
