// The three.js side of the page: the renderer, camera, lights and orbit controls, drawn on demand (only
// after a change: the controls moved, the window resized, something added). The scene's content (terrain,
// imagery, webbing, the walker) is added by its own modules through `add` and `redraw`.

import {
  AmbientLight, BufferAttribute, BufferGeometry, Color, DirectionalLight, DoubleSide, Mesh, MeshLambertMaterial,
  PerspectiveCamera, Scene, Vector3, WebGLRenderer, type Object3D,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ChunkMesh } from "./terrain";
import type { Level } from "./page";

export interface View {
  add(object: Object3D): void;
  /** Look at `target` from `from` (scene coordinates). */
  look(from: [number, number, number], target: [number, number, number]): void;
  redraw(): void;
  dispose(): void;
}

/** Draw into `host`; throws when the browser has no WebGL 2. `onLost`: the context was lost. */
export function createView(host: HTMLElement, level: Level, onLost: () => void): View {
  const canvas = document.createElement("canvas");
  canvas.className = "v3-canvas";
  const renderer = new WebGLRenderer({canvas, antialias: level === "full"});  // throws without WebGL 2
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  host.appendChild(canvas);
  const scene = new Scene();
  scene.background = new Color(0xc9d6df);
  scene.add(new AmbientLight(0xffffff, 0.9));
  const sun = new DirectionalLight(0xffffff, 2.2);
  sun.position.set(-0.6, 1, -0.4);  // from the north-west, as hill shading
  scene.add(sun);
  const camera = new PerspectiveCamera(50, 1, 1, 60000);
  const controls = new OrbitControls(camera, canvas);
  controls.maxPolarAngle = Math.PI * 0.495;  // never below the horizon

  let pending = false;
  const redraw = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; renderer.render(scene, camera); });
  };
  const resize = () => {
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    redraw();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  controls.addEventListener("change", redraw);
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); onLost(); });
  resize();

  return {
    add(object) { scene.add(object); redraw(); },
    look(from, target) {
      camera.position.set(...from);
      controls.target.copy(new Vector3(...target));
      controls.update();
      redraw();
    },
    redraw,
    dispose() { observer.disconnect(); controls.dispose(); renderer.dispose(); canvas.remove(); },
  };
}

/** A plain shaded mesh of a chunk. */
export function terrainMesh(chunk: ChunkMesh): Mesh {
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(chunk.positions, 3));
  geometry.setIndex(new BufferAttribute(chunk.indices, 1));
  geometry.computeVertexNormals();
  return new Mesh(geometry, new MeshLambertMaterial({color: 0xb9ab8c, side: DoubleSide}));
}
