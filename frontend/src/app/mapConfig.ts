import type { LngLatBoundsLike, RequestParameters } from 'maplibre-gl';

import { API_BASE_URL, API_KEY } from '@/shared/api/client';
import { GRIDDED_API_BASE_URL } from '@/shared/api/gridded/client';
import { getKeycloak } from '@/shared/auth';

/** Reclamation regions' extent. */
export const DEFAULT_MAP_BOUNDS: LngLatBoundsLike = [
  [-124.8, 25.8],
  [-93.5, 49.0],
];

// Prefix match on a path boundary so a lookalike host (e.g. :80001 vs :8000) gets no credentials.
const isApiUrl = (url: string, baseUrl: string) => {
  const base = baseUrl.replace(/\/+$/, '');
  return url === base || url.startsWith(`${base}/`) || url.startsWith(`${base}?`);
};

/**
 * Adds credentials to map requests aimed at our APIs, mirroring apiCallJson and
 * griddedApiCall. transformRequest is synchronous, so this uses the current
 * token without refreshing it.
 */
export const mapTransformRequest = (url: string): RequestParameters => {
  const token = getKeycloak().token;

  if (isApiUrl(url, GRIDDED_API_BASE_URL)) {
    return token ? { url, headers: { Authorization: `Bearer ${token}` } } : { url };
  }
  if (isApiUrl(url, API_BASE_URL)) {
    if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
    if (API_KEY) return { url, headers: { 'X-API-Key': API_KEY } };
  }
  return { url };
};
