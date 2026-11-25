import { Button, Group, Overlay, Paper, Stack, Text, Title } from '@mantine/core';
import { useLocation } from 'react-router-dom';

import { useAuth } from '@/shared/auth/useAuth';

import styles from './RequireAuth.module.css';

export const RequireAuth = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, login, signup } = useAuth();
  const location = useLocation();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    const redirectUri = `${window.location.origin}${location.pathname}${location.search}`;

    // Same overlay-and-dialog treatment as MapViewChooserModal, over the dimmed map
    return (
      <div className={styles.overlay}>
        <Overlay backgroundOpacity={0.38} zIndex={0} />
        <Paper
          component="dialog"
          open
          aria-labelledby="require-auth-title"
          shadow="lg"
          p="lg"
          withBorder
          className={styles.dialog}
        >
          <Stack align="center" ta="center">
            <div>
              <Title order={3} id="require-auth-title">
                Login Required
              </Title>
              <Text size="sm" c="dimmed" pt="xs">
                Please login to view this FVED module.
              </Text>
            </div>
            <Group justify="center" gap="sm">
              <Button onClick={() => login({ redirectUri })}>Login</Button>
              <Button variant="default" onClick={() => signup(redirectUri)}>
                Sign Up
              </Button>
            </Group>
          </Stack>
        </Paper>
      </div>
    );
  }

  return children;
};
