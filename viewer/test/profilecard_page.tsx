// A test page of result/view/ProfileCard, its Splitters and useCornersAboveCard (tests/test_layout.py builds it
// into a run's folder and opens it in headless Edge through Playwright from the app's server: the card follows
// ResizeObservers, which --dump-dom's virtual time never runs): a run's line selected, the card
// over a Leaflet map in a box of a fixed size, its edges moved by keys, the pointer and double clicks, folded,
// in a low and a narrow box, closed; the findings go into <pre id="result"> as JSON.

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { render } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { loadRun } from "../src/result/load";
import { ResultModel } from "../src/result/model";
import { useCornersAboveCard } from "../src/result/view/corners";
import { DEFAULT_LAYOUT, type Layout } from "../src/result/view/layout";
import { ProfileCard } from "../src/result/view/ProfileCard";

const out: Record<string, unknown> = {};
const finish = () => {
  const pre = document.createElement("pre");
  pre.id = "result";
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
};
const runId = decodeURIComponent(location.pathname.split("/")[2]);
const wait = (ms = 80) => new Promise((resolve) => setTimeout(resolve, ms));
const $ = <T extends Element = HTMLElement>(s: string) => document.querySelector<T>(s);
const commits: Layout[] = [];
let layoutNow: Layout = DEFAULT_LAYOUT;
let resize: (w: number, h: number) => void = () => {};

function Harness({model}: {model: ResultModel}) {
  const [layout, setLayout] = useState<Layout>(DEFAULT_LAYOUT);
  const [size, setSize] = useState({w: 1000, h: 700});
  const holder = useRef<HTMLDivElement>(null), mapBox = useRef<HTMLDivElement>(null);
  layoutNow = layout;
  resize = (w, h) => setSize({w, h});
  useEffect(() => {
    const map = L.map(mapBox.current!, {center: model.data.center, zoom: 16});
    L.control.scale({position: "bottomleft"}).addTo(map);
    return () => { map.remove(); };
  }, []);
  useCornersAboveCard(mapBox, holder, true);
  return <div class="t-holder" ref={holder} style={{position: "relative", width: `${size.w}px`, height: `${size.h}px`}}>
    <div class="t-map" ref={mapBox} style={{position: "absolute", inset: "0"}} />
    <ProfileCard model={model} layout={layout}
                 onLayout={(next, commit) => { layoutNow = next; setLayout(next); if (commit) commits.push(next); }} />
  </div>;
}

const key = (el: Element, k: string, shift = false) =>
  el.dispatchEvent(new KeyboardEvent("keydown", {key: k, shiftKey: shift, bubbles: true, cancelable: true}));
const pointer = (el: Element, type: string, x: number, y: number) =>
  el.dispatchEvent(new PointerEvent(type, {bubbles: true, cancelable: true, pointerId: 1, pointerType: "mouse",
                                           button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: x, clientY: y}));
const card = () => $(".r-card");
const chart = () => {
  const box = $(".r-card .fal-profile-chart"), svg = $(".r-card .fal-profile-chart svg");
  return {box: box?.clientHeight ?? 0, svg: Number(svg?.getAttribute("height") ?? 0)};
};
const state = () => {
  const c = card(), top = $(".r-card .r-card-top");
  return {height: c?.offsetHeight ?? 0, left: c?.offsetLeft ?? 0, width: c?.offsetWidth ?? 0,
          folded: !!c?.classList.contains("r-card-folded"), chart: chart(),
          now: Number(top?.getAttribute("aria-valuenow")), min: Number(top?.getAttribute("aria-valuemin")),
          max: Number(top?.getAttribute("aria-valuemax"))};
};
const corners = () => ({attribution: $(".t-map .leaflet-bottom.leaflet-right")?.style.bottom ?? null,
                        scale: $(".t-map .leaflet-bottom.leaflet-left")?.style.bottom ?? null});

(async () => {
  try {
    const data = await loadRun(runId);
    const model = new ResultModel(data, {favourites: false, profiles: false});
    const root = document.createElement("div");
    root.className = "ui";
    document.body.appendChild(root);
    const group = model.groups.find((g) => g.rep.prof)!;
    model.select(group);
    render(<Harness model={model} />, root);
    await wait(300);
    out.initial = state();
    const shown = (s: string) => { const e = $(s); return !!e && e.getClientRects().length > 0; };
    out.compact = {head: !!$(".r-card .fal-profile-head"), title: $(".r-card .fal-profile-title")?.textContent ?? "",
                   facts: $(".r-card .r-facts")?.textContent ?? "", legend: shown(".r-card .fal-profile-legend")};
    $<HTMLButtonElement>(".r-card .r-dock-bar .u-chip")!.click();
    await wait(150);
    out.rigging = {legend: shown(".r-card .fal-profile-legend"), scale: shown(".r-card .fal-key .fal-scale")};
    $<HTMLButtonElement>(".r-card .r-dock-bar .u-chip")!.click();
    await wait(150);
    out.initialCorners = corners();
    const top = $(".r-card .r-card-top")!;
    // The keys: ↑ 16, Shift+↑ 64; each kept
    key(top, "ArrowUp");
    await wait();
    key(top, "ArrowUp", true);
    await wait();
    out.keys = {...state(), commits: commits.length, kept: commits[commits.length - 1]?.profile.h};
    // The pointer: 40 px up, kept when released
    const r = top.getBoundingClientRect(), y = r.top + r.height / 2, x = r.left + r.width / 2;
    pointer(top, "pointerdown", x, y);
    pointer(top, "pointermove", x, y - 20);
    pointer(top, "pointermove", x, y - 40);
    await wait();
    out.dragging = {...state(), commits: commits.length, cls: top.className};
    pointer(top, "pointerup", x, y - 40);
    await wait();
    out.dragged = {...state(), commits: commits.length, kept: commits[commits.length - 1]?.profile.h};
    key(top, "Home");
    await wait(150);
    out.home = {...state(), kept: layoutNow.profile.h};
    key(top, "End");
    await wait(150);
    out.end = state();
    key(top, "Home");
    await wait(150);
    // The sides: → narrows from the left; the right edge dragged 100 px left; a double click resets the left
    const left = $(".r-card .r-card-l")!, right = $(".r-card .r-card-r")!;
    key(left, "ArrowRight");
    await wait();
    out.leftKey = {...state(), l: layoutNow.profile.l, r: layoutNow.profile.r};
    const rr = right.getBoundingClientRect();
    pointer(right, "pointerdown", rr.left + 3, rr.top + 10);
    pointer(right, "pointermove", rr.left - 97, rr.top + 10);
    pointer(right, "pointerup", rr.left - 97, rr.top + 10);
    await wait(150);
    out.rightDrag = {...state(), l: layoutNow.profile.l, r: layoutNow.profile.r, corners: corners()};
    left.dispatchEvent(new MouseEvent("dblclick", {bubbles: true}));
    await wait();
    out.leftReset = {l: layoutNow.profile.l, r: layoutNow.profile.r, kept: commits[commits.length - 1]?.profile.l};
    // A card clear of the attribution: the attribution in its place, the scale above the card
    const attribution = $(".t-map .leaflet-bottom.leaflet-right")!;
    const clear = 1000 - (attribution.getBoundingClientRect().left - $(".t-holder")!.getBoundingClientRect().left) + 20;
    key(right, "Home");  // the narrowest from the right
    await wait(150);
    out.clearOfAttribution = {...state(), r: layoutNow.profile.r, corners: corners(), clear};
    key(right, "End");
    await wait(150);
    out.coveringAgain = corners();
    // Folded by its button, unfolded by Enter on the top edge
    const before = commits.length;
    $<HTMLButtonElement>(".r-card .r-fold")!.click();
    await wait(150);
    out.folded = {...state(), kept: layoutNow.profile.folded, commits: commits.length - before, corners: corners(),
                  label: $(".r-card .r-fold")?.getAttribute("aria-label"),
                  expanded: $(".r-card .r-fold")?.getAttribute("aria-expanded")};
    key($(".r-card .r-card-top")!, "Enter");
    await wait(150);
    out.unfolded = {...state(), kept: layoutNow.profile.folded};
    // A low map: folded at once; unfolded there for the page, not kept
    const kept = commits.length;
    resize(1000, 380);
    await wait(300);
    out.low = {...state(), kept: layoutNow.profile.folded};
    $<HTMLButtonElement>(".r-card .r-fold")!.click();
    await wait(150);
    out.lowUnfolded = {...state(), kept: layoutNow.profile.folded, commits: commits.length - kept};
    // Its height and an edge moved there: for the page too, nothing reaches the layout
    const keptH = layoutNow.profile.h, keptL = layoutNow.profile.l;
    key($(".r-card .r-card-top")!, "Home");
    await wait(150);
    key($(".r-card .r-card-l")!, "ArrowRight");
    await wait(150);
    out.lowResized = {...state(), commits: commits.length - kept, h: layoutNow.profile.h, keptH,
                      l: layoutNow.profile.l, keptL};
    resize(1000, 700);
    await wait(300);
    out.backHigh = state();
    // A narrow map: the insets shrink (not kept), the card keeps its least width
    key($(".r-card .r-card-l")!, "ArrowRight", true);
    await wait();
    key($(".r-card .r-card-l")!, "ArrowRight", true);
    await wait(150);
    const wideL = layoutNow.profile.l, narrowCommits = commits.length;
    resize(500, 700);
    await wait(300);
    out.narrow = {...state(), l: layoutNow.profile.l, wideL, commits: commits.length - narrowCommits};
    resize(1000, 700);
    await wait(300);
    // Closed: no card, the corners back in their places
    $<HTMLButtonElement>(".r-card .r-dock-bar button[aria-label='Close the profile']")!.click();
    await wait(300);
    out.closed = {card: !!card(), closed: model.profileClosed, corners: corners()};
  } catch (e) {
    out.error = String(e && (e as Error).stack || e);
  }
  finish();
})();
