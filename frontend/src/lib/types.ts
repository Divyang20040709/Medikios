export type UserRole = 'patient' | 'physician' | 'admin';

export type LanguageCode = 'en' | 'hi' | 'gu';

export interface LanguageOption {
  code: LanguageCode;
  label: string;
  native: string;
  greeting?: string;
}

export type ConsultationType = 'modern' | 'ayush';

export type PatientStatus = 'waiting' | 'in_consultation' | 'completed' | 'triaged';

export interface Patient {
  id: string;
  token: string;
  abhaId?: string;
  encounterId?: string;
  sessionId?: string;
  mrn?: string;
  fullName: string;
  age: number;
  gender: 'Male' | 'Female' | 'Other';
  phone: string;
  city?: string;
  language: LanguageCode;
  consultationType: ConsultationType;
  department: string;
  /** Physician the encounter is routed to (General & Modern Medicine vs AYUSH), recorded when the kiosk saves the Step-4 stream choice. */
  assignedDoctorName?: string;
  isRegisteredNew: boolean;
  status: PatientStatus;
  isPriority: boolean;
  counterNumber: string;
  estimatedWaitMinutes: number;
  createdAt: string;
}

export interface SocratesData {
  site: string;
  onset: string;
  character: string;
  radiation: string;
  associations: string[];
  timing: string;
  exacerbatingFactors: string;
  relievingFactors: string;
  severityScore: number;
}

export interface PastCondition {
  id: string;
  condition: string;
  diagnosedYear: string;
  status: 'active' | 'managed' | 'resolved';
  notes?: string;
}

export interface PastProcedure {
  id: string;
  procedure: string;
  approxDate: string;
  hospitalOrReason?: string;
}

export interface Medication {
  id: string;
  name: string;
  dose: string;
  frequency: string;
  duration?: string;
}

export interface Allergy {
  id: string;
  category: 'drug' | 'food' | 'environmental';
  allergen: string;
  reaction: string;
  severity: 'mild' | 'moderate' | 'severe';
}

export interface FamilyHistoryItem {
  relation: string;
  condition: string;
}

export interface PersonalHistory {
  diet: string;
  sleepHours: string;
  exercise: string;
  tobacco: string;
  alcohol: string;
  occupation: string;
}

export interface ReviewOfSystems {
  general: string[];
  cardiovascular: string[];
  respiratory: string[];
  gastrointestinal: string[];
  neurological: string[];
  genitourinary: string[];
  musculoskeletal: string[];
  dermatological: string[];
}

export interface AyushAssessment {
  id: string;
  patientId: string;
  prakriti: string;
  vikriti: string;
  sara: string;
  samhanana: string;
  pramana: string;
  satmya: string;
  sattva: string;
  aharaShakti: string;
  vyayamaShakti: string;
  vaya: string;
  agni: string;
  koshtha: string;
  ahara: string;
  vihara: string;
  nidana: string;
  sampraptiSummary: string;
}

export interface ChiefComplaintItem {
  complaint: string;
  duration: string;
  severity: number;
}

export interface ClinicalCase {
  id: string;
  patientId: string;
  consultationType: ConsultationType;
  status: 'intake_pending' | 'intake_completed' | 'consulted';
  chiefComplaints: ChiefComplaintItem[];
  hpiNarrative: string;
  socrates?: SocratesData;
  pastMedicalHistory: PastCondition[];
  pastSurgicalHistory: PastProcedure[];
  medications: Medication[];
  allergies: Allergy[];
  familyHistory: FamilyHistoryItem[];
  personalHistory: PersonalHistory;
  reviewOfSystems: ReviewOfSystems;
  ayushAssessment?: AyushAssessment;
  hasRedFlags: boolean;
  redFlagReason?: string;
  aiDraftGeneratedAt: string;
  physicianReviewed: boolean;
  physicianReviewedBy?: string;
  physicianNotes?: string;
}

export interface TestResult {
  id: string;
  patientId: string;
  testName: string;
  date: string;
  result: string;
  unit: string;
  referenceRange: string;
  isAbnormal: boolean;
  clinicalSignificance?: string;
}

export interface ExtractedDocumentData {
  diagnoses: string[];
  medications: Array<{ name: string; dosage: string }>;
  investigations: Array<{ test: string; result: string; unit: string }>;
  procedures: string[];
  confidenceScore: number;
}

export interface DocumentItem {
  id: string;
  patientId: string;
  title: string;
  documentType: 'Prescription' | 'Laboratory Report' | 'Discharge Summary' | 'Imaging Report' | 'Previous Consultation';
  documentDate: string;
  fileUrl: string;
  status: 'pending' | 'verified';
  extractedData: ExtractedDocumentData;
  isVerifiedByPhysician: boolean;
  /** Backend OCR outcome for real uploads (demo/simulated documents have none). */
  ocrStatus?: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'NO_TEXT' | 'FAILED';
}

export interface TimelineItem {
  id: string;
  patientId: string;
  year: string;
  month: string;
  dateStr: string;
  type: 'prescription' | 'investigation' | 'consultation' | 'surgery';
  title: string;
  institution: string;
  summary: string;
  documentId?: string;
}

export interface RedFlag {
  id: string;
  patientId: string;
  patientName: string;
  token: string;
  triggerCondition: string;
  detectedAt: string;
  status: 'active' | 'triaged';
  physicianNote?: string;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  patientId: string;
  actor: string;
  action: string;
  details: string;
}

export interface ConsentRecord {
  patientId: string;
  clinicalInfoCollection: boolean;
  documentProcessing: boolean;
  staffSharing: boolean;
  signedAt: string;
}

export interface AccessibilitySettings {
  language: LanguageCode;
  textSize: 'normal' | 'large' | 'extra-large';
  highContrast: boolean;
  audioAssistance: boolean;
  screenReader: boolean;
}
