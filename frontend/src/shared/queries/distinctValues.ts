import { queryOptions, useQuery } from '@tanstack/react-query';

import { getDistinctValues } from '@/shared/api/queryables';

export const distinctValuesQuery = (
  table: string,
  columnName: string,
  filters?: Record<string, string>,
  enabled = true
) =>
  queryOptions({
    queryKey: ['distinctValues', table, columnName, filters],
    queryFn: () => getDistinctValues(table, columnName, filters),
    enabled,
  });

export const useDistinctValues = (
  table: string,
  columnName: string,
  filters?: Record<string, string>,
  enabled = true
) => useQuery(distinctValuesQuery(table, columnName, filters, enabled));
