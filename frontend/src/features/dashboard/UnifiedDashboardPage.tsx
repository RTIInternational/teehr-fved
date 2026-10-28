import type { Feature, Point } from 'geojson';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card } from 'react-bootstrap';

import { ForecastDashboardProvider } from '@/features/forecast';
import TimeseriesControls from '@/features/forecast/components/TimeseriesControls';
import {
  ActionTypes as ForecastActionTypes,
  useDashboard as useForecastDashboard,
} from '@/features/forecast/DashboardContext';
import { useFilters } from '@/features/forecast/hooks/useFilters';
import { useInitialFilters } from '@/features/forecast/hooks/useInitialFilters';
import { useLocationSelection } from '@/features/forecast/hooks/useLocationSelection';
import { useViewportUrlSync as useForecastViewportUrlSync } from '@/features/forecast/hooks/useViewportUrlSync';
import DashboardPanel from '@/shared/components/DashboardPanel';
import LocationCard from '@/shared/components/LocationCard';
import LocationMetrics from '@/shared/components/LocationMetrics';
import MapFilterButton from '@/shared/components/MapFilterButton';
import MapLegend from '@/shared/components/MapLegend';
import TimeseriesComponent from '@/shared/components/TimeseriesComponent';
import { useTilesLegend } from '@/shared/queries/gridded/tiles';
import { useMetricLocations } from '@/shared/queries/metrics';
import type { MapViewport } from '@/shared/types/maps';

import { GriddedDashboardProvider } from '../gridded';
import GriddedColorBar from '../gridded/components/GriddedColorBar';
import GriddedControls from '../gridded/components/GriddedControls';
import GriddedMapComponent from '../gridded/components/GriddedMapComponent';
import GriddedPolygonPanel from '../gridded/components/GriddedPolygonPanel';
import GriddedTimeseriesPanel from '../gridded/components/GriddedTimeseriesPanel';
import {
  ActionTypes as GriddedActionTypes,
  useDashboard as useGriddedDashboard,
} from '../gridded/DashboardContext';
import { useGriddedVariableStyles } from '../gridded/hooks/useGriddedVariableStyles';
import { useViewportUrlSync as useGriddedViewportUrlSync } from '../gridded/hooks/useViewportUrlSync';
import { OVERLAY_LAYERS } from '../gridded/utils/overlayLayers';
import StreamflowDataDock from './StreamflowDataDock';
import UnifiedDashboardShell from './UnifiedDashboardShell';

const STREAMFLOW_TABLES = ['fcst_metrics_by_location', 'fcst_metrics_by_lead_time_bins'];

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

const EmptyTimeseriesCard = () => {
  return (
    <Card className="shadow-sm streamflow-unified-view__empty-card">
      <Card.Body className="d-flex align-items-center justify-content-center h-100 text-muted">
        <div className="text-center">
          <div style={{ fontSize: '2.2rem' }}>📈</div>
          <h6>Select a Location</h6>
          <p className="small mb-0">Click on a location on the map to view time series data.</p>
        </div>
      </Card.Body>
    </Card>
  );
};

const EmptyMetricsCard = () => {
  return (
    <Card className="shadow-sm streamflow-unified-view__empty-card h-100">
      <Card.Body className="d-flex align-items-center justify-content-center h-100 text-muted">
        <div className="text-center">
          <div style={{ fontSize: '2rem' }}>📊</div>
          <h6>Metrics</h6>
          <p className="small mb-0">Select a location to view metrics.</p>
        </div>
      </Card.Body>
    </Card>
  );
};

const GriddedLegendCard = () => {
  const { state } = useGriddedDashboard();
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

type UnifiedDashboardContentProps = {
  view: string;
};

const UnifiedDashboardContent = ({ view }: UnifiedDashboardContentProps) => {
  const isSnowView = view === 'snow';

  const { state: forecastState, dispatch: forecastDispatch } = useForecastDashboard();
  const { state: griddedState, dispatch: griddedDispatch } = useGriddedDashboard();
  const { selectLocation, selectedLocation } = useLocationSelection();
  const { mapFilters, updateMapFilters, timeseriesFilters, updateTimeseriesFilters } = useFilters();
  const [searchTerm, setSearchTerm] = useState('');

  const { resetStyles, applyVariableStyleIfNew } = useGriddedVariableStyles();

  useInitialFilters(STREAMFLOW_TABLES[0]);

  const setForecastMapViewport = useCallback(
    (viewport: NonNullable<typeof forecastState.mapViewport>) => {
      forecastDispatch({ type: ForecastActionTypes.SET_MAP_VIEWPORT, payload: viewport });
    },
    [forecastDispatch]
  );

  const setGriddedMapViewport = useCallback(
    (viewport: NonNullable<MapViewport>) => {
      griddedDispatch({ type: GriddedActionTypes.SET_MAP_VIEWPORT, payload: viewport });
    },
    [griddedDispatch]
  );

  useForecastViewportUrlSync({
    mapViewport: forecastState.mapViewport,
    setMapViewport: setForecastMapViewport,
  });
  useGriddedViewportUrlSync({
    mapViewport: griddedState.mapViewport,
    setMapViewport: setGriddedMapViewport,
  });

  useEffect(() => {
    if (griddedState.mapFilters.dataset) {
      resetStyles();
    }
  }, [griddedState.mapFilters.dataset, resetStyles]);

  useEffect(() => {
    applyVariableStyleIfNew(griddedState.mapFilters.variable);
  }, [griddedState.mapFilters.variable, applyVariableStyleIfNew]);

  const locationFilters = useMemo(() => {
    if (!mapFilters.configuration || !mapFilters.variable) {
      return undefined;
    }

    return {
      table: STREAMFLOW_TABLES[0],
      configuration: mapFilters.configuration,
      variable: mapFilters.variable,
    };
  }, [mapFilters.configuration, mapFilters.variable]);

  const locations = useMetricLocations(locationFilters);

  const matchedLocations = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const features = locations.data?.features || [];

    if (!term) return [];

    return features
      .filter((feature: Feature) => {
        const props = feature?.properties || {};
        const primaryId = String(props.primary_location_id || '').toLowerCase();
        const secondaryId = String(props.secondary_location_id || '').toLowerCase();
        const name = String(props.name || '').toLowerCase();

        return primaryId.includes(term) || secondaryId.includes(term) || name.includes(term);
      })
      .slice(0, 15);
  }, [searchTerm, locations.data]);

  const handleSearchSelect = useCallback(
    (feature: Feature<Point>) => {
      const properties = feature.properties;
      const coordinates = feature.geometry?.coordinates;

      if (!properties || !Array.isArray(coordinates) || coordinates.length < 2) return;

      const lon = Number(coordinates[0]);
      const lat = Number(coordinates[1]);
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;

      selectLocation({
        primary_location_id: String(properties.primary_location_id || ''),
        secondary_location_id: String(properties.secondary_location_id || ''),
        name: String(properties.name || properties.primary_location_id || 'Unnamed location'),
        coordinates: [lon, lat],
      });

      setForecastMapViewport({
        center: [lon, lat],
        zoom: Math.max(forecastState.mapViewport?.zoom ?? 10, 10),
      });
      setSearchTerm('');
    },
    [selectLocation, setForecastMapViewport, forecastState.mapViewport?.zoom]
  );

  const mapContent = (
    <div
      className={isSnowView ? 'snow-unified-view__map-frame' : 'streamflow-unified-view__map-frame'}
    >
      <GriddedMapComponent
        mode={isSnowView ? 'snow' : 'streamflow'}
        showLegend={false}
        streamflow={{
          state: forecastState,
          dispatch: forecastDispatch,
          table: STREAMFLOW_TABLES[0],
          selectedLocation,
          selectLocation,
        }}
      />
    </div>
  );

  const streamflowTimeseriesPanel = selectedLocation ? (
    <TimeseriesComponent
      key={selectedLocation.primary_location_id}
      state={forecastState}
      Controls={TimeseriesControls}
      controlsProps={{
        table: STREAMFLOW_TABLES[0],
        timeseriesFilters,
        updateTimeseriesFilters,
        selectedLocation,
        mapFilters,
      }}
    />
  ) : (
    <EmptyTimeseriesCard />
  );

  const streamflowDockTimeseriesPanel = (headerControlsTarget: HTMLElement | null) =>
    selectedLocation ? (
      <TimeseriesComponent
        key={`dock-${selectedLocation.primary_location_id}`}
        state={forecastState}
        Controls={TimeseriesControls}
        controlsProps={{
          table: STREAMFLOW_TABLES[0],
          timeseriesFilters,
          updateTimeseriesFilters,
          selectedLocation,
          mapFilters,
        }}
        embeddedInAccordion
        headerControlsTarget={headerControlsTarget}
      />
    ) : (
      <EmptyTimeseriesCard />
    );

  const streamflowSideCard = (
    <div className="streamflow-unified-view__side-stack">
      {forecastState.error && (
        <div className="alert alert-danger alert-dismissible mb-2" role="alert">
          <i className="bi bi-exclamation-triangle-fill me-2"></i>
          <strong>Error:</strong> {forecastState.error}
          <button
            type="button"
            className="btn-close"
            onClick={() => forecastDispatch({ type: ForecastActionTypes.CLEAR_ERROR })}
            aria-label="Close"
          ></button>
        </div>
      )}

      <LocationCard selectedLocation={selectedLocation} onClose={() => selectLocation(null)} />

      <div className="streamflow-unified-view__timeseries-card">{streamflowTimeseriesPanel}</div>
    </div>
  );

  const streamflowMetricsCard = selectedLocation ? (
    <LocationMetrics selectedLocation={selectedLocation} tables={STREAMFLOW_TABLES} />
  ) : (
    <EmptyMetricsCard />
  );

  const streamflowDockMetricsPanel = (headerControlsTarget: HTMLElement | null) =>
    selectedLocation ? (
      <LocationMetrics
        selectedLocation={selectedLocation}
        tables={STREAMFLOW_TABLES}
        embeddedInAccordion
        headerControlsTarget={headerControlsTarget}
      />
    ) : (
      <EmptyMetricsCard />
    );

  const streamflowDesktopDataDock = (
    <StreamflowDataDock
      selectedLocation={selectedLocation}
      onClearSelection={() => selectLocation(null)}
      timeseriesContent={streamflowDockTimeseriesPanel}
      metricsContent={streamflowDockMetricsPanel}
      errorContent={
        forecastState.error ? (
          <div className="alert alert-danger alert-dismissible mb-0" role="alert">
            <i className="bi bi-exclamation-triangle-fill me-2"></i>
            <strong>Error:</strong> {forecastState.error}
            <button
              type="button"
              className="btn-close"
              onClick={() => forecastDispatch({ type: ForecastActionTypes.CLEAR_ERROR })}
              aria-label="Close"
            ></button>
          </div>
        ) : null
      }
    />
  );

  const streamflowMapOverlayCard = (
    <div className="streamflow-unified-view__map-overlay-stack">
      <Card className="shadow-sm streamflow-unified-view__search-card">
        <Card.Body className="p-2">
          <div className="input-group shadow-sm" style={{ height: '38px' }}>
            <span
              className="input-group-text bg-white border-end-0 rounded-start-3"
              aria-hidden="true"
            >
              🔎
            </span>
            <input
              type="text"
              className="form-control border-start-0"
              placeholder="Search by primary ID, secondary ID, or name"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              aria-label="Search map locations"
              style={{ height: '38px' }}
            />
            {searchTerm && (
              <button
                type="button"
                className="btn rounded-end-3"
                onClick={() => setSearchTerm('')}
                aria-label="Clear search"
                style={{
                  height: '38px',
                  backgroundColor: '#ffffff',
                  borderColor: '#ced4da',
                  color: '#6c757d',
                }}
              >
                Clear
              </button>
            )}
          </div>

          {searchTerm.trim() && (
            <div
              className="list-group shadow-sm mt-2"
              style={{ maxHeight: '260px', overflowY: 'auto' }}
            >
              {matchedLocations.length > 0 ? (
                matchedLocations.map((feature: Feature<Point>) => {
                  const props = feature.properties || {};
                  return (
                    <button
                      key={`${String(props.primary_location_id || '')}-${String(props.secondary_location_id || '')}`}
                      type="button"
                      className="list-group-item list-group-item-action"
                      aria-label={String(props.name || 'Unnamed location')}
                      onClick={() => handleSearchSelect(feature)}
                    >
                      <div className="d-flex justify-content-between align-items-start gap-2">
                        <div className="text-start">
                          <div className="fw-semibold">
                            {String(props.name || 'Unnamed location')}
                          </div>
                          <div className="small text-muted">
                            Primary: {String(props.primary_location_id || 'N/A')}
                          </div>
                          <div className="small text-muted">
                            Secondary: {String(props.secondary_location_id || 'N/A')}
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="list-group-item small text-muted">No matching locations found.</div>
              )}
            </div>
          )}
        </Card.Body>
      </Card>

      <MapFilterButton
        tables={STREAMFLOW_TABLES}
        mapFilters={mapFilters}
        updateMapFilters={updateMapFilters}
        floating={false}
      />

      <MapLegend metric={forecastState.mapFilters.metricName} floating={false} />
    </div>
  );

  const streamflowMobileBottomSheet = (
    <div className="streamflow-unified-view__mobile-sheet-stack">
      {streamflowMapOverlayCard}
      {streamflowSideCard}
      <div className="streamflow-unified-view__mobile-metrics">{streamflowMetricsCard}</div>
    </div>
  );

  const snowSideOverlayContent = (
    <div className="snow-unified-view__side-stack">
      {griddedState.error && (
        <div className="alert alert-danger alert-dismissible mb-2" role="alert">
          <i className="bi bi-exclamation-triangle-fill me-2"></i>
          <strong>Error:</strong> {griddedState.error}
          <button
            type="button"
            className="btn-close"
            onClick={() => griddedDispatch({ type: GriddedActionTypes.CLEAR_ERROR })}
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
                className={`nav-link${griddedState.rightPanelTab === tab.id ? ' active' : ''}`}
                onClick={() =>
                  griddedDispatch({ type: GriddedActionTypes.SET_RIGHT_PANEL_TAB, payload: tab.id })
                }
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
              display: griddedState.rightPanelTab === 'dataset' ? 'flex' : 'none',
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
              display: griddedState.rightPanelTab === 'polygons' ? 'flex' : 'none',
              flexDirection: 'column',
            }}
          >
            <GriddedPolygonPanel />
          </div>
        </div>
      </div>
    </div>
  );

  const snowTimeseriesOverlay = (
    <div className="snow-unified-view__timeseries-shell">
      <GriddedTimeseriesPanel />
    </div>
  );

  const snowLegendOverlay = <GriddedLegendCard />;

  const snowMobileBottomSheet = (
    <div className="snow-unified-view__mobile-sheet-stack">
      {snowSideOverlayContent}
      {snowTimeseriesOverlay}
      {snowLegendOverlay}
    </div>
  );

  return (
    <UnifiedDashboardShell
      transitionKey={view}
      mapContent={mapContent}
      desktopTopLeftCard={
        isSnowView
          ? {
              content: snowSideOverlayContent,
              className: 'snow-unified-view__desktop-side-card',
            }
          : undefined
      }
      desktopTopRightCard={{
        content: isSnowView ? snowLegendOverlay : streamflowMapOverlayCard,
        className: isSnowView
          ? 'snow-unified-view__desktop-legend-card'
          : 'streamflow-unified-view__desktop-map-overlays',
      }}
      desktopBottomCard={{
        content: isSnowView ? snowTimeseriesOverlay : streamflowDesktopDataDock,
        className: isSnowView
          ? 'snow-unified-view__desktop-timeseries-card'
          : 'streamflow-unified-view__desktop-data-dock-card',
      }}
      mobileBottomSheet={{
        content: isSnowView ? snowMobileBottomSheet : streamflowMobileBottomSheet,
        className: isSnowView
          ? 'snow-unified-view__mobile-sheet-card'
          : 'streamflow-unified-view__mobile-sheet-card',
      }}
    />
  );
};

type UnifiedDashboardPageProps = {
  view: string;
};

const UnifiedDashboardPage = ({ view }: UnifiedDashboardPageProps) => {
  return (
    <ForecastDashboardProvider>
      <GriddedDashboardProvider>
        <UnifiedDashboardContent view={view} />
      </GriddedDashboardProvider>
    </ForecastDashboardProvider>
  );
};

export default UnifiedDashboardPage;
