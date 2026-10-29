import { useEffect, useRef, useState, useCallback } from 'react';
import { Card } from 'react-bootstrap';

import DashboardPanel from '@/shared/components/DashboardPanel';
import { useTilesLegend } from '@/shared/queries/gridded/tiles';
import type { MapViewport } from '@/shared/types/maps';

import GriddedColorBar from '../gridded/components/GriddedColorBar';
import GriddedControls from '../gridded/components/GriddedControls';
import GriddedMapComponent from '../gridded/components/GriddedMapComponent';
import GriddedPolygonPanel from '../gridded/components/GriddedPolygonPanel';
import GriddedTimeseriesPanel from '../gridded/components/GriddedTimeseriesPanel';
import { ActionTypes, useDashboard } from '../gridded/DashboardContext';
import { useGriddedVariableStyles } from '../gridded/hooks/useGriddedVariableStyles';
import { useViewportUrlSync } from '../gridded/hooks/useViewportUrlSync';
import { OVERLAY_LAYERS } from '../gridded/utils/overlayLayers';
import SnowDisplayPopover from './SnowDisplayPopover';
import UnifiedDashboardShell from './UnifiedDashboardShell';

type ArcGisLegendEntry = {
  label: string;
  imageData: string;
  contentType: string;
  width: number;
  height: number;
};

type ArcGisLegendResponse = {
  layers?: Array<{
    layerId: number;
    legend?: ArcGisLegendEntry[];
  }>;
};

type GriddedTabName = 'dataset' | 'polygons';

const TABS: { id: GriddedTabName; label: string }[] = [
  { id: 'dataset', label: 'Dataset' },
  { id: 'polygons', label: 'Polygon Attributes' },
];

const GriddedLegendCard = () => {
  const { state } = useDashboard();
  const { mapLoaded, activeOverlays, mapFilters } = state;
  const { dataset, variable, colorRamp, colorRampMin, colorRampMax } = mapFilters;

  const [overlayLegends, setOverlayLegends] = useState<Record<string, ArcGisLegendEntry[]>>({});
  const fetchedLegends = useRef<Set<string>>(new Set());
  const tilesLegend = useTilesLegend(dataset, variable, colorRamp, colorRampMin, colorRampMax);

  useEffect(() => {
    const toFetch = OVERLAY_LAYERS.filter(
      (o) => activeOverlays.includes(o.id) && o.legendUrl && !fetchedLegends.current.has(o.id)
    );
    if (toFetch.length === 0) return;

    toFetch.forEach(async (overlay) => {
      fetchedLegends.current.add(overlay.id);
      const legendUrl = overlay.legendUrl;
      if (!legendUrl) return;
      try {
        const res = await fetch(legendUrl);
        const json: ArcGisLegendResponse = await res.json();
        const layer = json.layers?.find((l) => l.layerId === overlay.legendLayerId);
        const legendEntries = layer?.legend;
        if (legendEntries) {
          setOverlayLegends((prev) => ({ ...prev, [overlay.id]: legendEntries }));
        }
      } catch {
        // Legend fetch failure is non-critical.
      }
    });
  }, [activeOverlays]);

  const colorLegend = mapLoaded && dataset && variable ? (tilesLegend.data ?? null) : null;
  const activeLegendEntries = OVERLAY_LAYERS.filter(
    (o) => activeOverlays.includes(o.id) && overlayLegends[o.id]
  ).map((o) => ({ label: o.label, entries: overlayLegends[o.id] }));

  if (!colorLegend && activeLegendEntries.length === 0) {
    return null;
  }

  return (
    <Card className="shadow-sm snow-unified-view__legend-card">
      <Card.Header className="py-2 px-3">
        <h6 className="mb-0 small">Map Legend</h6>
      </Card.Header>
      <Card.Body className="py-2 px-3" style={{ maxHeight: '40vh', overflowY: 'auto' }}>
        {colorLegend && (
          <div style={{ marginBottom: activeLegendEntries.length > 0 ? '8px' : 0 }}>
            <GriddedColorBar legend={colorLegend} />
          </div>
        )}
        {activeLegendEntries.map(({ label, entries }) => (
          <div
            key={label}
            style={{ fontSize: '0.72rem', marginBottom: entries.length > 1 ? '6px' : 0 }}
          >
            <div style={{ fontWeight: 600, marginBottom: '2px' }}>{label}</div>
            {entries.map((entry, i) => (
              <div key={i} className="d-flex align-items-center gap-1">
                <img
                  src={`data:${entry.contentType};base64,${entry.imageData}`}
                  width={entry.width}
                  height={entry.height}
                  alt={entry.label}
                  style={{ flexShrink: 0 }}
                />
                <span>{entry.label}</span>
              </div>
            ))}
          </div>
        ))}
      </Card.Body>
    </Card>
  );
};

const SnowDashboardView = () => {
  const { state, dispatch } = useDashboard();
  const { resetStyles, applyVariableStyleIfNew } = useGriddedVariableStyles();

  const setMapViewport = useCallback(
    (viewport: NonNullable<MapViewport>) => {
      dispatch({ type: ActionTypes.SET_MAP_VIEWPORT, payload: viewport });
    },
    [dispatch]
  );

  useViewportUrlSync({ mapViewport: state.mapViewport, setMapViewport });

  useEffect(() => {
    if (state.mapFilters.dataset) {
      resetStyles();
    }
  }, [state.mapFilters.dataset, resetStyles]);

  useEffect(() => {
    applyVariableStyleIfNew(state.mapFilters.variable);
  }, [state.mapFilters.variable, applyVariableStyleIfNew]);

  const sideOverlayContent = (
    <div className="snow-unified-view__side-stack">
      {state.error && (
        <div className="alert alert-danger alert-dismissible mb-2" role="alert">
          <i className="bi bi-exclamation-triangle-fill me-2"></i>
          <strong>Error:</strong> {state.error}
          <button
            type="button"
            className="btn-close"
            onClick={() => dispatch({ type: ActionTypes.CLEAR_ERROR })}
            aria-label="Close"
          ></button>
        </div>
      )}

      <div className="snow-unified-view__tabs-shell">
        <ul className="nav nav-tabs" style={{ flex: '0 0 auto' }}>
          {TABS.map((tab) => (
            <li className="nav-item" key={tab.id}>
              <button
                type="button"
                className={`nav-link${state.rightPanelTab === tab.id ? ' active' : ''}`}
                onClick={() => dispatch({ type: ActionTypes.SET_RIGHT_PANEL_TAB, payload: tab.id })}
                style={{ fontSize: '0.88rem', padding: '6px 16px' }}
              >
                {tab.label}
              </button>
            </li>
          ))}
        </ul>

        <div style={{ flex: '1 1 0', minHeight: 0, position: 'relative' }}>
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: state.rightPanelTab === 'dataset' ? 'flex' : 'none',
              flexDirection: 'column',
            }}
          >
            <DashboardPanel style={{ height: '100%' }} bodyStyle={{ overflow: 'auto' }}>
              <GriddedControls />
            </DashboardPanel>
          </div>

          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: state.rightPanelTab === 'polygons' ? 'flex' : 'none',
              flexDirection: 'column',
            }}
          >
            <GriddedPolygonPanel />
          </div>
        </div>
      </div>
    </div>
  );

  const timeseriesOverlay = (
    <div className="snow-unified-view__timeseries-shell">
      <GriddedTimeseriesPanel />
    </div>
  );

  const legendOverlay = <GriddedLegendCard />;

  const mobileBottomSheet = (
    <div className="snow-unified-view__mobile-sheet-stack">
      {legendOverlay}
      {sideOverlayContent}
      {timeseriesOverlay}
    </div>
  );

  const mapContent = (
    <div className="snow-unified-view__map-frame">
      <GriddedMapComponent showLegend={false} />
    </div>
  );

  return (
    <UnifiedDashboardShell
      mapContent={mapContent}
      desktopTopLeftCard={{
        content: legendOverlay,
        className: 'snow-unified-view__desktop-legend-card',
      }}
      desktopTopRightCard={{
        content: <SnowDisplayPopover content={sideOverlayContent} />,
        className: 'snow-unified-view__desktop-display-card',
      }}
      desktopBottomCard={{
        content: timeseriesOverlay,
        className: 'snow-unified-view__desktop-timeseries-card',
      }}
      mobileBottomSheet={{
        content: mobileBottomSheet,
        className: 'snow-unified-view__mobile-sheet-card',
      }}
    />
  );
};

export default SnowDashboardView;
