// web/src/components/ui/TopHeader.tsx (top bar: back, title, language and theme controls, links)
'use client';

import React from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/i18n';
import { HeaderControls } from '@/components/ui/HeaderControls';

interface TopHeaderProps {
  title?: string;
  subtitle?: string;
  showBack?: boolean;
  pharmacyName?: string;
}

export function TopHeader({
  title,
  subtitle,
  showBack = false,
  pharmacyName,
}: TopHeaderProps) {
  const { isRTL, t } = useLanguage();

  return (
    <header className="fixed top-0 z-50 w-full bg-surface/80 pt-safe shadow-[0_1px_8px_rgba(0,0,0,0.04)] backdrop-blur-xl">
      <div className="flex h-16 items-center justify-between gap-space-sm px-margin-mobile">
        <div className="flex min-w-0 items-center gap-space-sm">
          {showBack && (
            <button
              type="button"
              aria-label={t('back')}
              onClick={() => history.back()}
              className="flex h-touch-target-min w-touch-target-min shrink-0 cursor-pointer items-center justify-center rounded-full text-on-surface transition-colors hover:bg-surface-container-high hover:text-primary"
            >
              <span
                className={`material-symbols-outlined text-[24px] ${
                  !isRTL ? 'rotate-180' : ''
                }`}
              >
                arrow_forward
              </span>
            </button>
          )}

          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-on-primary shadow-sm">
            <span className="material-symbols-outlined text-lg">
              local_pharmacy
            </span>
          </div>

          <div className="flex min-w-0 flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-headline-sm text-headline-sm truncate leading-tight text-on-surface">
                {title ?? pharmacyName}
              </span>
            </div>

            <span className="font-label-sm text-label-sm flex items-center gap-1 truncate text-on-surface-variant">
              {subtitle ?? t('app_subtitle')}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <HeaderControls />

          <Link
            href="/pharmacies"
            aria-label={t('my_pharmacies')}
            title={t('my_pharmacies')}
            className="flex h-9 w-9 items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
          >
            <span className="material-symbols-outlined text-[20px]">
              hub
            </span>
          </Link>

          <button
            type="button"
            aria-label={t('notifications')}
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
          >
            <span className="material-symbols-outlined text-[20px]">
              notifications
            </span>
          </button>

          <Link
            href="/settings"
            aria-label={t('settings_profile')}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-on-primary shadow-sm transition-transform hover:scale-105"
          >
            <span className="material-symbols-outlined text-[18px]">
              person
            </span>
          </Link>
        </div>
      </div>
    </header>
  );
}
