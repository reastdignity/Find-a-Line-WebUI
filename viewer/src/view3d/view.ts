// The three.js side of the page: the renderer, camera, lights and orbit controls, drawn on demand only (after a
// change: the controls moved, the window resized, something added, `invalidate`), or every frame while an owner
// keeps drawing (`keepDrawing`, the frame's callbacks of `onFrame`). The scene's content (terrain, imagery,
// webbing, the walker) is added by scene.ts. While the "Edges" look is on (`setEdges`), a frame is edges.ts' pass
// instead of one render. The walker's views (views.ts) leave the orbit (`setOrbit`) and place the camera themselves
// before each frame (`place`); back in the orbit the camera is as it was left.

import {
  AmbientLight, Color, DirectionalLight, PerspectiveCamera, Scene, Vector2, Vector3, WebGLRenderer, type Object3D,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { createEdgePass, edgesSupported, TERRAIN_LAYER, type EdgePass } from "./edges";
import type { Level } from "./page";

export interface View {
  scene: Scene;
  camera: PerspectiveCamera;
  renderer: WebGLRenderer;
  add(object: Object3D): void;
  remove(object: Object3D): void;
  /** Look at `target` from `from` (scene coordinates); `far`: the farthest distance the controls allow. */
  look(from: Vector3, target: Vector3, far?: number): void;
  invalidate(): void;
  onFrame(fn: (seconds: number) => void): () => void;
  /** Called before every frame drawn, on demand or not (after the `onFrame` callbacks); returns the unsubscribe. */
  beforeDraw(fn: () => void): () => void;
  keepDrawing(owner: string, on: boolean): void;
  /** Called after every resize with the drawing buffer's size in CSS pixels. */
  onResize(fn: (size: Vector2) => void): void;
  /** Called after every frame drawn (the renderer's counts are those of that frame). */
  onDrawn(fn: () => void): void;
  /** The orbit controls on or off (off while an anchor or the walker is dragged; always off outside the orbit). */
  setControls(on: boolean): void;
  /** Leave the orbit view (false: its camera kept, the controls off; the walker's views move the camera with
   *  `place`) or come back to it (true: the camera as it was). */
  setOrbit(on: boolean): void;
  /** Outside the orbit: the camera at `from` looking at `to` with a vertical field of view of `fov` degrees. */
  place(from: Vector3, to: Vector3, fov: number): void;
  /** The browser can draw the "Edges" look (edges.ts edgesSupported). */
  edgesSupported: boolean;
  /** The edges' pass on, its lines in `ink`, or off (null: its targets freed). */
  setEdges(ink: string | null): void;
  /** The edges' pass is on. */
  edgesOn(): boolean;
  dispose(): void;
}

/** Draw into `host`; throws when the browser has no WebGL 2. `onLost`: the context was lost. */
export function createView(host: HTMLElement, level: Level, background: string, onLost: () => void): View {
  const canvas = document.createElement("canvas");
  canvas.className = "v3-canvas";
  // preserveDrawingBuffer: drawn on demand, the last frame must be the one shown; WebKit (Playwright's iPhone)
  // showed the frame before it until another was drawn (the webbing grey after its profile came, 2 times in 4)
  const renderer = new WebGLRenderer({canvas, antialias: level === "full", preserveDrawingBuffer: true});  // throws without WebGL 2
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  host.appendChild(canvas);
  const scene = new Scene();
  scene.background = new Color(background);
  const ambient = new AmbientLight(0xffffff, 1.1);
  const sun = new DirectionalLight(0xffffff, 2.0);
  sun.position.set(-0.6, 1, -0.4);  // from the north-west, as hill shading
  for (const light of [ambient, sun]) {
    light.layers.enable(TERRAIN_LAYER);  // the edges' pass draws that layer alone: the lights stay the same
    scene.add(light);
  }
  const camera = new PerspectiveCamera(50, 1, 0.5, 60000);
  /** The walker's views come close to the webbing: a nearer near plane meanwhile. */
  const NEAR = 0.5, NEAR_WALKER = 0.2;
  const controls = new OrbitControls(camera, canvas);
  controls.maxPolarAngle = Math.PI * 0.495;  // never below the horizon
  controls.screenSpacePanning = false;       // panning keeps the height: the view stays over the terrain
  controls.enableDamping = false;

  const frameFns = new Set<(seconds: number) => void>(), owners = new Set<string>();
  const beforeFns = new Set<() => void>();
  const resizeFns: ((size: Vector2) => void)[] = [], drawnFns: (() => void)[] = [];
  let pending = 0, last = 0, lost = false, edgePass: EdgePass | null = null;
  let controlsOn = true, orbit: {position: Vector3; target: Vector3; fov: number} | null = null;
  const canEdges = edgesSupported(renderer);
  const draw = (time: number) => {
    pending = 0;
    if (lost) return;
    if (owners.size) {
      const seconds = last ? Math.max(0, (time - last) / 1000) : 0;
      last = time;
      for (const fn of [...frameFns]) fn(seconds);
    } else last = 0;
    for (const fn of [...beforeFns]) fn();
    if (edgePass) edgePass.render(); else renderer.render(scene, camera);
    for (const fn of drawnFns) fn();
    if (owners.size) invalidate();
  };
  const invalidate = () => { if (!pending && !lost) pending = requestAnimationFrame(draw); };
  const size = new Vector2(), buffer = new Vector2();
  const passSize = () => {
    renderer.getDrawingBufferSize(buffer);
    edgePass?.setSize(buffer.x, buffer.y);
  };
  const dropPass = () => { edgePass?.dispose(); edgePass = null; };
  const resize = () => {
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h, false);
    passSize();
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    size.set(w, h);
    for (const fn of resizeFns) fn(size);
    invalidate();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  controls.addEventListener("change", invalidate);
  canvas.addEventListener("webglcontextlost", (e) => {
    e.preventDefault();
    lost = true;
    if (pending) cancelAnimationFrame(pending);
    pending = 0;
    dropPass();
    onLost();
  });
  resize();

  return {
    scene, camera, renderer,
    add(object) { scene.add(object); invalidate(); },
    remove(object) { scene.remove(object); invalidate(); },
    look(from, target, far) {
      camera.position.copy(from);
      controls.target.copy(target);
      if (far) { controls.maxDistance = far; camera.far = far * 4; camera.updateProjectionMatrix(); }
      controls.update();
      invalidate();
    },
    invalidate,
    onFrame(fn) { frameFns.add(fn); return () => { frameFns.delete(fn); }; },
    beforeDraw(fn) { beforeFns.add(fn); return () => { beforeFns.delete(fn); }; },
    keepDrawing(owner, on) {
      if (on) owners.add(owner); else owners.delete(owner);
      invalidate();
    },
    onResize(fn) { resizeFns.push(fn); fn(size); },
    onDrawn(fn) { drawnFns.push(fn); },
    setControls(on) { controlsOn = on; controls.enabled = on && !orbit; },
    setOrbit(on) {
      if (on === !orbit) return;
      if (!on) {
        orbit = {position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov};
        controls.enabled = false;
        camera.near = NEAR_WALKER;
        camera.updateProjectionMatrix();
      } else {
        const kept = orbit!;
        orbit = null;
        camera.position.copy(kept.position);
        camera.fov = kept.fov;
        camera.near = NEAR;
        camera.updateProjectionMatrix();
        controls.target.copy(kept.target);
        controls.enabled = controlsOn;
        controls.update();
      }
      invalidate();
    },
    place(from, to, fov) {
      if (!orbit) return;
      camera.position.copy(from);
      camera.lookAt(to);
      if (camera.fov !== fov) { camera.fov = fov; camera.updateProjectionMatrix(); }
    },
    edgesSupported: canEdges,
    setEdges(ink) {
      if (ink === null || !canEdges || lost) dropPass();
      else if (!edgePass) {
        edgePass = createEdgePass(renderer, scene, camera, ink, level === "full" ? 4 : 0);
        passSize();
      }
      invalidate();
    },
    edgesOn() { return edgePass !== null; },
    dispose() {
      lost = true;
      if (pending) cancelAnimationFrame(pending);
      observer.disconnect();
      controls.dispose();
      dropPass();
      renderer.dispose();
      canvas.remove();
    },
  };
}
