'use client';

import React, { useState } from 'react';
import { AlertTriangle, PhoneCall, Volume2, VolumeX } from 'lucide-react';
import { AccessibilitySettings } from '@/lib/types';
import { SpeechAssistant } from '@/lib/clinicalStore';
import { NotificationModal } from '@/components/common/NotificationModal';

interface AccessibilityBannerProps {
  settings: AccessibilitySettings;
  onSettingsChange: (settings: AccessibilitySettings) => void;
  onEmergencyCall?: () => void;
}

export function AccessibilityBanner({
  settings,
  onSettingsChange,
  onEmergencyCall,
}: AccessibilityBannerProps) {
  const [emergencyOpen, setEmergencyOpen] = useState(false);

  const toggleContrast = () => {
    onSettingsChange({
      ...settings,
      highContrast: !settings.highContrast,
    });
  };

  const setFontSize = (size: 'normal' | 'large' | 'extra-large') => {
    onSettingsChange({
      ...settings,
      textSize: size,
    });
  };

  const toggleSpeech = () => {
    const nextState = !settings.audioAssistance;
    if (!nextState) {
      SpeechAssistant.stopSpeaking();
    }
    onSettingsChange({
      ...settings,
      audioAssistance: nextState,
    });
  };

  const handleEmergency = () => {
    // If the host screen wires a real dispatch handler, use it and stay silent.
    // Otherwise show the honest in-app dialog (no live paging in this build).
    if (onEmergencyCall) {
      onEmergencyCall();
    } else {
      setEmergencyOpen(true);
    }
  };

  return (
    <div
      className={`w-full border-b py-2 px-3 sm:px-6 transition-colors ${
        settings.highContrast
          ? 'bg-black text-white border-neutral-800'
          : 'bg-[#F3EEFC]/50 text-[#171717] border-neutral-200'
      }`}
    >
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-2.5 text-xs">
        {/* Emergency Alert Protocol */}
        <div className="flex items-center justify-between sm:justify-start gap-2 w-full sm:w-auto">
          <span className="flex items-center gap-1 font-bold text-[#4B238C] uppercase tracking-wide text-[11px] sm:text-xs">
            <AlertTriangle className="w-3.5 h-3.5 text-[#6C3FC5]" />
            Emergency Protocol:
          </span>
          <span className="hidden md:inline text-[#666666]">
            For sudden severe distress or altered consciousness, notify triage staff immediately.
          </span>
          <button
            type="button"
            onClick={handleEmergency}
            className="flex items-center gap-1 text-[11px] sm:text-xs font-bold text-white bg-[#4B238C] hover:bg-[#6C3FC5] px-2.5 py-1 rounded shadow-xs transition-colors"
          >
            <PhoneCall className="w-3 h-3" />
            <span>Alert Triage Nurse</span>
          </button>
        </div>

        {/* Accessibility Tools */}
        <div className="flex items-center justify-end gap-2 sm:gap-3 flex-wrap w-full sm:w-auto">
          {/* Font Resizing */}
          <div className="flex items-center gap-1 bg-white border border-neutral-200 rounded px-1.5 py-0.5 text-[#171717]">
            <span className="text-[11px] font-semibold mr-1 text-[#666666]">Font:</span>
            <button
              type="button"
              onClick={() => setFontSize('normal')}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                settings.textSize === 'normal'
                  ? 'bg-[#6C3FC5] text-white font-bold'
                  : 'hover:bg-[#F3EEFC] text-[#666666]'
              }`}
              title="Standard Font Size"
            >
              A
            </button>
            <button
              type="button"
              onClick={() => setFontSize('large')}
              className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                settings.textSize === 'large'
                  ? 'bg-[#6C3FC5] text-white font-bold'
                  : 'hover:bg-[#F3EEFC] text-[#666666]'
              }`}
              title="Large Font Size"
            >
              A+
            </button>
            <button
              type="button"
              onClick={() => setFontSize('extra-large')}
              className={`px-1.5 py-0.5 rounded text-xs font-bold transition-colors ${
                settings.textSize === 'extra-large'
                  ? 'bg-[#6C3FC5] text-white'
                  : 'hover:bg-[#F3EEFC] text-[#666666]'
              }`}
              title="Extra Large Font Size"
            >
              A++
            </button>
          </div>

          {/* High Contrast */}
          <button
            type="button"
            onClick={toggleContrast}
            className={`px-2 py-1 rounded text-xs font-medium border transition-colors ${
              settings.highContrast
                ? 'bg-white text-black border-white'
                : 'bg-white text-[#666666] border-neutral-200 hover:bg-[#F3EEFC] hover:text-[#6C3FC5]'
            }`}
          >
            {settings.highContrast ? 'Standard' : 'Contrast'}
          </button>

          {/* Audio Assistance */}
          <button
            type="button"
            onClick={toggleSpeech}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
              settings.audioAssistance
                ? 'bg-[#6C3FC5] text-white border-[#6C3FC5]'
                : 'bg-white text-[#666666] border-neutral-200 hover:bg-[#F3EEFC] hover:text-[#6C3FC5]'
            }`}
          >
            {settings.audioAssistance ? (
              <VolumeX className="w-3.5 h-3.5" />
            ) : (
              <Volume2 className="w-3.5 h-3.5 text-[#6C3FC5]" />
            )}
            <span>{settings.audioAssistance ? 'Voice: On' : 'Audio'}</span>
          </button>
        </div>
      </div>

      {/* Emergency assistance — honest in-app dialog (replaces native alert()).
          This build has no live nursing-station paging, so we must not claim
          staff were dispatched; we direct the user to real physical channels. */}
      <NotificationModal
        open={emergencyOpen}
        tone="emergency"
        title="Assistance requested"
        description="This demo kiosk is not connected to a live nursing station, so no staff have been paged. To get help right now, please raise your hand to alert an OPD volunteer, or call the triage helpline listed under Help."
        acknowledgeLabel="Understood"
        onCancel={() => setEmergencyOpen(false)}
      />
    </div>
  );
}
