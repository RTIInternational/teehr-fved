import { Button, Card, Text, Title } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';

const KEYCLOAK_BASE_URL =
  import.meta.env.VITE_KEYCLOAK_URL || 'https://auth.teehr.local.app.garden';

const KeycloakAdmin = () => {
  const keycloakAdminUrl = `${KEYCLOAK_BASE_URL}/admin/teehr/console/`;

  return (
    <Card withBorder padding="lg">
      <Title order={3}>TEEHR Keycloak</Title>
      <Text c="dimmed" mt="xs" mb="md">
        Manage users, groups, clients, and realm settings in the Keycloak admin console.
      </Text>
      <Button
        component="a"
        href={keycloakAdminUrl}
        target="_blank"
        rel="noreferrer"
        rightSection={<IconExternalLink size={16} />}
        w="fit-content"
      >
        Open Keycloak Admin Console
      </Button>
    </Card>
  );
};

export default KeycloakAdmin;
