import { Alert, Group, Loader, Paper, Text } from '@mantine/core';
import { IconAlertTriangle, IconMapPin } from '@tabler/icons-react';
import { useCallback, useMemo } from 'react';

import { useMap } from '@/core/map';
import { ForecastDashboardProvider } from '@/features/forecast';
import TimeseriesControls from '@/features/forecast/components/TimeseriesControls';
import { ActionTypes, useDashboard } from '@/features/forecast/DashboardContext';
import { useFilters } from '@/features/forecast/hooks/useFilters';
import { useInitialFilters } from '@/features/forecast/hooks/useInitialFilters';
import { useLocationSelection } from '@/features/forecast/hooks/useLocationSelection';
import LocationMetrics from '@/shared/components/LocationMetrics';
import MapFilterButton from '@/shared/components/MapFilterButton';
import MapLegend from '@/shared/components/MapLegend';
import TimeseriesComponent from '@/shared/components/TimeseriesComponent';
import { useMetricLocations } from '@/shared/queries/metrics';
import type { MapLocation } from '@/shared/types/locations';
import { MapDataDock } from '@/views/components/MapDataDock';
import { MapViewLayout } from '@/views/components/MapViewLayout';

import { LocationSearch } from './components/LocationSearch';
import { StreamflowMapLayers } from './components/StreamflowMapLayers';

const TABLES = ['fcst_metrics_by_location', 'fcst_metrics_by_lead_time_bins'];

const StreamflowContent = () => {
  const map = useMap();
  const { state, dispatch } = useDashboard();
  const { selectLocation, selectedLocation } = useLocationSelection();
  const { mapFilters, updateMapFilters, timeseriesFilters, updateTimeseriesFilters } = useFilters();

  useInitialFilters(TABLES[0]);

  const { configuration, variable } = mapFilters;
  const locationFilters = useMemo(
    () => (configuration && variable ? { table: TABLES[0], configuration, variable } : undefined),
    [configuration, variable]
  );
  const locations = useMetricLocations(locationFilters);
  const locationsKey = locationFilters ? `${configuration}|${variable}` : null;

  const handleMapError = useCallback(
    (message: string) => dispatch({ type: ActionTypes.SET_ERROR, payload: message }),
    [dispatch]
  );

  const handleSearchSelect = useCallback(
    (location: MapLocation) => {
      selectLocation(location);
      map?.flyTo({
        center: location.coordinates,
        zoom: Math.max(map.getZoom(), 10),
        duration: 700,
        essential: true,
      });
    },
    [map, selectLocation]
  );

  // Request the plot as soon as a location is selected, using the current filters.
  const autoRequestFilters = useMemo(() => {
    const { primary, secondary } = timeseriesFilters;
    if (
      !selectedLocation ||
      !primary.variables.length ||
      !secondary.variables.length ||
      !secondary.configurations.length
    ) {
      return null;
    }
    return { primary_location_id: selectedLocation.primary_location_id, primary, secondary };
  }, [selectedLocation, timeseriesFilters]);

  return (
    <MapViewLayout
      mapLayers={
        <StreamflowMapLayers
          locations={locations.data}
          locationsKey={locationsKey}
          metricName={mapFilters.metricName}
          selectedLocationId={selectedLocation?.primary_location_id ?? null}
          onSelect={selectLocation}
          onError={handleMapError}
        />
      }
      topRight={
        <>
          {state.error && (
            <Alert
              w="100%"
              color="red"
              title="Error"
              icon={<IconAlertTriangle size={18} />}
              withCloseButton
              closeButtonLabel="Dismiss error"
              onClose={() => dispatch({ type: ActionTypes.CLEAR_ERROR })}
            >
              {state.error}
            </Alert>
          )}
          <LocationSearch locations={locations.data} onSelect={handleSearchSelect} />
          <Group gap="xs" wrap="nowrap">
            {locations.isFetching && (
              <Paper shadow="sm" radius="md" px="sm" py={6}>
                <Group gap="xs" wrap="nowrap">
                  <Loader size="xs" />
                  <Text size="xs">Loading locations…</Text>
                </Group>
              </Paper>
            )}
            <MapFilterButton
              tables={TABLES}
              mapFilters={mapFilters}
              updateMapFilters={updateMapFilters}
            />
          </Group>
          <MapLegend metric={mapFilters.metricName} />
        </>
      }
      bottom={
        <MapDataDock
          icon={<IconMapPin size={18} style={{ flexShrink: 0 }} />}
          placeholder={
            !selectedLocation && 'Select a location on the map to view its time series and metrics.'
          }
          title={selectedLocation?.name}
          subtitle={[selectedLocation?.primary_location_id, selectedLocation?.secondary_location_id]
            .filter(Boolean)
            .join(' · ')}
          onClose={() => selectLocation(null)}
          closeLabel="Clear selected location"
          sections={
            selectedLocation
              ? [
                  {
                    value: 'timeseries',
                    label: 'Time Series',
                    content: (
                      <TimeseriesComponent
                        key={selectedLocation.primary_location_id}
                        state={state}
                        Controls={TimeseriesControls}
                        initialViewMode="plot"
                        autoRequestFilters={autoRequestFilters}
                        controlsProps={{
                          table: TABLES[0],
                          timeseriesFilters,
                          updateTimeseriesFilters,
                          selectedLocation,
                          mapFilters,
                        }}
                      />
                    ),
                  },
                  {
                    value: 'metrics',
                    label: 'Metrics',
                    content: (
                      <LocationMetrics
                        key={selectedLocation.primary_location_id}
                        selectedLocation={selectedLocation}
                        tables={TABLES}
                      />
                    ),
                  },
                ]
              : []
          }
        />
      }
    />
  );
};

/** Streamflow forecast locations, time series and metrics on the shared map. */
export const StreamflowView = () => (
  <ForecastDashboardProvider>
    <StreamflowContent />
  </ForecastDashboardProvider>
);
