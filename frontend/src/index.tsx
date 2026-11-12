import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';

import { AppProviders } from './app/AppProviders';

import '@mantine/core/styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders />
  </StrictMode>
);
