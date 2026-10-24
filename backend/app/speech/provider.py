import os
import io
import sys
import tempfile
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Ensure local model directory is discoverable in Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "model")
WHISPER_DIR = os.path.join(MODEL_DIR, "whisper")

if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

MAX_AUDIO_BYTES = int(os.getenv("SPEECH_MAX_AUDIO_SIZE_BYTES", str(15 * 1024 * 1024)))

class TranscriptionResult(BaseModel):
    transcript: str
    language: str
    confidence: float
    detected_language: Optional[str] = None
    provider: str
    clinical_grounding: Optional[Dict[str, Any]] = None

class SpeechProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> TranscriptionResult:
        pass

class WhisperSpeechProvider(SpeechProvider):
    """
    Whisper speech recognition provider powered by the local Whisper model module
    located in the 'model/whisper' folder.
    Supports multilingual transcription across English and Indian regional languages.
    """
    def __init__(self, model_name: str = "base", model_path: Optional[str] = None):
        self.model_name = os.getenv("WHISPER_MODEL_SIZE", model_name)
        self.model_path = model_path or os.getenv("WHISPER_MODEL_PATH", WHISPER_DIR)
        # Default to CPU: many local torch builds are incompatible with newer
        # GPUs (e.g. sm_120), and the 'base' model runs fine on CPU.
        self.device = os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu"
        self._model = None
        self._load_attempted = False

    def _get_model(self):
        if not self._load_attempted:
            self._load_attempted = True
            try:
                import whisper
                logger.info(f"Loading Whisper model '{self.model_name}' (device={self.device}) from: {self.model_path}")
                self._model = whisper.load_model(
                    self.model_name,
                    device=self.device,
                    download_root=self.model_path,
                )
                logger.info("Local Whisper ASR model loaded successfully.")
            except Exception as e:
                logger.info(
                    f"Local Whisper model initialization at {self.model_path} ({e}); "
                    "operating in clinical acoustic normalization fallback mode."
                )
                self._model = None
        return self._model

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> TranscriptionResult:
        logger.info(f"Whisper processing audio input: {len(audio_bytes)} bytes in requested language: {language}")
        
        model = self._get_model()
        if model is not None and len(audio_bytes) > 0:
            tmp_path = None
            try:
                # Write audio bytes to temporary file for Whisper ingestion
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_file.write(audio_bytes)
                    tmp_path = tmp_file.name

                import whisper
                whisper_lang = None if language in ("auto", "", None) else language
                result = whisper.transcribe(model, tmp_path, language=whisper_lang, fp16=False)
                transcript_text = result.get("text", "").strip()
                detected_lang = result.get("language", language)
                confidence = self._confidence_from_result(result, transcript_text)

                # Empty text with a loaded model means "no speech detected" —
                # an honest 200 result, NOT a service-unavailable error.
                grounding = self._ground_transcript(transcript_text, language) if transcript_text else None
                return TranscriptionResult(
                    transcript=transcript_text,
                    language=language,
                    confidence=confidence,
                    detected_language=detected_lang,
                    provider="whisper_local_model",
                    clinical_grounding=grounding
                )
            except Exception as exc:
                logger.warning(f"Whisper local inference execution fallback: {exc}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

        # Model unavailable — return honest error, never fabricate text
        logger.warning(
            "Whisper model not loaded and no real transcription available. "
            "Returning error instead of fabricated fallback text."
        )
        return TranscriptionResult(
            transcript="",
            language=language,
            confidence=0.0,
            detected_language=language,
            provider="whisper_unavailable",
            clinical_grounding=None,
        )

    @staticmethod
    def _confidence_from_result(result: Dict[str, Any], transcript_text: str) -> float:
        """Derive confidence from Whisper segment avg_logprob (0.0–1.0).
        Returns 0.0 when there is no text — nothing was heard."""
        if not transcript_text:
            return 0.0
        import math
        try:
            logprobs = [
                s.get("avg_logprob")
                for s in result.get("segments", [])
                if s.get("avg_logprob") is not None
            ]
            if logprobs:
                avg = sum(logprobs) / len(logprobs)
                return max(0.0, min(1.0, math.exp(avg)))  # geometric mean of probabilities
        except Exception:
            pass
        return 0.5  # produced text but no usable logprob data

    def _ground_transcript(self, text: str, language: str) -> Optional[Dict[str, Any]]:
        """Matches transcribed text against Indic clinical lexicon."""
        lexicon_file = os.path.join(MODEL_DIR, "indic_clinical_lexicon.json")
        if not os.path.exists(lexicon_file):
            return None
        try:
            import json
            with open(lexicon_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            lexicon = data.get("lexicon", {})
            text_lower = text.lower()
            matched = []
            for c_key, c_val in lexicon.items():
                terms = c_val.get("en", []) + c_val.get("hi", []) + c_val.get("gu", [])
                if any(t.lower() in text_lower for t in terms):
                    matched.append({
                        "concept": c_key,
                        "concept_id": c_val.get("concept_id"),
                        "department": c_val.get("department"),
                        "priority": c_val.get("priority")
                    })
            if matched:
                return {
                    "matched_concepts": matched,
                    "primary_department": matched[0]["department"],
                    "suggested_priority": matched[0]["priority"]
                }
        except Exception as e:
            logger.warning(f"Could not ground transcript: {e}")
        return None

# Backward-compatible alias for any legacy references
class BhashiniSpeechProvider(WhisperSpeechProvider):
    """
    Deprecated: Bhashini speech recognition has been replaced with Whisper.
    Delegates to WhisperSpeechProvider.
    """
    def __init__(self, *args, **kwargs):
        super().__init__()
        logger.info("BhashiniSpeechProvider called; redirected to WhisperSpeechProvider.")

def whisper_model_ready(model_path: Optional[str] = None, model_name: Optional[str] = None) -> bool:
    """
    Cheap, non-loading check for whether local Whisper weights exist.
    Mirrors the provider's own resolution (load_model is always called with
    download_root=WHISPER_MODEL_PATH), so it must not consult other caches.
    Never triggers a download.
    """
    import glob

    name = model_name or os.getenv("WHISPER_MODEL_SIZE", "base")
    roots = [model_path or os.getenv("WHISPER_MODEL_PATH", WHISPER_DIR)]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        # Exact-match filename or any checkpoint present for that size
        if glob.glob(os.path.join(root, f"*{name}*.pt")) or glob.glob(os.path.join(root, "*.pt")):
            return True
    return False


def _indicconformer_available() -> bool:
    """Return True if the IndicConformer provider is provisioned (does not load the model)."""
    try:
        from backend.app.speech.indicconformer_provider import (
            IndicConformerSpeechProvider,
        )
        return IndicConformerSpeechProvider().is_available
    except Exception:
        return False


def _indicconformer_preferred(lang: str) -> bool:
    """
    Policy for SPEECH_PROVIDER='auto' with an Indic language:
      - IndicConformer (600M) shines on GPU (INDICCONFORMER_DEVICE=cuda with a
        compatible torch build) → preferred for hi/gu accuracy.
      - On CPU-only / GPU-incompatible machines the subprocess reload of the
        2.4 GB checkpoint exceeds practical kiosk wait times, so the locally
        cached Whisper model is preferred when its weights are present.
      - If Whisper weights are missing, fall back to IndicConformer anyway —
        slow-but-correct beats unavailable.
    """
    if lang not in ("hi", "gu"):
        return False
    if not _indicconformer_available():
        return False
    if os.getenv("INDICCONFORMER_DEVICE", "cpu").strip().lower() == "cuda":
        return True
    return not whisper_model_ready()


def _resolve_auto(lang: str) -> SpeechProvider:
    if _indicconformer_preferred(lang):
        from backend.app.speech.indicconformer_provider import (
            IndicConformerSpeechProvider,
        )
        logger.info(f"Auto-selecting IndicConformer speech provider for '{lang}'.")
        return IndicConformerSpeechProvider()
    logger.info(f"Auto-selecting Whisper speech provider for '{lang}'.")
    return WhisperSpeechProvider()


def get_speech_provider(language: Optional[str] = None) -> SpeechProvider:
    """
    Returns the configured SpeechProvider based on the SPEECH_PROVIDER
    environment variable:
      - 'indicconformer' → IndicConformerSpeechProvider (real Indic ASR)
      - 'whisper'        → WhisperSpeechProvider (local Whisper model)
      - 'auto' (default) → per-language selection (see _indicconformer_preferred):
                           * Hindi / Gujarati → IndicConformer on GPU,
                             Whisper on CPU when weights exist, IC as last resort.
                           * English          → Whisper (IndicConformer has no
                             English support), honest 503 if weights missing.

    Falls back to Whisper if IndicConformer is requested but unavailable.
    """
    provider_name = os.getenv("SPEECH_PROVIDER", "auto").strip().lower()
    lang = (language or "").strip().lower()

    if provider_name == "indicconformer":
        try:
            from backend.app.speech.indicconformer_provider import (
                IndicConformerSpeechProvider,
            )
            provider = IndicConformerSpeechProvider()
            if provider.is_available:
                logger.info("Using IndicConformer speech provider.")
                return provider
            else:
                logger.warning(
                    f"IndicConformer not available: {provider.error_reason}. "
                    "Falling back to Whisper."
                )
        except Exception as e:
            logger.warning(
                f"Failed to initialize IndicConformer provider ({e}). "
                "Falling back to Whisper."
            )
    elif provider_name == "auto" and lang in ("hi", "gu"):
        return _resolve_auto(lang)

    logger.info("Using Whisper speech provider.")
    return WhisperSpeechProvider()


def get_speech_provider_info() -> Dict[str, Any]:
    """
    Readiness snapshot for the patient-interview voice UI. Reports what the
    server can genuinely do right now — no model is loaded or downloaded.
    """
    provider_name = os.getenv("SPEECH_PROVIDER", "auto").strip().lower()
    w_ready = whisper_model_ready()
    ic_provisioned = provider_name in ("auto", "indicconformer") and _indicconformer_available()

    def _entry(lang: str) -> Dict[str, Any]:
        if provider_name == "indicconformer":
            chosen, alt = ("indicconformer", ic_provisioned), ("whisper", w_ready)
        elif provider_name == "whisper":
            chosen, alt = ("whisper", w_ready), None
        else:  # auto
            if ic_provisioned and _indicconformer_preferred(lang):
                chosen = ("indicconformer", True)
                alt = ("whisper", w_ready)
            else:
                chosen = ("whisper", w_ready)
                alt = ("indicconformer", ic_provisioned) if lang in ("hi", "gu") else None
        ready = chosen[1] or (alt[1] if alt else False)
        return {"provider": chosen[0], "ready": ready}

    languages = {lang: _entry(lang) for lang in ("en", "hi", "gu")}
    return {
        "configured_provider": provider_name,
        "languages": languages,
        "max_upload_mb": round(MAX_AUDIO_BYTES / (1024 * 1024)),
        "any_backend_ready": any(v["ready"] for v in languages.values()),
    }
