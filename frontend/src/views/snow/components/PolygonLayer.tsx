import maplibregl, { type FilterSpecification, type MapLayerMouseEvent } from 'maplibre-gl';
import { FetchSource, PMTiles } from 'pmtiles';
import { useEffect, useEffectEvent } from 'react';

import { pmtilesProtocol, useMap } from '@/core/map';
import { ActionTypes, useDashboard } from '@/features/gridded/DashboardContext';
import { buildPmtilesUrl } from '@/shared/api/gridded/tiles';
import { ensureFreshToken } from '@/shared/auth/keycloak';
import { usePolygonLayers } from '@/shared/queries/gridded/tiles';
import type { PolygonFeatureProps, PolygonFeatures } from '@/shared/types/gridded/tiles';
import { escapeHtml } from '@/shared/utils/html';

import {
  POLYGON_FILL_LAYER_ID,
  POLYGON_OUTLINE_LAYER_ID,
  POLYGON_SELECTED_LAYER_ID,
  POLYGON_SOURCE_ID,
  removeMapResources,
  snowBeforeId,
} from '../utils/layerOrder';

const POLYGON_LAYER_IDS = [
  POLYGON_SELECTED_LAYER_ID,
  POLYGON_OUTLINE_LAYER_ID,
  POLYGON_FILL_LAYER_ID,
];

// Keycloak access tokens are short-lived; keep the archive's headers current.
const TOKEN_REFRESH_MS = 60_000;

const selectedFilter = (id: string | null): FilterSpecification => ['==', 'id', id ?? ''];

const authHeaders = (token: string | null) =>
  new Headers(token ? { Authorization: `Bearer ${token}` } : {});

// A polygon that spans a tile boundary comes back once per tile; keep one per id.
const dedupePolygonFeatures = (features: maplibregl.MapGeoJSONFeature[] = []) => {
  const seen = new Set<unknown>();
  return features.reduce<PolygonFeatures>((acc, feature) => {
    const props = (feature.properties || {}) as PolygonFeatureProps;
    const key = props.id ?? feature.id;
    if (key !== undefined && key !== null) {
      if (seen.has(key)) return acc;
      seen.add(key);
    }
    acc.push(props);
    return acc;
  }, []);
};

const hoverHtml = (features: PolygonFeatures) => {
  const rows = features
    .map(
      (props) => `
        <div style="padding:1px 0;">
          <span style="font-weight:600;">${escapeHtml(props.id ?? 'N/A')}</span>
          <span style="opacity:0.7;"> — ${escapeHtml(props.name ?? 'Unnamed')}</span>
        </div>`
    )
    .join('');
  return `
    <div style="padding:8px; font-size:0.8rem;">
      <div style="font-weight:600; margin-bottom:4px;">
        ${features.length} polygon${features.length === 1 ? '' : 's'} here
      </div>
      ${rows}
      <div style="margin-top:4px; font-size:0.7rem; opacity:0.7;">Click to list attributes</div>
    </div>`;
};

/**
 * The selected polygon archive (pmtiles) with hover and click. A click sends
 * every polygon under the cursor, nested ones included, to the attributes panel.
 */
export const PolygonLayer = () => {
  const map = useMap();
  const { state, dispatch } = useDashboard();
  const { activePolygonLayer, selectedLocation } = state;
  const selectedId = selectedLocation?.primary_location_id ?? null;

  const polygonLayers = usePolygonLayers();
  const layerMeta = polygonLayers.data?.find((layer) => layer.id === activePolygonLayer);

  const currentSelectedId = useEffectEvent(() => selectedId);

  useEffect(() => {
    if (!map || !layerMeta) return;

    const archiveUrl = buildPmtilesUrl(layerMeta.id);
    let fetchSource: FetchSource | null = null;
    let cancelled = false;

    const hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '280px',
    });

    const onHover = (event: MapLayerMouseEvent) => {
      const features = dedupePolygonFeatures(event.features);
      if (features.length === 0) return;
      map.getCanvas().style.cursor = 'pointer';
      hoverPopup.setLngLat(event.lngLat).setHTML(hoverHtml(features)).addTo(map);
    };

    const onLeave = () => {
      map.getCanvas().style.cursor = '';
      hoverPopup.remove();
    };

    const onClick = (event: MapLayerMouseEvent) => {
      const features = dedupePolygonFeatures(event.features);
      if (features.length === 0) return;
      dispatch({
        type: ActionTypes.SET_POLYGON_FEATURES,
        payload: { features, lngLat: { lon: event.lngLat.lng, lat: event.lngLat.lat } },
      });
    };

    // The pmtiles Protocol fetches on its own, bypassing transformRequest, so the
    // archive needs an authenticated FetchSource registered under its exact URL.
    void ensureFreshToken().then((token) => {
      if (cancelled) return;
      fetchSource = new FetchSource(archiveUrl, authHeaders(token));
      pmtilesProtocol.add(new PMTiles(fetchSource));

      const sourceLayer = layerMeta.source_layer;
      map.addSource(POLYGON_SOURCE_ID, { type: 'vector', url: `pmtiles://${archiveUrl}` });
      map.addLayer(
        {
          id: POLYGON_FILL_LAYER_ID,
          type: 'fill',
          source: POLYGON_SOURCE_ID,
          'source-layer': sourceLayer,
          paint: { 'fill-color': '#3388ff', 'fill-opacity': 0.5, 'fill-outline-color': '#1a3d6d' },
        },
        snowBeforeId(map, POLYGON_FILL_LAYER_ID)
      );
      map.addLayer(
        {
          id: POLYGON_OUTLINE_LAYER_ID,
          type: 'line',
          source: POLYGON_SOURCE_ID,
          'source-layer': sourceLayer,
          paint: { 'line-color': '#1a3d6d', 'line-width': 2 },
        },
        snowBeforeId(map, POLYGON_OUTLINE_LAYER_ID)
      );
      map.addLayer(
        {
          id: POLYGON_SELECTED_LAYER_ID,
          type: 'line',
          source: POLYGON_SOURCE_ID,
          'source-layer': sourceLayer,
          filter: selectedFilter(currentSelectedId()),
          paint: { 'line-color': '#dc3545', 'line-width': 3 },
        },
        snowBeforeId(map, POLYGON_SELECTED_LAYER_ID)
      );

      map.on('mousemove', POLYGON_FILL_LAYER_ID, onHover);
      map.on('mouseleave', POLYGON_FILL_LAYER_ID, onLeave);
      map.on('click', POLYGON_FILL_LAYER_ID, onClick);
    });

    const refreshTimer = window.setInterval(() => {
      void ensureFreshToken().then((token) => {
        if (!cancelled && token) fetchSource?.setHeaders(authHeaders(token));
      });
    }, TOKEN_REFRESH_MS);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
      map.off('mousemove', POLYGON_FILL_LAYER_ID, onHover);
      map.off('mouseleave', POLYGON_FILL_LAYER_ID, onLeave);
      map.off('click', POLYGON_FILL_LAYER_ID, onClick);
      hoverPopup.remove();
      map.getCanvas().style.cursor = '';
      removeMapResources(map, POLYGON_LAYER_IDS, [POLYGON_SOURCE_ID]);
    };
  }, [map, layerMeta, dispatch]);

  // Highlight the polygon chosen in the attributes panel.
  useEffect(() => {
    if (!map?.getLayer(POLYGON_SELECTED_LAYER_ID)) return;
    map.setFilter(POLYGON_SELECTED_LAYER_ID, selectedFilter(selectedId));
  }, [map, layerMeta, selectedId]);

  return null;
};
