import { useState, type ReactNode } from 'react';
import { Accordion, Button, Card, CloseButton } from 'react-bootstrap';

import type { MapLocation } from '@/shared/types/locations';

type DrawerKey = 'timeseries' | 'metrics';

type StreamflowDataDockProps = {
  selectedLocation: MapLocation | null;
  onClearSelection: () => void;
  timeseriesContent: (headerControlsTarget: HTMLElement | null) => ReactNode;
  metricsContent: (headerControlsTarget: HTMLElement | null) => ReactNode;
  errorContent?: ReactNode;
};

const StreamflowDataDock = ({
  selectedLocation,
  onClearSelection,
  timeseriesContent,
  metricsContent,
  errorContent,
}: StreamflowDataDockProps) => {
  const [activeDrawer, setActiveDrawer] = useState<DrawerKey | null>('timeseries');
  const [isExpanded, setIsExpanded] = useState(false);
  const [timeseriesControlsTarget, setTimeseriesControlsTarget] = useState<HTMLElement | null>(
    null
  );
  const [metricsControlsTarget, setMetricsControlsTarget] = useState<HTMLElement | null>(null);

  const hasSelection = Boolean(selectedLocation);
  const hasOpenDrawer = hasSelection && activeDrawer !== null;

  const handleDrawerToggle = (drawer: DrawerKey) => {
    if (!hasSelection) {
      return;
    }

    setActiveDrawer((current) => (current === drawer ? null : drawer));
  };

  const handleClearSelection = () => {
    setActiveDrawer('timeseries');
    setIsExpanded(false);
    onClearSelection();
  };

  return (
    <Card
      className={`shadow-lg streamflow-data-dock${hasOpenDrawer ? ' streamflow-data-dock--has-open-drawer' : ''}${isExpanded ? ' streamflow-data-dock--expanded' : ''}`}
      style={{ borderRadius: '10px' }}
    >
      <Card.Header className="py-2 px-3 d-flex align-items-center justify-content-between gap-2 streamflow-data-dock__header">
        <div className="d-flex align-items-center flex-grow-1" style={{ minWidth: 0 }}>
          <span style={{ fontSize: '0.9rem' }}>📍</span>
          <span className="ms-2 text-truncate" style={{ fontWeight: hasSelection ? 600 : 500 }}>
            {selectedLocation ? selectedLocation.name : 'Select a Location'}
          </span>
        </div>

        <div className="d-flex align-items-center gap-2">
          {hasSelection && (
            <CloseButton aria-label="Clear selected location" onClick={handleClearSelection} />
          )}

          {hasSelection && (
            <Button
              type="button"
              size="sm"
              variant={isExpanded ? 'primary' : 'outline-primary'}
              onClick={() => setIsExpanded((value) => !value)}
              aria-pressed={isExpanded}
            >
              {isExpanded ? 'Restore Size' : 'Expand 90%'}
            </Button>
          )}
        </div>
      </Card.Header>

      <Card.Body className="p-0 d-flex flex-column streamflow-data-dock__body">
        {errorContent && <div className="p-2 pb-0">{errorContent}</div>}

        {hasSelection && (
          <Accordion
            activeKey={activeDrawer ?? undefined}
            className="streamflow-data-dock__accordion"
            aria-label="Data sections"
          >
            <Accordion.Item eventKey="timeseries" className="streamflow-data-dock__drawer">
              <div className="streamflow-data-dock__drawer-header-row">
                <button
                  type="button"
                  className="streamflow-data-dock__drawer-toggle"
                  aria-expanded={activeDrawer === 'timeseries'}
                  onClick={() => handleDrawerToggle('timeseries')}
                >
                  <span aria-hidden="true" className="streamflow-data-dock__drawer-chevron">
                    {activeDrawer === 'timeseries' ? '▼' : '▶'}
                  </span>
                  <span>📈 Time Series</span>
                </button>
                <div
                  className="streamflow-data-dock__drawer-header-controls"
                  ref={(element) => {
                    setTimeseriesControlsTarget(element);
                  }}
                />
              </div>
              <Accordion.Collapse eventKey="timeseries">
                <div className="accordion-body streamflow-data-dock__drawer-body">
                  <div className="streamflow-data-dock__drawer-body-scroll">
                    <div className="streamflow-data-dock__timeseries-frame">
                      {timeseriesContent(timeseriesControlsTarget)}
                    </div>
                  </div>
                </div>
              </Accordion.Collapse>
            </Accordion.Item>

            <Accordion.Item eventKey="metrics" className="streamflow-data-dock__drawer">
              <div className="streamflow-data-dock__drawer-header-row">
                <button
                  type="button"
                  className="streamflow-data-dock__drawer-toggle"
                  aria-expanded={activeDrawer === 'metrics'}
                  onClick={() => handleDrawerToggle('metrics')}
                >
                  <span aria-hidden="true" className="streamflow-data-dock__drawer-chevron">
                    {activeDrawer === 'metrics' ? '▼' : '▶'}
                  </span>
                  <span>📊 Metrics</span>
                </button>
                <div
                  className="streamflow-data-dock__drawer-header-controls"
                  ref={(element) => {
                    setMetricsControlsTarget(element);
                  }}
                />
              </div>
              <Accordion.Collapse eventKey="metrics">
                <div className="accordion-body streamflow-data-dock__drawer-body">
                  <div className="streamflow-data-dock__drawer-body-scroll">
                    <div className="streamflow-data-dock__metrics-frame">
                      {metricsContent(metricsControlsTarget)}
                    </div>
                  </div>
                </div>
              </Accordion.Collapse>
            </Accordion.Item>
          </Accordion>
        )}
      </Card.Body>
    </Card>
  );
};

export default StreamflowDataDock;
