'use client';

import React from 'react';
import { Shield, MessageSquareText, FileText, CheckCircle2 } from 'lucide-react';

export const HowItWorksSection: React.FC = () => {
  const steps = [
    {
      number: '01',
      title: 'Consent & Identification',
      description: 'Patient registers using ABHA ID, Mobile, or Aadhaar. Granular DPDP-compliant consent is secured before collecting any clinical data.',
      icon: Shield,
      accent: 'text-cyan-400',
    },
    {
      number: '02',
      title: 'Multilingual Clinical Intake',
      description: 'Voice and touch kiosk experience powered by adaptive SOCRATES question trees across 10 Indian languages. Emergency red-flags are detected in real time.',
      icon: MessageSquareText,
      accent: 'text-teal-400',
    },
    {
      number: '03',
      title: 'Prescription & Report OCR',
      description: 'Physical prescriptions and laboratory reports are scanned and digitized. Extracted entities carry confidence scores to maintain clinical provenance.',
      icon: FileText,
      accent: 'text-indigo-400',
    },
    {
      number: '04',
      title: 'Physician Review & ABDM Export',
      description: 'Doctors receive structured drafts with timeline and memory graph relations. Clinicians review, edit, and sign off before persistent ABDM/FHIR sync.',
      icon: CheckCircle2,
      accent: 'text-emerald-400',
    },
  ];

  return (
    <section id="how-it-works" className="relative py-24 px-5 sm:px-8 md:px-16 lg:px-20 border-t border-white/10 bg-[#070D16]">
      <div className="max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <span className="text-xs uppercase tracking-widest font-mono text-cyan-400 font-semibold">
            Workflow Architecture
          </span>
          <h2 className="text-3xl sm:text-4xl font-normal tracking-tight text-white mt-3">
            From Kiosk to Consultation
          </h2>
          <p className="mt-4 text-sm sm:text-base text-white/70 font-light">
            Patient speaks → AI structures the history → medical records are organized → doctor gets a better consultation.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, idx) => {
            const Icon = step.icon;
            return (
              <div
                key={step.number}
                className="liquid-glass rounded-3xl p-6 relative group transition-all duration-300 hover:-translate-y-1 hover:bg-white/[0.04]"
              >
                <div className="flex items-center justify-between mb-6">
                  <span className="font-mono text-2xl font-light text-white/30 group-hover:text-cyan-400/80 transition-colors">
                    {step.number}
                  </span>
                  <div className={`h-10 w-10 rounded-2xl liquid-glass flex items-center justify-center ${step.accent}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                </div>

                <h3 className="text-lg font-medium text-white mb-2">{step.title}</h3>
                <p className="text-xs sm:text-sm text-white/65 font-light leading-relaxed">
                  {step.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
