// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TargetWorkflow } from './TargetWorkflow';

describe('TargetWorkflow', () => {
  it('exposes the active step and progress in the DOM', () => {
    render(<TargetWorkflow step={3} />);

    expect(screen.getByRole('navigation', { name: 'Flux Calculator Target' })).toBeInTheDocument();
    expect(screen.getByText('Pasul 3 din 4')).toBeInTheDocument();
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Ajustări manageri');
  });
});
