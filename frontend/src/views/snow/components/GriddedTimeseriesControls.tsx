import { Button, Stack, Text } from '@mantine/core';

import DateRangeInputs from '@/shared/components/DateRangeInputs';
import MultiSelectDropdown from '@/shared/components/MultiSelectDropdown';
import { useDatasets } from '@/shared/queries/gridded/datasets';
import type { GriddedTimeseriesFilters } from '@/shared/types/gridded/timeseries';

import { DEFAULT_TIMESERIES_FILTERS, timeseriesDatasets } from '../DashboardContext';

import styles from './GriddedTimeseriesControls.module.css';

export type GriddedTimeseriesControlsProps = {
  timeseriesFilters: GriddedTimeseriesFilters;
  updateTimeseriesFilters: (patch: Partial<GriddedTimeseriesFilters>) => void;
  activeDataset: string | null;
};

const GriddedTimeseriesControls = ({
  timeseriesFilters,
  updateTimeseriesFilters,
  activeDataset,
}: GriddedTimeseriesControlsProps) => {
  const datasets = useDatasets();
  const { start_date, end_date } = timeseriesFilters;

  const rangeError =
    start_date && end_date && start_date > end_date
      ? 'End date must not be before start date.'
      : null;

  return (
    <div className={styles.controls}>
      <Stack gap="sm" className={styles.fields}>
        <MultiSelectDropdown
          label="Datasets"
          loading={datasets.isLoading}
          disabled={datasets.isLoading}
          data={datasets.data}
          value={timeseriesDatasets(timeseriesFilters, activeDataset)}
          onChange={(selected) => updateTimeseriesFilters({ datasets: selected })}
          placeholder="Select datasets..."
        />

        <DateRangeInputs
          start={start_date}
          end={end_date}
          onStartChange={(value) => updateTimeseriesFilters({ start_date: value })}
          onEndChange={(value) => updateTimeseriesFilters({ end_date: value })}
          error={rangeError}
        />
        <Text size="xs" c="dimmed">
          Leave dates empty for up to 3 years before the map&apos;s date (max span 20 years).
        </Text>
      </Stack>

      <div className={styles.footer}>
        <Button
          fullWidth
          variant="default"
          size="sm"
          onClick={() => updateTimeseriesFilters(DEFAULT_TIMESERIES_FILTERS)}
        >
          Reset
        </Button>
      </div>
    </div>
  );
};

export default GriddedTimeseriesControls;
