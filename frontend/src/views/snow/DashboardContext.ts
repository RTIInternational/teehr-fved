import { createContext, useContext, type Dispatch } from 'react';

import type {
  ClickedPoint,
  MapFilters,
  PointQuery,
  PolygonQuery,
  SelectedLocation,
} from '@/shared/types/gridded/maps';
import type { PolygonFeatures } from '@/shared/types/gridded/tiles';
import type { GriddedTimeseriesFilters } from '@/shared/types/gridded/timeseries';

type PolygonFeaturesPayload = { features: PolygonFeatures; lngLat: ClickedPoint };

export type DashboardState = {
  mapFilters: MapFilters;
  activeOverlays: string[];
  activePolygonLayer: string | null;
  polygonFeatures: PolygonFeatures;
  polygonClickLngLat: ClickedPoint | null;
  selectedLocation: SelectedLocation | null;
  clickedPoint: PointQuery | null;
  polygonQuery: PolygonQuery | null;
  timeseriesFilters: GriddedTimeseriesFilters;
  error: string | null;
};

type UpdateMapFiltersPayload = Partial<MapFilters>;

export const DEFAULT_TIMESERIES_FILTERS: GriddedTimeseriesFilters = {
  datasets: [],
  start_date: null,
  end_date: null,
};

// Datasets in the point query: those checked, else the map's active dataset
export const timeseriesDatasets = (
  filters: GriddedTimeseriesFilters,
  activeDataset: string | null
) => (filters.datasets.length > 0 ? filters.datasets : activeDataset ? [activeDataset] : []);

export const initialState: DashboardState = {
  mapFilters: {
    dataset: null,
    variable: null,
    timestepIndex: 0,
    colorRamp: 'raster/plasma',
    colorRampMin: 0,
    colorRampMax: 100,
  },

  activeOverlays: [], // string[] of overlay IDs currently shown on the map

  // Polygon layers from S3/pmtiles
  activePolygonLayer: null, // string (layer id) | null — exclusive selection

  // Every polygon under the last map click, including nested/overlapping ones
  polygonFeatures: [], // [{ id, name, ... }] — deduped feature properties
  polygonClickLngLat: null, // { lon, lat } | null — where the polygons were picked
  selectedLocation: null, // { primary_location_id, name } | null — feature chosen for a warehouse query

  clickedPoint: null, // { lon, lat, time } | null — last point clicked on the map, with the map's date
  polygonQuery: null, // { location_id, name, time } | null — polygon loaded for a timeseries, with the map's date

  // Datasets and time span for the point or polygon timeseries
  timeseriesFilters: DEFAULT_TIMESERIES_FILTERS,

  error: null,
};

export const ActionTypes = {
  UPDATE_MAP_FILTERS: 'UPDATE_MAP_FILTERS',
  UPDATE_TIMESERIES_FILTERS: 'UPDATE_TIMESERIES_FILTERS',
  TOGGLE_OVERLAY: 'TOGGLE_OVERLAY',
  SET_ACTIVE_POLYGON_LAYER: 'SET_ACTIVE_POLYGON_LAYER',
  SET_POLYGON_FEATURES: 'SET_POLYGON_FEATURES',
  CLEAR_POLYGON_FEATURES: 'CLEAR_POLYGON_FEATURES',
  SELECT_LOCATION: 'SELECT_LOCATION',
  SET_CLICKED_POINT: 'SET_CLICKED_POINT',
  LOAD_POLYGON_TIMESERIES: 'LOAD_POLYGON_TIMESERIES',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
} as const;

export type DashboardAction =
  | { type: typeof ActionTypes.UPDATE_MAP_FILTERS; payload: UpdateMapFiltersPayload }
  | {
      type: typeof ActionTypes.UPDATE_TIMESERIES_FILTERS;
      payload: Partial<GriddedTimeseriesFilters>;
    }
  | { type: typeof ActionTypes.TOGGLE_OVERLAY; payload: string }
  | { type: typeof ActionTypes.SET_ACTIVE_POLYGON_LAYER; payload: string | null }
  | { type: typeof ActionTypes.SET_POLYGON_FEATURES; payload: PolygonFeaturesPayload }
  | { type: typeof ActionTypes.CLEAR_POLYGON_FEATURES }
  | { type: typeof ActionTypes.SELECT_LOCATION; payload: SelectedLocation }
  | { type: typeof ActionTypes.SET_CLICKED_POINT; payload: PointQuery | null }
  | { type: typeof ActionTypes.LOAD_POLYGON_TIMESERIES; payload: PolygonQuery }
  | { type: typeof ActionTypes.SET_ERROR; payload: string | null }
  | { type: typeof ActionTypes.CLEAR_ERROR };

export const reducer = (state: DashboardState, action: DashboardAction): DashboardState => {
  switch (action.type) {
    case ActionTypes.UPDATE_MAP_FILTERS:
      return {
        ...state,
        mapFilters: {
          ...state.mapFilters,
          ...action.payload,
        },
      };

    case ActionTypes.UPDATE_TIMESERIES_FILTERS:
      return {
        ...state,
        timeseriesFilters: {
          ...state.timeseriesFilters,
          ...action.payload,
        },
      };

    case ActionTypes.TOGGLE_OVERLAY: {
      const id = action.payload;
      const next = state.activeOverlays.includes(id)
        ? state.activeOverlays.filter((x) => x !== id)
        : [id];
      return { ...state, activeOverlays: next };
    }

    case ActionTypes.SET_ACTIVE_POLYGON_LAYER:
      return {
        ...state,
        activePolygonLayer: action.payload,
        // Features from the previous layer no longer apply
        polygonFeatures: [],
        polygonClickLngLat: null,
        selectedLocation: null,
      };

    case ActionTypes.SET_POLYGON_FEATURES:
      return {
        ...state,
        polygonFeatures: Array.isArray(action.payload?.features) ? action.payload.features : [],
        polygonClickLngLat: action.payload?.lngLat ?? null,
        selectedLocation: null,
      };

    case ActionTypes.CLEAR_POLYGON_FEATURES:
      return {
        ...state,
        polygonFeatures: [],
        polygonClickLngLat: null,
        selectedLocation: null,
      };

    case ActionTypes.SELECT_LOCATION:
      return {
        ...state,
        selectedLocation: action.payload,
      };

    // The timeseries panel plots whichever was requested last
    case ActionTypes.SET_CLICKED_POINT:
      return {
        ...state,
        clickedPoint: action.payload,
        polygonQuery: null,
      };

    case ActionTypes.LOAD_POLYGON_TIMESERIES:
      return {
        ...state,
        polygonQuery: action.payload,
        clickedPoint: null,
      };

    case ActionTypes.SET_ERROR:
      return { ...state, error: action.payload };

    case ActionTypes.CLEAR_ERROR:
      return { ...state, error: null };

    default:
      return state;
  }
};

export type DashboardContextValue = {
  state: DashboardState;
  dispatch: Dispatch<DashboardAction>;
};

export const GriddedDashboardContext = createContext<DashboardContextValue | undefined>(undefined);

export const useDashboard = () => {
  const context = useContext(GriddedDashboardContext);
  if (!context) {
    throw new Error('useGriddedDashboard must be used within a GriddedDashboardProvider');
  }
  return context;
};
