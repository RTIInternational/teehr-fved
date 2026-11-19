import {
  Badge,
  Overlay,
  Paper,
  SimpleGrid,
  Card,
  Text,
  ThemeIcon,
  Title,
  UnstyledButton,
  Group,
  Stack,
  List,
} from '@mantine/core';
import { useNavigate } from 'react-router-dom';

import { newViews } from '@/views/registry';

import styles from './MapViewChooserModal.module.css';

export const MapViewChooserModal = () => {
  const navigate = useNavigate();
  const firstEnabledIndex = newViews.findIndex((view) => !view.disabled);

  return (
    <div className={styles.overlay}>
      <Overlay backgroundOpacity={0.38} zIndex={0} />
      <Paper
        component="dialog"
        shadow="lg"
        p="lg"
        className={styles.dialog}
        open
        aria-label="Choose a dashboard view"
        withBorder
      >
        <Stack>
          <div>
            <Title order={3}>Choose a Map View</Title>
            <Text size="sm" c="dimmed">
              Select one of the available views to load its analysis overlays.
            </Text>
          </div>
          <div>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
              {newViews.map((option, index) => {
                const OptionIcon = option.icon;
                return (
                  <UnstyledButton
                    key={option.id}
                    disabled={option.disabled}
                    data-autofocus={index === firstEnabledIndex || undefined}
                    onClick={() => navigate(option.path)}
                  >
                    <Card
                      withBorder
                      shadow="sm"
                      padding="md"
                      className={styles.option}
                      data-disabled={option.disabled || undefined}
                    >
                      <Card.Section className={styles.optionHeader} inheritPadding>
                        <Group>
                          <Group gap="sm" flex={1}>
                            <ThemeIcon size={30} radius="md">
                              <OptionIcon size={20} stroke={1.8} />
                            </ThemeIcon>
                            <div>
                              <Title order={5}>{option.label}</Title>
                            </div>
                          </Group>
                          {option.statusLabel ? (
                            <Badge size="xs">{option.statusLabel}</Badge>
                          ) : null}
                        </Group>
                      </Card.Section>
                      <Text size="sm">{option.description}</Text>
                      <List size="sm" pt="sm">
                        {option.features?.map((featureString) => (
                          <List.Item key={featureString}>{featureString}</List.Item>
                        ))}
                      </List>
                    </Card>
                  </UnstyledButton>
                );
              })}
            </SimpleGrid>
          </div>
        </Stack>
      </Paper>
    </div>
  );
};
