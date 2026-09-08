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
    expect(heading.closest('.glass')).toHaveClass('p-4', 'hidden', 'lg:block');
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

  it('supports the earned compact mobile spacing without changing content semantics', () => {
    render(
      <ChartFrame
        title="Evolutie zilnica"
        icon={<span>icon</span>}
        contentClassName="daily-content"
        className="flex min-w-0 flex-col"
        compactMobile
      >
        <div>daily-chart</div>
      </ChartFrame>,
    );

    const heading = screen.getByRole('heading', { name: 'Evolutie zilnica' });
    const frame = heading.closest('.glass');
    expect(frame).toHaveClass('p-3', 'sm:p-4', 'flex', 'min-w-0', 'flex-col');
    expect(frame).not.toHaveClass('p-4');
    expect(heading.closest('div.mb-2')).toHaveClass('sm:mb-3');
    expect(screen.getByText('daily-chart').parentElement).toHaveClass('daily-content');
  });
});
