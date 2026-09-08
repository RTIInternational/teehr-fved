export type ClickedPoint = {
  lon: number;
  lat: number;
};

export type MapFilters = {
  dataset: string | null;
  variable: string | null;
  timestepIndex: number;
  colorRamp: string;
  colorRampMin: number;
  colorRampMax: number;
};
