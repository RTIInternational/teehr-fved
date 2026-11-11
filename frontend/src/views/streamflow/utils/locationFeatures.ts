import type { Feature, FeatureCollection, GeoJsonProperties, Point } from 'geojson';

import type { MapLocation } from '@/shared/types/locations';
import type { InvalidFeature, MapMetric, MapMetricClamped } from '@/shared/types/maps';

// Values beyond this overflow MapLibre's varint encoding of GeoJSON tiles.
const MAX_ABS_PROPERTY_VALUE = 1e6;

const roundCoordinate = (value: number) => Math.round(value * 1e8) / 1e8;

const sanitizeProperties = (
  properties: GeoJsonProperties,
  index: number,
  metricName: MapMetric | undefined,
  clamped: MapMetricClamped[]
): GeoJsonProperties => {
  if (!properties) return properties;

  const next: Record<string, unknown> = { ...properties };
  for (const [key, value] of Object.entries(next)) {
    if (typeof value !== 'number') continue;
    if (!Number.isFinite(value)) {
      next[key] = null;
    } else if (Math.abs(value) > MAX_ABS_PROPERTY_VALUE) {
      const clampedValue = Math.sign(value) * MAX_ABS_PROPERTY_VALUE;
      if (key === metricName) {
        clamped.push({ index, metric: key, original: value, clamped: clampedValue });
      }
      next[key] = clampedValue;
    }
  }
  return next;
};

/**
 * Drops features MapLibre can't render and clamps numeric properties, without
 * mutating the query cache's data. Ported from the legacy MapComponent.
 */
export const sanitizeLocationFeatures = (
  collection: FeatureCollection<Point>,
  metricName: MapMetric | undefined
): FeatureCollection<Point> => {
  const valid: Feature<Point>[] = [];
  const invalid: InvalidFeature[] = [];
  const clamped: MapMetricClamped[] = [];

  collection.features.forEach((feature, index) => {
    const coordinates = feature?.geometry?.coordinates;
    if (feature?.type !== 'Feature' || !Array.isArray(coordinates)) {
      invalid.push({ index, reason: 'invalid structure', feature });
      return;
    }

    const [lon, lat] = coordinates;
    if (typeof lon !== 'number' || typeof lat !== 'number') {
      invalid.push({ index, reason: 'non-numeric coordinates', feature });
      return;
    }
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      invalid.push({ index, reason: `non-finite coordinates: ${lon}, ${lat}`, feature });
      return;
    }
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
      invalid.push({ index, reason: `coordinates out of range: ${lon}, ${lat}`, feature });
      return;
    }

    valid.push({
      ...feature,
      geometry: { ...feature.geometry, coordinates: [roundCoordinate(lon), roundCoordinate(lat)] },
      properties: sanitizeProperties(feature.properties, index, metricName, clamped),
    });
  });

  if (invalid.length > 0 || clamped.length > 0) {
    console.warn('Streamflow: location data validation results', {
      totalFeatures: collection.features.length,
      validFeatures: valid.length,
      invalidDetails: invalid.map(({ index, reason }) => ({ index, reason })),
      clampedDetails: clamped,
    });
  }

  return { type: 'FeatureCollection', features: valid };
};

export const toMapLocation = (feature: Feature<Point>): MapLocation | null => {
  const [lon, lat] = feature.geometry?.coordinates ?? [];
  const properties = feature.properties;
  if (!properties || typeof lon !== 'number' || typeof lat !== 'number') return null;

  return {
    primary_location_id: String(properties.primary_location_id ?? ''),
    secondary_location_id: properties.secondary_location_id
      ? String(properties.secondary_location_id)
      : undefined,
    name: String(properties.name || properties.primary_location_id || 'Unnamed location'),
    coordinates: [lon, lat],
  };
};
