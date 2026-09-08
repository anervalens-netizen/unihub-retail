import { Fragment } from 'react';
import type { CalendarData, CalendarStore } from '../../api/grileCalendar';
import { monthDays } from './calendarModel';

export function Attendance({ data, store }: { data: CalendarData; store: CalendarStore }) {
  const days = data.attendance_days?.filter(d => d.site_code === store.site_code) ?? [];
  const totals = data.attendance_by_store?.[store.site_code] ?? [];
  const codes = [...new Set([...data.roster.filter(r => r.home_site_code === store.site_code).map(r => r.agent_code), ...days.map(d => d.agent_code)])].sort();
  const { dates } = monthDays(data.month);
  return <div><p className="mb-3 text-sm">Pontaj provizoriu · ore la locația efectivă · CO = concediu. Numele vor apărea după confirmarea identității; momentan folosim codul agentului.</p>
    <div className="overflow-x-auto"><table className="w-full border-collapse text-center text-sm"><thead><tr><th className="min-w-44 border p-2">Cod agent</th>{dates.map(date => <th key={date} className="border p-2">{Number(date.slice(-2))}</th>)}<th className="border p-2">Total ore</th></tr></thead><tbody>{codes.map(code => <Fragment key={code}>{['Ore', 'Interval', 'Pauză'].map((label, index) => <tr key={label}><th className="whitespace-nowrap border p-2 text-left">{index === 0 ? code : label}</th>{dates.map(date => {
      const day = days.find(d => d.agent_code === code && d.work_date === date);
      const weekend = [0, 6].includes(new Date(`${date}T00:00:00Z`).getUTCDay());
      let value: string | number = '';
      if (day?.status === 'work') value = index === 0 ? day.worked_minutes / 60 : index === 1 ? `${day.opens}–${day.closes}` : day.break_minutes / 60;
      if (day?.status === 'leave' && index === 0) value = 'CO';
      return <td key={date} className={`whitespace-nowrap border p-2 ${weekend ? 'bg-yellow-100 text-slate-900' : ''}`}>{value}</td>;
    })}<td className="border p-2 font-semibold">{index === 0 ? (totals.find(r => r.agent_code === code)?.worked_minutes ?? 0) / 60 : ''}</td></tr>)}</Fragment>)}</tbody></table></div>{!codes.length && <p>Nu există agenți confirmați.</p>}</div>;
}
