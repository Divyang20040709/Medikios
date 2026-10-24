from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend.app.database.session import get_db
from backend.app.api.auth_router import require_authenticated_roles
from backend.app.models.entities import (
    Encounter, Patient, ClinicalSummary, Observation, Medication, MedicalDocument, IntegrationEvent, User
)
from backend.app.fhir.serializers import FHIRSerializer

router = APIRouter(prefix="/api/fhir", tags=["ABDM & FHIR Interoperability"])

@router.get("/encounter/{encounter_id}")
async def export_encounter_fhir_bundle(
    encounter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """
    Generates an HL7 FHIR R4 document Bundle structured to follow ABDM profile
    conventions (locally generated and schema-consistent — NOT validated or
    certified by a live ABDM gateway).
    Encapsulates Patient, Encounter, Consent, Observation, MedicationRequest,
    DocumentReference, and Composition.
    Phase 6: requires an authenticated DOCTOR/ADMIN token — a bundle contains
    the full patient record.
    """
    enc_res = await db.execute(
        select(Encounter)
        .options(
            selectinload(Encounter.patient).selectinload(Patient.medications),
            selectinload(Encounter.patient).selectinload(Patient.observations),
            selectinload(Encounter.patient).selectinload(Patient.documents),
            selectinload(Encounter.clinical_summary),
            selectinload(Encounter.consent)
        )
        .where(Encounter.id == encounter_id)
    )
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    patient = encounter.patient
    summary = encounter.clinical_summary

    bundle = FHIRSerializer.to_bundle(
        patient=patient,
        encounter=encounter,
        summary=summary,
        observations=patient.observations,
        medications=patient.medications,
        documents=patient.documents,
        consent=encounter.consent
    )

    # Record Integration Event
    event = IntegrationEvent(
        service="FHIR_R4",
        event_type="FHIR_BUNDLE_EXPORT",
        payload={"encounter_id": encounter_id, "bundle_id": bundle["id"], "entries": len(bundle["entry"])},
        status="SUCCESS"
    )
    db.add(event)
    await db.commit()

    return bundle

@router.post("/abdm/push/{encounter_id}")
async def push_to_abdm_gateway(
    encounter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_authenticated_roles("DOCTOR", "ADMIN"))
):
    """
    ABDM Integration Boundary (SIMULATED — Phase 6 audit):
    validates the FHIR bundle shape and records the intended hand-off as an
    IntegrationEvent, but does NOT transmit anything to a real ABDM
    Health Information Provider: no institutional certificates, gateway
    onboarding or live HIP connectivity exist in this deployment. Nothing
    here constitutes ABDM certification or a live integration.
    """
    enc_res = await db.execute(select(Encounter).where(Encounter.id == encounter_id))
    encounter = enc_res.scalars().first()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    # Record event
    event = IntegrationEvent(
        service="ABDM",
        event_type="ABDM_HIP_PUSH",
        payload={"encounter_id": encounter_id, "mode": "SANDBOX_MOCK_INTEGRATION"},
        status="SUCCESS"
    )
    db.add(event)
    await db.commit()

    return {
        "status": "SIMULATED_NOT_TRANSMITTED",
        "encounter_id": encounter_id,
        "abdm_transaction_id": f"TXN-{encounter_id[:8].upper()}-ABDM",
        "integration_mode": "SANDBOX_SIMULATION",
        "gateway_note": (
            "No live ABDM HIP gateway is connected. This is a local schema-"
            "validation simulation only — not an ABDM-certified integration."
        ),
        "timestamp": datetime.utcnow().isoformat()
    }
