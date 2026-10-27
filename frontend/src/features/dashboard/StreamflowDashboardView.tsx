import type { Feature, Point } from 'geojson';
import { useCallback, useMemo, useState } from 'react';
import { Card } from 'react-bootstrap';

import TimeseriesControls from '@/features/forecast/components/TimeseriesControls';
import { ActionTypes, useDashboard } from '@/features/forecast/DashboardContext';
import { useFilters } from '@/features/forecast/hooks/useFilters';
import { useInitialFilters } from '@/features/forecast/hooks/useInitialFilters';
import { useLocationSelection } from '@/features/forecast/hooks/useLocationSelection';
import { useViewportUrlSync } from '@/features/forecast/hooks/useViewportUrlSync';
import LocationCard from '@/shared/components/LocationCard';
import LocationMetrics from '@/shared/components/LocationMetrics';
import MapComponent from '@/shared/components/MapComponent';
import MapFilterButton from '@/shared/components/MapFilterButton';
import MapLegend from '@/shared/components/MapLegend';
import TimeseriesComponent from '@/shared/components/TimeseriesComponent';
import { useMetricLocations } from '@/shared/queries/metrics';

import UnifiedDashboardShell from './UnifiedDashboardShell';

const TABLES = ['fcst_metrics_by_location', 'fcst_metrics_by_lead_time_bins'];

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

const StreamflowDashboardView = () => {
  const { state, dispatch } = useDashboard();
  const { selectLocation, selectedLocation } = useLocationSelection();
  const { mapFilters, updateMapFilters, timeseriesFilters, updateTimeseriesFilters } = useFilters();
  const [searchTerm, setSearchTerm] = useState('');

  useInitialFilters(TABLES[0]);

  const setMapViewport = useCallback(
    (viewport: NonNullable<typeof state.mapViewport>) => {
      dispatch({ type: ActionTypes.SET_MAP_VIEWPORT, payload: viewport });
    },
    [dispatch]
  );

  useViewportUrlSync({ mapViewport: state.mapViewport, setMapViewport });

  const locationFilters = useMemo(() => {
    if (!mapFilters.configuration || !mapFilters.variable) {
      return undefined;
    }

    return {
      table: TABLES[0],
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

      setMapViewport({
        center: [lon, lat],
        zoom: Math.max(state.mapViewport?.zoom ?? 10, 10),
      });
      setSearchTerm('');
    },
    [selectLocation, setMapViewport, state.mapViewport?.zoom]
  );

  const mapContent = (
    <div className="streamflow-unified-view__map-frame">
      <MapComponent
        state={state}
        dispatch={dispatch}
        table={TABLES[0]}
        ActionTypes={ActionTypes}
        selectLocation={selectLocation}
        selectedLocation={selectedLocation}
        showSearch={false}
        showMapControls={false}
        showLegend={false}
      />
    </div>
  );

  const timeseriesPanel = selectedLocation ? (
    <TimeseriesComponent
      key={selectedLocation.primary_location_id}
      state={state}
      Controls={TimeseriesControls}
      controlsProps={{
        table: TABLES[0],
        timeseriesFilters,
        updateTimeseriesFilters,
        selectedLocation,
        mapFilters,
      }}
    />
  ) : (
    <EmptyTimeseriesCard />
  );

  const sideCard = (
    <div className="streamflow-unified-view__side-stack">
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

      <LocationCard selectedLocation={selectedLocation} onClose={() => selectLocation(null)} />

      <div className="streamflow-unified-view__timeseries-card">{timeseriesPanel}</div>
    </div>
  );

  const metricsCard = selectedLocation ? (
    <LocationMetrics selectedLocation={selectedLocation} tables={TABLES} />
  ) : (
    <EmptyMetricsCard />
  );

  const mapOverlayCard = (
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
        tables={TABLES}
        mapFilters={mapFilters}
        updateMapFilters={updateMapFilters}
        floating={false}
      />

      <MapLegend metric={state.mapFilters.metricName} floating={false} />
    </div>
  );

  const mobileBottomSheet = (
    <div className="streamflow-unified-view__mobile-sheet-stack">
      {mapOverlayCard}
      {sideCard}
      <div className="streamflow-unified-view__mobile-metrics">{metricsCard}</div>
    </div>
  );

  return (
    <UnifiedDashboardShell
      mapContent={mapContent}
      desktopTopLeftCard={{
        content: sideCard,
        className: 'streamflow-unified-view__desktop-side-card',
      }}
      desktopTopRightCard={{
        content: mapOverlayCard,
        className: 'streamflow-unified-view__desktop-map-overlays',
      }}
      desktopBottomCard={{
        content: metricsCard,
        className: 'streamflow-unified-view__desktop-metrics-card',
      }}
      mobileBottomSheet={{
        content: mobileBottomSheet,
        className: 'streamflow-unified-view__mobile-sheet-card',
      }}
    />
  );
};

export default StreamflowDashboardView;
