import { Duration } from 'luxon';
import type Plotly from 'plotly.js-dist-min';

import type { TableProperties } from '@/shared/api/utils';
import { formatUnknownValueForDisplay } from '@/shared/utils/formatters';

export type MetricRecord = { [name: string]: unknown };
export type Row = string[];
export type SortState = { column: number | null; direction: 'asc' | 'desc' };
/** Selected values per group-by column index; an empty list means no filter. */
export type ColumnFilters = Record<number, string[]>;

const HOUR_MS = 60 * 60 * 1000;

export const isLeadTimeBinField = (field: string) => field.toLowerCase().includes('lead_time_bin');

/**
 * Start of a lead time bin in milliseconds. Bins are ISO durations, either a single
 * duration ("PT6H") or "START_END" ("PT6H_PT12H"); unparseable values sort as 0.
 */
export const leadTimeStartMs = (bin: unknown) => {
  if (typeof bin !== 'string' || !bin) return 0;
  const duration = Duration.fromISO(bin.split('_')[0]);
  return duration.isValid ? duration.as('milliseconds') : 0;
};

// Lead time bins keep their raw value; other numbers show four decimals
const formatCellValue = (header: string, value: unknown) => {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'number' && !isLeadTimeBinField(header)) return value.toFixed(4);
  return formatUnknownValueForDisplay(value, { nullishText: 'N/A' });
};

/**
 * Pivots metric records into table rows: group-by columns first, then the selected
 * metrics, ordered by lead time bin when the table has one. Without table properties
 * it falls back to name/value pairs.
 */
export const pivotMetrics = (
  metrics: MetricRecord[],
  tableProperties: TableProperties | null,
  selectedMetrics: string[]
): { headers: string[]; rows: Row[]; groupByCount: number } => {
  if (!tableProperties?.group_by || !tableProperties?.metrics) {
    if (metrics.length === 0) return { headers: ['Field', 'Value'], rows: [], groupByCount: 0 };

    // Already in metric_name/metric_value form
    if (metrics[0].metric_name && metrics[0].metric_value !== undefined) {
      return {
        headers: ['Metric', 'Value'],
        rows: metrics.map((m) => [String(m.metric_name) || 'Unknown', String(m.metric_value)]),
        groupByCount: 0,
      };
    }

    // Raw properties: show the first record's key/value pairs
    const entries = Object.entries(metrics[0]).filter(
      ([, value]) => value !== null && value !== undefined
    );
    return {
      headers: ['Field', 'Value'],
      rows: entries.map(([key, value]) => [key, formatCellValue(key, value)]),
      groupByCount: 0,
    };
  }

  const groupByFields = tableProperties.group_by;
  const leadTimeBinField = groupByFields.find(isLeadTimeBinField);
  const ordered = leadTimeBinField
    ? [...metrics].sort(
        (a, b) => leadTimeStartMs(a[leadTimeBinField]) - leadTimeStartMs(b[leadTimeBinField])
      )
    : metrics;

  const metricFields = tableProperties.metrics.filter((field) => selectedMetrics.includes(field));
  const headers = [...groupByFields, ...metricFields];
  const rows = ordered.map((item) =>
    headers.map((header) => formatCellValue(header, item[header]))
  );

  return { headers, rows, groupByCount: groupByFields.length };
};

/** Sorted distinct values of each group-by column, for the column filters. */
export const uniqueColumnValues = (rows: Row[], groupByCount: number) => {
  const values: Record<number, string[]> = {};
  for (let column = 0; column < groupByCount; column++) {
    values[column] = [...new Set(rows.map((row) => row[column] ?? ''))].sort();
  }
  return values;
};

export const filterRows = (rows: Row[], filters: ColumnFilters) => {
  const active = Object.entries(filters).filter(([, values]) => values.length > 0);
  if (active.length === 0) return rows;
  return rows.filter((row) => active.every(([column, values]) => values.includes(row[+column])));
};

// Numeric when both values parse as numbers, otherwise a string comparison
export const sortRows = (rows: Row[], { column, direction }: SortState) => {
  if (column === null) return rows;
  const sign = direction === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const aNum = parseFloat(a[column]);
    const bNum = parseFloat(b[column]);
    const result =
      !Number.isNaN(aNum) && !Number.isNaN(bNum)
        ? aNum - bNum
        : String(a[column]).localeCompare(String(b[column]));
    return sign * result;
  });
};

/**
 * Step-line traces of each metric against lead time (bin start, in hours). Rows are
 * split into one trace per combination of the other group-by columns that vary.
 */
export const buildLeadTimeTraces = (
  headers: string[],
  rows: Row[],
  groupByCount: number
): Plotly.Data[] => {
  const groupByFields = headers.slice(0, groupByCount);
  const metricFields = headers.slice(groupByCount);
  const leadTimeIndex = groupByFields.findIndex(isLeadTimeBinField);
  if (leadTimeIndex === -1 || rows.length === 0) return [];

  // Only group-by columns with more than one value split the traces
  const varyingColumns = groupByFields
    .map((field, index) => ({ field, index }))
    .filter(
      ({ index }) => index !== leadTimeIndex && new Set(rows.map((row) => row[index])).size > 1
    );

  const groups = new Map<string, Row[]>();
  for (const row of rows) {
    const key =
      varyingColumns.length > 0
        ? varyingColumns.map(({ field, index }) => `${field}: ${row[index]}`).join(', ')
        : 'All Data';
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }

  const traces: Plotly.Data[] = [];
  for (const [groupKey, groupRows] of groups) {
    const ordered = [...groupRows].sort(
      (a, b) => leadTimeStartMs(a[leadTimeIndex]) - leadTimeStartMs(b[leadTimeIndex])
    );
    const x = ordered.map((row) => leadTimeStartMs(row[leadTimeIndex]) / HOUR_MS);

    metricFields.forEach((metric, i) => {
      const column = groupByCount + i;
      traces.push({
        x,
        y: ordered.map((row) => parseFloat(row[column])),
        type: 'scatter',
        mode: 'lines',
        line: { width: 2, shape: 'hv' }, // horizontal then vertical, for a step plot
        name: varyingColumns.length > 0 ? `${metric} (${groupKey})` : metric,
        hovertemplate:
          varyingColumns.length > 0
            ? `${metric}<br>${groupKey}<br>Lead Time: %{x:.1f}h<br>Value: %{y}<extra></extra>`
            : `${metric}<br>Lead Time: %{x:.1f}h<br>Value: %{y}<extra></extra>`,
      });
    });
  }
  return traces;
};
