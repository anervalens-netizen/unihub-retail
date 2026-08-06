// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ExportWorkflow, PeriodSelector } from './controls';

describe('Settings export controls', () => {
  it('exposes the active export step in the DOM', () => {
    render(<ExportWorkflow step={4} onChange={() => undefined} />);

    expect(screen.getByRole('navigation', { name: 'Pași export Excel' })).toBeInTheDocument();
    expect(screen.getByText('Pasul 4 din 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { current: 'step' })).toHaveTextContent('Preview și export');
  });

  it('renders period controls with the selected-day summary', () => {
    render(
      <PeriodSelector
        years={['2026']}
        selectedYears={['2026']}
        onYearToggle={() => undefined}
        monthNumbers={['08']}
        selectedMonthNumbers={['08']}
        onMonthToggle={() => undefined}
        selectedDays={[1, 2]}
        onDayToggle={() => undefined}
        onSelectAllDays={() => undefined}
        onSelectFirstNineDays={() => undefined}
        selectedMonthCount={1}
      />,
    );

    expect(screen.getByText('1 luni rezultate · zilele 1, 2')).toBeInTheDocument();
    expect(screen.getAllByText('August')).toHaveLength(2);
  });
});
