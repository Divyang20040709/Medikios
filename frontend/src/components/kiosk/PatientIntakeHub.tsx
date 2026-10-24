'use client';

import React from 'react';
import { FileText, Upload, ArrowRight, ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-react';
import { Patient, LanguageCode } from '@/lib/types';
import { t } from '@/lib/i18n';

interface PatientIntakeHubProps {
  patient: Patient;
  hasCaseHistory?: boolean;
  onStartHistory: () => void;
  onGoToDocuments: () => void;
  onBack?: () => void;
  language?: LanguageCode;
}

export function PatientIntakeHub({
  patient,
  hasCaseHistory = false,
  onStartHistory,
  onGoToDocuments,
  onBack,
  language = 'en',
}: PatientIntakeHubProps) {
  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            {t('hub.stepLabel', language)}
          </span>
          <span className="font-mono bg-[#F3EEFC] text-[#6C3FC5] px-2 py-0.5 rounded border border-[#6C3FC5]/20">
            {t('hub.token', language)} {patient.token}
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('hub.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('hub.patientLine', language)} <strong className="text-[#171717]">{patient.fullName}</strong> ({patient.id}) • {patient.department}
        </p>
      </div>

      {/* Action Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {/* Start Symptom Intake */}
        <div
          onClick={onStartHistory}
          className="cursor-pointer p-6 rounded-2xl border-2 border-neutral-200 hover:border-[#6C3FC5] bg-white hover:bg-[#F3EEFC]/20 transition-all flex flex-col justify-between space-y-4 shadow-2xs hover:shadow-md group"
        >
          <div className="w-12 h-12 rounded-xl bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
            <FileText className="w-6 h-6" />
          </div>

          <div className="space-y-1.5">
            <h3 className="text-lg font-bold text-[#171717] group-hover:text-[#6C3FC5] transition-colors">
              {t('hub.c1Title', language)}
            </h3>
            <p className="text-xs text-[#666666] leading-relaxed">
              {t('hub.c1Desc', language)}
            </p>
          </div>

          <div className="pt-3 border-t border-neutral-100 flex items-center justify-between text-xs font-bold text-[#6C3FC5]">
            <span>{hasCaseHistory ? t('hub.c1Edit', language) : t('hub.c1Start', language)}</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        {/* Upload Medical Documents */}
        <div
          onClick={onGoToDocuments}
          className="cursor-pointer p-6 rounded-2xl border-2 border-neutral-200 hover:border-[#6C3FC5] bg-white hover:bg-[#F3EEFC]/20 transition-all flex flex-col justify-between space-y-4 shadow-2xs hover:shadow-md group"
        >
          <div className="w-12 h-12 rounded-xl bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
            <Upload className="w-6 h-6" />
          </div>

          <div className="space-y-1.5">
            <h3 className="text-lg font-bold text-[#171717] group-hover:text-[#6C3FC5] transition-colors">
              {t('hub.c2Title', language)}
            </h3>
            <p className="text-xs text-[#666666] leading-relaxed">
              {t('hub.c2Desc', language)}
            </p>
          </div>

          <div className="pt-3 border-t border-neutral-100 flex items-center justify-between text-xs font-bold text-[#6C3FC5]">
            <span>{t('hub.c2Action', language)}</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </div>
        </div>
      </div>

      <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-200 text-xs text-[#666666] flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-[#6C3FC5] flex-shrink-0" />
        <span>
          {t('hub.note', language)}
        </span>
      </div>

      {onBack && (
        <div className="pt-4 border-t border-neutral-200 flex items-center">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>{t('hub.back', language)}</span>
          </button>
        </div>
      )}
    </div>
  );
}
