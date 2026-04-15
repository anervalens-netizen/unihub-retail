import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {postFrontendError} from './api/errors';
import App from './App.tsx';
import './index.css';

window.onerror = (message, _source, lineno, colno, error) => {
  postFrontendError({
    message: String(message),
    traceback: error?.stack ?? null,
    path: window.location.pathname,
    extra: { lineno, colno },
  });
};

window.onunhandledrejection = (event: PromiseRejectionEvent) => {
  const reason = event.reason as { message?: string; stack?: string } | string | undefined;
  postFrontendError({
    message: reason && typeof reason === 'object' && reason.message
      ? reason.message
      : String(reason ?? 'Unhandled rejection'),
    traceback: reason && typeof reason === 'object' ? reason.stack ?? null : null,
    path: window.location.pathname,
  });
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
