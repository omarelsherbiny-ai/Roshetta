// web/src/components/ui/SettingsTabs.tsx (links between Account settings and Pharmacy settings)
'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLanguage } from '@/lib/i18n';

export function SettingsTabs() {
  const pathname = usePathname();
  const { t } = useLanguage();
  const items = [
    { href: '/settings/account', icon: 'manage_accounts', label: t('se_account') },
    { href: '/settings/pharmacy', icon: 'store', label: t('se_pharmacy') },
  ];

  return (
    <nav aria-label={t('se_sections')} className="flex gap-1 rounded-xl bg-surface-container-high p-1">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? 'page' : undefined}
            className={`flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-lg px-2 font-label-lg text-label-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
              active
                ? 'bg-surface-container-lowest text-primary shadow-sm'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
