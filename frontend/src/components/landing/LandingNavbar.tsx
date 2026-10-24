'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { CircleUserRound, Menu, X, Bot, Sparkles } from 'lucide-react';
import { Logo } from '../common/Logo';

interface LandingNavbarProps {
  activeSection?: string;
  onNavigate?: (section: string) => void;
}

export const LandingNavbar: React.FC<LandingNavbarProps> = ({
  activeSection = 'home',
  onNavigate,
}) => {
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLinkClick = (section: string) => {
    setMenuOpen(false);
    if (onNavigate) {
      onNavigate(section);
    }
  };

  return (
    <>
      <nav className="relative z-20 w-full px-5 pt-6 sm:px-8 sm:pt-8 md:px-16 lg:px-20">
        <div className="flex items-center justify-between">
          {/* LEFT: LOGO */}
          <Link href="/" className="group flex items-center gap-3">
            <Logo size={36} className="h-8 w-8 sm:h-9 sm:w-9" />
            <span className="text-xl font-medium tracking-tight text-white">
              MediKiosk
            </span>
          </Link>

          {/* CENTER NAVIGATION (DESKTOP) */}
          <div className="hidden md:flex items-center">
            <div className="liquid-glass rounded-full px-8 py-3 flex items-center gap-8">
              <button
                onClick={() => handleLinkClick('home')}
                className={`text-sm font-medium transition-colors duration-200 ${
                  activeSection === 'home'
                    ? 'text-white'
                    : 'text-white/65 hover:text-white'
                }`}
              >
                Home
              </button>
              <button
                onClick={() => handleLinkClick('how-it-works')}
                className={`text-sm font-medium transition-colors duration-200 ${
                  activeSection === 'how-it-works'
                    ? 'text-white'
                    : 'text-white/65 hover:text-white'
                }`}
              >
                How It Works
              </button>
              <button
                onClick={() => handleLinkClick('for-hospitals')}
                className={`text-sm font-medium transition-colors duration-200 ${
                  activeSection === 'for-hospitals'
                    ? 'text-white'
                    : 'text-white/65 hover:text-white'
                }`}
              >
                For Hospitals
              </button>
              <Link
                href="/chat"
                className="text-sm font-medium text-cyan-300 hover:text-cyan-200 flex items-center gap-1.5 transition-colors"
              >
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                AI Chatbot
              </Link>
            </div>
          </div>

          {/* RIGHT NAVIGATION */}
          <div className="flex items-center gap-3">
            {/* Direct Chatbot Button */}
            <Link
              href="/chat"
              className="hidden sm:flex items-center gap-2 px-3.5 py-2 rounded-full liquid-glass liquid-glass-hover text-xs font-medium text-cyan-300 border border-cyan-400/40 hover:bg-cyan-500/20 transition-all shadow-[0_0_15px_rgba(0,242,254,0.2)]"
            >
              <Bot className="h-4 w-4 text-cyan-400" />
              <span>Ask AI Chatbot</span>
            </Link>

            {/* Desktop User/Portal Button */}
            <Link
              href="/login"
              aria-label="Secure digital health account & staff portal login"
              className="hidden md:flex h-10 w-10 items-center justify-center rounded-full liquid-glass liquid-glass-hover text-white/80 hover:text-white transition-colors"
            >
              <CircleUserRound className="h-5 w-5" strokeWidth={1.5} />
            </Link>

            {/* Mobile Hamburger Toggle */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label={menuOpen ? "Close mobile menu" : "Open mobile menu"}
              aria-expanded={menuOpen}
              className="flex md:hidden h-10 w-10 items-center justify-center rounded-full liquid-glass text-white transition-all duration-300"
            >
              {menuOpen ? (
                <X className="h-5 w-5 transition-transform duration-300 rotate-90" />
              ) : (
                <Menu className="h-5 w-5 transition-transform duration-300" />
              )}
            </button>
          </div>
        </div>
      </nav>

      {/* MOBILE MENU OVERLAY */}
      {menuOpen && (
        <div className="fixed inset-0 z-10 flex flex-col items-center justify-center bg-black/85 backdrop-blur-xl md:hidden transition-opacity duration-500 ease-out">
          <div className="flex flex-col items-center gap-8 text-center animate-in fade-in slide-in-from-top-4 duration-300">
            <button
              onClick={() => handleLinkClick('home')}
              className="text-2xl font-medium text-white hover:text-cyan-400 transition-colors"
            >
              Home
            </button>
            <button
              onClick={() => handleLinkClick('how-it-works')}
              className="text-2xl font-medium text-white hover:text-cyan-400 transition-colors"
            >
              How It Works
            </button>
            <button
              onClick={() => handleLinkClick('for-hospitals')}
              className="text-2xl font-medium text-white hover:text-cyan-400 transition-colors"
            >
              For Hospitals
            </button>
            <Link
              href="/chat"
              onClick={() => setMenuOpen(false)}
              className="text-2xl font-medium text-cyan-300 hover:text-cyan-200 flex items-center gap-2 transition-colors"
            >
              <Sparkles className="h-5 w-5 text-cyan-400" />
              AI Chatbot
            </Link>

            <div className="mt-8 pt-8 border-t border-white/10 flex flex-col items-center gap-3">
              <Link
                href="/login"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-3 liquid-glass px-6 py-3 rounded-full text-white/90 hover:text-white"
              >
                <div className="h-8 w-8 rounded-full liquid-glass flex items-center justify-center text-cyan-400">
                  <CircleUserRound className="h-4 w-4" />
                </div>
                <div className="text-left">
                  <span className="block text-sm font-medium">Patient & Doctor Login</span>
                  <span className="block text-xs font-light text-white/60">Digital Health Account</span>
                </div>
              </Link>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
