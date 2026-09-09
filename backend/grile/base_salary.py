"""Owner rule: Bucuresti/Constanta/Cluj 2600 RON; other cities 2400 RON.
The home store controls this amount, never a visiting/supplemental shift.
"""
from decimal import Decimal

HIGH_BASE_STORES = frozenset({
    'AFICOTRO', 'AUCHMILI', 'AUCHTRIC', 'CORALEX', 'MC-MEGAMALL', 'PROMEN',
    'MCRFBAL', 'AUCHMIL2', 'PRKLK', 'PROM', 'CRFFEER', 'COTROCENI', 'MEGAMALL', 'SUNPLZ', 'UNIRII',
    'CCTCIT', 'CTCORA', 'CTVIVO', 'CTCRFTOM', 'CTCITYPRK', 'CTAUCH',
    'CJIULMALL', 'CLUJCFPOL', 'CJPPOL',
})

def base_salary(home_site: str):
    if home_site == 'TL':
        return None
    return Decimal(2600 if home_site in HIGH_BASE_STORES else 2400)
