import {
  Patient,
  ClinicalCase,
  TestResult,
  DocumentItem,
  TimelineItem,
  RedFlag,
  AuditLog,
  ConsentRecord,
  LanguageCode,
  ExtractedDocumentData
} from './types';

export const DEFAULT_PATIENT: Patient = {
  id: '',
  token: '',
  fullName: '',
  age: 0,
  gender: 'Male',
  phone: '',
  city: '',
  language: 'en',
  consultationType: 'modern',
  department: 'General Medicine',
  isRegisteredNew: true,
  status: 'waiting',
  isPriority: false,
  counterNumber: '',
  estimatedWaitMinutes: 0,
  createdAt: ''
};

export const INITIAL_PATIENTS: Patient[] = [];

export const INITIAL_CASES: Record<string, ClinicalCase> = {};
export const INITIAL_TESTS: TestResult[] = [];
export const INITIAL_DOCS: DocumentItem[] = [];
export const INITIAL_TIMELINE: TimelineItem[] = [];
export const INITIAL_RED_FLAGS: RedFlag[] = [];
export const INITIAL_AUDIT_LOGS: AuditLog[] = [];

export const POSTGRES_SCHEMA_SQL = `-- MediKiosk Production Database Schema
-- Smart India Hackathon | ABDM Sandbox & FHIR R4 Ready
-- Implements Row Level Security (RLS) & Audit Logging

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum Types
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('patient', 'physician', 'triage_nurse', 'admin');
  CREATE TYPE consultation_type AS ENUM ('modern', 'ayush');
  CREATE TYPE case_status AS ENUM ('intake_pending', 'intake_completed', 'consulted', 'triaged');
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

-- 1. Patients Table
CREATE TABLE IF NOT EXISTS public.patients (
  id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  abha_id TEXT,
  full_name TEXT NOT NULL,
  age INTEGER NOT NULL,
  gender TEXT NOT NULL,
  phone TEXT NOT NULL,
  city TEXT,
  language TEXT DEFAULT 'en',
  consultation_type consultation_type DEFAULT 'modern',
  department TEXT NOT NULL,
  status TEXT DEFAULT 'waiting',
  is_priority BOOLEAN DEFAULT FALSE,
  counter_number TEXT,
  estimated_wait_minutes INTEGER DEFAULT 15,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Digital Informed Consents (DPDP Act 2023 Compliant)
CREATE TABLE IF NOT EXISTS public.consents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  patient_id TEXT REFERENCES public.patients(id) ON DELETE CASCADE,
  clinical_info_collection BOOLEAN DEFAULT TRUE,
  document_processing BOOLEAN DEFAULT TRUE,
  staff_sharing BOOLEAN DEFAULT TRUE,
  signed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Clinical Cases Table (AI Synthesized History)
CREATE TABLE IF NOT EXISTS public.clinical_cases (
  id TEXT PRIMARY KEY,
  patient_id TEXT REFERENCES public.patients(id) ON DELETE CASCADE,
  consultation_type consultation_type NOT NULL,
  status case_status DEFAULT 'intake_pending',
  chief_complaints JSONB DEFAULT '[]'::jsonb,
  hpi_narrative TEXT,
  socrates JSONB,
  has_red_flags BOOLEAN DEFAULT FALSE,
  red_flag_reason TEXT,
  ai_draft_generated_at TIMESTAMPTZ DEFAULT NOW(),
  physician_reviewed BOOLEAN DEFAULT FALSE,
  physician_reviewed_by TEXT,
  physician_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Medical Documents (OCR Extracted Records)
CREATE TABLE IF NOT EXISTS public.documents (
  id TEXT PRIMARY KEY,
  patient_id TEXT REFERENCES public.patients(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  document_type TEXT NOT NULL,
  document_date TEXT,
  file_url TEXT,
  extracted_data JSONB,
  is_verified_by_physician BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Priority Safety Red Flags
CREATE TABLE IF NOT EXISTS public.red_flags (
  id TEXT PRIMARY KEY,
  patient_id TEXT REFERENCES public.patients(id) ON DELETE CASCADE,
  patient_name TEXT NOT NULL,
  token TEXT NOT NULL,
  trigger_condition TEXT NOT NULL,
  detected_at TIMESTAMPTZ DEFAULT NOW(),
  status TEXT DEFAULT 'active',
  physician_note TEXT
);

-- 6. Audit Trail & Access Logs
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id TEXT PRIMARY KEY,
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  patient_id TEXT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  details TEXT
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clinical_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.red_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Sample RLS Policies
CREATE POLICY "Allow public kiosk intake inserts" ON public.patients FOR ALL USING (true);
CREATE POLICY "Allow case read for active encounters" ON public.clinical_cases FOR ALL USING (true);
CREATE POLICY "Allow clinical staff full access" ON public.documents FOR ALL USING (true);
`;

class ClinicalStore {
  private patients: Patient[] = [];
  private clinicalCases: Record<string, ClinicalCase> = {};
  private tests: TestResult[] = [];
  private documents: DocumentItem[] = [];
  private timeline: TimelineItem[] = [];
  private redFlags: RedFlag[] = [];
  private auditLogs: AuditLog[] = [];
  private consents: Record<string, ConsentRecord> = {};
  private listeners: Array<() => void> = [];

  constructor() {
    this.loadState();
  }

  private loadState() {
    if (typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem('medikiosk_state_v3');
        if (stored) {
          const parsed = JSON.parse(stored);
          this.patients = parsed.patients || INITIAL_PATIENTS;
          this.clinicalCases = parsed.clinicalCases || INITIAL_CASES;
          this.tests = parsed.tests || INITIAL_TESTS;
          this.documents = parsed.documents || INITIAL_DOCS;
          this.timeline = parsed.timeline || INITIAL_TIMELINE;
          this.redFlags = parsed.redFlags || INITIAL_RED_FLAGS;
          this.auditLogs = parsed.auditLogs || INITIAL_AUDIT_LOGS;
          this.consents = parsed.consents || {};
          return;
        }
      } catch (err) {
        console.error('Failed to parse stored state, resetting to defaults', err);
      }
    }
    this.resetToDefaults();
  }

  public saveState() {
    if (typeof window !== 'undefined') {
      try {
        const payload = {
          patients: this.patients,
          clinicalCases: this.clinicalCases,
          tests: this.tests,
          documents: this.documents,
          timeline: this.timeline,
          redFlags: this.redFlags,
          auditLogs: this.auditLogs,
          consents: this.consents
        };
        localStorage.setItem('medikiosk_state_v3', JSON.stringify(payload));
      } catch (err) {
        console.error('Failed to save state to localStorage', err);
      }
    }
    this.notify();
  }

  public resetToDefaults() {
    this.patients = JSON.parse(JSON.stringify(INITIAL_PATIENTS));
    this.clinicalCases = JSON.parse(JSON.stringify(INITIAL_CASES));
    this.tests = JSON.parse(JSON.stringify(INITIAL_TESTS));
    this.documents = JSON.parse(JSON.stringify(INITIAL_DOCS));
    this.timeline = JSON.parse(JSON.stringify(INITIAL_TIMELINE));
    this.redFlags = JSON.parse(JSON.stringify(INITIAL_RED_FLAGS));
    this.auditLogs = JSON.parse(JSON.stringify(INITIAL_AUDIT_LOGS));
    this.consents = {};
    this.saveState();
  }

  public subscribe(fn: () => void): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter(l => l !== fn);
    };
  }

  private notify() {
    this.listeners.forEach(fn => fn());
  }

  public getPatients(): Patient[] {
    return [...this.patients];
  }

  public getPatientById(id: string): Patient | undefined {
    return this.patients.find(p => p.id === id);
  }

  public addOrUpdatePatient(p: Patient): Patient {
    const idx = this.patients.findIndex(item => item.id === p.id);
    if (idx >= 0) {
      this.patients[idx] = p;
    } else {
      this.patients.unshift(p);
    }
    this.logAudit(p.id, "Patient Registered / Updated", `ID: ${p.id}, Name: ${p.fullName}`);
    this.saveState();
    return p;
  }

  public updatePatientStatus(id: string, status: Patient['status']) {
    const p = this.patients.find(item => item.id === id);
    if (p) {
      p.status = status;
      this.logAudit(id, "Patient Status Updated", `Status changed to ${status}`);
      this.saveState();
    }
  }

  public getCaseByPatientId(id: string): ClinicalCase | undefined {
    return this.clinicalCases[id];
  }

  public saveCase(c: ClinicalCase): ClinicalCase {
    this.clinicalCases[c.patientId] = c;
    this.logAudit(c.patientId, "Case History Updated", `Draft timestamp: ${c.aiDraftGeneratedAt}`);
    this.saveState();
    return c;
  }

  public markCaseReviewed(patientId: string, physicianName: string, notes: string) {
    const c = this.clinicalCases[patientId];
    if (c) {
      c.physicianReviewed = true;
      c.physicianReviewedBy = physicianName;
      c.physicianNotes = notes;
      c.status = 'consulted';
      const patient = this.patients.find(p => p.id === patientId);
      if (patient) patient.status = 'completed';
      this.logAudit(patientId, "Physician Review Completed", `Signed by Dr. ${physicianName}`);
      this.saveState();
    }
  }

  public saveConsent(consent: ConsentRecord) {
    this.consents[consent.patientId] = consent;
    this.logAudit(consent.patientId, "Consent Captured", `Signed at: ${consent.signedAt}`);
    this.saveState();
  }

  public getConsent(patientId: string): ConsentRecord | undefined {
    return this.consents[patientId];
  }

  public getRedFlags(): RedFlag[] {
    return [...this.redFlags];
  }

  public triggerRedFlag(patient: Patient, condition: string): RedFlag {
    const existing = this.redFlags.find(rf => rf.patientId === patient.id && rf.status === 'active');
    if (existing) return existing;

    const rf: RedFlag = {
      id: `rf-${Date.now()}`,
      patientId: patient.id,
      patientName: patient.fullName,
      token: patient.token,
      triggerCondition: condition,
      detectedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'active'
    };
    this.redFlags.unshift(rf);
    patient.isPriority = true;
    this.logAudit(patient.id, "PRIORITY_RED_FLAG_RAISED", condition);
    this.saveState();
    return rf;
  }

  public acknowledgeRedFlag(flagId: string, physicianNote?: string) {
    const rf = this.redFlags.find(item => item.id === flagId);
    if (rf) {
      rf.status = 'triaged';
      if (physicianNote) rf.physicianNote = physicianNote;
      this.logAudit(rf.patientId, "Red Flag Triaged", `Acknowledged by physician. Note: ${physicianNote || 'None'}`);
      this.saveState();
    }
  }

  public getTestsByPatientId(patientId: string): TestResult[] {
    return this.tests.filter(t => t.patientId === patientId);
  }

  public getDocumentsByPatientId(patientId: string): DocumentItem[] {
    return this.documents.filter(d => d.patientId === patientId);
  }

  public addDocument(doc: DocumentItem) {
    this.documents.unshift(doc);
    this.logAudit(doc.patientId, "Document Uploaded", `${doc.title} (${doc.documentType})`);
    this.saveState();
  }

  public getTimelineByPatientId(patientId: string): TimelineItem[] {
    return this.timeline.filter(tl => tl.patientId === patientId);
  }

  public getAuditLogs(): AuditLog[] {
    return [...this.auditLogs];
  }

  public logAudit(patientId: string, action: string, details: string) {
    const log: AuditLog = {
      id: `log-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      patientId,
      actor: 'MediKiosk Clinical Rules Engine',
      action,
      details
    };
    this.auditLogs.unshift(log);
  }

  public getPostgresSchemaSql(): string {
    return POSTGRES_SCHEMA_SQL;
  }
}

export const clinicalStore = new ClinicalStore();

export class ClinicalRulesEngine {
  public static checkRedFlags(complaint: string, socrates?: { radiation?: string; associations?: string[]; site?: string; severityScore?: number }): { hasRedFlag: boolean; reason?: string } {
    const combined = `${complaint} ${socrates?.radiation || ''} ${(socrates?.associations || []).join(' ')} ${socrates?.site || ''}`.toLowerCase();

    if (
      combined.includes('chest pain') ||
      combined.includes('chest discomfort') ||
      combined.includes('crushing') ||
      combined.includes('heart attack') ||
      combined.includes('सीने में दर्द') ||
      combined.includes('বুকে ব্যথা') ||
      (socrates?.severityScore && socrates.severityScore >= 8 && socrates.site?.toLowerCase().includes('chest'))
    ) {
      return {
        hasRedFlag: true,
        reason: 'Potential Acute Coronary Syndrome (ACS) or Severe Cardiac Ischemia indicator. Requires immediate triage review.'
      };
    }

    if (
      combined.includes('breathing difficulty') ||
      combined.includes('shortness of breath') ||
      combined.includes('cannot breathe') ||
      combined.includes('gasping') ||
      combined.includes('सांस लेने में तकलीफ')
    ) {
      return {
        hasRedFlag: true,
        reason: 'Severe respiratory distress suspected. Requires immediate oxygen saturation and triage check.'
      };
    }

    if (
      combined.includes('sudden weakness') ||
      combined.includes('difficulty speaking') ||
      combined.includes('slurred speech') ||
      combined.includes('facial drooping') ||
      combined.includes('loss of consciousness') ||
      combined.includes('fainted')
    ) {
      return {
        hasRedFlag: true,
        reason: 'Acute focal neurological deficit or syncope indicator (FAST Stroke warning). Immediate clinical attention required.'
      };
    }

    return { hasRedFlag: false };
  }

  public static async simulateOcrExtraction(category: string, filename?: string): Promise<ExtractedDocumentData> {
    await new Promise(resolve => setTimeout(resolve, 2000));

    if (category === 'Prescription') {
      return {
        diagnoses: ['Essential Hypertension (Stage 1)', 'Mild Dyslipidemia'],
        medications: [
          { name: 'Tab Telmisartan', dosage: '40 mg OD morning' },
          { name: 'Tab Atorvastatin', dosage: '10 mg HS bedtime' }
        ],
        investigations: [
          { test: 'Serum Creatinine', result: '1.02', unit: 'mg/dL' },
          { test: 'Lipid Profile', result: 'Total Cholesterol 228', unit: 'mg/dL' }
        ],
        procedures: ['Advised BP monitoring log'],
        confidenceScore: 95
      };
    }

    if (category === 'Laboratory Report') {
      return {
        diagnoses: ['Platelet count reduction / Suspected viral thrombopathy'],
        medications: [],
        investigations: [
          { test: 'Platelet Count', result: '62,000', unit: '/mcL (Low)' },
          { test: 'Hemoglobin', result: '11.8', unit: 'g/dL' },
          { test: 'Total WBC', result: '3,800', unit: '/cumm' }
        ],
        procedures: ['Complete Blood Count (Automated Analyzer)'],
        confidenceScore: 97
      };
    }

    if (category === 'Discharge Summary') {
      return {
        diagnoses: ['Acute Appendicitis (Resolved)', 'Post-operative Day 5'],
        medications: [
          { name: 'Tab Cefuroxime Axetil', dosage: '500 mg BD x 5 days' },
          { name: 'Tab Pantoprazole', dosage: '40 mg OD before breakfast' }
        ],
        investigations: [
          { test: 'Ultrasound Abdomen', result: 'Inflamed tubular structure in RIF', unit: '' }
        ],
        procedures: ['Laparoscopic Appendectomy under GA'],
        confidenceScore: 92
      };
    }

    return {
      diagnoses: ['Clinical review required'],
      medications: [{ name: 'Tab Paracetamol', dosage: '650 mg SOS' }],
      investigations: [{ test: 'Blood Pressure', result: '136/84', unit: 'mmHg' }],
      procedures: ['Routine Vital Check'],
      confidenceScore: 89
    };
  }
}

export class SpeechAssistant {
  private static synth: SpeechSynthesis | null = typeof window !== 'undefined' ? window.speechSynthesis : null;

  public static speak(text: string, lang: LanguageCode = 'en') {
    if (this.synth) {
      try {
        this.synth.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        switch (lang) {
          case 'hi':
            utterance.lang = 'hi-IN';
            break;
          case 'gu':
            utterance.lang = 'gu-IN';
            break;
          default:
            utterance.lang = 'en-IN';
            break;
        }
        utterance.rate = 0.95;
        this.synth.speak(utterance);
      } catch (err) {
        console.error('Speech synthesis error:', err);
      }
    }
  }

  public static stopSpeaking() {
    if (this.synth) {
      try {
        this.synth.cancel();
      } catch (err) {
        console.error('Stop speaking error:', err);
      }
    }
  }

  public static isSpeechRecognitionSupported(): boolean {
    if (typeof window === 'undefined') return false;
    const win = window as any;
    return !!(win.SpeechRecognition || win.webkitSpeechRecognition);
  }

  public static startListening(
    lang: LanguageCode,
    onResult: (transcript: string) => void,
    onError?: (err: any) => void
  ): () => void {
    if (typeof window === 'undefined') return () => {};
    const win = window as any;
    const SpeechRecognition = win.SpeechRecognition || win.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      if (onError) {
        onError(new Error("Browser Web Speech API is not supported in this browser. Please use the microphone recording option."));
      }
      return () => {};
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = lang === 'hi' ? 'hi-IN' : lang === 'gu' ? 'gu-IN' : 'en-IN';

      recognition.onresult = (event: any) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) onResult(transcript);
      };

      recognition.onerror = (err: any) => {
        if (onError) onError(err);
      };

      recognition.start();
      return () => {
        try {
          recognition.stop();
        } catch {
          // Ignore
        }
      };
    } catch (err) {
      if (onError) onError(err);
      return () => {};
    }
  }
}
