import type { Map as MapLibreMap } from 'maplibre-gl';
import { useEffect, useState } from 'react';

import { useMap } from '@/core/map';
import { useDatasets } from '@/shared/queries/gridded/datasets';
import { useTimesteps } from '@/shared/queries/gridded/timesteps';
import { useVariables } from '@/shared/queries/gridded/variables';

import { useDashboard } from '../DashboardContext';
import { SNOW_SOURCE_IDS } from '../utils/layerOrder';

const TILE_EVENTS = ['dataloading', 'data', 'sourcedataabort', 'idle'] as const;

const anySourceLoading = (map: MapLibreMap) =>
  SNOW_SOURCE_IDS.some((id) => {
    try {
      return Boolean(map.getSource(id)) && !map.isSourceLoaded(id);
    } catch {
      // The source was removed between the check and the read.
      return false;
    }
  });

/** Whether any of the snow view's sources still has tiles in flight. */
const useSnowTilesLoading = () => {
  const map = useMap();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!map) return;
    const update = () => setLoading(anySourceLoading(map));
    for (const event of TILE_EVENTS) map.on(event, update);
    return () => {
      for (const event of TILE_EVENTS) map.off(event, update);
    };
  }, [map]);

  return loading;
};

/**
 * What the snow view's map is waiting on: dataset metadata first (the layers
 * can't be built without it), then tiles for the raster, polygons and overlays.
 * Null when everything on screen has loaded.
 */
export const useSnowLoading = (): string | null => {
  const { dataset } = useDashboard().state.mapFilters;
  const datasets = useDatasets();
  const variables = useVariables(dataset);
  const timesteps = useTimesteps(dataset);
  const tilesLoading = useSnowTilesLoading();

  if (datasets.isLoading) return 'Loading datasets…';
  if (variables.isLoading || timesteps.isLoading) return 'Loading dataset details…';
  if (tilesLoading) return 'Loading map tiles…';
  return null;
};
