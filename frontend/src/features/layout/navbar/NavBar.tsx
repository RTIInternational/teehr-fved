import { AppShell, Divider, Image, NavLink, ScrollArea } from '@mantine/core';
import { NavLink as RouterLink } from 'react-router-dom';

import { UserLogin } from './UserLogin';

import classes from './NavBar.module.css';

export const NavBar = () => {
  return (
    <>
      <AppShell.Section>
        <RouterLink to="/">
          <Image src="teehr.png" alt="TEEHR Logo" w="100%" className={classes.logo} />
        </RouterLink>
        <Divider />
      </AppShell.Section>
      <AppShell.Section>
        <UserLogin />
        <Divider />
      </AppShell.Section>
      <AppShell.Section grow component={ScrollArea}>
        <div>
          <NavLink
            renderRoot={(props) => <RouterLink to="/forecast" {...props} />}
            label="Streamflow"
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/water-supply" {...props} />}
            label="Water Supply"
            disabled
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/crmms" {...props} />}
            label="Colorado River"
            disabled
          />
          <NavLink renderRoot={(props) => <RouterLink to="/gridded" {...props} />} label="Snow" />
        </div>
      </AppShell.Section>
      <AppShell.Section>
        <Divider />
        <NavLink renderRoot={(props) => <RouterLink to="/" {...props} />} label="About" />
      </AppShell.Section>
    </>
  );
};
