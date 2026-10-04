// web/src/app/pharmacies/page.tsx (route: /pharmacies — "My Pharmacies" hub, rebuilt in Session 105; functional, not a Stitch design)
'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { getMyPharmacies, createMyPharmacy, selectMyPharmacy, getPersonalAccount, acceptPharmacyInvitation, InvitationRefusedError } from '@/lib/api';
import { isAuthenticated, parseToken, saveAuth } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { roleLabel } from '@/lib/roleLabel';
import { capturePendingInvite, clearPendingInvite } from '@/lib/pendingInvite';
import type { MyPharmaciesResponse } from '@/types';

export default function PharmaciesHubPage() {
  const router = useRouter();
  const { t, dir } = useLanguage();

  const [data, setData] = useState<MyPharmaciesResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [enteringId, setEnteringId] = useState<number | null>(null);
  const [enterError, setEnterError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const currentPharmacyId = parseToken()?.pharmacyId ?? null;
  // React strict mode runs effects twice in development; a ref makes sure the
  // invitation token is sent to the server only once.
  const inviteHandled = useRef(false);

  const load = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setData(await getMyPharmacies());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('ph_could_not_load_pharmacies'));
    } finally {
      setIsLoading(false);
    }
  };

  // The invitation token lives in sessionStorage from the moment the link was opened
  // (lib/pendingInvite.ts); a link opened here directly (#invite= or the old ?invite=)
  // is captured and removed from the address bar by capturePendingInvite.
  // Accept the invitation, switch to the pharmacy-scoped session and open the pharmacy.
  const acceptInvite = async (token: string) => {
    setIsLoading(true);
    setEnterError(null);
    try {
      const res = await acceptPharmacyInvitation(token);
      clearPendingInvite();
      const userRaw = sessionStorage.getItem('roshetta_user');
      const currentUser = userRaw ? JSON.parse(userRaw) : await getPersonalAccount();
      saveAuth({ token: res.token, user: currentUser, role: res.role, pharmacy: res.pharmacy ?? { id: res.pharmacy_id } });
      router.replace('/');
      return;
    } catch (error) {
      // Only a refusal from the server spends the token. A dropped connection keeps it,
      // so a reload tries again instead of losing the invitation.
      if (error instanceof InvitationRefusedError) clearPendingInvite();
      setEnterError(error instanceof Error ? error.message : t('ph_could_not_open_pharmacy'));
    }
    await load();
  };

  useEffect(() => {
    const invite = capturePendingInvite();
    if (!isAuthenticated()) {
      // The token stays in sessionStorage through the sign-in or registration.
      router.replace('/onboarding');
      return;
    }
    if (invite) {
      if (!inviteHandled.current) {
        inviteHandled.current = true;
        void acceptInvite(invite);
      }
      return;
    }
    void load();
  }, []);

  // Same hand-over as the details page: the server issues a pharmacy-scoped token.
  const enter = async (pharmacyId: number) => {
    setEnteringId(pharmacyId);
    setEnterError(null);
    try {
      const res = await selectMyPharmacy(pharmacyId);
      const userRaw = sessionStorage.getItem('roshetta_user');
      const currentUser = userRaw ? JSON.parse(userRaw) : await getPersonalAccount();
      saveAuth({ token: res.token, user: currentUser, role: res.role, pharmacy: res.pharmacy });
      router.push('/');
    } catch (error) {
      setEnterError(error instanceof Error ? error.message : t('ph_could_not_open_pharmacy'));
      setEnteringId(null);
    }
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isCreating) return;
    const cleanName = name.trim();
    if (!cleanName) {
      setCreateError(t('ph_please_enter_pharmacy_name'));
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      const res = await createMyPharmacy({
        pharmacy_name: cleanName,
        address: address.trim() || null,
        phone: phone.trim() || null,
      });
      await enter(res.pharmacy.id);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : t('ph_could_not_create_pharmacy'));
    } finally {
      setIsCreating(false);
    }
  };

  const atLimit = !!data && data.owned_count >= data.owned_limit;
  const fill = (text: string, vars: Record<string, number>) =>
    text.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? ''));

  const inputClass =
    'h-12 w-full rounded-xl border border-outline-variant bg-surface-container-lowest px-3 font-body-md text-body-md text-on-surface focus:border-primary focus:outline-none';

  return (
    <div className="bg-surface font-body-md text-on-surface antialiased flex flex-col min-h-screen">
      <TopHeader pharmacyName={t('my_pharmacies')} subtitle={t('ph_choose_workspace')} />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-12 bg-surface">
        <div className="flex flex-col w-full max-w-2xl mx-auto px-margin-mobile pt-space-md gap-space-md" dir={dir}>
          <div className="flex items-center justify-between gap-2">
            <h1 className="font-headline-sm text-headline-sm text-on-surface">{t('ph_your_pharmacies')}</h1>
            {data && (
              <span className="font-label-md text-label-md text-on-surface-variant">
                {fill(t('ph_owned_count'), { count: data.owned_count, limit: data.owned_limit })}
              </span>
            )}
          </div>

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

          {enterError && (
            <p role="alert" className="rounded-xl bg-error-container p-3 text-sm text-on-error-container">{enterError}</p>
          )}

          {data && data.pharmacies.length === 0 && (
            <div className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-1">
              <span className="font-label-lg text-label-lg text-on-surface">{t('ph_no_pharmacies_yet')}</span>
              <span className="font-body-sm text-body-sm text-on-surface-variant">{t('ph_empty_hint')}</span>
            </div>
          )}

          {data?.pharmacies.map((p) => (
            <div key={p.id} className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-3">
              <div className="flex items-start justify-between gap-2">
                <Link href={`/pharmacies/${p.id}`} className="min-w-0 flex flex-col gap-1">
                  <span className="font-headline-sm text-headline-sm text-on-surface truncate">{p.pharmacy_name}</span>
                  {p.address && <span className="font-body-sm text-body-sm text-on-surface-variant truncate">{p.address}</span>}
                </Link>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="rounded-full bg-primary-container px-2 py-0.5 font-label-sm text-label-sm text-on-primary-container">
                    {p.is_owner ? t('hm_role_owner') : roleLabel(t, undefined, p.role_name)}
                  </span>
                  {currentPharmacyId === p.id && (
                    <span className="font-label-sm text-label-sm text-primary">{t('ph_open_now')}</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void enter(p.id)}
                disabled={enteringId !== null}
                className="h-12 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg disabled:opacity-60"
              >
                {t('ph_enter')}
              </button>
            </div>
          ))}

          {data && atLimit && (
            <p className="rounded-xl bg-surface-container-low p-3 text-sm text-on-surface-variant">
              {fill(t('ph_limit_reached'), { limit: data.owned_limit })}
            </p>
          )}

          {data && !atLimit && (
            <form onSubmit={handleCreate} className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-3">
              <h2 className="font-label-lg text-label-lg text-on-surface">{t('ph_create_new_pharmacy')}</h2>
              <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder={t('st_pharmacy_name')} aria-label={t('st_pharmacy_name')} maxLength={150} />
              <input className={inputClass} value={address} onChange={(e) => setAddress(e.target.value)} placeholder={t('ph_address_optional')} aria-label={t('ph_address_optional')} />
              <input className={inputClass} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder={t('ph_phone_optional')} aria-label={t('ph_phone_optional')} inputMode="tel" />
              {createError && (
                <p role="alert" className="rounded-lg bg-error-container p-2 text-sm text-on-error-container">{createError}</p>
              )}
              <button type="submit" disabled={isCreating || enteringId !== null} className="h-12 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg disabled:opacity-60">
                {isCreating ? t('ph_creating') : t('ph_create_open')}
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}