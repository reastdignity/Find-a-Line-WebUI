// What a 3D view of one line would use from CesiumJS without ion and without the Viewer widgets.
import {
  CesiumWidget, CustomHeightmapTerrainProvider, ArcGISTiledElevationTerrainProvider, EllipsoidTerrainProvider,
  UrlTemplateImageryProvider, WebMapServiceImageryProvider, WebMapTileServiceImageryProvider, ImageryLayer,
  Cartesian3, Cartographic, Color, CallbackProperty, ScreenSpaceEventHandler, ScreenSpaceEventType,
  HeightReference, sampleTerrainMostDetailed, Math as CesiumMath, Model, PolylineGlowMaterialProperty,
  HeadingPitchRange, Rectangle, Credit, Transforms, JulianDate,
} from "@cesium/engine";

window.FAL3D = {
  CesiumWidget, CustomHeightmapTerrainProvider, ArcGISTiledElevationTerrainProvider, EllipsoidTerrainProvider,
  UrlTemplateImageryProvider, WebMapServiceImageryProvider, WebMapTileServiceImageryProvider, ImageryLayer,
  Cartesian3, Cartographic, Color, CallbackProperty, ScreenSpaceEventHandler, ScreenSpaceEventType,
  HeightReference, sampleTerrainMostDetailed, CesiumMath, Model, PolylineGlowMaterialProperty,
  HeadingPitchRange, Rectangle, Credit, Transforms, JulianDate,
};
