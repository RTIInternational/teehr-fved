import { Group, SegmentedControl, Select } from '@mantine/core';
import { IconChartLine, IconFilter, IconTable } from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';

import MetricsTable from '@/shared/components/MetricsTable';
import { useMetricsByLocation } from '@/shared/queries/metrics';
import { useTableProperties } from '@/shared/queries/queryables';
import type { MapLocation } from '@/shared/types/locations';

import styles from './LocationMetrics.module.css';

type ViewMode = 'filters' | 'plot' | 'table';

type LocationMetricsProps = {
  selectedLocation: MapLocation;
  tables: string[];
};

const viewOption = (value: ViewMode, icon: ReactNode, label: string) => ({
  value,
  label: (
    <Group gap={6} wrap="nowrap">
      {icon}
      <span>{label}</span>
    </Group>
  ),
});

const LocationMetrics = ({ selectedLocation, tables }: LocationMetricsProps) => {
  const { data: tableProperties = {} } = useTableProperties(tables);

  const [selectedTable, setSelectedTable] = useState(tables[0] || null);
  const [requestedViewMode, setViewMode] = useState<ViewMode>('table');

  const metrics = useMetricsByLocation(selectedLocation?.primary_location_id, selectedTable);

  // Check if current table has group_by fields for filter capability
  const hasFilters = Boolean(selectedTable && tableProperties[selectedTable]?.group_by?.length > 0);

  // Check if current table has lead time bins for plot capability
  const hasLeadTimeBin = Boolean(
    selectedTable &&
    tableProperties[selectedTable]?.group_by?.some(
      (field: string) =>
        field.toLowerCase().includes('lead_time_bin') ||
        field.toLowerCase().includes('forecast_lead_time_bin')
    )
  );

  // A view the selected table doesn't support (e.g. Plot after switching to a table
  // without lead time bins) falls back to the table
  const viewMode =
    (requestedViewMode === 'filters' && !hasFilters) ||
    (requestedViewMode === 'plot' && !hasLeadTimeBin)
      ? 'table'
      : requestedViewMode;

  if (!selectedLocation) {
    return null;
  }

  const viewOptions = [
    ...(hasFilters ? [viewOption('filters', <IconFilter size={14} />, 'Filters')] : []),
    viewOption('table', <IconTable size={14} />, 'Table'),
    ...(hasLeadTimeBin ? [viewOption('plot', <IconChartLine size={14} />, 'Plot')] : []),
  ];

  return (
    <div className={styles.panel}>
      <Group justify="space-between" wrap="nowrap" gap="xs" className={styles.toolbar}>
        {tables.length > 1 && (
          <Select
            aria-label="Metrics table"
            size="xs"
            data={tables.map((tableName) => ({
              value: tableName,
              label: tableProperties[tableName]?.description || tableName,
            }))}
            value={selectedTable}
            onChange={(value) => value && setSelectedTable(value)}
            allowDeselect={false}
            className={styles.tableSelect}
          />
        )}
        {(hasLeadTimeBin || hasFilters) && (
          <SegmentedControl
            size="xs"
            value={viewMode}
            onChange={(value) => setViewMode(value as ViewMode)}
            data={viewOptions}
            className={styles.viewToggle}
          />
        )}
      </Group>
      <div className={styles.body}>
        <MetricsTable
          metrics={metrics.data}
          loading={metrics.isLoading}
          error={metrics.error?.message}
          title="Metrics"
          emptyMessage={
            selectedTable
              ? `No metrics available for this location in ${selectedTable}.`
              : 'Select a table to view metrics.'
          }
          showTitle={false}
          tableProperties={selectedTable ? tableProperties[selectedTable] : null}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />
      </div>
    </div>
  );
};

export default LocationMetrics;
