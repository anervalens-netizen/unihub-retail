import { createElement, type ErrorInfo, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@sentry/react', () => ({
  captureException: vi.fn(),
}));

import * as Sentry from '@sentry/react';
import { ErrorBoundary } from './ErrorBoundary';

describe('ErrorBoundary', () => {
  it('renders children while no error is present', () => {
    const boundary = new ErrorBoundary({
      children: createElement('span', null, 'continut normal'),
    });

    const html = renderToStaticMarkup(boundary.render() as ReactElement);

    expect(html).toContain('continut normal');
  });

  it('renders the default recovery state after a render error', () => {
    const boundary = new ErrorBoundary({
      children: createElement('span', null, 'ascuns'),
    });
    boundary.state = ErrorBoundary.getDerivedStateFromError(
      new Error('render failed'),
    );

    const html = renderToStaticMarkup(boundary.render() as ReactElement);

    expect(html).toContain('Ecranul nu a putut fi incarcat');
    expect(html).toContain('Incearca din nou');
    expect(html).toContain('Reincarca aplicatia');
    expect(html).not.toContain('render failed');
  });

  it('supports contextual copy and reports the exception to Sentry', () => {
    const boundary = new ErrorBoundary({
      children: null,
      title: 'Salariile nu au putut fi incarcate',
      description: 'Reincearca dupa reincarcarea datelor.',
    });
    const error = new Error('sensitive internal failure');
    boundary.state = ErrorBoundary.getDerivedStateFromError(error);
    boundary.componentDidCatch(error, {
      componentStack: 'at SalaryPanel',
    } as ErrorInfo);

    const html = renderToStaticMarkup(boundary.render() as ReactElement);

    expect(html).toContain('Salariile nu au putut fi incarcate');
    expect(html).toContain('Reincearca dupa reincarcarea datelor.');
    expect(Sentry.captureException).toHaveBeenCalledWith(error, {
      extra: { componentStack: 'at SalaryPanel' },
    });
  });
});
