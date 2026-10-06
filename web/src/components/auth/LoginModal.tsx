// web/src/components/auth/LoginModal.tsx (login modal: sign in, pharmacy choice, first-run profile setup)
'use client';

import React, { useState } from 'react';
import { PharmacyLoginResponse, PharmacyProfile } from '@/types';
import {
  loginPharmacist, updatePharmacyProfile, switchPharmacy
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { getLanguage, nextLanguageCode } from '@/lib/languages';
import {
  Pill, Lock, Phone, Building2, ChevronRight, Users, ArrowLeft,
  ShieldCheck
} from 'lucide-react';

type Step = 'welcome' | 'login' | 'pharmacy' | 'profile';
type NumeralsFormat = 'western' | 'eastern';

interface LoginModalProps {
  isOpen:    boolean;
  onSuccess: (user: PharmacyLoginResponse['user'], pharmacy: PharmacyProfile, token: string, role: string, permissions: string[]) => void;
  /** Kept so existing callers compile; the language now always comes from the useLanguage() hook. */
  language?: string;
}

export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onSuccess }) => {
  const [step,       setStep]       = useState<Step>('welcome');
  const [phone,      setPhone]      = useState('');
  const [pin,        setPin]        = useState('');
  const [name,       setName]       = useState('');
  const [isLoading,  setIsLoading]  = useState(false);
  const [error,      setError]      = useState<string | null>(null);
  const [loginResult,setLoginResult]= useState<PharmacyLoginResponse | null>(null);

  // Profile setup (owner first-run)
  const [pharmacyName,    setPharmacyName]    = useState('');
  const [ownerName,       setOwnerName]       = useState('');
  const [address,         setAddress]         = useState('');
  const [licenseNumber,   setLicenseNumber]   = useState('');
  const [taxId,           setTaxId]           = useState('');
  const [numerals,        setNumerals]        = useState<NumeralsFormat>('western');
  const [lowStock,        setLowStock]        = useState(5);
  const { lang, isRTL, dir, t, setLanguage } = useLanguage();
  const nextLanguage = getLanguage(nextLanguageCode(lang));
  const roleLabels: Record<string, string> = {
    owner: t('lm_role_owner'),
    pharmacist: t('pharmacist'),
    cashier: t('cashier'),
    viewer: t('viewer'),
  };
  const roleLabel = (role: string) => roleLabels[role] ?? role;

  const switchLanguage = () => setLanguage(nextLanguage.code);

  if (!isOpen) return null;

  const reset = () => {
    setError(null); setIsLoading(false);
  };

  // ── Step: Login (owner or staff) ──────────────────────────
  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    reset();
    if (!phone.trim() || !pin.trim()) { setError(t('lm_err_phone_pin')); return; }
    setIsLoading(true);
    try {
      const data = await loginPharmacist(phone.trim(), pin.trim());
      setLoginResult(data);

      if (data.other_pharmacies?.length) {
        setStep('pharmacy');
        return;
      }

      if (!data.pharmacy.is_initialized && data.role === 'owner') {
        // First time — take owner to profile setup
        setOwnerName(data.user.name);
        setPharmacyName(data.pharmacy.pharmacy_name || '');
        setStep('profile');
      } else {
        onSuccess(data.user, data.pharmacy, data.token, data.role, data.permissions);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectPharmacy = async (pharmacyId: number) => {
    if (!loginResult) return;
    setError(null);
    setIsLoading(true);
    try {
      const data = pharmacyId === loginResult.pharmacy.id
        ? loginResult
        : await switchPharmacy(pharmacyId, loginResult.token);
      if (!data.pharmacy.is_initialized && data.role === 'owner') {
        setOwnerName(loginResult.user.name);
        setPharmacyName(data.pharmacy.pharmacy_name || '');
        setLoginResult({ ...loginResult, ...data });
        setStep('profile');
      } else {
        onSuccess(loginResult.user, data.pharmacy, data.token, data.role, data.permissions);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '');
    } finally {
      setIsLoading(false);
    }
  };

  // ── Step: First-run profile setup ─────────────────────────
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    reset();
    if (!pharmacyName || !ownerName) {
      setError(t('lm_err_profile_required'));
      return;
    }
    setIsLoading(true);
    try {
      const updated = await updatePharmacyProfile({
        pharmacy_name: pharmacyName, owner_name: ownerName,
        phone, address, license_number: licenseNumber, tax_id: taxId,
        numerals_format: numerals, low_stock_default: lowStock,
        language: lang as 'ar' | 'en',
      });
      if (loginResult) {
        onSuccess(loginResult.user, updated.profile, loginResult.token, loginResult.role, loginResult.permissions);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '');
    } finally {
      setIsLoading(false);
    }
  };

  // ─────────────────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/85 backdrop-blur-md p-0 sm:p-4">
      <div dir={dir} lang={lang} className="w-full sm:max-w-md bg-surface-container-lowest border border-outline-variant rounded-t-3xl sm:rounded-3xl p-5 sm:p-7 shadow-2xl text-on-surface max-h-[95vh] overflow-y-auto">
        <div className="flex justify-end mb-2">
          <button
            type="button"
            onClick={switchLanguage}
            aria-label={t('switch_language').replace('{name}', nextLanguage.name)}
            className="px-2.5 py-1 rounded-lg bg-surface-container border border-outline-variant text-xs font-semibold text-on-surface-variant hover:text-on-surface transition"
          >
            {nextLanguage.name}
          </button>
        </div>

        {/* ── WELCOME ── */}
        {step === 'welcome' && (
          <div className="flex flex-col items-center text-center gap-5 py-4">
            <div className="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center shadow-lg shadow-primary/30">
              <Pill className="w-8 h-8 text-on-primary" />
            </div>
            <div>
              <h2 className="text-2xl font-bold">{t('lm_app_name')}</h2>
              <p className="text-sm text-on-surface-variant mt-1 max-w-xs">
                {t('lm_tagline')}
              </p>
            </div>
            <div className="w-full space-y-3 mt-2">
              <button
                onClick={() => setStep('login')}
                className="w-full flex items-center justify-between p-4 rounded-2xl bg-primary/10 hover:bg-primary/20 border border-primary/30 transition active:scale-[0.98]"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/20 text-primary flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div className="text-start">
                    <p className="font-semibold text-sm text-on-surface">{t('lm_owner_title')}</p>
                    <p className="text-xs text-on-surface-variant">{t('lm_owner_sub')}</p>
                  </div>
                </div>
                <ChevronRight className={`w-4 h-4 text-on-surface-variant ${isRTL ? 'rotate-180' : ''}`} />
              </button>

              <button
                onClick={() => { window.location.href = '/onboarding'; }}
                className="w-full flex items-center justify-between p-4 rounded-2xl bg-secondary/10 hover:bg-secondary/20 border border-secondary/30 transition active:scale-[0.98]"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-secondary/20 text-secondary flex items-center justify-center">
                    <Users className="w-5 h-5" />
                  </div>
                  <div className="text-start">
                    <p className="font-semibold text-sm text-on-surface">{t('lm_join_title')}</p>
                    <p className="text-xs text-on-surface-variant">{t('lm_join_sub')}</p>
                  </div>
                </div>
                <ChevronRight className={`w-4 h-4 text-on-surface-variant ${isRTL ? 'rotate-180' : ''}`} />
              </button>

              <a
                href="/onboarding"
                className="w-full flex items-center justify-between p-4 rounded-2xl bg-surface-container hover:bg-surface-container-high border border-outline-variant transition active:scale-[0.98]"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-surface-container-high text-on-surface-variant flex items-center justify-center">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <div className="text-start">
                    <p className="font-semibold text-sm text-on-surface">{t('lm_create_title')}</p>
                    <p className="text-xs text-on-surface-variant">{t('lm_create_sub')}</p>
                  </div>
                </div>
                <ChevronRight className={`w-4 h-4 text-on-surface-variant ${isRTL ? 'rotate-180' : ''}`} />
              </a>
            </div>

          </div>
        )}

        {/* ── LOGIN (returning user) ── */}
        {step === 'login' && (
          <div>
            <div className="flex items-center gap-3 mb-5">
              <button onClick={() => setStep('welcome')} className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface-variant">
                <ArrowLeft className="w-4 h-4" />
              </button>
              <h2 className="font-bold text-base">{t('lm_sign_in_title')}</h2>
            </div>

            {error && <div className="mb-4 p-3 rounded-xl bg-error-container border border-error/30 text-on-error-container text-xs">{error}</div>}

            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t('lm_phone')}</label>
                <div className="flex items-center gap-2 bg-surface-container border border-outline-variant focus-within:border-primary rounded-xl px-3 py-2.5">
                  <Phone className="w-4 h-4 text-outline shrink-0" />
                  <input type="tel" required value={phone} onChange={e => setPhone(e.target.value)}
                    placeholder="01012345678" className="w-full bg-transparent text-sm focus:outline-none" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface-variant mb-1">{t('lm_pin')}</label>
                <div className="flex items-center gap-2 bg-surface-container border border-outline-variant focus-within:border-primary rounded-xl px-3 py-2.5">
                  <Lock className="w-4 h-4 text-outline shrink-0" />
                  <input type="password" maxLength={6} required value={pin} onChange={e => setPin(e.target.value)}
                    placeholder="••••" className="w-full bg-transparent text-sm focus:outline-none" />
                </div>
              </div>
              <button type="submit" disabled={isLoading}
                className="w-full py-3 rounded-xl bg-primary text-on-primary font-semibold text-sm shadow-lg disabled:opacity-50 active:scale-[0.98] transition">
                {isLoading ? '...' : t('lm_sign_in_btn')}
              </button>
            </form>
          </div>
        )}

        {step === 'pharmacy' && loginResult && (
          <div>
            <div className="flex items-center gap-3 mb-2">
              <button type="button" onClick={() => setStep('login')} aria-label={t('back')} className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface-variant">
                <ArrowLeft className="w-4 h-4" />
              </button>
              <h2 className="font-bold text-base">{t('lm_choose_pharmacy')}</h2>
            </div>
            <p className="mb-4 text-xs text-on-surface-variant">{t('lm_choose_hint')}</p>
            {error && <div role="alert" className="mb-4 p-3 rounded-xl bg-error-container border border-error/30 text-on-error-container text-xs">{error}</div>}
            <div className="space-y-2">
              {[
                { id: loginResult.pharmacy.id, name: loginResult.pharmacy.pharmacy_name, role: loginResult.role },
                ...loginResult.other_pharmacies,
              ].map((pharmacy: { id: number; name: string; role: string }) => (
                <button
                  key={pharmacy.id}
                  type="button"
                  disabled={isLoading}
                  onClick={() => void handleSelectPharmacy(pharmacy.id)}
                  className="w-full flex items-center justify-between gap-3 p-4 rounded-2xl bg-surface-container border border-outline-variant hover:border-primary/50 transition disabled:opacity-50 text-start"
                >
                  <span className="flex items-center gap-3 min-w-0">
                    <Building2 className="w-5 h-5 text-primary shrink-0" />
                    <span className="min-w-0 flex flex-col">
                      <span className="font-semibold text-sm text-on-surface break-words">{pharmacy.name}</span>
                      <span className="text-xs text-on-surface-variant">{roleLabel(pharmacy.role)}</span>
                    </span>
                  </span>
                  {isLoading ? <span className="text-xs text-on-surface-variant">...</span> : <ChevronRight className={`w-4 h-4 text-on-surface-variant shrink-0 ${isRTL ? 'rotate-180' : ''}`} />}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── PROFILE SETUP (owner first run) ── */}
        {step === 'profile' && (
          <div>
            <div className="text-center mb-5">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-primary/20 text-primary border border-primary/30 flex items-center justify-center mb-2">
                <Building2 className="w-6 h-6" />
              </div>
              <h2 className="font-bold text-lg">{t('lm_setup_title')}</h2>
              <p className="text-xs text-on-surface-variant">{t('lm_setup_hint')}</p>
            </div>

            {error && <div className="mb-4 p-3 rounded-xl bg-error-container border border-error/30 text-on-error-container text-xs">{error}</div>}

            <form onSubmit={handleSaveProfile} className="space-y-3">
              {[
                { label: t('lm_f_pharmacy_name'),     value: pharmacyName,  onChange: setPharmacyName,  req: true },
                { label: t('lm_f_owner_name'), value: ownerName, onChange: setOwnerName, req: true },
                { label: t('lm_f_address'),                    value: address,       onChange: setAddress,       req: false },
                { label: t('lm_f_license'),            value: licenseNumber, onChange: setLicenseNumber, req: false },
                { label: t('lm_f_tax'),               value: taxId,         onChange: setTaxId,         req: false },
              ].map(f => (
                <div key={f.label}>
                  <label className="block text-xs font-medium text-on-surface-variant mb-1">{f.label}</label>
                  <input type="text" required={f.req} value={f.value} onChange={e => f.onChange(e.target.value)}
                    className="w-full bg-surface-container border border-outline-variant focus:border-primary rounded-xl px-3 py-2.5 text-sm focus:outline-none" />
                </div>
              ))}

              <div className="grid grid-cols-2 gap-2 pt-1 border-t border-outline-variant">
                <div>
                  <label className="block text-[11px] text-on-surface-variant mb-1">{t('lm_numerals')}</label>
                  <select value={numerals} onChange={e => setNumerals(e.target.value as NumeralsFormat)}
                    className="w-full bg-surface-container border border-outline-variant focus:border-primary rounded-xl px-2 py-2 text-xs focus:outline-none">
                    <option value="western">{t('lm_numerals_western')}</option>
                    <option value="eastern">{t('lm_numerals_eastern')}</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-on-surface-variant mb-1">{t('lm_low_stock_alert')}</label>
                  <input type="number" min={1} value={lowStock} onChange={e => setLowStock(+e.target.value)}
                    className="w-full bg-surface-container border border-outline-variant focus:border-primary rounded-xl px-3 py-2 text-xs focus:outline-none" />
                </div>
              </div>

              <button type="submit" disabled={isLoading}
                className="w-full py-3 rounded-xl bg-primary text-on-primary font-semibold text-sm shadow-lg disabled:opacity-50 active:scale-[0.98] transition mt-2">
                {isLoading ? '...' : t('lm_save_launch')}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};