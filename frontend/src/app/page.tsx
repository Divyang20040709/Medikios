'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  UserRole,
  LanguageCode,
  AccessibilitySettings,
  Patient,
  ClinicalCase,
  DocumentItem
} from '@/lib/types';
import { clinicalStore, SpeechAssistant, DEFAULT_PATIENT } from '@/lib/clinicalStore';
import { staffEntryUrl } from '@/lib/auth';
import { useUiLanguage, useInterviewLanguage } from '@/lib/languagePrefs';
import { applyTextSize, accessibilityClasses } from '@/lib/accessibility';
import { KioskHeader } from '@/components/kiosk/KioskHeader';
import { AccessibilityBanner } from '@/components/kiosk/AccessibilityBanner';
import { HospitalHelpModal } from '@/components/kiosk/HospitalHelpModal';
import { SchemaModal } from '@/components/kiosk/SchemaModal';
import { LandingOverview } from '@/components/kiosk/LandingOverview';
import { Step1Language } from '@/components/kiosk/Step1Language';
import { Step2PatientIdent } from '@/components/kiosk/Step2PatientIdent';
import { Step3Consent } from '@/components/kiosk/Step3Consent';
import { Step4Department } from '@/components/kiosk/Step4Department';
import { PatientIntakeHub } from '@/components/kiosk/PatientIntakeHub';
import { SymptomHistoryInterview } from '@/components/kiosk/SymptomHistoryInterview';
import { AyushAssessmentModule } from '@/components/kiosk/AyushAssessmentModule';
import { DocumentScannerModule } from '@/components/kiosk/DocumentScannerModule';
import { HistoryReviewModule } from '@/components/kiosk/HistoryReviewModule';
import { TokenConfirmationSlip } from '@/components/kiosk/TokenConfirmationSlip';

type PatientViewState =
  | 'landing' | 'language' | 'patient_ident' | 'consent' | 'consult_type'
  | 'patient_dash' | 'history_interview' | 'ayush_module' | 'document_upload'
  | 'review' | 'token';

// QA BUG-008: only these in-patient-wizard views are reflected in the URL, so a
// refresh or bookmark returns the patient to the same kiosk step. Physician/admin
// workstations live on their own guarded routes (/doctor, /admin) and are excluded.
const VALID_PATIENT_VIEWS: ReadonlySet<string> = new Set<PatientViewState>([
  'landing', 'language', 'patient_ident', 'consent', 'consult_type',
  'patient_dash', 'history_interview', 'ayush_module', 'document_upload',
  'review', 'token',
]);

export default function Home() {
  const router = useRouter();
  // Navigation Role & Subviews
  const [activeRole, setActiveRole] = useState<UserRole>('patient');
  const [patientView, setPatientView] = useState<PatientViewState>('landing');

  // Accessibility State — UI language is persisted (survives refresh/route
  // changes); the AI interview language is stored separately under its own key.
  const [uiLanguage, setUiLanguage] = useUiLanguage();
  const [interviewLanguage, setInterviewLanguage] = useInterviewLanguage();
  const [accessibility, setAccessibility] = useState<AccessibilitySettings>({
    language: 'en',
    textSize: 'normal',
    highContrast: false,
    audioAssistance: false,
    screenReader: false,
  });
  const effectiveSettings: AccessibilitySettings = { ...accessibility, language: uiLanguage };

  const handleSettingsChange = (next: AccessibilitySettings) => {
    if (next.language !== uiLanguage) setUiLanguage(next.language);
    setAccessibility(next);
  };

  const [mounted, setMounted] = useState(false);
  const [patients, setPatients] = useState<Patient[]>([]);

  // Active Patient State (initialized safely for SSR hydration)
  const [currentPatient, setCurrentPatient] = useState<Patient>(DEFAULT_PATIENT);
  const [currentCase, setCurrentCase] = useState<ClinicalCase | undefined>(undefined);
  const [currentDocs, setCurrentDocs] = useState<DocumentItem[]>([]);

  // Modals
  const [helpOpen, setHelpOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);

  // Initialize store data on client mount to eliminate SSR hydration mismatch
  useEffect(() => {
    setMounted(true);
    const list = clinicalStore.getPatients();
    setPatients(list);
    if (list.length > 0) {
      setCurrentPatient(list[0]);
      setCurrentCase(clinicalStore.getCaseByPatientId(list[0].id));
      setCurrentDocs(clinicalStore.getDocumentsByPatientId(list[0].id));
    }

    const unsub = clinicalStore.subscribe(() => {
      const updated = clinicalStore.getPatients();
      setPatients(updated);
    });
    return () => unsub();
  }, []);

  // Re-fetch documents & cases when current patient changes
  useEffect(() => {
    if (currentPatient?.id) {
      setCurrentCase(clinicalStore.getCaseByPatientId(currentPatient.id));
      setCurrentDocs(clinicalStore.getDocumentsByPatientId(currentPatient.id));
    }
  }, [currentPatient?.id]);

  // QA BUG-008 (read): restore the kiosk step from ?view= on first mount so a
  // refresh or bookmarked deep link returns to the same wizard step.
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('view');
    if (requested && VALID_PATIENT_VIEWS.has(requested)) {
      setActiveRole('patient');
      setPatientView(requested as PatientViewState);
    }
  }, []);

  // QA BUG-008 (write): keep the URL in sync with the active patient view. Runs
  // only after mount (so prerendered HTML is unchanged) and is driven by state,
  // not the URL, so it cannot loop.
  useEffect(() => {
    if (!mounted) return;
    const params = new URLSearchParams(window.location.search);
    if (activeRole === 'patient' && patientView !== 'landing') {
      params.set('view', patientView);
    } else {
      params.delete('view');
    }
    const qs = params.toString();
    router.replace(qs ? `/?${qs}` : '/', { scroll: false });
  }, [activeRole, patientView, mounted, router]);

  const handleSelectRole = (role: UserRole) => {
    SpeechAssistant.stopSpeaking();
    // Routing fix: staff workstations live on their OWN guarded routes so the
    // address bar updates, refresh works, and RequireAuth + logout apply. Never
    // render them inline at '/' (which had no guard and kept stomping the URL).
    //
    // Shared-kiosk rule: both staff entry points ALWAYS pass through the sign-in
    // screen, even when a staff session is already stored. Nothing opens from
    // this click; access is granted only after the login form's token is
    // revalidated by RequireAuth against GET /api/auth/me.
    if (role === 'physician') {
      router.push(staffEntryUrl('/doctor'));
      return;
    }
    if (role === 'admin') {
      router.push(staffEntryUrl('/admin'));
      return;
    }
    // "Patient Kiosk" opens the canonical public patient intake flow.
    router.push('/patient/intake');
  };

  const handleSelectLanguage = (lang: LanguageCode) => {
    // Header menu changes ONLY the interface language. The AI interview keeps
    // running in the language chosen at Step 1 — patient answers are unaffected.
    setUiLanguage(lang);
  };

  const handlePatientIdentified = (patient: Patient) => {
    setCurrentPatient(patient);
    setCurrentCase(clinicalStore.getCaseByPatientId(patient.id));
    setCurrentDocs(clinicalStore.getDocumentsByPatientId(patient.id));
    setPatientView('consent');
  };

  // QA-03: the font-size control scales the document root (see lib/accessibility)
  // so every route reacts, not just the un-sized text on this page.
  React.useEffect(() => {
    applyTextSize(accessibility.textSize);
  }, [accessibility.textSize]);

  const contrastClass = accessibilityClasses(accessibility);

  return (
    <div
      className={`min-h-screen flex flex-col bg-white text-[#171717] font-sans selection:bg-[#6C3FC5] selection:text-white ${contrastClass}`}
    >
      {/* 1. Universal Top Header */}
      <KioskHeader
        activeRole={activeRole}
        onSelectRole={handleSelectRole}
        kioskId="KIOSK-01"
        currentLanguage={uiLanguage}
        onLanguageChange={handleSelectLanguage}
        isKioskMode={activeRole === 'patient' && patientView !== 'landing'}
        onHomeClick={() => {
          setActiveRole('patient');
          setPatientView('landing');
          SpeechAssistant.stopSpeaking();
        }}
        onOpenHelp={() => setHelpOpen(true)}
        onOpenSchema={() => setSchemaOpen(true)}
        onLoginClick={() => router.push('/login')}
        isSpeaking={accessibility.audioAssistance}
        onToggleAudioHelp={() =>
          setAccessibility((prev) => {
            const next = !prev.audioAssistance;
            if (!next) SpeechAssistant.stopSpeaking();
            return { ...prev, audioAssistance: next };
          })
        }
      />

      {/* 2. Accessibility & Emergency Protocol Banner */}
      <AccessibilityBanner
        settings={effectiveSettings}
        onSettingsChange={handleSettingsChange}
      />

      {/* 3. Main Workspace Router */}
      <main className="flex-1 flex flex-col bg-white">
        {/* PATIENT KIOSK VIEWS */}
        {activeRole === 'patient' && (
          <>
            {patientView === 'landing' && (
              <LandingOverview
                language={uiLanguage}
                onStart={() => setPatientView('language')}
                onDoctorClick={() => handleSelectRole('physician')}
                onSelectPresetPatient={(p) => {
                  setCurrentPatient(p);
                  setPatientView('consent');
                }}
                demoPatients={patients}
              />
            )}

            {patientView === 'language' && (
              <Step1Language
                currentLanguage={uiLanguage}
                onSelectLanguage={(lang) => {
                  // Step 1 selection sets BOTH the interface language and the
                  // AI interview language (patient's clinical answer language).
                  setUiLanguage(lang);
                  setInterviewLanguage(lang);
                }}
                onContinue={() => setPatientView('patient_ident')}
                onBack={() => setPatientView('landing')}
              />
            )}

            {patientView === 'patient_ident' && (
              <Step2PatientIdent
                currentPatient={currentPatient}
                onPatientIdentified={handlePatientIdentified}
                onBack={() => setPatientView('language')}
                demoPatients={patients}
                language={uiLanguage}
                interviewLanguage={interviewLanguage}
              />
            )}

            {patientView === 'consent' && (
              <Step3Consent
                patientId={currentPatient.id}
                patientName={currentPatient.fullName}
                encounterId={currentPatient.encounterId}
                language={uiLanguage}
                onConsentAgreed={() => setPatientView('consult_type')}
                onBack={() => setPatientView('patient_ident')}
                onConsentDeclined={() => setPatientView('landing')}
              />
            )}

            {patientView === 'consult_type' && (
              <Step4Department
                consultationType={currentPatient.consultationType}
                onSelectType={(type) => {
                  const updated = { ...currentPatient, consultationType: type };
                  setCurrentPatient(updated);
                  clinicalStore.addOrUpdatePatient(updated);
                }}
                onContinue={() => setPatientView('patient_dash')}
                onBack={() => setPatientView('consent')}
                patientName={currentPatient.fullName}
                language={uiLanguage}
              />
            )}

            {patientView === 'patient_dash' && (
              <PatientIntakeHub
                patient={currentPatient}
                hasCaseHistory={!!currentCase}
                language={uiLanguage}
                onStartHistory={() => setPatientView('history_interview')}
                onGoToDocuments={() => setPatientView('document_upload')}
                onBack={() => setPatientView('consult_type')}
              />
            )}

            {patientView === 'history_interview' && (
              <SymptomHistoryInterview
                patient={currentPatient}
                existingCase={currentCase}
                language={uiLanguage}
                speechLanguage={interviewLanguage}
                onCompleteHistory={(updatedCase) => {
                  setCurrentCase(updatedCase);
                  if (currentPatient.consultationType === 'ayush') {
                    setPatientView('ayush_module');
                  } else {
                    setPatientView('document_upload');
                  }
                }}
                onBack={() => setPatientView('patient_dash')}
              />
            )}

            {patientView === 'ayush_module' && (
              <AyushAssessmentModule
                patient={currentPatient}
                initialAssessment={currentCase?.ayushAssessment}
                onSave={() => setPatientView('document_upload')}
                onBack={() => setPatientView('history_interview')}
              />
            )}

            {patientView === 'document_upload' && (
              <DocumentScannerModule
                patient={currentPatient}
                documents={currentDocs}
                onDocumentsUpdated={(docs) => setCurrentDocs(docs)}
                onContinue={() => setPatientView('review')}
                onBack={() =>
                  setPatientView(
                    currentPatient.consultationType === 'ayush' ? 'ayush_module' : 'history_interview'
                  )
                }
              />
            )}

            {patientView === 'review' && (
              <HistoryReviewModule
                patient={currentPatient}
                clinicalCase={currentCase}
                documents={currentDocs}
                onConfirm={() => setPatientView('token')}
                onEdit={() => setPatientView('history_interview')}
                onBack={() => setPatientView('document_upload')}
              />
            )}

            {patientView === 'token' && (
              <TokenConfirmationSlip
                patient={currentPatient}
                language={uiLanguage}
                onDone={() => setPatientView('landing')}
              />
            )}
          </>
        )}
      </main>

      {/* 4. Global Modals */}
      <HospitalHelpModal isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
      <SchemaModal isOpen={schemaOpen} onClose={() => setSchemaOpen(false)} />
    </div>
  );
}
