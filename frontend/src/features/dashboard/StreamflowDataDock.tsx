import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { Accordion, Button, Card, CloseButton } from 'react-bootstrap';

import type { MapLocation } from '@/shared/types/locations';

type DrawerKey = 'timeseries' | 'metrics';

type StreamflowDataDockProps = {
  selectedLocation: MapLocation | null;
  onClearSelection: () => void;
  timeseriesContent: ReactNode;
  metricsContent: ReactNode;
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

  const hasSelection = Boolean(selectedLocation);

  const handleAccordionSelect = (
    eventKey: string | string[] | null | undefined,
    _event: SyntheticEvent<unknown>
  ) => {
    if (!hasSelection) {
      return;
    }

    if (Array.isArray(eventKey)) {
      return;
    }

    if (eventKey === 'timeseries' || eventKey === 'metrics') {
      setActiveDrawer(eventKey);
      return;
    }

    setActiveDrawer(null);
  };

  const handleClearSelection = () => {
    setActiveDrawer('timeseries');
    setIsExpanded(false);
    onClearSelection();
  };

  return (
    <Card
      className={`shadow-lg streamflow-data-dock${isExpanded ? ' streamflow-data-dock--expanded' : ''}`}
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

          <Button
            type="button"
            size="sm"
            variant={isExpanded ? 'primary' : 'outline-primary'}
            onClick={() => setIsExpanded((value) => !value)}
            aria-pressed={isExpanded}
          >
            {isExpanded ? 'Restore Size' : 'Expand 90%'}
          </Button>
        </div>
      </Card.Header>

      <Card.Body className="p-0 d-flex flex-column streamflow-data-dock__body">
        {errorContent && <div className="p-2 pb-0">{errorContent}</div>}

        <Accordion
          activeKey={hasSelection ? (activeDrawer ?? undefined) : undefined}
          onSelect={handleAccordionSelect}
          className="streamflow-data-dock__accordion"
        >
          <Accordion.Item
            eventKey="timeseries"
            className={`streamflow-data-dock__drawer${hasSelection ? '' : ' is-disabled'}`}
          >
            <Accordion.Header>
              <span aria-disabled={!hasSelection}>📈 Time Series</span>
            </Accordion.Header>
            <Accordion.Body className="streamflow-data-dock__drawer-body">
              <div className="streamflow-data-dock__timeseries-frame">{timeseriesContent}</div>
            </Accordion.Body>
          </Accordion.Item>

          <Accordion.Item
            eventKey="metrics"
            className={`streamflow-data-dock__drawer${hasSelection ? '' : ' is-disabled'}`}
          >
            <Accordion.Header>
              <span aria-disabled={!hasSelection}>📊 Metrics</span>
            </Accordion.Header>
            <Accordion.Body className="streamflow-data-dock__drawer-body">
              <div className="streamflow-data-dock__metrics-frame">{metricsContent}</div>
            </Accordion.Body>
          </Accordion.Item>
        </Accordion>
      </Card.Body>
    </Card>
  );
};

export default StreamflowDataDock;
