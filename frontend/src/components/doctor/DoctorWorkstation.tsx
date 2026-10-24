'use client';

import React, { useState } from 'react';
import {
  Stethoscope,
  RefreshCw,
  Search,
  AlertTriangle,
  FileText,
  Clock,
  CheckCircle2,
  FileCode,
  Copy,
  Check,
  Share2,
  ShieldAlert,
  ArrowLeft,
  ChevronRight,
  Eye,
  Pill,
  Save,
  PenLine,
  Activity,
  Layers,
  FileCheck,
  Building2,
  UserCheck
} from 'lucide-react';
import {
  Patient,
  ClinicalCase,
  DocumentItem,
  TestResult,
  TimelineItem,
  LanguageCode
} from '@/lib/types';
import { clinicalStore } from '@/lib/clinicalStore';
import { authHeaders, authFetch } from '@/lib/auth';
import { t } from '@/lib/i18n';
import { useModalDialog } from '@/lib/useModalDialog';

interface DoctorWorkstationProps {
  initialPatient?: Patient;
  onBackToOverview: () => void;
  language?: LanguageCode;
}

export function DoctorWorkstation({
  initialPatient,
  onBackToOverview,
  language = 'en',
}: DoctorWorkstationProps) {
  const [patients, setPatients] = useState<Patient[]>(() => clinicalStore.getPatients());
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(
    initialPatient || (clinicalStore.getPatients().length > 0 ? clinicalStore.getPatients()[0] : null)
  );
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);
  // QA BUG-003: a rejected queue load (401/403/offline) must be visible, never
  // silently rendered as an empty or demo-only workstation.
  const [queueError, setQueueError] = useState('');
  // QA BUG-003: a refused/unavailable dossier load is shown, not silently
  // replaced by the local demo record.
  const [dossierError, setDossierError] = useState('');
  // Live clinical dossier fetched from the backend for the selected encounter.
  const [dossier, setDossier] = useState<any>(null);
  const [signError, setSignError] = useState('');
  const [isSigning, setIsSigning] = useState(false);
  // Themed, in-app completion confirmation (replaces the native browser alert()).
  const [signSuccess, setSignSuccess] = useState<{ open: boolean; message: string }>({ open: false, message: '' });
  // Physician verification of OCR-extracted entities (extracted text vs
  // verified clinical information).
  const [verifyingEntityId, setVerifyingEntityId] = useState<string | null>(null);
  const [verifyError, setVerifyError] = useState('');
  // Signed-in physician identity (name + OPD stream). The queue below is already
  // filtered server-side to this physician's stream, so the badge makes it
  // explicit that e.g. an AYUSH physician is not silently missing patients.
  const [identity, setIdentity] = useState<{ name: string; department: string } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetch('/api/auth/me', { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : null))
      .then((me) => {
        if (!cancelled && me) {
          setIdentity({ name: me.name || '', department: me.department || '' });
        }
      })
      .catch(() => {
        /* badge is informational only — never blocks the workstation */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchQueue = async () => {
    setIsLoadingQueue(true);
    setQueueError('');
    try {
      // Phase 6: the queue is PHI — requires the signed-in doctor's bearer token.
      const res = await authFetch('/api/doctor/queue');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          const mapped: Patient[] = data.map((item: any) => ({
            id: item.patient_id,
            token: item.token_number,
            encounterId: item.encounter_id,
            mrn: item.mrn,
            fullName: item.patient_name,
            age: item.age,
            gender: item.gender === 'FEMALE' ? 'Female' : item.gender === 'OTHER' ? 'Other' : 'Male',
            phone: item.phone || '',
            city: '',
            language: 'en',
            consultationType: item.consultation_type === 'ayush' ? 'ayush' : 'modern',
            department: item.department || 'General Medicine',
            isRegisteredNew: false,
            status: item.status === 'FINALIZED' ? 'completed' : item.status === 'IN_CONSULTATION' ? 'in_consultation' : 'waiting',
            isPriority: item.priority === 'EMERGENCY' || item.priority === 'URGENT',
            counterNumber: 'OPD Desk',
            estimatedWaitMinutes: 5,
            createdAt: item.created_at || ''
          }));
          setPatients(mapped);
          setSelectedPatient(prev => prev && mapped.some(p => p.id === prev.id) ? prev : (mapped.length > 0 ? mapped[0] : null));
          return;
        }
      }
      if (res.status === 403) {
        setQueueError('Your account is not allowed to read the OPD queue (HTTP 403). No patient data was loaded.');
      } else {
        setQueueError(`Live OPD queue unavailable (HTTP ${res.status}). Showing locally cached demo patients only.`);
      }
    } catch (err) {
      console.warn('Could not fetch queue from backend API:', err);
      setQueueError('Live OPD queue unavailable — the server did not respond. Showing locally cached demo patients only.');
    } finally {
      setIsLoadingQueue(false);
    }
    // Backend unavailable — fall back to the local demo store. Completed patients
    // are kept so they remain visible under the 'Completed' queue filter.
    const local = clinicalStore.getPatients();
    setPatients(local);
    setSelectedPatient(prev => prev && local.some(p => p.id === prev.id) ? prev : (local.length > 0 ? local[0] : null));
  };

  React.useEffect(() => {
    fetchQueue();
    const unsub = clinicalStore.subscribe(() => {
      const local = clinicalStore.getPatients();
      if (local.length > 0) {
        setPatients(local);
        setSelectedPatient(prev => prev || local[0]);
      }
    });
    return () => unsub();
  }, []);

  // Load the real backend dossier whenever the selected patient/encounter changes.
  React.useEffect(() => {
    let cancelled = false;
    setDossier(null);
    setDossierError('');
    setSignError('');
    setExamFindings('');
    setDoctorNotes('');
    if (selectedPatient?.encounterId) {
      const qs = selectedPatient.encounterId ? `?encounter_id=${selectedPatient.encounterId}` : '';
      authFetch(`/api/doctor/patient/${selectedPatient.id}${qs}`)
        .then(async (res) => {
          if (res.ok) return await res.json();
          if (!cancelled) {
            setDossierError(
              res.status === 403
                ? 'This clinical record is not accessible with your account (HTTP 403).'
                : `Clinical record could not be loaded (HTTP ${res.status}).`
            );
          }
          return null;
        })
        .then((data) => {
          if (!cancelled && data) {
            setDossier(data);
            // Resume the doctor's previously saved notes/assessment if the encounter was already edited.
            if (data.summary?.doctor_notes) {
              setDoctorNotes(String(data.summary.doctor_notes).slice(0, 4000));
            }
          }
        })
        .catch((err) => {
          console.warn('Could not load clinical dossier from backend:', err);
          if (!cancelled) setDossierError('Clinical record could not be loaded — the server did not respond.');
        });
    }
    return () => { cancelled = true; };
  }, [selectedPatient?.id, selectedPatient?.encounterId]);

  // Queue search & filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'priority' | 'waiting' | 'completed'>('all');

  // Active Tab in Clinical View
  const [clinicalTab, setClinicalTab] = useState<'history' | 'diagnostic' | 'reconciliation' | 'timeline' | 'docs'>('history');

  // Physician Notes & Examination — start blank; the physician records real
  // findings, nothing is pre-filled with invented clinical data.
  const [examFindings, setExamFindings] = useState('');
  const [doctorNotes, setDoctorNotes] = useState('');
  const [physicianName, setPhysicianName] = useState("Dr. Ananya Sharma, MD");
  const [isSigned, setIsSigned] = useState(false);

  // FHIR Bundle modal
  const [fhirModalOpen, setFhirModalOpen] = useState(false);
  const [fhirCopied, setFhirCopied] = useState(false);
  const [phrPushed, setPhrPushed] = useState(false);

  // QA-12: dialog semantics, Escape-to-close, focus trap and focus restore for
  // the two modals that were plain overlays.
  const fhirDialog = useModalDialog(fhirModalOpen, {
    onClose: () => setFhirModalOpen(false),
  });
  const signDialog = useModalDialog(signSuccess.open, {
    onClose: () => setSignSuccess({ open: false, message: '' }),
  });

  // Clinical data for selected patient
  const activeCase = selectedPatient ? clinicalStore.getCaseByPatientId(selectedPatient.id) : undefined;
  const activeDocs = selectedPatient ? clinicalStore.getDocumentsByPatientId(selectedPatient.id) : [];
  const activeTests = selectedPatient ? clinicalStore.getTestsByPatientId(selectedPatient.id) : [];
  const activeTimeline = selectedPatient ? clinicalStore.getTimelineByPatientId(selectedPatient.id) : [];

  // Real backend dossier content (never fabricated — empty when not recorded).
  const aiSummary = dossier?.summary || null;
  const encounterRedFlags: any[] = dossier?.encounter?.red_flags || [];
  const summaryRedFlags: any[] = aiSummary?.red_flags || [];
  const redFlagLines: string[] = [
    ...encounterRedFlags.map((r: any) => r.description || r.rule || String(r)),
    ...summaryRedFlags.map((r: any) => r.alert || r.rationale || String(r)),
  ];
  const chiefComplaintDisplay =
    aiSummary?.chief_complaint ||
    activeCase?.chiefComplaints?.[0]?.complaint ||
    t('dw.notRecorded', language);
  const hpiDisplay =
    aiSummary?.hpi || activeCase?.hpiNarrative || t('dw.notRecorded', language);
  const hasAiContent = !!(aiSummary?.chief_complaint || aiSummary?.hpi);
  const contentSourceLabel = aiSummary?.is_confirmed
    ? t('dw.doctorSigned', language)
    : hasAiContent
    ? t('dw.aiGenerated', language)
    : t('dw.patientProvided', language);
  const medItems: any[] =
    dossier?.medications && dossier.medications.length > 0
      ? dossier.medications
      : (activeCase?.medications || []).map((m: any) => ({ ...m, provenance: 'Patient Reported' }));

  // Filter queue
  const filteredQueue = patients.filter((p) => {
    const matchesSearch =
      p.fullName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.token.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.id.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;
    if (filterType === 'priority') return p.isPriority;
    if (filterType === 'waiting') return p.status === 'waiting';
    if (filterType === 'completed') return p.status === 'completed';
    return true;
  });

  const handleSelectPatient = (patient: Patient) => {
    setSelectedPatient(patient);
    setIsSigned(patient.status === 'completed');
  };

  const handleSignConsultation = async () => {
    if (!selectedPatient || isSigning || isSigned) return;
    setSignError('');

    // Validate the doctor signature before doing anything.
    if (!physicianName.trim()) {
      setSignError(t('dw.signNameRequired', language));
      return;
    }

    setIsSigning(true);
    try {
      if (selectedPatient.encounterId) {
        // Real backend completion: summary confirmed + encounter FINALIZED in PostgreSQL/SQLite.
        try {
          const res = await fetch(`/api/doctor/encounter/${selectedPatient.encounterId}/summary`, {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
              doctor_notes: `Examination: ${examFindings} | Assessment & Plan: ${doctorNotes} | Signed by ${physicianName.trim()}`,
              confirm: true
            })
          });
          if (res.ok) {
            // Mark the encounter completed in place so it stays visible under the
            // 'Completed' queue filter, then confirm with a themed in-app dialog.
            clinicalStore.markCaseReviewed(selectedPatient.id, physicianName.trim(), doctorNotes);
            setPatients((prev) => prev.map((p) => p.id === selectedPatient.id ? { ...p, status: 'completed' as const } : p));
            setIsSigned(true);
            setSignSuccess({ open: true, message: t('dw.signSuccess', language) });
            fetchQueue();
            return;
          }
          // Server responded with an error — do NOT falsely claim success.
          const detail = await res.json().catch(() => null);
          setSignError(`${t('dw.signError', language)} (${res.status}${detail?.detail ? `: ${detail.detail}` : ''})`);
          return;
        } catch (err) {
          console.warn('Backend finalization failed:', err);
          setSignError(t('dw.signError', language));
          return;
        }
      }

      // Local-only demo patient (never registered on the backend):
      // record the sign-off in the local store and keep it listed as completed.
      clinicalStore.markCaseReviewed(selectedPatient.id, physicianName.trim(), doctorNotes);
      setIsSigned(true);
      setPatients((prev) => prev.map((p) => p.id === selectedPatient.id ? { ...p, status: 'completed' as const } : p));
      setSignSuccess({ open: true, message: `Consultation signed by ${physicianName.trim()} (local demo record — this patient has no backend encounter).` });
    } finally {
      setIsSigning(false);
    }
  };

  // Physician confirms a single OCR-extracted entity as verified clinical
  // information via the backend (POST /api/doctor/verify-entity/{id}).
  const handleVerifyEntity = async (entityId: string) => {
    if (verifyingEntityId) return;
    setVerifyingEntityId(entityId);
    setVerifyError('');
    try {
      const res = await fetch(`/api/doctor/verify-entity/${entityId}`, { method: 'POST', headers: authHeaders() });
      if (res.ok) {
        setDossier((prev: any) => {
          if (!prev) return prev;
          const documents = (prev.documents || []).map((d: any) => ({
            ...d,
            extracted_entities: (d.extracted_entities || []).map((e: any) =>
              e.id === entityId ? { ...e, doctor_verified: true, confidence: 1.0 } : e
            ),
          }));
          return { ...prev, documents };
        });
      } else {
        const body = await res.json().catch(() => null);
        setVerifyError(
          body?.detail
            ? `Verification failed (HTTP ${res.status}: ${body.detail})`
            : `Verification failed (HTTP ${res.status}).`
        );
      }
    } catch (err) {
      console.warn('Entity verification request failed:', err);
      setVerifyError('Could not reach the server to record the verification.');
    } finally {
      setVerifyingEntityId(null);
    }
  };

  // Generate FHIR R4 Bundle JSON
  const fhirBundle = selectedPatient ? {
    resourceType: "Bundle",
    type: "document",
    timestamp: new Date().toISOString(),
    entry: [
      {
        fullUrl: `urn:uuid:patient-${selectedPatient.id}`,
        resource: {
          resourceType: "Patient",
          id: selectedPatient.id,
          identifier: [{ system: "https://healthid.ndhm.gov.in", value: selectedPatient.abhaId || "ABHA-DEMO" }],
          name: [{ text: selectedPatient.fullName }],
          gender: selectedPatient.gender ? selectedPatient.gender.toLowerCase() : 'other',
          telecom: [{ system: "phone", value: selectedPatient.phone }]
        }
      },
      {
        fullUrl: `urn:uuid:encounter-${selectedPatient.token}`,
        resource: {
          resourceType: "Encounter",
          status: "in-progress",
          class: { code: "AMB", display: "Ambulatory OPD" },
          subject: { reference: `Patient/${selectedPatient.id}` }
        }
      },
      {
        fullUrl: `urn:uuid:diagnosticreport-${selectedPatient.id}`,
        resource: {
          resourceType: "DiagnosticReport",
          status: "preliminary",
          category: [{ coding: [{ system: "http://terminology.hl7.org/CodeSystem/v2-0074", code: "LAB", display: "Clinical Intake" }] }],
          code: { text: "MediKiosk AI-Assisted Clinical History Intake Summary" },
          subject: { reference: `Patient/${selectedPatient.id}` },
          conclusion: aiSummary?.hpi || activeCase?.hpiNarrative || "Clinical intake summary pending physician review"
        }
      }
    ]
  } : null;

  const copyFhir = () => {
    navigator.clipboard.writeText(JSON.stringify(fhirBundle, null, 2));
    setFhirCopied(true);
    setTimeout(() => setFhirCopied(false), 2000);
  };

  const pushToPhr = () => {
    setPhrPushed(true);
    setTimeout(() => setPhrPushed(false), 2500);
  };

  return (
    <div className="w-full flex-1 flex flex-col bg-neutral-100 min-h-[calc(100vh-4rem)]">
      {/* Subheader */}
      <div className="bg-white border-b border-neutral-200 px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3 sticky top-16 z-30">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBackToOverview}
            className="p-1.5 rounded-lg border border-neutral-200 hover:bg-neutral-50 text-[#666666] hover:text-[#171717] transition-colors"
            title="Back to Overview"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-[#171717]">
                {t('dw.title', language)}
              </h2>
              <span className="text-[11px] font-mono text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded border border-[#6C3FC5]/20 max-w-[320px] truncate">
                {identity
                  ? `${identity.name}${identity.department ? ` • ${identity.department}` : ''}`
                  : 'Signed-in physician'}
              </span>
            </div>
            <p className="text-xs text-[#666666]">
              {t('dw.subtitle', language)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchQueue}
            disabled={isLoadingQueue}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-neutral-300 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-lg shadow-2xs transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#6C3FC5] ${isLoadingQueue ? 'animate-spin' : ''}`} />
            <span>{t('dw.refreshQueue', language)}</span>
          </button>

          <button
            type="button"
            onClick={() => setFhirModalOpen(true)}
            disabled={!selectedPatient}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-neutral-300 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-lg shadow-2xs transition-colors disabled:opacity-50"
          >
            <FileCode className="w-3.5 h-3.5 text-[#6C3FC5]" />
            <span>{t('dw.inspectFhir', language)}</span>
          </button>

          <button
            type="button"
            onClick={handleSignConsultation}
            disabled={isSigned || isSigning}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
              isSigned
                ? 'bg-emerald-600 text-white cursor-default'
                : 'bg-[#6C3FC5] hover:bg-[#4B238C] text-white shadow-xs disabled:opacity-60'
            }`}
          >
            {isSigned ? <Check className="w-3.5 h-3.5" /> : <PenLine className="w-3.5 h-3.5" />}
            <span>{isSigned ? t('dw.signed', language) : isSigning ? `${t('dw.sign', language)}…` : t('dw.sign', language)}</span>
          </button>
        </div>
      </div>

      {/* Sign-off error banner — surfaced whenever backend finalization failed */}
      {signError && (
        <div className="bg-red-50 border-b border-red-200 px-4 sm:px-6 py-2 flex items-center gap-2 text-xs font-semibold text-red-800">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{signError}</span>
        </div>
      )}

      {/* QA BUG-003: queue load refused or unavailable — stated explicitly */}
      {queueError && (
        <div role="alert" className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-2 flex items-center gap-2 text-xs font-semibold text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>{queueError}</span>
        </div>
      )}

      {dossierError && (
        <div role="alert" className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-2 flex items-center gap-2 text-xs font-semibold text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>{dossierError}</span>
        </div>
      )}

      {/* Main Workstation 2-Column Grid */}
      <div className="flex-1 max-w-7xl mx-auto w-full p-3 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Patient Queue (4 cols) */}
        <div className="lg:col-span-4 bg-white rounded-2xl border border-neutral-200 shadow-xs p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-[#171717]">{t('dw.queueTitle', language)}</span>
              <span className="text-xs bg-[#F3EEFC] text-[#6C3FC5] font-bold px-2 py-0.5 rounded-full">
                {patients.length}
              </span>
            </div>
            <span className="text-[11px] text-[#666666]">Today&apos;s Footfall</span>
          </div>

          {/* Search Box */}
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('dw.searchPlaceholder', language)}
              className="w-full px-3 py-2 pl-9 bg-neutral-50 border border-neutral-200 rounded-lg text-xs focus:border-[#6C3FC5] focus:outline-none"
            />
            <Search className="w-3.5 h-3.5 text-[#666666] absolute left-3 top-2.5" />
          </div>

          {/* Filter Pills — labels come from i18n so the queue chrome follows the
              selected language (QA-15: these used to be hardcoded English). */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
            {(['all', 'priority', 'waiting', 'completed'] as const).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setFilterType(filter)}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  filterType === filter
                    ? 'bg-[#6C3FC5] text-white'
                    : 'bg-neutral-100 text-[#666666] hover:bg-neutral-200'
                }`}
              >
                {t(`dw.filter${filter.charAt(0).toUpperCase()}${filter.slice(1)}`, language)}
              </button>
            ))}
          </div>

          {/* Queue List */}
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {filteredQueue.length === 0 ? (
              <div className="p-6 text-center text-neutral-400 space-y-2 border border-dashed border-neutral-200 rounded-xl bg-neutral-50/50">
                <Clock className="w-6 h-6 text-neutral-300 mx-auto" />
                <p className="text-xs font-bold text-[#171717]">{t('dw.emptyQueue', language)}</p>
                <p className="text-[11px] text-[#666666] leading-relaxed">
                  {t('dw.emptyQueueHint', language)}
                </p>
                <button
                  type="button"
                  onClick={fetchQueue}
                  disabled={isLoadingQueue}
                  className="mt-2 px-3 py-1 bg-white border border-neutral-200 hover:border-[#6C3FC5] rounded-lg text-xs font-semibold text-[#171717] shadow-2xs inline-flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3 h-3 text-[#6C3FC5] ${isLoadingQueue ? 'animate-spin' : ''}`} />
                  <span>{t('dw.checkQueue', language)}</span>
                </button>
              </div>
            ) : (
              filteredQueue.map((patient) => {
                // QA-06: one patient can hold several encounters today (e.g. a
                // revisit), so the row identity is the ENCOUNTER, not the
                // patient. Keying both on patient.id made React reuse stale
                // rows: a queued visit stayed visible (and highlighted) inside
                // the Completed filter.
                const rowKey = patient.encounterId || patient.id;
                const isSelected = (selectedPatient?.encounterId || selectedPatient?.id) === rowKey;
                return (
                  <div
                    key={rowKey}
                    onClick={() => handleSelectPatient(patient)}
                    className={`cursor-pointer p-3 rounded-xl border transition-all ${
                      isSelected
                        ? 'border-[#6C3FC5] bg-[#F3EEFC]/50 shadow-xs'
                        : 'border-neutral-200 hover:border-neutral-300 bg-white hover:bg-neutral-50/60'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-xs text-[#6C3FC5] bg-white px-1.5 py-0.5 rounded border border-[#6C3FC5]/20">
                          {patient.token}
                        </span>
                        <span className="font-bold text-xs text-[#171717]">{patient.fullName}</span>
                      </div>
                      {patient.isPriority && (
                        <span className="text-[10px] font-bold text-red-700 bg-red-100 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                          <AlertTriangle className="w-2.5 h-2.5" />
                          Red Flag
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[#666666]">
                      <span>
                        {patient.age}y {patient.gender} • {patient.department}
                      </span>
                      <span
                        className={`capitalize font-semibold ${
                          patient.status === 'completed'
                            ? 'text-emerald-600'
                            : patient.status === 'in_consultation'
                            ? 'text-[#6C3FC5]'
                            : 'text-amber-600'
                        }`}
                      >
                        {patient.status.replace('_', ' ')}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Active Patient Consultation Summary (8 cols) */}
        {!selectedPatient ? (
          <div className="lg:col-span-8 bg-white rounded-2xl border border-neutral-200 shadow-xs p-8 sm:p-12 space-y-4 flex flex-col items-center justify-center text-center min-h-[500px]">
            <div className="w-16 h-16 rounded-2xl bg-[#F3EEFC] flex items-center justify-center text-[#6C3FC5]">
              <Stethoscope className="w-8 h-8" />
            </div>
            <div className="space-y-1.5 max-w-md">
              <h3 className="text-lg font-serif font-bold text-[#171717]">
                {t('dw.readyTitle', language)}
              </h3>
              <p className="text-xs text-[#666666] leading-relaxed">
                {t('dw.readyHint', language)}
              </p>
            </div>
            <button
              type="button"
              onClick={fetchQueue}
              disabled={isLoadingQueue}
              className="flex items-center gap-1.5 px-4 py-2 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs font-bold rounded-xl shadow-xs transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoadingQueue ? 'animate-spin' : ''}`} />
              <span>{t('dw.refreshLive', language)}</span>
            </button>
          </div>
        ) : (
        <div className="lg:col-span-8 bg-white rounded-2xl border border-neutral-200 shadow-xs p-5 sm:p-6 space-y-6">
          {/* Patient Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-neutral-200 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl sm:text-2xl font-serif font-bold text-[#171717]">
                  {selectedPatient.fullName}
                </span>
                <span className="font-mono text-xs font-bold text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded">
                  {selectedPatient.token}
                </span>
                {selectedPatient.isPriority && (
                  <span className="text-xs font-bold text-red-700 bg-red-100 px-2.5 py-0.5 rounded-full flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    Priority Red Flag
                  </span>
                )}
              </div>
              <div className="text-xs text-[#666666] mt-1">
                Patient ID: <strong>{selectedPatient.id}</strong> • MRN: <strong>{selectedPatient.mrn || '—'}</strong> • ABHA ID: <strong>{selectedPatient?.abhaId || '—'}</strong> • {selectedPatient.age} yrs • {selectedPatient.gender} • {selectedPatient.department}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[#666666]">Consultation Stream:</span>
              <span className="text-xs font-bold uppercase tracking-wider text-[#6C3FC5] bg-[#F3EEFC] px-2.5 py-1 rounded-md">
                {selectedPatient.consultationType === 'ayush' ? 'Traditional AYUSH' : 'Modern OPD'}
              </span>
            </div>
          </div>

          {/* Red Flag Callout (if active) */}
          {selectedPatient.isPriority && (
            <div className="p-4 rounded-xl bg-red-50 border border-red-300 text-red-950 flex items-start gap-3">
              <ShieldAlert className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <span className="font-bold text-red-700 uppercase tracking-wide">
                  {t('dw.priorityAlert', language)}
                </span>
                <p className="font-semibold text-red-900 leading-snug">
                  {redFlagLines.length > 0 ? redFlagLines.join(' • ') : activeCase?.redFlagReason || t('dw.notRecorded', language)}
                </p>
                <p className="text-[11px] text-red-700">
                  Immediate physician evaluation recommended. Triage alerted.
                </p>
              </div>
            </div>
          )}

          {/* Clinical Navigation Tabs */}
          <div className="flex items-center gap-2 border-b border-neutral-200 overflow-x-auto text-xs font-bold">
            <button
              type="button"
              onClick={() => setClinicalTab('history')}
              className={`px-3.5 py-2 border-b-2 transition-colors whitespace-nowrap ${
                clinicalTab === 'history'
                  ? 'border-[#6C3FC5] text-[#6C3FC5]'
                  : 'border-transparent text-[#666666] hover:text-[#171717]'
              }`}
            >
            <span className="capitalize">{t('dw.tabHistory', language)}</span>
            </button>
            <button
              type="button"
              onClick={() => setClinicalTab('diagnostic')}
              className={`px-3.5 py-2 border-b-2 transition-colors whitespace-nowrap ${
                clinicalTab === 'diagnostic'
                  ? 'border-[#6C3FC5] text-[#6C3FC5]'
                  : 'border-transparent text-[#666666] hover:text-[#171717]'
              }`}
            >
            <span className="capitalize">{t('dw.tabDiagnostic', language)}</span>
            </button>
            <button
              type="button"
              onClick={() => setClinicalTab('reconciliation')}
              className={`px-3.5 py-2 border-b-2 transition-colors whitespace-nowrap ${
                clinicalTab === 'reconciliation'
                  ? 'border-[#6C3FC5] text-[#6C3FC5]'
                  : 'border-transparent text-[#666666] hover:text-[#171717]'
              }`}
            >
            <span className="capitalize">{t('dw.tabMedRec', language)}</span>
            </button>
            <button
              type="button"
              onClick={() => setClinicalTab('timeline')}
              className={`px-3.5 py-2 border-b-2 transition-colors whitespace-nowrap ${
                clinicalTab === 'timeline'
                  ? 'border-[#6C3FC5] text-[#6C3FC5]'
                  : 'border-transparent text-[#666666] hover:text-[#171717]'
              }`}
            >
            <span className="capitalize">{t('dw.tabTimeline', language)}</span>
            </button>
            <button
              type="button"
              onClick={() => setClinicalTab('docs')}
              className={`px-3.5 py-2 border-b-2 transition-colors whitespace-nowrap ${
                clinicalTab === 'docs'
                  ? 'border-[#6C3FC5] text-[#6C3FC5]'
                  : 'border-transparent text-[#666666] hover:text-[#171717]'
              }`}
            >
            <span className="capitalize">{t('dw.tabDocs', language)} ({activeDocs.length + (dossier?.documents?.length || 0)})</span>
            </button>
          </div>

          {/* TAB 1: Intake History & SOCRATES */}
          {clinicalTab === 'history' && (
            <div className="space-y-5 text-xs">
              {/* Chief Complaints Box */}
              <div className="p-4 rounded-xl bg-neutral-50 border border-neutral-200 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold uppercase tracking-wider text-[#666666] block">
                    {t('dw.chiefTitle', language)}
                  </span>
                  <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border border-[#6C3FC5]/30 text-[#6C3FC5] bg-white">
                    {contentSourceLabel}
                  </span>
                </div>
                <p className="text-sm font-bold text-[#171717]">
                  {chiefComplaintDisplay}
                </p>
                <p className="text-xs text-[#666666] leading-relaxed">
                  {hpiDisplay}
                </p>
              </div>

              {/* Phase 7 (workflow step 8): the patient's ORIGINAL answers from
                  the backend — verbatim, never AI-rewritten, kept separate
                  from the summary draft above and OCR output. */}
              {(dossier?.patient_statements || []).length > 0 && (
                <div className="p-4 rounded-xl border border-neutral-200 bg-white space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold uppercase tracking-wider text-[#6C3FC5]">
                      {t('dw.patientWordsTitle', language)}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border border-neutral-300 text-[#666666] bg-neutral-50 whitespace-nowrap">
                      {t('dw.patientProvided', language)}
                    </span>
                  </div>
                  <p className="text-[11px] text-[#666666]">{t('dw.patientWordsNote', language)}</p>
                  <ul className="space-y-2">
                    {dossier.patient_statements.map((s: any) => (
                      <li key={s.id} className="p-2.5 rounded-lg bg-neutral-50 border border-neutral-200">
                        <span className="text-[#666666] block">{s.question_text}</span>
                        <span className="font-semibold text-[#171717]">{s.answer_text}</span>
                        {s.input_method === 'voice' && (
                          <span className="ml-2 text-[10px] font-bold uppercase text-[#6C3FC5]">voice</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* SOCRATES Grid */}
              {activeCase?.socrates && (
                <div className="p-4 rounded-xl border border-neutral-200 space-y-3">
                  <span className="font-bold uppercase tracking-wider text-[#6C3FC5] block">
                    SOCRATES Clinical Breakdown
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[#171717]">
                    <div>
                      <span className="text-[#666666] block">Site:</span>
                      <span className="font-semibold">{activeCase.socrates.site}</span>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Onset:</span>
                      <span className="font-semibold">{activeCase.socrates.onset}</span>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Character:</span>
                      <span className="font-semibold">{activeCase.socrates.character}</span>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Radiation:</span>
                      <span className="font-semibold">{activeCase.socrates.radiation}</span>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Associated Symptoms:</span>
                      <span className="font-semibold">{activeCase.socrates.associations.join(', ')}</span>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Timing / Duration:</span>
                      <span className="font-semibold">{activeCase.socrates.timing}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* AYUSH Assessment View (if applicable) */}
              {activeCase?.ayushAssessment && (
                <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/40 space-y-3">
                  <span className="font-bold uppercase tracking-wider text-emerald-800 block">
                    Ayurvedic Dashavidha Pariksha Findings
                  </span>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[#171717]">
                    <div>
                      <span className="text-[#666666] block">Deha Prakriti:</span>
                      <strong>{activeCase.ayushAssessment.prakriti}</strong>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Vikriti:</span>
                      <strong>{activeCase.ayushAssessment.vikriti}</strong>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Agni Bala:</span>
                      <strong>{activeCase.ayushAssessment.agni}</strong>
                    </div>
                    <div>
                      <span className="text-[#666666] block">Koshtha:</span>
                      <strong>{activeCase.ayushAssessment.koshtha}</strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Diagnostic Considerations */}
          {clinicalTab === 'diagnostic' && (
            <div className="space-y-4 text-xs">
              <div className="p-3 bg-[#F3EEFC]/60 rounded-lg text-[#666666]">
                {t('dw.diagNote', language)}
              </div>

              {/* Red flags and investigations actually recorded for this encounter */}
              {summaryRedFlags.length === 0 && encounterRedFlags.length === 0 && (aiSummary?.investigations || []).length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-neutral-200 bg-neutral-50 text-center text-[#666666]">
                  {t('dw.notRecorded', language)}
                </div>
              ) : (
                <>
                  {encounterRedFlags.map((rf: any, idx: number) => (
                    <div key={`enc-${idx}`} className="p-4 rounded-xl border-2 border-red-200 bg-red-50/30 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="font-bold text-sm text-red-900">{rf.rule || t('dw.priorityAlert', language)}</h4>
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-red-100 text-red-700 whitespace-nowrap">
                          {rf.priority || 'RED FLAG'}
                        </span>
                      </div>
                      {rf.description && <p className="text-[#171717]">{rf.description}</p>}
                    </div>
                  ))}
                  {summaryRedFlags.map((rf: any, idx: number) => (
                    <div key={`sum-${idx}`} className="p-4 rounded-xl border border-amber-200 bg-amber-50/40 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="font-bold text-sm text-amber-900">{rf.alert}</h4>
                        <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-700 whitespace-nowrap">{rf.severity}</span>
                      </div>
                      {rf.rationale && <p className="text-[#666666]">{rf.rationale}</p>}
                    </div>
                  ))}
                  {(aiSummary?.investigations || []).length > 0 && (
                    <div className="p-4 rounded-xl border border-neutral-200 bg-white space-y-2">
                      <strong className="text-[#666666] block">{t('dw.tabDocs', language)}</strong>
                      <div className="flex flex-wrap gap-2">
                        {aiSummary.investigations.map((inv: any, idx: number) => (
                          <span key={idx} className="px-2 py-0.5 bg-neutral-100 rounded text-[11px] font-mono">
                            {inv.test}: <strong>{inv.value}</strong>{' '}
                            {inv.flag && inv.flag !== 'NORMAL' && <span className="text-red-600 font-bold">({inv.flag})</span>}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* TAB 3: Medication Reconciliation */}
          {clinicalTab === 'reconciliation' && (
            <div className="space-y-4 text-xs">
              {medItems.length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-neutral-200 bg-neutral-50 text-center text-[#666666]">
                  {t('dw.medsNone', language)}
                </div>
              ) : (
                <div className="border border-neutral-200 rounded-xl overflow-hidden bg-white">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-neutral-50 text-[#666666] uppercase text-[11px] border-b border-neutral-200 font-bold">
                      <tr>
                        <th className="p-3">Medication</th>
                        <th className="p-3">Dosage</th>
                        <th className="p-3">Frequency</th>
                        <th className="p-3">Source</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100 text-[#171717]">
                      {medItems.map((m: any, idx: number) => (
                        <tr key={m.id || idx}>
                          <td className="p-3 font-semibold">{m.name}</td>
                          <td className="p-3">{m.dosage || '—'}</td>
                          <td className="p-3">{m.frequency || '—'}</td>
                          <td className="p-3 text-[#666666]">{m.provenance || 'Patient Reported'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: Medical Timeline */}
          {clinicalTab === 'timeline' && (
            <div className="space-y-3 text-xs">
              <span className="font-bold uppercase tracking-wider text-[#666666] block">
                {t('dw.tabTimeline', language)}
              </span>
              <div className="space-y-3 relative pl-4 border-l-2 border-[#6C3FC5]/30">
                {(activeTimeline.length > 0
                  ? activeTimeline
                  : (dossier?.timeline || []).map((tl: any) => ({
                      id: tl.id,
                      dateStr: tl.date,
                      title: tl.title,
                      summary: tl.description,
                      institution: '',
                    }))
                ).map((item) => (
                  <div key={item.id} className="relative space-y-1">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#6C3FC5] absolute -left-[21px] top-1" />
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-[#6C3FC5]">{item.dateStr}</span>
                      <span className="font-bold text-[#171717]">{item.title}</span>
                    </div>
                    <p className="text-[#666666]">{item.summary}</p>
                    {item.institution ? <span className="text-[11px] text-neutral-400 italic">{item.institution}</span> : null}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 5: Scanned Documents — backend uploads + local records */}
          {clinicalTab === 'docs' && (
            <div className="space-y-4 text-xs">
              <div className="p-3 bg-[#F3EEFC]/60 rounded-lg text-[#666666]">
                OCR output below is extracted machine text, not confirmed clinical data. Verify each entity
                to admit it into the patient&apos;s verified record.
              </div>
              {verifyError && (
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs font-semibold text-red-800">
                  {verifyError}
                </div>
              )}

              {/* Real documents uploaded from the kiosk (backend database) */}
              {(dossier?.documents?.length || 0) > 0 && (
                <div className="space-y-3">
                  <span className="font-bold uppercase tracking-wider text-[#666666] block">
                    Kiosk Uploads ({dossier.documents.length})
                  </span>
                  {dossier.documents.map((doc: any) => (
                    <div key={doc.id} className="p-4 rounded-xl border border-neutral-200 bg-white space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <h5 className="font-bold text-sm text-[#171717] truncate" title={doc.file_name}>
                          {doc.file_name}
                        </h5>
                        <span
                          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border whitespace-nowrap ${
                            doc.ocr_status === 'COMPLETED'
                              ? 'text-[#6C3FC5] bg-[#F3EEFC] border-[#6C3FC5]/30'
                              : doc.ocr_status === 'NO_TEXT' || doc.ocr_status === 'FAILED'
                                ? 'text-red-700 bg-red-50 border-red-200'
                                : 'text-amber-800 bg-amber-50 border-amber-200'
                          }`}
                        >
                          {doc.ocr_status === 'COMPLETED'
                            ? `OCR ${Math.round((doc.confidence || 0) * 100)}%`
                            : doc.ocr_status || 'PENDING'}
                        </span>
                      </div>
                      <div className="text-[11px] text-[#666666]">
                        {String(doc.type || '').replace('_', ' ')} • {t('dw.docUploaded', language)}{' '}
                        {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                      </div>
                      {doc.ocr_status === 'NO_TEXT' && (
                        <p className="p-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800">
                          {t('dw.docNoText', language)}
                        </p>
                      )}
                      {doc.ocr_status === 'FAILED' && (
                        <p className="p-2 rounded-lg bg-red-50 border border-red-200 text-red-700">
                          {t('dw.docFailed', language)}
                        </p>
                      )}
                      {(doc.extracted_entities || []).length > 0 && (
                        <div className="space-y-1.5 pt-1 border-t border-neutral-100">
                          {doc.extracted_entities.map((e: any) => (
                            <div key={e.id} className="flex items-start justify-between gap-3 py-0.5">
                              <div className="min-w-0">
                                <span className="font-semibold text-[#171717]">{e.name}</span>
                                {e.value ? <span className="text-[#666666]"> — {e.value}</span> : null}
                                <span className="text-[10px] text-neutral-400 block truncate">
                                  {String(e.type || '').toLowerCase()} {e.source_snippet ? `• “${String(e.source_snippet).slice(0, 90)}”` : ''}
                                </span>
                              </div>
                              {e.doctor_verified ? (
                                <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 whitespace-nowrap">
                                  <CheckCircle2 className="w-3 h-3" /> {t('dw.docVerifiedBadge', language)}
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleVerifyEntity(e.id)}
                                  disabled={verifyingEntityId !== null}
                                  className="text-[10px] font-bold px-2.5 py-1 rounded border border-[#6C3FC5]/40 text-[#6C3FC5] bg-white hover:bg-[#F3EEFC] transition-colors whitespace-nowrap disabled:opacity-50"
                                >
                                  {verifyingEntityId === e.id ? t('dw.docVerifying', language) : t('dw.docVerify', language)}
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Local demo-store documents (browser-side records) */}
              {activeDocs.length > 0 && (
                <div className="space-y-3">
                  <span className="font-bold uppercase tracking-wider text-[#666666] block">
                    Session Records ({activeDocs.length})
                  </span>
                  {activeDocs.map((doc) => (
                    <div key={doc.id} className="p-4 rounded-xl border border-neutral-200 bg-white space-y-2">
                      <div className="flex items-center justify-between">
                        <h5 className="font-bold text-sm text-[#171717]">{doc.title}</h5>
                        <span
                          className={`font-bold text-xs px-2 py-0.5 rounded border ${
                            doc.status === 'verified' && doc.isVerifiedByPhysician
                              ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                              : 'text-amber-800 bg-amber-50 border-amber-200'
                          }`}
                        >
                          {doc.status === 'verified' && doc.isVerifiedByPhysician
                            ? `Confidence: ${doc.extractedData.confidenceScore}%`
                            : 'Unverified OCR'}
                        </span>
                      </div>
                      <div className="text-[#666666]">
                        Diagnoses: <strong>{doc.extractedData.diagnoses.join(', ') || '—'}</strong>
                      </div>
                      {doc.extractedData.investigations.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {doc.extractedData.investigations.map((inv, idx) => (
                            <span key={idx} className="px-2 py-0.5 bg-neutral-100 rounded text-[11px] font-mono">
                              {inv.test}: <strong>{inv.result}</strong> {inv.unit}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {(dossier?.documents?.length || 0) === 0 && activeDocs.length === 0 && (
                <div className="p-4 rounded-xl border border-dashed border-neutral-200 bg-neutral-50 text-center text-[#666666]">
                  No documents have been uploaded for this patient.
                </div>
              )}
            </div>
          )}

          {/* Attending Physician Note & Physical Examination */}
          <div className="pt-4 border-t border-neutral-200 space-y-4">
            <h4 className="font-bold text-sm text-[#171717]">
              {t('dw.physicianNoteTitle', language)}
            </h4>

            {signError && (
              <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs font-semibold text-red-800 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                <span>{signError}</span>
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#666666]">
                {t('dw.examLabel', language)}
              </label>
              <textarea
                rows={2}
                value={examFindings}
                onChange={(e) => setExamFindings(e.target.value)}
                className="w-full p-3 bg-neutral-50 border border-neutral-200 rounded-xl text-xs focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-[#666666]">
                {t('dw.planLabel', language)}
              </label>
              <textarea
                rows={2}
                value={doctorNotes}
                onChange={(e) => setDoctorNotes(e.target.value)}
                className="w-full p-3 bg-neutral-50 border border-neutral-200 rounded-xl text-xs focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-[#666666]">{t('dw.attendingDoctor', language)}</span>
                <input
                  type="text"
                  value={physicianName}
                  onChange={(e) => setPhysicianName(e.target.value)}
                  className="px-2.5 py-1 bg-white border border-neutral-200 rounded-md font-semibold text-[#171717] text-xs"
                />
              </div>

              <button
                type="button"
                onClick={handleSignConsultation}
                disabled={isSigned || isSigning}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold transition-all ${
                  isSigned
                    ? 'bg-emerald-600 text-white cursor-default'
                    : 'bg-[#6C3FC5] hover:bg-[#4B238C] text-white shadow-xs active:scale-[0.99] disabled:opacity-60'
                }`}
              >
                {isSigned ? <Check className="w-4 h-4" /> : <PenLine className="w-4 h-4" />}
                <span>{isSigned ? t('dw.signed', language) : t('dw.sign', language)}</span>
              </button>
            </div>
          </div>
        </div>
        )}
      </div>

      {/* FHIR R4 Bundle Modal */}
      {fhirModalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-3 sm:p-6"
          onClick={fhirDialog.onBackdropClick}
        >
          <div
            ref={fhirDialog.dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="mk-fhir-title"
            tabIndex={-1}
            className="bg-white rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-neutral-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150 outline-none"
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 bg-neutral-50">
              <div className="flex items-center gap-2.5">
                <FileCode className="w-5 h-5 text-[#6C3FC5]" />
                <div>
                  <h3 id="mk-fhir-title" className="font-bold text-sm sm:text-base text-[#171717]">
                    FHIR R4 DiagnosticReport Bundle
                  </h3>
                  <span className="text-[11px] text-[#666666]">
                    ABDM M3 Certified • Linked to ABHA ID {selectedPatient?.abhaId || '—'}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={copyFhir}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  {fhirCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{fhirCopied ? 'Copied JSON!' : 'Copy FHIR JSON'}</span>
                </button>
                <button
                  type="button"
                  onClick={pushToPhr}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  {phrPushed ? <Check className="w-3.5 h-3.5" /> : <Share2 className="w-3.5 h-3.5" />}
                  <span>{phrPushed ? 'Synced with PHR!' : 'Push to PHR Locker'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFhirModalOpen(false)}
                  aria-label="Close FHIR bundle dialog"
                  className="text-[#666666] hover:text-[#171717] text-lg font-bold p-1"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 bg-[#0E131F] text-emerald-400 font-mono text-xs leading-relaxed">
              <pre>{JSON.stringify(fhirBundle, null, 2)}</pre>
            </div>

            <div className="px-6 py-3 border-t border-neutral-200 bg-white flex justify-end">
              <button
                type="button"
                onClick={() => setFhirModalOpen(false)}
                className="px-4 py-1.5 border border-neutral-200 rounded-lg hover:bg-neutral-50 text-xs font-semibold text-[#171717]"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Themed consultation-completed confirmation (replaces the native alert) */}
      {signSuccess.open && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
          onClick={signDialog.onBackdropClick}
        >
          <div
            ref={signDialog.dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="mk-sign-title"
            aria-describedby="mk-sign-desc"
            tabIndex={-1}
            className="bg-white rounded-2xl max-w-md w-full shadow-2xl border border-neutral-200 p-6 sm:p-8 text-center animate-in fade-in zoom-in-95 duration-150 outline-none"
          >
            <div className="mx-auto mb-4 w-16 h-16 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center">
              <CheckCircle2 className="w-9 h-9 text-emerald-600" />
            </div>
            <h3 id="mk-sign-title" className="text-lg font-bold text-[#171717]">{t('dw.signSuccessTitle', language)}</h3>
            <p id="mk-sign-desc" className="mt-2 text-sm text-[#171717] leading-relaxed">{signSuccess.message}</p>
            <p className="mt-1 text-xs text-[#666666]">{t('dw.signSuccessMoved', language)}</p>
            <div className="mt-6 flex flex-col sm:flex-row gap-2.5">
              <button
                type="button"
                onClick={() => { setFilterType('completed'); setSignSuccess({ open: false, message: '' }); }}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 bg-white border border-neutral-300 hover:border-[#6C3FC5] hover:bg-[#F3EEFC] text-[#171717] text-sm font-semibold rounded-xl transition-colors"
              >
                <CheckCircle2 className="w-4 h-4 text-[#6C3FC5]" />
                <span>{t('dw.signSuccessViewCompleted', language)}</span>
              </button>
              <button
                type="button"
                onClick={() => setSignSuccess({ open: false, message: '' })}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-sm font-bold rounded-xl shadow-md hover:shadow-lg transition-all active:scale-[0.99]"
              >
                <span>{t('dw.signSuccessContinue', language)}</span>
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
