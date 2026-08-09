from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from models import (
    VisitDetail,
    VisitReportResponse,
    VisitTreeResponse,
)
from composition import build_visits_service
from schemas.common import MonthStr
from services.visits_report import VisitsReportService

router = APIRouter(prefix="/api/visits-report", tags=["visits-report"])

get_visits_service = build_visits_service


@router.get("", response_model=VisitReportResponse)
async def get_visits_report(
    month: MonthStr = Query(...),
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitReportResponse:
    return await svc.get_visits_report(month, firma, rm, asm, magazin)


@router.get("/tree", response_model=VisitTreeResponse)
async def get_visits_tree(
    month: MonthStr = Query(...),
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitTreeResponse:
    return await svc.get_visits_tree(firma, rm, asm, magazin, month)


@router.get("/visit/{visit_id}", response_model=VisitDetail)
async def get_visit_detail(
    visit_id: str,
    svc: VisitsReportService = Depends(get_visits_service),
) -> VisitDetail:
    return await svc.get_visit_detail(visit_id)


@router.get(
    "/photo/{visit_id}/{filename}",
    responses={
        200: {
            "content": {
                "image/*": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
async def get_visit_photo(
    visit_id: str,
    filename: str,
    svc: VisitsReportService = Depends(get_visits_service),
) -> FileResponse:
    if (
        not visit_id
        or not filename
        or Path(visit_id).name != visit_id
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or "\\" in visit_id
        or ".." in visit_id
        or ".." in filename
    ):
        raise HTTPException(status_code=400, detail="Invalid path.")

    visit = await svc.get_visit_detail(visit_id)
    if filename not in visit.photos:
        raise HTTPException(status_code=404, detail="Poza nu a fost gasita.")

    raw_photo_path = svc.photo_path(visit_id, filename)
    if raw_photo_path.is_symlink():
        raise HTTPException(status_code=404, detail="Poza nu a fost gasita.")
    photo_path = raw_photo_path.resolve()
    images_dir = svc.images_dir_path().resolve()
    if not photo_path.is_relative_to(images_dir):
        raise HTTPException(status_code=400, detail="Invalid path.")
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Poza nu a fost gasita.")

    mime, _ = mimetypes.guess_type(filename)
    return FileResponse(photo_path, media_type=mime or "image/jpeg")
