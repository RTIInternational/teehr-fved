import { useEffect, useRef } from 'react';

import { SNOW_DASHBOARD_DEFAULTS, selectDefault } from '@/config/dashboardDefaults';
import { teehrMapping } from '@/shared/api/gridded/variableAttrs';
import { useDatasets } from '@/shared/queries/gridded/datasets';
import { useTimesteps } from '@/shared/queries/gridded/timesteps';
import { useVariableAttrs } from '@/shared/queries/gridded/variableAttrs';
import { useVariables } from '@/shared/queries/gridded/variables';

import { ActionTypes, useDashboard } from '../DashboardContext';
import { useGriddedVariableStyles } from './useGriddedVariableStyles';

/**
 * Snow view defaults: the preferred SWE dataset when nothing is selected, the
 * latest timestep whenever the dataset changes, and per-variable color styles.
 * State present at mount is treated as the user's and left alone.
 */
export const useSnowDefaults = () => {
  const { state, dispatch } = useDashboard();
  const { dataset, variable } = state.mapFilters;

  const datasets = useDatasets();
  const variables = useVariables(dataset);
  const timesteps = useTimesteps(dataset);
  const variableAttrs = useVariableAttrs(dataset);
  const { resetStyles, applyVariableStyleIfNew } = useGriddedVariableStyles();

  const defaultAppliedRef = useRef(dataset !== null);
  useEffect(() => {
    if (defaultAppliedRef.current || datasets.data.length === 0) return;
    defaultAppliedRef.current = true;

    const preferred = selectDefault(SNOW_DASHBOARD_DEFAULTS.preferredDataset, datasets.data);
    if (!preferred) return;
    dispatch({
      type: ActionTypes.UPDATE_MAP_FILTERS,
      payload: {
        dataset: preferred,
        // A teehr name: GriddedControls picks the dataset's variable with it (else its first).
        variable: SNOW_DASHBOARD_DEFAULTS.preferredVariable,
        timestepIndex: 0,
      },
    });
  }, [datasets.data, dispatch]);

  // A dataset change, including the default above, waits for its timesteps and a
  // valid variable (GriddedControls resets the index when it swaps the variable),
  // then jumps to the latest timestep.
  const baselineDatasetRef = useRef(dataset);
  const latestPendingRef = useRef(false);
  useEffect(() => {
    if (dataset === baselineDatasetRef.current) return;
    baselineDatasetRef.current = dataset;
    latestPendingRef.current = dataset !== null;
  }, [dataset]);

  useEffect(() => {
    if (!latestPendingRef.current || timesteps.data.length === 0) return;
    if (!variable || !variables.data.includes(variable)) return;
    latestPendingRef.current = false;
    dispatch({
      type: ActionTypes.UPDATE_MAP_FILTERS,
      payload: { timestepIndex: timesteps.data.length - 1 },
    });
  }, [variable, variables.data, timesteps.data, dispatch]);

  // Ported from the legacy gridded Dashboard.
  useEffect(() => {
    if (dataset) resetStyles();
  }, [dataset, resetStyles]);

  // Wait for the dataset's attributes: they convert the style's teehr units to the stored ones
  useEffect(() => {
    if (variable && variableAttrs.data) {
      applyVariableStyleIfNew(variable, teehrMapping(variable, variableAttrs.data[variable]));
    }
  }, [variable, variableAttrs.data, applyVariableStyleIfNew]);
};
