// Which WebGL contexts headless Edge offers, with the renderer and a few limits.
const lines = [];
for (const kind of ["webgl2", "webgl"]) {
  const canvas = document.createElement("canvas");
  let gl = null;
  try { gl = canvas.getContext(kind); } catch (e) { lines.push(`${kind}: throws ${e}`); }
  if (!gl) { lines.push(`${kind}: null`); continue; }
  const dbg = gl.getExtension("WEBGL_debug_renderer_info");
  lines.push(`${kind}: ok; renderer ${dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)}; ` +
    `MAX_TEXTURE_SIZE ${gl.getParameter(gl.MAX_TEXTURE_SIZE)}; ` +
    `ext float tex ${!!(gl.getExtension("OES_texture_float") || gl.getExtension("EXT_color_buffer_float"))}; ` +
    `ext uint32 index ${kind === "webgl2" || !!gl.getExtension("OES_element_index_uint")}`);
}
lines.push(`WebAssembly ${typeof WebAssembly}; createImageBitmap ${typeof createImageBitmap}; OffscreenCanvas ${typeof OffscreenCanvas}`);
document.getElementById("out").textContent = lines.join("\n");
