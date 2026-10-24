'use client';

/**
 * VoiceDictationPanel — patient-facing speech-to-text with a review step.
 * ────────────────────────────────────────────────────────────────────────
 * Flow: record (browser Web Speech when supported, otherwise microphone
 * recording uploaded to the free local backend ASR at /api/speech/transcribe)
 * → transcript shown in an EDITABLE box → patient explicitly confirms with
 * "Use this text" before it is applied to the interview field.
 *
 * Gracefully handles: permission denial, missing microphone, unsupported
 * browser, too-short audio, oversized uploads, ASR service unavailability
 * and network failures — always leaving keyboard typing as the fallback.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Loader2, Check, X, RefreshCw, AlertTriangle } from 'lucide-react';
import { LanguageCode } from '@/lib/types';
import { SpeechAssistant } from '@/lib/clinicalStore';
import { AudioRecorder, transcribeAudioBlob } from '@/lib/audioRecorder';
import { t } from '@/lib/i18n';

type PanelPhase =
  | 'idle'          // ready to start
  | 'requesting'    // waiting for microphone permission
  | 'recording'     // capturing audio
  | 'transcribing'  // uploaded / finalising, waiting for text
  | 'review'        // transcript shown, patient edits/confirms
  | 'error';        // recoverable problem with patient-friendly message

interface VoiceDictationPanelProps {
  /** Language the patient is speaking (interview language, not UI language). */
  speechLanguage: LanguageCode;
  /** UI language used for all labels in this panel. */
  language: LanguageCode;
  /** Called ONLY after the patient confirms the reviewed transcript. */
  onApply: (text: string) => void;
  /** Optional cancel button callback (parent decides whether to hide panel). */
  onClose?: () => void;
  /** Max recording length in seconds for the backend recording mode. */
  maxDurationSeconds?: number;
}

const MAX_UPLOAD_MB = 15;

export function VoiceDictationPanel({
  speechLanguage,
  language,
  onApply,
  onClose,
  maxDurationSeconds = 45,
}: VoiceDictationPanelProps) {
  const [phase, setPhase] = useState<PanelPhase>('idle');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [draftText, setDraftText] = useState<string>('');
  const [confidence, setConfidence] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState<number>(0);
  const [volume, setVolume] = useState<number>(0);

  const recorderRef = useRef<AudioRecorder | null>(null);
  const stopWebSpeechRef = useRef<(() => void) | null>(null);
  // Web Speech API exists only in some browsers; MediaRecorder is the
  // universal fallback that routes audio to the local backend ASR.
  const browserSpeechSupported =
    typeof window !== 'undefined' && SpeechAssistant.isSpeechRecognitionSupported();

  useEffect(() => {
    return () => {
      // Never leave the microphone held when the component unmounts.
      recorderRef.current?.cancel();
      recorderRef.current = null;
      stopWebSpeechRef.current?.();
      stopWebSpeechRef.current = null;
    };
  }, []);

  const resetToIdle = () => {
    setPhase('idle');
    setErrorMessage('');
    setDraftText('');
    setConfidence(null);
    setElapsed(0);
    setVolume(0);
  };

  const startBrowserDictation = async () => {
    setPhase('requesting');
    let started = false;
    const stopFn = SpeechAssistant.startListening(
      speechLanguage,
      (transcript) => {
        // Route browser-dictated text through the SAME review step.
        setDraftText(transcript);
        setConfidence(null);
        setPhase('review');
        stopWebSpeechRef.current?.();
        stopWebSpeechRef.current = null;
      },
      (err: any) => {
        started = false;
        const name = err?.error || err?.name || '';
        if (name === 'not-allowed' || name === 'service-not-allowed') {
          setErrorMessage(t('vc.errPermission', language));
        } else if (name === 'no-speech' || name === 'audio-capture') {
          setErrorMessage(t('vc.errNoMic', language));
        } else {
          setErrorMessage(t('vc.errTranscribe', language));
        }
        setPhase('error');
        stopWebSpeechRef.current = null;
      }
    );
    stopWebSpeechRef.current = stopFn;
    started = true;
    // Small tick so the 'requesting' state renders before permission prompt resolves.
    await Promise.resolve();
    if (started && stopWebSpeechRef.current) setPhase('recording');
  };

  const startBackendRecording = async () => {
    setPhase('requesting');
    const recorder = new AudioRecorder({
      maxDurationSeconds,
      onTimeUpdate: (sec) => setElapsed(sec),
      onVolumeChange: (v) => setVolume(v),
      onMaxDurationReached: () => {
        // Auto-stop handled below via stopAndTranscribe; guard double-call.
      },
    });
    recorderRef.current = recorder;
    try {
      await recorder.start();
      setPhase('recording');
    } catch (err: any) {
      recorderRef.current = null;
      const msg: string = err?.message || '';
      if (msg.toLowerCase().includes('permission') || msg.toLowerCase().includes('denied')) {
        setErrorMessage(t('vc.errPermission', language));
      } else if (msg.toLowerCase().includes('no microphone')) {
        setErrorMessage(t('vc.errNoMic', language));
      } else {
        setErrorMessage(msg || t('vc.errTranscribe', language));
      }
      setPhase('error');
    }
  };

  const startRecording = () => {
    if (browserSpeechSupported) {
      startBrowserDictation().catch(() => setErrorMessage(t('vc.errTranscribe', language)));
    } else {
      startBackendRecording().catch(() => setErrorMessage(t('vc.errTranscribe', language)));
    }
  };

  const stopAndTranscribe = async () => {
    if (browserSpeechSupported && stopWebSpeechRef.current) {
      // Browser engine finalises asynchronously via its result callback.
      stopWebSpeechRef.current();
      setPhase('transcribing');
      return;
    }
    const recorder = recorderRef.current;
    if (!recorder) {
      resetToIdle();
      return;
    }
    recorderRef.current = null;
    setPhase('transcribing');
    try {
      const blob = await recorder.stop();
      if (blob.size > MAX_UPLOAD_MB * 1024 * 1024) {
        setErrorMessage(t('vc.errTranscribe', language));
        setPhase('error');
        return;
      }
      if (blob.size < 2000) {
        // Almost certainly silence / accidental tap.
        setErrorMessage(t('vc.errTranscribe', language));
        setPhase('error');
        return;
      }
      const result = await transcribeAudioBlob(blob, speechLanguage);
      const text = (result.transcript || '').trim();
      if (!text) {
        setErrorMessage(t('vc.errTranscribe', language));
        setPhase('error');
        return;
      }
      setDraftText(text);
      setConfidence(typeof result.confidence === 'number' ? result.confidence : null);
      setPhase('review');
    } catch (err: any) {
      const msg: string = err?.message || '';
      const lower = msg.toLowerCase();
      if (lower.includes('permission') || lower.includes('denied')) {
        setErrorMessage(t('vc.errPermission', language));
      } else if (lower.includes('no microphone')) {
        setErrorMessage(t('vc.errNoMic', language));
      } else if (
        lower.includes('unavailable') ||
        lower.includes('empty or too short') ||
        lower.includes('exceeds') ||
        lower.includes('failed')
      ) {
        // 503 / 400 / 413 from the local ASR pipeline — honest, recoverable.
        setErrorMessage(t('vc.errTranscribe', language));
      } else {
        setErrorMessage(msg || t('vc.errTranscribe', language));
      }
      setPhase('error');
    }
  };

  const cancelRecording = () => {
    if (browserSpeechSupported && stopWebSpeechRef.current) {
      stopWebSpeechRef.current();
      stopWebSpeechRef.current = null;
    }
    recorderRef.current?.cancel();
    recorderRef.current = null;
    resetToIdle();
    onClose?.();
  };

  const applyText = () => {
    const text = draftText.trim();
    if (!text) {
      setErrorMessage(t('vc.errTranscribe', language));
      setPhase('error');
      return;
    }
    onApply(text);
    resetToIdle();
    onClose?.();
  };

  const isBusy = phase === 'requesting' || phase === 'recording' || phase === 'transcribing';

  return (
    <div className="rounded-xl border border-[#6C3FC5]/25 bg-[#FBF9FE] p-4 space-y-3 animate-in fade-in slide-in-from-top-1 duration-150">
      {/* ── Control row ─────────────────────────────────────────────── */}
      {phase !== 'review' && (
        <div className="flex flex-wrap items-center gap-2">
          {phase !== 'recording' ? (
            <button
              type="button"
              onClick={startRecording}
              disabled={isBusy}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold bg-[#6C3FC5] text-white hover:bg-[#5a34ab] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {phase === 'requesting' || phase === 'transcribing' ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Mic className="w-3.5 h-3.5" />
              )}
              <span>
                {phase === 'requesting'
                  ? t('vc.listening', language)
                  : phase === 'transcribing'
                    ? t('vc.transcribing', language)
                    : t('vc.record', language)}
              </span>
            </button>
          ) : (
            <button
              type="button"
              onClick={stopAndTranscribe}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold bg-red-600 text-white hover:bg-red-700 transition-colors animate-pulse"
            >
              <MicOff className="w-3.5 h-3.5" />
              <span>
                {t('vc.stop', language)}
                {!browserSpeechSupported && ` · ${elapsed}s`}
              </span>
            </button>
          )}

          {/* Live volume meter while recording via backend mode */}
          {phase === 'recording' && !browserSpeechSupported && (
            <div className="flex items-center gap-1 flex-1 min-w-[80px] max-w-[160px] h-2 bg-neutral-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-[#6C3FC5] transition-[width] duration-150 rounded-full"
                style={{ width: `${Math.round(Math.min(1, volume) * 100)}%` }}
              />
            </div>
          )}

          {phase !== 'idle' && (
            <button
              type="button"
              onClick={cancelRecording}
              className="flex items-center gap-1 px-2.5 py-2 rounded-lg text-xs font-semibold text-[#666666] hover:bg-neutral-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              <span>{t('vc.cancel', language)}</span>
            </button>
          )}
        </div>
      )}

      {/* ── Error row (permission / no mic / transcription failure) ──── */}
      {phase === 'error' && (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-300 px-3 py-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="space-y-2 flex-1">
            <p className="text-xs font-semibold text-amber-800 leading-snug">{errorMessage}</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={startRecording}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-bold bg-amber-600 text-white hover:bg-amber-700 transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                <span>{t('vc.rerecord', language)}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Review step: editable transcript, confirm before submission ─ */}
      {phase === 'review' && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#6C3FC5]">
              {t('vc.reviewTitle', language)}
            </span>
            {confidence !== null && (
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  confidence >= 0.75
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-amber-100 text-amber-800'
                }`}
                title={t('vc.confidence', language)}
              >
                {t('vc.confidence', language)}: {Math.round(confidence * 100)}%
              </span>
            )}
          </div>
          <p className="text-[11px] text-[#666666]">{t('vc.reviewHelp', language)}</p>
          <textarea
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={2}
            dir="auto"
            className="w-full px-3 py-2 bg-white border border-[#6C3FC5]/30 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:ring-1 focus:ring-[#6C3FC5] focus:outline-none resize-y"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={applyText}
              disabled={!draftText.trim()}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold bg-[#6C3FC5] text-white hover:bg-[#5a34ab] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Check className="w-3.5 h-3.5" />
              <span>{t('vc.useText', language)}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                resetToIdle();
                startRecording();
              }}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-neutral-100 text-[#171717] hover:bg-neutral-200 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>{t('vc.rerecord', language)}</span>
            </button>
            <button
              type="button"
              onClick={cancelRecording}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold text-[#666666] hover:bg-neutral-200 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              <span>{t('vc.cancel', language)}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
