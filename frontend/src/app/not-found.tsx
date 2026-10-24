import React from 'react';
import Link from 'next/link';
import { Logo } from '@/components/common/Logo';
import { Home, Stethoscope, MessageSquare, ShieldAlert } from 'lucide-react';

// QA BUG-007: branded, navigable 404 instead of the builtin unstyled Next.js page.
export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950 px-6">
      <div className="max-w-lg w-full text-center rounded-3xl border border-white/10 bg-white/[0.04] backdrop-blur-xl p-10 shadow-[0_10px_50px_rgba(0,0,0,0.6)]">
        <div className="flex justify-center mb-6">
          <Logo size={56} className="h-14 w-14" />
        </div>

        <p className="text-6xl font-semibold tracking-tight text-cyan-300 mb-2">404</p>
        <h1 className="text-xl font-medium text-white mb-2">Page not found</h1>
        <p className="text-sm text-white/60 leading-relaxed mb-8">
          The page you are looking for doesn&apos;t exist or may have moved.
          No clinical data was affected. Return to a safe starting point below.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center mb-8">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-950 text-sm font-semibold hover:opacity-90 transition-opacity"
          >
            <Home className="w-4 h-4" />
            Kiosk Home
          </Link>
          <Link
            href="/chat"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full border border-white/15 text-white/80 text-sm font-medium hover:bg-white/5 transition-colors"
          >
            <MessageSquare className="w-4 h-4" />
            AI Assistant
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-full border border-white/15 text-white/80 text-sm font-medium hover:bg-white/5 transition-colors"
          >
            <Stethoscope className="w-4 h-4" />
            Staff Login
          </Link>
        </div>

        <div className="mt-8 pt-6 border-t border-white/10 flex items-center justify-center gap-2 text-[11px] text-white/40">
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>MediKiosk clinical kiosk &mdash; if you reached this from a patient workflow, alert the OPD triage desk.</span>
        </div>
      </div>
    </div>
  );
}
