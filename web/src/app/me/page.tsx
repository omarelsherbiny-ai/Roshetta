// web/src/app/me/page.tsx (route: /me — personal profile editor, photo upload, language, sign out)
'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import { getPersonalAccount, updatePersonalAccount, uploadMyPhoto, loadMyPhotoObjectUrl, logoutSession } from '@/lib/api';
import { isAuthenticated, clearAuth } from '@/lib/auth';
import { useLanguage, translations } from '@/lib/i18n';
import { PersonalUser } from '@/types';

export default function MyProfilePage() {
  const router = useRouter();
  const { t, lang, dir, isRTL, setLanguage, languages } = useLanguage();

  const [user, setUser] = useState<PersonalUser | null>(null);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [fullname, setFullname] = useState('');
  const [location, setLocation] = useState('');
  const [birthdate, setBirthdate] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    loadProfile();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setAvatarSrc(null);
    if (!user?.photo_url) return;
    if (user.photo_url.startsWith('https://')) {
      setAvatarSrc(user.photo_url);
      return;
    }
    void loadMyPhotoObjectUrl(user.photo_url).then((url) => {
      objectUrl = url;
      if (cancelled) URL.revokeObjectURL(url);
      else setAvatarSrc(url);
    }).catch(() => {
      if (!cancelled) setAvatarSrc(null);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [user?.photo_url]);

  const loadProfile = async () => {
    setIsLoading(true);
    try {
      const data = await getPersonalAccount();
      setUser(data);
      setFullname(data.name || '');
      setLocation(data.location || '');
      setBirthdate(data.birth_date || '');
    } catch (e: any) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updated = await updatePersonalAccount({
        name: fullname.trim() || undefined,
        location: location.trim() || undefined,
        birth_date: birthdate || undefined,
      });
      setUser(updated.user);
      push('success', t('me_saved'));
    } catch (err) {
      push('error', err instanceof Error && err.message ? err.message : t('me_save_failed'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await uploadMyPhoto(file);
      if (res.photo_url && user) {
        setUser({ ...user, photo_url: res.photo_url });
        push('success', t('me_photo_updated'));
      }
    } catch (err) {
      push('error', err instanceof Error && err.message ? err.message : t('me_upload_failed'));
    } finally {
      e.target.value = '';
    }
  };

  const handleLogout = async () => {
    try {
      await logoutSession();
    } catch {}
    clearAuth();
    router.replace('/onboarding');
  };

  return (
    <div className="bg-surface text-on-surface flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={user?.name || t('me_my_account')}
        subtitle={t('me_my_profile')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-28 bg-surface px-margin">
        <div className="flex flex-col w-full pb-8 select-none" dir={dir}>
          {/* Top Navigation / Sub-header bar */}
          <div className="flex items-center justify-between py-space-sm mb-space-md">
            <div className="flex items-center gap-space-sm">
              <button
                type="button"
                aria-label={t('back')}
                onClick={() => router.back()}
                className="w-touch-target-min h-touch-target-min rounded-full flex items-center justify-center bg-surface-container text-on-surface hover:bg-surface-container-high transition-colors active:scale-95 shadow-sm"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {isRTL ? 'arrow_forward' : 'arrow_back'}
                </span>
              </button>
              <h1 className="font-headline-md text-headline-md text-on-surface font-bold leading-tight">
                {t('me_my_profile')}
              </h1>
            </div>
          </div>

          {/* User Avatar Profile Summary Card */}
          <div className="flex flex-col items-center bg-surface-container-lowest p-space-lg rounded-2xl shadow-sm mb-space-lg relative overflow-hidden">
            <div className="relative w-24 h-24 mb-space-sm flex items-center justify-center">
              <div className="w-24 h-24 rounded-full bg-surface-container-high flex items-center justify-center shadow-md overflow-hidden text-primary">
                {avatarSrc ? (
                  <img src={avatarSrc} alt={t('me_photo_alt')} className="w-full h-full object-cover" />
                ) : (
                  <span className="material-symbols-outlined text-[54px] select-none">person</span>
                )}
              </div>
              <label
                htmlFor="avatar-input"
                title={t('me_change_photo')}
                className="absolute bottom-0 right-0 w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center shadow-md cursor-pointer hover:bg-primary-container active:scale-90 transition-all touch-manipulation"
              >
                <span className="material-symbols-outlined text-[18px]">photo_camera</span>
                <input
                  id="avatar-input"
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleAvatarUpload}
                />
              </label>
            </div>
            <h2 className="font-headline-sm text-headline-sm text-on-surface font-extrabold text-center">
              {user?.name || (isLoading ? '...' : t('me_user_fallback'))}
            </h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant font-medium mt-1 dir-ltr text-center">
              {user?.phone || ''}
            </p>

            <div className="flex items-center gap-space-sm mt-3 pt-3 border-t border-surface-container-high w-full justify-center">
              <div className="flex items-center gap-1 text-on-surface-variant font-label-sm text-label-sm">
                <span className="material-symbols-outlined text-[16px] text-secondary">local_pharmacy</span>
                <span>{user?.location || t('me_location_not_set')}</span>
              </div>
            </div>
          </div>

          {/* Form Fields Container */}
          <form className="flex flex-col gap-space-md mb-space-lg" onSubmit={(e) => { e.preventDefault(); handleSave(); }}>
            {/* Field 1: full name */}
            <div className="flex flex-col gap-1.5">
              <label className="font-label-md text-label-md text-on-surface font-bold flex items-center gap-1.5" htmlFor="fullname">
                <span className="material-symbols-outlined text-[18px] text-primary">badge</span>
                <span>{t('me_f_fullname')}</span>
              </label>
              <div className="relative flex items-center bg-surface-container-lowest rounded-xl shadow-sm focus-within:shadow-md transition-shadow">
                <div className={`absolute ${isRTL ? 'right-3.5' : 'left-3.5'} flex items-center pointer-events-none text-on-surface-variant`}>
                  <span className="material-symbols-outlined text-[20px]">person_outline</span>
                </div>
                <input
                  id="fullname"
                  name="fullname"
                  type="text"
                  value={fullname}
                  onChange={(e) => setFullname(e.target.value)}
                  placeholder={t('me_ph_fullname')}
                  className={`w-full h-touch-target-min ${isRTL ? 'pr-11 pl-4' : 'pl-11 pr-4'} rounded-xl bg-transparent font-body-md text-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none`}
                />
              </div>
            </div>

            {/* Field 2: location / city */}
            <div className="flex flex-col gap-1.5">
              <label className="font-label-md text-label-md text-on-surface font-bold flex items-center gap-1.5" htmlFor="location">
                <span className="material-symbols-outlined text-[18px] text-primary">location_city</span>
                <span>{t('me_f_location')}</span>
              </label>
              <div className="relative flex items-center bg-surface-container-lowest rounded-xl shadow-sm focus-within:shadow-md transition-shadow">
                <div className={`absolute ${isRTL ? 'right-3.5' : 'left-3.5'} flex items-center pointer-events-none text-on-surface-variant`}>
                  <span className="material-symbols-outlined text-[20px]">location_on</span>
                </div>
                <input
                  id="location"
                  name="location"
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder={t('me_ph_location')}
                  className={`w-full h-touch-target-min ${isRTL ? 'pr-11 pl-4' : 'pl-11 pr-4'} rounded-xl bg-transparent font-body-md text-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none`}
                />
              </div>
            </div>

            {/* Field 3: birth date */}
            <div className="flex flex-col gap-1.5">
              <label className="font-label-md text-label-md text-on-surface font-bold flex items-center gap-1.5" htmlFor="birthdate">
                <span className="material-symbols-outlined text-[18px] text-primary">event</span>
                <span>{t('me_f_birthdate')}</span>
              </label>
              <div className="relative flex items-center bg-surface-container-lowest rounded-xl shadow-sm focus-within:shadow-md transition-shadow">
                <div className={`absolute ${isRTL ? 'right-3.5' : 'left-3.5'} flex items-center pointer-events-none text-on-surface-variant`}>
                  <span className="material-symbols-outlined text-[20px]">calendar_today</span>
                </div>
                <input
                  id="birthdate"
                  name="birthdate"
                  type="date"
                  value={birthdate}
                  onChange={(e) => setBirthdate(e.target.value)}
                  className={`w-full h-touch-target-min ${isRTL ? 'pr-11 pl-4' : 'pl-11 pr-4'} rounded-xl bg-transparent font-body-md text-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none`}
                />
              </div>
            </div>

            {/* Field 4: application language (segmented control, one button per registry language) */}
            <div className="flex flex-col gap-1.5">
              <span className="font-label-md text-label-md text-on-surface font-bold flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[18px] text-primary">translate</span>
                <span>{t('me_f_language')}</span>
              </span>
              <div className="bg-surface-container-lowest p-1 rounded-xl shadow-sm flex items-center justify-between gap-1 h-touch-target-min" role="group">
                {languages.map(({ code }) => {
                  const active = code === lang;
                  return (
                    <button
                      key={code}
                      type="button"
                      aria-pressed={active}
                      onClick={() => { if (!active) setLanguage(code); }}
                      className={`flex-1 h-full rounded-lg font-label-lg text-label-lg flex items-center justify-center gap-1.5 transition-all shadow-sm ${
                        active ? 'bg-primary text-on-primary' : 'bg-transparent text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      {active && <span className="material-symbols-outlined text-[18px]">check</span>}
                      <span>{translations[code]?.me_lang_name ?? code}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </form>

          {/* Bottom Action Buttons */}
          <div className="flex flex-col gap-space-sm w-full">
            <button
              id="save-button"
              type="button"
              disabled={isSaving}
              onClick={handleSave}
              className="w-full h-touch-target-min bg-primary text-on-primary rounded-xl font-label-lg text-label-lg flex items-center justify-center gap-space-xs shadow-md hover:bg-primary-container active:scale-[0.98] transition-all touch-manipulation disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-[22px]">
                {isSaving ? 'sync' : 'check'}
              </span>
              <span>{isSaving ? t('cat_saving') : t('pf_save_changes')}</span>
            </button>

            <button
              type="button"
              onClick={() => setSignOutOpen(true)}
              className="w-full h-touch-target-min rounded-xl bg-error-container/20 text-error font-label-lg text-label-lg flex items-center justify-center gap-space-xs hover:bg-error-container/30 active:scale-[0.98] transition-all touch-manipulation"
            >
              <span className="material-symbols-outlined text-[22px]">logout</span>
              <span>{t('me_sign_out')}</span>
            </button>
          </div>
        </div>
      </main>

      <BottomNav />

      <ToastStack toasts={toasts} onDismiss={dismiss} dismissLabel={t('rs_dismiss')} />
      <ConfirmDialog
        open={signOutOpen}
        title={t('me_signout_title')}
        description={t('me_confirm_signout')}
        confirmLabel={t('me_sign_out')}
        cancelLabel={t('cancel')}
        retryLabel={t('retry')}
        busyLabel={t('se_signout_working')}
        fallbackError={t('ob_request_failed')}
        variant="destructive"
        onConfirm={handleLogout}
        onClose={() => setSignOutOpen(false)}
      />
    </div>
  );
}