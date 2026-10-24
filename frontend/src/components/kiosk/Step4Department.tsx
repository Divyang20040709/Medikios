'use client';

import React from 'react';
import { Stethoscope, Flower2, ArrowRight, ArrowLeft, CheckCircle2 } from 'lucide-react';
import { ConsultationType, LanguageCode } from '@/lib/types';
import { t } from '@/lib/i18n';

interface Step4DepartmentProps {
  consultationType: ConsultationType;
  onSelectType: (type: ConsultationType) => void;
  onContinue: () => void;
  onBack: () => void;
  patientName?: string;
  language?: LanguageCode;
}

export function Step4Department({
  consultationType,
  onSelectType,
  onContinue,
  onBack,
  patientName,
  language = 'en',
}: Step4DepartmentProps) {
  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            {t('s4.stepLabel', language)}
          </span>
          {patientName && (
            <span className="text-[#171717] font-medium">{t('s4.patientLabel', language)} {patientName}</span>
          )}
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('s4.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('s4.sub', language)}
        </p>
      </div>

      {/* Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {/* Modern Medicine */}
        <div
          onClick={() => onSelectType('modern')}
          className={`cursor-pointer p-6 rounded-2xl border-2 transition-all flex flex-col justify-between space-y-4 ${
            consultationType === 'modern'
              ? 'border-[#6C3FC5] bg-[#F3EEFC]/50 shadow-md ring-1 ring-[#6C3FC5]'
              : 'border-neutral-200 hover:border-[#6C3FC5]/40 hover:bg-[#F3EEFC]/20 bg-white shadow-2xs'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="w-12 h-12 rounded-xl bg-white border border-neutral-200 flex items-center justify-center text-[#6C3FC5] shadow-xs">
              <Stethoscope className="w-6 h-6" />
            </div>
            {consultationType === 'modern' && (
              <span className="text-xs font-bold text-[#6C3FC5] bg-white px-2 py-0.5 rounded-full border border-[#6C3FC5]/30">
                {t('s4.selected', language)}
              </span>
            )}
          </div>

          <div className="space-y-1.5">
            <h3 className="text-lg font-bold text-[#171717]">{t('s4.modernTitle', language)}</h3>
            <p className="text-xs text-[#666666] leading-relaxed">
              {t('s4.modernDesc', language)}
            </p>
          </div>

          <div className="pt-2 border-t border-neutral-200/60 flex items-center gap-1.5 text-xs text-[#6C3FC5] font-semibold">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>{t('s4.modernFoot', language)}</span>
          </div>
        </div>

        {/* Traditional / AYUSH */}
        <div
          onClick={() => onSelectType('ayush')}
          className={`cursor-pointer p-6 rounded-2xl border-2 transition-all flex flex-col justify-between space-y-4 ${
            consultationType === 'ayush'
              ? 'border-[#6C3FC5] bg-[#F3EEFC]/50 shadow-md ring-1 ring-[#6C3FC5]'
              : 'border-neutral-200 hover:border-[#6C3FC5]/40 hover:bg-[#F3EEFC]/20 bg-white shadow-2xs'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="w-12 h-12 rounded-xl bg-white border border-neutral-200 flex items-center justify-center text-emerald-600 shadow-xs">
              <Flower2 className="w-6 h-6" />
            </div>
            {consultationType === 'ayush' && (
              <span className="text-xs font-bold text-[#6C3FC5] bg-white px-2 py-0.5 rounded-full border border-[#6C3FC5]/30">
                {t('s4.selected', language)}
              </span>
            )}
          </div>

          <div className="space-y-1.5">
            <h3 className="text-lg font-bold text-[#171717]">{t('s4.ayushTitle', language)}</h3>
            <p className="text-xs text-[#666666] leading-relaxed">
              {t('s4.ayushDesc', language)}
            </p>
          </div>

          <div className="pt-2 border-t border-neutral-200/60 flex items-center gap-1.5 text-xs text-emerald-700 font-semibold">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>{t('s4.ayushFoot', language)}</span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('s4.back', language)}</span>
        </button>

        <button
          type="button"
          onClick={onContinue}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>{t('s4.continue', language)}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
