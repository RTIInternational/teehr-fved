import { IconMapPin, IconPolygon } from '@tabler/icons-react';
import { useCallback, type ReactNode } from 'react';

import { ActionTypes, useDashboard } from '@/features/gridded/DashboardContext';
import { formatLatLon } from '@/shared/utils/formatters';

import type { SnowDockSection } from './useSnowDockSection';

type SnowDockHeader = {
  icon?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  placeholder?: ReactNode;
  onClose: () => void;
  closeLabel: string;
};

const ICON_STYLE = { flexShrink: 0 };
const POINT_ICON = <IconMapPin size={18} style={ICON_STYLE} />;
const POLYGON_ICON = <IconPolygon size={18} style={ICON_STYLE} />;

const joinParts = (...parts: (string | null | undefined | false)[]) =>
  parts.filter(Boolean).join(' · ');

// Midnight timesteps are daily data; show the hour only when it carries meaning.
const formatTimestep = (time: string) =>
  time.endsWith('T00:00:00') ? time.slice(0, 10) : time.slice(0, 16).replace('T', ' ');

/**
 * Dock header props describing what the active section shows: the queried
 * point or polygon for the time series, or the clicked polygons for attributes.
 * Until anything is queried, the dock shows a placeholder instead.
 */
export const useSnowDockHeader = (section: SnowDockSection): SnowDockHeader => {
  const { state, dispatch } = useDashboard();
  const {
    mapFilters,
    clickedPoint,
    polygonQuery,
    polygonFeatures,
    polygonClickLngLat,
    activePolygonLayer,
  } = state;

  // Clearing the point also clears a loaded polygon query.
  const onClose = useCallback(() => {
    dispatch({ type: ActionTypes.SET_CLICKED_POINT, payload: null });
    dispatch({ type: ActionTypes.CLEAR_POLYGON_FEATURES });
  }, [dispatch]);
  const base = { onClose, closeLabel: 'Clear map query' };

  if (!clickedPoint && !polygonQuery && polygonFeatures.length === 0) {
    return {
      ...base,
      icon: POINT_ICON,
      placeholder: 'Click the map for values and a time series, or a polygon for its attributes.',
    };
  }

  if (section === 'attributes') {
    if (polygonFeatures.length === 0) {
      return {
        ...base,
        icon: POLYGON_ICON,
        title: 'No polygons selected',
        subtitle: joinParts(activePolygonLayer, 'click a polygon to list its attributes'),
      };
    }
    const count = polygonFeatures.length;
    return {
      ...base,
      icon: POLYGON_ICON,
      title: `${count} polygon${count === 1 ? '' : 's'} here`,
      subtitle: joinParts(
        activePolygonLayer,
        polygonClickLngLat && formatLatLon(polygonClickLngLat.lat, polygonClickLngLat.lon)
      ),
    };
  }

  if (polygonQuery) {
    return {
      ...base,
      icon: POLYGON_ICON,
      title: polygonQuery.name || polygonQuery.location_id,
      subtitle: joinParts(activePolygonLayer, polygonQuery.location_id),
    };
  }

  if (clickedPoint) {
    return {
      ...base,
      icon: POINT_ICON,
      title: formatLatLon(clickedPoint.lat, clickedPoint.lon),
      subtitle: joinParts(
        mapFilters.dataset,
        mapFilters.variable,
        formatTimestep(clickedPoint.time)
      ),
    };
  }

  return {
    ...base,
    title: 'No time series loaded',
    subtitle: 'Click the map, or load a polygon from its attributes',
  };
};
