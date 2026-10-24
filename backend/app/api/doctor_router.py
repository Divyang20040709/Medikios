from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_db
from backend.app.api.auth_router import require_authenticated_roles
from backend.app.models.entities import (
    User, Patient, Encounter, ClinicalSummary, RedFlagAlert,
    MedicalDocument, ExtractedEntity, Medication, Observation,
    Allergy, Surgery, TimelineEvent, AuditLog
)
from backend.app.schemas.pydantic_models import (
    DoctorSummaryUpdate, DoctorMemoryGraphResponse
)
from backend.app.clinical.memory_graph import DoctorMemoryGraphBuilder
from backend.app.clinical.intake_time_model import IntakeTimeModel
from backend.app.clinical.streams import stream_for
from backend.app.services.llm_service import llm_service
from backend.app.models.entities import HistorySession

router = APIRouter(prefix="/api/doctor", tags=["Doctor Clinical Workspace"])

@router.get("/queue")
async def get_patient_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """
    Returns the real-time OPD patient queue sorted by clinical priority:
    EMERGENCY and URGENT triage cases appear first, followed by routine encounters.
    Finalized (signed & closed) consultations are included but always sorted to the
    end of the list, so the physician's active queue order is unchanged while the
    workstation can still list completed patients under its 'Completed' filter.
    RBAC (Phase 6): requires a valid DOCTOR or ADMIN bearer token — patient
    data is never served to anonymous callers.
    """
    query = (
        select(Encounter)
        .options(
            selectinload(Encounter.patient),
            selectinload(Encounter.clinical_summary),
            selectinload(Encounter.red_flag_alerts)
        )
        .where(
            Encounter.status.in_([
                "QUEUED", "INTAKE_IN_PROGRESS", "WAITING",
                "WAITING_CONSULTATION", "INTAKE_COMPLETED",
                "IN_CONSULTATION", "FINALIZED"
            ])
        )
        .order_by(
            # Custom sorting: EMERGENCY > URGENT > ROUTINE, then by created_at asc
            Encounter.priority.desc(),
            Encounter.created_at.asc()
        )
    )
    result = await db.execute(query)
    encounters = result.scalars().all()

    # Stream routing: each encounter belongs to the OPD stream the patient chose
    # at kiosk Step 4 (General & Modern Medicine vs Traditional / AYUSH). A
    # DOCTOR only receives patients of their own stream, so an AYUSH patient can
    # never land on a modern-medicine physician's queue and vice-versa. ADMIN
    # keeps the whole-hospital view. The stream is derived from the DB rows —
    # never from a client-supplied value.
    if current_user.role != "ADMIN":
        doctor_stream = stream_for(current_user.department)
        encounters = [enc for enc in encounters if stream_for(enc.department) == doctor_stream]

    queue_items = []
    for enc in encounters:
        if not enc.patient:
            continue

        # Sort key helper
        priority_weight = 3 if enc.priority == "EMERGENCY" else (2 if enc.priority == "URGENT" else 1)
        
        alerts = [
            {"rule": a.trigger_rule, "description": a.description, "priority": a.priority}
            for a in enc.red_flag_alerts if not a.acknowledged
        ]

        summary_preview = ""
        if enc.clinical_summary:
            summary_preview = enc.clinical_summary.chief_complaint or enc.clinical_summary.hpi or ""

        # Compute ML intake duration estimate
        est_duration = IntakeTimeModel.predict_intake_duration(
            age=enc.patient.age or 45,
            department=enc.department or "General Medicine",
            priority=enc.priority or "ROUTINE",
            symptom_count=1
        )

        queue_items.append({
            "encounter_id": enc.id,
            "patient_id": enc.patient.id,
            "token_number": enc.token_number,
            "patient_name": enc.patient.name,
            "age": enc.patient.age,
            "gender": enc.patient.gender,
            "mrn": enc.patient.mrn,
            "department": enc.department,
            "consultation_type": stream_for(enc.department).lower(),
            "status": enc.status,
            "priority": enc.priority,
            "priority_weight": priority_weight,
            "kiosk_id": enc.kiosk_id,
            "created_at": enc.created_at.isoformat() if enc.created_at else datetime.utcnow().isoformat(),
            "summary_preview": summary_preview[:120] + ("..." if len(summary_preview) > 120 else ""),
            "is_confirmed": enc.clinical_summary.is_confirmed_by_doctor if enc.clinical_summary else False,
            "estimated_intake_minutes": est_duration,
            "red_flag_alerts": alerts
        })

    # Sort in python to guarantee strict clinical order; finalized (completed)
    # encounters are always pushed to the bottom of the list.
    queue_items.sort(key=lambda x: (x["status"] == "FINALIZED", -x["priority_weight"], x["created_at"]))
    return queue_items

@router.get("/patient/{patient_id}")
async def get_patient_clinical_file(
    patient_id: str,
    encounter_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """
    Retrieves the complete clinical dossier for a patient:
    demographics, encounters, active draft summary, Doctor Memory Graph,
    medical timeline, and source document extractions with provenance.
    """
    pat_res = await db.execute(
        select(Patient)
        .options(
            selectinload(Patient.encounters).selectinload(Encounter.clinical_summary),
            selectinload(Patient.encounters).selectinload(Encounter.red_flag_alerts),
            selectinload(Patient.medications),
            selectinload(Patient.observations),
            selectinload(Patient.allergies),
            selectinload(Patient.surgeries),
            selectinload(Patient.timeline_events),
            selectinload(Patient.documents).selectinload(MedicalDocument.extracted_entities)
        )
        .where(Patient.id == patient_id)
    )
    patient = pat_res.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Find target encounter by ID if provided, otherwise latest
    target_encounter = None
    if encounter_id and patient.encounters:
        target_encounter = next((e for e in patient.encounters if e.id == encounter_id), None)
    if not target_encounter and patient.encounters:
        target_encounter = sorted(patient.encounters, key=lambda e: e.created_at or datetime.min)[-1]

    latest_encounter = target_encounter
    latest_summary = latest_encounter.clinical_summary if latest_encounter else None

    # Phase 7 (workflow step 8): the physician must be able to review the
    # patient's ORIGINAL answers next to the AI draft — verbatim HistoryResponses
    # for the target encounter, clearly separated from summaries and OCR output.
    patient_statements = []
    if latest_encounter:
        sess_res = await db.execute(
            select(HistorySession)
            .options(selectinload(HistorySession.responses))
            .where(HistorySession.encounter_id == latest_encounter.id)
        )
        history_session = sess_res.scalars().first()
        if history_session:
            patient_statements = [
                {
                    "id": r.id,
                    "section": r.section,
                    "question_text": r.question_text,
                    "answer_text": r.answer_text,
                    "input_method": r.input_method,
                    "confidence_score": r.confidence_score,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in history_session.responses
            ]

    # Flatten all extracted entities
    all_extracted = []
    for doc in patient.documents:
        all_extracted.extend(doc.extracted_entities)

    # Build Doctor Memory Graph
    memory_graph = DoctorMemoryGraphBuilder.build_graph(
        patient=patient,
        medications=patient.medications,
        observations=patient.observations,
        allergies=patient.allergies,
        surgeries=patient.surgeries,
        encounters=patient.encounters,
        extracted_entities=all_extracted
    )

    # Prepare timeline events
    timeline = [
        {
            "id": t.id,
            "date": t.event_date,
            "type": t.event_type,
            "title": t.title,
            "description": t.description,
            "confidence": t.confidence,
            "document_id": t.document_id
        }
        for t in patient.timeline_events
    ]

    # Prepare documents
    docs = [
        {
            "id": d.id,
            "file_name": d.file_name,
            "type": d.document_type,
            "ocr_status": d.ocr_status,
            "confidence": d.overall_confidence,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else datetime.utcnow().isoformat(),
            "extracted_entities": [
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "name": e.entity_name,
                    "value": e.entity_value,
                    "confidence": e.confidence,
                    "doctor_verified": e.doctor_verified,
                    "source_snippet": e.source_snippet
                }
                for e in d.extracted_entities
            ]
        }
        for d in patient.documents
    ]

    summary_data = None
    if latest_summary:
        summary_data = {
            "id": latest_summary.id,
            "chief_complaint": latest_summary.chief_complaint,
            "hpi": latest_summary.hpi,
            "past_medical_history": latest_summary.past_medical_history,
            "past_surgical_history": latest_summary.past_surgical_history,
            "drug_history": latest_summary.drug_history,
            "allergies": latest_summary.allergies,
            "family_history": latest_summary.family_history,
            "personal_history": latest_summary.personal_history,
            "review_of_systems": latest_summary.review_of_systems,
            "investigations": latest_summary.investigations,
            "red_flags": latest_summary.red_flags,
            "doctor_notes": latest_summary.doctor_notes,
            "is_confirmed": latest_summary.is_confirmed_by_doctor,
            "confirmed_at": latest_summary.confirmed_at.isoformat() if latest_summary.confirmed_at else None,
            "revision_count": latest_summary.revision_count
        }

    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "age": patient.age,
            "gender": patient.gender,
            "mrn": patient.mrn,
            "abha_id": patient.abha_id,
            "blood_group": patient.blood_group,
            "phone": patient.phone,
            "preferred_language": patient.preferred_language
        },
        "encounter": {
            "id": latest_encounter.id if latest_encounter else None,
            "token_number": latest_encounter.token_number if latest_encounter else None,
            "department": latest_encounter.department if latest_encounter else None,
            "status": latest_encounter.status if latest_encounter else None,
            "priority": latest_encounter.priority if latest_encounter else None,
            "red_flags": [
                {"rule": r.trigger_rule, "description": r.description, "priority": r.priority}
                for r in (latest_encounter.red_flag_alerts if latest_encounter else [])
            ]
        },
        "summary": summary_data,
        "patient_statements": patient_statements,
        "memory_graph": memory_graph.model_dump(),
        "timeline": timeline,
        "documents": docs,
        "medications": [
            {"id": m.id, "name": m.name, "dosage": m.dosage, "frequency": m.frequency, "provenance": m.provenance}
            for m in patient.medications
        ],
        "observations": [
            {"id": o.id, "test_name": o.test_name, "value": o.test_value, "unit": o.unit, "flag": o.flag, "ref": o.reference_range}
            for o in patient.observations
        ],
        "allergies": [
            {"id": a.id, "allergen": a.allergen, "reaction": a.reaction, "severity": a.severity}
            for a in patient.allergies
        ],
        "surgeries": [
            {"id": s.id, "procedure": s.procedure_name, "year": s.approximate_year, "notes": s.notes}
            for s in patient.surgeries
        ]
    }

@router.put("/summary/{summary_id}")
async def update_clinical_summary(
    summary_id: str,
    update: DoctorSummaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR"))
):
    """
    Allows the physician to edit the AI-generated draft summary, record clinical modifications,
    and officially confirm/sign the final clinical record with full audit provenance.
    RBAC (Phase 6): requires a valid DOCTOR bearer token — anonymous and
    non-clinical callers are rejected (401/403); ADMIN may not sign off.
    """
    res = await db.execute(select(ClinicalSummary).where(ClinicalSummary.id == summary_id))
    summary = res.scalars().first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    # Track changes for provenance without overwriting original patient answers
    old_state = {
        "chief_complaint": summary.chief_complaint,
        "hpi": summary.hpi,
        "doctor_notes": summary.doctor_notes
    }

    if update.chief_complaint is not None:
        summary.chief_complaint = update.chief_complaint
    if update.hpi is not None:
        summary.hpi = update.hpi
    if update.past_medical_history is not None:
        summary.past_medical_history = update.past_medical_history
    if update.past_surgical_history is not None:
        summary.past_surgical_history = update.past_surgical_history
    if update.drug_history is not None:
        summary.drug_history = update.drug_history
    if update.allergies is not None:
        summary.allergies = update.allergies
    if update.doctor_notes is not None:
        summary.doctor_notes = update.doctor_notes

    summary.revision_count += 1

    if update.confirm:
        # Duplicate sign-off guard: an encounter that is already FINALIZED
        # must not be re-finalized (safe against double clicks / replay).
        enc_res = await db.execute(select(Encounter).where(Encounter.id == summary.encounter_id))
        encounter = enc_res.scalars().first()
        if encounter and encounter.status == "FINALIZED":
            raise HTTPException(status_code=409, detail="Encounter is already finalized and signed.")

        summary.is_confirmed_by_doctor = True
        summary.confirmed_at = datetime.utcnow()

        # Update encounter status to FINALIZED
        if encounter:
            encounter.status = "FINALIZED"
            encounter.completed_at = datetime.utcnow()

    # Audit log — actor is guaranteed authenticated by the strict guard.
    audit = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="DOCTOR_CONFIRMED" if update.confirm else "DOCTOR_EDITED_SUMMARY",
        entity_type="SUMMARY",
        entity_id=summary.id,
        details={
            "revision": summary.revision_count,
            "confirmed": summary.is_confirmed_by_doctor,
            "signed_by": current_user.full_name,
            "previous_state": old_state
        }
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "SUCCESS",
        "summary_id": summary.id,
        "revision_count": summary.revision_count,
        "is_confirmed": summary.is_confirmed_by_doctor,
        "confirmed_at": summary.confirmed_at.isoformat() if summary.confirmed_at else None
    }

@router.post("/encounter/{encounter_id}/summary")
async def create_or_update_encounter_summary(
    encounter_id: str,
    update: DoctorSummaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR"))
):
    """
    Creates or updates a clinical summary directly for an encounter.
    RBAC (Phase 6): requires a valid DOCTOR bearer token — anonymous and
    non-clinical callers are rejected (401/403); ADMIN may not sign off.
    """
    enc_res = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.clinical_summary), selectinload(Encounter.patient))
        .where(Encounter.id == encounter_id)
    )
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    summary = encounter.clinical_summary
    if not summary:
        summary = ClinicalSummary(
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            chief_complaint=update.chief_complaint or "General Clinical Consultation",
            hpi=update.hpi or "",
            doctor_notes=update.doctor_notes or "",
            past_medical_history=update.past_medical_history or [],
            past_surgical_history=update.past_surgical_history or [],
            drug_history=update.drug_history or [],
            allergies=update.allergies or [],
            revision_count=1
        )
        db.add(summary)
        # Flush so summary.id exists before the audit log references it
        # (prevents NOT NULL IntegrityError -> 500 on first sign-off).
        await db.flush()
    else:
        if update.chief_complaint is not None:
            summary.chief_complaint = update.chief_complaint
        if update.hpi is not None:
            summary.hpi = update.hpi
        if update.doctor_notes is not None:
            summary.doctor_notes = update.doctor_notes
        if update.past_medical_history is not None:
            summary.past_medical_history = update.past_medical_history
        if update.past_surgical_history is not None:
            summary.past_surgical_history = update.past_surgical_history
        if update.drug_history is not None:
            summary.drug_history = update.drug_history
        if update.allergies is not None:
            summary.allergies = update.allergies
        summary.revision_count += 1

    if update.confirm:
        # Duplicate sign-off guard: refuse to re-finalize an already closed encounter.
        if encounter.status == "FINALIZED":
            raise HTTPException(status_code=409, detail="Encounter is already finalized and signed.")
        summary.is_confirmed_by_doctor = True
        summary.confirmed_at = datetime.utcnow()
        encounter.status = "FINALIZED"
        encounter.completed_at = datetime.utcnow()

    audit = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="DOCTOR_CONFIRMED" if update.confirm else "DOCTOR_UPDATED_SUMMARY",
        entity_type="SUMMARY",
        entity_id=summary.id,
        details={
            "encounter_id": encounter_id,
            "confirmed": summary.is_confirmed_by_doctor,
            "signed_by": current_user.full_name
        }
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "SUCCESS",
        "summary_id": summary.id,
        "revision_count": summary.revision_count,
        "is_confirmed": summary.is_confirmed_by_doctor,
        "confirmed_at": summary.confirmed_at.isoformat() if summary.confirmed_at else None
    }

@router.post("/verify-entity/{entity_id}")
async def verify_extracted_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR"))
):
    """
    Physician confirms or marks an OCR-extracted clinical entity as verified.
    RBAC (Phase 6): requires a valid DOCTOR bearer token — verification is a
    clinical act and can no longer be performed anonymously. Every
    verification is written to the audit trail.
    """
    res = await db.execute(select(ExtractedEntity).where(ExtractedEntity.id == entity_id))
    entity = res.scalars().first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.doctor_verified = True
    entity.confidence = 1.0

    db.add(AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="OCR_ENTITY_VERIFIED",
        entity_type="EXTRACTED_ENTITY",
        entity_id=entity.id,
        details={
            "entity_name": entity.entity_name,
            "entity_type": entity.entity_type,
            "verified_by": current_user.full_name
        }
    ))
    await db.commit()

    return {"status": "VERIFIED", "entity_id": entity.id, "confidence": 1.0}

@router.post("/encounter/{encounter_id}/generate-llm-summary")
async def generate_llm_summary_on_demand(
    encounter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR"))
):
    """
    On-demand physician-triggered LLM synthesis calling OpenRouter (NVIDIA Nemotron 3 Ultra)
    directly on live encounter context and updating the clinical summary draft.
    """
    enc_res = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.patient))
        .where(Encounter.id == encounter_id)
    )
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    # Clinical safety (Phase 6): an AI re-synthesis must never be attempted
    # against a physician-signed record — checked BEFORE spending an LLM call.
    signed_res = await db.execute(
        select(ClinicalSummary).where(
            ClinicalSummary.encounter_id == encounter_id,
            ClinicalSummary.is_confirmed_by_doctor == True
        )
    )
    if signed_res.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Clinical summary is already physician-confirmed; AI regeneration cannot overwrite a signed record."
        )

    patient = encounter.patient

    # Fetch interview responses
    sess_res = await db.execute(
        select(HistorySession)
        .options(selectinload(HistorySession.responses))
        .where(HistorySession.encounter_id == encounter_id)
    )
    session = sess_res.scalars().first()
    resp_dicts = []
    if session and session.responses:
        resp_dicts = [{"section": r.section, "question_text": r.question_text, "answer_text": r.answer_text} for r in session.responses]

    # Fetch documents. QA BUG-001: MedicalDocument has no `medications`/
    # `observations` relationships — OCR output is stored in ExtractedEntity
    # rows keyed by entity_type, so the LLM context is built from
    # `extracted_entities` (this previously raised AttributeError -> HTTP 500).
    doc_res = await db.execute(
        select(MedicalDocument)
        .options(selectinload(MedicalDocument.extracted_entities))
        .where(MedicalDocument.patient_id == patient.id)
    )
    docs = doc_res.scalars().all()
    docs_extracted = []
    for d in docs:
        medications = []
        observations = []
        for e in (d.extracted_entities or []):
            if e.entity_type == "MEDICATION":
                medications.append({"name": e.entity_name, "dosage": e.entity_value or "", "frequency": ""})
            elif e.entity_type == "LAB_VALUE":
                observations.append({"test_name": e.entity_name, "test_value": e.entity_value or "", "unit": "", "flag": ""})
        docs_extracted.append({
            "document_type": d.document_type,
            "medications": medications,
            "observations": observations
        })

    patient_info = {"name": patient.name, "age": patient.age, "gender": patient.gender, "mrn": patient.mrn}

    # Call LLM Service (OpenRouter NVIDIA Nemotron 3 Ultra)
    # Phase 6: no patient-identifying data in server logs.
    summary_data = await llm_service.generate_clinical_summary(
        patient_info=patient_info,
        intake_responses=resp_dicts,
        documents_extracted=docs_extracted,
        timeline_events=[]
    )

    # Check if summary already exists for this encounter
    sum_res = await db.execute(
        select(ClinicalSummary).where(ClinicalSummary.encounter_id == encounter_id)
    )
    summary = sum_res.scalars().first()

    if not summary:
        summary = ClinicalSummary(
            encounter_id=encounter.id,
            patient_id=patient.id,
            chief_complaint=summary_data.chief_complaint,
            hpi=summary_data.hpi,
            past_medical_history=summary_data.past_medical_history,
            past_surgical_history=summary_data.past_surgical_history,
            drug_history=summary_data.drug_history,
            allergies=summary_data.allergies,
            family_history=summary_data.family_history,
            personal_history=summary_data.personal_history,
            review_of_systems=summary_data.review_of_systems,
            investigations=summary_data.investigations,
            red_flags=summary_data.red_flags,
            doctor_notes="Physician-initiated LLM clinical re-synthesis via OpenRouter (NVIDIA Nemotron 3 Ultra)."
        )
        db.add(summary)
        await db.flush()
    else:
        summary.chief_complaint = summary_data.chief_complaint
        summary.hpi = summary_data.hpi
        summary.past_medical_history = summary_data.past_medical_history
        summary.past_surgical_history = summary_data.past_surgical_history
        summary.drug_history = summary_data.drug_history
        summary.allergies = summary_data.allergies
        summary.family_history = summary_data.family_history
        summary.personal_history = summary_data.personal_history
        summary.review_of_systems = summary_data.review_of_systems
        summary.investigations = summary_data.investigations
        summary.red_flags = summary_data.red_flags
        summary.revision_count += 1
        summary.doctor_notes = "Refreshed via OpenRouter NVIDIA Nemotron 3 Ultra synthesis."

    audit = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="LLM_SUMMARY_REGENERATED",
        entity_type="SUMMARY",
        entity_id=summary.id,
        details={"encounter_id": encounter_id, "model": llm_service.model, "openrouter_configured": bool(llm_service.api_key)}
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "SUCCESS",
        "encounter_id": encounter_id,
        "summary": {
            "id": summary.id,
            "chief_complaint": summary.chief_complaint,
            "hpi": summary.hpi,
            "past_medical_history": summary.past_medical_history,
            "past_surgical_history": summary.past_surgical_history,
            "drug_history": summary.drug_history,
            "allergies": summary.allergies,
            "family_history": summary.family_history,
            "investigations": summary.investigations,
            "red_flags": summary.red_flags,
            "doctor_notes": summary.doctor_notes
        },
        "llm_engine": {
            "model": llm_service.model,
            "openrouter_active": bool(llm_service.api_key)
        }
    }
