import type { ErrorEvent } from 'maplibre-gl';
import { useEffect } from 'react';

import { useMap } from '@/core/map';
import { ActionTypes, useDashboard } from '@/features/gridded/DashboardContext';

import { GriddedRasterLayer } from './GriddedRasterLayer';
import { OverlayLayers } from './OverlayLayers';
import { PointValueQuery } from './PointValueQuery';
import { PolygonLayer } from './PolygonLayer';

/** Everything the snow view draws on, or handles from, the shared map. */
export const SnowMapLayers = () => {
  const map = useMap();
  const { dispatch } = useDashboard();

  // Tile and source errors (e.g. 404s where a dataset has no data) carry a
  // sourceId and are expected; only surface map-level failures.
  useEffect(() => {
    if (!map) return;
    const onError = (event: ErrorEvent & { sourceId?: string }) => {
      if (event.sourceId) return;
      dispatch({
        type: ActionTypes.SET_ERROR,
        payload: `Map error: ${event.error?.message || 'Unknown error'}`,
      });
    };
    map.on('error', onError);
    return () => {
      map.off('error', onError);
    };
  }, [map, dispatch]);

  return (
    <>
      <OverlayLayers />
      <GriddedRasterLayer />
      <PolygonLayer />
      <PointValueQuery />
    </>
  );
};
