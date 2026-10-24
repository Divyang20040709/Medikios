'use client';

import React from 'react';
import Link from 'next/link';
import { staffEntryUrl } from '@/lib/auth';
import {
  UserRound,
  Sparkles,
  Stethoscope,
  ArrowUpRight,
  ArrowDown,
  Clock3,
  Languages,
  FileScan,
  ShieldCheck,
} from 'lucide-react';
import { FloatingKioskCard } from './FloatingKioskCard';
import { FloatingTimelineCard } from './FloatingTimelineCard';
import { TriageAlertBadge } from './TriageAlertBadge';
import { TelemetryMicroCard } from './TelemetryMicroCard';

interface LandingHeroProps {
  onLearnMore?: () => void;
}

export const LandingHero: React.FC<LandingHeroProps> = ({ onLearnMore }) => {
  return (
    <section className="relative min-h-screen w-full flex flex-col justify-between overflow-hidden">
      {/* 1. BACKGROUND FULL-VIEWPORT VIDEO WITH OPTIMIZED OVERLAY */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="h-full w-full object-cover"
        >
          <source
            src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260715_082433_69699cf8-444b-4484-93cc-053e57896dfd.mp4"
            type="video/mp4"
          />
        </video>
        {/* Recommended bg-black/45 dark overlay */}
        <div className="absolute inset-0 bg-black/50" />
        {/* Subtle cyan/teal central radial glow */}
        <div className="absolute inset-0 medical-ambient-glow" />
      </div>

      {/* 2. HERO CONTENT GRID */}
      <div className="relative z-10 w-full max-w-7xl mx-auto px-5 sm:px-8 md:px-16 lg:px-20 pt-8 sm:pt-14 md:pt-16 pb-12 flex-1 flex flex-col justify-center">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-8 items-center">
          
          {/* LEFT COLUMN: HERO TEXT & ACTIONS */}
          <div className="lg:col-span-7 flex flex-col items-start max-w-3xl">
            
            {/* PRODUCT STATUS BADGE WITH 3 OVERLAPPING ICONS */}
            <div className="rounded-full liquid-glass inline-flex items-center gap-3 px-3 py-1.5 sm:px-4 sm:py-2 mb-5 sm:mb-6">
              <div className="flex -space-x-2 overflow-hidden">
                <div className="h-6 w-6 rounded-full bg-cyan-950/80 border-2 border-white/20 flex items-center justify-center text-cyan-300">
                  <UserRound className="h-3 w-3" />
                </div>
                <div className="h-6 w-6 rounded-full bg-teal-950/80 border-2 border-white/20 flex items-center justify-center text-teal-300">
                  <Sparkles className="h-3 w-3" />
                </div>
                <div className="h-6 w-6 rounded-full bg-blue-950/80 border-2 border-white/20 flex items-center justify-center text-blue-300">
                  <Stethoscope className="h-3 w-3" />
                </div>
              </div>
              <span className="text-xs sm:text-sm font-light text-white/80">
                AI-assisted clinical intake
              </span>
            </div>

            {/* DOMINANT MAIN HEADING */}
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[1.05] text-white tracking-[-0.05em]">
              Smarter History.
              <br />
              Faster Care.
            </h1>

            {/* SUBTITLE */}
            <p className="mt-4 sm:mt-5 text-sm sm:text-base md:text-lg font-light text-white/70 max-w-xl leading-relaxed">
              AI-powered patient history taking, medical document digitization, and physician-ready clinical summaries.
            </p>

            {/* PRIMARY & SECONDARY ACTIONS */}
            <div className="mt-6 sm:mt-8 flex flex-wrap items-center gap-4 sm:gap-6">
              <Link
                href="/patient/intake"
                className="liquid-glass liquid-glass-hover px-6 py-3 sm:px-7 sm:py-3.5 rounded-full text-sm font-medium text-white flex items-center gap-2 group shadow-[0_0_25px_rgba(0,242,254,0.15)]"
              >
                <span>Start Patient Intake</span>
                <ArrowUpRight className="h-4 w-4 text-cyan-300 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </Link>

              {onLearnMore && (
                <button
                  onClick={onLearnMore}
                  className="text-sm font-light text-white/70 hover:text-white flex items-center gap-1.5 transition-colors py-2 px-3"
                >
                  <span>See how it works</span>
                  <ArrowDown className="h-3.5 w-3.5 text-white/50" />
                </button>
              )}

              <Link
                href={staffEntryUrl('/doctor')}
                className="text-sm font-light text-teal-300/80 hover:text-teal-200 flex items-center gap-1.5 transition-colors py-2 px-3 border border-teal-400/20 rounded-full"
              >
                <Stethoscope className="h-3.5 w-3.5" />
                <span>Doctor Workspace</span>
              </Link>
            </div>
          </div>

          {/* RIGHT COLUMN: 3D FLOATING INTERFACE COMPOSITION */}
          <div className="lg:col-span-5 relative flex flex-col items-center justify-center lg:items-end">
            
            {/* Top Micro Telemetry */}
            <div className="mb-4 self-center lg:self-end">
              <TelemetryMicroCard />
            </div>

            {/* Main Interactive Floating Kiosk Card */}
            <div className="relative animate-float">
              <FloatingKioskCard />

              {/* Offset Timeline Card Layered Behind / Beside */}
              <div className="hidden sm:block absolute -bottom-10 -left-12 lg:-left-20 z-0 animate-float-delayed">
                <FloatingTimelineCard />
              </div>

              {/* Triage Alert Badge Float */}
              <div className="absolute -top-6 -right-4 z-20">
                <TriageAlertBadge />
              </div>
            </div>

          </div>

        </div>
      </div>

      {/* 3. BOTTOM INFORMATION BAR */}
      <div className="relative z-10 w-full max-w-7xl mx-auto px-5 sm:px-8 md:px-16 lg:px-20 pb-8 pt-4 border-t border-white/10">
        <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-6">
          
          {/* THREE STATS */}
          <div className="flex flex-wrap items-center gap-8 sm:gap-12 md:gap-16">
            {/* STAT 1 */}
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded-full liquid-glass flex items-center justify-center text-cyan-400">
                <Clock3 className="h-4 w-4" />
              </div>
              <div className="text-left">
                <span className="block text-xs sm:text-sm font-medium text-white">Minutes Saved</span>
                <span className="block text-[11px] text-white/60 font-light">Per Consultation</span>
              </div>
            </div>

            {/* STAT 2 */}
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded-full liquid-glass flex items-center justify-center text-teal-400">
                <Languages className="h-4 w-4" />
              </div>
              <div className="text-left">
                <span className="block text-xs sm:text-sm font-medium text-white">Multilingual</span>
                <span className="block text-[11px] text-white/60 font-light">Voice + Touch Intake</span>
              </div>
            </div>

            {/* STAT 3 */}
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded-full liquid-glass flex items-center justify-center text-indigo-400">
                <FileScan className="h-4 w-4" />
              </div>
              <div className="text-left">
                <span className="block text-xs sm:text-sm font-medium text-white">Digital Records</span>
                <span className="block text-[11px] text-white/60 font-light">Prescriptions & Reports</span>
              </div>
            </div>
          </div>

          {/* RIGHT TRUST & LOCALIZATION LABELS */}
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3 sm:gap-8 text-left sm:text-right">
            <div>
              <span className="block text-xs font-light text-white/50">Designed for high-volume hospital OPDs</span>
              <span className="block text-[11px] font-mono text-cyan-400/70 tracking-wider">
                ABDM • FHIR • Consent-first
              </span>
            </div>
            
            <div className="hidden lg:block border-l border-white/10 pl-4">
              <span className="block text-xs font-light text-white/50">
                Built for India’s multilingual healthcare ecosystem
              </span>
              <span className="block text-[10px] text-teal-400/60 font-mono">
                🇮🇳 DPDP Act 2023 Compliant
              </span>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
};
