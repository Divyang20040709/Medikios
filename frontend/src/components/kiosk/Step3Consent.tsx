'use client';

import React, { useState } from 'react';
import { ShieldCheck, Volume2, VolumeX, CheckSquare, Square, ArrowRight, ArrowLeft, AlertTriangle } from 'lucide-react';
import { ConsentRecord, LanguageCode } from '@/lib/types';
import { clinicalStore, SpeechAssistant } from '@/lib/clinicalStore';
import { t } from '@/lib/i18n';

interface Step3ConsentProps {
  patientId: string;
  patientName: string;
  /** Server encounter id from /api/intake/init (Phase 7: consent is recorded
   *  explicitly here — check-in alone never marks it granted). */
  encounterId?: string;
  language?: LanguageCode;
  onConsentAgreed: (consent: ConsentRecord) => void;
  onBack: () => void;
  /** QA BUG-002: an explicit decline must be recorded server-side and then
   *  handed back to the wizard (which leaves the intake flow). */
  onConsentDeclined: () => void;
}

type DecisionStatus = 'idle' | 'submitting' | 'error' | 'declined';

interface ClauseCardProps {
  title: string;
  body: string;
  checked: boolean;
  onToggle: () => void;
}

/** One consent clause. Keyboard-operable (Space/Enter) and exposes its state
 *  to assistive technology as a real checkbox. */
function ClauseCard({ title, body, checked, onToggle }: ClauseCardProps) {
  return (
    <div
      role="checkbox"
      aria-checked={checked}
      tabIndex={0}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          onToggle();
        }
      }}
      className={`cursor-pointer p-4 rounded-xl border transition-all flex items-start gap-3.5 ${
        checked
          ? 'border-[#6C3FC5]/40 bg-white shadow-2xs'
          : 'border-neutral-200 bg-neutral-50/50'
      }`}
    >
      <div className="mt-0.5 text-[#6C3FC5]">
        {checked ? <CheckSquare className="w-5 h-5" /> : <Square className="w-5 h-5 text-neutral-400" />}
      </div>
      <div className="space-y-0.5">
        <h4 className="font-bold text-xs sm:text-sm text-[#171717]">{title}</h4>
        <p className="text-xs text-[#666666] leading-relaxed">{body}</p>
      </div>
    </div>
  );
}

export function Step3Consent({
  patientId,
  patientName,
  encounterId,
  language = 'en',
  onConsentAgreed,
  onBack,
  onConsentDeclined,
}: Step3ConsentProps) {
  // QA BUG-002: consent is a decision, not a default. Every clause starts
  // UNCHECKED and "Agree & Continue" stays disabled until the patient
  // explicitly accepts all three.
  const [clause1, setClause1] = useState(false);
  const [clause2, setClause2] = useState(false);
  const [clause3, setClause3] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [status, setStatus] = useState<DecisionStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const allAgreed = clause1 && clause2 && clause3;
  const busy = status === 'submitting';

  const toggleAudio = () => {
    if (isPlayingAudio) {
      SpeechAssistant.stopSpeaking();
      setIsPlayingAudio(false);
    } else {
      // Read the consent explanation in the patient's own language.
      SpeechAssistant.speak(t('s3.explText', language), language);
      setIsPlayingAudio(true);
    }
  };

  /** POST the explicit decision to the server. Throws on a transport failure
   *  or any non-2xx response so the caller can never report a false success. */
  const recordDecisionOnServer = async (granted: boolean): Promise<void> => {
    const res = await fetch('/api/intake/consent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        encounter_id: encounterId,
        patient_id: patientId,
        granted,
        audio_consent: granted,
      }),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const payload = await res.json();
        if (payload && payload.detail) {
          detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
        }
      } catch {
        /* keep the status code as the message */
      }
      throw new Error(detail);
    }
  };

  const failOpen = (err: unknown) => {
    setStatus('error');
    setErrorMessage(err instanceof Error ? err.message : String(err));
  };

  const handleAgree = async () => {
    if (!allAgreed || busy) return;
    setErrorMessage(null);

    const record: ConsentRecord = {
      patientId,
      clinicalInfoCollection: clause1,
      documentProcessing: clause2,
      staffSharing: clause3,
      signedAt: new Date().toISOString(),
    };

    // QA BUG-002: the decision is persisted server-side BEFORE the wizard
    // advances. Without a server encounter there is nothing to record, and the
    // local-only notice above already tells the patient that.
    if (encounterId) {
      setStatus('submitting');
      try {
        await recordDecisionOnServer(true);
      } catch (err) {
        failOpen(err);
        return;
      }
    }

    clinicalStore.saveConsent(record);
    SpeechAssistant.stopSpeaking();
    setIsPlayingAudio(false);
    setStatus('idle');
    onConsentAgreed(record);
  };

  const handleDecline = async () => {
    if (busy) return;
    setErrorMessage(null);

    if (encounterId) {
      setStatus('submitting');
      try {
        await recordDecisionOnServer(false);
      } catch (err) {
        failOpen(err);
        return;
      }
    }

    clinicalStore.saveConsent({
      patientId,
      clinicalInfoCollection: false,
      documentProcessing: false,
      staffSharing: false,
      signedAt: new Date().toISOString(),
    });
    SpeechAssistant.stopSpeaking();
    setIsPlayingAudio(false);
    setStatus('declined');
  };

  // Explicit decline confirmation — the intake journey stops here.
  if (status === 'declined') {
    return (
      <div className="max-w-3xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-6 animate-in fade-in duration-150">
        <div className="p-5 sm:p-6 rounded-xl border border-neutral-200 bg-neutral-50 space-y-3">
          <div className="flex items-center gap-2 text-[#171717]">
            <ShieldCheck className="w-5 h-5 text-neutral-500" />
            <h2 className="text-lg sm:text-xl font-serif font-bold">{t('s3.declinedTitle', language)}</h2>
          </div>
          <p className="text-xs sm:text-sm text-[#666666] leading-relaxed">{t('s3.declinedBody', language)}</p>
          {!encounterId && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              {t('s3.localOnly', language)}
            </p>
          )}
        </div>

        <div className="pt-4 border-t border-neutral-200 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setStatus('idle')}
            className="flex items-center justify-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>{t('s3.changeMind', language)}</span>
          </button>
          <button
            type="button"
            onClick={onConsentDeclined}
            className="flex items-center justify-center gap-2 px-7 py-3 rounded-xl text-xs sm:text-sm font-bold bg-neutral-800 hover:bg-neutral-900 text-white shadow-sm transition-colors"
          >
            <span>{t('s3.exit', language)}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            {t('s3.stepLabel', language)}
          </span>
          <span className="flex items-center gap-1 font-mono text-[11px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">
            {t('s3.dpdpBadge', language)}
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('s3.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('s3.patientLine', language)} <strong className="text-[#171717]">{patientName}</strong> ({patientId})
        </p>
      </div>

      {/* Explanation Banner */}
      <div className="p-4 sm:p-5 rounded-xl bg-[#F3EEFC]/60 border border-[#6C3FC5]/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 font-bold text-xs sm:text-sm text-[#171717]">
            <ShieldCheck className="w-4 h-4 text-[#6C3FC5]" />
            <span>{t('s3.audioTitle', language)}</span>
          </div>
          <p className="text-xs text-[#666666] leading-relaxed max-w-xl">
            {t('s3.explText', language)}
          </p>
        </div>

        <button
          type="button"
          onClick={toggleAudio}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold border transition-colors flex-shrink-0 ${
            isPlayingAudio
              ? 'bg-[#6C3FC5] text-white border-[#6C3FC5]'
              : 'bg-white text-[#6C3FC5] border-[#6C3FC5]/30 hover:bg-[#F3EEFC]'
          }`}
        >
          {isPlayingAudio ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          <span>{isPlayingAudio ? t('s3.stopAudio', language) : t('s3.playAudio', language)}</span>
        </button>
      </div>

      {/* No server session: be honest that this decision cannot be recorded. */}
      {!encounterId && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-[11px] sm:text-xs text-amber-800">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>{t('s3.localOnly', language)}</span>
        </div>
      )}

      {/* Recording failed: show the API failure, keep the patient on the step. */}
      {status === 'error' && errorMessage && (
        <div
          role="alert"
          className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-[11px] sm:text-xs text-red-800"
        >
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            {t('s3.recordError', language)} <span className="font-mono">({errorMessage})</span>
          </span>
        </div>
      )}

      {/* 3 Clauses */}
      <div className="space-y-3">
        <ClauseCard
          title={t('s3.c1Title', language)}
          body={t('s3.c1Text', language)}
          checked={clause1}
          onToggle={() => setClause1(!clause1)}
        />
        <ClauseCard
          title={t('s3.c2Title', language)}
          body={t('s3.c2Text', language)}
          checked={clause2}
          onToggle={() => setClause2(!clause2)}
        />
        <ClauseCard
          title={t('s3.c3Title', language)}
          body={t('s3.c3Text', language)}
          checked={clause3}
          onToggle={() => setClause3(!clause3)}
        />
      </div>

      {!allAgreed && (
        <p className="text-[11px] font-semibold text-[#6C3FC5] -mt-3">{t('s3.needAll', language)}</p>
      )}

      <div className="text-[11px] text-[#666666]">
        {t('s3.revokeNote', language)}
      </div>

      {/* Buttons */}
      <div className="pt-4 border-t border-neutral-200 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          disabled={busy}
          className="flex items-center justify-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors disabled:opacity-50"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('s3.back', language)}</span>
        </button>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* QA BUG-002: an equal, clearly visible way to refuse. */}
          <button
            type="button"
            onClick={handleDecline}
            disabled={busy}
            className="flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs sm:text-sm font-bold border border-neutral-300 text-neutral-700 hover:bg-neutral-100 transition-colors disabled:opacity-50"
          >
            <span>{busy ? t('s3.submitting', language) : t('s3.decline', language)}</span>
          </button>

          <button
            type="button"
            disabled={!allAgreed || busy}
            onClick={handleAgree}
            className={`flex items-center justify-center gap-2 px-7 py-3 rounded-xl text-xs sm:text-sm font-bold transition-all ${
              allAgreed && !busy
                ? 'bg-[#6C3FC5] hover:bg-[#4B238C] text-white shadow-sm hover:shadow-md active:scale-[0.99]'
                : 'bg-neutral-200 text-neutral-400 cursor-not-allowed'
            }`}
          >
            <span>{busy ? t('s3.submitting', language) : t('s3.agree', language)}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
