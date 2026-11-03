// Summarise npm release timelines: releases (no prerelease) in the last 12 months, the latest five.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2];
const since = new Date("2025-11-01T00:00:00Z");
for (const f of readdirSync(dir).filter((n) => n.startsWith("time-") && n.endsWith(".json"))) {
  let t;
  try { t = JSON.parse(readFileSync(join(dir, f), "utf8")); } catch (e) { console.log(f, "unreadable"); continue; }
  const rel = Object.entries(t).filter(([v]) => /^\d+\.\d+\.\d+$/.test(v))
    .map(([v, d]) => [v, new Date(d)]).sort((a, b) => a[1] - b[1]);
  const year = rel.filter(([, d]) => d >= since);
  const last = rel.slice(-5).map(([v, d]) => `${v} ${d.toISOString().slice(0, 10)}`).join(", ");
  console.log(`${f}: ${year.length} releases since 2025-11-01; first ever ${rel[0]?.[1].toISOString().slice(0, 10)}; last: ${last}`);
}
