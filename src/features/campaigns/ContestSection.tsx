import { Gift, Medal, Trophy } from "lucide-react";
import { ExportTableButton } from "../../components/ExportTableButton";
import { TableHeaderCell } from "../../components/common/TableHeader";
import type { ContestResponse } from "../../api/generated/runtime-types";
import { formatInt } from "../../lib/formatters";
import {
  CampaignMonthBar,
  ContestSelector,
  EmptyCard,
} from "./CampaignControls";

export function ContestSection({
  contests,
  selectedContest,
  month,
  months,
  currentMonth,
  onMonthChange,
  onSelect,
}: {
  contests: ContestResponse[];
  selectedContest: ContestResponse | null;
  month: string;
  months: string[];
  currentMonth: string;
  onMonthChange: (month: string) => void;
  onSelect: (key: string) => void;
}) {
  return (
    <>
      <CampaignMonthBar
        title="Concurs"
        icon={Trophy}
        months={months}
        value={month}
        onChange={onMonthChange}
        currentMonth={currentMonth}
      />
      {contests.length ? (
        <div className="space-y-3">
          <ContestSelector
            contests={contests}
            selectedKey={selectedContest?.key ?? ""}
            onSelect={onSelect}
          />
          {selectedContest && <ContestView contest={selectedContest} />}
        </div>
      ) : (
        <EmptyCard message={`Nu exista concurs activ in ${month}.`} />
      )}
    </>
  );
}

function ContestView({ contest }: { contest: ContestResponse }) {
  return (
    <>
      <div className="glass rounded-4xl border border-amber-100 bg-linear-to-br from-amber-50 via-white to-white p-4 dark:border-amber-900/30 dark:from-amber-950/20 dark:via-slate-900 dark:to-slate-900">
        <div className="mb-2 flex items-center gap-2 text-amber-600 dark:text-amber-400">
          <Trophy size={16} />
          <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
            Concurs
          </span>
        </div>
        <h4 className="text-base font-black tracking-tight">{contest.title}</h4>
        {contest.scope_label && (
          <p className="mt-1 text-xs font-bold text-amber-700 dark:text-amber-300">
            {contest.scope_label}
          </p>
        )}
        {contest.subtitle && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            {contest.subtitle}
          </p>
        )}
        <p className="mt-1 text-[11px] text-slate-400">
          {contest.start_date} – {contest.end_date} ·{" "}
          {formatInt(contest.store_count)} magazine
        </p>
        {contest.rules.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {contest.rules.map((rule) => (
              <span
                key={rule.type}
                className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
              >
                {rule.label} = {rule.points}p
              </span>
            ))}
          </div>
        )}
      </div>
      {contest.prizes.length > 0 && (
        <div className="glass rounded-3xl p-4">
          <div className="mb-2 flex items-center gap-2 text-amber-600 dark:text-amber-400">
            <Gift size={16} />
            <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
              Premii
            </span>
          </div>
          <div className="space-y-1">
            {contest.prizes.map((prize) => (
              <div
                key={`${prize.rank_from}-${prize.rank_to}`}
                className="flex items-center justify-between rounded-xl bg-amber-50/60 px-3 py-1.5 text-xs dark:bg-amber-900/10"
              >
                <span className="font-bold text-slate-500">
                  {prize.rank_from === prize.rank_to
                    ? `Locul ${prize.rank_from}`
                    : `Locurile ${prize.rank_from}–${prize.rank_to}`}
                </span>
                <span className="font-black text-amber-700 dark:text-amber-300">
                  {prize.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <ContestLeaderboard contest={contest} />
    </>
  );
}

function ContestLeaderboard({ contest }: { contest: ContestResponse }) {
  return (
    <div className="glass rounded-4xl border border-indigo-100 bg-linear-to-br from-indigo-50 via-white to-white p-4 dark:border-indigo-900/30 dark:from-indigo-950/20 dark:via-slate-900 dark:to-slate-900">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400">
          <Trophy size={16} />
          <span className="text-[11px] font-bold uppercase tracking-[0.22em]">
            Clasament agenti
          </span>
        </div>
        <ExportTableButton
          filename={`focus-concurs-${contest.month}-${contest.key}`}
          sheetName="Clasament agenti"
          rows={contest.leaderboard}
          columns={[
            { header: "#", value: (row) => row.rank, format: "integer" },
            { header: "Agent", value: (row) => row.agent },
            { header: "Magazin", value: (row) => row.store_name },
            { header: "Firma", value: (row) => row.firma },
            {
              header: "Focus",
              value: (row) => row.focus_points,
              format: "integer",
            },
            {
              header: "Promo",
              value: (row) => row.promo_points,
              format: "integer",
            },
            {
              header: ">150",
              value: (row) => row.price_points,
              format: "integer",
            },
            {
              header: "Total",
              value: (row) => row.total_points,
              format: "integer",
            },
            { header: "Premiu", value: (row) => row.prize },
          ]}
        />
      </div>
      {contest.leaderboard.length === 0 ? (
        <div className="rounded-2xl bg-slate-50 p-4 text-xs font-semibold text-slate-500 dark:bg-slate-800/60">
          Nu exista inca vanzari punctate in {contest.month}.
        </div>
      ) : (
        <div
          className="max-h-[480px] overflow-y-auto rounded-xl"
          style={{
            scrollbarWidth: "thin",
            scrollbarColor: "#c7d2fe transparent",
          }}
        >
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {[
                  "#",
                  "Agent",
                  "Focus",
                  "Promo",
                  ">150",
                  "Total",
                  "Premiu",
                ].map((label, index) => (
                  <TableHeaderCell
                    key={label}
                    align={index >= 2 && index <= 5 ? "right" : "left"}
                    className="sticky top-0 z-10 bg-indigo-50/90 backdrop-blur-sm dark:bg-indigo-950/70"
                  >
                    {label}
                  </TableHeaderCell>
                ))}
              </tr>
            </thead>
            <tbody>
              {contest.leaderboard.map((row) => (
                <tr
                  key={row.agent}
                  className={
                    row.prize
                      ? "bg-amber-50/50 dark:bg-amber-900/10"
                      : row.rank % 2 === 0
                        ? "bg-indigo-50/30 dark:bg-indigo-900/10"
                        : ""
                  }
                >
                  <td className="px-2 py-1.5">
                    <span
                      className={`font-bold ${row.rank <= 3 ? "text-amber-500" : "text-slate-400"}`}
                    >
                      {row.rank}
                    </span>
                  </td>
                  <td className="px-2 py-1.5">
                    <span className="truncate font-semibold" title={row.agent}>
                      {row.agent}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-500">
                    {formatInt(row.focus_points)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-500">
                    {formatInt(row.promo_points)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-500">
                    {formatInt(row.price_points)}
                  </td>
                  <td className="px-2 py-1.5 text-right font-black text-indigo-600">
                    {formatInt(row.total_points)}
                  </td>
                  <td className="px-2 py-1.5">
                    {row.prize ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                        <Medal size={11} />
                        {row.prize}
                      </span>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
