/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useReducer } from 'react';

const initialGriddedState = {
  datasets: [],       // string[] — available dataset names from xpublish
  variables: [],      // string[] — variables for the selected dataset
  timesteps: [],      // string[] — ISO datetime strings for selected dataset+variable

  mapFilters: {
    dataset: null,
    variable: null,
    timestepIndex: 0,
    colorRamp: 'raster/plasma',
    colorRampMin: 0,
    colorRampMax: 100,
  },

  activeOverlays: [],   // string[] of overlay IDs currently shown on the map

  variableAttrs: {},    // { [varName]: { units, long_name, ... } } — from /variable-attrs endpoint

  // Polygon layers from S3/pmtiles
  availablePolygonLayers: [],  // [{ id, path, source_layer }, ...] — from discovery endpoint
  activePolygonLayer: null,     // string (layer id) | null — exclusive selection
  polygonLayerLoading: false,
  polygonLayerError: null,

  // Which tab the right-hand panel shows. Lives here rather than in local state
  // because a map click needs to bring the polygon tab forward.
  rightPanelTab: 'dataset',   // 'dataset' | 'polygons'

  // Every polygon under the last map click, including nested/overlapping ones
  polygonFeatures: [],        // [{ id, name, ... }] — deduped feature properties
  polygonClickLngLat: null,   // { lon, lat } | null — where the polygons were picked
  selectedLocation: null,     // { primary_location_id, name } | null — feature chosen for a warehouse query

  clickedPoint: null,       // { lon, lat } | null — last point clicked on the map
  timeseriesLoading: false,
  timeseriesError: null,
  // One series at a time — the most recent request wins. `source` says which
  // backend produced it so the panel can label the plot correctly:
  //   'gridded'   — xpublish EDR point query  { times, values, lon, lat, variable }
  //   'warehouse' — iceberg query for a polygon { times, values, location_id, name, variable }
  timeseriesData: null,

  mapLoaded: false,
  loading: false,
  error: null,
};

export const ActionTypes = {
  SET_DATASETS: 'SET_DATASETS',
  SET_VARIABLES: 'SET_VARIABLES',
  SET_TIMESTEPS: 'SET_TIMESTEPS',
  UPDATE_MAP_FILTERS: 'UPDATE_MAP_FILTERS',
  TOGGLE_OVERLAY: 'TOGGLE_OVERLAY',
  SET_POLYGON_LAYERS: 'SET_POLYGON_LAYERS',
  SET_ACTIVE_POLYGON_LAYER: 'SET_ACTIVE_POLYGON_LAYER',
  SET_POLYGON_LAYER_LOADING: 'SET_POLYGON_LAYER_LOADING',
  SET_POLYGON_LAYER_ERROR: 'SET_POLYGON_LAYER_ERROR',
  SET_RIGHT_PANEL_TAB: 'SET_RIGHT_PANEL_TAB',
  SET_POLYGON_FEATURES: 'SET_POLYGON_FEATURES',
  CLEAR_POLYGON_FEATURES: 'CLEAR_POLYGON_FEATURES',
  SELECT_LOCATION: 'SELECT_LOCATION',
  SET_CLICKED_POINT: 'SET_CLICKED_POINT',
  SET_TIMESERIES_LOADING: 'SET_TIMESERIES_LOADING',
  SET_TIMESERIES_DATA: 'SET_TIMESERIES_DATA',
  SET_TIMESERIES_ERROR: 'SET_TIMESERIES_ERROR',
  SET_VARIABLE_ATTRS: 'SET_VARIABLE_ATTRS',
  SET_MAP_LOADED: 'SET_MAP_LOADED',
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
};

const griddedDashboardReducer = (state, action) => {
  switch (action.type) {
    case ActionTypes.SET_DATASETS:
      return {
        ...state,
        datasets: Array.isArray(action.payload) ? action.payload : [],
        loading: false,
      };

    case ActionTypes.SET_VARIABLES:
      return {
        ...state,
        variables: Array.isArray(action.payload) ? action.payload : [],
        // Reset variable and timestep when the dataset changes
        mapFilters: {
          ...state.mapFilters,
          variable: action.payload?.[0] ?? null,
          timestepIndex: 0,
        },
        timesteps: [],
      };

    case ActionTypes.SET_TIMESTEPS:
      return {
        ...state,
        timesteps: Array.isArray(action.payload) ? action.payload : [],
        mapFilters: {
          ...state.mapFilters,
          timestepIndex: 0,
        },
      };

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

    case ActionTypes.SET_POLYGON_LAYERS:
      return {
        ...state,
        availablePolygonLayers: Array.isArray(action.payload) ? action.payload : [],
        polygonLayerLoading: false,
        polygonLayerError: null,
      };

    case ActionTypes.SET_ACTIVE_POLYGON_LAYER:
      return {
        ...state,
        activePolygonLayer: action.payload,
        // Features from the previous layer no longer apply
        polygonFeatures: [],
        polygonClickLngLat: null,
        selectedLocation: null,
      };

    case ActionTypes.SET_RIGHT_PANEL_TAB:
      return { ...state, rightPanelTab: action.payload };

    case ActionTypes.SET_POLYGON_FEATURES:
      return {
        ...state,
        polygonFeatures: Array.isArray(action.payload?.features) ? action.payload.features : [],
        polygonClickLngLat: action.payload?.lngLat ?? null,
        selectedLocation: null,
        // Bring the results forward — otherwise the click looks like a no-op
        rightPanelTab: 'polygons',
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

    case ActionTypes.SET_POLYGON_LAYER_LOADING:
      return {
        ...state,
        polygonLayerLoading: action.payload,
      };

    case ActionTypes.SET_POLYGON_LAYER_ERROR:
      return {
        ...state,
        polygonLayerError: action.payload,
        polygonLayerLoading: false,
      };

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
      return { ...state, timeseriesData: action.payload, timeseriesLoading: false, timeseriesError: null };

    case ActionTypes.SET_TIMESERIES_ERROR:
      return { ...state, timeseriesError: action.payload, timeseriesLoading: false };

    case ActionTypes.SET_VARIABLE_ATTRS:
      return { ...state, variableAttrs: action.payload };

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

const GriddedDashboardContext = createContext(null);

export const GriddedDashboardProvider = ({ children }) => {
  const [state, dispatch] = useReducer(griddedDashboardReducer, initialGriddedState);
  return (
    <GriddedDashboardContext.Provider value={{ state, dispatch }}>
      {children}
    </GriddedDashboardContext.Provider>
  );
};

export const useGriddedDashboard = () => {
  const context = useContext(GriddedDashboardContext);
  if (!context) {
    throw new Error('useGriddedDashboard must be used within a GriddedDashboardProvider');
  }
  return context;
};
