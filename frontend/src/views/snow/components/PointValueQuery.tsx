import { Group, Loader, Text } from '@mantine/core';
import type { MapMouseEvent } from 'maplibre-gl';
import { useEffect, useEffectEvent, useState } from 'react';

import { MapPopup, MapPopupField, MapPopupNote, MapPopupTitle, useMap } from '@/core/map';
import { teehrMapping } from '@/shared/api/gridded/variableAttrs';
import { useEdrPointValue, type EdrPointArgs } from '@/shared/queries/gridded/edr';
import { useVariableAttrs } from '@/shared/queries/gridded/variableAttrs';

import { ActionTypes, useDashboard } from '../DashboardContext';
import { useCurrentTimestep } from '../hooks/useCurrentTimestep';
import { POLYGON_FILL_LAYER_ID } from '../utils/layerOrder';

type ClickedPoint = EdrPointArgs & { lngLat: [number, number] };

const formatValue = (
  value: unknown,
  toDisplay: (value: number) => number,
  units: string | null
) => {
  if (typeof value === 'number') return `${toDisplay(value).toFixed(2)}${units ? ` ${units}` : ''}`;
  if (typeof value === 'string') return value;
  return 'N/A';
};

/** The value at a clicked point, shown the teehr way (the repo stores other units). */
const PointValueContent = ({ point }: { point: EdrPointArgs }) => {
  const value = useEdrPointValue(point);
  const variableAttrs = useVariableAttrs(point.dataset);

  if (value.isPending) {
    return (
      <Group gap="xs" wrap="nowrap">
        <Loader size={14} />
        <Text size="xs" c="dimmed">
          Loading…
        </Text>
      </Group>
    );
  }
  if (value.isError) {
    return (
      <Text size="xs" c="red">
        Failed to retrieve value.
      </Text>
    );
  }

  const mapping = teehrMapping(point.variable, variableAttrs.data?.[point.variable]);
  return (
    <>
      <MapPopupTitle>{mapping.variable}</MapPopupTitle>
      <MapPopupField label="Value">
        {formatValue(value.data, mapping.toDisplay, mapping.units)}
      </MapPopupField>
      <MapPopupField label="Lat">{point.lat.toFixed(4)}</MapPopupField>
      <MapPopupField label="Lon">{point.lon.toFixed(4)}</MapPopupField>
      <MapPopupNote>{point.timestep}</MapPopupNote>
    </>
  );
};

/**
 * A click on the map (away from polygons, which take precedence) shows the
 * gridded value there and loads its time series.
 */
export const PointValueQuery = () => {
  const map = useMap();
  const { state, dispatch } = useDashboard();
  const { dataset, variable } = state.mapFilters;
  const timestep = useCurrentTimestep();
  // The popup keeps showing the dataset, variable and timestep it was opened for.
  const [point, setPoint] = useState<ClickedPoint | null>(null);

  const onMapClick = useEffectEvent((event: MapMouseEvent) => {
    if (!map) return;
    if (map.getLayer(POLYGON_FILL_LAYER_ID)) {
      const hits = map.queryRenderedFeatures(event.point, { layers: [POLYGON_FILL_LAYER_ID] });
      if (hits.length > 0) {
        setPoint(null);
        return;
      }
    }
    if (!dataset || !variable || !timestep) return;

    const { lng, lat } = event.lngLat;
    dispatch({ type: ActionTypes.SET_CLICKED_POINT, payload: { lon: lng, lat, time: timestep } });
    setPoint({ dataset, variable, timestep, lon: lng, lat, lngLat: [lng, lat] });
  });

  useEffect(() => {
    if (!map) return;
    const onClick = (event: MapMouseEvent) => onMapClick(event);
    map.on('click', onClick);
    return () => {
      map.off('click', onClick);
    };
  }, [map]);

  return (
    point && (
      <MapPopup lngLat={point.lngLat} closeButton onClose={() => setPoint(null)} maxWidth="280px">
        <PointValueContent point={point} />
      </MapPopup>
    )
  );
};
