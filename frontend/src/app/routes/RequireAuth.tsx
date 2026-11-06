import { Container, Alert } from 'react-bootstrap';
import { useLocation } from 'react-router-dom';

import { useAuth } from '@/shared/auth/useAuth';

export const RequireAuth = ({ children }: React.PropsWithChildren) => {
  const { ready, authenticated, login, signup } = useAuth();
  const location = useLocation();

  if (!ready) {
    return null;
  }

  if (!authenticated) {
    const redirectUri = `${window.location.origin}${location.pathname}${location.search}`;

    return (
      <Container className="mt-5 text-center">
        <Alert variant="info">
          <Alert.Heading>Login Required</Alert.Heading>
          <p>Please login to access the TEEHR dashboards.</p>
          <div className="d-flex justify-content-center gap-2 flex-wrap">
            <button
              type="button"
              className="btn btn-success"
              onClick={() => login({ redirectUri })}
            >
              Login
            </button>
            <button
              type="button"
              className="btn btn-outline-primary"
              onClick={() => signup(redirectUri)}
            >
              Sign Up
            </button>
          </div>
        </Alert>
      </Container>
    );
  }

  return children;
};
