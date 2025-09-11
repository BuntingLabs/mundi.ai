import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { init } from '@mundi/ee';
import App from './App';

init()
  .then(() => {
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  })
  .catch((e: unknown) => {
    // eslint-disable-next-line no-console
    console.error('[EE] init failed', e);
    const rootEl = document.getElementById('root')!;
    createRoot(rootEl).render(
      <StrictMode>
        <div style={{ padding: 24 }}>
          <h1>Initialization error</h1>
          <p>Authentication/EE initialization failed. Please refresh the page. If the issue persists, contact support.</p>
        </div>
      </StrictMode>,
    );
  });
