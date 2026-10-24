'use client';

import React, { useState } from 'react';
import { Sparkles, RefreshCw, AlertTriangle, Loader2 } from 'lucide-react';
import { LanguageCode } from '@/lib/types';
import { t } from '@/lib/i18n';

/**
 * Phase 3 — Local LLM follow-up questions.
 * Sends the patient's current interview answers to /api/intake/followup-questions;
 * the backend generates patient-friendly follow-ups with a free local model
 * (Ollama / LM Studio) and falls back to predefined guideline questions when
 * the model is offline. Red-flag escalation comes from the deterministic
 * rules engine and is displayed here verbatim — the LLM can never hide it.
 */

export interface FollowupStatement {
  question_text: string;
  answer_text: string;
  section_id?: string;
}

export interface FollowupAnswer {
  question_text: string;
  answer_text: string;
}

interface GeneratedQuestion {
  text: string;
  section: string;
  provenance: string; // local_ai | guideline
}

interface RedFlagInfo {
  title: string;
  priority: string;
  description: string;
}

interface FollowUpQuestionsProps {
  sessionId?: string | null;
  language: LanguageCode;        // UI language
  interviewLanguage: LanguageCode; // language questions are generated in
  statements: FollowupStatement[]; // answers collected so far (context)
  onAnswersChange: (answers: FollowupAnswer[]) => void;
}

export function FollowUpQuestions({
  sessionId,
  language,
  interviewLanguage,
  statements,
  onAnswersChange,
}: FollowUpQuestionsProps) {
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([]);
  const [source, setSource] = useState<string>('');
  const [redFlags, setRedFlags] = useState<RedFlagInfo[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});

  const hasContext = statements.some((s) => (s.answer_text || '').trim().length > 0);

  const notifyParent = (next: Record<number, string>, qs: GeneratedQuestion[]) => {
    onAnswersChange(
      qs
        .map((q, i) => ({ question_text: q.text, answer_text: (next[i] || '').trim() }))
        .filter((a) => a.answer_text.length > 0)
    );
  };

  const generate = async () => {
    setPhase('loading');
    try {
      const res = await fetch('/api/intake/followup-questions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId || null,
          language: interviewLanguage,
          max_questions: 3,
          answers: statements.filter((s) => (s.answer_text || '').trim().length > 0),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const qs: GeneratedQuestion[] = data.questions || [];
      setQuestions(qs);
      setSource(data.source || '');
      setRedFlags(data.red_flags || []);
      setAnswers({});
      notifyParent({}, qs);
      setPhase('ready');
    } catch (err) {
      console.warn('Follow-up generation request failed:', err);
      setPhase('error');
    }
  };

  const handleAnswer = (idx: number, value: string) => {
    const next = { ...answers, [idx]: value };
    setAnswers(next);
    notifyParent(next, questions);
  };

  return (
    <div className="p-5 sm:p-6 rounded-2xl border border-neutral-200 bg-white space-y-4 shadow-xs">
      <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
        <h3 className="font-bold text-sm sm:text-base text-[#171717] flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#6C3FC5]" />
          {t('fq.title', language)}
        </h3>
        {phase === 'ready' && source && (
          <span className="text-[11px] font-semibold text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded">
            {source === 'local_llm' ? t('fq.srcLocalAI', language) : t('fq.srcGuideline', language)}
          </span>
        )}
      </div>

      <p className="text-[11px] sm:text-xs text-[#666666]">{t('fq.sub', language)}</p>

      {/* Deterministic red-flag escalation — rendered from backend rules,
          never from model output, so it can't be suppressed. */}
      {redFlags.length > 0 && (
        <div className="p-3 rounded-xl bg-red-50 border-2 border-red-300 text-red-900 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="text-xs font-bold uppercase tracking-wider text-red-700">
              {t('fq.escalationTitle', language)}
            </span>
            {redFlags.map((rf, i) => (
              <p key={i} className="text-xs font-semibold leading-snug">
                {rf.title} — {rf.description}
              </p>
            ))}
          </div>
        </div>
      )}

      {phase === 'idle' || phase === 'error' ? (
        <div className="space-y-2">
          <button
            type="button"
            onClick={generate}
            disabled={!hasContext}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-2.5 bg-[#6C3FC5] hover:bg-[#4B238C] disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl text-xs font-bold transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            <span>{t('fq.generate', language)}</span>
          </button>
          {!hasContext && (
            <p className="text-[11px] text-[#666666]">{t('fq.needContext', language)}</p>
          )}
          {phase === 'error' && (
            <p className="text-[11px] font-semibold text-red-600">{t('fq.err', language)}</p>
          )}
        </div>
      ) : null}

      {phase === 'loading' && (
        <div className="flex items-center gap-2 text-xs text-[#666666] py-2">
          <Loader2 className="w-4 h-4 animate-spin text-[#6C3FC5]" />
          <span>{t('fq.generating', language)}</span>
        </div>
      )}

      {phase === 'ready' && (
        <div className="space-y-4">
          {questions.map((q, i) => (
            <div key={i} className="space-y-1.5">
              <label className="text-xs font-bold text-[#171717] flex items-start gap-2">
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 ${
                    q.provenance === 'local_ai'
                      ? 'bg-[#F3EEFC] text-[#6C3FC5]'
                      : 'bg-neutral-100 text-[#666666]'
                  }`}
                >
                  {q.provenance === 'local_ai'
                    ? t('fq.srcLocalAI', language)
                    : t('fq.srcGuideline', language)}
                </span>
                <span>{q.text}</span>
              </label>
              <input
                type="text"
                value={answers[i] || ''}
                onChange={(e) => handleAnswer(i, e.target.value)}
                placeholder={t('fq.answerPlaceholder', language)}
                className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>
          ))}

          <button
            type="button"
            onClick={generate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold text-[#6C3FC5] bg-[#F3EEFC] hover:bg-[#6C3FC5] hover:text-white transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>{t('fq.regenerate', language)}</span>
          </button>
        </div>
      )}
    </div>
  );
}
