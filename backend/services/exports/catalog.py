"""Export catalog: public datasets, dimensions and metric definitions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDef:
    key: str
    label: str
    type: str
    group: str


DATASETS = {
    "agents": {"label": "Agenti", "description": "Rand pe agent si magazin, folosind structura curenta.", "dimensions": ["agent", "site_code", "locatie", "firma", "regional", "asm"]},
    "stores": {"label": "Magazine", "description": "Rand pe magazin, folosind structura curenta.", "dimensions": ["site_code", "locatie", "firma", "regional", "asm"]},
    "regionals": {"label": "RM", "description": "Rand pe regional manager.", "dimensions": ["regional"]},
    "asms": {"label": "ASM", "description": "Rand pe ASM.", "dimensions": ["regional", "asm"]},
    "incentive_products": {"label": "Incentive pe produs", "description": "Produse incentive, categorii, excluderi promo si plata calculata pe pragul fiecarui magazin.", "dimensions": []},
}
DIMENSIONS = {
    "agent": ColumnDef("agent", "Agent", "text", "Identificare"), "site_code": ColumnDef("site_code", "Cod magazin", "text", "Identificare"), "locatie": ColumnDef("locatie", "Magazin", "text", "Identificare"), "firma": ColumnDef("firma", "Firma", "text", "Identificare"), "regional": ColumnDef("regional", "RM", "text", "Identificare"), "asm": ColumnDef("asm", "ASM", "text", "Identificare"),
}
METRICS = {
    "total_sales": ColumnDef("total_sales", "Vanzari", "currency", "Vanzari"), "total_quantity": ColumnDef("total_quantity", "Cantitate", "integer", "Vanzari"), "total_receipts": ColumnDef("total_receipts", "Bonuri", "integer", "Vanzari"), "avg_receipt_value": ColumnDef("avg_receipt_value", "Val. medie bon", "currency", "KPI"), "proc_bon2acc": ColumnDef("proc_bon2acc", "Bon2Acc %", "percent", "KPI"), "prc_focus_acc_qty": ColumnDef("prc_focus_acc_qty", "Focus %", "percent", "KPI"), "target": ColumnDef("target", "Target", "currency", "Target"), "target_progress_pct": ColumnDef("target_progress_pct", "Realizare target %", "percent", "Target"), "working_days": ColumnDef("working_days", "Zile active", "integer", "KPI"), "daily_average": ColumnDef("daily_average", "Medie zilnica", "currency", "KPI"), "store_count": ColumnDef("store_count", "Magazine active", "integer", "Identificare"), "agent_count": ColumnDef("agent_count", "Agenti activi", "integer", "Identificare"), "incentive_sales": ColumnDef("incentive_sales", "Incentive vanzari", "currency", "Campanii"), "incentive_quantity": ColumnDef("incentive_quantity", "Incentive cantitate", "integer", "Campanii"), "incentive_bonus": ColumnDef("incentive_bonus", "Incentive bonus", "currency", "Campanii"), "promo_sales": ColumnDef("promo_sales", "Promo vanzari", "currency", "Campanii"), "promo_quantity": ColumnDef("promo_quantity", "Promo cantitate", "integer", "Campanii"),
}
EVOLUTION_METRICS = {key: METRICS[key] for key in ("total_sales", "total_quantity", "total_receipts", "avg_receipt_value", "proc_bon2acc", "prc_focus_acc_qty", "target", "target_progress_pct", "incentive_sales", "incentive_quantity", "incentive_bonus", "promo_sales", "promo_quantity")}
DAILY_EVOLUTION_METRICS = {key: METRICS[key] for key in ("total_sales", "total_quantity", "total_receipts", "avg_receipt_value", "proc_bon2acc", "prc_focus_acc_qty")}
CAMPAIGN_METRICS = frozenset({"incentive_sales", "incentive_quantity", "incentive_bonus", "promo_sales", "promo_quantity"})
DEFAULT_METRICS = ["total_sales", "total_quantity", "total_receipts", "target", "target_progress_pct", "proc_bon2acc", "prc_focus_acc_qty", "daily_average"]
COMPARISON_LEVELS = {
    "general": {"label": "General", "sheet": "General", "dimensions": []},
    "asms": {"label": "ASM", "sheet": "ASM", "dimensions": ["asm"]},
    "stores": {"label": "Magazine", "sheet": "Magazine", "dimensions": ["site_code", "locatie", "asm"]},
    "agents": {"label": "Agenti", "sheet": "Agenti", "dimensions": ["agent", "site_code", "locatie", "asm"]},
}
