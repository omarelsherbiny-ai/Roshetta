// web/src/app/pharmacies/[id]/roles/page.tsx (route: /pharmacies/[id]/roles — custom role builder)
'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { TopHeader } from '@/components/ui/TopHeader';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ToastStack, useToasts } from '@/components/ui/Toast';
import {
  getPharmacyRoles,
  createPharmacyRole,
  updatePharmacyRole,
  deactivatePharmacyRole,
  selectMyPharmacy,
  getPersonalAccount,
} from '@/lib/api';
import { isAuthenticated, parseToken, saveAuth } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';
import type { PharmacyRoleDefinition } from '@/types';

// Texts live in the dictionaries; the server knows the scopes only by their ids.
const ALL_SCOPES = [
  { id: 'log_sale', icon: 'point_of_sale', titleKey: 'rl_scope_log_sale_title', descKey: 'rl_scope_log_sale_desc' },
  { id: 'log_expense', icon: 'receipt_long', titleKey: 'rl_scope_log_expense_title', descKey: 'rl_scope_log_expense_desc' },
  { id: 'log_restock', icon: 'add_shopping_cart', titleKey: 'rl_scope_log_restock_title', descKey: 'rl_scope_log_restock_desc' },
  { id: 'view_inventory', icon: 'search', titleKey: 'rl_scope_view_inventory_title', descKey: 'rl_scope_view_inventory_desc' },
  { id: 'manage_inventory', icon: 'inventory_2', titleKey: 'rl_scope_manage_inventory_title', descKey: 'rl_scope_manage_inventory_desc' },
  { id: 'view_reports', icon: 'bar_chart', titleKey: 'rl_scope_view_reports_title', descKey: 'rl_scope_view_reports_desc' },
  { id: 'scan_prescription', icon: 'prescriptions', titleKey: 'rl_scope_scan_prescription_title', descKey: 'rl_scope_scan_prescription_desc' },
  { id: 'view_audit', icon: 'history', titleKey: 'rl_scope_view_audit_title', descKey: 'rl_scope_view_audit_desc' },
  { id: 'view_staff_activity', icon: 'person_search', titleKey: 'rl_scope_view_staff_activity_title', descKey: 'rl_scope_view_staff_activity_desc' },
  { id: 'manage_staff', icon: 'badge', titleKey: 'rl_scope_manage_staff_title', descKey: 'rl_scope_manage_staff_desc' },
  { id: 'edit_settings', icon: 'tune', titleKey: 'rl_scope_edit_settings_title', descKey: 'rl_scope_edit_settings_desc' },
  { id: 'manage_payables', icon: 'account_balance_wallet', titleKey: 'rl_scope_manage_payables_title', descKey: 'rl_scope_manage_payables_desc' },
] as const;

const ROLE_SUGGESTION_KEYS = ['rl_sugg_trainee', 'rl_sugg_inventory', 'rl_sugg_pos', 'rl_sugg_procurement'] as const;

export default function RoleBuilderPage() {
  const params = useParams();
  const router = useRouter();
  const { t, dir, isRTL } = useLanguage();

  const pharmacyId = parseInt(params.id as string, 10);

  const [roleTitle, setRoleTitle] = useState('');
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
  const [roles, setRoles] = useState<PharmacyRoleDefinition[]>([]);
  const [editingRoleId, setEditingRoleId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [roleToDeactivate, setRoleToDeactivate] = useState<PharmacyRoleDefinition | null>(null);
  const { toasts, push, dismiss } = useToasts();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/onboarding');
      return;
    }
    if (Number.isNaN(pharmacyId)) {
      router.replace('/pharmacies');
      return;
    }
    void loadRoles();
  }, []);

  // Role endpoints need a pharmacy-scoped token. An account-scoped session (for example right
  // after creating a pharmacy, before pressing Enter on its page) is switched into this pharmacy
  // first, the same way the pharmacy page's Enter button does it. The server still checks membership.
  const ensurePharmacyScope = async () => {
    if (parseToken()?.pharmacyId === pharmacyId) return;
    const res = await selectMyPharmacy(pharmacyId);
    const userRaw = sessionStorage.getItem('roshetta_user');
    const currentUser = userRaw ? JSON.parse(userRaw) : await getPersonalAccount();
    saveAuth({ token: res.token, user: currentUser, role: res.role, pharmacy: res.pharmacy });
  };

  const loadRoles = async () => {
    try {
      await ensurePharmacyScope();
      const result = await getPharmacyRoles(pharmacyId);
      setRoles(result.roles);
      setLoadError('');
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('rl_could_not_load_roles'));
    }
  };

  const resetForm = () => {
    setEditingRoleId(null);
    setRoleTitle('');
    setSelectedScopes([]);
  };

  const editRole = (role: PharmacyRoleDefinition) => {
    setEditingRoleId(role.id);
    setRoleTitle(role.name);
    setSelectedScopes(role.scopes);
    setSavedSuccess(false);
  };

  const toggleScope = (scopeId: string) => {
    setSavedSuccess(false);
    setSelectedScopes((prev) =>
      prev.includes(scopeId) ? prev.filter((id) => id !== scopeId) : [...prev, scopeId]
    );
  };

  const toggleAllScopes = () => {
    setSavedSuccess(false);
    if (selectedScopes.length === ALL_SCOPES.length) {
      setSelectedScopes([]);
    } else {
      setSelectedScopes(ALL_SCOPES.map((s) => s.id));
    }
  };

  const handleSaveRole = async () => {
    if (!roleTitle.trim()) {
      push('warning', t('rl_please_enter_role_name'));
      return;
    }
    if (selectedScopes.length === 0) {
      push('warning', t('rl_please_select_at_least_one'));
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        name: roleTitle.trim(),
        scopes: selectedScopes,
      };
      if (editingRoleId) await updatePharmacyRole(pharmacyId, editingRoleId, payload);
      else await createPharmacyRole(pharmacyId, payload);
      setSavedSuccess(true);
      resetForm();
      await loadRoles();
      setIsSaving(false);
      setTimeout(() => setSavedSuccess(false), 1600);
    } catch (err) {
      push('error', err instanceof Error && err.message ? err.message : t('rl_save_failed'));
      setIsSaving(false);
    }
  };

  // Runs inside ConfirmDialog: a thrown error keeps the dialog open and shows the message with Retry.
  const handleDeactivateRole = async () => {
    const role = roleToDeactivate;
    if (!role) return;
    await deactivatePharmacyRole(pharmacyId, role.id);
    if (editingRoleId === role.id) resetForm();
    await loadRoles();
  };

  return (
    <div className="bg-surface font-body-md text-on-surface antialiased flex flex-col min-h-screen">
      <TopHeader
        pharmacyName={t('rl_new_role')}
        subtitle={t('rl_subtitle')}
        showBack={true}
      />

      <main className="flex flex-col relative w-full pt-16 pb-safe bg-surface min-h-screen">
        <div className="flex flex-col w-full pb-32" dir={dir}>
          <section className="px-margin-mobile pt-space-md" aria-labelledby="existing-roles-heading">
            <h2 id="existing-roles-heading" className="font-headline-sm text-headline-sm mb-3">
              {t('rl_existing_roles')}
            </h2>
            {loadError && <p role="alert" className="mb-3 rounded-lg bg-error-container p-3 text-on-error-container">{loadError}</p>}
            <div className="flex flex-col gap-2">
              {roles.map((role) => (
                <div key={role.id} className="flex items-center justify-between gap-3 rounded-xl bg-surface-container-lowest p-3 shadow-sm">
                  <div className="min-w-0">
                    <p className="font-label-lg text-label-lg font-bold truncate">{role.name}</p>
                    <p className="font-body-sm text-body-sm text-on-surface-variant">
                      {t('rl_scope_count').replace('{scopes}', String(role.scopes.length)).replace('{members}', String(role.assigned_count))}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button type="button" onClick={() => editRole(role)} className="rounded-lg bg-surface-container px-3 py-2 font-label-md text-label-md">
                      {t('edit')}
                    </button>
                    <button type="button" onClick={() => setRoleToDeactivate(role)} className="rounded-lg bg-error-container px-3 py-2 font-label-md text-label-md text-on-error-container">
                      {t('rl_remove')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Top Context Card */}
          <div className="px-margin-mobile pt-space-md">
            <div className="bg-surface-container-low rounded-xl p-space-md shadow-sm relative overflow-hidden">
              <div className="absolute -left-6 -bottom-6 w-24 h-24 rounded-full bg-primary-fixed/30 pointer-events-none"></div>
              <div className="flex items-start gap-space-sm relative z-10">
                <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shrink-0 shadow-sm text-on-primary">
                  <span className="material-symbols-outlined text-[22px]">admin_panel_settings</span>
                </div>
                <div className="flex flex-col">
                  <h2 className="font-headline-sm text-headline-sm text-on-surface">
                    {t('rl_role_scopes_privileges')}
                  </h2>
                  <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5 leading-relaxed">
                    {t('rl_intro')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Role Details Input Section */}
          <div className="px-margin-mobile mt-space-md">
            <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col gap-space-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-space-xs">
                  <label className="font-label-lg text-label-lg text-on-surface" htmlFor="role-title-input">
                    {editingRoleId ? t('rl_edit_role_name') : t('rl_role_title')}
                  </label>
                  <span className="text-error font-bold text-label-sm">*</span>
                </div>
                <span className="bg-primary-container/15 text-primary font-label-sm text-label-sm px-2.5 py-0.5 rounded-full font-bold">
                  {t('rl_required')}
                </span>
              </div>

              {/* Input Field */}
              <div className="relative flex items-center">
                <input
                  id="role-title-input"
                  type="text"
                  value={roleTitle}
                  onChange={(e) => { setRoleTitle(e.target.value); setSavedSuccess(false); }}
                  placeholder={t('rl_title_placeholder')}
                  className={`w-full bg-surface-container-low text-on-surface placeholder:text-outline font-body-md text-body-md rounded-lg py-3.5 ${
                    isRTL ? 'pr-12 pl-4' : 'pl-12 pr-4'
                  } focus:outline-none focus:bg-surface-container-lowest transition-colors shadow-inner`}
                />
                <div className={`absolute ${isRTL ? 'right-3.5' : 'left-3.5'} flex items-center pointer-events-none text-primary`}>
                  <span className="material-symbols-outlined text-[22px]">badge</span>
                </div>
              </div>

              {/* Quick Suggestion Chips */}
              <div className="flex flex-col gap-1.5 pt-1">
                <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                  {t('rl_quick_role_suggestions')}
                </span>
                <div className="flex items-center gap-2 overflow-x-auto py-1 no-scrollbar -mx-1 px-1">
                  {ROLE_SUGGESTION_KEYS.map((suggKey) => (                    <button
                      key={suggKey}
                      type="button"
                      onClick={() => setRoleTitle(t(suggKey))}
                      className="shrink-0 h-8 px-3 rounded-full bg-surface-container hover:bg-surface-container-high active:scale-95 text-on-surface font-label-sm text-label-sm transition-all"
                    >
                      {t(suggKey)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Permissions Header & Controls */}
          <div className="px-margin-mobile mt-space-lg flex items-center justify-between">
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <h3 className="font-headline-sm text-headline-sm text-on-surface">
                  {t('rl_assigned_scopes')}
                </h3>
                <span className="bg-primary text-on-primary font-label-sm text-label-sm px-2 py-0.5 rounded-full font-bold">
                  {t('rl_selected_of_total').replace('{selected}', String(selectedScopes.length)).replace('{total}', String(ALL_SCOPES.length))}
                </span>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
                {t('rl_pick_hint')}
              </p>
            </div>
            <button
              type="button"
              onClick={toggleAllScopes}
              className="h-9 px-3 rounded-lg bg-surface-container-highest active:bg-surface-dim text-primary font-label-md text-label-md flex items-center gap-1 shadow-sm transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">done_all</span>
              <span>
                {selectedScopes.length === ALL_SCOPES.length
                  ? t('rl_deselect_all')
                  : t('rl_select_all')}
              </span>
            </button>
          </div>

          {/* 2-Column Permissions Grid */}
          <div className="px-margin-mobile mt-space-sm grid grid-cols-2 gap-gutter-mobile">
            {ALL_SCOPES.map((scope) => {
              const isChecked = selectedScopes.includes(scope.id);
              return (
                <button
                  type="button"
                  aria-pressed={isChecked}
                  key={scope.id}
                  onClick={() => toggleScope(scope.id)}
                  className={`scope-card relative cursor-pointer select-none text-start bg-surface-container-lowest rounded-xl p-3.5 shadow-sm flex flex-col justify-between transition-all duration-200 ${
                    isChecked ? '' : 'opacity-70'
                  }`}
                >
                  <div className="flex items-start justify-between w-full">
                    <div
                      className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-colors ${
                        isChecked ? 'bg-primary-fixed text-primary' : 'bg-surface-container-high text-on-surface-variant'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[20px]">{scope.icon}</span>
                    </div>
                    <div
                      className={`w-6 h-6 rounded-md flex items-center justify-center transition-all ${
                        isChecked ? 'bg-primary text-on-primary shadow-sm scale-105' : 'bg-surface-container-highest text-transparent'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[16px] font-bold">check</span>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-col">
                    <span className="font-label-lg text-label-lg text-on-surface font-bold">
                      {t(scope.titleKey)}
                    </span>
                    <span className="font-body-sm text-body-sm text-on-surface-variant mt-0.5 line-clamp-2 leading-tight">
                      {t(scope.descKey)}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Security Compliance Banner */}
          <div className="px-margin-mobile mt-space-md">
            <div className="bg-secondary-fixed/50 rounded-xl p-space-sm flex items-start gap-space-xs text-on-secondary-fixed">
              <div className="w-7 h-7 rounded-full bg-secondary-container flex items-center justify-center shrink-0 mt-0.5 text-on-secondary-container">
                <span className="material-symbols-outlined text-[17px]">verified_user</span>
              </div>
              <div className="flex flex-col">
                <span className="font-label-md text-label-md font-bold">
                  {t('rl_compliance_title')}
                </span>
                <p className="font-body-sm text-body-sm text-on-secondary-container mt-0.5 leading-relaxed">
                  {t('rl_owner_only_note')}
                </p>
              </div>
            </div>
          </div>

          {/* Sticky Bottom Action Tray */}
          <div className="fixed bottom-0 right-0 left-0 z-40 bg-surface/90 backdrop-blur-md px-margin-mobile pt-3 pb-safe shadow-[0_-4px_20px_rgba(26,36,32,0.08)]">
            <div className="flex flex-col gap-2 max-w-md mx-auto">
              <button
                type="button"
                disabled={isSaving}
                onClick={handleSaveRole}
                className="w-full h-[52px] bg-primary active:bg-primary-container text-on-primary rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 shadow-md transition-all active:scale-[0.98] disabled:opacity-75"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {savedSuccess ? 'verified' : isSaving ? 'sync' : 'task_alt'}
                </span>
                <span>
                  {savedSuccess
                    ? t('rl_role_saved')
                    : isSaving
                    ? t('rl_saving')
                    : (editingRoleId ? t('rl_save_changes') : t('rl_save_authorize'))}
                </span>
              </button>
              {editingRoleId && <button type="button" onClick={resetForm} className="w-full h-10 flex items-center justify-center font-label-lg text-label-lg text-on-surface-variant">
                {t('rl_cancel_editing')}
              </button>}
              <button
                type="button"
                onClick={() => router.back()}
                className="w-full h-10 flex items-center justify-center font-label-lg text-label-lg text-on-surface-variant hover:text-error active:opacity-70 transition-colors"
              >
                {t('rl_cancel_go_back')}
              </button>
            </div>
          </div>
        </div>
      </main>

      <ToastStack toasts={toasts} onDismiss={dismiss} dismissLabel={t('rs_dismiss')} />
      <ConfirmDialog
        open={roleToDeactivate !== null}
        title={t('rl_deactivate_title')}
        description={t('rl_confirm_deactivate').replace('{name}', String(roleToDeactivate?.name ?? ''))}
        confirmLabel={t('rl_remove')}
        cancelLabel={t('cancel')}
        retryLabel={t('retry')}
        busyLabel={t('rl_deactivating')}
        fallbackError={t('rl_could_not_deactivate_role')}
        variant="destructive"
        onConfirm={handleDeactivateRole}
        onClose={() => setRoleToDeactivate(null)}
      />
    </div>
  );
}