import { useState } from 'react';

import { useDashboard } from '../DashboardContext';

export type SnowDockSection = 'attributes' | 'timeseries';

/**
 * The dock section to show, following what the user just did: a polygon click
 * shows its attributes; a point click or a loaded polygon shows the time series.
 * Attributes are only offered while a polygon layer is active.
 */
export const useSnowDockSection = () => {
  const { state } = useDashboard();
  const { polygonFeatures, clickedPoint, polygonQuery, activePolygonLayer } = state;
  const request = clickedPoint ?? polygonQuery;

  const [section, setSection] = useState<SnowDockSection>('timeseries');

  const [seen, setSeen] = useState({ polygonFeatures, request });
  if (polygonFeatures !== seen.polygonFeatures || request !== seen.request) {
    setSeen({ polygonFeatures, request });
    if (request && request !== seen.request) {
      setSection('timeseries');
    } else if (polygonFeatures.length > 0 && polygonFeatures !== seen.polygonFeatures) {
      setSection('attributes');
    }
  }

  const hasAttributes = activePolygonLayer !== null;
  return {
    section: hasAttributes ? section : 'timeseries',
    setSection: (next: string) => setSection(next as SnowDockSection),
    hasAttributes,
  };
};
