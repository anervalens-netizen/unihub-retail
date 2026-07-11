import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { pnlCapabilityQueryOptions, pnlCapabilityState } from './usePnlCapability';

const makeClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

async function fetchResult(
  client: QueryClient,
  subject: string,
  queryFn: () => Promise<{ can_view: boolean }>,
) {
  const observer = new QueryObserver(client, pnlCapabilityQueryOptions(subject, true, queryFn));
  const unsubscribe = observer.subscribe(() => undefined);
  await observer.refetch();
  const result = observer.getCurrentResult();
  unsubscribe();
  return result;
}

describe('P&L capability query', () => {
  it('uses strict query overrides and grants only validated current success', async () => {
    const client = makeClient();
    const queryFn = vi.fn().mockResolvedValue({ can_view: true });
    const result = await fetchResult(client, 'subject-a', queryFn);
    expect(pnlCapabilityQueryOptions('subject-a', true, queryFn)).toMatchObject({ staleTime: 0, gcTime: 0, refetchOnMount: 'always', retry: false });
    expect(pnlCapabilityState(true, true, result).hasPnlAccess).toBe(true);
  });

  it('fails closed for initial error and missing subject without pending forever', async () => {
    const result = await fetchResult(makeClient(), 'subject-a', vi.fn().mockRejectedValue(new Error('denied')));
    expect(pnlCapabilityState(true, true, result)).toMatchObject({ permissionPending: false, hasPnlAccess: false });
    const disabled = pnlCapabilityState(true, false, { ...result, isFetching: false });
    expect(disabled).toMatchObject({ permissionEnabled: false, permissionPending: false, hasPnlAccess: false });
  });

  it('does not grant cached true before a current fetch and blocks a refetch error', async () => {
    const client = makeClient();
    client.setQueryData(['store-pnl-permissions', 'subject-a'], { can_view: true });
    const observer = new QueryObserver(client, pnlCapabilityQueryOptions('subject-a', true, vi.fn().mockRejectedValue(new Error('denied'))));
    const cached = observer.getCurrentResult();
    expect(pnlCapabilityState(true, true, cached).hasPnlAccess).toBe(false);
    const unsubscribe = observer.subscribe(() => undefined);
    await observer.refetch();
    const failed = observer.getCurrentResult();
    unsubscribe();
    expect(failed.data).toEqual({ can_view: true });
    expect(pnlCapabilityState(true, true, failed)).toMatchObject({ permissionPending: false, hasPnlAccess: false });
  });

  it('isolates subjects and revalidates a same-subject remount', async () => {
    const client = makeClient();
    const first = vi.fn().mockResolvedValue({ can_view: true });
    expect(pnlCapabilityState(true, true, await fetchResult(client, 'subject-a', first)).hasPnlAccess).toBe(true);
    const second = vi.fn().mockResolvedValue({ can_view: false });
    expect(pnlCapabilityState(true, true, await fetchResult(client, 'subject-b', second)).hasPnlAccess).toBe(false);
    const sameSubject = vi.fn().mockResolvedValue({ can_view: false });
    expect(pnlCapabilityState(true, true, await fetchResult(client, 'subject-a', sameSubject)).hasPnlAccess).toBe(false);
    expect(sameSubject).toHaveBeenCalled();
  });
});
