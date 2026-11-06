import { useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { ViewHost } from '@/core/views';
import { getMapViewById, mapViewsRegistry, writeLastMapViewId } from '@/views/registry';

import { MapViewChooserModal } from './MapViewChooserModal';
import { MapViewPlaceholder } from './MapViewPlaceholder';

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

  return (
    <ViewHost viewId={selectedView.id} views={mapViewsRegistry}>
      {(view) => <MapViewPlaceholder view={view} />}
    </ViewHost>
  );
};
