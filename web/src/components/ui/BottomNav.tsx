'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useLanguage } from '@/lib/i18n';

type NavItem = {
  path: string;
  icon: string;
  labelKey: 'home' | 'assistant' | 'scan' | 'inventory' | 'records';
  isFab?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { path: '/',           icon: 'dashboard',        labelKey: 'home' },
  { path: '/assistant',  icon: 'support_agent',    labelKey: 'assistant' },
  { path: '/scan',       icon: 'document_scanner', labelKey: 'scan', isFab: true },
  { path: '/inventory',  icon: 'inventory_2',      labelKey: 'inventory' },
  { path: '/records',    icon: 'receipt_long',     labelKey: 'records' },
];

export function BottomNav() {
  const pathname = usePathname();
  const { t } = useLanguage();

  return (
    <nav className="fixed bottom-0 w-full z-50 pb-safe bg-surface/85 backdrop-blur-xl shadow-[0_-4px_20px_rgba(26,36,32,0.06)]">
      <div className="flex items-center justify-around h-20 px-space-xs">
        {NAV_ITEMS.map((item) => {
          const label = t(item.labelKey);

          if (item.isFab) {
            return (
              <div key={item.path} className="relative -top-5 flex flex-col items-center">
                <Link
                  href={item.path}
                  aria-label={label}
                  className="w-14 h-14 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-[0_8px_16px_-4px_rgba(31,111,80,0.35)] hover:scale-105 active:scale-95 transition-transform duration-150"
                >
                  <span className="material-symbols-outlined text-[28px]">{item.icon}</span>
                </Link>
                <span className="font-label-sm text-label-sm font-bold text-primary mt-1">{label}</span>
              </div>
            );
          }

          const isActive = pathname === item.path;
          return (
            <Link
              key={item.path}
              href={item.path}
              aria-current={isActive ? 'page' : undefined}
              className={`flex flex-col items-center justify-center gap-1 min-w-[56px] min-h-[48px] transition-colors ${
                isActive ? 'text-primary font-bold' : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[24px]">{item.icon}</span>
              <span className="font-label-sm text-label-sm">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}