// web/src/app/prescriptions/page.tsx (route: /prescriptions — saved prescription review list and safety alerts)
'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { BottomNav } from '@/components/ui/BottomNav';
import { TopHeader } from '@/components/ui/TopHeader';
import { getPharmacyProfile, getPrescriptionsList, reviewPrescription } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { pickLocalizedName } from '@/lib/languages';
import { formatDateTime } from '@/lib/utils';
import { PharmacyProfile, PrescriptionRecord } from '@/types';

type Filter = 'all' | 'alerts' | 'needs_review' | 'reviewed';

export default function PrescriptionsPage() {
  const { lang, dir, t } = useLanguage();
  const [records, setRecords] = useState<PrescriptionRecord[]>([]);
  const [pharmacy, setPharmacy] = useState<PharmacyProfile | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [list, profile] = await Promise.all([
        getPrescriptionsList(),
        getPharmacyProfile().catch(() => null),
      ]);
      setRecords(list);
      setPharmacy(profile);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('rx_load_error'));
    } finally {
      setLoading(false);
    }
  }, [t('rx_load_error')]);

  useEffect(() => { void loadData(); }, [loadData]);

  const countAlerts = (record: PrescriptionRecord) =>
    (record.extracted?.safety_alerts?.length ?? 0) > 0 || record.safety_status === 'critical_alert';

  const filteredRecords = useMemo(() => records.filter((record) => {
    const hasAlerts = countAlerts(record);
    if (filter === 'alerts' && !hasAlerts) return false;
    if (filter === 'needs_review' && record.review_decision) return false;
    if (filter === 'reviewed' && !record.review_decision) return false;
    const query = search.trim().toLocaleLowerCase();
    if (!query) return true;
    const medicineText = (record.extracted?.medicines ?? []).map((medicine) => medicine.name).join(' ');
    return [record.patient_name, record.doctor_name, medicineText]
      .some((value) => value?.toLocaleLowerCase().includes(query));
  }), [records, filter, search]);

  const handleReview = async (record: PrescriptionRecord) => {
    const hasAlerts = countAlerts(record);
    const decision = hasAlerts ? 'held' : 'reviewed';
    setReviewingId(record.id);
    setActionMessage(null);
    try {
      const result = await reviewPrescription(record.id, decision);
      setRecords((current) => current.map((item) => item.id === record.id
        ? { ...item, review_decision: result.review_decision, reviewed_at: result.reviewed_at }
        : item));
      setActionMessage(t('rx_review_done'));
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : t('rx_load_error'));
    } finally {
      setReviewingId(null);
    }
  };

  const formatDate = (value?: string | null) => {
    if (!value) return t('rx_unknown');
    const formatted = formatDateTime(value, lang);
    return formatted === value ? t('rx_unknown') : formatted;
  };

  const filters: Array<{ id: Filter; label: string }> = [
    { id: 'all', label: t('inv_all') },
    { id: 'alerts', label: t('rx_alerts') },
    { id: 'needs_review', label: t('rx_needs_review') },
    { id: 'reviewed', label: t('rx_reviewed') },
  ];

  return (
    <div className="bg-surface text-on-surface font-body-md text-body-md flex flex-col min-h-screen pb-28" dir={dir}>
      <TopHeader pharmacyName={pharmacy?.pharmacy_name || undefined} subtitle={t('rx_subtitle')} showBack />

      <main className="flex-1 w-full pt-16 bg-surface">
        <div className="w-full max-w-3xl mx-auto px-margin-mobile pt-space-md pb-space-lg flex flex-col gap-space-md">
          <header className="flex flex-col gap-1">
            <h1 className="font-headline-lg text-headline-lg text-on-surface">{t('rx_title')}</h1>
            <p className="font-body-sm text-body-sm text-on-surface-variant">{t('rx_intro')}</p>
          </header>

          <label className="relative block">
            <span className="material-symbols-outlined absolute start-3 top-1/2 -translate-y-1/2 text-outline">search</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('rx_search')}
              className="w-full h-12 ps-11 pe-3 rounded-xl bg-surface-container-lowest border border-outline-variant/40 text-on-surface placeholder:text-outline focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </label>

          <div className="flex gap-2 overflow-x-auto no-scrollbar pb-1" role="tablist" aria-label={t('rx_title')}>
            {filters.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={filter === item.id}
                onClick={() => setFilter(item.id)}
                className={`min-h-10 px-4 rounded-full whitespace-nowrap font-label-sm text-label-sm transition-colors ${filter === item.id ? 'bg-primary text-on-primary font-bold' : 'bg-surface-container text-on-surface-variant'}`}
              >
                {item.label}
                {item.id === 'needs_review' && <span className="ms-1.5">{records.filter((record) => !record.review_decision).length}</span>}
              </button>
            ))}
          </div>

          {actionMessage && (
            <div role="status" className="rounded-lg bg-surface-container px-3 py-2 text-body-sm text-on-surface">
              {actionMessage}
            </div>
          )}

          {loading ? (
            <div className="flex justify-center items-center gap-2 p-8 text-on-surface-variant" role="status">
              <span className="material-symbols-outlined animate-spin text-primary">progress_activity</span>
              <span>{t('rx_loading')}</span>
            </div>
          ) : loadError ? (
            <div className="rounded-xl bg-error-container text-on-error-container p-4 flex flex-col gap-3" role="alert">
              <p>{t('rx_load_error')} {loadError}</p>
              <button onClick={() => void loadData()} className="self-start min-h-10 px-4 rounded-lg bg-error text-on-error font-label-md">{t('retry')}</button>
            </div>
          ) : filteredRecords.length === 0 ? (
            <div className="rounded-xl bg-surface-container-lowest p-8 text-center text-on-surface-variant">
              <span className="material-symbols-outlined text-4xl text-outline">description</span>
              <p className="mt-2">{records.length === 0 ? t('rx_empty') : t('rx_empty_filter')}</p>
              {records.length === 0 && (
                <Link href="/scan" className="inline-flex min-h-11 items-center justify-center mt-4 px-4 rounded-lg bg-primary text-on-primary font-label-md">
                  {t('rx_open_scan')}
                </Link>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-space-md">
              {filteredRecords.map((record) => {
                const hasAlerts = countAlerts(record);
                const medicines = record.extracted?.medicines ?? [];
                return (
                  <article key={record.id} className="rounded-xl bg-surface-container-lowest border border-outline-variant/40 shadow-sm overflow-hidden">
                    <div className={`px-4 py-3 flex items-center justify-between gap-3 ${hasAlerts ? 'bg-tertiary-container text-on-tertiary-container' : 'bg-surface-container-low'}`}>
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="material-symbols-outlined shrink-0">{hasAlerts ? 'warning' : 'description'}</span>
                        <span className="font-label-md text-label-md font-bold truncate">
                          {record.review_decision === 'held' ? t('rx_held_status') : record.review_decision === 'reviewed' ? t('rx_reviewed_status') : hasAlerts ? t('rx_alerts') : t('rx_review_pending')}
                        </span>
                      </div>
                      <span className="font-label-sm text-label-sm shrink-0">#{record.id}</span>
                    </div>

                    <div className="p-space-md flex flex-col gap-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="rounded-lg bg-surface-container-low p-3 min-w-0">
                          <span className="block text-label-sm text-on-surface-variant">{t('rx_patient')}</span>
                          <span className="block font-label-md text-label-md break-words">{record.patient_name || t('rx_unknown')}</span>
                        </div>
                        <div className="rounded-lg bg-surface-container-low p-3 min-w-0">
                          <span className="block text-label-sm text-on-surface-variant">{t('rx_doctor')}</span>
                          <span className="block font-label-md text-label-md break-words">{record.doctor_name || t('rx_unknown')}</span>
                        </div>
                      </div>

                      <div className="text-body-sm text-on-surface-variant">
                        {t('rx_created')}: {formatDate(record.created_at)}
                      </div>

                      {hasAlerts && (
                        <div className="rounded-lg border border-tertiary/40 bg-tertiary-container/40 p-3 flex flex-col gap-2">
                          <h2 className="font-label-md text-label-md font-bold text-on-tertiary-container">{t('rx_alert')}</h2>
                          {(record.extracted?.safety_alerts ?? []).map((alert, index) => (
                            <div key={`${record.id}-alert-${index}`} className="text-body-sm text-on-surface">
                              <span className="font-bold">{alert.severity === 'critical' ? t('rx_critical') : alert.severity === 'warning' ? t('rx_warning') : t('rx_info')}: </span>
                              <span>{pickLocalizedName(lang, alert.description_ar, alert.description_en)}</span>
                            </div>
                          ))}
                          {record.safety_status === 'critical_alert' && !(record.extracted?.safety_alerts?.length) && <p className="text-body-sm">{t('rx_safety_note')}</p>}
                        </div>
                      )}

                      <section className="flex flex-col gap-2">
                        <h2 className="font-label-md text-label-md font-bold">{t('rx_medicines')}</h2>
                        {medicines.length === 0 ? (
                          <p className="text-body-sm text-on-surface-variant">{t('rx_no_medicines')}</p>
                        ) : medicines.map((medicine, index) => (
                          <div key={`${record.id}-medicine-${index}`} className="rounded-lg bg-surface-container-low p-3 min-w-0">
                            <p className="font-label-md text-label-md font-bold break-words">{medicine.name}</p>
                            {medicine.active_ingredient && <p className="text-body-sm text-on-surface-variant break-words">{medicine.active_ingredient}</p>}
                            {(medicine.dosage || medicine.frequency || medicine.duration) && (
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-body-sm text-on-surface-variant">
                                {medicine.dosage && <span>{t('rx_dosage')}: {medicine.dosage}</span>}
                                {medicine.frequency && <span>{t('rx_frequency')}: {medicine.frequency}</span>}
                                {medicine.duration && <span>{t('rx_duration')}: {medicine.duration}</span>}
                              </div>
                            )}
                          </div>
                        ))}
                      </section>

                      {record.review_notes && <p className="text-body-sm text-on-surface-variant break-words">{record.review_notes}</p>}
                      <p className="text-body-sm text-on-surface-variant">{t('rx_review_note')}</p>

                      {!record.review_decision && (
                        <button
                          type="button"
                          disabled={reviewingId === record.id}
                          onClick={() => void handleReview(record)}
                          className="min-h-12 w-full rounded-lg bg-primary text-on-primary font-label-md font-bold disabled:opacity-60"
                        >
                          {reviewingId === record.id ? t('rx_saving') : hasAlerts ? t('rx_hold') : t('rx_mark_reviewed')}
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </main>
      <BottomNav />
    </div>
  );
}