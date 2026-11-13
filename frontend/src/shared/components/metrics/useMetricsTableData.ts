import { useMemo, useState } from 'react';

import type { TableProperties } from '@/shared/api/utils';

import {
  filterRows,
  isLeadTimeBinField,
  pivotMetrics,
  sortRows,
  uniqueColumnValues,
  type ColumnFilters,
  type MetricRecord,
  type SortState,
} from './metricsTableUtils';

/**
 * Pivoted metric rows plus the sort, column-filter and metric-selection state the
 * table, filters and plot views share. Filters are keyed by column index, so key the
 * consumer by table to reset them when the table changes.
 */
export const useMetricsTableData = (
  metrics: MetricRecord[],
  tableProperties: TableProperties | null
) => {
  const [sort, setSort] = useState<SortState>({ column: null, direction: 'asc' });
  const [filters, setFilters] = useState<ColumnFilters>({});
  const [userSelectedMetrics, setSelectedMetrics] = useState<string[] | null>(null);

  const availableMetrics = tableProperties?.metrics;
  const selectedMetrics = useMemo(() => {
    const current = availableMetrics ?? [];
    if (userSelectedMetrics === null) return current;
    return userSelectedMetrics.filter((metric) => current.includes(metric));
  }, [userSelectedMetrics, availableMetrics]);

  const {
    headers,
    rows: allRows,
    groupByCount,
  } = useMemo(
    () => pivotMetrics(metrics, tableProperties, selectedMetrics),
    [metrics, tableProperties, selectedMetrics]
  );

  const uniqueValuesByColumn = useMemo(
    () => uniqueColumnValues(allRows, groupByCount),
    [allRows, groupByCount]
  );

  const rows = useMemo(
    () => sortRows(filterRows(allRows, filters), sort),
    [allRows, filters, sort]
  );

  const filterValues = Object.values(filters);

  return {
    headers,
    allRows,
    rows,
    groupByCount,
    hasLeadTimeBin: headers.slice(0, groupByCount).some(isLeadTimeBinField),
    uniqueValuesByColumn,

    availableMetrics: availableMetrics ?? [],
    selectedMetrics,
    setSelectedMetrics,

    filters,
    /** Selected values across all column filters. */
    selectionCount: filterValues.reduce((total, values) => total + values.length, 0),
    /** Columns with at least one selected value. */
    filteredColumnCount: filterValues.filter((values) => values.length > 0).length,
    setColumnFilter: (column: number, values: string[]) =>
      setFilters((previous) => ({ ...previous, [column]: values })),
    clearFilters: () => setFilters({}),

    sort,
    toggleSort: (column: number) =>
      setSort((previous) => ({
        column,
        direction: previous.column === column && previous.direction === 'asc' ? 'desc' : 'asc',
      })),
  };
};

export type MetricsTableData = ReturnType<typeof useMetricsTableData>;
