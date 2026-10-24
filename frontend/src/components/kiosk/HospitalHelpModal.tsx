'use client';

import React from 'react';
import { HelpCircle, PhoneCall, X } from 'lucide-react';
import { useModalDialog } from '@/lib/useModalDialog';

interface HospitalHelpModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function HospitalHelpModal({ isOpen, onClose }: HospitalHelpModalProps) {
  // QA-12: dialog semantics, Escape-to-close, focus trap and focus restore.
  const { dialogRef, onBackdropClick } = useModalDialog(isOpen, { onClose });

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onBackdropClick}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mk-help-title"
        aria-describedby="mk-help-desc"
        tabIndex={-1}
        className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-neutral-200 animate-in fade-in zoom-in-95 duration-150 outline-none"
      >
        <div className="flex items-start justify-between pb-3 border-b border-neutral-100">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 id="mk-help-title" className="text-base sm:text-lg font-bold text-[#171717]">Hospital Kiosk Assistance</h3>
              <p className="text-xs text-[#666666]">MediKiosk Help & Guidance</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close help dialog"
            className="text-[#666666] hover:text-[#171717] text-lg font-bold p-1 rounded-md"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div id="mk-help-desc" className="py-4 space-y-3 text-[#171717] text-sm leading-relaxed">
          <p className="font-semibold text-sm text-[#171717]">Need help? Ask a hospital staff member.</p>
          <p className="text-[#666666] text-xs sm:text-sm">
            Hospital &apos;Swasthya Mitras&apos; and reception volunteers are stationed at the OPD entry gate to assist with voice input, translation, and uploading paper documents.
          </p>
          <div className="p-3 bg-[#F3EEFC] rounded-lg border border-[#6C3FC5]/20 flex items-center gap-3">
            <PhoneCall className="w-5 h-5 text-[#6C3FC5] flex-shrink-0" />
            <div>
              <div className="text-xs text-[#666666] font-medium">OPD Triage Helpline</div>
              <div className="text-sm font-bold text-[#171717]">+91 11 2658 8500 (Ext. 402)</div>
            </div>
          </div>
          <p className="text-xs text-[#666666]">
            Notice: MediKiosk is designed to assist clinical history intake. All collected information is verified by a qualified physician.
          </p>
        </div>

        <div className="pt-3 border-t border-neutral-100 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-5 py-2 bg-[#6C3FC5] hover:bg-[#4B238C] text-white rounded-lg font-semibold text-xs sm:text-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
