import { QueryClient } from '@tanstack/react-query';

// Kept in its own module so HMR updates to AppProviders don't recreate the
// client and drop the query cache.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 1000 * 60 * 120,
      staleTime: 1000 * 60 * 120,
    },
  },
});
