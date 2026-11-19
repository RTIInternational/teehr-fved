import { Button, Group, Stack, Table, Text } from '@mantine/core';
import { IconPolygon } from '@tabler/icons-react';

import type { PolygonFeatureProps, PolygonFeatures } from '@/shared/types/gridded/tiles';

import { useDashboard, ActionTypes } from '../DashboardContext';
import { useCurrentTimestep } from '../hooks/useCurrentTimestep';

import styles from './GriddedPolygonPanel.module.css';

// Attribute columns are driven by the pmtiles archive, so render whatever the
// features carry rather than hard-coding a schema. `id` leads since it is the
// key a warehouse query is built on.
const orderedKeys = (features: PolygonFeatures) => {
  const keys = new Set();
  features.forEach((props) => Object.keys(props || {}).forEach((k) => keys.add(k)));
  keys.delete('id');
  return ['id', ...Array.from(keys)];
};

const GriddedPolygonPanel = () => {
  const { state, dispatch } = useDashboard();
  const { polygonFeatures, polygonClickLngLat, selectedLocation, activePolygonLayer } = state;

  const selectedId = selectedLocation?.primary_location_id ?? null;
  const currentTimestep = useCurrentTimestep();

  const selectFeature = (props: PolygonFeatureProps) => {
    dispatch({
      type: ActionTypes.SELECT_LOCATION,
      payload: {
        // Named to match the forecast state's selected location, so shared
        // query helpers work against this object unchanged.
        primary_location_id: props.id,
        name: props.name,
        coordinates: polygonClickLngLat ? [polygonClickLngLat.lon, polygonClickLngLat.lat] : null,
      },
    });
  };

  if (polygonFeatures.length === 0) {
    return (
      <Stack h="100%" align="center" justify="center" gap="xs">
        <IconPolygon size={32} stroke={1.5} color="var(--mantine-color-dimmed)" />
        <Text fw={600} c="dimmed">
          Polygon Attributes
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          {activePolygonLayer
            ? 'Click a polygon on the map to list every polygon at that location.'
            : 'Enable a polygon layer, then click the map.'}
        </Text>
      </Stack>
    );
  }

  const columns = orderedKeys(polygonFeatures);

  return (
    <div className={styles.panel}>
      <div className={styles.tableScroll}>
        <Table
          stickyHeader
          highlightOnHover
          fz="xs"
          verticalSpacing={4}
          horizontalSpacing="xs"
          className={styles.table}
        >
          <Table.Thead>
            <Table.Tr>
              {columns.map((key) => {
                if (typeof key === 'string' || typeof key === 'number') {
                  return (
                    <Table.Th key={key} scope="col">
                      {key}
                    </Table.Th>
                  );
                }
              })}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {polygonFeatures.map((props) => {
              const isSelected = selectedId != null && props.id === selectedId;
              return (
                <Table.Tr
                  key={props.id}
                  onClick={() => selectFeature(props)}
                  data-selected={isSelected || undefined}
                  className={styles.row}
                >
                  {columns.map((key) => {
                    if (typeof key === 'string' || typeof key === 'number') {
                      return (
                        <Table.Td key={key}>
                          {props[key] !== null && props[key] !== undefined
                            ? String(props[key] as string | number | boolean)
                            : 'N/A'}
                        </Table.Td>
                      );
                    }
                  })}
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </div>

      <Group justify="space-between" wrap="nowrap" gap="xs" className={styles.footer}>
        <Text size="sm" c="dimmed" truncate miw={0}>
          {selectedLocation
            ? `Selected: ${selectedLocation.primary_location_id}`
            : 'Select a row to choose a location'}
        </Text>
        <Button
          size="sm"
          disabled={!selectedLocation || !currentTimestep}
          onClick={() =>
            dispatch({
              type: ActionTypes.LOAD_POLYGON_TIMESERIES,
              payload: {
                location_id: selectedLocation!.primary_location_id,
                name: selectedLocation!.name,
                time: currentTimestep!,
              },
            })
          }
        >
          Load Timeseries
        </Button>
      </Group>
    </div>
  );
};

export default GriddedPolygonPanel;
