import maplibregl, { type MapMouseEvent } from 'maplibre-gl';
import { useEffect, useEffectEvent, useRef } from 'react';

import { useMap } from '@/core/map';
import { ActionTypes, useDashboard } from '@/features/gridded/DashboardContext';
import { useCurrentTimestep } from '@/features/gridded/hooks/useCurrentTimestep';
import { fetchGriddedEdrPoint } from '@/shared/api/gridded/edr';
import { escapeHtml } from '@/shared/utils/html';

import { POLYGON_FILL_LAYER_ID } from '../utils/layerOrder';

const formatValue = (value: unknown) => {
  if (typeof value === 'number') return value.toFixed(2);
  if (typeof value === 'string') return escapeHtml(value);
  return 'N/A';
};

/**
 * A click on the map (away from polygons, which take precedence) shows the
 * gridded value there and loads its time series.
 */
export const PointValueQuery = () => {
  const map = useMap();
  const { state, dispatch } = useDashboard();
  const { dataset, variable } = state.mapFilters;
  const timestep = useCurrentTimestep();
  // Only the latest click may write its result into the popup.
  const latestRequestRef = useRef(0);

  const queryPoint = useEffectEvent(async (event: MapMouseEvent, popup: maplibregl.Popup) => {
    if (!map) return;
    if (map.getLayer(POLYGON_FILL_LAYER_ID)) {
      const hits = map.queryRenderedFeatures(event.point, { layers: [POLYGON_FILL_LAYER_ID] });
      if (hits.length > 0) {
        popup.remove();
        return;
      }
    }
    if (!dataset || !variable || !timestep) return;

    const { lng, lat } = event.lngLat;
    dispatch({ type: ActionTypes.SET_CLICKED_POINT, payload: { lon: lng, lat, time: timestep } });

    const requestId = ++latestRequestRef.current;
    popup
      .setLngLat([lng, lat])
      .setHTML('<div style="padding:6px; font-size:0.8rem;">Loading…</div>')
      .addTo(map);

    let html: string;
    try {
      const value = await fetchGriddedEdrPoint(dataset, variable, timestep, lng, lat);
      html = `
        <div style="padding:8px; font-size:0.85rem;">
          <div style="font-weight:600; margin-bottom:4px;">${escapeHtml(variable)}</div>
          <div><strong>Value:</strong> ${formatValue(value)}</div>
          <div><strong>Lat:</strong> ${lat.toFixed(4)}</div>
          <div><strong>Lon:</strong> ${lng.toFixed(4)}</div>
          <div style="margin-top:4px; font-size:0.75rem; opacity:0.7;">${escapeHtml(timestep)}</div>
        </div>`;
    } catch (error) {
      console.error('Snow: EDR point query failed', error);
      html =
        '<div style="padding:6px; font-size:0.8rem; color:#dc3545;">Failed to retrieve value.</div>';
    }

    if (requestId !== latestRequestRef.current) return;
    popup.setHTML(html);
  });

  useEffect(() => {
    if (!map) return;

    const popup = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      maxWidth: '280px',
    });
    const onClick = (event: MapMouseEvent) => void queryPoint(event, popup);
    map.on('click', onClick);

    return () => {
      map.off('click', onClick);
      popup.remove();
    };
  }, [map]);

  return null;
};
