import { useReducer, type PropsWithChildren } from 'react';

import { DashboardContext, initialState, reducer } from './DashboardContext';

export const DashboardProvider = ({ children }: PropsWithChildren) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  return (
    <DashboardContext.Provider value={{ state, dispatch }}>{children}</DashboardContext.Provider>
  );
};
