import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useMap } from '@/core/map';
import {
  bboxBoundsToString,
  formatBboxFromBounds,
  parseBboxFromSearch,
  type BboxBounds,
} from '@/core/map/mapBboxUrl';

const LAST_BBOX_STORAGE_KEY = 'teehr:map:last-bbox';

const readLastBbox = (): BboxBounds | null => {
  try {
    return parseBboxFromSearch(window.localStorage.getItem(LAST_BBOX_STORAGE_KEY));
  } catch {
    return null;
  }
};

const writeLastBbox = (bbox: string) => {
  try {
    window.localStorage.setItem(LAST_BBOX_STORAGE_KEY, bbox);
  } catch {
    // Ignore localStorage write failures in restricted browser contexts.
  }
};

type MapViewportUrlSyncProps = {
  enabled: boolean;
};

/**
 * Syncs map bounds to ?bbox=w,s,e,n and restores the last known bbox when the
 * map route is opened without a bbox query param.
 */
export const MapViewportUrlSync = ({ enabled }: MapViewportUrlSyncProps) => {
  const map = useMap();
  const [searchParams, setSearchParams] = useSearchParams();
  const enabledRef = useRef(enabled);
  const skipNextMoveEndRef = useRef(false);
  const lastAppliedBboxRef = useRef<string | null>(null);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  useEffect(() => {
    if (!map) return;

    const subscription = map.on('moveend', () => {
      if (!enabledRef.current) return;
      if (skipNextMoveEndRef.current) {
        skipNextMoveEndRef.current = false;
        return;
      }

      const bbox = formatBboxFromBounds(map.getBounds());
      writeLastBbox(bbox);
      lastAppliedBboxRef.current = bbox;
      setSearchParams(
        (previous) => {
          if (previous.get('bbox') === bbox) {
            return previous;
          }
          const next = new URLSearchParams(previous);
          next.set('bbox', bbox);
          return next;
        },
        { replace: true }
      );
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [map, setSearchParams]);

  useEffect(() => {
    if (!map || !enabled) return;

    const bboxInUrl = searchParams.get('bbox');
    const parsedFromUrl = parseBboxFromSearch(bboxInUrl);

    if (parsedFromUrl && bboxInUrl) {
      const currentBbox = formatBboxFromBounds(map.getBounds());
      if (bboxInUrl !== currentBbox && bboxInUrl !== lastAppliedBboxRef.current) {
        skipNextMoveEndRef.current = true;
        lastAppliedBboxRef.current = bboxInUrl;
        map.fitBounds(parsedFromUrl, { duration: 0 });
      }
      writeLastBbox(bboxInUrl);
      return;
    }

    if (bboxInUrl) {
      return;
    }

    const savedBbox = readLastBbox();
    if (!savedBbox) return;

    const bboxString = bboxBoundsToString(savedBbox);
    skipNextMoveEndRef.current = true;
    lastAppliedBboxRef.current = bboxString;
    map.fitBounds(savedBbox, { duration: 0 });
    setSearchParams(
      (previous) => {
        if (previous.get('bbox') === bboxString) {
          return previous;
        }
        const next = new URLSearchParams(previous);
        next.set('bbox', bboxString);
        return next;
      },
      { replace: true }
    );
  }, [enabled, map, searchParams, setSearchParams]);

  return null;
};
