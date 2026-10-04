// web/src/components/ui/HeaderControls.tsx (language and theme controls shown in the top header on every page)
'use client';

import React from 'react';
import { useLanguage } from '@/lib/i18n';
import { getLanguage, nextLanguageCode } from '@/lib/languages';
import { useTheme, THEME_CHOICES, type ThemeChoice } from '@/lib/theme';

export const THEME_ICONS: Record<ThemeChoice, string> = {
  light: 'light_mode',
  dark: 'dark_mode',
  system: 'desktop_windows',
};

export const THEME_KEYS = {
  light: 'se_theme_light',
  dark: 'se_theme_dark',
  system: 'se_theme_system',
} as const;

const groupClass = 'items-center rounded-xl bg-surface-container-low p-0.5';
const optionBase =
  'flex h-11 min-w-[44px] items-center justify-center rounded-lg px-3 font-label-md text-label-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';
const optionOn = 'bg-surface-container-lowest text-primary shadow-sm';
const optionOff = 'text-on-surface-variant hover:text-on-surface';
const cycleClass =
  'flex h-11 min-w-[44px] items-center justify-center gap-1 rounded-full bg-surface-container px-2.5 font-label-md text-label-md text-primary transition-colors hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

/**
 * Language and theme in one tap. From the small-tablet width up each choice is its own button
 * (aria-pressed groups); on a phone each control is one button that moves to the next choice.
 * Both choices are saved on this device only (languages.ts / i18n.ts and theme.ts do the saving).
 */
export function HeaderControls() {
  const { lang, setLanguage, languages, t } = useLanguage();
  const { theme, setTheme } = useTheme();

  const nextLangName = getLanguage(nextLanguageCode(lang)).name;
  const nextTheme = THEME_CHOICES[(THEME_CHOICES.indexOf(theme) + 1) % THEME_CHOICES.length];
  const themeLabel = t('se_theme_cycle').replace('{name}', t(THEME_KEYS[theme]));

  return (
    <>
      {/* Phone: one button per control */}
      <div className="flex items-center gap-1 sm:hidden">
        <button
          type="button"
          onClick={() => setLanguage(nextLanguageCode(lang))}
          aria-label={t('switch_language').replace('{name}', nextLangName)}
          title={t('switch_language').replace('{name}', nextLangName)}
          className={cycleClass}
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">translate</span>
          <span>{lang.toUpperCase()}</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme(nextTheme)}
          aria-label={themeLabel}
          title={themeLabel}
          className={cycleClass}
        >
          <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{THEME_ICONS[theme]}</span>
        </button>
      </div>

      {/* Tablet and desktop: every choice visible */}
      <div className="hidden items-center gap-2 sm:flex">
        <div role="group" aria-label={t('se_language_label')} className={`flex ${groupClass}`}>
          {languages.map((language) => {
            const active = language.code === lang;
            return (
              <button
                key={language.code}
                type="button"
                aria-pressed={active}
                onClick={() => { if (!active) setLanguage(language.code); }}
                lang={language.code}
                className={`${optionBase} ${active ? optionOn : optionOff}`}
              >
                {language.name}
              </button>
            );
          })}
        </div>
        <div role="group" aria-label={t('se_theme')} className={`flex ${groupClass}`}>
          {THEME_CHOICES.map((choice) => {
            const active = choice === theme;
            const name = t(THEME_KEYS[choice]);
            return (
              <button
                key={choice}
                type="button"
                aria-pressed={active}
                aria-label={name}
                title={name}
                onClick={() => setTheme(choice)}
                className={`${optionBase} ${active ? optionOn : optionOff}`}
              >
                <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{THEME_ICONS[choice]}</span>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}
