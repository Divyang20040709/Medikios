'use client';

import React from 'react';
import { Globe, ArrowRight, ArrowLeft, Clock } from 'lucide-react';
import { LanguageCode } from '@/lib/types';
import { t } from '@/lib/i18n';

interface Step1LanguageProps {
  currentLanguage: LanguageCode;
  onSelectLanguage: (lang: LanguageCode) => void;
  onContinue: () => void;
  onBack: () => void;
}

export function Step1Language({
  currentLanguage,
  onSelectLanguage,
  onContinue,
  onBack,
}: Step1LanguageProps) {
  const languages: Array<{
    code: LanguageCode;
    native: string;
    label: string;
    greeting: string;
    subtext: string;
  }> = [
    {
      code: 'en',
      native: 'English',
      label: 'English',
      greeting: 'Welcome to MediKiosk',
      subtext: 'Medical terms in simple conversational English',
    },
    {
      code: 'hi',
      native: 'हिन्दी',
      label: 'Hindi',
      greeting: 'मेडीकिओस्क में आपका स्वागत है',
      subtext: 'सरल हिन्दी में अपनी स्वास्थ्य समस्याओं की जानकारी दें',
    },
    {
      code: 'gu',
      native: 'ગુજરાતી',
      label: 'Gujarati',
      greeting: 'મેડીકિયોસ્કમાં તમારું સ્વાગત છે',
      subtext: 'સરળ ગુજરાતીમાં તમારા લક્ષણો અને આરોગ્ય વિગતો જણાવો',
    },
  ];

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Step Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">{t('s1.stepLabel', currentLanguage)}</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {t('s1.estTime', currentLanguage)}
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('s1.title', currentLanguage)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('s1.sub', currentLanguage)}
        </p>
      </div>

      {/* Language Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {languages.map((item) => {
          const isSelected = currentLanguage === item.code;
          return (
            <div
              key={item.code}
              onClick={() => onSelectLanguage(item.code)}
              className={`cursor-pointer p-5 rounded-xl border-2 transition-all flex flex-col justify-between space-y-4 ${
                isSelected
                  ? 'border-[#6C3FC5] bg-[#F3EEFC]/50 shadow-sm'
                  : 'border-neutral-200 hover:border-[#6C3FC5]/40 hover:bg-[#F3EEFC]/20 bg-white'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-xl sm:text-2xl font-bold text-[#171717]">
                    {item.native}
                  </h3>
                  <span className="text-xs text-[#666666] font-medium">{item.label}</span>
                </div>
                <div
                  className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                    isSelected ? 'border-[#6C3FC5] bg-[#6C3FC5]' : 'border-neutral-300'
                  }`}
                >
                  {isSelected && <span className="w-2 h-2 rounded-full bg-white" />}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-[#171717]">{item.greeting}</p>
                <p className="text-xs text-[#666666] mt-0.5">{item.subtext}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Navigation Buttons */}
      <div className="pt-6 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('s1.back', currentLanguage)}</span>
        </button>

        <button
          type="button"
          onClick={onContinue}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>{t('s1.continue', currentLanguage)}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
