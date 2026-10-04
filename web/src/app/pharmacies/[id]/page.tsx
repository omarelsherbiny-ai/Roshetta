// web/src/app/pharmacies/[id]/page.tsx (route: /pharmacies/[id] — pharmacy details; rebuilt in Session 106, functional, not a Stitch design)
'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { getPharmacySummary, selectMyPharmacy, getPersonalAccount } from '@/lib/api';
import { isAuthenticated, parseToken, saveAuth } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import type { PharmacySummaryResponse } from '@/types';

export default function PharmacyDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const { t, lang, dir } = useLanguage();

  const rawId = String(params.id ?? '');
  const pharmacyId = /^\d+$/.test(rawId) ? Number(rawId) : null;

  const [summary, setSummary] = useState<PharmacySummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(pharmacyId !== null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isEntering, setIsEntering] = useState(false);
  const [enterError, setEnterError] = useState<string | null>(null);

  const load = async () => {
    if (pharmacyId === null) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      setSummary(await getPharmacySummary(pharmacyId));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('pd_could_not_load'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    void load();
  }, []);

  // The server issues a pharmacy-scoped token; the same hand-over the hub page uses.
  const enter = async () => {
    if (pharmacyId === null || isEntering) return;
    setIsEntering(true);
    setEnterError(null);
    try {
      const res = await selectMyPharmacy(pharmacyId);
      const userRaw = sessionStorage.getItem('roshetta_user');
      const currentUser = userRaw ? JSON.parse(userRaw) : await getPersonalAccount();
      saveAuth({ token: res.token, user: currentUser, role: res.role, pharmacy: res.pharmacy });
      router.push('/');
    } catch (error) {
      setEnterError(error instanceof Error ? error.message : t('ph_could_not_open_pharmacy'));
      setIsEntering(false);
    }
  };

  const isOpenNow = pharmacyId !== null && parseToken()?.pharmacyId === pharmacyId;
  const hiddenFigure = '—';
  const money = (value: number, currency: string) =>
    new Intl.NumberFormat(lang === 'ar' ? 'ar-EG' : 'en-US', { style: 'currency', currency: currency || 'EGP' }).format(value);
  const limited = !!summary && (summary.product_count === null || summary.today_revenue === null);

  const figures = summary
    ? [
        { label: t('pd_team_members'), value: String(summary.member_count) },
        { label: t('pd_products'), value: summary.product_count === null ? hiddenFigure : String(summary.product_count) },
        { label: t('pd_today_revenue'), value: summary.today_revenue === null ? hiddenFigure : money(summary.today_revenue, summary.currency) },
      ]
    : [];

  return (
    <div className="bg-surface font-body-md text-on-surface antialiased flex flex-col min-h-screen">
      <TopHeader pharmacyName={summary?.pharmacy_name ?? t('my_pharmacies')} subtitle={t('pd_subtitle')} showBack={true} />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-12 bg-surface">
        <div className="flex flex-col w-full max-w-2xl mx-auto px-margin-mobile pt-space-md gap-space-md" dir={dir}>
          {pharmacyId === null && (
            <p role="alert" className="rounded-xl bg-error-container p-3 text-sm text-on-error-container">{t('pd_invalid_id')}</p>
          )}

          {isLoading && (
            <p className="rounded-xl bg-surface-container-lowest p-space-md text-on-surface-variant shadow-sm">{t('loading')}</p>
          )}

          {loadError && (
            <div role="alert" className="flex flex-col gap-2 rounded-xl bg-error-container p-3 text-sm text-on-error-container">
              <span>{loadError}</span>
              <button type="button" onClick={() => void load()} className="self-start min-h-10 rounded-lg px-3 font-semibold underline">
                {t('retry')}
              </button>
            </div>
          )}

          {summary && (
            <>
              <div className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-1">
                <div className="flex items-start justify-between gap-2">
                  <span className="min-w-0 font-headline-sm text-headline-sm text-on-surface break-words">{summary.pharmacy_name}</span>
                  {isOpenNow && (
                    <span className="shrink-0 font-label-sm text-label-sm text-primary">{t('ph_open_now')}</span>
                  )}
                </div>
                {summary.address && (
                  <span className="font-body-sm text-body-sm text-on-surface-variant">{summary.address}</span>
                )}
              </div>

              <section aria-labelledby="pharmacy-figures-heading" className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-3">
                <h2 id="pharmacy-figures-heading" className="font-label-lg text-label-lg text-on-surface">{t('pd_figures')}</h2>
                <div className="grid grid-cols-1 gap-gutter-mobile sm:grid-cols-3">
                  {figures.map((figure) => (
                    <div key={figure.label} className="rounded-xl bg-surface-container-low p-3 flex flex-col gap-1">
                      <span className="font-label-sm text-label-sm text-on-surface-variant">{figure.label}</span>
                      <span className="font-stat-numeric text-stat-numeric text-on-surface break-words">{figure.value}</span>
                    </div>
                  ))}
                </div>
                {limited && (
                  <p className="rounded-lg bg-surface-container-low p-2 text-sm text-on-surface-variant">{t('pd_limited_view')}</p>
                )}
              </section>

              {enterError && (
                <p role="alert" className="rounded-xl bg-error-container p-3 text-sm text-on-error-container">{enterError}</p>
              )}

              <button
                type="button"
                onClick={() => void enter()}
                disabled={isEntering}
                className="h-12 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg disabled:opacity-60"
              >
                {t('ph_enter')}
              </button>
            </>
          )}
        </div>
      </main>
    </div>
  );
}