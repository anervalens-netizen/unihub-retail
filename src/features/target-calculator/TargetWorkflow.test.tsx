// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TargetWorkflow } from './TargetWorkflow';
import { TargetErrorNotice } from '../../components/TargetCalculatorSubtab';

describe('TargetWorkflow', () => {
  it('exposes the active step and progress in the DOM', () => {
    render(<TargetWorkflow step={3} />);

    expect(screen.getByRole('navigation', { name: 'Flux Calculator Target' })).toBeInTheDocument();
    expect(screen.getByText('Pasul 3 din 4')).toBeInTheDocument();
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Ajustări manageri');
  });

  it('exposes an actionable retry after an optimistic conflict', () => {
    const onRetry = vi.fn();
    render(
      <TargetErrorNotice
        error="Revizia scenariului s-a schimbat."
        conflictRetryAvailable
        busy={false}
        dirty
        onRetry={onRetry}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reîncearcă salvarea' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Revizia scenariului s-a schimbat.');
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
