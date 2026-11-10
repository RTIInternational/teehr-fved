import { Alert } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

import { MapDataDock, type MapDataDockSection } from '@/views/components/MapDataDock';
import { MapViewLayout } from '@/views/components/MapViewLayout';

import GriddedPolygonPanel from './components/GriddedPolygonPanel';
import GriddedTimeseriesPanel from './components/GriddedTimeseriesPanel';
import { SnowLayersPopover } from './components/SnowLayersPopover';
import { SnowLegend } from './components/SnowLegend';
import { SnowMapLayers } from './components/SnowMapLayers';
import { ActionTypes, DashboardProvider, useDashboard } from './DashboardContext';
import { useSnowDefaults } from './hooks/useSnowDefaults';
import { useSnowDockHeader } from './hooks/useSnowDockHeader';
import { useSnowDockSection } from './hooks/useSnowDockSection';

const SnowContent = () => {
  const { state, dispatch } = useDashboard();
  const { section, setSection, hasAttributes } = useSnowDockSection();
  const dockHeader = useSnowDockHeader(section);

  useSnowDefaults();

  const sections: MapDataDockSection[] = [
    { value: 'timeseries', label: 'Time Series', content: <GriddedTimeseriesPanel /> },
  ];
  if (hasAttributes) {
    sections.unshift({
      value: 'attributes',
      label: 'Polygon Attributes',
      content: <GriddedPolygonPanel />,
    });
  }

  return (
    <MapViewLayout
      mapLayers={<SnowMapLayers />}
      topLeft={<SnowLegend />}
      topRight={
        <>
          {state.error && (
            <Alert
              w="100%"
              color="red"
              title="Error"
              icon={<IconAlertTriangle size={18} />}
              withCloseButton
              closeButtonLabel="Dismiss error"
              onClose={() => dispatch({ type: ActionTypes.CLEAR_ERROR })}
            >
              {state.error}
            </Alert>
          )}
          <SnowLayersPopover />
        </>
      }
      bottom={
        <MapDataDock
          {...dockHeader}
          sections={sections}
          section={section}
          onSectionChange={setSection}
        />
      }
    />
  );
};

/** Gridded snow datasets, reference overlays and polygon attributes on the shared map. */
export const SnowView = () => (
  <DashboardProvider>
    <SnowContent />
  </DashboardProvider>
);
