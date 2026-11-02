// The walker's views, pure (docs/3d-view-contract.md, "Wave F"; tested in Node: tests/test_viewer.py): the
// camera of the views "eyes" and "behind" from the walker's pose and a gaze, the gaze turned by a drag, and the
// phone's turn from its DeviceOrientationEvent angles and the screen's orientation. Scene axes as geometry.ts:
// X east, Y up, Z south; a yaw is a rotation about Y (webbing.ts walkerPose's: 0 faces +Z, growing turns left).

export type ViewName = "orbit" | "eyes" | "behind";
export const VIEWS: readonly ViewName[] = ["orbit", "eyes", "behind"];

/** A point or direction in the scene's axes. */
export type Vec3 = [number, number, number];

/** Where one looks, relative to the walker: `yaw` added to the walker's (radians, growing turns left), `pitch`
 *  up from the horizontal (radians). */
export interface Gaze { yaw: number; pitch: number }

export interface ViewSpec {
  /** The camera's vertical field of view, degrees. */
  fov: number;
  /** The gaze on entering the view. */
  start: Gaze;
  /** The pitch's range (never upside down). */
  pitch: [number, number];
  /** A drag across the stage's whole height turns the gaze by this many radians; `grab`: the view follows the
   *  finger as if it held the world (eyes, as a panorama), else as the orbit view turns (behind). */
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
  eyes: {fov: 70, start: {yaw: 0, pitch: -0.2}, pitch: [-1.45, 1.45], dragTurn: 70 * Math.PI / 180, grab: true},
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
 *  along the gaze; behind: BEHIND_DISTANCE back from the walker's chest along the gaze, so the walker is in view
 *  and the camera turns around it. */
export function cameraPose(view: Exclude<ViewName, "orbit">, walker: WalkerAt, gaze: Gaze): {position: Vec3; target: Vec3} {
  const g = clampGaze(view, gaze), d = direction(walker.yaw + g.yaw, g.pitch), [x, y, z] = walker.feet;
  if (view === "eyes") {
    const eye: Vec3 = [x, y + EYE_HEIGHT, z];
    return {position: eye, target: [eye[0] + d[0], eye[1] + d[1], eye[2] + d[2]]};
  }
  const chest: Vec3 = [x, y + BEHIND_HEIGHT, z];
  return {position: [chest[0] - d[0] * BEHIND_DISTANCE, chest[1] - d[1] * BEHIND_DISTANCE, chest[2] - d[2] * BEHIND_DISTANCE],
          target: chest};
}

/** The gaze with its pitch in the view's range. */
export function clampGaze(view: Exclude<ViewName, "orbit">, gaze: Gaze): Gaze {
  const [lo, hi] = VIEW_SPECS[view].pitch;
  return {yaw: gaze.yaw, pitch: Math.min(hi, Math.max(lo, gaze.pitch))};
}

/** The gaze after a drag of (dx, dy) CSS pixels on a stage `height` pixels high. */
export function dragGaze(view: Exclude<ViewName, "orbit">, gaze: Gaze, dx: number, dy: number, height: number): Gaze {
  const spec = VIEW_SPECS[view], k = spec.dragTurn / Math.max(1, height), sign = spec.grab ? 1 : -1;
  // grab: dragging right pulls the world right, so one looks further left (the yaw grows); dragging down looks up.
  // Orbit-like: the opposite, as OrbitControls turns
  return clampGaze(view, {yaw: gaze.yaw + sign * dx * k, pitch: gaze.pitch + sign * dy * k});
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
