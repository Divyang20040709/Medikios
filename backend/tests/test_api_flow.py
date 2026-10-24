import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.scripts.seed import seed_data

# Dedicated test SQLite engine
_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)

async def override_get_db():
    async with _test_session_factory() as session:
        yield session

@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Seed test database if not seeded
    import hashlib
    from sqlalchemy.future import select
    from backend.app.models.entities import User, Patient, Encounter
    async with _test_session_factory() as db:
        res = await db.execute(select(User).where(User.email == "doctor@hospital.in"))
        if not res.scalars().first():
            doc = User(
                email="doctor@hospital.in",
                phone="9876543210",
                full_name="Dr. Test",
                role="DOCTOR",
                password_hash=hashlib.sha256("doctor123".encode()).hexdigest(),
                department="General Medicine"
            )
            p = Patient(name="Emergency Patient", age=50, gender="MALE", phone="9999999999", mrn="MRN-TEST-1")
            db.add_all([doc, p])
            await db.flush()
            
            enc = Encounter(patient_id=p.id, token_number="T-001", priority="EMERGENCY", status="WAITING")
            db.add(enc)
            await db.commit()

    yield
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"

@pytest.mark.asyncio
async def test_doctor_login_and_queue():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post("/api/auth/login", json={
            "identifier": "doctor@hospital.in",
            "password": "doctor123",
            "role": "DOCTOR"
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert "access_token" in data
        assert data["role"] == "DOCTOR"

        # Phase 6: queue is PHI — requires the doctor's bearer token.
        queue_resp = await client.get("/api/doctor/queue", headers={"Authorization": f"Bearer {data['access_token']}"})
        assert queue_resp.status_code == 200
        queue = queue_resp.json()
        assert len(queue) >= 1
        assert queue[0]["priority"] == "EMERGENCY"

@pytest.mark.asyncio
async def test_patient_intake_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        init_resp = await client.post("/api/intake/initialize", json={
            "phone": "9876543299",
            "name": "Test Intake Patient",
            "age": 35,
            "gender": "FEMALE",
            "preferred_language": "hi",
            "consent_teleconsult": True,
            "consent_data_sharing": True
        })
        assert init_resp.status_code == 200
        init_data = init_resp.json()
        session_id = init_data["session_id"]
        assert "token_number" in init_data

        q_resp = await client.get("/api/intake/questions/CHEST_PAIN?language=en")
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        assert len(q_data["questions"]) > 0

        ans_resp = await client.post("/api/intake/answer", json={
            "session_id": session_id,
            "section_id": "SITE",
            "question_text": "Where is the pain located?",
            "answer_text": "Retrosternal central pressure",
            "input_method": "touch"
        })
        assert ans_resp.status_code == 200
        ans_data = ans_resp.json()
        assert ans_data["status"] == "SAVED"
