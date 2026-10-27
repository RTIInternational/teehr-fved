import { ForecastDashboardProvider } from '@/features/forecast';
import { GriddedDashboardProvider } from '@/features/gridded';

import SnowDashboardView from './SnowDashboardView';
import StreamflowDashboardView from './StreamflowDashboardView';

type UnifiedDashboardPageProps = {
  view: string;
};

const UnifiedDashboardPage = ({ view }: UnifiedDashboardPageProps) => {
  if (view === 'snow') {
    return (
      <GriddedDashboardProvider>
        <SnowDashboardView />
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
