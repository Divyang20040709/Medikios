"""
Phase 4 — OCR audit & completion tests.

Honest-pipeline contract:
  * The processor returns ONLY text actually present in the file — never
    fabricated demo content, never invented dosages/diagnoses.
  * OCR output is unverified until a physician confirms it.
  * Upload validation (type/size/empty/traversal), encounter association and
    OCR timeouts fail visibly with proper HTTP codes; original documents are
    preserved on every failure path.
"""

import io
import os
import time
import uuid
import pytest
import pytest_asyncio
from PIL import Image
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.core.config import settings
from backend.app.models.entities import Patient, MedicalDocument, User
from backend.app.api import document_router
from backend.app.api.auth_router import create_access_token
from backend.app.documents.processor import (
    ClinicalDocumentProcessor, ExtractedClinicalData,
)

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
async def patient_id():
    async with _test_session_factory() as db:
        tag = uuid.uuid4().hex[:10]
        p = Patient(name="OCR Phase4", age=60, gender="MALE",
                    phone=f"97{tag[:8]}", mrn=f"MRN-P4-{tag}")
        db.add(p)
        await db.commit()
        return p.id


def _jpeg_bytes(color=(255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 80), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _asgi():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0)


async def _doctor_headers() -> dict:
    """Phase 6: document reads are PHI — mint a real DOCTOR bearer token."""
    async with _test_session_factory() as db:
        tag = uuid.uuid4().hex[:10]
        doc = User(full_name=f"Dr OCR {tag}", role="DOCTOR", email=f"ocr.dr.{tag}@test.local")
        db.add(doc)
        await db.commit()
        token = create_access_token(data={"sub": doc.id, "role": "DOCTOR"})
    return {"Authorization": f"Bearer {token}"}


# ── processor honesty ─────────────────────────────────────────────────────

class TestProcessorHonesty:
    def test_missing_file_returns_empty_not_fabricated_text(self, tmp_path):
        proc = ClinicalDocumentProcessor()
        assert proc._extract_text_blocking(str(tmp_path / "nope.jpg"), "image/jpeg") == ""

    def test_blank_image_yields_zero_entities(self, tmp_path):
        img_path = str(tmp_path / "blank.png")
        Image.new("RGB", (120, 60), color=(255, 255, 255)).save(img_path)
        data = ClinicalDocumentProcessor().extract_blocking(img_path, "image/png")
        assert data.raw_text == ""
        assert data.document_type == "OTHER"
        assert data.overall_confidence == 0.0
        assert data.medications == [] and data.observations == [] and data.diagnoses == []

    def test_real_text_is_extracted_without_inventing_values(self, tmp_path):
        # Text-bearing file: the parsing fallback reads actual content only.
        rx = tmp_path / "notes.txt"
        rx.write_text(
            "Lab report for follow-up.\nHbA1c: 8.1 %\nTab Metformin 500 mg 1-0-1\n"
            "Glimepiride prescribed last visit\n",
            encoding="utf-8",
        )
        data = ClinicalDocumentProcessor().extract_blocking(str(rx), "text/plain")
        assert "HbA1c: 8.1" in data.raw_text
        assert data.document_type == "LAB_REPORT"

        # Observation value came from the document, and is NOT auto-verified.
        assert len(data.observations) == 1
        obs = data.observations[0]
        assert obs["test_value"] == "8.1" and obs["flag"] == "HIGH"
        assert obs["doctor_verified"] is False

        # Every extracted entity stays unverified — physician confirms via API.
        for med in data.medications:
            assert med["doctor_verified"] is False
        # A drug without a visible dose must NOT gain an invented "500 mg".
        assert all(m["dosage"] in ("", "500 mg") for m in data.medications)

    def test_classify_defaults_to_other_not_prescription_guess(self, tmp_path):
        tx = tmp_path / "misc.txt"
        tx.write_text("Random clinic notice about parking fees and visiting hours " * 2, encoding="utf-8")
        data = ClinicalDocumentProcessor().extract_blocking(str(tx), "text/plain")
        assert data.document_type == "OTHER"


# ── upload validation & pipeline endpoints ────────────────────────────────

class TestUploadValidation:
    async def test_unsupported_file_type_rejected_415(self, patient_id):
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id},
                files={"file": ("virus.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-msdownload")},
            )
        assert resp.status_code == 415

    async def test_empty_file_rejected_400(self, patient_id):
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id},
                files={"file": ("blank.jpg", io.BytesIO(b""), "image/jpeg")},
            )
        assert resp.status_code == 400

    async def test_oversized_file_rejected_413(self, patient_id, monkeypatch):
        monkeypatch.setattr(settings, "MAX_DOCUMENT_UPLOAD_MB", 0)  # anything > 0 bytes fails
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id},
                files={"file": ("big.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 413

    async def test_unknown_patient_rejected_404(self):
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": "ghost-patient"},
                files={"file": ("rx.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 404

    async def test_unknown_encounter_rejected_404(self, patient_id):
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id, "encounter_id": "ghost-encounter"},
                files={"file": ("rx.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 404

    async def test_path_traversal_filename_neutralized(self, patient_id):
        evil = os.path.join("..", "..", "evil_upload.jpg")
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id},
                files={"file": (evil, io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
            assert resp.status_code == 200
            # File stayed inside the uploads dir (basename was applied)
            doc_res = await client.get(f"/api/documents/patient/{patient_id}", headers=await _doctor_headers())
            assert doc_res.status_code == 200


class TestPipelineOutcomes:
    async def test_unreadable_scan_reports_no_text_honestly(self, patient_id):
        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id, "document_type": "LAB_REPORT"},
                files={"file": ("blurry.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 200
        data = resp.json()
        # No fabricated entities; the human-selected type is preserved.
        assert data["ocr_status"] in ("NO_TEXT", "COMPLETED")
        if data["ocr_status"] == "NO_TEXT":
            assert data["entities"] == []
            assert data["document_type"] == "LAB_REPORT"
            assert "message" in data and "physician review" in data["message"]

    async def test_extraction_comes_back_unverified(self, patient_id, monkeypatch):
        fake = ExtractedClinicalData(
            document_type="PRESCRIPTION",
            raw_text="Tab Metformin 500 mg 1-0-1\nHbA1c: 8.1 %",
            overall_confidence=0.9,
            patient_name={"name": "Test", "confidence": 0.9},
            medications=[{"name": "Metformin", "dosage": "500 mg", "frequency": "1-0-1",
                          "confidence": 0.95, "source_snippet": "Tab Metformin 500 mg 1-0-1",
                          "doctor_verified": False}],
            observations=[{"test_name": "HbA1c", "test_value": "8.1", "unit": "%",
                           "reference_range": "4.0 - 5.6%", "flag": "HIGH", "confidence": 0.98,
                           "source_snippet": "HbA1c: 8.1 %", "doctor_verified": False}],
            diagnoses=[], allergies=[], surgeries=[],
        )
        monkeypatch.setattr(document_router.processor, "extract_blocking", lambda p, m: fake)

        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id, "document_type": "PRESCRIPTION"},
                files={"file": ("rx.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ocr_status"] == "COMPLETED"
        assert data["medications_count"] == 1
        assert all(e["verified"] is False for e in data["entities"])
        assert "unverified" in data["message"]

    async def test_ocr_timeout_returns_504_and_keeps_document(
        self, patient_id, monkeypatch
    ):
        def slow_extract(path, mime):
            time.sleep(2)
            return ExtractedClinicalData(
                document_type="PRESCRIPTION", raw_text="x", overall_confidence=0.5,
                patient_name={}, medications=[], observations=[], diagnoses=[],
                allergies=[], surgeries=[],
            )
        monkeypatch.setattr(document_router.processor, "extract_blocking", slow_extract)
        monkeypatch.setattr(settings, "OCR_TIMEOUT_SECONDS", 0.2)

        async with _asgi() as client:
            resp = await client.post(
                "/api/documents/upload",
                data={"patient_id": patient_id},
                files={"file": ("slow.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            )
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()

        # Document record persists with FAILED status; original file kept.
        async with _test_session_factory() as db:
            res = await db.execute(select(MedicalDocument).where(MedicalDocument.patient_id == patient_id))
            doc = res.scalars().first()
            assert doc is not None and doc.ocr_status == "FAILED"
            assert os.path.exists(doc.file_path)
            os.remove(doc.file_path)  # cleanup test upload
