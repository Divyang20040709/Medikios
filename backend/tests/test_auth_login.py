"""
Auth login hardening tests (Doctor/Admin login-failure investigation).

Covers:
  * successful Doctor/Admin sign-in and access to their guarded data endpoints,
  * invalid credentials / unknown users / missing fields -> 4xx JSON (never 500),
  * malformed (non-JSON) request bodies -> 422 JSON,
  * cross-role credential use stays rejected (backend never trusts the
    client-selected role),
  * wrong-role access to ADMIN-only endpoints stays 403,
  * unexpected server/DB failures still answer with a JSON 500 body (the
    global exception handler in backend.app.main) instead of Starlette's
    plain-text "Internal Server Error" that broke the frontend's JSON parse.

Isolated in-memory SQLite via dependency override — never touches the
live medikiosk_db.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.api.auth_router import get_password_hash
from backend.app.database.session import Base, get_db
from backend.app.models.entities import User

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
async def setup_test_database():
    # aiosqlite shares one connection, so :memory: tables survive between
    # tests — drop and recreate every time to keep tests independent.
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db

    # Staff accounts hashed exactly like production sign-in (bcrypt).
    async with _test_session_factory() as db:
        db.add_all(
            [
                User(
                    email="doctor@hospital.in",
                    phone="9876543210",
                    full_name="Dr. Test Sengupta",
                    role="DOCTOR",
                    password_hash=get_password_hash("doctor123"),
                    department="General Medicine",
                ),
                User(
                    email="admin@hospital.in",
                    phone="9876543211",
                    full_name="Test Hospital Admin",
                    role="ADMIN",
                    password_hash=get_password_hash("admin123"),
                    department="Hospital Administration",
                ),
            ]
        )
        await db.commit()

    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, identifier: str, password, role: str):
    body = {"identifier": identifier, "role": role}
    if password is not None:
        body["password"] = password
    return await client.post("/api/auth/login", json=body)


# ── 1. Successful staff logins + portal access ────────────────────────

@pytest.mark.asyncio
async def test_doctor_login_success_and_protected_queue_access():
    async with _client() as client:
        resp = await _login(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "DOCTOR"
        assert len(data["access_token"]) > 20
        # The issued token actually unlocks the DOCTOR data surface.
        queue = await client.get(
            "/api/doctor/queue",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert queue.status_code == 200


@pytest.mark.asyncio
async def test_admin_login_success_and_admin_endpoint_access():
    async with _client() as client:
        resp = await _login(client, "admin@hospital.in", "admin123", "ADMIN")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "ADMIN"
        staff = await client.get(
            "/api/admin/staff",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert staff.status_code == 200


# ── 2. Credential failures are 4xx JSON errors, never 500 ─────────────

@pytest.mark.asyncio
async def test_wrong_password_returns_401_json_detail():
    async with _client() as client:
        resp = await _login(client, "doctor@hospital.in", "totally-wrong", "DOCTOR")
        assert resp.status_code == 401
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json()["detail"]


@pytest.mark.asyncio
async def test_unknown_staff_identifier_returns_401_json():
    async with _client() as client:
        resp = await _login(client, "ghost@nowhere.invalid", "whatever", "DOCTOR")
        assert resp.status_code == 401
        assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_staff_login_without_password_is_rejected():
    async with _client() as client:
        resp = await _login(client, "admin@hospital.in", None, "ADMIN")
        assert resp.status_code == 401
        assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_cross_role_credentials_are_rejected():
    # Admin credentials must not mint a DOCTOR token (role comes from the DB).
    async with _client() as client:
        resp = await _login(client, "admin@hospital.in", "admin123", "DOCTOR")
        assert resp.status_code == 401


# ── 3. Malformed request bodies ────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_identifier_returns_422_json():
    # 'identifier' is a required LoginRequest field -> validation error JSON.
    async with _client() as client:
        resp = await client.post(
            "/api/auth/login", json={"password": "x", "role": "DOCTOR"}
        )
        assert resp.status_code == 422
        assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_missing_role_defaults_to_patient_and_cannot_hijack_staff_account():
    # LoginRequest.role defaults to PATIENT; a staff email on that path must
    # be rejected (401), never auto-attached to a patient identity.
    async with _client() as client:
        resp = await client.post(
            "/api/auth/login", json={"identifier": "doctor@hospital.in", "password": "doctor123"}
        )
        assert resp.status_code == 401
        assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_non_json_body_returns_4xx_not_500():
    async with _client() as client:
        resp = await client.post(
            "/api/auth/login",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        # FastAPI surfaces body parse failures as RequestValidationError (422
        # on this stack, 400 on others) — the contract is 4xx + JSON, not 500.
        assert 400 <= resp.status_code < 500
        assert resp.headers["content-type"].startswith("application/json")


# ── 4. Wrong-role authorization stays forbidden ────────────────────────

@pytest.mark.asyncio
async def test_doctor_token_forbidden_on_admin_only_endpoint():
    async with _client() as client:
        login = await _login(client, "doctor@hospital.in", "doctor123", "DOCTOR")
        token = login.json()["access_token"]
        resp = await client.get(
            "/api/admin/staff", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_anonymous_denied_on_admin_only_endpoint():
    async with _client() as client:
        resp = await client.get("/api/admin/staff")
        assert resp.status_code == 401


# ── 5. Unexpected failures still answer JSON (no plain-text 500) ───────

@pytest.mark.asyncio
async def test_database_crash_answers_json_500():
    """A DB outage inside the login flow must surface as a JSON 500 body via
    the global exception handler — never Starlette's plain-text
    'Internal Server Error' that crashed the frontend's res.json()."""
    from starlette.testclient import TestClient

    async def broken_db():
        raise RuntimeError("simulated database outage")

    app.dependency_overrides[get_db] = broken_db
    try:
        # raise_server_exceptions=False mirrors a real ASGI server: the
        # handler's response is what the client receives. (No `with` block —
        # that would run the lifespan against the real database.)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/auth/login",
            json={"identifier": "doctor@hospital.in", "password": "doctor123", "role": "DOCTOR"},
        )
        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert "detail" in body
        # No stack trace / internal exception text leaks to the client.
        text = resp.text.lower()
        assert "traceback" not in text and "runtimeerror" not in text
    finally:
        app.dependency_overrides[get_db] = override_get_db
