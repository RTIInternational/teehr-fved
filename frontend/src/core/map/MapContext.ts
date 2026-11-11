import type { Map as MapLibreMap } from 'maplibre-gl';
import { createContext, useContext } from 'react';

type MapContextValue = {
  /** The shared map; null until its style has loaded, and again after it is removed. */
  map: MapLibreMap | null;
  setMap: (map: MapLibreMap | null) => void;
};

export const MapContext = createContext<MapContextValue | null>(null);

export const useMapContext = () => {
  const context = useContext(MapContext);
  if (!context) {
    throw new Error('useMapContext must be used within MapProvider');
  }
  return context;
};

/** The shared map instance, or null while it is not ready. */
export const useMap = () => useMapContext().map;
