"""
QA-07 follow-up: OPD token allocation must stay unique under concurrency.

The previous implementation ("highest issued + 1") is correct only when two
check-ins never overlap. These tests cover:

1. the allocation still continues the existing sequence one at a time,
2. many simultaneous check-ins all receive distinct tokens,
3. the DATABASE rejects a duplicate token even if application logic regresses.

These run on the hermetic in-memory SQLite database used by the rest of the
suite (see test_release_audit.py). True multi-connection concurrency is proven
separately against the live PostgreSQL instance — see
scratch/qa_token_concurrency.py, which fires parallel HTTP requests.
"""
import asyncio

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import Encounter, Patient

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
)
_test_session_factory = async_sessionmaker(
    bind=_test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def setup_test_database():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def _check_in_payload(index: int) -> dict:
    """Distinct phone per patient so the "existing patient" branch is not hit."""
    return {
        "name": f"Concurrency Patient {index}",
        "age": 30,
        "gender": "MALE",
        "phone": f"98000{index:05d}",
    }


async def _tokens_from(calls) -> list:
    responses = await asyncio.gather(*calls)
    tokens = []
    for response in responses:
        assert response.status_code == 200, response.text
        tokens.append(response.json()["token_number"])
    return tokens


@pytest.mark.asyncio
async def test_allocation_continues_the_existing_sequence():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/intake/init", json=_check_in_payload(1))
        second = await client.post("/api/intake/init", json=_check_in_payload(2))

    assert first.json()["token_number"] == "OPD-101"
    assert second.json()["token_number"] == "OPD-102"


@pytest.mark.asyncio
async def test_simultaneous_check_ins_receive_unique_tokens():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens = await _tokens_from(
            [client.post("/api/intake/init", json=_check_in_payload(i)) for i in range(8)]
        )

    assert len(tokens) == 8
    assert len(set(tokens)) == 8, f"duplicate tokens issued: {sorted(tokens)}"


@pytest.mark.asyncio
async def test_database_rejects_a_duplicate_token_number():
    """The UNIQUE index is the backstop if allocation logic ever regresses."""
    async with _test_session_factory() as db:
        patient = Patient(
            name="Duplicate Token Patient", age=44, gender="FEMALE", mrn="MRN-DUP-1"
        )
        db.add(patient)
        await db.flush()

        db.add(
            Encounter(
                patient_id=patient.id,
                department="General Medicine",
                token_number="OPD-777",
                status="QUEUED",
            )
        )
        await db.commit()

        db.add(
            Encounter(
                patient_id=patient.id,
                department="General Medicine",
                token_number="OPD-777",
                status="QUEUED",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
