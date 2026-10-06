// web/src/app/pharmacies/[id]/members/page.tsx (route: /pharmacies/[id]/members — staff list, invitations, role changes)
'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { BottomNav } from '@/components/ui/BottomNav';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import {
  assignPharmacyRole,
  assignPharmacyFixedRole,
  createPharmacyInvitation,
  getPharmacyInvitations,
  getPharmacyRolesOverview,
  getPharmacySummary,
  getStaffList,
  removePharmacyStaff,
  revokePharmacyInvitation,
} from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import { roleLabel } from '@/lib/roleLabel';
import { localeOf } from '@/lib/languages';
import type { PharmacyInvitationSummary, PharmacyRoleOverviewItem, PharmacyStaffMember } from '@/types';

export default function PharmacyMembersPage() {
  const params = useParams();
  const router = useRouter();
  const { t, lang, dir, isRTL } = useLanguage();
  const { toasts, push, dismiss } = useToasts();
  const [removeTargetId, setRemoveTargetId] = useState<number | null>(null);

  const pharmacyId = parseInt(params.id as string, 10);

  const [members, setMembers] = useState<PharmacyStaffMember[]>([]);
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getPharmacySummary>> | null>(null);
  // Roles the signed-in member may hand out (the server decides with `grantable`; the owner may grant all but owner).
  const [grantableRoles, setGrantableRoles] = useState<PharmacyRoleOverviewItem[]>([]);
  const [invitations, setInvitations] = useState<PharmacyInvitationSummary[]>([]);
  const [filter, setFilter] = useState<'all' | 'owner' | 'pharmacist' | 'cashier'>('all');
  const [copied, setCopied] = useState(false);
  const [createdJoinLink, setCreatedJoinLink] = useState('');
  const [inviteRole, setInviteRole] = useState('cashier');
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [maxUses, setMaxUses] = useState(1);
  const [memberRoleValue, setMemberRoleValue] = useState('');
  const [savingInvitation, setSavingInvitation] = useState(false);
  const [pageError, setPageError] = useState('');
  const [selectedMember, setSelectedMember] = useState<PharmacyStaffMember | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    loadData();
  }, [pharmacyId]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [membersData, profileData] = await Promise.all([
        getStaffList(),
        getPharmacySummary(pharmacyId),
      ]);
      setMembers(membersData);
      setProfile(profileData);
      const [rolesResult, invitesResult] = await Promise.allSettled([
        getPharmacyRolesOverview(pharmacyId),
        getPharmacyInvitations(pharmacyId),
      ]);
      const grantable = rolesResult.status === 'fulfilled' ? rolesResult.value.roles.filter((role) => role.grantable) : [];
      setGrantableRoles(grantable);
      // Keep the invitation role valid: fall back to the first role this member may grant.
      setInviteRole((current) => (grantable.length === 0 || grantable.some((role) => role.key === current)
        ? current
        : grantable[0].key));
      setInvitations(invitesResult.status === 'fulfilled' ? invitesResult.value : []);
    } catch (e) {
      setPageError(e instanceof Error ? e.message : t('mb_could_not_load_staff_data'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyLink = async () => {
    if (!createdJoinLink) return;
    await navigator.clipboard?.writeText(createdJoinLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCreateInvitation = async () => {
    setSavingInvitation(true);
    try {
      const payload = inviteRole.startsWith('custom:')
        ? { custom_role_id: Number(inviteRole.slice('custom:'.length)), expires_in_days: expiresInDays, max_uses: maxUses }
        : { fixed_role: inviteRole as 'pharmacist' | 'cashier' | 'viewer', expires_in_days: expiresInDays, max_uses: maxUses };
      const created = await createPharmacyInvitation(pharmacyId, payload);
      setCreatedJoinLink(`${window.location.origin}${created.join_path}`);
      setCopied(false);
      setInvitations(await getPharmacyInvitations(pharmacyId));
    } catch (error) {
      setPageError(error instanceof Error ? error.message : t('mb_could_not_create_invitation'));
    } finally {
      setSavingInvitation(false);
    }
  };

  const handleRevokeInvitation = async (invitationId: number) => {
    try {
      await revokePharmacyInvitation(pharmacyId, invitationId);
      setInvitations(await getPharmacyInvitations(pharmacyId));
    } catch (error) {
      setPageError(error instanceof Error ? error.message : t('mb_could_not_revoke_invitation'));
    }
  };

  const handleAssignRole = async () => {
    if (!selectedMember || selectedMember.role === 'owner' || !memberRoleValue) return;
    try {
      if (memberRoleValue.startsWith('custom:')) {
        await assignPharmacyRole(pharmacyId, selectedMember.id, Number(memberRoleValue.slice('custom:'.length)));
      } else {
        await assignPharmacyFixedRole(pharmacyId, selectedMember.id, memberRoleValue as 'pharmacist' | 'cashier' | 'viewer');
      }
      setSelectedMember(null);
      await loadData();
    } catch (error) {
      // Close the drawer so the error banner at the top of the page is visible.
      setSelectedMember(null);
      setPageError(error instanceof Error ? error.message : t('mb_could_not_change_role'));
    }
  };

  // Opens the in-app confirmation; the removal itself runs in `confirmRemoveMember`.
  const handleRemoveMember = (userId: number) => {
    setRemoveTargetId(userId);
  };

  // Throws on failure so the dialog stays open and shows the error.
  const confirmRemoveMember = async () => {
    if (removeTargetId === null) return;
    await removePharmacyStaff(pharmacyId, removeTargetId);
    setSelectedMember(null);
    await loadData();
    push('success', t('mb_rm_done'));
  };

  // Overview keys are 'pharmacist' | 'cashier' | 'viewer' | 'custom:<id>', the same values the selects use.
  const roleOptions = (currentValue: string) => {
    const options = grantableRoles.map((role) => ({
      value: role.key,
      label: role.kind === 'custom' ? role.name : roleLabel(t, role.key, role.key),
    }));
    // The member's current role stays visible in the select even when this member may not grant it.
    if (selectedMember && !options.some((option) => option.value === currentValue)) {
      options.unshift({ value: currentValue, label: roleLabel(t, selectedMember.role, selectedMember.role_name) });
    }
    return options;
  };

  const filteredMembers = members.filter((m) => {
    if (filter === 'all') return true;
    return m.role === filter;
  });

  return (
    <div className="bg-surface font-body-md text-body-md text-on-surface flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={profile?.pharmacy_name || t('mb_pharmacy_team')}
        subtitle={t('mb_subtitle')}
        showBack={true}
      />

      <main className="flex-1 flex flex-col relative w-full pt-16 pb-24 bg-surface px-margin">
        <div className="flex flex-col w-full pb-6 space-y-4" dir={dir}>
          {pageError && <p role="alert" className="rounded-xl bg-error-container p-3 text-sm text-on-error-container">{pageError}</p>}
          {/* Top Navigation & Context Bar */}
          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label={t('mb_back_to_summary')}
                onClick={() => router.back()}
                className="w-12 h-12 flex items-center justify-center rounded-xl bg-surface-container-lowest text-on-surface shadow-sm hover:bg-surface-container active:scale-95 transition-all"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {isRTL ? 'arrow_forward' : 'arrow_back'}
                </span>
              </button>
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <span className="font-headline-sm text-headline-sm text-primary font-bold">
                    {t('mb_pharmacy_staff')}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed-variant font-label-sm text-label-sm font-bold flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
                    {members.length} {t('mb_members')}
                  </span>
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant">
                  {profile?.pharmacy_name || '...'}
                </span>
              </div>
            </div>
          </div>

          {/* Secure, scoped invitation creation */}
          {profile?.permissions?.includes('manage_staff') && <div className="rounded-xl p-4 bg-gradient-to-br from-surface-container-lowest via-surface-container-low to-surface-container shadow-sm flex flex-col space-y-3 relative overflow-hidden">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-primary-container text-on-primary-container flex items-center justify-center shadow-sm">
                  <span className="material-symbols-outlined text-[26px]">qr_code_scanner</span>
                </div>
                <div className="flex flex-col">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold leading-tight">
                    {t('mb_invite_staff_member')}
                  </h2>
                  <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                    {t('mb_instant_secure_access')}
                  </span>
                </div>
              </div>
            </div>

            <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
              {t('mb_invite_hint')}
            </p>
            <label className="flex flex-col gap-1 font-label-md text-label-md">
              <span>{t('mb_role_on_join')}</span>
              <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)} disabled={grantableRoles.length === 0} className="h-11 rounded-lg bg-surface-container-lowest px-3">
                {grantableRoles.map((role) => <option key={role.key} value={role.key}>{role.kind === 'custom' ? role.name : roleLabel(t, role.key, role.key)}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 font-label-md text-label-md">
                <span>{t('mb_expires_in_days')}</span>
                <input type="number" min={1} max={30} value={expiresInDays} onChange={(event) => setExpiresInDays(Math.max(1, Math.min(30, Number(event.target.value) || 1)))} className="h-11 rounded-lg bg-surface-container-lowest px-3" />
              </label>
              <label className="flex flex-col gap-1 font-label-md text-label-md">
                <span>{t('mb_maximum_uses')}</span>
                <input type="number" min={1} max={50} value={maxUses} onChange={(event) => setMaxUses(Math.max(1, Math.min(50, Number(event.target.value) || 1)))} className="h-11 rounded-lg bg-surface-container-lowest px-3" />
              </label>
            </div>
            <button type="button" disabled={savingInvitation || grantableRoles.length === 0} onClick={() => void handleCreateInvitation()} className="h-11 rounded-lg bg-primary px-4 font-label-lg text-label-lg font-bold text-on-primary disabled:opacity-60">
              {savingInvitation ? t('mb_creating') : t('mb_create_secure_invitation')}
            </button>
            {createdJoinLink && <div className="flex items-center gap-2 rounded-lg bg-surface-container-lowest p-2">
              <span className="min-w-0 flex-1 truncate font-mono text-sm" dir="ltr">{createdJoinLink}</span>
              <button type="button" onClick={() => void handleCopyLink()} className="rounded-lg bg-surface-container px-3 py-2 font-label-sm text-label-sm">
                {copied ? t('mb_copied') : t('mb_copy')}
              </button>
            </div>}
          </div>}

          {profile?.permissions?.includes('manage_staff') && invitations.length > 0 && <section className="rounded-xl bg-surface-container-lowest p-4 shadow-sm">
            <h2 className="mb-3 font-headline-sm text-headline-sm">{t('mb_invitations')}</h2>
            <div className="flex flex-col gap-2">
              {invitations.map((invitation) => <div key={invitation.id} className="flex items-center justify-between gap-3 rounded-lg bg-surface-container-low p-3">
                <div className="min-w-0">
                  <p className="font-label-md text-label-md font-bold">{roleLabel(t, invitation.role, invitation.role_name)}</p>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">{invitation.used_count}/{invitation.max_uses} · {new Date(invitation.expires_at).toLocaleDateString(localeOf(lang))}</p>
                </div>
                {invitation.is_active && <button type="button" onClick={() => void handleRevokeInvitation(invitation.id)} className="shrink-0 rounded-lg bg-error-container px-3 py-2 font-label-sm text-label-sm text-on-error-container">{t('mb_revoke')}</button>}
              </div>)}
            </div>
          </section>}

          {/* Quick Filter Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 -mx-margin px-margin no-scrollbar">
            {[
              { id: 'all' as const, label: t('mb_tab_all').replace('{count}', String(members.length)) },
              { id: 'owner' as const, label: t('hm_role_owner') },
              { id: 'pharmacist' as const, label: t('mb_tab_pharmacists') },
              { id: 'cashier' as const, label: t('mb_tab_cashiers') },
            ].map((tab) => {
              const active = filter === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setFilter(tab.id)}
                  className={`px-4 py-2 rounded-full font-label-sm text-label-sm font-bold shrink-0 transition-all shadow-sm ${
                    active ? 'bg-primary text-on-primary' : 'bg-surface-container-lowest text-on-surface-variant'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Team Member List */}
          <div className="flex flex-col space-y-3">
            {filteredMembers.map((m) => {
              const isOwner = m.role === 'owner';
              return (
                <div
                  key={m.id}
                  className="staff-card bg-surface-container-lowest rounded-xl p-4 shadow-sm flex flex-col space-y-3 transition-all active:scale-[0.99]"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <div className="w-12 h-12 rounded-full bg-primary-container text-on-primary font-headline-sm text-headline-sm flex items-center justify-center font-bold">
                          {m.name.slice(0, 2)}
                        </div>
                        <span className="absolute bottom-0 end-0 w-3.5 h-3.5 rounded-full bg-primary ring-2 ring-surface-container-lowest"></span>
                      </div>
                      <div className="flex flex-col">
                        <div className="flex items-center gap-1.5">
                          <h3 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                            {m.name}
                          </h3>
                          {isOwner && (
                            <span className="material-symbols-outlined text-[18px] text-primary">verified</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`px-2 py-0.5 rounded-md font-label-sm text-label-sm font-bold flex items-center gap-1 ${
                            isOwner ? 'bg-primary-container text-on-primary' : 'bg-surface-container text-primary'
                          }`}>
                            <span className="material-symbols-outlined text-[14px]">badge</span>
                            {roleLabel(t, m.role, m.role_name)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        setSelectedMember(m);
                        setMemberRoleValue(m.custom_role_id ? `custom:${m.custom_role_id}` : m.role);
                      }}
                      aria-label={t('mb_staff_options')}
                      className="w-12 h-12 flex items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container"
                    >
                      <span className="material-symbols-outlined text-[22px]">more_vert</span>
                    </button>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 pt-1 font-label-sm text-label-sm text-on-surface-variant">
                    <div className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-container-low text-primary">
                      <span className="material-symbols-outlined text-[16px]">call</span>
                      <span className="font-mono font-medium" dir="ltr">{m.phone}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </main>

      {/* Interactive Staff Options Drawer */}
      {selectedMember && (
        <div className="fixed inset-0 z-50 bg-inverse-surface/40 backdrop-blur-sm flex flex-col justify-end p-margin animate-in fade-in duration-200">
          <div className="flex-grow w-full" onClick={() => setSelectedMember(null)}></div>
          <div className="w-full bg-surface-container-lowest rounded-2xl p-5 shadow-2xl flex flex-col space-y-4 max-w-lg mx-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-full bg-primary-fixed text-on-primary-fixed flex items-center justify-center">
                  <span className="material-symbols-outlined text-[20px]">manage_accounts</span>
                </div>
                <div className="flex flex-col">
                  <span className="font-headline-sm text-headline-sm text-on-surface font-bold">
                    {selectedMember.name}
                  </span>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">
                    {roleLabel(t, selectedMember.role, selectedMember.role_name)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedMember(null)}
                className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-surface-container text-on-surface-variant"
              >
                <span className="material-symbols-outlined text-[22px]">close</span>
              </button>
            </div>

            <div className="flex flex-col space-y-2 pt-2">
              {profile?.permissions?.includes('manage_staff') && <>
              <label className="flex flex-col gap-1 font-label-md text-label-md">
                <span>{t('mb_member_role')}</span>
                <select value={memberRoleValue} onChange={(event) => setMemberRoleValue(event.target.value)} disabled={selectedMember.role === 'owner'} className="h-11 rounded-lg bg-surface-container-low px-3">
                  {roleOptions(selectedMember.custom_role_id ? `custom:${selectedMember.custom_role_id}` : selectedMember.role).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              {selectedMember.role !== 'owner' && <button type="button" disabled={memberRoleValue === (selectedMember.custom_role_id ? `custom:${selectedMember.custom_role_id}` : selectedMember.role)} onClick={() => void handleAssignRole()} className="h-11 rounded-lg bg-primary px-3 font-label-md text-label-md font-bold text-on-primary disabled:opacity-60">
                {t('mb_save_role')}
              </button>}
              </>}
              {profile?.user_role === 'owner' && <>
              <Link
                href={`/pharmacies/${pharmacyId}/roles`}
                className="w-full h-12 px-3 rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface font-label-lg text-label-lg flex items-center gap-3 transition-colors text-right"
              >
                <div className="w-8 h-8 rounded-lg bg-primary-fixed text-on-primary-fixed flex items-center justify-center">
                  <span className="material-symbols-outlined text-[18px]">vpn_key</span>
                </div>
                <div className="flex flex-col flex-1">
                  <span className="font-bold">{t('mb_edit_roles_scopes')}</span>
                </div>
              </Link>
              {selectedMember.role !== 'owner' && <Link
                href={`/pharmacies/${pharmacyId}/members/${selectedMember.id}`}
                className="w-full h-12 px-3 rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface font-label-lg text-label-lg flex items-center gap-3 transition-colors text-right"
              >
                <div className="w-8 h-8 rounded-lg bg-primary-fixed text-on-primary-fixed flex items-center justify-center">
                  <span className="material-symbols-outlined text-[18px]">schedule</span>
                </div>
                <span className="flex-1 font-bold">{t('mb_schedule_pay_activity')}</span>
              </Link>}
              </>}

              {selectedMember.role !== 'owner' && (
                <button
                  type="button"
                  onClick={() => handleRemoveMember(selectedMember.id)}
                  className="w-full h-12 px-3 rounded-xl bg-error-container text-on-error-container font-label-lg text-label-lg flex items-center gap-3 transition-colors text-right hover:opacity-90"
                >
                  <div className="w-8 h-8 rounded-lg bg-tertiary-container text-on-tertiary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[18px]">block</span>
                  </div>
                  <div className="flex flex-col flex-1">
                    <span className="font-bold text-error">
                      {t('mb_revoke_staff_access')}
                    </span>
                  </div>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={removeTargetId !== null}
        variant="destructive"
        title={t('mb_rm_title')}
        description={t('mb_confirm_revoke')}
        confirmLabel={t('mb_rm_confirm')}
        cancelLabel={t('mb_rm_cancel')}
        retryLabel={t('mb_rm_retry')}
        busyLabel={t('mb_rm_busy')}
        fallbackError={t('mb_remove_failed')}
        onConfirm={confirmRemoveMember}
        onClose={() => setRemoveTargetId(null)}
      />
      <ToastStack toasts={toasts} onDismiss={dismiss} dismissLabel={t('mb_toast_dismiss')} />

      <BottomNav />
    </div>
  );
}