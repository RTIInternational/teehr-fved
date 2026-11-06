import { Paper, Text } from '@mantine/core';
import { useParams } from 'react-router-dom';

import styles from './MapViewPlaceholder.module.css';

/** Temporary /map/:viewId content until the view system replaces it. */
export const MapViewPlaceholder = () => {
  const { viewId } = useParams();

  return (
    <div className={styles.overlay}>
      <Paper shadow="sm" p="xs" className={styles.badge}>
        <Text size="sm">View: {viewId}</Text>
      </Paper>
    </div>
  );
};
