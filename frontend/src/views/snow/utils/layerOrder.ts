import type { Map as MapLibreMap } from 'maplibre-gl';

import { OVERLAY_LAYERS } from '@/features/gridded/utils/overlayLayers';

export const RASTER_SOURCE_ID = 'snow-raster';
export const RASTER_LAYER_ID = 'snow-raster';
export const POLYGON_SOURCE_ID = 'snow-polygons';
export const POLYGON_FILL_LAYER_ID = 'snow-polygons-fill';
export const POLYGON_OUTLINE_LAYER_ID = 'snow-polygons-outline';
export const POLYGON_SELECTED_LAYER_ID = 'snow-polygons-selected';

/** Bottom-to-top order of the snow view's layers; overlays use their registry ids. */
const SNOW_LAYER_ORDER = [
  ...OVERLAY_LAYERS.map((overlay) => overlay.id),
  RASTER_LAYER_ID,
  POLYGON_FILL_LAYER_ID,
  POLYGON_OUTLINE_LAYER_ID,
  POLYGON_SELECTED_LAYER_ID,
];

/**
 * The layer to insert `layerId` before, so layers land in SNOW_LAYER_ORDER
 * regardless of which one is added first. Undefined means the top of the map.
 */
export const snowBeforeId = (map: MapLibreMap, layerId: string) => {
  const index = SNOW_LAYER_ORDER.indexOf(layerId);
  if (index === -1) return undefined;
  return SNOW_LAYER_ORDER.slice(index + 1).find((id) => map.getLayer(id));
};

/** Removes layers, then sources, that are still on the map; safe once the map is gone. */
export const removeMapResources = (map: MapLibreMap, layerIds: string[], sourceIds: string[]) => {
  try {
    for (const id of layerIds) if (map.getLayer(id)) map.removeLayer(id);
    for (const id of sourceIds) if (map.getSource(id)) map.removeSource(id);
  } catch {
    // The map was removed first (the whole app unmounted); nothing left to clean.
  }
};
