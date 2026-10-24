"""
IndicConformer Speech Provider
──────────────────────────────
Loads the AI4Bharat IndicConformer Multilingual 600M checkpoint (.nemo)
and provides real Gujarati/Hindi (and other Indic language) speech-to-text.

Requires the speech inference virtual-environment (.venv_speech) with:
  torch, torchaudio, nemo_toolkit[asr] (AI4Bharat fork, nemo-v2 branch)

Configuration env-vars
  INDICCONFORMER_MODEL_PATH   – path to the .nemo file (repo-relative default)
  INDICCONFORMER_DEVICE       – cuda | cpu  (auto-detected if unset)
  INDICCONFORMER_DECODER      – ctc | rnnt  (default: ctc)
  SPEECH_MAX_AUDIO_SIZE_BYTES – max upload size (default: 15 MB)
"""

import os
import io
import sys
import time
import wave
import struct
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.app.speech.provider import (
    SpeechProvider,
    TranscriptionResult,
    PROJECT_ROOT,
    MODEL_DIR,
)

logger = logging.getLogger(__name__)

# Languages supported by the IndicConformer multilingual checkpoint
SUPPORTED_LANGUAGES = {
    "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok",
    "mai", "ml", "mr", "mni", "ne", "or", "pa", "sa", "sat",
    "sd", "ta", "te", "ur",
}

# Default checkpoint filename (at repo root)
DEFAULT_CHECKPOINT_NAME = "indicconformer_stt_multi_hybrid_rnnt_600m.nemo"
DEFAULT_CHECKPOINT_PATH = os.path.join(PROJECT_ROOT, DEFAULT_CHECKPOINT_NAME)

# Max audio upload size (bytes)
MAX_AUDIO_SIZE = int(os.getenv("SPEECH_MAX_AUDIO_SIZE_BYTES", str(15 * 1024 * 1024)))

# Subprocess inference timeout. Cold CPU loads of the 2.4 GB checkpoint can
# exceed two minutes; override via env for slower hardware or GPU setups.
INFERENCE_TIMEOUT_SECONDS = int(os.getenv("SPEECH_INFERENCE_TIMEOUT_SECONDS", "300"))

# Path to the speech venv python
SPEECH_VENV_PYTHON = os.path.join(
    PROJECT_ROOT, ".venv_speech", "Scripts", "python.exe"
)

# Standalone inference script shipped alongside this module
_INFERENCE_SCRIPT = os.path.join(
    os.path.dirname(__file__), "indicconformer_infer.py"
)


def _resolve_model_path() -> str:
    """Return the absolute path to the .nemo checkpoint."""
    env_path = os.getenv("INDICCONFORMER_MODEL_PATH", "").strip()
    if env_path:
        # Support repo-relative paths
        if not os.path.isabs(env_path):
            env_path = os.path.join(PROJECT_ROOT, env_path)
        return env_path
    return DEFAULT_CHECKPOINT_PATH


def _resolve_device() -> str:
    env_dev = os.getenv("INDICCONFORMER_DEVICE", "").strip().lower()
    if env_dev:
        return env_dev
    return "cpu"  # Safe default (use INDICCONFORMER_DEVICE=cuda if GPU compute capability is supported)


def _resolve_decoder() -> str:
    env_dec = os.getenv("INDICCONFORMER_DECODER", "").strip().lower()
    if env_dec in ("ctc", "rnnt"):
        return env_dec
    return "ctc"


class IndicConformerSpeechProvider(SpeechProvider):
    """
    Real IndicConformer multilingual ASR provider.

    Runs inference in the dedicated .venv_speech process to avoid
    dependency conflicts with the FastAPI environment. The model is
    loaded once per worker process via subprocess caching.

    Never returns fabricated transcription. If the model fails to load
    or transcription encounters an error, the caller receives a clear
    error rather than fake text.
    """

    def __init__(self):
        self._model_path = _resolve_model_path()
        self._device = _resolve_device()
        self._decoder = _resolve_decoder()
        self._verified = False
        self._available = False
        self._error_reason: Optional[str] = None
        self._verify_setup()

    def _verify_setup(self):
        """Check that the checkpoint and inference environment exist."""
        # 1. Check checkpoint file
        if not os.path.isfile(self._model_path):
            self._error_reason = (
                f"IndicConformer checkpoint not found at: {self._model_path}"
            )
            logger.error(self._error_reason)
            self._verified = True
            return

        file_size = os.path.getsize(self._model_path)
        if file_size < 100_000_000:  # < 100MB is suspiciously small
            self._error_reason = (
                f"IndicConformer checkpoint is suspiciously small "
                f"({file_size} bytes) at: {self._model_path}"
            )
            logger.error(self._error_reason)
            self._verified = True
            return

        # 2. Check speech venv python
        if not os.path.isfile(SPEECH_VENV_PYTHON):
            self._error_reason = (
                f"Speech inference venv python not found: {SPEECH_VENV_PYTHON}. "
                "Run scripts/setup_speech_env.ps1 first."
            )
            logger.warning(self._error_reason)
            self._verified = True
            return

        # 3. Check inference script
        if not os.path.isfile(_INFERENCE_SCRIPT):
            self._error_reason = (
                f"Inference script not found: {_INFERENCE_SCRIPT}"
            )
            logger.error(self._error_reason)
            self._verified = True
            return

        logger.info(
            f"IndicConformer provider configured: "
            f"checkpoint={self._model_path} ({file_size / 1e9:.2f} GB), "
            f"device={self._device}, decoder={self._decoder}"
        )
        self._available = True
        self._verified = True

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def error_reason(self) -> Optional[str]:
        return self._error_reason

    async def transcribe(
        self, audio_bytes: bytes, language: str = "hi"
    ) -> TranscriptionResult:
        """
        Transcribe audio using IndicConformer via subprocess inference.

        Args:
            audio_bytes: Raw audio data (WAV preferred, 16kHz mono).
            language: ISO 639-1 language code (e.g. 'gu', 'hi').

        Returns:
            TranscriptionResult with real model output.

        Raises:
            ValueError: For invalid language or audio input.
            RuntimeError: If model is unavailable or inference fails.
        """
        # ── Validate language ────────────────────────────────────────
        lang = (language or "").strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Language '{language}' is not supported by IndicConformer. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )

        # ── Validate audio ───────────────────────────────────────────
        if not audio_bytes or len(audio_bytes) < 100:
            raise ValueError(
                "Audio data is empty or too small to contain speech."
            )

        if len(audio_bytes) > MAX_AUDIO_SIZE:
            raise ValueError(
                f"Audio file exceeds the {MAX_AUDIO_SIZE / (1024*1024):.0f} MB "
                f"size limit ({len(audio_bytes) / (1024*1024):.1f} MB received)."
            )

        # ── Check model availability ─────────────────────────────────
        if not self._available:
            raise RuntimeError(
                f"IndicConformer model is not available: {self._error_reason}"
            )

        # ── Write audio to temp file and run inference ───────────────
        tmp_audio = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, dir=tempfile.gettempdir()
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_audio = tmp.name

            start_time = time.monotonic()

            result = await self._run_inference_subprocess(
                tmp_audio, lang
            )

            elapsed = time.monotonic() - start_time
            logger.info(
                f"IndicConformer transcription completed: "
                f"lang={lang}, decoder={self._decoder}, "
                f"elapsed={elapsed:.2f}s, "
                f"transcript_len={len(result.get('transcript', ''))}"
            )

            transcript = result.get("transcript", "").strip()
            if not transcript:
                raise RuntimeError(
                    "IndicConformer returned empty transcription. "
                    "The audio may not contain recognizable speech."
                )

            # ── Clinical grounding ───────────────────────────────────
            grounding = self._ground_transcript(transcript, lang)

            return TranscriptionResult(
                transcript=transcript,
                language=lang,
                confidence=result.get("confidence", 0.0),
                detected_language=lang,
                provider=f"indicconformer_{self._decoder}",
                clinical_grounding=grounding,
            )

        finally:
            if tmp_audio and os.path.exists(tmp_audio):
                try:
                    os.remove(tmp_audio)
                except Exception:
                    pass

    async def _run_inference_subprocess(
        self, audio_path: str, lang: str
    ) -> Dict[str, Any]:
        """
        Run inference in the speech venv subprocess.
        Returns parsed JSON dict with transcript and confidence.
        """
        import asyncio
        import json

        cmd = [
            SPEECH_VENV_PYTHON,
            _INFERENCE_SCRIPT,
            "--model", self._model_path,
            "--audio", audio_path,
            "--language", lang,
            "--decoder", self._decoder,
            "--device", self._device,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=PROJECT_ROOT,
            )

            # Timeout: configurable via SPEECH_INFERENCE_TIMEOUT_SECONDS
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=INFERENCE_TIMEOUT_SECONDS
            )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                # Log stderr but don't expose raw paths to client
                logger.error(
                    f"IndicConformer inference failed (exit={proc.returncode}): "
                    f"{stderr_text[:500]}"
                )
                raise RuntimeError(
                    "Speech recognition inference failed. "
                    "Please try again or check the model configuration."
                )

            # Parse JSON output from inference script (find JSON line from output)
            for line in reversed(stdout_text.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue

            try:
                result = json.loads(stdout_text)
                return result
            except json.JSONDecodeError:
                logger.error(
                    f"Failed to parse inference output: {stdout_text[:300]}"
                )
                raise RuntimeError(
                    "Failed to parse speech recognition output."
                )

        except asyncio.TimeoutError:
            raise RuntimeError(
                "Speech recognition timed out. The audio may be too long."
            )
        except FileNotFoundError:
            self._available = False
            self._error_reason = (
                f"Speech inference environment not found: {SPEECH_VENV_PYTHON}"
            )
            raise RuntimeError(self._error_reason)

    def _ground_transcript(
        self, text: str, language: str
    ) -> Optional[Dict[str, Any]]:
        """Match transcribed text against the Indic clinical lexicon."""
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
                terms = (
                    c_val.get("en", [])
                    + c_val.get("hi", [])
                    + c_val.get("gu", [])
                )
                if any(t.lower() in text_lower for t in terms):
                    matched.append(
                        {
                            "concept": c_key,
                            "concept_id": c_val.get("concept_id"),
                            "department": c_val.get("department"),
                            "priority": c_val.get("priority"),
                        }
                    )
            if matched:
                return {
                    "matched_concepts": matched,
                    "primary_department": matched[0]["department"],
                    "suggested_priority": matched[0]["priority"],
                }
        except Exception as e:
            logger.warning(f"Could not ground transcript: {e}")
        return None
