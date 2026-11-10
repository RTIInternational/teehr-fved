import { Alert } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

import { GriddedDashboardProvider } from '@/features/gridded';
import GriddedPolygonPanel from '@/features/gridded/components/GriddedPolygonPanel';
import GriddedTimeseriesPanel from '@/features/gridded/components/GriddedTimeseriesPanel';
import { ActionTypes, useDashboard } from '@/features/gridded/DashboardContext';
import { MapDataDock, type MapDataDockSection } from '@/views/components/MapDataDock';

import { SnowLayersPopover } from './components/SnowLayersPopover';
import { SnowLegend } from './components/SnowLegend';
import { SnowMapLayers } from './components/SnowMapLayers';
import { useSnowDefaults } from './hooks/useSnowDefaults';
import { useSnowDockSection } from './hooks/useSnowDockSection';

import styles from './SnowView.module.css';

const SnowContent = () => {
  const { state, dispatch } = useDashboard();
  const { section, setSection, hasAttributes } = useSnowDockSection();

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
    <div className={styles.overlay}>
      <SnowMapLayers />

      <SnowLegend className={styles.legend} />

      <div className={styles.topRight}>
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
      </div>

      <MapDataDock sections={sections} section={section} onSectionChange={setSection} />
    </div>
  );
};

/** Gridded snow datasets, reference overlays and polygon attributes on the shared map. */
export const SnowView = () => (
  <GriddedDashboardProvider>
    <SnowContent />
  </GriddedDashboardProvider>
);
