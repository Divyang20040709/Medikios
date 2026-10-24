'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { KioskHeader } from '@/components/kiosk/KioskHeader';
import { AccessibilityBanner } from '@/components/kiosk/AccessibilityBanner';
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
import { HospitalHelpModal } from '@/components/kiosk/HospitalHelpModal';
import { staffEntryUrl } from '@/lib/auth';
import { SchemaModal } from '@/components/kiosk/SchemaModal';
import { Patient, ClinicalCase, DocumentItem, AccessibilitySettings, LanguageCode, ConsultationType } from '@/lib/types';
import { clinicalStore, SpeechAssistant, DEFAULT_PATIENT } from '@/lib/clinicalStore';
import { applyTextSize, accessibilityClasses } from '@/lib/accessibility';

// QA-02: identifies the patient this kiosk terminal is currently checking in.
// sessionStorage (not localStorage) on purpose — a new visitor or a new tab must
// never inherit the previous patient's chart.
const ACTIVE_INTAKE_KEY = 'medikiosk_intake_active_patient';

export default function PatientIntakeRoute() {
  const router = useRouter();
  const [step, setStep] = useState<
    'language' | 'ident' | 'consent' | 'dept' | 'hub' | 'interview' | 'ayush' | 'docs' | 'review' | 'token'
  >('language');

  const [accessibility, setAccessibility] = useState<AccessibilitySettings>({
    language: 'en',
    textSize: 'normal',
    highContrast: false,
    audioAssistance: false,
    screenReader: false,
  });

  // The chart is restored only for the patient THIS session identified (see the
  // mount effect below), never for "the last patient in the store": on a shared
  // kiosk that silently exposed the previous visitor's demographics and notes.
  const [patient, setPatient] = useState<Patient>(DEFAULT_PATIENT);
  const [clinicalCase, setClinicalCase] = useState<ClinicalCase | undefined>(undefined);
  const [docs, setDocs] = useState<DocumentItem[]>([]);

  const [helpOpen, setHelpOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);

  // QA-02: resume only the patient identified in this browser session, and let
  // the homepage deep links (?step=docs|review|interview) resume that same
  // patient. Without an identified patient the deep link is ignored and the
  // normal language-first wizard runs.
  React.useEffect(() => {
    const activeId = window.sessionStorage.getItem(ACTIVE_INTAKE_KEY);
    const resumed = activeId
      ? clinicalStore.getPatients().find((p) => p.id === activeId)
      : undefined;

    if (resumed) {
      setPatient(resumed);
      setClinicalCase(clinicalStore.getCaseByPatientId(resumed.id));
      setDocs(clinicalStore.getDocumentsByPatientId(resumed.id));
    }

    const requested = new URLSearchParams(window.location.search).get('step');
    if (resumed && (requested === 'docs' || requested === 'review' || requested === 'interview')) {
      setStep(requested);
    }
  }, []);

  // QA-03: font size scales the document root so the banner works on this route.
  React.useEffect(() => {
    applyTextSize(accessibility.textSize);
  }, [accessibility.textSize]);

  /**
   * Saves the Step-4 consultation stream on the encounter. This IS the
   * appointment routing decision: the encounter moves into the queue of the
   * matching physician — General & Modern Medicine, or Traditional / AYUSH.
   * The kiosk never stalls on it: if the server cannot be reached the locally
   * chosen stream is kept and the patient continues through the flow.
   */
  const saveConsultationType = async (type: ConsultationType) => {
    const chosen: Patient = {
      ...patient,
      consultationType: type,
      department:
        type === 'ayush'
          ? 'AYUSH / Kayachikitsa OPD'
          : patient.consultationType === 'ayush'
            ? 'General Medicine'
            : patient.department,
    };
    setPatient(chosen);
    clinicalStore.addOrUpdatePatient(chosen);

    if (!patient.encounterId) return;
    try {
      const res = await fetch(`/api/intake/${patient.encounterId}/consultation-type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consultation_type: type }),
      });
      if (!res.ok) return;
      const data = await res.json();
      const routed: Patient = {
        ...chosen,
        department: data.department || chosen.department,
        assignedDoctorName: data.assigned_doctor?.name,
      };
      setPatient(routed);
      clinicalStore.addOrUpdatePatient(routed);
    } catch {
      /* Offline kiosk: keep the local stream choice and continue. */
    }
  };

  return (
    <div
      className={`min-h-screen flex flex-col bg-white text-[#171717] font-sans selection:bg-[#6C3FC5] selection:text-white ${accessibilityClasses(
        accessibility
      )}`}
    >
      <KioskHeader
        activeRole="patient"
        onSelectRole={(role) => {
          // Staff areas are entered through an explicit sign-in every time
          // (shared-kiosk rule); RequireAuth then revalidates the real DB role.
          // 'patient' stays in this intake flow.
          if (role === 'physician') router.push(staffEntryUrl('/doctor'));
          else if (role === 'admin') router.push(staffEntryUrl('/admin'));
        }}
        kioskId="KIOSK-01"
        currentLanguage={accessibility.language}
        onLanguageChange={(lang: LanguageCode) => setAccessibility((prev) => ({ ...prev, language: lang }))}
        isKioskMode={true}
        onHomeClick={() => router.push('/')}
        onOpenHelp={() => setHelpOpen(true)}
        onOpenSchema={() => setSchemaOpen(true)}
        isSpeaking={accessibility.audioAssistance}
        onToggleAudioHelp={() =>
          setAccessibility((prev) => {
            const next = !prev.audioAssistance;
            if (!next) SpeechAssistant.stopSpeaking();
            return { ...prev, audioAssistance: next };
          })
        }
      />

      <AccessibilityBanner
        settings={accessibility}
        onSettingsChange={setAccessibility}
      />

      <main className="flex-1 flex flex-col">
        {step === 'language' && (
          <Step1Language
            currentLanguage={accessibility.language}
            onSelectLanguage={(lang) => setAccessibility((prev) => ({ ...prev, language: lang }))}
            onContinue={() => setStep('ident')}
            onBack={() => router.push('/')}
          />
        )}

        {step === 'ident' && (
          <Step2PatientIdent
            currentPatient={patient}
            onPatientIdentified={(p) => {
              setPatient(p);
              setClinicalCase(clinicalStore.getCaseByPatientId(p.id));
              setDocs(clinicalStore.getDocumentsByPatientId(p.id));
              window.sessionStorage.setItem(ACTIVE_INTAKE_KEY, p.id);
              setStep('consent');
            }}
            onBack={() => setStep('language')}
            demoPatients={clinicalStore.getPatients()}
            language={accessibility.language}
          />
        )}

        {step === 'consent' && (
          <Step3Consent
            patientId={patient.id}
            patientName={patient.fullName}
            encounterId={patient.encounterId}
            language={accessibility.language}
            onConsentAgreed={() => setStep('dept')}
            onBack={() => setStep('ident')}
            onConsentDeclined={() => router.push('/')}
          />
        )}

        {step === 'dept' && (
          <Step4Department
            consultationType={patient.consultationType}
            onSelectType={(type) => {
              const updated = { ...patient, consultationType: type };
              setPatient(updated);
              clinicalStore.addOrUpdatePatient(updated);
            }}
            onContinue={async () => {
              // Persist BEFORE leaving the step so the token slip and the
              // physician's queue already reflect the routed appointment.
              await saveConsultationType(patient.consultationType);
              setStep('hub');
            }}
            onBack={() => setStep('consent')}
            patientName={patient.fullName}
          />
        )}

        {step === 'hub' && (
          <PatientIntakeHub
            patient={patient}
            hasCaseHistory={!!clinicalCase}
            onStartHistory={() => setStep('interview')}
            onGoToDocuments={() => setStep('docs')}
            onBack={() => setStep('dept')}
          />
        )}

        {step === 'interview' && (
          <SymptomHistoryInterview
            patient={patient}
            existingCase={clinicalCase}
            language={accessibility.language}
            onCompleteHistory={(c) => {
              setClinicalCase(c);
              if (patient.consultationType === 'ayush') {
                setStep('ayush');
              } else {
                setStep('docs');
              }
            }}
            onBack={() => setStep('hub')}
          />
        )}

        {step === 'ayush' && (
          <AyushAssessmentModule
            patient={patient}
            initialAssessment={clinicalCase?.ayushAssessment}
            onSave={() => setStep('docs')}
            onBack={() => setStep('interview')}
          />
        )}

        {step === 'docs' && (
          <DocumentScannerModule
            patient={patient}
            documents={docs}
            language={accessibility.language}
            onDocumentsUpdated={(d) => setDocs(d)}
            onContinue={() => setStep('review')}
            onBack={() => setStep(patient.consultationType === 'ayush' ? 'ayush' : 'interview')}
          />
        )}

        {step === 'review' && (
          <HistoryReviewModule
            patient={patient}
            clinicalCase={clinicalCase}
            documents={docs}
            onConfirm={() => setStep('token')}
            onEdit={() => setStep('interview')}
            onBack={() => setStep('docs')}
          />
        )}

        {step === 'token' && (
          <TokenConfirmationSlip
            patient={patient}
            onDone={() => {
              // The visit is over — do not let the next visitor resume it.
              window.sessionStorage.removeItem(ACTIVE_INTAKE_KEY);
              router.push('/');
            }}
          />
        )}
      </main>

      <HospitalHelpModal isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
      <SchemaModal isOpen={schemaOpen} onClose={() => setSchemaOpen(false)} />
    </div>
  );
}
