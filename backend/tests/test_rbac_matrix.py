"""
Strict role-based access control matrix (task A/D).

Permission rules under test (enforced server-side from the DATABASE role):
  ADMIN   — Admin pages/APIs + Doctor/Physician OPD reads + patient kiosk.
  DOCTOR  — Doctor/Physician OPD + permitted patient workflows; NEVER Admin.
  PATIENT — patient kiosk/intake only; NEVER Doctor or Admin.
  anon    — public landing + shared-kiosk intake surface only.

Expectations from the task:
  1-4  denied access to Admin URLs/APIs (anon, patient, doctor incl. staff
       management + audit logs),
  5    Doctor -> Doctor queue allowed,
  6    Admin -> Admin, Doctor and patient routes allowed,
  10   client-side role tampering grants nothing (token role claim ignored,
       DB role wins),
  11   expired/garbage tokens are 401.

Runs on isolated in-memory SQLite — never touches the live medikiosk_db.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.api.auth_router import get_password_hash, create_access_token
from backend.app.database.session import Base, get_db
from backend.app.main import app
from backend.app.models.entities import User

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
)
_test_session_factory = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession, expire_on_commit=False
)

ADMIN_ONLY_ENDPOINTS = [
    ("get", "/api/admin/telemetry"),
    ("get", "/api/admin/opd-queue"),
    ("get", "/api/admin/red-flags"),
    ("get", "/api/admin/audit-logs?limit=5"),
    ("get", "/api/admin/staff"),
    ("get", "/api/admin/intake-time-model"),
    ("get", "/api/admin/models/status"),
    ("post", "/api/admin/red-flags/00000000-0000-0000-0000-000000000000/acknowledge"),
    ("post", "/api/admin/intake-time-model/predict"),
    ("post", "/api/admin/models/triage-test"),
]


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db
    async with _test_session_factory() as db:
        db.add_all(
            [
                User(
                    email="doctor@hospital.in", phone="9876543210",
                    full_name="Dr. RBAC Test", role="DOCTOR",
                    password_hash=get_password_hash("doctor123"),
                ),
                User(
                    email="admin@hospital.in", phone="9876543211",
                    full_name="RBAC Test Admin", role="ADMIN",
                    password_hash=get_password_hash("admin123"),
                ),
                User(
                    phone="9998887776", full_name="RBAC Test Patient",
                    role="PATIENT", password_hash=get_password_hash("patient123"),
                ),
            ]
        )
        await db.commit()
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _auth(client: AsyncClient, identifier: str, password: str, role: str) -> dict:
    resp = await client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": password, "role": role},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _hit(client: AsyncClient, method: str, path: str, headers: dict):
    if method == "get":
        return await client.get(path, headers=headers)
    return await client.post(path, headers=headers, json={})


# ── D1/D3: anonymous + patient denied on every Admin API ───────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADMIN_ONLY_ENDPOINTS)
async def test_anonymous_denied_on_all_admin_apis(method, path):
    async with _client() as client:
        resp = await _hit(client, method, path, {})
        assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADMIN_ONLY_ENDPOINTS)
async def test_patient_denied_on_all_admin_apis(method, path):
    async with _client() as client:
        headers = await _auth(client, "9998887776", "patient123", "PATIENT")
        resp = await _hit(client, method, path, headers)
        assert resp.status_code == 403, f"{method.upper()} {path} -> {resp.status_code}"


# ── D4: doctor denied on ALL Admin APIs, incl. staff mgmt & audit logs ──

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ADMIN_ONLY_ENDPOINTS)
async def test_doctor_denied_on_all_admin_apis(method, path):
    async with _client() as client:
        headers = await _auth(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        resp = await _hit(client, method, path, headers)
        assert resp.status_code == 403, f"{method.upper()} {path} -> {resp.status_code}"


# ── D2: patient denied on Doctor APIs ───────────────────────────────────

@pytest.mark.asyncio
async def test_patient_denied_on_doctor_queue():
    async with _client() as client:
        headers = await _auth(client, "9998887776", "patient123", "PATIENT")
        resp = await client.get("/api/doctor/queue", headers=headers)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_denied_on_doctor_queue():
    async with _client() as client:
        resp = await client.get("/api/doctor/queue")
        assert resp.status_code == 401


# ── D5/D6: allowed access matrix ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_doctor_allowed_on_doctor_queue():
    async with _client() as client:
        headers = await _auth(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        resp = await client.get("/api/doctor/queue", headers=headers)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_allowed_on_doctor_queue():
    # Rule A: ADMIN can access Doctor/Physician OPD features.
    async with _client() as client:
        headers = await _auth(client, "admin@hospital.in", "admin123", "ADMIN")
        resp = await client.get("/api/doctor/queue", headers=headers)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_allowed_on_admin_staff_and_audit():
    async with _client() as client:
        headers = await _auth(client, "admin@hospital.in", "admin123", "ADMIN")
        for path in ("/api/admin/staff", "/api/admin/audit-logs?limit=5",
                     "/api/admin/telemetry", "/api/admin/models/status"):
            resp = await client.get(path, headers=headers)
            assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_clinical_signoff_stays_doctor_only_for_admin():
    # Documented carve-out: signing/editing the clinical RECORD remains
    # DOCTOR-only (medical-signature rule); ADMIN gets OPD visibility.
    # Doctor passes auth and reaches lookup (404), ADMIN is refused (403).
    async with _client() as client:
        doc_h = await _auth(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        adm_h = await _auth(client, "admin@hospital.in", "admin123", "ADMIN")
        url = "/api/doctor/summary/does-not-exist"
        assert (await client.put(url, headers=doc_h, json={})).status_code == 404
        assert (await client.put(url, headers=adm_h, json={})).status_code == 403


# ── Kiosk surface stays available to patient/anonymous (rule A) ─────────

@pytest.mark.asyncio
async def test_anonymous_can_use_public_kiosk_intake_surface():
    async with _client() as client:
        assert (await client.get("/api/intake/languages")).status_code == 200


# ── D10: token role-claim tampering grants nothing (DB role wins) ───────

@pytest.mark.asyncio
async def test_forged_admin_role_claim_on_patient_token_is_ignored():
    async with _client() as client:
        # Patient account + patient token first (proves real role).
        headers = await _auth(client, "9998887776", "patient123", "PATIENT")
        assert (await client.get("/api/admin/staff", headers=headers)).status_code == 403

        # Same subject, role claim tampered to ADMIN — server must consult
        # the database row, not the claim.
        me = await client.get("/api/auth/me", headers=headers)
        forged = create_access_token(
            data={"sub": me.json()["id"], "role": "ADMIN", "name": "Mallory"}
        )
        tampered = {"Authorization": f"Bearer {forged}"}
        assert (await client.get("/api/auth/me", headers=tampered)).json()["role"] == "PATIENT"
        assert (await client.get("/api/admin/staff", headers=tampered)).status_code == 403


# ── D11: expired / invalid tokens handled as 401 ────────────────────────

@pytest.mark.asyncio
async def test_expired_token_rejected_with_401():
    async with _client() as client:
        headers = await _auth(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        me = await client.get("/api/auth/me", headers=headers)
        expired = create_access_token(
            data={"sub": me.json()["id"], "role": "DOCTOR", "name": "x"},
            expires_delta=timedelta(minutes=-5),
        )
        resp = await client.get(
            "/api/doctor/queue", headers={"Authorization": f"Bearer {expired}"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_garbage_token_rejected_with_401():
    async with _client() as client:
        resp = await client.get(
            "/api/doctor/queue", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert resp.status_code == 401
