import { Alert, Button, Group, SimpleGrid, Stack, Text } from '@mantine/core';

import MultiSelectDropdown from '@/shared/components/MultiSelectDropdown';

import type { MetricsTableData } from './useMetricsTableData';

import styles from './MetricsFilters.module.css';

type MetricsFiltersProps = {
  data: MetricsTableData;
};

/** Metric selection and per-column value filters for the metrics table and plot. */
const MetricsFilters = ({ data }: MetricsFiltersProps) => {
  const {
    headers,
    groupByCount,
    uniqueValuesByColumn,
    availableMetrics,
    selectedMetrics,
    setSelectedMetrics,
    filters,
    setColumnFilter,
    selectionCount,
    clearFilters,
  } = data;

  return (
    <div className={styles.root}>
      <Stack gap="sm">
        {availableMetrics.length > 0 && (
          <MultiSelectDropdown
            label="Select Metrics"
            data={availableMetrics}
            value={selectedMetrics}
            onChange={setSelectedMetrics}
            placeholder="No metrics"
          />
        )}

        <Text size="sm" fw={500}>
          Filter by Column
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="sm" verticalSpacing="sm">
          {headers.slice(0, groupByCount).map((header, index) => (
            <MultiSelectDropdown
              key={header}
              label={header}
              data={uniqueValuesByColumn[index] ?? []}
              value={filters[index] ?? []}
              onChange={(values) => setColumnFilter(index, values)}
              placeholder="All"
            />
          ))}
        </SimpleGrid>

        {selectionCount > 0 && (
          <Alert color="blue" p="xs">
            <Group justify="space-between" gap="xs">
              <Text size="sm">
                <strong>Active Filters:</strong> {selectionCount} selections
              </Text>
              <Button size="xs" variant="light" color="red" onClick={clearFilters}>
                Clear All Filters
              </Button>
            </Group>
          </Alert>
        )}
      </Stack>
    </div>
  );
};

export default MetricsFilters;
