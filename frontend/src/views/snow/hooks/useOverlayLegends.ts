import { useQueries } from '@tanstack/react-query';

import { OVERLAY_LAYERS } from '../utils/overlayLayers';

export type ArcGisLegendEntry = {
  label: string;
  imageData: string;
  contentType: string;
  width: number;
  height: number;
};

type ArcGisLegendResponse = {
  layers?: Array<{ layerId: number; legend?: ArcGisLegendEntry[] }>;
};

export type OverlayLegend = { id: string; label: string; entries: ArcGisLegendEntry[] };

const fetchLegend = async (url: string, layerId: number | undefined) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Legend request failed: ${response.status}`);
  const json: ArcGisLegendResponse = await response.json();
  return json.layers?.find((layer) => layer.layerId === layerId)?.legend ?? [];
};

/** ArcGIS legends for the active overlays that publish one; failures are skipped. */
export const useOverlayLegends = (activeOverlays: string[]): OverlayLegend[] => {
  const overlays = OVERLAY_LAYERS.filter(
    (overlay) => activeOverlays.includes(overlay.id) && overlay.legendUrl
  );

  const results = useQueries({
    queries: overlays.map((overlay) => ({
      queryKey: ['overlayLegend', overlay.id],
      queryFn: () => fetchLegend(overlay.legendUrl as string, overlay.legendLayerId),
      staleTime: Infinity,
      retry: false,
    })),
  });

  return overlays.flatMap((overlay, index) => {
    const entries = results[index]?.data;
    return entries?.length ? [{ id: overlay.id, label: overlay.label, entries }] : [];
  });
};
