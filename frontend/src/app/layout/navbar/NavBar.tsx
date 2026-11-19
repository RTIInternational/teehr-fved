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
import { IconExternalLink } from '@tabler/icons-react';
import { NavLink as RouterLink } from 'react-router-dom';

import { useAuth } from '@/shared/auth';
import { newViews } from '@/views/registry';

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
            renderRoot={(props) => <RouterLink to={`/map/`} end {...props} />}
            label="Map Views"
            styles={{
              label: {
                fontWeight: 'var(--mantine-font-weight-bold)',
              },
            }}
          />
          {newViews.map((view) => {
            const ViewIcon = view.icon;
            return (
              <NavLink
                key={view.id}
                renderRoot={(props) => <RouterLink to={view.path} {...props} />}
                label={view.label}
                disabled={view.disabled}
                leftSection={<ViewIcon size={20} />}
              />
            );
          })}
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
        <NavLink renderRoot={(props) => <RouterLink to="/about" {...props} />} label="About" />
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
