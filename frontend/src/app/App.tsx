import { AppShell, Box, Burger } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useEffect, useState } from 'react';

import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import { Outlet, useLocation, useMatch } from 'react-router-dom';

import { MapProvider, MapStage } from '@/core/map';

import { NAV_BREAKPOINT } from './layout/layoutConstants';
import { NavBar } from './layout/navbar/NavBar';
import { DEFAULT_MAP_BOUNDS, mapTransformRequest } from './mapConfig';
import { MapViewportUrlSync } from './routes/MapViewportUrlSync';

import styles from './App.module.css';

export const App = () => {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const isMapRoute = useMatch('/map/*') !== null;
  const [mapRequested, setMapRequested] = useState(isMapRoute);
  if (isMapRoute && !mapRequested) {
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
            <MapViewportUrlSync enabled={isMapRoute} />
            {mapRequested && (
              <MapStage
                className={styles.mapLayer}
                initialBounds={DEFAULT_MAP_BOUNDS}
                transformRequest={mapTransformRequest}
                hidden={!isMapRoute}
              />
            )}
            <Outlet />
          </AppShell.Main>
        </AppShell>
      </MapProvider>
    </div>
  );
};

export default App;
