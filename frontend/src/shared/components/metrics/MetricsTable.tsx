import { Alert, Center, Loader, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';

import type { TableProperties } from '@/shared/api/utils';

import MetricsDataTable from './MetricsDataTable';
import MetricsFilters from './MetricsFilters';
import MetricsLeadTimePlot from './MetricsLeadTimePlot';
import type { MetricRecord } from './metricsTableUtils';
import { useMetricsTableData } from './useMetricsTableData';

export type MetricsViewMode = 'filters' | 'plot' | 'table';

type MetricsTableProps = {
  metrics?: MetricRecord[];
  loading: boolean;
  error?: string | null;
  emptyMessage?: string;
  /** Contains the group_by and metrics fields used for pivoting. */
  tableProperties: TableProperties | null;
  viewMode: MetricsViewMode;
};

/**
 * Pivoted metrics for a location, shown as a sortable table, a lead time plot, or the
 * filters that drive both. The view mode is controlled by the parent. Key this by
 * table so its filters and sort reset when the table changes.
 */
const MetricsTable = ({
  metrics = [],
  loading,
  error = null,
  emptyMessage = 'No metrics available for this location.',
  tableProperties,
  viewMode,
}: MetricsTableProps) => {
  const data = useMetricsTableData(metrics, tableProperties);

  if (loading) {
    return (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <Loader />
        <Text size="sm" c="dimmed">
          Loading metrics...
        </Text>
      </Stack>
    );
  }

  if (error) {
    return (
      <Alert
        m="sm"
        color="red"
        title="Error loading metrics"
        icon={<IconAlertTriangle size={18} />}
      >
        {error}
      </Alert>
    );
  }

  if (data.allRows.length === 0) {
    return (
      <Center h="100%">
        <Text size="sm" c="dimmed" ta="center">
          {emptyMessage}
        </Text>
      </Center>
    );
  }

  if (viewMode === 'filters' && data.groupByCount > 0) return <MetricsFilters data={data} />;
  if (viewMode === 'plot' && data.hasLeadTimeBin) return <MetricsLeadTimePlot data={data} />;
  return <MetricsDataTable data={data} />;
};

export default MetricsTable;
