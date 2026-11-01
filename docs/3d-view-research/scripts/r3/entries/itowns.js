// iTowns: a globe with an elevation layer and WMS/WMTS/TMS colour layers.
import {
  GlobeView, PlanarView, WMTSSource, WMSSource, TMSSource, ColorLayer, ElevationLayer, Coordinates, Extent,
  GeoidLayer,
} from "itowns";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";

window.FAL3D = {
  GlobeView, PlanarView, WMTSSource, WMSSource, TMSSource, ColorLayer, ElevationLayer, Coordinates, Extent,
  GeoidLayer, Line2, LineMaterial, LineGeometry,
};
