import { Container, Alert } from 'react-bootstrap';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import {
  DASHBOARD_ROUTE,
  DEFAULT_DASHBOARD_VIEW,
  buildDashboardHref,
  getDashboardViewFromSearch,
  isAvailableDashboardView,
} from '@/config/dashboardNavigation';
import { UnifiedDashboardPage } from '@/features/dashboard';
import AdminHome from '@/pages/admin/AdminHome';
import AdminLayout from '@/pages/admin/AdminLayout';
import ApiKeysAdmin from '@/pages/admin/ApiKeysAdmin';
import KeycloakAdmin from '@/pages/admin/KeycloakAdmin';
import DashboardsHome from '@/pages/DashboardsHome';
import Home from '@/pages/Home';
import { useAuth } from '@/shared/auth';
import DashboardQuickSwitchBar from '@/shared/components/DashboardQuickSwitchBar';
import Navbar from '@/shared/components/Navbar';

import 'bootstrap/dist/css/bootstrap.min.css';
import '@/theme/themeTokens.css';
import './App.css';

const RequireAuth = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, login, signup } = useAuth();
  const location = useLocation();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    const redirectUri = `${window.location.origin}${location.pathname}${location.search}`;

    return (
      <Container className="mt-5 text-center">
        <Alert variant="info">
          <Alert.Heading>Login Required</Alert.Heading>
          <p>Please login to access the TEEHR dashboards.</p>
          <div className="d-flex justify-content-center gap-2 flex-wrap">
            <button
              type="button"
              className="btn btn-success"
              onClick={() => login({ redirectUri })}
            >
              Login
            </button>
            <button
              type="button"
              className="btn btn-outline-primary"
              onClick={() => signup(redirectUri)}
            >
              Sign Up
            </button>
          </div>
        </Alert>
      </Container>
    );
  }

  return children;
};

const AdminRoute = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, roles } = useAuth();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    return <Navigate to="/hub" replace />;
  }

  if (!roles.includes('admin')) {
    return (
      <Container className="mt-5 text-center">
        <Alert variant="danger">
          <Alert.Heading>Access Denied</Alert.Heading>
          <p>Admin role required.</p>
        </Alert>
      </Container>
    );
  }

  return children;
};

const UnifiedDashboardRoute = () => {
  const location = useLocation();
  const currentView = getDashboardViewFromSearch(location.search);

  if (!isAvailableDashboardView(currentView)) {
    return <Navigate to={buildDashboardHref(DEFAULT_DASHBOARD_VIEW, location.search)} replace />;
  }

  const resolvedView = currentView ?? DEFAULT_DASHBOARD_VIEW;

  return <UnifiedDashboardPage view={resolvedView} />;
};

const LegacyDashboardRedirect = ({ view }: { view: string }) => {
  const location = useLocation();
  return <Navigate to={buildDashboardHref(view, location.search)} replace />;
};

const AppRoutes = () => {
  const location = useLocation();
  const hasDashboardSwitcher = location.pathname === DASHBOARD_ROUTE;

  return (
    <div className={`App${hasDashboardSwitcher ? ' app-has-dashboard-switcher' : ''}`}>
      <Navbar />
      <DashboardQuickSwitchBar />
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/hub" element={<DashboardsHome />} />
          <Route
            path={DASHBOARD_ROUTE}
            element={
              <RequireAuth>
                <UnifiedDashboardRoute />
              </RequireAuth>
            }
          />
          <Route path="/forecast" element={<LegacyDashboardRedirect view="streamflow" />} />
          <Route path="/gridded" element={<LegacyDashboardRedirect view="snow" />} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <AdminLayout />
              </AdminRoute>
            }
          >
            <Route index element={<AdminHome />} />
            <Route path="api-keys" element={<ApiKeysAdmin />} />
            <Route path="keycloak" element={<KeycloakAdmin />} />
          </Route>
        </Routes>
      </main>
    </div>
  );
};

function App() {
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}

export default App;
