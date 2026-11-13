import { Alert, Container } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import { Navigate } from 'react-router-dom';

import { useAuth } from '@/shared/auth';

export const AdminRoute = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, roles } = useAuth();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    return <Navigate to="/" replace />;
  }

  if (!roles.includes('admin')) {
    return (
      <Container size="sm" py="xl">
        <Alert color="red" title="Access Denied" icon={<IconLock size={18} />}>
          Admin role required.
        </Alert>
      </Container>
    );
  }

  return children;
};
