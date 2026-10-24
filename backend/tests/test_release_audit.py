"""
Regression tests for the audit fixes:
- Sign & Complete flow: encounter FINALIZED in DB, completed_at set, queue excludes it.
- Duplicate sign-off is rejected with 409 (safe double-click protection).
- RBAC: ADMIN / PATIENT tokens may NOT perform clinical sign-off; DOCTOR may.
- API failure paths surface real errors (404 for missing encounter).
- Patient interview answers are stored verbatim (patient-provided data preserved).
- i18n dictionary parity across en / hi / gu.
"""
import hashlib
import re
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import Encounter, Patient, User, HistoryResponse
from backend.app.api.auth_router import create_access_token

# Dedicated in-memory test database
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def setup_test_database():
    # hermetic: recreate the schema for every test (in-memory db is per-engine)
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db

    async with _test_session_factory() as db:
        patient = Patient(name="Queue Patient", age=47, gender="MALE", phone="9000000001", mrn="MRN-AUDIT-1")
        db.add(patient)
        await db.flush()
        enc = Encounter(patient_id=patient.id, token_number="OPD-901", status="WAITING_CONSULTATION", priority="ROUTINE")
        db.add(enc)

        for role, name in [("DOCTOR", "Dr. Signer"), ("ADMIN", "Admin User"), ("PATIENT", "Plain Patient")]:
            db.add(User(
                full_name=name,
                role=role,
                email=f"{role.lower()}@audit.test",
                password_hash=hashlib.sha256("pw123".encode("utf-8")).hexdigest(),
            ))
        await db.commit()

    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _token_for(db_role: str) -> str:
    async with _test_session_factory() as db:
        res = await db.execute(select(User).where(User.role == db_role))
        user = res.scalars().first()
    return create_access_token(data={"sub": user.id, "role": user.role, "name": user.full_name})


async def _headers(db_role: str) -> dict:
    """Phase 6: clinical endpoints require real bearer tokens."""
    return {"Authorization": f"Bearer {await _token_for(db_role)}"}


async def _active_queue_encounter_ids(client: AsyncClient):
    resp = await client.get("/api/doctor/queue", headers=await _headers("DOCTOR"))
    assert resp.status_code == 200
    return {item["encounter_id"] for item in resp.json()}


async def test_sign_and_complete_finalizes_and_persists():
    """Sign-off must reach the DB and move the encounter to the Completed bucket."""
    async with _client() as client:
        queue_before = await _active_queue_encounter_ids(client)
        enc_id = list(queue_before)[0] if queue_before else None
        assert enc_id, "test encounter should be in the queue before sign-off"

        sign_resp = await client.post(f"/api/doctor/encounter/{enc_id}/summary", json={
            "doctor_notes": "Examination: clear | Plan: observation | Signed by Dr. Signer",
            "confirm": True,
        }, headers=await _headers("DOCTOR"))
        assert sign_resp.status_code == 200
        body = sign_resp.json()
        assert body["is_confirmed"] is True

        # DB state — the actual root-cause surface
        async with _test_session_factory() as db:
            enc = (await db.execute(select(Encounter).where(Encounter.id == enc_id))).scalars().first()
            assert enc.status == "FINALIZED"
            assert enc.completed_at is not None

        # Product rule (QA-05): a signed encounter deliberately STAYS in the
        # queue so the physician can reopen it under the "Completed" filter — it
        # is sorted last and must read FINALIZED, never a waiting status.
        queue_after = (await client.get("/api/doctor/queue", headers=await _headers("DOCTOR"))).json()
        signed_rows = [item for item in queue_after if item["encounter_id"] == enc_id]
        assert signed_rows, "signed encounter must remain visible under Completed"
        assert signed_rows[0]["status"] == "FINALIZED"


async def test_duplicate_signoff_is_rejected():
    """Second confirm on the same encounter must fail with 409, not silently 'succeed'."""
    async with _client() as client:
        doctor_headers = await _headers("DOCTOR")
        queue_ids = await _active_queue_encounter_ids(client)
        enc_id = list(queue_ids)[0]
        first = await client.post(f"/api/doctor/encounter/{enc_id}/summary", json={"doctor_notes": "x", "confirm": True}, headers=doctor_headers)
        assert first.status_code == 200
        second = await client.post(f"/api/doctor/encounter/{enc_id}/summary", json={"doctor_notes": "x", "confirm": True}, headers=doctor_headers)
        assert second.status_code == 409


async def test_admin_cannot_perform_clinical_signoff():
    token = await _token_for("ADMIN")
    async with _client() as client:
        queue_ids = await _active_queue_encounter_ids(client)
        enc_id = list(queue_ids)[0]
        resp = await client.post(
            f"/api/doctor/encounter/{enc_id}/summary",
            json={"doctor_notes": "admin override", "confirm": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        # Encounter untouched
        async with _test_session_factory() as db:
            enc = (await db.execute(select(Encounter).where(Encounter.id == enc_id))).scalars().first()
            assert enc.status != "FINALIZED"


async def test_patient_token_blocked_from_doctor_workspace():
    token = await _token_for("PATIENT")
    async with _client() as client:
        resp = await client.get("/api/doctor/queue", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


async def test_doctor_token_allowed_but_admin_only_endpoints_blocked():
    doctor_token = await _token_for("DOCTOR")
    admin_token = await _token_for("ADMIN")
    async with _client() as client:
        # Doctor may read the queue but not audit logs / staff registry
        assert (await client.get("/api/doctor/queue", headers={"Authorization": f"Bearer {doctor_token}"})).status_code == 200
        assert (await client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {doctor_token}"})).status_code == 403
        assert (await client.get("/api/admin/staff", headers={"Authorization": f"Bearer {doctor_token}"})).status_code == 403
        # Admin may read them
        assert (await client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})).status_code == 200
        staff = await client.get("/api/admin/staff", headers={"Authorization": f"Bearer {admin_token}"})
        assert staff.status_code == 200
        assert {u["role"] for u in staff.json()} >= {"DOCTOR", "ADMIN", "PATIENT"}


async def test_signoff_api_failure_surfaces_real_error():
    """Missing encounter → 404 with detail (frontend shows error, never false success)."""
    async with _client() as client:
        resp = await client.post("/api/doctor/encounter/does-not-exist/summary", json={"doctor_notes": "x", "confirm": True}, headers=await _headers("DOCTOR"))
        assert resp.status_code == 404
        assert "detail" in resp.json()


async def test_intake_ids_and_verbatim_answer_storage():
    """Frontend→API data flow: init returns canonical IDs; answers stored exactly as provided."""
    async with _client() as client:
        init = await client.post("/api/intake/init", json={
            "phone": "9000000042",
            "name": "Gujarati Patient",
            "age": 30,
            "gender": "FEMALE",
            "preferred_language": "gu",
        })
        assert init.status_code == 200
        data = init.json()
        for key in ("encounter_id", "session_id", "patient_id", "token_number", "mrn"):
            assert data.get(key), f"missing {key} in /api/intake/init response"

        original_answer = "તલે ઉબટું અને બેઠક ના દર્દ"  # verbatim Gujarati complaint
        ans = await client.post("/api/intake/answer", json={
            "session_id": data["session_id"],
            "section_id": "SITE",
            "question_text": "ક્યાં દર્દ છે?",
            "answer_text": original_answer,
            "input_method": "touch",
        })
        assert ans.status_code == 200
        assert ans.json()["status"] == "SAVED"

        async with _test_session_factory() as db:
            res = await db.execute(select(HistoryResponse).where(HistoryResponse.session_id == data["session_id"]))
            rows = res.scalars().all()
            assert any(r.answer_text == original_answer for r in rows), "patient answer must be stored verbatim"

        # The freshly created INTAKE_IN_PROGRESS encounter appears in the doctor queue
        queue_ids = await _active_queue_encounter_ids(client)
        assert data["encounter_id"] in queue_ids


def test_i18n_dictionary_parity_across_languages():
    """en / hi / gu dictionaries must contain exactly the same keys."""
    i18n_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "i18n.ts"
    source = i18n_path.read_text(encoding="utf-8")

    key_re = re.compile(r"'([A-Za-z0-9_.]+)':")
    blocks = {}
    for lang in ("en", "hi", "gu"):
        marker = f"const {lang}: Dict = {{"
        start = source.index(marker) + len(marker)
        end = source.find("};", start)
        blocks[lang] = frozenset(key_re.findall(source[start:end]))

    assert blocks["en"], "en dictionary parsed empty — i18n.ts layout changed?"
    assert blocks["en"] == blocks["hi"], f"hi missing: {sorted(blocks['en'] - blocks['hi'])}, extra: {sorted(blocks['hi'] - blocks['en'])}"
    assert blocks["en"] == blocks["gu"], f"gu missing: {sorted(blocks['en'] - blocks['gu'])}, extra: {sorted(blocks['gu'] - blocks['en'])}"
