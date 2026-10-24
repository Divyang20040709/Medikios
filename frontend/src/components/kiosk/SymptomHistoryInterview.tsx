'use client';

import React, { useState, useEffect } from 'react';
import {
  Mic,
  MicOff,
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  Check,
  Plus,
  Trash2,
  PhoneCall,
  Sparkles,
  HelpCircle
} from 'lucide-react';
import { Patient, ClinicalCase, LanguageCode, SocratesData, PastCondition, Medication, Allergy } from '@/lib/types';
import { clinicalStore, ClinicalRulesEngine } from '@/lib/clinicalStore';
import { t, chipLabel } from '@/lib/i18n';
import { VoiceDictationPanel } from '@/components/kiosk/VoiceDictationPanel';
import { FollowUpQuestions, FollowupAnswer, FollowupStatement } from '@/components/kiosk/FollowUpQuestions';
import { NotificationModal } from '@/components/common/NotificationModal';

interface SymptomHistoryInterviewProps {
  patient: Patient;
  existingCase?: ClinicalCase;
  language?: LanguageCode;
  speechLanguage?: LanguageCode;
  onCompleteHistory: (clinicalCase: ClinicalCase) => void;
  onBack: () => void;
}

export function SymptomHistoryInterview({
  patient,
  existingCase,
  language = 'en',
  speechLanguage,
  onCompleteHistory,
  onBack,
}: SymptomHistoryInterviewProps) {
  // Voice/interview language is decoupled from the UI language: changing the
  // interface language mid-interview must not switch the transcription locale.
  const interviewLanguage = speechLanguage ?? language;

  // QA BUG-004: in-progress answers are autosaved to a per-patient draft so
  // navigating Back (which unmounts this step) or refreshing does not discard
  // them. The draft is hydrated through lazy state initializers — an effect
  // would race the autosave under React StrictMode dev double-mounting — and
  // takes precedence over the last completed case because it is more recent.
  const draftKey = `medikiosk_interview_draft_${patient.id}`;
  const [draft] = useState(() => {
    if (typeof window === 'undefined') return null;
    try {
      const raw = window.localStorage.getItem(draftKey);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  // 1. Chief Complaint — starts EMPTY; never prefills fabricated clinical data.
  const [chiefComplaint, setChiefComplaint] = useState(
    draft?.chiefComplaint ?? existingCase?.chiefComplaints?.[0]?.complaint ?? ''
  );
  const [duration, setDuration] = useState(
    draft?.duration ?? existingCase?.chiefComplaints?.[0]?.duration ?? ''
  );
  const [severityScore, setSeverityScore] = useState(
    draft?.severityScore ?? existingCase?.socrates?.severityScore ?? 5
  );

  // Voice dictation — record → review/edit → apply flow (see VoiceDictationPanel).
  const [showVoicePanel, setShowVoicePanel] = useState(false);
  const [chiefVoiceTranscript, setChiefVoiceTranscript] = useState<string | null>(null);

  // Phase 3 — local-LLM follow-up questions (patient answers merged into save).
  const [followupAnswers, setFollowupAnswers] = useState<FollowupAnswer[]>([]);

  // 2. SOCRATES Details — only patient-entered answers, no demo prefills.
  const [site, setSite] = useState(draft?.site ?? existingCase?.socrates?.site ?? '');
  const [onset, setOnset] = useState(draft?.onset ?? existingCase?.socrates?.onset ?? '');
  const [character, setCharacter] = useState(draft?.character ?? existingCase?.socrates?.character ?? '');
  const [radiation, setRadiation] = useState(draft?.radiation ?? existingCase?.socrates?.radiation ?? '');
  const [associations, setAssociations] = useState<string[]>(
    Array.isArray(draft?.associations) ? draft.associations : existingCase?.socrates?.associations || []
  );
  const [timing, setTiming] = useState(draft?.timing ?? existingCase?.socrates?.timing ?? '');
  const [exacerbating, setExacerbating] = useState(draft?.exacerbating ?? existingCase?.socrates?.exacerbatingFactors ?? '');
  const [relieving, setRelieving] = useState(draft?.relieving ?? existingCase?.socrates?.relievingFactors ?? '');

  // 3. Past History
  const [pastConditions, setPastConditions] = useState<PastCondition[]>(
    Array.isArray(draft?.pastConditions) ? draft.pastConditions : existingCase?.pastMedicalHistory || []
  );
  const [newConditionInput, setNewConditionInput] = useState('');

  // 4. Medications
  const [medications, setMedications] = useState<Medication[]>(
    Array.isArray(draft?.medications) ? draft.medications : existingCase?.medications || []
  );
  const [newMedName, setNewMedName] = useState('');
  const [newMedDose, setNewMedDose] = useState('');

  // 5. Red Flag State
  const [redFlagInfo, setRedFlagInfo] = useState<{ hasRedFlag: boolean; reason?: string }>({ hasRedFlag: false });
  const [triageAlertSent, setTriageAlertSent] = useState(false);
  // Acknowledgement dialog for the "Notify Triage Staff" action (replaces alert()).
  const [notifyModalOpen, setNotifyModalOpen] = useState(false);

  // Check red flags whenever inputs change
  useEffect(() => {
    const check = ClinicalRulesEngine.checkRedFlags(chiefComplaint, {
      radiation,
      associations,
      site,
      severityScore,
    });
    setRedFlagInfo(check);
    if (check.hasRedFlag && !triageAlertSent) {
      clinicalStore.triggerRedFlag(patient, check.reason || 'Clinical red flag detected');
    }
  }, [chiefComplaint, radiation, associations, site, severityScore]);

  // QA BUG-004 autosave: initial state is already draft-hydrated, so writing
  // on every change (including the first) can never clobber the draft.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        draftKey,
        JSON.stringify({
          chiefComplaint, duration, severityScore, site, onset, character,
          radiation, timing, exacerbating, relieving, associations,
          pastConditions, medications,
        })
      );
    } catch {
      /* storage unavailable - draft is best-effort only */
    }
  }, [chiefComplaint, duration, severityScore, site, onset, character, radiation,
      timing, exacerbating, relieving, associations, pastConditions, medications, draftKey]);

  // Voice dictation is handled by VoiceDictationPanel (browser Web Speech
  // when available, otherwise microphone upload to the local backend ASR).

  const commonComplaints = [
    'Chest discomfort and tightness',
    'Severe Abdominal Pain',
    'Fever & High Body Temperature',
    'Joint Pain & Morning Stiffness',
    'Shortness of breath on exertion',
    'Persistent Cough with phlegm'
  ];

  const handleAddCondition = () => {
    if (!newConditionInput.trim()) return;
    setPastConditions([
      ...pastConditions,
      {
        id: `pmh-${Date.now()}`,
        condition: newConditionInput.trim(),
        diagnosedYear: '2023',
        status: 'active'
      }
    ]);
    setNewConditionInput('');
  };

  const handleAddMedication = () => {
    if (!newMedName.trim()) return;
    setMedications([
      ...medications,
      {
        id: `med-${Date.now()}`,
        name: newMedName.trim(),
        dose: newMedDose.trim() || 'Standard Dose',
        frequency: 'Daily'
      }
    ]);
    setNewMedName('');
    setNewMedDose('');
  };

  const toggleAssociation = (item: string) => {
    if (associations.includes(item)) {
      setAssociations(associations.filter(a => a !== item));
    } else {
      setAssociations([...associations, item]);
    }
  };

  // Context sent to the follow-up generator: the answers collected so far,
  // in the SAME shape the intake router expects ({question_text, answer_text}).
  const followupContext: FollowupStatement[] = [
    chiefComplaint.trim() && {
      question_text: 'Chief complaint',
      answer_text: [chiefComplaint, duration && `duration: ${duration}`, `severity ${severityScore}/10`].filter(Boolean).join(' | '),
      section_id: 'CHIEF_COMPLAINT',
    },
    (site || onset || character || radiation || timing) && {
      question_text: 'SOCRATES symptom breakdown',
      answer_text: [
        site && `Site: ${site}`,
        onset && `Onset: ${onset}`,
        character && `Character: ${character}`,
        radiation && `Radiation: ${radiation}`,
        timing && `Timing: ${timing}`,
        associations.length && `Associated: ${associations.join(', ')}`,
      ].filter(Boolean).join('; '),
      section_id: 'SOCRATES',
    },
  ].filter(Boolean) as FollowupStatement[];

  const handleSaveAndContinue = async () => {
    const socratesObj: SocratesData = {
      site,
      onset,
      character,
      radiation,
      associations,
      timing,
      exacerbatingFactors: exacerbating,
      relievingFactors: relieving,
      severityScore,
    };

    const updatedCase: ClinicalCase = {
      id: existingCase?.id || `CASE-${patient.id.replace('P-', '')}`,
      patientId: patient.id,
      consultationType: patient.consultationType,
      status: 'intake_completed',
      chiefComplaints: [{ complaint: chiefComplaint, duration, severity: severityScore }],
      hpiNarrative: [
        chiefComplaint && `Patient reports ${chiefComplaint}${duration ? ` of ${duration} duration` : ''}.`,
        site && `Site: ${site}.`,
        onset && `Onset: ${onset}.`,
        character && `Character: ${character}.`,
        radiation && `Radiates to: ${radiation}.`,
        associations.length ? `Associated with: ${associations.join(', ')}.` : '',
        `Severity score: ${severityScore}/10.`,
      ].filter(Boolean).join(' '),
      socrates: socratesObj,
      pastMedicalHistory: pastConditions,
      pastSurgicalHistory: existingCase?.pastSurgicalHistory || [],
      medications,
      allergies: existingCase?.allergies || [],
      familyHistory: existingCase?.familyHistory || [],
      personalHistory: existingCase?.personalHistory || {
        diet: '',
        sleepHours: '',
        exercise: '',
        tobacco: '',
        alcohol: '',
        occupation: ''
      },
      reviewOfSystems: existingCase?.reviewOfSystems || {
        general: [],
        cardiovascular: [],
        respiratory: [],
        gastrointestinal: [],
        neurological: [],
        genitourinary: [],
        musculoskeletal: [],
        dermatological: []
      },
      hasRedFlags: redFlagInfo.hasRedFlag,
      redFlagReason: redFlagInfo.reason,
      aiDraftGeneratedAt: new Date().toISOString().replace('T', ' ').substring(0, 16),
      physicianReviewed: false
    };

    clinicalStore.saveCase(updatedCase);

    // QA BUG-004: the history is now captured (store + backend), so the local
    // in-progress draft is no longer needed and is cleared.
    try {
      window.localStorage.removeItem(draftKey);
    } catch {
      /* ignore */
    }

    // Persist the ORIGINAL patient answers (in their own words) to the backend
    // so the physician sees patient-provided data, separate from AI summaries.
    if (patient.sessionId) {
      try {
        const answers = [
          {
            section_id: 'CHIEF_COMPLAINT',
            question_text: 'Chief complaint',
            answer_text: [chiefComplaint, duration && `duration: ${duration}`, `severity ${severityScore}/10`].filter(Boolean).join(' | '),
            input_method: chiefVoiceTranscript ? 'voice' : 'touch',
            audio_transcript: chiefVoiceTranscript,
          },
          {
            section_id: 'SOCRATES',
            question_text: 'SOCRATES symptom breakdown',
            input_method: 'touch',
            audio_transcript: null,
            answer_text: [
              site && `Site: ${site}`,
              onset && `Onset: ${onset}`,
              character && `Character: ${character}`,
              radiation && `Radiation: ${radiation}`,
              timing && `Timing: ${timing}`,
              exacerbating && `Worsened by: ${exacerbating}`,
              relieving && `Relieved by: ${relieving}`,
              associations.length && `Associated: ${associations.join(', ')}`,
            ].filter(Boolean).join('; '),
          },
          {
            section_id: 'PAST_MEDICAL_HISTORY',
            question_text: 'Past medical conditions & chronic illness',
            input_method: 'touch',
            audio_transcript: null,
            answer_text: pastConditions.map((c) => `${c.condition}${c.diagnosedYear ? ` (${c.diagnosedYear})` : ''}`).join(', '),
          },
          {
            section_id: 'MEDICATIONS',
            question_text: 'Current medications',
            input_method: 'touch',
            audio_transcript: null,
            answer_text: medications.map((m) => `${m.name}${m.dose ? ` ${m.dose}` : ''}${m.frequency ? ` - ${m.frequency}` : ''}`).join(', '),
          },
          // Follow-up Q&A generated during the interview (structured data only).
          ...followupAnswers.map((fa) => ({
            section_id: 'FOLLOW_UP',
            question_text: fa.question_text,
            answer_text: fa.answer_text,
            input_method: 'touch',
            audio_transcript: null,
          })),
        ].filter((a) => a.answer_text.trim().length > 0);

        for (const a of answers) {
          await fetch('/api/intake/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: patient.sessionId,
              question_text: a.question_text,
              answer_text: a.answer_text,
              section_id: a.section_id,
              input_method: a.input_method,
              audio_transcript: a.audio_transcript,
            }),
          });
        }
        // Finalizes the session, generates the AI summary draft & queues the encounter.
        await fetch(`/api/intake/complete/${patient.sessionId}`, { method: 'POST' });
      } catch (err) {
        console.warn('Could not persist interview answers to backend:', err);
      }
    }

    onCompleteHistory(updatedCase);
  };

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            {t('iv.stepLabel', language)}
          </span>
          <span className="font-mono bg-[#F3EEFC] text-[#6C3FC5] px-2 py-0.5 rounded border border-[#6C3FC5]/20">
            {patient.fullName} ({patient.id})
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('iv.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('iv.sub', language)}
        </p>
      </div>

      {/* Red Flag Warning Box */}
      {redFlagInfo.hasRedFlag && (
        <div className="p-4 sm:p-5 rounded-xl bg-red-50 border-2 border-red-300 text-red-900 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-in fade-in duration-150">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="text-xs font-bold uppercase tracking-wider text-red-700">
                {t('iv.redFlagTitle', language)}
              </span>
              <p className="text-xs sm:text-sm font-semibold text-red-900 leading-snug">
                {redFlagInfo.reason}
              </p>
              <p className="text-[11px] text-red-700">
                {t('iv.redFlagNote', language)}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setTriageAlertSent(true);
              setNotifyModalOpen(true);
            }}
            className="flex items-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold shadow-xs flex-shrink-0 transition-colors"
          >
            <PhoneCall className="w-3.5 h-3.5" />
            <span>{triageAlertSent ? t('iv.notified', language) : t('iv.notify', language)}</span>
          </button>
        </div>
      )}

      {/* Red-flag triage acknowledgement — honest in-app dialog (replaces native alert()).
          No live nurse station is paged from this button; the flag travels with the
          intake record and is escalated when the encounter is submitted. */}
      <NotificationModal
        open={notifyModalOpen}
        tone="danger"
        title={t('iv.notifyModalTitle', language)}
        description={t('iv.notifyModalBody', language)}
        acknowledgeLabel={t('iv.notifyModalOk', language)}
        onCancel={() => setNotifyModalOpen(false)}
      />

      {/* 1. Chief Complaint Selection & Microphone */}
      <div className="p-5 sm:p-6 rounded-2xl border border-neutral-200 bg-white space-y-4 shadow-xs">
        <label className="text-xs font-bold uppercase tracking-wider text-[#666666] block">
          {t('iv.chiefLabel', language)}
        </label>

        {/* Quick complaint chips */}
        <div className="flex flex-wrap gap-2">
          {commonComplaints.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setChiefComplaint(item)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                chiefComplaint === item
                  ? 'bg-[#6C3FC5] text-white border-[#6C3FC5]'
                  : 'bg-neutral-50 text-[#171717] border-neutral-200 hover:bg-[#F3EEFC] hover:text-[#6C3FC5]'
              }`}
            >
              {chipLabel(item, language)}
            </button>
          ))}
        </div>

        {/* Input box with Microphone */}
        <div className="relative">
          <input
            type="text"
            value={chiefComplaint}
            onChange={(e) => setChiefComplaint(e.target.value)}
            placeholder={t('iv.chiefPlaceholder', language)}
            className="w-full px-4 py-3 pr-24 bg-white border border-neutral-300 rounded-xl text-xs sm:text-sm focus:border-[#6C3FC5] focus:ring-1 focus:ring-[#6C3FC5] focus:outline-none"
          />

          <button
            type="button"
            onClick={() => setShowVoicePanel((v) => !v)}
            className={`absolute right-2 top-2 px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              showVoicePanel
                ? 'bg-red-600 text-white'
                : 'bg-[#F3EEFC] text-[#6C3FC5] hover:bg-[#6C3FC5] hover:text-white'
            }`}
          >
            {showVoicePanel ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
            <span>{t('iv.voice', language)}</span>
          </button>
        </div>

        {/* Speech-to-text with mandatory patient review/edit step before apply */}
        {showVoicePanel && (
          <VoiceDictationPanel
            speechLanguage={interviewLanguage}
            language={language}
            onApply={(text) => {
              setChiefComplaint(text);
              setChiefVoiceTranscript(text);
            }}
            onClose={() => setShowVoicePanel(false)}
          />
        )}
      </div>

      {/* 2. SOCRATES Structured Questionnaire */}
      <div className="p-5 sm:p-6 rounded-2xl border border-neutral-200 bg-white space-y-5 shadow-xs">
        <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
          <h3 className="font-bold text-sm sm:text-base text-[#171717]">
            {t('iv.socratesTitle', language)}
          </h3>
          <span className="text-[11px] font-semibold text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded">
            {t('iv.clinicalStandard', language)}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          {/* Site */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.site', language)}</label>
            <input
              type="text"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Onset */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.onset', language)}</label>
            <input
              type="text"
              value={onset}
              onChange={(e) => setOnset(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Character */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.character', language)}</label>
            <input
              type="text"
              value={character}
              onChange={(e) => setCharacter(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Radiation */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.radiation', language)}</label>
            <input
              type="text"
              value={radiation}
              onChange={(e) => setRadiation(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Exacerbating */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.worsened', language)}</label>
            <input
              type="text"
              value={exacerbating}
              onChange={(e) => setExacerbating(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Relieving */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">{t('iv.relieved', language)}</label>
            <input
              type="text"
              value={relieving}
              onChange={(e) => setRelieving(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>
        </div>

        {/* Associations chips */}
        <div className="space-y-1.5 pt-2">
          <label className="text-xs font-bold text-[#171717] block">{t('iv.assocTitle', language)}</label>
          <div className="flex flex-wrap gap-2">
            {[
              'Profuse sweating (diaphoresis)',
              'Shortness of breath on exertion',
              'Nausea or Vomiting',
              'Dizziness / Lightheadedness',
              'Palpitations',
              'Loss of appetite'
            ].map((sym) => {
              const active = associations.includes(sym);
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => toggleAssociation(sym)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${
                    active
                      ? 'bg-[#6C3FC5] text-white border-[#6C3FC5]'
                      : 'bg-neutral-50 text-[#171717] border-neutral-200 hover:bg-[#F3EEFC]'
                  }`}
                >
                  {chipLabel(sym, language)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Severity Slider */}
        <div className="space-y-2 pt-2 border-t border-neutral-100">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-[#171717]">{t('iv.severity', language)} {severityScore}/10</span>
            <span className="text-[#666666]">
              {severityScore >= 8 ? t('iv.severe', language) : severityScore >= 5 ? t('iv.moderate', language) : t('iv.mild', language)}
            </span>
          </div>
          <input
            type="range"
            min="1"
            max="10"
            value={severityScore}
            onChange={(e) => setSeverityScore(parseInt(e.target.value))}
            className="w-full accent-[#6C3FC5] cursor-pointer"
          />
        </div>
      </div>

      {/* 3. Follow-up questions — free local LLM with guideline fallback */}
      <FollowUpQuestions
        sessionId={patient.sessionId}
        language={language}
        interviewLanguage={interviewLanguage}
        statements={followupContext}
        onAnswersChange={setFollowupAnswers}
      />

      {/* 4. Past Medical History */}
      <div className="p-5 sm:p-6 rounded-2xl border border-neutral-200 bg-white space-y-4 shadow-xs">
        <h3 className="font-bold text-sm sm:text-base text-[#171717]">
          {t('iv.pastTitle', language)}
        </h3>

        <div className="flex flex-wrap gap-2">
          {pastConditions.map((cond) => (
            <span
              key={cond.id}
              className="px-3 py-1.5 rounded-lg bg-[#F3EEFC] text-[#6C3FC5] text-xs font-medium border border-[#6C3FC5]/20 flex items-center gap-1.5"
            >
              <span>{cond.condition}</span>
              <button
                type="button"
                onClick={() => setPastConditions(pastConditions.filter(c => c.id !== cond.id))}
                className="hover:text-red-600"
              >
                ×
              </button>
            </span>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={newConditionInput}
            onChange={(e) => setNewConditionInput(e.target.value)}
            placeholder={t('iv.addConditionPlaceholder', language)}
            className="flex-1 px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs focus:border-[#6C3FC5] focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAddCondition}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-900 text-white rounded-lg text-xs font-semibold"
          >
            {t('iv.add', language)}
          </button>
        </div>
      </div>

      {/* Navigation Buttons */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('iv.back', language)}</span>
        </button>

        <button
          type="button"
          onClick={handleSaveAndContinue}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>
            {patient.consultationType === 'ayush' ? t('iv.continueAyush', language) : t('iv.continueDocs', language)}
          </span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
