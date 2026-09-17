export type PolygonFeatures = Record<string, unknown>[];

export type VectorTile = {
  id: string;
  source_layer: string;
};

export type VectorTilesResponse = {
  items: VectorTile[];
};
