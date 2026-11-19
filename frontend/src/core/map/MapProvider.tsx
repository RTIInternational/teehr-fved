import type { Map as MapLibreMap } from 'maplibre-gl';
import { type PropsWithChildren, useMemo, useState } from 'react';

import { MapContext } from './MapContext';

/** Holds the shared map instance created by MapStage so any descendant can reach it. */
export const MapProvider = ({ children }: PropsWithChildren) => {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const value = useMemo(() => ({ map, setMap }), [map]);

  return <MapContext.Provider value={value}>{children}</MapContext.Provider>;
};
