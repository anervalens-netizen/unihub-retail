import asyncio
from collections import defaultdict
from functools import partial
from typing import Any

from fastapi import HTTPException

from db.connection import get_pool
from models import (
    TeamLeaderGroup,
    VisitDayGroup,
    VisitDetail,
    VisitMonthGroup,
    VisitReportResponse,
    VisitReportRow,
    VisitSummaryItem,
    VisitTreeResponse,
)
from repositories.visits_report import VisitsReportRepository
from services.filters import normalize_filter


def _split_filter_values(value: str | None) -> list[str]:
    normalized = normalize_filter(value)
    if normalized is None:
        return []
    return [item.strip() for item in normalized.split(",") if item.strip()]


class VisitsReportService:
    def __init__(self, repo: VisitsReportRepository):
        self.repo = repo

    async def get_visits_report(
        self,
        month: str,
        firma: str | None,
        rm: str | None,
        asm: str | None,
        magazin: str | None,
    ) -> VisitReportResponse:
        if not self.repo.db_exists():
            raise HTTPException(status_code=503, detail="Baza de date vizite nu este disponibila.")

        filters = {
            "firma": normalize_filter(firma),
            "rm": normalize_filter(rm),
            "asm": normalize_filter(asm),
            "magazin": normalize_filter(magazin),
        }
        store_metadata, site_codes = await self._resolve_store_scope(filters)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                self.repo.query_sqlite,
                month,
                filters,
                store_metadata=store_metadata,
                site_codes=site_codes,
            ),
        )

        report_rows = [
            VisitReportRow(
                magazin=r["magazin"] or "",
                asm=r["asm"],
                regional=r["regional"],
                firma=r["firma"],
                nr_vizite=r["nr_vizite"],
                avg_completion=float(r["avg_completion"]) if r["avg_completion"] else 0.0,
                curatenie_pct=float(r["curatenie_pct"]) if r["curatenie_pct"] else 0.0,
                imagine_pct=float(r["imagine_pct"]) if r["imagine_pct"] else 0.0,
                uniforma_pct=float(r["uniforma_pct"]) if r["uniforma_pct"] else 0.0,
                afise_pct=float(r["afise_pct"]) if r["afise_pct"] else 0.0,
                produse_promo_pct=float(r["produse_promo_pct"]) if r["produse_promo_pct"] else 0.0,
                last_visit=r["last_visit"],
            )
            for r in result["rows"]
        ]

        return VisitReportResponse(
            month=month,
            total_vizite=result["total"],
            magazine_unice=result["magazine_unice"],
            avg_completion=result["avg_completion"],
            rows=report_rows,
        )

    async def get_visits_tree(
        self,
        firma: str | None,
        rm: str | None,
        asm: str | None,
        magazin: str | None,
    ) -> VisitTreeResponse:
        if not self.repo.db_exists():
            raise HTTPException(status_code=503, detail="Baza de date vizite nu este disponibila.")

        filters = {
            "firma": normalize_filter(firma),
            "rm": normalize_filter(rm),
            "asm": normalize_filter(asm),
            "magazin": normalize_filter(magazin),
        }
        store_metadata, site_codes = await self._resolve_store_scope(filters)

        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(
            None,
            partial(self.repo.query_tree, filters, store_metadata=store_metadata, site_codes=site_codes),
        )

        # Group by the team leader who made the visit (snapshot `team_leader_name`),
        # not by the store's current ASM.
        tl_map: dict[str, dict[str, dict[str, list[VisitSummaryItem]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

        for r in rows:
            tl_key = r["team_leader_name"] or "Fără TL atribuit"
            month_key = r["data_raport"][:7] if r["data_raport"] else "—"
            day_key = r["data_raport"] or "—"
            has_photos = any(r[f"foto{i}"] for i in range(1, 5))
            tl_map[tl_key][month_key][day_key].append(
                VisitSummaryItem(
                    id=r["id"],
                    magazin=r["magazin"] or "",
                    locatie=r.get("locatie"),
                    ora=r["ora_trimitere"],
                    completion_pct=r["completion_pct"],
                    firma=r["firma"],
                    has_photos=has_photos,
                )
            )

        team_leaders: list[TeamLeaderGroup] = []
        for tl_key in sorted(tl_map):
            months: list[VisitMonthGroup] = []
            for month_key in sorted(tl_map[tl_key], reverse=True):
                days: list[VisitDayGroup] = []
                for day_key in sorted(tl_map[tl_key][month_key], reverse=True):
                    visits = tl_map[tl_key][month_key][day_key]
                    days.append(VisitDayGroup(date=day_key, nr_vizite=len(visits), visits=visits))
                total_month = sum(d.nr_vizite for d in days)
                months.append(VisitMonthGroup(month=month_key, nr_vizite=total_month, days=days))
            total_tl = sum(m.nr_vizite for m in months)
            team_leaders.append(
                TeamLeaderGroup(team_leader=tl_key, nr_vizite=total_tl, months=months)
            )

        return VisitTreeResponse(team_leaders=team_leaders)

    async def _resolve_store_scope(
        self,
        filters: dict[str, str | None],
    ) -> tuple[dict[str, dict[str, str]], list[str] | None]:
        firma_values = _split_filter_values(filters.get("firma"))
        regional_values = _split_filter_values(filters.get("rm"))
        asm_values = _split_filter_values(filters.get("asm"))
        site_values = _split_filter_values(filters.get("magazin"))

        clauses = ["locatie NOT ILIKE 'TR %'"]
        params: list[object] = []

        def add_any_clause(column: str, values: list[str]) -> None:
            if not values:
                return
            params.append(values)
            clauses.append(f"{column} = ANY(${len(params)}::text[])")

        add_any_clause("firma", firma_values)
        add_any_clause("regional", regional_values)
        add_any_clause("asm", asm_values)
        add_any_clause("site_code", site_values)

        has_scope_filter = bool(firma_values or regional_values or asm_values or site_values)
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT site_code, firma, regional, asm, locatie
                FROM stores
                WHERE {" AND ".join(clauses)}
                """,
                *params,
            )

        metadata = {
            row["site_code"]: {
                "firma": row["firma"] or "",
                "regional": row["regional"] or "",
                "asm": row["asm"] or "",
                "locatie": row["locatie"] or "",
            }
            for row in rows
        }
        return metadata, list(metadata) if has_scope_filter else None

    async def get_visit_detail(self, visit_id: str) -> VisitDetail:
        loop = asyncio.get_running_loop()
        row = await loop.run_in_executor(None, self.repo.query_visit, visit_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Vizita nu a fost gasita.")

        photos = self.repo.get_photo_filenames(visit_id)

        def _b(v: Any) -> bool:
            return bool(v) if v is not None else False

        return VisitDetail(
            id=row["id"],
            data_raport=row["data_raport"],
            ora_trimitere=row["ora_trimitere"],
            firma=row["firma"],
            regional=row["regional"],
            asm=row["asm"],
            team_leader=row["team_leader_name"],
            magazin=row["magazin"],
            durata_vizita_ore=row["durata_vizita_ore"],
            curatenie=_b(row["curatenie"]),
            imagine=_b(row["imagine"]),
            uniforma=_b(row["uniforma"]),
            afise=_b(row["afise"]),
            produse_promo=_b(row["produse_promo"]),
            tpu=row["tpu"],
            sticla=row["sticla"],
            altele=row["altele"],
            avizat=_b(row["avizat"]),
            charisma=row["charisma"],
            casa=row["casa"],
            incarcari_epay=row["incarcari_epay"],
            incarcari_charisma=row["incarcari_charisma"],
            agent1_nume=row["agent1_nume"],
            agent1_perf=row["agent1_perf"],
            agent1_doi_pe_bon=row["agent1_doi_pe_bon"],
            agent1_focus=row["agent1_focus"],
            agent1_analiza=row["agent1_analiza"],
            agent1_plan=row["agent1_plan"],
            agent2_nume=row["agent2_nume"],
            agent2_perf=row["agent2_perf"],
            agent2_doi_pe_bon=row["agent2_doi_pe_bon"],
            agent2_focus=row["agent2_focus"],
            agent2_analiza=row["agent2_analiza"],
            agent2_plan=row["agent2_plan"],
            photos=photos,
            completion_pct=row["completion_pct"],
            notes=row["notes"],
        )
