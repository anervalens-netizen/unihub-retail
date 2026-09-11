from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from schemas.common import MonthStr, StrictApiModel

MAX_FILTER_VALUE_LENGTH = 180
MAX_SELECTION_ITEMS = 50
SavedViewModule = Literal["hub", "focus", "agents", "management"]


def _normalized_text(value: str, *, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or any(not char.isprintable() for char in normalized):
        raise ValueError("value must be non-blank printable text within bounds")
    return normalized


class SavedViewFilters(StrictApiModel):
    firma: str = Field(max_length=MAX_FILTER_VALUE_LENGTH)
    rm: str = Field(max_length=MAX_FILTER_VALUE_LENGTH)
    magazin: list[str] = Field(default_factory=list, max_length=MAX_SELECTION_ITEMS)
    agent: list[str] = Field(default_factory=list, max_length=MAX_SELECTION_ITEMS)

    @field_validator("firma", "rm")
    @classmethod
    def normalize_scalar(cls, value: str) -> str:
        return _normalized_text(value, maximum=MAX_FILTER_VALUE_LENGTH)

    @field_validator("magazin", "agent")
    @classmethod
    def normalize_selection(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = _normalized_text(raw, maximum=MAX_FILTER_VALUE_LENGTH)
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result


class SavedViewState(StrictApiModel):
    tab: SavedViewModule
    period: MonthStr | None = None
    filters: SavedViewFilters
    section: str | None = Field(default=None, max_length=40)
    subtab: str | None = Field(default=None, max_length=40)

    @field_validator("section", "subtab")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return None if value is None else _normalized_text(value, maximum=40)

    @model_validator(mode="after")
    def validate_module_context(self):
        if self.tab == "hub":
            if self.section not in {"current", "history", "visits"} or self.subtab is not None:
                raise ValueError("hub saved views require a valid section and no subtab")
        elif self.tab == "focus":
            if self.section not in {"incentive", "promo", "concurs", "premium", "focus"} or self.subtab is not None:
                raise ValueError("focus saved views require a valid section and no subtab")
        elif self.tab == "agents":
            if self.section not in {"overview", "grile", "analysis"} or self.subtab is not None:
                raise ValueError("agents saved views require a valid section and no subtab")
        elif self.section is not None or self.subtab not in {"asm", "target-calculator", "salarii", "pnl"}:
            raise ValueError("management saved views require a valid subtab and no section")
        return self


class SavedViewCreate(StrictApiModel):
    name: str = Field(min_length=1, max_length=80)
    state: SavedViewState

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalized_text(value, maximum=80)


class SavedViewUpdate(StrictApiModel):
    name: str | None = Field(default=None, max_length=80)
    state: SavedViewState | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else _normalized_text(value, maximum=80)

    @model_validator(mode="after")
    def require_change(self):
        if self.name is None and self.state is None:
            raise ValueError("at least one saved view field must change")
        return self


class SavedViewItem(StrictApiModel):
    id: int = Field(ge=1)
    module_id: SavedViewModule
    name: str
    state: SavedViewState
    schema_version: Literal[1]
    created_at: str
    updated_at: str


class SavedViewListResponse(StrictApiModel):
    items: list[SavedViewItem]


class SavedViewDeleteResponse(StrictApiModel):
    ok: bool
