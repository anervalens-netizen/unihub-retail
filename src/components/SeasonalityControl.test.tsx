// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SeasonalityControl } from './SeasonalityControl';

describe('SeasonalityControl', () => {
  it('keeps the calculation controls disabled until initialization', () => {
    render(<SeasonalityControl value={null} disabled onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Anul trecut' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Multi-year' })).toBeDisabled();
  });

  it('emits the exact manually selected mode', () => {
    const onChange = vi.fn();
    render(<SeasonalityControl value="single" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Multi-year' }));
    expect(onChange).toHaveBeenCalledWith('multi');
  });
});
