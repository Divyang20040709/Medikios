'use client';

import { useCallback, useEffect, useState } from 'react';
import { LanguageCode } from './types';

/**
 * Persistent language preferences for the MediKiosk frontend.
 *
 * UI language (what the interface renders in) and AI interview language
 * (what language the patient gives clinical answers in / voice assistant locale)
 * are stored under SEPARATE keys so switching one never resets the other,
 * and both survive route navigation and page refreshes.
 */

export const UI_LANGUAGE_KEY = 'medikiosk_ui_language';
export const INTERVIEW_LANGUAGE_KEY = 'medikiosk_interview_language';

const VALID_LANGUAGES: LanguageCode[] = ['en', 'hi', 'gu'];

function isLanguageCode(value: unknown): value is LanguageCode {
  return typeof value === 'string' && (VALID_LANGUAGES as string[]).includes(value);
}

function readLang(key: string): LanguageCode {
  if (typeof window === 'undefined') return 'en';
  try {
    const stored = window.localStorage.getItem(key);
    return isLanguageCode(stored) ? stored : 'en';
  } catch {
    return 'en';
  }
}

function writeLang(key: string, lang: LanguageCode): void {
  try {
    window.localStorage.setItem(key, lang);
  } catch {
    // Private mode / storage full — language still works for this session.
  }
}

export function readUiLanguage(): LanguageCode {
  return readLang(UI_LANGUAGE_KEY);
}

export function writeUiLanguage(lang: LanguageCode): void {
  writeLang(UI_LANGUAGE_KEY, lang);
}

export function readInterviewLanguage(): LanguageCode {
  // Falls back to the UI language when no explicit interview choice exists yet.
  const stored = readLang(INTERVIEW_LANGUAGE_KEY);
  if (stored !== 'en') return stored;
  return readLang(UI_LANGUAGE_KEY);
}

export function writeInterviewLanguage(lang: LanguageCode): void {
  writeLang(INTERVIEW_LANGUAGE_KEY, lang);
}

/**
 * Hook: UI language state backed by localStorage.
 * Loads the persisted value on mount (SSR-safe) and syncs across tabs/routes.
 * Changing the UI language only re-renders text — it never remounts forms,
 * so patient input data is preserved.
 */
export function useUiLanguage(): [LanguageCode, (lang: LanguageCode) => void, boolean] {
  const [language, setLanguageState] = useState<LanguageCode>('en');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLanguageState(readUiLanguage());
    setLoaded(true);
    const onStorage = (e: StorageEvent) => {
      if (e.key === UI_LANGUAGE_KEY) setLanguageState(readUiLanguage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setLanguage = useCallback((lang: LanguageCode) => {
    setLanguageState(lang);
    writeUiLanguage(lang);
  }, []);

  return [language, setLanguage, loaded];
}

/**
 * Hook: AI interview language state (voice/system prompt language), stored
 * separately from the UI language.
 */
export function useInterviewLanguage(): [LanguageCode, (lang: LanguageCode) => void] {
  const [language, setLanguageState] = useState<LanguageCode>('en');

  useEffect(() => {
    setLanguageState(readInterviewLanguage());
    const onStorage = (e: StorageEvent) => {
      if (e.key === INTERVIEW_LANGUAGE_KEY) setLanguageState(readInterviewLanguage());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setLanguage = useCallback((lang: LanguageCode) => {
    setLanguageState(lang);
    writeInterviewLanguage(lang);
  }, []);

  return [language, setLanguage];
}
