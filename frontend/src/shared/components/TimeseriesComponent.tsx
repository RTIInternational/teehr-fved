import React, { useEffect, useRef, useState } from 'react';
import { Card, Spinner, ButtonGroup, Button } from 'react-bootstrap';
import { createPortal } from 'react-dom';

import type { TimeseriesRequestFilters } from '@/shared/api/timeseries';
import PlotlyChart from '@/shared/components/PlotlyChart';
import { usePrimaryTimeseries, useSecondaryTimeseries } from '@/shared/queries/timeseries';
import type { TimeseriesState } from '@/shared/types/timeseries';

type TimeseriesControlInjectedProps = {
  setRequestFilters: (filters: TimeseriesRequestFilters) => void;
  onViewModeChange: (viewMode: string) => void;
};

type TimeseriesComponentProps<TControlsProps extends object> = {
  state: TimeseriesState;
  Controls: React.ComponentType<TControlsProps & TimeseriesControlInjectedProps>;
  controlsProps: TControlsProps;
  embeddedInAccordion?: boolean;
  headerControlsTarget?: Element | null;
  initialViewMode?: 'filters' | 'plot';
  autoRequestFilters?: TimeseriesRequestFilters | null;
};

const TimeseriesComponent = <TControlsProps extends object>({
  state,
  Controls,
  controlsProps,
  embeddedInAccordion = false,
  headerControlsTarget = null,
  initialViewMode = 'filters',
  autoRequestFilters = null,
}: TimeseriesComponentProps<TControlsProps>) => {
  const [viewMode, setViewMode] = useState(initialViewMode);
  const [requestFilters, setRequestFilters] = useState<TimeseriesRequestFilters>();
  const lastAutoRequestKeyRef = useRef<string | null>(null);
  const primary = usePrimaryTimeseries(requestFilters);
  const secondary = useSecondaryTimeseries(requestFilters);

  useEffect(() => {
    if (!autoRequestFilters) {
      lastAutoRequestKeyRef.current = null;
      return;
    }

    const nextRequestKey = JSON.stringify(autoRequestFilters);
    if (lastAutoRequestKeyRef.current === nextRequestKey) {
      return;
    }

    lastAutoRequestKeyRef.current = nextRequestKey;
    setRequestFilters(autoRequestFilters);
  }, [autoRequestFilters]);

  const primaryData = primary.data ?? [];
  const secondaryData = secondary.data ?? [];

  const hasData = primaryData.length > 0 || secondaryData.length > 0;

  const modeButtons = state.selectedLocation && (
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
  );

  const shouldPortalModeButtons = Boolean(
    headerControlsTarget && modeButtons && state.selectedLocation
  );
  const modeButtonsPortal =
    shouldPortalModeButtons && headerControlsTarget && modeButtons
      ? createPortal(modeButtons, headerControlsTarget)
      : null;

  const bodyContent = !state.selectedLocation ? (
    <div className="d-flex align-items-center justify-content-center flex-grow-1 text-muted">
      <div className="text-center">
        <div style={{ fontSize: '3rem' }}>📍</div>
        <h5>Select a Location</h5>
        <p>Click on a location on the map to view its time series data.</p>
      </div>
    </div>
  ) : viewMode === 'filters' ? (
    <div className="p-3 flex-grow-1 overflow-auto">
      <Controls
        {...controlsProps}
        setRequestFilters={setRequestFilters}
        onViewModeChange={setViewMode}
      />
    </div>
  ) : primary.isLoading || secondary.isLoading ? (
    <div className="d-flex justify-content-center align-items-center flex-grow-1">
      <div className="text-center">
        <Spinner animation="border" variant="primary" />
        <div className="mt-2 small text-muted">Loading timeseries data...</div>
      </div>
    </div>
  ) : (
    <>
      {hasData ? (
        <div className="flex-grow-1 p-2" style={{ overflow: 'hidden', minHeight: 0 }}>
          <PlotlyChart
            primaryData={primaryData}
            secondaryData={secondaryData}
            selectedLocation={state.selectedLocation}
            filters={state.timeseriesFilters}
            height="100%"
          />
        </div>
      ) : (
        <div className="d-flex align-items-center justify-content-center flex-grow-1 text-muted">
          <div className="text-center">
            <div style={{ fontSize: '2rem' }}>📊</div>
            <h6>No Data Available</h6>
            <p className="small">
              Try switching to Filters to adjust the time range or check if data exists for this
              location.
            </p>
          </div>
        </div>
      )}
    </>
  );

  if (embeddedInAccordion) {
    return (
      <>
        {modeButtonsPortal}
        <div className="timeseries-component--embedded h-100 d-flex flex-column">
          {!shouldPortalModeButtons && state.selectedLocation && (
            <div className="timeseries-component--embedded__controls">{modeButtons}</div>
          )}
          <div className="d-flex flex-column flex-grow-1 overflow-hidden">{bodyContent}</div>
        </div>
      </>
    );
  }

  return (
    <Card className="shadow-lg h-100 d-flex flex-column" style={{ borderRadius: '8px' }}>
      <Card.Header className="py-2 d-flex justify-content-between align-items-center flex-shrink-0">
        <div className="d-flex align-items-center gap-2">
          <Card.Title as="h6" className="mb-0">
            📈 Time Series
          </Card.Title>
          {modeButtons}
        </div>
      </Card.Header>
      <Card.Body className="p-0 d-flex flex-column flex-grow-1 overflow-hidden">
        {bodyContent}
      </Card.Body>
    </Card>
  );
};

export default TimeseriesComponent;
