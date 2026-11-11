import { Button, Center, Code, Stack, Text, Title } from '@mantine/core';
import { IconMap } from '@tabler/icons-react';
import { Link, useLocation } from 'react-router-dom';

/** Shown for any path that doesn't match a page. */
const NotFound = () => {
  const { pathname } = useLocation();

  return (
    <Center mih="100dvh" p="md">
      <Stack align="center" gap="sm" maw={480} ta="center">
        <Title order={2}>Page not found</Title>
        <Text c="dimmed">
          There is no page at <Code>{pathname}</Code>. It may have moved or been removed.
        </Text>
        <Button component={Link} to="/map" leftSection={<IconMap size={18} />} mt="sm">
          Go to map views
        </Button>
      </Stack>
    </Center>
  );
};

export default NotFound;
