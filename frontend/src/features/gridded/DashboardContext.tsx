/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useReducer, type Dispatch } from 'react';
import type { TimeseriesData } from '@/shared/types/gridded/edr';
import type { ClickedPoint, MapFilters } from '@/shared/types/gridded/maps';

export type DashboardState = {
  mapFilters: MapFilters;
  activeOverlays: string[];
  clickedPoint: ClickedPoint | null;
  timeseriesLoading: boolean;
  timeseriesError: string | null;
  timeseriesData: TimeseriesData | null;
  mapLoaded: boolean;
  loading: boolean;
  error: string | null;
};

type UpdateMapFiltersPayload = Partial<MapFilters>;

const initialState: DashboardState = {
  mapFilters: {
    dataset: null,
    variable: null,
    timestepIndex: 0,
    colorRamp: 'raster/plasma',
    colorRampMin: 0,
    colorRampMax: 100,
  },

  activeOverlays: [], // string[] of overlay IDs currently shown on the map

  clickedPoint: null, // { lon, lat } | null — last point clicked on the map
  timeseriesLoading: false,
  timeseriesError: null,
  timeseriesData: null, // { times: string[], values: number[], lon, lat, variable } | null

  mapLoaded: false,
  loading: false,
  error: null,
};

export const ActionTypes = {
  SET_TIMESTEPS: 'SET_TIMESTEPS',
  UPDATE_MAP_FILTERS: 'UPDATE_MAP_FILTERS',
  TOGGLE_OVERLAY: 'TOGGLE_OVERLAY',
  SET_CLICKED_POINT: 'SET_CLICKED_POINT',
  SET_TIMESERIES_LOADING: 'SET_TIMESERIES_LOADING',
  SET_TIMESERIES_DATA: 'SET_TIMESERIES_DATA',
  SET_TIMESERIES_ERROR: 'SET_TIMESERIES_ERROR',
  SET_MAP_LOADED: 'SET_MAP_LOADED',
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
} as const;

export type DashboardAction =
  | { type: typeof ActionTypes.UPDATE_MAP_FILTERS; payload: UpdateMapFiltersPayload }
  | { type: typeof ActionTypes.TOGGLE_OVERLAY; payload: string }
  | { type: typeof ActionTypes.SET_CLICKED_POINT; payload: ClickedPoint | null }
  | { type: typeof ActionTypes.SET_TIMESERIES_LOADING; payload: boolean }
  | { type: typeof ActionTypes.SET_TIMESERIES_DATA; payload: TimeseriesData | null }
  | { type: typeof ActionTypes.SET_TIMESERIES_ERROR; payload: string | null }
  | { type: typeof ActionTypes.SET_MAP_LOADED; payload: boolean }
  | { type: typeof ActionTypes.SET_LOADING; payload: boolean }
  | { type: typeof ActionTypes.SET_ERROR; payload: string | null }
  | { type: typeof ActionTypes.CLEAR_ERROR };

const reducer = (state: DashboardState, action: DashboardAction): DashboardState => {
  switch (action.type) {
    case ActionTypes.UPDATE_MAP_FILTERS:
      return {
        ...state,
        mapFilters: {
          ...state.mapFilters,
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

    case ActionTypes.SET_CLICKED_POINT:
      return {
        ...state,
        clickedPoint: action.payload,
        timeseriesData: null,
        timeseriesError: null,
      };

    case ActionTypes.SET_TIMESERIES_LOADING:
      return { ...state, timeseriesLoading: action.payload };

    case ActionTypes.SET_TIMESERIES_DATA:
      return {
        ...state,
        timeseriesData: action.payload,
        timeseriesLoading: false,
        timeseriesError: null,
      };

    case ActionTypes.SET_TIMESERIES_ERROR:
      return { ...state, timeseriesError: action.payload, timeseriesLoading: false };

    case ActionTypes.SET_MAP_LOADED:
      return { ...state, mapLoaded: action.payload };

    case ActionTypes.SET_LOADING:
      return { ...state, loading: action.payload };

    case ActionTypes.SET_ERROR:
      return { ...state, error: action.payload, loading: false };

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

const GriddedDashboardContext = createContext<DashboardContextValue | undefined>(undefined);

export const DashboardProvider = ({ children }: React.PropsWithChildren) => {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <GriddedDashboardContext.Provider value={{ state, dispatch }}>
      {children}
    </GriddedDashboardContext.Provider>
  );
};

export const useDashboard = () => {
  const context = useContext(GriddedDashboardContext);
  if (!context) {
    throw new Error('useGriddedDashboard must be used within a GriddedDashboardProvider');
  }
  return context;
};
