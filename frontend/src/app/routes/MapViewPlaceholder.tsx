import { Paper, Text } from '@mantine/core';

import type { ViewDefinition } from '@/core/views';

import styles from './MapViewPlaceholder.module.css';

/** Temporary /map/:viewId content until the view system replaces it. */
type MapViewPlaceholderProps = {
  view: ViewDefinition;
};

export const MapViewPlaceholder = ({ view }: MapViewPlaceholderProps) => {
  return (
    <div className={styles.overlay}>
      <Paper shadow="sm" p="xs" className={styles.badge}>
        <Text size="sm">View: {view.id}</Text>
      </Paper>
    </div>
  );
};
