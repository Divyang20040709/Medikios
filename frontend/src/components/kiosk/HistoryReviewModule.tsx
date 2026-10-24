'use client';

import React, { useState } from 'react';
import {
  FileText,
  AlertTriangle,
  CheckSquare,
  Square,
  ArrowRight,
  ArrowLeft,
  Edit2,
  FileCheck,
  ShieldCheck,
  CheckCircle2
} from 'lucide-react';
import { Patient, ClinicalCase, DocumentItem } from '@/lib/types';
import { clinicalStore } from '@/lib/clinicalStore';

interface HistoryReviewModuleProps {
  patient: Patient;
  clinicalCase?: ClinicalCase;
  documents: DocumentItem[];
  onConfirm: () => void;
  onEdit: () => void;
  onBack: () => void;
}

export function HistoryReviewModule({
  patient,
  clinicalCase,
  documents,
  onConfirm,
  onEdit,
  onBack,
}: HistoryReviewModuleProps) {
  const [confirmed, setConfirmed] = useState(true);

  const handleSubmit = () => {
    if (!confirmed) return;
    clinicalStore.updatePatientStatus(patient.id, 'waiting');
    onConfirm();
  };

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            Clinical History Review
          </span>
          <span className="font-mono bg-[#F3EEFC] text-[#6C3FC5] px-2 py-0.5 rounded border border-[#6C3FC5]/20">
            {patient.fullName} ({patient.id})
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          Your Clinical History
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          Review your structured intake summary before finalizing. You may edit any field.
        </p>
      </div>

      {/* Safety Notice */}
      <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="space-y-1 text-xs">
          <span className="font-bold">Needs Physician Verification</span>
          <p className="text-amber-800 leading-relaxed">
            AI-generated draft. Requires verification by a healthcare professional. MediKiosk does not autonomously diagnose or prescribe medication.
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="space-y-4">
        {/* Chief Complaint */}
        <div className="p-5 rounded-xl border border-neutral-200 bg-white space-y-2 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-[#666666]">
              Chief Complaint:
            </span>
            <button
              type="button"
              onClick={onEdit}
              className="text-xs text-[#6C3FC5] hover:underline flex items-center gap-1 font-semibold"
            >
              <Edit2 className="w-3 h-3" />
              <span>Edit</span>
            </button>
          </div>
          <p className="text-base font-bold text-[#171717]">
            {clinicalCase?.chiefComplaints?.[0]?.complaint || 'No complaint logged'}
          </p>
          <div className="text-xs text-[#666666]">
            Duration: <strong>{clinicalCase?.chiefComplaints?.[0]?.duration || 'N/A'}</strong> • Severity:{' '}
            <strong>{clinicalCase?.chiefComplaints?.[0]?.severity || 5}/10</strong>
          </div>
        </div>

        {/* SOCRATES Breakdown */}
        {clinicalCase?.socrates && (
          <div className="p-5 rounded-xl border border-neutral-200 bg-white space-y-3 shadow-2xs text-xs">
            <span className="font-bold uppercase tracking-wider text-[#666666] block">
              SOCRATES Analysis:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[#171717]">
              <div>
                <span className="text-[#666666] block">Site:</span>
                <span className="font-medium">{clinicalCase.socrates.site}</span>
              </div>
              <div>
                <span className="text-[#666666] block">Onset:</span>
                <span className="font-medium">{clinicalCase.socrates.onset}</span>
              </div>
              <div>
                <span className="text-[#666666] block">Character:</span>
                <span className="font-medium">{clinicalCase.socrates.character}</span>
              </div>
              <div>
                <span className="text-[#666666] block">Radiation:</span>
                <span className="font-medium">{clinicalCase.socrates.radiation}</span>
              </div>
              <div className="sm:col-span-2">
                <span className="text-[#666666] block">Associated Symptoms:</span>
                <span className="font-medium">{clinicalCase.socrates.associations.join(', ')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Past Conditions & Meds */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="p-5 rounded-xl border border-neutral-200 bg-white space-y-2 shadow-2xs">
            <span className="font-bold uppercase tracking-wider text-[#666666] block">
              Medical Conditions:
            </span>
            {clinicalCase?.pastMedicalHistory && clinicalCase.pastMedicalHistory.length > 0 ? (
              <ul className="list-disc list-inside space-y-1 text-[#171717]">
                {clinicalCase.pastMedicalHistory.map((c) => (
                  <li key={c.id}>
                    <strong>{c.condition}</strong> ({c.diagnosedYear})
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[#666666]">No chronic conditions reported.</p>
            )}
          </div>

          <div className="p-5 rounded-xl border border-neutral-200 bg-white space-y-2 shadow-2xs">
            <span className="font-bold uppercase tracking-wider text-[#666666] block">
              Current Medications:
            </span>
            {clinicalCase?.medications && clinicalCase.medications.length > 0 ? (
              <ul className="list-disc list-inside space-y-1 text-[#171717]">
                {clinicalCase.medications.map((m) => (
                  <li key={m.id}>
                    <strong>{m.name}</strong> - {m.dose} ({m.frequency})
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[#666666]">No active medications logged.</p>
            )}
          </div>
        </div>

        {/* AYUSH Assessment (if applicable) */}
        {clinicalCase?.ayushAssessment && (
          <div className="p-5 rounded-xl border border-emerald-200 bg-emerald-50/40 space-y-2 shadow-2xs text-xs">
            <span className="font-bold uppercase tracking-wider text-emerald-800 block">
              AYUSH Dashavidha Pariksha Summary:
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[#171717]">
              <div>
                <span className="text-[#666666] block">Prakriti:</span>
                <strong>{clinicalCase.ayushAssessment.prakriti}</strong>
              </div>
              <div>
                <span className="text-[#666666] block">Agni:</span>
                <strong>{clinicalCase.ayushAssessment.agni}</strong>
              </div>
              <div>
                <span className="text-[#666666] block">Koshtha:</span>
                <strong>{clinicalCase.ayushAssessment.koshtha}</strong>
              </div>
              <div>
                <span className="text-[#666666] block">Sara / Bala:</span>
                <strong>{clinicalCase.ayushAssessment.sara}</strong>
              </div>
            </div>
          </div>
        )}

        {/* Attached Documents */}
        <div className="p-5 rounded-xl border border-neutral-200 bg-white space-y-2 shadow-2xs text-xs">
          <span className="font-bold uppercase tracking-wider text-[#666666] block">
            Attached Documents ({documents.length}):
          </span>
          {documents.length > 0 ? (
            <div className="space-y-1.5">
              {documents.map((d) => (
                <div key={d.id} className="flex items-center justify-between py-1 border-b border-neutral-100 last:border-0">
                  <span className="font-medium text-[#171717]">{d.title}</span>
                  <span className="text-[#6C3FC5] font-semibold">{d.documentType}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[#666666]">No previous documents attached.</p>
          )}
        </div>
      </div>

      {/* Confirmation Checkbox */}
      <div
        onClick={() => setConfirmed(!confirmed)}
        className="cursor-pointer p-4 rounded-xl border border-neutral-200 bg-white flex items-start gap-3 shadow-2xs"
      >
        <div className="mt-0.5 text-[#6C3FC5]">
          {confirmed ? <CheckSquare className="w-5 h-5" /> : <Square className="w-5 h-5 text-neutral-400" />}
        </div>
        <p className="text-xs text-[#171717] leading-relaxed select-none">
          I confirm that the above information accurately reflects my symptoms and medical history. I understand that my doctor will review this summary during consultation.
        </p>
      </div>

      {/* Buttons */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Documents</span>
        </button>

        <button
          type="button"
          disabled={!confirmed}
          onClick={handleSubmit}
          className={`flex items-center gap-2 px-7 py-3 rounded-xl text-xs sm:text-sm font-bold transition-all ${
            confirmed
              ? 'bg-[#6C3FC5] hover:bg-[#4B238C] text-white shadow-sm hover:shadow-md active:scale-[0.99]'
              : 'bg-neutral-200 text-neutral-400 cursor-not-allowed'
          }`}
        >
          <span>Submit & Generate OPD Token</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
