import { ForecastDashboard, ForecastDashboardProvider } from '@/features/forecast';
import { GriddedDashboard, GriddedDashboardProvider } from '@/features/gridded';

import UnifiedDashboardShell from './UnifiedDashboardShell';

type UnifiedDashboardPageProps = {
  view: string;
};

const UnifiedDashboardPage = ({ view }: UnifiedDashboardPageProps) => {
  const mapContent =
    view === 'snow' ? (
      <GriddedDashboardProvider>
        <GriddedDashboard />
      </GriddedDashboardProvider>
    ) : (
      <ForecastDashboardProvider>
        <ForecastDashboard />
      </ForecastDashboardProvider>
    );

  return <UnifiedDashboardShell mapContent={mapContent} />;
};

export default UnifiedDashboardPage;
