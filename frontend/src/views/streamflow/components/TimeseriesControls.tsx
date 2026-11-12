import { Button, Grid, Group, Select, Stack, Tabs, Text, TextInput } from '@mantine/core';
import { useState } from 'react';

import type { TimeseriesRequestFilters } from '@/shared/api/timeseries';
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
  onViewModeChange: (viewMode: string) => void;
};

const TimeseriesControls = ({
  table,
  timeseriesFilters,
  updateTimeseriesFilters,
  setRequestFilters,
  selectedLocation,
  onViewModeChange,
}: TimeseriesControlsProps) => {
  const [activeTab, setActiveTab] = useState<string | null>('observations');

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

  const handleLoadData = async () => {
    if (!canLoadTimeseries) return;

    setRequestFilters({
      primary_location_id: selectedLocation.primary_location_id,
      primary: primaryFilters,
      secondary: secondaryFilters,
    });

    if (onViewModeChange) {
      onViewModeChange('plot');
    }
  };

  return (
    <Stack h="100%" justify="space-between">
      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List grow mb="md">
          <Tabs.Tab value="observations">Observations (Primary)</Tabs.Tab>
          <Tabs.Tab value="forecast">Forecast (Secondary)</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="observations">
          <Grid gap="sm">
            <Grid.Col span={6}>
              <MultiSelectDropdown
                label="Variable"
                data={(Array.isArray(primaryVariables.data) ? primaryVariables.data : []).map(
                  toDisplayVariableName
                )}
                value={(primaryFilters.variables || []).map(toDisplayVariableName)}
                onChange={(displaySelected) =>
                  handlePrimaryFilterChange(
                    'variables',
                    displaySelected.map(fromDisplayVariableName)
                  )
                }
                placeholder="Select variables..."
              />
            </Grid.Col>
            <Grid.Col span={6}>
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
            </Grid.Col>

            <Grid.Col span={6}>
              <TextInput
                type="datetime-local"
                label="Start Date"
                value={primaryFilters.start_date || ''}
                onChange={(e) => handlePrimaryFilterChange('start_date', e.target.value || null)}
              />
            </Grid.Col>

            <Grid.Col span={6}>
              <TextInput
                type="datetime-local"
                label="End Date"
                value={primaryFilters.end_date || ''}
                onChange={(e) => handlePrimaryFilterChange('end_date', e.target.value || null)}
              />
            </Grid.Col>
          </Grid>
        </Tabs.Panel>

        <Tabs.Panel value="forecast">
          <Grid gap="sm">
            <Grid.Col span={12}>
              <MultiSelectDropdown
                label="Configurations"
                data={Array.isArray(configurations.data) ? configurations.data : []}
                value={secondaryFilters.configurations}
                onChange={(selected) => handleSecondaryFilterChange('configurations', selected)}
                placeholder="Select configurations..."
              />
            </Grid.Col>

            <Grid.Col span={12}>
              <MultiSelectDropdown
                label="Variable"
                data={Array.isArray(variables.data) ? variables.data : []}
                value={secondaryFilters.variables}
                onChange={(selected) => handleSecondaryFilterChange('variables', selected)}
                placeholder="Select variables..."
              />
            </Grid.Col>

            <Grid.Col span={6}>
              <TextInput
                type="datetime-local"
                label="Reference Start Date"
                value={secondaryFilters.reference_start_date || ''}
                onChange={(e) =>
                  handleSecondaryFilterChange('reference_start_date', e.target.value || null)
                }
              />
            </Grid.Col>

            <Grid.Col span={6}>
              <TextInput
                type="datetime-local"
                label="Reference End Date"
                value={secondaryFilters.reference_end_date || ''}
                onChange={(e) =>
                  handleSecondaryFilterChange('reference_end_date', e.target.value || null)
                }
              />
            </Grid.Col>
          </Grid>
        </Tabs.Panel>
      </Tabs>

      <Group justify="space-between" pt="xs" className={styles.footer}>
        <Text size="sm" c="dimmed">
          Configure observations and forecast independently, then load.
        </Text>
        <Button size="sm" onClick={handleLoadData} disabled={!canLoadTimeseries}>
          Load Timeseries Data
        </Button>
      </Group>
    </Stack>
  );
};

export default TimeseriesControls;
