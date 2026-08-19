import { useCallback } from 'react';
import { griddedApiService } from '../../../services/griddedApi';
import { useGriddedDashboard, ActionTypes } from '../DashboardContext';

export const useGriddedDataFetching = () => {
  const { state, dispatch } = useGriddedDashboard();

  const loadVariableAttrs = useCallback(
    async (datasetId) => {
      try {
        const data = await griddedApiService.getGriddedVariableAttrs(datasetId);
        dispatch({ type: ActionTypes.SET_VARIABLE_ATTRS, payload: data.variables ?? {} });
      } catch (err) {
        console.error('useGriddedDataFetching: Failed to load variable attrs:', err);
      }
    },
    [dispatch]
  );

  const runTimeseriesQuery = useCallback(
    async (lon, lat) => {
      const { dataset, variable } = state.mapFilters;
      const { timesteps } = state;
      if (!dataset || !variable || timesteps.length === 0) return;
      dispatch({ type: ActionTypes.SET_TIMESERIES_LOADING, payload: true });
      try {
        const data = await griddedApiService.fetchGriddedEdrTimeseries(
          dataset,
          variable,
          lon,
          lat,
          timesteps
        );
        dispatch({
          type: ActionTypes.SET_TIMESERIES_DATA,
          payload: { ...data, lon, lat, variable },
        });
      } catch (err) {
        console.error('useGriddedDataFetching: Timeseries query failed:', err);
        dispatch({ type: ActionTypes.SET_TIMESERIES_ERROR, payload: err.message });
      }
    },
    [state.mapFilters.dataset, state.mapFilters.variable, state.timesteps, dispatch]
  );

  return { loadVariableAttrs, runTimeseriesQuery };
};
