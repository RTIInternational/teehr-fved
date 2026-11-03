import { AppShell, Box, Burger, type MantineBreakpoint } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Outlet } from 'react-router-dom';

import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import { NavBar } from './features/layout/navbar/NavBar';

import styles from './App.module.css';

export const App = () => {
  const [opened, { toggle }] = useDisclosure();
  const navBreakpoint: MantineBreakpoint = 'sm';

  return (
    <div className="App">
      <AppShell navbar={{ breakpoint: navBreakpoint, width: 250, collapsed: { mobile: !opened } }}>
        <Box hiddenFrom={navBreakpoint} className={styles.mobileMenuToggle}>
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
