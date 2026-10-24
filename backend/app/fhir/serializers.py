from typing import Dict, Any, List, Optional
from datetime import datetime
from html import escape as _html_escape
import uuid

class FHIRSerializer:
    """
    Transforms internal MediKiosk models into HL7 FHIR R4 compliant resources,
    aligned with Ayushman Bharat Digital Mission (ABDM) profiles.
    """

    @staticmethod
    def to_patient(patient: Any) -> Dict[str, Any]:
        telecom = []
        if getattr(patient, "phone", None):
            telecom.append({
                "system": "phone",
                "value": patient.phone,
                "use": "mobile"
            })

        identifiers = [
            {
                "system": "https://healthid.ndhm.gov.in",
                "value": getattr(patient, "abha_id", "") or f"ABHA-{patient.id[:8]}",
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]}
            },
            {
                "system": "https://hospital.org/mrn",
                "value": getattr(patient, "mrn", f"MRN-{patient.id[:8]}"),
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MR"}]}
            }
        ]

        gender_map = {"MALE": "male", "FEMALE": "female", "OTHER": "other"}
        fhir_gender = gender_map.get(getattr(patient, "gender", "OTHER").upper(), "other")

        return {
            "resourceType": "Patient",
            "id": patient.id,
            "meta": {
                "profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Patient"]
            },
            "identifier": identifiers,
            "name": [
                {
                    "use": "official",
                    "text": patient.name
                }
            ],
            "telecom": telecom,
            "gender": fhir_gender,
            "birthDate": f"{datetime.utcnow().year - getattr(patient, 'age', 30)}-01-01"
        }

    @staticmethod
    def to_encounter(encounter: Any, patient_id: str) -> Dict[str, Any]:
        return {
            "resourceType": "Encounter",
            "id": encounter.id,
            "meta": {
                "profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Encounter"]
            },
            "status": "in-progress" if encounter.status != "FINALIZED" else "finished",
            "class": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "AMB",
                "display": "ambulatory"
            },
            "subject": {
                "reference": f"Patient/{patient_id}"
            },
            "serviceType": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "408443003",
                        "display": getattr(encounter, "department", "General Medicine")
                    }
                ]
            },
            "priority": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ActPriority",
                        "code": "CR" if encounter.priority == "EMERGENCY" else ("UR" if encounter.priority == "URGENT" else "R"),
                        "display": encounter.priority
                    }
                ]
            },
            "period": {
                "start": encounter.created_at.isoformat() if hasattr(encounter, "created_at") else datetime.utcnow().isoformat()
            }
        }

    @staticmethod
    def to_observation(obs: Any, patient_id: str, encounter_id: Optional[str] = None) -> Dict[str, Any]:
        obs_id = getattr(obs, "id", str(uuid.uuid4()))
        val = getattr(obs, "test_value", "")
        unit = getattr(obs, "unit", "") or ""

        # Phase 6 honesty: never invent a numeric 0.0 for non-numeric results.
        value: Dict[str, Any]
        try:
            value = {"valueQuantity": {"value": float(val), "unit": unit}}
        except (TypeError, ValueError):
            value = {"valueString": str(val)}

        flag = getattr(obs, "flag", "NORMAL")
        interp_code = {"HIGH": "H", "LOW": "L", "CRITICAL": "HH"}.get(flag, "N")

        res = {
            "resourceType": "Observation",
            "id": obs_id,
            "meta": {
                "profile": ["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Observation"],
                # Provenance tag: machine-extracted vs clinician-entered data stays visible.
                "tag": [{
                    "system": "https://medikiosk.local/provenance",
                    "code": getattr(obs, "provenance", "LAB_REPORT")
                }]
            },
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "display": getattr(obs, "test_name", "Lab Test")
                    }
                ],
                "text": getattr(obs, "test_name", "Lab Test")
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "interpretation": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": interp_code
                        }
                    ]
                }
            ]
        }
        res.update(value)
        return res

    @staticmethod
    def to_medication_request(med: Any, patient_id: str) -> Dict[str, Any]:
        med_id = getattr(med, "id", str(uuid.uuid4()))
        return {
            "resourceType": "MedicationRequest",
            "id": med_id,
            "meta": {
                "tag": [{
                    "system": "https://medikiosk.local/provenance",
                    "code": getattr(med, "provenance", "PATIENT_HISTORY")
                }]
            },
            "status": "active" if getattr(med, "is_active", True) else "stopped",
            "intent": "order",
            "medicationCodeableConcept": {
                "text": getattr(med, "name", "Medication")
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "dosageInstruction": [
                {
                    "text": f"{getattr(med, 'dosage', '') or ''} - {getattr(med, 'frequency', '') or ''}".strip()
                }
            ]
        }

    @staticmethod
    def to_document_reference(doc: Any, patient_id: str) -> Dict[str, Any]:
        doc_id = getattr(doc, "id", str(uuid.uuid4()))
        return {
            "resourceType": "DocumentReference",
            "id": doc_id,
            "status": "current",
            "type": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "display": getattr(doc, "document_type", "PRESCRIPTION")
                    }
                ]
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "content": [
                {
                    "attachment": {
                        "contentType": getattr(doc, "mime_type", "image/jpeg"),
                        # Phase 6: opaque, role-guarded download URL — the raw
                        # server-side file path is never exposed in exports.
                        "url": f"api/documents/file/{doc_id}"
                    }
                }
            ]
        }

    @staticmethod
    def to_consent(consent: Any, patient_id: str, encounter_id: str) -> Dict[str, Any]:
        """FHIR R4 Consent artifact mirroring the DPDP consent recorded at intake.

        Phase 7 honesty: consent created at check-in is PENDING until the
        patient explicitly accepts on the consent screen — that state exports
        as status 'draft' with a deny provision, never as 'active'.
        """
        revoked = bool(getattr(consent, "revoked", False))
        granted = bool(getattr(consent, "granted", False))
        status = "revoked" if revoked else ("active" if granted else "draft")
        recorded_at = getattr(consent, "granted_at", None) or datetime.utcnow()
        return {
            "resourceType": "Consent",
            "id": getattr(consent, "id", str(uuid.uuid4())),
            "status": status,
            "scope": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "treatment"}],
                "text": getattr(consent, "purpose", "Clinical OPD Intake")
            },
            "category": [
                {
                    "coding": [{
                        "system": "https://medikiosk.local/consent-version",
                        "code": getattr(consent, "consent_version", "DPDP-2023-V1.0")
                    }]
                }
            ],
            "patient": {"reference": f"Patient/{patient_id}"},
            "sourceReference": {"reference": f"Encounter/{encounter_id}"},
            "dateTime": recorded_at.isoformat(),
            "provision": {
                "type": "permit" if (granted and not revoked) else "deny",
                "period": {
                    "start": recorded_at.isoformat()
                },
                "action": ["collect", "access", "use"] if (granted and not revoked) else ["deny"],
                "class": [
                    {
                        "system": "https://medikiosk.local/data-categories",
                        "code": c
                    } for c in (getattr(consent, "data_categories", None) or [])
                ]
            }
        }

    @staticmethod
    def to_bundle(
        patient: Any,
        encounter: Any,
        summary: Any,
        observations: List[Any],
        medications: List[Any],
        documents: List[Any],
        consent: Optional[Any] = None
    ) -> Dict[str, Any]:
        bundle_id = str(uuid.uuid4())
        entries = []

        patient_res = FHIRSerializer.to_patient(patient)
        entries.append({"resource": patient_res})

        encounter_res = FHIRSerializer.to_encounter(encounter, patient.id)
        entries.append({"resource": encounter_res})

        # DPDP consent artifact — included whenever the encounter has one,
        # so data-sharing provenance travels with the record (ABDM expectation).
        if consent is not None:
            entries.append({"resource": FHIRSerializer.to_consent(consent, patient.id, encounter.id)})

        for obs in observations:
            entries.append({"resource": FHIRSerializer.to_observation(obs, patient.id, encounter.id)})

        for med in medications:
            entries.append({"resource": FHIRSerializer.to_medication_request(med, patient.id)})

        for doc in documents:
            entries.append({"resource": FHIRSerializer.to_document_reference(doc, patient.id)})

        # Composition resource encapsulating physician intake note
        composition = {
            "resourceType": "Composition",
            "id": str(uuid.uuid4()),
            "status": "final" if getattr(summary, "is_confirmed_by_doctor", False) else "preliminary",
            "type": {
                "coding": [{"system": "http://snomed.info/sct", "code": "371530004", "display": "Clinical consultation report"}]
            },
            "subject": {"reference": f"Patient/{patient.id}"},
            "encounter": {"reference": f"Encounter/{encounter.id}"},
            "date": datetime.utcnow().isoformat(),
            "title": "MediKiosk Clinical Intake Consultation Note",
            "section": [
                {
                    "title": "Chief Complaint",
                    # Patient/OCR/AI text is HTML-escaped — never raw markup.
                    "text": {"status": "generated", "div": f"<div>{_html_escape(str(getattr(summary, 'chief_complaint', '')))}</div>"}
                },
                {
                    "title": "History of Present Illness",
                    "text": {"status": "generated", "div": f"<div>{_html_escape(str(getattr(summary, 'hpi', '')))}</div>"}
                }
            ]
        }
        entries.append({"resource": composition})

        return {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "document",
            "timestamp": datetime.utcnow().isoformat(),
            "entry": entries
        }
