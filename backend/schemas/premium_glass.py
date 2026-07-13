from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PremiumGlassSummary(BaseModel):
    month: str
    total_qty: int = 0
    total_sales: Decimal = Decimal(0)
    premium_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_qty: int = 0
    regular_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    premium_sales_share_pct: Decimal | None = None
    active_stores: int = 0
    active_agents: int = 0
    premium_active_stores: int = 0
    premium_active_agents: int = 0
    target_model_count: int = 0


class PremiumGlassModelStat(BaseModel):
    model_key: str
    model_label: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    premium_item_count: int = 0
    regular_item_count: int = 0


class PremiumGlassSurfaceStat(BaseModel):
    surface_key: Literal["screen", "camera"]
    surface_label: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassStoreStat(BaseModel):
    site_code: str
    locatie: str
    firma: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassManagerStat(BaseModel):
    manager: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None
    store_count: int = 0
    agent_count: int = 0


class PremiumGlassAgentStat(BaseModel):
    agent: str
    site_code: str
    locatie: str
    firma: str
    premium_qty: int = 0
    regular_qty: int = 0
    total_qty: int = 0
    premium_sales: Decimal = Decimal(0)
    regular_sales: Decimal = Decimal(0)
    total_sales: Decimal = Decimal(0)
    premium_qty_share_pct: Decimal | None = None


class PremiumGlassProductStat(BaseModel):
    item_code: str
    item_name: str
    is_premium: bool
    model_labels: list[str] = Field(default_factory=list)
    qty: int = 0
    sales: Decimal = Decimal(0)
    store_count: int = 0


class PremiumGlassAnalysis(BaseModel):
    summary: PremiumGlassSummary
    models: list[PremiumGlassModelStat] = Field(default_factory=list)
    surfaces: list[PremiumGlassSurfaceStat] = Field(default_factory=list)
    managers: list[PremiumGlassManagerStat] = Field(default_factory=list)
    stores: list[PremiumGlassStoreStat] = Field(default_factory=list)
    agents: list[PremiumGlassAgentStat] = Field(default_factory=list)
    products: list[PremiumGlassProductStat] = Field(default_factory=list)
