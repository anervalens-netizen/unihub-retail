from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

VISITS_DB = Path("/opt/Mobiup/unihub-retail/data/visits/visits.db")
IMAGES_DIR = Path("/opt/Mobiup/unihub-retail/data/visits/images")

class VisitsReportRepository:
    def __init__(self, db_path: Path | None = None, images_dir: Path | None = None):
        self.db_path = db_path or VISITS_DB
        self.images_dir = images_dir or IMAGES_DIR

    def query_sqlite(
        self,
        month: str,
        filters: dict[str, str | None],
        *,
        store_metadata: dict[str, dict[str, str]] | None = None,
        site_codes: list[str] | None = None,
    ) -> dict:
        if not self.db_path.exists():
            return {"total": 0, "magazine_unice": 0, "avg_completion": 0.0, "rows": []}

        clauses, params = self._build_clauses(filters, month=month, site_codes=site_codes)
        where = " AND ".join(clauses)

        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            raw_rows = con.execute(
                f"""
                SELECT magazin, asm, regional, firma, completion_pct,
                       curatenie, imagine, uniforma, afise, produse_promo, data_raport
                FROM visits WHERE {where}
                """,
                params,
            ).fetchall()
        finally:
            con.close()

        rows = self._aggregate_report_rows(raw_rows, store_metadata or {})
        total = len(raw_rows)
        completion_values = [float(row["completion_pct"] or 0) for row in raw_rows]
        return {
            "total": total,
            "magazine_unice": len({row["magazin"] for row in raw_rows if row["magazin"]}),
            "avg_completion": round(sum(completion_values) / total, 1) if total else 0.0,
            "rows": rows,
        }

    def query_tree(
        self,
        filters: dict[str, str | None],
        *,
        store_metadata: dict[str, dict[str, str]] | None = None,
        site_codes: list[str] | None = None,
    ) -> list[dict]:
        if not self.db_path.exists():
            return []

        clauses, params = self._build_clauses(filters, site_codes=site_codes)
        where = " AND ".join(clauses)

        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                f"""
                SELECT id, data_raport, ora_trimitere, asm, magazin, firma,
                       completion_pct, foto1, foto2, foto3, foto4
                FROM visits WHERE {where}
                ORDER BY asm ASC, data_raport DESC, ora_trimitere DESC
                """,
                params,
            ).fetchall()
        finally:
            con.close()

        return [self._enrich_visit_row(dict(r), store_metadata or {}) for r in rows]

    def query_visit(self, visit_id: str) -> dict | None:
        if not self.db_path.exists():
            return None
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT * FROM visits WHERE id = ?", [visit_id]).fetchone()
        finally:
            con.close()
        return dict(row) if row else None

    def get_photo_filenames(self, visit_id: str) -> list[str]:
        folder = self.images_dir / visit_id
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})

    def photo_path(self, visit_id: str, filename: str) -> Path:
        return self.images_dir / visit_id / filename

    def images_dir_path(self) -> Path:
        return self.images_dir

    def db_exists(self) -> bool:
        return self.db_path.exists()

    def _build_clauses(
        self,
        filters: dict[str, str | None],
        month: str | None = None,
        site_codes: list[str] | None = None,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = ["status != 'draft'"]
        params: list[Any] = []

        if month:
            clauses.append("strftime('%Y-%m', data_raport) = ?")
            params.append(month)
        if site_codes is not None:
            if not site_codes:
                clauses.append("1 = 0")
            else:
                placeholders = ",".join("?" for _ in site_codes)
                clauses.append(f"magazin IN ({placeholders})")
                params.extend(site_codes)
            return clauses, params

        if filters.get("firma"):
            clauses.append("firma = ?")
            params.append(filters["firma"])
        if filters.get("rm"):
            clauses.append("regional = ?")
            params.append(filters["rm"])
        if filters.get("asm"):
            clauses.append("asm = ?")
            params.append(filters["asm"])
        if filters.get("magazin"):
            clauses.append("magazin = ?")
            params.append(filters["magazin"])

        return clauses, params

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
        return enriched

    def _aggregate_report_rows(
        self,
        raw_rows: list[sqlite3.Row],
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
            if row.get("data_raport") and (bucket["last_visit"] is None or row["data_raport"] > bucket["last_visit"]):
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
