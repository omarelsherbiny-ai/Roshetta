// web/src/app/settings/account/page.tsx (route: /settings/account — personal account settings: profile, photo, language, theme, sign out)
'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { SettingsTabs } from '@/components/ui/SettingsTabs';
import { ChangePinCard } from '@/components/settings/ChangePinCard';
import { InlineBanner } from '@/components/ui/InlineBanner';
import { THEME_ICONS, THEME_KEYS } from '@/components/ui/HeaderControls';
import {
  getPersonalAccount,
  updatePersonalAccount,
  uploadMyPhoto,
  loadMyPhotoObjectUrl,
  logoutSession,
} from '@/lib/api';
import { isAuthenticated, clearAuth } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { useTheme, THEME_CHOICES } from '@/lib/theme';
import type { PersonalUser } from '@/types';

const NAME_MAX = 100;
const LOCATION_MAX = 160;
const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

const cardClass = 'flex flex-col gap-space-md rounded-xl bg-surface-container-lowest p-space-lg shadow-sm';
const labelClass = 'font-label-lg text-label-lg text-on-surface';
const hintClass = 'font-body-sm text-body-sm text-on-surface-variant';
const inputClass =
  'h-touch-target-min w-full rounded-lg bg-surface-container-low px-space-md font-body-md text-body-md text-on-surface outline-none placeholder:text-on-surface-variant/60 focus-visible:ring-2 focus-visible:ring-primary';
const segBase =
  'flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg px-3 font-label-md text-label-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary';

type Banner = { kind: 'success' | 'error'; message: string; retry?: () => void } | null;

/** Today as YYYY-MM-DD in the browser's own time zone (latest allowed birth date). */
function todayString(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function AccountSettingsPage() {
  const router = useRouter();
  const { t, dir, lang, setLanguage, languages } = useLanguage();
  const { theme, setTheme } = useTheme();

  const [user, setUser] = useState<PersonalUser | null>(null);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [fullname, setFullname] = useState('');
  const [location, setLocation] = useState('');
  const [birthdate, setBirthdate] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [banner, setBanner] = useState<Banner>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [birthError, setBirthError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [confirmingSignOut, setConfirmingSignOut] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const loadAccount = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await getPersonalAccount();
      setUser(data);
      setFullname(data.name || '');
      setLocation(data.location || '');
      setBirthdate(data.birth_date || '');
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
    void loadAccount();
  }, [loadAccount, router]);

  // The profile photo is private: it is loaded with the token and shown from an object URL.
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setAvatarSrc(null);
    if (!user?.photo_url) return;
    if (user.photo_url.startsWith('https://')) {
      setAvatarSrc(user.photo_url);
      return;
    }
    void loadMyPhotoObjectUrl(user.photo_url)
      .then((url) => {
        objectUrl = url;
        if (cancelled) URL.revokeObjectURL(url);
        else setAvatarSrc(url);
      })
      .catch(() => {
        if (!cancelled) setAvatarSrc(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [user?.photo_url]);

  const handleSave = async () => {
    const name = fullname.trim();
    const nextNameError = name ? null : t('ob_enter_your_name');
    const nextBirthError = birthdate && birthdate > todayString() ? t('se_birth_future') : null;
    setNameError(nextNameError);
    setBirthError(nextBirthError);
    if (nextNameError || nextBirthError) return;

    setIsSaving(true);
    setBanner(null);
    try {
      const updated = await updatePersonalAccount({
        name,
        location: location.trim(),
        birth_date: birthdate || undefined,
      });
      setUser(updated.user);
      setBanner({ kind: 'success', message: t('me_saved') });
    } catch (error) {
      setBanner({
        kind: 'error',
        message: error instanceof Error ? error.message : t('me_save_failed'),
        retry: () => void handleSave(),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handlePhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.target;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (!PHOTO_TYPES.includes(file.type)) {
      setPhotoError(t('se_photo_type'));
      return;
    }
    if (file.size > PHOTO_MAX_BYTES) {
      setPhotoError(t('se_photo_size'));
      return;
    }
    setPhotoError(null);
    setBanner(null);
    setIsUploading(true);
    try {
      const res = await uploadMyPhoto(file);
      setUser((current) => (current ? { ...current, photo_url: res.photo_url } : current));
      setBanner({ kind: 'success', message: t('me_photo_updated') });
    } catch (error) {
      setBanner({
        kind: 'error',
        message: error instanceof Error ? error.message : t('me_upload_failed'),
      });
    } finally {
      setIsUploading(false);
    }
  };

  const chooseLanguage = (code: string) => {
    if (code === lang) return;
    setLanguage(code);
    // The server stores only Arabic or English as the account language; failing here changes nothing on this device.
    if (code === 'ar' || code === 'en') {
      void updatePersonalAccount({ language_pref: code }).catch(() => undefined);
    }
  };

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await logoutSession();
    } catch {
      /* the local session is cleared either way */
    }
    clearAuth();
    router.replace('/onboarding');
  };

  const maxBirth = todayString();

  return (
    <div className="flex min-h-screen flex-col bg-surface text-on-surface">
      <TopHeader pharmacyName={t('se_account')} subtitle={t('se_account_subtitle')} showBack={true} />

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
              onRetry={() => void loadAccount()}
            />
          )}

          {isLoading ? (
            <div className="flex animate-pulse flex-col gap-space-md" aria-busy="true" aria-label={t('st_loading')}>
              <div className="h-40 rounded-xl bg-surface-container-high" />
              <div className="h-64 rounded-xl bg-surface-container-high" />
              <div className="h-40 rounded-xl bg-surface-container-high" />
            </div>
          ) : user ? (
            <>
              {/* Photo */}
              <section className={`${cardClass} items-center text-center sm:flex-row sm:text-start`}>
                <div className="relative h-24 w-24 shrink-0">
                  <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-full bg-surface-container-high text-primary shadow-sm">
                    {avatarSrc ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={avatarSrc} alt={t('me_photo_alt')} className="h-full w-full object-cover" />
                    ) : (
                      <span className="material-symbols-outlined select-none text-[54px]" aria-hidden="true">person</span>
                    )}
                  </div>
                </div>
                <div className="flex min-w-0 flex-1 flex-col items-center gap-space-xs sm:items-start">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">{user.name}</h2>
                  <label
                    htmlFor="account-photo"
                    className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg bg-surface-container px-4 font-label-md text-label-md text-primary transition-colors hover:bg-surface-container-high focus-within:ring-2 focus-within:ring-primary"
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                      {isUploading ? 'sync' : 'photo_camera'}
                    </span>
                    <span>{isUploading ? t('cat_saving') : t('me_change_photo')}</span>
                    <input
                      id="account-photo"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="sr-only"
                      disabled={isUploading}
                      onChange={handlePhoto}
                      aria-describedby="account-photo-hint"
                    />
                  </label>
                  <p id="account-photo-hint" className={hintClass}>{t('se_photo_hint')}</p>
                  {photoError && (
                    <p role="alert" className="font-body-sm text-body-sm text-error">{photoError}</p>
                  )}
                </div>
              </section>

              {/* Personal details */}
              <form
                className={cardClass}
                noValidate
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleSave();
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">badge</span>
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('se_profile_section')}</h2>
                </div>

                <div className="grid grid-cols-1 gap-space-md md:grid-cols-2">
                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="account-name">
                        {t('me_f_fullname')} <span className="text-error" aria-hidden="true">*</span>
                      </label>
                      <span className={hintClass} aria-hidden="true">{fullname.length} / {NAME_MAX}</span>
                    </div>
                    <input
                      id="account-name"
                      type="text"
                      value={fullname}
                      maxLength={NAME_MAX}
                      required
                      aria-required="true"
                      aria-invalid={nameError ? true : undefined}
                      aria-describedby={nameError ? 'account-name-error' : undefined}
                      onChange={(e) => setFullname(e.target.value)}
                      placeholder={t('me_ph_fullname')}
                      className={`${inputClass} ${nameError ? 'ring-2 ring-error' : ''}`}
                    />
                    {nameError && (
                      <p id="account-name-error" className="font-body-sm text-body-sm text-error">{nameError}</p>
                    )}
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="account-phone">{t('se_phone')}</label>
                      <span className="inline-flex items-center gap-1 rounded-full bg-surface-container-high px-2 py-0.5 font-label-sm text-label-sm text-on-surface-variant">
                        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">lock</span>
                        {t('se_read_only')}
                      </span>
                    </div>
                    <input
                      id="account-phone"
                      type="text"
                      dir="ltr"
                      readOnly
                      value={user.phone}
                      aria-describedby="account-phone-hint"
                      className="h-touch-target-min w-full cursor-not-allowed rounded-lg bg-surface-container px-space-md text-start font-body-md text-body-md text-on-surface-variant outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    />
                    <p id="account-phone-hint" className={hintClass}>{t('se_phone_note')}</p>
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <div className="flex items-center justify-between gap-2">
                      <label className={labelClass} htmlFor="account-location">
                        {t('me_f_location')} <span className={hintClass}>({t('se_optional')})</span>
                      </label>
                      <span className={hintClass} aria-hidden="true">{location.length} / {LOCATION_MAX}</span>
                    </div>
                    <input
                      id="account-location"
                      type="text"
                      value={location}
                      maxLength={LOCATION_MAX}
                      onChange={(e) => setLocation(e.target.value)}
                      placeholder={t('me_ph_location')}
                      className={inputClass}
                    />
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <label className={labelClass} htmlFor="account-birth">
                      {t('me_f_birthdate')} <span className={hintClass}>({t('se_optional')})</span>
                    </label>
                    <input
                      id="account-birth"
                      type="date"
                      value={birthdate}
                      max={maxBirth}
                      aria-invalid={birthError ? true : undefined}
                      aria-describedby={birthError ? 'account-birth-error' : undefined}
                      onChange={(e) => setBirthdate(e.target.value)}
                      className={`${inputClass} ${birthError ? 'ring-2 ring-error' : ''}`}
                    />
                    {birthError && (
                      <p id="account-birth-error" className="font-body-sm text-body-sm text-error">{birthError}</p>
                    )}
                  </div>
                </div>

                <div className="flex justify-end pt-space-xs">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-primary px-6 font-label-lg text-label-lg text-on-primary shadow-sm transition hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-60 sm:w-auto"
                  >
                    <span className="material-symbols-outlined text-[20px]" aria-hidden="true">
                      {isSaving ? 'sync' : 'save'}
                    </span>
                    <span>{isSaving ? t('cat_saving') : t('pf_save_changes')}</span>
                  </button>
                </div>
              </form>

              {/* Change PIN: its own states and toasts live inside the card */}
              <ChangePinCard />

              {/* Preferences: saved on this device the moment they are chosen */}
              <section className={cardClass}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[22px] text-primary" aria-hidden="true">tune</span>
                    <h2 className="font-headline-sm text-headline-sm text-on-surface">{t('se_preferences')}</h2>
                  </div>
                  <span className={hintClass}>{t('se_preferences_note')}</span>
                </div>

                <div className="grid grid-cols-1 gap-space-md md:grid-cols-2">
                  <div className="flex flex-col gap-space-xs">
                    <span className={labelClass} id="account-language-label">{t('me_f_language')}</span>
                    <div
                      role="group"
                      aria-labelledby="account-language-label"
                      className="flex gap-1 rounded-xl bg-surface-container-low p-1"
                    >
                      {languages.map((language) => {
                        const active = language.code === lang;
                        return (
                          <button
                            key={language.code}
                            type="button"
                            lang={language.code}
                            aria-pressed={active}
                            onClick={() => chooseLanguage(language.code)}
                            className={`${segBase} ${
                              active
                                ? 'bg-primary text-on-primary shadow-sm'
                                : 'text-on-surface-variant hover:text-on-surface'
                            }`}
                          >
                            {language.name}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-col gap-space-xs">
                    <span className={labelClass} id="account-theme-label">{t('se_theme')}</span>
                    <div
                      role="group"
                      aria-labelledby="account-theme-label"
                      className="flex gap-1 rounded-xl bg-surface-container-low p-1"
                    >
                      {THEME_CHOICES.map((choice) => {
                        const active = choice === theme;
                        return (
                          <button
                            key={choice}
                            type="button"
                            aria-pressed={active}
                            onClick={() => setTheme(choice)}
                            className={`${segBase} ${
                              active
                                ? 'bg-primary text-on-primary shadow-sm'
                                : 'text-on-surface-variant hover:text-on-surface'
                            }`}
                          >
                            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">
                              {THEME_ICONS[choice]}
                            </span>
                            <span>{t(THEME_KEYS[choice])}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </section>

              {/* Sign out: two steps inside the page */}
              <section className={cardClass}>
                {!confirmingSignOut ? (
                  <button
                    type="button"
                    onClick={() => setConfirmingSignOut(true)}
                    className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-error-container px-6 font-label-lg text-label-lg text-error transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error sm:w-auto sm:self-start"
                  >
                    <span className="material-symbols-outlined text-[20px]" aria-hidden="true">logout</span>
                    <span>{t('me_sign_out')}</span>
                  </button>
                ) : (
                  <div role="alertdialog" aria-labelledby="signout-title" aria-describedby="signout-hint" className="flex flex-col gap-space-md">
                    <div className="flex items-start gap-space-sm">
                      <span className="material-symbols-outlined text-[24px] text-error" aria-hidden="true">warning</span>
                      <div className="flex flex-col gap-space-xs">
                        <h3 id="signout-title" className="font-label-lg text-label-lg text-on-surface">{t('se_signout_title')}</h3>
                        <p id="signout-hint" className={hintClass}>{t('se_signout_hint')}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-space-sm">
                      <button
                        type="button"
                        disabled={signingOut}
                        onClick={() => setConfirmingSignOut(false)}
                        className="min-h-[44px] rounded-lg bg-surface-container px-4 font-label-md text-label-md text-on-surface transition hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        {t('cancel')}
                      </button>
                      <button
                        type="button"
                        disabled={signingOut}
                        onClick={() => void handleSignOut()}
                        className="flex min-h-[44px] items-center gap-2 rounded-lg bg-error px-4 font-label-md text-label-md text-on-error transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-offset-2 disabled:opacity-60"
                      >
                        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">logout</span>
                        <span>{signingOut ? t('se_signout_working') : t('se_signout_yes')}</span>
                      </button>
                    </div>
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </main>

      <BottomNav />
    </div>
  );
}