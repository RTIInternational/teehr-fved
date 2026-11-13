import { Group, Loader, SegmentedControl, Stack, Text } from '@mantine/core';
import { IconChartLine, IconDatabaseOff, IconFilter, IconMapPin } from '@tabler/icons-react';
import React, { useState } from 'react';

import type { TimeseriesRequestFilters } from '@/shared/api/timeseries';
import PlotlyChart from '@/shared/components/PlotlyChart';
import { usePrimaryTimeseries, useSecondaryTimeseries } from '@/shared/queries/timeseries';
import type { TimeseriesState } from '@/shared/types/timeseries';

import styles from './TimeseriesComponent.module.css';

type TimeseriesControlInjectedProps = {
  setRequestFilters: (filters: TimeseriesRequestFilters) => void;
  onViewModeChange: (viewMode: string) => void;
};

type TimeseriesComponentProps<TControlsProps extends object> = {
  state: TimeseriesState;
  Controls: React.ComponentType<TControlsProps & TimeseriesControlInjectedProps>;
  controlsProps: TControlsProps;
  initialViewMode?: 'filters' | 'plot';
  /**
   * Request issued without submitting the filters form. The first non-null value
   * is kept until the user submits the form; key the component by location to
   * reset it.
   */
  autoRequestFilters?: TimeseriesRequestFilters | null;
};

const VIEW_OPTIONS = [
  {
    value: 'filters',
    label: (
      <Group gap={6} wrap="nowrap">
        <IconFilter size={14} />
        <span>Filters</span>
      </Group>
    ),
  },
  {
    value: 'plot',
    label: (
      <Group gap={6} wrap="nowrap">
        <IconChartLine size={14} />
        <span>Plot</span>
      </Group>
    ),
  },
];

const TimeseriesComponent = <TControlsProps extends object>({
  state,
  Controls,
  controlsProps,
  initialViewMode = 'filters',
  autoRequestFilters = null,
}: TimeseriesComponentProps<TControlsProps>) => {
  const [viewMode, setViewMode] = useState<string>(initialViewMode);
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
          Try switching to Filters to adjust the time range or check if data exists for this
          location.
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
    <div className={styles.panel}>
      <Group justify="flex-end" className={styles.toolbar}>
        <SegmentedControl size="xs" value={viewMode} onChange={setViewMode} data={VIEW_OPTIONS} />
      </Group>
      <div className={styles.body}>
        {viewMode === 'plot' ? (
          plotBody
        ) : (
          <div className={styles.filters}>
            <Controls
              {...controlsProps}
              setRequestFilters={setRequestFilters}
              onViewModeChange={setViewMode}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default TimeseriesComponent;
