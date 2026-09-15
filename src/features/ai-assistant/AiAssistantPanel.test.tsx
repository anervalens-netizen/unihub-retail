// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AiAssistantPanel } from './AiAssistantPanel';

const context = {
  tab: 'hub' as const,
  period: '2026-08',
  hubSection: 'current' as const,
  filters: { firma: [], rm: [], magazin: [], agent: [] },
};

describe('AiAssistantPanel', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('is absent without owner access', () => {
    render(<AiAssistantPanel canAccess={false} currentContext={context} messages={[]} runStatus="idle" onSubmit={vi.fn()} onStop={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Deschide UniHub AI' })).not.toBeInTheDocument();
  });

  it('opens the responsive shell and submits the page context with effort', () => {
    const submit = vi.fn();
    render(<AiAssistantPanel canAccess currentContext={context} messages={[]} runStatus="idle" onSubmit={submit} onStop={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Deschide UniHub AI' }));
    expect(screen.getByRole('complementary', { name: 'UniHub AI' })).toBeInTheDocument();
    expect(screen.getByText(/Context: hub · 2026-08/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Mesaj pentru UniHub AI'), { target: { value: 'Analizează luna curentă' } });
    fireEvent.click(screen.getByRole('button', { name: /Trimite/ }));

    expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      text: 'Analizează luna curentă',
      effort: 'high',
      includeCurrentView: true,
      mode: 'send',
      currentView: expect.objectContaining({ retail: context }),
    }));
  });

  it('turns a new message into steer while a run is active and exposes stop', () => {
    const submit = vi.fn();
    const stop = vi.fn();
    render(<AiAssistantPanel canAccess currentContext={context} messages={[]} runStatus="running" onSubmit={submit} onStop={stop} />);
    fireEvent.click(screen.getByRole('button', { name: 'Deschide UniHub AI' }));
    fireEvent.change(screen.getByLabelText('Mesaj pentru UniHub AI'), { target: { value: 'Pe ASM, nu pe regional' } });
    fireEvent.click(screen.getByRole('button', { name: /Steer/ }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ mode: 'steer' }));
    fireEvent.click(screen.getByRole('button', { name: /Stop/ }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it('keeps uploads in the composer and can omit current-page context', () => {
    const submit = vi.fn();
    render(<AiAssistantPanel canAccess currentContext={context} messages={[]} runStatus="idle" onSubmit={submit} onStop={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Deschide UniHub AI' }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['store,value\nA,10'], 'sample.csv', { type: 'text/csv' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByText('sample.csv')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Context/, { selector: 'input' }));
    fireEvent.click(screen.getByRole('button', { name: /Trimite/ }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({
      files: [file],
      includeCurrentView: false,
      currentView: null,
    }));
  });

  it('shows generated attachments and unavailable runtime state', () => {
    render(<AiAssistantPanel
      canAccess
      currentContext={context}
      messages={[{
        id: 'm1', role: 'assistant', text: 'Am terminat raportul.', status: 'complete', createdAt: '2026-09-15T00:00:00Z',
        attachments: [{ id: 'a1', filename: 'raport.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', sizeBytes: 4096, kind: 'output' }],
      }]}
      runStatus="unavailable"
      onSubmit={vi.fn()}
      onStop={vi.fn()}
    />);
    fireEvent.click(screen.getByRole('button', { name: 'Deschide UniHub AI' }));
    expect(screen.getByText('raport.xlsx')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Trimite/ })).toBeDisabled();
  });
});
