import { queryOptions, useQuery } from '@tanstack/react-query';

import { griddedApiService } from '../../../services/griddedApi';

const fetchVariables = async (datasetId?: string | null) => {
  if (!datasetId) {
    throw new Error('Dataset required to retrieve variables');
  }

  return griddedApiService.getGriddedVariables(datasetId);
};

export const variablesQueryOptions = (datasetId?: string | null) =>
  queryOptions({
    queryKey: ['gridded', datasetId, 'variables'],
    queryFn: () => fetchVariables(datasetId),
    enabled: !!datasetId,
    select: (data) => data.variables,
  });

export const useVariables = (datasetId?: string | null) => {
  const query = useQuery(variablesQueryOptions(datasetId));
  return { ...query, data: query.data ?? [] };
};
