import type { MapViewport } from '@/shared/types/maps';

export type ViewportParamKeys = {
  lon: string;
  lat: string;
  zoom: string;
};

export const DEFAULT_VIEWPORT_PARAM_KEYS: ViewportParamKeys = {
  lon: 'lon',
  lat: 'lat',
  zoom: 'z',
};

export type ViewportValidationLimits = {
  minLon: number;
  maxLon: number;
  minLat: number;
  maxLat: number;
  minZoom: number;
  maxZoom: number;
};

export const DEFAULT_VIEWPORT_VALIDATION_LIMITS: ViewportValidationLimits = {
  minLon: -180,
  maxLon: 180,
  minLat: -90,
  maxLat: 90,
  minZoom: 0,
  maxZoom: 24,
};

export type ViewportSerializationOptions = {
  keys?: ViewportParamKeys;
  limits?: ViewportValidationLimits;
  lonLatPrecision?: number;
  zoomPrecision?: number;
};

const clamp = (value: number, min: number, max: number) => {
  return Math.min(max, Math.max(min, value));
};

const toNumber = (value: string | null) => {
  if (value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const trimLeadingQuestionMark = (search: string) => {
  return search.startsWith('?') ? search.slice(1) : search;
};

const getParams = (searchOrParams: string | URLSearchParams) => {
  if (searchOrParams instanceof URLSearchParams) {
    return new URLSearchParams(searchOrParams);
  }
  return new URLSearchParams(trimLeadingQuestionMark(searchOrParams));
};

export const hasViewportParams = (
  searchOrParams: string | URLSearchParams,
  keys: ViewportParamKeys = DEFAULT_VIEWPORT_PARAM_KEYS
) => {
  const params = getParams(searchOrParams);
  return params.has(keys.lon) || params.has(keys.lat) || params.has(keys.zoom);
};

export const parseViewportFromSearch = (
  searchOrParams: string | URLSearchParams,
  options: Pick<ViewportSerializationOptions, 'keys' | 'limits'> = {}
): MapViewport | null => {
  const keys = options.keys ?? DEFAULT_VIEWPORT_PARAM_KEYS;
  const limits = options.limits ?? DEFAULT_VIEWPORT_VALIDATION_LIMITS;
  const params = getParams(searchOrParams);

  const lon = toNumber(params.get(keys.lon));
  const lat = toNumber(params.get(keys.lat));
  const zoom = toNumber(params.get(keys.zoom));

  if (lon == null || lat == null || zoom == null) {
    return null;
  }

  if (lon < limits.minLon || lon > limits.maxLon) return null;
  if (lat < limits.minLat || lat > limits.maxLat) return null;
  if (zoom < limits.minZoom || zoom > limits.maxZoom) return null;

  return {
    center: [lon, lat],
    zoom,
  };
};

export const setViewportParams = (
  params: URLSearchParams,
  viewport: MapViewport,
  options: ViewportSerializationOptions = {}
) => {
  const keys = options.keys ?? DEFAULT_VIEWPORT_PARAM_KEYS;
  const limits = options.limits ?? DEFAULT_VIEWPORT_VALIDATION_LIMITS;
  const lonLatPrecision = options.lonLatPrecision ?? 5;
  const zoomPrecision = options.zoomPrecision ?? 3;

  const lon = clamp(viewport.center[0], limits.minLon, limits.maxLon);
  const lat = clamp(viewport.center[1], limits.minLat, limits.maxLat);
  const zoom = clamp(viewport.zoom, limits.minZoom, limits.maxZoom);

  params.set(keys.lon, lon.toFixed(lonLatPrecision));
  params.set(keys.lat, lat.toFixed(lonLatPrecision));
  params.set(keys.zoom, zoom.toFixed(zoomPrecision));

  return params;
};

export const removeViewportParams = (
  params: URLSearchParams,
  keys: ViewportParamKeys = DEFAULT_VIEWPORT_PARAM_KEYS
) => {
  params.delete(keys.lon);
  params.delete(keys.lat);
  params.delete(keys.zoom);
  return params;
};

export const updateSearchWithViewport = (
  currentSearch: string,
  viewport: MapViewport | null,
  options: ViewportSerializationOptions = {}
) => {
  const params = getParams(currentSearch);
  if (viewport == null) {
    removeViewportParams(params, options.keys ?? DEFAULT_VIEWPORT_PARAM_KEYS);
  } else {
    setViewportParams(params, viewport, options);
  }

  const next = params.toString();
  return next ? `?${next}` : '';
};

export const keepOnlyViewportParams = (
  searchOrParams: string | URLSearchParams,
  keys: ViewportParamKeys = DEFAULT_VIEWPORT_PARAM_KEYS
) => {
  const source = getParams(searchOrParams);
  const scoped = new URLSearchParams();

  const lon = source.get(keys.lon);
  const lat = source.get(keys.lat);
  const zoom = source.get(keys.zoom);

  if (lon != null) scoped.set(keys.lon, lon);
  if (lat != null) scoped.set(keys.lat, lat);
  if (zoom != null) scoped.set(keys.zoom, zoom);

  return scoped;
};

export const buildSearchFromViewportOnly = (
  searchOrParams: string | URLSearchParams,
  keys: ViewportParamKeys = DEFAULT_VIEWPORT_PARAM_KEYS
) => {
  const params = keepOnlyViewportParams(searchOrParams, keys);
  const next = params.toString();
  return next ? `?${next}` : '';
};
