import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SegmentedTabs } from './SegmentedTabs';

describe('SegmentedTabs', () => {
  it('renders tablist and selected tab state', () => {
    const html = renderToStaticMarkup(
      createElement(SegmentedTabs, {
        ariaLabel: 'Sectiuni',
        value: 'promo',
        onChange: () => undefined,
        options: [
          { value: 'incentive', label: 'Incentive' },
          { value: 'promo', label: 'Promo' },
        ],
      }),
    );

    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-label="Sectiuni"');
    expect(html).toContain('aria-selected="true"');
    expect(html).toContain('Promo');
  });

  it('marks disabled tabs in markup', () => {
    const html = renderToStaticMarkup(
      createElement(SegmentedTabs, {
        ariaLabel: 'Sectiuni',
        value: 'incentive',
        onChange: () => undefined,
        options: [
          { value: 'incentive', label: 'Incentive' },
          { value: 'promo', label: 'Promo', disabled: true },
        ],
      }),
    );

    expect(html).toContain('disabled=""');
  });
});
