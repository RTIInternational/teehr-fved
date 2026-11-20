import { useReducer, type PropsWithChildren } from 'react';

import { GriddedDashboardContext, initialState, reducer } from './DashboardContext';

export const DashboardProvider = ({ children }: PropsWithChildren) => {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <GriddedDashboardContext.Provider value={{ state, dispatch }}>
      {children}
    </GriddedDashboardContext.Provider>
  );
};
