import { IconBucket, IconDroplet, IconRipple, IconSnowflake, type Icon } from '@tabler/icons-react';

import type { ViewDefinition } from '@/core/views';

export type RegisteredView = {
  id: string;
  label: string;
  path: string;
  description: string;
  icon: Icon;
  disabled?: boolean;
  statusLabel?: string;
};

export const newViews: RegisteredView[] = [
  {
    id: 'streamflow',
    label: 'Streamflow',
    path: '/map/streamflow',
    description: 'New map-centric streamflow view (modular architecture path).',
    icon: IconRipple,
  },
  {
    id: 'water-supply',
    label: 'Water Supply',
    path: '/water-supply',
    description: 'Water supply outlook dashboards are in planning and not yet available.',
    icon: IconBucket,
    disabled: true,
    statusLabel: 'Coming Soon',
  },
  {
    id: 'colorado-river',
    label: 'Colorado River',
    path: '/crmms',
    description: 'Colorado River model and monitoring view is in planning and not yet available.',
    icon: IconDroplet,
    disabled: true,
    statusLabel: 'Coming Soon',
  },
  {
    id: 'snow',
    label: 'Snow',
    path: '/map/snow',
    description: 'New map-centric snow view (modular architecture path).',
    icon: IconSnowflake,
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

export const mapViewsRegistry: ViewDefinition[] = newViews
  .filter((view) => !view.disabled)
  .map((view) => {
    const ViewIcon = view.icon;

    return {
      id: view.id,
      label: view.label,
      description: view.description,
      leftSection: <ViewIcon size={20} />,
    };
  });

export const LAST_MAP_VIEW_KEY = 'teehr:map:last-view-id';

const isKnownViewId = (viewId: string) => {
  return mapViewsRegistry.some((view) => view.id === viewId);
};

export const getMapViewById = (viewId: string | undefined) => {
  if (!viewId) return null;
  return mapViewsRegistry.find((view) => view.id === viewId) ?? null;
};

export const getDefaultMapViewId = () => {
  return mapViewsRegistry[0]?.id || 'streamflow';
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
