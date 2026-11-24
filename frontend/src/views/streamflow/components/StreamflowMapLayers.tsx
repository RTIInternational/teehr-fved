import type { Feature, FeatureCollection, Point } from 'geojson';
import maplibregl, { type MapLayerMouseEvent, type MapMouseEvent } from 'maplibre-gl';
import { useEffect, useEffectEvent, useRef, useState } from 'react';

import { MapPopup, MapPopupField, MapPopupNote, MapPopupTitle, useMap } from '@/core/map';
import type { MapLocation } from '@/shared/types/locations';
import type { MapMetric } from '@/shared/types/maps';
import { getMetricColorExpression, getMetricLabel, isLngLatTuple } from '@/shared/utils/mapMetrics';

import { sanitizeLocationFeatures, toMapLocation } from '../utils/locationFeatures';

const SOURCE_ID = 'streamflow-locations';
const LAYER_ID = 'streamflow-locations';
const SELECTED_LAYER_ID = 'streamflow-locations-selected';
const DEFAULT_METRIC: MapMetric = 'relative_bias';

const EMPTY_COLLECTION: FeatureCollection<Point> = { type: 'FeatureCollection', features: [] };

const selectedFilter = (locationId: string | null): maplibregl.FilterSpecification => [
  '==',
  ['get', 'primary_location_id'],
  locationId ?? '',
];

type HoveredLocation = {
  location: MapLocation;
  /** The feature's properties, where its metric values are. */
  properties: Record<string, unknown>;
};

const LocationHoverContent = ({
  hovered: { location, properties },
  metric,
}: {
  hovered: HoveredLocation;
  metric: MapMetric;
}) => {
  const [lon, lat] = location.coordinates;
  const value = properties[metric];
  return (
    <>
      <MapPopupTitle>{location.name}</MapPopupTitle>
      <MapPopupField label="ID">{location.primary_location_id}</MapPopupField>
      <MapPopupField label="Lat">{lat.toFixed(4)}</MapPopupField>
      <MapPopupField label="Lon">{lon.toFixed(4)}</MapPopupField>
      <MapPopupField label={getMetricLabel(metric)}>
        {value !== null && value !== undefined ? Number(value).toFixed(3) : 'N/A'}
      </MapPopupField>
      <MapPopupNote>Click to select</MapPopupNote>
    </>
  );
};

type StreamflowMapLayersProps = {
  locations: FeatureCollection<Point> | undefined;
  /** Identifies the query behind `locations`; a change fits the map to the new data. */
  locationsKey: string | null;
  metricName: MapMetric | undefined;
  selectedLocationId: string | null;
  onSelect: (location: MapLocation | null) => void;
  onError: (message: string) => void;
};

/**
 * Draws streamflow locations on the shared map. Everything it adds is derived
 * from props and removed on unmount, so remounting with the same props
 * reproduces the same map.
 */
export const StreamflowMapLayers = ({
  locations,
  locationsKey,
  metricName,
  selectedLocationId,
  onSelect,
  onError,
}: StreamflowMapLayersProps) => {
  const map = useMap();
  const metric = metricName ?? DEFAULT_METRIC;
  const [hovered, setHovered] = useState<HoveredLocation | null>(null);

  const handleSelect = useEffectEvent((location: MapLocation | null) => onSelect(location));
  const handleError = useEffectEvent((message: string) => onError(message));

  // Source, layers and interaction handlers live as long as the map does.
  useEffect(() => {
    if (!map) return;

    const colorExpression = getMetricColorExpression(DEFAULT_METRIC);
    map.addSource(SOURCE_ID, { type: 'geojson', data: EMPTY_COLLECTION });
    map.addLayer({
      id: LAYER_ID,
      type: 'circle',
      source: SOURCE_ID,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 6, 8, 9, 12, 12],
        'circle-color': colorExpression,
        'circle-stroke-width': 1,
        'circle-stroke-color': 'black',
        'circle-opacity': 0.8,
      },
    });
    map.addLayer({
      id: SELECTED_LAYER_ID,
      type: 'circle',
      source: SOURCE_ID,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 8, 8, 11, 12, 14],
        'circle-color': colorExpression,
        'circle-stroke-width': 2,
        'circle-stroke-color': 'black',
        'circle-opacity': 1,
      },
      filter: selectedFilter(null),
    });

    const onLocationClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0] as Feature<Point> | undefined;
      if (!feature) return;
      const location = toMapLocation(feature);
      if (location) handleSelect(location);
    };

    // mousemove rather than mouseenter, so moving straight onto an overlapping
    // neighbour updates the popup. Same feature, same state: no re-render.
    const onLocationMove = (event: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = 'pointer';
      const feature = event.features?.[0] as Feature<Point> | undefined;
      if (!feature || !isLngLatTuple(feature.geometry.coordinates)) return;
      const location = toMapLocation(feature);
      if (!location) return;
      setHovered((current) =>
        current?.location.primary_location_id === location.primary_location_id
          ? current
          : { location, properties: feature.properties ?? {} }
      );
    };

    const onLocationLeave = () => {
      map.getCanvas().style.cursor = '';
      setHovered(null);
    };

    // A click away from every location clears the selection.
    const onMapClick = (event: MapMouseEvent) => {
      const hits = map.queryRenderedFeatures(event.point, { layers: [LAYER_ID] });
      if (hits.length === 0) handleSelect(null);
    };

    const onMapError = (event: maplibregl.ErrorEvent & { sourceId?: string }) => {
      if (event.sourceId !== SOURCE_ID) return;
      handleError(`Map error: ${event.error?.message || 'Unknown error'}`);
    };

    map.on('click', LAYER_ID, onLocationClick);
    map.on('mousemove', LAYER_ID, onLocationMove);
    map.on('mouseleave', LAYER_ID, onLocationLeave);
    map.on('click', onMapClick);
    map.on('error', onMapError);

    return () => {
      map.off('click', LAYER_ID, onLocationClick);
      map.off('mousemove', LAYER_ID, onLocationMove);
      map.off('mouseleave', LAYER_ID, onLocationLeave);
      map.off('click', onMapClick);
      map.off('error', onMapError);
      map.getCanvas().style.cursor = '';
      // The map may already be gone when the whole app unmounts.
      try {
        if (map.getLayer(SELECTED_LAYER_ID)) map.removeLayer(SELECTED_LAYER_ID);
        if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
        if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
      } catch {
        // Nothing left to clean up.
      }
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const source = map.getSource<maplibregl.GeoJSONSource>(SOURCE_ID);
    if (!source) return;

    if (!locations?.features) {
      source.setData(EMPTY_COLLECTION);
      return;
    }

    const sanitized = sanitizeLocationFeatures(locations, metric);
    if (locations.features.length > 0 && sanitized.features.length === 0) {
      handleError('Location data format is invalid - no valid features found');
    }
    source.setData(sanitized);
  }, [map, locations, metric]);

  useEffect(() => {
    if (!map) return;
    const colorExpression = getMetricColorExpression(metric);
    map.setPaintProperty(LAYER_ID, 'circle-color', colorExpression);
    map.setPaintProperty(SELECTED_LAYER_ID, 'circle-color', colorExpression);
  }, [map, metric]);

  useEffect(() => {
    if (!map) return;
    map.setFilter(SELECTED_LAYER_ID, selectedFilter(selectedLocationId));
  }, [map, selectedLocationId]);

  // Fit to the data when the query changes, but not for the first data this view
  // shows: that extent comes from the bbox the user returned with.
  const fittedKeyRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!map || !locations?.features?.length) return;
    if (fittedKeyRef.current === undefined) {
      fittedKeyRef.current = locationsKey;
      return;
    }
    if (fittedKeyRef.current === locationsKey) return;
    fittedKeyRef.current = locationsKey;

    const bounds = new maplibregl.LngLatBounds();
    for (const feature of locations.features) {
      const coordinates = feature.geometry?.coordinates;
      if (isLngLatTuple(coordinates)) bounds.extend(coordinates);
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 50, duration: 700, maxZoom: 14 });
    }
  }, [map, locations, locationsKey]);

  return (
    hovered && (
      <MapPopup lngLat={hovered.location.coordinates}>
        <LocationHoverContent hovered={hovered} metric={metric} />
      </MapPopup>
    )
  );
};
