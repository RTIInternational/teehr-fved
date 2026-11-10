import type { LayerSpecification, SourceSpecification } from 'maplibre-gl';
import { useEffect } from 'react';

import { useMap } from '@/core/map';
import { useDashboard } from '@/features/gridded/DashboardContext';
import { OVERLAY_LAYERS } from '@/features/gridded/utils/overlayLayers';

import { removeMapResources, snowBeforeId } from '../utils/layerOrder';

/** External reference overlays (e.g. NWS outlooks), drawn beneath the gridded data. */
export const OverlayLayers = () => {
  const map = useMap();
  const { state } = useDashboard();
  const { activeOverlays } = state;

  useEffect(() => {
    if (!map) return;

    const active = OVERLAY_LAYERS.filter((overlay) => activeOverlays.includes(overlay.id));
    for (const { id, sourceConfig, layerConfig } of active) {
      map.addSource(id, sourceConfig as SourceSpecification);
      map.addLayer({ id, source: id, ...layerConfig } as LayerSpecification, snowBeforeId(map, id));
    }

    const ids = active.map((overlay) => overlay.id);
    return () => removeMapResources(map, ids, ids);
  }, [map, activeOverlays]);

  return null;
};
