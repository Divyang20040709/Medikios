"""
Phase 2 — Patient interview speech recognition tests.
Covers: /api/speech/status contract, transcribe endpoint validation errors
(400/413/unsupported language), and the auto provider orchestration that
selects the free local IndicConformer for hi/gu and Whisper for en.
"""
import io
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.speech import provider as provider_module
from backend.app.speech.provider import (
    WhisperSpeechProvider,
    get_speech_provider,
    get_speech_provider_info,
    whisper_model_ready,
)

TEST_WAV = os.path.join(os.path.dirname(__file__), "test_audio", "test_tone_16k.wav")

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── /api/speech/status ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_speech_status_endpoint_contract():
    async with _client() as client:
        resp = await client.get("/api/speech/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["supported_languages"] == ["en", "hi", "gu"]
        assert set(data["languages"].keys()) == {"en", "hi", "gu"}
        for lang_info in data["languages"].values():
            assert "provider" in lang_info
            assert isinstance(lang_info["ready"], bool)
        assert data["max_upload_mb"] >= 1
        # Status must never claim a backend is ready when nothing is provisioned
        assert data["any_backend_ready"] == any(
            v["ready"] for v in data["languages"].values()
        )


# ── /api/speech/transcribe validation errors ────────────────────────────

@pytest.mark.asyncio
async def test_transcribe_rejects_too_short_audio():
    async with _client() as client:
        files = {"audio": ("tiny.wav", io.BytesIO(b"RIFF"), "audio/wav")}
        resp = await client.post("/api/speech/transcribe", data={"language": "en"}, files=files)
        assert resp.status_code == 400
        assert "short" in resp.json()["detail"].lower() or "empty" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_transcribe_rejects_unsupported_language():
    with open(TEST_WAV, "rb") as f:
        audio = f.read()
    async with _client() as client:
        files = {"audio": ("voice.wav", io.BytesIO(audio), "audio/wav")}
        resp = await client.post("/api/speech/transcribe", data={"language": "fr"}, files=files)
        assert resp.status_code == 400
        assert "not supported" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_transcribe_rejects_oversized_audio():
    async with _client() as client:
        big = b"\x00" * (15 * 1024 * 1024 + 10)
        files = {"audio": ("big.wav", io.BytesIO(big), "audio/wav")}
        resp = await client.post("/api/speech/transcribe", data={"language": "en"}, files=files)
        assert resp.status_code == 413


@pytest.mark.asyncio
async def test_transcribe_never_fakes_success_without_model():
    """When no ASR backend is ready the endpoint must fail visibly (503),
    so the UI can show an honest error instead of invented text."""
    if whisper_model_ready():
        pytest.skip("Whisper weights provisioned in this environment")
    with open(TEST_WAV, "rb") as f:
        audio = f.read()
    async with _client() as client:
        files = {"audio": ("voice.wav", io.BytesIO(audio), "audio/wav")}
        resp = await client.post("/api/speech/transcribe", data={"language": "en"}, files=files)
        assert resp.status_code == 503


# ── Provider orchestration (SPEECH_PROVIDER=auto) ───────────────────────

def test_auto_selects_whisper_for_english(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    p = get_speech_provider("en")
    assert isinstance(p, WhisperSpeechProvider)


def test_auto_selects_indicconformer_for_hi_gu_on_gpu(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("INDICCONFORMER_DEVICE", "cuda")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: True)
    from backend.app.speech.indicconformer_provider import IndicConformerSpeechProvider
    for lang in ("hi", "gu"):
        p = get_speech_provider(lang)
        assert isinstance(p, IndicConformerSpeechProvider)


def test_auto_prefers_whisper_for_indic_on_cpu_when_weights_present(monkeypatch):
    """CPU kiosk: cached Whisper responds in seconds; IC reloads 2.4 GB per
    call. Auto must pick the patient-practical engine."""
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("INDICCONFORMER_DEVICE", "cpu")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: True)
    monkeypatch.setattr(provider_module, "whisper_model_ready", lambda: True)
    p = get_speech_provider("gu")
    assert isinstance(p, WhisperSpeechProvider)


def test_auto_uses_indicconformer_on_cpu_only_when_whisper_missing(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("INDICCONFORMER_DEVICE", "cpu")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: True)
    monkeypatch.setattr(provider_module, "whisper_model_ready", lambda: False)
    from backend.app.speech.indicconformer_provider import IndicConformerSpeechProvider
    p = get_speech_provider("hi")
    assert isinstance(p, IndicConformerSpeechProvider)


def test_auto_falls_back_to_whisper_for_indic_when_not_provisioned(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: False)
    p = get_speech_provider("gu")
    assert isinstance(p, WhisperSpeechProvider)


def test_explicit_whisper_pin_never_upgrades(monkeypatch):
    """Existing pinned behaviour must stay intact (backward compatibility)."""
    monkeypatch.setenv("SPEECH_PROVIDER", "whisper")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: True)
    p = get_speech_provider("hi")
    assert isinstance(p, WhisperSpeechProvider)


def test_whisper_model_ready_is_false_for_empty_dir(tmp_path):
    assert whisper_model_ready(model_path=str(tmp_path), model_name="base") is False


def test_whisper_model_ready_detects_local_checkpoint(tmp_path):
    (tmp_path / "base.pt").write_bytes(b"dummy")
    assert whisper_model_ready(model_path=str(tmp_path), model_name="base") is True


def test_provider_info_structure(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "auto")
    monkeypatch.setenv("INDICCONFORMER_DEVICE", "cuda")
    monkeypatch.setattr(provider_module, "_indicconformer_available", lambda: True)
    info = get_speech_provider_info()
    assert info["configured_provider"] == "auto"
    assert info["languages"]["gu"]["provider"] == "indicconformer"
    assert info["languages"]["gu"]["ready"] is True
    assert info["languages"]["en"]["provider"] == "whisper"
