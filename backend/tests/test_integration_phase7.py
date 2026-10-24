"""
Phase 7 — End-to-end integration tests (patient intake → physician sign-off).

Covers the confirmed Phase 7 fixes with deterministic, hermetic tests:
  * P7-B1 Consent: intake init leaves consent PENDING (never pre-granted);
    the explicit decision arrives via POST /api/intake/consent; FHIR exports
    pending/declined consent honestly (draft + deny), forgery across the
    encounter/patient pair is refused.
  * P7-B2 Workflow step 8: the patient's ORIGINAL answers reach the doctor
    dossier verbatim (patient_statements), separate from AI summary & OCR.
  * P7-B3 Idempotency: repeated /complete never doubles ClinicalSummary or
    re-spends the LLM; repeated sign-off is rejected 409.
  * P7-B4 OCR pipeline: every upload path (valid, unsupported, empty,
    oversized, NO_TEXT, timeout, engine crash) behaves honestly and the
    original file is preserved; entities stay unverified until a DOCTOR
    confirms them.
  * P7-B5 Speech honesty: 400/413/503 error contract, en/hi/gu passthrough.
  * Red flags remain deterministic when the LLM fails or returns dismissive
    content, and emergency priority survives answers → completion → queue.
  * FHIR bundle: Consent/provenance resources correct unsigned AND signed;
    document URLs are opaque; ABDM push stays explicitly simulated.

No external services are used — LLM and OCR engines are mocked at the
service boundary; everything else runs the real application.
"""

import asyncio
import io
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from PIL import Image
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.core.config import settings
from backend.app.models.entities import (
    Patient, Encounter, ConsentRecord, HistorySession, HistoryResponse,
    ClinicalSummary, MedicalDocument, ExtractedEntity, AuditLog, User,
)
from backend.app.api.auth_router import create_access_token
from backend.app.api import document_router, speech_router
from backend.app.api import intake_router
from backend.app.services.llm_service import llm_service
from backend.app.services.followup_service import LocalLLMClient
from backend.app.schemas.pydantic_models import ClinicalSummaryCreate
from backend.app.documents.processor import ExtractedClinicalData
from backend.app.speech.provider import TranscriptionResult

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
)
_test_session_factory = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def mock_summary_llm(monkeypatch):
    """The clinical-summary LLM is always mocked: /complete must never reach
    the network in tests. Yields the call counter so idempotency (P7-B3) can
    assert the LLM is spent exactly once."""
    calls: List[Dict[str, Any]] = []

    async def fake_generate(patient_info=None, intake_responses=None,
                           documents_extracted=None, timeline_events=None):
        calls.append({"patient": patient_info})
        return ClinicalSummaryCreate(
            chief_complaint="Chest pain x 2 days",
            hpi="Patient reports central chest pain radiating to left arm.",
        )

    monkeypatch.setattr(llm_service, "generate_clinical_summary", fake_generate)
    yield calls


# ── helpers ────────────────────────────────────────────────────────────────

def _asgi() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0)


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), color=(255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


async def _doctor_headers(role: str = "DOCTOR") -> Dict[str, str]:
    async with _test_session_factory() as db:
        tag = uuid.uuid4().hex[:10]
        doc = User(full_name=f"Dr P7 {tag}", role=role, email=f"p7.{role.lower()}.{tag}@test.local")
        db.add(doc)
        await db.commit()
        token = create_access_token(data={"sub": doc.id, "role": role})
    return {"Authorization": f"Bearer {token}"}


async def _start_intake(client: AsyncClient, name="Lokesh", language="hi") -> Dict[str, str]:
    resp = await client.post("/api/intake/init", json={
        "name": name, "age": 55, "gender": "MALE",
        "phone": f"98{uuid.uuid4().hex[:8]}", "preferred_language": language,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _answer(client: AsyncClient, session_id: str, section: str,
                  question: str, answer: str, method: str = "touch") -> Dict[str, Any]:
    resp = await client.post("/api/intake/answer", json={
        "session_id": session_id, "section_id": section,
        "question_text": question, "answer_text": answer, "input_method": method,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _consent(client: AsyncClient, ids: Dict[str, str], granted=True, **kw) -> Any:
    body = {"encounter_id": ids["encounter_id"], "patient_id": ids["patient_id"],
            "granted": granted, **kw}
    return await client.post("/api/intake/consent", json=body)


async def _db_consent(encounter_id: str) -> Optional[ConsentRecord]:
    async with _test_session_factory() as db:
        res = await db.execute(select(ConsentRecord).where(ConsentRecord.encounter_id == encounter_id))
        return res.scalars().first()


async def _db_audit_actions(entity_id: str) -> List[str]:
    async with _test_session_factory() as db:
        res = await db.execute(select(AuditLog).where(AuditLog.entity_id == entity_id))
        return [a.action for a in res.scalars().all()]


async def _db_summaries(encounter_id: str) -> List[ClinicalSummary]:
    async with _test_session_factory() as db:
        res = await db.execute(select(ClinicalSummary).where(ClinicalSummary.encounter_id == encounter_id))
        return list(res.scalars().all())


def _bundle_resources(bundle: Dict[str, Any], resource_type: str) -> List[Dict[str, Any]]:
    return [e["resource"] for e in bundle.get("entry", [])
            if e.get("resource", {}).get("resourceType") == resource_type]


def _extracted_with_entities() -> ExtractedClinicalData:
    return ExtractedClinicalData(
        document_type="PRESCRIPTION",
        raw_text="Tab Paracetamol 500 mg 1-0-1 x 3 days\nHbA1c 8.1 % (ref 4.0-5.6)",
        overall_confidence=0.92,
        patient_name={},
        medications=[{"name": "Paracetamol", "dosage": "500 mg", "frequency": "1-0-1",
                      "confidence": 0.95, "source_snippet": "Tab Paracetamol 500 mg 1-0-1",
                      "doctor_verified": False}],
        observations=[{"test_name": "HbA1c", "test_value": "8.1", "unit": "%",
                       "reference_range": "4.0-5.6", "flag": "HIGH", "confidence": 0.9,
                       "source_snippet": "HbA1c 8.1 %", "doctor_verified": False}],
        diagnoses=[], allergies=[], surgeries=[],
    )


def _extracted_blank() -> ExtractedClinicalData:
    return ExtractedClinicalData(
        document_type="OTHER", raw_text="", overall_confidence=0.0,
        patient_name={}, medications=[], observations=[], diagnoses=[],
        allergies=[], surgeries=[],
    )


async def _upload(client: AsyncClient, patient_id: str, encounter_id: Optional[str] = None,
                  filename="prescription.jpg", content: bytes = None,
                  ctype: str = "image/jpeg"):
    if content is None:
        content = _jpeg_bytes()
    data = {"patient_id": patient_id}
    if encounter_id:
        data["encounter_id"] = encounter_id
    return await client.post(
        "/api/documents/upload", data=data,
        files={"file": (filename, content, ctype)},
    )


# ── A. Consent enforcement (P7-B1) ────────────────────────────────────────

class TestConsentEnforcement:

    async def test_init_leaves_consent_pending_not_granted(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            assert ids["consent_status"] == "PENDING"
            consent = await _db_consent(ids["encounter_id"])
            assert consent is not None
            assert consent.granted is False
            assert consent.granted_at is None
            assert consent.audio_consent_granted is False
            # Nothing may claim the patient agreed before the consent screen
            assert "CONSENT_GRANTED" not in await _db_audit_actions(ids["encounter_id"])

    async def test_explicit_acceptance_records_granted_and_audits(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _consent(client, ids, granted=True, audio_consent=True)
            assert resp.status_code == 200
            body = resp.json()
            assert body["consent_status"] == "GRANTED"
            assert body["audio_consent_granted"] is True
            consent = await _db_consent(ids["encounter_id"])
            assert consent.granted is True
            assert consent.granted_at is not None
            assert "CONSENT_GRANTED" in await _db_audit_actions(ids["encounter_id"])

    async def test_explicit_rejection_records_decline(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _consent(client, ids, granted=False)
            assert resp.json()["consent_status"] == "DECLINED"
            consent = await _db_consent(ids["encounter_id"])
            assert consent.granted is False
            assert consent.granted_at is None
            # audio cannot be granted if overall consent declined
            assert consent.audio_consent_granted is False
            assert "CONSENT_DECLINED" in await _db_audit_actions(ids["encounter_id"])

    async def test_missing_consent_stays_pending_and_exports_draft_deny(self):
        """§2A: consent never given must NOT appear as granted anywhere —
        including the FHIR export."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            headers = await _doctor_headers()
            resp = await client.get(f"/api/fhir/encounter/{ids['encounter_id']}", headers=headers)
            assert resp.status_code == 200
            consents = _bundle_resources(resp.json(), "Consent")
            assert len(consents) == 1
            assert consents[0]["status"] == "draft"
            assert consents[0]["provision"]["type"] == "deny"

    async def test_repeated_identical_submission_is_idempotent(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids, granted=True)
            first = await _db_consent(ids["encounter_id"])
            first_granted_at = first.granted_at
            await _consent(client, ids, granted=True)  # double tap / retry
            actions = await _db_audit_actions(ids["encounter_id"])
            assert actions.count("CONSENT_GRANTED") == 1
            again = await _db_consent(ids["encounter_id"])
            assert again.granted_at == first_granted_at

    async def test_changed_decision_reaudits(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids, granted=True)
            await _consent(client, ids, granted=False)
            actions = await _db_audit_actions(ids["encounter_id"])
            assert actions.count("CONSENT_GRANTED") == 1
            assert actions.count("CONSENT_DECLINED") == 1
            consent = await _db_consent(ids["encounter_id"])
            assert consent.granted is False

    async def test_consent_forgery_for_other_patients_encounter_rejected(self):
        """§2A: one session cannot write consent onto another patient's
        encounter with a guessed/modified id pair."""
        async with _asgi() as client:
            ids_a = await _start_intake(client, name="Patient A")
            ids_b = await _start_intake(client, name="Patient B")
            resp = await client.post("/api/intake/consent", json={
                "encounter_id": ids_a["encounter_id"],
                "patient_id": ids_b["patient_id"],
                "granted": True,
            })
            assert resp.status_code == 400
            consent = await _db_consent(ids_a["encounter_id"])
            assert consent.granted is False  # untouched

    async def test_consent_for_unknown_encounter_404(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await client.post("/api/intake/consent", json={
                "encounter_id": str(uuid.uuid4()),
                "patient_id": ids["patient_id"],
                "granted": True,
            })
            assert resp.status_code == 404


# ── A2. Anonymous-session boundaries ──────────────────────────────────────

class TestSessionBoundaries:

    async def test_session_ids_are_uuid4_unguessable(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            assert UUID(ids["session_id"]).version == 4
            assert UUID(ids["encounter_id"]).version == 4

    async def test_guessed_session_id_cannot_receive_data(self):
        async with _asgi() as client:
            fake = str(uuid.uuid4())
            resp = await client.post("/api/intake/answer", json={
                "session_id": fake, "section_id": "SITE",
                "question_text": "Q", "answer_text": "A",
            })
            assert resp.status_code == 404
            resp = await client.post(f"/api/intake/complete/{fake}")
            assert resp.status_code == 404

    async def test_one_session_cannot_read_another_via_doctor_routes(self):
        """§2A: PHI reads stay behind the DOCTOR token boundary (Phase 6)."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await client.get(f"/api/doctor/patient/{ids['patient_id']}")
            assert resp.status_code == 401
            resp = await client.get(f"/api/documents/patient/{ids['patient_id']}")
            assert resp.status_code == 401


# ── B. Speech honesty (§2B) ───────────────────────────────────────────────

class _FakeSpeechProvider:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def transcribe(self, audio_bytes: bytes, language: str = "en"):
        if self._exc:
            raise self._exc
        return self._result


class TestSpeechHonesty:

    async def test_empty_audio_rejected(self):
        async with _asgi() as client:
            resp = await client.post("/api/speech/transcribe",
                                     files={"audio": ("a.wav", b"abc", "audio/wav")},
                                     data={"language": "hi"})
            assert resp.status_code == 400

    async def test_unsupported_language_rejected(self):
        async with _asgi() as client:
            resp = await client.post("/api/speech/transcribe",
                                     files={"audio": ("a.wav", b"x" * 500, "audio/wav")},
                                     data={"language": "de"})
            assert resp.status_code == 400

    async def test_oversized_audio_rejected(self):
        async with _asgi() as client:
            resp = await client.post("/api/speech/transcribe",
                                     files={"audio": ("a.wav", b"\x00" * (15 * 1024 * 1024 + 10), "audio/wav")},
                                     data={"language": "en"})
            assert resp.status_code == 413

    async def test_unavailable_provider_reports_503_not_fake_text(self):
        async with _asgi() as client:
            result = TranscriptionResult(transcript="", language="hi", confidence=0.0,
                                         provider="unavailable:IndicConformer")
            provider = _FakeSpeechProvider(result=result)
            import backend.app.api.speech_router as sr
            original = sr.get_speech_provider
            sr.get_speech_provider = lambda lang: provider
            try:
                resp = await client.post("/api/speech/transcribe",
                                         files={"audio": ("a.wav", b"x" * 500, "audio/wav")},
                                         data={"language": "hi"})
            finally:
                sr.get_speech_provider = original
            assert resp.status_code == 503

    async def test_runtime_error_maps_to_503(self):
        async with _asgi() as client:
            provider = _FakeSpeechProvider(exc=RuntimeError("model load failed"))
            original = speech_router.get_speech_provider
            speech_router.get_speech_provider = lambda lang: provider
            try:
                resp = await client.post("/api/speech/transcribe",
                                         files={"audio": ("a.wav", b"x" * 500, "audio/wav")},
                                         data={"language": "gu"})
            finally:
                speech_router.get_speech_provider = original
            assert resp.status_code == 503

    @pytest.mark.parametrize("lang,transcript", [
        ("en", "sharp chest pain since morning"),
        ("hi", "seene mein dard"),
        ("gu", "chapra mate dard"),
    ])
    async def test_transcription_passthrough_en_hi_gu(self, lang, transcript):
        async with _asgi() as client:
            result = TranscriptionResult(transcript=transcript, language=lang,
                                         confidence=0.91, provider="fake:test")
            provider = _FakeSpeechProvider(result=result)
            original = speech_router.get_speech_provider
            speech_router.get_speech_provider = lambda l: provider
            try:
                resp = await client.post("/api/speech/transcribe",
                                         files={"audio": ("a.wav", b"x" * 500, "audio/wav")},
                                         data={"language": lang})
            finally:
                speech_router.get_speech_provider = original
            assert resp.status_code == 200
            assert resp.json()["transcript"] == transcript


# ── C. Red flags + AI fallback (§2C) ──────────────────────────────────────

class TestRedFlagsAndAI:

    async def test_red_flag_raises_emergency_and_persists(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _answer(client, ids["session_id"], "SITE",
                          "Where is the pain?", "Pain at center of chest")
            res = await _answer(client, ids["session_id"], "RADIATION",
                                "Does it spread anywhere?", "Spreads to left arm")
            assert res["red_flag_triggered"] is True
            async with _test_session_factory() as db:
                enc = (await db.execute(
                    select(Encounter).where(Encounter.id == ids["encounter_id"]))).scalars().first()
                assert enc.priority == "EMERGENCY"

    async def test_emergency_survives_later_answers_and_completion(self, monkeypatch):
        """§2C: later benign answers and a failing LLM must not demote or
        erase the emergency escalation."""
        async def broken_chat(self, *a, **kw):
            raise ConnectionError("ollama down")
        monkeypatch.setattr(LocalLLMClient, "chat", broken_chat)

        async with _asgi() as client:
            ids = await _start_intake(client)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Pain at center of chest")
            await _answer(client, ids["session_id"], "RADIATION", "Spread?", "Spreads to left arm")
            await _answer(client, ids["session_id"], "ONSET", "When?", "Gradual over months")

            fu = await client.post("/api/intake/followup-questions", json={
                "session_id": ids["session_id"], "language": "en"})
            assert fu.status_code == 200
            fu_body = fu.json()
            assert fu_body["source"] == "rule_fallback"          # safe fallback
            assert fu_body["escalation_required"] is True          # deterministic
            assert any(rf["priority"] == "EMERGENCY" for rf in fu_body["red_flags"])

            done = await client.post(f"/api/intake/complete/{ids['session_id']}")
            assert done.json()["priority"] == "EMERGENCY"

            headers = await _doctor_headers()
            q1 = (await client.get("/api/doctor/queue", headers=headers)).json()
            q2 = (await client.get("/api/doctor/queue", headers=headers)).json()  # refresh
            assert q1 and q1[0]["priority"] == "EMERGENCY"
            assert q2[0]["encounter_id"] == ids["encounter_id"]
            assert q2[0]["red_flag_alerts"]  # alert still attached after refresh

    async def test_dismissive_llm_cannot_suppress_red_flag(self, monkeypatch):
        """§2C: even if the model returns 'don't worry' content, validation
        rejects it and the deterministic escalation still fires."""
        async def dismissive_chat(self, *a, **kw):
            return '[{"text": "Dont worry, nothing serious about the chest", "section": "FOLLOW_UP"}]'
        monkeypatch.setattr(LocalLLMClient, "chat", dismissive_chat)

        async with _asgi() as client:
            ids = await _start_intake(client)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Pain at center of chest")
            await _answer(client, ids["session_id"], "RADIATION", "Spread?", "Spreads to left arm")
            fu = await client.post("/api/intake/followup-questions", json={
                "session_id": ids["session_id"], "language": "en"})
            body = fu.json()
            assert body["escalation_required"] is True
            assert all("worry" not in q["text"].lower() for q in body["questions"])

    async def test_ai_summary_never_overwrites_patient_answers(self, mock_summary_llm):
        """P7-B2/B: the draft is stored separately; original rows untouched."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _answer(client, ids["session_id"], "SITE", "Where?",
                          "Pain at center of chest", method="voice")
            await client.post(f"/api/intake/complete/{ids['session_id']}")
            async with _test_session_factory() as db:
                rows = (await db.execute(
                    select(HistoryResponse))).scalars().all()
                assert any(r.answer_text == "Pain at center of chest" for r in rows)
                summary = (await db.execute(select(ClinicalSummary))).scalars().first()
                assert summary.chief_complaint == "Chest pain x 2 days"  # AI draft distinct


# ── D. Document / OCR pipeline (§2D) ──────────────────────────────────────

class TestDocumentPipeline:

    async def test_unsupported_type_rejected_before_disk(self, monkeypatch):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"],
                                 filename="notes.txt", content=b"hello", ctype="text/plain")
            assert resp.status_code == 415

    async def test_empty_file_rejected(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"], content=b"")
            assert resp.status_code == 400

    async def test_oversized_file_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "MAX_DOCUMENT_UPLOAD_MB", 0)
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"],
                                 content=b"12345")
            assert resp.status_code == 413

    async def test_unknown_encounter_rejected(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], str(uuid.uuid4()))
            assert resp.status_code == 404

    async def test_no_text_upload_stays_honest(self, monkeypatch):
        """§2D NO_TEXT: nothing extracted, nothing invented, original kept."""
        monkeypatch.setattr(document_router.processor, "extract_blocking",
                            lambda path, mime: _extracted_blank())
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"])
            assert resp.status_code == 200
            body = resp.json()
            assert body["ocr_status"] == "NO_TEXT"
            assert body["entities"] == []
            assert "message" in body
            assert "DOCUMENT_UPLOADED_NO_TEXT" in await _db_audit_actions(body["document_id"])
            async with _test_session_factory() as db:
                doc = (await db.execute(select(MedicalDocument))).scalars().first()
                import os as _os
                assert _os.path.isfile(doc.file_path)  # original preserved

    async def test_ocr_timeout_returns_504_and_marks_failed(self, monkeypatch):
        def slow_extract(path, mime):
            import time
            time.sleep(1.0)
            return _extracted_blank()
        monkeypatch.setattr(document_router.processor, "extract_blocking", slow_extract)
        monkeypatch.setattr(settings, "OCR_TIMEOUT_SECONDS", 0.05)
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"])
            assert resp.status_code == 504
            async with _test_session_factory() as db:
                doc = (await db.execute(select(MedicalDocument))).scalars().first()
                assert doc.ocr_status == "FAILED"

    async def test_engine_crash_marks_failed_never_fabricates(self, monkeypatch):
        def crash_extract(path, mime):
            raise RuntimeError("Paddle oneDNN crash")
        monkeypatch.setattr(document_router.processor, "extract_blocking", crash_extract)
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"])
            assert resp.status_code == 500
            async with _test_session_factory() as db:
                doc = (await db.execute(select(MedicalDocument))).scalars().first()
                assert doc.ocr_status == "FAILED"
                assert doc.ocr_text in ("", None)

    async def test_entities_unverified_until_doctor_confirms(self, monkeypatch):
        """§2D: extraction stores doctor_verified=False; verification is a
        DOCTOR-only clinical act with an audit row."""
        monkeypatch.setattr(document_router.processor, "extract_blocking",
                            lambda path, mime: _extracted_with_entities())
        async with _asgi() as client:
            ids = await _start_intake(client)
            resp = await _upload(client, ids["patient_id"], ids["encounter_id"])
            assert resp.status_code == 200
            body = resp.json()
            assert body["ocr_status"] == "COMPLETED"
            assert all(e["verified"] is False for e in body["entities"])
            assert "DOCUMENT_OCR_PROCESSED" in await _db_audit_actions(body["document_id"])

            # anonymous verification refused
            ent_id = (await _db_entity_ids(body["document_id"]))[0]
            resp = await client.post(f"/api/doctor/verify-entity/{ent_id}")
            assert resp.status_code == 401

            headers = await _doctor_headers()
            resp = await client.post(f"/api/doctor/verify-entity/{ent_id}", headers=headers)
            assert resp.status_code == 200
            async with _test_session_factory() as db:
                ent = (await db.execute(
                    select(ExtractedEntity).where(ExtractedEntity.id == ent_id))).scalars().first()
                assert ent.doctor_verified is True
            assert "OCR_ENTITY_VERIFIED" in await _db_audit_actions(ent_id)

    async def test_document_travels_to_doctor_workstation(self, monkeypatch):
        """§2D workflow step 6→7: dossier shows the upload + unverified entities."""
        monkeypatch.setattr(document_router.processor, "extract_blocking",
                            lambda path, mime: _extracted_with_entities())
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _upload(client, ids["patient_id"], ids["encounter_id"])
            headers = await _doctor_headers()
            dossier = (await client.get(
                f"/api/doctor/patient/{ids['patient_id']}", headers=headers)).json()
            docs = dossier["documents"]
            assert len(docs) == 1
            assert docs[0]["ocr_status"] == "COMPLETED"
            assert docs[0]["extracted_entities"]
            assert all(e["doctor_verified"] is False for e in docs[0]["extracted_entities"])


async def _db_entity_ids(document_id: str) -> List[str]:
    async with _test_session_factory() as db:
        res = await db.execute(select(ExtractedEntity).where(ExtractedEntity.document_id == document_id))
        return [e.id for e in res.scalars().all()]


# ── E/F. Duplicate submissions, sign-off, queue, FHIR final state ────────

class TestDuplicateAndSignOff:

    async def test_complete_is_idempotent(self, mock_summary_llm):
        """P7-B3: retry posts exactly one ClinicalSummary and one LLM call."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Head")
            r1 = await client.post(f"/api/intake/complete/{ids['session_id']}")
            r2 = await client.post(f"/api/intake/complete/{ids['session_id']}")
            assert r1.status_code == 200 and r2.status_code == 200
            assert r1.json().get("already_completed") is None
            assert r2.json()["already_completed"] is True
            assert r2.json()["chief_complaint"] == r1.json()["chief_complaint"]
            assert len(mock_summary_llm) == 1
            assert len(await _db_summaries(ids["encounter_id"])) == 1

    async def test_repeated_signoff_rejected(self, mock_summary_llm):
        """§2E: double click on sign-off cannot re-finalize."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Head")
            await client.post(f"/api/intake/complete/{ids['session_id']}")
            summary = (await _db_summaries(ids["encounter_id"]))[0]
            headers = await _doctor_headers()
            body = {"confirm": True, "doctor_notes": "Reviewed."}
            r1 = await client.put(f"/api/doctor/summary/{summary.id}", json=body, headers=headers)
            r2 = await client.put(f"/api/doctor/summary/{summary.id}", json=body, headers=headers)
            assert r1.status_code == 200 and r1.json()["is_confirmed"] is True
            assert r2.status_code == 409

    async def test_signed_summary_cannot_be_regenerated_by_ai(self, mock_summary_llm):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Head")
            await client.post(f"/api/intake/complete/{ids['session_id']}")
            summary = (await _db_summaries(ids["encounter_id"]))[0]
            headers = await _doctor_headers()
            await client.put(f"/api/doctor/summary/{summary.id}",
                             json={"confirm": True}, headers=headers)
            resp = await client.post(
                f"/api/doctor/encounter/{ids['encounter_id']}/generate-llm-summary",
                headers=headers)
            assert resp.status_code == 409

    async def test_admin_cannot_sign_off(self, mock_summary_llm):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Head")
            await client.post(f"/api/intake/complete/{ids['session_id']}")
            summary = (await _db_summaries(ids["encounter_id"]))[0]
            headers = await _doctor_headers(role="ADMIN")
            resp = await client.put(f"/api/doctor/summary/{summary.id}",
                                    json={"confirm": True}, headers=headers)
            assert resp.status_code == 403


# ── QA BUG-001 (Phase 9): on-demand LLM summary on UNSIGNED encounters ────

class TestLlmSummaryOnDemandFix:
    """BUG-001 regression: POST /generate-llm-summary previously raised
    AttributeError (deterministic HTTP 500) because it queried
    MedicalDocument.medications/observations — relationships that do not
    exist on the model. Context must be built from real ExtractedEntity
    rows; signed records and RBAC behavior stay unchanged."""

    async def test_unsigned_with_ocr_documents_returns_200(self, monkeypatch):
        captured = {}

        async def _fake_generate(patient_info=None, intake_responses=None,
                                 documents_extracted=None, timeline_events=None):
            captured["documents_extracted"] = documents_extracted
            return ClinicalSummaryCreate(chief_complaint="Regenerated draft",
                                         hpi="Physician-triggered re-synthesis.")

        monkeypatch.setattr(document_router.processor, "extract_blocking",
                            lambda path, mime: _extracted_with_entities())
        monkeypatch.setattr(llm_service, "generate_clinical_summary", _fake_generate)
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _upload(client, ids["patient_id"], ids["encounter_id"])
            headers = await _doctor_headers()
            resp = await client.post(
                f"/api/doctor/encounter/{ids['encounter_id']}/generate-llm-summary",
                headers=headers)
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "SUCCESS"
            # The LLM saw document data derived from ExtractedEntity rows.
            docs = captured["documents_extracted"]
            assert len(docs) == 1
            assert docs[0]["medications"][0]["name"] == "Paracetamol"
            assert docs[0]["observations"][0]["test_name"] == "HbA1c"

    async def test_unsigned_without_documents_returns_200(self, monkeypatch):
        async def _fake_generate(**kwargs):
            return ClinicalSummaryCreate(chief_complaint="Draft", hpi="No docs")

        monkeypatch.setattr(llm_service, "generate_clinical_summary", _fake_generate)
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            headers = await _doctor_headers()
            resp = await client.post(
                f"/api/doctor/encounter/{ids['encounter_id']}/generate-llm-summary",
                headers=headers)
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "SUCCESS"

    async def test_signed_encounter_still_returns_409(self, mock_summary_llm):
        """The fix must not weaken the signed-record guard — and the guard
        runs BEFORE any LLM spend (call count stays at the one /complete use)."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids)
            await _answer(client, ids["session_id"], "SITE", "Where?", "Head")
            await client.post(f"/api/intake/complete/{ids['session_id']}")
            assert len(mock_summary_llm) == 1
            summary = (await _db_summaries(ids["encounter_id"]))[0]
            headers = await _doctor_headers()
            await client.put(f"/api/doctor/summary/{summary.id}",
                             json={"confirm": True}, headers=headers)
            resp = await client.post(
                f"/api/doctor/encounter/{ids['encounter_id']}/generate-llm-summary",
                headers=headers)
            assert resp.status_code == 409
            assert len(mock_summary_llm) == 1  # no second LLM call after signing

    async def test_rbac_unchanged_on_generate_endpoint(self):
        """No token -> 401; wrong role -> 403. The fix does not relax RBAC."""
        async with _asgi() as client:
            ids = await _start_intake(client)
            url = f"/api/doctor/encounter/{ids['encounter_id']}/generate-llm-summary"
            anon = await client.post(url)
            assert anon.status_code == 401
            patient_headers = await _doctor_headers(role="NURSE")
            wrong_role = await client.post(url, headers=patient_headers)
            assert wrong_role.status_code == 403


# ── Full workflow trace: intake → sign-off (§1, §2F) ──────────────────────

class TestEndToEndWorkflow:

    async def test_full_patient_to_physician_flow(self, mock_summary_llm, monkeypatch):
        async def broken_chat(self, *a, **kw):
            raise ConnectionError("no local model in tests")
        monkeypatch.setattr(LocalLLMClient, "chat", broken_chat)
        monkeypatch.setattr(document_router.processor, "extract_blocking",
                            lambda path, mime: _extracted_with_entities())

        async with _asgi() as client:
            # 1–2. language + check-in + explicit consent
            ids = await _start_intake(client, name="Workflow Patient", language="hi")
            assert ids["consent_status"] == "PENDING"
            consent = await _consent(client, ids, granted=True, audio_consent=True)
            assert consent.json()["consent_status"] == "GRANTED"

            # 3. symptom answers (text + voice), red-flag pair included
            await _answer(client, ids["session_id"], "SITE",
                          "Where is the pain?", "Pain at center of chest")
            await _answer(client, ids["session_id"], "RADIATION",
                          "Does it spread?", "Spreads to left arm")
            await _answer(client, ids["session_id"], "ASSOCIATED_SYMPTOMS",
                          "Anything else?", "Cold sweats", method="voice")

            # 4. follow-ups degrade safely, escalation stays deterministic
            fu = (await client.post("/api/intake/followup-questions", json={
                "session_id": ids["session_id"], "language": "hi"})).json()
            assert fu["source"] == "rule_fallback"
            assert fu["escalation_required"] is True

            # 5–6. document upload, honest unverified entities
            up = (await _upload(client, ids["patient_id"], ids["encounter_id"])).json()
            assert up["ocr_status"] == "COMPLETED"

            # completion
            done = await client.post(f"/api/intake/complete/{ids['session_id']}")
            assert done.status_code == 200
            assert done.json()["priority"] == "EMERGENCY"

            headers = await _doctor_headers()

            # 7. encounter reaches the workstation at the top of the queue
            queue = (await client.get("/api/doctor/queue", headers=headers)).json()
            mine = [q for q in queue if q["encounter_id"] == ids["encounter_id"]]
            assert len(mine) == 1
            assert queue[0]["encounter_id"] == ids["encounter_id"]
            assert queue[0]["red_flag_alerts"]

            # 8. doctor sees answers, summary, docs and flags in one dossier
            dossier = (await client.get(
                f"/api/doctor/patient/{ids['patient_id']}?encounter_id={ids['encounter_id']}",
                headers=headers)).json()
            statements = dossier["patient_statements"]
            assert {s["answer_text"] for s in statements} >= {
                "Pain at center of chest", "Spreads to left arm", "Cold sweats"}
            assert any(s["input_method"] == "voice" for s in statements)
            assert dossier["summary"]["is_confirmed"] is False
            assert dossier["encounter"]["priority"] == "EMERGENCY"
            assert dossier["encounter"]["red_flags"]

            # FHIR BEFORE sign-off: consent active, composition preliminary
            bundle = (await client.get(
                f"/api/fhir/encounter/{ids['encounter_id']}", headers=headers)).json()
            consent_res = _bundle_resources(bundle, "Consent")
            assert consent_res[0]["status"] == "active"
            assert consent_res[0]["provision"]["type"] == "permit"
            comp = _bundle_resources(bundle, "Composition")
            assert comp[0]["status"] == "preliminary"

            # 9. verify an OCR entity, then sign the summary
            ent_ids = await _db_entity_ids(up["document_id"])
            assert ent_ids
            ver = await client.post(f"/api/doctor/verify-entity/{ent_ids[0]}", headers=headers)
            assert ver.json()["status"] == "VERIFIED"
            summary = (await _db_summaries(ids["encounter_id"]))[0]
            signed = await client.put(f"/api/doctor/summary/{summary.id}",
                                      json={"confirm": True, "doctor_notes": "Signed after review."},
                                      headers=headers)
            assert signed.json()["is_confirmed"] is True

            # 10. final state everywhere: encounter, queue, audit, FHIR
            async with _test_session_factory() as db:
                enc = (await db.execute(select(Encounter)
                     .where(Encounter.id == ids["encounter_id"]))).scalars().first()
                assert enc.status == "FINALIZED"
            # Product rule (QA-05): the signed encounter stays in the queue's
            # Completed bucket (sorted last) and must read FINALIZED.
            queue_after = (await client.get("/api/doctor/queue", headers=headers)).json()
            signed_rows = [q for q in queue_after if q["encounter_id"] == ids["encounter_id"]]
            assert signed_rows, "signed encounter must remain visible under Completed"
            assert signed_rows[0]["status"] == "FINALIZED"

            actions = await _db_audit_actions(ids["encounter_id"])
            for expected in ("INTAKE_INITIALIZED", "CONSENT_GRANTED", "INTAKE_COMPLETED"):
                assert expected in actions
            doc_actions = await _db_audit_actions(up["document_id"])
            assert "DOCUMENT_OCR_PROCESSED" in doc_actions

            bundle2 = (await client.get(
                f"/api/fhir/encounter/{ids['encounter_id']}", headers=headers)).json()
            assert _bundle_resources(bundle2, "Composition")[0]["status"] == "final"
            assert _bundle_resources(bundle2, "Encounter")[0]["status"] == "finished"
            # document URLs are opaque — no filesystem paths anywhere
            for dr in _bundle_resources(bundle2, "DocumentReference"):
                url = dr["content"][0]["attachment"]["url"]
                assert url.startswith("api/documents/file/")
                assert "uploads" not in url and "\\" not in url and ":" not in url.replace("api:", "")

            # provenance tags retained
            obs = _bundle_resources(bundle2, "Observation")
            assert all("tag" in o.get("meta", {}) for o in obs)

            # ABDM push remains explicitly simulated
            push = await client.post(f"/api/fhir/abdm/push/{ids['encounter_id']}", headers=headers)
            assert push.status_code == 200
            body = push.json()
            assert body["status"] == "SIMULATED_NOT_TRANSMITTED"
            assert "not an ABDM-certified integration" in body["gateway_note"]

    async def test_declined_consent_exports_deny_and_revoked_state(self):
        async with _asgi() as client:
            ids = await _start_intake(client)
            await _consent(client, ids, granted=False)
            headers = await _doctor_headers()
            bundle = (await client.get(
                f"/api/fhir/encounter/{ids['encounter_id']}", headers=headers)).json()
            consent = _bundle_resources(bundle, "Consent")[0]
            assert consent["status"] == "draft"
            assert consent["provision"]["type"] == "deny"

            # explicit revocation after granting is exported as revoked
            async with _test_session_factory() as db:
                rec = (await db.execute(select(ConsentRecord)
                       .where(ConsentRecord.encounter_id == ids["encounter_id"]))).scalars().first()
                rec.granted = True
                rec.revoked = True
                await db.commit()
            bundle2 = (await client.get(
                f"/api/fhir/encounter/{ids['encounter_id']}", headers=headers)).json()
            assert _bundle_resources(bundle2, "Consent")[0]["status"] == "revoked"
