from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from config import get_visits_images_dir


class VisitsReportRepository:
    """Shared FieldOps visit shaping and protected photo filesystem helpers.

    Visit rows are read exclusively by ``VisitsReportPostgresRepository``. This
    class deliberately has no database reader; the old SQLite file is archive
    material and must not be reachable from the runtime read path.
    """

    def __init__(self, images_dir: Path | None = None):
        self.images_dir = images_dir or get_visits_images_dir()

    def get_photo_filenames(self, visit_id: str) -> list[str]:
        folder = self.images_dir / visit_id
        if not folder.exists() or folder.is_symlink():
            return []
        return sorted(
            p.name
            for p in folder.iterdir()
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )

    def photo_path(self, visit_id: str, filename: str) -> Path:
        return self.images_dir / visit_id / filename

    def images_dir_path(self) -> Path:
        return self.images_dir

    def _enrich_visit_row(
        self,
        row: dict[str, Any],
        store_metadata: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        store = store_metadata.get(str(row.get("magazin") or ""))
        if not store:
            return row

        enriched = dict(row)
        enriched["firma"] = store.get("firma") or enriched.get("firma")
        enriched["regional"] = store.get("regional") or enriched.get("regional")
        enriched["asm"] = store.get("asm") or enriched.get("asm")
        enriched["locatie"] = store.get("locatie") or enriched.get("locatie")
        return enriched

    def _aggregate_report_rows(
        self,
        raw_rows: Sequence[Mapping[str, Any]],
        store_metadata: dict[str, dict[str, str]],
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str | None, str | None, str | None], dict[str, Any]] = {}
        bool_fields = ["curatenie", "imagine", "uniforma", "afise", "produse_promo"]

        for raw in raw_rows:
            row = self._enrich_visit_row(dict(raw), store_metadata)
            key = (row.get("magazin") or "", row.get("asm"), row.get("regional"), row.get("firma"))
            bucket = grouped.setdefault(
                key,
                {
                    "magazin": key[0],
                    "asm": key[1],
                    "regional": key[2],
                    "firma": key[3],
                    "nr_vizite": 0,
                    "completion_sum": 0.0,
                    "last_visit": None,
                    **{f"{field}_sum": 0 for field in bool_fields},
                },
            )
            bucket["nr_vizite"] += 1
            bucket["completion_sum"] += float(row.get("completion_pct") or 0)
            if row.get("data_raport") and (
                bucket["last_visit"] is None or row["data_raport"] > bucket["last_visit"]
            ):
                bucket["last_visit"] = row["data_raport"]
            for field in bool_fields:
                bucket[f"{field}_sum"] += 1 if row.get(field) else 0

        rows: list[dict[str, Any]] = []
        for bucket in grouped.values():
            count = bucket["nr_vizite"] or 1
            rows.append(
                {
                    "magazin": bucket["magazin"],
                    "asm": bucket["asm"],
                    "regional": bucket["regional"],
                    "firma": bucket["firma"],
                    "nr_vizite": bucket["nr_vizite"],
                    "avg_completion": round(bucket["completion_sum"] / count, 1),
                    "curatenie_pct": round(100.0 * bucket["curatenie_sum"] / count, 1),
                    "imagine_pct": round(100.0 * bucket["imagine_sum"] / count, 1),
                    "uniforma_pct": round(100.0 * bucket["uniforma_sum"] / count, 1),
                    "afise_pct": round(100.0 * bucket["afise_sum"] / count, 1),
                    "produse_promo_pct": round(100.0 * bucket["produse_promo_sum"] / count, 1),
                    "last_visit": bucket["last_visit"],
                }
            )

        return sorted(rows, key=lambda row: (-row["nr_vizite"], row["magazin"]))
