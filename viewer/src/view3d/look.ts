// The walker's views, pure (docs/3d-view-contract.md, "Wave F"; tested in Node: tests/test_viewer.py): the
// camera of the views "eyes" and "behind" from the walker's pose and a gaze, the gaze turned by a drag, and the
// phone's turn from its DeviceOrientationEvent angles and the screen's orientation; the zoom of each view ("Wave
// F2": the eyes' horizontal angle like binoculars, the distance behind the walker). Scene axes as geometry.ts:
// X east, Y up, Z south; a yaw is a rotation about Y (webbing.ts walkerPose's: 0 faces +Z, growing turns left).

export type ViewName = "orbit" | "eyes" | "behind";
export const VIEWS: readonly ViewName[] = ["orbit", "eyes", "behind"];

/** A point or direction in the scene's axes. */
export type Vec3 = [number, number, number];

/** Where one looks, relative to the walker: `yaw` added to the walker's (radians, growing turns left), `pitch`
 *  up from the horizontal (radians). */
export interface Gaze { yaw: number; pitch: number }

export interface ViewSpec {
  /** The field of view at the default zoom, degrees: horizontal for the eyes (the same on every screen, the
   *  vertical angle follows from the canvas's aspect: verticalFov), vertical behind the walker. */
  fov: number;
  /** The gaze on entering the view. */
  start: Gaze;
  /** The pitch's range (never upside down). */
  pitch: [number, number];
  /** A drag across the stage's whole height turns the gaze by this many radians, unless dragGaze is given the
   *  turn (the eyes: the camera's vertical angle, so the world follows the finger at every zoom); `grab`: the view
   *  follows the finger as if it held the world (eyes, as a panorama), else as the orbit view turns (behind). */
  dragTurn: number;
  grab: boolean;
}

/** The eyes' height over the feet, metres (the walker is webbing.ts WALKER_HEIGHT tall). */
export const EYE_HEIGHT = 1.6;
/** Behind: the camera's distance from the point it looks at, that point's height over the feet (the chest). */
export const BEHIND_DISTANCE = 5;
export const BEHIND_HEIGHT = 1.2;
/** Behind: the camera at least this high over the terrain under it. */
export const BEHIND_CLEARANCE = 1;

export const VIEW_SPECS: Record<Exclude<ViewName, "orbit">, ViewSpec> = {
  eyes: {fov: 60, start: {yaw: 0, pitch: -0.2}, pitch: [-1.45, 1.45], dragTurn: 60 * Math.PI / 180, grab: true},
  behind: {fov: 60, start: {yaw: 0, pitch: -0.3}, pitch: [-1.35, 0.25], dragTurn: Math.PI, grab: false},
};

/** The walker as the views need it: its feet in the scene and its yaw (walker.group's position and rotation.y). */
export interface WalkerAt { feet: Vec3; yaw: number }

/** The unit direction of a total yaw and a pitch. */
export function direction(yaw: number, pitch: number): Vec3 {
  const c = Math.cos(pitch);
  return [Math.sin(yaw) * c, Math.sin(pitch), Math.cos(yaw) * c];
}

/** The camera of `view` for the walker and a gaze: its position and the point it looks at. Eyes: at the eyes,
 *  along the gaze; behind: `distance` (metres, behindDistance of the zoom) back from the walker's chest along the
 *  gaze, so the walker is in view and the camera turns around it. */
export function cameraPose(view: Exclude<ViewName, "orbit">, walker: WalkerAt, gaze: Gaze,
                           distance = BEHIND_DISTANCE): {position: Vec3; target: Vec3} {
  const g = clampGaze(view, gaze), d = direction(walker.yaw + g.yaw, g.pitch), [x, y, z] = walker.feet;
  if (view === "eyes") {
    const eye: Vec3 = [x, y + EYE_HEIGHT, z];
    return {position: eye, target: [eye[0] + d[0], eye[1] + d[1], eye[2] + d[2]]};
  }
  const chest: Vec3 = [x, y + BEHIND_HEIGHT, z];
  return {position: [chest[0] - d[0] * distance, chest[1] - d[1] * distance, chest[2] - d[2] * distance],
          target: chest};
}

/** The gaze with its pitch in the view's range. */
export function clampGaze(view: Exclude<ViewName, "orbit">, gaze: Gaze): Gaze {
  const [lo, hi] = VIEW_SPECS[view].pitch;
  return {yaw: gaze.yaw, pitch: Math.min(hi, Math.max(lo, gaze.pitch))};
}

/** The gaze after a drag of (dx, dy) CSS pixels on a stage `height` pixels high; `turn`: the radians of a drag
 *  over the whole height (the view's dragTurn when not given). */
export function dragGaze(view: Exclude<ViewName, "orbit">, gaze: Gaze, dx: number, dy: number, height: number,
                         turn?: number): Gaze {
  const spec = VIEW_SPECS[view], k = (turn ?? spec.dragTurn) / Math.max(1, height), sign = spec.grab ? 1 : -1;
  // grab: dragging right pulls the world right, so one looks further left (the yaw grows); dragging down looks up.
  // Orbit-like: the opposite, as OrbitControls turns
  return clampGaze(view, {yaw: gaze.yaw + sign * dx * k, pitch: gaze.pitch + sign * dy * k});
}

// The zoom ("Wave F2"): one number per view, larger is nearer, 1 on entering. The eyes': the magnification
// against the default horizontal angle (binoculars: tan(30°) / tan(h / 2), so ×8 is about 8.3°, the widest 110°
// about ×0.4); behind the walker: BEHIND_DISTANCE over the camera's distance (1.5 to 30 m). The buttons step by
// ZOOM_STEP onto the steps' grid (×1, ×1.4, ×2, ...), the wheel and the pinch change it smoothly.

/** The eyes' widest horizontal angle (degrees) and largest magnification; behind: the nearest and farthest
 *  distances, metres. */
export const EYES_WIDEST = 110;
export const EYES_ZOOM_MAX = 8;
export const BEHIND_NEAREST = 1.5;
export const BEHIND_FARTHEST = 30;
/** One button's step of the zoom (a factor), and the wheel's rate per CSS pixel of its deltaY. */
export const ZOOM_STEP = Math.SQRT2;
export const WHEEL_RATE = 0.002;

type WalkerView = Exclude<ViewName, "orbit">;
const RAD = Math.PI / 180;
const tanHalf = (deg: number) => Math.tan(deg * RAD / 2);

/** The zoom's range of `view`. */
export function zoomRange(view: WalkerView): [number, number] {
  return view === "eyes" ? [tanHalf(VIEW_SPECS.eyes.fov) / tanHalf(EYES_WIDEST), EYES_ZOOM_MAX]
                         : [BEHIND_DISTANCE / BEHIND_FARTHEST, BEHIND_DISTANCE / BEHIND_NEAREST];
}

export function clampZoom(view: WalkerView, zoom: number): number {
  const [lo, hi] = zoomRange(view);
  return Number.isFinite(zoom) ? Math.min(hi, Math.max(lo, zoom)) : 1;
}

/** The zoom multiplied by `factor` (> 1: nearer), in its range. */
export function zoomBy(view: WalkerView, zoom: number, factor: number): number {
  return clampZoom(view, zoom * factor);
}

/** A button's step: to the next step of the grid ZOOM_STEP^k nearer (+1) or farther (-1), in the range. */
export function zoomStep(view: WalkerView, zoom: number, direction: 1 | -1): number {
  const k = Math.log(zoom) / Math.log(ZOOM_STEP), eps = 1e-6;
  const next = direction > 0 ? Math.floor(k + eps) + 1 : Math.ceil(k - eps) - 1;
  return clampZoom(view, ZOOM_STEP ** next);
}

/** The wheel's factor of the zoom from a WheelEvent's deltaY and deltaMode (0 pixels, 1 lines, 2 pages): turned
 *  away from the user (deltaY < 0) nearer; one event at most a factor of e. */
export function wheelFactor(deltaY: number, deltaMode = 0): number {
  const px = deltaY * (deltaMode === 1 ? 16 : deltaMode === 2 ? 400 : 1);
  return Number.isFinite(px) ? Math.exp(-Math.max(-500, Math.min(500, px)) * WHEEL_RATE) : 1;
}

/** The pinch's factor of the zoom from two fingers' positions [x1, y1, x2, y2] when it began and now: their
 *  distance now over their distance then (spread: nearer); 1 when the fingers began on one spot. */
export function pinchFactor(start: number[], now: number[]): number {
  const d0 = Math.hypot(start[2] - start[0], start[3] - start[1]), d1 = Math.hypot(now[2] - now[0], now[3] - now[1]);
  return d0 >= 1 && Number.isFinite(d1) ? Math.max(1e-3, d1 / d0) : 1;
}

/** The eyes' horizontal angle at a zoom, degrees. */
export function eyesAngle(zoom: number): number {
  return 2 * Math.atan(tanHalf(VIEW_SPECS.eyes.fov) / zoom) / RAD;
}

/** The camera's distance behind the walker at a zoom, metres. */
export function behindDistance(zoom: number): number {
  return BEHIND_DISTANCE / zoom;
}

/** The vertical angle (degrees) of a horizontal one on a canvas `aspect` (width over height) wide. */
export function verticalFov(horizontal: number, aspect: number): number {
  return 2 * Math.atan(tanHalf(horizontal) / (aspect > 0 && Number.isFinite(aspect) ? aspect : 1)) / RAD;
}

/** The camera's vertical field of view (degrees) of `view` at a zoom on a canvas `aspect` wide. */
export function cameraFov(view: WalkerView, zoom: number, aspect: number): number {
  return view === "eyes" ? verticalFov(eyesAngle(zoom), aspect) : VIEW_SPECS.behind.fov;
}

/** The zoom's indicator value: the eyes' magnification against the default angle ("2", "1.4", "0.5"), the
 *  distance behind in metres ("5", "3.5", "14"); one decimal under 10, none from 10 on. */
export function zoomLabel(view: WalkerView, zoom: number): string {
  const v = view === "eyes" ? zoom : behindDistance(zoom);
  return v >= 9.95 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, "");
}

/** Where the phone's back camera points, from DeviceOrientationEvent's alpha, beta, gamma (degrees, the earth's
 *  frame of W3C: x east, y north, z up; alpha's zero is arbitrary on iOS: only turns count) and the screen's
 *  orientation angle (screen.orientation.angle, degrees counter-clockwise): `heading` (radians, growing as the
 *  phone turns right) and `pitch` (radians, up from the horizontal); null without the angles. The heading comes
 *  from the direction looked along and the screen's up together (the screen's up as the user holds it, portrait
 *  or landscape): steady also when the phone points down. */
export function deviceLook(alpha: number | null, beta: number | null, gamma: number | null, screenAngle: number):
    {heading: number; pitch: number} | null {
  if (alpha === null || beta === null || gamma === null ||
      !Number.isFinite(alpha) || !Number.isFinite(beta) || !Number.isFinite(gamma)) return null;
  const r = Math.PI / 180, [ca, sa] = [Math.cos(alpha * r), Math.sin(alpha * r)];
  const [cb, sb] = [Math.cos(beta * r), Math.sin(beta * r)], [cg, sg] = [Math.cos(gamma * r), Math.sin(gamma * r)];
  // R = Rz(alpha) · Rx(beta) · Ry(gamma): the device's axes in the earth's frame
  const R = [
    [ca * cg - sa * sb * sg, -sa * cb, ca * sg + sa * sb * cg],
    [sa * cg + ca * sb * sg, ca * cb, sa * sg - ca * sb * cg],
    [-cb * sg, sb, cb * cg],
  ];
  const apply = (v: Vec3): Vec3 => [0, 1, 2].map((i) => R[i][0] * v[0] + R[i][1] * v[1] + R[i][2] * v[2]) as Vec3;
  const o = (screenAngle || 0) * r;
  const f = apply([0, 0, -1]);                      // out of the phone's back
  const u = apply([Math.sin(o), Math.cos(o), 0]);   // the screen's up as it is held
  const pitch = Math.asin(Math.max(-1, Math.min(1, f[2])));
  // held level, f = cos p · H + sin p · Z and u = −sin p · H + cos p · Z for the heading H: H = f cos p − u sin p
  const hx = f[0] * Math.cos(pitch) - u[0] * Math.sin(pitch), hy = f[1] * Math.cos(pitch) - u[1] * Math.sin(pitch);
  if (!(Math.hypot(hx, hy) > 1e-9)) return null;
  return {heading: Math.atan2(hx, hy), pitch};
}

/** An angle in (−π, π]. */
export function wrap(a: number): number {
  const w = ((a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
  return w === -Math.PI ? Math.PI : w;
}

/** The gaze's change from the phone's turn since `base` (the reading when the motion was switched on or the view
 *  entered): turning right turns the view right (the yaw falls), tilting up looks up. */
export function motionOffset(base: {heading: number; pitch: number}, now: {heading: number; pitch: number}): Gaze {
  return {yaw: -wrap(now.heading - base.heading), pitch: now.pitch - base.pitch};
}

/** A change of the phone's turn smaller than this (radians, about 0.15°) draws nothing: the sensors' noise of a
 *  phone at rest would keep the page drawing. */
export const MOTION_DEADBAND = 0.0025;

export function gazeMoved(a: Gaze, b: Gaze): boolean {
  return Math.abs(wrap(a.yaw - b.yaw)) > MOTION_DEADBAND || Math.abs(a.pitch - b.pitch) > MOTION_DEADBAND;
}

/** The screen's orientation angle, degrees (screen.orientation, or iOS's older window.orientation). */
export function screenAngle(): number {
  const s = (globalThis as {screen?: {orientation?: {angle?: number}}}).screen?.orientation?.angle;
  if (typeof s === "number") return s;
  const w = (globalThis as {orientation?: number}).orientation;
  return typeof w === "number" ? w : 0;
}
