import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { App } from '@/App';
import { ForecastDashboard, ForecastDashboardProvider } from '@/features/forecast';
import { GriddedDashboard, GriddedDashboardProvider } from '@/features/gridded';
import AdminHome from '@/pages/admin/AdminHome';
import AdminLayout from '@/pages/admin/AdminLayout';
import ApiKeysAdmin from '@/pages/admin/ApiKeysAdmin';
import KeycloakAdmin from '@/pages/admin/KeycloakAdmin';
import DashboardsHome from '@/pages/DashboardsHome';
import Home from '@/pages/Home';

import { AdminRoute } from './AdminRoute';
import { RequireAuth } from './RequireAuth';

export const AppRouter = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<App />}>
        <Route index element={<Home />} />
        <Route path="/hub" element={<DashboardsHome />} />
        <Route
          path="/forecast"
          element={
            <RequireAuth>
              <ForecastDashboardProvider>
                <ForecastDashboard />
              </ForecastDashboardProvider>
            </RequireAuth>
          }
        />
        <Route
          path="/gridded"
          element={
            <RequireAuth>
              <GriddedDashboardProvider>
                <GriddedDashboard />
              </GriddedDashboardProvider>
            </RequireAuth>
          }
        />
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
      </Route>
    </Routes>
  </BrowserRouter>
);
