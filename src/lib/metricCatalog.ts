export const METRIC_CATALOG_VERSION = 1 as const;

export type MetricUnit = 'RON' | 'count' | 'percent';
export type MetricGranularity =
  | 'dashboard'
  | 'period-comparison'
  | 'regional'
  | 'asm'
  | 'store'
  | 'agent';

export interface MetricThreshold {
  label: string;
  minInclusive?: number;
  maxExclusive?: number;
}

export interface MetricDefinition {
  id: string;
  name: string;
  description: string;
  unit: MetricUnit;
  precision: number;
  formula: string;
  granularities: readonly MetricGranularity[];
  aggregation: string;
  sources: readonly string[];
  inclusions: readonly string[];
  exclusions: readonly string[];
  organizationSemantics: {
    current: string;
    historical: string;
  };
  freshness: string;
  visualThresholds: readonly MetricThreshold[] | null;
  implementationRefs: readonly string[];
  verificationRefs: readonly string[];
  limitations: readonly string[];
  version: typeof METRIC_CATALOG_VERSION;
}

const REPORTING_FRESHNESS =
  'Se actualizează odată cu read-modelurile de reporting după un import de vânzări finalizat; nu este calculat din browser în timp real.';

const ORGANIZATION = {
  current:
    'În current_scope, firma/RM/ASM și statusul activ sunt rezolvate din stores; scope-ul managerului folosește ownership-ul organizațional curent.',
  historical:
    'În istoric, dimensiunile organizaționale stocate în reporting_* la import rămân autoritative; comparațiile istorice de perioadă păstrează cohorta de magazine din selecția curentă.',
} as const;

const REPORTING_EXCLUSIONS = [
  'Cartelele sunt excluse din KPI Retail și raportate separat.',
  'Locațiile de distribuție cu locatie LIKE "TR %" sunt excluse de read-modelul Retail.',
] as const;

const NET_RETURN_NOTE =
  'Retururile cu cantitate negativă reduc valorile nete; numărul bonurilor de retur este urmărit separat.';

export const METRIC_CATALOG = [
  {
    id: 'retail.sales.net_value',
    name: 'Vânzări nete',
    description: 'Valoarea netă Retail a accesoriilor pentru selecția și perioada active.',
    unit: 'RON',
    precision: 2,
    formula: 'SUM(total_sales)',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Aditivă prin însumarea valorii nete la granularitatea selectată.',
    sources: ['reporting_agent_day.total_sales', 'reporting_agent_month.total_sales'],
    inclusions: [NET_RETURN_NOTE],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_cartela_does_not_contaminate_retail_totals',
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [],
    version: 1,
  },
  {
    id: 'retail.target.value',
    name: 'Target',
    description: 'Ținta de vânzări aferentă selecției pentru luna activă.',
    unit: 'RON',
    precision: 2,
    formula:
      'Dashboard/magazin/RM/ASM: SUM(store_targets.target_value). Agent: agent_targets.target_value dacă există; altfel targetul magazinului / numărul de agenți activi.',
    granularities: ['dashboard', 'regional', 'asm', 'store', 'agent'],
    aggregation:
      'Aditivă la nivel de magazin/RM/ASM/dashboard. La agent se folosește effective_target, nu se derivează din procentul de realizare.',
    sources: ['store_targets.target_value', 'agent_targets.target_value', 'reporting_agent_month'],
    inclusions: ['Sunt incluse numai magazinele prezente în scope-ul Retail al selecției.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: 'Țintele sunt lunare; disponibilitatea lor urmează încărcarea/configurarea targeturilor pentru luna activă.',
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: ['Targetul unui agent poate fi null dacă nu există nici target explicit, nici fallback distribuibil.'],
    version: 1,
  },
  {
    id: 'retail.target.attainment_pct',
    name: 'Realizare target',
    description: 'Procentul de realizare a targetului pentru selecția curentă.',
    unit: 'percent',
    precision: 2,
    formula: '100 × vânzări_nete / target, dacă target > 0; altfel null.',
    granularities: ['dashboard', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Se recalculează din totalurile agregate; procentele copil nu se însumează și nu se mediază simplu.',
    sources: ['retail.sales.net_value', 'retail.target.value'],
    inclusions: ['Moștenește scope-ul și regulile celor două metrici sursă.'],
    exclusions: [],
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: ['Nu există un prag vizual global oficial pentru această metrică în V3.'],
    version: 1,
  },
  {
    id: 'retail.accessories.net_quantity',
    name: 'Accesorii nete',
    description: 'Cantitatea netă de accesorii Retail pentru selecția activă.',
    unit: 'count',
    precision: 0,
    formula: 'SUM(total_quantity)',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Aditivă.',
    sources: ['reporting_agent_day.total_quantity', 'reporting_agent_month.total_quantity'],
    inclusions: [NET_RETURN_NOTE],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [],
    version: 1,
  },
  {
    id: 'retail.receipts.positive_count',
    name: 'Bonuri Retail',
    description: 'Numărul canonic de bonuri Retail cu cantitate netă pozitivă.',
    unit: 'count',
    precision: 0,
    formula:
      'La read-modelul zilnic: COUNT(DISTINCT bon_nr) unde cantitatea netă a bonului > 0; valorile zilnice sunt apoi aditive în reporting_agent_month.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Aditivă peste grain-ul zi × magazin × agent; aceeași valoare bon_nr pe altă zi/magazin/agent rămâne distinctă.',
    sources: ['reporting_agent_day.receipt_count', 'reporting_agent_month.receipt_count'],
    inclusions: ['Numai bonurile a căror cantitate netă Retail este > 0.'],
    exclusions: [...REPORTING_EXCLUSIONS, 'Bonurile exclusiv de retur nu intră în receipt_count.'],
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_3',
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/services/receipt_identity.py::canonical_receipt_identity_sql',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
      'backend/tests/test_h03_return_receipt_identity_integration.py',
    ],
    limitations: ['Nu reprezintă numărul brut de bon_nr din sales_transactions.'],
    version: 1,
  },
  {
    id: 'retail.receipts.bon2acc_pct',
    name: 'Bon2Acc',
    description: 'Ponderea bonurilor Retail cu cel puțin două accesorii nete.',
    unit: 'percent',
    precision: 2,
    formula: '100 × receipt_2plus_count / receipt_count; null când receipt_count = 0.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Se recalculează ponderat din numărător și numitor; procentele copil nu se mediază simplu.',
    sources: ['reporting_agent_day.receipt_2plus_count', 'reporting_agent_day.receipt_count'],
    inclusions: ['receipt_2plus_count numără bonurile cu net_quantity >= 2.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: [
      { label: 'Critic', maxExclusive: 28 },
      { label: 'Atenție', minInclusive: 28, maxExclusive: 30 },
      { label: 'Solid', minInclusive: 30, maxExclusive: 31 },
      { label: 'Foarte bun', minInclusive: 31 },
    ],
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'src/features/dashboard/DashboardWidgets.tsx::getBon2AccTone',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [],
    version: 1,
  },
  {
    id: 'retail.focus.accessory_pct',
    name: 'Focus / accesorii',
    description: 'Ponderea cantității nete de produse Focus în cantitatea netă totală de accesorii.',
    unit: 'percent',
    precision: 2,
    formula: '100 × focus_quantity / total_quantity; null când total_quantity = 0.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Se recalculează ponderat din cantități; procentele copil nu se mediază simplu.',
    sources: ['reporting_agent_day.focus_quantity', 'reporting_agent_day.total_quantity', 'focus_products'],
    inclusions: ['focus_quantity include numai item_code-urile prezente în focus_products și păstrează semnul cantității.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: [
      { label: 'Critic', maxExclusive: 6 },
      { label: 'Sub țintă', minInclusive: 6, maxExclusive: 7 },
      { label: 'În target', minInclusive: 7, maxExclusive: 8 },
      { label: 'Foarte bun', minInclusive: 8 },
    ],
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'src/features/dashboard/DashboardWidgets.tsx::getFocusTone',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: ['Setul focus_products este o intrare de business și se poate modifica independent de catalog.'],
    version: 1,
  },
  {
    id: 'retail.sales.avg_product_value',
    name: 'Medie produs',
    description: 'Valoarea medie netă per accesoriu net.',
    unit: 'RON',
    precision: 2,
    formula: 'vânzări_nete / accesorii_nete; null când accesorii_nete <= 0.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Se recalculează din totalurile agregate; mediile copil nu se mediază simplu.',
    sources: ['retail.sales.net_value', 'retail.accessories.net_quantity'],
    inclusions: ['Moștenește semantica netă a valorii și cantității.'],
    exclusions: [],
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: ['Dacă net quantity este zero sau negativ, metrica nu are sens și rămâne null.'],
    version: 1,
  },
  {
    id: 'retail.sales.daily_average',
    name: 'Medie zilnică',
    description: 'Vânzarea medie pe zi, cu denominatorul explicit dependent de granularitate.',
    unit: 'RON',
    precision: 2,
    formula:
      'Dashboard/comparație/magazin: vânzări / zile de vânzare distincte. Agent: vânzări / working_days agent. RM/ASM: vânzări / suma working_days ale agenților.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Nu este aditivă; se recalculează folosind denominatorul granularității respective.',
    sources: ['reporting_agent_day.sale_date', 'reporting_agent_month.working_days', 'retail.sales.net_value'],
    inclusions: ['Numără numai zilele prezente în read-modelul Retail pentru grain-ul relevant.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/services/dashboard/query_comparison.py::_fetch_comparison_point',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/DashboardWidgets.tsx::getStoreDailyAverage',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: ['RM/ASM folosesc suma zilelor-agent, nu numărul de zile calendaristice distincte ale regiunii.'],
    version: 1,
  },
  {
    id: 'retail.sales.avg_receipt_value',
    name: 'Valoare medie bon',
    description: 'Valoarea netă medie pentru un bon Retail pozitiv.',
    unit: 'RON',
    precision: 2,
    formula: 'vânzări_nete / bonuri_Retail; null/0 în UI când bonuri_Retail = 0.',
    granularities: ['dashboard', 'period-comparison'],
    aggregation: 'Se recalculează din totalurile agregate.',
    sources: ['retail.sales.net_value', 'retail.receipts.positive_count'],
    inclusions: ['În comparația de perioade formula este calculată server-side; Overview o afișează din aceleași două totaluri canonice.'],
    exclusions: [],
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/services/dashboard/query_comparison.py::_fetch_comparison_point',
      'src/features/dashboard/CurrentDashboardSections.tsx::CurrentSummary',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: ['Nu există în prezent ca field separat în DashboardSummary; Overview îl derivează local din totalurile serverului.'],
    version: 1,
  },
  {
    id: 'retail.receipts.return_count',
    name: 'Bonuri retur',
    description: 'Numărul materializat de bonuri cu cel puțin o poziție Retail cu cantitate negativă.',
    unit: 'count',
    precision: 0,
    formula:
      'La grain-ul zi × magazin × agent: COUNT(DISTINCT bon_nr) pentru quantity < 0, non-cartela, non-TR și bon_nr nenul; luna este suma valorilor zilnice.',
    granularities: ['regional', 'store', 'agent'],
    aggregation: 'Aditivă din reporting_agent_day în reporting_agent_month și apoi peste grain-urile de raportare.',
    sources: ['reporting_agent_day.return_receipt_count', 'reporting_agent_month.return_receipt_count'],
    inclusions: ['Același bon_nr pe altă zi, magazin sau agent rămâne o identitate distinctă.'],
    exclusions: [...REPORTING_EXCLUSIONS, 'Pozițiile cu quantity >= 0 nu contribuie.'],
    organizationSemantics: ORGANIZATION,
    freshness: REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/db/migrations/074_v3_reporting_return_receipt_count.sql',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
    ],
    verificationRefs: [
      'backend/tests/test_lot23_return_read_model_materialization.py',
      'backend/tests/test_v3_return_read_model_parity_characterization.py',
    ],
    limitations: ['Este separat de receipt_count; nu se scade încă o dată din numărul de bonuri pozitive.'],
    version: 1,
  },
] as const satisfies readonly MetricDefinition[];

export type MetricId = (typeof METRIC_CATALOG)[number]['id'];

export function getMetricDefinition(id: string): MetricDefinition | undefined {
  return METRIC_CATALOG.find((metric) => metric.id === id);
}

export function searchMetricCatalog(query: string): readonly MetricDefinition[] {
  const normalized = query.trim().toLocaleLowerCase('ro-RO');
  if (!normalized) return METRIC_CATALOG;
  return METRIC_CATALOG.filter((metric) =>
    [
      metric.id,
      metric.name,
      metric.description,
      metric.formula,
      metric.sources.join(' '),
      metric.granularities.join(' '),
    ]
      .join(' ')
      .toLocaleLowerCase('ro-RO')
      .includes(normalized),
  );
}
