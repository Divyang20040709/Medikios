'use client';

import React from 'react';
import { FileText, Activity, Clock } from 'lucide-react';

export const FloatingTimelineCard: React.FC = () => {
  return (
    <div
      className="w-[240px] lg:w-[270px] rounded-2xl liquid-glass p-4 text-white shadow-xl backdrop-blur-xl transition-all duration-500"
      style={{
        transform: 'perspective(1000px) rotateY(6deg) rotateX(-2deg) translateY(10px)',
        boxShadow: '0 20px 40px -10px rgba(0, 0, 0, 0.6), 0 0 20px rgba(0, 201, 167, 0.1)',
      }}
    >
      <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-3">
        <span className="text-[10px] font-semibold tracking-wider text-teal-400 uppercase">
          Previous Records
        </span>
        <span className="text-[10px] text-white/50">Chronological</span>
      </div>

      <div className="relative pl-3 space-y-3 before:absolute before:left-1 before:top-2 before:bottom-2 before:w-[1px] before:bg-white/20">
        {/* Item 1 */}
        <div className="relative flex items-start gap-2">
          <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-teal-400" />
          <div className="text-left">
            <span className="block text-[10px] text-white/50 font-mono">Aug 2026</span>
            <span className="block text-xs font-medium text-white/90">Lab Report (HbA1c & Lipids)</span>
          </div>
        </div>

        {/* Item 2 */}
        <div className="relative flex items-start gap-2">
          <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-cyan-400" />
          <div className="text-left">
            <span className="block text-[10px] text-white/50 font-mono">Jun 2026</span>
            <span className="block text-xs font-medium text-white/90">Prescription (Metformin 500mg)</span>
          </div>
        </div>

        {/* Item 3 */}
        <div className="relative flex items-start gap-2">
          <span className="absolute -left-[11px] top-1.5 h-1.5 w-1.5 rounded-full bg-indigo-400" />
          <div className="text-left">
            <span className="block text-[10px] text-white/50 font-mono">Jan 2026</span>
            <span className="block text-xs font-medium text-white/90">Discharge Summary</span>
          </div>
        </div>
      </div>

      <div className="mt-3 pt-2 border-t border-white/10 flex items-center justify-between text-[10px] text-white/60">
        <span className="text-cyan-300/80 font-medium">AI organized 12 records</span>
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
      </div>
    </div>
  );
};
