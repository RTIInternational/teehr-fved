import {
  AppShell,
  Center,
  Divider,
  Group,
  Image,
  NavLink,
  ScrollArea,
  Stack,
  Text,
} from '@mantine/core';
import {
  IconBucket,
  IconDroplet,
  IconExternalLink,
  IconRipple,
  IconSnowflake,
} from '@tabler/icons-react';
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
        <RouterLink to="/" className={classes.logoLink}>
          <Center p="xs">
            <Stack gap={0}>
              <Group align="center" justify="center" gap="xs" wrap="nowrap">
                <Image src="/usbr-seal-white.png" alt="USBR Logo" w={54} />
                <Text fz={60} fw={800} lh={1.3} className={classes.logoText}>
                  FVED
                </Text>
              </Group>
            </Stack>
          </Center>
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
            renderRoot={(props) => <RouterLink to="/hub" {...props} />}
            label="Dashboard Views"
            styles={{
              label: {
                fontWeight: 'var(--mantine-font-weight-bold)',
              },
            }}
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/forecast" {...props} />}
            label="Streamflow"
            leftSection={<IconRipple size={20} />}
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/water-supply" {...props} />}
            label="Water Supply"
            disabled
            leftSection={<IconBucket size={20} />}
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/crmms" {...props} />}
            label="Colorado River"
            disabled
            leftSection={<IconDroplet size={20} />}
          />
          <NavLink
            renderRoot={(props) => <RouterLink to="/gridded" {...props} />}
            label="Snow"
            leftSection={<IconSnowflake size={20} />}
          />
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
      <AppShell.Section>
        <Divider />
        {/* <Text c="dimmed" fs="italic">
          Developed by
        </Text> */}
        <Center>
          <a href="https://www.rti.org/" target="_blank">
            <Image src="/RTI_logo_rgb_sm.png" w={150} />
          </a>
        </Center>
      </AppShell.Section>
    </>
  );
};
