'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { UserCheck, Stethoscope, Building2, ArrowRight, Loader2, AlertCircle, Activity } from 'lucide-react';

import { clinicalStore } from '@/lib/clinicalStore';
import { roleCanOpen, safeNextTarget } from '@/lib/auth';
import { Patient } from '@/lib/types';

export default function LoginPage() {
  const router = useRouter();
  // QA-13: pre-filled demo credentials are a development convenience only.
  // Next.js inlines NODE_ENV at build time, so a production bundle ships with
  // DEMO_PREFILL_ENABLED === false and every field starts empty instead of
  // handing out a working staff account.
  const DEMO_PREFILL_ENABLED = process.env.NODE_ENV !== 'production';
  const DEMO_DOCTOR_ID = 'general@hospital.in';
  const DEMO_ADMIN_ID = 'admin@hospital.in';
  const DEMO_PATIENT_ID = '91-8832-1102-9912';
  const prefilled = (value: string) => (DEMO_PREFILL_ENABLED ? value : '');

  const [role, setRole] = useState<'PATIENT' | 'DOCTOR' | 'ADMIN'>('DOCTOR');
  const [identifier, setIdentifier] = useState(prefilled(DEMO_DOCTOR_ID));
  const [password, setPassword] = useState(prefilled(DEMO_DOCTOR_ID));
  const [patientName, setPatientName] = useState('Rajesh Kumar');
  const [patientAge, setPatientAge] = useState('45');
  const [patientGender, setPatientGender] = useState<'Male' | 'Female' | 'Other'>('Male');
  const [patientDepartment, setPatientDepartment] = useState('General Medicine');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  // QA BUG-010: explicit, styled client-side validation for the patient register
  // fields instead of relying solely on native HTML5 messages (which are inconsistent
  // across kiosk browsers / assistive tech). Server-side validation remains the backstop.
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const handleRoleChange = (newRole: 'PATIENT' | 'DOCTOR' | 'ADMIN') => {
    setRole(newRole);
    setErrorMsg('');
    setFieldErrors({});
    if (newRole === 'DOCTOR') {
      setIdentifier(prefilled(DEMO_DOCTOR_ID));
      setPassword(prefilled(DEMO_DOCTOR_ID));
    } else if (newRole === 'ADMIN') {
      setIdentifier(prefilled(DEMO_ADMIN_ID));
      setPassword(prefilled(DEMO_ADMIN_ID));
    } else {
      setIdentifier(prefilled(DEMO_PATIENT_ID));
      setPassword('');
    }
  };

  // A homepage role link (e.g. /login?role=doctor) preselects that tab. Only the
  // three known roles are accepted; anything else is ignored so we never trust an
  // arbitrary value. This is a UI convenience only — the backend still verifies
  // the real role, and staff sign-in requires a matching password.
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('role')?.toUpperCase();
    if (requested === 'PATIENT' || requested === 'DOCTOR' || requested === 'ADMIN') {
      handleRoleChange(requested);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const validatePatientRegister = (): boolean => {
    const errs: Record<string, string> = {};
    if (!patientName.trim()) errs.patientName = 'Full name is required.';
    const ageNum = parseInt(patientAge, 10);
    if (!patientAge.trim() || Number.isNaN(ageNum) || ageNum < 1 || ageNum > 120) {
      errs.patientAge = 'Enter a valid age between 1 and 120.';
    }
    if (!patientGender) errs.patientGender = 'Please select a gender.';
    if (!patientDepartment.trim()) errs.patientDepartment = 'Please select an OPD department.';
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');

    // QA BUG-010: the form is noValidate so we control messaging with explicit,
    // styled feedback instead of native HTML5 bubbles (unreliable on kiosk
    // browsers / assistive tech). Server-side validation remains the backstop.
    if (role === 'PATIENT') {
      if (!validatePatientRegister()) return;
    } else {
      const errs: Record<string, string> = {};
      if (!identifier.trim()) errs.identifier = role === 'DOCTOR' ? 'Doctor email or registration number is required.' : 'Admin email is required.';
      if (!password) errs.password = 'Password is required.';
      setFieldErrors(errs);
      if (Object.keys(errs).length > 0) return;
    }
    setFieldErrors({});
    setIsLoading(true);

    try {
      const payload: any = {
        identifier,
        password: password || undefined,
        role,
      };

      if (role === 'PATIENT') {
        payload.name = patientName.trim();
        payload.age = parseInt(patientAge) || 35;
        payload.gender = patientGender;
        payload.department = patientDepartment;
      }

      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      // Parse error bodies defensively: FastAPI errors are JSON ({detail}),
      // but the Next.js /api proxy answers its own plain-text 500 when the
      // backend is unreachable. Never let res.json() throw a parse error
      // into the user's face ("Unexpected token 'I', \"Internal S\"...").
      const readDetail = async (fallback: string): Promise<string> => {
        try {
          const err = await res.json();
          if (typeof err?.detail === 'string' && err.detail.trim()) return err.detail;
        } catch {
          /* non-JSON body — use the fallback below */
        }
        return fallback;
      };

      if (!res.ok) {
        const fallback = res.status >= 500
          ? 'Cannot reach the MediKiosk server. It may be offline \u2014 please try again in a moment.'
          : 'Login failed. Please check your credentials and try again.';
        throw new Error(await readDetail(fallback));
      }

      let data: any;
      try {
        data = await res.json();
      } catch {
        throw new Error('Received an unreadable response from the server. Please try again.');
      }
      localStorage.setItem('medikiosk_token', data.access_token);
      localStorage.setItem('medikiosk_user', JSON.stringify(data));

      // QA BUG-003: return the user to the protected page that started sign-in
      // (?next=...). Only same-origin paths that are not another login page are
      // accepted, and patients never carry a protected destination. The target
      // must also be one THIS role can open — otherwise a DOCTOR signing in from
      // ?next=/admin would be dropped back on the guard's denied panel.
      const requested =
        role === 'PATIENT' ? null : safeNextTarget(new URLSearchParams(window.location.search));
      const preserved = requested && roleCanOpen(data.role, requested) ? requested : null;

      if (data.role === 'DOCTOR') {
        router.push(preserved || '/doctor');
      } else if (data.role === 'ADMIN') {
        router.push(preserved || '/admin');
      } else {
        const newPatient: Patient = {
          id: data.user_id,
          token: `T-${Math.floor(10 + Math.random() * 90)}`,
          abhaId: identifier.includes('-') ? identifier : undefined,
          fullName: patientName.trim() || data.name || 'Patient',
          age: parseInt(patientAge) || 35,
          gender: patientGender,
          phone: identifier.includes('-') ? '+91 98765 43210' : identifier,
          language: 'en',
          consultationType: 'modern',
          department: patientDepartment,
          isRegisteredNew: true,
          status: 'waiting',
          isPriority: false,
          counterNumber: 'Counter 01',
          estimatedWaitMinutes: 5,
          createdAt: new Date().toISOString()
        };
        clinicalStore.addOrUpdatePatient(newPatient);
        router.push('/patient/intake');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Network error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen w-full flex flex-col bg-white text-[#171717] font-sans selection:bg-[#6C3FC5] selection:text-white">
      {/* Top brand bar (matches KioskHeader styling) */}
      <header className="w-full border-b border-neutral-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center">
          <Link href="/" className="flex items-center gap-2.5 hover:opacity-90 transition-opacity">
            <div className="w-9 h-9 rounded-lg bg-[#6C3FC5] flex items-center justify-center text-white shadow-sm flex-shrink-0">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <span className="font-sans font-extrabold text-2xl tracking-tight">
              Medi<span className="text-[#6C3FC5]">Kiosk</span>
            </span>
          </Link>
        </div>
      </header>

      {/* Centered sign-in area */}
      <div className="flex-1 w-full flex items-center justify-center px-4 sm:px-6 py-10 sm:py-14 bg-gradient-to-b from-[#F3EEFC]/40 to-white">
        <div className="w-full max-w-md">
          {/* Heading */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] text-xs font-semibold mb-4">
              <Stethoscope className="w-3.5 h-3.5" />
              <span>Role-based clinical intake &amp; management system</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-sans font-extrabold text-[#171717] tracking-tight">
              Hospital Portal Sign In
            </h1>
          </div>

          {/* Login Card */}
          <div className="bg-white rounded-2xl border border-neutral-200 shadow-xl p-6 sm:p-8">
            {/* Role Tabs */}
            <div className="grid grid-cols-3 gap-1.5 p-1.5 rounded-xl bg-[#F3EEFC] border border-[#6C3FC5]/15 mb-6">
              <button
                type="button"
                onClick={() => handleRoleChange('PATIENT')}
                className={`py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                  role === 'PATIENT'
                    ? 'bg-[#6C3FC5] text-white shadow-xs'
                    : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
                }`}
              >
                <UserCheck className="h-3.5 w-3.5" />
                <span>Patient</span>
              </button>
              <button
                type="button"
                onClick={() => handleRoleChange('DOCTOR')}
                className={`py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                  role === 'DOCTOR'
                    ? 'bg-[#6C3FC5] text-white shadow-xs'
                    : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
                }`}
              >
                <Stethoscope className="h-3.5 w-3.5" />
                <span>Doctor</span>
              </button>
              <button
                type="button"
                onClick={() => handleRoleChange('ADMIN')}
                className={`py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                  role === 'ADMIN'
                    ? 'bg-[#6C3FC5] text-white shadow-xs'
                    : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
                }`}
              >
                <Building2 className="h-3.5 w-3.5" />
                <span>Admin</span>
              </button>
            </div>

            {errorMsg && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-4">
              {role === 'PATIENT' && (
                <div>
                  <label className="block text-xs font-semibold text-[#171717] mb-1.5">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    aria-invalid={!!fieldErrors.patientName}
                    value={patientName}
                    onChange={(e) => { setPatientName(e.target.value); setFieldErrors((p) => ({ ...p, patientName: '' })); }}
                    placeholder="e.g. Rajesh Kumar"
                    className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] placeholder-neutral-400 text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.patientName ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                  />
                  {fieldErrors.patientName && (
                    <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.patientName}
                    </p>
                  )}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-[#171717] mb-1.5">
                  {role === 'PATIENT'
                    ? 'ABHA ID / Mobile Number / MRN'
                    : role === 'DOCTOR'
                    ? 'Doctor Email or Reg No'
                    : 'Hospital Admin Email'}
                </label>
                <input
                  type="text"
                  required
                  aria-invalid={!!fieldErrors.identifier}
                  value={identifier}
                  onChange={(e) => { setIdentifier(e.target.value); setFieldErrors((p) => ({ ...p, identifier: '' })); }}
                  placeholder={
                    role === 'PATIENT'
                      ? '91-8832-1102-9912 or 9830112233'
                      : role === 'DOCTOR'
                      ? 'general@hospital.in or ayush@hospital.in'
                      : 'admin@hospital.in'
                  }
                  className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] placeholder-neutral-400 text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.identifier ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                />
                {fieldErrors.identifier && (
                  <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.identifier}
                  </p>
                )}
              </div>

              {role === 'PATIENT' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-[#171717] mb-1.5">Age</label>
                      <input
                        type="number"
                        min="1"
                        max="120"
                        required
                        aria-invalid={!!fieldErrors.patientAge}
                        value={patientAge}
                        onChange={(e) => { setPatientAge(e.target.value); setFieldErrors((p) => ({ ...p, patientAge: '' })); }}
                        className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] placeholder-neutral-400 text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.patientAge ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                      />
                      {fieldErrors.patientAge && (
                        <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.patientAge}
                        </p>
                      )}
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[#171717] mb-1.5">Gender</label>
                      <select
                        required
                        aria-invalid={!!fieldErrors.patientGender}
                        value={patientGender}
                        onChange={(e) => { setPatientGender(e.target.value as any); setFieldErrors((p) => ({ ...p, patientGender: '' })); }}
                        className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.patientGender ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                      >
                        <option value="">Select…</option>
                        <option value="Male">Male</option>
                        <option value="Female">Female</option>
                        <option value="Other">Other</option>
                      </select>
                      {fieldErrors.patientGender && (
                        <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                          <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.patientGender}
                        </p>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#171717] mb-1.5">OPD Department</label>
                    <select
                      required
                      aria-invalid={!!fieldErrors.patientDepartment}
                      value={patientDepartment}
                      onChange={(e) => { setPatientDepartment(e.target.value); setFieldErrors((p) => ({ ...p, patientDepartment: '' })); }}
                      className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.patientDepartment ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                    >
                      <option value="">Select department…</option>
                      <option value="General Medicine">General Medicine</option>
                      <option value="Cardiology / Acute Medicine">Cardiology</option>
                      <option value="Pulmonology / Chest Clinic">Pulmonology</option>
                      <option value="AYUSH / Kayachikitsa OPD">AYUSH / Kayachikitsa</option>
                      <option value="Geriatric Medicine">Geriatric Medicine</option>
                    </select>
                    {fieldErrors.patientDepartment && (
                      <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.patientDepartment}
                      </p>
                    )}
                  </div>
                </>
              )}

              {role !== 'PATIENT' && (
                <div>
                  <label className="block text-xs font-semibold text-[#171717] mb-1.5">
                    Password
                  </label>
                  <input
                    type="password"
                    required
                    aria-invalid={!!fieldErrors.password}
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); setFieldErrors((p) => ({ ...p, password: '' })); }}
                    placeholder={'\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
                    className={`w-full px-4 py-3 rounded-xl bg-white border text-[#171717] placeholder-neutral-400 text-sm focus:outline-none focus:ring-2 transition-all ${fieldErrors.password ? 'border-red-400 focus:border-red-500 focus:ring-red-500/20' : 'border-neutral-300 focus:border-[#6C3FC5] focus:ring-[#6C3FC5]/20'}`}
                  />
                  {fieldErrors.password && (
                    <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3 shrink-0" />{fieldErrors.password}
                    </p>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3.5 px-6 rounded-xl bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-sm font-bold flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all active:scale-[0.99] disabled:opacity-60"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Authenticating...</span>
                  </>
                ) : (
                  <>
                    <span>
                      {role === 'PATIENT' ? 'Continue to Kiosk Intake' : 'Access Portal'}
                    </span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            {/* Development Quick Credentials — QA-13: these chips fill in a
                WORKING account in one click, so they are compiled out of
                production builds alongside the mount-time prefill. */}
            {DEMO_PREFILL_ENABLED && (
            <div className="mt-6 pt-4 border-t border-neutral-200 text-center">
              <span className="text-[11px] font-semibold text-[#666666] uppercase tracking-wider block mb-2">Development Demo Logins</span>
              <div className="flex flex-wrap justify-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    handleRoleChange('DOCTOR');
                    setIdentifier(DEMO_DOCTOR_ID);
                    setPassword(DEMO_DOCTOR_ID);
                  }}
                  className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] hover:bg-[#6C3FC5] hover:text-white transition-colors"
                >
                  Dr. Sengupta (General)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleRoleChange('DOCTOR');
                    setIdentifier('ayush@hospital.in');
                    setPassword('ayush@hospital.in');
                  }}
                  className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] hover:bg-[#6C3FC5] hover:text-white transition-colors"
                >
                  Dr. Sharma (AYUSH)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleRoleChange('PATIENT');
                    setIdentifier(DEMO_PATIENT_ID);
                  }}
                  className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] hover:bg-[#6C3FC5] hover:text-white transition-colors"
                >
                  Patient (Ramesh Kumar)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleRoleChange('ADMIN');
                    setIdentifier(DEMO_ADMIN_ID);
                    setPassword(DEMO_ADMIN_ID);
                  }}
                  className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#F3EEFC] border border-[#6C3FC5]/20 text-[#6C3FC5] hover:bg-[#6C3FC5] hover:text-white transition-colors"
                >
                  Admin
                </button>
              </div>
            </div>
            )}
          </div>

          <div className="mt-6 text-center text-sm text-[#666666]">
            <Link href="/" className="inline-flex items-center gap-1 hover:text-[#6C3FC5] transition-colors">
              <ArrowRight className="h-4 w-4 rotate-180" />
              <span>Back to Homepage</span>
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
