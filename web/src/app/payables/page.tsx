// web/src/app/payables/page.tsx (route: /payables — supplier payables: what is still owed per credit restock, record payments)
'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { getPayables, getPayablesSummary, recordSettlement } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { localeOf } from '@/lib/languages';
import { formatDateTime } from '@/lib/utils';
import { usePharmacyName } from '@/hooks/usePharmacyName';
import { DateRangePicker } from '@/components/records/DateRangePicker';
import { addDays, cairoToday } from '@/lib/dateRange';
import type { PayableResponse, PayablesSummaryResponse, PayableStatus } from '@/types';

// Restocks load this many at a time. One extra row is requested to learn whether more exist.
const PAGE_SIZE = 20;
// Debts can be older than today, so the page opens on the last 90 days (the picker can widen it).
const DEFAULT_RANGE_DAYS = 90;

// One look per status, used for the badge, the chip and the icon everywhere (never two icons for one status).
const STATUS_STYLES: Record<PayableStatus, { icon: string; badge: string }> = {
  unpaid: { icon: 'schedule', badge: 'bg-error-container text-error' },
  partly_paid: { icon: 'timelapse', badge: 'bg-secondary-fixed text-on-secondary-fixed' },
  paid: { icon: 'check_circle', badge: 'bg-primary-fixed text-on-primary-fixed-variant' },
};

// Payment methods a settlement can use (SettlementCreate.payment_method: cash | card).
const METHOD_ICONS: Record<'cash' | 'card', string> = {
  cash: 'payments',
  card: 'credit_card',
};

type StatusFilter = 'all' | PayableStatus;
type SupplierGroup = { name: string | null; rows: PayableResponse[]; owed: number };

const round2 = (value: number) => Math.round(value * 100) / 100;

export default function PayablesPage() {
  const router = useRouter();
  const { t, lang, dir } = useLanguage();
  const pharmacyName = usePharmacyName();
  const fmt = (value: number) => value.toLocaleString(localeOf(lang), { maximumFractionDigits: 2 });
  const statusLabels: Record<PayableStatus, string> = {
    unpaid: t('pb_status_unpaid'),
    partly_paid: t('pb_status_partly'),
    paid: t('pb_status_paid'),
  };
  const methodLabels: Record<string, string> = { cash: t('rc_pay_cash'), card: t('rc_pay_card') };

  const [startDay, setStartDay] = useState(() => addDays(cairoToday(), -(DEFAULT_RANGE_DAYS - 1)));
  const [endDay, setEndDay] = useState(() => cairoToday());
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [summary, setSummary] = useState<PayablesSummaryResponse | null>(null);
  const [rows, setRows] = useState<PayableResponse[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [payingRow, setPayingRow] = useState<PayableResponse | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Bumped after a payment or a retry so both the summary and the list load again.
  const [reloadKey, setReloadKey] = useState(0);

  // Bumped on every fresh load so a slow "Show more" response from an old range or filter is ignored.
  const listVersion = useRef(0);
  const statusParam = statusFilter === 'all' ? undefined : statusFilter;
  const loadFailedText = t('pb_load_error');

  // Summary strip and chip counts: depend on the date range only.
  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/onboarding'); return; }
    let active = true;
    getPayablesSummary(startDay, endDay)
      .then((data) => { if (active) setSummary(data); })
      .catch((error) => {
        if (active) setLoadError(error instanceof Error && error.message ? error.message : loadFailedText);
      });
    return () => { active = false; };
  }, [startDay, endDay, reloadKey, router, lang]);

  // Restock list: depends on the date range and the status chip (the server filters, so chips cover the whole range).
  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/onboarding'); return; }
    let active = true;
    const version = ++listVersion.current;
    setIsLoading(true);
    setLoadError(null);
    setMoreError(null);
    setHasMore(false);
    getPayables({ limit: PAGE_SIZE + 1, status: statusParam, startDay, endDay })
      .then((data) => {
        if (!active || version !== listVersion.current) return;
        setRows(data.slice(0, PAGE_SIZE));
        setHasMore(data.length > PAGE_SIZE);
      })
      .catch((error) => {
        if (active) {
          setRows([]);
          setLoadError(error instanceof Error && error.message ? error.message : loadFailedText);
        }
      })
      .finally(() => { if (active) setIsLoading(false); });
    return () => { active = false; };
  }, [startDay, endDay, statusFilter, reloadKey, router, lang]);

  // The success message disappears on its own; the timer is cleared if the page closes first.
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const loadMore = async () => {
    if (isLoadingMore) return;
    const version = listVersion.current;
    setIsLoadingMore(true);
    setMoreError(null);
    try {
      const data = await getPayables({ limit: PAGE_SIZE + 1, offset: rows.length, status: statusParam, startDay, endDay });
      if (version !== listVersion.current) return;
      setRows((prev) => {
        // New restocks can arrive while paging; skip any row already shown.
        const seen = new Set(prev.map((row) => row.id));
        return [...prev, ...data.slice(0, PAGE_SIZE).filter((row) => !seen.has(row.id))];
      });
      setHasMore(data.length > PAGE_SIZE);
    } catch {
      if (version === listVersion.current) {
        setMoreError(t('rc_more_error'));
      }
    } finally {
      setIsLoadingMore(false);
    }
  };

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handlePaid = () => {
    setPayingRow(null);
    setToast(t('pb_paid_toast'));
    setReloadKey((key) => key + 1);
  };

  // Group the loaded restocks by supplier name; restocks without a name go last.
  const groupMap = new Map<string, SupplierGroup>();
  for (const row of rows) {
    const name = row.supplier_name?.trim() || null;
    const key = name ?? '\u0000none';
    const group = groupMap.get(key) ?? { name, rows: [], owed: 0 };
    group.rows.push(row);
    group.owed = round2(group.owed + row.remaining_amount);
    groupMap.set(key, group);
  }
  const groups: SupplierGroup[] = Array.from(groupMap.values()).sort((a, b) => Number(a.name === null) - Number(b.name === null));

  const trackingDay = summary?.tracking_started_at
    ? new Date(summary.tracking_started_at).toLocaleDateString(localeOf(lang), {
        timeZone: 'Africa/Cairo', year: 'numeric', month: 'long', day: 'numeric',
      })
    : null;
  const totalCount = summary ? summary.unpaid_count + summary.partly_paid_count + summary.paid_count : null;
  const chips: { id: StatusFilter; label: string; icon: string; count: number | null }[] = [
    { id: 'all', label: t('inv_all'), icon: 'view_list', count: totalCount },
    { id: 'unpaid', label: statusLabels.unpaid, icon: STATUS_STYLES.unpaid.icon, count: summary?.unpaid_count ?? null },
    { id: 'partly_paid', label: statusLabels.partly_paid, icon: STATUS_STYLES.partly_paid.icon, count: summary?.partly_paid_count ?? null },
    { id: 'paid', label: statusLabels.paid, icon: STATUS_STYLES.paid.icon, count: summary?.paid_count ?? null },
  ];

  const actionClasses =
    'inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg px-4 font-label-lg text-label-lg transition-all active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

  return (
    <div className="flex flex-col min-h-screen bg-surface text-on-surface">
      <TopHeader
        pharmacyName={pharmacyName}
        subtitle={t('rc_payables')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-28 bg-surface">
        <div className="flex flex-col w-full max-w-3xl mx-auto px-margin-mobile pt-3 pb-6 gap-space-md" dir={dir}>

          <DateRangePicker
            start={startDay}
            end={endDay}
            onApply={(newStart, newEnd) => {
              setStartDay(newStart);
              setEndDay(newEnd);
            }}
          />

          {/* ── Summary: what is still owed for restocks in the selected range ── */}
          {summary && (
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-tertiary-fixed text-on-tertiary-fixed rounded-xl p-3 shadow-sm">
                <span className="font-label-sm text-label-sm block">{t('pb_total_owed')}</span>
                <span className="font-stat-numeric text-[22px] font-bold text-tertiary" dir="ltr">
                  {fmt(summary.total_remaining)} {t('currency')}
                </span>
              </div>
              <div className="bg-surface-container-lowest rounded-xl p-3 shadow-sm">
                <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('pb_open_restocks')}</span>
                <span className="font-stat-numeric text-[22px] font-bold text-on-surface">{fmt(summary.open_count)}</span>
              </div>
            </div>
          )}
          {trackingDay && (
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              {t('pb_tracking').replace('{date}', trackingDay)}
            </p>
          )}

          {/* ── Status chips (counts cover the whole selected range) ── */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
            {chips.map((chip) => (
              <button
                key={chip.id}
                type="button"
                aria-pressed={statusFilter === chip.id}
                onClick={() => setStatusFilter(chip.id)}
                className={`inline-flex min-h-[44px] items-center gap-1.5 px-3.5 py-1.5 rounded-full font-label-sm text-label-sm shrink-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  statusFilter === chip.id
                    ? 'bg-primary text-on-primary font-bold shadow-sm'
                    : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[16px]">{chip.icon}</span>
                {chip.label}
                {chip.count !== null && <span className="font-stat-numeric">({fmt(chip.count)})</span>}
              </button>
            ))}
          </div>

          {/* ── List ── */}
          <div className="flex flex-col gap-space-md">
            {loadError && !isLoading && (
              <div role="alert" className="flex items-center justify-between gap-3 rounded-xl bg-error-container p-4 text-sm text-error">
                <span>{loadError}</span>
                <button
                  type="button"
                  onClick={() => { setLoadError(null); setReloadKey((key) => key + 1); }}
                  className={`${actionClasses} shrink-0 bg-surface-container-lowest text-error`}
                >
                  {t('retry')}
                </button>
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center p-8 text-on-surface-variant gap-2" role="status">
                <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
                <span className="text-sm">{t('pb_loading')}</span>
              </div>
            ) : rows.length === 0 ? (
              !loadError && (
                <div className="text-center p-8 bg-surface-container-lowest rounded-xl text-on-surface-variant">
                  {statusFilter === 'all'
                    ? t('pb_empty_all')
                    : t('pb_empty_status')}
                </div>
              )
            ) : (
              groups.map((group) => (
                <section key={group.name ?? 'none'} className="flex flex-col gap-2.5" aria-label={group.name ?? t('pb_no_supplier')}>
                  <div className="flex items-center justify-between gap-2 px-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span aria-hidden="true" className="material-symbols-outlined text-primary text-[20px]">local_shipping</span>
                      <h2 className="font-headline-sm text-headline-sm text-on-surface truncate">
                        {group.name ?? t('pb_no_supplier')}
                      </h2>
                    </div>
                    <div className="flex flex-col items-end shrink-0">
                      <span className="font-stat-numeric text-label-lg font-bold text-tertiary" dir="ltr">
                        {fmt(group.owed)} {t('currency')}
                      </span>
                      <span className="font-label-sm text-label-sm text-on-surface-variant">
                        {t('pb_group_owed').replace('{count}', fmt(group.rows.length))}
                      </span>
                    </div>
                  </div>

                  {group.rows.map((row) => {
                    const style = STATUS_STYLES[row.status];
                    const isOpen = expanded.has(row.id);
                    return (
                      <article key={row.id} className="bg-surface-container-lowest rounded-xl p-3.5 shadow-sm flex flex-col gap-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex flex-col min-w-0">
                            <span className="font-label-md text-label-md font-bold text-on-surface">
                              {formatDateTime(row.confirmed_at ?? row.created_at, lang)}
                            </span>
                            {row.confirmed_by_name && (
                              <span className="font-body-sm text-[11px] text-on-surface-variant">
                                {t('rc_confirmed_by')} {row.confirmed_by_name}
                              </span>
                            )}
                          </div>
                          <span className={`inline-flex items-center gap-1 shrink-0 rounded-full px-2.5 py-1 font-label-sm text-label-sm font-bold ${style.badge}`}>
                            <span aria-hidden="true" className="material-symbols-outlined text-[14px]">{style.icon}</span>
                            {statusLabels[row.status]}
                          </span>
                        </div>

                        {row.notes && (
                          <span className="text-[11px] text-on-surface-variant italic break-words">
                            {t('rc_notes')} {row.notes}
                          </span>
                        )}

                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="bg-surface-container-low rounded-lg p-2">
                            <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('as_total')}</span>
                            <span className="font-stat-numeric text-label-lg font-bold text-on-surface" dir="ltr">{fmt(row.total_amount)}</span>
                          </div>
                          <div className="bg-surface-container-low rounded-lg p-2">
                            <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('pb_paid')}</span>
                            <span className="font-stat-numeric text-label-lg font-bold text-primary" dir="ltr">{fmt(row.paid_amount)}</span>
                          </div>
                          <div className="bg-surface-container-low rounded-lg p-2">
                            <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('pb_remaining')}</span>
                            <span className="font-stat-numeric text-label-lg font-bold text-tertiary" dir="ltr">{fmt(row.remaining_amount)}</span>
                          </div>
                        </div>

                        <div className="flex items-center justify-between gap-2">
                          <button
                            type="button"
                            aria-expanded={isOpen}
                            onClick={() => toggleExpanded(row.id)}
                            className={`${actionClasses} px-2 text-on-surface-variant hover:text-on-surface`}
                          >
                            <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
                              {isOpen ? 'expand_less' : 'expand_more'}
                            </span>
                            {t('pb_items_payments')}
                          </button>
                          {row.status !== 'paid' && (
                            <button
                              type="button"
                              onClick={() => setPayingRow(row)}
                              className={`${actionClasses} bg-primary text-on-primary shadow-sm`}
                            >
                              <span aria-hidden="true" className="material-symbols-outlined text-[18px]">payments</span>
                              {t('pb_record_payment')}
                            </button>
                          )}
                        </div>

                        {isOpen && (
                          <div className="flex flex-col gap-3">
                            <div className="bg-surface-container-low/70 rounded-lg p-2 flex flex-col gap-1 text-xs">
                              {row.items.length === 0 ? (
                                <span className="text-on-surface-variant">{t('pb_no_items')}</span>
                              ) : (
                                row.items.map((item, idx) => (
                                  <div key={idx} className="flex items-center justify-between text-on-surface">
                                    <span>{item.item_name} × {fmt(item.quantity)}</span>
                                    <span>{fmt(item.subtotal)} {t('currency')}</span>
                                  </div>
                                ))
                              )}
                            </div>
                            <div className="bg-surface-container-low/70 rounded-lg p-2 flex flex-col gap-1.5 text-xs">
                              <span className="font-label-sm text-label-sm font-bold text-on-surface">{t('pb_recorded_payments')}</span>
                              {row.settlements.length === 0 ? (
                                <span className="text-on-surface-variant">{t('pb_no_payments')}</span>
                              ) : (
                                row.settlements.map((payment) => {
                                  return (
                                    <div key={payment.id} className="flex items-center justify-between gap-2 text-on-surface">
                                      <div className="flex flex-col min-w-0">
                                        <span>{formatDateTime(payment.paid_at, lang)}</span>
                                        <span className="text-[11px] text-on-surface-variant">
                                          {methodLabels[payment.payment_method] ?? payment.payment_method}
                                          {payment.paid_by_name && <> · {t('pb_recorded_by')} {payment.paid_by_name}</>}
                                        </span>
                                      </div>
                                      <span className="font-stat-numeric font-bold text-primary shrink-0">{fmt(payment.amount)} {t('currency')}</span>
                                    </div>
                                  );
                                })
                              )}
                            </div>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </section>
              ))
            )}

            {/* ── Count and Show more (same pattern as /records) ── */}
            {!isLoading && !loadError && rows.length > 0 && (
              <div className="mt-space-md flex flex-col items-center gap-2 font-body-sm text-body-sm text-on-surface-variant text-center">
                <span>{t('pb_showing').replace('{count}', fmt(rows.length))}</span>
                {hasMore && (
                  <span>
                    {t('pb_totals_note')}
                  </span>
                )}
                {moreError && <span role="alert" className="text-error">{moreError}</span>}
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

      {toast && (
        <div
          role="status"
          className="fixed bottom-24 left-1/2 z-40 -translate-x-1/2 flex items-center gap-2 rounded-full bg-inverse-surface px-4 py-2.5 text-inverse-on-surface shadow-lg"
        >
          <span aria-hidden="true" className="material-symbols-outlined text-[18px] text-inverse-primary">check_circle</span>
          <span className="font-label-md text-label-md">{toast}</span>
        </div>
      )}

      {payingRow && (
        <PaymentDialog
          row={payingRow}
          onClose={() => setPayingRow(null)}
          onPaid={handlePaid}
        />
      )}

      <BottomNav />
    </div>
  );
}

// Payment sheet on a phone, dialog on a wider screen. The payer is always the signed-in user (the server records it).
function PaymentDialog({
  row, onClose, onPaid,
}: {
  row: PayableResponse;
  onClose: () => void;
  onPaid: () => void;
}) {
  const { t, lang, dir } = useLanguage();
  const currency = t('currency');
  const fmt = (value: number) => value.toLocaleString(localeOf(lang), { maximumFractionDigits: 2 });
  const methodLabels: Record<'cash' | 'card', string> = { cash: t('rc_pay_cash'), card: t('rc_pay_card') };
  const remaining = round2(row.remaining_amount);

  const [amountText, setAmountText] = useState(remaining.toFixed(2));
  const [method, setMethod] = useState<'cash' | 'card'>('cash');
  const [isSaving, setIsSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const typed = amountText.trim() === '' ? NaN : Number(amountText);
  let amountError: string | null = null;
  if (amountText.trim() === '' || !Number.isFinite(typed)) {
    amountError = t('pb_err_enter');
  } else if (round2(typed) <= 0) {
    amountError = t('pb_err_zero');
  } else if (round2(typed) > remaining) {
    amountError = t('pb_err_over').replace('{amount}', fmt(remaining)).replace('{currency}', currency);
  }

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  // Stop the page behind from scrolling while the dialog is open.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSaving) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isSaving, onClose]);

  const submit = async () => {
    if (amountError || isSaving) return;
    setIsSaving(true);
    setSubmitError(null);
    try {
      await recordSettlement(row.id, { amount: round2(typed), payment_method: method });
      onPaid();
    } catch (error) {
      setSubmitError(error instanceof Error && error.message ? error.message : t('pb_dlg_submit_error'));
      setIsSaving(false);
    }
  };

  const supplier = row.supplier_name?.trim() || t('pb_no_supplier');

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center" dir={dir}>
      <div
        className="absolute inset-0 bg-inverse-surface/50"
        onClick={() => { if (!isSaving) onClose(); }}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="payment-dialog-title"
        className="relative w-full md:max-w-md max-h-[90vh] overflow-y-auto bg-surface-container-lowest rounded-t-2xl md:rounded-2xl p-space-md pb-safe shadow-xl flex flex-col gap-space-md"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col min-w-0">
            <h2 id="payment-dialog-title" className="font-headline-sm text-headline-sm text-on-surface">
              {t('pb_dlg_title')}
            </h2>
            <span className="font-body-sm text-body-sm text-on-surface-variant truncate">{supplier}</span>
          </div>
          <button
            type="button"
            aria-label={t('cat_close')}
            disabled={isSaving}
            onClick={onClose}
            className="w-10 h-10 shrink-0 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-surface-container disabled:opacity-60"
          >
            <span aria-hidden="true" className="material-symbols-outlined text-[22px]">close</span>
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="bg-surface-container-low rounded-lg p-2">
            <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('pb_dlg_restock_total')}</span>
            <span className="font-stat-numeric text-label-lg font-bold" dir="ltr">{fmt(row.total_amount)} {currency}</span>
          </div>
          <div className="bg-surface-container-low rounded-lg p-2">
            <span className="font-label-sm text-label-sm text-on-surface-variant block">{t('pb_remaining')}</span>
            <span className="font-stat-numeric text-label-lg font-bold text-tertiary" dir="ltr">{fmt(remaining)} {currency}</span>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="payment-amount" className="font-label-md text-label-md text-on-surface">
            {t('pb_dlg_amount')}
          </label>
          <div className={`flex items-center gap-2 bg-surface-container-low rounded-lg p-2.5 ${amountError ? 'ring-2 ring-error' : ''}`}>
            <input
              id="payment-amount"
              ref={inputRef}
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              dir="ltr"
              value={amountText}
              disabled={isSaving}
              onChange={(e) => setAmountText(e.target.value)}
              aria-invalid={amountError !== null}
              aria-describedby={amountError ? 'payment-amount-error' : undefined}
              className="w-full bg-transparent font-stat-numeric text-headline-sm text-on-surface focus:outline-none"
            />
            <span className="font-label-md text-label-md text-on-surface-variant shrink-0">{currency}</span>
          </div>
          {amountError && (
            <p id="payment-amount-error" role="alert" className="flex items-center gap-1 pt-0.5 font-body-sm text-body-sm text-error">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">error</span>
              {amountError}
            </p>
          )}
        </div>

        <fieldset className="flex flex-col gap-1">
          <legend className="font-label-md text-label-md text-on-surface mb-1">{t('pb_dlg_method')}</legend>
          <div className="grid grid-cols-2 gap-2">
            {(['cash', 'card'] as const).map((id) => (
              <button
                key={id}
                type="button"
                aria-pressed={method === id}
                disabled={isSaving}
                onClick={() => setMethod(id)}
                className={`inline-flex min-h-[48px] items-center justify-center gap-1.5 rounded-lg font-label-lg text-label-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60 ${
                  method === id ? 'bg-primary text-on-primary shadow-sm' : 'bg-surface-container text-on-surface-variant'
                }`}
              >
                <span aria-hidden="true" className="material-symbols-outlined text-[20px]">{METHOD_ICONS[id]}</span>
                {methodLabels[id]}
              </button>
            ))}
          </div>
        </fieldset>

        <p className="font-body-sm text-body-sm text-on-surface-variant">
          {t('pb_dlg_signed_in')}
        </p>

        {submitError && (
          <div role="alert" className="flex items-start gap-2 rounded-lg bg-error-container p-2.5 text-on-error-container">
            <span aria-hidden="true" className="material-symbols-outlined text-error text-[20px] shrink-0">error</span>
            <span className="font-body-sm text-body-sm break-words">{submitError}</span>
          </div>
        )}

        <div className="flex flex-col gap-2 sm:flex-row-reverse sm:justify-start">
          <button
            type="button"
            onClick={submit}
            disabled={amountError !== null || isSaving}
            className="w-full sm:w-auto sm:px-8 min-h-[52px] rounded-lg bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-2 active:scale-[0.98] transition-transform shadow-md disabled:opacity-60"
          >
            <span aria-hidden="true" className={`material-symbols-outlined text-[22px] ${isSaving ? 'animate-spin' : ''}`}>
              {isSaving ? 'progress_activity' : 'check'}
            </span>
            {isSaving ? t('pb_dlg_saving') : t('pb_dlg_confirm')}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={isSaving}
            className="w-full sm:w-auto sm:px-6 min-h-[44px] rounded-lg text-on-surface-variant hover:text-on-surface font-label-md text-label-md flex items-center justify-center disabled:opacity-60"
          >
            {t('cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}