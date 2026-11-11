import { useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { getMapViewById, writeLastMapViewId } from '@/views/registry';

import { MapViewChooserModal } from './MapViewChooserModal';

export const MapRoute = () => {
  const { viewId } = useParams();
  const selectedView = getMapViewById(viewId);

  useEffect(() => {
    if (!selectedView) return;
    writeLastMapViewId(selectedView.id);
  }, [selectedView]);

  if (!selectedView) {
    return <MapViewChooserModal />;
  }

  // Keyed so switching views fully unmounts the previous one and its map layers.
  const View = selectedView.component;
  return <View key={selectedView.id} />;
};
