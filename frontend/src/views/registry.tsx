import { IconBucket, IconDroplet, IconRipple, IconSnowflake, type Icon } from '@tabler/icons-react';
import type { ComponentType } from 'react';

import { SnowView } from '@/views/snow/SnowView';
import { StreamflowView } from '@/views/streamflow/StreamflowView';

export type RegisteredView = {
  id: string;
  label: string;
  path: string;
  description: string;
  features?: string[];
  icon: Icon;
  disabled?: boolean;
  statusLabel?: string;
  /** Rendered over the shared map at /map/:viewId. */
  component?: ComponentType;
};

export const newViews: RegisteredView[] = [
  {
    id: 'streamflow',
    label: 'Streamflow',
    path: '/map/streamflow',
    description: 'Real-time streamflow forecast visualization and performance evaluation.',
    features: [
      'Live forecast and observation data',
      'Forecast vs. observation comparison',
      'Forecast performance metrics',
    ],
    icon: IconRipple,
    component: StreamflowView,
  },
  {
    id: 'water-supply',
    label: 'Water Supply',
    path: '/water-supply',
    description:
      'Seasonal water supply forecast visualization and evaluation using real-time and historical data.',
    features: [
      'Operational and experimental forecasts',
      'Historical forecast comparison',
      'Probabilistic forecast verification',
    ],
    icon: IconBucket,
    disabled: true,
    statusLabel: 'Coming Soon',
  },
  {
    id: 'colorado-river',
    label: 'Colorado River',
    path: '/crmms',
    description:
      'Explore projected Colorado River Basin reservoir operations under different forecasts and scenarios.',
    features: [
      'Automated CRMMS model execution',
      'Forecast-driven reservoir projections',
      'Reservoir performance metrics',
    ],
    icon: IconDroplet,
    disabled: true,
    statusLabel: 'Coming Soon',
  },
  {
    id: 'snow',
    label: 'Snow',
    path: '/map/snow',
    description:
      'Interactive maps and visualizations for exploring snow conditions and related environmental datasets.',
    features: [
      'Multi-source SWE data',
      'Interactive maps and timeseries',
      'Custom basin-level analysis',
    ],
    icon: IconSnowflake,
    component: SnowView,
  },
];

export const legacyViews: RegisteredView[] = [
  {
    id: 'streamflow-legacy',
    label: 'Streamflow (Legacy)',
    path: '/forecast',
    icon: IconRipple,
    description: 'Legacy streamflow dashboard with existing context-backed panels.',
  },
  {
    id: 'water-supply-legacy',
    label: 'Water Supply',
    path: '/water-supply',
    icon: IconBucket,
    disabled: true,
    description: 'Legacy water supply dashboards are not currently available.',
  },
  {
    id: 'colorado-river-legacy',
    label: 'Colorado River',
    path: '/crmms',
    icon: IconDroplet,
    disabled: true,
    description: 'Legacy Colorado River dashboard is not currently available.',
  },
  {
    id: 'snow-legacy',
    label: 'Snow (Legacy)',
    path: '/gridded',
    icon: IconSnowflake,
    description: 'Legacy snow dashboard with gridded layers and polygon workflows.',
  },
];

type MapView = RegisteredView & { component: ComponentType };

/** Views that can be opened at /map/:viewId. */
export const mapViews: MapView[] = newViews.filter(
  (view): view is MapView => !view.disabled && view.component !== undefined
);

export const LAST_MAP_VIEW_KEY = 'teehr:map:last-view-id';

const isKnownViewId = (viewId: string) => {
  return mapViews.some((view) => view.id === viewId);
};

export const getMapViewById = (viewId: string | undefined) => {
  if (!viewId) return null;
  return mapViews.find((view) => view.id === viewId) ?? null;
};

export const getDefaultMapViewId = () => {
  return mapViews[0]?.id || 'streamflow';
};

export const readLastMapViewId = () => {
  try {
    const stored = window.localStorage.getItem(LAST_MAP_VIEW_KEY);
    if (!stored || !isKnownViewId(stored)) return null;
    return stored;
  } catch {
    return null;
  }
};

export const writeLastMapViewId = (viewId: string) => {
  if (!isKnownViewId(viewId)) return;
  try {
    window.localStorage.setItem(LAST_MAP_VIEW_KEY, viewId);
  } catch {
    // Ignore storage failures in restricted browser contexts.
  }
};
