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
  'Intrările din read-modelurile reporting se actualizează după un import de vânzări finalizat. Unele KPI-uri derivate pot fi recalculate în browser când UI agregă mai multe luni, dar acea recomputare folosește valorile serverului și nu schimbă freshness-ul datelor sursă.';

const DERIVED_REPORTING_FRESHNESS =
  'Intrările se actualizează odată cu read-modelurile reporting după un import de vânzări finalizat. La selecții multi-lună, UI recalculează această metrică în browser din totalurile sau ponderile primite de la server; recomputarea din browser nu schimbă freshness-ul datelor sursă.';

const LEGACY_YEAR_HISTORY_FRESHNESS =
  'Sursele reporting se actualizează după importul normal de vânzări. Year History poate citi separat historical_monthly_sales sau historical_annual_sales; aceste surse legacy urmează propriile importuri istorice și nu sunt reconstruite de un import normal de vânzări.';

const ORGANIZATION = {
  current:
    'În current_scope, firma/RM/ASM și statusul activ sunt rezolvate din stores; scope-ul managerului folosește ownership-ul organizațional curent.',
  historical:
    'În istoric, dimensiunile organizaționale stocate în reporting_* la import rămân autoritative; comparațiile istorice de perioadă păstrează cohorta de magazine din selecția curentă.',
} as const;

const LEGACY_YEAR_HISTORY_ORGANIZATION = {
  current: ORGANIZATION.current,
  historical:
    'Istoricul modern din reporting_* păstrează dimensiunile organizaționale importate când current_scope este oprit. Year History poate combina însă surse legacy: historical_monthly_sales păstrează firma istorică, dar filtrează RM/ASM prin stores curent; fallback-ul historical_annual_sales păstrează firma istorică fără current_scope, dar folosește de asemenea stores curent pentru RM/ASM. Cu current_scope, ownership-ul curent din stores este folosit explicit.',
} as const;

const TARGET_ORGANIZATION = {
  current: ORGANIZATION.current,
  historical:
    'În History, vânzările păstrează dimensiunile organizaționale istorice din reporting_*, dar target_summary filtrează store_targets prin stores curent pentru firmă/RM/ASM. După mutarea unui magazin, targetul istoric poate urma ownership-ul curent chiar dacă vânzările rămân în ownership-ul istoric.',
} as const;

const REPORTING_EXCLUSIONS = [
  'Cartelele sunt excluse din KPI Retail și raportate separat.',
  'Locațiile de distribuție cu locatie LIKE "TR %" sunt excluse de read-modelul Retail.',
] as const;

const NET_RETURN_NOTE =
  'Retururile cu cantitate negativă reduc valorile nete; numărul bonurilor de retur este urmărit separat.';

const LEGACY_ANNUAL_FALLBACK_LIMITATION =
  'Fallback-ul historical_annual_sales este eligibil numai pentru anii <= 2023, numai fără filtru de agent și numai când niciun rând lunar nu are total_sales > 0 sau total_quantity > 0. project_year_history ascunde rândurile lunare pentru care sales, target și quantity sunt toate <= 0, iar agregatul anual este emis numai dacă total_sales anual > 0; o lună doar cu retururi sau alte valori nepozitive poate astfel dispărea și permite fallback-ul anual.';

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
    sources: [
      'reporting_agent_day.total_sales',
      'reporting_agent_month.total_sales',
      'historical_monthly_sales.total_value',
      'historical_annual_sales.total_value',
    ],
    inclusions: [NET_RETURN_NOTE],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: LEGACY_YEAR_HISTORY_ORGANIZATION,
    freshness: LEGACY_YEAR_HISTORY_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_monthly',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_agg',
      'backend/services/dashboard/history.py::load_history_by_year',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_cartela_does_not_contaminate_retail_totals',
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [
      'Year History poate combina reporting_agent_month cu historical_monthly_sales; historical_annual_sales este un fallback legacy cu condiții suplimentare de eligibilitate.',
      LEGACY_ANNUAL_FALLBACK_LIMITATION,
      'Pe sursele legacy de Year History, firma poate rămâne cea stocată istoric, dar filtrele RM/ASM sunt rezolvate prin stores curent; un magazin mutat poate apărea sub ownership-ul managerial curent.',
    ],
    version: 1,
  },
  {
    id: 'retail.target.value',
    name: 'Target',
    description: 'Ținta de vânzări aferentă selecției pentru luna activă.',
    unit: 'RON',
    precision: 2,
    formula:
      'Dashboard/magazin/RM/ASM: SUM(store_targets.target_value). Agent: agent_targets.target_value dacă există. Regula canonică de business pentru fallback este target_magazin / zile_vânzare_magazin × zile_vânzare_agent; implementarea curentă din _agent_base_query încă împarte egal targetul magazinului la numărul de agenți activi când lipsește agent_targets.',
    granularities: ['dashboard', 'regional', 'asm', 'store', 'agent'],
    aggregation:
      'Aditivă la nivel de magazin/RM/ASM/dashboard. La agent se folosește effective_target, nu se derivează din procentul de realizare.',
    sources: [
      'store_targets.target_value',
      'agent_targets.target_value',
      'reporting_agent_day.site_code',
      'reporting_agent_month',
    ],
    inclusions: [
      'Current Dashboard summary: store_targets contribuie numai pentru site_code-urile prezente în filtered_days din reporting_agent_day pentru selecția Retail curentă.',
      'History/Year History: targeturile sunt însumate direct din store_targets după filtrele disponibile pe stores; nu este necesar ca magazinul să aibă un rând Retail reporting în luna respectivă.',
    ],
    exclusions: [],
    organizationSemantics: TARGET_ORGANIZATION,
    freshness:
      'Țintele sunt citite la request din store_targets/agent_targets și se pot modifica independent de read-modelurile de vânzări.',
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_monthly_history',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_monthly',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: [
      'Regula canonică Retail cere alocarea fallback a targetului agentului proporțional cu selling days; fallback-ul curent al Dashboard este încă egal pe active_agents și este o deviație de implementare, nu formula canonică.',
      'Targetul unui agent poate fi null dacă nu există nici target explicit, nici fallback distribuibil.',
      'În History filtrat pe firmă/RM/ASM, targetul folosește ownership-ul curent din stores, în timp ce vânzările folosesc ownership-ul istoric; pentru magazine mutate cele două scope-uri pot diverge.',
      'În History/Year History, target_summary/month_targets citesc store_targets direct după filtrele de stores și nu cer existența unui rând de vânzări Retail; un target poate contribui chiar dacă magazinul nu are vânzări Retail în lună.',
      'În History/Year History, excluderea de locație Retail pentru locatie LIKE "TR %" nu este reaplicată explicit asupra store_targets; targetul istoric nu trebuie tratat ca fiind limitat strict la cohorta Retail.',
      'În History/Year History, filtrul de agent este păstrat pe vânzări, dar clauzele cu .agent sunt eliminate înainte de construirea query-ului de target. Targetul istoric poate astfel include toate store_targets permise de restul scope-ului, iar dacă agentul este singurul filtru denominatorul poate deveni practic global.',
    ],
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
    organizationSemantics: TARGET_ORGANIZATION,
    freshness:
      'Combină două intrări cu freshness independent: vânzările se schimbă după rebuild-ul reporting, iar targeturile sunt citite la request din store_targets/agent_targets. La selecții multi-lună, UI recalculează procentul în browser din totalurile primite; această recomputare nu schimbă freshness-ul celor două surse.',
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_monthly_history',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_monthly',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: [
      'Nu există un prag vizual global oficial pentru această metrică în V3.',
      'La nivel agent, realizarea moștenește deviația fallback documentată la retail.target.value atunci când lipsește agent_targets.',
      'În History filtrat pe firmă/RM/ASM, numărătorul de vânzări poate folosi ownership istoric iar targetul ownership curent; procentul rezultat moștenește această asimetrie pentru magazine mutate.',
      'În History/Year History, denominatorul de target poate include store_targets pentru magazine fără rând Retail reporting sau locații TR %, astfel încât scope-ul denominatorului poate diferi de scope-ul vânzărilor din numărător.',
      'În History/Year History filtrat pe agent, numărătorul de vânzări respectă filtrul de agent, dar denominatorul de target îl ignoră; procentul poate compara vânzările unui singur agent cu targetul întregului scope rămas sau chiar cu targetul global dacă nu există alte filtre.',
    ],
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
    sources: [
      'reporting_agent_day.total_quantity',
      'reporting_agent_month.total_quantity',
      'historical_monthly_sales.total_qty',
      'historical_annual_sales.total_qty',
    ],
    inclusions: [NET_RETURN_NOTE],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: LEGACY_YEAR_HISTORY_ORGANIZATION,
    freshness: LEGACY_YEAR_HISTORY_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_monthly',
      'backend/repositories/dashboard.py::DashboardRepository.fetch_year_history_agg',
      'backend/services/dashboard/history.py::load_history_by_year',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [
      'Year History poate combina reporting_agent_month.total_quantity cu historical_monthly_sales.total_qty; historical_annual_sales.total_qty este un fallback legacy cu condiții suplimentare de eligibilitate.',
      LEGACY_ANNUAL_FALLBACK_LIMITATION,
      'Pe sursele legacy de Year History, firma poate rămâne cea stocată istoric, dar filtrele RM/ASM sunt rezolvate prin stores curent; un magazin mutat poate apărea sub ownership-ul managerial curent.',
    ],
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
    formula:
      'Current/single-month server: 100 × receipt_2plus_count / receipt_count; null când receipt_count = 0. Monthly History: _monthly_history_sql aplică COALESCE(proc_bon2acc, 0), deci o lună fără bonuri pozitive expune 0% în loc de null.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation:
      'Single-month server și agregarea multi-lună la agent folosesc numărătorul și numitorul brut. Pentru Dashboard/RM/ASM/magazin/comparație perioade multi-lună, frontendul reconstruiește un numărător aproximativ ca (proc_bon2acc rotunjit / 100) × receipt_count pentru fiecare lună și apoi îl însumează.',
    sources: [
      'reporting_agent_day.receipt_2plus_count',
      'reporting_agent_day.receipt_count',
      'reporting_agent_month.receipt_2plus_count',
      'reporting_agent_month.receipt_count',
    ],
    inclusions: ['receipt_2plus_count numără bonurile cu net_quantity >= 2.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: DERIVED_REPORTING_FRESHNESS,
    visualThresholds: [
      { label: 'Critic', maxExclusive: 28 },
      { label: 'Atenție', minInclusive: 28, maxExclusive: 30 },
      { label: 'Solid', minInclusive: 30, maxExclusive: 31 },
      { label: 'Foarte bun', minInclusive: 31 },
    ],
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'src/features/dashboard/DashboardWidgets.tsx::getBon2AccTone',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [
      'În Monthly History, o lună fără bonuri pozitive poate apărea ca 0% din cauza COALESCE și este astfel încadrată în banda vizuală Critic, chiar dacă current summary ar expune null.',
      'În multi-lună pentru Dashboard/RM/ASM/magazin și comparație perioade, reconstruirea pornește din procente deja rotunjite la două zecimale, nu din receipt_2plus_count brut; rezultatul poate diferi de raportul canonic SUM(receipt_2plus_count) / SUM(receipt_count) și poate traversa un prag vizual cu aproximativ 0.01 puncte procentuale.',
    ],
    version: 1,
  },
  {
    id: 'retail.focus.accessory_pct',
    name: 'Focus / accesorii',
    description: 'Ponderea cantității nete de produse Focus în cantitatea netă totală de accesorii.',
    unit: 'percent',
    precision: 2,
    formula:
      'Single-month Dashboard server și comparație perioade: 100 × focus_quantity / total_quantity când total_quantity != 0. Single-month RM/ASM/magazin/agent: procentul este expus numai când total_quantity > 0. În multi-lună, agentul agregă raw acc_focus_qty/acc_qty_realizat; Dashboard/RM/ASM/magazin/comparație perioade reconstruiesc contribuția Focus din procentul lunar rotunjit × cantitatea lunară, iar un procent null este tratat ca zero în frontend.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation:
      'Agent multi-lună recalculează din numărător și numitor brut. Celelalte suprafețe multi-lună folosesc o reconstrucție ponderată din procentul lunar deja rotunjit și cantitatea semnată; procentele null sunt convertite la zero înainte de ponderare.',
    sources: [
      'reporting_agent_day.focus_quantity',
      'reporting_agent_day.total_quantity',
      'reporting_agent_month.focus_quantity',
      'reporting_agent_month.total_quantity',
      'focus_products',
    ],
    inclusions: ['focus_quantity include numai item_code-urile prezente în focus_products și păstrează semnul cantității.'],
    exclusions: REPORTING_EXCLUSIONS,
    organizationSemantics: ORGANIZATION,
    freshness: DERIVED_REPORTING_FRESHNESS,
    visualThresholds: [
      { label: 'Critic', maxExclusive: 6 },
      { label: 'Sub țintă', minInclusive: 6, maxExclusive: 7 },
      { label: 'În target', minInclusive: 7, maxExclusive: 8 },
      { label: 'Foarte bun', minInclusive: 8 },
    ],
    implementationRefs: [
      'backend/services/reporting_refresh_month.py::_REPORTING_MONTH_SQL_5',
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'backend/services/dashboard/query_comparison.py::_fetch_comparison_point',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/DashboardWidgets.tsx::getFocusTone',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: [
      'backend/tests/test_dashboard_summary_integration.py::test_reporting_uses_net_quantity_for_kpis_and_keeps_returns_separate',
    ],
    limitations: [
      'Setul focus_products este o intrare de business și se poate modifica independent de catalog.',
      'Monthly History aplică COALESCE(prc_focus_acc_qty, 0), deci lipsa valorii poate fi expusă ca 0 în loc de null.',
      'Pentru total_quantity negativ, Dashboard summary și comparația de perioade pot produce un procent semnat, în timp ce RM/ASM/magazin/agent returnează null; catalogul documentează comportamentul existent, nu o regulă unificată.',
      'Într-o selecție multi-lună cu luni de semn mixt, RM/ASM/magazin pot avea o lună cu total_quantity <= 0 și prc_focus_acc_qty null; frontendul transformă acel null în 0 dar păstrează cantitatea negativă în denominatorul agregat. Rezultatul poate devia material de la SUM(focus_quantity) / SUM(total_quantity) chiar dacă total_quantity agregat este pozitiv.',
      'Și pe lunile fără null, reconstrucția multi-lună pentru Dashboard/RM/ASM/magazin/comparație perioade pornește din procente Focus deja rotunjite, nu din focus_quantity brut.',
    ],
    version: 1,
  },
  {
    id: 'retail.sales.avg_product_value',
    name: 'Medie produs',
    description: 'Valoarea medie netă per accesoriu net.',
    unit: 'RON',
    precision: 2,
    formula:
      'Dashboard server și comparație perioade: vânzări_nete / accesorii_nete când accesorii_nete != 0. RM/ASM/magazin/agent și agregările multi-lună frontend: formula este expusă numai când accesorii_nete > 0; altfel null.',
    granularities: ['dashboard', 'period-comparison', 'regional', 'asm', 'store', 'agent'],
    aggregation: 'Se recalculează din totalurile agregate; mediile copil nu se mediază simplu.',
    sources: ['retail.sales.net_value', 'retail.accessories.net_quantity'],
    inclusions: ['Moștenește semantica netă a valorii și cantității.'],
    exclusions: [],
    organizationSemantics: ORGANIZATION,
    freshness: DERIVED_REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'backend/services/dashboard/query_comparison.py::_fetch_comparison_point',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_stores.py::_store_stats_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/presenters.ts::aggregateSummary',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: [
      'Monthly History aplică COALESCE(medie_produs, 0), deci lipsa valorii poate fi expusă ca 0 în loc de null.',
      'Pentru accesorii_nete negativ, Dashboard summary și comparația de perioade pot produce o valoare semnată, în timp ce RM/ASM/magazin/agent și agregarea frontend returnează null; catalogul documentează comportamentul existent.',
    ],
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
    freshness: DERIVED_REPORTING_FRESHNESS,
    visualThresholds: null,
    implementationRefs: [
      'backend/repositories/dashboard.py::_summary_sql',
      'backend/repositories/dashboard.py::_monthly_history_sql',
      'backend/services/dashboard/query_comparison.py::_fetch_comparison_point',
      'backend/services/dashboard/query_agents.py::_agent_base_query',
      'backend/services/dashboard/query_managers.py::_regional_base_query',
      'backend/services/dashboard/query_managers.py::_fetch_asm_base_rows',
      'src/features/dashboard/DashboardWidgets.tsx::getStoreDailyAverage',
    ],
    verificationRefs: ['backend/tests/test_dashboard_queries.py'],
    limitations: [
      'Monthly History aplică COALESCE(daily_average, 0), deci lipsa valorii poate fi expusă ca 0 în loc de null.',
      'RM/ASM folosesc suma zilelor-agent, nu numărul de zile calendaristice distincte ale regiunii.',
    ],
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
    freshness: DERIVED_REPORTING_FRESHNESS,
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
    organizationSemantics: {
      current:
        'Subquery-urile de retur folosesc stores curent pentru scope; în current_scope acest lucru urmează ownership-ul organizațional curent.',
      historical:
        'Valoarea materializată aparține lunii/magazinului/agentului istoric, dar subquery-urile de retur filtrează prin stores curent; la nivel regional return_summary grupează explicit după stores.regional curent, nu după regionalul istoric din reporting_agent_month.',
    },
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
    limitations: [
      'Este separat de receipt_count; nu se scade încă o dată din numărul de bonuri pozitive.',
      'Pentru un magazin mutat între regiuni, bonurile retur ale unei luni istorice pot fi atribuite regionalului curent sau pot lipsi din rândul regional istoric; catalogul documentează comportamentul existent și nu îl tratează ca istoric-authoritative.',
    ],
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
