import { Container, Alert } from 'react-bootstrap';
import { Navigate } from 'react-router-dom';

import { useAuth } from '@/shared/auth';

export const AdminRoute = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, roles } = useAuth();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    return <Navigate to="/hub" replace />;
  }

  if (!roles.includes('admin')) {
    return (
      <Container className="mt-5 text-center">
        <Alert variant="danger">
          <Alert.Heading>Access Denied</Alert.Heading>
          <p>Admin role required.</p>
        </Alert>
      </Container>
    );
  }

  return children;
};
