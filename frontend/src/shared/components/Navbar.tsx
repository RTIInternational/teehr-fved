import { useMemo, useState } from 'react';
import { Dropdown } from 'react-bootstrap';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import {
  DASHBOARD_NAV_ITEMS,
  DASHBOARD_ROUTE,
  getDashboardViewFromSearch,
} from '@/config/dashboardNavigation';
import { useAuth } from '@/shared/auth';
import { buildSearchFromViewportOnly } from '@/shared/utils/mapViewportUrl';

const JUPYTERHUB_URL =
  import.meta.env.VITE_JUPYTERHUB_URL || 'https://hub.teehr.local.app.garden/hub/spawn';

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const { ready, authenticated, username, roles, login, signup, logout } = useAuth();
  const isAdmin = roles.includes('admin');
  const canViewHubDeployment = authenticated && roles.includes('jupyter-user');

  const viewportSearch = useMemo(
    () => buildSearchFromViewportOnly(location.search),
    [location.search]
  );

  const activeView = useMemo(() => getDashboardViewFromSearch(location.search), [location.search]);

  const activeId = useMemo(() => {
    return DASHBOARD_NAV_ITEMS.find((item) => (item.viewKey ?? item.id) === activeView)?.id ?? null;
  }, [activeView]);

  const navigateToDashboard = (
    viewKey: string | undefined,
    fallbackId: string,
    isDisabled: boolean
  ) => {
    if (isDisabled) return;

    const resolvedView = viewKey ?? fallbackId;
    const params = new URLSearchParams(
      viewportSearch.startsWith('?') ? viewportSearch.slice(1) : ''
    );
    params.set('view', resolvedView);
    const search = params.toString();
    const target = search ? `${DASHBOARD_ROUTE}?${search}` : DASHBOARD_ROUTE;
    const current = `${location.pathname}${location.search}`;
    if (target === current) {
      setIsDrawerOpen(false);
      return;
    }
    navigate(target);
    setIsDrawerOpen(false);
  };

  const closeDrawer = () => setIsDrawerOpen(false);

  return (
    <>
      <button
        type="button"
        className="app-sidebar-toggle d-md-none"
        aria-label={isDrawerOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={isDrawerOpen}
        onClick={() => setIsDrawerOpen((prev) => !prev)}
      >
        <span aria-hidden="true">Menu</span>
      </button>

      {isDrawerOpen && (
        <button
          type="button"
          className="app-sidebar-backdrop d-md-none"
          aria-label="Close navigation menu"
          onClick={closeDrawer}
        />
      )}

      <aside
        className={`app-sidebar ${isDrawerOpen ? 'is-open' : ''}`}
        aria-label="Application navigation"
      >
        <div className="app-sidebar__scroll">
          <div className="app-sidebar__logo-wrap">
            <Link
              to="/"
              className="app-sidebar__logo-link d-inline-flex align-items-center"
              aria-label="TEEHR-Cloud Home"
              onClick={closeDrawer}
            >
              <img
                src="/teehr.png"
                alt="TEEHR Dashboard"
                height="34"
                className="d-inline-block align-text-top navbar-teehr-logo"
              />
            </Link>
          </div>

          <hr className="app-sidebar__divider" />

          <section className="app-sidebar__section" aria-label="Profile and authentication">
            {!ready && (
              <button className="btn btn-outline-primary btn-sm w-100" disabled>
                Auth Loading...
              </button>
            )}

            {ready && authenticated && (
              <Dropdown align="end" key={location.pathname} className="w-100">
                <Dropdown.Toggle variant="outline-primary" size="sm" className="w-100">
                  Profile
                </Dropdown.Toggle>
                <Dropdown.Menu
                  style={{ maxWidth: '352px', overflowY: 'auto', maxHeight: 'calc(100vh - 16px)' }}
                >
                  <Dropdown.ItemText className="text-wrap" style={{ overflowWrap: 'anywhere' }}>
                    Signed in as {username || 'user'}
                  </Dropdown.ItemText>
                  {isAdmin && (
                    <Dropdown.Item as={Link} to="/admin" onClick={closeDrawer}>
                      Admin Page
                    </Dropdown.Item>
                  )}
                  <Dropdown.Divider />
                  <Dropdown.Item
                    as="button"
                    onClick={() => {
                      void logout();
                      closeDrawer();
                    }}
                  >
                    Logout
                  </Dropdown.Item>
                </Dropdown.Menu>
              </Dropdown>
            )}

            {ready && !authenticated && (
              <div className="d-flex flex-column gap-2">
                <button
                  className="btn btn-outline-primary btn-sm"
                  onClick={() => signup(window.location.href)}
                >
                  Sign Up
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => login({ redirectUri: window.location.href })}
                >
                  Login
                </button>
              </div>
            )}
          </section>

          <section className="app-sidebar__section" aria-label="Dashboard navigation">
            <p className="app-sidebar__section-title mb-2">Dashboards</p>
            <div className="app-sidebar__dashboard-links">
              {DASHBOARD_NAV_ITEMS.map((item) => {
                const isActive = location.pathname === DASHBOARD_ROUTE && activeId === item.id;
                const isDisabled = item.status !== 'available';

                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`btn app-sidebar__dashboard-link text-start ${isActive ? 'is-active' : ''} ${isDisabled ? 'is-disabled' : ''}`}
                    onClick={() => navigateToDashboard(item.viewKey, item.id, isDisabled)}
                    disabled={isDisabled}
                    aria-current={isActive ? 'page' : undefined}
                    aria-label={isDisabled ? `${item.label} (coming soon)` : item.label}
                  >
                    <span>{item.label}</span>
                    {isDisabled ? <span className="small ms-1">(Soon)</span> : null}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="app-sidebar__section mt-auto" aria-label="Utility links">
            {canViewHubDeployment && (
              <a
                className="btn btn-outline-primary btn-sm w-100"
                href={JUPYTERHUB_URL}
                target="_blank"
                rel="noreferrer"
                onClick={closeDrawer}
              >
                JupyterHub
              </a>
            )}

            <Link
              className="btn btn-outline-primary btn-sm w-100 mt-2"
              to="/about"
              onClick={closeDrawer}
            >
              About
            </Link>
          </section>
        </div>
      </aside>
    </>
  );
};

export default Navbar;
