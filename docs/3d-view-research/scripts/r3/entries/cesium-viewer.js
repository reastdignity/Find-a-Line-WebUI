// The same with the Viewer (Knockout widgets) for comparison.
import { Viewer } from "@cesium/widgets";
import {
  CustomHeightmapTerrainProvider, ArcGISTiledElevationTerrainProvider, UrlTemplateImageryProvider,
  WebMapServiceImageryProvider, WebMapTileServiceImageryProvider, ImageryLayer, Cartesian3, Color,
  CallbackProperty, ScreenSpaceEventHandler, ScreenSpaceEventType, Model,
} from "@cesium/engine";

window.FAL3D = {
  Viewer, CustomHeightmapTerrainProvider, ArcGISTiledElevationTerrainProvider, UrlTemplateImageryProvider,
  WebMapServiceImageryProvider, WebMapTileServiceImageryProvider, ImageryLayer, Cartesian3, Color,
  CallbackProperty, ScreenSpaceEventHandler, ScreenSpaceEventType, Model,
};
