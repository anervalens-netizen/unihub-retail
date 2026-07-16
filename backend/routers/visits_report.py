from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from models import (
    VisitDetail,
    VisitReportResponse,
    VisitTreeResponse,
)
from repositories.visits_report import VisitsReportRepository
from repositories.visits_report_postgres import VisitsReportPostgresRepository
from services.visits_report import VisitsReportService

router = APIRouter(prefix="/api/visits-report", tags=["visits-report"])

async def get_visits_service() -> VisitsReportService:
    repo = VisitsReportRepository()
    return VisitsReportService(repo, VisitsReportPostgresRepository())


@router.get("", response_model=VisitReportResponse)
async def get_visits_report(
    month: str = Query(...),
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitReportResponse:
    return await svc.get_visits_report(month, firma, rm, asm, magazin)


@router.get("/tree", response_model=VisitTreeResponse)
async def get_visits_tree(
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitTreeResponse:
    return await svc.get_visits_tree(firma, rm, asm, magazin)


@router.get("/visit/{visit_id}", response_model=VisitDetail)
async def get_visit_detail(
    visit_id: str,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitDetail:
    return await svc.get_visit_detail(visit_id)


@router.get("/photo/{visit_id}/{filename}")
async def get_visit_photo(
    visit_id: str,
    filename: str,
    svc: VisitsReportService = Depends(get_visits_service),
) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in visit_id or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid path.")

    photo_path = svc.repo.photo_path(visit_id, filename).resolve()
    images_dir = svc.repo.images_dir_path().resolve()
    if not str(photo_path).startswith(str(images_dir)):
        raise HTTPException(status_code=400, detail="Invalid path.")
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Poza nu a fost gasita.")

    mime, _ = mimetypes.guess_type(filename)
    return FileResponse(photo_path, media_type=mime or "image/jpeg")
