import { AppShell, Box, Burger } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useEffect, useState } from 'react';

import './App.css';
import { Outlet, useLocation } from 'react-router-dom';

import { MapProvider, MapStage } from '@/core/map';

import { NAV_BREAKPOINT } from './layout/layoutConstants';
import { NavBar } from './layout/navbar/NavBar';
import { DEFAULT_MAP_BOUNDS, mapTransformRequest } from './mapConfig';
import { MapViewportUrlSync } from './routes/MapViewportUrlSync';

import styles from './AppLayout.module.css';

export const AppLayout = () => {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const isMapShellRoute = location.pathname === '/' || location.pathname.startsWith('/map');
  const [mapRequested, setMapRequested] = useState(isMapShellRoute);
  if (isMapShellRoute && !mapRequested) {
    setMapRequested(true);
  }

  useEffect(() => {
    close();
  }, [location.pathname, close]);

  return (
    <div className="App">
      <MapProvider>
        <AppShell
          navbar={{ breakpoint: NAV_BREAKPOINT, width: 250, collapsed: { mobile: !opened } }}
        >
          <Box hiddenFrom={NAV_BREAKPOINT} className={styles.mobileMenuToggle}>
            <Burger opened={opened} onClick={toggle} size="sm" aria-label="Toggle navigation" />
          </Box>
          <AppShell.Navbar>
            <NavBar />
          </AppShell.Navbar>
          <AppShell.Main>
            <MapViewportUrlSync enabled={isMapShellRoute} />
            {mapRequested && (
              <MapStage
                className={styles.mapLayer}
                initialBounds={DEFAULT_MAP_BOUNDS}
                transformRequest={mapTransformRequest}
                hidden={!isMapShellRoute}
              />
            )}
            <Outlet />
          </AppShell.Main>
        </AppShell>
      </MapProvider>
    </div>
  );
};

export default AppLayout;
