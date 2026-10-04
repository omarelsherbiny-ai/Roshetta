import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from agents.agents.ocr_extract import OCRProviderUnavailable, ocr_document_agent
from server.app.config import settings
from server.app.db.models import AuditLog, PrescriptionRecord, StoredUpload, has_permission
from server.app.db.session import get_db
from server.app.services.rbac import get_current_user, require_permission
from server.app.services.clock import utc_now_naive

router = APIRouter(prefix="/api/ocr", tags=["OCR"])

UPLOAD_DIR = Path(settings.STORAGE_LOCAL_DIR)
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = Path(__file__).resolve().parents[3] / UPLOAD_DIR
def _require_ocr_provider(document_type: str) -> None:
    try:
        ocr_document_agent(doc_type=document_type)
    except OCRProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _require_document_permission(document_type: str, ctx: dict) -> None:
    required_permission = {
        "prescription": "scan_prescription",
        "product": "manage_inventory",
        "invoice": "log_expense",
        "receipt": "log_expense",
    }.get(document_type)
    if not required_permission:
        raise HTTPException(status_code=422, detail="Unsupported document type.")
    if not has_permission(ctx["role"], required_permission, ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="Your role cannot access this document.")


@router.post("/scan", status_code=503)
async def scan_document(
    file: UploadFile = File(...),
    document_type: Literal["prescription", "invoice", "receipt"] = Form("receipt"),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    # Resolve availability before reading or persisting a potentially sensitive image.
    _require_document_permission(document_type, ctx)
    _require_ocr_provider(document_type)


@router.post("/product-box", status_code=503)
async def scan_product_box(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    _require_document_permission("product", ctx)
    _require_ocr_provider("product")


class PrescriptionReviewRequest(BaseModel):
    decision: Literal["reviewed", "held"]
    notes: str | None = Field(default=None, max_length=1000)


class PrescriptionRecordResponse(BaseModel):
    id: str
    doctor_name: str | None
    patient_name: str | None
    image_url: str | None
    safety_status: str
    review_decision: str | None
    review_notes: str | None
    reviewed_by: int | None
    reviewed_at: str | None
    created_at: str | None
    extracted: dict[str, Any]


class PrescriptionReviewResponse(BaseModel):
    success: bool
    id: str
    review_decision: Literal["reviewed", "held"]
    reviewed_at: str


@router.get("/prescriptions", response_model=list[PrescriptionRecordResponse])
async def list_prescriptions(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("scan_prescription")),
):
    result = await db.execute(
        select(PrescriptionRecord)
        .where(PrescriptionRecord.pharmacy_id == ctx["pharmacy_id"])
        .order_by(PrescriptionRecord.created_at.desc())
    )
    output = []
    for record in result.scalars().all():
        extracted = {}
        if record.extracted_json:
            try:
                extracted = json.loads(record.extracted_json)
            except (TypeError, ValueError):
                extracted = {}
        output.append({
            "id": record.id,
            "doctor_name": record.doctor_name,
            "patient_name": record.patient_name,
            "image_url": record.image_url,
            "safety_status": record.safety_status,
            "review_decision": record.review_decision,
            "review_notes": record.review_notes,
            "reviewed_by": record.reviewed_by,
            "reviewed_at": record.reviewed_at.isoformat() + "Z" if record.reviewed_at else None,
            "created_at": record.created_at.isoformat() + "Z" if record.created_at else None,
            "extracted": extracted,
        })
    return output


@router.post("/prescriptions/{prescription_id}/review", response_model=PrescriptionReviewResponse)
async def review_prescription(
    prescription_id: str,
    req: PrescriptionReviewRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("scan_prescription")),
):
    result = await db.execute(
        select(PrescriptionRecord).where(
            PrescriptionRecord.id == prescription_id,
            PrescriptionRecord.pharmacy_id == ctx["pharmacy_id"],
        )
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    extracted = {}
    try:
        extracted = json.loads(record.extracted_json or "{}")
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail="Prescription data cannot be reviewed because its saved extraction is invalid.")
    has_alerts = bool(extracted.get("safety_alerts")) or record.safety_status == "critical_alert"
    if has_alerts and req.decision == "reviewed":
        raise HTTPException(
            status_code=409,
            detail="This prescription has safety alerts. Record it as held while the alerts are unresolved.",
        )

    now = utc_now_naive()
    record.review_decision = req.decision
    record.review_notes = req.notes.strip() if req.notes and req.notes.strip() else None
    record.reviewed_by = ctx["user_id"]
    record.reviewed_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="REVIEW_PRESCRIPTION",
        entity_type="prescription",
        entity_id=record.id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name"),
        user_role=ctx["role"],
        details_json=json.dumps({"decision": req.decision, "has_alerts": has_alerts, "role_name": ctx.get("role_name")}, ensure_ascii=False),
        timestamp=now,
    ))
    await db.commit()
    return {
        "success": True,
        "id": record.id,
        "review_decision": record.review_decision,
        "reviewed_at": now.isoformat() + "Z",
    }


@router.get(
    "/uploads/{storage_key}",
    response_class=FileResponse,
    responses={200: {"content": {
        "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
        "image/png": {"schema": {"type": "string", "format": "binary"}},
        "image/webp": {"schema": {"type": "string", "format": "binary"}},
    }}},
)
async def get_private_upload(
    storage_key: str,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(StoredUpload).where(
            StoredUpload.storage_key == storage_key,
            StoredUpload.pharmacy_id == ctx["pharmacy_id"],
        )
    )
    upload = result.scalars().first()
    if not upload:
        raise HTTPException(status_code=404, detail="Image not found.")
    _require_document_permission(upload.document_type, ctx)
    path = UPLOAD_DIR / upload.storage_key
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file is unavailable.")
    return FileResponse(path, media_type=upload.content_type)