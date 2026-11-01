// three.js with our own data: a 1025 px terrain-RGB tile of the Polish 1 m DEM decoded in the page,
// meshed with martini (?err=0.25 m), draped with an orthophoto tile, a fat line for the webbing, a
// one-triangle glTF, a BVH raycast at the centre of the view.
(async () => {
  const T = window.FAL3D;
  const notes = REPORT.notes;
  const err = Number(new URLSearchParams(location.search).get("err") || "0.25");
  try {
    const t0 = performance.now();
    const bmp = await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = "/dem/pl-1025.png";
    });
    const canvas = document.createElement("canvas");
    canvas.width = bmp.naturalWidth; canvas.height = bmp.naturalHeight;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0);
    const px = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    const n = canvas.width;
    const heights = new Float32Array(n * n);
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < n * n; i++) {
      const h = -10000 + (px[4 * i] * 65536 + px[4 * i + 1] * 256 + px[4 * i + 2]) * 0.1;
      heights[i] = h;
      if (h < lo) lo = h;
      if (h > hi) hi = h;
    }
    const t1 = performance.now();
    const martini = new T.Martini(n);
    const mesh = martini.createTile(heights).getMesh(err);
    const nv = mesh.vertices.length / 2;
    const pos = new Float32Array(nv * 3), uv = new Float32Array(nv * 2);
    for (let i = 0; i < nv; i++) {
      const x = mesh.vertices[2 * i], y = mesh.vertices[2 * i + 1];
      pos[3 * i] = x; pos[3 * i + 1] = heights[y * n + x] - lo; pos[3 * i + 2] = y;
      uv[2 * i] = x / (n - 1); uv[2 * i + 1] = 1 - y / (n - 1);
    }
    const geom = new T.BufferGeometry();
    geom.setAttribute("position", new T.BufferAttribute(pos, 3));
    geom.setAttribute("uv", new T.BufferAttribute(uv, 2));
    geom.setIndex(new T.BufferAttribute(mesh.triangles, 1));
    geom.computeVertexNormals();
    const t2 = performance.now();
    geom.boundsTree = new T.MeshBVH(geom);
    T.Mesh.prototype.raycast = T.acceleratedRaycast;
    const t3 = performance.now();
    const tex = await new T.TextureLoader().loadAsync("/tiles/16/36360/22180.jpg");
    tex.colorSpace = T.SRGBColorSpace;
    const scene = new T.Scene();
    scene.background = new T.Color(0x88aacc);
    const ground = new T.Mesh(geom, new T.MeshLambertMaterial({ map: tex }));
    scene.add(ground, new T.AmbientLight(0xffffff, 0.6));
    const sun = new T.DirectionalLight(0xffffff, 1.5);
    sun.position.set(300, 800, 200);
    scene.add(sun);
    const pts = [];
    const ax = 300, bx = 700, zline = 512;
    const ha = heights[zline * n + ax] - lo + 2, hb = heights[zline * n + bx] - lo + 2;
    for (let k = 0; k <= 40; k++) {
      const t = k / 40;
      pts.push(ax + (bx - ax) * t, ha + (hb - ha) * t - 4 * 15 * t * (1 - t), zline);
    }
    const lineGeom = new T.LineGeometry();
    lineGeom.setPositions(pts);
    const lineMat = new T.LineMaterial({ color: 0xff8800, linewidth: 4 });
    lineMat.resolution.set(1000, 700);
    scene.add(new T.Line2(lineGeom, lineMat));
    const gltf = await new T.GLTFLoader().loadAsync("/walker.gltf");
    gltf.scene.position.set(500, ha, zline);
    gltf.scene.scale.setScalar(3);
    scene.add(gltf.scene);
    const renderer = new T.WebGLRenderer({ antialias: true });
    renderer.setSize(1000, 700);
    document.getElementById("c").appendChild(renderer.domElement);
    const camera = new T.PerspectiveCamera(50, 1000 / 700, 1, 20000);
    camera.position.set(512, (hi - lo) + 500, 1500);
    const controls = new T.MapControls(camera, renderer.domElement);
    controls.target.set(512, (hi - lo) / 2, 512);
    controls.update();
    for (let f = 0; f < 10; f++) renderer.render(scene, camera);
    const rc = new T.Raycaster();
    rc.firstHitOnly = true;
    rc.setFromCamera(new T.Vector2(0, 0), camera);
    const t4 = performance.now();
    const hits = rc.intersectObject(ground);
    const t5 = performance.now();
    const gl = renderer.getContext();
    notes.push(`webgl2 ${renderer.capabilities.isWebGL2}; heights ${lo.toFixed(2)}..${hi.toFixed(2)} m decoded in ${(t1 - t0).toFixed(0)} ms`);
    notes.push(`martini ${err} m: ${nv} vertices, ${mesh.triangles.length / 3} triangles in ${(t2 - t1).toFixed(0)} ms; BVH ${(t3 - t2).toFixed(0)} ms`);
    notes.push(`raycast hit ${hits.length ? (hits[0].point.y + lo).toFixed(1) + " m" : "none"} in ${(t5 - t4).toFixed(2)} ms`);
    notes.push(`renderer.info: ${renderer.info.render.triangles} triangles drawn, geometries ${renderer.info.memory.geometries}, textures ${renderer.info.memory.textures}; MAX_TEXTURE_SIZE ${gl.getParameter(gl.MAX_TEXTURE_SIZE)}`);
    finish();
  } catch (e) {
    REPORT.errors.push("test: " + (e && (e.stack || e.message) || e));
    finish();
  }
})();
