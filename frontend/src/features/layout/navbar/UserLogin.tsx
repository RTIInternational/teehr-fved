import { Anchor, Button, Center, Loader, Stack, Text } from '@mantine/core';

import { useAuth } from '@/shared/auth';

import { UserCard } from './UserCard';

export const UserLogin = () => {
  const { ready, authenticated, username, roles, login, signup, logout } = useAuth();

  return (
    <Center h={75}>
      {!ready ? (
        <Loader size="sm" />
      ) : authenticated ? (
        <UserCard username={username} roles={roles} logout={logout} />
      ) : (
        <Stack gap="xs" align="center">
          <Button
            size="xs"
            variant="filled"
            onClick={() => login({ redirectUri: window.location.href })}
          >
            Login
          </Button>
          <Text c="dimmed" size="xs">
            New user?{' '}
            <Anchor component="button" onClick={() => signup(window.location.href)}>
              Sign up here.
            </Anchor>
          </Text>
        </Stack>
      )}
    </Center>
  );
};
