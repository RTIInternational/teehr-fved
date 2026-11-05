import { AppShell, Box, Burger } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useEffect } from 'react';

import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import { Outlet, useLocation } from 'react-router-dom';

import { NAV_BREAKPOINT } from './features/layout/layoutConstants';
import { NavBar } from './features/layout/navbar/NavBar';

import styles from './App.module.css';

export const App = () => {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();

  useEffect(() => {
    close();
  }, [location.pathname, close]);

  return (
    <div className="App">
      <AppShell navbar={{ breakpoint: NAV_BREAKPOINT, width: 250, collapsed: { mobile: !opened } }}>
        <Box hiddenFrom={NAV_BREAKPOINT} className={styles.mobileMenuToggle}>
          <Burger opened={opened} onClick={toggle} size="sm" aria-label="Toggle navigation" />
        </Box>
        <AppShell.Navbar>
          <NavBar />
        </AppShell.Navbar>
        <AppShell.Main>
          <Outlet />
        </AppShell.Main>
      </AppShell>
    </div>
  );
};

export default App;
