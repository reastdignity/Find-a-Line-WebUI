// The "Edges" look of the 3D view (docs/3d-view-contract.md, "Wave E"): the terrain on paper with bold lines in
// screen space and the mesh's thin feature edges. The pass (`createEdgePass`, view.ts runs it while the look is
// on): the scene drawn into a colour target (multisampled at level full), the terrain alone (the meshes on
// TERRAIN_LAYER: the patch's chunks and the ring's tiles; never the webbing, the walker or the overlay) into a
// target of its view-space normals and distances, then a full-screen pass drawing `--ink` where the distance
// jumps (silhouettes: ridges against what lies behind them, the horizon) or the normal turns sharply (creases:
// cliff edges, gullies). The neighbours are sampled `sampleStep` texels away (the pixel ratio, at most 2), so a
// line is about one CSS pixel wide at every pixel ratio. `featureEdges` (pure, tested in Node) gives the thin
// lines of the mesh: edges between two faces turning by more than FEATURE_ANGLE degrees, never the outline of a
// chunk or its skirts (the chunks' seams would show).

import {
  Color, HalfFloatType, Mesh, MeshNormalMaterial, NearestFilter, OrthographicCamera, PlaneGeometry, Scene,
  ShaderMaterial, Vector2, WebGLRenderTarget, type Material, type Object3D, type PerspectiveCamera, type Plane,
  type Side, type Texture, type WebGLRenderer,
} from "three";

/** The layer of the terrain's meshes (the patch's chunks, the ring's tiles): drawn alone into the normals. */
export const TERRAIN_LAYER = 1;

/** The look's thresholds (the user's choice of the prototype's variant M): silhouettes where the distance from
 *  the camera jumps by a relative SILHOUETTE[0]..[1], creases where 1 − dot of the normals is CREASE[0]..[1],
 *  drawn at CREASE_STRENGTH; the mesh's feature edges where its faces turn by more than FEATURE_ANGLE degrees. */
export const SILHOUETTE: [number, number] = [0.012, 0.035];
export const CREASE: [number, number] = [0.10, 0.28];
export const CREASE_STRENGTH = 0.75;
export const FEATURE_ANGLE = 28;

/** Texels between a pixel and the neighbours it is compared with: the pixel ratio, 1 to 2. */
export function sampleStep(pixelRatio: number): number {
  return Math.min(2, Math.max(1, Number.isFinite(pixelRatio) ? pixelRatio : 1));
}

/** The feature edges of an indexed mesh (its first `count` index entries): the segments (x, y, z pairs) of the
 *  edges two triangles share whose normals differ by at least `angle` degrees (as three's EdgesGeometry decides:
 *  dot ≤ cos angle). Edges of one triangle only (the outline, the holes over no data) are left out, as are
 *  degenerate triangles. */
export function featureEdges(positions: ArrayLike<number>, indices: ArrayLike<number>, count: number,
                             angle = FEATURE_ANGLE): Float32Array {
  const triangles = Math.floor(Math.min(count, indices.length) / 3), limit = Math.cos(angle * Math.PI / 180);
  const normals = new Float64Array(3 * triangles), ok = new Uint8Array(triangles);
  const vertices = positions.length / 3;
  for (let t = 0; t < triangles; t++) {
    const a = 3 * indices[3 * t], b = 3 * indices[3 * t + 1], c = 3 * indices[3 * t + 2];
    const ux = positions[b] - positions[a], uy = positions[b + 1] - positions[a + 1], uz = positions[b + 2] - positions[a + 2];
    const vx = positions[c] - positions[a], vy = positions[c + 1] - positions[a + 1], vz = positions[c + 2] - positions[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, len = Math.hypot(nx, ny, nz);
    if (!(len > 0)) continue;
    normals[3 * t] = nx / len; normals[3 * t + 1] = ny / len; normals[3 * t + 2] = nz / len;
    ok[t] = 1;
  }
  const first = new Map<number, number>(), out: number[] = [];
  for (let t = 0; t < triangles; t++) {
    if (!ok[t]) continue;
    for (let k = 0; k < 3; k++) {
      const p = indices[3 * t + k], q = indices[3 * t + (k + 1) % 3];
      const key = Math.min(p, q) * vertices + Math.max(p, q), other = first.get(key);
      if (other === undefined) { first.set(key, t); continue; }
      if (other < 0) continue;  // a third face on the edge: not a surface
      first.set(key, -1);
      const dot = normals[3 * t] * normals[3 * other] + normals[3 * t + 1] * normals[3 * other + 1] +
                  normals[3 * t + 2] * normals[3 * other + 2];
      if (dot <= limit) {
        out.push(positions[3 * p], positions[3 * p + 1], positions[3 * p + 2],
                 positions[3 * q], positions[3 * q + 1], positions[3 * q + 2]);
      }
    }
  }
  return new Float32Array(out);
}

const QUAD_VERTEX = `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const QUAD_FRAGMENT = `
uniform sampler2D tColor;
uniform sampler2D tND;
uniform vec2 texel;
uniform float spacing;
uniform vec3 lineColor;
uniform vec2 silhouette;
uniform vec2 crease;
uniform float creaseStrength;
varying vec2 vUv;
vec4 nd(vec2 o) { return texture2D(tND, vUv + o * texel * spacing); }
void main() {
  vec4 c = texture2D(tColor, vUv);
  vec4 p = nd(vec2(0.0));
  float sil = 0.0;
  float cre = 0.0;
  for (int k = 0; k < 8; k++) {
    vec2 o = k == 0 ? vec2(1.0, 0.0) : k == 1 ? vec2(-1.0, 0.0) : k == 2 ? vec2(0.0, 1.0) : k == 3 ? vec2(0.0, -1.0)
           : k == 4 ? vec2(1.0, 1.0) : k == 5 ? vec2(-1.0, 1.0) : k == 6 ? vec2(1.0, -1.0) : vec2(-1.0, -1.0);
    vec4 q = nd(o);
    bool a = p.w > 0.0;
    bool b = q.w > 0.0;
    if (a != b) { sil = 1.0; continue; }
    if (!a) continue;
    float rel = abs(q.w - p.w) / min(q.w, p.w);
    sil = max(sil, smoothstep(silhouette.x, silhouette.y, rel));
    cre = max(cre, smoothstep(crease.x, crease.y, 1.0 - dot(p.xyz, q.xyz)));
  }
  float e = max(sil, creaseStrength * cre);
  gl_FragColor = vec4(mix(c.rgb, lineColor, e), 1.0);
  #include <colorspace_fragment>
}`;

type Source = Material & {
  displacementMap?: Texture | null; displacementScale?: number; displacementBias?: number;
  bumpMap?: Texture | null; bumpScale?: number;
};

/** A material writing the view-space normal (xyz) and the distance in front of the camera (w) of `source`'s
 *  surface: three's MeshNormalMaterial with the source's displacement and bump maps (the ring's tiles are
 *  displaced on the GPU), clipping planes and side, and the source's own bump chunk (onBeforeCompile). */
class NormalsMaterial extends MeshNormalMaterial {
  private key = "";

  constructor(private source: Source) {
    super();
    this.onBeforeCompile = (shader, renderer) => {
      source.onBeforeCompile?.(shader, renderer);  // e.g. the ring's smooth bump chunk
      shader.vertexShader = "varying float vFalDistance;\n" + shader.vertexShader
        .replace("#include <project_vertex>", "#include <project_vertex>\nvFalDistance = - mvPosition.z;");
      shader.fragmentShader = "varying float vFalDistance;\n" + shader.fragmentShader
        .replace("gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );",
                 "gl_FragColor = vec4( normalize( normal ), vFalDistance );")
        .replace("gl_FragColor.a = 1.0;", "");
    };
    this.sync();
  }

  override customProgramCacheKey(): string {
    return "findaline-normals:" + this.source.customProgramCacheKey();
  }

  /** Follow the source's maps and clipping (a new program when what they define changes). */
  sync() {
    const s = this.source;
    this.displacementMap = s.displacementMap ?? null;
    this.displacementScale = s.displacementScale ?? 1;
    this.displacementBias = s.displacementBias ?? 0;
    this.bumpMap = s.bumpMap ?? null;
    this.bumpScale = s.bumpScale ?? 1;
    this.clippingPlanes = s.clippingPlanes as Plane[] | null;
    this.clipIntersection = s.clipIntersection;
    this.side = s.side as Side;
    const key = [!!this.displacementMap, !!this.bumpMap, this.clippingPlanes?.length ?? 0, this.side].join();
    if (key !== this.key) { this.key = key; this.needsUpdate = true; }
  }
}

export interface EdgePass {
  render(): void;
  setSize(width: number, height: number): void;
  dispose(): void;
}

/** The edges' pipeline for `scene` seen by `camera`, its lines in `ink`; `samples`: the colour target's MSAA
 *  (0: none). The renderer's counts (`info.render`) are those of all three draws of a frame. */
export function createEdgePass(renderer: WebGLRenderer, scene: Scene, camera: PerspectiveCamera, ink: string,
                               samples: number): EdgePass {
  const colour = new WebGLRenderTarget(1, 1, {type: HalfFloatType, samples});
  const normals = new WebGLRenderTarget(1, 1, {type: HalfFloatType, minFilter: NearestFilter, magFilter: NearestFilter});
  const quadMaterial = new ShaderMaterial({
    vertexShader: QUAD_VERTEX, fragmentShader: QUAD_FRAGMENT, depthTest: false, depthWrite: false,
    uniforms: {
      tColor: {value: colour.texture}, tND: {value: normals.texture}, texel: {value: new Vector2(1, 1)},
      spacing: {value: sampleStep(renderer.getPixelRatio())}, lineColor: {value: new Color(ink)},
      silhouette: {value: new Vector2(...SILHOUETTE)}, crease: {value: new Vector2(...CREASE)},
      creaseStrength: {value: CREASE_STRENGTH},
    },
  });
  const quad = new Mesh(new PlaneGeometry(2, 2), quadMaterial);
  const quadScene = new Scene();
  quadScene.add(quad);
  const quadCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const own = new Map<Material, NormalsMaterial>();
  const normalsOf = (source: Material) => {
    let m = own.get(source);
    if (!m) {
      const made = m = new NormalsMaterial(source);
      own.set(source, made);
      source.addEventListener("dispose", function gone() {  // a ring tile unloaded
        source.removeEventListener("dispose", gone);
        own.delete(source);
        made.dispose();
      });
    } else m.sync();
    return m;
  };
  const clear = new Color(), swapped: [Mesh, Material | Material[]][] = [];
  const terrainOnly = (o: Object3D) => {
    const mesh = o as Mesh;
    if (!mesh.isMesh || !mesh.layers.isEnabled(TERRAIN_LAYER) || Array.isArray(mesh.material)) return;
    swapped.push([mesh, mesh.material]);
    mesh.material = normalsOf(mesh.material);
  };
  return {
    render() {
      const info = renderer.info, autoReset = info.autoReset;
      info.autoReset = false;
      info.reset();
      renderer.setRenderTarget(colour);
      renderer.render(scene, camera);
      // the terrain alone, its normals and distances (0 where there is none)
      const sky = scene.background, alpha = renderer.getClearAlpha(), layers = camera.layers.mask;
      renderer.getClearColor(clear);
      scene.background = null;
      scene.traverseVisible(terrainOnly);
      camera.layers.set(TERRAIN_LAYER);
      renderer.setRenderTarget(normals);
      renderer.setClearColor(0x000000, 0);
      renderer.clear();
      renderer.render(scene, camera);
      camera.layers.mask = layers;
      for (const [mesh, material] of swapped.splice(0)) mesh.material = material;
      scene.background = sky;
      renderer.setClearColor(clear, alpha);
      renderer.setRenderTarget(null);
      renderer.render(quadScene, quadCamera);
      info.autoReset = autoReset;
    },
    setSize(width, height) {
      colour.setSize(width, height);
      normals.setSize(width, height);
      quadMaterial.uniforms.texel.value.set(1 / width, 1 / height);
      quadMaterial.uniforms.spacing.value = sampleStep(renderer.getPixelRatio());
    },
    dispose() {
      colour.dispose();
      normals.dispose();
      for (const m of own.values()) m.dispose();
      own.clear();
      quadMaterial.dispose();
      quad.geometry.dispose();
    },
  };
}

/** Whether the browser can draw into the pass's targets (half floats as colours). */
export function edgesSupported(renderer: WebGLRenderer): boolean {
  return renderer.extensions.has("EXT_color_buffer_float") || renderer.extensions.has("EXT_color_buffer_half_float");
}
