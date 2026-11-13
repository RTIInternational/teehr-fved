// Global stylesheets load before any component so component CSS modules win ties
// with Mantine's styles.
import '@mantine/core/styles.css';
import '@mantine/dates/styles.css';
import { StrictMode } from 'react';
import ReactDOM from 'react-dom/client';

import { AppProviders } from './app/AppProviders';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders />
  </StrictMode>
);
