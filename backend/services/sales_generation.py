from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, Mapping
import unicodedata

import asyncpg
import pandas as pd


MONEY_QUANTUM = Decimal("0.01")
SOURCE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_ROW_REGRESSION_PCT = Decimal("5")
DEFAULT_RECEIPT_REGRESSION_PCT = Decimal("5")
DEFAULT_VALUE_REGRESSION_PCT = Decimal("10")
DEFAULT_QUANTITY_REGRESSION_PCT = Decimal("10")


class SalesAnomalyClassification(str, Enum):
    """Authoritative-replace anomaly classes persisted in the manifest."""

    INFORMATIONAL = "informational"
    STRUCTURAL_CONTRADICTION = "structural_contradiction"


@dataclass(frozen=True, slots=True)
class SalesAnomaly:
    code: str
    classification: SalesAnomalyClassification
    message: str
    details: Mapping[str, Any]

    @property
    def blocking(self) -> bool:
        return self.classification is SalesAnomalyClassification.STRUCTURAL_CONTRADICTION

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "classification": self.classification.value,
            # Kept for consumers of the pre-classification manifest contract.
            "blocking": self.blocking,
            **dict(self.details),
            "message": self.message,
        }


def make_sales_anomaly(
    code: str,
    classification: SalesAnomalyClassification,
    message: str,
    **details: Any,
) -> dict[str, Any]:
    return SalesAnomaly(code, classification, message, details).as_dict()


class SalesPolicyValidationError(ValueError):
    """A structural contradiction that must not enter authoritative live data."""

    def __init__(self, anomalies: SalesAnomaly | Mapping[str, Any] | list[Mapping[str, Any]]) -> None:
        if isinstance(anomalies, SalesAnomaly):
            values = [anomalies.as_dict()]
        elif isinstance(anomalies, Mapping):
            values = [dict(anomalies)]
        else:
            values = [dict(item) for item in anomalies]
        if not values:
            raise ValueError("At least one sales policy anomaly is required")
        self.anomalies = tuple(values)
        super().__init__("; ".join(str(item["message"]) for item in values))


class SalesGenerationConflictError(RuntimeError):
    """The caller no longer owns the generation/head it attempted to mutate."""


class SalesGenerationValidationError(SalesPolicyValidationError):
    """A staged generation has a structural contradiction or integrity failure."""

    def __init__(self, message: str, *, code: str = "generation_validation") -> None:
        super().__init__(
            make_sales_anomaly(
                code,
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                message,
            )
        )


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTUM)


def _normalized_agent(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return " ".join(text.split())


def _canonical_sales_row(row: Any) -> dict[str, Any]:
    return {
        "sale_date": row.Data.isoformat(),
        "site_code": str(row.SiteCode),
        "bon_nr": str(row.Nr),
        "item_code": str(row.ItemCode),
        "item_name": str(row.ItemName),
        "brand": None if pd.isna(row.Brand) else str(row.Brand),
        "category": None if pd.isna(row.Categorie) else str(row.Categorie),
        "subcategory": None if pd.isna(row.SubCategorie) else str(row.SubCategorie),
        "quantity": int(row.Cantitate),
        "unit_price": f"{_money(row.Pret):.2f}",
        "total_value": f"{_money(row.Valoare):.2f}",
        "agent": str(row.Agent),
        "is_cartela": bool(row.is_cartela),
        "is_return": bool(row.is_return),
    }


def _stage_digest_scalar(value: Any) -> str:
    """Match ``sales_stage_digest_scalar`` in migration 037 byte for byte."""
    if value is None or pd.isna(value):
        return "N"
    text = str(value)
    return f"V{len(text.encode('utf-8'))}:{text}"


def canonical_sales_stage_rows_sha256(df: pd.DataFrame, *, import_month: str) -> str:
    """Digest every persisted staging field in its source row order.

    This is intentionally separate from the business manifest hash: it covers
    source metadata as well as business fields and binds ordered row
    multiplicity.  PostgreSQL recomputes the identical representation before
    accepting validation or a head move.
    """
    canonical_rows: list[str] = []
    for row_number, row in enumerate(df.itertuples(index=False), start=1):
        sale_date = row.Data.isoformat()
        values = (
            row_number,
            import_month,
            sale_date,
            str(row.SiteCode),
            str(row.Locatie),
            str(row.Firma),
            str(row.Regional),
            str(row.ASM),
            str(row.Nr),
            str(row.ItemCode),
            str(row.ItemName),
            None if pd.isna(row.Brand) else str(row.Brand),
            None if pd.isna(row.Categorie) else str(row.Categorie),
            None if pd.isna(row.SubCategorie) else str(row.SubCategorie),
            int(row.Cantitate),
            f"{_money(row.Pret):.2f}",
            f"{_money(row.Valoare):.2f}",
            str(row.Agent),
            str(bool(row.is_cartela)).lower(),
            str(bool(row.is_return)).lower(),
        )
        canonical_rows.append("\x1f".join(_stage_digest_scalar(value) for value in values))
    return sha256("\x1e".join(canonical_rows).encode("utf-8")).hexdigest()


def _validate_generation_source(df: pd.DataFrame, source_sha256: str) -> None:
    if not SOURCE_SHA256_RE.fullmatch(source_sha256):
        raise SalesPolicyValidationError(
            make_sales_anomaly(
                "invalid_source_sha256",
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                "source_sha256 must be a lowercase SHA-256 digest",
            )
        )
    if df.empty:
        raise SalesPolicyValidationError(
            make_sales_anomaly(
                "empty_generation",
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                "Sales generation cannot be empty",
            )
        )


def build_sales_generation_manifest(
    df: pd.DataFrame,
    *,
    source_sha256: str,
    cutoff_date: date,
    rows_in_file: int,
    rows_filtered: int,
) -> dict[str, Any]:
    _validate_generation_source(df, source_sha256)
    months = {value.strftime("%Y-%m") for value in df["Data"]}
    if len(months) != 1:
        raise SalesPolicyValidationError(
            make_sales_anomaly(
                "mixed_import_months",
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                "Sales generation must contain exactly one month",
                months=sorted(months),
            )
        )
    import_month = next(iter(months))
    if cutoff_date.strftime("%Y-%m") != import_month:
        raise SalesPolicyValidationError(
            make_sales_anomaly(
                "cutoff_month_mismatch",
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                "Cutoff date must belong to the imported month",
                import_month=import_month,
                cutoff_date=cutoff_date.isoformat(),
            )
        )
    maximum_sale_date = max(df["Data"])
    if maximum_sale_date > cutoff_date:
        raise SalesPolicyValidationError(
            make_sales_anomaly(
                "row_after_cutoff",
                SalesAnomalyClassification.STRUCTURAL_CONTRADICTION,
                "Sales generation contains rows after the declared cutoff",
                max_sale_date=maximum_sale_date.isoformat(),
                cutoff_date=cutoff_date.isoformat(),
            )
        )

    canonical_rows: list[str] = []
    receipts: set[tuple[str, str, str, str]] = set()
    site_days: dict[tuple[str, str], dict[str, Any]] = {}
    total_value = Decimal("0")
    total_quantity = 0
    for row in df.itertuples(index=False):
        canonical = _canonical_sales_row(row)
        canonical_rows.append(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        sale_date = canonical["sale_date"]
        site_code = canonical["site_code"]
        receipt = (
            sale_date,
            site_code,
            _normalized_agent(canonical["agent"]),
            canonical["bon_nr"],
        )
        receipts.add(receipt)
        key = (site_code, sale_date)
        aggregate = site_days.setdefault(
            key,
            {
                "site_code": site_code,
                "sale_date": sale_date,
                "rows": 0,
                "receipts": set(),
                "quantity": 0,
                "value": Decimal("0"),
            },
        )
        aggregate["rows"] += 1
        aggregate["receipts"].add(receipt)
        aggregate["quantity"] += canonical["quantity"]
        aggregate["value"] += Decimal(canonical["total_value"])
        total_quantity += canonical["quantity"]
        total_value += Decimal(canonical["total_value"])

    site_day_rows = [
        {
            "site_code": payload["site_code"],
            "sale_date": payload["sale_date"],
            "rows": payload["rows"],
            "receipts": len(payload["receipts"]),
            "quantity": payload["quantity"],
            "value": f"{payload['value'].quantize(MONEY_QUANTUM):.2f}",
        }
        for _, payload in sorted(site_days.items())
    ]
    canonical_rows.sort()
    business_hash = sha256("\n".join(canonical_rows).encode("utf-8")).hexdigest()
    site_day_hash = canonical_json_sha256(site_day_rows)
    return {
        "schema_version": 1,
        "import_month": import_month,
        "source_sha256": source_sha256,
        "cutoff_date": cutoff_date.isoformat(),
        "max_sale_date": maximum_sale_date.isoformat(),
        "rows_in_file": int(rows_in_file),
        "rows_imported": len(df),
        "rows_filtered": int(rows_filtered),
        "store_count": int(df["SiteCode"].nunique()),
        "agent_count": int(df["Agent"].nunique()),
        "receipt_count": len(receipts),
        "total_value": f"{total_value.quantize(MONEY_QUANTUM):.2f}",
        "total_quantity": total_quantity,
        "site_day_count": len(site_day_rows),
        "site_day_sha256": site_day_hash,
        "site_days": site_day_rows,
        "business_sha256": business_hash,
    }


def _drop_pct(current: Decimal, previous: Decimal) -> Decimal:
    if previous <= 0 or current >= previous:
        return Decimal("0")
    return ((previous - current) * Decimal("100") / previous).quantize(Decimal("0.01"))


def classify_authoritative_replace_anomalies(
    incoming: dict[str, Any],
    previous: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if previous is None:
        return [
            make_sales_anomaly(
                "first_generation_review",
                SalesAnomalyClassification.INFORMATIONAL,
                "Prima generație a lunii necesită review-ul cutoffului și control totals.",
            )
        ]

    anomalies: list[dict[str, Any]] = []
    incoming_cutoff = date.fromisoformat(str(incoming["cutoff_date"]))
    previous_cutoff = date.fromisoformat(str(previous["cutoff_date"]))
    if incoming_cutoff < previous_cutoff:
        anomalies.append(
            make_sales_anomaly(
                "cutoff_regression",
                SalesAnomalyClassification.INFORMATIONAL,
                "Cutofful generației noi este mai vechi decât cutofful promovat; raportul curent rămâne autoritativ.",
                previous=previous_cutoff.isoformat(),
                incoming=incoming_cutoff.isoformat(),
            )
        )

    previous_site_days = {
        (str(item["site_code"]), str(item["sale_date"]))
        for item in previous.get("site_days", [])
        if date.fromisoformat(str(item["sale_date"])) <= incoming_cutoff
    }
    incoming_site_days = {
        (str(item["site_code"]), str(item["sale_date"]))
        for item in incoming.get("site_days", [])
    }
    missing_site_days = sorted(previous_site_days - incoming_site_days)
    if missing_site_days:
        anomalies.append(
            make_sales_anomaly(
                "site_day_disappeared",
                SalesAnomalyClassification.INFORMATIONAL,
                "Cel puțin un site-day observat anterior a dispărut; raportul curent rămâne autoritativ.",
                count=len(missing_site_days),
                site_days=[f"{site_code}:{sale_date}" for site_code, sale_date in missing_site_days],
            )
        )

    comparisons = (
        ("rows_imported", DEFAULT_ROW_REGRESSION_PCT),
        ("receipt_count", DEFAULT_RECEIPT_REGRESSION_PCT),
        ("total_value", DEFAULT_VALUE_REGRESSION_PCT),
        ("total_quantity", DEFAULT_QUANTITY_REGRESSION_PCT),
    )
    for key, threshold in comparisons:
        current = Decimal(str(incoming.get(key, 0)))
        old = Decimal(str(previous.get(key, 0)))
        regression = _drop_pct(current, old)
        if regression > threshold:
            anomalies.append(
                make_sales_anomaly(
                    f"{key}_regression",
                    SalesAnomalyClassification.INFORMATIONAL,
                    f"{key} a regresat peste pragul configurat; necesită review înainte de reconciliere.",
                    previous=str(previous.get(key, 0)),
                    incoming=str(incoming.get(key, 0)),
                    drop_pct=f"{regression:.2f}",
                    threshold_pct=f"{threshold:.2f}",
                )
            )
    return anomalies


def compare_sales_generation_manifests(
    incoming: dict[str, Any],
    previous: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Backward-compatible name for the authoritative-replace policy."""
    return classify_authoritative_replace_anomalies(incoming, previous)


def manifest_has_structural_contradictions(manifest: Mapping[str, Any]) -> bool:
    for item in manifest.get("anomalies", []):
        classification = item.get("classification")
        if classification == SalesAnomalyClassification.STRUCTURAL_CONTRADICTION.value:
            return True
    return False


def manifest_requires_override(manifest: dict[str, Any]) -> bool:
    """Compatibility predicate; structural contradictions are not overrideable."""
    return manifest_has_structural_contradictions(manifest)


async def stage_sales_generation_rows(
    conn: asyncpg.Connection,
    df: pd.DataFrame,
    *,
    snapshot_id: int,
    import_month: str,
) -> int:
    def records() -> Any:
        for row_number, row in enumerate(df.itertuples(index=False), start=1):
            yield (
                snapshot_id,
                row_number,
                import_month,
                row.Data,
                row.SiteCode,
                row.Locatie,
                row.Firma,
                row.Regional,
                row.ASM,
                row.Nr,
                row.ItemCode,
                row.ItemName,
                row.Brand,
                row.Categorie,
                row.SubCategorie,
                int(row.Cantitate),
                _money(row.Pret),
                _money(row.Valoare),
                row.Agent,
                bool(row.is_cartela),
                bool(row.is_return),
            )

    await conn.copy_records_to_table(
        "sales_import_stage_rows",
        records=records(),
        columns=[
            "snapshot_id",
            "row_number",
            "import_month",
            "sale_date",
            "site_code",
            "locatie",
            "firma",
            "regional",
            "asm",
            "bon_nr",
            "item_code",
            "item_name",
            "brand",
            "category",
            "subcategory",
            "quantity",
            "unit_price",
            "total_value",
            "agent",
            "is_cartela",
            "is_return",
        ],
    )
    return len(df)


async def copy_staged_generation_to_live(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    import_month: str,
) -> int:
    result = await conn.execute(
        """
        INSERT INTO sales_transactions (
            import_month, sale_date, site_code, bon_nr, item_code, item_name,
            brand, category, subcategory, quantity, unit_price, total_value,
            agent, is_cartela, is_return, snapshot_id
        )
        SELECT import_month, sale_date, site_code, bon_nr, item_code, item_name,
               brand, category, subcategory, quantity, unit_price, total_value,
               agent, is_cartela, is_return, snapshot_id
        FROM sales_import_stage_rows
        WHERE snapshot_id = $1 AND import_month = $2
        ORDER BY row_number
        """,
        snapshot_id,
        import_month,
    )
    return int(result.rsplit(" ", 1)[-1])


async def fenced_generation_heartbeat(
    conn: asyncpg.Connection,
    *,
    snapshot_id: int,
    generation_token: str,
    owner_id: str,
    lease_seconds: int,
) -> None:
    updated = await conn.fetchval(
        """
        UPDATE import_snapshots
        SET heartbeat_at = now(),
            lease_until = now() + make_interval(secs => $4)
        WHERE id = $1
          AND generation_token = $2::uuid
          AND owner_id = $3::uuid
          AND status = 'processing'
          AND lease_until > now()
        RETURNING id
        """,
        snapshot_id,
        generation_token,
        owner_id,
        lease_seconds,
    )
    if updated is None:
        raise SalesGenerationConflictError("Sales generation lease was lost")
