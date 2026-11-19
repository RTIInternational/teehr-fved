import type { ReactNode } from 'react';

import { MapLoadingBar, MapLoadingLabel } from './MapLoadingIndicator';
import { useMapLoadingStatus } from './useMapLoadingStatus';

import styles from './MapViewLayout.module.css';

type MapViewLayoutProps = {
  /** Renderless components that draw on the shared map. */
  mapLayers?: ReactNode;
  /** Compact, glanceable content such as a legend. */
  topLeft?: ReactNode;
  /** A right-aligned stack: alerts, search, controls. Items shrink to fit unless full width. */
  topRight?: ReactNode;
  /** Usually a MapDataDock. */
  bottom?: ReactNode;
  /**
   * What the view's map data is waiting on, e.g. "Loading locations…"; null or
   * omitted when ready. Shows a bar along the top edge and a status label;
   * the map stays usable throughout.
   */
  loading?: string | null;
};

/**
 * Places a map view's panels over the shared map. Only the panels take pointer
 * input; everywhere else, clicks and drags reach the map.
 */
export const MapViewLayout = ({
  mapLayers,
  topLeft,
  topRight,
  bottom,
  loading = null,
}: MapViewLayoutProps) => {
  const status = useMapLoadingStatus(loading);

  return (
    <div className={styles.overlay}>
      {mapLayers}
      <MapLoadingBar visible={status.visible} />
      {/* The label goes last in the top-left stack so a legend above it doesn't shift. */}
      <div className={styles.topLeft}>
        {topLeft}
        <MapLoadingLabel visible={status.visible} label={status.label} />
      </div>
      {topRight && <div className={styles.topRight}>{topRight}</div>}
      {bottom}
    </div>
  );
};
