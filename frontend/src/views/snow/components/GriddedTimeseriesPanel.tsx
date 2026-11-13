import { Center, Group, List, Loader, SegmentedControl, Stack, Text } from '@mantine/core';
import { IconChartLine, IconDatabaseOff, IconFilter } from '@tabler/icons-react';
import { useQueries } from '@tanstack/react-query';
import Plotly from 'plotly.js-dist-min';
import { useEffect, useRef, useState } from 'react';

import { usePlotResize } from '@/shared/hooks/usePlotResize';
import { useEdrTimeseries } from '@/shared/queries/gridded/edr';
import { usePolygonTimeseries } from '@/shared/queries/gridded/polygonTimeseries';
import { variableAttrsQueryOptions } from '@/shared/queries/gridded/variableAttrs';
import { parseUtcTime, shortestStep } from '@/shared/utils/dates';
import { formatUnitName, formatVariableName } from '@/shared/utils/formatters';
import { seriesColor } from '@/shared/utils/plotColors';

import { ActionTypes, timeseriesDatasets, useDashboard } from '../DashboardContext';
import GriddedTimeseriesControls from './GriddedTimeseriesControls';

import styles from './GriddedTimeseriesPanel.module.css';

type PlotSeries = {
  name: string;
  variable: string;
  unit: string;
  times: string[];
  values: (number | null)[];
};

type PlotData = { plotted: PlotSeries[]; notes: string[]; isLoading: boolean };

// Break the line across missing steps: a gap longer than the series' shortest step gets a null
const withGaps = ({ times, values }: PlotSeries) => {
  const ms = times.map(parseUtcTime);
  const step = shortestStep(ms);
  const x: string[] = [];
  const y: (number | null)[] = [];
  times.forEach((time, i) => {
    if (i > 0 && ms[i] - ms[i - 1] > step) {
      x.push(new Date(ms[i - 1] + step).toISOString().slice(0, 19));
      y.push(null);
    }
    x.push(time);
    y.push(values[i]);
  });
  return { x, y };
};

const GriddedTimeseriesPanel = () => {
  const { state, dispatch } = useDashboard();
  const { mapFilters, clickedPoint, polygonQuery, timeseriesFilters } = state;
  const plotRef = useRef<HTMLDivElement>(null);
  const [viewMode, setViewMode] = useState('plot');

  // A new map click or polygon load shows its plot
  const request = clickedPoint ?? polygonQuery;
  const [lastRequest, setLastRequest] = useState(request);
  if (request !== lastRequest) {
    setLastRequest(request);
    if (request) setViewMode('plot');
  }

  const datasets = timeseriesDatasets(timeseriesFilters, mapFilters.dataset);
  const series = useEdrTimeseries({
    ...timeseriesFilters,
    datasets,
    preferredVariable: mapFilters.variable,
    lon: clickedPoint?.lon,
    lat: clickedPoint?.lat,
    anchor: clickedPoint?.time,
  });
  const variableAttrs = useQueries({
    queries: datasets.map((ds) => variableAttrsQueryOptions(ds)),
  });
  const polygonSeries = usePolygonTimeseries({
    ...timeseriesFilters,
    datasets,
    locationId: polygonQuery?.location_id,
    variable: mapFilters.variable,
    anchor: polygonQuery?.time,
  });

  // Point and polygon queries plot through the same series shape
  const { plotted, notes, isLoading }: PlotData = polygonQuery
    ? {
        plotted: (polygonSeries.data ?? []).map((ts) => ({
          name: ts.configuration_name,
          variable: formatVariableName(ts.variable_name),
          unit: formatUnitName(ts.unit_name),
          times: ts.timeseries.map((p) => p.value_time),
          values: ts.timeseries.map((p) => p.value),
        })),
        notes: polygonSeries.error ? [polygonSeries.error.message] : [],
        isLoading: polygonSeries.isLoading,
      }
    : {
        plotted: series.flatMap((s, i) =>
          s.data?.values.some((v) => v !== null)
            ? [
                {
                  name: s.datasetId,
                  variable: formatVariableName(s.variable ?? undefined),
                  unit: formatUnitName(
                    s.variable ? (variableAttrs[i]?.data?.[s.variable]?.units ?? null) : null
                  ),
                  ...s.data,
                },
              ]
            : []
        ),
        notes: series.flatMap((s) =>
          s.skipped ? [s.skipped] : s.error ? [`${s.datasetId}: ${s.error}`] : []
        ),
        isLoading: series.some((s) => s.isLoading),
      };
  usePlotResize(plotRef, viewMode === 'plot' && !!request && !isLoading && plotted.length > 0);

  useEffect(() => {
    if (!plotRef.current || !request || plotted.length === 0) return;
    const traces = plotted.map((s, i) => ({
      ...withGaps(s),
      name: `${s.name} · ${s.variable}${s.unit ? ` (${s.unit})` : ''}`,
      type: 'scatter',
      mode: 'lines+markers',
      connectgaps: false,
      marker: { size: 4 },
      line: { color: seriesColor(i) },
      hovertemplate:
        '<b>%{fullData.name}</b><br>' +
        'Date: %{x}<br>' +
        `${s.variable}: %{y}${s.unit ? ' ' + s.unit : ''}<br>` +
        '<extra></extra>',
    }));
    const sharedUnit = plotted.every((s) => s.unit === plotted[0].unit) ? plotted[0].unit : '';

    void Plotly.react(
      plotRef.current,
      traces as Partial<Plotly.ScatterData>[],
      {
        xaxis: { title: 'Time', type: 'date' },
        yaxis: { title: sharedUnit || 'Value' },
        showlegend: true,
        legend: { orientation: 'h', y: -0.2 },
        margin: { t: 10, r: 20, b: 50, l: 60 },
        autosize: true,
      } as Partial<Plotly.Layout>,
      { responsive: true, displayModeBar: false }
    );
  });

  const notesList = notes.length > 0 && (
    <List size="sm" c="dimmed" withPadding className={styles.notes}>
      {notes.map((note) => (
        <List.Item key={note}>{note}</List.Item>
      ))}
    </List>
  );

  let plotBody;
  if (!request) {
    plotBody = (
      <Center h="100%">
        <Text size="sm" c="dimmed">
          Click a point on the map, or load a timeseries for a selected polygon
        </Text>
      </Center>
    );
  } else if (isLoading) {
    plotBody = (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <Loader />
        <Text size="sm" c="dimmed">
          Loading timeseries data...
        </Text>
      </Stack>
    );
  } else if (plotted.length === 0) {
    plotBody = (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <IconDatabaseOff size={32} stroke={1.5} color="var(--mantine-color-dimmed)" />
        <Text fw={600} c="dimmed">
          No Data Available
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          Try switching to Filters to adjust the datasets or time span.
        </Text>
        {notesList}
      </Stack>
    );
  } else {
    // Keyed so React never reuses this div for another state with Plotly's nodes still in it
    plotBody = (
      <div key="plot" className={styles.plot}>
        <div ref={plotRef} className={styles.plotArea} />
        {notesList}
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <Group justify="flex-end" className={styles.toolbar}>
        <SegmentedControl
          size="xs"
          value={viewMode}
          onChange={setViewMode}
          data={[
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
          ]}
        />
      </Group>
      <div className={styles.body}>
        {viewMode === 'filters' ? (
          <div className={styles.filters}>
            <GriddedTimeseriesControls
              timeseriesFilters={timeseriesFilters}
              updateTimeseriesFilters={(patch) =>
                dispatch({ type: ActionTypes.UPDATE_TIMESERIES_FILTERS, payload: patch })
              }
              activeDataset={mapFilters.dataset}
            />
          </div>
        ) : (
          plotBody
        )}
      </div>
    </div>
  );
};

export default GriddedTimeseriesPanel;
