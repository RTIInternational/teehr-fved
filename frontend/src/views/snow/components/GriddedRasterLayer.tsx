import { useEffect } from 'react';

import { useMap } from '@/core/map';
import { buildGriddedTileUrl } from '@/shared/api/gridded/tiles';
import { ensureFreshToken } from '@/shared/auth/keycloak';

import { useDashboard } from '../DashboardContext';
import { useCurrentTimestep } from '../hooks/useCurrentTimestep';
import {
  RASTER_LAYER_ID,
  RASTER_SOURCE_ID,
  removeMapResources,
  snowBeforeId,
} from '../utils/layerOrder';

/** The selected dataset's raster tiles for the current timestep and color ramp. */
export const GriddedRasterLayer = () => {
  const map = useMap();
  const { state } = useDashboard();
  const { dataset, variable, colorRamp, colorRampMin, colorRampMax } = state.mapFilters;
  const timestep = useCurrentTimestep();

  useEffect(() => {
    if (!map || !dataset || !variable || !timestep) return;

    const tileUrl = buildGriddedTileUrl(
      dataset,
      variable,
      timestep,
      colorRamp,
      colorRampMin,
      colorRampMax
    );
    let cancelled = false;

    // The shared transformRequest reads the current token synchronously, so
    // refresh it before the first tile request goes out.
    void ensureFreshToken().then(() => {
      if (cancelled) return;
      map.addSource(RASTER_SOURCE_ID, { type: 'raster', tiles: [tileUrl], tileSize: 256 });
      map.addLayer(
        {
          id: RASTER_LAYER_ID,
          type: 'raster',
          source: RASTER_SOURCE_ID,
          paint: { 'raster-opacity': 0.8 },
        },
        snowBeforeId(map, RASTER_LAYER_ID)
      );
    });

    return () => {
      cancelled = true;
      removeMapResources(map, [RASTER_LAYER_ID], [RASTER_SOURCE_ID]);
    };
  }, [map, dataset, variable, timestep, colorRamp, colorRampMin, colorRampMax]);

  return null;
};
