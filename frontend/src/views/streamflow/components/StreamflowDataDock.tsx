import {
  ActionIcon,
  Box,
  CloseButton,
  Group,
  Paper,
  SegmentedControl,
  Text,
  Tooltip,
} from '@mantine/core';
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconChevronDown,
  IconChevronUp,
  IconMapPin,
} from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';

import type { MapLocation } from '@/shared/types/locations';

import styles from './StreamflowDataDock.module.css';

type DockSection = 'timeseries' | 'metrics';

const SECTIONS: { value: DockSection; label: string }[] = [
  { value: 'timeseries', label: 'Time Series' },
  { value: 'metrics', label: 'Metrics' },
];

type StreamflowDataDockProps = {
  selectedLocation: MapLocation | null;
  onClearSelection: () => void;
  timeseries: ReactNode;
  metrics: ReactNode;
};

/** Bottom panel with the selected location's time series and metrics. */
export const StreamflowDataDock = ({
  selectedLocation,
  onClearSelection,
  timeseries,
  metrics,
}: StreamflowDataDockProps) => {
  const [section, setSection] = useState<DockSection>('timeseries');
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  if (!selectedLocation) {
    return (
      <Paper shadow="md" radius="md" px="md" py="sm" withBorder className={styles.dock}>
        <Group gap="xs" wrap="nowrap">
          <IconMapPin size={18} />
          <Text size="sm" c="dimmed">
            Select a location on the map to view its time series and metrics.
          </Text>
        </Group>
      </Paper>
    );
  }

  const ids = [selectedLocation.primary_location_id, selectedLocation.secondary_location_id]
    .filter(Boolean)
    .join(' · ');

  return (
    <Paper
      shadow="md"
      radius="md"
      withBorder
      className={styles.dock}
      data-expanded={(expanded && !collapsed) || undefined}
    >
      <Group justify="space-between" gap="sm" px="md" py="xs" wrap="nowrap">
        <Group gap="xs" wrap="nowrap" miw={0}>
          <IconMapPin size={18} style={{ flexShrink: 0 }} />
          <Box miw={0}>
            <Text size="sm" fw={600} truncate>
              {selectedLocation.name}
            </Text>
            <Text size="xs" c="dimmed" truncate>
              {ids}
            </Text>
          </Box>
        </Group>

        <Group gap="xs" wrap="nowrap">
          <SegmentedControl
            size="xs"
            data={SECTIONS}
            value={section}
            onChange={(value) => {
              setSection(value as DockSection);
              setCollapsed(false);
            }}
          />
          {!collapsed && (
            <Tooltip label={expanded ? 'Restore size' : 'Expand'}>
              <ActionIcon
                variant="subtle"
                aria-label={expanded ? 'Restore panel size' : 'Expand panel'}
                aria-pressed={expanded}
                onClick={() => setExpanded((value) => !value)}
              >
                {expanded ? <IconArrowsMinimize size={18} /> : <IconArrowsMaximize size={18} />}
              </ActionIcon>
            </Tooltip>
          )}
          <Tooltip label={collapsed ? 'Show panel' : 'Hide panel'}>
            <ActionIcon
              variant="subtle"
              aria-label={collapsed ? 'Show panel' : 'Hide panel'}
              aria-expanded={!collapsed}
              onClick={() => setCollapsed((value) => !value)}
            >
              {collapsed ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
            </ActionIcon>
          </Tooltip>
          <CloseButton aria-label="Clear selected location" onClick={onClearSelection} />
        </Group>
      </Group>

      {/* Both sections stay mounted so their state (submitted filters, view modes,
          selected table) survives switching and collapsing. */}
      <div className={styles.body} hidden={collapsed}>
        <div className={styles.section} hidden={section !== 'timeseries'}>
          {timeseries}
        </div>
        <div className={styles.section} hidden={section !== 'metrics'}>
          {metrics}
        </div>
      </div>
    </Paper>
  );
};
