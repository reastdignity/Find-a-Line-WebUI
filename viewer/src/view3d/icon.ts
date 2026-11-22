// The kit's icons (24 × 24, stroked with currentColor) for the 3D view's plain DOM: the notice's dismiss ("close"),
// the sorted column of "Lines from a point" ("sort"), a favourite's star on another line's label ("star"), the
// phone's "About this view" button ("info").
// Decorative (aria-hidden): the control carries its name. The paths are copies of ui/icons.tsx ICONS (that module
// imports the logo's SVG files, which the Node tests' bundles of these modules cannot load):
// tests/test_viewer.py::test_view3d_icons_are_the_kits holds them equal. Static markup, so setting it as innerHTML
// is safe under the CSP (no style attributes).

export const KIT_ICONS = {
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  sort: '<path d="M12 4v16M6 14l6 6 6-6"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8 6.8 19.5l1-5.8-4.2-4.1 5.8-.8z"/>',
} as const;

const SVG = "http://www.w3.org/2000/svg";

export function kitIcon(name: keyof typeof KIT_ICONS, cls = ""): SVGSVGElement {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", "u-ic" + (cls ? " " + cls : ""));
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = KIT_ICONS[name];
  return svg;
}
