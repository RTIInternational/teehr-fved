type VectorTile = {
  id: string;
  source_layer: string;
};

export type VectorTilesResponse = {
  items: VectorTile[];
};
