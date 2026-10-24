'use client';

import React from 'react';
import { CheckCircle2 } from 'lucide-react';

export const TelemetryMicroCard: React.FC = () => {
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full liquid-glass border border-cyan-400/20 text-white/90 text-xs shadow-md backdrop-blur-xl animate-float">
      <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
      <span className="text-[11px] font-medium text-cyan-200">History Captured</span>
      <span className="text-white/40">•</span>
      <span className="text-[10px] text-teal-300 flex items-center gap-1">
        <CheckCircle2 className="h-3 w-3" /> Summary Ready
      </span>
    </div>
  );
};
