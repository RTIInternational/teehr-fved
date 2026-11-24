import { Loader, Stack, Text } from '@mantine/core';
import { IconDatabaseOff, IconMapPin } from '@tabler/icons-react';
import React, { useState } from 'react';

import type { TimeseriesRequestFilters } from '@/shared/api/timeseries';
import FilterSidebarLayout from '@/shared/components/FilterSidebarLayout';
import PlotlyChart from '@/shared/components/PlotlyChart';
import { useFilterSidebar } from '@/shared/hooks/useFilterSidebar';
import { usePrimaryTimeseries, useSecondaryTimeseries } from '@/shared/queries/timeseries';
import type { TimeseriesState } from '@/shared/types/timeseries';

import styles from './TimeseriesComponent.module.css';

type TimeseriesControlInjectedProps = {
  setRequestFilters: (filters: TimeseriesRequestFilters) => void;
  /** Called once the filters are submitted. */
  onLoad: () => void;
};

type TimeseriesComponentProps<TControlsProps extends object> = {
  state: TimeseriesState;
  Controls: React.ComponentType<TControlsProps & TimeseriesControlInjectedProps>;
  controlsProps: TControlsProps;
  /**
   * Request issued without submitting the filters form. The first non-null value
   * is kept until the user submits the form; key the component by location to
   * reset it.
   */
  autoRequestFilters?: TimeseriesRequestFilters | null;
};

const TimeseriesComponent = <TControlsProps extends object>({
  state,
  Controls,
  controlsProps,
  autoRequestFilters = null,
}: TimeseriesComponentProps<TControlsProps>) => {
  const sidebar = useFilterSidebar();
  const [requestFilters, setRequestFilters] = useState<TimeseriesRequestFilters>();
  const [autoFilters, setAutoFilters] = useState(autoRequestFilters ?? undefined);
  if (!autoFilters && autoRequestFilters) {
    setAutoFilters(autoRequestFilters);
  }
  const activeFilters = requestFilters ?? autoFilters;
  const primary = usePrimaryTimeseries(activeFilters);
  const secondary = useSecondaryTimeseries(activeFilters);

  const primaryData = primary.data ?? [];
  const secondaryData = secondary.data ?? [];

  const hasData = primaryData.length > 0 || secondaryData.length > 0;

  if (!state.selectedLocation) {
    return (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <IconMapPin size={32} stroke={1.5} color="var(--mantine-color-dimmed)" />
        <Text fw={600} c="dimmed">
          Select a Location
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          Click on a location on the map to view its time series data.
        </Text>
      </Stack>
    );
  }

  let plotBody;
  if (primary.isLoading || secondary.isLoading) {
    plotBody = (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <Loader />
        <Text size="sm" c="dimmed">
          Loading timeseries data...
        </Text>
      </Stack>
    );
  } else if (!hasData) {
    plotBody = (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <IconDatabaseOff size={32} stroke={1.5} color="var(--mantine-color-dimmed)" />
        <Text fw={600} c="dimmed">
          No Data Available
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          Adjust the filters or check if data exists for this location.
        </Text>
      </Stack>
    );
  } else {
    plotBody = (
      <div className={styles.plot}>
        <PlotlyChart
          primaryData={primaryData}
          secondaryData={secondaryData}
          selectedLocation={state.selectedLocation}
          filters={state.timeseriesFilters}
          height="100%"
        />
      </div>
    );
  }

  return (
    <FilterSidebarLayout
      opened={sidebar.opened}
      onOpenedChange={sidebar.setOpened}
      filters={
        <Controls
          {...controlsProps}
          setRequestFilters={setRequestFilters}
          onLoad={sidebar.closeIfOverlay}
        />
      }
    >
      {plotBody}
    </FilterSidebarLayout>
  );
};

export default TimeseriesComponent;
