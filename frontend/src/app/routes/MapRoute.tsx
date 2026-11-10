import { useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';

import { useMap } from '@/core/map';
import { getMapViewById, writeLastMapViewId } from '@/views/registry';

import { MapViewChooserModal } from './MapViewChooserModal';

const BASEMAP_ID = 'basemap';

/**
 * Dev-only: warns when the previous view left layers or sources on the shared map.
 * Render it keyed and before the view, so its mount effect runs after the old
 * view's cleanup and before the new view adds anything.
 */
const MapLeakCheck = () => {
  const map = useMap();
  // StrictMode re-runs this effect after the new view has added its own layers;
  // the ref survives that simulated remount, so only the first run checks.
  const checkedRef = useRef(false);

  useEffect(() => {
    if (!import.meta.env.DEV || !map || checkedRef.current) return;
    checkedRef.current = true;
    const style = map.getStyle();
    const layers = style.layers.map((layer) => layer.id).filter((id) => id !== BASEMAP_ID);
    const sources = Object.keys(style.sources).filter((id) => id !== BASEMAP_ID);
    if (layers.length > 0 || sources.length > 0) {
      console.warn('MapRoute: previous view left map resources behind', { layers, sources });
    }
  }, [map]);

  return null;
};

export const MapRoute = () => {
  const { viewId } = useParams();
  const selectedView = getMapViewById(viewId);

  useEffect(() => {
    if (!selectedView) return;
    writeLastMapViewId(selectedView.id);
  }, [selectedView]);

  if (!selectedView) {
    return (
      <>
        <MapLeakCheck key="chooser" />
        <MapViewChooserModal />
      </>
    );
  }

  const View = selectedView.component;

  return (
    <>
      <MapLeakCheck key={`check-${selectedView.id}`} />
      <View key={selectedView.id} />
    </>
  );
};
