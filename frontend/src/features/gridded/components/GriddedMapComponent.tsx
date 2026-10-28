import type { Feature, Point } from 'geojson';
import maplibregl from 'maplibre-gl';
import { FetchSource, PMTiles, Protocol } from 'pmtiles';
import { useEffect, useRef, useCallback, useState, type Dispatch } from 'react';

import 'maplibre-gl/dist/maplibre-gl.css';
import {
  ActionTypes as ForecastActionTypes,
  type DashboardState as ForecastDashboardState,
} from '@/features/forecast/DashboardContext';
import { GRIDDED_API_BASE_URL } from '@/shared/api/gridded/client';
import { fetchGriddedEdrPoint } from '@/shared/api/gridded/edr';
import { buildGriddedTileUrl, buildPmtilesUrl } from '@/shared/api/gridded/tiles';
import { ensureFreshToken } from '@/shared/auth/keycloak';
import { usePolygonLayers, useTilesLegend } from '@/shared/queries/gridded/tiles';
import { useMetricLocations } from '@/shared/queries/metrics';
import type { PolygonFeatureProps, PolygonFeatures } from '@/shared/types/gridded/tiles';
import type { MapLocation } from '@/shared/types/locations';
import type { MapViewport } from '@/shared/types/maps';
import { getMetricColorExpression, getMetricLabel, isLngLatTuple } from '@/shared/utils/mapMetrics';

import { useDashboard, ActionTypes } from '../DashboardContext';
import { useCurrentTimestep } from '../hooks/useCurrentTimestep';
import { OVERLAY_LAYERS } from '../utils/overlayLayers';
import GriddedColorBar from './GriddedColorBar';

// The pmtiles Protocol issues its own fetches, so maplibre's transformRequest
// never sees them — the archive's bearer token has to be attached to a
// FetchSource registered here instead. Protocol.add keys the source by its
// exact URL and silently falls back to an unauthenticated fetch on a mismatch,
// so the registered URL and the pmtiles:// source URL must agree byte for byte.
const pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', pmtilesProtocol.tile);

type ArcGisLegendEntry = {
  label: string;
  imageData: string;
  contentType: string;
  width: number;
  height: number;
};

type ArcGisLegendResponse = {
  layers?: Array<{
    layerId: number;
    legend?: ArcGisLegendEntry[];
  }>;
};

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

const escapeHtml = (value: unknown): string =>
  String(value).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c] ?? c);

const POLYGON_LAYER_ID = 'polygon-layer';
const POLYGON_SOURCE_ID = 'polygon-source';
const POLYGON_SELECTED_LAYER_ID = 'polygon-layer-selected';

const viewportSignature = (viewport: MapViewport | null) => {
  if (!viewport) return null;
  return `${viewport.center[0].toFixed(5)}:${viewport.center[1].toFixed(5)}:${viewport.zoom.toFixed(3)}`;
};

const normalizeViewport = (viewport: MapViewport): MapViewport => {
  return {
    center: [Number(viewport.center[0].toFixed(5)), Number(viewport.center[1].toFixed(5))],
    zoom: Number(viewport.zoom.toFixed(3)),
  };
};

// A polygon that spans a tile boundary is split across tiles, so the same feature
// can come back once per tile. Collapse those down to one entry per location id.
const dedupePolygonFeatures = (features?: maplibregl.MapGeoJSONFeature[]) => {
  const seen = new Set();
  return (features || []).reduce<PolygonFeatures>((acc, feature) => {
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

type GriddedMapComponentProps = {
  mode?: 'snow' | 'streamflow';
  showLegend?: boolean;
  streamflow?: {
    state: ForecastDashboardState;
    dispatch: Dispatch<any>;
    table: string;
    selectedLocation: MapLocation | null;
    selectLocation: (location: MapLocation | null) => void;
  };
};

const GriddedMapComponent = ({
  mode = 'snow',
  showLegend = true,
  streamflow,
}: GriddedMapComponentProps) => {
  const { state, dispatch } = useDashboard();
  const {
    mapFilters,
    mapViewport,
    mapLoaded,
    activeOverlays,
    activePolygonLayer,
    selectedLocation,
  } = state;
  const { dataset, variable, colorRamp, colorRampMin, colorRampMax } = mapFilters;

  const streamflowState = streamflow?.state;
  const streamflowDispatch = streamflow?.dispatch;
  const streamflowSelectedLocation = streamflow?.selectedLocation ?? null;
  const streamflowSelectLocation = streamflow?.selectLocation;
  const streamflowTable = streamflow?.table;
  const isStreamflow = mode === 'streamflow' && !!streamflowState && !!streamflowDispatch;
  const activeViewport = isStreamflow ? streamflowState.mapViewport : mapViewport;
  const activeMapLoaded = isStreamflow ? (streamflowState?.mapLoaded ?? false) : mapLoaded;

  const streamflowFilters =
    isStreamflow &&
    streamflowState?.mapFilters.configuration &&
    streamflowState?.mapFilters.variable
      ? {
          table: streamflowTable ?? 'fcst_metrics_by_location',
          configuration: streamflowState.mapFilters.configuration,
          variable: streamflowState.mapFilters.variable,
        }
      : undefined;

  const streamflowLocations = useMetricLocations(streamflowFilters);

  const polygonLayers = usePolygonLayers();
  const currentTimestep = useCurrentTimestep();

  const mapContainer = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popup = useRef<maplibregl.Popup | null>(null);
  const griddedDispatchRef = useRef(dispatch);
  const streamflowDispatchRef = useRef(streamflowDispatch);
  const latestViewportRef = useRef<MapViewport | null>(activeViewport ?? null);
  const isApplyingViewportRef = useRef(false);
  const lastStreamflowAutoFitDataKeyRef = useRef<string | null>(null);
  // Separate popup for polygon hover so it never clobbers the click popup
  const hoverPopup = useRef<maplibregl.Popup | null>(null);
  // Holds the current Bearer token for synchronous use inside transformRequest
  const tokenRef = useRef<string | null>(null);
  // The active archive's FetchSource, so a refreshed token can be pushed into
  // its headers without tearing the source down.
  const polygonFetchSource = useRef<FetchSource | null>(null);
  // Track the click handler so it can be removed when dependencies change
  const clickHandlerRef = useRef<((e: maplibregl.MapMouseEvent) => void | Promise<void>) | null>(
    null
  );

  const removeStreamflowArtifacts = useCallback((mapInstance: maplibregl.Map) => {
    if (mapInstance.getLayer('locations-layer')) mapInstance.removeLayer('locations-layer');
    if (mapInstance.getLayer('locations-selected')) mapInstance.removeLayer('locations-selected');
    if (mapInstance.getSource('locations')) mapInstance.removeSource('locations');
    popup.current?.remove();
  }, []);

  const removeSnowArtifacts = useCallback((mapInstance: maplibregl.Map) => {
    if (clickHandlerRef.current) {
      mapInstance.off('click', clickHandlerRef.current);
      clickHandlerRef.current = null;
    }

    if (mapInstance.getLayer('gridded-layer')) mapInstance.removeLayer('gridded-layer');
    if (mapInstance.getSource('gridded-tiles')) mapInstance.removeSource('gridded-tiles');

    OVERLAY_LAYERS.forEach(({ id }) => {
      if (mapInstance.getLayer(id)) mapInstance.removeLayer(id);
      if (mapInstance.getSource(id)) mapInstance.removeSource(id);
    });

    if (mapInstance.getLayer(POLYGON_SELECTED_LAYER_ID))
      mapInstance.removeLayer(POLYGON_SELECTED_LAYER_ID);
    if (mapInstance.getLayer(`${POLYGON_LAYER_ID}-outline`))
      mapInstance.removeLayer(`${POLYGON_LAYER_ID}-outline`);
    if (mapInstance.getLayer(POLYGON_LAYER_ID)) mapInstance.removeLayer(POLYGON_LAYER_ID);
    if (mapInstance.getSource(POLYGON_SOURCE_ID)) mapInstance.removeSource(POLYGON_SOURCE_ID);

    hoverPopup.current?.remove();
    polygonFetchSource.current = null;
  }, []);

  // Prime the token so a polygon layer selected before the first tile load
  // still builds its FetchSource with an Authorization header.
  useEffect(() => {
    griddedDispatchRef.current = dispatch;
    streamflowDispatchRef.current = streamflowDispatch;
  }, [dispatch, streamflowDispatch]);

  useEffect(() => {
    void ensureFreshToken().then((token) => {
      tokenRef.current = token;
    });
  }, []);

  // Map of overlay id -> array of { label, imageData, contentType, width, height }
  const [overlayLegends, setOverlayLegends] = useState<Record<string, ArcGisLegendEntry[]>>({});
  const [styleReadyVersion, setStyleReadyVersion] = useState(0);
  const fetchedLegends = useRef<Set<string>>(new Set());
  const streamflowStyleWaitMapRef = useRef<maplibregl.Map | null>(null);

  const tilesLegend = useTilesLegend(dataset, variable, colorRamp, colorRampMin, colorRampMax);

  useEffect(() => {
    latestViewportRef.current = activeViewport ?? null;
  }, [activeViewport]);

  // Fetch ArcGIS legend JSON for newly-activated overlays that declare a legendUrl.
  useEffect(() => {
    const toFetch = OVERLAY_LAYERS.filter(
      (o) => activeOverlays.includes(o.id) && o.legendUrl && !fetchedLegends.current.has(o.id)
    );
    if (toFetch.length === 0) return;

    toFetch.forEach(async (overlay) => {
      fetchedLegends.current.add(overlay.id);
      const legendUrl = overlay.legendUrl;
      if (!legendUrl) return;
      try {
        const res = await fetch(legendUrl);
        const json: ArcGisLegendResponse = await res.json();
        const layer = json.layers?.find((l) => l.layerId === overlay.legendLayerId);
        const legendEntries = layer?.legend;
        if (legendEntries) {
          setOverlayLegends((prev) => ({ ...prev, [overlay.id]: legendEntries }));
        }
      } catch {
        // Legend fetch failure is non-critical; silently skip.
      }
    });
  }, [activeOverlays]);

  // Initialize map once on mount
  useEffect(() => {
    if (map.current || !mapContainer.current) return;

    const initialViewport = latestViewportRef.current
      ? normalizeViewport(latestViewportRef.current)
      : null;

    const mapInstance = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {},
        layers: [],
      },
      ...(initialViewport
        ? {
            center: initialViewport.center,
            zoom: initialViewport.zoom,
          }
        : {
            // Reclamation regions' extent
            bounds: [
              [-124.8, 25.8],
              [-93.5, 49.0],
            ] as [[number, number], [number, number]],
          }),
      attributionControl: false,
      // Add the Bearer token to every tile request aimed at the xpublish-api.
      // transformRequest is synchronous — tokenRef is kept current by updateTileLayer.
      transformRequest: (url: string) => {
        if (url.startsWith(GRIDDED_API_BASE_URL)) {
          const token = tokenRef.current;
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
    });
    map.current = mapInstance;

    popup.current = new maplibregl.Popup({
      closeButton: true,
      closeOnClick: false,
      maxWidth: '280px',
    });

    hoverPopup.current = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '280px',
    });

    mapInstance.on('load', () => {
      mapInstance.addSource('osm', {
        type: 'raster',
        tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
        tileSize: 256,
      });
      mapInstance.addLayer({ id: 'osm', type: 'raster', source: 'osm' });

      setStyleReadyVersion((version) => version + 1);

      griddedDispatchRef.current({ type: ActionTypes.SET_MAP_LOADED, payload: true });
      if (streamflowDispatchRef.current) {
        streamflowDispatchRef.current({ type: ForecastActionTypes.SET_MAP_LOADED, payload: true });
      }
    });

    const handleStyleData = () => {
      if (mapInstance.isStyleLoaded()) {
        setStyleReadyVersion((version) => version + 1);
      }
    };

    mapInstance.on('styledata', handleStyleData);

    mapInstance.on('moveend', () => {
      if (isApplyingViewportRef.current) {
        isApplyingViewportRef.current = false;
        return;
      }

      const center = mapInstance.getCenter();
      const nextViewport = normalizeViewport({
        center: [center.lng, center.lat],
        zoom: mapInstance.getZoom(),
      });

      if (viewportSignature(latestViewportRef.current) === viewportSignature(nextViewport)) {
        return;
      }

      latestViewportRef.current = nextViewport;
      griddedDispatchRef.current({ type: ActionTypes.SET_MAP_VIEWPORT, payload: nextViewport });
      if (streamflowDispatchRef.current) {
        streamflowDispatchRef.current({
          type: ForecastActionTypes.SET_MAP_VIEWPORT,
          payload: nextViewport,
        });
      }
    });

    mapInstance.on('error', (e: maplibregl.ErrorEvent) => {
      console.error('GriddedMapComponent: MapLibre error:', e);
      // e.sourceId is set for tile/source errors (e.g. 404 for areas with no data); only surface fatal map errors.
      const sourceId = (e as { sourceId?: string }).sourceId;
      if (!sourceId) {
        griddedDispatchRef.current({
          type: ActionTypes.SET_ERROR,
          payload: `Map error: ${e.error?.message || 'Unknown error'}`,
        });
      }
    });

    return () => {
      mapInstance.off('styledata', handleStyleData);
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance || !activeMapLoaded || !activeViewport) return;

    const currentViewport = normalizeViewport({
      center: [mapInstance.getCenter().lng, mapInstance.getCenter().lat],
      zoom: mapInstance.getZoom(),
    });
    const targetViewport = normalizeViewport(activeViewport);

    if (viewportSignature(currentViewport) === viewportSignature(targetViewport)) {
      return;
    }

    isApplyingViewportRef.current = true;
    latestViewportRef.current = targetViewport;
    mapInstance.jumpTo({ center: targetViewport.center, zoom: targetViewport.zoom });
  }, [activeMapLoaded, activeViewport]);

  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance || !activeMapLoaded) return;

    if (isStreamflow) {
      removeSnowArtifacts(mapInstance);
      return;
    }

    removeStreamflowArtifacts(mapInstance);
  }, [activeMapLoaded, isStreamflow, removeSnowArtifacts, removeStreamflowArtifacts]);

  useEffect(() => {
    if (!isStreamflow || !streamflowState || !streamflowSelectLocation) return;

    const mapInstance = map.current;
    if (!mapInstance || !activeMapLoaded) return;
    if (!mapInstance.isStyleLoaded()) {
      if (streamflowStyleWaitMapRef.current === mapInstance) {
        return;
      }

      streamflowStyleWaitMapRef.current = mapInstance;

      const handleIdle = () => {
        streamflowStyleWaitMapRef.current = null;
        setStyleReadyVersion((version) => version + 1);
      };

      void mapInstance.once('idle', handleIdle);

      return () => {
        mapInstance.off('idle', handleIdle);
        if (streamflowStyleWaitMapRef.current === mapInstance) {
          streamflowStyleWaitMapRef.current = null;
        }
      };
    }

    streamflowStyleWaitMapRef.current = null;

    const metricName = streamflowState.mapFilters.metricName ?? 'relative_bias';
    const features = streamflowLocations.data?.features ?? [];

    const handleLocationClick = (e: maplibregl.MapLayerMouseEvent) => {
      if (!e.features || e.features.length === 0) return;
      const feature = e.features[0] as Feature<Point>;
      if (!feature.properties || !feature.geometry?.coordinates) return;
      if (!isLngLatTuple(feature.geometry.coordinates)) return;

      const coordinates = feature.geometry.coordinates;
      streamflowSelectLocation({
        primary_location_id: String(feature.properties.primary_location_id ?? ''),
        secondary_location_id: String(feature.properties.secondary_location_id ?? ''),
        name: String(feature.properties.name ?? ''),
        coordinates,
      });
    };

    const handleLocationHover = (e: maplibregl.MapLayerMouseEvent) => {
      mapInstance.getCanvas().style.cursor = 'pointer';
      if (!e.features?.length) return;
      const feature = e.features[0] as Feature<Point>;
      const coordinates = feature.geometry.coordinates;
      const properties = feature.properties;

      if (!properties || !streamflowState.mapFilters.metricName || !isLngLatTuple(coordinates))
        return;

      const metricValue =
        properties[streamflowState.mapFilters.metricName as keyof typeof properties];
      const metricLabel = getMetricLabel(streamflowState.mapFilters.metricName);

      popup.current
        ?.setLngLat(coordinates)
        .setHTML(
          `
          <div style="padding: 8px; font-size: 0.85rem;">
            <div style="font-weight: 600; margin-bottom: 4px; color: #495057;">${escapeHtml(properties.name ?? 'Unnamed location')}</div>
            <div style="margin: 2px 0;"><strong>ID:</strong> ${escapeHtml(properties.primary_location_id ?? 'N/A')}</div>
            <div style="margin: 2px 0;"><strong>Lat:</strong> ${coordinates[1].toFixed(4)}</div>
            <div style="margin: 2px 0;"><strong>Lon:</strong> ${coordinates[0].toFixed(4)}</div>
            <div style="margin: 2px 0;"><strong>${escapeHtml(metricLabel)}:</strong> ${metricValue !== null && metricValue !== undefined ? Number(metricValue).toFixed(3) : 'N/A'}</div>
            <div style="margin-top: 4px; font-size: 0.75rem; color: #6c757d;">Click to select</div>
          </div>
        `
        )
        .addTo(mapInstance);
    };

    const handleLocationLeave = () => {
      mapInstance.getCanvas().style.cursor = '';
      popup.current?.remove();
    };

    removeStreamflowArtifacts(mapInstance);

    if (features.length === 0) {
      return;
    }

    mapInstance.addSource('locations', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features,
      },
    });

    const colorExpression = getMetricColorExpression(metricName);

    mapInstance.addLayer({
      id: 'locations-layer',
      type: 'circle',
      source: 'locations',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 6, 8, 9, 12, 12],
        'circle-color': colorExpression,
        'circle-stroke-width': 1,
        'circle-stroke-color': 'black',
        'circle-opacity': 0.8,
      },
    });

    mapInstance.addLayer({
      id: 'locations-selected',
      type: 'circle',
      source: 'locations',
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 8, 8, 11, 12, 14],
        'circle-color': colorExpression,
        'circle-stroke-width': 2,
        'circle-stroke-color': 'black',
        'circle-opacity': 1,
      },
      filter: ['==', 'primary_location_id', streamflowSelectedLocation?.primary_location_id ?? ''],
    });

    mapInstance.on('click', 'locations-layer', handleLocationClick);
    mapInstance.on('mouseenter', 'locations-layer', handleLocationHover);
    mapInstance.on('mouseleave', 'locations-layer', handleLocationLeave);

    const hasExternalViewport = !!streamflowState.mapViewport;
    const dataVersionKey = String(streamflowLocations.dataUpdatedAt);

    if (!hasExternalViewport && lastStreamflowAutoFitDataKeyRef.current !== dataVersionKey) {
      const lons = features.map((f) => f.geometry?.coordinates?.[0]).filter(Number.isFinite);
      const lats = features.map((f) => f.geometry?.coordinates?.[1]).filter(Number.isFinite);

      if (lons.length > 0 && lats.length > 0) {
        const minLon = Math.min(...lons);
        const maxLon = Math.max(...lons);
        const minLat = Math.min(...lats);
        const maxLat = Math.max(...lats);

        if (isFinite(minLon) && isFinite(minLat) && isFinite(maxLon) && isFinite(maxLat)) {
          lastStreamflowAutoFitDataKeyRef.current = dataVersionKey;
          mapInstance.fitBounds(
            [
              [minLon, minLat],
              [maxLon, maxLat],
            ],
            { padding: 50, duration: 700, maxZoom: 14 }
          );
        }
      }
    }

    return () => {
      const currentMap = map.current;
      if (!currentMap || currentMap !== mapInstance) return;

      try {
        if (currentMap.getLayer('locations-layer')) {
          currentMap.off('click', 'locations-layer', handleLocationClick);
          currentMap.off('mouseenter', 'locations-layer', handleLocationHover);
          currentMap.off('mouseleave', 'locations-layer', handleLocationLeave);
        }
      } catch {
        // The map can be disposed between effect scheduling and cleanup.
      }
    };
  }, [
    activeMapLoaded,
    isStreamflow,
    styleReadyVersion,
    streamflowLocations.data,
    streamflowLocations.dataUpdatedAt,
    streamflowSelectedLocation?.primary_location_id,
    streamflowSelectLocation,
    streamflowState,
    removeStreamflowArtifacts,
  ]);

  useEffect(() => {
    if (!isStreamflow) return;
    const mapInstance = map.current;
    if (!mapInstance || !activeMapLoaded || !mapInstance.isStyleLoaded()) return;
    if (!mapInstance.getLayer('locations-selected')) return;

    mapInstance.setFilter('locations-selected', [
      '==',
      'primary_location_id',
      streamflowSelectedLocation?.primary_location_id ?? '',
    ]);
  }, [
    activeMapLoaded,
    isStreamflow,
    styleReadyVersion,
    streamflowSelectedLocation?.primary_location_id,
  ]);

  // Update the gridded tile layer when filters change
  const updateTileLayer = useCallback(async () => {
    const mapInstance = map.current;
    if (!mapInstance || !mapLoaded || isStreamflow) return;

    // Remove previous layer and source
    if (mapInstance.getLayer('gridded-layer')) mapInstance.removeLayer('gridded-layer');
    if (mapInstance.getSource('gridded-tiles')) mapInstance.removeSource('gridded-tiles');

    if (!dataset || !variable || !currentTimestep) return;

    // Refresh the token before issuing tile requests so transformRequest has a current value.
    tokenRef.current = await ensureFreshToken();
    // transformRequest does not cover pmtiles, so push the refreshed token into
    // the archive's own source as well.
    if (tokenRef.current && polygonFetchSource.current) {
      polygonFetchSource.current.setHeaders(
        new Headers({ Authorization: `Bearer ${tokenRef.current}` })
      );
    }

    const tileUrl = buildGriddedTileUrl(
      dataset,
      variable,
      currentTimestep,
      colorRamp,
      colorRampMin,
      colorRampMax
    );

    mapInstance.addSource('gridded-tiles', {
      type: 'raster',
      tiles: [tileUrl],
      tileSize: 256,
    });

    mapInstance.addLayer({
      id: 'gridded-layer',
      type: 'raster',
      source: 'gridded-tiles',
      paint: { 'raster-opacity': 0.8 },
    });
  }, [
    mapLoaded,
    dataset,
    variable,
    currentTimestep,
    colorRamp,
    colorRampMin,
    colorRampMax,
    isStreamflow,
  ]);

  useEffect(() => {
    void updateTileLayer();
  }, [updateTileLayer]);

  // Sync external overlay layers to the map whenever the active set changes.
  // Overlays are inserted below gridded-layer so the primary data renders on top.
  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance || !mapLoaded || isStreamflow) return;

    OVERLAY_LAYERS.forEach(({ id, sourceConfig, layerConfig }) => {
      const isActive = activeOverlays.includes(id);
      const hasLayer = !!mapInstance.getLayer(id);
      const hasSource = !!mapInstance.getSource(id);

      if (isActive && !hasLayer) {
        if (!hasSource) {
          mapInstance.addSource(id, sourceConfig as maplibregl.SourceSpecification);
        }
        const beforeId = mapInstance.getLayer('gridded-layer') ? 'gridded-layer' : undefined;
        mapInstance.addLayer(
          { id, source: id, ...(layerConfig as object) } as maplibregl.LayerSpecification,
          beforeId
        );
      } else if (!isActive && hasLayer) {
        mapInstance.removeLayer(id);
        if (hasSource) mapInstance.removeSource(id);
      }
    });
  }, [mapLoaded, activeOverlays, isStreamflow]);

  // Sync polygon layer from pmtiles when activePolygonLayer changes
  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance || !mapLoaded || isStreamflow) return;

    const polygonLayerId = POLYGON_LAYER_ID;
    const polygonSourceId = POLYGON_SOURCE_ID;

    // Hover shows every polygon under the cursor, so nested features are visible
    // before committing to a click.
    const handlePolygonHover = (e: maplibregl.MapLayerMouseEvent) => {
      const features = dedupePolygonFeatures(e.features);
      if (features.length === 0) return;

      mapInstance.getCanvas().style.cursor = 'pointer';

      const rows = features
        .map(
          (props) => `
            <div style="padding:1px 0;">
              <span style="font-weight:600;">${escapeHtml(props.id ?? 'N/A')}</span>
              <span style="color:#6c757d;"> — ${escapeHtml(props.name ?? 'Unnamed')}</span>
            </div>
          `
        )
        .join('');

      if (hoverPopup.current) {
        hoverPopup.current
          .setLngLat(e.lngLat)
          .setHTML(`
          <div style="padding:8px; font-size:0.8rem;">
            <div style="font-weight:600; margin-bottom:4px; color:#495057;">
              ${features.length} polygon${features.length === 1 ? '' : 's'} here
            </div>
            ${rows}
            <div style="margin-top:4px; font-size:0.7rem; color:#6c757d;">Click to list attributes</div>
          </div>
        `)
          .addTo(mapInstance);
      }
    };

    const handlePolygonLeave = () => {
      mapInstance.getCanvas().style.cursor = '';
      if (hoverPopup.current) hoverPopup.current.remove();
    };

    const removePolygonLayer = () => {
      const polygonOutlineLayerId = `${polygonLayerId}-outline`;

      polygonFetchSource.current = null;
      hoverPopup.current?.remove();

      if (mapInstance.getLayer(POLYGON_SELECTED_LAYER_ID)) {
        mapInstance.removeLayer(POLYGON_SELECTED_LAYER_ID);
      }
      if (mapInstance.getLayer(polygonOutlineLayerId)) {
        mapInstance.removeLayer(polygonOutlineLayerId);
      }
      if (mapInstance.getLayer(polygonLayerId)) {
        mapInstance.removeLayer(polygonLayerId);
      }
      if (mapInstance.getSource(polygonSourceId)) {
        mapInstance.removeSource(polygonSourceId);
      }
    };

    if (!activePolygonLayer) {
      removePolygonLayer();
      return;
    }

    // Find the layer metadata
    const selectedLayer = polygonLayers.data?.find((l) => l.id === activePolygonLayer);
    if (!selectedLayer) {
      removePolygonLayer();
      return;
    }

    try {
      // Remove old layer/source if they exist
      removePolygonLayer();

      // Register an authenticated source before adding it to the map: on a
      // cache miss the Protocol would otherwise build a plain unauthenticated
      // FetchSource for this URL and every range request would 401.
      const archiveUrl = buildPmtilesUrl(selectedLayer.id);
      const headers = new Headers();
      if (tokenRef.current) headers.set('Authorization', `Bearer ${tokenRef.current}`);
      const fetchSource = new FetchSource(archiveUrl, headers);
      polygonFetchSource.current = fetchSource;
      pmtilesProtocol.add(new PMTiles(fetchSource));

      mapInstance.addSource(polygonSourceId, {
        type: 'vector',
        url: `pmtiles://${archiveUrl}`,
      });

      // Add layer with semi-transparent blue fill and dark outline
      mapInstance.addLayer({
        id: polygonLayerId,
        type: 'fill',
        source: polygonSourceId,
        'source-layer': selectedLayer.source_layer,
        paint: {
          'fill-color': '#3388ff',
          'fill-opacity': 0.5,
          'fill-outline-color': '#1a3d6d',
        },
      });

      // Add an outline layer on top for better visibility
      mapInstance.addLayer({
        id: `${polygonLayerId}-outline`,
        type: 'line',
        source: polygonSourceId,
        'source-layer': selectedLayer.source_layer,
        paint: {
          'line-color': '#1a3d6d',
          'line-width': 2,
        },
      });

      // Highlight for the polygon chosen in the attributes panel. The filter is
      // set to match nothing until a selection is made.
      mapInstance.addLayer({
        id: POLYGON_SELECTED_LAYER_ID,
        type: 'line',
        source: polygonSourceId,
        'source-layer': selectedLayer.source_layer,
        filter: ['==', 'id', ''],
        paint: {
          'line-color': '#dc3545',
          'line-width': 3,
        },
      });

      mapInstance.on('mousemove', polygonLayerId, handlePolygonHover);
      mapInstance.on('mouseleave', polygonLayerId, handlePolygonLeave);
    } catch (err) {
      console.error('GriddedMapComponent: Failed to load polygon layer:', err);
    }

    return () => {
      mapInstance.off('mousemove', polygonLayerId, handlePolygonHover);
      mapInstance.off('mouseleave', polygonLayerId, handlePolygonLeave);
      hoverPopup.current?.remove();
    };
  }, [mapLoaded, activePolygonLayer, polygonLayers.data, isStreamflow]);

  // Keep the highlight layer in sync with the polygon chosen in the panel
  useEffect(() => {
    const mapInstance = map.current;
    if (
      !mapInstance ||
      !mapLoaded ||
      isStreamflow ||
      !mapInstance.getLayer(POLYGON_SELECTED_LAYER_ID)
    )
      return;

    mapInstance.setFilter(POLYGON_SELECTED_LAYER_ID, [
      '==',
      'id',
      selectedLocation?.primary_location_id ?? '',
    ]);
  }, [mapLoaded, selectedLocation, activePolygonLayer, isStreamflow]);

  // Update EDR click handler when active filters change
  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance || !mapLoaded || isStreamflow) return;

    // Remove previous click handler
    if (clickHandlerRef.current) {
      mapInstance.off('click', clickHandlerRef.current);
    }

    const handleClick = async (e: maplibregl.MapMouseEvent) => {
      const popupInstance = popup.current;
      if (!popupInstance) return;

      const { lng, lat } = e.lngLat;

      // Polygons take precedence over the gridded query. Every polygon under the
      // click — including nested ones — goes to the attributes panel.
      if (activePolygonLayer) {
        const features = mapInstance.queryRenderedFeatures(e.point, {
          layers: [POLYGON_LAYER_ID],
        });
        if (features.length > 0) {
          popupInstance.remove();
          dispatch({
            type: ActionTypes.SET_POLYGON_FEATURES,
            payload: {
              features: dedupePolygonFeatures(features),
              lngLat: { lon: lng, lat },
            },
          });
          return;
        }
      }

      // Otherwise, query the gridded data if available
      if (!dataset || !variable || !currentTimestep) return;

      dispatch({
        type: ActionTypes.SET_CLICKED_POINT,
        payload: { lon: lng, lat, time: currentTimestep },
      });

      popupInstance
        .setLngLat([lng, lat])
        .setHTML('<div style="padding:6px; font-size:0.8rem;">Loading…</div>')
        .addTo(mapInstance);

      try {
        const value = await fetchGriddedEdrPoint(dataset, variable, currentTimestep, lng, lat);
        popupInstance.setHTML(`
          <div style="padding:8px; font-size:0.85rem;">
            <div style="font-weight:600; margin-bottom:4px; color:#495057;">${escapeHtml(variable)}</div>
            <div><strong>Value:</strong> ${value !== null && value !== undefined ? (typeof value === 'number' ? value.toFixed(2) : escapeHtml(value)) : 'N/A'}</div>
            <div><strong>Lat:</strong> ${lat.toFixed(4)}</div>
            <div><strong>Lon:</strong> ${lng.toFixed(4)}</div>
            <div style="margin-top:4px; font-size:0.75rem; color:#6c757d;">${escapeHtml(currentTimestep)}</div>
          </div>
        `);
      } catch (err) {
        console.error('GriddedMapComponent: EDR point query failed:', err);
        popupInstance.setHTML(
          '<div style="padding:6px; font-size:0.8rem; color:#dc3545;">Failed to retrieve value.</div>'
        );
      }
    };

    clickHandlerRef.current = handleClick;
    mapInstance.on('click', handleClick);

    return () => {
      if (mapInstance && clickHandlerRef.current) {
        mapInstance.off('click', clickHandlerRef.current);
      }
    };
  }, [mapLoaded, dataset, variable, currentTimestep, activePolygonLayer, dispatch, isStreamflow]);

  const colorLegend =
    !isStreamflow && mapLoaded && dataset && variable ? (tilesLegend.data ?? null) : null;

  const activeLegendEntries = OVERLAY_LAYERS.filter(
    (o) => activeOverlays.includes(o.id) && overlayLegends[o.id]
  ).map((o) => ({ label: o.label, entries: overlayLegends[o.id] }));

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
      {showLegend && (colorLegend || activeLegendEntries.length > 0) && (
        <div
          style={{
            position: 'absolute',
            bottom: '8px',
            right: '8px',
            background: 'rgba(255,255,255,0.92)',
            border: '1px solid #ccc',
            borderRadius: '4px',
            padding: '6px 8px',
            maxHeight: '40vh',
            overflowY: 'auto',
            pointerEvents: 'none',
            zIndex: 1,
          }}
        >
          {colorLegend && (
            <div style={{ marginBottom: activeLegendEntries.length > 0 ? '8px' : 0 }}>
              <GriddedColorBar legend={colorLegend} />
            </div>
          )}
          {activeLegendEntries.map(({ label, entries }) => (
            <div
              key={label}
              style={{ fontSize: '0.72rem', marginBottom: entries.length > 1 ? '6px' : 0 }}
            >
              <div style={{ fontWeight: 600, marginBottom: '2px' }}>{label}</div>
              {entries.map((entry, i) => (
                <div key={i} className="d-flex align-items-center gap-1">
                  <img
                    src={`data:${entry.contentType};base64,${entry.imageData}`}
                    width={entry.width}
                    height={entry.height}
                    alt={entry.label}
                    style={{ flexShrink: 0 }}
                  />
                  <span>{entry.label}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default GriddedMapComponent;
