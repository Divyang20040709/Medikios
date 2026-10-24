'use client';

import React from 'react';
import { AlertCircle } from 'lucide-react';

export const TriageAlertBadge: React.FC = () => {
  return (
    <div
      className="inline-flex items-center gap-2.5 px-3.5 py-2 rounded-2xl liquid-glass border border-amber-500/30 bg-amber-500/[0.04] text-white/90 shadow-lg backdrop-blur-xl animate-float-delayed"
      style={{
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 0 15px rgba(245, 158, 11, 0.15)',
      }}
    >
      <div className="h-5 w-5 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400">
        <AlertCircle className="h-3.5 w-3.5" />
      </div>
      <div className="text-left">
        <span className="block text-[11px] font-semibold text-amber-300 uppercase tracking-wide">
          Triage Alert
        </span>
        <span className="block text-[10px] text-white/70">
          High-priority symptoms detected
        </span>
      </div>
    </div>
  );
};
