export type QueryKeyParams = Readonly<object>;

export const queryKeys = {
  dashboard: {
    all: ['dashboard'] as const,
    current: (month: string, query: QueryKeyParams) =>
      ['dashboard', 'current', month, query] as const,
    history: (month: string, query: QueryKeyParams) =>
      ['dashboard', 'history', month, query] as const,
    historyDetail: (months: readonly string[], query: QueryKeyParams) =>
      ['dashboard', 'history-detail', [...months], query] as const,
    currentHistory: (month: string, query: QueryKeyParams) =>
      ['dashboard', 'current-history', month, query] as const,
    yearHistory: (year: number, query: QueryKeyParams) =>
      ['dashboard', 'year-history', year, query] as const,
  },
  aiForecast: {
    current: (month: string, query: QueryKeyParams) =>
      ['ai-forecast', 'current', month, query] as const,
    rolling12: (month: string, query: QueryKeyParams) =>
      ['ai-forecast', 'rolling-12', month, query] as const,
  },
  campaigns: {
    all: ['campaigns'] as const,
    current: (
      section: string,
      month: string,
      promotionKey: string,
      query: QueryKeyParams,
    ) => ['campaigns', 'current', section, month, promotionKey, query] as const,
    history: (month: string, query: QueryKeyParams) =>
      ['campaigns', 'history', month, query] as const,
    contests: (month: string) => ['campaigns', 'contests', month] as const,
  },
  agents: {
    all: ['agents'] as const,
    overview: (month: string, query: QueryKeyParams) =>
      ['agents', 'overview', month, query] as const,
    evaluation: (query: QueryKeyParams) =>
      ['agents', 'evaluation', query] as const,
    evaluationV2: (query: QueryKeyParams) =>
      ['agents', 'evaluation-v2', query] as const,
    profile: (agent: string, month: string) =>
      ['agents', 'profile', agent, month] as const,
    history: (agent: string) => ['agents', 'history', agent] as const,
    movement: (query: QueryKeyParams) =>
      ['agents', 'movement', query] as const,
    coverage: (query: QueryKeyParams) =>
      ['agents', 'coverage', query] as const,
    list: (query: QueryKeyParams) => ['agents', 'list', query] as const,
  },
  grile: {
    all: ['grile'] as const,
    overview: (month: string) => ['grile', 'overview', month] as const,
    runs: (month: string) => ['grile', 'runs', month] as const,
    monthlyOperations: (month: string) =>
      ['grile', 'monthly-operations', month] as const,
  },
  settings: {
    identity: (identityKey: string) => ['settings', identityKey] as const,
    imports: (identityKey: string) => ['settings', identityKey, 'imports'] as const,
    exports: (query: QueryKeyParams) => ['settings', 'exports', query] as const,
    exportCatalog: (identityKey: string) =>
      ['settings', identityKey, 'export-catalog'] as const,
    exportFilters: (identityKey: string, month: string) =>
      ['settings', identityKey, 'export-filters', month] as const,
    exportOperation: (identityKey: string, operationId: number) =>
      ['settings', identityKey, 'export-operation', operationId] as const,
    exportResumable: (identityKey: string) =>
      ['settings', identityKey, 'export-operation', 'resumable'] as const,
  },
  visits: {
    report: (month: string) => ['visits', 'report', month] as const,
    tree: (month: string) => ['visits', 'tree', month] as const,
    detail: (visitId: string) => ['visits', 'detail', visitId] as const,
    activeStores: (month: string) => ['visits', 'active-stores', month] as const,
  },
} as const;
