'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { KioskHeader } from '@/components/kiosk/KioskHeader';
import { AccessibilityBanner } from '@/components/kiosk/AccessibilityBanner';
import { DoctorWorkstation } from '@/components/doctor/DoctorWorkstation';
import { RequireAuth } from '@/components/common/RequireAuth';
import { signOutStaff, staffEntryUrl } from '@/lib/auth';
import { HospitalHelpModal } from '@/components/kiosk/HospitalHelpModal';
import { SchemaModal } from '@/components/kiosk/SchemaModal';
import { AccessibilitySettings } from '@/lib/types';
import { SpeechAssistant } from '@/lib/clinicalStore';
import { useUiLanguage } from '@/lib/languagePrefs';
import { applyTextSize, accessibilityClasses } from '@/lib/accessibility';

export default function DoctorPage() {
  const router = useRouter();
  const [helpOpen, setHelpOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  // UI language is shared across all routes and persisted (localStorage).
  const [uiLanguage, setUiLanguage] = useUiLanguage();
  const [accessibility, setAccessibility] = useState<AccessibilitySettings>({
    language: 'en',
    textSize: 'normal',
    highContrast: false,
    audioAssistance: false,
    screenReader: false,
  });

  const effectiveSettings: AccessibilitySettings = { ...accessibility, language: uiLanguage };

  // QA-03: the banner's font-size control had no effect on this route.
  React.useEffect(() => {
    applyTextSize(accessibility.textSize);
  }, [accessibility.textSize]);

  const handleSettingsChange = (next: AccessibilitySettings) => {
    if (next.language !== uiLanguage) setUiLanguage(next.language);
    setAccessibility({ ...next, language: uiLanguage });
  };

  return (
    <div
      className={`min-h-screen flex flex-col bg-white text-[#171717] font-sans selection:bg-[#6C3FC5] selection:text-white ${accessibilityClasses(
        effectiveSettings
      )}`}
    >
      {/* SEC: the ENTIRE staff surface (header chrome + workstation) is gated.
          Nothing of the Physician OPD page paints until GET /api/auth/me confirms
          the bearer token and an allowed role: anonymous/expired -> /login?next=...
          and a wrong role -> explicit denied panel. A click on "Physician OPD" can
          never reveal workstation chrome or data without a server-validated session. */}
      <RequireAuth allowedRoles={['DOCTOR', 'ADMIN']}>
        <>
      <KioskHeader
        activeRole="physician"
        onSelectRole={(role) => {
          // "Patient Kiosk" opens the patient intake flow directly — the landing
          // page is only the public front door, not a required hop. Intake is a
          // public kiosk surface, so no sign-in is requested here.
          if (role === 'patient') router.push('/patient/intake');
          // Shared-kiosk rule: switching to another staff area re-authenticates.
          else if (role === 'admin') router.push(staffEntryUrl('/admin'));
        }}
        kioskId="OPD-DOCTOR-01"
        currentLanguage={effectiveSettings.language}
        onLanguageChange={(lang) => setUiLanguage(lang)}
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
        onSignOut={() => {
          // QA BUG-011 / SEC-2: end the staff session and return to sign-in.
          // Client-side logout only — the JWT API has no server revocation.
          signOutStaff();
          router.replace('/login');
        }}
      />
      <AccessibilityBanner
        settings={effectiveSettings}
        onSettingsChange={handleSettingsChange}
      />
      <main className="flex-1 flex flex-col">
        {/* QA BUG-003: ADMIN may read the OPD queue (existing behaviour), but
            every clinical action stays DOCTOR-only and is enforced server-side. */}
        <DoctorWorkstation onBackToOverview={() => router.push('/')} language={uiLanguage} />
      </main>
        </>
      </RequireAuth>
      <HospitalHelpModal isOpen={helpOpen} onClose={() => setHelpOpen(false)} />
      <SchemaModal isOpen={schemaOpen} onClose={() => setSchemaOpen(false)} />
    </div>
  );
}
