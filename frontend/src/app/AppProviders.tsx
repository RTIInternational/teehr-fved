import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';

import { AuthProvider } from '@/shared/auth';
import { FvedTheme } from '@/theme';

import { queryClient } from './queryClient';
import { AppRouter } from './routes/AppRouter';

export function AppProviders() {
  return (
    <MantineProvider theme={FvedTheme}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AppRouter />
        </AuthProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
