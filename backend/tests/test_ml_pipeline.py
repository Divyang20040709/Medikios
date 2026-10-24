import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import User
from backend.app.api.auth_router import create_access_token
from backend.app.clinical.intake_time_model import IntakeTimeModel
from backend.app.clinical.red_flags import RedFlagEngine

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "model")

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def admin_token():
    """Isolated in-memory SQLite (never the real dev DB) with one ADMIN row.
    aiosqlite shares a single :memory: connection across tests, so the schema
    is dropped and recreated each time to stay independent."""
    engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_maker() as db:
        admin = User(full_name="ML Admin", role="ADMIN", email="ml.admin@itest.local")
        doctor = User(full_name="ML Doctor", role="DOCTOR", email="ml.doctor@itest.local")
        db.add_all([admin, doctor])
        await db.commit()
        admin_tok = create_access_token(data={"sub": admin.id, "role": "ADMIN"})
        doctor_tok = create_access_token(data={"sub": doctor.id, "role": "DOCTOR"})

    yield {"ADMIN": admin_tok, "DOCTOR": doctor_tok}

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_ml_artifacts_exist():
    assert os.path.exists(os.path.join(MODEL_DIR, "intake_duration_regressor.joblib"))
    assert os.path.exists(os.path.join(MODEL_DIR, "clinical_triage_classifier.joblib"))
    assert os.path.exists(os.path.join(MODEL_DIR, "indic_clinical_lexicon.json"))
    assert os.path.exists(os.path.join(MODEL_DIR, "intake_duration_evaluation.json"))
    assert os.path.exists(os.path.join(MODEL_DIR, "clinical_triage_evaluation.json"))

@pytest.mark.asyncio
async def test_intake_duration_ml_prediction():
    # Predict for standard adult patient
    pred = IntakeTimeModel.predict_intake_duration(
        age=45,
        department="General Medicine",
        has_voice=True,
        document_count=1,
        symptom_count=2,
        priority="ROUTINE"
    )
    assert isinstance(pred, float)
    assert 1.5 <= pred <= 15.0

    # Detailed prediction with explainable clinical factors
    detail = IntakeTimeModel.predict_intake_duration_detailed(
        age=72,
        department="Cardiology / Acute Medicine",
        has_voice=False,
        document_count=2,
        symptom_count=3,
        priority="EMERGENCY"
    )
    assert detail["predicted_minutes"] <= 4.0
    assert "factors" in detail
    assert "time_saved_vs_manual_baseline_minutes" in detail
    assert detail["time_saved_vs_manual_baseline_minutes"] > 10.0

@pytest.mark.asyncio
async def test_clinical_triage_classifier():
    # 1. Emergency chest pain
    res_cardio = RedFlagEngine.classify_complaint_ml(
        "Severe crushing central chest pain radiating to left arm with cold sweating"
    )
    assert res_cardio["priority"] == "EMERGENCY"
    assert "Cardiology" in res_cardio["department"]
    assert res_cardio["is_red_flag"] is True

    # 2. Pediatric asthma complaint
    res_peds = RedFlagEngine.classify_complaint_ml(
        "4-year-old child coughing persistantly for three weeks with asthma attack"
    )
    assert res_peds["priority"] in ("URGENT", "EMERGENCY")

    # 3. Gujarati complaint grounding
    res_gu = RedFlagEngine.classify_complaint_ml(
        "છેલ્લા બે દિવસથી છાતીમાં ભારે દુખાવો અને શ્વાસ લેવામાં તકલીફ છે"
    )
    assert res_gu["priority"] in ("EMERGENCY", "URGENT")
    assert len(res_gu["matched_concepts"]) > 0

@pytest.mark.asyncio
async def test_api_models_status_endpoint(admin_token):
    """RBAC tightening: /api/admin/models/status is ADMIN-only — anonymous
    access is 401 and a DOCTOR token is 403; ADMIN sees the model registry."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/api/admin/models/status")).status_code == 401
        denied = await ac.get("/api/admin/models/status", headers={
            "Authorization": f"Bearer {admin_token['DOCTOR']}"})
        assert denied.status_code == 403

        resp = await ac.get("/api/admin/models/status", headers={
            "Authorization": f"Bearer {admin_token['ADMIN']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "OPERATIONAL"
        assert "models" in data
        assert data["models"]["intake_duration_regressor"]["status"] == "ACTIVE_VERIFIED"
        assert data["models"]["clinical_triage_classifier"]["status"] == "ACTIVE_VERIFIED"
        assert data["models"]["indic_speech_normalizer"]["status"] == "ACTIVE_VERIFIED"

@pytest.mark.asyncio
async def test_api_triage_test_endpoint(admin_token):
    """RBAC tightening: /api/admin/models/triage-test is ADMIN-only."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.post("/api/admin/models/triage-test", json={
            "complaint_text": "chest pain"})).status_code == 401

        resp = await ac.post("/api/admin/models/triage-test", json={
            "complaint_text": "सीने में दो दिन से भारी दर्द महसूस हो रहा है और सांस फूल रही है"
        }, headers={"Authorization": f"Bearer {admin_token['ADMIN']}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "triage" in data
        assert "duration_prediction" in data
        assert data["triage"]["priority"] in ("EMERGENCY", "URGENT")

@pytest.mark.asyncio
async def test_api_intake_classify_complaint_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/intake/classify-complaint", json={
            "text": "Frequent urination, extreme thirst, fasting glucose 260 mg/dL"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "department" in data
        assert "priority" in data
