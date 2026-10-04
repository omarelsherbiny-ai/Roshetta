// web/src/app/me/activity/page.tsx (route: /me/activity — personal staff work summary)
'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { getMyActivity, getPersonalAccount } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { localeOf } from '@/lib/languages';
import { MyActivityResponse, PersonalUser } from '@/types';

type PeriodType = 'day' | 'week' | 'month' | 'all';

export default function MyActivityPage() {
  const router = useRouter();
  const { t, lang, dir, isRTL } = useLanguage();

  const [user, setUser] = useState<PersonalUser | null>(null);
  const [period, setPeriod] = useState<PeriodType>('day');
  const [activity, setActivity] = useState<MyActivityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    loadUserData();
    loadActivity(period);
  }, []);

  const loadUserData = async () => {
    try {
      const data = await getPersonalAccount();
      setUser(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadActivity = async (selectedPeriod: PeriodType) => {
    setIsLoading(true);
    setLoadError(false);
    try {
      const data = await getMyActivity(undefined, selectedPeriod);
      setActivity(data);
    } catch (e) {
      console.error(e);
      // No numbers from another period and no zeros: the page shows an error card with a retry instead.
      setActivity(null);
      setLoadError(true);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePeriodChange = (newPeriod: PeriodType) => {
    setPeriod(newPeriod);
    loadActivity(newPeriod);
  };

  // Digits and separators follow the language's locale tag from the registry
  const formatNum = (val: number) => {
    return val.toLocaleString(localeOf(lang));
  };

  const paymentLabels: Record<string, string> = { cash: t('rc_pay_cash'), card: t('as_card') };

  // While the first load runs, numbers are placeholders, never zeros that look like real data.
  const skeleton = (width: string) => (
    <span
      className={`inline-block h-6 ${width} animate-pulse rounded bg-surface-container-highest align-middle motion-reduce:animate-none`}
      aria-hidden="true"
    />
  );
  const countText = (value: number | undefined) => (activity ? String(value ?? 0) : '…');

  const periodOptions: { id: PeriodType; label: string }[] = [
    { id: 'day', label: t('hm_today') },
    { id: 'week', label: t('ma_period_week') },
    { id: 'month', label: t('ma_period_month') },
    { id: 'all', label: t('ma_period_all') },
  ];
  const periodLabel = periodOptions.find((p) => p.id === period)?.label ?? '';

  return (
    <div className="bg-surface text-on-surface flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={user?.name || t('ma_title')}
        subtitle={t('ma_subtitle')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-28 bg-surface px-margin">
        <div className="flex flex-col w-full pb-6 select-none" dir={dir}>
          {/* Page Context Bar */}
          <div className="flex items-center justify-between py-space-sm mb-space-sm">
            <div className="flex items-center gap-space-sm">
              <button
                type="button"
                aria-label={t('back')}
                onClick={() => router.back()}
                className="w-touch-target-min h-touch-target-min rounded-xl bg-surface-container-lowest shadow-sm flex items-center justify-center text-on-surface hover:bg-surface-container active:scale-95 transition-all"
              >
                <span className="material-symbols-outlined text-[22px]">
                  {isRTL ? 'arrow_forward' : 'arrow_back'}
                </span>
              </button>
              <div className="flex flex-col">
                <h1 className="font-headline-sm text-headline-sm text-on-surface leading-tight">
                  {t('ma_title')}
                </h1>
                <span className="font-body-sm text-body-sm text-on-surface-variant">
                  {user ? `${user.name} • ${periodLabel}` : '...'}
                </span>
              </div>
            </div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-container text-primary">
              <span className="w-2 h-2 rounded-full bg-primary"></span>
              <span className="font-label-sm text-label-sm font-bold">
                {t('ma_shift_summary')}
              </span>
            </div>
          </div>

          {/* Hero Visual / Live Shift Progress Card (an error card with retry replaces it when loading fails) */}
          {loadError ? (
            <div className="mb-space-md">
              <ErrorCard
                message={t('ma_load_error')}
                retryLabel={t('retry')}
                onRetry={() => loadActivity(period)}
                retrying={isLoading}
              />
            </div>
          ) : (
          <div className="w-full rounded-2xl bg-surface-container-lowest p-space-md shadow-sm mb-space-md relative overflow-hidden">
            <div className="flex items-start justify-between relative z-10">
              <div>
                <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                  {t('ma_your_period_revenue')}
                </span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="font-stat-numeric text-stat-numeric text-primary leading-none">
                    {activity ? formatNum(activity.total_sales) : skeleton('w-16')}
                  </span>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">
                    {t('currency')}
                  </span>
                </div>
              </div>
              <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                <span className="material-symbols-outlined text-[24px]">verified</span>
              </div>
            </div>
            <div className="flex justify-between items-center mt-3">
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                {t('ma_sales_recorded').replace('{count}', (activity ? formatNum(activity.sales_count) : '…'))}
              </span>
            </div>
          </div>
          )}

          {/* Time Period Selector (Chips) */}
          <div className="flex items-center gap-space-xs mb-space-md overflow-x-auto no-scrollbar py-1">
            {periodOptions.map((p) => {
              const isActive = period === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handlePeriodChange(p.id)}
                  className={`px-4 h-10 rounded-full font-label-md text-label-md flex items-center justify-center transition-all shadow-sm ${
                    isActive
                      ? 'bg-primary text-on-primary'
                      : 'bg-surface-container-lowest text-on-surface hover:bg-surface-container active:scale-95'
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>

          {!loadError && (
          <>
          {/* Personal sales, expenses, and stock movement summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-xs mb-space-lg">
            {/* Sales Card */}
            <div className="bg-surface-container-lowest rounded-2xl p-space-sm shadow-sm flex flex-col justify-between relative overflow-hidden transition-transform active:scale-[0.98]">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  {t('sales')}
                </span>
                <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                  <span className="material-symbols-outlined text-[14px]">trending_up</span>
                </div>
              </div>
              <div className="my-2">
                <div className="font-stat-numeric text-headline-sm text-primary leading-none">
                  {activity ? formatNum(activity.total_sales) : skeleton('w-16')}
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant mt-0.5 block">
                  {t('currency')}
                </span>
              </div>
              <span className="font-body-sm text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded text-center truncate font-medium">
                {t('ma_ops').replace('{count}', countText(activity?.sales_count))}
              </span>
            </div>

            {/* Expenses Card */}
            <div className="bg-surface-container-lowest rounded-2xl p-space-sm shadow-sm flex flex-col justify-between relative overflow-hidden transition-transform active:scale-[0.98]">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  {t('expenses')}
                </span>
                <div className="w-6 h-6 rounded-full bg-secondary-container/20 text-secondary flex items-center justify-center">
                  <span className="material-symbols-outlined text-[14px]">receipt_long</span>
                </div>
              </div>
              <div className="my-2">
                <div className="font-stat-numeric text-headline-sm text-secondary leading-none">
                  {activity ? formatNum(activity.total_expenses) : skeleton('w-16')}
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant mt-0.5 block">
                  {t('currency')}
                </span>
              </div>
              <span className="font-body-sm text-[10px] text-secondary bg-secondary-container/20 px-1.5 py-0.5 rounded text-center truncate font-medium">
                {t('ma_bills').replace('{count}', countText(activity?.expenses_count))}
              </span>
            </div>

            {/* Items Sold Card */}
            <div className="bg-surface-container-lowest rounded-2xl p-space-sm shadow-sm flex flex-col justify-between relative overflow-hidden transition-transform active:scale-[0.98]">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  {t('ma_units')}
                </span>
                <div className="w-6 h-6 rounded-full bg-surface-container-highest text-on-surface flex items-center justify-center">
                  <span className="material-symbols-outlined text-[14px]">medication</span>
                </div>
              </div>
              <div className="my-2">
                <div className="font-stat-numeric text-headline-sm text-on-surface leading-none">
                  {activity ? formatNum(activity.items_sold) : skeleton('w-16')}
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant mt-0.5 block">
                  {t('ov_pkgs')}
                </span>
              </div>
              <span className="font-body-sm text-[10px] text-on-surface bg-surface-container px-1.5 py-0.5 rounded text-center truncate font-medium">
                {t('ma_sold')}
              </span>
            </div>

            {/* Units restocked */}
            <div className="bg-surface-container-lowest rounded-2xl p-space-sm shadow-sm flex flex-col justify-between relative overflow-hidden transition-transform active:scale-[0.98]">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  {t('ma_restocked')}
                </span>
                <div className="w-6 h-6 rounded-full bg-tertiary-container/30 text-tertiary flex items-center justify-center">
                  <span className="material-symbols-outlined text-[14px]">inventory_2</span>
                </div>
              </div>
              <div className="my-2">
                <div className="font-stat-numeric text-headline-sm text-tertiary leading-none">
                  {activity ? formatNum(activity.items_restocked) : skeleton('w-16')}
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant mt-0.5 block">
                  {t('ma_units_added')}
                </span>
              </div>
              <span className="font-body-sm text-[10px] text-tertiary bg-tertiary-container/30 px-1.5 py-0.5 rounded text-center truncate font-medium">
                {t('ma_intakes').replace('{count}', countText(activity?.restocks_count))}
              </span>
            </div>
          </div>

          {/* Transaction Details Section Header */}
          <div className="flex items-center justify-between mb-space-sm">
            <div className="flex items-center gap-2">
              <h2 className="font-headline-sm text-headline-sm text-on-surface">
                {t('ma_transaction_log')}
              </h2>
              <span className="font-label-sm text-label-sm bg-surface-container px-2 py-0.5 rounded-full text-on-surface-variant font-bold">
                {t('ma_actions').replace('{count}', countText(activity?.recent_entries?.length))}
              </span>
            </div>
          </div>

          {/* Recent Transactions List */}
          <div className="flex flex-col gap-space-xs" id="transactions-list">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-on-surface-variant gap-2">
                <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                <span className="text-sm">{t('loading')}</span>
              </div>
            ) : !activity?.recent_entries || activity.recent_entries.length === 0 ? (
              <div className="text-center p-8 bg-surface-container-lowest rounded-xl text-on-surface-variant">
                {t('ma_no_transactions_recorded_period')}
              </div>
            ) : (
              activity.recent_entries.map((entry) => {
                const isSale = entry.entry_type === 'log_sale';
                const isExpense = entry.entry_type === 'log_expense';
                const timeStr = entry.created_at
                  ? new Date(entry.created_at).toLocaleTimeString(localeOf(lang), {
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : '';

                return (
                  <div
                    key={entry.id}
                    className="w-full bg-surface-container-lowest rounded-xl p-space-sm shadow-sm flex items-center justify-between active:bg-surface-container-low transition-colors"
                  >
                    <div className="flex items-center gap-space-sm min-w-0">
                      <div
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                          isSale ? 'bg-primary' : isExpense ? 'bg-error' : 'bg-secondary'
                        }`}
                      ></div>
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-label-lg text-label-lg text-on-surface truncate">
                            {entry.notes || (isSale ? t('rc_type_sale') : t('hm_type_expense'))}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0 ${
                              isSale
                                ? 'bg-primary/10 text-primary'
                                : isExpense
                                ? 'bg-error-container text-on-error-container'
                                : 'bg-surface-container text-on-surface'
                            }`}
                          >
                            {paymentLabels[entry.payment_method || 'cash'] ?? entry.payment_method}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="font-body-sm text-body-sm text-on-surface-variant">{timeStr}</span>
                          <span className="text-on-surface-variant">•</span>
                          <span className="font-body-sm text-body-sm text-on-surface-variant truncate">
                            #{entry.id.slice(-6)}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <div className="flex flex-col items-end">
                        <span
                          className={`font-label-lg text-label-lg font-bold ${
                            isSale ? 'text-primary' : 'text-error'
                          }`}
                        >
                          {isSale ? '+' : '-'}{formatNum(entry.total_amount)}
                        </span>
                        <span className="font-label-sm text-[10px] text-on-surface-variant">
                          {t('currency')}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
          </>
          )}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}