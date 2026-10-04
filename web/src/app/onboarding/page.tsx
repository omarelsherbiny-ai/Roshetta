// web/src/app/onboarding/page.tsx (route: /onboarding — personal account sign in and registration)
'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useLanguage } from '@/lib/i18n';
import { registerPersonalAccount, loginPersonalAccount } from '@/lib/api';
import { saveAccountAuth } from '@/lib/auth';
import { capturePendingInvite } from '@/lib/pendingInvite';
import { getLanguage, nextLanguageCode } from '@/lib/languages';

export default function OnboardingPage() {
  const router = useRouter();
  const { t, lang, dir, toggleLanguage } = useLanguage();
  const [mode, setMode] = useState<'register' | 'login'>('register');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // The invitation token comes from the link's #fragment (or the old ?invite= form) and is
  // kept in sessionStorage until it is accepted or refused (see lib/pendingInvite.ts).
  useEffect(() => {
    capturePendingInvite();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');

    if (!/^\d{4,6}$/.test(pin)) {
      setError(t('ob_pin_must_contain_4_6'));
      return;
    }

    if (mode === 'register') {
      if (!name.trim()) {
        setError(t('ob_enter_your_name'));
        return;
      }

      if (pin !== confirmPin) {
        setError(t('ob_pin_entries_do_not_match'));
        return;
      }
    }

    if (!phone.trim()) {
      setError(t('ob_enter_your_phone_number'));
      return;
    }

    setLoading(true);

    try {
      const result =
        mode === 'register'
          ? await registerPersonalAccount({
              name: name.trim(),
              phone: phone.trim(),
              pin,
              // The server accepts only 'ar' or 'en'; any other registry language falls back to English.
              language_pref: lang === 'ar' ? 'ar' : 'en',
            })
          : await loginPersonalAccount(phone.trim(), pin);

      saveAccountAuth(result);

      // /pharmacies reads the pending invitation from sessionStorage and accepts it.
      router.replace('/pharmacies');
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : t('ob_request_failed'),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      dir={dir}
      className="min-h-screen bg-background px-4 py-6 text-on-surface"
    >
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-lg flex-col justify-center">
        <div className="mb-5 flex justify-end">
          <button
            type="button"
            onClick={toggleLanguage}
            className="rounded-full bg-surface-container px-4 py-2 text-sm font-semibold text-primary"
          >
            {getLanguage(nextLanguageCode(lang)).name}
          </button>
        </div>

        <section className="rounded-3xl border border-outline-variant/40 bg-surface-container-lowest p-5 shadow-sm sm:p-8">
          <header className="mb-6 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary text-on-primary shadow-sm">
              <span className="material-symbols-outlined text-4xl">
                local_pharmacy
              </span>
            </div>

            <p className="mb-2 inline-flex rounded-full bg-primary-fixed/40 px-3 py-1 text-xs font-semibold text-primary">
              {t('ob_personal_account')}
            </p>

            <h1 className="text-2xl font-extrabold tracking-tight">
              {mode === 'register'
                ? t('ob_create_personal_account')
                : t('ob_sign_in')}
            </h1>

            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              {t('ob_intro')}
            </p>
          </header>

          <div className="mb-5 grid grid-cols-2 rounded-xl bg-surface-container p-1">
            <button
              type="button"
              onClick={() => {
                setMode('register');
                setError('');
              }}
              className={`rounded-lg px-3 py-3 text-sm font-bold ${
                mode === 'register'
                  ? 'bg-surface-container-lowest text-primary shadow-sm'
                  : 'text-on-surface-variant'
              }`}
            >
              {t('ob_create_account')}
            </button>

            <button
              type="button"
              onClick={() => {
                setMode('login');
                setError('');
              }}
              className={`rounded-lg px-3 py-3 text-sm font-bold ${
                mode === 'login'
                  ? 'bg-surface-container-lowest text-primary shadow-sm'
                  : 'text-on-surface-variant'
              }`}
            >
              {t('ob_tab_have_account')}
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === 'register' && (
              <label className="block space-y-1.5">
                <span className="text-sm font-semibold">
                  {t('ob_name')}
                </span>

                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  autoComplete="name"
                  maxLength={100}
                  required
                  className="h-12 w-full rounded-xl border border-outline-variant/50 bg-surface-container-low px-4 outline-none focus:border-primary"
                />
              </label>
            )}

            <label className="block space-y-1.5">
              <span className="text-sm font-semibold">
                {t('ob_phone_number')}
              </span>

              <input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                type="tel"
                autoComplete="tel"
                dir="ltr"
                maxLength={20}
                required
                className="h-12 w-full rounded-xl border border-outline-variant/50 bg-surface-container-low px-4 text-left outline-none focus:border-primary"
              />
            </label>

            <label className="block space-y-1.5">
              <span className="text-sm font-semibold">
                {t('ob_pin')}
              </span>

              <input
                value={pin}
                onChange={(event) =>
                  setPin(
                    event.target.value.replace(/\D/g, '').slice(0, 6),
                  )
                }
                type="password"
                inputMode="numeric"
                autoComplete={
                  mode === 'login'
                    ? 'current-password'
                    : 'new-password'
                }
                minLength={4}
                maxLength={6}
                required
                dir="ltr"
                className="h-12 w-full rounded-xl border border-outline-variant/50 bg-surface-container-low px-4 text-left tracking-[0.4em] outline-none focus:border-primary"
              />

              <span className="block text-xs text-on-surface-variant">
                {t('ob_pin_hint')}
              </span>
            </label>

            {mode === 'register' && (
              <label className="block space-y-1.5">
                <span className="text-sm font-semibold">
                  {t('ob_confirm_pin')}
                </span>

                <input
                  value={confirmPin}
                  onChange={(event) =>
                    setConfirmPin(
                      event.target.value
                        .replace(/\D/g, '')
                        .slice(0, 6),
                    )
                  }
                  type="password"
                  inputMode="numeric"
                  autoComplete="new-password"
                  minLength={4}
                  maxLength={6}
                  required
                  dir="ltr"
                  className="h-12 w-full rounded-xl border border-outline-variant/50 bg-surface-container-low px-4 text-left tracking-[0.4em] outline-none focus:border-primary"
                />
              </label>
            )}

            <p className="rounded-xl border border-outline-variant/40 bg-surface-container-low p-3 text-sm leading-6 text-on-surface-variant">
              {t('ob_pharmacy_details_not_needed_here')}
            </p>

            {error && (
              <p
                role="alert"
                className="rounded-xl bg-error-container p-3 text-sm text-on-error-container"
              >
                {error}
              </p>
            )}

            <button
              disabled={loading}
              type="submit"
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 font-bold text-on-primary shadow-sm disabled:cursor-wait disabled:opacity-60"
            >
              {loading
                ? t('ob_submitting')
                : mode === 'register'
                  ? t('ob_create_account_continue')
                  : t('ob_sign_continue')}

              {!loading && (
                <span className="material-symbols-outlined rtl:-scale-x-100" aria-hidden="true">
                  arrow_forward
                </span>
              )}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}