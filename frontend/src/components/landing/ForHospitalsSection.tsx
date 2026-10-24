'use client';

import React from 'react';
import Link from 'next/link';
import { Building2, Network, ShieldAlert, Cpu, Check, ArrowRight } from 'lucide-react';
import { staffEntryUrl } from '@/lib/auth';

export const ForHospitalsSection: React.FC = () => {
  const capabilities = [
    {
      icon: Building2,
      title: 'High-Volume OPD Scalability',
      description: 'Built for government and private hospital OPDs handling thousands of daily registrations. Reduces consultation history-taking by 60–80%.',
    },
    {
      icon: Network,
      title: 'Doctor Memory Graph',
      description: 'Longitudinal relationship graph linking chronic conditions, active medications, allergies, and lab trends across encounters to avoid repetitive questioning.',
    },
    {
      icon: ShieldAlert,
      title: 'Red-Flag Safety Triage',
      description: 'Predefined clinical emergency rules identify high-urgency symptoms immediately, escalating triage position while doctors retain all diagnostic authority.',
    },
    {
      icon: Cpu,
      title: 'ABDM & FHIR R4 Compliant',
      description: 'Native serializers generate compliant Patient, Encounter, Observation, and Medication bundles for Ayushman Bharat Digital Mission integration.',
    },
  ];

  return (
    <section id="for-hospitals" className="relative py-24 px-5 sm:px-8 md:px-16 lg:px-20 border-t border-white/10 bg-[#050A12]">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          
          <div className="lg:col-span-5 text-left">
            <span className="text-xs uppercase tracking-widest font-mono text-teal-400 font-semibold">
              Hospital Operations
            </span>
            <h2 className="text-3xl sm:text-4xl font-normal tracking-tight text-white mt-3 leading-tight">
              Clinical Quality at High OPD Volume
            </h2>
            <p className="mt-4 text-sm sm:text-base text-white/70 font-light leading-relaxed">
              When clinicians have only 2 to 4 minutes per patient, manual history taking leads to fragmented records. MediKiosk shifts data collection to the patient-facing kiosk, delivering structured, verified context before the patient enters the consultation room.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-stretch sm:items-center gap-4">
              <Link
                href={staffEntryUrl('/admin')}
                className="liquid-glass px-6 py-3 rounded-full text-sm font-medium text-white hover:bg-white/10 flex items-center justify-center gap-2 border border-white/10"
              >
                <span>Admin Operations Portal</span>
                <ArrowRight className="h-4 w-4 text-teal-300" />
              </Link>
            </div>
          </div>

          <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-2 gap-6">
            {capabilities.map((cap, i) => {
              const Icon = cap.icon;
              return (
                <div
                  key={cap.title}
                  className="liquid-glass rounded-3xl p-6 relative group transition-all duration-300 hover:bg-white/[0.04]"
                >
                  <div className="h-10 w-10 rounded-2xl liquid-glass flex items-center justify-center text-cyan-400 mb-4">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-base font-medium text-white mb-2">{cap.title}</h3>
                  <p className="text-xs sm:text-sm text-white/60 font-light leading-relaxed">
                    {cap.description}
                  </p>
                </div>
              );
            })}
          </div>

        </div>
      </div>
    </section>
  );
};
