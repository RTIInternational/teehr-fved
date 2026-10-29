import { Container, Alert } from 'react-bootstrap';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';

import {
  DASHBOARD_ROUTE,
  buildDashboardBaseHref,
  buildDashboardHref,
  getDashboardViewFromSearch,
  isKnownDashboardView,
} from '@/config/dashboardNavigation';
import { UnifiedDashboardPage } from '@/features/dashboard';
import AdminHome from '@/pages/admin/AdminHome';
import AdminLayout from '@/pages/admin/AdminLayout';
import ApiKeysAdmin from '@/pages/admin/ApiKeysAdmin';
import KeycloakAdmin from '@/pages/admin/KeycloakAdmin';
import DashboardsHome from '@/pages/DashboardsHome';
import Home from '@/pages/Home';
import { useAuth } from '@/shared/auth';
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

  if (currentView && !isKnownDashboardView(currentView)) {
    return <Navigate to={buildDashboardBaseHref(location.search)} replace />;
  }

  return <UnifiedDashboardPage view={currentView} />;
};

const LegacyDashboardRedirect = ({ view }: { view: string }) => {
  const location = useLocation();
  return <Navigate to={buildDashboardHref(view, location.search)} replace />;
};

const AppRoutes = () => {
  return (
    <div className="App">
      <Navbar />
      <main className="app-main-content">
        <Routes>
          <Route path="/" element={<Navigate to={DASHBOARD_ROUTE} replace />} />
          <Route path="/about" element={<Home />} />
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
