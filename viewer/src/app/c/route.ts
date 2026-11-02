// C's pages in the address's hash, so the server needs no routes and Back and Forward work:
// #home (the default), #new (#new&edit=<job>: edit & run again; #new&cell=<id>:<band>:<level>:<i>:<j>: a
// cell of the highline layer), #favourites (#favourites&folder=<id>: a folder of them), #account, #admin, #osm,
// #layer (#layer&country=<id>: the highline layer of a country) and
// #run=<id>&line=<lat1,lon1,lat2,lon2> (the line optional; the link LineDetails copies, appLink).

export type Route =
  | {page: "home"}
  | {page: "new"; edit: string | null; cell: string | null}
  | {page: "favourites"}
  | {page: "account"}
  | {page: "admin"}
  | {page: "osm"}
  | {page: "layer"; country: string | null}
  | {page: "run"; id: string; line: string | null};

const PLAIN = ["favourites", "account", "admin", "osm"] as const;

/** The page of a hash ("#run=…&line=…"); anything unknown is home. */
export function parseRoute(hash: string): Route {
  const text = hash.replace(/^#/, "");
  if (!text || text === "home") return {page: "home"};
  const params = new URLSearchParams(text);
  const run = params.get("run");
  if (run) return {page: "run", id: run, line: params.get("line") || null};
  if (params.has("new")) return {page: "new", edit: params.get("edit") || null, cell: params.get("cell") || null};
  if (params.has("layer")) return {page: "layer", country: params.get("country") || null};
  for (const page of PLAIN) if (params.has(page)) return {page};
  return {page: "home"};
}

/** The hash of a run's page, with a selected line (its coordinates, ResultModel.lineLink). */
export function runHash(id: string, line?: string | null): string {
  return `#run=${encodeURIComponent(id)}` + (line ? `&line=${encodeURIComponent(line)}` : "");
}

/** The favourites page with a folder chosen (null: the top level). */
export function favouritesHash(folder: number | null): string {
  return folder === null ? "#favourites" : `#favourites&folder=${folder}`;
}

/** The folder of a favourites hash; null: the top level (or none given). */
export function folderOfHash(hash: string): number | null {
  const value = new URLSearchParams(hash.replace(/^#/, "")).get("folder");
  return value && /^\d+$/.test(value) ? Number(value) : null;
}

/** The highline layer, of a country (null: the first). */
export function layerHash(country: string | null): string {
  return country ? `#layer&country=${encodeURIComponent(country)}` : "#layer";
}

/** A new search of a cell of the highline layer (#new&cell=<id>:<band>:<level>:<i>:<j>, api.countryRequest). */
export function cellHash(country: string, band: string, level: number, i: number, j: number): string {
  return `#new&cell=${[country, band, level, i, j].map((p) => encodeURIComponent(String(p))).join(":")}`;
}

/** The parts of a #new&cell= value; null when it is not one. */
export function parseCell(cell: string): {country: string; band: string; level: number; i: number; j: number} | null {
  const parts = cell.split(":");
  if (parts.length !== 5 || !parts[0] || !parts[1] || !parts.slice(2).every((p) => /^-?\d+$/.test(p))) return null;
  const [level, i, j] = parts.slice(2).map(Number);
  return {country: parts[0], band: parts[1], level, i, j};
}

export function editHash(job: string): string {
  return `#new&edit=${encodeURIComponent(job)}`;
}

/** Go to a page: a new history entry, or (`replace`) instead of the current one. */
export function go(hash: string, replace = false) {
  if (replace) location.replace(hash);
  else location.hash = hash;
}
