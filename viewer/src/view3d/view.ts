// The three.js side of the page: the renderer, camera, lights and orbit controls, drawn on demand only (after a
// change: the controls moved, the window resized, something added, `invalidate`), or every frame while an owner
// keeps drawing (`keepDrawing`, the frame's callbacks of `onFrame`). The scene's content (terrain, imagery,
// webbing, the walker) is added by scene.ts.

import {
  AmbientLight, Color, DirectionalLight, PerspectiveCamera, Scene, Vector2, Vector3, WebGLRenderer, type Object3D,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
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
  /** The orbit controls on or off (off while an anchor or the walker is dragged). */
  setControls(on: boolean): void;
  dispose(): void;
}

/** Draw into `host`; throws when the browser has no WebGL 2. `onLost`: the context was lost. */
export function createView(host: HTMLElement, level: Level, background: string, onLost: () => void): View {
  const canvas = document.createElement("canvas");
  canvas.className = "v3-canvas";
  const renderer = new WebGLRenderer({canvas, antialias: level === "full"});  // throws without WebGL 2
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  host.appendChild(canvas);
  const scene = new Scene();
  scene.background = new Color(background);
  scene.add(new AmbientLight(0xffffff, 1.1));
  const sun = new DirectionalLight(0xffffff, 2.0);
  sun.position.set(-0.6, 1, -0.4);  // from the north-west, as hill shading
  scene.add(sun);
  const camera = new PerspectiveCamera(50, 1, 0.5, 60000);
  const controls = new OrbitControls(camera, canvas);
  controls.maxPolarAngle = Math.PI * 0.495;  // never below the horizon
  controls.screenSpacePanning = false;       // panning keeps the height: the view stays over the terrain
  controls.enableDamping = false;

  const frameFns = new Set<(seconds: number) => void>(), owners = new Set<string>();
  const beforeFns = new Set<() => void>();
  const resizeFns: ((size: Vector2) => void)[] = [], drawnFns: (() => void)[] = [];
  let pending = 0, last = 0, lost = false;
  const draw = (time: number) => {
    pending = 0;
    if (lost) return;
    if (owners.size) {
      const seconds = last ? Math.max(0, (time - last) / 1000) : 0;
      last = time;
      for (const fn of [...frameFns]) fn(seconds);
    } else last = 0;
    for (const fn of [...beforeFns]) fn();
    renderer.render(scene, camera);
    for (const fn of drawnFns) fn();
    if (owners.size) invalidate();
  };
  const invalidate = () => { if (!pending && !lost) pending = requestAnimationFrame(draw); };
  const size = new Vector2();
  const resize = () => {
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h, false);
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
    setControls(on) { controls.enabled = on; },
    dispose() {
      lost = true;
      if (pending) cancelAnimationFrame(pending);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      canvas.remove();
    },
  };
}
