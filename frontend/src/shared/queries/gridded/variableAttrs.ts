import { queryOptions, useQuery } from '@tanstack/react-query';

import { griddedApiService } from '../../../services/griddedApi';

const fetchVariableAttrs = async (datasetId?: string | null) => {
  if (!datasetId) {
    throw new Error('Dataset required to retrieve variables');
  }

  return griddedApiService.getGriddedVariableAttrs(datasetId);
};

export const variableAttrsQueryOptions = (datasetId?: string | null) =>
  queryOptions({
    queryKey: ['gridded', datasetId, 'variableAttrs'],
    queryFn: () => fetchVariableAttrs(datasetId),
    enabled: !!datasetId,
    select: (data) => data.variables,
  });

export const useVariableAttrs = (datasetId?: string | null) =>
  useQuery(variableAttrsQueryOptions(datasetId));
