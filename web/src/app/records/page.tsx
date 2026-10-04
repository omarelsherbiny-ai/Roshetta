// web/src/app/records/page.tsx (route: /records — transaction ledger)
'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { getRecentEntries, getFinancialSummary } from '@/lib/api';
import type { LedgerEntryTypeFilter } from '@/lib/api';
import { FinancialSummary, LedgerEntryResponse } from '@/types';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { localeOf } from '@/lib/languages';
import { formatDateTime } from '@/lib/utils';
import { usePharmacyName } from '@/hooks/usePharmacyName';
import { DateRangePicker } from '@/components/records/DateRangePicker';
import { cairoToday } from '@/lib/dateRange';

// Entries load this many at a time. One extra row is requested to learn whether more exist.
const PAGE_SIZE = 50;

// One look per entry type, so a sale, an expense and a restock never share an icon or a color.
// The same colors drive the row icon, the amount and the tab: sale = emerald, expense = amber, restock = rust.
const ENTRY_STYLES: Record<string, { icon: string; iconWrap: string; text: string; sign: string }> = {
  log_sale: { icon: 'point_of_sale', iconWrap: 'bg-surface-container text-primary', text: 'text-primary', sign: '+' },
  log_expense: { icon: 'payments', iconWrap: 'bg-secondary-fixed text-secondary', text: 'text-secondary', sign: '−' },
  log_restock: { icon: 'local_shipping', iconWrap: 'bg-tertiary-fixed text-tertiary', text: 'text-tertiary', sign: '−' },
};

export default function RecordsPage() {
  const router = useRouter();
  const { t, lang, dir } = useLanguage();
  const pharmacyName = usePharmacyName();
  const fmt = (value: number) => value.toLocaleString(localeOf(lang), { maximumFractionDigits: 2 });
  const paymentLabels: Record<string, string> = {
    cash: t('rc_pay_cash'),
    card: t('rc_pay_card'),
    credit: t('rc_pay_credit'),
  };
  const [entries, setEntries] = useState<LedgerEntryResponse[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [financials, setFinancials] = useState<FinancialSummary | null>(null);
  const [filterType, setFilterType] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [reportStartDate, setReportStartDate] = useState(() => cairoToday());
  const [reportEndDate, setReportEndDate] = useState(() => cairoToday());

  // Bumped on every fresh load so a slow "Show more" response from an old range or filter is ignored.
  const listVersion = useRef(0);
  const entryTypeFilter: LedgerEntryTypeFilter | undefined =
    filterType === 'all' ? undefined : (filterType as LedgerEntryTypeFilter);

  // Summary strip: depends on the date range only.
  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/onboarding'); return; }
    let active = true;
    setFinancials(null);
    getFinancialSummary(undefined, reportStartDate, reportEndDate)
      .then((fin) => { if (active) setFinancials(fin); })
      .catch(() => {
        if (active) setLoadError(t('rc_load_error'));
      });
    return () => { active = false; };
  }, [reportStartDate, reportEndDate, router, lang]);

  // Entries list: depends on the date range and the type tab (the server filters, so tabs cover the whole range).
  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/onboarding'); return; }
    let active = true;
    const version = ++listVersion.current;
    setIsLoading(true);
    setLoadError(null);
    setMoreError(null);
    setEntries([]);
    setHasMore(false);
    getRecentEntries(PAGE_SIZE + 1, undefined, reportStartDate, reportEndDate, { entryType: entryTypeFilter })
      .then((rows) => {
        if (!active || version !== listVersion.current) return;
        setEntries(rows.slice(0, PAGE_SIZE));
        setHasMore(rows.length > PAGE_SIZE);
      })
      .catch(() => {
        if (active) setLoadError(t('rc_load_error'));
      })
      .finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; };
  }, [reportStartDate, reportEndDate, filterType, router, lang]);

  const loadMore = async () => {
    if (isLoadingMore) return;
    const version = listVersion.current;
    setIsLoadingMore(true);
    setMoreError(null);
    try {
      const rows = await getRecentEntries(PAGE_SIZE + 1, undefined, reportStartDate, reportEndDate, {
        offset: entries.length,
        entryType: entryTypeFilter,
      });
      if (version !== listVersion.current) return;
      setEntries((prev) => {
        // New entries can arrive while paging; skip any row already shown.
        const seen = new Set(prev.map((e) => e.id));
        return [...prev, ...rows.slice(0, PAGE_SIZE).filter((e) => !seen.has(e.id))];
      });
      setHasMore(rows.length > PAGE_SIZE);
    } catch {
      if (version === listVersion.current) {
        setMoreError(t('rc_more_error'));
      }
    } finally {
      setIsLoadingMore(false);
    }
  };

  const actionClasses =
    'inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg px-4 font-label-lg text-label-lg transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

  return (
    <div className="flex flex-col min-h-screen bg-surface text-on-surface">
      <TopHeader
        pharmacyName={pharmacyName}
        subtitle={t('records')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-28 bg-surface">
        <div className={`flex flex-col w-full px-margin-mobile pt-3 pb-6 gap-space-md`} dir={dir}>

          <DateRangePicker
            start={reportStartDate}
            end={reportEndDate}
            onApply={(newStart, newEnd) => {
              setReportStartDate(newStart);
              setReportEndDate(newEnd);
            }}
          />

          {/* ── Financial Strip ── */}
          {financials && (
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-surface-container-lowest rounded-xl p-3 shadow-sm text-center">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('sales')}</span>
                <span className="font-stat-numeric text-[20px] font-bold text-primary">
                  {financials.total_sales.toLocaleString(localeOf(lang))} {t('currency')}
                </span>
              </div>
              <div className="bg-surface-container-lowest rounded-xl p-3 shadow-sm text-center">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('expenses')}</span>
                <span className="font-stat-numeric text-[20px] font-bold text-secondary">
                  {financials.total_expenses.toLocaleString(localeOf(lang))} {t('currency')}
                </span>
              </div>
              <div className="bg-primary-container text-on-primary-container rounded-xl p-3 shadow-sm text-center">
                <span className="font-label-sm text-label-sm text-primary-fixed block">{t('net_profit')}</span>
                <span className="font-stat-numeric text-[20px] font-bold text-on-primary">
                  {financials.net_profit === null ? t('rc_unavailable') : `${financials.net_profit.toLocaleString(localeOf(lang))} ${t('currency')}`}
                </span>
              </div>
            </div>
          )}

          {/* ── Filter Tabs ── */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
            {[
              { id: 'all', label: t('rc_tab_all'), icon: 'view_list', active: 'bg-primary text-on-primary', iconColor: 'text-on-surface-variant' },
              { id: 'log_sale', label: t('sales'), icon: 'point_of_sale', active: 'bg-primary text-on-primary', iconColor: 'text-primary' },
              { id: 'log_expense', label: t('rc_tab_expense'), icon: 'payments', active: 'bg-secondary text-on-secondary', iconColor: 'text-secondary' },
              { id: 'log_restock', label: t('rc_tab_restock'), icon: 'local_shipping', active: 'bg-tertiary text-on-tertiary', iconColor: 'text-tertiary' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                aria-pressed={filterType === tab.id}
                onClick={() => setFilterType(tab.id)}
                className={`inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-1.5 rounded-full font-label-sm text-label-sm shrink-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  filterType === tab.id
                    ? `${tab.active} font-bold shadow-sm`
                    : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <span aria-hidden="true" className={`material-symbols-outlined text-[16px] ${filterType === tab.id ? '' : tab.iconColor}`}>{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>

          {/* ── Entry point to supplier payables (restocks recorded on credit create what is owed) ── */}
          {filterType === 'log_restock' && (
            <button
              type="button"
              onClick={() => router.push('/payables')}
              className={`${actionClasses} self-start bg-tertiary-fixed text-tertiary`}
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">account_balance_wallet</span>
              {t('rc_payables')}
            </button>
          )}

          {/* ── Entries List ── */}
          <div className="flex flex-col gap-2.5">
            {loadError && !isLoading && (
              <div role="alert" className="rounded-xl bg-error-container p-4 text-sm text-error">
                {loadError}
              </div>
            )}
            {isLoading ? (
              <div className="flex items-center justify-center p-8 text-on-surface-variant gap-2">
                <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                <span className="text-sm">{t('rc_loading')}</span>
              </div>
            ) : entries.length === 0 ? (
              <div className="text-center p-8 bg-surface-container-lowest rounded-xl text-on-surface-variant">
                {t('rc_empty')}
              </div>
            ) : (
              entries.map((e) => {
                const style = ENTRY_STYLES[e.entry_type] ?? ENTRY_STYLES.log_expense;
                // Payment methods the ledger stores (LedgerEntry.payment_method: cash | card | credit).
                const paymentText = paymentLabels[e.payment_method] ?? e.payment_method;

                return (
                  <div
                    key={e.id}
                    className="bg-surface-container-lowest rounded-xl p-3.5 shadow-sm flex flex-col gap-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${style.iconWrap}`}
                        >
                          <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                            {style.icon}
                          </span>
                        </div>
                        <div className="flex flex-col">
                          <span className={`font-label-md text-label-md font-bold ${style.text}`}>
                            {e.entry_type === 'log_sale' ? t('rc_type_sale') : e.entry_type === 'log_restock' ? t('rc_type_restock') : t('rc_type_expense')}
                          </span>
                          <span className="font-body-sm text-[11px] text-on-surface-variant">
                            {formatDateTime(e.confirmed_at ?? e.created_at, lang)}
                          </span>
                        </div>
                      </div>

                      <div className="text-left font-stat-numeric text-[17px] font-bold">
                        <span dir="ltr" className={style.text}>
                          {style.sign}{fmt(e.total_amount)} {t('currency')}
                        </span>
                      </div>
                    </div>

                    {/* Breakdown items */}
                    {e.items && e.items.length > 0 && (
                      <div className="bg-surface-container-low/70 rounded-lg p-2 flex flex-col gap-1 text-xs">
                        {e.items.map((item, idx) => (
                          <div key={idx} className="flex items-center justify-between text-on-surface">
                            <span>{item.item_name} × {fmt(item.quantity)}</span>
                            <span>{fmt(item.subtotal)} {t('currency')}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {e.notes && (
                      <span className="text-[11px] text-on-surface-variant italic">
                        {t('rc_notes')} {e.notes}
                      </span>
                    )}

                    {/* Payment method and who confirmed the entry (both real ledger fields) */}
                    <span className="font-body-sm text-[11px] text-on-surface-variant">
                      {t('rc_payment')} {paymentText}
                      {e.confirmed_by_name && (
                        <> · {t('rc_confirmed_by')} {e.confirmed_by_name}</>
                      )}
                    </span>
                  </div>
                );
              })
            )}

            {/* ── Count and Show more (same pattern as /inventory) ── */}
            {!isLoading && !loadError && entries.length > 0 && (
              <div className="mt-space-md flex flex-col items-center gap-2 font-body-sm text-body-sm text-on-surface-variant">
                <span>
                  {t('rc_showing').replace('{count}', fmt(entries.length))}
                </span>
                {moreError && (
                  <span role="alert" className="text-error">{moreError}</span>
                )}
                {hasMore && (
                  <button
                    type="button"
                    onClick={loadMore}
                    disabled={isLoadingMore}
                    className={`${actionClasses} bg-surface-container-high text-on-surface disabled:opacity-60`}
                  >
                    {isLoadingMore ? t('rc_loading_more') : t('inv_show_more')}
                  </button>
                )}
              </div>
            )}
          </div>

        </div>
      </main>

      <BottomNav />
    </div>
  );
}