import { Avatar, Box, Group, Menu, Text, UnstyledButton, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconChevronRight } from '@tabler/icons-react';
import { useState } from 'react';
import { NavLink as RouterLink } from 'react-router-dom';

import { NAV_BREAKPOINT } from '../layoutConstants';

type UserCardProps = {
  username: string | null;
  roles: string[];
  logout: () => void;
};

export const UserCard = ({ username, roles, logout }: UserCardProps) => {
  const name = username ?? 'Unknown User';
  const isAdmin = roles.includes('admin');
  const role = isAdmin ? 'Admin' : 'User';
  const [opened, setOpened] = useState(false);
  const theme = useMantineTheme();
  const isMobile = useMediaQuery(`(max-width: ${theme.breakpoints[NAV_BREAKPOINT]})`);
  const menuPosition = isMobile ? 'bottom-end' : 'right-start';

  return (
    <Menu shadow="md" width={200} position={menuPosition} zIndex={2000} onChange={setOpened}>
      <Menu.Target>
        <UnstyledButton w="100%">
          <Group wrap="nowrap" w="100%" align="center" justify="flex-start" px="md">
            <Avatar size="md" name={name} alt={name} color="initials" />
            <Box flex={1}>
              <Text fw={500}>{name}</Text>
              <Text c="dimmed" fz="sm">
                {role}
              </Text>
            </Box>
            <IconChevronRight
              stroke={1.5}
              color="gray"
              style={{
                transform: opened ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 150ms ease',
              }}
            />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        {isAdmin && (
          <>
            <Menu.Label>Navigation</Menu.Label>
            <Menu.Item renderRoot={(props) => <RouterLink to="/admin" {...props} />}>
              Admin Tools
            </Menu.Item>
          </>
        )}
        <Menu.Label>Actions</Menu.Label>
        <Menu.Item
          onClick={() => {
            logout();
          }}
        >
          Logout
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
};
