import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/app/AppLayout';
import AdminHome from '@/pages/admin/AdminHome';
import AdminLayout from '@/pages/admin/AdminLayout';
import ApiKeysAdmin from '@/pages/admin/ApiKeysAdmin';
import KeycloakAdmin from '@/pages/admin/KeycloakAdmin';
import Home from '@/pages/Home';
import NotFound from '@/pages/NotFound';

import { AdminRoute } from './AdminRoute';
import { MapRoute as NonAuthMapRoute } from './MapRoute';
import { RequireAuth } from './RequireAuth';

/** Temporary auth handler -- remove when API supports non-auth reads */
const MapRoute = () => (
  <RequireAuth>
    <NonAuthMapRoute />
  </RequireAuth>
);

export const AppRouter = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<MapRoute />} />
        <Route path="/about" element={<Home />} />
        <Route path="/map" element={<MapRoute />} />
        <Route path="/map/:viewId" element={<MapRoute />} />
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
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  </BrowserRouter>
);
