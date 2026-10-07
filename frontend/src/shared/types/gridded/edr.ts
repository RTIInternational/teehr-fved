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

export type EdrTimeseriesResponse = string;

export type TimeseriesData = {
  times: string[];
  // null where a step has no data
  values: (number | null)[];
};

// One dataset's part of a point query: data, an error, or why it was skipped
export type DatasetTimeseries = {
  datasetId: string;
  variable: string | null;
  data?: TimeseriesData;
  error?: string;
  skipped?: string;
  isLoading: boolean;
};
