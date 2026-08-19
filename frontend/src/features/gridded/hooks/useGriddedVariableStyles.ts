import { useCallback, useRef } from 'react';
import { useGriddedDashboard } from '../GriddedDashboardContext';
import { getVariableStyle } from '../utils/variableStyles';

type UpdateMapFiltersAction = {
  type: 'UPDATE_MAP_FILTERS';
  payload: {
    colorRamp: string;
    colorRampMin: number;
    colorRampMax: number;
  };
};

type GriddedDispatch = (action: UpdateMapFiltersAction) => void;

export const useGriddedVariableStyles = () => {
  const { dispatch } = useGriddedDashboard() as { dispatch: GriddedDispatch };
  const styledVariablesRef = useRef(new Set());

  const resetStyles = useCallback(() => {
    styledVariablesRef.current = new Set();
  }, []);

  const applyVariableStyleIfNew = useCallback(
    (variable: string | null) => {
      if (!variable || styledVariablesRef.current.has(variable)) return;
      styledVariablesRef.current.add(variable);
      const { colorRamp, min, max } = getVariableStyle(variable);
      dispatch({
        type: 'UPDATE_MAP_FILTERS',
        payload: { colorRamp, colorRampMin: min, colorRampMax: max },
      });
    },
    [dispatch]
  );

  return { resetStyles, applyVariableStyleIfNew };
};
