"""Pure value/range mapping for the Grile V2 native-template pilot.

The result is suitable for Google Sheets ``values.batchUpdate``.  Formatting,
template cloning and clearing are intentionally handled by the caller.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any, cast


def _col(n: int) -> str:
    out = ""
    while n >= 0:
        out = chr(65 + n % 26) + out
        n = n // 26 - 1
    return out


def _cell(sheet: str, row: int, col: int, value: Any) -> dict[str, Any]:
    return {"range": f"'{sheet}'!{_col(col)}{row}", "values": [[value]]}


def _num(value: Any) -> Any:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _pct(value: Any) -> Any:
    value = _num(value)
    return "" if value == "" else value / 100


def _put_metric(data: list[dict[str, Any]], sheet: str, row: int, col: int,
                label: str, value: Any, percentage: bool = False) -> None:
    data.extend((_cell(sheet, row, col, label),
                 _cell(sheet, row + 1, col, _pct(value) if percentage else _num(value))))


def _name(roster: dict[str, str], code: str) -> str:
    return roster.get(code) or code


def _date(month: str, day: int) -> str:
    return f"{month}-{day:02d}"


def _agent_values(data: list[dict[str, Any]], layout: dict[str, Any], agents: list[dict[str, Any]], synced_at: str) -> None:
    for i, agent in enumerate(agents):
        pair, slot = divmod(i, 2)
        row = 9 + pair * 24
        col = slot * 13
        code = agent.get("agent_code", "")
        layout["card_rows"][code] = row
        if slot == 0:
            layout["agent_pairs"].append({"pair": pair + 1, "row": row, "agents": []})
        layout["agent_pairs"][-1]["agents"].append(code)
        p, k, y = agent.get("performance", {}), agent.get("compensation", {}), agent.get("salary", {})
        data += [_cell("Grilă", row, col, agent.get("display_name") or code),
                 _cell("Grilă", row + 1, col, f"COD {code}"),
                 _cell("Grilă", row + 2, col, f"Programate {p.get('scheduled_days', '')}    Lucrate {p.get('worked_days', '')}    CO {p.get('leave_days', '')}    Suplimentare {p.get('supplemental_days', '')}")]
        for rr, items in ((row + 4, (("Target personal", "target", False), ("Realizat", "sales", False))),
                          (row + 5, (("Progres", "progress", True), ("Forecast %", "forecast_progress", True))),
                          (row + 6, (("Medie / zi", "average", False), ("Forecast vânzări", "forecast", False)))):
            for offset, (label, key, pct) in ((0, items[0]), (6, items[1])):
                data += [_cell("Grilă", rr, col + offset, label),
                         _cell("Grilă", rr, col + offset + 4, _pct(p.get(key)) if pct else _num(p.get(key)))]
        for j, threshold in enumerate((80, 100, 120)):
            data += [_cell("Grilă", row + 8, col + 3 + j * 3, threshold / 100),
                     _cell("Grilă", row + 9, col + 3 + j * 3, _num(p.get(f"daily_{threshold}")))]
        data.append(_cell("Grilă", row + 8, col, "Daily"))
        data.append(_cell("Grilă", row + 11, col, "Salariu — detaliere și proiecție"))
        salary_metrics = (("Salariu bază", k.get("salary_base")), ("Tichete masă", k.get("vouchers")),
                          ("Comision accesorii", agent.get("home_commission")), (f"SIM · {k.get('sim_quantity', 0)} buc.", y.get("sim_pay")),
                          ("E-pay <50 lei · buc.", k.get("epay_under_50")), ("E-pay ≥50 lei · buc.", k.get("epay_over_50")),
                          ("Total salariu curent", y.get("current_total")), ("Forecast salariu", y.get("forecast_total")),
                          ("Potențial la 100%", y.get("potential_100")), ("Potențial la 120%", y.get("potential_120")),
                          ("Incentive", k.get("incentive")), ("Comision total curent", y.get("commission_total")),
                          ("Total suplimentar", agent.get("supplemental_pay")), ("Comision alte locații", agent.get("away_commission")),
                          ("E-pay · plată", y.get("epay_pay")))
        salary_rows = (row + 12, row + 13, row + 14, row + 16, row + 17, row + 19, row + 20, row + 21)
        for j, (label, value) in enumerate(salary_metrics):
            rr, cc = salary_rows[j // 2], col + (j % 2) * 6
            data += [_cell("Grilă", rr, cc, label), _cell("Grilă", rr, cc + 4, _num(value))]
    last_pair = (len(agents) + 1) // 2
    layout["supplement_row"] = 32 + max(0, last_pair - 1) * 24
    layout["note_row"] = layout["supplement_row"] + 3
    extras = [f"{a.get('display_name') or a.get('agent_code')} · {x.get('work_date')} · {x.get('site_code')}"
              for a in agents for x in a.get("days", []) if x.get("supplemental") or x.get("away")]
    data += [_cell("Grilă", layout["supplement_row"], 0, "Zile suplimentare · agenții magazinului"),
             _cell("Grilă", layout["supplement_row"] + 1, 0, "\n".join(extras) if extras else "Fără zile suplimentare."),
             _cell("Grilă", layout["note_row"], 0, f"Sincronizare pilot · {synced_at}")]


def _calendar_program(cal: dict[str, Any], site: str) -> str:
    hours = (cal.get("store_hours") or [{}])[0]
    if not hours:
        effective = [x for x in cal.get('attendance_days', []) if x.get('site_code') == site and x.get('status') == 'work']
        hours = effective[0] if effective else {}
    return (f"{hours.get('opens')}–{hours.get('closes')} · pauză {hours.get('break_minutes')} min"
            if hours.get("opens") and hours.get("closes") else "neconfigurat")


def _calendar_grid_values(data: list[dict[str, Any]], cal: dict[str, Any], roster: dict[str, str], site: str, month: str) -> tuple[int, int]:
    first_weekday, days_in_month = date.fromisoformat(month + "-01").weekday(), monthrange(*map(int, month.split("-")))[1]
    data += [_cell("Calendar", 5, i, name) for i, name in enumerate(("Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"))]
    for day in range(1, days_in_month + 1):
        idx, col = first_weekday + day - 1, (first_weekday + day - 1) % 7
        row = 6 + (idx // 7) * 3
        current = _date(month, day)
        names = [_name(roster, x.get("agent_code")) for x in cal.get("days", []) if x.get("work_date") == current and x.get("site_code") == site and x.get("status") == "work"]
        state = "Închisă" if current in {x.get("work_date") for x in cal.get("closures", [])} else ("\n".join(names) if names else "Fără agent")
        data += [_cell("Calendar", row, col, day), _cell("Calendar", row + 1, col, state)]
    return days_in_month, (first_weekday + days_in_month + 6) // 7


def _calendar_sections(data: list[dict[str, Any]], cal: dict[str, Any], roster: dict[str, str], site: str, weeks: int) -> dict[str, int]:
    leave_row, supplement_row = 6 + weeks * 3 + 1, 6 + weeks * 3 + 4
    leave = [f"{_name(roster, x.get('agent_code'))} · {x.get('work_date')}" for x in cal.get("days", []) if x.get("status") == "leave"]
    incoming = [f"{_name(roster, x.get('agent_code'))} · {x.get('work_date')}" for x in cal.get("days", []) if x.get("site_code") == site and x.get("status") == "work" and x.get("supplemental")]
    data += [_cell("Calendar", leave_row, 0, "Concedii · agenții magazinului"), _cell("Calendar", leave_row + 1, 0, "\n".join(leave) if leave else "Nu sunt concedii înregistrate."),
             _cell("Calendar", supplement_row, 0, "Suplimentari în această locație"), _cell("Calendar", supplement_row + 1, 0, "\n".join(incoming) if incoming else "Nu sunt zile suplimentare programate.")]
    return {"leave_row": leave_row, "supplement_row": supplement_row}


def _attendance_row(data: list[dict[str, Any]], by_agent_day: dict[tuple[Any, Any], dict[str, Any]], roster: dict[str, str], code: str, month: str, days_in_month: int, row: int, total: dict[str, Any] | None) -> None:
    data += [_cell("Pontaj", row, 0, _name(roster, code or "")), _cell("Pontaj", row + 1, 0, f"COD {code} · interval"), _cell("Pontaj", row + 2, 0, "Pauză (ore)")]
    for day in range(1, days_in_month + 1):
        item = by_agent_day.get((code, _date(month, day)))
        if not item:
            continue
        status = item.get("status")
        val = "CO" if status == "leave" else (_num(item.get("worked_minutes", 0)) / 60 if status == "work" else "")
        data += [_cell("Pontaj", row, day, val), _cell("Pontaj", row + 1, day, f"{item.get('opens')}–{item.get('closes')}" if status == "work" else ""),
                 _cell("Pontaj", row + 2, day, _num(item.get("break_minutes", 0)) / 60 if status == "work" else "")]
    data.append(_cell("Pontaj", row, 32, _num(total.get("worked_minutes", 0)) / 60 if total else ""))


def _pontaj_values(data: list[dict[str, Any]], cal: dict[str, Any], roster: dict[str, str], agents: list[dict[str, Any]], month: str, days_in_month: int, site: str, program: str) -> None:
    data += [_cell("Pontaj", 1, 0, cal.get("store_name", "")),
             _cell("Pontaj", 2, 0, cal.get("store_subtitle", "")),
             _cell("Pontaj", 3, 0, "Pontaj provizoriu · ore la locația efectivă · CO = concediu"),
             _cell("Pontaj", 4, 0, f"Program magazin {program}")]
    attendance = [x for x in cal.get("attendance_days", []) if x.get("site_code") == site]
    data += [_cell("Pontaj", 6, 0, "Nume / Cod agent"), _cell("Pontaj", 6, 32, "Total ore")]
    data += [_cell("Pontaj", 6, day, day) for day in range(1, days_in_month + 1)]
    by_agent_day = {(x.get("agent_code"), x.get("work_date")): x for x in attendance}
    totals = {x.get("agent_code"): x for x in cal.get("attendance_by_store", [])}
    codes = list(dict.fromkeys([a.get("agent_code") for a in agents] + [x.get("agent_code") for x in attendance]))
    for i, raw_code in enumerate(codes):
        code = cast(str, raw_code)
        _attendance_row(data, by_agent_day, roster, code, month, days_in_month, 7 + i * 3, totals.get(code))


def _calendar_values(data: list[dict[str, Any]], layout: dict[str, Any], d: dict[str, Any], store: dict[str, Any], agents: list[dict[str, Any]], site: str, month: str, display_month: str, synced_at: str) -> None:
    cal = d.get("calendar", {})
    roster = {x.get("agent_code"): x.get("display_name", x.get("agent_code")) for x in cal.get("roster", [])}
    program = _calendar_program(cal, site)
    data += [_cell("Calendar", 1, 0, store.get("locatie", "")),
             _cell("Calendar", 2, 0, f"{store.get('firma', '')} · {display_month} · {site}"),
             _cell("Calendar", 3, 0, f"Program magazin {program}")]
    days_in_month, weeks = _calendar_grid_values(data, cal, roster, site, month)
    layout["calendar_weeks"] = [{"week": i + 1, "start_row": 6 + i * 3} for i in range(weeks)]
    layout["calendar_sections"] = _calendar_sections(data, cal, roster, site, weeks)
    supplement_row = layout["calendar_sections"]["supplement_row"]
    data.append(_cell("Calendar", supplement_row + 3, 0, f"Sincronizare pilot · {synced_at}"))
    cal_with_labels = {**cal, "store_name": store.get("locatie", ""), "store_subtitle": f"{store.get('firma', '')} · {display_month} · {site}"}
    _pontaj_values(data, cal_with_labels, roster, agents, month, days_in_month, site, program)
    layout["synced_at"] = synced_at
    return None


def build_values(snapshot: dict[str, Any], synced_at: str) -> dict[str, Any]:
    """Map a snapshot to values updates and layout metadata.

    No business metrics are recomputed here.  Decimal strings become numeric
    cell values; percentage metrics are divided by 100 for Sheets formatting.
    """
    d = snapshot
    store = d.get("store", {})
    month = d.get("month") or date.today().strftime("%Y-%m")
    month_names = ('Ianuarie','Februarie','Martie','Aprilie','Mai','Iunie','Iulie','August','Septembrie','Octombrie','Noiembrie','Decembrie')
    display_month = f"{month_names[int(month[5:])-1]} {month[:4]}"
    site = store.get("site_code", "")
    data: list[dict[str, Any]] = []

    data += [_cell("Grilă", 1, 0, store.get("locatie", "")),
             _cell("Grilă", 2, 0, f"{store.get('firma', '')} · {display_month} · {site}"),
             ]
    sp = d.get("store_performance") or {}
    for i, (label, key, is_pct) in enumerate((
        ("Target", "target", False), ("Realizat", "sales", False),
        ("Forecast", "forecast", False), ("Daily 90%", "daily_90", False),
        ("Daily 100%", "daily_100", False))):
        col = i * 5
        _put_metric(data, "Grilă", 5, col, label, sp.get(key))
        if key in ("sales", "forecast"):
            data.append(_cell("Grilă", 7, col, _pct(sp.get("progress" if key == "sales" else "forecast_progress"))))
    data += [_cell("Grilă", 4, 0, "Performanță magazin"),
             _cell("Grilă", 4, 14, f"Vânzări până la {'.'.join(str(d.get('cutoff', '')).split('-')[::-1])}")]
    layout: dict[str, Any] = {"agent_pairs": [], "card_rows": {}, "supplement_row": 0,
                              "note_row": 0, "calendar_weeks": [], "calendar_sections": {}}
    agents = d.get("agents", [])
    _agent_values(data, layout, agents, synced_at)

    _calendar_values(data, layout, d, store, agents, site, month, display_month, synced_at)
    return {"data": data, "layout": layout}
