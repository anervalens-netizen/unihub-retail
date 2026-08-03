import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AgentEvaluationSubtab } from './AgentEvaluationSubtab';

describe('AgentEvaluationSubtab', () => {
  it('defaults to the initial analysis and the latest closed month', () => {
    const html = renderToStaticMarkup(createElement(AgentEvaluationSubtab, {
      currentMonth: '2026-08',
      months: ['2026-08', '2026-06', '2026-07'],
    }));

    expect(html).toContain('Iulie 2026');
    expect(html).toContain('Mecanism analiză agenți');
    expect(html).toContain('Punctaj 0–100');
    expect(html).not.toContain('Comparație veche');
    expect(html.indexOf('>Analiză</button>')).toBeLessThan(html.indexOf('>Punctaj 0–100</button>'));
    expect(html).not.toContain('Cum se face evaluarea');
  });
});
