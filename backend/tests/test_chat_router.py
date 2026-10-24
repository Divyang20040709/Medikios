import pytest
from unittest.mock import AsyncMock, patch
from backend.app.api.chat_router import send_chat_message, get_suggested_prompts, ChatMessageRequest

@pytest.mark.asyncio
async def test_get_suggested_prompts():
    patient_prompts = await get_suggested_prompts(role="patient", language="en")
    assert len(patient_prompts) >= 3
    assert any("chest" in p["text"].lower() for p in patient_prompts)

    hindi_prompts = await get_suggested_prompts(role="patient", language="hi")
    assert len(hindi_prompts) >= 3

    gujarati_prompts = await get_suggested_prompts(role="patient", language="gu")
    assert len(gujarati_prompts) >= 3

    doctor_prompts = await get_suggested_prompts(role="doctor", language="en")
    assert len(doctor_prompts) >= 3
    assert any("differential" in p["text"].lower() for p in doctor_prompts)

@pytest.mark.asyncio
async def test_chat_message_execution():
    mock_db = AsyncMock()
    
    with patch("backend.app.api.chat_router.llm_service.chat_completion", new_callable=AsyncMock) as mock_llm:
        # QA BUG-006: chat_router now requests return_engine=True, so the service
        # returns (reply_text, engine). The endpoint must surface that engine.
        mock_llm.return_value = ("MediKiosk Assistant: Based on your description, please proceed to consultation.", "deterministic_fallback")

        req = ChatMessageRequest(
            message="I have severe chest pressure",
            role="patient",
            language="en"
        )

        response = await send_chat_message(req, mock_db)
        assert response["role"] == "assistant"
        assert "MediKiosk Assistant" in response["reply"]
        assert response["language"] == "en"
        # Honest provenance is exposed and no commercial model is named for a fallback.
        assert response["engine"] == "deterministic_fallback"
        assert response["model"] is None
