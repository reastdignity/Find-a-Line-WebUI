// The browser's own bars in the ground of the theme the page shows: a phone browser's toolbar and an installed app's
// status bar ("its own strip in the page's ground", the user's answer 21 to round 7's mock-up). Every page's head names
// the two grounds (runs.HOME_SCREEN_HEAD: a `<meta name="theme-color">` with the light ground under
// "(prefers-color-scheme: light)" and one with the dark ground under "dark", tokens.css's --bg), and the browser takes
// the one of the system's theme. A page that shows the theme chosen in the app (Screen: the app, the kit's pages, a
// run's map.html; the coverage map; the disk notice) calls themeBars with the theme it shows: a chosen theme puts its
// ground into both lines, "auto" gives each line its own value back, so a change of the system's theme still works
// without a script. The two lines keep their media.
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

// NOT FOR MERGE (branch bars-variants, round 7's brief BV): three ways of colouring an iPhone's status strip, chosen
// by the page's port for the user's LAN test: 8444 A (one fresh line without media), 8445 B (today's lines and the
// page's own ground on <html> and <body>), 8446 C (A and B); any other port: today's code.
type Variant = "A" | "B" | "C" | null;
const VARIANT: Variant = typeof location === "undefined" ? null
  : ({"8444": "A", "8445": "B", "8446": "C"} as Record<string, Variant>)[location.port] ?? null;
let fresh: HTMLMetaElement | null = null;  // A, C: the one line without media while a chosen theme is shown
let label = false;

/** A, C: a chosen theme removes the head's two lines and puts one new line in their place (a new element at every
 *  change); "auto" removes it and puts the two lines back where they stood. */
function freshLine(g: Grounds, theme: "auto" | "light" | "dark"): void {
  const {light, dark} = g.lines;
  const [first, second] = light.compareDocumentPosition(dark) & Node.DOCUMENT_POSITION_FOLLOWING
    ? [light, dark] : [dark, light];
  if (theme === "auto") {
    if (!fresh) return;
    fresh.before(first, second);
    fresh.remove();
    fresh = null;
    return;
  }
  const line = document.createElement("meta");
  line.name = "theme-color";
  line.content = g.values[theme];
  if (fresh) { fresh.replaceWith(line); } else { first.before(line); first.remove(); second.remove(); }
  fresh = line;
}

/** B, C: the shown theme's ground and colour scheme on the document's root, its ground on the body; "auto" removes
 *  them. */
function pageGround(g: Grounds, theme: "auto" | "light" | "dark"): void {
  const html = document.documentElement.style, body = document.body?.style;
  if (theme === "auto") {
    html.removeProperty("background-color");
    html.removeProperty("color-scheme");
    body?.removeProperty("background-color");
    return;
  }
  html.backgroundColor = g.values[theme];
  html.colorScheme = theme;
  if (body) body.backgroundColor = g.values[theme];
}

/** The variant's name in a corner, once: covers nothing pressable (no pointer events), hidden from assistive tech. */
function showLabel(): void {
  if (label || !VARIANT || !document.body) return;
  label = true;
  const tag = document.createElement("div");
  tag.textContent = "bars " + VARIANT;
  tag.setAttribute("aria-hidden", "true");
  tag.id = "fal-bars-variant";
  Object.assign(tag.style, {position: "fixed", left: "4px", bottom: "calc(env(safe-area-inset-bottom, 0px) + 76px)",
    zIndex: "2147483647", font: "bold 11px/1 sans-serif", color: "#e00", pointerEvents: "none",
    background: "rgb(255 255 255 / .7)", padding: "2px 3px", borderRadius: "3px"});
  document.body.appendChild(tag);
}

/** The bars in the ground of `theme`, the theme the page shows ("auto": the system's, as the head says it). */
export function themeBars(theme: "auto" | "light" | "dark"): void {
  showLabel();
  if (!grounds) grounds = headGrounds();
  if (!grounds) return;
  if (VARIANT === "A" || VARIANT === "C") freshLine(grounds, theme);
  if (VARIANT === "B" || VARIANT === "C") pageGround(grounds, theme);
  if (VARIANT === "A" || VARIANT === "C") return;
  for (const scheme of ["light", "dark"] as const) {
    const value = grounds.values[theme === "auto" ? scheme : theme], line = grounds.lines[scheme];
    if (line.content !== value) line.content = value;
  }
}
