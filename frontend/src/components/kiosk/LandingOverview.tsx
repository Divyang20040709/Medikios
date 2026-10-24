'use client';

import React from 'react';
import Link from 'next/link';
import Image from 'next/image';
import {
  ArrowRight,
  Stethoscope,
  Activity,
  FileText,
  Clock,
  ShieldCheck,
  CheckCircle2,
  ChevronRight,
  AlertTriangle,
  Building2,
  Users,
  Sparkles,
} from 'lucide-react';
import { Patient, LanguageCode } from '@/lib/types';
import { staffEntryUrl } from '@/lib/auth';

interface LandingOverviewProps {
  language: LanguageCode;
  onStart: () => void;
  onDoctorClick: () => void;
  onSelectPresetPatient?: (patient: Patient) => void;
  demoPatients: Patient[];
}

export function LandingOverview({
  language,
  onStart,
  onDoctorClick,
  onSelectPresetPatient,
  demoPatients,
}: LandingOverviewProps) {
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);
  return (
    <div className="w-full flex flex-col bg-white">
      {/* 1. Hero Section */}
      <section className="relative w-full border-b border-neutral-200 bg-gradient-to-b from-[#F3EEFC]/30 to-white py-12 sm:py-16 lg:py-20 px-4 sm:px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
          <div className="lg:col-span-7 flex flex-col items-start space-y-6">
            {/* Top pill badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] text-xs font-semibold">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Empowering Clinical Consultations • AI-assisted history intake for high-volume hospitals</span>
            </div>

            {/* Main Headline */}
            <h1 className="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-sans font-extrabold text-[#171717] tracking-tight leading-[1.15] break-words">
              Your health history,{' '}
              <span className="text-[#6C3FC5]">prepared before you see the doctor.</span>
            </h1>

            {/* Subtitle */}
            <p className="text-base sm:text-lg text-[#666666] leading-relaxed max-w-2xl font-normal">
              MediKiosk assists patients in recording their symptoms in their native tongue, uploading past records, and delivering an AI-synthesized clinical summary to their doctor.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4 pt-1 w-full sm:w-auto">
              <button
                type="button"
                onClick={onStart}
                className="w-full sm:w-auto flex items-center justify-center gap-2.5 min-h-[48px] px-6 sm:px-8 py-3.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white rounded-xl font-bold text-sm sm:text-base shadow-md hover:shadow-lg transition-all active:scale-[0.99]"
              >
                <span>Start Patient Check-in</span>
                <ArrowRight className="w-5 h-5" />
              </button>

              <button
                type="button"
                onClick={onDoctorClick}
                className="w-full sm:w-auto flex items-center justify-center gap-2.5 min-h-[48px] px-5 sm:px-7 py-3.5 bg-white hover:bg-[#F3EEFC] text-[#171717] border border-neutral-300 hover:border-[#6C3FC5]/40 rounded-xl font-semibold text-sm sm:text-base transition-all active:scale-[0.99]"
              >
                <Stethoscope className="w-5 h-5 text-[#6C3FC5]" />
                <span>Physician OPD Workstation</span>
              </button>
            </div>

            {/* Role sign-in options — a common, clearly visible entry to the
                single existing /login flow (?role= preselects the tab). */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-xs font-semibold text-[#666666]">Login:</span>
              <Link
                href="/login?role=patient"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-neutral-300 hover:border-[#6C3FC5] hover:bg-[#F3EEFC] text-[#171717] transition-colors"
              >
                <Users className="w-3.5 h-3.5 text-[#6C3FC5]" />
                <span>Patient Login</span>
              </Link>
              <Link
                href="/login?role=doctor"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-neutral-300 hover:border-[#6C3FC5] hover:bg-[#F3EEFC] text-[#171717] transition-colors"
              >
                <Stethoscope className="w-3.5 h-3.5 text-[#6C3FC5]" />
                <span>Doctor Login</span>
              </Link>
              <Link
                href="/login?role=admin"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-neutral-300 hover:border-[#6C3FC5] hover:bg-[#F3EEFC] text-[#171717] transition-colors"
              >
                <Building2 className="w-3.5 h-3.5 text-[#6C3FC5]" />
                <span>Admin Login</span>
              </Link>
            </div>

            {/* Badges / Trust points */}
            <div className="pt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-[#666666] font-medium border-t border-neutral-100 w-full">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-[#6C3FC5]" />
                <span>Smart India Hackathon</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-[#6C3FC5]" />
                <span>DPDP Act 2023 Compliant</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-[#6C3FC5]" />
                <span>ABDM & FHIR R4 Ready</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-[#6C3FC5]" />
                <span>AYUSH Dashavidha Pariksha</span>
              </div>
            </div>
          </div>

          {/* Hero Image / Tablet Preview */}
          <div className="lg:col-span-5 relative">
            <div className="relative rounded-2xl overflow-hidden border border-neutral-200 shadow-xl bg-neutral-100">
              <img
                src="https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=1000&q=80"
                alt="Doctor with digital tablet consulting with patient"
                className="w-full h-[240px] sm:h-[340px] lg:h-[420px] object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
              <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur-xs p-4 rounded-xl border border-white/60 shadow-lg">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs font-bold text-[#171717]">Kiosk-Terminal-01 Active</span>
                  </div>
                  <span className="text-[11px] font-mono text-[#6C3FC5] bg-[#F3EEFC] px-1.5 py-0.5 rounded">
                    Room 104 • Block B
                  </span>
                </div>
                <p className="text-xs text-[#666666]">
                  Patient intakes are automatically converted into SOCRATES structured records and sent to the doctor queue.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Four Core Capabilities */}
      <section className="py-14 sm:py-20 px-4 sm:px-6 bg-white border-b border-neutral-200">
        <div className="max-w-7xl mx-auto space-y-12">
          <div className="text-center max-w-3xl mx-auto space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider text-[#6C3FC5] bg-[#F3EEFC] px-3 py-1 rounded-full">
              Hospital OPD Flow
            </span>
            <h2 className="text-3xl sm:text-4xl font-sans font-bold text-[#171717]">
              Designed for Comprehensive Hospital Intake
            </h2>
            <p className="text-sm sm:text-base text-[#666666]">
              Four core capabilities streamlining the patient journey from OPD queue to physician sign-off.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Card 1 — AI-assisted history: full patient intake/history workflow */}
            <Link
              href="/patient/intake"
              className="flex flex-col rounded-xl border border-neutral-200 overflow-hidden bg-white shadow-xs hover:shadow-md transition-shadow"
            >
              <div className="h-44 overflow-hidden relative">
                <img
                  src="https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?auto=format&fit=crop&w=600&q=80"
                  alt="Doctor listening intently to patient during clinical history"
                  className="w-full h-full object-cover"
                />
                <span className="absolute top-2.5 right-2.5 bg-white/95 text-[11px] font-bold text-[#6C3FC5] px-2 py-0.5 rounded shadow-xs">
                  Save 15 min / patient
                </span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-between space-y-2">
                <div>
                  <h3 className="font-bold text-[#171717] text-base mb-1">AI-Assisted History</h3>
                  <p className="text-xs text-[#666666] leading-relaxed">
                    Conversational symptom elicitation with SOCRATES scoring, red flag safety alerts, and multi-language voice support.
                  </p>
                </div>
                <div className="pt-2 text-[11px] font-semibold text-[#6C3FC5] flex items-center gap-1">
                  <span>Adaptive Questions</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </Link>

            {/* Card 2 — document scanning: existing OCR module (intake 'docs' step) */}
            <Link
              href="/patient/intake?step=docs"
              className="flex flex-col rounded-xl border border-neutral-200 overflow-hidden bg-white shadow-xs hover:shadow-md transition-shadow"
            >
              <div className="h-44 overflow-hidden relative">
                <img
                  src="https://images.unsplash.com/photo-1576091160550-2173dba999ef?auto=format&fit=crop&w=600&q=80"
                  alt="Medical chart and laboratory diagnostic report review"
                  className="w-full h-full object-cover"
                />
                <span className="absolute top-2.5 right-2.5 bg-white/95 text-[11px] font-bold text-[#6C3FC5] px-2 py-0.5 rounded shadow-xs">
                  Instant Extraction
                </span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-between space-y-2">
                <div>
                  <h3 className="font-bold text-[#171717] text-base mb-1">Document Scanning</h3>
                  <p className="text-xs text-[#666666] leading-relaxed">
                    Instant OCR extraction for previous prescriptions, laboratory results, discharge summaries, and radiology reports.
                  </p>
                </div>
                <div className="pt-2 text-[11px] font-semibold text-[#6C3FC5] flex items-center gap-1">
                  <span>PaddleOCR & AI Models</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </Link>

            {/* Card 3 — structured records: clinical-history review module (intake 'review' step) */}
            <Link
              href="/patient/intake?step=review"
              className="flex flex-col rounded-xl border border-neutral-200 overflow-hidden bg-white shadow-xs hover:shadow-md transition-shadow"
            >
              <div className="h-44 overflow-hidden relative">
                <img
                  src="https://images.unsplash.com/photo-1551076805-e1869033e561?auto=format&fit=crop&w=600&q=80"
                  alt="Digital patient health record timeline on tablet"
                  className="w-full h-full object-cover"
                />
                <span className="absolute top-2.5 right-2.5 bg-white/95 text-[11px] font-bold text-[#6C3FC5] px-2 py-0.5 rounded shadow-xs">
                  Longitudinal View
                </span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-between space-y-2">
                <div>
                  <h3 className="font-bold text-[#171717] text-base mb-1">Structured Records</h3>
                  <p className="text-xs text-[#666666] leading-relaxed">
                    Chronological timeline synthesis, past condition tracking, and standardized medication reconciliation.
                  </p>
                </div>
                <div className="pt-2 text-[11px] font-semibold text-[#6C3FC5] flex items-center gap-1">
                  <span>Timeline Synthesis</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </Link>

            {/* Card 4 — Physician OPD Workstation. Shared-kiosk rule: the card
                leads to the sign-in screen (/login?next=/doctor&role=DOCTOR),
                never straight into the guarded /doctor route. */}
            <Link
              href={staffEntryUrl('/doctor')}
              className="flex flex-col rounded-xl border border-neutral-200 overflow-hidden bg-white shadow-xs hover:shadow-md transition-shadow"
            >
              <div className="h-44 overflow-hidden relative">
                <img
                  src="https://images.unsplash.com/photo-1551601651-2a8555f1a136?auto=format&fit=crop&w=600&q=80"
                  alt="Doctor workstation and clinical decision assistance"
                  className="w-full h-full object-cover"
                />
                <span className="absolute top-2.5 right-2.5 bg-white/95 text-[11px] font-bold text-[#6C3FC5] px-2 py-0.5 rounded shadow-xs">
                  Physician Control
                </span>
              </div>
              <div className="p-5 flex-1 flex flex-col justify-between space-y-2">
                <div>
                  <h3 className="font-bold text-[#171717] text-base mb-1">Doctor Dashboard</h3>
                  <p className="text-xs text-[#666666] leading-relaxed">
                    One-click review with ICD-10 suggestions, red flag badges, FHIR R4 exports, and digital signing.
                  </p>
                </div>
                <div className="pt-2 text-[11px] font-semibold text-[#6C3FC5] flex items-center gap-1">
                  <span>FHIR R4 Diagnostic Report</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </div>
              </div>
            </Link>
          </div>
        </div>
      </section>

      {/* 3. Clinical Governance & Ethics Banner */}
      <section className="py-12 px-4 sm:px-6 bg-[#F3EEFC]/40 border-b border-neutral-200">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-4 space-y-2">
            <span className="text-xs font-bold text-[#6C3FC5] uppercase tracking-wider">
              Clinical Governance & Ethics
            </span>
            <h3 className="text-2xl sm:text-3xl font-sans font-bold text-[#171717]">
              Assisting physicians, not replacing them.
            </h3>
          </div>
          <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-[#666666]">
            <div className="p-4 bg-white rounded-xl border border-neutral-200 space-y-1.5 shadow-2xs">
              <div className="flex items-center gap-2 font-bold text-[#171717]">
                <ShieldCheck className="w-4 h-4 text-[#6C3FC5]" />
                <span>Doctor In Control</span>
              </div>
              <p>Every draft summary requires explicit physician review and digital signature before updating the hospital EHR.</p>
            </div>
            <div className="p-4 bg-white rounded-xl border border-neutral-200 space-y-1.5 shadow-2xs">
              <div className="flex items-center gap-2 font-bold text-[#171717]">
                <ShieldCheck className="w-4 h-4 text-[#6C3FC5]" />
                <span>Patient Data Privacy</span>
              </div>
              <p>Informed consent captured at registration, zero third-party advertising or profiling, DPDP Act 2023 compliant.</p>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Simulated Clinical Showcase (Interactive Quick Load) */}
      <section className="py-14 sm:py-20 px-4 sm:px-6 bg-white border-b border-neutral-200">
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6C3FC5] bg-[#F3EEFC] px-3 py-1 rounded-full">
                Interactive Profiles
              </span>
              <h2 className="text-2xl sm:text-3xl font-sans font-bold text-[#171717] mt-2">
                Simulated Clinical Data
              </h2>
              <p className="text-xs sm:text-sm text-[#666666]">
                Click any patient below to view their journey, uploaded documents, clinical history, and physician review.
              </p>
            </div>
            <span className="text-xs text-[#666666] font-mono bg-neutral-100 px-3 py-1.5 rounded-lg border border-neutral-200">
              ABDM Sandbox Verified
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" suppressHydrationWarning>
            {mounted && demoPatients.slice(0, 4).map((patient) => (
              <div
                key={patient.id}
                onClick={() => onSelectPresetPatient && onSelectPresetPatient(patient)}
                className="cursor-pointer p-4 rounded-xl border border-neutral-200 hover:border-[#6C3FC5] bg-white hover:bg-[#F3EEFC]/20 transition-all shadow-2xs hover:shadow-xs group"
              >
                <div className="flex items-start justify-between mb-2">
                  <span className="text-xs font-mono font-bold text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded">
                    {patient.token}
                  </span>
                  {patient.isPriority && (
                    <span className="text-[10px] font-bold text-red-700 bg-red-100 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <AlertTriangle className="w-2.5 h-2.5" />
                      Priority Red Flag
                    </span>
                  )}
                </div>
                <h4 className="font-bold text-[#171717] group-hover:text-[#6C3FC5] transition-colors">
                  {patient.fullName}
                </h4>
                <div className="text-xs text-[#666666] mt-0.5">
                  {patient.age}y • {patient.gender} • {patient.city || 'India'}
                </div>
                <div className="text-xs font-medium text-[#171717] mt-2 pt-2 border-t border-neutral-100 flex items-center justify-between">
                  <span className="truncate max-w-[170px]">{patient.department}</span>
                  <ChevronRight className="w-4 h-4 text-[#666666] group-hover:translate-x-0.5 transition-transform" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. Minimal Footer */}
      <footer className="py-8 px-4 sm:px-6 bg-neutral-50 text-xs text-[#666666]">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-[#171717]">MediKiosk</span>
            <span>— Clinical History-Taking & Patient Intake Platform</span>
          </div>
          <div>
            <span>Smart India Hackathon • DPDP Act 2023 Compliant • ABDM & FHIR R4 Ready</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
