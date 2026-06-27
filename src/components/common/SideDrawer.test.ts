import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SideDrawer } from './SideDrawer';

describe('SideDrawer', () => {
  it('renders nothing while closed', () => {
    const html = renderToStaticMarkup(
      createElement(SideDrawer, {
        open: false,
        onClose: () => undefined,
        title: 'Detalii',
        children: createElement('span', null, 'continut'),
      }),
    );

    expect(html).toBe('');
  });

  it('renders dialog markup and content while open', () => {
    const html = renderToStaticMarkup(
      createElement(SideDrawer, {
        open: true,
        onClose: () => undefined,
        title: 'Detalii magazin',
        children: createElement('section', null, 'continut drawer'),
      }),
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('Detalii magazin');
    expect(html).toContain('continut drawer');
  });
});
