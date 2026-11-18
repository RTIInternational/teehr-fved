import { Button, Card, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';
import { Link } from 'react-router-dom';

const KEYCLOAK_BASE_URL =
  import.meta.env.VITE_KEYCLOAK_URL || 'https://auth.teehr.local.app.garden';
const PREFECT_BASE_URL =
  import.meta.env.VITE_PREFECT_URL || 'https://prefect.teehr.local.app.garden';

type BaseCard = {
  title: string;
  description: string;
  buttonLabel: string;
};

type InternalCard = BaseCard & {
  to: string;
  isExternal?: false;
};

type ExternalCard = BaseCard & {
  href: string;
  isExternal: true;
};

type AdminCard = InternalCard | ExternalCard;

const cards: AdminCard[] = [
  {
    title: 'API Keys',
    description: 'Create, review, and revoke API keys for administrative workflows.',
    to: '/admin/api-keys',
    buttonLabel: 'Manage API Keys',
  },
  {
    title: 'Keycloak',
    description: 'Manage users, groups, clients, and realm settings in the Keycloak admin console.',
    href: `${KEYCLOAK_BASE_URL}/admin/teehr/console/`,
    buttonLabel: 'Open Keycloak Admin',
    isExternal: true,
  },
  {
    title: 'Prefect',
    description: 'Access Prefect admin console to manage workflows and deployments.',
    href: PREFECT_BASE_URL,
    buttonLabel: 'Open Prefect',
    isExternal: true,
  },
];

const AdminHome = () => {
  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>Admin Home</Title>
        <Text c="dimmed">
          Use this workspace to manage platform administration tasks. Additional tools will be added
          over time.
        </Text>
      </div>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {cards.map((card) => (
          <Card key={card.title} withBorder padding="lg">
            <Stack gap="sm" h="100%">
              <Title order={4}>{card.title}</Title>
              <Text size="sm" c="dimmed">
                {card.description}
              </Text>
              {/* mt="auto" keeps the buttons aligned along the bottom of the row */}
              {card.isExternal ? (
                <Button
                  component="a"
                  href={card.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="outline"
                  rightSection={<IconExternalLink size={16} />}
                  mt="auto"
                  w="fit-content"
                >
                  {card.buttonLabel}
                </Button>
              ) : (
                <Button component={Link} to={card.to} variant="outline" mt="auto" w="fit-content">
                  {card.buttonLabel}
                </Button>
              )}
            </Stack>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
};

export default AdminHome;
