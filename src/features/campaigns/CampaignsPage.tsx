import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { IncentiveDesktopHeader } from "../../components/IncentiveDesktopDashboard";
import type { AppFilters } from "../../lib/appFilters";
import { PageHeader } from "../../components/common/DesktopLayout";
import {
  SegmentedTabs,
  type SegmentedTabOption,
} from "../../components/common/SegmentedTabs";
import {
  ErrorCard,
  LoadingCard,
} from "../../components/common/DataDisplay";
import { ContestSection } from "./ContestSection";
import { FocusSection } from "./FocusSection";
import { IncentiveSection } from "./IncentiveSection";
import { PremiumGlassFocusSection } from "./PremiumView";
import { PromoSection } from "./PromoSection";
import type { CampaignSection } from "./types";
import { useCampaignsData } from "./useCampaignsData";

export type { CampaignSection } from "./types";

export interface CampaignsProps {
  currentMonth: string;
  months: string[];
  filters: AppFilters;
  preferredSection: CampaignSection;
  onSectionChange: (section: CampaignSection) => void;
  onFilterMonthChange?: (month: string) => void;
}

const SECTION_TABS: SegmentedTabOption<CampaignSection>[] = [
  { value: "incentive", label: "Incentive" },
  { value: "promo", label: "Promo" },
  { value: "concurs", label: "Concurs" },
  { value: "premium", label: "Folii premium" },
  { value: "focus", label: "Focus" },
];

type CampaignData = ReturnType<typeof useCampaignsData>;

function campaignLoadingLabel(section: CampaignSection): string {
  if (section === "promo") return "Se incarca promotia...";
  if (section === "incentive") return "Se incarca incentive-ul...";
  if (section === "premium") return "Se incarca analiza foliilor premium...";
  return "Se incarca datele de focus...";
}

function CampaignContent({ activeSection, data, months }: { activeSection: CampaignSection; data: CampaignData; months: string[] }) {
  const selectedContest = data.contests.find((contest) => contest.key === data.selectedContestKey) ?? data.contests[0] ?? null;
  if (activeSection === "concurs") {
    if (data.contestLoading) return <LoadingCard label="Se incarca concursul..." />;
    if (data.contestError) return <ErrorCard message={data.contestError} onRetry={() => void data.refetchContests()} />;
    return <ContestSection contests={data.contests} selectedContest={selectedContest} month={data.promoMonth} months={months} currentMonth={data.latestMonth} onMonthChange={data.setPromoMonth} onSelect={data.setSelectedContestKey} />;
  }
  if (data.loading) return <LoadingCard label={campaignLoadingLabel(activeSection)} />;
  if (data.currentError) return <ErrorCard message={data.currentError} onRetry={() => void data.refetchCurrent()} />;
  if (activeSection === "promo") {
    return <PromoSection data={data.promoData} month={data.promoMonth} months={months} currentMonth={data.latestMonth} selectedPromotionKey={data.selectedPromotionKey} onMonthChange={data.setPromoMonth} onPromotionChange={data.setSelectedPromotionKey} />;
  }
  if (activeSection === "incentive") {
    return <IncentiveSection data={data.promoData} month={data.promoMonth} months={months} currentMonth={data.latestMonth} onMonthChange={data.setPromoMonth} />;
  }
  if (activeSection === "premium") {
    return <><PremiumMonthSelector month={data.promoMonth} months={months} currentMonth={data.latestMonth} onChange={data.setPromoMonth} /><PremiumGlassFocusSection analysis={data.premiumGlass} surfaceMode={data.premiumSurfaceMode} onSurfaceModeChange={data.setPremiumSurfaceMode} /></>;
  }
  return <FocusSection snapshot={data.snapshot} history={data.focusHistory} historyMonth={data.historyMonth} month={data.promoMonth} months={months} currentMonth={data.latestMonth} loading={data.historyLoading} error={data.historyError} onHistoryMonthChange={data.setHistoryMonth} onMonthChange={data.setPromoMonth} onRetry={() => void data.refetchHistory()} />;
}

function CampaignDesktopHeader({ activeSection, data, months }: { activeSection: CampaignSection; data: CampaignData; months: string[] }) {
  if (activeSection !== "incentive" && activeSection !== "promo") return null;
  const promo = activeSection === "promo";
  return (
    <IncentiveDesktopHeader
      promoData={data.promoData} months={months} value={data.promoMonth} onChange={data.setPromoMonth} currentMonth={data.latestMonth}
      {...(promo ? { sectionLabel: "Promo", title: data.promoData?.promo_title || "Promo", description: data.promoData?.promo_description || "Mecanismul promo activ și performanța curentă." } : {})}
    />
  );
}

export function CampaignsPage({
  currentMonth,
  months,
  filters,
  preferredSection,
  onSectionChange,
  onFilterMonthChange,
}: CampaignsProps) {
  const [activeSection, setActiveSection] =
    useState<CampaignSection>(preferredSection);
  const data = useCampaignsData({
    currentMonth,
    months,
    filters,
    activeSection,
    onFilterMonthChange,
  });
  useEffect(() => {
    setActiveSection(preferredSection);
  }, [preferredSection]);
  useEffect(() => {
    onSectionChange(activeSection);
  }, [activeSection, onSectionChange]);

  return (
    <div className="mx-auto max-w-6xl space-y-3 p-3 pb-24 pt-2 lg:max-w-none lg:px-6 lg:pb-6 lg:pt-4">
      <PageHeader
        className="lg:hidden"
        title="Focus"
        description={
          <>
            Incentive, promo, concurs si folii premium folosesc luna{" "}
            {data.promoMonth}; istoricul focus se analizeaza separat.
          </>
        }
      />
      <SegmentedTabs<CampaignSection>
        ariaLabel="Sectiuni Focus"
        className="glass"
        options={SECTION_TABS}
        value={activeSection}
        onChange={setActiveSection}
      />
      <CampaignDesktopHeader activeSection={activeSection} data={data} months={months} />
      <CampaignContent activeSection={activeSection} data={data} months={months} />
    </div>
  );
}

function PremiumMonthSelector({
  month,
  months,
  currentMonth,
  onChange,
}: {
  month: string;
  months: string[];
  currentMonth: string;
  onChange: (month: string) => void;
}) {
  return (
    <div className="glass flex items-center justify-between rounded-3xl p-3">
      <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400">
        <Sparkles size={16} />
        <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
          Folii premium
        </span>
      </div>
      <select
        value={month}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs font-bold text-amber-700 dark:border-amber-800 dark:bg-slate-800 dark:text-amber-300"
      >
        {months.map((candidate) => (
          <option key={candidate} value={candidate}>
            {candidate}
            {candidate === currentMonth ? " (curent)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Stable feature facade for lazy loaders and direct feature imports. */
export { CampaignsPage as Campaigns };
export default CampaignsPage;
