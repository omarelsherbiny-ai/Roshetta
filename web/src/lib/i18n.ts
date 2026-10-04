// web/src/lib/i18n.ts (language state hook; languages, directions and texts come from languages.ts and locales/)
'use client';

import { useState, useEffect } from 'react';
import {
  DEFAULT_LANGUAGE,
  LANGUAGES,
  getLanguage,
  isLanguageCode,
  nextLanguageCode,
  type Dictionary,
} from './languages';

/** A language code from the registry in `languages.ts`. */
export type Language = string;

const STORAGE_KEY = 'roshetta_lang';

function readLanguage(): Language {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved && isLanguageCode(saved) ? saved : DEFAULT_LANGUAGE;
}

/** The saved language code; the default on the server or when nothing valid is saved. */
export function getStoredLanguage(): Language {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE;
  return readLanguage();
}

function applyToDocument(code: Language): void {
  const language = getLanguage(code);
  document.documentElement.dir = language.dir;
  document.documentElement.lang = language.code;
}

export function persistLanguage(language: Language): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, language);
  applyToDocument(language);
  window.dispatchEvent(new Event('roshetta_lang_changed'));
}

/** Dictionaries by language code (kept for code that reads a specific language directly). */
export const translations: Record<string, Dictionary> = Object.fromEntries(
  LANGUAGES.map((language) => [language.code, language.dictionary]),
);

export function useLanguage() {
  const [lang, setLang] = useState<Language>(DEFAULT_LANGUAGE);

  useEffect(() => {
    const sync = () => {
      const current = readLanguage();
      setLang(current);
      applyToDocument(current);
    };

    sync();

    window.addEventListener('roshetta_lang_changed', sync);

    return () =>
      window.removeEventListener('roshetta_lang_changed', sync);
  }, []);

  const setLanguage = (code: Language) => {
    if (!isLanguageCode(code)) return;

    persistLanguage(code);
    setLang(code);
  };

  const toggleLanguage = () => {
    setLanguage(nextLanguageCode(lang));
  };

  const info = getLanguage(lang);

  const t = (key: keyof Dictionary): string => {
    return info.dictionary[key] ?? String(key);
  };

  return {
    lang,
    isRTL: info.dir === 'rtl',
    dir: info.dir,
    t,
    toggleLanguage,
    setLanguage,
    languages: LANGUAGES,
  };
}