import { Center, Text } from '@mantine/core';
import Plotly from 'plotly.js-dist-min';
import { useEffect, useMemo, useRef } from 'react';

import { usePlotResize } from '@/shared/hooks/usePlotResize';

import { buildLeadTimeTraces } from './metricsTableUtils';
import type { MetricsTableData } from './useMetricsTableData';

import styles from './MetricsLeadTimePlot.module.css';

const LAYOUT: Partial<Plotly.Layout> = {
  title: { text: 'Metrics by Lead Time Bin', x: 0.5, xanchor: 'center' },
  xaxis: {
    title: { text: 'Lead Time (hours)', standoff: 20 },
    type: 'linear',
    showgrid: true,
    gridcolor: 'rgba(0,0,0,0.1)',
  },
  yaxis: {
    title: { text: 'Metric Value', standoff: 20 },
    showgrid: true,
    gridcolor: 'rgba(0,0,0,0.1)',
  },
  margin: { l: 70, r: 50, t: 70, b: 70 },
  showlegend: true,
  legend: { x: 1, xanchor: 'left', y: 1 },
  autosize: true,
};

const CONFIG: Partial<Plotly.Config> = {
  displayModeBar: true,
  modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
  responsive: true,
};

type MetricsLeadTimePlotProps = {
  data: MetricsTableData;
};

/** Step plot of the filtered, selected metrics against lead time. */
const MetricsLeadTimePlot = ({ data }: MetricsLeadTimePlotProps) => {
  const { headers, rows, groupByCount } = data;
  const plotRef = useRef<HTMLDivElement>(null);
  const traces = useMemo(
    () => buildLeadTimeTraces(headers, rows, groupByCount),
    [headers, rows, groupByCount]
  );
  const hasTraces = traces.length > 0;

  usePlotResize(plotRef, hasTraces);

  useEffect(() => {
    const element = plotRef.current;
    if (!element || !hasTraces) return;
    void Plotly.react(element, traces, LAYOUT, CONFIG).catch((error) => {
      console.error('MetricsLeadTimePlot: Failed to render plot', error);
    });
  }, [traces, hasTraces]);

  // Release Plotly's listeners and DOM when the plot goes away
  useEffect(() => {
    const element = plotRef.current;
    return () => {
      if (element) Plotly.purge(element);
    };
  }, [hasTraces]);

  if (!hasTraces) {
    return (
      <Center h="100%">
        <Text size="sm" c="dimmed">
          No metrics to plot. Check the selected metrics and filters.
        </Text>
      </Center>
    );
  }

  return (
    <div className={styles.root}>
      <div ref={plotRef} className={styles.plot} />
    </div>
  );
};

export default MetricsLeadTimePlot;
