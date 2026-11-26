// The browser's own bars in the ground of the theme the page shows: a phone browser's toolbar and an installed app's
// status bar ("its own strip in the page's ground", the user's answer 21 to round 7's mock-up). Every page's head names
// the two grounds (runs.HOME_SCREEN_HEAD: a `<meta name="theme-color">` with the light ground under
// "(prefers-color-scheme: light)" and one with the dark ground under "dark", tokens.css's --bg), and the browser takes
// the one of the system's theme. A page that shows the theme chosen in the app (Screen: the app, the kit's pages, a
// run's map.html; the coverage map; the disk notice) calls themeBars with the theme it shows: a chosen theme puts its
// ground into both lines, "auto" gives each line its own value back, so a change of the system's theme still works
// without a script. The two lines keep their media. An iPhone's installed app reads them only when it starts: a theme
// chosen there colours its status bar from the app's next start (tried 2026-11-26; docs/known-bugs.md, round 7).
//
// The grounds are the head's own two values, remembered at the first call that finds both lines (no copy of the
// tokens here, and nothing that waits for the CSS or the page's root). A page whose head has not exactly those two
// lines (a map.html saved before round 7, a page of another kind) is left as it is.

type Scheme = "light" | "dark";
type Grounds = {lines: Record<Scheme, HTMLMetaElement>; values: Record<Scheme, string>};

const SCHEME = /^\(prefers-color-scheme:\s*(light|dark)\)$/;
let grounds: Grounds | null = null;

/** The head's two theme-color lines with their values as the head gave them, or null when it has not exactly two,
 *  one for each scheme. */
function headGrounds(): Grounds | null {
  if (typeof document === "undefined") return null;
  const metas = Array.from(document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]'));
  const found: Partial<Record<Scheme, HTMLMetaElement>> = {};
  for (const meta of metas) {
    // the attribute, not the property: a browser that does not reflect a meta's media must not throw here
    const scheme = SCHEME.exec((meta.getAttribute("media") || "").trim())?.[1] as Scheme | undefined;
    if (scheme) found[scheme] = meta;
  }
  const {light, dark} = found;
  if (metas.length !== 2 || !light || !dark) return null;
  return {lines: {light, dark}, values: {light: light.content, dark: dark.content}};
}

/** The bars in the ground of `theme`, the theme the page shows ("auto": the system's, as the head says it). */
export function themeBars(theme: "auto" | "light" | "dark"): void {
  if (!grounds) grounds = headGrounds();
  if (!grounds) return;
  for (const scheme of ["light", "dark"] as const) {
    const value = grounds.values[theme === "auto" ? scheme : theme], line = grounds.lines[scheme];
    if (line.content !== value) line.content = value;
  }
}
