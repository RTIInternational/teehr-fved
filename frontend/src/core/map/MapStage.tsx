import maplibregl, {
  type LngLatBoundsLike,
  type Map as MapLibreMap,
  type RequestTransformFunction,
} from 'maplibre-gl';
import { useEffect, useRef } from 'react';

import 'maplibre-gl/dist/maplibre-gl.css';

import { createBasemapStyle } from './basemap';
import { useMapContext } from './MapContext';

import styles from './MapStage.module.css';

const passThrough: RequestTransformFunction = (url) => ({ url });

type MapStageProps = {
  className?: string;
  initialBounds: LngLatBoundsLike;
  transformRequest?: RequestTransformFunction;
  hidden?: boolean;
};

/**
 * Creates the shared map and publishes it through MapProvider once the basemap
 * style has loaded.
 */
export const MapStage = ({
  className,
  initialBounds,
  transformRequest = passThrough,
  hidden = false,
}: MapStageProps) => {
  const { setMap } = useMapContext();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const initialOptionsRef = useRef({ initialBounds, transformRequest });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: createBasemapStyle(),
      bounds: initialOptionsRef.current.initialBounds,
      transformRequest: initialOptionsRef.current.transformRequest,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on('error', (event) => {
      console.error('MapStage: MapLibre error', event.error);
    });
    map.on('load', () => setMap(map));

    return () => {
      mapRef.current = null;
      setMap(null);
      map.remove();
    };
  }, [setMap]);

  useEffect(() => {
    mapRef.current?.setTransformRequest(transformRequest);
  }, [transformRequest]);

  return (
    <div
      className={className ? `${styles.stage} ${className}` : styles.stage}
      data-hidden={hidden || undefined}
      aria-hidden={hidden || undefined}
    >
      <div ref={containerRef} className={styles.container} />
    </div>
  );
};
