import { useQueries } from '@tanstack/react-query';
import Plotly from 'plotly.js-dist-min';
import { useEffect, useRef, useState } from 'react';
import { Button, ButtonGroup, Spinner } from 'react-bootstrap';

import DashboardPanel from '@/shared/components/DashboardPanel';
import { useEdrTimeseries } from '@/shared/queries/gridded/edr';
import { variableAttrsQueryOptions } from '@/shared/queries/gridded/variableAttrs';
import { formatUnitName, formatVariableName } from '@/shared/utils/formatters';
import { seriesColor } from '@/shared/utils/plotColors';

import { ActionTypes, timeseriesDatasets, useDashboard } from '../DashboardContext';
import GriddedTimeseriesControls from './GriddedTimeseriesControls';

const formatPoint = (lat: number, lon: number) =>
  `(${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(4)}°${lon >= 0 ? 'E' : 'W'})`;

const GriddedTimeseriesPanel = () => {
  const { state, dispatch } = useDashboard();
  const { mapFilters, clickedPoint, timeseriesFilters } = state;
  const plotRef = useRef<HTMLDivElement>(null);
  const [viewMode, setViewMode] = useState('plot');

  // A new map click shows its plot
  const [lastClickedPoint, setLastClickedPoint] = useState(clickedPoint);
  if (clickedPoint !== lastClickedPoint) {
    setLastClickedPoint(clickedPoint);
    if (clickedPoint) setViewMode('plot');
  }

  const datasets = timeseriesDatasets(timeseriesFilters, mapFilters.dataset);
  const series = useEdrTimeseries({
    ...timeseriesFilters,
    datasets,
    preferredVariable: mapFilters.variable,
    lon: clickedPoint?.lon,
    lat: clickedPoint?.lat,
  });
  const variableAttrs = useQueries({
    queries: datasets.map((ds) => variableAttrsQueryOptions(ds)),
  });

  const units = series.map((s, i) =>
    formatUnitName(s.variable ? (variableAttrs[i]?.data?.[s.variable]?.units ?? null) : null)
  );
  const plotted = series
    .map((s, i) => ({ ...s, unit: units[i] }))
    .filter((s) => s.data && s.data.times.length > 0);
  const notes = series.flatMap((s) =>
    s.skipped ? [s.skipped] : s.error ? [`${s.datasetId}: ${s.error}`] : []
  );
  const isLoading = series.some((s) => s.isLoading);

  useEffect(() => {
    if (!plotRef.current || !clickedPoint || plotted.length === 0) return;
    const traces = plotted.map((s, i) => {
      const varName = formatVariableName(s.variable ?? undefined);
      return {
        x: s.data!.times,
        y: s.data!.values,
        name: `${s.datasetId} · ${varName}${s.unit ? ` (${s.unit})` : ''}`,
        type: 'scatter',
        mode: 'lines+markers',
        marker: { size: 4 },
        line: { color: seriesColor(i) },
        hovertemplate:
          '<b>%{fullData.name}</b><br>' +
          'Date: %{x}<br>' +
          `${varName}: %{y}${s.unit ? ' ' + s.unit : ''}<br>` +
          '<extra></extra>',
      };
    });
    const sharedUnit = plotted.every((s) => s.unit === plotted[0].unit) ? plotted[0].unit : '';

    void Plotly.react(
      plotRef.current,
      traces as Partial<Plotly.ScatterData>[],
      {
        title: { text: formatPoint(clickedPoint.lat, clickedPoint.lon), font: { size: 13 } },
        xaxis: { title: 'Time', type: 'date' },
        yaxis: { title: sharedUnit || 'Value' },
        showlegend: true,
        legend: { orientation: 'h', y: -0.2 },
        margin: { t: 40, r: 20, b: 50, l: 60 },
        autosize: true,
      } as Partial<Plotly.Layout>,
      { responsive: true, displayModeBar: false }
    );
  });

  const header = (
    <div className="d-flex justify-content-between align-items-center">
      <span className="small fw-bold">Timeseries</span>
      <ButtonGroup size="sm">
        <Button
          variant={viewMode === 'filters' ? 'primary' : 'outline-primary'}
          onClick={() => setViewMode('filters')}
          style={{ fontSize: '11px' }}
        >
          🔍 Filters
        </Button>
        <Button
          variant={viewMode === 'plot' ? 'primary' : 'outline-primary'}
          onClick={() => setViewMode('plot')}
          style={{ fontSize: '11px' }}
        >
          📈 Plot
        </Button>
      </ButtonGroup>
    </div>
  );

  const notesList = notes.length > 0 && (
    <ul className="small text-muted mb-0 px-3 pb-2" style={{ flex: '0 0 auto' }}>
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  );

  let body;
  if (viewMode === 'filters') {
    body = (
      <div className="p-3 h-100 overflow-auto">
        <GriddedTimeseriesControls
          timeseriesFilters={timeseriesFilters}
          updateTimeseriesFilters={(patch) =>
            dispatch({ type: ActionTypes.UPDATE_TIMESERIES_FILTERS, payload: patch })
          }
          activeDataset={mapFilters.dataset}
        />
      </div>
    );
  } else if (!clickedPoint) {
    body = (
      <div className="d-flex align-items-center justify-content-center h-100 text-muted small">
        Click a point on the map, or load a timeseries for a selected polygon
      </div>
    );
  } else if (isLoading && plotted.length === 0) {
    body = (
      <div className="d-flex justify-content-center align-items-center h-100">
        <div className="text-center">
          <Spinner animation="border" variant="primary" />
          <div className="mt-2 small text-muted">Loading timeseries data...</div>
        </div>
      </div>
    );
  } else if (plotted.length === 0) {
    body = (
      <div className="d-flex flex-column align-items-center justify-content-center h-100">
        <div className="text-center text-muted">
          <div style={{ fontSize: '2rem' }}>📊</div>
          <h6>No Data Available</h6>
          <p className="small">Try switching to Filters to adjust the datasets or time span.</p>
        </div>
        {notesList}
      </div>
    );
  } else {
    body = (
      <div className="d-flex flex-column h-100">
        <div ref={plotRef} style={{ flex: '1 1 auto', minHeight: 0, width: '100%' }} />
        {notesList}
      </div>
    );
  }

  return (
    <DashboardPanel
      header={header}
      style={{ height: '100%' }}
      bodyStyle={{ padding: 0, overflow: 'hidden', height: '100%' }}
    >
      {body}
    </DashboardPanel>
  );
};

export default GriddedTimeseriesPanel;
