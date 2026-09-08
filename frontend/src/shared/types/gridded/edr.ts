import type { FeatureCollection, Point } from 'geojson';

export type EdrPointResponse = FeatureCollection<Point, EdrPointProps>;

type EdrPointProps = Record<string, unknown> & {
  time: string;
  lat: number;
  lon: number;
  longitude: number;
  latitude: number;
  spatial_ref: number;
};

export type EdrTimeseriesFilters = {
  datasetId: string | null;
  variable: string | null;
  lon?: number;
  lat?: number;
  timesteps: string[];
};

export type EdrTimeseriesResponse = string;

export type TimeseriesData = {
  times: string[];
  values: number[];
  lon: number;
  lat: number;
  variable: string;
};
