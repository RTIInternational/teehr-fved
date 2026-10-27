export type DashboardStatus = 'available' | 'coming-soon';

export type DashboardNavigationItem = {
  id: string;
  label: string;
  description: string;
  features: string[];
  route: string;
  status: DashboardStatus;
  image: string;
  color: string;
  viewKey?: string;
};

export const DASHBOARD_ROUTE = '/dashboard';
export const DEFAULT_DASHBOARD_VIEW = 'streamflow';

export const DASHBOARD_NAV_ITEMS: DashboardNavigationItem[] = [
  {
    id: 'streamflow',
    label: 'Streamflow',
    description:
      'Real-time forecast analysis and validation tools for operational and research data streams.',
    features: ['Live forecast data', 'Forecast vs observation comparison', 'Lead time analysis'],
    route: DASHBOARD_ROUTE,
    status: 'available',
    image: '/api/static/preview-forecast.png',
    color: 'secondary',
    viewKey: 'streamflow',
  },
  {
    id: 'snow',
    label: 'Snow',
    description:
      'Explore gridded snow data including SWE, snow depth, and precipitation rate from icechunk datasets.',
    features: [
      'Interactive raster tile map',
      'Variable and timestep selection',
      'Point-based timeseries query',
      'Overlay layers (NWS CPC, SMAP, VIIRS)',
    ],
    route: DASHBOARD_ROUTE,
    status: 'available',
    image: '/api/static/preview-snow.png',
    color: 'info',
    viewKey: 'snow',
  },
  {
    id: 'water-supply',
    label: 'Water Supply',
    description: 'Evaluate ensemble forecasts for water supply applications.',
    features: [
      'Continuous and seasonal evaluation',
      'Ensemble metrics',
      'Evaluate low flows, low flow duration',
      'Variable low flow thresholds',
      'Interactive maps and plots',
      'Filter by physical, geographical, temporal or hydrologic attributes to see trends',
      'Sampling uncertainty estimated',
    ],
    route: DASHBOARD_ROUTE,
    status: 'coming-soon',
    image: '/api/static/preview-data.png',
    color: 'success',
    viewKey: 'water-supply',
  },
  {
    id: 'crmms',
    label: 'CRMMS',
    description:
      'Evaluate multiple historical simulations compared to a baseline, considering sampling uncertainty.',
    features: [
      'Probability of improvement of alternative models over a baseline.',
      'Interactive maps, heatmaps and plots',
      'Aggregated and detailed summaries',
      'Filter by physical, geographical, temporal or hydrologic attributes to see trends',
    ],
    route: DASHBOARD_ROUTE,
    status: 'coming-soon',
    image: '/api/static/preview-data.png',
    color: 'primary',
    viewKey: 'crmms',
  },
];

export const getDashboardViewFromSearch = (search: string) => {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return params.get('view');
};

export const buildDashboardHref = (viewKey: string, search = '') => {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  params.set('view', viewKey);
  const query = params.toString();
  return query ? `${DASHBOARD_ROUTE}?${query}` : DASHBOARD_ROUTE;
};

export const isAvailableDashboardView = (viewKey: string | null) => {
  if (!viewKey) return false;
  return DASHBOARD_NAV_ITEMS.some(
    (item) => item.status === 'available' && (item.viewKey ?? item.id) === viewKey
  );
};

export const getDashboardLabelByRoute = (route: string, search = '') => {
  if (route === DASHBOARD_ROUTE) {
    const viewKey = getDashboardViewFromSearch(search);
    if (!viewKey) {
      return DASHBOARD_NAV_ITEMS.find(
        (item) =>
          item.status === 'available' && (item.viewKey ?? item.id) === DEFAULT_DASHBOARD_VIEW
      )?.label;
    }

    return DASHBOARD_NAV_ITEMS.find((item) => (item.viewKey ?? item.id) === viewKey)?.label;
  }

  const availableMatch = DASHBOARD_NAV_ITEMS.find(
    (item) => item.route === route && item.status === 'available'
  );

  if (availableMatch) {
    return availableMatch.label;
  }

  return DASHBOARD_NAV_ITEMS.find((item) => item.route === route)?.label;
};
