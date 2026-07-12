import { useQuery, type QueryObserverResult, type UseQueryOptions } from '@tanstack/react-query';

import { getPnlPermissions, type PnlPermissions } from '../api/storePnl';

export type PnlCapabilityState = {
  permissionEnabled: boolean;
  permissionPending: boolean;
  hasPnlAccess: boolean;
};

export function pnlCapabilityQueryOptions(
  verifiedSubject: string | undefined,
  permissionEnabled: boolean,
  queryFn: () => Promise<PnlPermissions> = () => getPnlPermissions(),
): UseQueryOptions<PnlPermissions, Error> {
  return {
    queryKey: ['store-pnl-permissions', verifiedSubject],
    queryFn,
    enabled: permissionEnabled,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: 'always',
    retry: false,
  };
}

export function pnlCapabilityState(
  hasManagementAccess: boolean,
  permissionEnabled: boolean,
  query: Pick<QueryObserverResult<PnlPermissions, Error>, 'isSuccess' | 'isFetchedAfterMount' | 'isFetching' | 'isError' | 'isRefetchError' | 'data'>,
): PnlCapabilityState {
  const permissionPending = permissionEnabled && (!query.isFetchedAfterMount || query.isFetching);
  return {
    permissionEnabled,
    permissionPending,
    hasPnlAccess: hasManagementAccess
      && permissionEnabled
      && query.isSuccess
      && query.isFetchedAfterMount
      && !query.isFetching
      && !query.isError
      && !query.isRefetchError
      && query.data?.can_view === true,
  };
}

export function usePnlCapability(
  isAuthenticated: boolean,
  verifiedSubject: string | undefined,
  hasManagementAccess: boolean,
  accessToken: string | undefined,
): PnlCapabilityState {
  const validSubject = typeof verifiedSubject === 'string' && verifiedSubject.trim()
    ? verifiedSubject
    : undefined;
  const permissionEnabled = isAuthenticated && Boolean(validSubject);
  const query = useQuery(
    pnlCapabilityQueryOptions(
      validSubject,
      permissionEnabled,
      () => getPnlPermissions(accessToken),
    ),
  );
  return pnlCapabilityState(hasManagementAccess, permissionEnabled, query);
}
