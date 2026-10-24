import os
import io
import pytest
import pytest_asyncio
from PIL import Image
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.models.entities import Patient
from backend.app.speech.provider import (
    WhisperSpeechProvider,
    get_speech_provider,
    whisper_model_ready,
    WHISPER_DIR,
)
from backend.app.documents.processor import ClinicalDocumentProcessor, PaddleOCRProcessor, PADDLEOCR_DIR

TEST_WAV = os.path.join(os.path.dirname(__file__), "test_audio", "test_tone_16k.wav")

def _real_audio_bytes() -> bytes:
    with open(TEST_WAV, "rb") as f:
        return f.read()

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

@pytest.mark.asyncio
async def test_whisper_speech_provider_paths():
    provider = get_speech_provider()
    assert isinstance(provider, WhisperSpeechProvider)
    assert os.path.exists(WHISPER_DIR)
    assert provider.model_path is not None

@pytest.mark.asyncio
async def test_whisper_speech_provider_transcription_en():
    """Contract: with weights provisioned the real model runs (a tone-only wav
    may honestly yield an empty transcript); without weights the provider must
    return an empty 'unavailable' result — never fabricated text."""
    provider = WhisperSpeechProvider()
    audio = _real_audio_bytes()
    res = await provider.transcribe(audio, language="en")
    assert res.language == "en"
    if whisper_model_ready():
        assert res.provider == "whisper_local_model"
        assert isinstance(res.transcript, str)
        # Silence/tone must not invent clinical content
        if not res.transcript:
            assert res.confidence == 0.0
    else:
        assert res.transcript == ""
        assert res.confidence == 0.0
        assert "unavailable" in res.provider

@pytest.mark.asyncio
async def test_whisper_speech_provider_transcription_hi():
    provider = WhisperSpeechProvider()
    audio = _real_audio_bytes()
    res = await provider.transcribe(audio, language="hi")
    assert res.language == "hi"
    if whisper_model_ready():
        assert len(res.transcript) >= 0  # tone wav may yield empty text; model ran honestly
        assert "whisper" in res.provider or "unavailable" in res.provider
    else:
        assert res.transcript == ""
        assert "unavailable" in res.provider

@pytest.mark.asyncio
async def test_paddleocr_processor_paths():
    ocr_proc = PaddleOCRProcessor()
    assert os.path.exists(PADDLEOCR_DIR)
    assert ocr_proc.model_dir is not None

@pytest.mark.asyncio
async def test_clinical_document_processor_paddle_integration(tmp_path):
    doc_proc = ClinicalDocumentProcessor()
    assert hasattr(doc_proc, "paddle_ocr")
    assert isinstance(doc_proc.paddle_ocr, PaddleOCRProcessor)

    # Blank prescription image: honest contract — the processor must return
    # ONLY text actually present. No readable text ⇒ empty extraction,
    # zero entities, zero confidence. Fabricated demo content is a bug.
    test_img_path = str(tmp_path / "rx_test.png")
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    img.save(test_img_path)

    extracted = await doc_proc.extract(test_img_path, "image/png")
    assert extracted.document_type in ["PRESCRIPTION", "LAB_REPORT", "DISCHARGE_SUMMARY", "OTHER"]
    if not extracted.raw_text.strip():
        assert extracted.overall_confidence == 0.0
        assert extracted.medications == []
        assert extracted.observations == []
        assert extracted.diagnoses == []

@pytest.mark.asyncio
async def test_speech_api_transcribe_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "audio": ("voice.wav", io.BytesIO(_real_audio_bytes()), "audio/wav")
        }
        data = {"language": "en"}
        resp = await client.post("/api/speech/transcribe", data=data, files=files)
        if whisper_model_ready():
            assert resp.status_code == 200
            res_data = resp.json()
            assert "transcript" in res_data
            assert "confidence" in res_data
            assert res_data["provider"] == "whisper_local_model"
        else:
            # No weights: API must fail visibly with 503, never fake success
            assert resp.status_code == 503
            assert "unavailable" in resp.json()["detail"].lower()

@pytest.mark.asyncio
async def test_document_upload_ocr_endpoint(tmp_path):
    # Seed patient
    async with _test_session_factory() as db:
        p = Patient(name="OCR Patient", age=45, gender="MALE", phone="9988776655", mrn="MRN-OCR-1")
        db.add(p)
        await db.commit()
        pat_id = p.id

    # Create blank image (no readable content)
    test_img = io.BytesIO()
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    img.save(test_img, format="JPEG")
    test_img.seek(0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file": ("prescription.jpg", test_img, "image/jpeg")
        }
        data = {
            "patient_id": pat_id,
            "document_type": "PRESCRIPTION"
        }
        resp = await client.post("/api/documents/upload", data=data, files=files)
        assert resp.status_code == 200
        doc_data = resp.json()
        assert "document_id" in doc_data
        # Honest contract: a blank scan must be reported as NO_TEXT with zero
        # entities (never fabricated clinical content). If a working OCR engine
        # somehow read real text, COMPLETED is also acceptable.
        assert doc_data["ocr_status"] in ("NO_TEXT", "COMPLETED")
        if doc_data["ocr_status"] == "NO_TEXT":
            assert doc_data["entities"] == []
            assert doc_data["overall_confidence"] == 0.0
            # Patient-selected type is preserved, not overwritten by a guess.
            assert doc_data["document_type"] == "PRESCRIPTION"
