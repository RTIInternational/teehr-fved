import { useEffect } from 'react';

import { FORECAST_DASHBOARD_DEFAULTS, selectDefault } from '@/config/dashboardDefaults';
import { ActionTypes, useDashboard } from '@/features/forecast/DashboardContext';
import { useDistinctValues } from '@/shared/queries/distinctValues';

/**
 * Load filters from data warehouse API and apply defaults
 * @param table Data warehouse table to reference in queries
 * @param enabled Set false to skip loading and applying defaults
 * @returns UseQueryResult objects for configurations and variables
 */
export const useInitialFilters = (table: string, enabled = true) => {
  const { dispatch } = useDashboard();

  const configurations = useDistinctValues(table, 'configuration_name', undefined, enabled);
  const variables = useDistinctValues(table, 'variable_name', undefined, enabled);
  useDistinctValues('primary_timeseries', 'variable_name', undefined, enabled);

  const defaultConfiguration = selectDefault(
    FORECAST_DASHBOARD_DEFAULTS.preferredConfiguration,
    configurations.data ?? []
  );

  const defaultVariable = selectDefault(
    FORECAST_DASHBOARD_DEFAULTS.preferredVariable,
    variables.data ?? []
  );

  useEffect(() => {
    if (!enabled) {
      return;
    }

    if (!defaultConfiguration || !defaultVariable) {
      return;
    }

    dispatch({
      type: ActionTypes.INITIALIZE_FILTERS,
      payload: {
        configuration: defaultConfiguration,
        variable: defaultVariable,
      },
    });
  }, [enabled, defaultConfiguration, defaultVariable, dispatch]);

  return {
    configurations,
    variables,
  };
};
