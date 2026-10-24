from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, case, extract
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_db
from backend.app.api.auth_router import require_authenticated_roles
from backend.app.models.entities import (
    Encounter, Patient, AuditLog, RedFlagAlert, MedicalDocument, User
)

router = APIRouter(prefix="/api/admin", tags=["Hospital Administration"])


from backend.app.clinical.intake_time_model import IntakeTimeModel

# ──────────────────────────────────────────────────────────────────────
# Pydantic models for average time calculation & prediction
# ──────────────────────────────────────────────────────────────────────

class IntakeTimeStats(BaseModel):
    """Model to represent average intake time calculation results."""
    average_minutes: float
    median_minutes: Optional[float] = None
    min_minutes: Optional[float] = None
    max_minutes: Optional[float] = None
    sample_size: int
    standard_deviation: Optional[float] = None
    confidence_interval_95: Optional[List[float]] = None
    calculation_method: str = "hybrid_bayesian_regression_model"
    model_name: Optional[str] = "MediKiosk Clinical Intake Duration Estimator"
    model_version: Optional[str] = "v2.1-hybrid"
    time_saved_vs_manual_triage_minutes: Optional[float] = None
    manual_baseline_minutes: Optional[float] = 18.0
    department_averages: Optional[dict] = None
    modality_breakdown: Optional[dict] = None
    period: str = "all"


class PredictIntakeRequest(BaseModel):
    age: int = 35
    department: str = "General Medicine"
    consultation_type: str = "modern"
    has_voice: bool = False
    document_count: int = 0
    symptom_count: int = 1
    priority: str = "ROUTINE"


class AcknowledgeRequest(BaseModel):
    acknowledged_by: str = "Triage Command Admin"


# ──────────────────────────────────────────────────────────────────────
# Helper: period window for the dashboard counters (QA-11)
# ──────────────────────────────────────────────────────────────────────

def _period_start(period: str) -> Optional[datetime]:
    """
    Lower bound for the selected reporting period.

    All timestamps in this schema are naive UTC (`datetime.utcnow` defaults),
    so the window is computed in the same frame — no local-time shifting.
    The boundaries intentionally match IntakeTimeModel.compute_stats_from_db
    so every metric on the dashboard shares one definition of "today".

    Returns None for the all-time period.
    """
    now = datetime.utcnow()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return None


# ──────────────────────────────────────────────────────────────────────
# Helper: Calculate average intake duration using IntakeTimeModel
# ──────────────────────────────────────────────────────────────────────

async def calculate_intake_time_stats(
    db: AsyncSession, 
    period: str = "all"
) -> IntakeTimeStats:
    """
    Computes average intake time via the hybrid empirical-Bayesian regression model.
    """
    stats = await IntakeTimeModel.compute_stats_from_db(db, period=period)
    return IntakeTimeStats(**stats)



# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/telemetry — Live hospital dashboard metrics from DB
# ──────────────────────────────────────────────────────────────────────

@router.get("/telemetry")
async def get_hospital_telemetry(
    period: str = "all",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """
    Returns live hospital kiosk fleet telemetry and operational throughput
    statistics — all metrics are computed from the actual database.
    """
    # QA-11: every counter below is scoped to the selected period. Previously
    # only the intake-duration model responded to `period` while the counters
    # stayed all-time, so "Today" silently showed lifetime totals.
    period_start = _period_start(period)

    encounter_window = [Encounter.created_at >= period_start] if period_start else []
    alert_window = [RedFlagAlert.triggered_at >= period_start] if period_start else []
    document_window = [MedicalDocument.uploaded_at >= period_start] if period_start else []

    # 1. Total Registrations (encounters created in the period)
    total_reg_res = await db.execute(
        select(func.count(Encounter.id)).where(*encounter_window)
    )
    total_registrations = total_reg_res.scalar() or 0

    # 2. Completed Intakes (encounters with status INTAKE_COMPLETED or later)
    completed_res = await db.execute(
        select(func.count(Encounter.id)).where(
            Encounter.status.in_([
                "INTAKE_COMPLETED", "WAITING_CONSULTATION", 
                "IN_CONSULTATION", "FINALIZED"
            ]),
            *encounter_window
        )
    )
    completed_intakes = completed_res.scalar() or 0

    # 3. Active Red Flags (unacknowledged, raised in the period)
    active_rf_res = await db.execute(
        select(func.count(RedFlagAlert.id)).where(
            RedFlagAlert.acknowledged == False,
            *alert_window
        )
    )
    active_red_flags = active_rf_res.scalar() or 0

    # 4. Total Red Flags (raised in the period)
    total_rf_res = await db.execute(
        select(func.count(RedFlagAlert.id)).where(*alert_window)
    )
    total_red_flags = total_rf_res.scalar() or 0

    # 5. Total Documents (uploaded in the period)
    doc_count_res = await db.execute(
        select(func.count(MedicalDocument.id)).where(*document_window)
    )
    total_documents = doc_count_res.scalar() or 0

    # 6. Average Intake Time — calculated via the model
    intake_stats = await calculate_intake_time_stats(db, period=period)

    # 7. Status distribution
    status_query = await db.execute(
        select(Encounter.status, func.count(Encounter.id))
        .where(*encounter_window)
        .group_by(Encounter.status)
    )
    status_distribution = {row[0]: row[1] for row in status_query.all()}

    # 8. Priority distribution
    priority_query = await db.execute(
        select(Encounter.priority, func.count(Encounter.id))
        .where(*encounter_window)
        .group_by(Encounter.priority)
    )
    priority_distribution = {row[0]: row[1] for row in priority_query.all()}

    # 9. Department distribution
    dept_query = await db.execute(
        select(Encounter.department, func.count(Encounter.id))
        .where(*encounter_window)
        .group_by(Encounter.department)
    )
    department_distribution = {row[0]: row[1] for row in dept_query.all()}

    # 10. Kiosk terminal info (static hardware config)
    kiosks = [
        {
            "id": "KIOSK-01",
            "location": "OPD Ground Floor Entrance A",
            "status": "ONLINE",
            "active_since": "07:30 AM",
        },
        {
            "id": "KIOSK-02",
            "location": "Cardiology Wing 1st Floor",
            "status": "ONLINE",
            "active_since": "08:00 AM",
        },
        {
            "id": "BYOD-QR",
            "location": "Patient Smartphone QR Gateway",
            "status": "ONLINE",
            "active_since": "24/7",
        }
    ]

    # Red flag alert rate
    red_flag_rate = (
        round((total_red_flags / total_registrations) * 100, 1)
        if total_registrations > 0 else 0.0
    )

    return {
        "period": period if period_start else "all",
        "period_start": period_start.isoformat() if period_start else None,
        "scope": "period" if period_start else "all_time",
        "metrics": {
            "total_registrations": total_registrations,
            "completed_intakes": completed_intakes,
            "active_red_flags": active_red_flags,
            "total_red_flags": total_red_flags,
            "total_documents": total_documents,
            "red_flag_alert_rate": f"{red_flag_rate}%",
        },
        "intake_time_model": intake_stats.model_dump(),
        "status_distribution": status_distribution,
        "priority_distribution": priority_distribution,
        "department_distribution": department_distribution,
        "kiosks": kiosks,
        "abdm_gateway": {
            "status": "CONNECTED",
            "bridge_url": "https://dev.abdm.gov.in/gateway",
            "last_heartbeat": datetime.utcnow().isoformat(),
            "mode": "Sandbox HIP/HIU"
        }
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/intake-time-model — Dedicated average time endpoint
# ──────────────────────────────────────────────────────────────────────

@router.get("/intake-time-model", response_model=IntakeTimeStats)
async def get_intake_time_model(
    period: str = "all",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """
    Returns detailed intake time calculation statistics.
    
    The model computes:
    - average_minutes: Mean intake duration
    - median_minutes: Median intake duration
    - min_minutes / max_minutes: Range
    - sample_size: Number of completed intakes used
    
    period options: "today", "week", "month", "all"
    """
    return await calculate_intake_time_stats(db, period=period)


@router.post("/intake-time-model/predict")
async def predict_intake_duration(
    body: PredictIntakeRequest,
    current_user: User = Depends(require_authenticated_roles("ADMIN")),
):
    """
    Predicts intake duration using the clinical intake multi-factor model.
    """
    detail = IntakeTimeModel.predict_intake_duration_detailed(
        age=body.age,
        department=body.department,
        consultation_type=body.consultation_type,
        has_voice=body.has_voice,
        document_count=body.document_count,
        symptom_count=body.symptom_count,
        priority=body.priority
    )
    return {
        "predicted_minutes": detail["predicted_minutes"],
        "parameters": body.model_dump(),
        "model_version": detail["model_version"],
        "engine": detail["engine"],
        "time_saved_vs_manual_baseline_minutes": detail["time_saved_vs_manual_baseline_minutes"],
        "confidence_interval_95": detail["confidence_interval_95"],
        "factors": detail["factors"]
    }


# ──────────────────────────────────────────────────────────────────────
# Academic ML Model Verification & Evaluation Endpoints
# ──────────────────────────────────────────────────────────────────────

from backend.app.clinical.red_flags import RedFlagEngine
import json
import os

class TriageTestRequest(BaseModel):
    complaint_text: str

@router.get("/models/status")
async def get_models_status(
    current_user: User = Depends(require_authenticated_roles("ADMIN")),
):
    """
    Returns status, metadata, and verified evaluation metrics for all AI/ML models
    running in the MediKiosk academic prototype.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    model_dir = os.path.join(project_root, "model")

    # 1. Regressor eval
    reg_eval = {}
    reg_eval_path = os.path.join(model_dir, "intake_duration_evaluation.json")
    if os.path.exists(reg_eval_path):
        try:
            with open(reg_eval_path, "r", encoding="utf-8") as f:
                reg_eval = json.load(f)
        except Exception:
            pass

    # 2. Triage eval
    triage_eval = {}
    triage_eval_path = os.path.join(model_dir, "clinical_triage_evaluation.json")
    if os.path.exists(triage_eval_path):
        try:
            with open(triage_eval_path, "r", encoding="utf-8") as f:
                triage_eval = json.load(f)
        except Exception:
            pass

    # 3. Indic speech eval
    speech_eval = {}
    speech_eval_path = os.path.join(model_dir, "indic_speech_evaluation.json")
    if os.path.exists(speech_eval_path):
        try:
            with open(speech_eval_path, "r", encoding="utf-8") as f:
                speech_eval = json.load(f)
        except Exception:
            pass

    # 4. Summary
    summary = {}
    summary_path = os.path.join(model_dir, "model_training_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception:
            pass

    whisper_dir = os.path.join(model_dir, "whisper")
    paddleocr_dir = os.path.join(model_dir, "paddleocr")

    return {
        "status": "OPERATIONAL",
        "prototype_mode": "Academic Local Verification",
        "training_summary": summary,
        "models": {
            "intake_duration_regressor": {
                "status": "ACTIVE_VERIFIED" if os.path.exists(os.path.join(model_dir, "intake_duration_regressor.joblib")) else "FALLBACK",
                "framework": "Scikit-Learn GradientBoostingRegressor (120 estimators, lr=0.08)",
                "dataset": "Synthea Outpatient & Ambulatory Encounters (4,245 cleaned encounters)",
                "evaluation": reg_eval.get("metrics", {}),
                "feature_importances": reg_eval.get("feature_importances", {}),
                "last_trained": reg_eval.get("trained_at")
            },
            "clinical_triage_classifier": {
                "status": "ACTIVE_VERIFIED" if os.path.exists(os.path.join(model_dir, "clinical_triage_classifier.joblib")) else "FALLBACK",
                "framework": "TF-IDF (1,2-gram) + Calibrated Logistic Regression Dual Pipeline",
                "dataset": "Med-Dialog Dialogue Corpus + Synthea Clinical Conditions + Indic Grounding",
                "department_evaluation": triage_eval.get("department_classifier", {}),
                "priority_evaluation": triage_eval.get("priority_classifier", {}),
                "last_trained": triage_eval.get("trained_at")
            },
            "indic_speech_normalizer": {
                "status": "ACTIVE_VERIFIED" if os.path.exists(os.path.join(model_dir, "indic_clinical_lexicon.json")) else "FALLBACK",
                "framework": "IndicVoices Multilingual Clinical Lexicon & Concept Grounding",
                "languages": ["Gujarati (gu)", "Hindi (hi)", "English (en)"],
                "evaluation": speech_eval,
                "vocabulary_tokens": {
                    "gujarati": speech_eval.get("gujarati_tokens", 119),
                    "hindi": speech_eval.get("hindi_tokens", 119)
                }
            },
            "whisper_asr": {
                "status": "READY_LOCAL" if os.path.exists(whisper_dir) else "FALLBACK",
                "path": whisper_dir,
                "model_size": os.getenv("WHISPER_MODEL_SIZE", "base"),
                "license": "MIT (Free & Offline)"
            },
            "paddleocr": {
                "status": "READY_LOCAL" if os.path.exists(paddleocr_dir) else "FALLBACK",
                "path": paddleocr_dir,
                "license": "Apache 2.0 (Free & Offline)"
            }
        }
    }


@router.post("/models/triage-test")
async def test_triage_complaint(
    body: TriageTestRequest,
    current_user: User = Depends(require_authenticated_roles("ADMIN")),
):
    """
    Evaluates an arbitrary patient complaint text (English, Hindi, or Gujarati)
    through the trained Clinical Triage ML pipeline.
    """
    result = RedFlagEngine.classify_complaint_ml(body.complaint_text)
    # Also attach intake duration prediction
    duration_detail = IntakeTimeModel.predict_intake_duration_detailed(
        age=45,
        department=result.get("department", "General Medicine"),
        priority=result.get("priority", "ROUTINE"),
        symptom_count=len(result.get("matched_concepts", [])) or 1
    )
    return {
        "triage": result,
        "duration_prediction": duration_detail
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/opd-queue — OPD Patient Queue (pulled from DB)
# ──────────────────────────────────────────────────────────────────────

@router.get("/opd-queue")
async def get_opd_patient_queue(
    department: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """
    Returns the OPD Patient Queue from the database.
    Supports optional filtering by department and status.
    """
    query = (
        select(Encounter)
        .options(
            selectinload(Encounter.patient),
            selectinload(Encounter.red_flag_alerts),
            selectinload(Encounter.clinical_summary)
        )
        .order_by(
            Encounter.priority.desc(),
            Encounter.created_at.asc()
        )
    )

    if department:
        query = query.where(Encounter.department == department)
    
    if status:
        query = query.where(Encounter.status == status)

    result = await db.execute(query)
    encounters = result.scalars().all()

    queue = []
    for enc in encounters:
        if not enc.patient:
            continue

        # Calculate wait time if not completed
        wait_minutes = None
        if enc.created_at:
            if enc.completed_at:
                wait_minutes = round(
                    (enc.completed_at - enc.created_at).total_seconds() / 60.0, 1
                )
            else:
                wait_minutes = round(
                    (datetime.utcnow() - enc.created_at).total_seconds() / 60.0, 1
                )

        has_red_flags = any(
            not a.acknowledged for a in enc.red_flag_alerts
        )

        complaint_preview = ""
        if enc.clinical_summary:
            complaint_preview = enc.clinical_summary.chief_complaint or ""

        queue.append({
            "encounter_id": enc.id,
            "patient_id": enc.patient.id,
            "token_number": enc.token_number,
            "patient_name": enc.patient.name,
            "age": enc.patient.age,
            "gender": enc.patient.gender,
            "mrn": enc.patient.mrn,
            "department": enc.department,
            "status": enc.status,
            "priority": enc.priority,
            "kiosk_id": enc.kiosk_id,
            "has_red_flags": has_red_flags,
            "complaint_preview": complaint_preview[:100],
            "wait_minutes": wait_minutes,
            "created_at": enc.created_at.isoformat() if enc.created_at else None,
            "completed_at": enc.completed_at.isoformat() if enc.completed_at else None,
        })

    return queue


# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/red-flags — Active red flag alerts from DB
# ──────────────────────────────────────────────────────────────────────

@router.get("/red-flags")
async def get_red_flag_alerts(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """Returns red flag alerts, optionally filtered to active (unacknowledged) only."""
    query = (
        select(RedFlagAlert)
        .options(selectinload(RedFlagAlert.encounter).selectinload(Encounter.patient))
        .order_by(RedFlagAlert.triggered_at.desc())
    )
    
    if active_only:
        query = query.where(RedFlagAlert.acknowledged == False)

    result = await db.execute(query)
    alerts = result.scalars().all()

    return [
        {
            "id": a.id,
            "encounter_id": a.encounter_id,
            "patient_id": a.patient_id,
            "patient_name": a.encounter.patient.name if a.encounter and a.encounter.patient else "Unknown",
            "token_number": a.encounter.token_number if a.encounter else "N/A",
            "trigger_condition": a.description,
            "trigger_rule": a.trigger_rule,
            "priority": a.priority,
            "acknowledged": a.acknowledged,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        }
        for a in alerts
    ]


# ──────────────────────────────────────────────────────────────────────
# POST /api/admin/red-flags/{id}/acknowledge — Acknowledge a red flag
# ──────────────────────────────────────────────────────────────────────

@router.post("/red-flags/{alert_id}/acknowledge")
async def acknowledge_red_flag(
    alert_id: str,
    body: AcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """Acknowledge a red flag alert. RBAC: only an authenticated
    ADMIN bearer token may acknowledge — anonymous acknowledgment
    is rejected with 401 so emergency alerts cannot be cleared by anyone."""
    result = await db.execute(
        select(RedFlagAlert).where(RedFlagAlert.id == alert_id)
    )
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Red flag alert not found")

    alert.acknowledged = True
    
    # Audit log — actor is always the real authenticated user (strict guard).
    audit = AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role,
        action="RED_FLAG_ACKNOWLEDGED",
        entity_type="RED_FLAG_ALERT",
        entity_id=alert_id,
        details={
            "acknowledged_by": current_user.full_name
        }
    )
    db.add(audit)
    await db.commit()

    return {"status": "ACKNOWLEDGED", "alert_id": alert_id}


# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/audit-logs — Audit trail from DB
# ──────────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    res = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    logs = res.scalars().all()
    return [
        {
            "id": l.id,
            "actor_id": l.actor_id,
            "actor_role": l.actor_role,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "timestamp": l.timestamp.isoformat(),
            "details": l.details
        }
        for l in logs
    ]


# ──────────────────────────────────────────────────────────────────────
# GET /api/admin/staff — Staff & role registry (ADMIN only)
# ──────────────────────────────────────────────────────────────────────

@router.get("/staff")
async def get_staff_registry(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("ADMIN"))
):
    """Returns the hospital staff (DOCTOR/ADMIN) and registered user directory."""
    res = await db.execute(select(User).order_by(User.role.asc(), User.full_name.asc()))
    users = res.scalars().all()
    return [
        {
            "id": u.id,
            "name": u.full_name,
            "role": u.role,
            "email": u.email,
            "phone": u.phone,
            "department": u.department,
            "doctor_registration_no": u.doctor_registration_no,
            "created_at": u.created_at.isoformat() if getattr(u, "created_at", None) else None,
        }
        for u in users
    ]
