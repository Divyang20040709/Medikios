import os
import uuid
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.database.session import get_db
from backend.app.api.auth_router import require_authenticated_roles
from backend.app.models.entities import (
    MedicalDocument, ExtractedEntity, Patient, Encounter, User,
    Medication, Observation, TimelineEvent, AuditLog
)
from backend.app.documents.processor import ClinicalDocumentProcessor
from backend.app.schemas.pydantic_models import OCRProcessingResult, ExtractedEntityItem

router = APIRouter(prefix="/api/documents", tags=["Medical Document Processing"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

processor = ClinicalDocumentProcessor()

# Document upload validation (mirrors the kiosk UI promise: PDF/JPG/PNG ≤ 25 MB)
ALLOWED_DOC_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
ALLOWED_DOC_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp",
    "image/tiff", "application/pdf", "application/octet-stream",
}

@router.post("/upload")
async def upload_document(
    patient_id: str = Form(...),
    encounter_id: Optional[str] = Form(None),
    document_type: str = Form("PRESCRIPTION"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads a physical prescription or lab report scan, performs OCR & information extraction,
    stores confidence metrics, and links extracted facts to the patient's longitudinal record.
    """
    pat_res = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = pat_res.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Same encounter id as the rest of the check-in flow must actually exist.
    if encounter_id:
        enc_res = await db.execute(select(Encounter).where(Encounter.id == encounter_id))
        if not enc_res.scalars().first():
            raise HTTPException(status_code=404, detail="Encounter not found")

    # ── Validate BEFORE writing anything to disk ─────────────────────────
    safe_name = os.path.basename(file.filename or "document")  # strip path traversal
    file_ext = os.path.splitext(safe_name)[1].lower()
    mime = (file.content_type or "").lower()
    if file_ext not in ALLOWED_DOC_EXTENSIONS or (mime and mime not in ALLOWED_DOC_MIMES):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file_ext or mime or 'unknown'}'. "
                   "Upload a PDF, JPG or PNG scan of the medical document.",
        )

    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{safe_name}")
    max_bytes = settings.MAX_DOCUMENT_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.MAX_DOCUMENT_UPLOAD_MB} MB upload limit.",
                    )
                buffer.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    except HTTPException:
        os.remove(file_path)  # do not keep rejected uploads
        raise

    # Create document record
    doc = MedicalDocument(
        patient_id=patient.id,
        encounter_id=encounter_id,
        document_type=document_type.upper(),
        file_name=file.filename,
        file_path=file_path,
        mime_type=file.content_type or "image/jpeg",
        ocr_status="PROCESSING"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Run OCR & Extraction Pipeline
    try:
        # Blocking OCR/PDF parsing runs in a worker thread with a hard timeout
        # so a slow or stuck engine can neither hang the event loop nor the kiosk.
        try:
            extracted = await asyncio.wait_for(
                asyncio.to_thread(processor.extract_blocking, file_path, doc.mime_type),
                timeout=settings.OCR_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            doc.ocr_status = "FAILED"
            await db.commit()
            raise HTTPException(
                status_code=504,
                detail="OCR processing timed out. The original document is preserved; retry or hand it to staff.",
            )

        if not extracted.raw_text.strip():
            # Unreadable scan / OCR engine unavailable: preserve the original
            # file, record the honest NO_TEXT status — extract nothing, invent
            # nothing. The patient-selected document_type is kept as-is.
            doc.ocr_status = "NO_TEXT"
            doc.ocr_text = ""
            doc.overall_confidence = 0.0
            db.add(AuditLog(
                actor_role="PATIENT",
                action="DOCUMENT_UPLOADED_NO_TEXT",
                entity_type="DOCUMENT",
                entity_id=doc.id,
                details={"type": doc.document_type, "file": doc.file_name}
            ))
            await db.commit()
            return {
                "document_id": doc.id,
                "document_type": doc.document_type,
                "ocr_status": "NO_TEXT",
                "overall_confidence": 0.0,
                "medications_count": 0,
                "observations_count": 0,
                "entities": [],
                "ocr_engine_available": processor.engine_available(),
                "message": "No readable text could be extracted from this scan. "
                           "The original document is saved for physician review.",
            }

        doc.ocr_status = "COMPLETED"
        doc.ocr_text = extracted.raw_text
        doc.overall_confidence = extracted.overall_confidence
        if extracted.document_type != "OTHER":
            # Only refine the type from actual document evidence, never from a
            # fabricated default.
            doc.document_type = extracted.document_type

        # Save extracted entities
        all_entities = []
        for m in extracted.medications:
            ent = ExtractedEntity(
                document_id=doc.id,
                entity_type="MEDICATION",
                entity_name=m["name"],
                entity_value=(f"{m['dosage']} {m['frequency']}").strip() or None,
                confidence=m["confidence"],
                source_snippet=m["source_snippet"],
                doctor_verified=m["doctor_verified"]
            )
            db.add(ent)
            all_entities.append(ent)

            # Also persist in patient's active medications table
            med = Medication(
                patient_id=patient.id,
                name=m["name"],
                dosage=m["dosage"],
                frequency=m["frequency"],
                provenance=f"Prescription OCR ({doc.file_name})"
            )
            db.add(med)

        for obs in extracted.observations:
            ent = ExtractedEntity(
                document_id=doc.id,
                entity_type="LAB_VALUE",
                entity_name=obs["test_name"],
                entity_value=f"{obs['test_value']} {obs['unit']}",
                confidence=obs["confidence"],
                source_snippet=obs["source_snippet"],
                doctor_verified=obs["doctor_verified"]
            )
            db.add(ent)
            all_entities.append(ent)

            # Persist in observations table
            db_obs = Observation(
                patient_id=patient.id,
                test_name=obs["test_name"],
                test_value=obs["test_value"],
                unit=obs["unit"],
                reference_range=obs["reference_range"],
                flag=obs["flag"],
                provenance=f"Lab Report OCR ({doc.file_name})"
            )
            db.add(db_obs)

        for diag in extracted.diagnoses:
            ent = ExtractedEntity(
                document_id=doc.id,
                entity_type="DIAGNOSIS",
                entity_name=diag["name"],
                confidence=diag["confidence"],
                source_snippet=diag["source_snippet"],
                doctor_verified=diag["doctor_verified"]
            )
            db.add(ent)
            all_entities.append(ent)

        for surg in extracted.surgeries:
            ent = ExtractedEntity(
                document_id=doc.id,
                entity_type="SURGERY",
                entity_name=surg["procedure_name"],
                confidence=surg["confidence"],
                source_snippet=surg.get("note", ""),
                doctor_verified=surg["doctor_verified"]
            )
            db.add(ent)
            all_entities.append(ent)

        # Create Timeline Event
        month_year = datetime.utcnow().strftime("%b %Y")
        timeline_event = TimelineEvent(
            patient_id=patient.id,
            event_date=month_year,
            event_type=doc.document_type,
            title=f"{doc.document_type.replace('_', ' ').title()}: {doc.file_name}",
            description=f"Digitized {len(extracted.medications)} medications, {len(extracted.observations)} lab readings.",
            document_id=doc.id,
            confidence=doc.overall_confidence
        )
        db.add(timeline_event)

        # Audit Log
        audit = AuditLog(
            actor_role="PATIENT",
            action="DOCUMENT_OCR_PROCESSED",
            entity_type="DOCUMENT",
            entity_id=doc.id,
            details={"type": doc.document_type, "confidence": doc.overall_confidence, "entities_count": len(all_entities)}
        )
        db.add(audit)
        await db.commit()

        return {
            "document_id": doc.id,
            "document_type": doc.document_type,
            "ocr_status": doc.ocr_status,
            "overall_confidence": doc.overall_confidence,
            "medications_count": len(extracted.medications),
            "observations_count": len(extracted.observations),
            "ocr_engine_available": processor.engine_available(),
            "message": "Extracted values are unverified OCR output until a physician confirms them.",
            "entities": [
                {
                    "type": e.entity_type,
                    "name": e.entity_name,
                    "value": e.entity_value,
                    "confidence": e.confidence,
                    "verified": e.doctor_verified
                }
                for e in all_entities
            ]
        }

    except HTTPException:
        # 4xx/5xx raised inside the pipeline (e.g. OCR timeout) — the original
        # document stays on disk; do not re-wrap it as a generic 500.
        raise
    except Exception as e:
        doc.ocr_status = "FAILED"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Document OCR processing error: {str(e)}")

@router.get("/patient/{patient_id}")
async def get_patient_documents(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """Phase 6: document metadata and OCR extracts are PHI — an authenticated
    DOCTOR/ADMIN token is required (was readable by anyone). Kiosk uploads
    stay anonymous by design; the kiosk UI keeps its own local copy."""
    res = await db.execute(
        select(MedicalDocument)
        .options(selectinload(MedicalDocument.extracted_entities))
        .where(MedicalDocument.patient_id == patient_id)
        .order_by(MedicalDocument.uploaded_at.desc())
    )
    docs = res.scalars().all()
    return [
        {
            "id": d.id,
            "file_name": d.file_name,
            "document_type": d.document_type,
            "ocr_status": d.ocr_status,
            "overall_confidence": d.overall_confidence,
            "uploaded_at": d.uploaded_at.isoformat(),
            "extracted_entities": [
                {
                    "id": e.id,
                    "entity_type": e.entity_type,
                    "entity_name": e.entity_name,
                    "entity_value": e.entity_value,
                    "confidence": e.confidence,
                    "doctor_verified": e.doctor_verified
                }
                for e in d.extracted_entities
            ]
        }
        for d in docs
    ]


@router.get("/file/{document_id}")
async def get_document_file(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """Controlled original-document download (Phase 6).

    Replaces the previous public /uploads static mount: the stored path is
    reduced to its basename (no traversal), the file must belong to an
    existing MedicalDocument row, and only an authenticated DOCTOR/ADMIN
    token can retrieve it. Served inline with the recorded MIME type.
    """
    res = await db.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))
    doc = res.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    safe_name = os.path.basename(doc.file_path or "")
    if not safe_name:
        raise HTTPException(status_code=404, detail="Document file not found")
    abs_path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Document file not found")

    # PHI access is itself an auditable event.
    db.add(AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="DOCUMENT_DOWNLOADED",
        entity_type="DOCUMENT",
        entity_id=doc.id,
        details={"file_name": doc.file_name, "accessed_by": current_user.full_name}
    ))
    await db.commit()

    return FileResponse(abs_path, media_type=doc.mime_type or "application/octet-stream")
