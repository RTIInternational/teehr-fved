import { Button, Fieldset, Select, Stack, Text } from '@mantine/core';

import type { TimeseriesRequestFilters } from '@/shared/api/timeseries';
import DateRangeInputs from '@/shared/components/DateRangeInputs';
import MultiSelectDropdown from '@/shared/components/MultiSelectDropdown';
import { useDistinctValues } from '@/shared/queries/distinctValues';
import type { MapLocation } from '@/shared/types/locations';
import type { MapFilters } from '@/shared/types/maps';
import type { TimeseriesFilters } from '@/shared/types/timeseries';
import {
  toDisplayVariableName,
  fromDisplayVariableName,
  isTimestepVariable,
  DURATION_NAME_TO_ISO,
} from '@/shared/utils/durationUtils';

import styles from './TimeseriesControls.module.css';

export type TimeseriesControlsProps = {
  table: string;
  timeseriesFilters: TimeseriesFilters;
  updateTimeseriesFilters: (patch: Partial<TimeseriesFilters>) => void;
  setRequestFilters: (filters: TimeseriesRequestFilters) => void;
  selectedLocation: MapLocation;
  mapFilters: MapFilters;
  onLoad: () => void;
};

const SectionLegend = ({ title, note }: { title: string; note: string }) => (
  <>
    {title}{' '}
    <Text span size="xs" c="dimmed" fw={400}>
      {note}
    </Text>
  </>
);

const TimeseriesControls = ({
  table,
  timeseriesFilters,
  updateTimeseriesFilters,
  setRequestFilters,
  selectedLocation,
  onLoad,
}: TimeseriesControlsProps) => {
  const configurations = useDistinctValues(table, 'configuration_name');
  const variables = useDistinctValues(table, 'variable_name');
  const primaryVariables = useDistinctValues('primary_timeseries', 'variable_name');

  const primaryFilters = timeseriesFilters.primary;
  const secondaryFilters = timeseriesFilters.secondary;

  const handlePrimaryFilterChange = (field: string, value: unknown) => {
    updateTimeseriesFilters({
      primary: {
        ...primaryFilters,
        [field]: value,
      },
    });
  };

  const handleSecondaryFilterChange = (field: string, value: unknown) => {
    updateTimeseriesFilters({
      secondary: {
        ...secondaryFilters,
        [field]: value,
      },
    });
  };

  const canLoadTimeseries = Boolean(
    selectedLocation?.primary_location_id &&
    primaryFilters.variables?.length &&
    secondaryFilters.variables?.length &&
    secondaryFilters.configurations?.length
  );

  const handleLoadData = () => {
    if (!canLoadTimeseries) return;

    setRequestFilters({
      primary_location_id: selectedLocation.primary_location_id,
      primary: primaryFilters,
      secondary: secondaryFilters,
    });

    onLoad();
  };

  return (
    <div className={styles.controls}>
      <Stack gap="lg" className={styles.fields}>
        <Fieldset
          legend={<SectionLegend title="Observations" note="primary" />}
          variant="unstyled"
          classNames={{ legend: styles.legend }}
        >
          <Stack gap="xs">
            <MultiSelectDropdown
              label="Variable"
              data={(Array.isArray(primaryVariables.data) ? primaryVariables.data : []).map(
                toDisplayVariableName
              )}
              value={(primaryFilters.variables || []).map(toDisplayVariableName)}
              onChange={(displaySelected) =>
                handlePrimaryFilterChange('variables', displaySelected.map(fromDisplayVariableName))
              }
              placeholder="Select variables..."
            />
            <Select
              label="Obs timestep (if available)"
              data={Object.entries(DURATION_NAME_TO_ISO).map(([label, value]) => ({
                label,
                value,
              }))}
              value={primaryFilters.duration || null}
              allowDeselect={false}
              disabled={!(primaryFilters.variables || []).some(isTimestepVariable)}
              onChange={(value) => value && handlePrimaryFilterChange('duration', value)}
            />
            <DateRangeInputs
              start={primaryFilters.start_date || null}
              end={primaryFilters.end_date || null}
              onStartChange={(value) => handlePrimaryFilterChange('start_date', value)}
              onEndChange={(value) => handlePrimaryFilterChange('end_date', value)}
            />
          </Stack>
        </Fieldset>

        <Fieldset
          legend={<SectionLegend title="Forecast" note="secondary" />}
          variant="unstyled"
          classNames={{ legend: styles.legend }}
        >
          <Stack gap="xs">
            <MultiSelectDropdown
              label="Configurations"
              data={Array.isArray(configurations.data) ? configurations.data : []}
              value={secondaryFilters.configurations}
              onChange={(selected) => handleSecondaryFilterChange('configurations', selected)}
              placeholder="Select configurations..."
            />
            <MultiSelectDropdown
              label="Variable"
              data={Array.isArray(variables.data) ? variables.data : []}
              value={secondaryFilters.variables}
              onChange={(selected) => handleSecondaryFilterChange('variables', selected)}
              placeholder="Select variables..."
            />
            <DateRangeInputs
              start={secondaryFilters.reference_start_date || null}
              end={secondaryFilters.reference_end_date || null}
              onStartChange={(value) => handleSecondaryFilterChange('reference_start_date', value)}
              onEndChange={(value) => handleSecondaryFilterChange('reference_end_date', value)}
              startLabel="Reference Start Date"
              endLabel="Reference End Date"
            />
          </Stack>
        </Fieldset>
      </Stack>

      <div className={styles.footer}>
        <Button fullWidth size="sm" onClick={handleLoadData} disabled={!canLoadTimeseries}>
          Load Time Series
        </Button>
      </div>
    </div>
  );
};

export default TimeseriesControls;
