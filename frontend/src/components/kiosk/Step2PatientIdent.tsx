'use client';

import React, { useState } from 'react';
import { User, QrCode, Phone, ArrowRight, ArrowLeft, Search, Sparkles, Building2 } from 'lucide-react';
import { Patient, LanguageCode, ConsultationType } from '@/lib/types';
import { clinicalStore } from '@/lib/clinicalStore';
import { t } from '@/lib/i18n';

interface Step2PatientIdentProps {
  currentPatient?: Patient;
  onPatientIdentified: (patient: Patient) => void;
  onBack: () => void;
  demoPatients: Patient[];
  language?: LanguageCode;
  interviewLanguage?: LanguageCode;
}

export function Step2PatientIdent({
  currentPatient,
  onPatientIdentified,
  onBack,
  demoPatients,
  language = 'en',
  interviewLanguage,
}: Step2PatientIdentProps) {
  // Language the patient will answer the AI interview in (kept separate from
  // the interface language so header switches never change clinical intake locale).
  const patientInterviewLanguage = interviewLanguage ?? language;
  const [tab, setTab] = useState<'existing' | 'new'>('existing');
  const [searchQuery, setSearchQuery] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // New patient form fields
  const [fullName, setFullName] = useState('');
  const [age, setAge] = useState('');
  const [gender, setGender] = useState<'Male' | 'Female' | 'Other'>('Male');
  const [phone, setPhone] = useState('');
  const [city, setCity] = useState('');
  const [department, setDepartment] = useState('General Medicine');
  const [consultType, setConsultType] = useState<ConsultationType>('modern');

  const handleSearchExisting = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      setErrorMsg(t('s2.errEnterId', language));
      return;
    }

    const found = demoPatients.find(
      (p) =>
        p.id.toLowerCase() === query ||
        p.phone.replace(/\s+/g, '').includes(query.replace(/\s+/g, '')) ||
        (p.abhaId && p.abhaId.toLowerCase().includes(query)) ||
        p.fullName.toLowerCase().includes(query)
    );

    if (found) {
      onPatientIdentified(found);
    } else {
      setErrorMsg(t('s2.errNotFound', language));
    }
  };

  const handleRegisterNew = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName || !age || !phone) {
      setErrorMsg(t('s2.errRequired', language));
      return;
    }

    const newId = `P-${Math.floor(10000 + Math.random() * 90000)}`;
    const newToken = `T-${Math.floor(10 + Math.random() * 90)}`;
    const newPatient: Patient = {
      id: newId,
      token: newToken,
      fullName: fullName.trim(),
      age: parseInt(age) || 30,
      gender,
      phone: phone.trim(),
      city: city.trim() || 'New Delhi',
      language: patientInterviewLanguage,
      consultationType: consultType,
      department: consultType === 'ayush' ? 'AYUSH / Kayachikitsa OPD' : department,
      isRegisteredNew: true,
      status: 'waiting',
      isPriority: false,
      counterNumber: consultType === 'ayush' ? 'AYUSH Room 12' : 'Counter 02',
      estimatedWaitMinutes: 15,
      createdAt: new Date().toISOString().replace('T', ' ').substring(0, 16),
    };

    // Persist to the backend database and adopt the server-issued identifiers
    // (patient_id, encounter_id, session_id, token, MRN) so the SAME ids are
    // used from check-in through the physician workstation. Falls back to the
    // local-only patient when the backend is unreachable.
    let finalPatient = newPatient;
    try {
      const res = await fetch('/api/intake/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: fullName.trim(),
          age: parseInt(age) || 30,
          gender: gender.toUpperCase(),
          phone: phone.trim(),
          preferred_language: patientInterviewLanguage,
          department: consultType === 'ayush' ? 'AYUSH / Kayachikitsa OPD' : department
        })
      });
      if (res.ok) {
        const data = await res.json();
        finalPatient = {
          ...newPatient,
          id: data.patient_id || newPatient.id,
          encounterId: data.encounter_id || undefined,
          sessionId: data.session_id || undefined,
          token: data.token_number || newPatient.token,
          mrn: data.mrn || undefined,
          abhaId: data.abha_id || newPatient.abhaId,
        };
      } else {
        console.warn('Backend intake/init returned', res.status);
      }
    } catch (err) {
      console.warn('Could not register in backend database:', err);
    }

    clinicalStore.addOrUpdatePatient(finalPatient);
    onPatientIdentified(finalPatient);
  };

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Step Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">{t('s2.stepLabel', language)}</span>
          <span className="font-mono bg-[#F3EEFC] text-[#6C3FC5] px-2 py-0.5 rounded border border-[#6C3FC5]/20">
            KIOSK-TERMINAL-01
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          {t('s2.title', language)}
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          {t('s2.sub', language)}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-neutral-200">
        <button
          type="button"
          onClick={() => {
            setTab('existing');
            setErrorMsg('');
          }}
          className={`px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition-colors ${
            tab === 'existing'
              ? 'border-[#6C3FC5] text-[#6C3FC5]'
              : 'border-transparent text-[#666666] hover:text-[#171717]'
          }`}
        >
          {t('s2.tabExisting', language)}
        </button>
        <button
          type="button"
          onClick={() => {
            setTab('new');
            setErrorMsg('');
          }}
          className={`px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition-colors ${
            tab === 'new'
              ? 'border-[#6C3FC5] text-[#6C3FC5]'
              : 'border-transparent text-[#666666] hover:text-[#171717]'
          }`}
        >
          {t('s2.tabNew', language)}
        </button>
      </div>

      {errorMsg && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
          {errorMsg}
        </div>
      )}

      {/* Existing Patient Search */}
      {tab === 'existing' ? (
        <div className="space-y-6">
          <form onSubmit={handleSearchExisting} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-[#171717] block">
                {t('s2.searchLabel', language)}
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="e.g. P-10241, 98451 22301, or Rajesh Kumar"
                  className="w-full px-4 py-3 pl-10 bg-white border border-neutral-300 rounded-xl text-sm focus:border-[#6C3FC5] focus:ring-1 focus:ring-[#6C3FC5] focus:outline-none"
                />
                <Search className="w-4 h-4 text-[#666666] absolute left-3.5 top-3.5" />
              </div>
              <span className="text-[11px] text-[#666666] block">
                {t('s2.searchHint', language)}
              </span>
            </div>

            <button
              type="submit"
              className="w-full sm:w-auto px-6 py-2.5 bg-[#6C3FC5] hover:bg-[#4B238C] text-white rounded-lg text-xs sm:text-sm font-bold transition-colors"
            >
              {t('s2.searchBtn', language)}
            </button>
          </form>

          {/* Quick Demo Loader (only if demo patients available) */}
          {demoPatients && demoPatients.length > 0 ? (
            <div className="pt-4 border-t border-neutral-200 space-y-3">
              <div className="flex items-center gap-1.5 text-xs font-bold text-[#666666]">
                <Sparkles className="w-3.5 h-3.5 text-[#6C3FC5]" />
                <span>{t('s2.demoTitle', language)}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {demoPatients.slice(0, 4).map((patient) => (
                  <button
                    key={patient.id}
                    type="button"
                    onClick={() => onPatientIdentified(patient)}
                    className="text-left p-3 rounded-lg border border-neutral-200 hover:border-[#6C3FC5] bg-white hover:bg-[#F3EEFC]/30 transition-all flex items-center justify-between group"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-[#171717] group-hover:text-[#6C3FC5]">
                          {patient.fullName}
                        </span>
                        <span className="text-[11px] font-mono text-[#6C3FC5] bg-[#F3EEFC] px-1 py-0.2 rounded">
                          {patient.id}
                        </span>
                      </div>
                      <span className="text-[11px] text-[#666666]">
                        {patient.age}y {patient.gender} • {patient.department}
                      </span>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-[#666666] group-hover:translate-x-0.5 transition-transform" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="pt-4 border-t border-neutral-200 text-xs text-[#666666]">
              <span>{t('s2.ftvPrefix', language)} </span>
              <button
                type="button"
                onClick={() => setTab('new')}
                className="text-[#6C3FC5] font-bold underline hover:text-[#4B238C]"
              >
                {t('s2.ftvLink', language)}
              </button>
              <span> {t('s2.ftvSuffix', language)}</span>
            </div>
          )}
        </div>
      ) : (
        /* First-Time Registration Form */
        <form onSubmit={handleRegisterNew} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fName', language)}</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g. Rameshwar Prasad"
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fPhone', language)}</label>
              <input
                type="tel"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98765 43210"
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fAge', language)}</label>
              <input
                type="number"
                required
                value={age}
                onChange={(e) => setAge(e.target.value)}
                placeholder="e.g. 52"
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fGender', language)}</label>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as any)}
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              >
                <option value="Male">{t('s2.male', language)}</option>
                <option value="Female">{t('s2.female', language)}</option>
                <option value="Other">{t('s2.other', language)}</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fCity', language)}</label>
              <input
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="e.g. Varanasi, Uttar Pradesh"
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs font-bold text-[#171717]">{t('s2.fDept', language)}</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white border border-neutral-300 rounded-lg text-xs sm:text-sm focus:border-[#6C3FC5] focus:outline-none"
              >
                <option value="General Medicine">General Medicine</option>
                <option value="Cardiology">Cardiology</option>
                <option value="Pulmonology">Pulmonology</option>
                <option value="Endocrinology">Endocrinology & Diabetology</option>
                <option value="AYUSH / Kayachikitsa">AYUSH / Kayachikitsa</option>
              </select>
            </div>
          </div>

          <div className="p-3 bg-[#F3EEFC]/60 rounded-lg text-xs text-[#666666]">
            {t('s2.privacyNote', language)}
          </div>

          <button
            type="submit"
            className="w-full sm:w-auto px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl transition-colors shadow-sm"
          >
            {t('s2.registerBtn', language)}
          </button>
        </form>
      )}

      {/* Back button */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>{t('s2.back', language)}</span>
        </button>
      </div>
    </div>
  );
}
