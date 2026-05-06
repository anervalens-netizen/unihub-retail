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

    def query_sqlite(self, month: str, filters: dict[str, str | None]) -> dict:
        if not self.db_path.exists():
            return {"total": 0, "magazine_unice": 0, "avg_completion": 0.0, "rows": []}

        clauses, params = self._build_clauses(filters, month=month)
        where = " AND ".join(clauses)

        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            cur = con.cursor()
            summary = cur.execute(
                f"""
                SELECT COUNT(*) AS total_vizite,
                       COUNT(DISTINCT magazin) AS magazine_unice,
                       ROUND(AVG(completion_pct), 1) AS avg_completion
                FROM visits WHERE {where}
                """,
                params,
            ).fetchone()

            rows = cur.execute(
                f"""
                SELECT magazin, asm, regional, firma,
                       COUNT(*) AS nr_vizite,
                       ROUND(AVG(completion_pct), 1) AS avg_completion,
                       ROUND(100.0 * SUM(curatenie)     / COUNT(*), 1) AS curatenie_pct,
                       ROUND(100.0 * SUM(imagine)       / COUNT(*), 1) AS imagine_pct,
                       ROUND(100.0 * SUM(uniforma)      / COUNT(*), 1) AS uniforma_pct,
                       ROUND(100.0 * SUM(afise)         / COUNT(*), 1) AS afise_pct,
                       ROUND(100.0 * SUM(produse_promo) / COUNT(*), 1) AS produse_promo_pct,
                       MAX(data_raport) AS last_visit
                FROM visits WHERE {where}
                GROUP BY magazin, asm, regional, firma
                ORDER BY nr_vizite DESC, magazin ASC
                """,
                params,
            ).fetchall()
        finally:
            con.close()

        return {
            "total": summary["total_vizite"] if summary else 0,
            "magazine_unice": summary["magazine_unice"] if summary else 0,
            "avg_completion": float(summary["avg_completion"]) if summary and summary["avg_completion"] else 0.0,
            "rows": [dict(r) for r in rows],
        }

    def query_tree(self, filters: dict[str, str | None]) -> list[dict]:
        if not self.db_path.exists():
            return []

        clauses, params = self._build_clauses(filters)
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

        return [dict(r) for r in rows]

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
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = ["status != 'draft'"]
        params: list[Any] = []

        if month:
            clauses.append("strftime('%Y-%m', data_raport) = ?")
            params.append(month)
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
