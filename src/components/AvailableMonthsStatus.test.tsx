// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AvailableMonthsStatus } from './AvailableMonthsStatus';

describe('AvailableMonthsStatus', () => {
  it('shows a retry action for a transient unavailable state', () => {
    const onRetry = vi.fn();
    render(<AvailableMonthsStatus status="unavailable" onRetry={onRetry} />);
    expect(screen.getByText('Lunile disponibile nu au putut fi încărcate.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reîncearcă' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('does not offer a blind retry after session expiry', () => {
    render(<AvailableMonthsStatus status="session_expired" onRetry={vi.fn()} />);
    expect(screen.getByText(/Sesiunea a expirat/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
