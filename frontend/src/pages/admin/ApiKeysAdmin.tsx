import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Code,
  CopyButton,
  Grid,
  Group,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useMemo, useState } from 'react';

import { useApiKeys, useCreateApiKey, useRevokeApiKey } from '@/shared/queries/apiKeys';

import styles from './ApiKeysAdmin.module.css';

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

const ApiKeysAdmin = () => {
  const [error, setError] = useState('');

  const [createName, setCreateName] = useState('');
  const [createScopes, setCreateScopes] = useState('');
  const [createdKey, setCreatedKey] = useState('');

  const apiKeysQuery = useApiKeys();
  const createApiKeyMutation = useCreateApiKey();
  const revokeApiKeyMutation = useRevokeApiKey();

  const sortedItems = useMemo(
    () => [...(apiKeysQuery.data || [])].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
    [apiKeysQuery.data]
  );

  const onCreate = async (event: React.SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setCreatedKey('');

    const name = createName.trim();
    if (!name) {
      setError('Name is required');
      return;
    }

    const scopes = createScopes
      .split(',')
      .map((scope) => scope.trim())
      .filter(Boolean);

    try {
      const created = await createApiKeyMutation.mutateAsync({ name, scopes });
      setCreatedKey(created?.api_key || '');
      setCreateName('');
      setCreateScopes('');
    } catch (error) {
      setError(getErrorMessage(error, 'Failed to create API key'));
    }
  };

  const onRevoke = async (keyId: string) => {
    setError('');
    try {
      await revokeApiKeyMutation.mutateAsync(keyId);
    } catch (error) {
      setError(getErrorMessage(error, 'Failed to revoke API key'));
    }
  };

  const isBusy =
    apiKeysQuery.isLoading || createApiKeyMutation.isPending || revokeApiKeyMutation.isPending;

  return (
    <Stack gap="md">
      <Title order={3}>API Keys</Title>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder padding="lg">
            <Title order={4}>Create API Key</Title>
            <Text size="sm" c="dimmed" mb="md">
              Key value is only shown once. Save it securely.
            </Text>

            <form onSubmit={onCreate}>
              <Stack gap="sm">
                <TextInput
                  label="Name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  maxLength={120}
                  placeholder="e.g. docs-test-key"
                  required
                />
                <TextInput
                  label="Scopes (optional)"
                  value={createScopes}
                  onChange={(e) => setCreateScopes(e.target.value)}
                  placeholder="comma,separated,scopes"
                />
                <Button type="submit" loading={createApiKeyMutation.isPending} w="fit-content">
                  Create Key
                </Button>
              </Stack>
            </form>

            {createdKey && (
              <Alert color="green" title="New key (copy now)" mt="md">
                <Group gap="xs" wrap="nowrap">
                  <Code block className={styles.key}>
                    {createdKey}
                  </Code>
                  <CopyButton value={createdKey}>
                    {({ copied, copy }) => (
                      <Tooltip label={copied ? 'Copied' : 'Copy key'}>
                        <ActionIcon
                          variant="subtle"
                          color={copied ? 'green' : 'gray'}
                          onClick={copy}
                          aria-label="Copy API key"
                        >
                          {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                        </ActionIcon>
                      </Tooltip>
                    )}
                  </CopyButton>
                </Group>
              </Alert>
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder padding="lg">
            <Title order={4} mb="md">
              Existing API Keys
            </Title>

            {(error || apiKeysQuery.error) && (
              <Alert color="red" mb="md">
                {error || apiKeysQuery.error?.message}
              </Alert>
            )}

            <Table.ScrollContainer minWidth={560}>
              <Table striped highlightOnHover withTableBorder withColumnBorders fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>Scopes</Table.Th>
                    <Table.Th>Created</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th>Action</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {apiKeysQuery.isLoading && (
                    <Table.Tr>
                      <Table.Td colSpan={5} ta="center" c="dimmed" py="md">
                        Loading API keys...
                      </Table.Td>
                    </Table.Tr>
                  )}
                  {!apiKeysQuery.isLoading && sortedItems.length === 0 && (
                    <Table.Tr>
                      <Table.Td colSpan={5} ta="center" c="dimmed" py="md">
                        No API keys yet.
                      </Table.Td>
                    </Table.Tr>
                  )}
                  {sortedItems.map((item) => {
                    const revoked = Boolean(item.revoked_at);
                    return (
                      <Table.Tr key={item.id}>
                        <Table.Td>{item.name}</Table.Td>
                        <Table.Td>{(item.scopes || []).join(', ') || '-'}</Table.Td>
                        <Table.Td>
                          {item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="light" color={revoked ? 'gray' : 'green'}>
                            {revoked ? 'Revoked' : 'Active'}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {!revoked ? (
                            <Button
                              variant="outline"
                              color="red"
                              size="compact-xs"
                              disabled={isBusy}
                              loading={
                                revokeApiKeyMutation.isPending &&
                                revokeApiKeyMutation.variables === item.id
                              }
                              onClick={() => onRevoke(item.id)}
                            >
                              Revoke
                            </Button>
                          ) : (
                            '-'
                          )}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  );
};

export default ApiKeysAdmin;
