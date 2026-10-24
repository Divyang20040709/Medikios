"""
Phase 3 — Local LLM integration tests.

Hermetic: no network. The single HTTP seam `local_llm._http_json` is
monkeypatched to simulate Ollama / OpenAI-compatible servers, timeouts and
garbage output. Endpoint tests use an in-memory SQLite DB.
"""

import json
import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.app.main import app
from backend.app.database.session import Base, get_db
from backend.app.services import local_llm
from backend.app.services.local_llm import LocalLLMClient, reset_availability_cache
from backend.app.services.followup_service import (
    validate_question, parse_json_array, guideline_questions, generate_followups,
)
from backend.app.services.llm_service import llm_service


# ── hermetic DB (same pattern as test_api_flow.py) ───────────────────────
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
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_llm_cache():
    reset_availability_cache()
    yield
    reset_availability_cache()


# ── output validation (safety contract) ──────────────────────────────────

class TestValidation:
    def test_rejects_dosage_advice(self):
        assert validate_question("You should take 500mg tablet every morning?", "en") is None

    def test_rejects_symptom_minimising_wording(self):
        assert validate_question("Do not worry, the pain is nothing serious?", "en") is None
        assert validate_question("The swelling is perfectly fine?", "en") is None

    def test_rejects_diagnosis_and_prescription(self):
        assert validate_question("Are you aware you probably have asthma?", "en") is None
        assert validate_question("Did the doctor prescribe anything for this?", "en") is None

    def test_rejects_missing_question_mark(self):
        assert validate_question("Tell me more about the pain", "en") is None

    def test_rejects_too_short_and_too_long(self):
        assert validate_question("Bad?", "en") is None
        assert validate_question("Does " + "the pain " * 30 + "hurt?", "en") is None

    def test_rejects_latin_script_for_hindi(self):
        assert validate_question("Do you have shortness of breath?", "hi") is None

    def test_accepts_devanagari_hindi(self):
        good = "\u0915\u094d\u092f\u093e \u0906\u092a\u0915\u094b \u0938\u093e\u0902\u0938 \u0932\u0947\u0928\u0947 \u092e\u0947\u0902 \u0924\u0915\u0932\u0940\u092b \u0939\u094b \u0930\u0939\u0940 \u0939\u0948?"
        assert validate_question(good, "hi") == good

    def test_rejects_indic_leakage_in_english(self):
        assert validate_question("Do you have \u0926\u0930\u094d\u0922 (dard) somewhere?", "en") is None

    def test_accepts_plain_english_question(self):
        assert validate_question("Does the pain spread to your arm or jaw?", "en") == \
            "Does the pain spread to your arm or jaw?"

    def test_tolerant_json_array_parse(self):
        assert parse_json_array('Sure! ["any breathing trouble?", "how long?"] thanks') == \
            ["any breathing trouble?", "how long?"]
        assert parse_json_array('{"questions": ["q1 one?", "q2 two?"]}') == ["q1 one?", "q2 two?"]
        assert parse_json_array("not json at all") is None


class TestGuidelineFallback:
    def test_returns_questions_skipping_answered_sections(self):
        qs = guideline_questions("chest pain since morning", ["SITE", "ONSET"], "en", 3)
        assert len(qs) == 3
        assert all(q["provenance"] == "guideline" for q in qs)
        assert all(q["section"] not in ("SITE", "ONSET") for q in qs)

    def test_gujarati_honestly_falls_back_to_english_text(self):
        # Ontology has hi+bn translations but no gu — must not crash or fabricate.
        qs = guideline_questions("mujhe tav bahut din se hai", [], "gu", 2)
        assert len(qs) == 2


# ── LocalLLMClient transport (monkeypatched HTTP seam) ───────────────────

def _install_server(monkeypatch, handler):
    async def fake_http_json(method, url, payload=None, timeout=5.0):
        return handler(method, url, payload)
    monkeypatch.setattr(local_llm, "_http_json", fake_http_json)


class TestLocalLLMClient:
    async def test_ollama_detected_and_generates(self, monkeypatch):
        def handler(method, url, payload):
            if url.endswith("/api/tags"):
                return {"models": [{"name": "llama3.2:latest"}]}
            assert url.endswith("/api/chat")
            assert payload["format"] == "json"
            return {"message": {"content": '["How long has the pain lasted?"]'}}
        _install_server(monkeypatch, handler)

        client = LocalLLMClient()
        assert await client.probe() == "ollama"
        out = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)
        assert out == '["How long has the pain lasted?"]'

    async def test_openai_compat_detected_when_ollama_absent(self, monkeypatch):
        def handler(method, url, payload):
            if url.endswith("/api/tags"):
                raise httpx.ConnectError("refused")
            if url.endswith("/v1/models"):
                return {"data": [{"id": "local-model-x"}]}
            assert url.endswith("/v1/chat/completions")
            return {"choices": [{"message": {"content": "ok"}}]}
        _install_server(monkeypatch, handler)

        client = LocalLLMClient()
        assert await client.probe() == "openai"
        assert client.model == "local-model-x"
        assert await client.chat([{"role": "user", "content": "hi"}]) == "ok"

    async def test_no_server_returns_none_never_raises(self, monkeypatch):
        def handler(method, url, payload):
            raise httpx.ConnectError("connection refused")
        _install_server(monkeypatch, handler)

        client = LocalLLMClient()
        assert await client.probe() is None
        assert await client.chat([{"role": "user", "content": "hi"}]) is None

    async def test_timeout_during_generation_returns_none(self, monkeypatch):
        def handler(method, url, payload):
            if url.endswith("/api/tags"):
                return {"models": [{"name": "llama3.2:latest"}]}
            raise httpx.ReadTimeout("slow CPU inference")
        _install_server(monkeypatch, handler)

        client = LocalLLMClient()
        assert await client.chat([{"role": "user", "content": "hi"}]) is None

    async def test_model_not_pulled_disables_until_provisioned(self, monkeypatch):
        def handler(method, url, payload):
            if url.endswith("/api/tags"):
                return {"models": [{"name": "phi3:mini"}]}
            raise httpx.ConnectError("refused")
        _install_server(monkeypatch, handler)
        assert await LocalLLMClient().probe() is None

    async def test_master_switch_off_skips_network(self, monkeypatch):
        from backend.app.core.config import settings
        monkeypatch.setattr(settings, "LOCAL_LLM_ENABLED", False)
        assert await LocalLLMClient().probe() is None


# ── generate_followups orchestration ─────────────────────────────────────

_STATEMENTS = [
    {"question_text": "Chief complaint", "answer_text": "Chest pain since 2 days, worse at night"},
]


class TestGenerateFollowups:
    async def test_valid_llm_output_is_used(self, monkeypatch):
        payload = json.dumps([
            "Does the pain spread anywhere else?",
            "You should take 500mg paracetamol?",  # unsafe → must be dropped
        ])

        async def fake_chat(self, messages, **kw):
            return payload
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        result = await generate_followups(_STATEMENTS, "en", 2)
        texts = [q["text"] for q in result["questions"]]
        assert "Does the pain spread anywhere else?" in texts
        assert all("500mg" not in t for t in texts)
        assert result["source"] in ("local_llm", "hybrid")
        assert len(result["questions"]) == 2

    async def test_llm_offline_falls_back_to_guideline_questions(self, monkeypatch):
        async def fake_chat(self, messages, **kw):
            return None  # transport unavailable
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        result = await generate_followups(_STATEMENTS, "en", 3)
        assert result["source"] == "rule_fallback"
        assert len(result["questions"]) == 3
        assert all(q["provenance"] == "guideline" for q in result["questions"])

    async def test_garbage_output_falls_back_safely(self, monkeypatch):
        async def fake_chat(self, messages, **kw):
            return "Sorry, I cannot help with medical questions."
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        result = await generate_followups(_STATEMENTS, "en", 2)
        assert result["source"] == "rule_fallback"
        assert all("?" in q["text"] for q in result["questions"])

    async def test_hindi_output_in_english_script_is_rejected(self, monkeypatch):
        async def fake_chat(self, messages, **kw):
            return json.dumps(["Do you have fever in the evening?"])
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        result = await generate_followups(_STATEMENTS, "hi", 2)
        # Latin-script "hindi" rejected → guideline pool (hi translations exist)
        assert result["source"] == "rule_fallback"
        assert len(result["questions"]) == 2


# ── chat_completion local-first chain ────────────────────────────────────

class TestChatCompletionLocalFirst:
    async def test_local_answer_preferred_over_fallback(self, monkeypatch):
        async def fake_chat(self, messages, **kw):
            return "Local answer: please describe the pain."
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        out = await llm_service.chat_completion([{"role": "user", "content": "my chest hurts"}])
        assert out == "Local answer: please describe the pain."

    async def test_safe_hardcoded_fallback_when_local_absent(self, monkeypatch):
        async def fake_chat(self, messages, **kw):
            return None
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        if llm_service.api_key:
            pytest.skip("OPENROUTER key configured — hardcoded fallback not reachable")
        out = await llm_service.chat_completion([{"role": "user", "content": "ok"}])
        assert "MediKiosk Clinical Assistant" in out


# ── POST /api/intake/followup-questions endpoint ─────────────────────────

@pytest.fixture()
def llm_off(monkeypatch):
    """Deterministic endpoint behaviour without any local server running."""
    async def fake_chat(self, messages, **kw):
        return None
    monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)


class TestFollowupEndpoint:
    async def test_no_answers_is_400(self, llm_off):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/intake/followup-questions", json={"answers": []})
            assert resp.status_code == 400

    async def test_unknown_session_is_404(self, llm_off):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/intake/followup-questions", json={
                "session_id": "does-not-exist", "answers": [
                    {"question_text": "Q", "answer_text": "A", "section_id": "SITE"}]
            })
            assert resp.status_code == 404

    async def test_inline_answers_generate_guideline_questions(self, llm_off):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/intake/followup-questions", json={
                "language": "en", "max_questions": 2, "answers": [
                    {"question_text": "Chief complaint",
                     "answer_text": "Stomach pain after meals", "section_id": "CHIEF_COMPLAINT"}]
            })
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["questions"]) == 2
            assert data["source"] == "rule_fallback"
            assert all("?" in q["text"] for q in data["questions"])

    async def test_red_flag_escalation_survives_llm_path(self, monkeypatch):
        """Even when the LLM answers (or tries to downplay), the deterministic
        RedFlagEngine escalation MUST be attached to the response."""
        async def fake_chat(self, messages, **kw):
            return json.dumps(["Do not worry the pain is nothing serious?",
                               "Does the pain spread to your back?"])
        monkeypatch.setattr(LocalLLMClient, "chat", fake_chat)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/intake/followup-questions", json={
                "language": "en", "max_questions": 2, "answers": [
                    {"question_text": "SOCRATES symptom breakdown",
                     "answer_text": "Site: central chest; Radiation: left arm; Associated: cold sweating",
                     "section_id": "SOCRATES"}]
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["escalation_required"] is True
            assert any("Cardiac" in rf["title"] for rf in data["red_flags"])
            # Unsafe "don't worry" question must have been rejected by validation
            assert all("worry" not in q["text"].lower() for q in data["questions"])
