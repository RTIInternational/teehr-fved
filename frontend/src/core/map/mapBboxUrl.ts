import type { LngLatBounds } from 'maplibre-gl';

export const BBOX_DECIMALS = 5;

export type BboxBounds = [[number, number], [number, number]];

export const formatBboxFromBounds = (bounds: LngLatBounds, decimals = BBOX_DECIMALS) => {
  const west = bounds.getWest().toFixed(decimals);
  const south = bounds.getSouth().toFixed(decimals);
  const east = bounds.getEast().toFixed(decimals);
  const north = bounds.getNorth().toFixed(decimals);
  return `${west},${south},${east},${north}`;
};

export const bboxBoundsToString = (bounds: BboxBounds, decimals = BBOX_DECIMALS) => {
  const [sw, ne] = bounds;
  return [sw[0], sw[1], ne[0], ne[1]].map((part) => part.toFixed(decimals)).join(',');
};

export const parseBboxFromSearch = (value: string | null): BboxBounds | null => {
  if (!value) return null;

  const parts = value.split(',').map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => !Number.isFinite(part))) {
    return null;
  }

  const [west, south, east, north] = parts;
  if (west < -180 || west > 180 || east < -180 || east > 180) return null;
  if (south < -90 || south > 90 || north < -90 || north > 90) return null;
  if (west >= east || south >= north) return null;

  return [
    [west, south],
    [east, north],
  ];
};
