from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile

from auth import AuthClaims
from db.connection import get_pool
from models import ImportHistoryEntry, ImportJobStatus, ImportResponse, PromoActualImportResponse, SalesGenerationPromotionRequest
from permissions import require_import_admin
from repositories.erp_reconciliation import ErpReconciliationRepository
from repositories.imports import ImportsRepository
from rate_limits import SALES_IMPORT_UPLOAD_LIMIT, rate_limit
from schemas.erp_reconciliation import ErpReconciliationResponse
from services.erp_reconciliation import ErpReconciliationService
from services.imports import ImportsService

router = APIRouter(prefix="/api/import", tags=["imports"])

async def get_imports_service() -> ImportsService:
    pool = await get_pool()
    repo = ImportsRepository(pool)
    return ImportsService(repo, pool)


async def get_erp_reconciliation_service() -> ErpReconciliationService:
    pool = await get_pool()
    return ErpReconciliationService(ErpReconciliationRepository(pool), pool)


@router.post("/sales", response_model=ImportJobStatus)
async def upload_sales_file(
    file: UploadFile = File(...),
    cutoff_date: date = Form(...),
    claims: AuthClaims = Depends(require_import_admin),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ImportsService = Depends(get_imports_service),
) -> ImportJobStatus:
    return await svc.import_sales(
        file,
        cutoff_date=cutoff_date,
        requested_by_sub=claims.sub,
    )


@router.post("/sales/{snapshot_id}/promote", response_model=ImportJobStatus)
async def promote_sales_generation(
    snapshot_id: int,
    payload: SalesGenerationPromotionRequest,
    claims: AuthClaims = Depends(require_import_admin),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ImportsService = Depends(get_imports_service),
) -> ImportJobStatus:
    return await svc.promote_sales_generation(
        snapshot_id=snapshot_id,
        request=payload,
        requested_by_sub=claims.sub,
    )


@router.post("/promo-actuals", response_model=PromoActualImportResponse)
async def upload_promo_actuals_file(
    import_month: str = Form(...),
    cutoff_date: date = Form(...),
    file: UploadFile = File(...),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ImportsService = Depends(get_imports_service),
) -> PromoActualImportResponse:
    return await svc.import_promo_actuals(
        file=file,
        import_month=import_month,
        cutoff_date=cutoff_date,
    )


@router.post("/erp-reconciliation", response_model=ErpReconciliationResponse)
async def reconcile_erp_report_file(
    import_month: str = Form(...),
    file: UploadFile = File(...),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ErpReconciliationService = Depends(get_erp_reconciliation_service),
) -> ErpReconciliationResponse:
    return await svc.reconcile(file=file, import_month=import_month)


@router.get("/jobs/{job_id}", response_model=ImportJobStatus)
async def get_import_job_status(
    job_id: str,
    svc: ImportsService = Depends(get_imports_service),
) -> ImportJobStatus:
    return await svc.get_import_job_status(job_id)


@router.get("/history", response_model=list[ImportHistoryEntry])
async def get_import_history(
    svc: ImportsService = Depends(get_imports_service),
) -> list[ImportHistoryEntry]:
    return await svc.get_import_history()
