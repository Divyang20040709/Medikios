from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str

class LoginRequest(BaseModel):
    identifier: str # Email, ABHA ID, Phone, or MRN
    password: Optional[str] = None
    role: str = "PATIENT" # PATIENT, DOCTOR, ADMIN
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    department: Optional[str] = None

class PatientRegisterRequest(BaseModel):
    # QA-01: check-in data used to be accepted unvalidated, so a blank payload
    # created an anonymous "Patient / 0y / X" record in the OPD queue. The kiosk
    # already validates these fields client-side; the server now enforces them
    # too, because /api/intake/init is reachable directly.
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=1, le=120)
    gender: str
    phone: Optional[str] = None
    abha_id: Optional[str] = None
    aadhaar_last4: Optional[str] = None
    blood_group: Optional[str] = None
    emergency_contact: Optional[str] = None
    preferred_language: str = "en"
    department: str = "General Medicine"

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Patient name is required")
        return value.strip()

    @field_validator("gender")
    @classmethod
    def _gender_known(cls, value: str) -> str:
        cleaned = (value or "").strip().upper()
        if cleaned not in {"MALE", "FEMALE", "OTHER"}:
            raise ValueError("Gender must be MALE, FEMALE or OTHER")
        return cleaned

# Consent Schemas
class ConsentCreate(BaseModel):
    encounter_id: str
    patient_id: str
    purpose: str = "Clinical OPD Intake and AI-Assisted History Taking"
    data_categories: List[str] = ["demographics", "symptoms", "past_records", "voice_recordings"]
    audio_consent: bool = True
    # Phase 7: consent must be an EXPLICIT patient action on the kiosk screen.
    # granted=True records acceptance; granted=False records an explicit
    # decline. Intake initialization leaves consent pending (never pre-granted).
    granted: bool = True

# Interview Schemas
class AnswerSubmit(BaseModel):
    session_id: str
    section_id: str
    question_text: str
    answer_text: str
    input_method: str = "touch" # "voice" or "touch"
    audio_transcript: Optional[str] = None

class QuestionOption(BaseModel):
    id: str
    label: str
    value: str
    subtext: Optional[str] = None

class ClinicalQuestion(BaseModel):
    id: str
    section: str
    category: str # "COMPLAINT", "SOCRATES", "ROS", "PAST_HISTORY", "MEDICATIONS"
    question_en: str
    translations: Dict[str, str] = Field(default_factory=dict)
    input_type: str # "single_select", "multi_select", "text", "voice_or_touch", "scale"
    options: Optional[List[QuestionOption]] = None
    required: bool = True
    next_question_id: Optional[str] = None
    red_flag_triggers: Optional[List[Dict[str, Any]]] = None

# OCR and Extraction Schemas
class ExtractedEntityItem(BaseModel):
    entity_type: str # MEDICATION, LAB_VALUE, DIAGNOSIS, SURGERY, ALLERGY
    entity_name: str
    entity_value: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    confidence: float = 0.90
    source_snippet: Optional[str] = None

class OCRProcessingResult(BaseModel):
    document_id: str
    document_type: str
    ocr_text: str
    overall_confidence: float
    extracted_entities: List[ExtractedEntityItem]

# Clinical Fact & Summary Schemas
class ClinicalFact(BaseModel):
    entity: str
    category: str
    detail: Optional[str] = None
    confidence: float = 1.0
    provenance: str = "PATIENT_INTAKE"

class ClinicalSummaryCreate(BaseModel):
    chief_complaint: str
    hpi: str
    past_medical_history: List[Dict[str, Any]] = Field(default_factory=list)
    past_surgical_history: List[Dict[str, Any]] = Field(default_factory=list)
    drug_history: List[Dict[str, Any]] = Field(default_factory=list)
    allergies: List[Dict[str, Any]] = Field(default_factory=list)
    family_history: List[Dict[str, Any]] = Field(default_factory=list)
    personal_history: List[Dict[str, Any]] = Field(default_factory=list)
    review_of_systems: List[Dict[str, Any]] = Field(default_factory=list)
    investigations: List[Dict[str, Any]] = Field(default_factory=list)
    red_flags: List[Dict[str, Any]] = Field(default_factory=list)

class DoctorSummaryUpdate(BaseModel):
    chief_complaint: Optional[str] = None
    hpi: Optional[str] = None
    past_medical_history: Optional[List[Dict[str, Any]]] = None
    past_surgical_history: Optional[List[Dict[str, Any]]] = None
    drug_history: Optional[List[Dict[str, Any]]] = None
    allergies: Optional[List[Dict[str, Any]]] = None
    doctor_notes: Optional[str] = None
    confirm: bool = False

# Memory Graph Schemas
class GraphNode(BaseModel):
    id: str
    type: str # "PATIENT", "CONDITION", "MEDICATION", "ALLERGY", "SURGERY", "OBSERVATION", "ENCOUNTER"
    label: str
    details: Optional[Dict[str, Any]] = None
    confidence: float = 1.0

class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str # "HAS_CONDITION", "TAKES_MEDICATION", "ALLERGIC_TO", "UNDERWENT_SURGERY", "HAS_OBSERVATION"
    provenance: str

class DoctorMemoryGraphResponse(BaseModel):
    patient_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]

# Red Flag Alert Schemas
class RedFlagItem(BaseModel):
    id: str
    trigger_rule: str
    description: str
    priority: str
    triggered_at: datetime
    acknowledged: bool
