// web/src/app/settings/pharmacy/page.tsx (route: /settings/pharmacy — pharmacy details and defaults; editable with edit_settings, read-only otherwise)
'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { SettingsTabs } from '@/components/ui/SettingsTabs';
import { InlineBanner } from '@/components/ui/InlineBanner';
import { getPharmacyProfile, getPharmacySummary, updatePharmacyProfile } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import type { PharmacyProfile, PharmacyProfileUpdate } from '@/types';

const LIMITS = { name: 150, owner: 100, phone: 20, address: 255, license: 50, tax: 50 } as const;
const PHONE_MIN = 7;

const cardClass = 'flex flex-col gap-space-md rounded-xl bg-surface-container-lowest p-space-lg shadow-sm';
const labelClass = 'font-label-lg text-label-lg text-on-surface';
const hintClass = 'font-body-sm text-body-sm text-on-surface-variant';
const inputClass =
  'h-touch-target-min w-full rounded-lg bg-surface-container-low px-space-md font-body-md text-body-md text-on-surface outline-none placeholder:text-on-surface-variant/60 focus-visible:ring-2 focus-visible:ring-primary';
const segBase =
  'flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg px-3 font-label-md text-label-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

type Banner = { kind: 'success' | 'error'; message: string; retry?: () => void } | null;
type Numerals = 'western' | 'eastern';
type PharmacyLanguage = 'ar' | 'en';
type FieldErrors = { name?: string; phone?: string; threshold?: string };

export default function PharmacySettingsPage() {
  const router = useRouter();
  const { t, dir, languages } = useLanguage();

  const [profile, setProfile] = useState<PharmacyProfile | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [banner, setBanner] = useState<Banner>(null);
  const [errors, setErrors] = useState<FieldErrors>({});

  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [license, setLicense] = useState('');
  const [tax, setTax] = useState('');
  const [numerals, setNumerals] = useState<Numerals>('western');
  const [threshold, setThreshold] = useState('');
  const [pharmacyLang, setPharmacyLang] = useState<PharmacyLanguage>('ar');

  const fillForm = (p: PharmacyProfile) => {
    setName(p.pharmacy_name || '');
    setOwner(p.owner_name || '');
    setPhone(p.phone || '');
    setAddress(p.address || '');
    setLicense(p.license_number || '');
    setTax(p.tax_id || '');
    setNumerals(p.numerals_format === 'eastern' ? 'eastern' : 'western');
    setThreshold(p.low_stock_default != null ? String(p.low_stock_default) : '');
    setPharmacyLang(p.language === 'en' ? 'en' : 'ar');
  };

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const p = await getPharmacyProfile();
      setProfile(p);
      fillForm(p);
      setIsOwner(sessionStorage.getItem('roshetta_role') === 'owner');
      // Whether this member may edit comes from the server's own permission list; if it cannot be read the page stays read-only.
      try {
        const summary = await getPharmacySummary(p.id);
        setCanEdit(summary.permissions.includes('edit_settings'));
      } catch {
        setCanEdit(false);
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('st_load_error'));
    } finally {
      setIsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    void load();
  }, [load, router]);

  const handleSave = async () => {
    const next: FieldErrors = {};
    if (!name.trim()) next.name = t('ph_please_enter_pharmacy_name');
    const phoneValue = phone.trim();
    if (phoneValue && (phoneValue.length < PHONE_MIN || phoneValue.length > LIMITS.phone)) {
      next.phone = t('se_phone_invalid');
    }
    const thresholdNumber = Number(threshold);
    if (!/^\d+$/.test(threshold.trim()) || !Number.isInteger(thresholdNumber) || thresholdNumber < 1) {
      next.threshold = t('se_threshold_invalid');
    }
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    const payload: PharmacyProfileUpdate = {
      pharmacy_name: name.trim(),
      owner_name: owner.trim() || undefined,
      phone: phoneValue || undefined,
      address: address.trim(),
      license_number: license.trim(),
      tax_id: tax.trim(),
      currency: 'EGP',
      numerals_format: numerals,
      low_stock_default: thresholdNumber,
      language: pharmacyLang,
    };

    setIsSaving(true);
    setBanner(null);
    try {
      const res = await updatePharmacyProfile(payload);
      setProfile(res.profile);
      fillForm(res.profile);
      setBanner({ kind: 'success', message: t('st_saved') });
    } catch (error) {
      setBanner({
        kind: 'error',
        message: error instanceof Error ? error.message : t('st_save_failed'),
        retry: () => void handleSave(),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const counter = (value: string, max: number) => (
    <span className={hintClass} aria-hidden="true">{value.length} / {max}</span>
  );

  const ownLanguages = languages.filter((l) => l.code === 'ar' || l.code === 'en');
  const numeralsLabel = (value: string | undefined) =>
    value === 'eastern' ? t('lm_numerals_eastern') : t('lm_numerals_western');
  const languageName = (code: string | undefined) => languages.find((l) => l.code === code)?.name ?? '';

  return (
    <div className="flex min-h-screen flex-col bg-surface text-on-surface">
      <TopHeader
        pharmacyName={profile?.pharmacy_name || t('se_pharmacy')}
        subtitle={t('se_pharmacy_subtitle')}
        showBack={true}
      />

      <main className="relative flex w-full flex-1 flex-col bg-surface pb-28 pt-16">
        <div className="mx-auto flex w-full max-w-[960px] flex-col gap-space-md px-margin-mobile pb-6 pt-3" dir={dir}>
          <SettingsTabs />

          {banner && (
            <InlineBanner
              kind={banner.kind}
              message={banner.message}
              dismissLabel={t('rs_dismiss')}
              onDismiss={() => setBanner(null)}
              retryLabel={t('retry')}
              onRetry={banner.retry}
            />
          )}

          {loadError && (
            <InlineBanner
              kind="error"
              message={loadError}
              dismissLabel={t('rs_dismiss')}
              onDismiss={() => setLoadError(null)}
              retryLabel={t('retry')}
              onRetry={() => void load()}
            />
          )}

          {isLoading ? (
            <div className="flex animate-pulse flex-col gap-space-md" aria-busy="true" aria-label={t('st_loading')}>
              <div className="h-48 rounded-xl bg-surface-container-high" />
              <div className="h-40 rounded-xl bg-surface-container-high" />
              <div className="h-56 rounded-xl bg-surface-container-high" />
            </div>
          ) : profile && canEdit ? (
            <form
              className="flex flex-col gap-space-md"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void handleSave();
              }}
            >
              {/* Identity */}
              <section className={cardClass}>
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">store</span>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('se_identity')}</h2>
                </div>
                <div className="grid grid-cols-1 gap-space-md md:grid-cols-2">
                  <div className="flex flex-col gap-space-xs md:col-span-2">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-name">
                        {t('st_pharmacy_name')} <span className="text-error" aria-hidden="true">*</span>
                      </label>
                      {counter(name, LIMITS.name)}
                    </div>
                    <input
                      id="ph-name"
                      type="text"
                      value={name}
                      maxLength={LIMITS.name}
                      required
                      aria-required="true"
                      aria-invalid={errors.name ? true : undefined}
                      aria-describedby={errors.name ? 'ph-name-error' : undefined}
                      onChange={(e) => setName(e.target.value)}
                      className={`${inputClass} ${errors.name ? 'ring-2 ring-error' : ''}`}
                    />
                    {errors.name && <p id="ph-name-error" className="font-body-sm text-body-sm text-error">{errors.name}</p>}
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-owner">{t('st_owner_name')}</label>
                      {counter(owner, LIMITS.owner)}
                    </div>
                    <input id="ph-owner" type="text" value={owner} maxLength={LIMITS.owner} onChange={(e) => setOwner(e.target.value)} className={inputClass} />
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-license">{t('st_license')}</label>
                      {counter(license, LIMITS.license)}
                    </div>
                    <input id="ph-license" type="text" dir="ltr" value={license} maxLength={LIMITS.license} onChange={(e) => setLicense(e.target.value)} className={`${inputClass} text-start`} />
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-tax">{t('lm_f_tax')}</label>
                      {counter(tax, LIMITS.tax)}
                    </div>
                    <input id="ph-tax" type="text" dir="ltr" value={tax} maxLength={LIMITS.tax} onChange={(e) => setTax(e.target.value)} className={`${inputClass} text-start`} />
                  </div>
                </div>
              </section>

              {/* Contact */}
              <section className={cardClass}>
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">location_on</span>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('se_contact')}</h2>
                </div>
                <div className="grid grid-cols-1 gap-space-md md:grid-cols-3">
                  <div className="flex flex-col gap-space-xs md:col-span-1">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-phone">{t('se_phone_pharmacy')}</label>
                      {counter(phone, LIMITS.phone)}
                    </div>
                    <input
                      id="ph-phone"
                      type="tel"
                      dir="ltr"
                      value={phone}
                      maxLength={LIMITS.phone}
                      aria-invalid={errors.phone ? true : undefined}
                      aria-describedby={errors.phone ? 'ph-phone-error' : undefined}
                      onChange={(e) => setPhone(e.target.value)}
                      className={`${inputClass} text-start ${errors.phone ? 'ring-2 ring-error' : ''}`}
                    />
                    {errors.phone && <p id="ph-phone-error" className="font-body-sm text-body-sm text-error">{errors.phone}</p>}
                  </div>

                  <div className="flex flex-col gap-space-xs md:col-span-2">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-address">{t('lm_f_address')}</label>
                      {counter(address, LIMITS.address)}
                    </div>
                    <textarea
                      id="ph-address"
                      rows={2}
                      value={address}
                      maxLength={LIMITS.address}
                      onChange={(e) => setAddress(e.target.value)}
                      className="w-full resize-none rounded-lg bg-surface-container-low px-space-md py-space-sm font-body-md text-body-md text-on-surface outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    />
                  </div>
                </div>
              </section>

              {/* Operating defaults */}
              <section className={cardClass}>
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">tune</span>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('se_operations')}</h2>
                </div>
                <div className="grid grid-cols-1 gap-space-md md:grid-cols-2">
                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="ph-currency">{t('se_currency')}</label>
                      <span className="inline-flex items-center gap-1 rounded-full bg-surface-container-high px-2 py-0.5 font-label-sm text-label-sm text-on-surface-variant">
                        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">lock</span>
                        {t('se_read_only')}
                      </span>
                    </div>
                    <input
                      id="ph-currency"
                      type="text"
                      readOnly
                      value={t('se_currency_value')}
                      aria-describedby="ph-currency-hint"
                      className="h-touch-target-min w-full cursor-not-allowed rounded-lg bg-surface-container px-space-md font-body-md text-body-md text-on-surface-variant outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    />
                    <p id="ph-currency-hint" className={hintClass}>{t('se_currency_note')}</p>
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <label className={labelClass} htmlFor="ph-threshold">
                      {t('se_threshold')} <span className="text-error" aria-hidden="true">*</span>
                    </label>
                    <input
                      id="ph-threshold"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      step={1}
                      value={threshold}
                      required
                      aria-required="true"
                      aria-invalid={errors.threshold ? true : undefined}
                      aria-describedby={errors.threshold ? 'ph-threshold-error' : undefined}
                      onChange={(e) => setThreshold(e.target.value)}
                      className={`${inputClass} ${errors.threshold ? 'ring-2 ring-error' : ''}`}
                    />
                    {errors.threshold && <p id="ph-threshold-error" className="font-body-sm text-body-sm text-error">{errors.threshold}</p>}
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <span className={labelClass} id="ph-numerals-label">{t('lm_numerals')}</span>
                    <div role="group" aria-labelledby="ph-numerals-label" className="flex gap-1 rounded-xl bg-surface-container-low p-1">
                      {(['western', 'eastern'] as const).map((value) => {
                        const active = numerals === value;
                        return (
                          <button
                            key={value}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setNumerals(value)}
                            className={`${segBase} ${active ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
                          >
                            {numeralsLabel(value)}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <span className={labelClass} id="ph-language-label">{t('se_pharmacy_language')}</span>
                    <div role="group" aria-labelledby="ph-language-label" className="flex gap-1 rounded-xl bg-surface-container-low p-1">
                      {ownLanguages.map((language) => {
                        const active = pharmacyLang === language.code;
                        return (
                          <button
                            key={language.code}
                            type="button"
                            lang={language.code}
                            aria-pressed={active}
                            onClick={() => setPharmacyLang(language.code as PharmacyLanguage)}
                            className={`${segBase} ${active ? 'bg-primary text-on-primary shadow-sm' : 'text-on-surface-variant hover:text-on-surface'}`}
                          >
                            {language.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </section>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={isSaving}
                  className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 font-label-lg text-label-lg text-on-primary shadow-sm transition hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-60 sm:w-auto"
                >
                  <span className="material-symbols-outlined text-[20px]" aria-hidden="true">{isSaving ? 'sync' : 'save'}</span>
                  <span>{isSaving ? t('cat_saving') : t('st_save_changes')}</span>
                </button>
              </div>
            </form>
          ) : profile ? (
            <>
              <div role="note" className="flex items-start gap-space-sm rounded-xl bg-surface-container-high p-space-md text-on-surface">
                <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">lock</span>
                <div className="flex flex-col gap-space-xs">
                  <h2 className="font-label-lg text-label-lg">{t('se_view_only')}</h2>
                  <p className={hintClass}>{t('se_view_only_note')}</p>
                </div>
              </div>
              <section className={cardClass}>
                <dl className="grid grid-cols-1 gap-space-md md:grid-cols-2">
                  <div className="flex flex-col gap-space-xs md:col-span-2">
                    <dt className={hintClass}>{t('st_pharmacy_name')}</dt>
                    <dd className="rounded-lg bg-surface-container-low p-space-md font-headline-sm text-headline-sm text-on-surface">{profile.pharmacy_name}</dd>
                  </div>
                  <div className="flex flex-col gap-space-xs">
                    <dt className={hintClass}>{t('se_currency')}</dt>
                    <dd className="rounded-lg bg-surface-container-low p-space-md font-label-lg text-label-lg text-on-surface">{t('se_currency_value')}</dd>
                  </div>
                  <div className="flex flex-col gap-space-xs">
                    <dt className={hintClass}>{t('lm_numerals')}</dt>
                    <dd className="rounded-lg bg-surface-container-low p-space-md font-label-lg text-label-lg text-on-surface">{numeralsLabel(profile.numerals_format)}</dd>
                  </div>
                  <div className="flex flex-col gap-space-xs">
                    <dt className={hintClass}>{t('se_threshold')}</dt>
                    <dd className="rounded-lg bg-surface-container-low p-space-md font-label-lg text-label-lg text-on-surface">
                      {profile.low_stock_default != null ? profile.low_stock_default : t('inv_none_value')}
                    </dd>
                  </div>
                  <div className="flex flex-col gap-space-xs">
                    <dt className={hintClass}>{t('se_pharmacy_language')}</dt>
                    <dd className="rounded-lg bg-surface-container-low p-space-md font-label-lg text-label-lg text-on-surface">{languageName(profile.language)}</dd>
                  </div>
                </dl>
              </section>
            </>
          ) : null}

          {!isLoading && profile && isOwner && (
            <Link
              href={`/pharmacies/${profile.id}/members`}
              className="flex min-h-[48px] items-center justify-between rounded-xl bg-primary-container p-4 text-on-primary-container shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              <span className="flex items-center gap-2 font-semibold">
                <span className="material-symbols-outlined" aria-hidden="true">group</span>
                {t('st_manage_staff')}
              </span>
              <span className="material-symbols-outlined rtl:-scale-x-100" aria-hidden="true">arrow_forward</span>
            </Link>
          )}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}
