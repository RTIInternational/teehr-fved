import { ForecastDashboardProvider } from '@/features/forecast';
import { GriddedDashboard, GriddedDashboardProvider } from '@/features/gridded';

import StreamflowDashboardView from './StreamflowDashboardView';

type UnifiedDashboardPageProps = {
  view: string;
};

const UnifiedDashboardPage = ({ view }: UnifiedDashboardPageProps) => {
  if (view === 'snow') {
    return (
      <GriddedDashboardProvider>
        <GriddedDashboard />
      </GriddedDashboardProvider>
    );
  }

  return (
    <ForecastDashboardProvider>
      <StreamflowDashboardView />
    </ForecastDashboardProvider>
  );
};

export default UnifiedDashboardPage;
