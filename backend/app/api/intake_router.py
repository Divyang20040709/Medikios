import random
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_db
from backend.app.models.entities import (
    Patient, User, Encounter, ConsentRecord, HistorySession, HistoryResponse,
    RedFlagAlert, ClinicalSummary, AuditLog
)
from backend.app.schemas.pydantic_models import (
    PatientRegisterRequest, AnswerSubmit, ClinicalQuestion, ConsentCreate
)
from backend.app.clinical.ontology import (
    SUPPORTED_LANGUAGES, COMPLAINT_CATEGORIES, QUESTION_TREES, COMMON_QUESTIONS
)
from backend.app.clinical.red_flags import RedFlagEngine
from backend.app.clinical.streams import department_for_stream, stream_for
from backend.app.services.llm_service import llm_service
from backend.app.services.followup_service import generate_followups
from backend.app.services.token_service import next_opd_token, opd_token_guard

router = APIRouter(prefix="/api/intake", tags=["Patient Kiosk Intake"])

@router.get("/languages")
async def get_languages():
    return SUPPORTED_LANGUAGES

@router.get("/complaints")
async def get_complaint_categories():
    return COMPLAINT_CATEGORIES

class ComplaintClassificationRequest(BaseModel):
    text: str
    patient_id: Optional[str] = None

@router.post("/classify-complaint")
async def classify_complaint_endpoint(req: ComplaintClassificationRequest):
    """
    Uses the trained Scikit-Learn TF-IDF classifier and Indic clinical lexicon
    to classify chief complaints, recommending the optimal OPD department and detecting red-flag priority.
    """
    return RedFlagEngine.classify_complaint_ml(req.text)

@router.post("/init")
@router.post("/initialize")
async def initialize_intake(req: PatientRegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Initializes a patient intake session, creating or matching the patient,
    recording DPDP-compliant consent, and creating an active Encounter with an OPD token.
    """
    patient = None
    if req.abha_id:
        res = await db.execute(select(Patient).where(Patient.abha_id == req.abha_id))
        patient = res.scalars().first()

    if not patient and req.phone:
        res = await db.execute(select(Patient).where(Patient.phone == req.phone))
        patient = res.scalars().first()

    if patient:
        # If matching patient exists, update with latest intake details if provided
        if req.name and req.name.strip():
            patient.name = req.name.strip()
        if req.age:
            patient.age = req.age
        if req.gender:
            patient.gender = req.gender
        if req.preferred_language:
            patient.preferred_language = req.preferred_language
        if req.blood_group:
            patient.blood_group = req.blood_group
        if req.emergency_contact:
            patient.emergency_contact = req.emergency_contact
        await db.commit()
        await db.refresh(patient)
    else:
        mrn_num = random.randint(1000, 9999)
        patient = Patient(
            name=req.name.strip() if req.name else "Patient",
            age=req.age,
            gender=req.gender,
            phone=req.phone,
            abha_id=req.abha_id or f"91-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}",
            aadhaar_last4=req.aadhaar_last4,
            blood_group=req.blood_group,
            emergency_contact=req.emergency_contact,
            preferred_language=req.preferred_language,
            mrn=f"MRN-2026-{mrn_num}"
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)

    # QA-07: token numbers used to be drawn at random from 101-299 with no
    # collision check. "max + 1" alone still raced under concurrent check-ins,
    # so allocate → insert → commit now happens inside one guarded window, and a
    # UNIQUE index on encounters.token_number backs it up.
    async with opd_token_guard(db):
        token_number = await next_opd_token(db)
        encounter = Encounter(
            patient_id=patient.id,
            department=req.department or "General Medicine",
            token_number=token_number,
            status="INTAKE_IN_PROGRESS",
            priority="ROUTINE"
        )
        db.add(encounter)
        await db.commit()
        await db.refresh(encounter)

    # Record Consent — PENDING (Phase 7): the consent screen (kiosk Step 3) is
    # shown AFTER check-in, so nothing may be recorded as granted here. The
    # explicit decision arrives via POST /api/intake/consent.
    consent = ConsentRecord(
        encounter_id=encounter.id,
        patient_id=patient.id,
        purpose="Clinical OPD Intake and AI-Assisted History Taking",
        granted=False,
        granted_at=None,
        audio_consent_granted=False
    )
    db.add(consent)

    # Initialize History Session
    history_session = HistorySession(
        encounter_id=encounter.id,
        language=req.preferred_language,
        current_step="COMPLAINT_SELECTION"
    )
    db.add(history_session)

    # Audit log
    audit = AuditLog(
        actor_role="PATIENT",
        action="INTAKE_INITIALIZED",
        entity_type="ENCOUNTER",
        entity_id=encounter.id,
        details={"token": token_number, "mrn": patient.mrn}
    )
    db.add(audit)
    await db.commit()

    return {
        "encounter_id": encounter.id,
        "session_id": history_session.id,
        "patient_id": patient.id,
        "name": patient.name,
        "token_number": token_number,
        "mrn": patient.mrn,
        "abha_id": patient.abha_id,
        "language": req.preferred_language,
        "consent_status": "PENDING"
    }

@router.post("/consent")
async def submit_consent(req: ConsentCreate, db: AsyncSession = Depends(get_db)):
    """
    Records the patient's EXPLICIT consent decision from the kiosk consent
    screen (Phase 7). Idempotent: repeated identical submissions update the
    same ConsentRecord and only write an audit entry when the decision
    actually changes. Consent belongs to exactly one encounter/patient pair —
    a mismatched pair is refused (400) so one session cannot forge consent on
    another patient's encounter.
    """
    enc_res = await db.execute(
        select(Encounter).where(Encounter.id == req.encounter_id)
    )
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    if encounter.patient_id != req.patient_id:
        raise HTTPException(
            status_code=400,
            detail="Encounter does not belong to this patient."
        )

    consent_res = await db.execute(
        select(ConsentRecord).where(ConsentRecord.encounter_id == req.encounter_id)
    )
    consent = consent_res.scalars().first()
    previous = None if consent is None else consent.granted

    if not consent:
        consent = ConsentRecord(
            encounter_id=req.encounter_id,
            patient_id=req.patient_id,
            purpose=req.purpose,
            granted=req.granted,
            audio_consent_granted=req.audio_consent and req.granted,
            granted_at=datetime.utcnow() if req.granted else None,
        )
        db.add(consent)
    else:
        consent.purpose = req.purpose
        consent.data_categories = req.data_categories
        consent.granted = req.granted
        consent.audio_consent_granted = req.audio_consent and req.granted
        consent.revoked = False if req.granted else consent.revoked
        if req.granted and previous is not True:
            consent.granted_at = datetime.utcnow()

    # Audit an explicit decision: whenever it changes the recorded state, or
    # when it is the patient's FIRST decision on this encounter — a decline
    # from the pending (False) state changes nothing boolean, but must still
    # be traceable. Repeated identical submissions stay audit-silent.
    prior_decision_res = await db.execute(select(AuditLog.id).where(
        AuditLog.entity_id == req.encounter_id,
        AuditLog.action.in_(["CONSENT_GRANTED", "CONSENT_DECLINED"])
    ))
    first_decision = prior_decision_res.scalars().first() is None
    if previous != req.granted or (not req.granted and first_decision):
        db.add(AuditLog(
            actor_role="PATIENT",
            action="CONSENT_GRANTED" if req.granted else "CONSENT_DECLINED",
            entity_type="ENCOUNTER",
            entity_id=req.encounter_id,
            details={"audio_consent": consent.audio_consent_granted, "purpose": req.purpose}
        ))
    await db.commit()

    return {
        "status": "SUCCESS",
        "encounter_id": req.encounter_id,
        "consent_status": "GRANTED" if req.granted else "DECLINED",
        "audio_consent_granted": consent.audio_consent_granted,
    }

class ConsultationTypeUpdate(BaseModel):
    consultation_type: str  # "modern" | "ayush"


@router.post("/{encounter_id}/consultation-type")
async def set_consultation_type(
    encounter_id: str,
    req: ConsultationTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Records the patient's kiosk Step-4 consultation stream on the encounter.

    This is the appointment-routing decision: the encounter becomes an
    assignment to the matching physician stream — General & Modern Medicine or
    Traditional Medicine / AYUSH — and therefore appears only in that
    physician's queue (GET /api/doctor/queue). Public like the rest of the kiosk
    intake flow: it accepts only an encounter the kiosk already created and an
    allow-listed stream value, and returns no clinical data.
    """
    requested = (req.consultation_type or "").strip().lower()
    if requested not in ("modern", "ayush"):
        raise HTTPException(
            status_code=422,
            detail="consultation_type must be 'modern' or 'ayush'."
        )

    enc_res = await db.execute(select(Encounter).where(Encounter.id == encounter_id))
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    encounter.department = department_for_stream(requested, encounter.department)
    await db.commit()
    await db.refresh(encounter)

    # The physician this patient is now queued for: first DOCTOR of that stream.
    stream = stream_for(encounter.department)
    doctors = (
        await db.execute(select(User).where(User.role == "DOCTOR"))
    ).scalars().all()
    assigned = next((d for d in doctors if stream_for(d.department) == stream), None)

    return {
        "encounter_id": encounter.id,
        "consultation_type": stream.lower(),
        "department": encounter.department,
        "assigned_doctor": (
            {"name": assigned.full_name, "department": assigned.department}
            if assigned else None
        ),
    }


@router.get("/questions/{complaint_id}")
async def get_questions_for_complaint(complaint_id: str, language: str = "en"):
    """
    Returns the adaptive question tree for the selected clinical complaint,
    including common past medical questions, localized in the patient's language.
    """
    cid = complaint_id.upper()
    specific_questions = QUESTION_TREES.get(cid, QUESTION_TREES["GENERAL_OPD"])
    all_questions: List[ClinicalQuestion] = list(specific_questions) + list(COMMON_QUESTIONS)

    # Localize question texts if translation available
    localized = []
    for q in all_questions:
        q_dict = q.model_dump()
        if language in q.translations and q.translations[language]:
            q_dict["display_question"] = q.translations[language]
        else:
            q_dict["display_question"] = q.question_en
        localized.append(q_dict)

    return {
        "complaint_id": cid,
        "language": language,
        "total_questions": len(localized),
        "questions": localized
    }

class FollowupQuestionsRequest(BaseModel):
    session_id: Optional[str] = None
    language: str = "en"
    max_questions: int = 3
    # In-progress interview answers (used when the patient has not yet
    # submitted; merged with persisted HistoryResponses when session_id given)
    answers: Optional[List[Dict[str, str]]] = None

@router.post("/followup-questions")
async def followup_questions(req: FollowupQuestionsRequest, db: AsyncSession = Depends(get_db)):
    """
    Generates 1–4 patient-friendly follow-up questions from the patient's own
    interview answers, using the free LOCAL LLM when provisioned and falling
    back to predefined clinically-reviewed ontology questions otherwise.

    Red-flag escalation is computed by the deterministic RedFlagEngine and is
    returned alongside the questions — model output can never suppress it.
    """
    statements: List[Dict[str, str]] = []
    answered_sections: List[str] = []

    for a in (req.answers or []):
        text = (a.get("answer_text") or "").strip()
        if text:
            statements.append({
                "question_text": a.get("question_text", ""),
                "answer_text": text,
                "section_id": a.get("section_id") or "",
            })
            if a.get("section_id"):
                answered_sections.append(a["section_id"])

    if req.session_id:
        sess_res = await db.execute(
            select(HistorySession).where(HistorySession.id == req.session_id)
        )
        session = sess_res.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        resp_res = await db.execute(
            select(HistoryResponse).where(HistoryResponse.session_id == session.id)
        )
        for r in resp_res.scalars().all():
            if (r.answer_text or "").strip():
                statements.append({
                    "question_text": r.question_text or "",
                    "answer_text": r.answer_text,
                    "section_id": r.section or "",
                })
                answered_sections.append(r.section or "")

    if not statements:
        raise HTTPException(
            status_code=400,
            detail="No interview answers available to base follow-up questions on."
        )

    # Deterministic safety layer — independent of, and never filtered by, the LLM.
    # 1) Evaluate with the REAL section ids (matches /answer behaviour).
    # 2) The kiosk UI sends free-text SOCRATES blobs (CHIEF_COMPLAINT / SOCRATES /
    #    FOLLOW_UP) that no rule key reads directly, so scan EVERY answer text
    #    across all rule sections too. Deduplicating by rule name means this
    #    can only ADD escalation, never remove it.
    rf_scan_sections = (
        "SITE", "RADIATION", "CHARACTER", "ASSOCIATED_SYMPTOMS",
        "RESPIRATORY_SYMPTOMS", "INHALER_USAGE", "ABDOMINAL_ASSOCIATED",
        "FEVER_PATTERN", "DIABETES_COMPLICATIONS",
    )
    red_flags: List[Dict[str, Any]] = []
    seen_rules = set()

    def _collect(rf_list) -> None:
        for rf in rf_list:
            if rf.is_triggered and rf.rule_name not in seen_rules:
                seen_rules.add(rf.rule_name)
                red_flags.append({
                    "title": rf.alert_title,
                    "priority": rf.priority,
                    "description": rf.description,
                })

    _collect(RedFlagEngine.evaluate_symptoms([
        {"section": s["section_id"], "answer_text": s["answer_text"]} for s in statements
    ]))
    for s in statements:
        _collect(RedFlagEngine.evaluate_symptoms([
            {"section": sec, "answer_text": s["answer_text"]} for sec in rf_scan_sections
        ]))

    result = await generate_followups(
        statements=statements,
        language=req.language,
        max_questions=req.max_questions,
        answered_sections=answered_sections,
    )
    result["red_flags"] = red_flags
    result["escalation_required"] = len(red_flags) > 0
    return result

@router.post("/answer")
async def record_answer(answer: AnswerSubmit, db: AsyncSession = Depends(get_db)):
    """
    Records an answer (touch or transcribed speech) in the patient's history session.
    Runs real-time clinical red-flag checks.
    """
    sess_res = await db.execute(select(HistorySession).where(HistorySession.id == answer.session_id))
    session = sess_res.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    response = HistoryResponse(
        session_id=session.id,
        section=answer.section_id,
        question_text=answer.question_text,
        answer_text=answer.answer_text,
        input_method=answer.input_method,
        audio_transcript=answer.audio_transcript,
        confidence_score=0.96 if answer.input_method == "voice" else 1.0
    )
    db.add(response)
    await db.commit()

    # Query all responses so far for red-flag triage evaluation
    all_resp_res = await db.execute(select(HistoryResponse).where(HistoryResponse.session_id == session.id))
    all_responses = all_resp_res.scalars().all()
    resp_dicts = [{"section": r.section, "answer_text": r.answer_text} for r in all_responses]

    red_flags = RedFlagEngine.evaluate_symptoms(resp_dicts)
    triggered_alerts = []

    if red_flags:
        # Fetch encounter to escalate priority
        enc_res = await db.execute(select(Encounter).where(Encounter.id == session.encounter_id))
        encounter = enc_res.scalars().first()
        
        for rf in red_flags:
            if rf.is_triggered:
                # Escalate priority
                if rf.priority == "EMERGENCY":
                    encounter.priority = "EMERGENCY"
                elif rf.priority == "URGENT" and encounter.priority != "EMERGENCY":
                    encounter.priority = "URGENT"

                alert = RedFlagAlert(
                    encounter_id=session.encounter_id,
                    patient_id=encounter.patient_id,
                    trigger_rule=rf.rule_name or "CLINICAL_TRIGGER",
                    description=rf.description or "",
                    priority=rf.priority
                )
                db.add(alert)
                triggered_alerts.append({
                    "title": rf.alert_title,
                    "description": rf.description,
                    "priority": rf.priority,
                    "rationale": rf.clinical_rationale
                })
        await db.commit()

    return {
        "status": "SAVED",
        "response_id": response.id,
        "red_flag_triggered": len(triggered_alerts) > 0,
        "active_alerts": triggered_alerts
    }

@router.post("/complete/{session_id}")
async def complete_intake(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Finalizes patient intake, generates physician-ready clinical summary draft
    via LLM service, and updates encounter status.
    """
    sess_res = await db.execute(
        select(HistorySession)
        .options(selectinload(HistorySession.responses))
        .where(HistorySession.id == session_id)
    )
    session = sess_res.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Phase 7 idempotency: a repeated submit (double tap / kiosk retry) must
    # never generate a second ClinicalSummary row or re-spend the LLM call —
    # the first completion's result is returned unchanged.
    if session.is_completed:
        existing_res = await db.execute(
            select(ClinicalSummary).where(ClinicalSummary.encounter_id == session.encounter_id)
        )
        existing = existing_res.scalars().first()
        enc_res = await db.execute(select(Encounter).where(Encounter.id == session.encounter_id))
        enc = enc_res.scalars().first()
        return {
            "status": "COMPLETED",
            "encounter_id": session.encounter_id,
            "token_number": enc.token_number if enc else None,
            "priority": enc.priority if enc else None,
            "chief_complaint": existing.chief_complaint if existing else None,
            "hpi": existing.hpi if existing else None,
            "confirmed": existing.is_confirmed_by_doctor if existing else False,
            "already_completed": True,
        }

    session.is_completed = True
    session.completed_at = datetime.utcnow()

    enc_res = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.patient))
        .where(Encounter.id == session.encounter_id)
    )
    encounter = enc_res.scalars().first()
    patient = encounter.patient

    encounter.status = "INTAKE_COMPLETED"
    encounter.completed_at = datetime.utcnow()

    # Gather data for LLM summary
    resp_dicts = [{"section": r.section, "question_text": r.question_text, "answer_text": r.answer_text} for r in session.responses]
    patient_info = {"name": patient.name, "age": patient.age, "gender": patient.gender, "mrn": patient.mrn}

    # Generate physician draft summary
    summary_data = await llm_service.generate_clinical_summary(
        patient_info=patient_info,
        intake_responses=resp_dicts,
        documents_extracted=[],
        timeline_events=[]
    )

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
        doctor_notes="AI-assisted clinical intake draft. Awaiting physician confirmation."
    )
    db.add(summary)

    # Audit log
    audit = AuditLog(
        actor_role="PATIENT",
        action="INTAKE_COMPLETED",
        entity_type="ENCOUNTER",
        entity_id=encounter.id,
        details={"summary_id": summary.id, "priority": encounter.priority}
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "COMPLETED",
        "encounter_id": encounter.id,
        "token_number": encounter.token_number,
        "priority": encounter.priority,
        "chief_complaint": summary.chief_complaint,
        "hpi": summary.hpi,
        "confirmed": False
    }
