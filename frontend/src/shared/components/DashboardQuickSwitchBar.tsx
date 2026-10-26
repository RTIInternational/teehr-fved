import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { DASHBOARD_NAV_ITEMS } from '@/config/dashboardNavigation';
import { buildSearchFromViewportOnly } from '@/shared/utils/mapViewportUrl';

const DASHBOARD_ROUTES_WITH_SWITCHER = new Set(['/forecast', '/gridded']);

const DashboardQuickSwitchBar = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const isVisible = DASHBOARD_ROUTES_WITH_SWITCHER.has(location.pathname);
  const viewportSearch = useMemo(
    () => buildSearchFromViewportOnly(location.search),
    [location.search]
  );

  const activeId = useMemo(() => {
    return DASHBOARD_NAV_ITEMS.find((item) => item.route === location.pathname)?.id ?? null;
  }, [location.pathname]);

  const enabledItems = DASHBOARD_NAV_ITEMS.filter((item) => item.status === 'available');

  const navigateToDashboard = (route: string) => {
    const target = `${route}${viewportSearch}`;
    const current = `${location.pathname}${location.search}`;
    if (target === current) return;
    navigate(target);
  };

  if (!isVisible) {
    return null;
  }

  return (
    <nav className="dashboard-switcher-bar border-bottom" aria-label="Dashboard quick switcher">
      <div className="container-fluid px-3 px-md-4 py-2">
        <div className="dashboard-switcher-desktop d-none d-md-flex gap-2 align-items-center flex-wrap">
          {DASHBOARD_NAV_ITEMS.map((item) => {
            const isActive = activeId === item.id;
            const isDisabled = item.status !== 'available';

            return (
              <button
                key={item.id}
                type="button"
                className={`btn btn-sm ${isActive ? 'btn-primary' : 'btn-outline-primary'} ${isDisabled ? 'dashboard-switcher-disabled' : ''}`}
                onClick={() => navigateToDashboard(item.route)}
                disabled={isDisabled}
                aria-current={isActive ? 'page' : undefined}
                aria-label={isDisabled ? `${item.label} (coming soon)` : item.label}
              >
                {item.label}
                {isDisabled ? <span className="ms-1 small">(Soon)</span> : null}
              </button>
            );
          })}
        </div>

        <div className="dashboard-switcher-mobile d-md-none d-flex align-items-center gap-2">
          <label htmlFor="dashboard-switcher-select" className="form-label mb-0 fw-semibold small">
            Dashboard:
          </label>
          <select
            id="dashboard-switcher-select"
            className="form-select form-select-sm"
            value={activeId ?? ''}
            onChange={(e) => {
              const selected = enabledItems.find((item) => item.id === e.target.value);
              if (selected) {
                navigateToDashboard(selected.route);
              }
            }}
            aria-label="Select dashboard"
          >
            {DASHBOARD_NAV_ITEMS.map((item) => (
              <option key={item.id} value={item.id} disabled={item.status !== 'available'}>
                {item.label}
                {item.status !== 'available' ? ' (Coming Soon)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>
    </nav>
  );
};

export default DashboardQuickSwitchBar;
