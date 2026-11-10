import type { ReactNode } from 'react';

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
};

/**
 * Places a map view's panels over the shared map. Only the panels take pointer
 * input; everywhere else, clicks and drags reach the map.
 */
export const MapViewLayout = ({ mapLayers, topLeft, topRight, bottom }: MapViewLayoutProps) => (
  <div className={styles.overlay}>
    {mapLayers}
    {topLeft && <div className={styles.topLeft}>{topLeft}</div>}
    {topRight && <div className={styles.topRight}>{topRight}</div>}
    {bottom}
  </div>
);
