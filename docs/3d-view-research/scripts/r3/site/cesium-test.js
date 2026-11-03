// CesiumWidget without ion: a synthetic heightmap terrain, our cached orthophoto tiles (same origin),
// a sagging polyline updated through a CallbackProperty, a walker point, a one-triangle glTF, picking.
// ?lean=1: no sky box, atmosphere, sun or moon.
(async () => {
  const C = window.FAL3D;
  const query = new URLSearchParams(location.search);
  const lean = query.get("lean") === "1", rrm = query.get("rrm") === "1";
  const started = performance.now();
  const notes = REPORT.notes;
  try {
    const terrain = new C.CustomHeightmapTerrainProvider({
      width: 65, height: 65,
      callback(x, y, level) {
        const r = terrain.tilingScheme.tileXYToRectangle(x, y, level);
        const a = new Float32Array(65 * 65);
        for (let j = 0; j < 65; j++) {
          for (let i = 0; i < 65; i++) {
            const lon = C.CesiumMath.toDegrees(r.west + (r.east - r.west) * i / 64);
            const lat = C.CesiumMath.toDegrees(r.north - (r.north - r.south) * j / 64);
            a[j * 65 + i] = 300 + 100 / (1 + Math.exp(-(lon - 19.756) * 3000)) + 20 * Math.sin(lat * 2000);
          }
        }
        return a;
      },
    });
    const options = { baseLayer: false, terrainProvider: terrain };
    if (lean) Object.assign(options, { skyBox: false, skyAtmosphere: false });
    if (rrm) Object.assign(options, { requestRenderMode: true, maximumRenderTimeChange: Infinity });
    const widget = new C.CesiumWidget("c", options);
    if (lean) { widget.scene.sun = undefined; widget.scene.moon = undefined; }
    notes.push(`webgl2 ${widget.scene.context.webgl2}; lean ${lean}`);
    widget.imageryLayers.add(new C.ImageryLayer(new C.UrlTemplateImageryProvider({
      url: (query.get("xo") === "1" ? `http://localhost:${location.port}` : "") + "/tiles/{z}/{x}/{y}.jpg",
      minimumLevel: 10, maximumLevel: 16,
      rectangle: C.Rectangle.fromDegrees(19.72, 50.15, 19.80, 50.21),
    })));
    const A = C.Cartographic.fromDegrees(19.7535, 50.1559), B = C.Cartographic.fromDegrees(19.7590, 50.1562);
    const height = (c) => 300 + 100 / (1 + Math.exp(-(C.CesiumMath.toDegrees(c.longitude) - 19.756) * 3000))
      + 20 * Math.sin(C.CesiumMath.toDegrees(c.latitude) * 2000);
    const a = { height: height(A) }, b = { height: height(B) };
    try { await C.sampleTerrainMostDetailed(terrain, [A.clone(), B.clone()]); notes.push("sampleTerrainMostDetailed ok"); }
    catch (e) { notes.push("sampleTerrainMostDetailed refuses this provider: " + e.message); }
    let sag = 15;
    const positions = [];
    const update = () => {
      positions.length = 0;
      for (let k = 0; k <= 40; k++) {
        const t = k / 40;
        positions.push(C.Cartesian3.fromRadians(A.longitude + (B.longitude - A.longitude) * t,
          A.latitude + (B.latitude - A.latitude) * t, a.height + (b.height - a.height) * t + 2 - 4 * sag * t * (1 - t)));
      }
    };
    update();
    widget.entities.add({ polyline: { positions: new C.CallbackProperty(() => positions, false), width: 3,
      material: C.Color.ORANGE } });
    widget.entities.add({ position: new C.CallbackProperty(() => positions[20], false),
      point: { pixelSize: 12, color: C.Color.RED } });
    const model = await C.Model.fromGltfAsync({ url: "/walker.gltf",
      modelMatrix: C.Transforms.eastNorthUpToFixedFrame(positions[20]), scale: 3 });
    widget.scene.primitives.add(model);
    widget.camera.setView({ destination: C.Cartesian3.fromDegrees(19.7562, 50.1515, a.height + 400),
      orientation: { heading: 0, pitch: -0.45, roll: 0 } });
    let frames = 0;
    widget.scene.postRender.addEventListener(() => { frames += 1; });
    const done = () => new Promise((resolve) => {
      const check = () => {
        if (rrm) widget.scene.requestRender();
        return widget.scene.globe.tilesLoaded && frames > 30 ? resolve() : setTimeout(check, 250);
      };
      check();
    });
    await done();
    sag = 20; update();  // a live change: the CallbackProperty picks it up next frame
    const ray = widget.camera.getPickRay({ x: 500, y: 350 });
    const hit = widget.scene.globe.pick(ray, widget.scene);
    const g = widget.scene.globe.getHeight(C.Cartographic.fromDegrees(19.757, 50.156));
    notes.push(`globe.getHeight at a point: ${g === undefined ? "undefined" : g.toFixed(1) + " m"}`);
    notes.push(`globe.pick at the centre: ${hit ? C.Cartographic.fromCartesian(hit).height.toFixed(1) + " m" : "none"}`);
    notes.push(`frames rendered ${frames}; model ready ${model.ready}; ${((performance.now() - started) / 1000).toFixed(1)} s to loaded`);
    finish();
  } catch (e) {
    REPORT.errors.push("test: " + (e && (e.stack || e.message) || e));
    finish();
  }
})();
