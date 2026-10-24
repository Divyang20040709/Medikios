"""
QA-11 regression: the admin dashboard counters must actually honour the
selected period.

Before the fix only the intake-duration model reacted to `period`; the four
metric cards silently returned all-time totals for "Today" and "Week".
These tests pin the window boundaries and prove the counters move.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import Encounter, Patient, User
from backend.app.api.auth_router import create_access_token
from backend.app.api.admin_router import _period_start


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


def test_period_start_boundaries():
    """`today` is midnight UTC; `week`/`month` are trailing 7/30 day windows."""
    today = _period_start("today")
    assert today.hour == 0 and today.minute == 0 and today.second == 0
    assert today.microsecond == 0
    assert today <= datetime.utcnow()

    week = _period_start("week")
    assert timedelta(days=6, hours=23) < datetime.utcnow() - week < timedelta(days=7, minutes=1)

    month = _period_start("month")
    assert timedelta(days=29, hours=23) < datetime.utcnow() - month < timedelta(days=30, minutes=1)

    # Unknown / "all" must mean "no lower bound", never a zero window.
    assert _period_start("all") is None
    assert _period_start("nonsense") is None


@pytest.mark.asyncio
async def test_telemetry_counts_are_period_scoped(test_db):
    """
    Counters must differ between periods: one encounter today, one 20 days ago.

    today  -> 1   week (7 d)  -> 1   month (30 d) -> 2   all  -> 2
    """
    async with test_db() as db:
        admin = User(full_name="Period Admin", role="ADMIN", email="period.admin@itest.local")
        db.add(admin)
        await db.commit()

        patient = Patient(name="Period Patient", age=40, gender="MALE", mrn="MRN-PERIOD-1")
        db.add(patient)
        await db.commit()
        await db.refresh(patient)

        now = datetime.utcnow()
        db.add_all([
            Encounter(
                patient_id=patient.id, department="General Medicine",
                token_number="OPD-901", status="FINALIZED", priority="ROUTINE",
                created_at=now, completed_at=now,
            ),
            Encounter(
                patient_id=patient.id, department="General Medicine",
                token_number="OPD-902", status="FINALIZED", priority="ROUTINE",
                created_at=now - timedelta(days=20),
                completed_at=now - timedelta(days=20),
            ),
        ])
        await db.commit()
        admin_id = admin.id

    token = create_access_token(data={"sub": admin_id, "role": "ADMIN"})
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}

        async def count(period: str) -> int:
            res = await client.get(f"/api/admin/telemetry?period={period}", headers=headers)
            assert res.status_code == 200, res.text
            return res.json()["metrics"]["total_registrations"]

        today = await count("today")
        week = await count("week")
        month = await count("month")
        all_time = await count("all")

        # The regression this guards: every period used to return 2.
        assert all_time == 2
        assert today == 1
        assert week == 1
        assert month == 2
        assert today < all_time, "today must not report the all-time total"

        # The payload must state its own scope so the UI can label it.
        res = await client.get("/api/admin/telemetry?period=today", headers=headers)
        body = res.json()
        assert body["scope"] == "period"
        assert body["period"] == "today"
        assert body["period_start"] is not None

        res = await client.get("/api/admin/telemetry?period=all", headers=headers)
        body = res.json()
        assert body["scope"] == "all_time"
        assert body["period_start"] is None
