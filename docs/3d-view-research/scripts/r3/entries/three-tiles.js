// three.js + 3DTilesRendererJS: a globe of streamed terrain tiles (terrain-RGB / terrarium / quantized
// mesh) with WMS/WMTS/XYZ overlays, plus what three-own.js has.
import {
  WebGLRenderer, Scene, PerspectiveCamera, Mesh, BufferGeometry, BufferAttribute, MeshBasicMaterial,
  MeshLambertMaterial, Raycaster, Vector2, Vector3, Color, DirectionalLight, AmbientLight, Group, Clock,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { TilesRenderer, GlobeControls, EnvironmentControls } from "3d-tiles-renderer";
import {
  ImageOverlayPlugin, XYZTilesOverlay, WMSTilesOverlay, WMTSTilesOverlay, TerrariumMeshPlugin,
  TerrainRGBMeshPlugin, QuantizedMeshPlugin, TilesFadePlugin, UpdateOnChangePlugin,
} from "3d-tiles-renderer/plugins";

window.FAL3D = {
  WebGLRenderer, Scene, PerspectiveCamera, Mesh, BufferGeometry, BufferAttribute, MeshBasicMaterial,
  MeshLambertMaterial, Raycaster, Vector2, Vector3, Color, DirectionalLight, AmbientLight, Group, Clock,
  GLTFLoader, Line2, LineMaterial, LineGeometry, TilesRenderer, GlobeControls, EnvironmentControls,
  ImageOverlayPlugin, XYZTilesOverlay, WMSTilesOverlay, WMTSTilesOverlay, TerrariumMeshPlugin,
  TerrainRGBMeshPlugin, QuantizedMeshPlugin, TilesFadePlugin, UpdateOnChangePlugin,
};
