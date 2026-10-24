import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from backend.app.speech.provider import (
    get_speech_provider,
    get_speech_provider_info,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/speech", tags=["Multilingual Speech Pipeline"])

MAX_AUDIO_SIZE = 15 * 1024 * 1024  # 15 MB

SUPPORTED_INTERVIEW_LANGUAGES = ["en", "hi", "gu"]


@router.get("/status")
async def speech_status():
    """
    Readiness snapshot used by the patient kiosk voice UI to decide how to
    capture speech (browser dictation vs. microphone recording uploaded to
    this API). Reports the truth about locally provisioned models; performs
    no model loading and no downloads.
    """
    info = get_speech_provider_info()
    info["supported_languages"] = SUPPORTED_INTERVIEW_LANGUAGES
    return info


@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(
    language: str = Form("hi"),
    audio: UploadFile = File(...)
):
    """
    Receives an audio stream/file from the patient kiosk microphone,
    transcribes it using the active speech provider (IndicConformer or Whisper),
    and returns a normalized transcript with confidence score and clinical grounding.
    """
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio file provided."
        )

    audio_bytes = await audio.read()

    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty or too short. Please speak for at least a second and try again."
        )

    lang = (language or "en").strip().lower()
    if lang not in SUPPORTED_INTERVIEW_LANGUAGES and lang != "auto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Language '{language}' is not supported. Supported languages: "
                   f"{', '.join(SUPPORTED_INTERVIEW_LANGUAGES)}."
        )

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds the maximum allowed size of {MAX_AUDIO_SIZE // (1024*1024)} MB."
        )

    provider = get_speech_provider(lang)

    try:
        result = await provider.transcribe(audio_bytes, language=lang)
        
        # Check if the provider was unavailable
        if "unavailable" in result.provider and not result.transcript:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Speech recognition service ({result.provider}) is temporarily unavailable."
            )
            
        return result
    except HTTPException:
        # Phase 7: the router's own responses (e.g. 503 unavailable provider)
        # must not be re-wrapped by the generic handler below — the kiosk UI
        # relies on the honest status code to decide its fallback path.
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except RuntimeError as re:
        logger.error(f"Speech transcription runtime error: {re}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(re)
        )
    except Exception as exc:
        logger.exception(f"Unexpected error during transcription: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during speech transcription."
        )
