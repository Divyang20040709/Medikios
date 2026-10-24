'use client';

import React from 'react';
import { CheckCircle2, Printer, ArrowRight, Building2, Clock, QrCode } from 'lucide-react';
import { Patient, LanguageCode } from '@/lib/types';
import { t } from '@/lib/i18n';

interface TokenConfirmationSlipProps {
  patient: Patient;
  onDone: () => void;
  language?: LanguageCode;
}

export function TokenConfirmationSlip({ patient, onDone, language = 'en' }: TokenConfirmationSlipProps) {
  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="max-w-2xl mx-auto w-full px-4 sm:px-6 py-10 sm:py-16 flex flex-col items-center text-center space-y-8 animate-in fade-in duration-200">
      {/* Success Badge */}
      <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center shadow-xs">
        <CheckCircle2 className="w-9 h-9" />
      </div>

      <div className="space-y-2">
        <h2 className="text-3xl sm:text-4xl font-serif font-bold text-[#171717]">
          {t('tk.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666] max-w-md mx-auto">
          {t('tk.sub', language)}
        </p>
      </div>

      {/* Printable Consultation Slip Card */}
      <div
        id="print-slip"
        className="w-full bg-white rounded-2xl border-2 border-dashed border-[#6C3FC5]/40 p-6 sm:p-8 text-left space-y-6 shadow-sm relative overflow-hidden"
      >
        <div className="flex items-center justify-between border-b border-neutral-200 pb-4">
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-[#6C3FC5]">
              {t('tk.tokenHeading', language)}
            </div>
            <h3 className="text-lg font-bold text-[#171717]">{patient.fullName}</h3>
            <span className="text-xs text-[#666666]">
              ID: {patient.id} • {patient.age}y {patient.gender}
              {patient.mrn && <span className="block">MRN: {patient.mrn}</span>}
            </span>
          </div>

          <div className="text-right">
            <span className="text-3xl sm:text-4xl font-mono font-black text-[#6C3FC5]">
              {patient.token}
            </span>
            <div className="text-[10px] font-mono text-[#666666] mt-0.5">TOKEN NUMBER</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-xs">
          <div className="space-y-1">
            <span className="text-[#666666] flex items-center gap-1 font-semibold">
              <Building2 className="w-3.5 h-3.5 text-[#6C3FC5]" />
              {t('tk.location', language)}
            </span>
            <strong className="text-sm text-[#171717] block">
              {patient.counterNumber || 'OPD Room 104, Block B'}
            </strong>
          </div>

          <div className="space-y-1">
            <span className="text-[#666666] flex items-center gap-1 font-semibold">
              <Clock className="w-3.5 h-3.5 text-[#6C3FC5]" />
              {t('tk.wait', language)}
            </span>
            <strong className="text-sm text-[#171717] block">
              ~{patient.estimatedWaitMinutes || 15} {t('tk.mins', language)}
            </strong>
          </div>

          <div className="col-span-2 pt-2 border-t border-neutral-100 space-y-1">
            <span className="text-[#666666] block">{t('tk.dept', language)}</span>
            <span className="font-bold text-[#171717]">{patient.department}</span>
          </div>

          {/* Routed appointment: the physician whose stream the patient chose at
              Step 4 (General & Modern Medicine vs Traditional / AYUSH). */}
          {patient.assignedDoctorName && (
            <div className="col-span-2 pt-2 border-t border-neutral-100 space-y-1">
              <span className="text-[#666666] block">{t('tk.doctor', language)}</span>
              <span className="font-bold text-[#171717]">{patient.assignedDoctorName}</span>
            </div>
          )}
        </div>

        <div className="p-3 bg-[#F3EEFC]/60 rounded-xl border border-[#6C3FC5]/20 text-xs text-[#666666] leading-relaxed">
          {t('tk.instructions', language)}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center justify-center gap-3 w-full sm:w-auto">
        <button
          type="button"
          onClick={handlePrint}
          className="flex items-center justify-center gap-2 px-6 py-3 bg-white border border-neutral-300 hover:border-[#6C3FC5] text-[#171717] text-xs sm:text-sm font-bold rounded-xl transition-colors shadow-2xs"
        >
          <Printer className="w-4 h-4 text-[#6C3FC5]" />
          <span>{t('tk.print', language)}</span>
        </button>

        <button
          type="button"
          onClick={onDone}
          className="flex items-center justify-center gap-2 px-8 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>{t('tk.finish', language)}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
