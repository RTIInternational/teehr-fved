import { AppShell, Divider, Image, NavLink, ScrollArea } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';
import { NavLink as RouterLink } from 'react-router-dom';

import { useAuth } from '@/shared/auth';

import { UserLogin } from './UserLogin';

import classes from './NavBar.module.css';

const JUPYTERHUB_URL =
  import.meta.env.VITE_JUPYTERHUB_URL || 'https://hub.teehr.local.app.garden/hub/spawn';

export const NavBar = () => {
  const { authenticated, roles } = useAuth();
  const canViewHubDeployment = authenticated && roles.includes('jupyter-user');

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
      {canViewHubDeployment && (
        <AppShell.Section>
          <Divider />
          <NavLink
            href={JUPYTERHUB_URL}
            label="JupyterHub"
            rightSection={<IconExternalLink size={20} stroke={1.5} />}
            target="_blank"
          />
        </AppShell.Section>
      )}
      <AppShell.Section>
        <Divider />
        <NavLink renderRoot={(props) => <RouterLink to="/" {...props} />} label="About" />
      </AppShell.Section>
    </>
  );
};
