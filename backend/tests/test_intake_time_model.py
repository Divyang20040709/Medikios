import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import Encounter, Patient, User
from backend.app.api.auth_router import create_access_token
from backend.app.clinical.intake_time_model import IntakeTimeModel


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield async_session

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_intake_time_model_empty_baseline(test_db):
    """Test model returns expected baseline prior when database has zero encounters."""
    async with test_db() as db:
        stats = await IntakeTimeModel.compute_stats_from_db(db, period="all")
        assert stats["sample_size"] == 0
        assert stats["average_minutes"] == IntakeTimeModel.PRIOR_AVERAGE_MINUTES
        assert stats["calculation_method"] == "predictive_prior_baseline"
        assert "department_averages" in stats
        assert "modality_breakdown" in stats


@pytest.mark.asyncio
async def test_intake_time_model_with_completed_encounters(test_db):
    """Test model computes accurate durations when encounters are completed in DB."""
    async with test_db() as db:
        pat = Patient(name="Test Patient", age=40, gender="MALE", mrn="MRN-TEST-1")
        db.add(pat)
        await db.commit()
        await db.refresh(pat)

        now = datetime.utcnow()
        # Create encounters with 4 min and 6 min intake duration
        enc1 = Encounter(
            patient_id=pat.id,
            department="General Medicine",
            token_number="T-01",
            status="INTAKE_COMPLETED",
            created_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=6)
        )
        enc2 = Encounter(
            patient_id=pat.id,
            department="Cardiology / Acute Medicine",
            token_number="T-02",
            status="INTAKE_COMPLETED",
            created_at=now - timedelta(minutes=20),
            completed_at=now - timedelta(minutes=14)
        )
        db.add_all([enc1, enc2])
        await db.commit()

        stats = await IntakeTimeModel.compute_stats_from_db(db, period="all")
        assert stats["sample_size"] == 2
        assert stats["calculation_method"] == "empirical_db_bayesian_smoothed"
        assert stats["average_minutes"] > 0
        assert stats["time_saved_vs_manual_triage_minutes"] > 0


@pytest.mark.asyncio
async def test_intake_time_model_prediction():
    """Test multi-factor prediction logic."""
    predicted_routine = IntakeTimeModel.predict_intake_duration(
        age=30, department="General Medicine", has_voice=False, priority="ROUTINE"
    )
    predicted_voice = IntakeTimeModel.predict_intake_duration(
        age=30, department="General Medicine", has_voice=True, priority="ROUTINE"
    )
    predicted_emergency = IntakeTimeModel.predict_intake_duration(
        age=30, department="General Medicine", has_voice=False, priority="EMERGENCY"
    )
    predicted_ayush = IntakeTimeModel.predict_intake_duration(
        age=30, department="AYUSH / Kayachikitsa OPD", consultation_type="ayush"
    )

    # Voice input should be faster than touch
    assert predicted_voice < predicted_routine
    # Emergency should be fast-tracked
    assert predicted_emergency <= 2.5
    # AYUSH includes Ashtavidha Pariksha, so it takes longer
    assert predicted_ayush > predicted_routine


@pytest.mark.asyncio
async def test_admin_telemetry_endpoint(test_db):
    """Test /api/admin/telemetry returns database metrics and model calculations.
    Phase 6: the endpoint requires an authenticated ADMIN/DOCTOR bearer token."""
    async with test_db() as db:
        admin = User(full_name="Telemetry Admin", role="ADMIN", email="telemetry.admin@itest.local")
        db.add(admin)
        await db.commit()
        token = create_access_token(data={"sub": admin.id, "role": "ADMIN"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Anonymous access is now refused (was an audit finding).
        assert (await client.get("/api/admin/telemetry")).status_code == 401
        res = await client.get("/api/admin/telemetry", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert "metrics" in data
        assert "total_registrations" in data["metrics"]
        assert "completed_intakes" in data["metrics"]
        assert "active_red_flags" in data["metrics"]
        assert "intake_time_model" in data
        assert "average_minutes" in data["intake_time_model"]


@pytest.mark.asyncio
async def test_admin_predict_endpoint(test_db):
    """Test /api/admin/intake-time-model/predict endpoint.
    RBAC tightening: the endpoint is ADMIN-only — anonymous access is 401,
    a valid ADMIN bearer token is required for the 200 predictions."""
    async with test_db() as db:
        admin = User(full_name="Predict Admin", role="ADMIN", email="predict.admin@itest.local")
        db.add(admin)
        await db.commit()
        token = create_access_token(data={"sub": admin.id, "role": "ADMIN"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        anon = await client.post("/api/admin/intake-time-model/predict", json={
            "age": 45, "priority": "ROUTINE"})
        assert anon.status_code == 401

        res = await client.post("/api/admin/intake-time-model/predict", json={
            "age": 45,
            "department": "Cardiology / Acute Medicine",
            "consultation_type": "modern",
            "has_voice": True,
            "document_count": 2,
            "symptom_count": 2,
            "priority": "URGENT"
        }, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert "predicted_minutes" in data
        assert data["predicted_minutes"] > 0
