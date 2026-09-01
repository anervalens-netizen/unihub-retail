// @vitest-environment jsdom

import { createElement } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { GrileMonthlyPanelModel } from './useGrileMonthlyPanel';
import { GrileMonthlyPanelView, grileMonthlyIssueLabel } from './GrileMonthlyPanelView';

describe('grileMonthlyIssueLabel', () => {
  it('renders a safe, actionable Romanian source location', () => {
    expect(grileMonthlyIssueLabel({
      site_code: 'CRFZAL',
      store: 'CARREFOUR ZALAU',
      slot: 2,
      code: 'invalid_numeric_value',
      field: 'worked_hours',
    })).toBe('CRFZAL · CARREFOUR ZALAU · agent 2 · ore lucrate');
  });

  it('falls back to the bounded error code when no field is known', () => {
    expect(grileMonthlyIssueLabel({
      site_code: 'SITE01',
      store: 'Magazin',
      slot: 0,
      code: 'google_response_incomplete',
      field: null,
    })).toBe('SITE01 · Magazin · agent ? · google_response_incomplete');
  });

  it('shows the failed operation context and bounded source issue list', () => {
    const issues = Array.from({ length: 13 }, (_, index) => ({
      site_code: `SITE${index + 1}`,
      store: `Magazin ${index + 1}`,
      slot: 1,
      code: 'invalid_numeric_value',
      field: 'worked_hours',
    }));
    const model = {
      permissions: { data: { can_run: true } },
      open: true,
      setOpen: vi.fn(),
      job: null,
      running: false,
      result: null,
      error: null,
      manifest: {
        id: 8,
        operation_id: 11,
        month: '2026-08',
        operation: 'finalize',
        status: 'failed',
        expected: { stores: 71, agents: 143 },
        processed: { stores: 66, agents: 134 },
        error_count: 1,
        issues,
        approved: false,
      },
      approveManifest: vi.fn(),
      approving: false,
      approvedManifestId: null,
      trigger: vi.fn(),
      downloading: null,
      download: vi.fn(),
    } as unknown as GrileMonthlyPanelModel;

    render(createElement(GrileMonthlyPanelView, { month: '2026-08', model }));

    expect(screen.getByText(/Manifest finalizare \(failed\): 66\/71 magazine/)).toBeTruthy();
    expect(screen.getByText('SITE1 · Magazin 1 · agent 1 · ore lucrate')).toBeTruthy();
    expect(screen.getByText('+ 1 probleme suplimentare')).toBeTruthy();
  });
});
