import { ActionIcon, Text, Tooltip } from '@mantine/core';
import { IconFilter, IconLayoutSidebarLeftCollapse } from '@tabler/icons-react';
import type { ReactNode } from 'react';

import styles from './FilterSidebarLayout.module.css';

type FilterSidebarLayoutProps = {
  /** Inputs that drive `children`, shown in the collapsible left column. */
  filters: ReactNode;
  /** The result the filters drive, e.g. a plot. */
  children: ReactNode;
  opened: boolean;
  onOpenedChange: (opened: boolean) => void;
  title?: string;
};

/**
 * Filters beside the content they drive, so both stay in view. The column
 * collapses to a narrow rail; below `sm` it covers the content instead. The
 * filters stay mounted while hidden, so their state survives.
 * Pair with `useFilterSidebar` for the open state.
 */
const FilterSidebarLayout = ({
  filters,
  children,
  opened,
  onOpenedChange,
  title = 'Filters',
}: FilterSidebarLayoutProps) => (
  <div className={styles.layout}>
    <aside className={styles.sidebar} hidden={!opened} aria-label={title}>
      <div className={styles.header}>
        <Text size="sm" fw={600}>
          {title}
        </Text>
        <Tooltip label={`Hide ${title.toLowerCase()}`}>
          <ActionIcon
            variant="subtle"
            size="sm"
            aria-label={`Hide ${title.toLowerCase()}`}
            onClick={() => onOpenedChange(false)}
          >
            <IconLayoutSidebarLeftCollapse size={16} />
          </ActionIcon>
        </Tooltip>
      </div>
      <div className={styles.filters}>{filters}</div>
    </aside>

    {!opened && (
      <div className={styles.rail}>
        <Tooltip label={`Show ${title.toLowerCase()}`} position="right">
          <ActionIcon
            variant="default"
            aria-label={`Show ${title.toLowerCase()}`}
            aria-expanded={false}
            onClick={() => onOpenedChange(true)}
          >
            <IconFilter size={16} />
          </ActionIcon>
        </Tooltip>
      </div>
    )}

    <div className={styles.content}>{children}</div>
  </div>
);

export default FilterSidebarLayout;
