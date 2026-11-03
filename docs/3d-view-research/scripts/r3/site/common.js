// Shared by the test pages: records CSP violations, errors and the bytes of every resource, and
// writes them into <pre id="out"> when window.finish(extra) is called (or after 40 s).
window.REPORT = { violations: [], errors: [], notes: [] };
document.addEventListener("securitypolicyviolation", (e) => REPORT.violations.push(
  `${e.effectiveDirective} blocked=${e.blockedURI} src=${(e.sourceFile || "").split("/").pop()}:${e.lineNumber} ${(e.sample || "").slice(0, 60)}`));
window.addEventListener("error", (e) => REPORT.errors.push("error: " + (e.message || e)));
window.addEventListener("unhandledrejection", (e) => REPORT.errors.push("rejection: " + (e.reason && (e.reason.message || e.reason))));
window.finish = function (extra) {
  if (window.FINISHED) return;
  window.FINISHED = true;
  const groups = {};
  for (const r of performance.getEntriesByType("resource")) {
    const path = new URL(r.name, location.href).pathname;
    const key = path.split("/").slice(0, 3).join("/");
    const g = groups[key] || (groups[key] = { n: 0, bytes: 0 });
    g.n += 1;
    g.bytes += r.encodedBodySize || r.transferSize || 0;
  }
  const lines = [
    ...REPORT.notes, ...(extra || []),
    `violations (${REPORT.violations.length}):`, ...[...new Set(REPORT.violations)].slice(0, 25).map((v) => "  " + v),
    `errors (${REPORT.errors.length}):`, ...[...new Set(REPORT.errors)].slice(0, 15).map((v) => "  " + v),
    "resources:", ...Object.entries(groups).sort((a, b) => b[1].bytes - a[1].bytes)
      .map(([k, g]) => `  ${k}: ${g.n} files, ${(g.bytes / 1024).toFixed(0)} KB`),
    "files of the library folders:", ...performance.getEntriesByType("resource")
      .filter((r) => /\/(cesium|lib)\//.test(new URL(r.name).pathname))
      .map((r) => `  ${new URL(r.name).pathname} ${(r.encodedBodySize / 1024).toFixed(0)} KB`),
    `JS heap used ${performance.memory ? (performance.memory.usedJSHeapSize / 1e6).toFixed(0) + " MB" : "n/a"}`,
  ];
  document.getElementById("out").textContent = lines.join("\n");
};
setTimeout(() => window.finish(["(finished by the 30 s timer)"]), 30000);
