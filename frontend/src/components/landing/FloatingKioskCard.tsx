'use client';

import React, { useState } from 'react';
import { Mic, Sparkles } from 'lucide-react';

interface FloatingKioskCardProps {
  onSelectOption?: (option: string) => void;
}

export const FloatingKioskCard: React.FC<FloatingKioskCardProps> = ({ onSelectOption }) => {
  const [selected, setSelected] = useState<string>('Chest pain');
  const [isListening, setIsListening] = useState<boolean>(false);

  const options = ['Chest pain', 'Fever', 'Abdominal pain'];

  const handleSelect = (opt: string) => {
    setSelected(opt);
    if (onSelectOption) onSelectOption(opt);
  };

  const toggleMic = () => {
    setIsListening(!isListening);
  };

  return (
    <div
      className="relative z-10 w-[300px] lg:w-[340px] rounded-3xl liquid-glass p-6 text-white shadow-2xl backdrop-blur-2xl transition-transform duration-500 ease-out hover:rotate-0"
      style={{
        transform: 'perspective(1000px) rotateY(-4deg) rotateX(2deg) rotateZ(-3deg)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 35px rgba(0, 242, 254, 0.15)',
      }}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <span className="text-[10px] font-semibold tracking-widest text-cyan-400 uppercase">
          Patient Intake
        </span>
        <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
      </div>

      {/* Clinical Question */}
      <div className="mt-4">
        <h4 className="text-base font-normal text-white/95">
          What brings you here today?
        </h4>
        <p className="mt-1 text-xs text-white/60 font-light">
          Tap an option or speak in your language
        </p>
      </div>

      {/* Selectable Buttons */}
      <div className="mt-4 space-y-2">
        {options.map((opt) => {
          const isCurrent = selected === opt;
          return (
            <button
              key={opt}
              onClick={() => handleSelect(opt)}
              className={`w-full text-left px-4 py-2.5 rounded-2xl text-xs sm:text-sm font-medium transition-all duration-200 flex items-center justify-between ${
                isCurrent
                  ? 'bg-cyan-500/20 border border-cyan-400/50 text-white shadow-[0_0_15px_rgba(0,242,254,0.2)]'
                  : 'bg-white/[0.03] border border-white/10 text-white/80 hover:bg-white/[0.08] hover:text-white'
              }`}
            >
              <span>{opt}</span>
              {isCurrent && (
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f2fe]" />
              )}
            </button>
          );
        })}
      </div>

      {/* Voice Interaction Button */}
      <button
        onClick={toggleMic}
        className={`mt-4 w-full py-2.5 px-4 rounded-2xl text-xs sm:text-sm font-medium flex items-center justify-center gap-2 transition-all duration-300 ${
          isListening
            ? 'bg-rose-500/30 border border-rose-400 text-rose-200 animate-pulse'
            : 'liquid-glass hover:bg-white/10 text-white/90'
        }`}
      >
        <Mic className={`h-4 w-4 ${isListening ? 'text-rose-400' : 'text-cyan-400'}`} />
        <span>{isListening ? 'Listening in Hindi / English...' : 'Speak your answer'}</span>
      </button>

      {/* Bottom Telemetry Status */}
      <div className="mt-5 pt-3 border-t border-white/10 flex items-center justify-between text-[11px] text-white/60">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3 w-3 text-teal-400" />
          <span>AI History Assistant</span>
        </div>
        <span className="text-teal-400/90 font-mono text-[10px]">Adaptive v1.4</span>
      </div>
    </div>
  );
};
