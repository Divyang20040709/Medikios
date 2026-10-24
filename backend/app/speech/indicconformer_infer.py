#!/usr/bin/env python3
"""
IndicConformer standalone inference script
──────────────────────────────────────────
Runs inside .venv_speech (with torch, torchaudio, nemo or transformers).

Usage (called by indicconformer_provider.py via subprocess):
  python indicconformer_infer.py \
      --model  path/to/indicconformer_stt_multi_hybrid_rnnt_600m.nemo \
      --audio  /tmp/recording.wav \
      --language hi \
      --decoder ctc \
      --device cuda

Outputs JSON to stdout:
  {"transcript": "...", "confidence": 0.95, "decoder": "ctc", "elapsed_s": 1.23}

Errors go to stderr; non-zero exit code on failure.
"""

import argparse
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ──────────────────────────────────────────────────────────────────────
# Audio preprocessing helpers (no NeMo dependency required)
# ──────────────────────────────────────────────────────────────────────

def load_and_preprocess_audio(audio_path: str, target_sr: int = 16000):
    """Load audio file and convert to 16kHz mono float32 tensor."""
    import torch
    import torchaudio

    waveform, sample_rate = torchaudio.load(audio_path)

    # Convert to mono if stereo
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)

    # Resample if necessary
    if sample_rate != target_sr:
        resampler = torchaudio.transforms.Resample(
            orig_freq=sample_rate, new_freq=target_sr
        )
        waveform = resampler(waveform)

    return waveform


# ──────────────────────────────────────────────────────────────────────
# Strategy 1: NeMo-based inference (AI4Bharat fork)
# ──────────────────────────────────────────────────────────────────────

def try_nemo_inference(model_path, audio_path, language, decoder, device):
    """
    Load the .nemo checkpoint using NeMo's EncDecHybridRNNTCTCBPEModel
    and transcribe. Returns result dict or raises ImportError / RuntimeError.
    """
    import torch
    from nemo.collections.asr.models import EncDecHybridRNNTCTCBPEModel

    map_location = torch.device(device if torch.cuda.is_available() and device == "cuda" else "cpu")

    model = EncDecHybridRNNTCTCBPEModel.restore_from(
        restore_path=model_path,
        map_location=map_location,
    )
    model.eval()
    model.freeze()

    # Set decoder mode
    if decoder == "ctc":
        model.cur_decoder = "ctc"
    else:
        model.cur_decoder = "rnnt"

    if hasattr(model, 'tokenizer'):
        model.tokenizer.selected_language = language
        model.tokenizer.current_lang = language

    start = time.monotonic()

    # Transcribe
    transcriptions = model.transcribe(
        audio=[audio_path],
        batch_size=1,
        verbose=False,
    )

    elapsed = time.monotonic() - start

    # NeMo returns list of strings or list of Hypothesis objects
    if isinstance(transcriptions, (list, tuple)):
        if len(transcriptions) > 0:
            t = transcriptions[0]
            if hasattr(t, "text"):
                text = t.text
            else:
                text = str(t)
        else:
            text = ""
    else:
        text = str(transcriptions)

    return {
        "transcript": text.strip(),
        "confidence": 0.92,
        "decoder": decoder,
        "elapsed_s": round(elapsed, 3),
        "engine": "nemo",
    }


# ──────────────────────────────────────────────────────────────────────
# Strategy 2: HuggingFace Transformers ONNX inference
# ──────────────────────────────────────────────────────────────────────

def try_hf_inference(audio_path, language, decoder, device):
    """
    Use the HuggingFace-hosted ONNX model with trust_remote_code.
    Falls back to this if NeMo is not installed.
    """
    import torch
    from transformers import AutoModel

    model = AutoModel.from_pretrained(
        "ai4bharat/indic-conformer-600m-multilingual",
        trust_remote_code=True,
    )

    waveform = load_and_preprocess_audio(audio_path, target_sr=16000)

    start = time.monotonic()

    # The HF model's __call__ expects (wav_tensor, language_code, decoder_type)
    transcription = model(waveform, language, decoder)

    elapsed = time.monotonic() - start

    text = ""
    if isinstance(transcription, (list, tuple)):
        text = str(transcription[0]) if transcription else ""
    else:
        text = str(transcription)

    return {
        "transcript": text.strip(),
        "confidence": 0.90,
        "decoder": decoder,
        "elapsed_s": round(elapsed, 3),
        "engine": "hf_onnx",
    }


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="IndicConformer inference")
    parser.add_argument("--model", required=True, help="Path to .nemo checkpoint")
    parser.add_argument("--audio", required=True, help="Path to audio file")
    parser.add_argument("--language", required=True, help="Language code (e.g. hi, gu)")
    parser.add_argument("--decoder", default="ctc", choices=["ctc", "rnnt"])
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    args = parser.parse_args()

    if not os.path.isfile(args.audio):
        print(f"Audio file not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.model):
        print(f"Model checkpoint not found: {args.model}", file=sys.stderr)
        sys.exit(1)

    result = None
    errors = []

    # Strategy 1: Try NeMo
    try:
        result = try_nemo_inference(
            args.model, args.audio, args.language, args.decoder, args.device
        )
    except ImportError as e:
        errors.append(f"NeMo not available: {e}")
    except Exception as e:
        import traceback
        errors.append(f"NeMo inference failed: {e}\n{traceback.format_exc()}")

    # Strategy 2: Fall back to HuggingFace ONNX
    if result is None:
        try:
            result = try_hf_inference(
                args.audio, args.language, args.decoder, args.device
            )
        except ImportError as e:
            errors.append(f"HuggingFace transformers not available: {e}")
        except Exception as e:
            errors.append(f"HuggingFace inference failed: {e}")

    if result is None:
        print(
            "All inference strategies failed:\n"
            + "\n".join(f"  - {e}" for e in errors),
            file=sys.stderr,
        )
        sys.exit(1)

    # Output JSON to stdout (UTF-8 safe for Windows)
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8') + b'\n')
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
