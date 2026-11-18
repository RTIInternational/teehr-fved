import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

// addProtocol is global and replaces any earlier handler, so there must be only
// one Protocol per page or archives added to an earlier one are orphaned.
//
// The Protocol fetches on its own, bypassing transformRequest; authenticated
// archives need pmtilesProtocol.add(new PMTiles(new FetchSource(url, headers))).
// The registered URL must match the pmtiles:// source URL exactly, or it
// silently falls back to an unauthenticated fetch.
export const pmtilesProtocol = new Protocol();
maplibregl.addProtocol('pmtiles', pmtilesProtocol.tile);
