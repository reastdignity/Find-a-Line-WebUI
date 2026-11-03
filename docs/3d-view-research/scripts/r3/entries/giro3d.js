// Giro3D: a map (planar, metric CRS) or globe with an elevation layer and an orthophoto layer.
import Instance from "@giro3d/giro3d/core/Instance.js";
import Map from "@giro3d/giro3d/entities/Map.js";
import Globe from "@giro3d/giro3d/entities/Globe.js";
import ElevationLayer from "@giro3d/giro3d/core/layer/ElevationLayer.js";
import ColorLayer from "@giro3d/giro3d/core/layer/ColorLayer.js";
import TiledImageSource from "@giro3d/giro3d/sources/TiledImageSource.js";
import WmtsSource from "@giro3d/giro3d/sources/WmtsSource.js";
import WmsSource from "@giro3d/giro3d/sources/WmsSource.js";
import GeoTIFFSource from "@giro3d/giro3d/sources/GeoTIFFSource.js";
import MapboxTerrainFormat from "@giro3d/giro3d/formats/MapboxTerrainFormat.js";
import Extent from "@giro3d/giro3d/core/geographic/Extent.js";
import XYZ from "ol/source/XYZ.js";
import { MapControls } from "three/addons/controls/MapControls.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";

window.FAL3D = {
  Instance, Map, Globe, ElevationLayer, ColorLayer, TiledImageSource, WmtsSource, WmsSource, GeoTIFFSource,
  MapboxTerrainFormat, Extent, XYZ, MapControls, Line2, LineMaterial, LineGeometry,
};
