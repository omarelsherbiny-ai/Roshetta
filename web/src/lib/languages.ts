// web/src/lib/languages.ts (language registry: the only list of languages, their direction and dictionaries)
// No 'use client': the root layout (a server component) imports this file too.
import ar from '@/locales/ar.json';
import en from '@/locales/en.json';

export type Direction = 'rtl' | 'ltr';

/** Every dictionary must have exactly the keys of this one; a missing key is a compile error. */
export type Dictionary = typeof en;

export interface LanguageInfo {
  code: string;
  /** Written in the language itself, never translated. */
  name: string;
  dir: Direction;
  /** BCP 47 tag used to format numbers and dates (digits, separators, month names). */
  locale: string;
  /** First day of the week in calendars: 0 = Sunday ... 6 = Saturday. */
  weekStart: number;
  dictionary: Dictionary;
}

/**
 * To add a language: add `web/src/locales/<code>.json` with the same keys as `en.json`,
 * import it above and add one line here (with its locale tag and first weekday). Nothing else in the app lists languages.
 */
export const LANGUAGES: readonly LanguageInfo[] = [
  { code: 'ar', name: 'العربية', dir: 'rtl', locale: 'ar-EG', weekStart: 6, dictionary: ar },
  { code: 'en', name: 'English', dir: 'ltr', locale: 'en-US', weekStart: 1, dictionary: en },
];

/** Used before the saved choice is read and whenever the saved code is unknown. */
export const DEFAULT_LANGUAGE: string = LANGUAGES[0].code;

export function isLanguageCode(code: string): boolean {
  return LANGUAGES.some((language) => language.code === code);
}

export function getLanguage(code: string): LanguageInfo {
  return LANGUAGES.find((language) => language.code === code) ?? LANGUAGES[0];
}

export function localeOf(code: string): string {
  return getLanguage(code).locale;
}

export function weekStartOf(code: string): number {
  return getLanguage(code).weekStart;
}

export function directionOf(code: string): Direction {
  return getLanguage(code).dir;
}

/** The language after `code` in the list, wrapping around (what the header toggle uses). */
export function nextLanguageCode(code: string): string {
  const index = LANGUAGES.findIndex((language) => language.code === code);
  return LANGUAGES[(index + 1) % LANGUAGES.length].code;
}

/**
 * Product names are stored in Arabic and English only. Arabic shows the Arabic name first,
 * every other language shows the English one first; the other name is the fallback.
 */
export function pickLocalizedName(
  code: string,
  nameAr: string | null | undefined,
  nameEn: string | null | undefined,
): string {
  return (code === 'ar' ? nameAr || nameEn : nameEn || nameAr) ?? '';
}

/** The name that is not shown first (the small line under a product name). */
export function pickOtherName(
  code: string,
  nameAr: string | null | undefined,
  nameEn: string | null | undefined,
): string {
  return (code === 'ar' ? nameEn : nameAr) ?? '';
}

/** Text direction of the name returned by `pickOtherName`: English for Arabic, Arabic for every other language. */
export function otherNameDirection(code: string): Direction {
  return code === 'ar' ? 'ltr' : 'rtl';
}