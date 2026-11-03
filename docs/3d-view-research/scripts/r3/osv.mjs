// Ask OSV (api.osv.dev) for the advisories of npm packages; print id, aliases, date, summary, fixed versions.
const pkgs = process.argv.slice(2);
for (const name of pkgs) {
  const res = await fetch("https://api.osv.dev/v1/query", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ package: { name, ecosystem: "npm" } }),
  });
  const data = await res.json();
  const vulns = data.vulns || [];
  console.log(`== ${name}: ${vulns.length} advisories`);
  for (const v of vulns) {
    const fixed = [];
    for (const a of v.affected || []) for (const r of a.ranges || []) for (const e of r.events || []) {
      if (e.fixed) fixed.push(e.fixed);
      if (e.last_affected) fixed.push("last_affected " + e.last_affected);
    }
    console.log(`  ${v.id} [${(v.aliases || []).join(",")}] ${(v.published || "").slice(0, 10)} fixed:${fixed.join("|")} :: ${(v.summary || v.details || "").slice(0, 140).replace(/\s+/g, " ")}`);
  }
}
