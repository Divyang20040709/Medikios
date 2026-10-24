'use client';

import React, { useState } from 'react';
import {
  Upload,
  FileText,
  CheckCircle2,
  Loader2,
  Sparkles,
  ArrowRight,
  ArrowLeft,
  FileCheck,
  ShieldCheck,
} from 'lucide-react';
import { Patient, DocumentItem, ExtractedDocumentData, LanguageCode } from '@/lib/types';
import { clinicalStore, ClinicalRulesEngine } from '@/lib/clinicalStore';
import { t, chipLabel } from '@/lib/i18n';

interface DocumentScannerModuleProps {
  patient: Patient;
  documents: DocumentItem[];
  /** Phase 7: patient-facing scanner was untranslated English-only. */
  language?: LanguageCode;
  onDocumentsUpdated: (docs: DocumentItem[]) => void;
  onContinue: () => void;
  onBack: () => void;
}

export function DocumentScannerModule({
  patient,
  documents,
  language = 'en',
  onDocumentsUpdated,
  onContinue,
  onBack,
}: DocumentScannerModuleProps) {
  const [selectedCategory, setSelectedCategory] = useState<
    'Prescription' | 'Laboratory Report' | 'Discharge Summary' | 'Imaging Report'
  >('Prescription');

  const [isScanning, setIsScanning] = useState(false);
  const [scanStage, setScanStage] = useState('');
  const [extractedResult, setExtractedResult] = useState<ExtractedDocumentData | null>(null);
  // Demo (simulated) extractions end in 'verified'; real backend uploads always
  // stay unverified until a physician confirms them at the workstation.
  const [extractionVerified, setExtractionVerified] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ kind: 'success' | 'info' | 'error'; text: string } | null>(null);

  const simulateScan = async (title: string, category: any) => {
    setIsScanning(true);
    setExtractedResult(null);
    setStatusMessage(null);

    setScanStage(t('ds.stageRead', language));
    await new Promise((r) => setTimeout(r, 600));

    setScanStage(t('ds.stageExtract', language));
    await new Promise((r) => setTimeout(r, 700));

    setScanStage(t('ds.stageTaxonomy', language));
    const result = await ClinicalRulesEngine.simulateOcrExtraction(category, title);

    setScanStage(t('ds.stageTimeline', language));
    await new Promise((r) => setTimeout(r, 400));

    setIsScanning(false);
    setExtractionVerified(true);
    setExtractedResult(result);

    const newDoc: DocumentItem = {
      id: `DOC-${Date.now()}`,
      patientId: patient.id,
      title,
      documentType: category,
      documentDate: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
      fileUrl: '/docs/sample_doc.pdf',
      status: 'verified',
      extractedData: result,
      isVerifiedByPhysician: true,
    };

    clinicalStore.addDocument(newDoc);
    onDocumentsUpdated([newDoc, ...documents]);
  };

  // Frontend pre-checks mirror the backend validation in /api/documents/upload
  // (server-side checks remain authoritative — this only gives faster feedback).
  const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'];
  const MAX_UPLOAD_MB = 25;
  const CATEGORY_TO_BACKEND_TYPE: Record<string, string> = {
    Prescription: 'PRESCRIPTION',
    'Laboratory Report': 'LAB_REPORT',
    'Discharge Summary': 'DISCHARGE_SUMMARY',
    'Imaging Report': 'IMAGING',
  };

  const uploadToBackend = async (file: File, category: string) => {
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED_UPLOAD_EXTENSIONS.includes(ext)) {
      setStatusMessage({ kind: 'error', text: `"${ext}" — ${t('ds.errType', language)}` });
      setExtractedResult(null);
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setStatusMessage({ kind: 'error', text: t('ds.errSize', language) });
      return;
    }
    if (file.size === 0) {
      setStatusMessage({ kind: 'error', text: t('ds.errEmpty', language) });
      return;
    }

    setIsScanning(true);
    setExtractedResult(null);
    setStatusMessage(null);
    setScanStage(t('ds.stageUpload', language));

    const formData = new FormData();
    formData.append('file', file);
    formData.append('patient_id', patient.id);
    if (patient.encounterId) formData.append('encounter_id', patient.encounterId);
    formData.append('document_type', CATEGORY_TO_BACKEND_TYPE[category] || 'OTHER');

    let resp: Response;
    try {
      setScanStage(t('ds.stageOcr', language));
      resp = await fetch('/api/documents/upload', { method: 'POST', body: formData });
    } catch (err) {
      setIsScanning(false);
      setStatusMessage({ kind: 'error', text: t('ds.errNetwork', language) });
      return;
    }

    if (!resp.ok) {
      setIsScanning(false);
      let detail = `Upload failed (HTTP ${resp.status}).`
      try {
        const body = await resp.json();
        if (typeof body?.detail === 'string') detail = body.detail;
      } catch { /* keep generic message */ }
      setStatusMessage({ kind: 'error', text: detail });
      return;
    }

    const data = await resp.json();
    const entities: Array<{ type: string; name: string; value?: string | null }> = data.entities || [];
    const extracted: ExtractedDocumentData = {
      diagnoses: entities.filter((e) => e.type === 'DIAGNOSIS').map((e) => e.name),
      medications: entities.filter((e) => e.type === 'MEDICATION').map((e) => ({ name: e.name, dosage: e.value || '' })),
      investigations: entities.filter((e) => e.type === 'LAB_VALUE').map((e) => ({ test: e.name, result: e.value || '', unit: '' })),
      procedures: entities.filter((e) => e.type === 'SURGERY').map((e) => e.name),
      confidenceScore: Math.round((data.overall_confidence || 0) * 100),
    };

    setIsScanning(false);
    const completed = data.ocr_status === 'COMPLETED';
    if (completed) {
      setExtractionVerified(false); // OCR output is never self-verified
      setExtractedResult(extracted);
      setStatusMessage({
        kind: 'info',
        text: data.message || 'Extracted values are unverified OCR output until a physician confirms them.',
      });
    } else {
      // NO_TEXT / FAILED: the original document is still saved for staff.
      // Localized wording preferred over the English backend message for the
      // patient-facing kiosk.
      setStatusMessage({
        kind: 'info',
        text: t('ds.msgNoText', language),
      });
    }

    const newDoc: DocumentItem = {
      id: data.document_id || `DOC-${Date.now()}`,
      patientId: patient.id,
      title: file.name,
      documentType: category as DocumentItem['documentType'],
      documentDate: new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
      fileUrl: '',
      status: 'pending',
      extractedData: extracted,
      isVerifiedByPhysician: false,
      ocrStatus: data.ocr_status,
    };

    clinicalStore.addDocument(newDoc);
    onDocumentsUpdated([newDoc, ...documents]);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (file) {
      uploadToBackend(file, selectedCategory);
    }
  };

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">
            {t('ds.stepLabel', language)}
          </span>
          <span className="font-mono bg-[#F3EEFC] text-[#6C3FC5] px-2 py-0.5 rounded border border-[#6C3FC5]/20">
            {patient.fullName} ({patient.id})
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('ds.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('ds.sub', language)}
        </p>
      </div>

      {/* Category Selection */}
      <div className="space-y-2">
        <label className="text-xs font-bold text-[#171717]">{t('ds.categoryLabel', language)}</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {(['Prescription', 'Laboratory Report', 'Discharge Summary', 'Imaging Report'] as const).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`p-3 rounded-xl text-xs font-bold border text-center transition-all ${
                selectedCategory === cat
                  ? 'border-[#6C3FC5] bg-[#F3EEFC] text-[#6C3FC5] shadow-xs'
                  : 'border-neutral-200 bg-white text-[#666666] hover:bg-neutral-50 hover:text-[#171717]'
              }`}
            >
              {chipLabel(cat, language)}
            </button>
          ))}
        </div>
      </div>

      {/* Upload Zone & Quick Sample Loaders */}
      <div className="p-6 sm:p-8 rounded-2xl border-2 border-dashed border-neutral-300 hover:border-[#6C3FC5] bg-neutral-50/50 hover:bg-[#F3EEFC]/10 transition-colors flex flex-col items-center justify-center text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
          <Upload className="w-7 h-7" />
        </div>

        <div className="space-y-1">
          <h4 className="font-bold text-sm sm:text-base text-[#171717]">
            {t('ds.dropTitle', language)}
          </h4>
          <p className="text-xs text-[#666666]">
            {t('ds.formats', language)}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
          <label className="cursor-pointer px-5 py-2.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs font-bold rounded-xl shadow-xs transition-colors">
            <span>{t('ds.browse', language)}</span>
            <input
              type="file"
              accept=".pdf,image/*"
              className="hidden"
              onChange={handleFileUpload}
            />
          </label>

          {/* Quick Demo Preloads */}
          <button
            type="button"
            onClick={() => simulateScan("Cardiology_Followup_Rx_2026.pdf", "Prescription")}
            className="px-3.5 py-2.5 bg-white border border-neutral-200 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-xl transition-colors shadow-2xs"
          >
            {t('ds.sampleRx', language)}
          </button>
          <button
            type="button"
            onClick={() => simulateScan("Complete_Blood_Count_Report.pdf", "Laboratory Report")}
            className="px-3.5 py-2.5 bg-white border border-neutral-200 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-xl transition-colors shadow-2xs"
          >
            {t('ds.sampleLab', language)}
          </button>
          <button
            type="button"
            onClick={() => simulateScan("Discharge_Summary_Appendicitis.pdf", "Discharge Summary")}
            className="px-3.5 py-2.5 bg-white border border-neutral-200 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-xl transition-colors shadow-2xs"
          >
            {t('ds.sampleDischarge', language)}
          </button>
        </div>
      </div>

      {/* Scanning Progress Bar */}
      {isScanning && (
        <div className="p-5 rounded-xl bg-[#F3EEFC]/60 border border-[#6C3FC5]/30 space-y-3 animate-in fade-in duration-150">
          <div className="flex items-center justify-between text-xs font-bold text-[#6C3FC5]">
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t('ds.analyzing', language)}</span>
            </span>
            <span className="text-[11px] font-mono text-[#666666]">AI OCR Active</span>
          </div>
          <div className="text-xs font-medium text-[#171717]">{scanStage}</div>
          <div className="w-full h-1.5 bg-neutral-200 rounded-full overflow-hidden">
            <div className="h-full bg-[#6C3FC5] animate-pulse rounded-full w-3/4" />
          </div>
        </div>
      )}

      {/* Upload / Extraction Status Message */}
      {statusMessage && !isScanning && (
        <div
          className={`p-4 rounded-xl border text-xs sm:text-sm font-medium animate-in fade-in duration-150 ${
            statusMessage.kind === 'error'
              ? 'bg-red-50 border-red-200 text-red-700'
              : statusMessage.kind === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                : 'bg-amber-50 border-amber-200 text-amber-800'
          }`}
        >
          {statusMessage.text}
        </div>
      )}

      {/* Extracted Details Box */}
      {extractedResult && (
        <div className={`p-5 rounded-xl bg-white border-2 space-y-3 shadow-xs animate-in fade-in duration-150 ${extractionVerified ? 'border-emerald-400' : 'border-amber-300'}`}>
          <div className="flex items-center justify-between border-b border-neutral-100 pb-2">
            <div className="flex items-center gap-2">
              {extractionVerified ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              ) : (
                <ShieldCheck className="w-5 h-5 text-amber-600" />
              )}
              <span className="font-bold text-xs sm:text-sm text-[#171717]">
                {extractionVerified
                  ? t('ds.verifiedTitle', language)
                  : t('ds.awaitingTitle', language)}
              </span>
            </div>
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded border ${
                extractionVerified
                  ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                  : 'text-amber-800 bg-amber-50 border-amber-200'
              }`}
            >
              {t('ds.confidence', language)}: {extractedResult.confidenceScore}%
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="font-bold text-[#666666] block mb-1">{t('ds.diag', language)}</span>
              <ul className="list-disc list-inside space-y-0.5 text-[#171717]">
                {extractedResult.diagnoses.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>

            {extractedResult.medications.length > 0 && (
              <div>
                <span className="font-bold text-[#666666] block mb-1">{t('ds.meds', language)}</span>
                <ul className="list-disc list-inside space-y-0.5 text-[#171717]">
                  {extractedResult.medications.map((m, i) => (
                    <li key={i}>
                      {m.name} ({m.dosage})
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {extractedResult.investigations.length > 0 && (
              <div className="sm:col-span-2">
                <span className="font-bold text-[#666666] block mb-1">{t('ds.investigations', language)}</span>
                <div className="flex flex-wrap gap-2">
                  {extractedResult.investigations.map((inv, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 bg-neutral-100 rounded text-[11px] font-mono text-[#171717]"
                    >
                      {inv.test}: <strong>{inv.result}</strong> {inv.unit}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Uploaded Documents List */}
      <div className="space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-[#666666]">
          {t('ds.uploadedList', language)} ({documents.length})
        </h4>

        {documents.length === 0 ? (
          <div className="p-4 bg-neutral-50 rounded-xl border border-neutral-200 text-xs text-[#666666]">
            {t('ds.noneNote', language)}
          </div>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="p-3.5 bg-white rounded-xl border border-neutral-200 flex items-center justify-between gap-3 shadow-2xs"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
                    <FileCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h5 className="font-bold text-xs sm:text-sm text-[#171717]">{doc.title}</h5>
                    <span className="text-[11px] text-[#666666]">
                      {doc.documentType} • {doc.documentDate}
                    </span>
                  </div>
                </div>

                <span className="text-[11px] font-bold px-2 py-0.5 rounded border">
                  {doc.status === 'verified' && doc.isVerifiedByPhysician ? (
                    <span className="text-emerald-700 bg-emerald-50 border-emerald-200">{t('ds.badgeVerified', language)}</span>
                  ) : doc.ocrStatus === 'NO_TEXT' || doc.ocrStatus === 'FAILED' ? (
                    <span className="text-red-700 bg-red-50 border-red-200">{t('ds.badgeStaff', language)}</span>
                  ) : (
                    <span className="text-amber-800 bg-amber-50 border-amber-200">{t('ds.badgeUnverified', language)}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('ds.back', language)}</span>
        </button>

        <button
          type="button"
          onClick={onContinue}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>{t('ds.continue', language)}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
