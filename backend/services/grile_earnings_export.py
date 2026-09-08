"""Provisional earnings and attendance from the same immutable read snapshot."""
from __future__ import annotations

import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from shutil import copyfileobj
from tempfile import SpooledTemporaryFile
from zipfile import ZipFile

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from grile.calendar_models import CalendarAttendance, CalendarMonth
from grile.earnings_models import EarningsMonth
from services.grile_attendance_export import build_attendance_zip

_LABELS = {
    'salary_base': 'Bază salarială', 'vouchers': 'Bonuri', 'sim': 'SIM',
    'epay': 'E-pay', 'manual_incentives': 'Stimulente manuale',
    'confirmed': 'Confirmată', 'unavailable': 'Indisponibilă', 'conflicting': 'Contradictorie',
    'missing_published_source': 'Lipsește sursa publicată', 'missing_sales': 'Lipsesc vânzările',
    'missing_positive_target': 'Lipsește un target pozitiv', 'after_cutoff': 'Planificat după data limită',
}


def _rows(sheet, rows) -> None:
    for number, row in enumerate(rows, 1):
        sheet.append(row)
        for column, value in enumerate(row, 1):
            if isinstance(value, str):
                sheet.cell(number, column).data_type = 's'
            if isinstance(value, Decimal):
                sheet.cell(number, column).number_format = '#,##0.00'
    sheet.freeze_panes = 'C5'
    sheet.auto_filter.ref = f'A4:{sheet.cell(sheet.max_row, sheet.max_column).coordinate}'
    for cell in sheet[4]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True)
    sheet.row_dimensions[4].height = 36
    width = sheet.max_column
    for number in range(1, 4):
        text = ' · '.join(str(cell.value) for cell in sheet[number] if cell.value is not None)
        sheet.merge_cells(start_row=number, start_column=1, end_row=number, end_column=width)
        sheet.cell(number, 1, text).data_type = 's'
        sheet.cell(number, 1).alignment = Alignment(wrap_text=True)
        sheet.row_dimensions[number].height = 30
    for column in range(1, width + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 24
    sheet.print_title_rows = '1:4'
    sheet.sheet_view.showGridLines = False


def _summary_rows(data: EarningsMonth, calendar: CalendarMonth):
    attendance = {a.agent_code: a for a in calendar.attendance}
    for agent in data.agents:
        totals = attendance.get(agent.agent_code, CalendarAttendance(agent_code=agent.agent_code))
        yield [agent.agent_code, agent.display_name, agent.home_site_code, _LABELS[agent.identity_status],
               agent.home_work_days, agent.home_target, agent.home_sales, agent.home_commission,
               agent.away_commission, agent.supplemental_pay, agent.known_earnings,
               ', '.join(_LABELS.get(value, value) for value in agent.issues),
               totals.worked_minutes / 60, totals.leave_days]


def _calendar_rows(calendar: CalendarMonth):
    grouped = defaultdict(list)
    for day in calendar.days:
        grouped[(day.site_code, day.work_date)].append(day)
    roster = {r.agent_code: r for r in calendar.roster}
    attendance = {(d.agent_code, d.work_date): d for d in calendar.attendance_days}
    sites = {r.home_site_code for r in calendar.roster if r.active} | set(calendar.attendance_by_store) | {h.site_code for h in calendar.store_hours} | {d.site_code for d in calendar.days}
    if len(sites) > 200:
        raise HTTPException(422, "Calendar export exceeds 200 stores")
    year, month = map(int, calendar.month.split('-'))
    labels = {'work': 'Lucrează', 'leave': 'Concediu', 'off': 'Liber', 'cancelled': 'Anulat'}
    for site in sorted(sites):
        for number in range(1, monthrange(year, month)[1] + 1):
            current = date(year, month, number)
            entries = grouped[(site, current)]
            for day in sorted(entries, key=lambda row: row.agent_code):
                person = roster[day.agent_code]
                hours = attendance.get((day.agent_code, current))
                yield [site, current.isoformat(), day.agent_code, person.display_name,
                       labels[day.status], day.supplemental, person.home_site_code,
                       hours.opens if hours else None, hours.closes if hours else None,
                       hours.break_minutes if hours else 0, hours.worked_minutes / 60 if hours else 0]
            if not any(day.status == 'work' for day in entries):
                yield [site, current.isoformat(), None, None, 'Nealocat']


def _workbook(data: EarningsMonth, calendar: CalendarMonth) -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.identifier = data.projection_revision
    summary = workbook.create_sheet('Castiguri provizorii')
    _rows(summary, [
        ['PROVIZORIU — nu reprezintă salariul oficial', data.month],
        ['Vânzări până la', str(data.cutoff or 'Indisponibil')],
        ['Componente neincluse', ', '.join(_LABELS.get(value, value) for value in data.unavailable_components)],
        ['Cod agent', 'Nume confirmat', 'Magazin de bază', 'Identitate', 'Zile bază', 'Target personal (lei)',
         'Vânzări bază (lei)', 'Comision lunar (lei)', 'Comision alte locații (lei)', 'Plata suplimentărilor (lei)', 'Total calculat (lei)', 'Probleme', 'Ore programate în toate magazinele', 'Zile CO programate'],
        *_summary_rows(data, calendar),
    ])
    detail = workbook.create_sheet('Detalii zile')
    _rows(detail, [
        ['PROVIZORIU — atribuirea urmează calendarul confirmat', data.month],
        ['Vânzări până la', str(data.cutoff or 'Indisponibil')],
        ['Celule monetare goale = indisponibil; zilele viitoare rămân planificate'],
        ['Cod agent', 'Data', 'Magazin lucrat', 'Altă locație', 'Suplimentare', 'Vânzări',
         'Target zilnic', 'Comision alte locații', 'Plata suplimentării', 'Problemă'],
        *[[a.agent_code, d.work_date.isoformat(), d.site_code, d.away, d.supplemental,
           d.sales, d.daily_target, d.commission, d.supplemental_pay, _LABELS.get(d.issue or '', d.issue or '')]
          for a in data.agents for d in a.days],
    ])
    unassigned = workbook.create_sheet('Vanzari nealocate')
    _rows(unassigned, [
        ['PROVIZORIU — nu sunt atribuite automat unei persoane', data.month],
        ['Vânzări până la', str(data.cutoff or 'Indisponibil')],
        ['Calendar complet necesar pentru target; divizorul este numărul zilelor work programate'],
        ['Magazin', 'Data', 'Vânzări'],
        *[[r.site_code, r.sale_date.isoformat(), r.sales] for r in data.unassigned_sales],
    ])
    schedule = workbook.create_sheet('Calendar')
    _rows(schedule, [
        ['PROVIZORIU — program confirmat, fără atribuiri din vânzări', calendar.month],
        ['Nealocat = niciun lucrător confirmat în magazin în acea zi'],
        ['Orele și concediile includ programul întregii luni, inclusiv zilele viitoare'],
        ['Magazin lucrat', 'Data', 'Cod agent', 'Nume confirmat', 'Tip zi', 'Suplimentare',
         'Magazin de bază', 'Deschidere', 'Închidere', 'Pauză (minute)', 'Ore programate'],
        *_calendar_rows(calendar),
    ])
    return workbook


def build_earnings_zip(calendar: CalendarMonth, earnings: EarningsMonth):
    if earnings.calendar_revision != calendar.projection_revision or earnings.month != calendar.month:
        raise HTTPException(409, 'Earnings and attendance must share one calendar revision')
    if len(calendar.days) > 62000 or len(earnings.agents) > 2000 or sum(len(a.days) for a in earnings.agents) > 62000 or len(earnings.unassigned_sales) > 62000:
        raise HTTPException(422, 'Earnings export exceeds the supported monthly cohort')
    artifact = build_attendance_zip(calendar)
    try:
        workbook = _workbook(earnings, calendar)
        try:
            with SpooledTemporaryFile(max_size=1024 * 1024, mode='w+b') as file:
                workbook.save(file)
                file.seek(0)
                with ZipFile(artifact.stream, 'a') as archive:
                    with archive.open(f'Castiguri-provizorii-{calendar.month}.xlsx', 'w') as member:
                        copyfileobj(file, member, length=256 * 1024)
                    archive.writestr('castiguri-manifest.json', json.dumps({
                        'month': earnings.month, 'status': 'provisional',
                        'projection_revision': earnings.projection_revision,
                        'calendar_revision': earnings.calendar_revision,
                        'cutoff': str(earnings.cutoff) if earnings.cutoff else None,
                        'selling_days': earnings.selling_days,
                        'unavailable_components': earnings.unavailable_components,
                    }, ensure_ascii=False))
        finally:
            workbook.close()
        artifact.filename = f'Grile-pontaje-provizorii-{calendar.month}.zip'
        artifact.size = artifact.stream.tell()
        return artifact
    except BaseException:
        artifact.close()
        raise
