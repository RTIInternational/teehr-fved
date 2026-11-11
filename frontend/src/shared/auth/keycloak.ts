import Keycloak from 'keycloak-js';

const keycloakConfig = {
  url: import.meta.env.VITE_KEYCLOAK_URL || 'https://auth.teehr.local.app.garden',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'teehr',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'teehr-frontend',
};

const keycloak = new Keycloak(keycloakConfig);
let initPromise: Promise<boolean>;

export const initKeycloak = async () => {
  if (!initPromise) {
    initPromise = keycloak.init({
      onLoad: 'check-sso',
      pkceMethod: 'S256',
      silentCheckSsoFallback: false,
    });
  }
  return initPromise;
};

export const getKeycloak = () => keycloak;

export const login = (options = {}) => keycloak.login(options);

export const signup = (redirectUri: string) =>
  keycloak.login({
    action: 'register',
    ...(redirectUri ? { redirectUri } : {}),
  });

export const logout = () => keycloak.logout({ redirectUri: window.location.origin });

const INIT_WAIT_TIMEOUT_MS = 10_000;

/**
 * Waits for Keycloak init, up to INIT_WAIT_TIMEOUT_MS, so a slow or unreachable
 * Keycloak fails requests instead of hanging them. Init itself keeps running;
 * AuthProvider still waits for it and reports failures.
 */
const waitForInit = async () => {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<void>((resolve) => {
    timer = setTimeout(() => {
      console.warn(
        `Keycloak init exceeded ${INIT_WAIT_TIMEOUT_MS} ms; sending request without a token.`
      );
      resolve();
    }, INIT_WAIT_TIMEOUT_MS);
  });
  try {
    await Promise.race([initKeycloak(), timeout]);
  } catch {
    // Init failed; continue unauthenticated.
  } finally {
    clearTimeout(timer);
  }
};

/**
 * The current access token, refreshed if close to expiry. Waits for Keycloak
 * init first, so requests made during app boot carry the token instead of
 * racing it and failing with a 401.
 */
export const ensureFreshToken = async () => {
  await waitForInit();

  if (!keycloak.authenticated && !keycloak.token) {
    return null;
  }

  try {
    await keycloak.updateToken(30);
    return keycloak.token || null;
  } catch {
    // If refresh fails but a token is still present, keep using it.
    return keycloak.token || null;
  }
};

export const parseRoles = () => {
  if (!keycloak.tokenParsed) {
    return [];
  }
  return keycloak.tokenParsed.realm_access?.roles || [];
};
