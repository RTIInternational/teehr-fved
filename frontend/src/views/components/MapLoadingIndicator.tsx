import { Group, Loader, Paper, Text, VisuallyHidden } from '@mantine/core';

import styles from './MapLoadingIndicator.module.css';

/** A bar along the map's top edge while the view loads its map data. */
export const MapLoadingBar = ({ visible }: { visible: boolean }) =>
  visible ? <div className={styles.bar} aria-hidden /> : null;

/** A short status label, plus the same text announced to screen readers. */
export const MapLoadingLabel = ({ visible, label }: { visible: boolean; label: string }) => (
  <>
    {visible && (
      <Paper shadow="sm" radius="xl" px="sm" py={6} aria-hidden>
        <Group gap="xs" wrap="nowrap">
          <Loader size="xs" />
          <Text size="xs">{label}</Text>
        </Group>
      </Paper>
    )}
    <VisuallyHidden component="output" aria-live="polite">
      {visible ? label : ''}
    </VisuallyHidden>
  </>
);
