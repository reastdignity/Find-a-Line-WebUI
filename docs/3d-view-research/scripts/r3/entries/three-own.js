// three.js for a single patch of our own DEM draped with our orthophoto: mesh, controls, a fat line,
// a glTF walker, picking with a BVH, meshing with martini.
import {
  WebGLRenderer, Scene, PerspectiveCamera, Mesh, BufferGeometry, BufferAttribute, MeshBasicMaterial,
  MeshLambertMaterial, TextureLoader, Raycaster, Vector2, Vector3, Color, DirectionalLight, AmbientLight,
  Group, SRGBColorSpace, CanvasTexture, Sprite, SpriteMaterial, Clock,
} from "three";
import { MapControls } from "three/addons/controls/MapControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { MeshBVH, acceleratedRaycast, computeBoundsTree, disposeBoundsTree } from "three-mesh-bvh";
import Martini from "@mapbox/martini";

window.FAL3D = {
  WebGLRenderer, Scene, PerspectiveCamera, Mesh, BufferGeometry, BufferAttribute, MeshBasicMaterial,
  MeshLambertMaterial, TextureLoader, Raycaster, Vector2, Vector3, Color, DirectionalLight, AmbientLight,
  Group, SRGBColorSpace, CanvasTexture, Sprite, SpriteMaterial, Clock,
  MapControls, GLTFLoader, Line2, LineMaterial, LineGeometry,
  MeshBVH, acceleratedRaycast, computeBoundsTree, disposeBoundsTree, Martini,
};
