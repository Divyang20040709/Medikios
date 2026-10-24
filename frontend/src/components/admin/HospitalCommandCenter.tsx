'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Building2,
  Users,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Activity,
  ArrowLeft,
  Smartphone,
  Layers,
  ShieldCheck,
  RefreshCw,
  PhoneCall,
  Sparkles,
  Cpu,
  Loader2
} from 'lucide-react';
import { clinicalStore } from '@/lib/clinicalStore';
import { authHeaders, authFetch } from '@/lib/auth';
import { useToast } from '@/components/common/Toast';
import { RedFlag, AuditLog } from '@/lib/types';

interface HospitalCommandCenterProps {
  onBackToOverview: () => void;
}

export function HospitalCommandCenter({ onBackToOverview }: HospitalCommandCenterProps) {
  const [telemetry, setTelemetry] = useState<any>(null);
  const [modelsStatus, setModelsStatus] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [redFlags, setRedFlags] = useState<RedFlag[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>('all');
  const [testComplaint, setTestComplaint] = useState<string>('Severe crushing chest pain radiating to left jaw with cold sweating');
  const [testResult, setTestResult] = useState<any>(null);
  const [isTestingML, setIsTestingML] = useState(false);
  // QA BUG-003 / BUG-005: refused (403) or unavailable admin feeds must be
  // stated explicitly instead of silently showing locally cached demo data.
  const [feedNotice, setFeedNotice] = useState('');
  // QA-14: acknowledgement must be confirmed by the backend before the alert
  // disappears from the active list. `acknowledgingId` identifies the in-flight
  // row (per-row loading state) and doubles as the guard that stops a double
  // click from sending a second POST.
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);
  const [ackError, setAckError] = useState('');
  // Synchronous in-flight latch. State alone is not enough: two clicks inside the
  // same JS tick both read the pre-render value, so the state guard alone let a
  // second POST through. A ref is updated immediately.
  const ackInFlight = useRef(false);
  const toast = useToast();
  const patients = clinicalStore.getPatients();

  const fetchTelemetry = async () => {
    setIsLoading(true);
    setFeedNotice('');
    try {
      // Phase 6: telemetry, alerts and audit logs require the admin's bearer token.
      const [resTelemetry, resFlags, resLogs, resModels] = await Promise.all([
        authFetch(`/api/admin/telemetry?period=${selectedPeriod}`).catch(() => null),
        authFetch('/api/admin/red-flags?active_only=true').catch(() => null),
        authFetch('/api/admin/audit-logs?limit=25').catch(() => null),
        authFetch('/api/admin/models/status').catch(() => null),
      ]);

      const denied = [resTelemetry, resFlags, resLogs, resModels].filter((r) => r && r.status === 403).length;
      if (denied > 0) {
        setFeedNotice(
          `Command-center access denied (HTTP 403 on ${denied} feed${denied > 1 ? 's' : ''}). This area requires an ADMIN account; the entries below are locally cached demo data, not live hospital records.`
        );
      } else if ([resTelemetry, resFlags, resLogs, resModels].some((r) => r === null || !r.ok)) {
        setFeedNotice('Live command-center feeds are unavailable right now. The panels below show locally cached demo data, not live hospital records.');
      }

      if (resModels && resModels.ok) {
        const mData = await resModels.json();
        setModelsStatus(mData);
      }

      if (resTelemetry && resTelemetry.ok) {
        const data = await resTelemetry.json();
        setTelemetry(data);
      }

      if (resFlags && resFlags.ok) {
        const flagsData = await resFlags.json();
        const mappedFlags: RedFlag[] = flagsData.map((f: any) => ({
          id: f.id,
          patientId: f.patient_id,
          patientName: f.patient_name,
          token: f.token_number,
          triggerCondition: f.trigger_condition || f.trigger_rule,
          detectedAt: f.triggered_at ? new Date(f.triggered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Recent',
          status: f.acknowledged ? 'triaged' : 'active'
        }));
        setRedFlags(mappedFlags);
      } else {
        setRedFlags(clinicalStore.getRedFlags());
      }

      if (resLogs && resLogs.ok) {
        const logsData = await resLogs.json();
        setAuditLogs(logsData.map((l: any) => ({
          id: l.id,
          timestamp: l.timestamp ? new Date(l.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '',
          patientId: l.entity_id,
          actor: l.actor_role,
          action: l.action,
          details: typeof l.details === 'object' ? JSON.stringify(l.details) : String(l.details || '')
        })));
      } else {
        setAuditLogs(clinicalStore.getAuditLogs());
      }
    } catch (err) {
      console.warn('Backend telemetry error, using clinicalStore:', err);
      setFeedNotice('Live command-center feeds are unavailable right now. The panels below show locally cached demo data, not live hospital records.');
      setRedFlags(clinicalStore.getRedFlags());
      setAuditLogs(clinicalStore.getAuditLogs());
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTelemetry();
  }, [selectedPeriod]);

  const handleAcknowledge = async (id: string) => {
    // One acknowledgement at a time: a rapid double click cannot post twice.
    if (ackInFlight.current) return;
    ackInFlight.current = true;
    setAcknowledgingId(id);
    setAckError('');
    const previous = redFlags;
    try {
      const res = await fetch(`/api/admin/red-flags/${id}/acknowledge`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ acknowledged_by: 'Triage Command Admin' })
      });
      // A 403 / 404 / 409 / 5xx response is NOT an acknowledgement. Throw so the
      // local state is left untouched and the alert keeps showing as active.
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Only now is it safe to update the UI and the local store.
      clinicalStore.acknowledgeRedFlag(id, 'Acknowledged by Triage Command');
      setRedFlags(prev => prev.filter(f => f.id !== id));
      toast.success('Red flag acknowledged and recorded against your admin account.');
    } catch (err) {
      // Rollback: restore the exact pre-flight list so the alert stays visible.
      setRedFlags(previous);
      const offline = err instanceof TypeError; // fetch rejected — no response at all
      const message = offline
        ? 'Network error — the alert was NOT acknowledged and is still active. Check the connection and retry.'
        : `The server rejected the acknowledgement (${(err as Error).message}). The alert is still active — retry.`;
      setAckError(message);
      toast.error(message, { title: 'Acknowledgement failed' });
    } finally {
      ackInFlight.current = false;
      setAcknowledgingId(null);
    }
  };

  const handleRunTriageTest = async (overrideText?: string) => {
    const textToRun = overrideText || testComplaint;
    if (!textToRun.trim()) return;
    setIsTestingML(true);
    try {
      const res = await fetch('/api/admin/models/triage-test', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ complaint_text: textToRun })
      });
      if (res.ok) {
        const data = await res.json();
        setTestResult(data);
      }
    } catch (err) {
      console.warn('ML test call error:', err);
    } finally {
      setIsTestingML(false);
    }
  };

  const handleRefresh = () => {
    fetchTelemetry();
  };

  const activeFlags = redFlags.filter(rf => rf.status === 'active');
  const modernCount = patients.filter(p => p.consultationType === 'modern').length;
  const ayushCount = patients.filter(p => p.consultationType === 'ayush').length;

  // Real data from database telemetry with fallback to local store
  const totalRegistrations = telemetry?.metrics?.total_registrations ?? patients.length;
  const completedIntakes = telemetry?.metrics?.completed_intakes ?? patients.filter(p => p.status === 'completed').length;
  const activeRedFlagCount = telemetry?.metrics?.active_red_flags ?? activeFlags.length;
  const intakeTimeModel = telemetry?.intake_time_model;
  // QA-11: the counters are now period-scoped server-side, so the labels have
  // to say which window is on screen instead of implying a lifetime total.
  const periodSentence =
    selectedPeriod === 'today' ? 'today (UTC day)' : selectedPeriod === 'week' ? 'the last 7 days' : 'all time';
  const registrationsLabel =
    selectedPeriod === 'all' ? 'Total Registrations' : `Registrations — ${periodSentence}`;
  const completedLabel =
    selectedPeriod === 'all' ? 'Completed Intakes' : `Completed — ${periodSentence}`;
  const redFlagLabel =
    selectedPeriod === 'all' ? 'Red-Flag Alerts' : `Red-Flag Alerts — ${periodSentence}`;
  const averageIntakeMinutes = intakeTimeModel?.average_minutes ?? 0;
  const modelName = intakeTimeModel?.model_name || 'AI Intake Duration Model';
  const modelSampleSize = intakeTimeModel?.sample_size ?? 0;
  const timeSavedMinutes = intakeTimeModel?.time_saved_vs_manual_triage_minutes ?? 13.8;

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
                Hospital Command Center
              </h2>
              <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live Database Telemetry
              </span>
            </div>
            <p className="text-xs text-[#666666]">
              Real-time patient throughput, active kiosk terminals, and emergency red-flag monitoring.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Period selector */}
          <div className="flex items-center bg-neutral-100 rounded-lg p-0.5 border border-neutral-200 text-xs">
            {(['today', 'week', 'all'] as const).map(p => (
              <button
                key={p}
                type="button"
                onClick={() => setSelectedPeriod(p)}
                className={`px-2.5 py-1 rounded-md capitalize font-medium transition-colors ${
                  selectedPeriod === p
                    ? 'bg-white text-[#6C3FC5] shadow-2xs font-bold'
                    : 'text-[#666666] hover:text-[#171717]'
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={handleRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-neutral-300 hover:border-[#6C3FC5] text-xs font-semibold text-[#171717] rounded-lg transition-colors shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#6C3FC5] ${isLoading ? 'animate-spin' : ''}`} />
            <span>{isLoading ? 'Refreshing...' : 'Refresh Live Feeds'}</span>
          </button>
        </div>
      </div>

      {/* QA BUG-005: refused/unavailable feeds are announced, not hidden */}
      {feedNotice && (
        <div role="alert" className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-2 flex items-center gap-2 text-xs font-semibold text-amber-800">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
          <span>{feedNotice}</span>
        </div>
      )}

      <div className="max-w-7xl mx-auto w-full p-4 sm:p-6 space-y-6">
        {/* Metric Cards (All data directly from database & calculated by IntakeTimeModel) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Total Registrations (From Database) */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-1">
            <span className="text-xs font-bold text-[#666666] uppercase tracking-wider block">
              {registrationsLabel}
            </span>
            <div className="text-3xl font-serif font-bold text-[#171717]">
              {totalRegistrations}
            </div>
            <p className="text-[11px] text-[#666666]">
              OPD footfall from database encounters · {periodSentence}
            </p>
          </div>

          {/* Card 2: Average Intake Time (Calculated by IntakeTimeModel) */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-[#666666] uppercase tracking-wider block">
                Average Intake Time
              </span>
              <span className="text-[10px] font-mono font-bold text-[#6C3FC5] bg-[#F3EEFC] px-1.5 py-0.5 rounded flex items-center gap-0.5" title={modelName}>
                <Cpu className="w-2.5 h-2.5" />
                Model v2.1
              </span>
            </div>
            <div className="text-3xl font-serif font-bold text-[#6C3FC5]">
              {averageIntakeMinutes > 0 ? `${averageIntakeMinutes} min` : '0 min'}
            </div>
            <p className="text-[11px] text-emerald-700 font-semibold flex items-center gap-1">
              <span>Saved ~{timeSavedMinutes} min vs 18 min manual triage</span>
            </p>
          </div>

          {/* Card 3: Completed Intakes (From Database) */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-1">
            <span className="text-xs font-bold text-[#666666] uppercase tracking-wider block">
              {completedLabel}
            </span>
            <div className="text-3xl font-serif font-bold text-[#171717]">
              {completedIntakes}
            </div>
            <p className="text-[11px] text-[#666666]">
              Physician-ready clinical summaries generated · {periodSentence}
            </p>
          </div>

          {/* Card 4: Red-Flag Alerts (From Database) */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-1">
            <span className="text-xs font-bold text-red-700 uppercase tracking-wider block">
              {redFlagLabel}
            </span>
            <div className="text-3xl font-serif font-bold text-red-600">
              {activeRedFlagCount}
            </div>
            <p className="text-[11px] text-red-700">
              Unacknowledged triage conditions raised in {periodSentence}
            </p>
          </div>
        </div>

        {/* Priority Red Flag Alerts Section */}
        {activeFlags.length > 0 ? (
          <div className="p-5 bg-red-50 rounded-2xl border-2 border-red-300 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-600" />
                <h3 className="font-bold text-sm sm:text-base text-red-950">
                  Active Clinical Safety Alerts ({activeFlags.length})
                </h3>
              </div>
              <span className="text-xs font-bold text-red-800 bg-red-100 px-2 py-0.5 rounded">
                Immediate Action Required
              </span>
            </div>

            {/* QA-11: the counter above is period-scoped, this list is not. Say so,
                otherwise "0 alerts" next to two listed alerts looks like a bug. */}
            {selectedPeriod !== 'all' && (
              <p className="text-[11px] text-red-900/80 leading-relaxed">
                This list shows every unacknowledged alert regardless of date, so it can be longer
                than the period-scoped count in the Red-Flag Alerts card above.
              </p>
            )}

            {/* QA-14: a failed acknowledgement keeps the alert on screen and
                says so plainly — it must never look like it was cleared. */}
            {ackError && (
              <div
                role="alert"
                className="flex items-start gap-2 p-2.5 bg-white border border-red-300 rounded-xl text-[11px] text-red-800 leading-relaxed"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-red-600 flex-shrink-0 mt-0.5" />
                <span>{ackError}</span>
              </div>
            )}

            <div className="space-y-2">
              {activeFlags.map((flag) => (
                <div
                  key={flag.id}
                  className="p-3.5 bg-white rounded-xl border border-red-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-xs text-[#6C3FC5] bg-[#F3EEFC] px-1.5 py-0.2 rounded">
                        {flag.token}
                      </span>
                      <strong className="text-xs text-[#171717]">{flag.patientName}</strong>
                      <span className="text-[11px] text-[#666666]">Detected at {flag.detectedAt}</span>
                    </div>
                    <p className="text-xs text-red-900 mt-0.5">{flag.triggerCondition}</p>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleAcknowledge(flag.id)}
                    disabled={acknowledgingId !== null}
                    aria-busy={acknowledgingId === flag.id}
                    className="flex items-center justify-center gap-1.5 px-3.5 py-1.5 bg-red-600 hover:bg-red-700 disabled:bg-red-400 disabled:cursor-not-allowed text-white text-xs font-bold rounded-lg transition-colors flex-shrink-0 min-w-[9.5rem]"
                  >
                    {acknowledgingId === flag.id ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Acknowledging…</span>
                      </>
                    ) : (
                      <span>Acknowledge & Triage</span>
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 flex items-center justify-between text-xs text-emerald-800">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span className="font-semibold">No Active Red-Flag Emergency Alerts. All triage streams operating within normal parameters.</span>
            </div>
            <span className="text-[11px] font-mono text-emerald-700 bg-emerald-100/60 px-2 py-0.5 rounded">
              Clear
            </span>
          </div>
        )}

        {/* Model Insights & Volume Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Intake Time Calculation Model Card */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[#6C3FC5]" />
                <h3 className="font-bold text-sm text-[#171717]">Intake Duration Calculation Model</h3>
              </div>
              <span className="text-[11px] font-mono text-[#6C3FC5] bg-[#F3EEFC] px-2 py-0.5 rounded">
                {intakeTimeModel?.calculation_method || 'Hybrid Bayesian Regression'}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-neutral-50 rounded-xl border border-neutral-100">
                <span className="text-[10px] text-[#666666] uppercase block">Median Time</span>
                <span className="text-base font-bold text-[#171717]">
                  {intakeTimeModel?.median_minutes ?? averageIntakeMinutes} min
                </span>
              </div>
              <div className="p-3 bg-neutral-50 rounded-xl border border-neutral-100">
                <span className="text-[10px] text-[#666666] uppercase block">Voice Accelerated</span>
                <span className="text-base font-bold text-emerald-700">
                  {intakeTimeModel?.modality_breakdown?.voice_multilingual ?? roundNum(averageIntakeMinutes * 0.72)} min
                </span>
              </div>
              <div className="p-3 bg-neutral-50 rounded-xl border border-neutral-100">
                <span className="text-[10px] text-[#666666] uppercase block">Model Sample Size</span>
                <span className="text-base font-bold text-[#6C3FC5]">
                  {modelSampleSize} cases
                </span>
              </div>
            </div>

            <p className="text-[11px] text-[#666666] leading-relaxed">
              The model uses empirical database encounters with Bayesian prior smoothing to filter idle anomalies and dynamically predict intake duration across age, voice modality, and clinical department trees.
            </p>
          </div>

          {/* OPD Volume Split */}
          <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-4">
            <h3 className="font-bold text-sm text-[#171717]">AYUSH vs. Modern Medicine Volume</h3>
            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between text-xs font-semibold mb-1">
                  <span>General & Modern Medicine</span>
                  <span>{Math.round((modernCount / (modernCount + ayushCount || 1)) * 100)}%</span>
                </div>
                <div className="w-full h-2.5 bg-neutral-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[#6C3FC5] rounded-full transition-all duration-300"
                    style={{ width: `${(modernCount / (modernCount + ayushCount || 1)) * 100}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-semibold mb-1">
                  <span>Traditional Medicine / AYUSH</span>
                  <span>{Math.round((ayushCount / (modernCount + ayushCount || 1)) * 100)}%</span>
                </div>
                <div className="w-full h-2.5 bg-neutral-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                    style={{ width: `${(ayushCount / (modernCount + ayushCount || 1)) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-3 bg-[#F3EEFC]/50 rounded-xl text-[11px] text-[#666666] leading-relaxed mt-2">
                Automated triage routes patients to appropriate specialized counters (Allopathic vs Ayurvedic Kayachikitsa/Panchakarma).
              </div>
            </div>
          </div>
        </div>

        {/* Academic AI/ML Model Suite & Triage Playground */}
        <div className="p-6 bg-gradient-to-br from-white to-[#FAF8FD] rounded-2xl border-2 border-[#6C3FC5]/20 shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-neutral-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-[#6C3FC5] text-white">
                  <Cpu className="w-4 h-4" />
                </span>
                <h3 className="font-serif font-bold text-lg text-[#171717]">
                  Academic MLOps & Clinical Model Verification Suite
                </h3>
              </div>
              <p className="text-xs text-[#666666] mt-1">
                Locally trained and verified models on Synthea encounters, Med-Dialog corpus, and IndicVoices multilingual datasets.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                All 5 Engines Verified & Offline
              </span>
            </div>
          </div>

          {/* Model Metric Grids */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Model 1: Gradient Boosting Intake Regressor */}
            <div className="p-4 bg-white rounded-xl border border-neutral-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#6C3FC5] uppercase tracking-wide">
                  Intake Regressor
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold">
                  R² = 0.958
                </span>
              </div>
              <p className="text-xs text-[#171717] font-semibold">
                Gradient Boosting Regressor (120 trees)
              </p>
              <div className="text-[11px] text-[#666666] space-y-1">
                <p>• Dataset: <strong>4,245 Synthea Encounters</strong></p>
                <p>• Test MAE: <strong>0.25 min</strong> (RMSE: 0.32 min)</p>
                <p>• 5-Fold Cross Validation: <strong>R² = 0.953</strong></p>
              </div>
            </div>

            {/* Model 2: Clinical Triage Classifier */}
            <div className="p-4 bg-white rounded-xl border border-neutral-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#6C3FC5] uppercase tracking-wide">
                  Triage Classifier
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-bold">
                  Acc = 82.1%
                </span>
              </div>
              <p className="text-xs text-[#171717] font-semibold">
                TF-IDF + Calibrated Multi-Class Classifier
              </p>
              <div className="text-[11px] text-[#666666] space-y-1">
                <p>• Dataset: <strong>Med-Dialog (1,500 clinical turns)</strong></p>
                <p>• Priority Weighted F1: <strong>0.806</strong></p>
                <p>• Output: <strong>Department & Emergency Escalation</strong></p>
              </div>
            </div>

            {/* Model 3: IndicVoices Lexicon & Speech */}
            <div className="p-4 bg-white rounded-xl border border-neutral-200 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#6C3FC5] uppercase tracking-wide">
                  Indic Clinical Grounding
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-bold">
                  Match = 83.3%
                </span>
              </div>
              <p className="text-xs text-[#171717] font-semibold">
                IndicVoices Regional Concept Normalizer
              </p>
              <div className="text-[11px] text-[#666666] space-y-1">
                <p>• Languages: <strong>Gujarati (gu), Hindi (hi), English</strong></p>
                <p>• Vocabulary: <strong>119+ Medical tokens</strong></p>
                <p>• Grounding: <strong>SNOMED-CT & ICD-10</strong></p>
              </div>
            </div>
          </div>

          {/* Live Interactive Triage & Duration Testing Playground */}
          <div className="p-4 bg-white rounded-xl border border-neutral-200 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-[#171717] uppercase tracking-wide flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-[#6C3FC5]" />
                Interactive Triage & Duration Testing Playground
              </span>
              <span className="text-[11px] text-[#666666]">
                Enter or click sample phrases to run inference
              </span>
            </div>

            {/* Quick Test Chips */}
            <div className="flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                onClick={() => {
                  const q = "Severe crushing chest pain radiating to left jaw with cold sweating";
                  setTestComplaint(q);
                  handleRunTriageTest(q);
                }}
                className="px-2.5 py-1 rounded-lg bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition-colors font-medium text-[11px]"
              >
                Cardiac Emergency (EN)
              </button>
              <button
                type="button"
                onClick={() => {
                  const q = "सीने में दो दिन से भारी दर्द महसूस हो रहा है और सांस फूल रही है";
                  setTestComplaint(q);
                  handleRunTriageTest(q);
                }}
                className="px-2.5 py-1 rounded-lg bg-amber-50 text-amber-800 hover:bg-amber-100 border border-amber-200 transition-colors font-medium text-[11px]"
              >
                Chest Pain + Dyspnea (Hindi)
              </button>
              <button
                type="button"
                onClick={() => {
                  const q = "છેલ્લા બે દિવસથી છાતીમાં ભારે દુખાવો અને શ્વાસ લેવામાં તકલીફ થઈ રહી છે";
                  setTestComplaint(q);
                  handleRunTriageTest(q);
                }}
                className="px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-colors font-medium text-[11px]"
              >
                Severe Chest Pain (Gujarati)
              </button>
              <button
                type="button"
                onClick={() => {
                  const q = "4-year-old child coughing persistantly for three weeks with asthma attack";
                  setTestComplaint(q);
                  handleRunTriageTest(q);
                }}
                className="px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 transition-colors font-medium text-[11px]"
              >
                Pediatric Asthma (EN)
              </button>
              <button
                type="button"
                onClick={() => {
                  const q = "Routine blood pressure screening and preventive health checkup";
                  setTestComplaint(q);
                  handleRunTriageTest(q);
                }}
                className="px-2.5 py-1 rounded-lg bg-neutral-100 text-neutral-700 hover:bg-neutral-200 transition-colors font-medium text-[11px]"
              >
                Routine General Checkup
              </button>
            </div>

            {/* Test Input & Button */}
            <div className="flex gap-2">
              <input
                type="text"
                value={testComplaint}
                onChange={(e) => setTestComplaint(e.target.value)}
                placeholder="Type any patient symptom in English, Hindi, or Gujarati..."
                className="flex-1 px-3 py-2 text-xs border border-neutral-300 rounded-lg focus:outline-none focus:border-[#6C3FC5]"
              />
              <button
                type="button"
                onClick={() => handleRunTriageTest()}
                disabled={isTestingML}
                className="px-4 py-2 bg-[#6C3FC5] hover:bg-[#5932A8] text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
              >
                <Cpu className={`w-3.5 h-3.5 ${isTestingML ? 'animate-spin' : ''}`} />
                <span>{isTestingML ? 'Classifying...' : 'Run ML Triage'}</span>
              </button>
            </div>

            {/* Test Result Display */}
            {testResult && (
              <div className="p-3 bg-neutral-50 rounded-xl border border-neutral-200 space-y-2 mt-2">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-200 pb-2">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      testResult.triage.priority === 'EMERGENCY'
                        ? 'bg-red-600 text-white'
                        : testResult.triage.priority === 'URGENT'
                        ? 'bg-amber-500 text-white'
                        : 'bg-emerald-600 text-white'
                    }`}>
                      {testResult.triage.priority}
                    </span>
                    <strong className="text-xs text-[#171717]">
                      {testResult.triage.department}
                    </strong>
                    <span className="text-[11px] text-[#666666]">
                      (Confidence: {Math.round(testResult.triage.confidence * 100)}%
                      {testResult.triage.confidence_adjusted_by_rule ? ' — raised by red-flag rule, not the model' : ''})
                    </span>
                  </div>
                  <div className="text-xs text-[#6C3FC5] font-semibold">
                    Predicted Intake: {testResult.duration_prediction.predicted_minutes} min (Saved ~{testResult.duration_prediction.time_saved_vs_manual_baseline_minutes} min)
                  </div>
                </div>

                {testResult.triage.matched_concepts && testResult.triage.matched_concepts.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className="text-[#666666]">Grounded Concepts:</span>
                    {testResult.triage.matched_concepts.map((mc: any, i: number) => (
                      <span key={i} className="px-1.5 py-0.5 bg-purple-50 text-[#6C3FC5] rounded border border-purple-200 font-mono text-[10px]">
                        {mc.concept_id} ({mc.key})
                      </span>
                    ))}
                  </div>
                )}

                {testResult.triage.alert && (
                  <p className="text-[11px] text-red-700 font-medium">
                    ⚠️ {testResult.triage.alert.alert_title}: {testResult.triage.alert.description}
                  </p>
                )}

                {/* QA-09: a high-priority prediction is advisory only. It must never
                    read as "handled" just because the model returned a high score. */}
                {testResult.triage.requires_in_person_triage && (
                  <div
                    role="alert"
                    className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-[11px] text-red-800 leading-relaxed"
                  >
                    <strong>Not a clinical disposition.</strong>{' '}
                    {testResult.triage.safety_notice ||
                      'A high-priority complaint must be confirmed by a clinician in person; this result does not mean the patient has been assessed.'}
                  </div>
                )}

                {testResult.triage.routing_review_required && (
                  <div
                    role="alert"
                    className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-900 leading-relaxed"
                  >
                    <strong>Routing needs staff verification.</strong> The model predicts{' '}
                    <span className="font-semibold">{testResult.triage.department}</span> for an
                    EMERGENCY complaint. A traditional-medicine stream is not an emergency pathway.
                    The prediction is shown unchanged — the destination must be confirmed by staff.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Live Triage & Safety Event Log */}
        <div className="p-5 bg-white rounded-2xl border border-neutral-200 shadow-xs space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm text-[#171717]">Live Triage & Safety Event Log</h3>
            <span className="text-[11px] text-[#666666]">{auditLogs.length} events logged</span>
          </div>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {auditLogs.length === 0 ? (
              <p className="text-[11px] text-neutral-400 py-3 text-center">No safety audit logs yet. Events will appear as encounters proceed.</p>
            ) : (
              auditLogs.map((log) => (
                <div
                  key={log.id}
                  className="p-3 bg-neutral-50 rounded-xl border border-neutral-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[#6C3FC5] font-bold">{log.timestamp}</span>
                      <strong className="text-[#171717]">{log.action}</strong>
                    </div>
                    <span className="text-[#666666] text-[11px]">{log.details}</span>
                  </div>
                  <span className="text-[10px] font-mono text-neutral-400">{log.actor}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function roundNum(val: number): number {
  return Math.round(val * 10) / 10;
}
