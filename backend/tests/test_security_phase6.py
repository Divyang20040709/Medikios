"""
Phase 6 — Security, Clinical Safety & FHIR audit regression tests.

Every test here pins a fix for a CONFIRMED audit finding (see the Phase 6
report). Synthetic data only — never real patient records.

Confirmed findings covered:
  F-01 Staff login previously worked with NO password            -> 401 now
  F-02 require_roles passed anonymous callers on clinical/admin
       endpoints (verify-entity, sign-off, PHI reads, FHIR)      -> 401 now
  F-03 unsalted SHA-256 password storage                        -> bcrypt (+ legacy verify)
  F-04 public /uploads static mount exposed every original doc  -> removed,
       role-guarded GET /api/documents/file/{id} instead
  F-05 /api/documents/patient/{id} readable by anyone (IDOR)    -> DOCTOR/ADMIN only
  F-06 unauthenticated FHIR export + false ABDM compliance claim-> guarded + honest
  F-07 patient-identifying data in server log prints            -> removed
  F-08 signed summary could be silently overwritten by AI       -> 409 guard
  Safety: deterministic red-flag escalation independent of LLM output.
"""

import hashlib
import io
import json
import os
import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import (
    User, Patient, Encounter, ConsentRecord, MedicalDocument, ExtractedEntity,
    ClinicalSummary, Observation, RedFlagAlert, AuditLog, IntegrationEvent,
)
from backend.app.api.auth_router import (
    create_access_token, get_password_hash, verify_password, is_legacy_hash,
)
from backend.app.api import document_router

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)

LEGACY_PW = "SyntheticPw123"


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def setup_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db

    tag = uuid.uuid4().hex[:8]
    async with _test_session_factory() as db:
        db.add_all([
            User(id="u-doc", full_name="Dr Synthetic", role="DOCTOR",
                 email=f"doc.{tag}@test.local", phone=f"98{tag[:6]}01",
                 password_hash=hashlib.sha256(LEGACY_PW.encode()).hexdigest()),
            User(id="u-adm", full_name="Admin Synthetic", role="ADMIN",
                 email=f"adm.{tag}@test.local", password_hash=hashlib.sha256(LEGACY_PW.encode()).hexdigest()),
            User(id="u-pat", full_name="Patient Synthetic", role="PATIENT",
                 email=f"pat.{tag}@test.local", password_hash=hashlib.sha256(LEGACY_PW.encode()).hexdigest()),
        ])
        patient = Patient(id="p-sec", name="Synthetic Patient", age=55, gender="MALE",
                          phone="9000000099", mrn=f"MRN-P6-{tag}", abha_id="91-1111-2222-3333")
        db.add(patient)
        await db.flush()
        enc = Encounter(id="e-sec", patient_id=patient.id, token_number="OPD-P601",
                        status="WAITING_CONSULTATION", priority="ROUTINE", department="Cardiology")
        db.add(enc)
        await db.flush()
        db.add(ConsentRecord(encounter_id=enc.id, patient_id=patient.id, granted=True))
        doc = MedicalDocument(id="d-sec", patient_id=patient.id, encounter_id=enc.id,
                              document_type="LAB_REPORT", file_name="syn.jpg",
                              file_path="C:\\secret\\server\\path\\syn.jpg",
                              mime_type="image/jpeg", ocr_status="COMPLETED", overall_confidence=0.8)
        db.add(doc)
        await db.flush()
        db.add_all([
            ExtractedEntity(id="x-sec", document_id=doc.id, entity_type="MEDICATION",
                            entity_name="Metformin", entity_value="500 mg", doctor_verified=False),
            Observation(id="o-sec", patient_id=patient.id, test_name="Urine culture",
                        test_value="Trace growth", unit="", flag="NORMAL"),
            RedFlagAlert(id="rf-sec", encounter_id=enc.id, patient_id=patient.id,
                         trigger_rule="ACUTE_CHEST_DISCOMFORT_TRIAGE",
                         description="Synthetic red flag", priority="EMERGENCY"),
        ])
        await db.commit()
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _token(user_id: str, role: str, minutes: int = 60) -> str:
    return create_access_token(
        data={"sub": user_id, "role": role},
        expires_delta=timedelta(minutes=minutes),
    )


def _headers(user_id: str, role: str, minutes: int = 60) -> dict:
    return {"Authorization": f"Bearer {_token(user_id, role, minutes)}"}


BAD_TOKEN = {"Authorization": "Bearer not.a.jwt"}
EXPIRED_DOCTOR = {"Authorization": f"Bearer {_token('u-doc', 'DOCTOR', minutes=-5)}"}
DOCTOR = lambda: _headers("u-doc", "DOCTOR")          # noqa: E731
ADMIN = lambda: _headers("u-adm", "ADMIN")            # noqa: E731
PATIENT = lambda: _headers("u-pat", "PATIENT")        # noqa: E731


# ── F-03: password storage ────────────────────────────────────────────────

class TestPasswordHashing:
    def test_new_hashes_are_salted_bcrypt(self):
        h = get_password_hash(LEGACY_PW)
        assert h.startswith("$2") and h != get_password_hash(LEGACY_PW)  # salted
        assert verify_password(LEGACY_PW, h) and not verify_password("wrong", h)

    def test_legacy_sha256_still_verifies(self):
        legacy = hashlib.sha256(LEGACY_PW.encode()).hexdigest()
        assert is_legacy_hash(legacy)
        assert verify_password(LEGACY_PW, legacy) and not verify_password("wrong", legacy)

    def test_empty_hash_never_matches(self):
        assert not verify_password("anything", "")


# ── F-01: login hardening ─────────────────────────────────────────────────

class TestLoginHardening:
    async def test_doctor_login_without_password_rejected(self):
        async with _client() as c:
            resp = await c.post("/api/auth/login",
                                json={"identifier": "u1@nope.test", "role": "DOCTOR"})
            # Unknown user OR missing password must never mint a staff token.
            assert resp.status_code == 401

    async def test_existing_staff_login_requires_password(self):
        async with _client() as c:
            email = (await _user_email("u-doc"))
            resp = await c.post("/api/auth/login", json={"identifier": email, "role": "DOCTOR"})
            assert resp.status_code == 401
            assert "password" in resp.json()["detail"].lower()

    async def test_wrong_staff_password_rejected(self):
        async with _client() as c:
            resp = await c.post("/api/auth/login", json={
                "identifier": await _user_email("u-doc"), "password": "guess", "role": "DOCTOR"})
            assert resp.status_code == 401

    async def test_role_mismatch_rejected(self):
        async with _client() as c:
            resp = await c.post("/api/auth/login", json={
                "identifier": await _user_email("u-doc"), "password": LEGACY_PW, "role": "ADMIN"})
            assert resp.status_code == 401

    async def test_valid_legacy_login_succeeds_and_hash_upgraded(self):
        async with _client() as c:
            resp = await c.post("/api/auth/login", json={
                "identifier": await _user_email("u-doc"), "password": LEGACY_PW, "role": "DOCTOR"})
            assert resp.status_code == 200
            assert resp.json()["access_token"]
        async with _test_session_factory() as db:
            user = (await db.execute(select(User).where(User.id == "u-doc"))).scalars().first()
            assert user.password_hash.startswith("$2")  # upgraded from SHA-256
            assert verify_password(LEGACY_PW, user.password_hash)
            upgrade = (await db.execute(
                select(AuditLog).where(AuditLog.action == "PASSWORD_HASH_UPGRADED"))).scalars().first()
            assert upgrade is not None

    async def test_staff_phone_cannot_be_used_on_patient_tab(self):
        phone = (await _user_phone("u-doc"))
        async with _client() as c:
            resp = await c.post("/api/auth/login", json={"identifier": phone, "role": "PATIENT"})
            assert resp.status_code == 401


async def _user_email(user_id: str) -> str:
    async with _test_session_factory() as db:
        u = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
        return u.email


async def _user_phone(user_id: str) -> str:
    async with _test_session_factory() as db:
        u = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
        return u.phone


# ── F-02: strict authorization on every PHI / clinical surface ────────────

PHI_ENDPOINTS = [
    ("get", "/api/doctor/queue"),
    ("get", "/api/doctor/patient/p-sec"),
    ("get", "/api/admin/telemetry"),
    ("get", "/api/admin/opd-queue"),
    ("get", "/api/admin/red-flags"),
    ("get", "/api/admin/audit-logs"),
    ("get", "/api/admin/staff"),
    ("get", "/api/documents/patient/p-sec"),
    ("get", "/api/documents/file/d-sec"),
    ("get", "/api/fhir/encounter/e-sec"),
    ("post", "/api/fhir/abdm/push/e-sec"),
]


class TestStrictAuthorization:
    @pytest.mark.parametrize("method,path", PHI_ENDPOINTS)
    async def test_anonymous_rejected_401(self, method, path):
        async with _client() as c:
            resp = await (c.get(path) if method == "get" else c.post(path))
            assert resp.status_code == 401, f"{method.upper()} {path} allowed anonymous"

    @pytest.mark.parametrize("method,path", PHI_ENDPOINTS)
    async def test_garbage_and_expired_tokens_rejected_401(self, method, path):
        async with _client() as c:
            for bad in (BAD_TOKEN, EXPIRED_DOCTOR):
                resp = await (c.get(path, headers=bad) if method == "get" else c.post(path, headers=bad))
                assert resp.status_code == 401

    async def test_patient_token_blocked_from_clinical_workspace(self):
        async with _client() as c:
            for path in ("/api/doctor/queue", "/api/doctor/patient/p-sec",
                         "/api/documents/patient/p-sec", "/api/fhir/encounter/e-sec",
                         "/api/admin/audit-logs"):
                assert (await c.get(path, headers=PATIENT())).status_code == 403

    async def test_doctor_allowed_phil_read_admin_allowed(self):
        async with _client() as c:
            assert (await c.get("/api/doctor/queue", headers=DOCTOR())).status_code == 200
            assert (await c.get("/api/admin/telemetry", headers=ADMIN())).status_code == 200

    async def test_admin_cannot_verify_entities_or_sign_off(self):
        """Verification and sign-off are clinical acts — DOCTOR role only."""
        async with _client() as c:
            resp = await c.post("/api/doctor/verify-entity/x-sec", headers=ADMIN())
            assert resp.status_code == 403
            async with _test_session_factory() as db:
                e = (await db.execute(select(ExtractedEntity).where(ExtractedEntity.id == "x-sec"))).scalars().first()
                assert e.doctor_verified is False  # rejected attempt changed nothing

    async def test_doctor_verify_entity_requires_token_and_audits(self):
        async with _client() as c:
            anon = await c.post("/api/doctor/verify-entity/x-sec")
            assert anon.status_code == 401  # F-02: previously succeeded anonymously
            ok = await c.post("/api/doctor/verify-entity/x-sec", headers=DOCTOR())
            assert ok.status_code == 200
        async with _test_session_factory() as db:
            e = (await db.execute(select(ExtractedEntity).where(ExtractedEntity.id == "x-sec"))).scalars().first()
            assert e.doctor_verified is True
            audit = (await db.execute(
                select(AuditLog).where(AuditLog.action == "OCR_ENTITY_VERIFIED"))).scalars().first()
            assert audit is not None and audit.actor_id == "u-doc"

    async def test_anonymous_signoff_cannot_finalize(self):
        async with _client() as c:
            resp = await c.post("/api/doctor/encounter/e-sec/summary",
                                 json={"doctor_notes": "anonymous override", "confirm": True})
            assert resp.status_code == 401
            async with _test_session_factory() as db:
                enc = (await db.execute(select(Encounter).where(Encounter.id == "e-sec"))).scalars().first()
                assert enc.status != "FINALIZED"
            ok = await c.post("/api/doctor/encounter/e-sec/summary",
                              json={"doctor_notes": "signed", "confirm": True}, headers=DOCTOR())
            assert ok.status_code == 200 and ok.json()["is_confirmed"] is True

    async def test_anonymous_red_flag_acknowledge_rejected(self):
        async with _client() as c:
            resp = await c.post("/api/admin/red-flags/rf-sec/acknowledge",
                                json={"acknowledged_by": "whoever"})
            assert resp.status_code == 401
            async with _test_session_factory() as db:
                alert = (await db.execute(select(RedFlagAlert).where(RedFlagAlert.id == "rf-sec"))).scalars().first()
                assert alert.acknowledged is False  # emergency alert NOT suppressed
            ok = await c.post("/api/admin/red-flags/rf-sec/acknowledge",
                              json={"acknowledged_by": "ignored"}, headers=ADMIN())
            assert ok.status_code == 200


# ── F-04/F-05: document access control ────────────────────────────────────

class TestDocumentAccess:
    async def test_public_uploads_mount_removed(self):
        async with _client() as c:
            resp = await c.get("/uploads/syn.jpg")
            assert resp.status_code == 404  # no unauthenticated static serving

    async def test_controlled_download_requires_doctor(self, tmp_path, monkeypatch):
        payload = b"\xff\xd8\xff synthetic jpeg"
        (tmp_path / "stored.jpg").write_bytes(payload)
        monkeypatch.setattr(document_router, "UPLOAD_DIR", str(tmp_path))
        # Point the record at the tmp file (basename only matters).
        async with _test_session_factory() as db:
            d = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == "d-sec"))).scalars().first()
            d.file_path = "stored.jpg"
            await db.commit()

        async with _client() as c:
            assert (await c.get("/api/documents/file/d-sec")).status_code == 401
            assert (await c.get("/api/documents/file/d-sec", headers=PATIENT())).status_code == 403
            ok = await c.get("/api/documents/file/d-sec", headers=DOCTOR())
            assert ok.status_code == 200
            assert ok.content == payload
        async with _test_session_factory() as db:
            dl = (await db.execute(
                select(AuditLog).where(AuditLog.action == "DOCUMENT_DOWNLOADED"))).scalars().first()
            assert dl is not None and dl.actor_id == "u-doc"

    async def test_traversal_path_in_record_never_escalates(self):
        async with _client() as c:
            # d-sec's stored path is an absolute foreign path; the endpoint
            # only ever joins the BASENAME inside UPLOAD_DIR.
            resp = await c.get("/api/documents/file/d-sec", headers=DOCTOR())
            assert resp.status_code == 404  # basename not in uploads dir -> refused
            resp2 = await c.get("/api/documents/file/ghost", headers=DOCTOR())
            assert resp2.status_code == 404

    async def test_kiosk_upload_boundary_stays_anonymous(self):
        """Shared-kiosk upload is an intentional anonymous surface (Phase 4)."""
        async with _client() as c:
            buf = io.BytesIO(b"\xff\xd8\xff" + b"0" * 100)
            resp = await c.post(
                "/api/documents/upload",
                data={"patient_id": "p-sec"},
                files={"file": ("kiosk.jpg", buf, "image/jpeg")},
            )
            assert resp.status_code == 200  # upload must NOT start requiring a token
            # Cleanup: remove the synthetic upload artifact from disk.
            doc_id = resp.json()["document_id"]
            async with _test_session_factory() as db:
                d = (await db.execute(select(MedicalDocument).where(MedicalDocument.id == doc_id))).scalars().first()
                if d and os.path.exists(d.file_path):
                    os.remove(d.file_path)


# ── F-08 + clinical safety ────────────────────────────────────────────────

class TestClinicalSafety:
    async def test_ai_cannot_overwrite_signed_summary(self, monkeypatch):
        async with _client() as c:
            await c.post("/api/doctor/encounter/e-sec/summary",
                         json={"doctor_notes": "signed record", "confirm": True}, headers=DOCTOR())

        called = {"llm": False}

        async def _fake_summary(**kwargs):
            called["llm"] = True
            raise AssertionError("must not reach the LLM for a signed record")

        monkeypatch.setattr("backend.app.api.doctor_router.llm_service.generate_clinical_summary", _fake_summary)
        async with _client() as c:
            resp = await c.post("/api/doctor/encounter/e-sec/generate-llm-summary", headers=DOCTOR())
            assert resp.status_code == 409
            assert called["llm"] is False  # guard runs BEFORE any LLM cost

    async def test_red_flag_escalation_is_independent_of_llm(self, monkeypatch):
        """A dismissive / failing LLM can never suppress deterministic escalation."""
        async def _dismissive(self, **kwargs):
            # Misleading model output: downplays a textbook cardiac presentation.
            return json.dumps([
                "You are completely fine, this is not an emergency, go home and rest.",
                "Take paracetamol twice daily and avoid hospitals.",
            ])

        monkeypatch.setattr("backend.app.services.followup_service.LocalLLMClient.chat", _dismissive)

        async with _client() as c:
            init = await c.post("/api/intake/init", json={
                "phone": "9000000077", "name": "Synthetic Angina Patient",
                "age": 60, "gender": "MALE", "preferred_language": "en",
            })
            assert init.status_code == 200
            sid = init.json()["session_id"]

            a1 = await c.post("/api/intake/answer", json={
                "session_id": sid, "section_id": "SITE",
                "question_text": "Where is the pain?", "answer_text": "Pain at center of chest",
                "input_method": "touch"})
            assert a1.status_code == 200
            a2 = await c.post("/api/intake/answer", json={
                "session_id": sid, "section_id": "RADIATION",
                "question_text": "Does it spread?", "answer_text": "Spreads to left arm",
                "input_method": "touch"})
            body = a2.json()
            assert body["red_flag_triggered"] is True  # deterministic, LLM never consulted here

            fu = await c.post("/api/intake/followup-questions", json={
                "session_id": sid, "language": "en", "max_questions": 2,
                "answers": [
                    {"section_id": "SITE", "answer_text": "Pain at center of chest"},
                    {"section_id": "RADIATION", "answer_text": "Spreads to left arm"},
                ],
            })
            assert fu.status_code == 200
            fdata = fu.json()
            assert fdata["escalation_required"] is True and len(fdata["red_flags"]) >= 1
            # Dismissive/diagnostic LLM lines were rejected by validation —
            # the patient never sees "you are completely fine".
            for q in fdata["questions"]:
                text = q.get("text") or q.get("question_text") or str(q)
                assert "completely fine" not in text.lower()
                assert "paracetamol" not in text.lower()

        async with _test_session_factory() as db:
            enc = (await db.execute(
                select(Encounter).where(Encounter.patient_id == "p-sec"))).scalars().first()
            # A synthetic alert row exists and the NEW cardiac encounter escalated:
            alerts = (await db.execute(select(RedFlagAlert))).scalars().all()
            assert len(alerts) >= 2
            new_pat = (await db.execute(select(Patient).where(Patient.phone == "9000000077"))).scalars().first()
            new_enc = (await db.execute(
                select(Encounter).where(Encounter.patient_id == new_pat.id))).scalars().first()
            assert new_enc.priority == "EMERGENCY"

    async def test_llm_total_failure_still_escalates(self, monkeypatch):
        async def _boom(self, **kwargs):
            raise RuntimeError("model unavailable")
        monkeypatch.setattr("backend.app.services.followup_service.LocalLLMClient.chat", _boom)
        async with _client() as c:
            fu = await c.post("/api/intake/followup-questions", json={
                "language": "en", "max_questions": 2,
                "answers": [
                    {"section_id": "SITE", "answer_text": "Pain at center of chest"},
                    {"section_id": "RADIATION", "answer_text": "Pain radiates to left arm and jaw"},
                ],
            })
            assert fu.status_code == 200
            assert fu.json()["escalation_required"] is True
            assert fu.json()["source"] == "rule_fallback"

    async def test_f07_no_patient_names_logged(self):
        src = open(os.path.join(os.path.dirname(document_router.__file__), "doctor_router.py"),
                   encoding="utf-8").read()
        assert "for Patient: {patient.name}" not in src
        assert not any("patient.name" in line for line in src.splitlines() if "print(" in line)


# ── F-06: FHIR R4 & ABDM honesty ──────────────────────────────────────────

class TestFhirAndAbdm:
    async def test_bundle_export_guarded(self):
        async with _client() as c:
            assert (await c.get("/api/fhir/encounter/e-sec")).status_code == 401
            assert (await c.get("/api/fhir/encounter/e-sec", headers=DOCTOR())).status_code == 200

    async def test_bundle_contains_consent_and_honest_content(self):
        # Sign a summary with HTML-dangerous complaint to prove escaping.
        async with _test_session_factory() as db:
            db.add(ClinicalSummary(encounter_id="e-sec", patient_id="p-sec",
                                   chief_complaint="<script>evil</script> chest pain",
                                   hpi="Crushing pain <b>2 days</b>",
                                   is_confirmed_by_doctor=True))
            await db.commit()
        async with _client() as c:
            resp = await c.get("/api/fhir/encounter/e-sec", headers=DOCTOR())
            assert resp.status_code == 200
            bundle = resp.json()
            types = [e["resource"]["resourceType"] for e in bundle["entry"]]
            assert "Consent" in types  # DPDP consent artifact travels with the record
            consent = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Consent")
            assert consent["status"] == "active"
            assert consent["patient"]["reference"] == "Patient/p-sec"

            docref = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "DocumentReference")
            url = docref["content"][0]["attachment"]["url"]
            assert url == "api/documents/file/d-sec"       # opaque + guarded
            assert "secret" not in url and ":\\" not in url  # no server paths leaked

            comp = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Composition")
            div = comp["section"][0]["text"]["div"]
            assert "<script>" not in div and "&lt;script&gt;" in div

            obs = next(e["resource"] for e in bundle["entry"]
                       if e["resource"]["resourceType"] == "Observation" and e["resource"]["id"] == "o-sec")
            # Non-numeric lab text must NOT be invented as a fake 0.0 number.
            assert "valueQuantity" not in obs and obs["valueString"] == "Trace growth"

        async with _test_session_factory() as db:
            evt = (await db.execute(
                select(IntegrationEvent).where(IntegrationEvent.event_type == "FHIR_BUNDLE_EXPORT"))).scalars().first()
            assert evt is not None and evt.status == "SUCCESS"  # export is audited

    async def test_unconfirmed_composition_is_preliminary(self):
        async with _client() as c:
            bundle = (await c.get("/api/fhir/encounter/e-sec", headers=DOCTOR())).json()
            comp = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Composition")
            assert comp["status"] == "preliminary"  # unverified until physician signs off

    async def test_abdm_push_is_honestly_simulated_and_guarded(self):
        async with _client() as c:
            assert (await c.post("/api/fhir/abdm/push/e-sec")).status_code == 401
            assert (await c.post("/api/fhir/abdm/push/e-sec", headers=PATIENT())).status_code == 403
            resp = await c.post("/api/fhir/abdm/push/e-sec", headers=DOCTOR())
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "SIMULATED_NOT_TRANSMITTED"
            assert "compliance" not in body  # no false certification claims
            assert "SIMULATION" in body["integration_mode"]
            assert "no live" in body["gateway_note"].lower()
        async with _test_session_factory() as db:
            evt = (await db.execute(
                select(IntegrationEvent).where(IntegrationEvent.event_type == "ABDM_HIP_PUSH"))).scalars().first()
            assert evt is not None and "MOCK" in evt.payload["mode"]
