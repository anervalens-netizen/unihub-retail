// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ChartFrame } from './ChartFrame';

describe('ChartFrame', () => {
  it('renders shared title, subtitle, controls and chart content', () => {
    render(
      <ChartFrame
        title="Evolutie lunara"
        subtitle="Ultimele 13 luni"
        controls={<button type="button">Standard</button>}
        contentClassName="h-64"
        headerAlign="start"
        className="hidden lg:block"
      >
        <div>chart-content</div>
      </ChartFrame>,
    );

    const heading = screen.getByRole('heading', { name: 'Evolutie lunara' });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText('Ultimele 13 luni')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Standard' })).toBeInTheDocument();
    expect(screen.getByText('chart-content')).toBeInTheDocument();
    expect(heading.closest('.glass')).toHaveClass('hidden', 'lg:block');
  });

  it('uses the same content slot for loading and empty states', () => {
    const { rerender } = render(
      <ChartFrame
        title="Trend KPI"
        contentClassName="h-48"
        loading
      >
        <div>chart-content</div>
      </ChartFrame>,
    );

    expect(screen.getByText('Se incarca...')).toBeInTheDocument();
    expect(screen.queryByText('chart-content')).not.toBeInTheDocument();

    rerender(
      <ChartFrame
        title="Trend KPI"
        contentClassName="h-48"
        empty
        emptyLabel="Nu exista date."
      >
        <div>chart-content</div>
      </ChartFrame>,
    );

    expect(screen.getByText('Nu exista date.')).toBeInTheDocument();
    expect(screen.queryByText('chart-content')).not.toBeInTheDocument();
  });
});
