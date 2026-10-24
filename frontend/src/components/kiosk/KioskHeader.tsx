'use client';

import React, { useState } from 'react';
import {
  Users,
  Stethoscope,
  Building2,
  Volume2,
  VolumeX,
  Globe,
  HelpCircle,
  Menu,
  X,
  Activity,
  Database,
  LogOut,
  LogIn
} from 'lucide-react';
import { UserRole, LanguageCode } from '@/lib/types';
import { SpeechAssistant } from '@/lib/clinicalStore';

interface KioskHeaderProps {
  activeRole: UserRole;
  onSelectRole: (role: UserRole) => void;
  kioskId?: string;
  currentLanguage: LanguageCode;
  onLanguageChange: (lang: LanguageCode) => void;
  isKioskMode?: boolean;
  onHomeClick: () => void;
  onOpenHelp: () => void;
  onOpenSchema?: () => void;
  /** Common sign-in entry point. Rendered only when provided (e.g. the public
   *  homepage), so signed-in staff screens show Sign Out instead of Login. */
  onLoginClick?: () => void;
  isSpeaking?: boolean;
  onToggleAudioHelp?: () => void;
  /** QA BUG-011 / SEC-2: staff sign-out. Rendered only when provided, so the
   *  unauthenticated patient kiosk (no session) never shows a sign-out. */
  onSignOut?: () => void;
}

export function KioskHeader({
  activeRole,
  onSelectRole,
  kioskId = 'KIOSK-01',
  currentLanguage,
  onLanguageChange,
  isKioskMode = false,
  onHomeClick,
  onOpenHelp,
  onOpenSchema,
  onLoginClick,
  isSpeaking = false,
  onToggleAudioHelp,
  onSignOut,
}: KioskHeaderProps) {
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const languages: Array<{ code: LanguageCode; label: string; native: string }> = [
    { code: 'en', label: 'English', native: 'English' },
    { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
    { code: 'gu', label: 'Gujarati', native: 'ગુજરાતી' },
  ];

  const currentLangObj = languages.find((l) => l.code === currentLanguage) || languages[0];

  const handleRoleSelect = (role: UserRole) => {
    onSelectRole(role);
    setMobileMenuOpen(false);
  };

  return (
    <header className="w-full bg-white border-b border-neutral-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 h-16 flex items-center justify-between gap-2 sm:gap-4">
        {/* Brand Logo */}
        <div
          onClick={onHomeClick}
          className="cursor-pointer hover:opacity-90 transition-opacity py-1 flex items-center gap-2.5"
          title="Return to Welcome"
        >
          <div className="w-9 h-9 rounded-lg bg-[#6C3FC5] flex items-center justify-center text-white shadow-sm flex-shrink-0">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-sans font-extrabold text-xl sm:text-2xl text-[#171717] tracking-tight">
                Medi<span className="text-[#6C3FC5]">Kiosk</span>
              </span>
              <span className="hidden xl:inline text-[11px] font-mono text-[#666666] bg-[#F3EEFC] px-1.5 py-0.5 rounded border border-[#6C3FC5]/20">
                {kioskId}
              </span>
            </div>
            {!isKioskMode && (
              <span className="hidden sm:inline text-[11px] text-[#666666] font-medium tracking-normal -mt-0.5">
                Clinical History-Taking & Patient Intake
              </span>
            )}
          </div>
        </div>

        {/* Role Switcher (Desktop) */}
        <nav aria-label="Role Switcher" className="hidden md:flex items-center bg-[#F3EEFC] p-1 rounded-lg border border-[#6C3FC5]/15 text-xs font-semibold">
          <button
            type="button"
            onClick={() => handleRoleSelect('patient')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
              activeRole === 'patient'
                ? 'bg-[#6C3FC5] text-white shadow-xs'
                : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Patient Kiosk</span>
          </button>
          <button
            type="button"
            onClick={() => handleRoleSelect('physician')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
              activeRole === 'physician'
                ? 'bg-[#6C3FC5] text-white shadow-xs'
                : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
            }`}
          >
            <Stethoscope className="w-3.5 h-3.5" />
            <span>Physician OPD</span>
          </button>
          <button
            type="button"
            onClick={() => handleRoleSelect('admin')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
              activeRole === 'admin'
                ? 'bg-[#6C3FC5] text-white shadow-xs'
                : 'text-[#666666] hover:text-[#171717] hover:bg-white/60'
            }`}
          >
            <Building2 className="w-3.5 h-3.5" />
            <span>Admin & Triage</span>
          </button>
        </nav>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5 sm:gap-2.5">
          {/* SQL Schema Inspector Button */}
          {onOpenSchema && (
            <button
              type="button"
              onClick={onOpenSchema}
              className="hidden lg:flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md border border-neutral-200 bg-white text-[#666666] hover:bg-[#F3EEFC] hover:text-[#6C3FC5] transition-colors"
              title="Postgres & Supabase Schema DDL"
            >
              <Database className="w-3.5 h-3.5 text-[#6C3FC5]" />
              <span>SQL DDL</span>
            </button>
          )}

          {/* Voice Narrator Button */}
          {onToggleAudioHelp && (
            <button
              type="button"
              onClick={onToggleAudioHelp}
              className={`hidden sm:flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md border transition-colors ${
                isSpeaking
                  ? 'bg-[#6C3FC5] text-white border-[#6C3FC5]'
                  : 'bg-white text-[#666666] border-neutral-200 hover:bg-[#F3EEFC] hover:text-[#6C3FC5]'
              }`}
              title="Voice Narrator"
            >
              {isSpeaking ? (
                <VolumeX className="w-4 h-4" />
              ) : (
                <Volume2 className="w-4 h-4 text-[#6C3FC5]" />
              )}
              <span className="hidden lg:inline">{isSpeaking ? 'Mute Audio' : 'Audio Guide'}</span>
            </button>
          )}

          {/* Language Selector Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setLangMenuOpen(!langMenuOpen)}
              className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md border border-neutral-200 bg-white text-[#171717] hover:bg-[#F3EEFC] hover:border-[#6C3FC5]/30 transition-colors"
              aria-expanded={langMenuOpen}
            >
              <Globe className="w-4 h-4 text-[#6C3FC5]" />
              <span>{currentLangObj.native}</span>
            </button>
            {langMenuOpen && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-neutral-200 py-1.5 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
                <div className="px-3 py-1 text-[11px] font-bold text-[#666666] uppercase tracking-wider border-b border-neutral-100">
                  Select Language
                </div>
                {languages.map((lang) => (
                  <button
                    key={lang.code}
                    type="button"
                    onClick={() => {
                      onLanguageChange(lang.code);
                      setLangMenuOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-xs sm:text-sm flex items-center justify-between hover:bg-[#F3EEFC] transition-colors ${
                      currentLanguage === lang.code
                        ? 'font-bold text-[#6C3FC5] bg-[#F3EEFC]/60'
                        : 'text-[#171717]'
                    }`}
                  >
                    <span>{lang.native}</span>
                    <span className="text-xs text-[#666666] font-normal">{lang.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Hospital Help Button */}
          <button
            type="button"
            onClick={onOpenHelp}
            className="hidden sm:flex items-center gap-1 px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md border border-neutral-200 bg-white text-[#666666] hover:bg-[#F3EEFC] hover:text-[#6C3FC5] transition-colors"
            title="Hospital Help"
          >
            <HelpCircle className="w-4 h-4 text-[#6C3FC5]" />
            <span className="hidden sm:inline">Help</span>
          </button>

          {/* Common Login (public homepage) */}
          {onLoginClick && (
            <button
              type="button"
              onClick={onLoginClick}
              className="flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 text-xs sm:text-sm font-bold rounded-md bg-[#6C3FC5] hover:bg-[#4B238C] text-white shadow-xs transition-colors"
              title="Sign in as Patient, Doctor or Admin"
            >
              <LogIn className="w-4 h-4" />
              <span>Login</span>
            </button>
          )}

          {/* Sign Out (staff only) */}
          {onSignOut && (
            <button
              type="button"
              onClick={onSignOut}
              className="hidden sm:flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md border border-neutral-200 bg-white text-[#666666] hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
              title="Sign out of this workstation"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden lg:inline">Sign Out</span>
            </button>
          )}

          {/* Mobile Menu Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-md text-[#171717] hover:bg-[#F3EEFC] hover:text-[#6C3FC5] border border-neutral-200 transition-colors"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-neutral-200 bg-white px-4 py-3 shadow-md space-y-2 animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="text-[11px] font-bold text-[#666666] uppercase tracking-wider mb-1">
            Switch View / Role
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            <button
              type="button"
              onClick={() => handleRoleSelect('patient')}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md text-sm font-semibold transition-colors ${
                activeRole === 'patient'
                  ? 'bg-[#6C3FC5] text-white'
                  : 'bg-[#F3EEFC]/60 text-[#171717] hover:bg-[#F3EEFC]'
              }`}
            >
              <span className="flex items-center gap-2">
                <Users className="w-4 h-4" />
                <span>Patient Kiosk</span>
              </span>
              {activeRole === 'patient' && <span className="text-xs">Active</span>}
            </button>
            <button
              type="button"
              onClick={() => handleRoleSelect('physician')}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md text-sm font-semibold transition-colors ${
                activeRole === 'physician'
                  ? 'bg-[#6C3FC5] text-white'
                  : 'bg-[#F3EEFC]/60 text-[#171717] hover:bg-[#F3EEFC]'
              }`}
            >
              <span className="flex items-center gap-2">
                <Stethoscope className="w-4 h-4" />
                <span>Physician OPD Workstation</span>
              </span>
              {activeRole === 'physician' && <span className="text-xs">Active</span>}
            </button>
            <button
              type="button"
              onClick={() => handleRoleSelect('admin')}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-md text-sm font-semibold transition-colors ${
                activeRole === 'admin'
                  ? 'bg-[#6C3FC5] text-white'
                  : 'bg-[#F3EEFC]/60 text-[#171717] hover:bg-[#F3EEFC]'
              }`}
            >
              <span className="flex items-center gap-2">
                <Building2 className="w-4 h-4" />
                <span>Admin & Triage Monitor</span>
              </span>
              {activeRole === 'admin' && <span className="text-xs">Active</span>}
            </button>
            {onToggleAudioHelp && (
              <button
                type="button"
                onClick={() => {
                  onToggleAudioHelp();
                  setMobileMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3.5 py-2.5 rounded-md text-sm font-semibold bg-white border border-neutral-200 text-[#171717] hover:bg-[#F3EEFC]"
              >
                {isSpeaking ? (
                  <VolumeX className="w-4 h-4 text-[#6C3FC5]" />
                ) : (
                  <Volume2 className="w-4 h-4 text-[#6C3FC5]" />
                )}
                <span>{isSpeaking ? 'Mute Voice Narrator' : 'Enable Voice Narrator'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                onOpenHelp();
                setMobileMenuOpen(false);
              }}
              className="w-full flex items-center gap-2 px-3.5 py-2.5 rounded-md text-sm font-semibold bg-white border border-neutral-200 text-[#171717] hover:bg-[#F3EEFC]"
            >
              <HelpCircle className="w-4 h-4 text-[#6C3FC5]" />
              <span>Hospital Help & OPD Guide</span>
            </button>
            {onOpenSchema && (
              <button
                type="button"
                onClick={() => {
                  onOpenSchema();
                  setMobileMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3.5 py-2.5 rounded-md text-sm font-semibold bg-white border border-neutral-200 text-[#171717] hover:bg-[#F3EEFC]"
              >
                <Database className="w-4 h-4 text-[#6C3FC5]" />
                <span>View PostgreSQL / Supabase Schema</span>
              </button>
            )}
            {onLoginClick && (
              <button
                type="button"
                onClick={() => {
                  onLoginClick();
                  setMobileMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3.5 py-2.5 rounded-md text-sm font-bold bg-[#6C3FC5] text-white hover:bg-[#4B238C] transition-colors"
              >
                <LogIn className="w-4 h-4" />
                <span>Login</span>
              </button>
            )}
            {onSignOut && (
              <button
                type="button"
                onClick={() => {
                  onSignOut();
                  setMobileMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3.5 py-2.5 rounded-md text-sm font-semibold bg-white border border-neutral-200 text-[#171717] hover:bg-red-50 hover:text-red-600"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
