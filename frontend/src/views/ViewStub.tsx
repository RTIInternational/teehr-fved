import { Paper, Text } from '@mantine/core';

import styles from './ViewStub.module.css';

type ViewStubProps = {
  label: string;
};

/** Temporary map view content until the view's real implementation lands. */
export const ViewStub = ({ label }: ViewStubProps) => {
  return (
    <div className={styles.overlay}>
      <Paper shadow="sm" p="xs" className={styles.badge}>
        <Text size="sm">View: {label}</Text>
      </Paper>
    </div>
  );
};
