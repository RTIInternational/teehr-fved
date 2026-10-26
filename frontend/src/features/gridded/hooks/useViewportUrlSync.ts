import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import type { MapViewport } from '@/shared/types/maps';
import {
  hasViewportParams,
  parseViewportFromSearch,
  updateSearchWithViewport,
} from '@/shared/utils/mapViewportUrl';

const viewportKey = (viewport: MapViewport | null) => {
  if (!viewport) return null;
  return `${viewport.center[0].toFixed(5)}:${viewport.center[1].toFixed(5)}:${viewport.zoom.toFixed(3)}`;
};

type UseViewportUrlSyncArgs = {
  mapViewport: MapViewport | null;
  setMapViewport: (viewport: MapViewport) => void;
};

export const useViewportUrlSync = ({ mapViewport, setMapViewport }: UseViewportUrlSyncArgs) => {
  const location = useLocation();
  const navigate = useNavigate();
  const viewportStateRef = useRef(mapViewport);

  useEffect(() => {
    viewportStateRef.current = mapViewport;
  }, [mapViewport]);

  useEffect(() => {
    if (!hasViewportParams(location.search)) {
      return;
    }

    const parsedViewport = parseViewportFromSearch(location.search);
    if (!parsedViewport) {
      return;
    }

    const nextViewportKey = viewportKey(parsedViewport);
    const currentViewportKey = viewportKey(viewportStateRef.current);

    if (currentViewportKey !== nextViewportKey) {
      viewportStateRef.current = parsedViewport;
      setMapViewport(parsedViewport);
    }
  }, [location.search, setMapViewport]);

  useEffect(() => {
    const nextSearch = updateSearchWithViewport(location.search, mapViewport);
    if (nextSearch !== location.search) {
      navigate(
        {
          pathname: location.pathname,
          search: nextSearch,
        },
        { replace: true }
      );
    }
  }, [mapViewport, location.pathname, location.search, navigate]);
};
