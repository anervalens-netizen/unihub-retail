"""Original payroll locations for P&L modelling, without payroll mutations."""
from collections import defaultdict
from decimal import Decimal


def salary_inputs_by_source_location(rows, stores):
    # Reuse the payroll importer's reviewed, company-specific mapping. This
    # offline estimator does not resolve people or change recorded identities.
    from scripts.import_salary_records import LOCATION_ALIASES, company_key, normalize_text

    locations = defaultdict(set)
    for store in stores:
        locations[(company_key(store['firma']), normalize_text(store['locatie']))].add(store['site_code'])
    totals = defaultdict(Decimal)
    for row in rows:
        company = row['company_name']
        location = normalize_text(row['location'] or '')
        key = (company, location)
        if key in LOCATION_ALIASES:
            site = LOCATION_ALIASES[key]
        else:
            candidates = locations.get((company_key(company), location), set())
            site = next(iter(candidates)) if len(candidates) == 1 else None
        # Unknown locations and Team Leaders stay unallocated. Never fall back
        # to a conflicting current site_code or guess from an agent's name.
        if site is not None:
            totals[(company, row['period'], site)] += row['amount']
    return [dict(company_name=c, period=p, site_code=s, amount=amount)
            for (c, p, s), amount in sorted(totals.items())]


def prefer_reconciled_hr_allocations(recorded_source_rows, recorded_inputs, archive_rows):
    """Use original HR distribution only for an exactly reconciled month.

    HR changes the estimation location breakdown, never the official payroll
    total. Include unallocated rows in the reconciliation before excluding them
    from store-level model inputs. Ambiguous or partial HR stays a fallback.
    """
    recorded = defaultdict(lambda: [Decimal(0), 0])
    archive = defaultdict(lambda: [Decimal(0), 0, 0])
    for row in recorded_source_rows:
        key = (row['company_name'], row['period'])
        recorded[key][0] += row['amount']
        recorded[key][1] += row['row_count']
    for row in archive_rows:
        key = (row['company_name'], row['period'])
        archive[key][0] += row['amount']
        archive[key][1] += row['row_count']
        archive[key][2] = max(archive[key][2], row['source_count'])
    trusted = {key for key, values in archive.items()
               if values[2] == 1 and values[:2] == recorded.get(key)}
    return [r for r in recorded_inputs if (r['company_name'], r['period']) not in trusted] + [
        {k: r[k] for k in ('company_name', 'period', 'site_code', 'amount')}
        for r in archive_rows
        if (r['company_name'], r['period']) in trusted and r['site_code']
    ]
