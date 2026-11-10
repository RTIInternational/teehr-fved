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
import { useUncontrolled } from '@mantine/hooks';
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconChevronDown,
  IconChevronUp,
} from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';

import styles from './MapDataDock.module.css';

export type MapDataDockSection = {
  value: string;
  label: string;
  content: ReactNode;
};

type MapDataDockProps = {
  sections: MapDataDockSection[];
  /** Controlled active section; omit to let the dock manage it. */
  section?: string;
  onSectionChange?: (section: string) => void;
  icon?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  /** Shows a close button that calls this, e.g. to clear the selection. */
  onClose?: () => void;
  closeLabel?: string;
  /** When set, the dock shows only this message instead of its sections. */
  placeholder?: ReactNode;
};

/**
 * Bottom panel for a map view's results. Every section stays mounted, so their
 * state survives switching, collapsing and expanding.
 */
export const MapDataDock = ({
  sections,
  section,
  onSectionChange,
  icon,
  title,
  subtitle,
  onClose,
  closeLabel = 'Close',
  placeholder,
}: MapDataDockProps) => {
  const [requestedSection, setActiveSection] = useUncontrolled({
    value: section,
    defaultValue: sections[0]?.value,
    onChange: onSectionChange,
  });
  // Sections can come and go (e.g. none until something is selected); fall back
  // to the first one when the requested section isn't offered.
  const activeSection = sections.some(({ value }) => value === requestedSection)
    ? requestedSection
    : sections[0]?.value;
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // A section change, including one made by the parent, brings the dock back.
  const [shownSection, setShownSection] = useState(activeSection);
  if (activeSection !== shownSection) {
    setShownSection(activeSection);
    setCollapsed(false);
  }

  if (placeholder) {
    return (
      <Paper shadow="md" radius="md" px="md" py="sm" withBorder className={styles.dock}>
        <Group gap="xs" wrap="nowrap">
          {icon}
          <Text size="sm" c="dimmed">
            {placeholder}
          </Text>
        </Group>
      </Paper>
    );
  }

  return (
    <Paper
      shadow="md"
      radius="md"
      withBorder
      className={styles.dock}
      data-expanded={(expanded && !collapsed) || undefined}
    >
      <div className={styles.header}>
        <Group gap="xs" wrap="nowrap" className={styles.title}>
          {icon}
          {(title || subtitle) && (
            <Box miw={0}>
              {title && (
                <Text size="sm" fw={600} truncate>
                  {title}
                </Text>
              )}
              {subtitle && (
                <Text size="xs" c="dimmed" truncate>
                  {subtitle}
                </Text>
              )}
            </Box>
          )}
        </Group>

        <Group gap="xs" wrap="nowrap" className={styles.controls}>
          {sections.length > 1 && (
            <SegmentedControl
              size="xs"
              data={sections.map(({ value, label }) => ({ value, label }))}
              value={activeSection}
              onChange={setActiveSection}
            />
          )}
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
          {onClose && <CloseButton aria-label={closeLabel} onClick={onClose} />}
        </Group>
      </div>

      <div className={styles.body} hidden={collapsed}>
        {sections.map(({ value, content }) => (
          <div key={value} className={styles.section} hidden={value !== activeSection}>
            {content}
          </div>
        ))}
      </div>
    </Paper>
  );
};
