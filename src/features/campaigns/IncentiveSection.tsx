import { Gift } from "lucide-react";
import { IncentiveDesktopDashboard } from "../../components/IncentiveDesktopDashboard";
import type { CampaignsPromotionsResponse } from "../../api/generated/runtime-types";
import { CampaignMonthBar } from "./CampaignControls";
import { IncentiveCategoryCard, IncentiveCard } from "./IncentiveSummary";
import { IncentiveAgentsTable, IncentiveStoresTable } from "./IncentiveTables";

export function IncentiveSection({
  data,
  month,
  months,
  currentMonth,
  onMonthChange,
}: {
  data: CampaignsPromotionsResponse | null;
  month: string;
  months: string[];
  currentMonth: string;
  onMonthChange: (month: string) => void;
}) {
  return (
    <>
      <div className="lg:hidden">
        <CampaignMonthBar
          title="Incentive"
          icon={Gift}
          months={months}
          value={month}
          onChange={onMonthChange}
          currentMonth={currentMonth}
        />
      </div>
      {data?.incentive_calculation_status === "invalid" ? (
        <div
          role="alert"
          className="glass rounded-3xl border border-rose-200 bg-rose-50/70 p-4 text-sm font-semibold text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200"
        >
          {data.calculation_warnings[0] ||
            "Calculul Incentive este indisponibil deoarece excluderile Promo nu au putut fi validate complet."}
        </div>
      ) : (
        <>
          <div className="lg:hidden">
            <IncentiveCard promoData={data} />
          </div>
          <IncentiveDesktopDashboard promoData={data} month={month} />
          <div className="grid gap-3 xl:grid-cols-2">
            {data && data.top_agents.length > 0 && (
              <IncentiveAgentsTable rows={data.top_agents} month={month} />
            )}
            {data && data.top_stores.length > 0 && (
              <IncentiveStoresTable rows={data.top_stores} month={month} />
            )}
          </div>
          <div className="lg:hidden">
            <IncentiveCategoryCard promoData={data} month={month} />
          </div>
        </>
      )}
    </>
  );
}
