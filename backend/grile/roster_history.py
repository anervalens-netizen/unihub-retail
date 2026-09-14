"""Physical home follows confirmed dates, never the POS activation date."""
from datetime import date

def home_on(entry, day: date) -> str:
    home = entry.home_site_code
    for transfer in sorted(entry.transfers, key=lambda t: (t.effective_from, t.roster_revision)):
        if transfer.effective_from <= day:
            home = transfer.home_site_code
    return home
