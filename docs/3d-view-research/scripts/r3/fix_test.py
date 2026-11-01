import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("""    const [a, b] = await C.sampleTerrainMostDetailed(terrain, [A, B]);
    notes.push(`anchor heights from the terrain ${a.height.toFixed(1)} / ${b.height.toFixed(1)} m`);""",
"""    const height = (c) => 300 + 100 / (1 + Math.exp(-(C.CesiumMath.toDegrees(c.longitude) - 19.756) * 3000))
      + 20 * Math.sin(C.CesiumMath.toDegrees(c.latitude) * 2000);
    const a = { height: height(A) }, b = { height: height(B) };
    try { await C.sampleTerrainMostDetailed(terrain, [A.clone(), B.clone()]); notes.push("sampleTerrainMostDetailed ok"); }
    catch (e) { notes.push("sampleTerrainMostDetailed refuses this provider: " + e.message); }""")
s = s.replace("""    notes.push(`globe.pick at the centre:""", """    const g = widget.scene.globe.getHeight(C.Cartographic.fromDegrees(19.757, 50.156));
    notes.push(`globe.getHeight at a point: ${g === undefined ? "undefined" : g.toFixed(1) + " m"}`);
    notes.push(`globe.pick at the centre:""")
open(p, "w", encoding="utf-8").write(s)
