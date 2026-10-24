import pytest
from datetime import datetime
from backend.app.fhir.serializers import FHIRSerializer

class MockPatient:
    id = "test-pat-123"
    name = "Ramesh Kumar"
    age = 58
    gender = "MALE"
    phone = "9830112233"
    abha_id = "91-8832-1102-9912"
    mrn = "MRN-2026-9021"

class MockEncounter:
    id = "test-enc-456"
    department = "Cardiology"
    token_number = "OPD-101"
    status = "INTAKE_COMPLETED"
    priority = "EMERGENCY"
    created_at = datetime.utcnow()

class MockObservation:
    id = "obs-1"
    test_name = "HbA1c"
    test_value = "8.2"
    unit = "%"
    flag = "HIGH"

class MockMedication:
    id = "med-1"
    name = "Metformin"
    dosage = "500 mg"
    frequency = "BD"
    is_active = True

class MockDocument:
    id = "doc-1"
    document_type = "PRESCRIPTION"
    mime_type = "image/jpeg"
    file_path = "/uploads/prescription.jpg"

class MockSummary:
    id = "sum-1"
    chief_complaint = "Chest heaviness"
    hpi = "Crushing chest discomfort for 2 days"
    is_confirmed_by_doctor = True

def test_fhir_patient_mapping():
    pat = MockPatient()
    res = FHIRSerializer.to_patient(pat)
    assert res["resourceType"] == "Patient"
    assert res["id"] == "test-pat-123"
    assert res["name"][0]["text"] == "Ramesh Kumar"
    assert res["gender"] == "male"
    assert any(i["value"] == "91-8832-1102-9912" for i in res["identifier"])

def test_fhir_encounter_mapping():
    enc = MockEncounter()
    res = FHIRSerializer.to_encounter(enc, "test-pat-123")
    assert res["resourceType"] == "Encounter"
    assert res["id"] == "test-enc-456"
    assert res["subject"]["reference"] == "Patient/test-pat-123"
    assert res["priority"]["coding"][0]["code"] == "CR"

def test_fhir_bundle_composition():
    bundle = FHIRSerializer.to_bundle(
        patient=MockPatient(),
        encounter=MockEncounter(),
        summary=MockSummary(),
        observations=[MockObservation()],
        medications=[MockMedication()],
        documents=[MockDocument()]
    )
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "document"
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "Patient" in types
    assert "Encounter" in types
    assert "Observation" in types
    assert "MedicationRequest" in types
    assert "DocumentReference" in types
    assert "Composition" in types
