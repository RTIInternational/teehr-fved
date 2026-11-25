import { Button, Group, Table, Text, UnstyledButton } from '@mantine/core';
import { IconArrowDown, IconArrowsSort, IconArrowUp } from '@tabler/icons-react';

import type { MetricsTableData } from './useMetricsTableData';

import styles from './MetricsDataTable.module.css';

type MetricsDataTableProps = {
  data: MetricsTableData;
};

/** Sortable table of pivoted metrics; group-by columns lead, metric values align right. */
const MetricsDataTable = ({ data }: MetricsDataTableProps) => {
  const { headers, rows, groupByCount, sort, toggleSort, filteredColumnCount, clearFilters } = data;

  return (
    <div className={styles.root}>
      {filteredColumnCount > 0 && (
        <Group gap="xs" className={styles.filterBar}>
          <Text size="xs" c="dimmed">
            Active filters: {filteredColumnCount}
          </Text>
          <Button size="compact-xs" variant="default" onClick={clearFilters}>
            Clear All
          </Button>
        </Group>
      )}

      <div className={styles.scroll}>
        <Table
          stickyHeader
          highlightOnHover
          withColumnBorders
          fz="xs"
          verticalSpacing={4}
          horizontalSpacing="xs"
          className={styles.table}
        >
          <Table.Thead>
            <Table.Tr>
              {headers.map((header, index) => {
                const sorted = sort.column === index;
                const SortIcon = !sorted
                  ? IconArrowsSort
                  : sort.direction === 'asc'
                    ? IconArrowUp
                    : IconArrowDown;
                return (
                  <Table.Th
                    key={header}
                    aria-sort={
                      sorted ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined
                    }
                  >
                    <UnstyledButton className={styles.sortButton} onClick={() => toggleSort(index)}>
                      <span>{header}</span>
                      <SortIcon
                        size={12}
                        className={styles.sortIcon}
                        data-active={sorted || undefined}
                        aria-hidden
                      />
                    </UnstyledButton>
                  </Table.Th>
                );
              })}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row, rowIndex) => (
              <Table.Tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <Table.Td
                    key={headers[cellIndex]}
                    className={cellIndex < groupByCount ? styles.groupByCell : styles.metricCell}
                  >
                    {cell}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </div>
    </div>
  );
};

export default MetricsDataTable;
