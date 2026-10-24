import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from backend.app.database.session import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=True)
    phone = Column(String(50), unique=True, index=True, nullable=True)
    abha_id = Column(String(50), unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="PATIENT") # PATIENT, DOCTOR, ADMIN
    password_hash = Column(String(255), nullable=True)
    doctor_registration_no = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    patient_profile = relationship("Patient", back_populates="user", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="actor")

class Patient(Base):
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    abha_id = Column(String(50), unique=True, index=True, nullable=True)
    aadhaar_last4 = Column(String(4), nullable=True)
    mrn = Column(String(50), unique=True, index=True, nullable=False) # Medical Record Number
    name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(20), nullable=False) # MALE, FEMALE, OTHER
    blood_group = Column(String(10), nullable=True)
    phone = Column(String(50), nullable=True)
    emergency_contact = Column(String(100), nullable=True)
    preferred_language = Column(String(50), default="en")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="patient_profile")
    encounters = relationship("Encounter", back_populates="patient", cascade="all, delete-orphan")
    documents = relationship("MedicalDocument", back_populates="patient", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="patient", cascade="all, delete-orphan")
    observations = relationship("Observation", back_populates="patient", cascade="all, delete-orphan")
    allergies = relationship("Allergy", back_populates="patient", cascade="all, delete-orphan")
    surgeries = relationship("Surgery", back_populates="patient", cascade="all, delete-orphan")
    timeline_events = relationship("TimelineEvent", back_populates="patient", cascade="all, delete-orphan")

class Encounter(Base):
    __tablename__ = "encounters"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    department = Column(String(100), nullable=False, default="General Medicine")
    token_number = Column(String(50), nullable=False, unique=True, index=True) # e.g. "OPD-102" — UNIQUE: one token never identifies two encounters (QA-07)
    status = Column(String(50), nullable=False, default="QUEUED") # QUEUED, INTAKE_IN_PROGRESS, INTAKE_COMPLETED, IN_CONSULTATION, FINALIZED
    priority = Column(String(50), nullable=False, default="ROUTINE") # ROUTINE, URGENT, EMERGENCY
    kiosk_id = Column(String(50), nullable=True, default="KIOSK-01")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="encounters")
    consent = relationship("ConsentRecord", back_populates="encounter", uselist=False, cascade="all, delete-orphan")
    history_session = relationship("HistorySession", back_populates="encounter", uselist=False, cascade="all, delete-orphan")
    clinical_summary = relationship("ClinicalSummary", back_populates="encounter", uselist=False, cascade="all, delete-orphan")
    red_flag_alerts = relationship("RedFlagAlert", back_populates="encounter", cascade="all, delete-orphan")

class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=False)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    purpose = Column(String(255), nullable=False, default="Clinical OPD Intake and AI-Assisted History Taking")
    data_categories = Column(JSON, default=lambda: ["demographics", "symptoms", "past_records", "voice_recordings"])
    consent_version = Column(String(50), default="DPDP-2023-V1.0")
    granted = Column(Boolean, default=True)
    # Phase 7 honesty: no auto-timestamp — a pending/declined consent must not
    # carry a granted_at value. The /api/intake/consent endpoint stamps this
    # only when the patient explicitly accepts. (Client-side default only —
    # no schema migration required.)
    granted_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
    audio_consent_granted = Column(Boolean, default=True)

    encounter = relationship("Encounter", back_populates="consent")

class HistorySession(Base):
    __tablename__ = "history_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=False)
    primary_complaint = Column(String(255), nullable=True) # e.g. "Chest Pain", "Diabetes", "Asthma"
    complaint_tree = Column(String(100), nullable=True)
    current_step = Column(String(100), default="START")
    language = Column(String(20), default="en")
    is_completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    encounter = relationship("Encounter", back_populates="history_session")
    responses = relationship("HistoryResponse", back_populates="session", cascade="all, delete-orphan")

class HistoryResponse(Base):
    __tablename__ = "history_responses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("history_sessions.id"), nullable=False)
    section = Column(String(100), nullable=False) # e.g. "SOCRATES_SITE", "DURATION", "SEVERITY"
    question_text = Column(String(500), nullable=False)
    answer_text = Column(Text, nullable=False)
    input_method = Column(String(50), default="touch") # "voice" or "touch"
    audio_transcript = Column(Text, nullable=True)
    confidence_score = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("HistorySession", back_populates="responses")

class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=True)
    document_type = Column(String(100), default="PRESCRIPTION") # PRESCRIPTION, LAB_REPORT, DISCHARGE_SUMMARY, OTHER
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), default="image/jpeg")
    ocr_status = Column(String(50), default="PENDING") # PENDING, PROCESSING, COMPLETED, NO_TEXT, FAILED
    ocr_text = Column(Text, nullable=True)
    overall_confidence = Column(Float, default=0.0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="documents")
    extracted_entities = relationship("ExtractedEntity", back_populates="document", cascade="all, delete-orphan")

class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("medical_documents.id"), nullable=False)
    entity_type = Column(String(100), nullable=False) # MEDICATION, LAB_VALUE, DIAGNOSIS, SURGERY, ALLERGY
    entity_name = Column(String(255), nullable=False)
    entity_value = Column(String(255), nullable=True) # e.g. "500 mg BD", "8.4 %"
    confidence = Column(Float, default=0.90)
    source_snippet = Column(Text, nullable=True)
    doctor_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("MedicalDocument", back_populates="extracted_entities")

class Medication(Base):
    __tablename__ = "medications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    name = Column(String(255), nullable=False)
    dosage = Column(String(100), nullable=True)
    frequency = Column(String(100), nullable=True)
    start_date = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    provenance = Column(String(255), default="PATIENT_HISTORY") # PATIENT_HISTORY, OCR_DOCUMENT, DOCTOR_ENTERED

    patient = relationship("Patient", back_populates="medications")

class Observation(Base):
    __tablename__ = "observations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    test_name = Column(String(255), nullable=False)
    test_value = Column(String(100), nullable=False)
    unit = Column(String(50), nullable=True)
    reference_range = Column(String(100), nullable=True)
    flag = Column(String(50), default="NORMAL") # NORMAL, HIGH, LOW, CRITICAL
    observed_date = Column(String(50), nullable=True)
    provenance = Column(String(255), default="LAB_REPORT")

    patient = relationship("Patient", back_populates="observations")

class Allergy(Base):
    __tablename__ = "allergies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    allergen = Column(String(255), nullable=False)
    reaction = Column(String(255), nullable=True)
    severity = Column(String(50), default="MODERATE") # MILD, MODERATE, SEVERE
    provenance = Column(String(255), default="PATIENT_HISTORY")

    patient = relationship("Patient", back_populates="allergies")

class Surgery(Base):
    __tablename__ = "surgeries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    procedure_name = Column(String(255), nullable=False)
    approximate_year = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    provenance = Column(String(255), default="PATIENT_HISTORY")

    patient = relationship("Patient", back_populates="surgeries")

class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    event_date = Column(String(50), nullable=False) # e.g. "Aug 2026", "2026-06-15"
    event_type = Column(String(100), nullable=False) # ENCOUNTER, PRESCRIPTION, LAB_REPORT, DISCHARGE_SUMMARY, SURGERY
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    document_id = Column(String(36), nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="timeline_events")

class ClinicalSummary(Base):
    __tablename__ = "clinical_summaries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=False)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    
    # Structured Clinical Sections
    chief_complaint = Column(Text, nullable=True)
    hpi = Column(Text, nullable=True) # History of Present Illness
    past_medical_history = Column(JSON, default=list)
    past_surgical_history = Column(JSON, default=list)
    drug_history = Column(JSON, default=list)
    allergies = Column(JSON, default=list)
    family_history = Column(JSON, default=list)
    personal_history = Column(JSON, default=list)
    review_of_systems = Column(JSON, default=list)
    investigations = Column(JSON, default=list)
    red_flags = Column(JSON, default=list)
    
    # Doctor Review & Confirmation
    doctor_notes = Column(Text, nullable=True)
    is_confirmed_by_doctor = Column(Boolean, default=False)
    confirmed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    revision_count = Column(Integer, default=1)
    
    # Provenance data linking facts to source inputs
    provenance_map = Column(JSON, default=dict)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    encounter = relationship("Encounter", back_populates="clinical_summary")

class RedFlagAlert(Base):
    __tablename__ = "red_flag_alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    encounter_id = Column(String(36), ForeignKey("encounters.id"), nullable=False)
    patient_id = Column(String(36), ForeignKey("patients.id"), nullable=False)
    trigger_rule = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(50), default="URGENT") # URGENT, CRITICAL
    acknowledged = Column(Boolean, default=False)
    acknowledged_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    triggered_at = Column(DateTime, default=datetime.utcnow)

    encounter = relationship("Encounter", back_populates="red_flag_alerts")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    actor_role = Column(String(50), default="SYSTEM") # PATIENT, DOCTOR, ADMIN, SYSTEM
    action = Column(String(100), nullable=False) # e.g. "INTAKE_STARTED", "CONSENT_GRANTED", "SUMMARY_EDITED", "DOCTOR_CONFIRMED"
    entity_type = Column(String(100), nullable=False) # "ENCOUNTER", "SUMMARY", "DOCUMENT"
    entity_id = Column(String(36), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, default=dict)
    ip_address = Column(String(50), nullable=True)

    actor = relationship("User", back_populates="audit_logs")

class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    service = Column(String(50), nullable=False) # "ABDM", "FHIR", "HIS"
    event_type = Column(String(100), nullable=False) # "FHIR_BUNDLE_EXPORT", "ABDM_RECORD_SYNC"
    payload = Column(JSON, nullable=True)
    status = Column(String(50), default="SUCCESS") # SUCCESS, PENDING, FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
